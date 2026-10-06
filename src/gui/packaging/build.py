"""Build a portable Windows single EXE or macOS app/ZIP on its native OS."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import shutil
import stat
import subprocess
import sys
import tempfile
import zipfile

from gui.catalog import TOOLS
from shared.version import repository_version


ROOT = Path(__file__).resolve().parents[3]
SOURCE = ROOT / "src"


def run(command: list[str], cwd: Path = ROOT, env: dict | None = None) -> None:
    subprocess.run(command, cwd=cwd, env=env, check=True)


def prepare_resources() -> None:
    from gui.packaging.icons import prepare_icons

    resources = SOURCE / "gui/resources"
    pin = json.loads((ROOT / "workbench-ui.json").read_text(encoding="utf-8"))
    provenance = json.loads((resources / "workbench-ui.json").read_text(encoding="utf-8"))
    if provenance.get("commit") != pin["revision"] or provenance.get("dirty") is not False:
        raise ValueError("Frontend assets do not match the pinned Workbench UI; rebuild the frontend")
    resources.mkdir(parents=True, exist_ok=True)
    prepare_icons(resources / "icons")
    (resources / "catalog.json").write_text(
        json.dumps([tool.payload() for tool in TOOLS], ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    # Cache the default encoding so packaged token counting also works offline.
    os.environ["TIKTOKEN_CACHE_DIR"] = str(resources / "tiktoken")
    import tiktoken

    tiktoken.get_encoding("o200k_base")
    tiktoken.get_encoding("cl100k_base")


def archive_application(app: Path, target: Path) -> None:
    if sys.platform == "darwin":
        run(["ditto", "-c", "-k", "--sequesterRsrc", "--keepParent", str(app), str(target)])
        return
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for file in sorted(app.rglob("*")):
            if file.is_file():
                archive.write(file, Path(app.name) / file.relative_to(app))


def place_macos_runner(app: Path) -> None:
    if sys.platform != "darwin":
        return
    destination = app / "Contents/MacOS/launch-worker"
    if destination.is_file():
        return
    candidates = [path for path in app.rglob("launch-worker") if path.is_file()]
    if len(candidates) != 1:
        raise RuntimeError("PyInstaller did not produce exactly one macOS CLI runner")
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(candidates[0], destination)
    destination.chmod(destination.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-frontend", action="store_true", help="Reuse an existing React build")
    parser.add_argument("--workbench-ui", type=Path, help="Workbench UI checkout used to build frontend assets")
    parser.add_argument("--webview2-runtime", type=Path, help="Extracted Microsoft Fixed Version WebView2 runtime (required on Windows)")
    parser.add_argument("--output-root", type=Path, help="Desktop output root; existing version folders are never overwritten")
    args = parser.parse_args(argv)
    if sys.platform not in {"win32", "darwin"}:
        parser.error("Build Windows on Windows or macOS on macOS")
    from gui.packaging.webview2 import validate_runtime

    runtime = None
    if sys.platform == "win32":
        if args.webview2_runtime is None:
            parser.error("Windows portable builds require --webview2-runtime; no dependency is installed on the user's computer")
        try:
            runtime = validate_runtime(args.webview2_runtime)
        except (OSError, ValueError) as error:
            parser.error(str(error))
    elif args.webview2_runtime is not None:
        parser.error("WebView2 is only used on Windows")
    version = repository_version(ROOT)
    system = "windows" if sys.platform == "win32" else "macos"
    architecture = {"amd64": "x64", "x86_64": "x64", "aarch64": "arm64"}.get(platform.machine().lower(), platform.machine().lower())
    label = f"my-py-tools-{version}-{system}-{architecture}"
    output_root = (args.output_root or ROOT / "dist/desktop").expanduser().resolve()
    destination = output_root / label
    if destination.exists():
        parser.error(f"Output already exists: {destination}; choose a new version or move the previous build")
    npm = shutil.which("npm")
    if not args.skip_frontend:
        if not npm:
            parser.error("Node.js/npm is required to build React")
        if args.workbench_ui is None:
            parser.error("Provide --workbench-ui for shared interface assets, or reuse a verified build with --skip-frontend")
        node = shutil.which("node")
        if not node:
            parser.error("Node.js is required to prepare Workbench UI assets")
        run([node, "sync-workbench.mjs", "--source", str(args.workbench_ui.resolve()), "--python", sys.executable], SOURCE / "gui/frontend")
        run([npm, "ci"], SOURCE / "gui/frontend")
        run([npm, "run", "build"], SOURCE / "gui/frontend")
    resources = SOURCE / "gui/resources"
    provenance = resources / "workbench-ui.json"
    if not provenance.is_file() or not (resources / "web/index.html").is_file():
        parser.error("Build the frontend with Workbench UI assets first")
    prepare_resources()
    destination.parent.mkdir(parents=True, exist_ok=True)
    # Keep PyInstaller's replace/cleanup operations inside this unique temporary directory.
    with tempfile.TemporaryDirectory(prefix="gui-build-", dir=output_root) as temporary:
        staging = Path(temporary)
        run([
            sys.executable, "-m", "PyInstaller", "--noconfirm",
            "--distpath", str(staging / "dist"), "--workpath", str(staging / "work"),
            str(SOURCE / "gui/packaging/desktop.spec"),
        ])
        app = staging / "dist" / ("MyPyTools" if sys.platform == "win32" else "launch-gui.app")
        if sys.platform == "win32":
            internal = app / "_internal"
            if not internal.is_dir():
                raise RuntimeError("PyInstaller did not produce the internal runtime folder")
            shutil.move(str(app / "launch-worker.exe"), str(internal / "launch-worker.exe"))
        if runtime is not None:
            shutil.copytree(runtime, app / "WebView2")
        if system == "windows":
            from gui.packaging.portable_payload import inspect_executable

            payload = staging / "gui_payload.zip"
            archive_application(app, payload)
            with zipfile.ZipFile(payload) as zipped, payload.open("rb") as stream:
                payload_info = {
                    "size": payload.stat().st_size, "sha256": hashlib.file_digest(stream, "sha256").hexdigest(),
                    "files": len(zipped.infolist()), "unpacked_size": sum(item.file_size for item in zipped.infolist()),
                }
            (staging / "payload-info.json").write_text(json.dumps(payload_info), encoding="utf-8")
            run([
                sys.executable, "-m", "PyInstaller", "--noconfirm",
                "--distpath", str(staging / "portable"), "--workpath", str(staging / "portable-work"),
                str(SOURCE / "gui/packaging/portable.spec"),
            ], env=dict(os.environ, MY_PY_TOOLS_GUI_PAYLOAD=str(staging)))
            executable = staging / "portable/launch-gui.exe"
            inspect_executable(executable)
            destination.mkdir()
            archive = destination / f"launch-gui-{version}-{system}-{architecture}.exe"
            shutil.move(str(executable), str(archive))
        else:
            place_macos_runner(app)
            destination.mkdir()
            app = Path(shutil.move(str(app), str(destination / app.name)))
            archive = destination / f"{label}.zip"
            archive_application(app, archive)
    dependencies = {name: importlib.metadata.version(name) for name in (
        "pywebview", "pyinstaller", "pypdf", "pdfplumber", "openpyxl", "python-docx", "python-pptx", "tiktoken",
    )}
    manifest = {
        "version": version, "os": system, "architecture": architecture,
        "python": platform.python_version(), "dependencies": dependencies,
        "tools": [tool.module for tool in TOOLS],
        "asset": archive.name, "size": archive.stat().st_size,
        "sha256": "",
        "signed": False,
        "format": "onefile-exe" if system == "windows" else "app-zip",
        "entrypoints": {"gui": archive.name if system == "windows" else "launch-gui.app/Contents/MacOS/launch-gui"},
        "interface": json.loads(provenance.read_text(encoding="utf-8")),
        "browser_runtime": {"mode": "bundled-fixed", "folder": "WebView2"} if runtime else {"mode": "system-webkit"},
    }
    with archive.open("rb") as stream:
        manifest["sha256"] = hashlib.file_digest(stream, "sha256").hexdigest()
    if system == "windows":
        manifest["payload"] = payload_info
    (destination / "desktop-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"READY {archive}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
