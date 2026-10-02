"""Launch every supported command from the React desktop GUI."""

from __future__ import annotations

import argparse
import codecs
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import shlex
import shutil
import signal
import subprocess
import sys
import threading
import time
from typing import Any
import uuid

from gui.catalog import DISCOVERY_WARNINGS, TOOLS, TOOLS_BY_ID
from gui.runtime import is_bundled, log_root, runner_path
REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_LIMIT = 2 * 1024 * 1024
LOG_ROOT = log_root()
LOG_PATH = LOG_ROOT / "my-py-tools-gui.log"
SUPPORTED_DOCUMENT_SUFFIXES = {".pdf", ".xlsx", ".docx", ".pptx", ".csv", ".txt"}


def append_arguments(current: str, paths: tuple[str, ...] | list[str]) -> str:
    addition = command_text(list(paths))
    return " ".join(part for part in (current.strip(), addition) if part)


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
        source_only = tool.payload()["source_only"]
        if is_bundled() and source_only and arguments not in (["--help"], ["-h"]):
            if not python_value:
                raise ValueError("此開發工具需要選擇完整 my-py-tools 原始碼目錄與開發用 Python")
            if not (cwd / "VERSION").is_file() or not (cwd / "scripts/release.py").is_file():
                raise ValueError("工作目錄需選擇完整的 my-py-tools 原始碼 repository")
            executable = resolve_executable(python_value)
            command = [str(executable), "-u", "-m", tool.module, *arguments]
        elif is_bundled():
            runner = runner_path()
            if not runner.is_file():
                raise ValueError(f"Bundled tool runner not found: {runner}")
            command = [str(runner), tool.module, *arguments]
        else:
            executable = resolve_executable(python_value)
            command = [str(executable), "-u", "-m", tool.module, *arguments]
        environment = os.environ.copy()
        if not is_bundled():
            current_python_path = environment.get("PYTHONPATH")
            environment["PYTHONPATH"] = str(REPOSITORY_ROOT) + (
                os.pathsep + current_python_path if current_python_path else ""
            )
        else:
            environment.pop("PYTHONPATH", None)
            environment.pop("PYTHONHOME", None)
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
            # The capture thread must flush stdout and the exit code before reporting completion.
            running = self.process is not None and self.finished_at is None
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


def gui_defaults(startup_files: list[Path] | None = None) -> dict[str, object]:
    files = startup_files or []
    working_directory = files[0].parent if files else (Path.home() if is_bundled() else REPOSITORY_ROOT)
    return {
        "python": "" if is_bundled() else default_tool_python(),
        "cwd": str(working_directory),
        "tool_id": "document-to-markdown" if files else None,
        "args": command_text([str(path) for path in files]),
        "files": [str(path) for path in files],
        "bundled": is_bundled(),
    }


class GuiArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise ValueError(message)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = GuiArgumentParser(description=__doc__)
    parser.add_argument("--smoke-test", action="store_true", help="Verify the desktop bridge and then close")
    parser.add_argument(
        "files",
        nargs="*",
        type=Path,
        help="Documents dropped on the launcher; preloaded into the Markdown converter",
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
    startup_files = [path.expanduser().resolve() for path in args.files]
    missing = [str(path) for path in startup_files if not path.is_file()]
    if missing:
        return startup_error(f"input file not found: {missing[0]}")
    try:
        from gui.webview_app import run_app

        console_message(f"My Py Tools GUI started: pywebview pid={os.getpid()}")
        return run_app(gui_defaults(startup_files), smoke_test=args.smoke_test)
    except (ImportError, OSError, RuntimeError) as exc:
        return startup_error(f"unable to start desktop GUI: {exc}")


if __name__ == "__main__":
    raise SystemExit(main())
