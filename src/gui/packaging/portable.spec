"""Thin onefile wrapper; all GUI/worker/browser files stay in one payload."""
import os
from pathlib import Path

source = Path(SPECPATH).parents[1]
payload = Path(os.environ["MY_PY_TOOLS_GUI_PAYLOAD"])
a = Analysis(
    [str(Path(SPECPATH) / "portable_entry.py")], pathex=[str(source)],
    binaries=[], datas=[(str(payload / "gui_payload.zip"), "."), (str(payload / "payload-info.json"), ".")],
    hiddenimports=[], hookspath=[], runtime_hooks=[], excludes=["tkinter", "webview", "PyInstaller", "PyQt5", "PyQt6", "PySide6"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], name="launch-gui",
          debug=False, strip=False, upx=False, console=False, disable_windowed_traceback=True,
          icon=str(source / "gui/resources/icons/app.ico"))
