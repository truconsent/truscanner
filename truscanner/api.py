import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
from urllib.parse import unquote, urlparse

from src.ai_scanner import AIScanner
from src.regex_scanner import RegexScanner
from src.report_utils import generate_report_id


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
                # Supports UNC-like file URLs.
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


def scan(
    path_or_url: PathLike,
    *,
    with_ai: bool = False,
    personal_only: bool = False,
    use_openai: Optional[bool] = None,
    model: Optional[str] = None,
    extensions: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Programmatic scan API for local paths or file:// URLs."""
    target = _resolve_local_path(path_or_url)
    target_str = str(target)

    scanner = RegexScanner()
    configured_elements = len(getattr(scanner, "data_elements", []) or [])
    report_id = generate_report_id(target_str)

    start_time = time.time()
    findings = scanner.scan_directory(target_str, extensions=extensions)
    duration = time.time() - start_time

    if personal_only:
        findings = [
            finding
            for finding in findings
            if any(cat in finding.get("element_category", "") for cat in PERSONAL_CATEGORIES)
        ]

    ai_findings: List[Dict[str, Any]] = []
    ai_duration: Optional[float] = None
    selected_model: Optional[str] = None

    if with_ai:
        ai_scanner = AIScanner()

        if use_openai is None:
            use_openai = bool(os.environ.get("OPENAI_API_KEY"))

        if not use_openai:
            if model:
                selected_model = model
            else:
                available_models = ai_scanner.get_available_ollama_models()
                if available_models:
                    selected_model = available_models[0]

        if use_openai or selected_model:
            ai_start = time.time()
            ai_findings = ai_scanner.scan_directory(
                target_str,
                use_openai=bool(use_openai),
                model=selected_model,
                extensions=extensions,
            )
            ai_duration = time.time() - ai_start

    return {
        "scan_report_id": report_id,
        "directory_scanned": target_str,
        "configured_data_elements": configured_elements,
        "total_findings": len(findings),
        "scan_duration_seconds": duration,
        "findings": findings,
        "ai_enabled": with_ai,
        "ai_model": "gpt-4o" if use_openai else selected_model,
        "ai_total_findings": len(ai_findings),
        "ai_scan_duration_seconds": ai_duration,
        "ai_findings": ai_findings,
    }
