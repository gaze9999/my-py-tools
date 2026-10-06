"""Local Windows observations and handle-bound termination, without elevation."""

from __future__ import annotations

import base64
import ctypes
from ctypes import wintypes as w
from dataclasses import dataclass, field
import json
import os
from pathlib import Path
import subprocess


@dataclass(frozen=True)
class Process:
    pid: int
    ppid: int
    name: str
    created: int = 0
    executable: str = ""
    sid: str = ""
    session: int = -1
    command: str | None = None
    cpu: int | None = None
    io: int | None = None
    critical: bool | None = None
    errors: tuple[str, ...] = ()


@dataclass
class Observation:
    processes: dict[int, Process]
    services: set[int] = field(default_factory=set)
    services_known: bool = False
    warnings: list[str] = field(default_factory=list)


class SafetyError(RuntimeError):
    """Only static messages/error codes belong in public diagnostics."""


class Entry(ctypes.Structure):
    _fields_ = [("size", w.DWORD), ("usage", w.DWORD), ("pid", w.DWORD),
                ("heap", ctypes.c_size_t), ("module", w.DWORD), ("threads", w.DWORD),
                ("ppid", w.DWORD), ("priority", w.LONG), ("flags", w.DWORD),
                ("name", w.WCHAR * 260)]


class IoCounters(ctypes.Structure):
    _fields_ = [(name, ctypes.c_ulonglong) for name in
                ("read_ops", "write_ops", "other_ops", "read_bytes", "write_bytes", "other_bytes")]


class SidAttributes(ctypes.Structure):
    _fields_ = [("sid", ctypes.c_void_p), ("attributes", w.DWORD)]


def _ticks(value: w.FILETIME) -> int:
    return (value.dwHighDateTime << 32) | value.dwLowDateTime


class WindowsApi:
    def __init__(self) -> None:
        if os.name != "nt":
            raise SafetyError("This tool requires Windows; no processes were changed")
        self.kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        self.advapi = ctypes.WinDLL("advapi32", use_last_error=True)
        definitions = {
            "OpenProcess": ([w.DWORD, w.BOOL, w.DWORD], w.HANDLE),
            "CloseHandle": ([w.HANDLE], w.BOOL),
            "CreateToolhelp32Snapshot": ([w.DWORD, w.DWORD], w.HANDLE),
            "Process32FirstW": ([w.HANDLE, ctypes.POINTER(Entry)], w.BOOL),
            "Process32NextW": ([w.HANDLE, ctypes.POINTER(Entry)], w.BOOL),
            "GetProcessTimes": ([w.HANDLE] + [ctypes.POINTER(w.FILETIME)] * 4, w.BOOL),
            "QueryFullProcessImageNameW": ([w.HANDLE, w.DWORD, w.LPWSTR, ctypes.POINTER(w.DWORD)], w.BOOL),
            "GetProcessIoCounters": ([w.HANDLE, ctypes.POINTER(IoCounters)], w.BOOL),
            "IsProcessCritical": ([w.HANDLE, ctypes.POINTER(w.BOOL)], w.BOOL),
            "WaitForSingleObject": ([w.HANDLE, w.DWORD], w.DWORD),
            "TerminateProcess": ([w.HANDLE, w.UINT], w.BOOL),
            "LocalFree": ([ctypes.c_void_p], ctypes.c_void_p),
        }
        for name, (arguments, result) in definitions.items():
            function = getattr(self.kernel, name)
            function.argtypes, function.restype = arguments, result
        for name, arguments in {
            "OpenProcessToken": [w.HANDLE, w.DWORD, ctypes.POINTER(w.HANDLE)],
            "GetTokenInformation": [w.HANDLE, ctypes.c_int, ctypes.c_void_p, w.DWORD, ctypes.POINTER(w.DWORD)],
            "ConvertSidToStringSidW": [ctypes.c_void_p, ctypes.POINTER(w.LPWSTR)],
        }.items():
            function = getattr(self.advapi, name)
            function.argtypes, function.restype = arguments, w.BOOL

    def open(self, pid: int, terminate: bool = False) -> int:
        # QUERY_LIMITED_INFORMATION | SYNCHRONIZE, never ALL_ACCESS or debug privilege.
        handle = self.kernel.OpenProcess(0x1000 | 0x100000 | (1 if terminate else 0), False, pid)
        if not handle:
            raise SafetyError(f"OpenProcess failed (Windows error {ctypes.get_last_error()})")
        return handle

    def identity(self, handle: int) -> dict[str, object]:
        created, exited, kernel, user = (w.FILETIME() for _ in range(4))
        if not self.kernel.GetProcessTimes(handle, *(ctypes.byref(v) for v in (created, exited, kernel, user))):
            raise SafetyError("Process timing unavailable")
        length = w.DWORD(32768)
        image = ctypes.create_unicode_buffer(length.value)
        if not self.kernel.QueryFullProcessImageNameW(handle, 0, image, ctypes.byref(length)):
            raise SafetyError("Executable identity unavailable")
        token = w.HANDLE()
        if not self.advapi.OpenProcessToken(handle, 8, ctypes.byref(token)):
            raise SafetyError("Ownership token unavailable")
        try:
            needed = w.DWORD()
            self.advapi.GetTokenInformation(token, 1, None, 0, ctypes.byref(needed))
            if not needed.value:
                raise SafetyError("Owner SID unavailable")
            buffer = ctypes.create_string_buffer(needed.value)
            if not self.advapi.GetTokenInformation(token, 1, buffer, needed, ctypes.byref(needed)):
                raise SafetyError("Owner SID unavailable")
            sid = ctypes.cast(buffer, ctypes.POINTER(SidAttributes)).contents.sid
            text_sid = w.LPWSTR()
            if not self.advapi.ConvertSidToStringSidW(sid, ctypes.byref(text_sid)):
                raise SafetyError("Owner SID conversion unavailable")
            try:
                owner = text_sid.value
            finally:
                self.kernel.LocalFree(ctypes.cast(text_sid, ctypes.c_void_p))
            session = w.DWORD()
            if not self.advapi.GetTokenInformation(token, 12, ctypes.byref(session), ctypes.sizeof(session), ctypes.byref(needed)):
                raise SafetyError("Owner session unavailable")
        finally:
            self.kernel.CloseHandle(token)
        io = IoCounters()
        io_value = None
        if self.kernel.GetProcessIoCounters(handle, ctypes.byref(io)):
            io_value = io.read_bytes + io.write_bytes + io.other_bytes
        critical = w.BOOL()
        critical_value = None
        if self.kernel.IsProcessCritical(handle, ctypes.byref(critical)):
            critical_value = bool(critical.value)
        return {"created": _ticks(created), "executable": image.value, "sid": owner,
                "session": session.value, "cpu": _ticks(kernel) + _ticks(user),
                "io": io_value, "critical": critical_value}

    def enumerate(self) -> dict[int, Process]:
        snapshot = self.kernel.CreateToolhelp32Snapshot(2, 0)
        if snapshot == ctypes.c_void_p(-1).value:
            raise SafetyError("Native process enumeration failed")
        processes = {}
        try:
            entry = Entry()
            entry.size = ctypes.sizeof(entry)
            more = self.kernel.Process32FirstW(snapshot, ctypes.byref(entry))
            if not more:
                raise SafetyError("Native process enumeration unavailable")
            while more:
                data = {}
                errors = ()
                try:
                    handle = self.open(entry.pid)
                    try:
                        data = self.identity(handle)
                    finally:
                        self.kernel.CloseHandle(handle)
                except SafetyError:
                    errors = ("native_identity_unavailable",)
                processes[entry.pid] = Process(entry.pid, entry.ppid, entry.name, **data, errors=errors)
                more = self.kernel.Process32NextW(snapshot, ctypes.byref(entry))
            if ctypes.get_last_error() != 18:  # ERROR_NO_MORE_FILES
                raise SafetyError("Native process enumeration incomplete")
        finally:
            self.kernel.CloseHandle(snapshot)
        return processes


# Only fixed local queries, no user strings or raw commands in the script/errors.
_QUERY = r"""
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
$rows = @(Get-CimInstance Win32_Process | ForEach-Object {
    [pscustomobject]@{pid=[int]$_.ProcessId; created=if ($_.CreationDate) {
        $_.CreationDate.ToUniversalTime().ToFileTimeUtc().ToString() } else { '0' };
        command=$_.CommandLine}
})
$servicesKnown = $true
$services = @()
try { $services = @(Get-CimInstance Win32_Service | Where-Object { $_.ProcessId -gt 0 } |
    ForEach-Object { [int]$_.ProcessId }) } catch { $servicesKnown = $false }
[pscustomobject]@{rows=$rows; services=$services; services_known=$servicesKnown} |
    ConvertTo-Json -Depth 4 -Compress
"""


class WindowsBackend:
    def __init__(self) -> None:
        self.api = WindowsApi()

    def collect(self) -> Observation:
        cim = None
        warnings = []
        # An explicit SystemRoot path avoids executing a PATH-shadowed PowerShell.
        shell = Path(os.environ.get("SystemRoot", "C:/Windows")) / "System32/WindowsPowerShell/v1.0/powershell.exe"
        try:
            result = subprocess.run(
                [str(shell), "-NoLogo", "-NoProfile", "-NonInteractive", "-EncodedCommand",
                 base64.b64encode(_QUERY.encode("utf-16-le")).decode("ascii")],
                capture_output=True, timeout=30, creationflags=subprocess.CREATE_NO_WINDOW,
                check=False,
            )
            if result.returncode == 0:
                cim = json.loads(result.stdout.decode("utf-8").lstrip("\ufeff"))
        except (OSError, subprocess.TimeoutExpired, ValueError, UnicodeError):
            pass
        if not isinstance(cim, dict):
            warnings.append("CIM unavailable: native identity/activity only; all processes retained")
            cim = {}
        try:
            if not all(key in cim for key in ("rows", "services", "services_known")):
                raise ValueError
            commands = {int(row["pid"]): row for row in cim.get("rows", [])}
            if len(commands) != len(cim["rows"]):
                raise ValueError
            services = {int(pid) for pid in cim.get("services", [])}
            for row in commands.values():
                if int(row["created"]) < 0 or not (row.get("command") is None or isinstance(row["command"], str)):
                    raise ValueError
        except (KeyError, TypeError, ValueError, OverflowError):
            warnings.append("Invalid CIM evidence; all processes retained")
            commands, services, cim = {}, set(), {}
        native = self.api.enumerate()
        processes = {}
        for pid, process in native.items():
            row = commands.get(pid, {})
            # WMI timestamps have microsecond precision. Never associate a reused PID.
            command = row.get("command") if process.created and int(row.get("created", 0)) // 10 == process.created // 10 else None
            processes[pid] = Process(**{**vars(process), "command": command})
        known = cim.get("services_known") is True
        if not known:
            warnings.append("Service ownership unavailable; all processes retained")
        return Observation(processes, services, known, warnings)

    def open_target(self, pid: int) -> int:
        return self.api.open(pid, terminate=True)

    def verify_handle(self, handle: int, expected: dict[str, object]) -> None:
        if self.api.kernel.WaitForSingleObject(handle, 0) != 258:  # WAIT_TIMEOUT means alive.
            raise SafetyError("Target exited or wait status unavailable")
        actual = self.api.identity(handle)
        for key in ("created", "executable", "sid", "session"):
            if actual[key] != expected[key]:
                raise SafetyError("Handle identity changed; retained")
        if actual["critical"] is not False:
            raise SafetyError("Critical-process status unknown or protected; retained")

    def terminate(self, handle: int) -> str:
        if not self.api.kernel.TerminateProcess(handle, 1):
            raise SafetyError(f"Termination failed (Windows error {ctypes.get_last_error()})")
        status = self.api.kernel.WaitForSingleObject(handle, 5000)
        return "terminated" if status == 0 else "termination_requested_exit_unconfirmed"

    def close(self, handle: int) -> None:
        self.api.kernel.CloseHandle(handle)
