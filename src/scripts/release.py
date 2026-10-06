#!/usr/bin/env python3
"""Validate, prepare, and explicitly publish a my-py-tools GitHub Release."""

from __future__ import annotations

import argparse
import ast
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

if __package__:
    from scripts import prepare_release
else:
    import prepare_release


REPO = Path(__file__).resolve().parents[2]


def run(*args: str, capture: bool = False) -> str:
    result = subprocess.run(args, cwd=REPO, text=True, encoding="utf-8", capture_output=capture, check=False)
    if result.returncode:
        detail = (result.stderr if capture else "").strip()
        raise ValueError(f"Command failed ({result.returncode}): {' '.join(args)}{': ' + detail if detail else ''}")
    return result.stdout.strip() if capture else ""


def validate_source() -> None:
    run(sys.executable, "-m", "unittest", "discover", "-s", "tests", "-t", ".", "-v")
    roots = ("src", "packages", "tests")
    errors = []
    for root in roots:
        for directory, names, files in os.walk(REPO / root):
            names[:] = [name for name in names if name not in {"__pycache__", "node_modules", "resources", "vendor"} and not name.startswith(".")]
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


def validate_desktop_content(archive: Path, metadata: dict) -> None:
    system = metadata.get("os")
    if system not in {"windows", "macos"} or metadata.get("architecture") not in {"x64", "arm64"}:
        raise ValueError("Unsupported desktop platform")
    if metadata.get("interface", {}).get("name") != "workbench-ui":
        raise ValueError("Desktop package must record its Workbench UI input")
    if metadata["interface"].get("dirty"):
        raise ValueError("Release packaging requires committed Workbench UI assets, not an uncommitted working tree")
    if system == "windows":
        from gui.packaging.portable_payload import inspect_executable

        expected = f"launch-gui-{metadata.get('version')}-windows-x64.exe"
        if (metadata.get("architecture") != "x64" or archive.name != expected
                or metadata.get("format") != "onefile-exe"
                or metadata.get("entrypoints") != {"gui": expected}):
            raise ValueError("Windows desktop requires a single portable GUI EXE entry point")
        if metadata.get("browser_runtime", {}).get("mode") != "bundled-fixed":
            raise ValueError("Windows desktop EXE must include Fixed WebView2")
        if inspect_executable(archive) != metadata.get("payload"):
            raise ValueError("Desktop manifest does not match its embedded payload")
        return
    if archive.suffix != ".zip":
        raise ValueError("macOS desktop requires an application ZIP")
    with zipfile.ZipFile(archive) as zipped:
        names = set(zipped.namelist())
        if zipped.testzip() is not None or any(name.startswith(("/", "\\")) or ".." in name.replace("\\", "/").split("/") for name in names):
            raise ValueError("Desktop ZIP has invalid CRC or unsafe paths")
        if not any(name.endswith("/Contents/MacOS/launch-gui") for name in names):
            raise ValueError("macOS desktop ZIP is missing its application executable")


def desktop_assets(directory: Path, version: str) -> tuple[Path, Path, dict]:
    directory = directory.expanduser().resolve()
    marker = directory / "desktop-manifest.json"
    metadata = json.loads(marker.read_text(encoding="utf-8"))
    name = metadata.get("asset")
    if not isinstance(name, str) or Path(name).name != name or not name.endswith((".zip", ".exe")):
        raise ValueError("Invalid desktop asset name")
    archive = directory / name
    import hashlib

    with archive.open("rb") as stream:
        checksum = hashlib.file_digest(stream, "sha256").hexdigest()
    if metadata.get("version") != version or metadata.get("sha256") != checksum or metadata.get("size") != archive.stat().st_size:
        raise ValueError("Desktop version, size or SHA-256 mismatch")
    validate_desktop_content(archive, metadata)
    return archive, marker, metadata


def attach_desktop(tag: str, output_root: Path, directory: Path) -> None:
    version = prepare_release.normalize_version(tag)
    archive, marker, metadata = desktop_assets(directory, version)
    folder = output_root.expanduser().resolve() / ("v" + version)
    prepare_release.check_output(folder, "v" + version)
    manifest_path = folder / prepare_release.MANIFEST
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    marker_name = f"desktop-manifest-{metadata['os']}-{metadata['architecture']}.json"
    candidates = ((archive, archive.name, "desktop"), (marker, marker_name, "desktop-manifest"))
    if any((folder / name).exists() for _source, name, _kind in candidates):
        raise ValueError("Desktop assets already exist, do not replace independently prepared files")
    additions = []
    copied = []
    try:
        for source, name, kind in candidates:
            target = folder / name
            with source.open("rb") as input_stream, target.open("xb") as output_stream:
                copied.append(target)
                shutil.copyfileobj(input_stream, output_stream)
            import hashlib

            with target.open("rb") as stream:
                checksum = hashlib.file_digest(stream, "sha256").hexdigest()
            additions.append({"name": name, "size": target.stat().st_size, "sha256": checksum, "type": kind})
        manifest["assets"].extend(additions)
        prepare_release.atomic_write(manifest_path, (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
    except Exception:
        for path in copied:
            path.unlink(missing_ok=True)
        raise


def cli_assets(directory: Path, version: str) -> tuple[Path, Path, dict]:
    directory = directory.expanduser().resolve()
    markers = list(directory.glob("cli-manifest-*.json"))
    if len(markers) != 1:
        raise ValueError("Exactly one CLI manifest is required")
    marker = markers[0]
    metadata = json.loads(marker.read_text(encoding="utf-8"))
    if not isinstance(metadata, dict) or metadata.get("product") != "cli":
        raise ValueError("Invalid CLI manifest")
    system, architecture = metadata.get("os"), metadata.get("architecture")
    if system not in {"windows", "macos"} or architecture not in {"x64", "arm64"}:
        raise ValueError("Unsupported CLI platform")
    if marker.name != f"cli-manifest-{system}-{architecture}.json":
        raise ValueError("CLI manifest filename does not match its platform")
    name = metadata.get("asset")
    if not isinstance(name, str) or name != f"my-py-tools-{version}-cli-{system}-{architecture}.zip":
        raise ValueError("Invalid CLI asset name or version")
    archive = directory / name
    import hashlib

    with archive.open("rb") as stream:
        checksum = hashlib.file_digest(stream, "sha256").hexdigest()
    if metadata.get("version") != version or metadata.get("sha256") != checksum or metadata.get("size") != archive.stat().st_size:
        raise ValueError("CLI version, size or SHA-256 mismatch")
    executable = "MyPyToolsCLI/launch-cli" + (".exe" if system == "windows" else "")
    with zipfile.ZipFile(archive) as zipped:
        names = set(zipped.namelist())
        if zipped.testzip() is not None or any(name.startswith(("/", "\\")) or ".." in name.replace("\\", "/").split("/") for name in names):
            raise ValueError("CLI ZIP has invalid CRC or unsafe paths")
        if executable not in names or "MyPyToolsCLI/_internal/gui/resources/catalog.json" not in names:
            raise ValueError("CLI ZIP is missing its executable or tool catalog")
        if "MyPyToolsCLI/_internal/gui/resources/web/index.html" not in names or metadata.get("modes") != ["terminal", "browser"]:
            raise ValueError("CLI ZIP must support terminal and shared browser modes")
        if metadata.get("interface", {}).get("name") != "workbench-ui" or metadata["interface"].get("dirty"):
            raise ValueError("CLI release requires committed Workbench UI assets")
        entrypoints = {"cli": executable}
        if system == "windows":
            entrypoints["cmd"] = "MyPyToolsCLI/launch-cli.cmd"
            entrypoints["web_cmd"] = "MyPyToolsCLI/launch-web.cmd"
            entrypoints["ps1"] = "MyPyToolsCLI/launch-cli.ps1"
            entrypoints["web_ps1"] = "MyPyToolsCLI/launch-web.ps1"
            if not set(entrypoints.values()).issubset(names):
                raise ValueError("Windows CLI ZIP must include separate terminal and web CMD/PS1 launchers")
        if metadata.get("entrypoints") != entrypoints:
            raise ValueError("CLI entry point does not match its executable")
        if any("WebView2" in name.split("/") or name.endswith("/launch-gui.exe") for name in names):
            raise ValueError("CLI ZIP must not contain a GUI executable or WebView2")
        if system == "macos" and not ((zipped.getinfo(executable).external_attr >> 16) & 0o111):
            raise ValueError("macOS CLI executable must preserve executable permissions")
    return archive, marker, metadata


def prepare_cli(args) -> tuple[Path, Path, dict]:
    version = prepare_release.normalize_version((REPO / "VERSION").read_text(encoding="utf-8"))
    if prepare_release.normalize_version(args.tag) != version:
        raise ValueError("VERSION must match the CLI release tag")
    if args.cli_assets:
        return cli_assets(args.cli_assets, version)
    import platform
    from distribution.build_cli import main as build_cli

    system = "windows" if sys.platform == "win32" else "macos"
    architecture = {"amd64": "x64", "x86_64": "x64", "aarch64": "arm64"}.get(platform.machine().lower(), platform.machine().lower())
    output = (args.asset_root or REPO / "dist/cli").resolve()
    if not args.workbench_ui:
        raise ValueError("Provide --workbench-ui or --cli-assets")
    if build_cli(["--output-root", str(output), "--workbench-ui", str(args.workbench_ui)]):
        raise ValueError("CLI build failed")
    return cli_assets(output / f"my-py-tools-{version}-cli-{system}-{architecture}", version)


def prepare_desktop(args) -> tuple[Path, Path, dict]:
    version = prepare_release.normalize_version((REPO / "VERSION").read_text(encoding="utf-8"))
    if prepare_release.normalize_version(args.tag) != version:
        raise ValueError("VERSION must match the desktop release tag")
    if args.desktop_assets:
        return desktop_assets(args.desktop_assets, version)
    if not args.workbench_ui:
        raise ValueError("Provide --workbench-ui or --desktop-assets")
    import platform
    from gui.packaging.build import main as build_desktop

    system = "windows" if sys.platform == "win32" else "macos"
    architecture = {"amd64": "x64", "x86_64": "x64", "aarch64": "arm64"}.get(platform.machine().lower(), platform.machine().lower())
    output = (args.asset_root or REPO / "dist/desktop").resolve()
    command = ["--workbench-ui", str(args.workbench_ui), "--output-root", str(output)]
    if args.webview2_runtime:
        command.extend(["--webview2-runtime", str(args.webview2_runtime)])
    if build_desktop(command):
        raise ValueError("Desktop build failed")
    return desktop_assets(output / f"my-py-tools-{version}-{system}-{architecture}", version)


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
        if not isinstance(item.get("name"), str) or Path(item["name"]).name != item["name"]:
            raise ValueError("Invalid release asset name")
        path = folder / item["name"]
        data = path.read_bytes()
        if len(data) != item.get("size") or prepare_release.digest(data) != item.get("sha256"):
            raise ValueError(f"Release asset changed: {path.name}")
        if path.name == source_name:
            expected_files = {f"my-py-tools-{tag}/{name}": content for name, (_path, content) in source_files.items()}
            with zipfile.ZipFile(path) as archive:
                if (archive.testzip() is not None or len(archive.namelist()) != len(expected_files)
                        or set(archive.namelist()) != set(expected_files)
                        or any(((item.external_attr >> 16) & 0o170000) not in {0, 0o100000} for item in archive.infolist())
                        or any(archive.read(name) != content for name, content in expected_files.items())):
                    raise ValueError("Source archive does not match the current repository")
        elif path.suffix == ".whl":
            metadata = prepare_release.wheel_metadata(data)
            expected = manifest["packages"].get(metadata["name"])
            if metadata["version"] != expected:
                raise ValueError(f"Wheel metadata does not match pyproject.toml: {path.name}")
        elif item.get("type") == "desktop":
            # Content validation follows the platform manifest, not the extension alone.
            if path.suffix not in {".zip", ".exe"}:
                raise ValueError("Invalid desktop release asset")
        elif item.get("type") == "desktop-manifest":
            desktop = json.loads(data)
            matching = [entry for entry in assets if entry.get("type") == "desktop" and entry.get("name") == desktop.get("asset")]
            if len(matching) != 1 or desktop.get("version") != version or desktop.get("sha256") != matching[0].get("sha256") or desktop.get("size") != matching[0].get("size"):
                raise ValueError("Desktop manifest does not match its asset or release version")
            validate_desktop_content(folder / desktop["asset"], desktop)
        else:
            raise ValueError(f"Unsupported release asset: {path.name}")
        paths.append(path)
    if manifest.get("source_files") != len(source_files) or source_name not in expected_names:
        raise ValueError("Release source manifest does not match the repository")
    desktop_names = {item['name'] for item in assets if item.get('type') == 'desktop'}
    manifest_desktops = {json.loads((folder / item['name']).read_text(encoding='utf-8')).get('asset') for item in assets if item.get('type') == 'desktop-manifest'}
    if desktop_names != manifest_desktops:
        raise ValueError("Every desktop asset requires a matching platform manifest")
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
    prepare.add_argument("--desktop", action="store_true", help="Include a native portable GUI in this release")
    prepare.add_argument("--desktop-assets", type=Path, help="Reuse an already verified desktop build directory")
    prepare.add_argument("--workbench-ui", type=Path, help="Committed Workbench UI checkout for a fresh desktop build")
    prepare.add_argument("--webview2-runtime", type=Path, help="Extracted Fixed Version WebView2, required on Windows")
    publish_parser = subparsers.add_parser("publish", help="Push a reviewed commit and create a GitHub Release")
    publish_parser.add_argument("tag", help="Prepared release tag, e.g. v0.2.0")
    publish_parser.add_argument("--asset-root", type=Path, help="Prepared asset root; default: <repo>/dist")
    desktop_parser = subparsers.add_parser("desktop", help="Build native portable assets for Release CI, or verify an existing test build")
    desktop_parser.add_argument("tag")
    desktop_parser.add_argument("--asset-root", type=Path)
    desktop_parser.add_argument("--desktop-assets", type=Path)
    desktop_parser.add_argument("--workbench-ui", type=Path)
    desktop_parser.add_argument("--webview2-runtime", type=Path)
    cli_parser = subparsers.add_parser("cli", help="Build independent native CLI assets for Release CI")
    cli_parser.add_argument("tag")
    cli_parser.add_argument("--asset-root", type=Path)
    cli_parser.add_argument("--cli-assets", type=Path, help="Verify an existing native CLI test build")
    cli_parser.add_argument("--workbench-ui", type=Path)
    args = parser.parse_args()
    try:
        if args.action == "publish":
            publish(args.tag, args.asset_root)
        elif args.action == "cli":
            validate_source()
            archive, marker, _metadata = prepare_cli(args)
            print(f"READY {archive}\nMANIFEST {marker}")
        elif args.action == "desktop":
            validate_source()
            archive, marker, metadata = prepare_desktop(args)
            target = marker.with_name(f"desktop-manifest-{metadata['os']}-{metadata['architecture']}.json")
            if target.exists():
                if target.read_bytes() != marker.read_bytes():
                    raise ValueError("Platform manifest already exists with different contents")
            else:
                with target.open("xb") as stream:
                    stream.write(marker.read_bytes())
            print(f"READY {archive}\nMANIFEST {target}")
        else:
            if args.desktop_assets and not args.desktop:
                raise ValueError("Use --desktop with --desktop-assets")
            if args.desktop and args.dry_run and not args.desktop_assets:
                raise ValueError("Desktop dry-run requires --desktop-assets; it verifies an existing build without creating output")
            if args.desktop and not args.desktop_assets and not args.workbench_ui:
                raise ValueError("A fresh desktop build requires --workbench-ui")
            validate_source()
            output_root = args.asset_root or REPO / "dist"
            selected_version = args.version or (REPO / "VERSION").read_text(encoding="utf-8").strip()
            if args.desktop_assets:
                desktop_assets(args.desktop_assets, prepare_release.normalize_version(selected_version))
            result = prepare_release.prepare(REPO, args.version, output_root, args.dry_run)
            if not args.dry_run:
                if args.desktop:
                    directory = args.desktop_assets
                    if directory is None:
                        from gui.packaging.build import main as build_desktop
                        import platform

                        system = "windows" if sys.platform == "win32" else "macos"
                        architecture = {"amd64": "x64", "x86_64": "x64", "aarch64": "arm64"}.get(platform.machine().lower(), platform.machine().lower())
                        desktop_root = output_root.resolve() / "desktop"
                        command = ["--workbench-ui", str(args.workbench_ui), "--output-root", str(desktop_root)]
                        if args.webview2_runtime:
                            command.extend(["--webview2-runtime", str(args.webview2_runtime)])
                        if build_desktop(command):
                            raise ValueError("Desktop build failed")
                        directory = desktop_root / f"my-py-tools-{result['version']}-{system}-{architecture}"
                    attach_desktop(str(result["tag"]), output_root, directory)
                verify(str(result["tag"]), output_root)
            count = result['assets'] + (2 if args.desktop else 0)
            print(f"{'PREVIEW' if args.dry_run else 'READY'} {result['tag']}: {count} assets")
            if not args.dry_run:
                suffix = f" --asset-root {output_root}" if args.asset_root else ""
                print(f"Review changes, commit them, then run: python launch-cli.py scripts.release publish {result['tag']}{suffix}")
    except (OSError, ValueError, json.JSONDecodeError, zipfile.BadZipFile) as error:
        print(f"FAIL {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
