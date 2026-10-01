"""Start the GUI with pythonw and show a visible fallback when initialization fails."""

from __future__ import annotations

import os
from pathlib import Path
import sys
import traceback


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
STARTUP_LOG = REPOSITORY_ROOT / ".gui" / "startup-error.log"


def report_startup_error(error: BaseException) -> None:
    message = f"GUI 初始化失敗: {type(error).__name__}: {error}"
    try:
        STARTUP_LOG.parent.mkdir(parents=True, exist_ok=True)
        STARTUP_LOG.write_text(traceback.format_exc(), encoding="utf-8")
    except OSError:
        pass
    if os.name == "nt":
        try:
            import ctypes

            ctypes.windll.user32.MessageBoxW(
                None,
                message + f"\n\n詳細資訊: {STARTUP_LOG}",
                "My Py Tools",
                0x10,
            )
            return
        except (AttributeError, OSError):
            pass
    if sys.stderr is not None:
        print(message, file=sys.stderr)


def main() -> int:
    try:
        from gui.launcher import main as launch

        return launch()
    except SystemExit as exc:
        return int(exc.code or 0)
    except BaseException as exc:
        report_startup_error(exc)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
