#!/usr/bin/env python3
"""Preview and quarantine disposable development caches and work artifacts.

Examples:
  python -m maintenance.cleanup_work_artifacts
  python -m maintenance.cleanup_work_artifacts --root
  python -m maintenance.cleanup_work_artifacts --root /path/to/project
  python -m maintenance.cleanup_work_artifacts --root /path/to/project --include-work-dirs --apply
  python -m maintenance.cleanup_work_artifacts --purge-quarantine --older-than-days 7
"""
from __future__ import annotations

import argparse
import json
import math
import os
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path


CACHE_DIRECTORIES = {
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".tox",
    ".nox",
    "htmlcov",
}
BUILD_DIRECTORIES = {"build", "dist"}
WORK_DIRECTORIES = {"work", ".work", "tmp", "temp"}
CACHE_FILE_NAMES = {".coverage", ".DS_Store", "Thumbs.db", "desktop.ini"}
CACHE_FILE_SUFFIXES = {".pyc", ".pyo", ".tmp", ".temp", ".swp"}
NEVER_ENTER = {".git", ".hg", ".svn", ".codex", "logs", "backups", "quarantine"}


@dataclass(frozen=True)
class Candidate:
    root: str
    path: str
    relative_path: str
    kind: str
    reason: str
    size_bytes: int
    modified_at: str


def utc_iso(timestamp: float | None = None) -> str:
    value = datetime.now(timezone.utc) if timestamp is None else datetime.fromtimestamp(timestamp, timezone.utc)
    return value.isoformat()


def run_stamp() -> str:
    return datetime.now().astimezone().strftime("%Y%m%d-%H%M%S-%f")


def default_output_directory() -> Path:
    return Path.home() / ".work-artifact-cleaner"


def resolve_roots(values: list[str]) -> list[Path]:
    roots: list[Path] = []
    for value in values or ["."]:
        root = Path(value).expanduser().resolve()
        if not root.is_dir():
            raise ValueError(f"Root does not exist or is not a directory: {root}")
        if root == Path(root.anchor):
            raise ValueError(f"Refusing to scan a filesystem root: {root}")
        if root not in roots:
            roots.append(root)
    return roots


def directory_size(path: Path) -> int:
    if path.is_symlink():
        return 0
    total = 0
    for current, directory_names, file_names in os.walk(path, followlinks=False):
        directory_names[:] = [
            name for name in directory_names if not (Path(current) / name).is_symlink()
        ]
        for name in file_names:
            try:
                total += (Path(current) / name).stat(follow_symlinks=False).st_size
            except OSError:
                continue
    return total


def contains_nested_repository(path: Path) -> bool:
    if not path.is_dir() or path.is_symlink():
        return False
    for current, directory_names, _ in os.walk(path, followlinks=False):
        if any(name in {".git", ".hg", ".svn"} for name in directory_names):
            return True
        directory_names[:] = [name for name in directory_names if name not in NEVER_ENTER]
    return False


def repository_root(path: Path) -> Path | None:
    working_directory = path if path.is_dir() else path.parent
    try:
        process = subprocess.run(
            ["git", "-C", str(working_directory), "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            timeout=10,
        )
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
        return None
    if process.returncode != 0:
        return None
    return Path(process.stdout.strip()).resolve()


def contains_tracked_content(path: Path) -> bool:
    repo = repository_root(path)
    if repo is None:
        return False
    try:
        relative = path.resolve().relative_to(repo).as_posix()
    except ValueError:
        return False
    pathspec = relative + ("/" if path.is_dir() and not path.is_symlink() else "")
    try:
        process = subprocess.run(
            ["git", "-C", str(repo), "ls-files", "-z", "--", pathspec],
            capture_output=True,
            check=False,
            timeout=20,
        )
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
        return True
    return process.returncode != 0 or bool(process.stdout)


def reason_for(path: Path, include_build: bool, include_work_dirs: bool) -> str | None:
    name = path.name
    lower_name = name.lower()
    if path.is_dir() and not path.is_symlink():
        if name in CACHE_DIRECTORIES:
            return "standard_cache_directory"
        if include_build and (lower_name in BUILD_DIRECTORIES or lower_name.endswith(".egg-info")):
            return "optional_build_directory"
        if include_work_dirs and lower_name in WORK_DIRECTORIES:
            return "optional_work_directory"
        return None
    if name in CACHE_FILE_NAMES or path.suffix.lower() in CACHE_FILE_SUFFIXES or name.endswith("~"):
        return "standard_cache_file"
    return None


def scan_root(
    root: Path,
    include_build: bool,
    include_work_dirs: bool,
    minimum_age_days: float,
) -> tuple[list[Candidate], list[dict[str, str]]]:
    cutoff = datetime.now(timezone.utc) - timedelta(days=minimum_age_days)
    candidates: list[Candidate] = []
    skipped: list[dict[str, str]] = []

    for current, directory_names, file_names in os.walk(root, topdown=True, followlinks=False):
        current_path = Path(current)
        directory_names[:] = [name for name in directory_names if name not in NEVER_ENTER]
        matched_directories: list[str] = []

        for name in directory_names:
            path = current_path / name
            reason = reason_for(path, include_build, include_work_dirs)
            if reason is None:
                continue
            matched_directories.append(name)
            if contains_nested_repository(path):
                skipped.append({"path": str(path), "reason": "contains_nested_repository"})
                continue
            if contains_tracked_content(path):
                skipped.append({"path": str(path), "reason": "contains_git_tracked_content"})
                continue
            try:
                stat = path.stat(follow_symlinks=False)
            except OSError as error:
                skipped.append({"path": str(path), "reason": f"stat_failed: {error}"})
                continue
            if datetime.fromtimestamp(stat.st_mtime, timezone.utc) > cutoff:
                skipped.append({"path": str(path), "reason": "newer_than_minimum_age"})
                continue
            candidates.append(
                Candidate(
                    root=str(root),
                    path=str(path),
                    relative_path=path.relative_to(root).as_posix(),
                    kind="directory",
                    reason=reason,
                    size_bytes=directory_size(path),
                    modified_at=utc_iso(stat.st_mtime),
                )
            )
        directory_names[:] = [name for name in directory_names if name not in matched_directories]

        for name in file_names:
            path = current_path / name
            reason = reason_for(path, include_build, include_work_dirs)
            if reason is None:
                continue
            if contains_tracked_content(path):
                skipped.append({"path": str(path), "reason": "git_tracked"})
                continue
            try:
                stat = path.stat(follow_symlinks=False)
            except OSError as error:
                skipped.append({"path": str(path), "reason": f"stat_failed: {error}"})
                continue
            if datetime.fromtimestamp(stat.st_mtime, timezone.utc) > cutoff:
                skipped.append({"path": str(path), "reason": "newer_than_minimum_age"})
                continue
            candidates.append(
                Candidate(
                    root=str(root),
                    path=str(path),
                    relative_path=path.relative_to(root).as_posix(),
                    kind="file",
                    reason=reason,
                    size_bytes=stat.st_size,
                    modified_at=utc_iso(stat.st_mtime),
                )
            )
    return candidates, skipped


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    temporary.replace(path)


def append_event(path: Path, event: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps({"timestamp": utc_iso(), **event}, ensure_ascii=False) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def quarantine(
    candidates: list[Candidate],
    roots: list[Path],
    destination: Path,
    event_log: Path,
) -> list[dict[str, str]]:
    root_numbers = {str(root): index for index, root in enumerate(roots, start=1)}
    moved: list[dict[str, str]] = []
    for candidate in candidates:
        source = Path(candidate.path)
        root_number = root_numbers[candidate.root]
        root_name = Path(candidate.root).name or "scan"
        target = destination / f"root-{root_number:02d}-{root_name}" / candidate.relative_path
        if not source.exists() and not source.is_symlink():
            append_event(event_log, {"event": "skipped_missing", "source": str(source)})
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists() or target.is_symlink():
            raise FileExistsError(f"Quarantine target already exists: {target}")
        shutil.move(str(source), str(target))
        record = {"source": str(source), "destination": str(target)}
        moved.append(record)
        append_event(event_log, {"event": "quarantined", **record})
    return moved


def purge_quarantine(base: Path, older_than_days: float, event_log: Path) -> tuple[int, int]:
    if not base.is_dir():
        return 0, 0
    cutoff = datetime.now(timezone.utc) - timedelta(days=older_than_days)
    count = 0
    size = 0
    for run_directory in base.iterdir():
        if not run_directory.is_dir() or run_directory.is_symlink():
            continue
        if datetime.fromtimestamp(run_directory.stat().st_mtime, timezone.utc) > cutoff:
            continue
        run_size = directory_size(run_directory)
        shutil.rmtree(run_directory)
        count += 1
        size += run_size
        append_event(event_log, {"event": "purged", "path": str(run_directory), "size_bytes": run_size})
    return count, size


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        action="append",
        nargs="?",
        const=".",
        default=[],
        help="Directory to scan; may be repeated. Omit its value to use the current directory.",
    )
    parser.add_argument("--apply", action="store_true", help="Move candidates to quarantine; default is preview.")
    parser.add_argument("--include-build", action="store_true", help="Include untracked build/dist/*.egg-info directories.")
    parser.add_argument("--include-work-dirs", action="store_true", help="Include untracked work/.work/tmp/temp directories.")
    parser.add_argument("--min-age-days", type=float, default=1.0, help="Minimum age in days; default: 1.")
    parser.add_argument("--output-dir", type=Path, default=default_output_directory(), help="Parent for logs and quarantine.")
    parser.add_argument("--purge-quarantine", action="store_true", help="Permanently delete old quarantine runs.")
    parser.add_argument("--older-than-days", type=float, default=7.0, help="Quarantine retention before purge; default: 7.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    day_values = (args.min_age_days, args.older_than_days)
    if any(not math.isfinite(value) or value < 0 or value > 365_000 for value in day_values):
        print("error: day values must be finite and between 0 and 365000", file=sys.stderr)
        return 2

    output_directory = args.output_dir.expanduser().resolve()
    name = f"cache-cleanup-{run_stamp()}"
    log_directory = output_directory / "logs" / name
    event_log = log_directory / "cleanup.jsonl"
    quarantine_base = output_directory / "quarantine"

    try:
        if args.purge_quarantine:
            count, size = purge_quarantine(quarantine_base, args.older_than_days, event_log)
            result = {"mode": "purge", "status": "completed", "removed_runs": count, "removed_bytes": size}
            write_json(log_directory / "result.json", result)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0

        roots = resolve_roots(args.root)
        candidates: list[Candidate] = []
        skipped: list[dict[str, str]] = []
        for root in roots:
            root_candidates, root_skipped = scan_root(
                root,
                include_build=args.include_build,
                include_work_dirs=args.include_work_dirs,
                minimum_age_days=args.min_age_days,
            )
            candidates.extend(root_candidates)
            skipped.extend(root_skipped)

        manifest = {
            "schema_version": 1,
            "mode": "quarantine" if args.apply else "preview",
            "created_at": utc_iso(),
            "roots": [str(root) for root in roots],
            "candidate_count": len(candidates),
            "candidate_bytes": sum(item.size_bytes for item in candidates),
            "candidates": [asdict(item) for item in candidates],
            "skipped": skipped,
        }
        write_json(log_directory / "manifest.json", manifest)
        append_event(event_log, {"event": "scan_completed", "candidate_count": len(candidates)})

        if not args.apply:
            print(json.dumps({key: manifest[key] for key in ("mode", "candidate_count", "candidate_bytes")}, ensure_ascii=False, indent=2))
            print(f"Manifest: {log_directory / 'manifest.json'}")
            return 0

        quarantine_directory = quarantine_base / name
        moved = quarantine(candidates, roots, quarantine_directory, event_log)
        result = {
            "mode": "quarantine",
            "status": "completed",
            "moved_count": len(moved),
            "candidate_bytes": manifest["candidate_bytes"],
            "quarantine_directory": str(quarantine_directory),
            "moved": moved,
        }
        write_json(log_directory / "result.json", result)
        print(json.dumps({key: result[key] for key in ("status", "moved_count", "candidate_bytes", "quarantine_directory")}, ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        append_event(event_log, {"event": "failed", "error": str(error)})
        print(f"error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
