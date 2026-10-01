#!/usr/bin/env python3
"""Validate, prepare, and explicitly publish a my-py-tools GitHub Release."""

from __future__ import annotations

import argparse
import ast
import json
import os
from pathlib import Path
import subprocess
import sys
import zipfile

try:
    from scripts import prepare_release
except ModuleNotFoundError:
    import prepare_release


REPO = Path(__file__).resolve().parents[1]


def run(*args: str, capture: bool = False) -> str:
    result = subprocess.run(args, cwd=REPO, text=True, encoding="utf-8", capture_output=capture, check=False)
    if result.returncode:
        detail = (result.stderr if capture else "").strip()
        raise ValueError(f"Command failed ({result.returncode}): {' '.join(args)}{': ' + detail if detail else ''}")
    return result.stdout.strip() if capture else ""


def validate_source() -> None:
    run(sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v")
    roots = ("angular", "documents", "gui", "maintenance", "markdown", "packages", "shared", "src", "text", "validation")
    errors = []
    for root in roots:
        for directory, names, files in os.walk(REPO / root):
            names[:] = [name for name in names if name != "__pycache__" and not name.startswith(".")]
            for name in files:
                if not name.endswith(".py"):
                    continue
                path = Path(directory, name)
                try:
                    ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
                except (OSError, SyntaxError, UnicodeError) as exc:
                    errors.append(f"{path.relative_to(REPO)}: {exc}")
    if errors:
        raise ValueError("Python syntax validation failed: " + "; ".join(errors))


def verify(tag: str, output_root: Path | None = None) -> list[Path]:
    version = prepare_release.normalize_version(tag)
    tag = "v" + version
    if prepare_release.normalize_version((REPO / "VERSION").read_text(encoding="utf-8")) != version:
        raise ValueError("VERSION does not match the release tag")
    folder = (output_root or REPO / "dist").expanduser().resolve() / tag
    manifest = json.loads((folder / prepare_release.MANIFEST).read_text(encoding="utf-8"))
    if manifest.get("producer") != prepare_release.PRODUCER or manifest.get("tag") != tag or manifest.get("repository_version") != version:
        raise ValueError("Release manifest has the wrong producer or version")
    if manifest.get("packages") != prepare_release.project_versions(REPO):
        raise ValueError("Release package versions do not match pyproject.toml")
    assets = manifest.get("assets")
    if not isinstance(assets, list) or not assets:
        raise ValueError("Release manifest has no assets")
    expected_names = {item.get("name") for item in assets if isinstance(item, dict)}
    if len(expected_names) != len(assets) or {path.name for path in folder.iterdir()} != expected_names | {prepare_release.MANIFEST}:
        raise ValueError("Release folder contains missing or unexpected files")
    source_files = prepare_release.source_snapshot(REPO, version)
    source_name = f"my-py-tools-{tag}.zip"
    paths = []
    for item in assets:
        path = folder / item["name"]
        data = path.read_bytes()
        if len(data) != item.get("size") or prepare_release.digest(data) != item.get("sha256"):
            raise ValueError(f"Release asset changed: {path.name}")
        if path.name == source_name:
            if data != prepare_release.source_archive(source_files, tag):
                raise ValueError("Source archive does not match the current repository")
        elif path.suffix == ".whl":
            metadata = prepare_release.wheel_metadata(data)
            expected = manifest["packages"].get(metadata["name"])
            if metadata["version"] != expected:
                raise ValueError(f"Wheel metadata does not match pyproject.toml: {path.name}")
        else:
            raise ValueError(f"Unsupported release asset: {path.name}")
        paths.append(path)
    if manifest.get("source_files") != len(source_files) or source_name not in expected_names:
        raise ValueError("Release source manifest does not match the repository")
    return sorted(paths)


def publish(tag: str, output_root: Path | None = None) -> None:
    version = prepare_release.normalize_version(tag)
    tag = "v" + version
    if run("git", "status", "--porcelain=v1", "-uall", capture=True):
        raise ValueError("Commit and review all source changes before publishing")
    branch = run("git", "branch", "--show-current", capture=True)
    if not branch:
        raise ValueError("A local branch is required")
    upstream = run("git", "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}", capture=True)
    if upstream != f"origin/{branch}":
        raise ValueError(f"Branch must track origin/{branch}")
    validate_source()
    assets = verify(tag, output_root)
    if run("git", "tag", "--list", tag, capture=True):
        raise ValueError(f"Local tag already exists: {tag}")
    if run("git", "ls-remote", "--tags", "origin", f"refs/tags/{tag}", capture=True):
        raise ValueError(f"Remote tag already exists: {tag}")
    run("gh", "auth", "status", capture=True)
    existing = subprocess.run(["gh", "release", "view", tag, "--json", "tagName"], cwd=REPO, capture_output=True, text=True, encoding="utf-8")
    if existing.returncode == 0:
        raise ValueError(f"GitHub Release already exists: {tag}")
    head = run("git", "rev-parse", "HEAD", capture=True)
    print(f"Ready to push {branch} ({head[:12]}) and publish {tag} with {len(assets)} assets")
    if input("Type the tag to confirm: ").strip() != tag:
        print("Cancelled")
        return
    run("git", "push", "origin", branch)
    remote = run("git", "ls-remote", "origin", f"refs/heads/{branch}", capture=True)
    if not remote or remote.split()[0] != head:
        raise ValueError("Remote branch does not match the reviewed commit")
    run("gh", "release", "create", tag, *(str(path) for path in assets), "--target", head, "--title", tag, "--generate-notes")
    remote_release = json.loads(run("gh", "release", "view", tag, "--json", "tagName,assets", capture=True))
    remote_assets = remote_release.get("assets", [])
    if remote_release.get("tagName") != tag or {item.get("name"): item.get("size") for item in remote_assets} != {path.name: path.stat().st_size for path in assets}:
        raise ValueError("GitHub Release assets do not match the local release")
    print(f"Published {tag}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="action", required=True)
    prepare = subparsers.add_parser("prepare", help="Run tests, build source ZIP and independent wheels")
    prepare.add_argument("--version", help="Repository version; package versions remain independent")
    prepare.add_argument("--dry-run", action="store_true")
    prepare.add_argument("--asset-root", type=Path, help="Asset root; default: <repo>/dist")
    publish_parser = subparsers.add_parser("publish", help="Push a reviewed commit and create a GitHub Release")
    publish_parser.add_argument("tag", help="Prepared release tag, e.g. v0.2.0")
    publish_parser.add_argument("--asset-root", type=Path, help="Prepared asset root; default: <repo>/dist")
    args = parser.parse_args()
    try:
        if args.action == "publish":
            publish(args.tag, args.asset_root)
        else:
            validate_source()
            output_root = args.asset_root or REPO / "dist"
            result = prepare_release.prepare(REPO, args.version, output_root, args.dry_run)
            if not args.dry_run:
                verify(str(result["tag"]), output_root)
            print(f"{'PREVIEW' if args.dry_run else 'READY'} {result['tag']}: {result['assets']} assets")
            if not args.dry_run:
                suffix = f" --asset-root {output_root}" if args.asset_root else ""
                print(f"Review changes, commit them, then run: python scripts/release.py publish {result['tag']}{suffix}")
    except (OSError, ValueError, json.JSONDecodeError, zipfile.BadZipFile) as error:
        print(f"FAIL {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
