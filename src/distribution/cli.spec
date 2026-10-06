# Terminal and browser modes share the desktop HTML, without a browser runtime.
from pathlib import Path
import sys

root = Path(SPECPATH).parents[1]
source = root / "src"
sys.path.insert(0, str(source))
sys.path.insert(0, str(root / "packages/workspace_core"))
from gui.catalog import TOOLS
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

resources = source / "gui/resources"
data = [
    (str(root / "VERSION"), "."),
    (str(resources / "catalog.json"), "gui/resources"),
    (str(resources / "web/index.html"), "gui/resources/web"),
    (str(resources / "tiktoken"), "tiktoken-cache"),
]
for package in ("docx", "pptx"):
    data += collect_data_files(package)
hidden = [tool.module for tool in TOOLS] + [
    "gui.browser_app", "my_py_workspace_core", "pypdf", "pdfplumber", "openpyxl", "docx", "pptx", "tiktoken", "tiktoken_ext.openai_public",
]
hidden += collect_submodules("my_py_workspace_core")
analysis = Analysis(
    [str(source / "distribution/cli_entry.py")],
    pathex=[str(source), str(root / "packages/workspace_core")],
    hookspath=[str(source / "gui/packaging/hooks")],
    binaries=[], datas=data, hiddenimports=hidden,
    excludes=["webview", "gui.background_launcher", "tkinter", "PyQt5", "PyQt6", "PySide2", "PySide6"],
    noarchive=False,
)
pyz = PYZ(analysis.pure)
executable = EXE(pyz, analysis.scripts, [], exclude_binaries=True, name="launch-cli", console=True, upx=False,
                 icon=str(resources / "icons/app.ico") if sys.platform == "win32" else None)
collection = COLLECT(executable, analysis.binaries, analysis.datas, strip=False, upx=False, name="MyPyToolsCLI")
