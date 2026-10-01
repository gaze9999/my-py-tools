"""Compare two directory trees by relative path, size, and SHA-256."""

from __future__ import annotations

import fnmatch
import hashlib
import os
from pathlib import Path
from typing import Iterable


DEFAULT_EXCLUDES = (
    ".git/**",
    ".hg/**",
    ".svn/**",
    ".venv/**",
    "**/__pycache__/**",
    "**/*.pyc",
    ".env",
    ".env.*",
    "**/.env",
    "**/.env.*",
    "*.key",
    "*.pem",
    "**/*.key",
    "**/*.pem",
    "credentials*",
    "secrets*",
    "**/credentials*",
    "**/secrets*",
)


def _matches(path: str, patterns: Iterable[str]) -> bool:
    name = path.rsplit("/", 1)[-1]
    return any(fnmatch.fnmatchcase(path, pattern) or fnmatch.fnmatchcase(name, pattern) for pattern in patterns)


def _digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _manifest(
    root: Path,
    includes: tuple[str, ...],
    excludes: tuple[str, ...],
    max_files: int,
) -> tuple[dict[str, dict[str, object]], int, list[dict[str, str]]]:
    manifest: dict[str, dict[str, object]] = {}
    excluded = 0
    errors: list[dict[str, str]] = []
    for current, directories, files in os.walk(root, followlinks=False):
        current_path = Path(current)
        kept_directories = []
        for name in directories:
            path = current_path / name
            relative = path.relative_to(root).as_posix() + "/"
            if path.is_symlink() or _matches(relative, excludes):
                excluded += 1
            else:
                kept_directories.append(name)
        directories[:] = kept_directories
        for name in sorted(files, key=str.casefold):
            path = current_path / name
            relative = path.relative_to(root).as_posix()
            if path.is_symlink() or _matches(relative, excludes) or (includes and not _matches(relative, includes)):
                excluded += 1
                continue
            if len(manifest) >= max_files:
                raise ValueError(f"File limit exceeded: {max_files}")
            try:
                stat = path.stat()
                manifest[relative] = {"size": stat.st_size, "sha256": _digest(path)}
            except OSError as exc:
                errors.append({"path": str(path), "error": str(exc)})
    return manifest, excluded, errors


def compare_trees(
    source: Path,
    target: Path,
    *,
    includes: Iterable[str] = (),
    excludes: Iterable[str] = DEFAULT_EXCLUDES,
    max_files: int = 20_000,
) -> dict[str, object]:
    source = source.expanduser().resolve(strict=True)
    target = target.expanduser().resolve(strict=True)
    if not source.is_dir() or not target.is_dir():
        raise ValueError("source and target must be existing directories")
    if source == target or source.is_relative_to(target) or target.is_relative_to(source):
        raise ValueError("source and target must be separate, non-nested directories")
    if not 1 <= max_files <= 200_000:
        raise ValueError("max_files must be between 1 and 200000")
    include_patterns = tuple(includes)
    exclude_patterns = tuple(excludes)
    left, left_excluded, left_errors = _manifest(source, include_patterns, exclude_patterns, max_files)
    right, right_excluded, right_errors = _manifest(target, include_patterns, exclude_patterns, max_files)
    shared = sorted(left.keys() & right.keys())
    changed = [
        {
            "path": path,
            "source": left[path],
            "target": right[path],
        }
        for path in shared
        if left[path] != right[path]
    ]
    return {
        "source": str(source),
        "target": str(target),
        "status": "match" if left.keys() == right.keys() and not changed and not left_errors and not right_errors else "different",
        "source_files": len(left),
        "target_files": len(right),
        "missing_in_target": sorted(left.keys() - right.keys()),
        "extra_in_target": sorted(right.keys() - left.keys()),
        "changed": changed,
        "excluded": {"source": left_excluded, "target": right_excluded},
        "errors": {"source": left_errors, "target": right_errors},
    }
