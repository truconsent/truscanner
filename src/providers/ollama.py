"""Ollama provider for AI-based privacy scanning."""

from typing import Any, List

import ollama as _ollama
from loguru import logger

from .base import extract_message_content, run_with_progress


def call_ollama(
    prompt: str,
    filepath: str,
    *,
    model: str,
    num_ctx: int,
    max_tokens: int,
) -> str:
    """Send *prompt* to a local Ollama model and return the raw response text.

    Args:
        prompt: The full prompt string to send to the model.
        filepath: Path of the file being scanned (used only for progress display).
        model: Ollama model name, e.g. ``"llama3"`` or ``"mistral"``.
        num_ctx: Context window size in tokens.
        max_tokens: Maximum number of tokens the model may generate.

    Returns:
        Raw text from the model response, or an empty string on failure.
    """
    def _call() -> Any:
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "options": {
                "temperature": 0,
                "num_ctx": num_ctx,
                "num_predict": max_tokens,
            },
        }
        try:
            return _ollama.chat(format="json", **payload)
        except TypeError:
            # Older ollama clients may not accept `format` as a keyword arg.
            return _ollama.chat(**payload)

    response = run_with_progress(filepath, _call)
    if not response:
        return ""
    return extract_message_content(response)


def list_models() -> List[str]:
    """Return the names of locally available Ollama models.

    Returns an empty list if Ollama is not running or has no models installed.
    """
    try:
        models_info = _ollama.list()
        if hasattr(models_info, "models"):
            return [m.model for m in models_info.models]
        if isinstance(models_info, list):
            return [m.get("name") or m.model for m in models_info]
        return []
    except Exception as e:
        logger.error("Error listing Ollama models: {}", e)
        return []
