"""Validate the Windows GUI payload before extracting or publishing it."""

from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path
import stat
import struct
import zipfile
import zlib


REQUIRED = {
    "MyPyTools/launch-gui.exe", "MyPyTools/_internal/launch-worker.exe",
    "MyPyTools/WebView2/msedgewebview2.exe", "MyPyTools/WebView2/msedge.dll",
    "MyPyTools/_internal/gui/resources/catalog.json",
    "MyPyTools/_internal/gui/resources/web/index.html",
}


def validate_payload(archive: zipfile.ZipFile, metadata: dict) -> None:
    names = set()
    normalized = set()
    total = 0
    for entry in archive.infolist():
        # Python normalizes backslashes and truncates NUL on Windows. Validate
        # the stored name, not merely its sanitized extraction representation.
        name = entry.orig_filename
        parts = name.split("/")
        mode = (entry.external_attr >> 16) & 0o170000
        if ("\\" in name or ":" in name or any(ord(char) < 32 or char in '<>"|?*' for char in name)
                or any(part in {"", ".", ".."} for part in parts)
                or parts[0] != "MyPyTools" or len(parts) < 2
                or mode not in {0, stat.S_IFREG}
                or any(part.endswith((".", " ")) for part in parts)
                or any(part.split(".")[0].upper() in {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))} for part in parts)):
            raise ValueError(f"Unsafe portable payload path: {name}")
        if name.casefold() in normalized:
            raise ValueError(f"Duplicate portable payload path: {name}")
        names.add(name)
        normalized.add(name.casefold())
        total += entry.file_size
    if not REQUIRED.issubset(names):
        raise ValueError("Portable payload must include its GUI, internal worker, frontend and Fixed WebView2")
    public = {name for name in names if name.count("/") == 1 and name.lower().endswith(".exe")}
    if public != {"MyPyTools/launch-gui.exe"}:
        raise ValueError("Portable payload must expose only the GUI executable")
    # Also reject a file used as another member's parent, on case-insensitive Windows.
    if any("/".join(name.casefold().split("/")[:index]) in normalized
           for name in names for index in range(1, len(name.split("/")))):
        raise ValueError("Portable payload has conflicting file and directory paths")
    if metadata.get("unpacked_size") != total or metadata.get("files") != len(names):
        raise ValueError("Portable payload file count or unpacked size mismatch")
    if archive.testzip() is not None:
        raise ValueError("Portable payload CRC failed")


def check_hash(stream, metadata: dict, size: int) -> None:
    if metadata.get("size") != size or hashlib.file_digest(stream, "sha256").hexdigest() != metadata.get("sha256"):
        raise ValueError("Portable payload size or SHA-256 mismatch")


def extract_payload(payload: Path, metadata: dict, destination: Path) -> Path:
    with payload.open("rb") as stream:
        check_hash(stream, metadata, payload.stat().st_size)
    with zipfile.ZipFile(payload) as archive:
        validate_payload(archive, metadata)
        target = destination / "MyPyTools"
        if target.exists():
            raise ValueError("Portable extraction target already exists")
        # Only the bootloader-owned, fresh directory is used. Never replace user files.
        target.mkdir()
        archive.extractall(destination)
    return target / "launch-gui.exe"


def inspect_executable(executable: Path) -> dict:
    """Build-time inspection only; PyInstaller is not imported by the launcher."""
    try:
        from PyInstaller.archive.readers import ArchiveReadError, CArchiveReader
    except ImportError as error:
        raise ValueError("EXE verification requires setup/requirements-build.txt") from error
    try:
        with executable.open("rb") as stream:
            if stream.read(2) != b"MZ":
                raise ValueError("Portable executable is not a Windows PE")
            stream.seek(60)
            offset = struct.unpack("<I", stream.read(4))[0]
            stream.seek(offset)
            if stream.read(6) != b"PE\0\0\x64\x86":
                raise ValueError("Portable executable must be Windows x64")
            stream.seek(offset + 24 + 68)
            if stream.read(2) != b"\x02\x00":
                raise ValueError("Portable executable must use the windowless GUI subsystem")
        reader = CArchiveReader(str(executable))
        metadata = json.loads(reader.extract("payload-info.json"))
        payload = reader.extract("gui_payload.zip")
        if not isinstance(metadata, dict) or not isinstance(payload, bytes):
            raise ValueError("Invalid portable payload metadata")
        stream = io.BytesIO(payload)
        check_hash(stream, metadata, len(payload))
        with zipfile.ZipFile(stream) as archive:
            validate_payload(archive, metadata)
        return metadata
    except (ArchiveReadError, KeyError, TypeError, struct.error, zlib.error, json.JSONDecodeError, zipfile.BadZipFile) as error:
        raise ValueError("Invalid portable executable payload") from error
