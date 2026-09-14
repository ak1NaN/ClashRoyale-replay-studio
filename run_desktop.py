"""Stable launcher; works regardless of the repository directory's name."""

import importlib.util
from pathlib import Path
import sys

root = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location(
    "native_engine", root / "__init__.py", submodule_search_locations=[str(root)]
)
module = importlib.util.module_from_spec(spec)
sys.modules["native_engine"] = module
spec.loader.exec_module(module)
from native_engine.desktop.gui import main

if __name__ == "__main__":
    main()
