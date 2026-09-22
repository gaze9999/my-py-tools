"""Read optional ``TOOL_*`` variables without making tools depend on .env."""

from __future__ import annotations

import os
import math
import re
import sys
from pathlib import Path


ENV_KEY_RE = re.compile(r"TOOL_[A-Z0-9_]+")
VARIABLE_RE = re.compile(r"\$\{(TOOL_[A-Z0-9_]+)\}")
REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


class ToolConfig:
    """Load optional tool variables from .env and the process environment.

    Invalid or missing files do not block CLI-only operation. Process
    environment values override the local file. Paths intentionally do not
    belong in this layer; each command accepts its own path arguments.
    """

    def __init__(self, env_file: str | Path | None = None):
        self.file = (
            Path(env_file) if env_file is not None else REPOSITORY_ROOT / ".env"
        ).expanduser().resolve()
        self.values: dict[str, str] = {}
        self.warnings: list[str] = []
        self._read_file(env_file is not None)
        self.values.update(
            (key, value.strip())
            for key, value in os.environ.items()
            if ENV_KEY_RE.fullmatch(key) and value.strip()
        )
        self._expand_values()

    def _read_file(self, explicitly_selected: bool) -> None:
        if not self.file.is_file():
            if explicitly_selected:
                self.warnings.append(f"environment file not found: {self.file}")
            return
        try:
            lines = self.file.read_text(encoding="utf-8-sig").splitlines()
        except (OSError, UnicodeError) as exc:
            self.warnings.append(f"unable to read environment file {self.file}: {exc}")
            return
        for number, raw_line in enumerate(lines, 1):
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            key, separator, value = line.partition("=")
            key, value = key.strip(), value.strip()
            if not separator or not ENV_KEY_RE.fullmatch(key):
                self.warnings.append(f"ignored invalid setting at {self.file}:{number}")
                continue
            if key in self.values:
                self.warnings.append(f"ignored duplicate setting {key} at {self.file}:{number}")
                continue
            if value.startswith(("\"", "'")):
                if len(value) < 2 or value[-1] != value[0]:
                    self.warnings.append(f"ignored unclosed quoted setting {key} at {self.file}:{number}")
                    continue
                value = value[1:-1]
            self.values[key] = value

    def _expand_values(self) -> None:
        expanded: dict[str, str] = {}

        def expand(key: str, stack: tuple[str, ...] = ()) -> str:
            if key in expanded:
                return expanded[key]
            if key in stack:
                raise ValueError(" -> ".join((*stack, key)))
            raw = self.values.get(key, "")

            def replace(match: re.Match[str]) -> str:
                referenced = match.group(1)
                if referenced not in self.values:
                    raise KeyError(referenced)
                return expand(referenced, (*stack, key))

            value = VARIABLE_RE.sub(replace, raw).strip()
            expanded[key] = value
            return value

        for key in tuple(self.values):
            try:
                expand(key)
            except (KeyError, ValueError) as exc:
                self.warnings.append(f"ignored unresolvable setting {key}: {exc}")
                expanded.pop(key, None)
        self.values = expanded

    def emit_warnings(self) -> None:
        for warning in self.warnings:
            print(f"warning: {warning}", file=sys.stderr)

    def value(self, key: str, default: str | None = None) -> str:
        return self.values.get(key) or default or ""

    def positive_float(self, key: str, default: float) -> float:
        raw = self.value(key, str(default))
        try:
            value = float(raw)
        except ValueError:
            self.warnings.append(f"invalid {key}={raw!r}; using {default}")
            return default
        if not math.isfinite(value) or value <= 0:
            self.warnings.append(f"invalid {key}={raw!r}; using {default}")
            return default
        return value

    def namespace(self, override: str | None = None) -> str:
        value = override or self.value("TOOL_HISTORY_NAMESPACE", "project-task")
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}", value):
            fallback = "project-task"
            self.warnings.append(
                f"invalid TOOL_HISTORY_NAMESPACE={value!r}; using {fallback}"
            )
            return fallback
        return value
