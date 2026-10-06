"""Serve the shared desktop interface on authenticated loopback HTTP only."""

from __future__ import annotations

import argparse
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import inspect
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import threading
import webbrowser

from gui.launcher import gui_defaults
from gui.runtime import is_bundled
from gui.webview_app import DesktopApi, resource_path


RPC_METHODS = {
    "bootstrap", "set_language", "choose_files", "choose_folder", "choose_python", "choose_save",
    "normalize_documents", "preview_command", "start_tool", "run_status", "stop_tool", "send_input",
    "append_paths", "document_arguments", "close_service",
}
MAX_BODY = 1024 * 1024

# Fixed scripts only. No path or user input is interpolated into executable code.
WINDOWS_PICKER = r'''
param([string]$kind)
Add-Type -AssemblyName System.Windows.Forms
if ($kind -eq 'folder') {
    $dialog = New-Object System.Windows.Forms.FolderBrowserDialog
} elseif ($kind -eq 'save') {
    $dialog = New-Object System.Windows.Forms.SaveFileDialog
    $dialog.Filter = 'Markdown (*.md)|*.md'
    $dialog.FileName = 'combined.md'
} else {
    $dialog = New-Object System.Windows.Forms.OpenFileDialog
    $dialog.Multiselect = $kind -ne 'python'
    if ($kind -eq 'documents') { $dialog.Filter = 'Documents|*.pdf;*.xlsx;*.docx;*.pptx;*.csv;*.txt|All files|*.*' }
    elseif ($kind -eq 'python') { $dialog.Filter = 'Python|python*.exe|All files|*.*' }
}
try {
    $values = @()
    if ($dialog.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) {
        if ($kind -eq 'folder') { $values = @($dialog.SelectedPath) }
        elseif ($kind -eq 'save') { $values = @($dialog.FileName) }
        else { $values = @($dialog.FileNames) }
    }
    [Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
    ConvertTo-Json -InputObject $values -Compress
} finally { $dialog.Dispose() }
'''

MAC_PICKER = r'''
function run(args) {
    const app = Application.currentApplication();
    app.includeStandardAdditions = true;
    app.activate();
    try {
        let values;
        if (args[0] === 'folder') values = [app.chooseFolder()];
        else if (args[0] === 'save') values = [app.chooseFileName({defaultName: 'combined.md'})];
        else {
            values = app.chooseFile({multipleSelectionsAllowed: args[0] !== 'python'});
            if (!Array.isArray(values)) values = [values];
        }
        return JSON.stringify(values.map(value => value.toString()));
    } catch (error) { if (error.errorNumber === -128) return '[]'; throw error; }
}
'''


class BrowserApi(DesktopApi):
    def __init__(self, defaults: dict[str, object]):
        super().__init__(defaults)
        self._lifecycle = threading.RLock()
        self._picker_lock = threading.Lock()
        self._picker: subprocess.Popen | None = None
        self._closed = False

    def _choose(self, kind: str) -> list[str]:
        if sys.platform == "win32":
            executable = Path(os.environ.get("SystemRoot", "C:/Windows")) / "System32/WindowsPowerShell/v1.0/powershell.exe"
            command = [str(executable), "-NoProfile", "-STA", "-Command", "& {" + WINDOWS_PICKER + "} " + kind]
        elif sys.platform == "darwin":
            command = ["osascript", "-l", "JavaScript", "-e", MAC_PICKER, kind]
        else:
            raise RuntimeError("Native picker unavailable; enter the full local path")
        with self._picker_lock:
            if self._closed or self._picker is not None:
                raise ValueError("File picker is unavailable or already open")
            process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0)
            self._picker = process
        try:
            output, error = process.communicate(timeout=120)
            if process.returncode:
                raise RuntimeError("Native picker unavailable; enter the full local path")
            values = json.loads(output.decode("utf-8-sig").strip())
            if not isinstance(values, list) or not all(isinstance(value, str) for value in values):
                raise ValueError("Invalid file picker response")
            return values
        except subprocess.TimeoutExpired:
            process.kill()
            process.communicate()
            raise RuntimeError("File picker timed out; enter the full local path") from None
        finally:
            with self._picker_lock:
                self._picker = None

    def choose_files(self, documents_only: bool = False) -> list[str]:
        if not isinstance(documents_only, bool):
            raise ValueError("documents_only must be a boolean")
        return self._choose("documents" if documents_only else "files")

    def choose_folder(self) -> str:
        values = self._choose("folder")
        return values[0] if values else ""

    def choose_python(self) -> str:
        values = self._choose("python")
        return values[0] if values else ""

    def choose_save(self) -> str:
        values = self._choose("save")
        return values[0] if values else ""

    def start_tool(self, tool_id: str, args_text: str, cwd: str, python: str) -> dict:
        with self._lifecycle:
            if self._closed:
                raise RuntimeError("Web service stopped")
            return super().start_tool(tool_id, args_text, cwd, python)

    def close_service(self) -> bool:
        return True

    def _shutdown(self) -> None:
        with self._lifecycle:
            self._closed = True
            with self._picker_lock:
                if self._picker is not None and self._picker.poll() is None:
                    self._picker.kill()
            super()._shutdown()


class BrowserServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, api: BrowserApi, index: Path, port: int = 0):
        self.api = api
        self.page = index.read_text(encoding="utf-8").replace("<head>", "<head><script>window.__MY_PY_TOOLS_BROWSER__=true;</script>", 1).encode("utf-8")
        self.token = secrets.token_urlsafe(32)
        self.closing = threading.Event()
        super().__init__(("127.0.0.1", port), BrowserHandler)
        self.origin = f"http://127.0.0.1:{self.server_port}"
        self.cookie_name = f"my_py_tools_{self.server_port}"

    def close(self) -> None:
        self.closing.set()
        self.api._shutdown()
        self.server_close()


class BrowserHandler(BaseHTTPRequestHandler):
    server: BrowserServer
    protocol_version = "HTTP/1.1"
    timeout = 10

    def handle(self) -> None:
        try:
            super().handle()
        except (ConnectionResetError, BrokenPipeError):
            pass  # A browser/client can disconnect between keep-alive requests.

    def log_message(self, *_args) -> None:
        pass  # Never log local paths, parameters or session credentials.

    def _reply(self, status: int, payload: object) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self._send(status, data, "application/json; charset=utf-8")

    def _send(self, status: int, data: bytes, content_type: str, *, cookie: bool = False) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src data:; connect-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'")
        if cookie:
            self.send_header("Set-Cookie", f"{self.server.cookie_name}={self.server.token}; HttpOnly; SameSite=Strict; Path=/")
        self.end_headers()
        self.wfile.write(data)

    def _local(self) -> bool:
        return self.headers.get("Host") == self.server.origin.removeprefix("http://")

    def do_GET(self) -> None:
        if not self._local():
            self._reply(403, {"error": "Invalid local host"})
        elif self.path in {"/", "/index.html"}:
            self._send(200, self.server.page, "text/html; charset=utf-8", cookie=True)
        else:
            self._reply(404, {"error": "Not found"})

    def do_POST(self) -> None:
        # Consume bounded requests before rejecting them. Closing a Windows socket
        # with unread bytes can reset the connection before the client gets an error.
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if self.headers.get("Transfer-Encoding") or not 0 < size <= MAX_BODY:
                raise ValueError("Invalid request size")
            body = self.rfile.read(size)
            if len(body) != size:
                raise ValueError("Incomplete request body")
        except (ValueError, OSError) as error:
            self.close_connection = True
            self._reply(400, {"error": str(error)})
            return
        cookie = SimpleCookie()
        try:
            cookie.load(self.headers.get("Cookie", ""))
        except Exception:
            self._reply(403, {"error": "Invalid session"})
            return
        session = cookie.get(self.server.cookie_name)
        if (not self._local() or self.headers.get("Origin") != self.server.origin
                or self.headers.get("X-My-Py-Tools") != "1" or session is None
                or not secrets.compare_digest(session.value.encode("utf-8"), self.server.token.encode("ascii"))):
            self._reply(403, {"error": "Invalid local session or origin"})
            return
        if self.server.closing.is_set():
            self._reply(503, {"error": "Web service stopped"})
            return
        method_name = self.path.removeprefix("/api/") if self.path.startswith("/api/") else ""
        if method_name not in RPC_METHODS:
            self._reply(404, {"error": "Unknown API method"})
            return
        try:
            if self.headers.get("Content-Type") != "application/json":
                raise ValueError("Use application/json")
            values = json.loads(body)
            if not isinstance(values, list) or len(values) > 8:
                raise ValueError("API arguments must be an array")
            method = getattr(self.server.api, method_name)
            inspect.signature(method).bind(*values)
            result = method(*values)
            self._reply(200, {"value": result})
            if method_name == "close_service":
                self.server.closing.set()
                threading.Thread(target=self.server.shutdown, daemon=True).start()
        except (ValueError, TypeError, OSError, RuntimeError, AttributeError) as error:
            self._reply(400, {"error": str(error)})


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=0, help="Loopback port, 0 chooses an available port")
    parser.add_argument("--no-browser", action="store_true", help="Print the local URL without opening a browser")
    parser.add_argument("--cwd", type=Path, default=Path.cwd(), help="Initial tool working directory")
    args = parser.parse_args(argv)
    cwd = args.cwd.expanduser().resolve()
    if not 0 <= args.port <= 65535 or not cwd.is_dir():
        parser.error("Choose a valid port and existing working directory")
    index = resource_path("gui/resources/web/index.html" if is_bundled() else "src/gui/resources/web/index.html")
    if not index.is_file():
        parser.error("Shared interface is missing; build the frontend with Workbench UI first")
    defaults = gui_defaults()
    defaults.update(cwd=str(cwd), browser=True)
    try:
        server = BrowserServer(BrowserApi(defaults), index, args.port)
    except OSError as error:
        parser.error(f"Unable to start local web service: {error}")
    print(f"WEB {server.origin}/", flush=True)
    if not args.no_browser:
        try:
            if not webbrowser.open(server.origin + "/"):
                print("Browser could not be opened; open the printed local URL", file=sys.stderr)
        except (webbrowser.Error, OSError):
            print("Browser could not be opened; open the printed local URL", file=sys.stderr)
    try:
        server.serve_forever(poll_interval=0.2)
    except KeyboardInterrupt:
        pass
    finally:
        server.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
