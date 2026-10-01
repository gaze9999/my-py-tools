"""Test-only helper that starts a delayed child process."""

from __future__ import annotations

from pathlib import Path
import subprocess
import sys
import time


def main() -> int:
    marker = Path(sys.argv[1])
    child_code = (
        "from pathlib import Path; import sys, time; "
        "time.sleep(2); Path(sys.argv[1]).write_text('alive', encoding='utf-8')"
    )
    subprocess.Popen([sys.executable, "-c", child_code, str(marker)])
    print("child started", flush=True)
    time.sleep(30)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
