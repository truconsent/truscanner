"""Shared utilities used by all AI provider implementations."""

import sys
import threading
import time
from typing import Any, Callable, Dict


def run_with_progress(filepath: str, fn: Callable[[], Any]) -> Any:
    """Run *fn* in a daemon thread while printing an elapsed-time spinner.

    Returns the value returned by *fn*, or re-raises any exception it raised.
    Using a daemon thread means the spinner will not prevent interpreter exit.
    """
    result: Dict[str, Any] = {"value": None, "error": None}

    def _worker() -> None:
        try:
            result["value"] = fn()
        except Exception as exc:
            result["error"] = exc

    thread = threading.Thread(target=_worker, daemon=True)
    thread.start()

    start_time = time.time()
    while thread.is_alive():
        elapsed = time.time() - start_time
        sys.stdout.write(f"\rAI Scanning: {filepath}... ({elapsed:.1f}s taken)")
        sys.stdout.flush()
        time.sleep(0.1)

    elapsed = time.time() - start_time
    sys.stdout.write(f"\r\033[K✓ AI Scanned: {filepath} ({elapsed:.1f}s taken)\n")
    sys.stdout.flush()

    if result["error"] is not None:
        raise result["error"]
    return result["value"]


def extract_message_content(response: Any) -> str:
    """Return the text content of an Ollama-style chat response.

    Handles both dict-style and attribute-style response objects so that
    different ollama client versions work transparently.
    """
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
