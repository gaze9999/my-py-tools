"""Read and validate the repository release version."""

from __future__ import annotations

from pathlib import Path
import re


VERSION_PATTERN = re.compile(
    r"(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-[0-9A-Za-z]+(?:[.-][0-9A-Za-z]+)*)?"
    r"(?:\+[0-9A-Za-z]+(?:[.-][0-9A-Za-z]+)*)?"
)


def repository_version(root: Path | None = None) -> str:
    path = (root or Path(__file__).resolve().parents[1]) / "VERSION"
    value = path.read_text(encoding="utf-8").strip()
    if not VERSION_PATTERN.fullmatch(value):
        raise ValueError(f"Invalid VERSION value: {value!r}")
    return value

