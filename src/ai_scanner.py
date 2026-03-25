"""AI-based privacy scanner.

Orchestrates LLM providers to detect privacy-sensitive data elements in source
files. Provider-specific call logic lives in :mod:`src.providers`; response
parsing lives in :mod:`src.ai_parser`.
"""

import os
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from loguru import logger

from .ai_parser import parse_llm_response
from .providers import call_bedrock, call_ollama, call_openai, list_ollama_models
from .utils import (
    get_bedrock_access_key_id,
    get_bedrock_model_id,
    get_bedrock_profile,
    get_bedrock_region,
    get_bedrock_secret_access_key,
    get_bedrock_session_token,
    get_openai_api_key,
    load_runtime_env,
    normalize_ai_provider,
)


load_runtime_env()


class AIScanner:
    """Scanner that uses LLMs to identify privacy data elements in source code."""

    DEFAULT_AI_MODE = "balanced"
    DEFAULT_OPENAI_MODEL = "gpt-4o"
    DEFAULT_OLLAMA_MODEL = "llama3"
    DEFAULT_BEDROCK_MODEL = "anthropic.claude-3-haiku-20240307-v1:0"

    # Preset configurations controlling prompt size and token budgets.
    AI_MODE_PRESETS = {
        "fast": {
            "max_prompt_chars": 3500,
            "max_relevant_lines": 45,
            "max_model_output_tokens": 260,
            "ollama_num_ctx": 2048,
            "strict_large_file_multiplier": 1.5,
            "skip_signal_less_large_files": True,
        },
        "balanced": {
            "max_prompt_chars": 5000,
            "max_relevant_lines": 70,
            "max_model_output_tokens": 350,
            "ollama_num_ctx": 4096,
            "strict_large_file_multiplier": 2.0,
            "skip_signal_less_large_files": False,
        },
        "full": {
            "max_prompt_chars": 9000,
            "max_relevant_lines": 120,
            "max_model_output_tokens": 500,
            "ollama_num_ctx": 8192,
            "strict_large_file_multiplier": 3.0,
            "skip_signal_less_large_files": False,
        },
    }

    # Quick-filter keywords and regex signals used to detect relevant lines in
    # large files before sending them to the LLM.
    KEYWORD_HINTS = (
        "email", "phone", "mobile", "contact", "address", "name", "dob", "birth",
        "ip", "cookie", "token", "password", "username", "upi", "aadhaar", "pan",
        "ssn", "passport", "credit", "card", "account", "bank", "location",
        "lat", "lng", "gps",
    )
    SIMPLE_SIGNAL_PATTERNS = (
        re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE),
        re.compile(r"\b\d{3}[-.\s]?\d{2}[-.\s]?\d{4}\b"),
        re.compile(r"\b(?:\+?\d{1,3}[-.\s]?)?(?:\(?\d{2,4}\)?[-.\s]?)?\d{6,10}\b"),
        re.compile(r"\b(?:aadhaar|pan|passport|upi|ifsc|cvv)\b", re.IGNORECASE),
    )

    # -----------------------------------------------------------------------
    # Initialisation
    # -----------------------------------------------------------------------

    def __init__(
        self,
        data_elements_dir: Optional[str] = None,
        ai_mode: Optional[str] = None,
    ) -> None:
        if data_elements_dir is None:
            data_elements_dir = Path(__file__).parent.parent / "data_elements"
        self.data_elements_dir = Path(data_elements_dir)
        self.data_elements_names = self._load_data_elements_names()
        self.selected_model = "Unknown"

        env_mode = os.environ.get("TRUSCANNER_AI_MODE", self.DEFAULT_AI_MODE)
        requested_mode = (ai_mode or env_mode or self.DEFAULT_AI_MODE).strip().lower()
        if requested_mode not in self.AI_MODE_PRESETS:
            requested_mode = self.DEFAULT_AI_MODE
        self.ai_mode = requested_mode

        mode_settings = self.AI_MODE_PRESETS[self.ai_mode]
        self.max_prompt_chars: int = int(mode_settings["max_prompt_chars"])
        self.max_relevant_lines: int = int(mode_settings["max_relevant_lines"])
        self.max_model_output_tokens: int = int(mode_settings["max_model_output_tokens"])
        self.ollama_num_ctx: int = int(mode_settings["ollama_num_ctx"])
        self.strict_large_file_multiplier: float = float(mode_settings["strict_large_file_multiplier"])
        self.skip_signal_less_large_files: bool = bool(mode_settings["skip_signal_less_large_files"])

        # Allow per-env overrides on top of the preset defaults.
        for attr, env_key, minimum in [
            ("max_prompt_chars", "TRUSCANNER_AI_MAX_PROMPT_CHARS", 2000),
            ("max_model_output_tokens", "TRUSCANNER_AI_MAX_MODEL_OUTPUT_TOKENS", 120),
            ("max_relevant_lines", "TRUSCANNER_AI_MAX_RELEVANT_LINES", 40),
            ("ollama_num_ctx", "TRUSCANNER_AI_NUM_CTX", 1024),
        ]:
            try:
                override = int(os.environ.get(env_key, str(getattr(self, attr))))
                setattr(self, attr, max(override, minimum))
            except ValueError:
                pass

    # -----------------------------------------------------------------------
    # Data element loading
    # -----------------------------------------------------------------------

    def _load_data_elements_names(self) -> List[str]:
        """Return a flat list of data element names from all JSON definition files."""
        names: List[str] = []
        if self.data_elements_dir.exists():
            for json_file in self.data_elements_dir.rglob("*.json"):
                try:
                    with open(json_file, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    for source in data.get("sources", []):
                        names.append(source["name"])
                except Exception as e:
                    logger.error("Error loading {} for AI context: {}", json_file, e)
        return names

    # -----------------------------------------------------------------------
    # Prompt building
    # -----------------------------------------------------------------------

    def _prepare_content_for_prompt(self, content: str) -> str:
        """Trim large file content to a signal-dense excerpt for the LLM prompt.

        - Files under ``max_prompt_chars`` are passed through unchanged.
        - Larger files are filtered to lines containing keywords or pattern
          signals, with one line of surrounding context.
        - In ``fast`` mode, very large low-signal files are skipped (returns
          empty string).
        - Falls back to head + tail sampling for files with no signal lines.
        """
        if len(content) <= self.max_prompt_chars:
            return content

        lines = content.splitlines()
        relevant_lines: List[Tuple[int, str]] = []
        seen_line_numbers: set = set()
        strict_signal_mode = len(content) > (self.max_prompt_chars * self.strict_large_file_multiplier)

        for idx, raw_line in enumerate(lines, 1):
            line_lower = raw_line.lower()
            has_keyword = any(kw in line_lower for kw in self.KEYWORD_HINTS)
            has_signal = any(p.search(raw_line) for p in self.SIMPLE_SIGNAL_PATTERNS)

            if strict_signal_mode:
                if self.ai_mode == "fast":
                    if not has_signal:
                        continue
                elif not has_keyword and not has_signal:
                    continue
            elif not has_keyword and not has_signal:
                continue

            # Include one line of context before and after interesting lines.
            for line_no in range(max(1, idx - 1), min(len(lines), idx + 1) + 1):
                if line_no in seen_line_numbers:
                    continue
                seen_line_numbers.add(line_no)

                candidate = lines[line_no - 1].strip()
                if not candidate:
                    continue
                if len(candidate) > 240:
                    candidate = candidate[:237] + "..."
                relevant_lines.append((line_no, candidate))
                if len(relevant_lines) >= self.max_relevant_lines:
                    break

            if len(relevant_lines) >= self.max_relevant_lines:
                break

        if relevant_lines:
            body = "\n".join(
                f"L{line_no}: {line}"
                for line_no, line in relevant_lines[: self.max_relevant_lines]
            )
            return (
                "The source file was condensed for faster analysis. "
                "Use the line number prefix (e.g., L42) when returning findings.\n\n"
                f"{body}"
            )

        if strict_signal_mode and self.skip_signal_less_large_files:
            return ""

        # Fallback: head + tail sampling.
        half = max(800, self.max_prompt_chars // 2)
        head = content[:half]
        tail = content[-half:]
        return (
            "The source file is large and was sampled for coverage. "
            "Analyze these excerpts and return only high-confidence findings.\n"
            "[BEGIN FILE HEAD]\n"
            f"{head}\n"
            "[END FILE HEAD]\n"
            "[BEGIN FILE TAIL]\n"
            f"{tail}\n"
            "[END FILE TAIL]"
        )

    def _get_prompt(self, file_content: str, filename: str) -> str:
        """Build the LLM prompt for a single file.

        Only the base file name is embedded in the prompt (not the full path)
        to avoid leaking filesystem structure and to prevent path injection.
        """
        elements_list = ", ".join(
            name.strip()
            for name in self.data_elements_names
            if isinstance(name, str) and name.strip()
        ) or "All configured privacy data elements"

        # Use only the file name to avoid embedding user-controlled path components.
        safe_filename = Path(filename).name

        return f"""
Analyze the code from '{safe_filename}' and find privacy-sensitive data handling (PII and related identifiers).

Use these data element types as guidance: {elements_list}

Return ONLY valid JSON in this exact shape:
{{"findings":[{{"line_number":0,"line_content":"","matched_text":"","element_name":"","element_category":"","reason":""}}]}}

Rules:
- No markdown, no prose, no code fences.
- "line_number" must be an integer line number from the source content.
- If no findings exist, return: {{"findings":[]}}
- Keep "matched_text" short and specific.
- Ignore comments, docs, and generic keyword/enumeration lists that do not represent real data handling.
- Prefer runtime data collection/storage/transmission paths over configuration constants.

Code Content:
{file_content}
"""

    # -----------------------------------------------------------------------
    # Provider helpers
    # -----------------------------------------------------------------------

    @staticmethod
    def _resolve_provider(
        provider: Optional[str] = None,
        use_openai: bool = False,
    ) -> str:
        """Resolve the provider string to a canonical identifier."""
        normalized = normalize_ai_provider(provider)
        if normalized:
            return normalized
        if use_openai:
            return "openai"
        return "ollama"

    @classmethod
    def _get_bedrock_model(cls, model: Optional[str] = None) -> str:
        return (
            get_bedrock_model_id(model=model, default=cls.DEFAULT_BEDROCK_MODEL)
            or cls.DEFAULT_BEDROCK_MODEL
        )

    def get_available_ollama_models(self) -> List[str]:
        """Return names of locally available Ollama models."""
        return list_ollama_models()

    # -----------------------------------------------------------------------
    # File scanning
    # -----------------------------------------------------------------------

    def scan_file(
        self,
        filepath: str,
        provider: Optional[str] = None,
        use_openai: bool = False,
        model: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Scan a single file using the configured LLM provider.

        Returns a list of finding dicts, or an empty list if the file is empty,
        has no signal, or the provider call fails.
        """
        try:
            with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()

            if not content.strip():
                return []

            file_lines = content.splitlines()
            prompt_content = self._prepare_content_for_prompt(content)
            if not prompt_content.strip():
                return []

            prompt = self._get_prompt(prompt_content, filepath)
            selected_provider = self._resolve_provider(provider=provider, use_openai=use_openai)

            raw_text = self._call_provider(selected_provider, prompt, filepath, model)
            return parse_llm_response(
                raw_text, filepath, self.selected_model, file_lines=file_lines
            )

        except Exception as e:
            logger.error("Error scanning {} with AI: {}", filepath, e)
            return []

    def _call_provider(
        self,
        provider: str,
        prompt: str,
        filepath: str,
        model: Optional[str],
    ) -> str:
        """Dispatch to the correct provider and return raw LLM response text."""
        if provider == "openai" and get_openai_api_key():
            self.selected_model = self.DEFAULT_OPENAI_MODEL
            return call_openai(
                prompt,
                filepath,
                api_key=get_openai_api_key(),  # type: ignore[arg-type]
                model=self.selected_model,
            )

        if provider == "bedrock":
            self.selected_model = self._get_bedrock_model(model)
            region = get_bedrock_region()
            if not region:
                logger.error("Bedrock error: TRUSCANNER_REGION is required")
                return ""
            return call_bedrock(
                prompt,
                filepath,
                model_id=self.selected_model,
                region=region,
                access_key_id=get_bedrock_access_key_id(),
                secret_access_key=get_bedrock_secret_access_key(),
                session_token=get_bedrock_session_token(),
                profile_name=get_bedrock_profile(),
                max_tokens=self.max_model_output_tokens,
            )

        # Default: Ollama
        self.selected_model = model or self.DEFAULT_OLLAMA_MODEL
        return call_ollama(
            prompt,
            filepath,
            model=self.selected_model,
            num_ctx=self.ollama_num_ctx,
            max_tokens=self.max_model_output_tokens,
        )

    # -----------------------------------------------------------------------
    # Directory scanning
    # -----------------------------------------------------------------------

    def scan_directory(
        self,
        directory: str,
        provider: Optional[str] = None,
        use_openai: bool = False,
        model: Optional[str] = None,
        extensions: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """Scan all eligible files in *directory* using AI.

        File filtering (extensions, excluded dirs/files) mirrors the regex
        scanner defaults for consistency.
        """
        all_findings: List[Dict[str, Any]] = []
        path = Path(directory)

        from .regex_scanner import RegexScanner

        exclude_dirs = RegexScanner.DEFAULT_EXCLUDE_DIRS
        exclude_files = RegexScanner.DEFAULT_EXCLUDE_FILES
        exclude_exts = RegexScanner.DEFAULT_EXCLUDE_EXTENSIONS
        allowed_extensions = (
            RegexScanner._normalize_extensions(extensions)
            if extensions is not None
            else RegexScanner.DEFAULT_CODE_EXTENSIONS
        )

        files_to_scan: List[str] = []
        if path.is_file():
            files_to_scan = [str(path)]
        else:
            # followlinks=False (default) prevents symlink loop traversal.
            for root, dirs, files in os.walk(path, followlinks=False):
                dirs[:] = [d for d in dirs if d not in exclude_dirs and not d.startswith(".")]
                for file in files:
                    if file.startswith(".") or file in exclude_files:
                        continue
                    file_ext = Path(file).suffix.lower()
                    if file_ext in exclude_exts or file_ext not in allowed_extensions:
                        continue
                    files_to_scan.append(os.path.join(root, file))

        for file_path in files_to_scan:
            try:
                file_findings = self.scan_file(
                    file_path,
                    provider=provider,
                    use_openai=use_openai,
                    model=model,
                )
            except TypeError as exc:
                # Preserve compatibility with older tests/callers that monkeypatch
                # scan_file with the legacy two-argument signature.
                if "provider" not in str(exc):
                    raise
                file_findings = self.scan_file(file_path, use_openai=use_openai, model=model)
            all_findings.extend(file_findings)

        return all_findings


# ---------------------------------------------------------------------------
# Backward-compatible async wrapper
# ---------------------------------------------------------------------------

async def scan_directory_ai(
    directory: str,
    ai_mode: Optional[str] = None,
    provider: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Async wrapper around :class:`AIScanner` kept for backward compatibility."""
    scanner = AIScanner(ai_mode=ai_mode)
    normalized_provider = normalize_ai_provider(provider)
    use_openai = normalized_provider == "openai" or (
        normalized_provider is None and bool(get_openai_api_key())
    )
    return scanner.scan_directory(
        directory,
        provider=normalized_provider,
        use_openai=use_openai,
    )
