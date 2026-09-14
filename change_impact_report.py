#!/usr/bin/env python3
"""Summarize changed source files and nearby public-contract markers; read-only."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from tool_config import ToolConfig

MARKERS = ("selector:", "@Input", "@Output", "CustomEvent", "createCustomElement", "component-mapping")


def changed(root: Path) -> list[str]:
    commands = (("diff", "--name-only"), ("diff", "--cached", "--name-only"), ("ls-files", "--others", "--exclude-standard"))
    names: set[str] = set()
    for command in commands:
        result = subprocess.run(("git", "-C", str(root), *command), check=True, capture_output=True, text=True, encoding="utf-8")
        names.update(line.replace("\\", "/") for line in result.stdout.splitlines() if line)
    return sorted(names)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path)
    parser.add_argument("--root", type=Path, help="Repository root; overrides TOOL_GENERATOR_ROOT")
    args = parser.parse_args(argv)
    try:
        root = ToolConfig(args.env_file).path("TOOL_GENERATOR_ROOT", args.root)
        rows = []
        for name in changed(root):
            path = root / name
            markers = []
            if path.suffix in {".ts", ".html", ".scss", ".css", ".json"} and path.is_file():
                text = path.read_text(encoding="utf-8", errors="replace")
                markers = [marker for marker in MARKERS if marker in text]
            rows.append({"path": name, "exists": path.exists(), "public_contract_markers": markers})
        print(json.dumps({"root": str(root), "changed_files": rows}, ensure_ascii=False, indent=2))
        return 0
    except (OSError, subprocess.CalledProcessError, UnicodeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
