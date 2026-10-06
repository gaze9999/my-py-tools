"""Load the workspace core from an installation or this source checkout."""

from __future__ import annotations

import importlib
from pathlib import Path
import sys


def load_workspace_core():
    try:
        core = importlib.import_module("my_py_workspace_core")
    except ModuleNotFoundError as exc:
        if exc.name != "my_py_workspace_core":
            raise
        source = Path(__file__).resolve().parents[2] / "packages" / "workspace_core"
        if not (source / "my_py_workspace_core" / "__init__.py").is_file():
            raise RuntimeError("my-py-workspace-core is unavailable") from exc
        sys.path.insert(0, str(source))
        core = importlib.import_module("my_py_workspace_core")
    if getattr(core, "API_VERSION", None) != 1:
        raise RuntimeError("Unsupported workspace core API; expected API_VERSION=1")
    return core
