"""Anthropic (Claude) provider for AI-based privacy scanning.

Uses the Messages HTTP API directly via ``requests`` (no SDK dependency).
"""

from typing import Any

import requests

from .base import run_with_progress

ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"


def call_anthropic(
    prompt: str,
    filepath: str,
    *,
    api_key: str,
    model: str,
    max_tokens: int = 1024,
    timeout: float = 120,
) -> str:
    """Send *prompt* to the Anthropic Messages API and return the text.

    The API key is only sent in the ``x-api-key`` header; it is never logged
    and never included in raised error messages.

    Returns:
        Concatenated text of all ``text`` content blocks.
    """
    def _call() -> Any:
        try:
            resp = requests.post(
                ANTHROPIC_API_URL,
                headers={
                    "x-api-key": api_key,
                    "anthropic-version": ANTHROPIC_VERSION,
                    "content-type": "application/json",
                },
                json={
                    "model": model,
                    "max_tokens": max_tokens,
                    "temperature": 0,
                    "messages": [{"role": "user", "content": prompt}],
                },
                timeout=timeout,
            )
        except requests.exceptions.RequestException as exc:
            raise RuntimeError(
                f"Anthropic request failed: {type(exc).__name__}"
            ) from None
        if resp.status_code >= 400:
            detail = ""
            try:
                detail = str(resp.json().get("error", {}).get("message", ""))[:200]
            except Exception:
                pass
            if api_key:
                detail = detail.replace(api_key, "***")
            raise RuntimeError(f"Anthropic API error {resp.status_code}: {detail}")
        return resp.json()

    data = run_with_progress(filepath, _call)
    if not isinstance(data, dict):
        return ""
    blocks = data.get("content") or []
    return "".join(
        b.get("text", "")
        for b in blocks
        if isinstance(b, dict) and b.get("type", "text") == "text"
    )
