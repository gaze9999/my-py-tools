"""Launch every supported command from a token-protected localhost Web GUI."""

from __future__ import annotations

import argparse
import codecs
import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import secrets
import shlex
import shutil
import signal
import subprocess
import sys
import threading
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse
import uuid
import webbrowser

from gui.catalog import DISCOVERY_WARNINGS, TOOLS, TOOLS_BY_ID
from shared.version import repository_version


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
ASSET_ROOT = Path(__file__).resolve().with_name("web")
OUTPUT_LIMIT = 2 * 1024 * 1024
REQUEST_LIMIT = 64 * 1024
LOG_ROOT = REPOSITORY_ROOT / ".gui"
LOG_PATH = LOG_ROOT / "my-py-tools-gui.log"
REPOSITORY_VERSION = repository_version(REPOSITORY_ROOT)


def configure_logging() -> None:
    LOG_ROOT.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(LOG_PATH, maxBytes=512 * 1024, backupCount=1, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(logging.INFO)


def console_message(message: str, *, error: bool = False) -> None:
    stream = sys.stderr if error else sys.stdout
    if stream is not None:
        print(message, file=stream, flush=True)
    (logging.error if error else logging.info)(message)


def startup_error(message: str) -> int:
    console_message(f"error: {message}", error=True)
    if os.name == "nt" and sys.stderr is None:
        try:
            import ctypes

            ctypes.windll.user32.MessageBoxW(None, message, "My Py Tools", 0x10)
        except (AttributeError, OSError):
            pass
    return 2


def split_cli_args(value: str) -> list[str]:
    if not value.strip():
        return []
    if os.name != "nt":
        return shlex.split(value)

    import ctypes
    from ctypes import wintypes

    argc = ctypes.c_int()
    command_line_to_argv = ctypes.windll.shell32.CommandLineToArgvW
    command_line_to_argv.argtypes = (wintypes.LPCWSTR, ctypes.POINTER(ctypes.c_int))
    command_line_to_argv.restype = ctypes.POINTER(wintypes.LPWSTR)
    pointer = command_line_to_argv(value, ctypes.byref(argc))
    if not pointer:
        raise ValueError("Unable to parse Windows command line")
    try:
        return [pointer[index] for index in range(argc.value)]
    finally:
        local_free = ctypes.windll.kernel32.LocalFree
        local_free.argtypes = (ctypes.c_void_p,)
        local_free.restype = ctypes.c_void_p
        local_free(ctypes.cast(pointer, ctypes.c_void_p))


def command_text(command: list[str]) -> str:
    return subprocess.list2cmdline(command) if os.name == "nt" else shlex.join(command)


def resolve_executable(value: str) -> Path:
    candidate = Path(value).expanduser()
    if candidate.is_file():
        return candidate.resolve()
    found = shutil.which(value)
    if found:
        return Path(found).resolve()
    raise ValueError(f"Python executable not found: {value}")


def default_tool_python() -> str:
    executable = Path(sys.executable)
    if os.name == "nt" and executable.name.casefold() == "pythonw.exe":
        console_python = executable.with_name("python.exe")
        if console_python.is_file():
            return str(console_python)
    return str(executable)


def _windows_process_tree(root_pid: int) -> list[int]:
    """Return descendants before their parents, followed by the root process."""
    import ctypes
    from ctypes import wintypes

    class ProcessEntry(ctypes.Structure):
        _fields_ = [
            ("size", wintypes.DWORD),
            ("usage", wintypes.DWORD),
            ("process_id", wintypes.DWORD),
            ("default_heap_id", ctypes.c_size_t),
            ("module_id", wintypes.DWORD),
            ("threads", wintypes.DWORD),
            ("parent_process_id", wintypes.DWORD),
            ("priority_class_base", wintypes.LONG),
            ("flags", wintypes.DWORD),
            ("exe_file", wintypes.WCHAR * 260),
        ]

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    create_snapshot = kernel32.CreateToolhelp32Snapshot
    create_snapshot.argtypes = (wintypes.DWORD, wintypes.DWORD)
    create_snapshot.restype = wintypes.HANDLE
    process_first = kernel32.Process32FirstW
    process_first.argtypes = (wintypes.HANDLE, ctypes.POINTER(ProcessEntry))
    process_first.restype = wintypes.BOOL
    process_next = kernel32.Process32NextW
    process_next.argtypes = (wintypes.HANDLE, ctypes.POINTER(ProcessEntry))
    process_next.restype = wintypes.BOOL
    close_handle = kernel32.CloseHandle
    close_handle.argtypes = (wintypes.HANDLE,)
    close_handle.restype = wintypes.BOOL

    snapshot = create_snapshot(0x00000002, 0)  # TH32CS_SNAPPROCESS
    if snapshot == wintypes.HANDLE(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    parents: dict[int, int] = {}
    try:
        entry = ProcessEntry()
        entry.size = ctypes.sizeof(entry)
        if process_first(snapshot, ctypes.byref(entry)):
            while True:
                parents[int(entry.process_id)] = int(entry.parent_process_id)
                if not process_next(snapshot, ctypes.byref(entry)):
                    break
    finally:
        close_handle(snapshot)

    depths = {root_pid: 0}
    changed = True
    while changed:
        changed = False
        for process_id, parent_id in parents.items():
            if process_id not in depths and parent_id in depths:
                depths[process_id] = depths[parent_id] + 1
                changed = True
    return sorted(depths, key=depths.__getitem__, reverse=True)


def _terminate_windows_process_tree(root_pid: int) -> list[str]:
    """Terminate a Windows process tree without opening a console window."""
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    open_process = kernel32.OpenProcess
    open_process.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    open_process.restype = wintypes.HANDLE
    terminate_process = kernel32.TerminateProcess
    terminate_process.argtypes = (wintypes.HANDLE, wintypes.UINT)
    terminate_process.restype = wintypes.BOOL
    wait_for_single_object = kernel32.WaitForSingleObject
    wait_for_single_object.argtypes = (wintypes.HANDLE, wintypes.DWORD)
    wait_for_single_object.restype = wintypes.DWORD
    close_handle = kernel32.CloseHandle
    close_handle.argtypes = (wintypes.HANDLE,)
    close_handle.restype = wintypes.BOOL

    errors = []
    for process_id in _windows_process_tree(root_pid):
        handle = open_process(0x0001 | 0x00100000, False, process_id)
        if not handle:
            error_code = ctypes.get_last_error()
            if error_code != 87:  # Process already exited.
                errors.append(f"pid {process_id}: {ctypes.WinError(error_code)}")
            continue
        try:
            if not terminate_process(handle, 1):
                errors.append(f"pid {process_id}: {ctypes.WinError(ctypes.get_last_error())}")
                continue
            wait_for_single_object(handle, 3000)
        finally:
            close_handle(handle)
    return errors


def directory_payload(value: str | None) -> dict[str, Any]:
    raw = (value or str(REPOSITORY_ROOT)).strip()
    path = Path(raw).expanduser().resolve()
    if path.is_file():
        path = path.parent
    if not path.is_dir():
        raise ValueError(f"Directory not found: {path}")
    entries = []
    try:
        children = sorted(path.iterdir(), key=lambda item: (not item.is_dir(), item.name.casefold()))
    except OSError as exc:
        raise ValueError(f"Unable to list directory: {exc}") from exc
    for child in children[:500]:
        try:
            is_directory = child.is_dir()
        except OSError:
            continue
        entries.append({"name": child.name, "path": str(child), "is_directory": is_directory})
    parent = path.parent if path.parent != path else None
    return {
        "path": str(path),
        "parent": str(parent) if parent else None,
        "entries": entries,
        "truncated": len(children) > 500,
    }


class ProcessManager:
    def __init__(self) -> None:
        self.lock = threading.RLock()
        self.process: subprocess.Popen[bytes] | None = None
        self.run_id: str | None = None
        self.output = ""
        self.output_truncated = False
        self.exit_code: int | None = None
        self.started_at: float | None = None
        self.finished_at: float | None = None
        self.command = ""

    def start(self, tool_id: str, args_text: str, cwd_value: str, python_value: str) -> dict[str, Any]:
        tool = TOOLS_BY_ID.get(tool_id)
        if tool is None:
            raise ValueError("Unknown tool")
        arguments = split_cli_args(args_text)
        if len(arguments) > 256:
            raise ValueError("Too many arguments")
        cwd = Path(cwd_value).expanduser().resolve()
        if not cwd.is_dir():
            raise ValueError(f"Working directory not found: {cwd}")
        executable = resolve_executable(python_value)
        command = [str(executable), "-u", "-m", tool.module, *arguments]
        environment = os.environ.copy()
        current_python_path = environment.get("PYTHONPATH")
        environment["PYTHONPATH"] = str(REPOSITORY_ROOT) + (
            os.pathsep + current_python_path if current_python_path else ""
        )
        environment["PYTHONUTF8"] = "1"
        environment["PYTHONUNBUFFERED"] = "1"
        creation_flags = 0
        start_new_session = os.name != "nt"
        if os.name == "nt":
            creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(
                subprocess, "CREATE_NEW_PROCESS_GROUP", 0
            )

        with self.lock:
            if self.process is not None and self.process.poll() is None:
                raise ValueError("Another tool is still running")
            self.run_id = uuid.uuid4().hex
            self.output = ""
            self.output_truncated = False
            self.exit_code = None
            self.started_at = time.time()
            self.finished_at = None
            self.command = command_text(command)
            try:
                self.process = subprocess.Popen(
                    command,
                    cwd=cwd,
                    env=environment,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    bufsize=0,
                    creationflags=creation_flags,
                    start_new_session=start_new_session,
                )
            except OSError as exc:
                self.process = None
                raise ValueError(f"Unable to start tool: {exc}") from exc
            run_id = self.run_id
            process = self.process

        threading.Thread(
            target=self._capture,
            args=(run_id, process),
            name=f"gui-tool-{run_id[:8]}",
            daemon=True,
        ).start()
        return self.snapshot(run_id)

    def _append(self, text: str) -> None:
        if not text:
            return
        self.output += text
        if len(self.output) > OUTPUT_LIMIT:
            self.output = self.output[-OUTPUT_LIMIT:]
            self.output_truncated = True

    def _capture(self, run_id: str, process: subprocess.Popen[bytes]) -> None:
        decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
        stream = process.stdout
        if stream is None:
            return
        try:
            while True:
                chunk = stream.read(4096)
                if not chunk:
                    break
                with self.lock:
                    if self.run_id == run_id:
                        self._append(decoder.decode(chunk))
            tail = decoder.decode(b"", final=True)
            with self.lock:
                if self.run_id == run_id:
                    self._append(tail)
        finally:
            exit_code = process.wait()
            stream.close()
            if process.stdin is not None:
                process.stdin.close()
            with self.lock:
                if self.run_id == run_id:
                    self.exit_code = exit_code
                    self.finished_at = time.time()

    def snapshot(self, run_id: str | None = None) -> dict[str, Any]:
        with self.lock:
            if run_id and run_id != self.run_id:
                raise ValueError("Run not found")
            running = self.process is not None and self.process.poll() is None
            return {
                "run_id": self.run_id,
                "running": running,
                "exit_code": self.exit_code,
                "output": self.output,
                "output_truncated": self.output_truncated,
                "started_at": self.started_at,
                "finished_at": self.finished_at,
                "command": self.command,
            }

    def send_input(self, run_id: str, value: str) -> dict[str, Any]:
        if len(value) > 4096:
            raise ValueError("stdin input is too long")
        with self.lock:
            if run_id != self.run_id or self.process is None or self.process.poll() is not None:
                raise ValueError("No matching running tool")
            if self.process.stdin is None:
                raise ValueError("Tool stdin is unavailable")
            try:
                self.process.stdin.write((value + "\n").encode("utf-8"))
                self.process.stdin.flush()
            except (BrokenPipeError, OSError) as exc:
                raise ValueError(f"Unable to write stdin: {exc}") from exc
        return self.snapshot(run_id)

    def stop(self, run_id: str | None = None) -> dict[str, Any]:
        with self.lock:
            if self.process is None or self.process.poll() is not None:
                return self.snapshot(run_id)
            if run_id and run_id != self.run_id:
                raise ValueError("Run not found")
            process = self.process
        if os.name == "nt":
            try:
                errors = _terminate_windows_process_tree(process.pid)
                if errors:
                    logging.warning("Unable to stop part of process tree: %s", "; ".join(errors))
            except OSError as exc:
                logging.warning("Unable to enumerate process tree for pid %s: %s", process.pid, exc)
            if process.poll() is None:
                process.terminate()
        else:
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except OSError:
                pass
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            if os.name == "nt":
                process.kill()
            else:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except OSError:
                    process.kill()
            process.wait(timeout=3)
        return self.snapshot(run_id)


class GuiServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address: tuple[str, int], token: str, startup_files: list[Path] | None = None):
        super().__init__(address, GuiRequestHandler)
        self.token = token
        self.manager = ProcessManager()
        self.startup_files = startup_files or []

    def defaults(self) -> dict[str, str | None]:
        return {
            "python": default_tool_python(),
            "cwd": str(REPOSITORY_ROOT),
            "tool_id": "document-to-markdown" if self.startup_files else None,
            "args": command_text([str(path) for path in self.startup_files]),
        }

    def handle_error(self, request: object, client_address: tuple[str, int]) -> None:
        logging.exception("Unhandled GUI request error from %s:%s", *client_address)


class GuiRequestHandler(BaseHTTPRequestHandler):
    server: GuiServer

    def log_message(self, format: str, *args: object) -> None:
        return

    def _headers(self, content_type: str, length: int, status: HTTPStatus = HTTPStatus.OK) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(length))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self' data:",
        )
        self.end_headers()

    def _bytes(self, data: bytes, content_type: str, status: HTTPStatus = HTTPStatus.OK) -> None:
        self._headers(content_type, len(data), status)
        self.wfile.write(data)

    def _json(self, value: object, status: HTTPStatus = HTTPStatus.OK) -> None:
        self._bytes(
            json.dumps(value, ensure_ascii=False).encode("utf-8"),
            "application/json; charset=utf-8",
            status,
        )

    def _authorized(self, query: dict[str, list[str]]) -> bool:
        supplied = self.headers.get("X-GUI-Token") or (query.get("token") or [""])[0]
        return secrets.compare_digest(supplied, self.server.token)

    def _require_api_token(self, query: dict[str, list[str]]) -> bool:
        if self._authorized(query):
            return True
        self._json({"error": "Unauthorized"}, HTTPStatus.FORBIDDEN)
        return False

    def _asset(self, name: str, content_type: str) -> None:
        try:
            data = (ASSET_ROOT / name).read_bytes()
        except OSError:
            self._json({"error": "Asset not found"}, HTTPStatus.NOT_FOUND)
            return
        self._bytes(data, content_type)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        if parsed.path == "/":
            if not self._authorized(query):
                self._bytes(b"Forbidden", "text/plain; charset=utf-8", HTTPStatus.FORBIDDEN)
                return
            self._asset("index.html", "text/html; charset=utf-8")
            return
        if parsed.path == "/app.js":
            self._asset("app.js", "text/javascript; charset=utf-8")
            return
        if parsed.path == "/style.css":
            self._asset("style.css", "text/css; charset=utf-8")
            return
        if not parsed.path.startswith("/api/") or not self._require_api_token(query):
            if not parsed.path.startswith("/api/"):
                self._json({"error": "Not found"}, HTTPStatus.NOT_FOUND)
            return
        try:
            if parsed.path == "/api/tools":
                self._json(
                    {
                        "tools": [tool.payload() for tool in TOOLS],
                        "version": REPOSITORY_VERSION,
                        "defaults": self.server.defaults(),
                        "discovery_warnings": DISCOVERY_WARNINGS,
                    }
                )
            elif parsed.path == "/api/status":
                run_id = (query.get("run_id") or [None])[0]
                self._json(self.server.manager.snapshot(run_id))
            elif parsed.path == "/api/files":
                self._json(directory_payload((query.get("path") or [None])[0]))
            else:
                self._json({"error": "Not found"}, HTTPStatus.NOT_FOUND)
        except ValueError as exc:
            self._json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)

    def _body(self) -> dict[str, Any]:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError as exc:
            raise ValueError("Invalid Content-Length") from exc
        if not 0 < length <= REQUEST_LIMIT:
            raise ValueError("Invalid request size")
        try:
            value = json.loads(self.rfile.read(length).decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise ValueError("Invalid JSON request") from exc
        if not isinstance(value, dict):
            raise ValueError("JSON request must be an object")
        return value

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        if not parsed.path.startswith("/api/") or not self._require_api_token(query):
            if not parsed.path.startswith("/api/"):
                self._json({"error": "Not found"}, HTTPStatus.NOT_FOUND)
            return
        try:
            body = self._body()
            if parsed.path == "/api/run":
                result = self.server.manager.start(
                    str(body.get("tool_id", "")),
                    str(body.get("args", "")),
                    str(body.get("cwd", "")),
                    str(body.get("python", "")),
                )
            elif parsed.path == "/api/input":
                result = self.server.manager.send_input(
                    str(body.get("run_id", "")), str(body.get("value", ""))
                )
            elif parsed.path == "/api/stop":
                result = self.server.manager.stop(str(body.get("run_id", "")) or None)
            elif parsed.path == "/api/shutdown":
                result = {"status": "closing"}
                self.server.manager.stop()
                threading.Thread(target=self.server.shutdown, daemon=True).start()
            else:
                self._json({"error": "Not found"}, HTTPStatus.NOT_FOUND)
                return
            self._json(result)
        except ValueError as exc:
            self._json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)


class GuiArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise ValueError(message)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = GuiArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=0, help="Local port; 0 selects an available port")
    parser.add_argument("--no-browser", action="store_true", help="Print the URL without opening a browser")
    parser.add_argument(
        "files",
        nargs="*",
        type=Path,
        help="Documents dropped on launch-gui.cmd; preloaded into the Markdown converter",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    try:
        configure_logging()
    except OSError as exc:
        return startup_error(f"unable to initialize GUI log: {exc}")
    for warning in DISCOVERY_WARNINGS:
        logging.warning("GUI tool discovery skipped %s", warning)
    try:
        args = parse_args(argv)
    except ValueError as exc:
        return startup_error(f"invalid GUI arguments: {exc}")
    if not 0 <= args.port <= 65535:
        return startup_error("--port must be between 0 and 65535")
    startup_files = [path.expanduser().resolve() for path in args.files]
    missing = [str(path) for path in startup_files if not path.is_file()]
    if missing:
        return startup_error(f"input file not found: {missing[0]}")
    token = secrets.token_urlsafe(24)
    try:
        server = GuiServer(("127.0.0.1", args.port), token, startup_files)
    except OSError as exc:
        return startup_error(f"unable to start local GUI server: {exc}")
    port = server.server_address[1]
    url = f"http://127.0.0.1:{port}/?token={token}"
    console_message(f"My Py Tools GUI started: {url} pid={os.getpid()}")
    if not args.no_browser:
        threading.Timer(0.25, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever(poll_interval=0.25)
    except KeyboardInterrupt:
        pass
    finally:
        server.manager.stop()
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
