"""Shared frozen entry point; the console helper dispatches only catalog tools."""

from pathlib import Path
import sys

if Path(sys.executable).stem == "MyPyToolsRunner":
    from gui.tool_runner import main
else:
    from gui.background_launcher import main

if __name__ == "__main__":
    raise SystemExit(main())
