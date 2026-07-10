from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
ROOT_STR = str(ROOT)

if sys.path[0] != ROOT_STR:
    try:
        sys.path.remove(ROOT_STR)
    except ValueError:
        pass
    sys.path.insert(0, ROOT_STR)

loaded_app = sys.modules.get("app")
loaded_app_file = getattr(loaded_app, "__file__", "") if loaded_app else ""
if loaded_app_file and not str(Path(loaded_app_file).resolve()).startswith(str((ROOT / "app").resolve())):
    for module_name in list(sys.modules):
        if module_name == "app" or module_name.startswith("app."):
            del sys.modules[module_name]
