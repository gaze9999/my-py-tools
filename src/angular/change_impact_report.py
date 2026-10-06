#!/usr/bin/env python3
"""Summarize changed source files and nearby public-contract markers; read-only."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

MARKERS = ("selector:", "@Input", "@Output", "CustomEvent", "createCustomElement", "component-mapping")
SOURCE_EXTENSIONS = {".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".html", ".scss", ".sass", ".less", ".css", ".json"}


def changed(root: Path) -> list[str]:
    commands = (
        ("diff", "--name-only", "-z"),
        ("diff", "--cached", "--name-only", "-z"),
        ("ls-files", "--others", "--exclude-standard", "-z"),
    )
    names: set[str] = set()
    for command in commands:
        result = subprocess.run(("git", "-C", str(root), *command), check=True, capture_output=True)
        names.update(
            os.fsdecode(raw).replace("\\", "/")
            for raw in result.stdout.split(b"\0")
            if raw
        )
    return sorted(names)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="Repository root (default: current directory)")
    args = parser.parse_args(argv)
    try:
        root = args.root.expanduser().resolve()
        rows = []
        for name in changed(root):
            path = root / name
            markers = []
            if path.suffix.casefold() in SOURCE_EXTENSIONS and path.is_file():
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
