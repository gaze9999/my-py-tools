#!/usr/bin/env python3
"""Locate Markdown extracts by recorded source path and SHA-256 metadata."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys
from typing import Iterable


SKIP_DIRECTORIES = {".git", ".hg", ".svn", ".venv", "__pycache__", "build", "dist", "node_modules"}
SOURCE_RE = re.compile(r"^- Source(?: path)?:\s+(?:`(?P<quoted>.+)`|(?P<plain>.+))$")
HASH_RE = re.compile(r"^- Source SHA-256:\s+`?([0-9a-fA-F]{64})`?$")
COMBINED_SOURCE_RE = re.compile(r"^- `(.+)` \([^,]+, SHA-256 `([0-9a-fA-F]{64})`\)$")
EXTRACTED_RE = re.compile(r"^- Extracted on: (.+)$")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def metadata_records(text: str) -> list[dict[str, str | None]]:
    records: list[dict[str, str | None]] = []
    current: dict[str, str | None] | None = None
    for line in text.splitlines():
        combined_match = COMBINED_SOURCE_RE.match(line)
        if combined_match:
            if current is not None:
                records.append(current)
            current = {
                "source": combined_match.group(1),
                "source_sha256": combined_match.group(2).lower(),
                "extracted_on": None,
            }
            continue
        source_match = SOURCE_RE.match(line)
        if source_match:
            if current is not None:
                records.append(current)
            source = source_match.group("quoted") or source_match.group("plain")
            current = {"source": source.strip(), "source_sha256": None, "extracted_on": None}
            continue
        if current is None:
            continue
        hash_match = HASH_RE.match(line)
        if hash_match:
            current["source_sha256"] = hash_match.group(1).lower()
            continue
        extracted_match = EXTRACTED_RE.match(line)
        if extracted_match:
            current["extracted_on"] = extracted_match.group(1).strip()
    if current is not None:
        records.append(current)
    return records


def _normalized_path(value: str | Path) -> str:
    return os.path.normcase(os.path.abspath(os.path.expanduser(str(value))))


def _markdown_files(roots: Iterable[Path], max_files: int) -> tuple[list[Path], bool]:
    files: list[Path] = []
    for root in roots:
        for current, directories, names in os.walk(root, followlinks=False):
            directories[:] = [
                name
                for name in directories
                if name not in SKIP_DIRECTORIES and not name.startswith(".")
            ]
            for name in sorted(names, key=str.casefold):
                if not name.casefold().endswith(".md"):
                    continue
                files.append(Path(current, name))
                if len(files) >= max_files:
                    return files, True
    return files, False


def locate_extracts(
    roots: Iterable[Path],
    *,
    source: Path | None = None,
    source_sha256: str | None = None,
    limit: int = 50,
    max_files: int = 10_000,
) -> dict[str, object]:
    resolved_roots = [Path(root).expanduser().resolve(strict=True) for root in roots]
    if not resolved_roots or any(not root.is_dir() for root in resolved_roots):
        raise ValueError("At least one existing search root is required")
    if not 1 <= limit <= 1000:
        raise ValueError("limit must be between 1 and 1000")
    if not 1 <= max_files <= 100_000:
        raise ValueError("max_files must be between 1 and 100000")

    resolved_source = source.expanduser().resolve(strict=True) if source is not None else None
    if resolved_source is not None and not resolved_source.is_file():
        raise ValueError(f"Source is not a file: {resolved_source}")
    expected_hash = (source_sha256 or (sha256(resolved_source) if resolved_source else "")).lower()
    if expected_hash and not re.fullmatch(r"[0-9a-f]{64}", expected_hash):
        raise ValueError("source_sha256 must be 64 hexadecimal characters")
    if resolved_source is None and not expected_hash:
        raise ValueError("Provide source or source_sha256")

    source_path = _normalized_path(resolved_source) if resolved_source else None
    source_name = resolved_source.name.casefold() if resolved_source else None
    markdown_files, scan_truncated = _markdown_files(resolved_roots, max_files)
    candidates: list[dict[str, object]] = []
    errors: list[dict[str, str]] = []
    for markdown_path in markdown_files:
        try:
            records = metadata_records(markdown_path.read_text(encoding="utf-8-sig"))
        except (OSError, UnicodeError) as exc:
            errors.append({"path": str(markdown_path), "error": str(exc)})
            continue
        for record in records:
            recorded_source = str(record["source"])
            recorded_hash = str(record["source_sha256"] or "").lower()
            path_match = source_path is not None and _normalized_path(recorded_source) == source_path
            hash_match = bool(expected_hash and recorded_hash == expected_hash)
            name_match = source_name is not None and Path(recorded_source).name.casefold() == source_name
            if not (path_match or hash_match or name_match):
                continue
            if hash_match:
                status, rank = "current", 0
            elif path_match and recorded_hash:
                status, rank = "stale", 1
            else:
                status, rank = "candidate", 2
            reasons = [
                reason
                for matched, reason in (
                    (path_match, "source_path"),
                    (hash_match, "source_sha256"),
                    (name_match, "source_filename"),
                )
                if matched
            ]
            candidates.append(
                {
                    "markdown": str(markdown_path.resolve()),
                    "recorded_source": recorded_source,
                    "recorded_source_sha256": recorded_hash or None,
                    "extracted_on": record["extracted_on"],
                    "status": status,
                    "match_reasons": reasons,
                    "_rank": rank,
                }
            )
    candidates.sort(
        key=lambda item: (
            int(item["_rank"]),
            str(item["markdown"]).casefold(),
            str(item["recorded_source"]).casefold(),
        )
    )
    selected = candidates[:limit]
    for item in selected:
        item.pop("_rank", None)
    return {
        "source": str(resolved_source) if resolved_source else None,
        "source_sha256": expected_hash or None,
        "roots": [str(root) for root in resolved_roots],
        "candidates": selected,
        "candidate_count": len(candidates),
        "candidate_truncated": len(candidates) > limit,
        "scanned_markdown_files": len(markdown_files),
        "scan_truncated": scan_truncated,
        "errors": errors,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, action="append", required=True, help="Search root; repeatable")
    parser.add_argument("--source", type=Path, help="Existing original source file")
    parser.add_argument("--source-sha256", help="Known source SHA-256 when the original is unavailable")
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--max-files", type=int, default=10_000)
    args = parser.parse_args(argv)
    try:
        result = locate_extracts(
            args.root,
            source=args.source,
            source_sha256=args.source_sha256,
            limit=args.limit,
            max_files=args.max_files,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 1 if result["errors"] else 0
    except (OSError, UnicodeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
