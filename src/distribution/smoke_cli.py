"""Verify a native portable CLI's browser API without a local Python dependency."""

from __future__ import annotations

import argparse
import http.client
import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import tempfile
import threading
import time
from urllib.parse import urlsplit


def verify(executable: Path, *, launcher: list[str] | None = None) -> dict[str, object]:
    environment = dict(os.environ)
    for name in ("PYTHONHOME", "PYTHONPATH", "TIKTOKEN_CACHE_DIR"):
        environment.pop(name, None)
    environment["PATH"] = str(Path(environment.get("SystemRoot", "C:/Windows")) / "System32") if sys.platform == "win32" else "/usr/bin:/bin"
    connection = None
    with tempfile.TemporaryDirectory(prefix="portable-cli-web-") as temporary:
        process = subprocess.Popen(
            [*(launcher or [str(executable), "--web"]), "--no-browser", "--cwd", temporary], cwd=temporary,
            env=environment, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8",
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
        lines: queue.Queue[str] = queue.Queue()
        reader = threading.Thread(target=lambda: lines.put(process.stdout.readline()), daemon=True)
        reader.start()
        try:
            line = lines.get(timeout=30).strip()
            if not line.startswith("WEB "):
                raise RuntimeError("Portable browser service did not report a local URL")
            address = urlsplit(line[4:])
            if address.scheme != "http" or address.hostname != "127.0.0.1" or not address.port or address.path != "/":
                raise RuntimeError("Portable browser service reported an invalid URL")
            connection = http.client.HTTPConnection(address.hostname, address.port, timeout=15)
            connection.request("GET", "/")
            page = connection.getresponse()
            cookie = page.getheader("Set-Cookie", "").split(";", 1)[0]
            if page.status != 200 or b"__MY_PY_TOOLS_BROWSER__=true" not in page.read() or not cookie:
                raise RuntimeError("Shared portable interface was not served")
            headers = {"Content-Type": "application/json", "X-My-Py-Tools": "1", "Origin": f"http://127.0.0.1:{address.port}", "Cookie": cookie}

            def call(name: str, arguments: list | None = None):
                connection.request("POST", "/api/" + name, json.dumps(arguments or []), headers)
                response = connection.getresponse()
                payload = json.loads(response.read())
                if response.status != 200:
                    raise RuntimeError(f"Portable browser API failed: {name}: {payload.get('error')}")
                return payload["value"]

            data = call("bootstrap")
            if not data["defaults"]["browser"] or not data["defaults"]["bundled"] or not data["tools"]:
                raise RuntimeError("Browser did not load the bundled CLI catalog")
            source = Path(temporary) / "中文 source.txt"
            source.write_text("本機文件測試\nPortable browser conversion\n", encoding="utf-8")
            arguments = call("document_arguments", [[str(source)], "source", "", False])
            state = call("start_tool", ["document-to-markdown", arguments, temporary, ""])
            deadline = time.monotonic() + 30
            while state["running"] and time.monotonic() < deadline:
                time.sleep(0.1)
                state = call("run_status", [state["run_id"]])
            if state["running"] or state["exit_code"] != 0 or not source.with_suffix(".md").is_file():
                raise RuntimeError("Browser could not convert the original local document using the bundled worker")
            call("close_service")
            connection.close()
            connection = None
            if process.wait(timeout=10) != 0:
                raise RuntimeError("Portable browser service shutdown failed")
            return {"passed": True, "tool_count": len(data["tools"]), "shared_interface": True, "document_conversion": True, "clean_shutdown": True}
        finally:
            if connection is not None:
                if "call" in locals() and process.poll() is None:
                    try:
                        call("close_service")
                    except (OSError, ValueError, RuntimeError, http.client.HTTPException):
                        pass
                connection.close()
            if process.poll() is None:
                process.kill()
            process.communicate(timeout=10)
            reader.join(3)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("executable", type=Path)
    args = parser.parse_args(argv)
    executable = args.executable.expanduser().resolve()
    if not executable.is_file():
        parser.error("Provide the native portable CLI executable")
    print(json.dumps(verify(executable)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
