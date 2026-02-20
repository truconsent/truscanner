import os
import json
import asyncio
import time
import sys
import threading
import re
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple

import ollama
from openai import OpenAI


class AIScanner:
    """Scanner that uses LLMs (Ollama or OpenAI) to identify privacy data elements."""
    DEFAULT_AI_MODE = "balanced"
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

    KEYWORD_HINTS = (
        "email", "phone", "mobile", "contact", "address", "name", "dob", "birth",
        "ip", "cookie", "token", "password", "username", "upi", "aadhaar", "pan",
        "ssn", "passport", "credit", "card", "account", "bank", "location",
        "lat", "lng", "gps"
    )
    SIMPLE_SIGNAL_PATTERNS = (
        re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE),
        re.compile(r"\b\d{3}[-.\s]?\d{2}[-.\s]?\d{4}\b"),
        re.compile(r"\b(?:\+?\d{1,3}[-.\s]?)?(?:\(?\d{2,4}\)?[-.\s]?)?\d{6,10}\b"),
        re.compile(r"\b(?:aadhaar|pan|passport|upi|ifsc|cvv)\b", re.IGNORECASE),
    )

    def __init__(self, data_elements_dir: Optional[str] = None, ai_mode: Optional[str] = None):
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
        self.max_prompt_chars = int(mode_settings["max_prompt_chars"])
        self.max_relevant_lines = int(mode_settings["max_relevant_lines"])
        self.max_model_output_tokens = int(mode_settings["max_model_output_tokens"])
        self.ollama_num_ctx = int(mode_settings["ollama_num_ctx"])
        self.strict_large_file_multiplier = float(mode_settings["strict_large_file_multiplier"])
        self.skip_signal_less_large_files = bool(mode_settings["skip_signal_less_large_files"])

        try:
            self.max_prompt_chars = max(
                int(os.environ.get("TRUSCANNER_AI_MAX_PROMPT_CHARS", str(self.max_prompt_chars))),
                2000,
            )
        except ValueError:
            pass
        try:
            self.max_model_output_tokens = max(
                int(
                    os.environ.get(
                        "TRUSCANNER_AI_MAX_MODEL_OUTPUT_TOKENS",
                        str(self.max_model_output_tokens),
                    )
                ),
                120,
            )
        except ValueError:
            pass
        try:
            self.max_relevant_lines = max(
                int(os.environ.get("TRUSCANNER_AI_MAX_RELEVANT_LINES", str(self.max_relevant_lines))),
                40,
            )
        except ValueError:
            pass
        try:
            self.ollama_num_ctx = max(
                int(os.environ.get("TRUSCANNER_AI_NUM_CTX", str(self.ollama_num_ctx))),
                1024,
            )
        except ValueError:
            pass

    def _load_data_elements_names(self) -> List[str]:
        """Load all data element names from JSON files for context."""
        names = []
        if self.data_elements_dir.exists():
            for json_file in self.data_elements_dir.rglob("*.json"):
                try:
                    with open(json_file, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    for source in data.get("sources", []):
                        names.append(source["name"])
                except Exception as e:
                    print(f"Error loading {json_file} for AI context: {e}")
        return names

    def _prepare_content_for_prompt(self, content: str) -> str:
        """Shrink large files to relevant snippets for faster local inference.

        In `fast` mode, very large files without signal lines may be skipped.
        In `balanced`/`full`, it falls back to head+tail excerpts to preserve coverage.
        """
        if len(content) <= self.max_prompt_chars:
            return content

        lines = content.splitlines()
        relevant_lines: List[Tuple[int, str]] = []
        seen_line_numbers = set()
        strict_signal_mode = len(content) > (self.max_prompt_chars * self.strict_large_file_multiplier)

        for idx, raw_line in enumerate(lines, 1):
            line_lower = raw_line.lower()
            has_keyword = any(keyword in line_lower for keyword in self.KEYWORD_HINTS)
            has_signal = any(pattern.search(raw_line) for pattern in self.SIMPLE_SIGNAL_PATTERNS)

            # For very large files, only keep strong signal lines to avoid slow, low-value prompts.
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
            body = "\n".join(f"L{line_no}: {line}" for line_no, line in relevant_lines[:self.max_relevant_lines])
            return (
                "The source file was condensed for faster analysis. "
                "Use the line number prefix (e.g., L42) when returning findings.\n\n"
                f"{body}"
            )

        # In fast mode, very large low-signal files can be skipped.
        if strict_signal_mode and self.skip_signal_less_large_files:
            return ""

        # Fallback for long files without obvious signals.
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
        """Construct the prompt for the LLM."""
        # Include every configured element name so AI guidance matches the full catalog.
        elements_list = ", ".join(
            name.strip()
            for name in self.data_elements_names
            if isinstance(name, str) and name.strip()
        ) or "All configured privacy data elements"

        prompt = f"""
Analyze the code from '{filename}' and find privacy-sensitive data handling (PII and related identifiers).

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
        return prompt

    def get_available_ollama_models(self) -> List[str]:
        """Fetch list of available model names from Ollama."""
        try:
            models_info = ollama.list()
            if hasattr(models_info, "models"):
                return [m.model for m in models_info.models]
            if isinstance(models_info, list):
                return [m.get("name") or m.model for m in models_info]
            return []
        except Exception as e:
            print(f"Error listing Ollama models: {e}")
            return []

    def scan_file(self, filepath: str, use_openai: bool = False, model: Optional[str] = None) -> List[Dict[str, Any]]:
        """Scan a single file using the selected LLM."""
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

            if use_openai and os.environ.get("OPENAI_API_KEY"):
                self.selected_model = "gpt-4o"
                return self._scan_with_openai(prompt, filepath, file_lines=file_lines)

            self.selected_model = model or "llama3"
            return self._scan_with_ollama(prompt, filepath, model=self.selected_model, file_lines=file_lines)

        except Exception as e:
            print(f"Error scanning {filepath} with AI: {e}")
            return []

    @staticmethod
    def _extract_message_content(response: Any) -> str:
        """Get message.content regardless of response object style."""
        if isinstance(response, dict):
            message = response.get("message", {})
            if isinstance(message, dict):
                return str(message.get("content", "") or "")

        message = getattr(response, "message", None)
        if isinstance(message, dict):
            return str(message.get("content", "") or "")
        if message is not None:
            content = getattr(message, "content", None)
            if content is not None:
                return str(content)

        return ""

    def _scan_with_ollama(
        self,
        prompt: str,
        filepath: str,
        model: Optional[str] = None,
        file_lines: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """Call Ollama for analysis with a real-time timer."""
        if not model:
            model = "llama3"

        try:
            result = {"response": None, "error": None}

            def chat_thread():
                try:
                    request_payload = {
                        "model": model,
                        "messages": [{"role": "user", "content": prompt}],
                        "options": {
                            "temperature": 0,
                            "num_ctx": self.ollama_num_ctx,
                            "num_predict": self.max_model_output_tokens,
                        },
                    }
                    try:
                        response = ollama.chat(format="json", **request_payload)
                    except TypeError:
                        # Older ollama clients may not accept `format` as a keyword arg.
                        response = ollama.chat(**request_payload)
                    result["response"] = response
                except Exception as e:
                    result["error"] = e

            t = threading.Thread(target=chat_thread)
            t.start()

            start_time = time.time()
            while t.is_alive():
                elapsed = time.time() - start_time
                sys.stdout.write(f"\rAI Scanning: {filepath}... ({elapsed:.1f}s taken)")
                sys.stdout.flush()
                time.sleep(0.1)

            elapsed = time.time() - start_time
            sys.stdout.write(f"\r\033[K✓ AI Scanned: {filepath} ({elapsed:.1f}s taken)\n")
            sys.stdout.flush()

            if result["error"]:
                raise result["error"]
            if not result["response"]:
                return []

            response_content = self._extract_message_content(result["response"])
            return self._parse_llm_response(response_content, filepath, file_lines=file_lines)
        except Exception as e:
            print(f"Ollama error: {e}")
            return []

    def _scan_with_openai(
        self,
        prompt: str,
        filepath: str,
        file_lines: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """Call OpenAI for analysis with a real-time timer."""
        try:
            result = {"response": None, "error": None}

            def chat_thread():
                try:
                    client = OpenAI()
                    response = client.chat.completions.create(
                        model="gpt-4o",
                        messages=[{"role": "user", "content": prompt}],
                        response_format={"type": "json_object"},
                        temperature=0,
                    )
                    result["response"] = response
                except Exception as e:
                    result["error"] = e

            t = threading.Thread(target=chat_thread)
            t.start()

            start_time = time.time()
            while t.is_alive():
                elapsed = time.time() - start_time
                sys.stdout.write(f"\rAI Scanning: {filepath}... ({elapsed:.1f}s taken)")
                sys.stdout.flush()
                time.sleep(0.1)

            elapsed = time.time() - start_time
            sys.stdout.write(f"\r\033[K✓ AI Scanned: {filepath} ({elapsed:.1f}s taken)\n")
            sys.stdout.flush()

            if result["error"]:
                raise result["error"]
            if not result["response"]:
                return []

            response_content = result["response"].choices[0].message.content or ""
            return self._parse_llm_response(response_content, filepath, file_lines=file_lines)
        except Exception as e:
            print(f"OpenAI error: {e}")
            return []

    @staticmethod
    def _coerce_line_number(value: Any) -> int:
        """Parse a positive integer line number from model output."""
        if isinstance(value, int):
            return value if value > 0 else 0
        if isinstance(value, float):
            return int(value) if value > 0 else 0
        if isinstance(value, str):
            match = re.search(r"\d+", value)
            if match:
                return int(match.group(0))
        return 0

    @staticmethod
    def _line_number_from_prefix(text: str) -> int:
        """Read line number from leading prefixes like `L42:`."""
        if not isinstance(text, str):
            return 0
        match = re.match(r"^\s*L?(\d+)\s*[:|-]", text)
        if match:
            return int(match.group(1))
        return 0

    @staticmethod
    def _strip_line_prefix(text: str) -> str:
        """Drop leading line-number markers like `L42:`."""
        if not isinstance(text, str):
            return ""
        return re.sub(r"^\s*L?\d+\s*[:|-]\s*", "", text).strip()

    @staticmethod
    def _extract_json_payload(content: str) -> Optional[Any]:
        """Extract the first JSON payload from text with basic sanitation."""
        if not content:
            return None

        cleaned = content.strip()
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```$", "", cleaned, flags=re.IGNORECASE).strip()

        decoder = json.JSONDecoder()
        candidates = [cleaned]

        first_object = cleaned.find("{")
        first_list = cleaned.find("[")
        starts = [idx for idx in (first_object, first_list) if idx != -1]
        if starts:
            candidates.append(cleaned[min(starts):].strip())

        for candidate in candidates:
            if not candidate:
                continue
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                pass
            try:
                payload, _ = decoder.raw_decode(candidate)
                return payload
            except json.JSONDecodeError:
                pass
            sanitized = re.sub(r",(\s*[}\]])", r"\1", candidate)
            try:
                return json.loads(sanitized)
            except json.JSONDecodeError:
                continue

        return None

    def _parse_llm_response(
        self,
        content: str,
        filepath: str,
        file_lines: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """Parse JSON from LLM response with robust handling for malformed outputs."""
        try:
            raw_findings = self._extract_json_payload(content)
            if raw_findings is None:
                if content.strip():
                    print(f"⚠️ No JSON found in LLM response for {filepath}")
                return []

            findings_list: Any = []
            if isinstance(raw_findings, list):
                findings_list = raw_findings
            elif isinstance(raw_findings, dict):
                findings_list = raw_findings.get(
                    "findings",
                    raw_findings.get("data_elements", raw_findings.get("data", [])),
                )
                if not findings_list and {"line_number", "element_name"} <= set(raw_findings.keys()):
                    findings_list = [raw_findings]

            if isinstance(findings_list, dict):
                findings_list = [findings_list]
            if not isinstance(findings_list, list):
                return []

            validated_findings = []
            for finding in findings_list:
                if not isinstance(finding, dict):
                    continue

                raw_line_content = str(finding.get("line_content", finding.get("context", "")) or "")

                line_number = self._coerce_line_number(finding.get("line_number"))
                if line_number <= 0:
                    line_number = self._line_number_from_prefix(raw_line_content)

                cleaned_line_content = self._strip_line_prefix(raw_line_content)

                if file_lines and line_number <= 0 and cleaned_line_content:
                    # Best-effort lookup when model omitted line numbers.
                    for idx, line in enumerate(file_lines, 1):
                        if line.strip() == cleaned_line_content:
                            line_number = idx
                            break

                if file_lines and 0 < line_number <= len(file_lines):
                    cleaned_line_content = file_lines[line_number - 1].strip() or cleaned_line_content

                matched_text = finding.get("matched_text") or finding.get("matched") or finding.get("value") or ""
                valid_finding = {
                    "line_number": line_number,
                    "line_content": cleaned_line_content,
                    "matched_text": matched_text,
                    "element_name": finding.get("element_name", finding.get("type", "Unknown PII")),
                    "element_category": finding.get("element_category", finding.get("category", "Privacy")),
                    "reason": finding.get("reason", ""),
                    "filename": filepath,
                    "source": f"LLM ({self.selected_model})",
                }
                validated_findings.append(valid_finding)

            return validated_findings
        except Exception as e:
            print(f"Error parsing LLM response for {filepath}: {e}")
            return []

    def scan_directory(
        self,
        directory: str,
        use_openai: bool = False,
        model: Optional[str] = None,
        extensions: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        """Scan all files in a directory using AI."""
        all_findings = []
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
        files_to_scan = []
        if path.is_file():
            files_to_scan = [str(path)]
        else:
            for root, dirs, files in os.walk(path):
                dirs[:] = [d for d in dirs if d not in exclude_dirs and not d.startswith('.')]
                for file in files:
                    if file.startswith('.') or file in exclude_files:
                        continue
                    file_ext = Path(file).suffix.lower()
                    if file_ext in exclude_exts:
                        continue
                    if file_ext not in allowed_extensions:
                        continue
                    files_to_scan.append(os.path.join(root, file))

        for file_path in files_to_scan:
            # The scanning message and timer are handled inside scanner methods.
            file_findings = self.scan_file(file_path, use_openai=use_openai, model=model)
            all_findings.extend(file_findings)

        return all_findings


async def scan_directory_ai(directory: str, ai_mode: Optional[str] = None) -> List[Dict[str, Any]]:
    """Backward compatible wrapper for AIScanner."""
    scanner = AIScanner(ai_mode=ai_mode)
    use_openai = bool(os.environ.get("OPENAI_API_KEY"))
    # Note: AIScanner.scan_directory is synchronous, but the original was async.
    # We call it in a thread to keep the async interface if needed, or just run it.
    return scanner.scan_directory(directory, use_openai=use_openai)
