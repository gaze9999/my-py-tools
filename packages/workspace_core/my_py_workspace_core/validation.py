"""Read and normalize validation evidence without replaying commands."""

from __future__ import annotations

import json
from pathlib import Path


def read_run(path: Path) -> dict[str, object]:
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict):
        raise ValueError("top-level JSON must be an object")
    results = data.get("results", [])
    if not isinstance(results, list):
        raise ValueError("results must be an array")
    normalized = []
    for index, row in enumerate(results):
        if not isinstance(row, dict):
            raise ValueError(f"results[{index}] must be an object")
        normalized.append(
            {
                "name": row.get("name"),
                "status": row.get("status"),
                "reason": row.get("reason"),
                "command": row.get("command"),
                "log": row.get("log"),
                "source": row.get("source"),
                "baseline": row.get("baseline"),
            }
        )
    return {
        "run": path.parent.name,
        "path": str(path.resolve()),
        "started": data.get("started"),
        "source": data.get("source"),
        "baseline": data.get("baseline"),
        "results": normalized,
        "unverified": data.get("unverified", []),
    }


def index_evidence(root: Path, limit: int = 20) -> dict[str, object]:
    root = root.expanduser().resolve(strict=True)
    if not root.is_dir():
        raise ValueError(f"validation root is not a directory: {root}")
    if not 1 <= limit <= 1000:
        raise ValueError("limit must be between 1 and 1000")
    runs = []
    errors = []
    for path in sorted(root.glob("run-*/results.json"), reverse=True)[:limit]:
        try:
            runs.append(read_run(path))
        except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as exc:
            errors.append({"run": path.parent.name, "path": str(path), "error": str(exc)})
    return {"root": str(root), "runs": runs, "errors": errors}
