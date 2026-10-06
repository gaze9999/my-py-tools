from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from gui.packaging.portable_payload import REQUIRED, extract_payload, inspect_executable, validate_payload


def payload_fixture(extra=(), omit=()) -> tuple[bytes, dict]:
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        for name in sorted(REQUIRED - set(omit)):
            archive.writestr(name, b"fixture")
        for name in extra:
            entry = zipfile.ZipInfo(name)
            # ZipInfo normalizes Windows separators when constructed; emulate an
            # archive from another platform without normalizing its stored name.
            entry.filename = name
            archive.writestr(entry, b"fixture")
    data = stream.getvalue()
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        metadata = {"size": len(data), "sha256": hashlib.sha256(data).hexdigest(),
                    "files": len(archive.infolist()), "unpacked_size": sum(item.file_size for item in archive.infolist())}
    return data, metadata


def executable_fixture(path: Path, payload: bytes, metadata: dict) -> None:
    from PyInstaller.archive.writers import CArchiveWriter

    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        (root / "gui_payload.zip").write_bytes(payload)
        (root / "payload-info.json").write_text(json.dumps(metadata), encoding="utf-8")
        CArchiveWriter(str(root / "payload.pkg"), [
            (name, str(root / name), True, "x") for name in ("gui_payload.zip", "payload-info.json")
        ], "python314.dll")
        header = bytearray(256)
        header[:2] = b"MZ"
        struct.pack_into("<I", header, 60, 64)
        header[64:70] = b"PE\0\0\x64\x86"
        struct.pack_into("<H", header, 64 + 24 + 68, 2)
        path.write_bytes(header + (root / "payload.pkg").read_bytes())


class PortablePayloadTests(unittest.TestCase):
    def test_valid_payload_extracts_without_overwriting(self):
        data, metadata = payload_fixture()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            payload = root / "gui_payload.zip"
            payload.write_bytes(data)
            self.assertEqual(extract_payload(payload, metadata, root), root / "MyPyTools/launch-gui.exe")
            self.assertEqual((root / "MyPyTools/launch-gui.exe").read_bytes(), b"fixture")
            with self.assertRaisesRegex(ValueError, "already exists"):
                extract_payload(payload, metadata, root)

    def test_unsafe_names_collisions_and_extra_public_cli_rejected(self):
        for name in ("../escaped", "/absolute", "MyPyTools/../escaped", "MyPyTools\\escaped",
                     "MyPyTools/stream:ads", "MyPyTools/NUL.txt", "MyPyTools/trailing.", "MyPyTools/bad?name",
                     "MyPyTools/LAUNCH-GUI.EXE", "MyPyTools/_internal", "MyPyTools/launch-cli.exe"):
            with self.subTest(name=name):
                data, metadata = payload_fixture(extra=[name])
                with zipfile.ZipFile(io.BytesIO(data)) as archive, self.assertRaises(ValueError):
                    validate_payload(archive, metadata)

    def test_missing_components_and_size_rejected_before_extraction(self):
        for omit in REQUIRED:
            data, metadata = payload_fixture(omit=[omit])
            with zipfile.ZipFile(io.BytesIO(data)) as archive, self.assertRaisesRegex(ValueError, "Fixed WebView2"):
                validate_payload(archive, metadata)
        data, metadata = payload_fixture()
        metadata["unpacked_size"] += 1
        with zipfile.ZipFile(io.BytesIO(data)) as archive, self.assertRaisesRegex(ValueError, "unpacked size"):
            validate_payload(archive, metadata)

    def test_hash_and_crc_fail_before_writes(self):
        data, metadata = payload_fixture()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            payload = root / "gui_payload.zip"
            payload.write_bytes(data + b"corrupt")
            with self.assertRaisesRegex(ValueError, "SHA-256"):
                extract_payload(payload, metadata, root)
            self.assertFalse((root / "MyPyTools").exists())
            damaged = bytearray(data)
            damaged[data.index(b"fixture")] ^= 1
            payload.write_bytes(damaged)
            metadata.update(size=len(damaged), sha256=hashlib.sha256(damaged).hexdigest())
            with self.assertRaisesRegex(ValueError, "CRC"):
                extract_payload(payload, metadata, root)
            self.assertFalse((root / "MyPyTools").exists())

    def test_symlink_rejected(self):
        data, metadata = payload_fixture()
        stream = io.BytesIO(data)
        with zipfile.ZipFile(stream, "a") as archive:
            entry = zipfile.ZipInfo("MyPyTools/link")
            entry.external_attr = 0o120777 << 16
            archive.writestr(entry, "outside")
        with zipfile.ZipFile(stream) as archive, self.assertRaisesRegex(ValueError, "Unsafe"):
            validate_payload(archive, metadata)

    def test_onefile_archive_inspection_and_subsystem(self):
        try:
            import PyInstaller
        except ImportError:
            self.skipTest("Install setup/requirements-build.txt for EXE archive tests")
        data, metadata = payload_fixture()
        with tempfile.TemporaryDirectory() as temporary:
            executable = Path(temporary) / "launch-gui.exe"
            executable_fixture(executable, data, metadata)
            self.assertEqual(inspect_executable(executable), metadata)
            raw = bytearray(executable.read_bytes())
            struct.pack_into("<H", raw, 64 + 24 + 68, 3)
            executable.write_bytes(raw)
            with self.assertRaisesRegex(ValueError, "windowless"):
                inspect_executable(executable)
            executable.write_bytes(b"renamed file")
            with self.assertRaisesRegex(ValueError, "Windows PE"):
                inspect_executable(executable)

    @unittest.skipUnless(sys.platform == "win32", "Windows launcher")
    def test_wrapper_waits_for_child_and_resets_dll_environment(self):
        from gui.packaging import portable_entry

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "payload-info.json").write_text("{}", encoding="utf-8")
            with patch.object(sys, "_MEIPASS", str(root), create=True), patch.dict("os.environ", LOCALAPPDATA=str(root)), \
                    patch.object(portable_entry, "extract_payload", return_value=root / "MyPyTools/launch-gui.exe"), \
                    patch.object(portable_entry.subprocess, "Popen") as spawn, \
                    patch.object(portable_entry.ctypes.windll.kernel32, "SetDllDirectoryW") as reset:
                spawn.return_value.wait.return_value = 7
                self.assertEqual(portable_entry.main(), 7)
                self.assertEqual(spawn.call_args.kwargs["env"]["PYINSTALLER_RESET_ENVIRONMENT"], "1")
                self.assertEqual(spawn.call_args.kwargs["creationflags"], subprocess_flag())
                spawn.return_value.wait.assert_called_once()
                reset.assert_called_once_with(None)
            for handler in portable_entry.logging.getLogger("portable-launcher").handlers[:]:
                handler.close()
                portable_entry.logging.getLogger("portable-launcher").removeHandler(handler)


def subprocess_flag():
    import subprocess
    return subprocess.CREATE_NO_WINDOW
