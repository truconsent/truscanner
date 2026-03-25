"""AI provider implementations for truscanner.

Each provider module exposes a single ``call_*`` function that accepts a prompt
and returns the raw LLM response text. The :mod:`src.ai_scanner` module selects
the appropriate provider at runtime based on user configuration.

Adding a new provider
---------------------
1. Create ``src/providers/<name>.py`` with a ``call_<name>(prompt, filepath, ...)``
   function that uses :func:`~src.providers.base.run_with_progress` for the
   spinner display.
2. Export the function here.
3. Handle the new provider key in :meth:`src.ai_scanner.AIScanner.scan_file`.
"""

from .bedrock import call_bedrock
from .ollama import call_ollama, list_models as list_ollama_models
from .openai import call_openai

__all__ = [
    "call_ollama",
    "list_ollama_models",
    "call_openai",
    "call_bedrock",
]
