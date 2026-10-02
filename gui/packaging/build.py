"""Build a portable Windows folder/ZIP or macOS app/ZIP on its native OS."""

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


ROOT = Path(__file__).resolve().parents[2]


def run(command: list[str], cwd: Path = ROOT) -> None:
    subprocess.run(command, cwd=cwd, check=True)


def prepare_resources() -> None:
    resources = ROOT / "gui/resources"
    resources.mkdir(parents=True, exist_ok=True)
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
    destination = app / "Contents/MacOS/MyPyToolsRunner"
    if destination.is_file():
        return
    candidates = [path for path in app.rglob("MyPyToolsRunner") if path.is_file()]
    if len(candidates) != 1:
        raise RuntimeError("PyInstaller did not produce exactly one macOS CLI runner")
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(candidates[0], destination)
    destination.chmod(destination.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-frontend", action="store_true", help="Reuse an existing React build")
    args = parser.parse_args(argv)
    if sys.platform not in {"win32", "darwin"}:
        parser.error("Build Windows on Windows or macOS on macOS")
    version = repository_version(ROOT)
    system = "windows" if sys.platform == "win32" else "macos"
    architecture = {"amd64": "x64", "x86_64": "x64", "aarch64": "arm64"}.get(platform.machine().lower(), platform.machine().lower())
    label = f"my-py-tools-{version}-{system}-{architecture}"
    destination = ROOT / "dist/desktop" / label
    if destination.exists():
        parser.error(f"Output already exists: {destination}; choose a new version or move the previous build")
    npm = shutil.which("npm")
    if not args.skip_frontend:
        if not npm:
            parser.error("Node.js/npm is required to build React")
        run([npm, "ci"], ROOT / "gui/frontend")
        run([npm, "run", "build"], ROOT / "gui/frontend")
    prepare_resources()
    destination.parent.mkdir(parents=True, exist_ok=True)
    # Keep PyInstaller's replace/cleanup operations inside this unique temporary directory.
    with tempfile.TemporaryDirectory(prefix="gui-build-", dir=ROOT / "dist/desktop") as temporary:
        staging = Path(temporary)
        run([
            sys.executable, "-m", "PyInstaller", "--noconfirm",
            "--distpath", str(staging / "dist"), "--workpath", str(staging / "work"),
            str(ROOT / "gui/packaging/desktop.spec"),
        ])
        app = staging / "dist" / ("MyPyTools" if sys.platform == "win32" else "My Py Tools.app")
        destination.mkdir()
        shutil.move(str(app), str(destination / app.name))
    app = destination / app.name
    place_macos_runner(app)
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
    }
    with archive.open("rb") as stream:
        manifest["sha256"] = hashlib.file_digest(stream, "sha256").hexdigest()
    (destination / "desktop-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"READY {archive}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
