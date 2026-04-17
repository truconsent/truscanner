import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
from urllib.parse import unquote, urlparse

from src.ai_scanner import AIScanner
from src.regex_scanner import RegexScanner
from src.report_utils import generate_report_id
from src.scanner import run_ai_scan, run_regex_scan
from src.utils import (
    get_bedrock_model_id,
    get_openai_api_key,
    has_bedrock_credentials,
    load_runtime_env,
    normalize_ai_provider,
)

load_runtime_env()


PathLike = Union[str, os.PathLike]


PERSONAL_CATEGORIES = [
    "Personal Identifiable Information",
    "PII",
    "Contact Information",
    "Government-Issued Identifiers",
    "Authentication & Credentials",
    "Health & Biometric Data",
    "Sensitive Personal Data",
]


def _resolve_local_path(path_or_url: PathLike) -> Path:
    """Resolve a local filesystem path or file:// URL to an absolute Path."""
    raw = os.fspath(path_or_url)
    parsed = urlparse(raw)

    if parsed.scheme in ("", "file"):
        if parsed.scheme == "file":
            if parsed.netloc and parsed.netloc not in ("", "localhost"):
                candidate = Path(f"//{parsed.netloc}{unquote(parsed.path)}")
            else:
                candidate = Path(unquote(parsed.path))
        else:
            candidate = Path(raw)
    else:
        raise ValueError(
            "Only local paths or file:// URLs are supported. "
            f"Received scheme '{parsed.scheme}'."
        )

    resolved = candidate.expanduser().resolve()
    if not resolved.exists():
        raise FileNotFoundError(f"Path not found: {resolved}")
    return resolved


def _filter_personal_findings(findings: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [
        finding
        for finding in findings
        if any(cat in finding.get("element_category", "") for cat in PERSONAL_CATEGORIES)
    ]


def _resolve_requested_ai_provider(
    ai_provider: Optional[str] = None,
    use_openai: Optional[bool] = None,
    model: Optional[str] = None,
) -> str:
    """Resolve the requested provider while preserving old API behavior."""
    normalized = normalize_ai_provider(ai_provider)
    if normalized:
        return normalized
    if use_openai:
        return "openai"
    if model:
        return "ollama"
    if get_openai_api_key():
        return "openai"
    if has_bedrock_credentials():
        return "bedrock"
    return "ollama"


def _resolve_ai_model(ai_provider: str, model: Optional[str] = None) -> Optional[str]:
    """Resolve the provider-specific model identifier used for the AI scan."""
    provider = normalize_ai_provider(ai_provider)

    if provider == "openai":
        return AIScanner.DEFAULT_OPENAI_MODEL
    if provider == "bedrock":
        return get_bedrock_model_id(model=model, default=AIScanner.DEFAULT_BEDROCK_MODEL)
    if provider == "ollama":
        if model:
            return model
        scanner = AIScanner()
        available_models = scanner.get_available_ollama_models()
        if available_models:
            return available_models[0]
    return None


def scan_regex(
    path_or_url: PathLike,
    *,
    personal_only: bool = False,
    extensions: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Run only the regex/static scanner on a local path or ``file://`` URL.

    Args:
        path_or_url: Filesystem path or ``file://`` URL to a file or directory.
        personal_only: When ``True``, keep only PII-related findings (Personal
            Identifiable Information, Contact Information, Government-Issued
            Identifiers, etc.).
        extensions: Restrict scanning to files with these extensions, e.g.
            ``[".py", ".js"]``. Defaults to all supported code extensions.

    Returns:
        A dict with the following keys:

        - ``scan_report_id`` – unique ID generated from the target path.
        - ``directory_scanned`` – resolved absolute path that was scanned.
        - ``configured_data_elements`` – number of pattern definitions loaded.
        - ``total_findings`` – count of findings (after any personal_only filter).
        - ``scan_duration_seconds`` – wall-clock seconds the scan took.
        - ``findings`` – list of finding dicts, each containing ``filename``,
          ``line_number``, ``element_name``, ``element_category``,
          ``matched_text``, ``line_content``, ``tags``, and ``source``.
    """
    target = _resolve_local_path(path_or_url)
    target_str = str(target)

    scanner = RegexScanner()
    configured_elements = len(getattr(scanner, "data_elements", []) or [])
    report_id = generate_report_id(target_str)

    start_time = time.time()
    findings = run_regex_scan(
        target_str,
        extensions=extensions,
        regex_scanner=scanner,
    )
    duration = time.time() - start_time

    if personal_only:
        findings = _filter_personal_findings(findings)

    return {
        "scan_report_id": report_id,
        "directory_scanned": target_str,
        "configured_data_elements": configured_elements,
        "total_findings": len(findings),
        "scan_duration_seconds": duration,
        "token_usage": getattr(scanner, "last_scan_usage", {}),
        "findings": findings,
    }


def scan_ai(
    path_or_url: PathLike,
    *,
    ai_provider: Optional[str] = None,
    ai_mode: str = "balanced",
    use_openai: Optional[bool] = None,
    model: Optional[str] = None,
    extensions: Optional[List[str]] = None,
    personal_only: bool = False,
) -> Dict[str, Any]:
    """Run only the AI/LLM scanner on a local path or ``file://`` URL.

    Args:
        path_or_url: Filesystem path or ``file://`` URL to a file or directory.
        ai_provider: LLM provider to use — ``"ollama"``, ``"openai"``, or
            ``"bedrock"``. Defaults to auto-detection based on available
            credentials.
        ai_mode: Scanning depth — ``"fast"``, ``"balanced"`` (default), or
            ``"full"``. Controls prompt size and token budget.
        use_openai: Deprecated shorthand for ``ai_provider="openai"``.
        model: Override the default model for the selected provider (e.g.
            an Ollama model name or a Bedrock model ID).
        extensions: Restrict scanning to files with these extensions.
        personal_only: When ``True``, keep only PII-related findings.

    Returns:
        A dict with the following keys:

        - ``directory_scanned`` – resolved absolute path that was scanned.
        - ``ai_provider`` – resolved provider name used for the scan.
        - ``ai_model`` – model identifier used.
        - ``ai_total_findings`` – count of AI findings.
        - ``ai_scan_duration_seconds`` – wall-clock seconds the AI scan took.
        - ``ai_findings`` – list of finding dicts (same schema as regex findings
          but with ``source`` set to ``"LLM (<model>)"`` and an extra
          ``reason`` field).
    """
    target = _resolve_local_path(path_or_url)
    target_str = str(target)
    provider = _resolve_requested_ai_provider(
        ai_provider=ai_provider,
        use_openai=use_openai,
        model=model,
    )
    selected_model = _resolve_ai_model(provider, model=model)

    start_time = time.time()
    findings = run_ai_scan(
        target_str,
        ai_provider=provider,
        ai_mode=ai_mode,
        model=selected_model,
        extensions=extensions,
        use_openai=provider == "openai",
    )
    duration = time.time() - start_time

    if personal_only:
        findings = _filter_personal_findings(findings)

    return {
        "directory_scanned": target_str,
        "ai_provider": provider,
        "ai_model": selected_model,
        "ai_total_findings": len(findings),
        "ai_scan_duration_seconds": duration,
        "token_usage": getattr(run_ai_scan, "last_usage", {}),
        "ai_findings": findings,
    }


def scan(
    path_or_url: PathLike,
    *,
    with_ai: bool = False,
    personal_only: bool = False,
    use_openai: Optional[bool] = None,
    ai_provider: Optional[str] = None,
    model: Optional[str] = None,
    extensions: Optional[List[str]] = None,
    ai_mode: str = "balanced",
) -> Dict[str, Any]:
    """Run a full scan (regex + optional AI) on a local path or ``file://`` URL.

    This is the primary programmatic entry point. It always runs the regex
    scanner and optionally follows up with an AI scanner when ``with_ai=True``.

    Args:
        path_or_url: Filesystem path or ``file://`` URL to a file or directory.
        with_ai: When ``True``, run the AI/LLM scanner after the regex scan.
        personal_only: When ``True``, keep only PII-related findings from both
            scanners.
        use_openai: Deprecated shorthand for ``ai_provider="openai"``.
        ai_provider: LLM provider — ``"ollama"``, ``"openai"``, or
            ``"bedrock"``. Auto-detected when omitted.
        model: Model identifier override for the selected AI provider.
        extensions: Restrict scanning to files with these extensions.
        ai_mode: AI scanning depth — ``"fast"``, ``"balanced"`` (default),
            or ``"full"``.

    Returns:
        A merged dict containing all regex result keys plus:

        - ``ai_enabled`` – whether the AI scan was requested.
        - ``ai_provider`` – provider used (``None`` when AI is disabled).
        - ``ai_model`` – model used (``None`` when AI is disabled).
        - ``ai_total_findings`` – count of AI findings (0 when AI is disabled).
        - ``ai_scan_duration_seconds`` – AI scan duration (``None`` when disabled).
        - ``ai_findings`` – list of AI finding dicts (empty when AI is disabled).

    Example::

        from truscanner import scan

        result = scan("/path/to/project", with_ai=True, ai_provider="openai")
        print(result["total_findings"])   # regex findings count
        print(result["ai_total_findings"])  # AI findings count
    """
    regex_result = scan_regex(
        path_or_url,
        personal_only=personal_only,
        extensions=extensions,
    )

    ai_result = {
        "directory_scanned": regex_result["directory_scanned"],
        "ai_provider": None,
        "ai_model": None,
        "ai_total_findings": 0,
        "ai_scan_duration_seconds": None,
        "token_usage": {},
        "ai_findings": [],
    }

    if with_ai:
        ai_result = scan_ai(
            path_or_url,
            ai_provider=ai_provider,
            ai_mode=ai_mode,
            use_openai=use_openai,
            model=model,
            extensions=extensions,
            personal_only=personal_only,
        )

    return {
        "scan_report_id": regex_result["scan_report_id"],
        "directory_scanned": regex_result["directory_scanned"],
        "configured_data_elements": regex_result["configured_data_elements"],
        "total_findings": regex_result["total_findings"],
        "scan_duration_seconds": regex_result["scan_duration_seconds"],
        "token_usage": regex_result.get("token_usage", {}),
        "findings": regex_result["findings"],
        "ai_enabled": with_ai,
        "ai_provider": ai_result["ai_provider"],
        "ai_model": ai_result["ai_model"],
        "ai_total_findings": ai_result["ai_total_findings"],
        "ai_scan_duration_seconds": ai_result["ai_scan_duration_seconds"],
        "ai_token_usage": ai_result.get("token_usage", {}),
        "ai_findings": ai_result["ai_findings"],
    }
