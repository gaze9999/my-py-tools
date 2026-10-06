"""Run one catalog CLI inside the bundled Windows/macOS helper executable."""

from __future__ import annotations

import runpy
import os
import sys
import traceback

from gui.catalog import TOOLS_BY_ID
from gui.runtime import is_bundled, resource_root


def main(argv: list[str] | None = None) -> int:
    if is_bundled():
        os.environ.setdefault("TIKTOKEN_CACHE_DIR", str(resource_root() / "tiktoken-cache"))
    values = list(sys.argv[1:] if argv is None else argv)
    if not values:
        print("error: tool module is required", file=sys.stderr)
        return 2
    module, *arguments = values
    if module not in {tool.module for tool in TOOLS_BY_ID.values()}:
        print(f"error: tool module is not available: {module}", file=sys.stderr)
        return 2
    for stream in (sys.stdout, sys.stderr):
        if stream is not None and hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
    sys.argv = [module, *arguments]
    try:
        runpy.run_module(module, run_name="__main__", alter_sys=False)
    except SystemExit as exc:
        if isinstance(exc.code, str):
            print(exc.code, file=sys.stderr)
            return 1
        return int(exc.code or 0)
    except Exception:
        traceback.print_exc()
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
