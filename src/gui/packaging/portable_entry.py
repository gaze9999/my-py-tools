"""Windowless onefile entry; the inner GUI retains its independent runtime."""

from __future__ import annotations

import ctypes
import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import subprocess
import sys

from gui.packaging.portable_payload import extract_payload


def main() -> int:
    logger = logging.getLogger("portable-launcher")
    child = None
    try:
        log_root = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData/Local") / "MyPyTools/logs"
        log_root.mkdir(parents=True, exist_ok=True)
        logger.addHandler(RotatingFileHandler(log_root / "portable-launcher.log", maxBytes=512 * 1024, backupCount=1, encoding="utf-8"))
        logger.setLevel(logging.INFO)
        root = Path(sys._MEIPASS)
        metadata = json.loads((root / "payload-info.json").read_text(encoding="utf-8"))
        executable = extract_payload(root / "gui_payload.zip", metadata, root)
        logger.info("Starting bundled GUI: %s", executable)
        environment = dict(os.environ, PYINSTALLER_RESET_ENVIRONMENT="1")
        # Windows inherits the outer bootloader's DLL search path. The inner EXE
        # must load its own Python DLL, not the thin launcher's copy.
        ctypes.windll.kernel32.SetDllDirectoryW(None)
        child = subprocess.Popen([str(executable), *sys.argv[1:]], env=environment,
                                 creationflags=subprocess.CREATE_NO_WINDOW)
        result = child.wait()
        logger.info("Bundled GUI exited: %s", result)
        return result
    except Exception:
        logger.exception("Portable GUI startup failed")
        ctypes.windll.user32.MessageBoxW(None,
            "無法啟動 My Py Tools / Unable to start My Py Tools.\n"
            "請確認本機暫存磁碟空間與檔案權限, 詳細資訊請查看:\n"
            "%LOCALAPPDATA%\\MyPyTools\\logs\\portable-launcher.log",
            "My Py Tools", 0x10)
        return 1
    finally:
        # Never let bootloader cleanup remove files still used by our own child.
        if child is not None and child.poll() is None:
            child.wait()


if __name__ == "__main__":
    raise SystemExit(main())
