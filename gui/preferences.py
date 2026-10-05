"""Persist only the desktop language preference, with safe read defaults."""

from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile

from gui.runtime import log_root


LANGUAGES = {"zh-TW", "en"}


def preference_path() -> Path:
    return log_root() / "preferences.json"


def load_language(path: Path | None = None) -> str:
    try:
        value = json.loads((path or preference_path()).read_text(encoding="utf-8"))
        language = value.get("language") if isinstance(value, dict) else None
        return language if language in LANGUAGES else "zh-TW"
    except (OSError, UnicodeError, ValueError, TypeError):
        return "zh-TW"


def save_language(language: str, path: Path | None = None) -> None:
    if language not in LANGUAGES:
        raise ValueError("Unsupported language")
    target = path or preference_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=target.parent, suffix=".tmp", delete=False) as stream:
            temporary = Path(stream.name)
            json.dump({"language": language}, stream)
            stream.write("\n")
        os.replace(temporary, target)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
