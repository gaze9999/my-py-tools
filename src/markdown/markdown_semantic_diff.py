#!/usr/bin/env python3
"""Compare Markdown headings, list items, and table rows without remote reads or writes."""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import re
import sys
from pathlib import Path


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def tokens(path: Path) -> dict[str, list[str]]:
    result = {"headings": [], "list_items": [], "table_rows": []}
    fence: tuple[str, int] | None = None
    for raw in path.read_text(encoding="utf-8-sig").splitlines():
        marker = re.match(r"^ {0,3}(`{3,}|~{3,})(.*)$", raw)
        if marker:
            run, tail = marker.groups()
            if fence is None:
                fence = (run[0], len(run))
            elif run[0] == fence[0] and len(run) >= fence[1] and not tail.strip():
                fence = None
            continue
        if fence is not None:
            continue
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
        changes = {}
        for kind in left:
            left_counts = Counter(left[kind])
            right_counts = Counter(right[kind])
            changes[kind] = {
                "only_left": sorted((left_counts - right_counts).elements()),
                "only_right": sorted((right_counts - left_counts).elements()),
                "order_changed": left_counts == right_counts and left[kind] != right[kind],
            }
        print(json.dumps({"left": str(args.left), "right": str(args.right),
                          "left_sha256": digest(args.left), "right_sha256": digest(args.right), "changes": changes},
                         ensure_ascii=False, indent=2))
        return 0
    except (OSError, UnicodeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
