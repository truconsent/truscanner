import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
from urllib.parse import unquote, urlparse

from dotenv import load_dotenv

from src.ai_scanner import AIScanner
from src.regex_scanner import RegexScanner
from src.report_utils import generate_report_id
from src.scanner import run_ai_scan, run_regex_scan
from src.utils import (
    get_bedrock_model_id,
    get_openai_api_key,
    has_bedrock_credentials,
    normalize_ai_provider,
)


load_dotenv()


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
    """Run only the regex scanner and return structured results."""
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
    """Run only the AI scanner and return structured results."""
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
    """Programmatic scan API for local paths or file:// URLs."""
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
        "findings": regex_result["findings"],
        "ai_enabled": with_ai,
        "ai_provider": ai_result["ai_provider"],
        "ai_model": ai_result["ai_model"],
        "ai_total_findings": ai_result["ai_total_findings"],
        "ai_scan_duration_seconds": ai_result["ai_scan_duration_seconds"],
        "ai_findings": ai_result["ai_findings"],
    }
