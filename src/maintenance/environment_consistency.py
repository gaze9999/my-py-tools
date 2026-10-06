#!/usr/bin/env python3
"""Compare reusable Skills or environment trees without modifying either side."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from shared.workspace_core import load_workspace_core


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--target", type=Path, required=True)
    parser.add_argument("--include", action="append", default=[], help="Glob to include; repeatable")
    parser.add_argument("--exclude", action="append", default=[], help="Additional glob to exclude; repeatable")
    parser.add_argument("--no-default-excludes", action="store_true")
    parser.add_argument("--max-files", type=int, default=20_000)
    args = parser.parse_args(argv)
    try:
        core = load_workspace_core()
        excludes = tuple(args.exclude)
        if not args.no_default_excludes:
            excludes = core.environment.DEFAULT_EXCLUDES + excludes
        result = core.environment.compare_trees(
            args.source,
            args.target,
            includes=args.include,
            excludes=excludes,
            max_files=args.max_files,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["status"] == "match" else 1
    except (OSError, UnicodeError, ValueError, RuntimeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
