"""Validate an extracted, architecture-matched Microsoft Fixed Version runtime."""

from pathlib import Path
import struct


def validate_runtime(directory: Path) -> Path:
    runtime = directory.expanduser().resolve()
    if not runtime.is_dir() or str(runtime).startswith("\\\\"):
        raise ValueError("Fixed WebView2 must be an extracted directory on a local disk")
    executable = runtime / "msedgewebview2.exe"
    if not executable.is_file() or not (runtime / "msedge.dll").is_file():
        raise ValueError("Choose the complete Fixed Version folder containing msedgewebview2.exe and msedge.dll")
    with executable.open("rb") as stream:
        header = stream.read(64)
        if len(header) != 64 or header[:2] != b"MZ":
            raise ValueError("Invalid WebView2 PE executable")
        stream.seek(struct.unpack_from("<I", header, 60)[0])
        pe = stream.read(6)
    import platform

    expected = {"amd64": 0x8664, "x86_64": 0x8664, "arm64": 0xAA64, "aarch64": 0xAA64}.get(platform.machine().lower())
    if len(pe) != 6 or pe[:4] != b"PE\0\0" or expected is None or struct.unpack_from("<H", pe, 4)[0] != expected:
        raise ValueError("WebView2 runtime architecture must match the build computer")
    if any(path.is_symlink() for path in runtime.rglob("*")):
        raise ValueError("Linked files are not supported in the bundled runtime")
    return runtime
