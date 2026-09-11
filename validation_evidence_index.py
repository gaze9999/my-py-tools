#!/usr/bin/env python3
"""Summarize validation run results.json files without replaying builds or tests."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from tool_config import ToolConfig


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path)
    parser.add_argument("--root", type=Path, help="Run directory parent; overrides TOOL_VALIDATION_ROOT")
    parser.add_argument("--limit", type=int, default=20)
    args = parser.parse_args(argv)
    try:
        root = ToolConfig(args.env_file).path("TOOL_VALIDATION_ROOT", args.root)
        if args.limit < 1:
            raise ValueError("--limit must be positive")
        runs = []
        for path in sorted(root.glob("run-*/results.json"), reverse=True)[:args.limit]:
            data = json.loads(path.read_text(encoding="utf-8"))
            results = data.get("results", [])
            runs.append({"run": path.parent.name, "started": data.get("started"),
                         "results": [{"name": row.get("name"), "status": row.get("status"),
                                      "reason": row.get("reason"), "log": row.get("log")}
                                     for row in results]})
        print(json.dumps({"root": str(root), "runs": runs}, ensure_ascii=False, indent=2))
        return 0
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
