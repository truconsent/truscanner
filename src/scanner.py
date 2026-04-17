import os
from pathlib import Path
from typing import Callable, Dict, Any, List, Optional

from loguru import logger

from .ai_scanner import AIScanner
from .regex_scanner import RegexScanner
from .utils import has_bedrock_credentials, has_openai_credentials, normalize_ai_provider


def scan_file(filepath: str, regex_scanner: Optional[RegexScanner] = None) -> List[Dict[str, Any]]:
    """Backward-compatible regex scan for a single file."""
    findings = []
    try:
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()

        if regex_scanner:
            regex_findings = regex_scanner.scan_text(content, context=filepath)
            for finding in regex_findings:
                findings.append({
                    "filename": filepath,
                    "line_number": finding["line_number"],
                    "element_name": finding["element_name"],
                    "element_category": finding["element_category"],
                    "matched_text": finding.get("matched_text", ""),
                    "line_content": finding.get("line_content", ""),
                    "tags": finding.get("tags", {}),
                    "source": "Regex"
                })

    except Exception as e:
        logger.error("Could not read {}: {}", filepath, e)
    return findings


def run_regex_scan(
    directory: str,
    *,
    extensions: Optional[List[str]] = None,
    progress_callback: Optional[Callable[[int, int, str], None]] = None,
    regex_scanner: Optional[RegexScanner] = None,
) -> List[Dict[str, Any]]:
    """Run the regex/static scan only."""
    scanner = regex_scanner or RegexScanner()
    if hasattr(scanner, "scan_directory"):
        return scanner.scan_directory(
            directory,
            extensions=extensions,
            progress_callback=progress_callback,
        )

    exclude_dirs = getattr(scanner, "DEFAULT_EXCLUDE_DIRS", RegexScanner.DEFAULT_EXCLUDE_DIRS)
    exclude_files = getattr(scanner, "DEFAULT_EXCLUDE_FILES", RegexScanner.DEFAULT_EXCLUDE_FILES)
    exclude_exts = getattr(scanner, "DEFAULT_EXCLUDE_EXTENSIONS", RegexScanner.DEFAULT_EXCLUDE_EXTENSIONS)
    default_extensions = getattr(scanner, "DEFAULT_CODE_EXTENSIONS", RegexScanner.DEFAULT_CODE_EXTENSIONS)
    if extensions is None:
        allowed_extensions = default_extensions
    elif hasattr(scanner, "_normalize_extensions"):
        allowed_extensions = scanner._normalize_extensions(extensions)
    else:
        allowed_extensions = {
            ext.lower() if str(ext).startswith(".") else f".{str(ext).lower()}"
            for ext in extensions
        }

    files_to_scan = []
    path = Path(directory)
    if path.is_file():
        files_to_scan = [str(path)]
    else:
        for root, dirs, files in os.walk(directory, followlinks=False):
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

    results = []
    total = len(files_to_scan)
    for index, filepath in enumerate(files_to_scan, 1):
        if progress_callback:
            progress_callback(index, total, filepath)
        results.extend(scan_file(filepath, regex_scanner=scanner))
    return results


def run_ai_scan(
    directory: str,
    *,
    ai_provider: Optional[str] = None,
    ai_mode: str = "balanced",
    model: Optional[str] = None,
    extensions: Optional[List[str]] = None,
    use_openai: bool = False,
) -> List[Dict[str, Any]]:
    """Run the AI scan only with the selected provider."""
    provider = normalize_ai_provider(ai_provider)
    scanner = AIScanner(ai_mode=ai_mode)

    if provider == "openai":
        if not has_openai_credentials():
            logger.warning("OpenAI scan requested but OPENAI_KEY is not set")
            run_ai_scan.last_usage = getattr(scanner, "last_scan_usage", {})
            return []
    elif provider == "bedrock":
        if not has_bedrock_credentials():
            logger.warning(
                "AWS Bedrock scan requested but credentials are not fully configured "
                "(TRUSCANNER_ACCESS_KEY_ID, TRUSCANNER_SECRET_ACCESS_KEY, TRUSCANNER_REGION)"
            )
            run_ai_scan.last_usage = getattr(scanner, "last_scan_usage", {})
            return []
    else:
        if model is None:
            available_models = scanner.get_available_ollama_models()
            if not available_models:
                logger.warning("Ollama scan requested but no Ollama models are available")
                run_ai_scan.last_usage = getattr(scanner, "last_scan_usage", {})
                return []
            model = available_models[0]

    results = scanner.scan_directory(
        directory,
        provider=provider,
        use_openai=use_openai or provider == "openai",
        model=model,
        extensions=extensions,
    )
    run_ai_scan.last_usage = getattr(scanner, "last_scan_usage", {})
    return results


def scan_directory(
    directory: str,
    use_ai: bool = False,
    ai_mode: str = "balanced",
    ai_provider: Optional[str] = None,
    model: Optional[str] = None,
    extensions: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """Backward-compatible combined scan wrapper."""
    results = run_regex_scan(directory, extensions=extensions)

    if use_ai:
        results.extend(
            run_ai_scan(
                directory,
                ai_provider=ai_provider,
                ai_mode=ai_mode,
                model=model,
                extensions=extensions,
                use_openai=ai_provider is None and has_openai_credentials(),
            )
        )

    return results
