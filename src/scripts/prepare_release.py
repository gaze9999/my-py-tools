#!/usr/bin/env python3
"""Build a reviewed my-py-tools release bundle and its independent core wheels."""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile


SEMVER = re.compile(
    r"v?(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-[0-9A-Za-z]+(?:[.-][0-9A-Za-z]+)*)?"
    r"(?:\+[0-9A-Za-z]+(?:[.-][0-9A-Za-z]+)*)?"
)
PROJECT_VERSION = re.compile(r'(?m)^version\s*=\s*"([^"]+)"\s*$')
PRODUCER = "my-py-tools.prepare_release.v1"
MANIFEST = "release-manifest.json"
PACKAGE_PROJECTS = (
    (Path("."), "my-py-document-core"),
    (Path("packages/workspace_core"), "my-py-workspace-core"),
)
SKIP_DIRS = {
    ".git", ".gui", ".bundle", ".venv", "venv", "build", "dist", "__pycache__",
    ".pytest_cache", ".mypy_cache", ".ruff_cache", ".tox", ".nox", "node_modules", ".build-inputs",
}
SKIP_FILES = (
    "*.pyc", "*.pyo", "*.log", "*.tmp", "*.temp", "*.bak", "*.pem", "*.key",
    "*.swp", "*.swo", "*~", ".DS_Store", "Thumbs.db", "Desktop.ini",
)


def normalize_version(value: str) -> str:
    value = value.strip()
    if not SEMVER.fullmatch(value):
        raise ValueError(f"Invalid version: {value}; use X.Y.Z or vX.Y.Z")
    return value.removeprefix("v")


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def atomic_write(path: Path, data: bytes) -> None:
    with tempfile.NamedTemporaryFile(dir=path.parent, prefix=path.name + ".", suffix=".tmp", delete=False) as stream:
        temporary = Path(stream.name)
        stream.write(data)
    try:
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def git_output(repo: Path, *args: str) -> str | None:
    if not (repo / ".git").exists():
        return None
    try:
        result = subprocess.run(
            ["git", "-c", f"safe.directory={repo.as_posix()}", "-C", str(repo), *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return result.stdout if result.returncode == 0 else None


def ignored(path: Path) -> bool:
    return (
        bool(SKIP_DIRS.intersection(path.parts))
        or path.as_posix().startswith(("setup/runtime/", "src/gui/resources/", "src/gui/frontend/src/vendor/"))
        or (path.name.startswith(".env") and path.name != ".env.example")
        or path.name.casefold().startswith(("credentials", "secrets"))
        or any(fnmatch.fnmatch(path.name, pattern) for pattern in SKIP_FILES)
    )


def source_snapshot(repo: Path, version: str) -> dict[str, tuple[Path, bytes]]:
    listed = git_output(repo, "ls-files", "--cached", "--others", "--exclude-standard", "-z")
    if listed is None:
        candidates = [path for path in repo.rglob("*") if path.is_file()]
    else:
        candidates = [repo / value for value in listed.split("\0") if value]
    files: dict[str, tuple[Path, bytes]] = {}
    root = repo.resolve()
    for path in sorted(candidates, key=lambda item: item.as_posix().casefold()):
        relative = path.relative_to(repo)
        if ignored(relative) or not path.exists():
            continue
        if path.is_symlink() or not path.resolve().is_relative_to(root):
            raise ValueError(f"Linked or external source file is unsupported: {path}")
        files[relative.as_posix()] = (path, (version + "\n").encode() if relative.as_posix() == "VERSION" else path.read_bytes())
    if "VERSION" not in files:
        raise ValueError("VERSION is missing from the release source")
    return files


def project_versions(repo: Path) -> dict[str, str]:
    versions = {}
    for relative, name in PACKAGE_PROJECTS:
        path = repo / relative / "pyproject.toml"
        match = PROJECT_VERSION.search(path.read_text(encoding="utf-8"))
        if not match:
            raise ValueError(f"Package version not found: {path}")
        versions[name] = normalize_version(match.group(1))
    return versions


def _copy_ignore(_directory: str, names: list[str]) -> set[str]:
    skipped = {name for name in names if ignored(Path(name))}
    directory = Path(_directory)
    if directory.name == "setup":
        skipped.add("runtime")
    if directory.name == "gui" and directory.parent.name == "src":
        skipped.add("resources")
    if directory.name == "src" and directory.parent.name == "frontend":
        skipped.add("vendor")
    skipped.add(".build-inputs")
    return skipped


def wheel_metadata(data: bytes) -> dict[str, str]:
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        if archive.testzip() is not None:
            raise ValueError("Wheel CRC validation failed")
        metadata = [name for name in archive.namelist() if name.endswith(".dist-info/METADATA")]
        if len(metadata) != 1:
            raise ValueError("Wheel must contain exactly one METADATA file")
        text = archive.read(metadata[0]).decode("utf-8")
    values = {}
    for key in ("Name", "Version"):
        match = re.search(rf"(?m)^{key}:\s*(.+)$", text)
        if not match:
            raise ValueError(f"Wheel metadata is missing {key}")
        values[key.casefold()] = match.group(1).strip()
    return values


def build_wheels(repo: Path, version: str) -> dict[str, bytes]:
    with tempfile.TemporaryDirectory(prefix="my-py-tools-release-") as directory:
        temporary = Path(directory)
        source = temporary / "source"
        wheels = temporary / "wheels"
        shutil.copytree(repo, source, ignore=_copy_ignore)
        (source / "VERSION").write_text(version + "\n", encoding="utf-8")
        wheels.mkdir()
        for relative, _name in PACKAGE_PROJECTS:
            result = subprocess.run(
                [sys.executable, "-m", "pip", "wheel", "--no-deps", "--no-build-isolation", "--wheel-dir", str(wheels), str(source / relative)],
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=180,
                check=False,
            )
            if result.returncode:
                detail = (result.stderr or result.stdout).strip()
                raise ValueError(f"Wheel build failed for {relative}: {detail}")
        built = {path.name: path.read_bytes() for path in sorted(wheels.glob("*.whl"))}
    expected = project_versions(repo)
    seen = {}
    for name, data in built.items():
        metadata = wheel_metadata(data)
        seen[metadata["name"]] = metadata["version"]
    if seen != expected:
        raise ValueError(f"Built wheel metadata does not match package projects: {seen!r} != {expected!r}")
    return built


def source_archive(files: dict[str, tuple[Path, bytes]], tag: str) -> bytes:
    prefix = f"my-py-tools-{tag}/"
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name, (_path, data) in sorted(files.items()):
            info = zipfile.ZipInfo(prefix + name, (1980, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, data, compresslevel=9)
    data = stream.getvalue()
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        if archive.testzip() is not None or len(archive.namelist()) != len(files):
            raise ValueError("Source archive validation failed")
    return data


def check_output(output: Path, tag: str) -> None:
    if not output.exists():
        return
    if output.is_symlink() or not output.is_dir():
        raise ValueError(f"Output must be a regular directory: {output}")
    actual = {path.name for path in output.iterdir()}
    if not actual:
        return
    marker = output / MANIFEST
    if not marker.is_file() or marker.is_symlink():
        raise ValueError(f"Output contains unmanaged files: {output}")
    manifest = json.loads(marker.read_text(encoding="utf-8"))
    if manifest.get("producer") != PRODUCER or manifest.get("tag") != tag:
        raise ValueError(f"Output belongs to another release: {output}")
    assets = manifest.get("assets")
    if not isinstance(assets, list):
        raise ValueError(f"Invalid output manifest: {marker}")
    expected = {MANIFEST}
    for asset in assets:
        if not isinstance(asset, dict) or not isinstance(asset.get("name"), str) or not isinstance(asset.get("sha256"), str):
            raise ValueError(f"Invalid output manifest: {marker}")
        path = output / asset["name"]
        if Path(asset["name"]).name != asset["name"]:
            raise ValueError("Invalid asset name in output manifest")
        expected.add(asset["name"])
        if path.exists() and (path.is_symlink() or digest(path.read_bytes()) != asset["sha256"]):
            raise ValueError(f"Release asset was changed independently: {path}")
    if actual != expected:
        raise ValueError(f"Output contains missing or unmanaged files: {output}")


def prepare(repo: Path, version: str | None, output_root: Path, dry_run: bool = False) -> dict[str, object]:
    repo = repo.resolve()
    current = normalize_version((repo / "VERSION").read_text(encoding="utf-8"))
    selected = normalize_version(version) if version else current
    tag = "v" + selected
    output_root = output_root.expanduser().resolve()
    output = output_root / tag
    check_output(output, tag)
    files = source_snapshot(repo, selected)
    wheels = build_wheels(repo, selected)
    source_name = f"my-py-tools-{tag}.zip"
    assets = {source_name: source_archive(files, tag), **wheels}
    packages = project_versions(repo)
    manifest = {
        "producer": PRODUCER,
        "tag": tag,
        "repository_version": selected,
        "source_files": len(files),
        "packages": packages,
        "assets": [
            {"name": name, "size": len(data), "sha256": digest(data), "type": "source" if name == source_name else "wheel"}
            for name, data in sorted(assets.items())
        ],
    }
    result = {"tag": tag, "version": selected, "output": str(output), "assets": len(assets), "packages": packages, "dry_run": dry_run}
    if dry_run:
        return result
    output_root.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(dir=output_root, prefix=".prepare-release-"))
    fresh = staging / "new"
    previous = staging / "previous"
    fresh.mkdir()
    original_version = (repo / "VERSION").read_bytes()
    moved_previous = False
    wrote_version = False
    try:
        for name, data in assets.items():
            (fresh / name).write_bytes(data)
        (fresh / MANIFEST).write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        for name, (path, _data) in source_snapshot(repo, current).items():
            if name != "VERSION" and path.read_bytes() != files[name][1]:
                raise ValueError(f"Source changed during packaging: {path}")
        if selected != current:
            atomic_write(repo / "VERSION", (selected + "\n").encode())
            wrote_version = True
        check_output(output, tag)
        if output.exists():
            output.rename(previous)
            moved_previous = True
        fresh.rename(output)
    except Exception:
        if moved_previous and not output.exists():
            previous.rename(output)
        if wrote_version:
            atomic_write(repo / "VERSION", original_version)
        raise
    finally:
        shutil.rmtree(staging, ignore_errors=True)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", help="Repository version, e.g. 0.3.0; package versions remain independent")
    parser.add_argument("--repo", type=Path, help="Repository root; defaults to this script's repository")
    parser.add_argument("--output-dir", type=Path, help="Output root; default: <repo>/dist")
    parser.add_argument("--dry-run", action="store_true", help="Build and validate in temporary storage without writing")
    args = parser.parse_args()
    repo = (args.repo or Path(__file__).resolve().parents[2]).expanduser().resolve()
    try:
        result = prepare(repo, args.version, args.output_dir or repo / "dist", args.dry_run)
    except (OSError, ValueError, json.JSONDecodeError, zipfile.BadZipFile) as error:
        print(f"FAIL {error}", file=sys.stderr)
        return 1
    print(f"{'PREVIEW' if args.dry_run else 'READY'} {result['tag']}; assets={result['assets']}; packages={result['packages']}")
    print(f"OUTPUT {result['output']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
