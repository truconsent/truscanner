import os
import re
from pathlib import Path

def get_version():
    """Dynamically fetch version from package metadata or pyproject.toml."""
    try:
        from importlib.metadata import version, PackageNotFoundError
        return version("truscanner")
    except (ImportError, PackageNotFoundError):
        # Fallback to parsing pyproject.toml
        try:
            pyproject_path = Path(__file__).parent.parent / "pyproject.toml"
            if pyproject_path.exists():
                with open(pyproject_path, "r", encoding="utf-8") as f:
                    content = f.read()
                    match = re.search(r'^version\s*=\s*[\'"]([^\'"]+)[\'"]', content, re.MULTILINE)
                    if match:
                        return match.group(1)
        except Exception:
            pass
    return "0.2.4" # Final fallback

__version__ = get_version()

from .main import main

__all__ = ["main", "__version__"]