# Build on the target OS. Only the GUI is a public entry point; its worker is internal.
from pathlib import Path
import sys

root = Path(SPECPATH).parents[2]
source = root / "src"
sys.path.insert(0, str(source))
sys.path.insert(0, str(root / "packages/workspace_core"))
from gui.catalog import TOOLS
from shared.version import repository_version
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

version = repository_version(root)
resources = source / "gui/resources"
if not (resources / "catalog.json").is_file() or not (resources / "web/index.html").is_file():
    raise RuntimeError("Run python -m gui.packaging.build first")
data = [
    (str(root / "VERSION"), "."),
    (str(resources / "catalog.json"), "gui/resources"),
    (str(resources / "web/index.html"), "gui/resources/web"),
    (str(resources / "tiktoken"), "tiktoken-cache"),
]
for package in ("webview", "docx", "pptx"):
    data += collect_data_files(package)
hidden = [tool.module for tool in TOOLS] + [
    "gui.tool_runner", "my_py_workspace_core", "pypdf", "pdfplumber",
    "openpyxl", "docx", "pptx", "tiktoken", "tiktoken_ext.openai_public",
]
hidden += collect_submodules("my_py_workspace_core")
analysis = Analysis(
    [str(source / "gui/packaging/desktop_entry.py")],
    pathex=[str(source), str(root / "packages/workspace_core")],
    hookspath=[str(source / "gui/packaging/hooks")],
    binaries=[], datas=data, hiddenimports=hidden,
    excludes=["tkinter", "customtkinter", "tkinterdnd2", "PyQt5", "PyQt6", "PySide2", "PySide6"],
    noarchive=False,
)
pyz = PYZ(analysis.pure)
gui = EXE(
    pyz, analysis.scripts, [], exclude_binaries=True, name="launch-gui",
    console=False, upx=False, icon=str(resources / "icons/app.ico") if sys.platform == "win32" else None,
)
runner = EXE(
    pyz, analysis.scripts, [], exclude_binaries=True, name="launch-worker",
    console=True, upx=False, icon=str(resources / "icons/app.ico") if sys.platform == "win32" else None,
    # Windows worker is relocated beside its DLLs inside _internal after collection.
    contents_directory="." if sys.platform == "win32" else "_internal",
)
collection = COLLECT(gui, runner, analysis.binaries, analysis.datas, strip=False, upx=False, name="MyPyTools")
if sys.platform == "darwin":
    application = BUNDLE(
        collection, name="launch-gui.app", bundle_identifier="io.github.gaze9999.mypytools",
        version=version, icon=str(resources / "icons/app.icns"),
        info_plist={"NSHighResolutionCapable": True, "CFBundleShortVersionString": version},
    )
