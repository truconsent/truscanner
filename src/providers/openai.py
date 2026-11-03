"""OpenAI (and OpenAI-compatible) provider for AI-based privacy scanning."""

from typing import Any, Optional

from openai import OpenAI

from .base import run_with_progress


def _is_client_error(exc: Exception) -> bool:
    """True for 4xx-class API errors (e.g. unsupported ``response_format``)."""
    status = getattr(exc, "status_code", None)
    if isinstance(status, int):
        return 400 <= status < 500
    name = type(exc).__name__
    return name in ("BadRequestError", "UnprocessableEntityError", "InvalidRequestError")


def call_openai(
    prompt: str,
    filepath: str,
    *,
    api_key: str,
    model: str,
    base_url: Optional[str] = None,
) -> str:
    """Send *prompt* to an OpenAI-compatible chat completions API.

    Args:
        prompt: The full prompt string to send to the model.
        filepath: Path of the file being scanned (used only for progress display).
        api_key: API key (never logged).
        model: Model name, e.g. ``"gpt-4o"``.
        base_url: Optional custom endpoint for OpenAI-compatible servers.

    The request first asks for ``response_format=json_object``; if the server
    rejects it with a 4xx error, it is retried once without it.

    Returns:
        Raw text from the model response, or an empty string on failure.
    """
    def _call() -> Any:
        client_kwargs = {"api_key": api_key}
        if base_url:
            client_kwargs["base_url"] = base_url
        client = OpenAI(**client_kwargs)
        kwargs = dict(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
        )
        try:
            return client.chat.completions.create(
                response_format={"type": "json_object"}, **kwargs
            )
        except Exception as exc:
            if not _is_client_error(exc):
                raise
            return client.chat.completions.create(**kwargs)

    response = run_with_progress(filepath, _call)
    if not response:
        return ""
    return response.choices[0].message.content or ""
