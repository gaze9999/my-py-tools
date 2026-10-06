"""Read and normalize validation evidence without replaying commands."""

from __future__ import annotations

import json
from pathlib import Path
import re


def assess_evidence(recorded: object, current: dict) -> dict[str, object]:
    """Compare explicitly supplied provenance; never read files or replay commands."""
    if not isinstance(current, dict):
        raise ValueError("current baseline must be an object")

    def validate(value):
        for key in ("source_diff_sha256", "artifact_sha256"):
            if key in value and (not isinstance(value[key], str) or not re.fullmatch(r"[a-fA-F0-9]{64}", value[key])):
                raise ValueError("invalid " + key)
        if "source_revision" in value and (not isinstance(value["source_revision"], str) or not re.fullmatch(r"[a-fA-F0-9]{7,64}", value["source_revision"])):
            raise ValueError("invalid source_revision")
        hashes = value.get("source_files", {})
        if not isinstance(hashes, dict) or any(not isinstance(key, str) or not key or not isinstance(sha, str) or not re.fullmatch(r"[a-fA-F0-9]{64}", sha) for key, sha in hashes.items()):
            raise ValueError("invalid source_files")
        for key in ("affected_paths", "covered_paths"):
            if key in value and (not isinstance(value[key], list) or any(not isinstance(path, str) or not path for path in value[key])):
                raise ValueError("invalid " + key)

    validate(current)
    result = {"status": "unverified", "scope": "supplied_source_and_artifact_provenance", "reasons": [], "uncovered_paths": []}
    if not isinstance(recorded, dict):
        result["reasons"] = ["recorded_baseline_missing_or_unstructured"]
        return result
    try:
        validate(recorded)
    except ValueError:
        result["reasons"] = ["recorded_baseline_malformed"]
        return result
    reasons, changed, missing, matched = [], False, False, False
    recorded_files = recorded.get("source_files", {})
    for path, expected in recorded_files.items():
        actual = current.get("source_files", {}).get(path)
        if actual is None:
            missing = True
            reasons.append("source_file_hash_missing:" + path)
        elif actual.lower() != expected.lower():
            changed = True
            reasons.append("source_file_changed:" + path)
        else:
            matched = True
    identity_matches = []
    for key in ("source_revision", "source_diff_sha256"):
        if key not in recorded or key not in current:
            identity_matches.append(False)
        else:
            same = recorded[key].lower() == current[key].lower()
            identity_matches.append(same)
            if not same:
                reasons.append(key + "_changed")
    if all(identity_matches):
        matched = True
    elif not recorded_files:
        matched = False
        reasons.append("current_source_identity_not_established")
        changed = any(reason in {"source_revision_changed", "source_diff_sha256_changed"} for reason in reasons)
    if "artifact_sha256" in recorded:
        if "artifact_sha256" not in current:
            missing = True
            reasons.append("artifact_hash_missing")
        elif recorded["artifact_sha256"].lower() != current["artifact_sha256"].lower():
            changed = True
            reasons.append("artifact_changed")
    affected = current.get("affected_paths")
    covered = recorded.get("covered_paths")
    coverage_known = affected is not None and covered is not None
    uncovered = sorted(set(affected or []) - set(covered or []))
    if not coverage_known:
        reasons.append("affected_path_coverage_unknown")
    elif uncovered:
        reasons.append("affected_paths_not_covered")
    if coverage_known and not all(identity_matches):
        unhashed = sorted(set(affected) - recorded_files.keys())
        if unhashed:
            missing = True
            reasons.append("affected_source_hashes_missing")
    status = "outdated" if changed else "unverified" if not matched else "partial" if missing or not coverage_known or uncovered else "current"
    return {**result, "status": status, "reasons": reasons, "uncovered_paths": uncovered}


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


def index_evidence(root: Path, limit: int = 20, current: dict | None = None) -> dict[str, object]:
    if current is not None:
        assess_evidence(None, current)
    root = root.expanduser().resolve(strict=True)
    if not root.is_dir():
        raise ValueError(f"validation root is not a directory: {root}")
    if not 1 <= limit <= 1000:
        raise ValueError("limit must be between 1 and 1000")
    runs = []
    errors = []
    for path in sorted(root.glob("run-*/results.json"), reverse=True)[:limit]:
        try:
            run = read_run(path)
            if current is not None:
                run["validity"] = assess_evidence(run["baseline"], current)
                for row in run["results"]:
                    row["validity"] = assess_evidence(row["baseline"] if row["baseline"] is not None else run["baseline"], current)
            runs.append(run)
        except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as exc:
            errors.append({"run": path.parent.name, "path": str(path), "error": str(exc)})
    return {"root": str(root), "runs": runs, "errors": errors}
