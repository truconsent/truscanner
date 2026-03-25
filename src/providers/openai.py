"""OpenAI provider for AI-based privacy scanning."""

from typing import Any

from openai import OpenAI

from .base import run_with_progress


def call_openai(
    prompt: str,
    filepath: str,
    *,
    api_key: str,
    model: str,
) -> str:
    """Send *prompt* to the OpenAI chat completions API and return the response text.

    Args:
        prompt: The full prompt string to send to the model.
        filepath: Path of the file being scanned (used only for progress display).
        api_key: OpenAI API key.
        model: OpenAI model name, e.g. ``"gpt-4o"``.

    Returns:
        Raw text from the model response, or an empty string on failure.
    """
    def _call() -> Any:
        client = OpenAI(api_key=api_key)
        return client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            temperature=0,
        )

    response = run_with_progress(filepath, _call)
    if not response:
        return ""
    return response.choices[0].message.content or ""
