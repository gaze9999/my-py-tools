#!/usr/bin/env python3
"""Summarize validation run results.json files without replaying builds or tests."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from shared.workspace_core import load_workspace_core

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="Run directory parent (default: current directory)")
    parser.add_argument("--limit", type=int, default=20)
    args = parser.parse_args(argv)
    try:
        result = load_workspace_core().validation.index_evidence(args.root, args.limit)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 1 if result["errors"] else 0
    except (OSError, UnicodeError, ValueError, RuntimeError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
