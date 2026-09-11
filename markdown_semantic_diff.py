#!/usr/bin/env python3
"""Compare Markdown headings, list items, and table rows without remote reads or writes."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def tokens(path: Path) -> dict[str, list[str]]:
    result = {"headings": [], "list_items": [], "table_rows": []}
    for raw in path.read_text(encoding="utf-8-sig").splitlines():
        line = re.sub(r"\s+", " ", raw.strip())
        if re.match(r"^#{1,6} ", line):
            result["headings"].append(line)
        elif re.match(r"^(?:[-*+] |\d+[.)] )", line):
            result["list_items"].append(line)
        elif line.startswith("|") and line.endswith("|") and not re.match(r"^\|[ :|-]+\|$", line):
            result["table_rows"].append(line)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--left", type=Path, required=True)
    parser.add_argument("--right", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if not args.left.is_file() or not args.right.is_file():
            raise ValueError("Both inputs must be existing Markdown files")
        left, right = tokens(args.left), tokens(args.right)
        changes = {kind: {"only_left": sorted(set(left[kind]) - set(right[kind])),
                          "only_right": sorted(set(right[kind]) - set(left[kind]))}
                   for kind in left}
        print(json.dumps({"left": str(args.left), "right": str(args.right),
                          "left_sha256": digest(args.left), "right_sha256": digest(args.right), "changes": changes},
                         ensure_ascii=False, indent=2))
        return 0
    except (OSError, UnicodeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
