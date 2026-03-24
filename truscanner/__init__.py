import sys
import types
from typing import Any

from src import __version__

from .api import scan, scan_ai, scan_regex


class _CallableModule(types.ModuleType):
    """Allow `import truscanner; truscanner(path)` in Python code."""

    def __call__(self, path_or_url: str, **kwargs: Any):
        return scan(path_or_url, **kwargs)


def truscanner(path_or_url: str, **kwargs: Any):
    """Function alias for users who prefer explicit function calls."""
    return scan(path_or_url, **kwargs)


__all__ = ["scan", "scan_regex", "scan_ai", "truscanner", "__version__"]

sys.modules[__name__].__class__ = _CallableModule
