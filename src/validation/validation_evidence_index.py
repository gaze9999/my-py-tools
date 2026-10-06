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
    parser.add_argument("--current-baseline", type=Path, help="Explicit JSON provenance for current source/artifact and affected paths")
    args = parser.parse_args(argv)
    try:
        current = json.loads(args.current_baseline.read_text(encoding="utf-8-sig")) if args.current_baseline else None
        core = load_workspace_core()
        if current is not None and not callable(getattr(core.validation, 'assess_evidence', None)):
            raise RuntimeError('Update the installed my-py-workspace-core to 0.2.0 or later for baseline comparison')
        result = core.validation.index_evidence(args.root, args.limit, current) if current is not None else core.validation.index_evidence(args.root, args.limit)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 1 if result["errors"] else 0
    except (OSError, UnicodeError, ValueError, RuntimeError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
