# Build on the target OS. The GUI and CLI helper share one bundled Python runtime.
from pathlib import Path
import sys

root = Path(SPECPATH).parents[1]
sys.path.insert(0, str(root))
sys.path.insert(0, str(root / "packages/workspace_core"))
from gui.catalog import TOOLS
from shared.version import repository_version
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

version = repository_version(root)
resources = root / "gui/resources"
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
    [str(root / "gui/packaging/desktop_entry.py")],
    pathex=[str(root), str(root / "packages/workspace_core")],
    hookspath=[str(root / "gui/packaging/hooks")],
    binaries=[], datas=data, hiddenimports=hidden,
    excludes=["tkinter", "customtkinter", "tkinterdnd2", "PyQt5", "PyQt6", "PySide2", "PySide6"],
    noarchive=False,
)
pyz = PYZ(analysis.pure)
gui = EXE(
    pyz, analysis.scripts, [], exclude_binaries=True, name="MyPyTools",
    console=False, upx=False,
)
runner = EXE(
    pyz, analysis.scripts, [], exclude_binaries=True, name="MyPyToolsRunner",
    console=True, upx=False,
)
collection = COLLECT(gui, runner, analysis.binaries, analysis.datas, strip=False, upx=False, name="MyPyTools")
if sys.platform == "darwin":
    application = BUNDLE(
        collection, name="My Py Tools.app", bundle_identifier="io.github.gaze9999.mypytools",
        version=version,
        info_plist={"NSHighResolutionCapable": True, "CFBundleShortVersionString": version},
    )
