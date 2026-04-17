"""Token counting helpers used for scan usage reporting."""

from __future__ import annotations

from functools import lru_cache
from typing import Optional

try:
    import tiktoken
except ImportError:  # pragma: no cover - fallback when dependency is unavailable
    tiktoken = None  # type: ignore[assignment]


HAS_TIKTOKEN = tiktoken is not None


DEFAULT_ENCODING = "o200k_base"


@lru_cache(maxsize=32)
def _get_encoding(model: Optional[str] = None):
    if tiktoken is None:
        return None

    if model:
        try:
            return tiktoken.encoding_for_model(model)
        except Exception:
            pass

    try:
        return tiktoken.get_encoding(DEFAULT_ENCODING)
    except Exception:
        return None


def count_tokens(text: str, model: Optional[str] = None) -> int:
    """Count tokens for *text* using tiktoken when available.

    Falls back to a coarse whitespace-based estimate if tiktoken is not
    installed or the encoding cannot be resolved.
    """
    if not text:
        return 0

    encoding = _get_encoding(model)
    if encoding is not None:
        try:
            return len(encoding.encode(text))
        except Exception:
            pass

    # Fallback approximation keeps the scan usable even when tiktoken is
    # missing in local/dev environments.
    return max(1, len(text.split()))


def tokenizer_source() -> str:
    return "tiktoken" if HAS_TIKTOKEN else "fallback"
