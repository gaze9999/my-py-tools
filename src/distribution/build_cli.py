"""Build a self-contained Windows/macOS CLI ZIP on its native architecture."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
from pathlib import Path
import platform
import shutil
import sys
import tempfile

from gui.catalog import TOOLS
from gui.packaging.build import archive_application, prepare_resources, run
from shared.version import repository_version


ROOT = Path(__file__).resolve().parents[2]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, help="Output root; existing builds are never overwritten")
    parser.add_argument("--workbench-ui", type=Path, help="Workbench UI checkout for the shared browser interface")
    parser.add_argument("--skip-frontend", action="store_true", help="Reuse a verified existing shared frontend build")
    args = parser.parse_args(argv)
    if sys.platform not in {"win32", "darwin"}:
        parser.error("Build Windows on Windows or macOS on macOS")
    system = "windows" if sys.platform == "win32" else "macos"
    architecture = {"amd64": "x64", "aarch64": "arm64", "x86_64": "x64"}.get(platform.machine().lower(), platform.machine().lower())
    if architecture not in {"arm64", "x64"}:
        parser.error("Supported architectures: arm64, x64")
    version = repository_version(ROOT)
    label = f"my-py-tools-{version}-cli-{system}-{architecture}"
    output = (args.output_root or ROOT / "dist/cli").expanduser().resolve()
    destination = output / label
    if destination.exists():
        parser.error(f"Output already exists: {destination}")
    frontend = ROOT / "src/gui/frontend"
    if not args.skip_frontend:
        node, npm = shutil.which("node"), shutil.which("npm")
        if not node or not npm or args.workbench_ui is None:
            parser.error("Provide --workbench-ui and Node.js/npm, or reuse an existing build with --skip-frontend")
        run([node, "sync-workbench.mjs", "--source", str(args.workbench_ui.resolve()), "--python", sys.executable], frontend)
        run([npm, "ci"], frontend)
        run([npm, "run", "build"], frontend)
    resources = ROOT / "src/gui/resources"
    provenance = resources / "workbench-ui.json"
    if not provenance.is_file() or not (resources / "web/index.html").is_file():
        parser.error("Build the shared interface with Workbench UI first")
    prepare_resources()
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="cli-build-", dir=output) as temporary:
        staging = Path(temporary)
        run([sys.executable, "-m", "PyInstaller", "--noconfirm", "--distpath", str(staging / "dist"), "--workpath", str(staging / "work"), str(ROOT / "src/distribution/cli.spec")])
        destination.mkdir()
        shutil.move(str(staging / "dist/MyPyToolsCLI"), str(destination / "MyPyToolsCLI"))
    if system == "windows":
        shutil.copy2(ROOT / "src/distribution/launch-cli.cmd", destination / "MyPyToolsCLI/launch-cli.cmd")
        shutil.copy2(ROOT / "src/distribution/launch-web.cmd", destination / "MyPyToolsCLI/launch-web.cmd")
        for name in ("launch-cli.ps1", "launch-web.ps1"):
            shutil.copy2(ROOT / name, destination / "MyPyToolsCLI" / name)
    archive = destination / f"{label}.zip"
    archive_application(destination / "MyPyToolsCLI", archive)
    with archive.open("rb") as stream:
        checksum = hashlib.file_digest(stream, "sha256").hexdigest()
    manifest = {
        "product": "cli", "version": version, "os": system, "architecture": architecture,
        "python": platform.python_version(), "signed": False,
        "dependencies": {name: importlib.metadata.version(name) for name in ("pyinstaller", "pypdf", "pdfplumber", "openpyxl", "python-docx", "python-pptx", "tiktoken")},
        "tools": [tool.module for tool in TOOLS], "source_only_tools": [tool.module for tool in TOOLS if tool.payload()["source_only"]],
        "entrypoints": {"cli": "MyPyToolsCLI/launch-cli" + (".exe" if system == "windows" else "")},
        "modes": ["terminal", "browser"], "interface": json.loads(provenance.read_text(encoding="utf-8")),
        "asset": archive.name, "size": archive.stat().st_size, "sha256": checksum,
    }
    if system == "windows":
        manifest["entrypoints"]["cmd"] = "MyPyToolsCLI/launch-cli.cmd"
        manifest["entrypoints"]["web_cmd"] = "MyPyToolsCLI/launch-web.cmd"
        manifest["entrypoints"]["ps1"] = "MyPyToolsCLI/launch-cli.ps1"
        manifest["entrypoints"]["web_ps1"] = "MyPyToolsCLI/launch-web.ps1"
    (destination / f"cli-manifest-{system}-{architecture}.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"READY {archive}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
