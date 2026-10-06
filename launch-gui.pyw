"""Start the My Py Tools desktop GUI without opening a console window."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from gui.background_launcher import main


if __name__ == "__main__":
    raise SystemExit(main())
