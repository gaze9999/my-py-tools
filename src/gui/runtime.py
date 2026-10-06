"""Paths for editable source and standalone Windows/macOS applications."""

from __future__ import annotations

import os
from pathlib import Path
import sys


def is_bundled() -> bool:
    return bool(getattr(sys, "frozen", False))


def resource_root() -> Path:
    return Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2]))


def runner_path() -> Path:
    if is_bundled() and Path(sys.executable).stem == "launch-cli":
        return Path(sys.executable)
    name = "launch-worker.exe" if sys.platform == "win32" else "launch-worker"
    if sys.platform == "win32" and is_bundled():
        return resource_root() / name
    return Path(sys.executable).with_name(name)


def log_root() -> Path:
    if not is_bundled():
        return resource_root() / ".gui"
    if sys.platform == "win32":
        return Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData/Local") / "MyPyTools/logs"
    if sys.platform == "darwin":
        return Path.home() / "Library/Logs/MyPyTools"
    return Path.home() / ".local/state/my-py-tools"
