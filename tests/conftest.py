import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


loaded_src = sys.modules.get("src")
if loaded_src is not None:
    src_file = getattr(loaded_src, "__file__", "") or ""
    if "site-packages" in src_file:
        for module_name in list(sys.modules):
            if module_name == "src" or module_name.startswith("src."):
                del sys.modules[module_name]


loaded_truscanner = sys.modules.get("truscanner")
if loaded_truscanner is not None:
    truscanner_file = getattr(loaded_truscanner, "__file__", "") or ""
    if "site-packages" in truscanner_file:
        for module_name in list(sys.modules):
            if module_name == "truscanner" or module_name.startswith("truscanner."):
                del sys.modules[module_name]
