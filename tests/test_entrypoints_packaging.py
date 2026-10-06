from pathlib import Path
import base64
import contextlib
import io
import json
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from gui.packaging.fetch_webview2 import validate_url
from gui.packaging.webview2 import validate_runtime
from gui.runtime import runner_path
import cli


ROOT = Path(__file__).resolve().parents[1]


class EntryPointTests(unittest.TestCase):
    @unittest.skipUnless(sys.platform == "win32", "Windows PowerShell launchers")
    def test_ps1_launchers_preserve_arguments_cwd_and_exit_codes(self):
        text = '中文 with "quotes" & symbols; trailing\\'
        with tempfile.TemporaryDirectory(prefix="PS launch ") as temporary:
            for shell in ("powershell.exe", "pwsh.exe"):
                executable = shutil.which(shell)
                if not executable:
                    continue
                for name, values, expected in (
                    ("launch-cli.ps1", ["text.tokenizer", "--text", text, "--json"], 0),
                    ("launch-cli.ps1", ["documents.convert_to_markdown", "missing file.txt"], 2),
                    ("launch-web.ps1", ["--port", "-1"], 2),
                ):
                    with self.subTest(shell=shell, launcher=name):
                        payload = base64.b64encode(json.dumps(values, ensure_ascii=False).encode()).decode()
                        command = f"$values = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('{payload}')) | ConvertFrom-Json; & '{ROOT / name}' @values; exit $LASTEXITCODE"
                        encoded = base64.b64encode(command.encode("utf-16-le")).decode()
                        result = subprocess.run([executable, "-NoProfile", "-ExecutionPolicy", "Bypass", "-EncodedCommand", encoded], cwd=temporary, capture_output=True, encoding="utf-8", errors="replace", timeout=30)
                        self.assertEqual(result.returncode, expected, result.stderr)
                        if expected == 0:
                            self.assertEqual(json.loads(result.stdout)["chars"], len(text))

    @unittest.skipUnless(sys.platform == "win32", "Windows PowerShell launchers")
    def test_gui_ps1_starts_hidden_without_waiting_and_quotes_native_arguments(self):
        with tempfile.TemporaryDirectory(prefix="GUI launch ") as temporary:
            directory = Path(temporary)
            script = directory / "launch-gui.ps1"
            shutil.copy2(ROOT / script.name, script)
            (directory / "launch-gui.exe").write_bytes(b"fixture")
            for shell in ("powershell.exe", "pwsh.exe"):
                executable = shutil.which(shell)
                if not executable:
                    continue
                command = """
function Start-Process {
    param($FilePath, $ArgumentList, $WorkingDirectory, $WindowStyle, [switch] $Wait)
    [Console]::WriteLine((@{file=$FilePath; arguments=$ArgumentList; cwd=$WorkingDirectory; hidden=$WindowStyle; wait=[bool]$Wait} | ConvertTo-Json -Compress))
}
""" + f"& '{script}' 'a b' 'a\"b' 'tail\\' ''; exit $LASTEXITCODE"
                encoded = base64.b64encode(command.encode("utf-16-le")).decode()
                result = subprocess.run([executable, "-NoProfile", "-ExecutionPolicy", "Bypass", "-EncodedCommand", encoded], capture_output=True, encoding="utf-8", timeout=15)
                with self.subTest(shell=shell):
                    self.assertEqual(result.returncode, 0, result.stderr)
                    data = json.loads(result.stdout)
                    self.assertEqual(data["file"], str(directory / "launch-gui.exe"))
                    self.assertEqual(data["cwd"], str(directory))
                    self.assertEqual(data["hidden"], "Hidden")
                    self.assertFalse(data["wait"])
                    self.assertEqual(data["arguments"], '"a b" "a\\"b" "tail\\\\" ""')

    @unittest.skipUnless(sys.platform == "win32", "Windows CMD launchers")
    def test_separate_cmd_launchers_preserve_arguments_and_errors(self):
        with tempfile.TemporaryDirectory() as temporary:
            result = subprocess.run(["cmd.exe", "/d", "/c", str(ROOT / "launch-cli.cmd"), "text.tokenizer", "--text", "hello", "--json"], cwd=temporary, capture_output=True, text=True, encoding="utf-8")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('"chars": 5', result.stdout)
            result = subprocess.run(["cmd.exe", "/d", "/c", str(ROOT / "launch-web.cmd"), "--port", "-1"], cwd=temporary, capture_output=True, text=True, encoding="utf-8")
            self.assertEqual(result.returncode, 2)
            self.assertIn("valid port", result.stderr)

    def test_portable_cli_rejects_source_only_execution_and_gui_builders(self):
        for arguments in (["scripts.release", "prepare", "--dry-run"], ["gui.launcher"]):
            with self.subTest(arguments=arguments), patch.dict(os.environ), patch.object(cli, "is_bundled", return_value=True), contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
                cli.main(list(arguments))
            self.assertEqual(error.exception.code, 2)

    def test_windows_gui_finds_worker_only_inside_internal_runtime(self):
        with patch("sys.platform", "win32"), patch("sys.frozen", True, create=True), patch("sys._MEIPASS", str(ROOT / "app/_internal"), create=True):
            self.assertEqual(runner_path(), ROOT / "app/_internal/launch-worker.exe")

    def test_cli_runs_from_unrelated_directory_and_preserves_exit_code(self):
        with tempfile.TemporaryDirectory() as temporary:
            command = [sys.executable, str(ROOT / "launch-cli.py")]
            result = subprocess.run([*command, "text.tokenizer", "--text", "hello", "--json"], cwd=temporary, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('"chars": 5', result.stdout)
            result = subprocess.run([*command, "documents.convert_to_markdown", "missing.txt"], cwd=temporary, capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)

    def test_cli_rejects_modules_outside_the_tool_catalog(self):
        result = subprocess.run([sys.executable, str(ROOT / "launch-cli.py"), "os"], capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        self.assertIn("Unknown tool", result.stderr)

    def test_cli_list_always_uses_utf8_even_with_legacy_python_stdio(self):
        environment = dict(os.environ, PYTHONIOENCODING="cp950")
        result = subprocess.run([sys.executable, str(ROOT / "launch-cli.py"), "--list"], env=environment, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("文件", result.stdout.decode("utf-8"))

    def test_microsoft_download_urls_are_restricted(self):
        self.assertEqual(validate_url("https://msedge.sf.dl.delivery.mp.microsoft.com/test.cab"), "https://msedge.sf.dl.delivery.mp.microsoft.com/test.cab")
        for value in ("http://download.microsoft.com/test.cab", "https://example.com/test.cab", "https://download.microsoft.com.evil.example/test.cab", "https://user:password@download.microsoft.com/test.cab"):
            with self.subTest(url=value), self.assertRaises(ValueError):
                validate_url(value)

    def test_fixed_runtime_requires_complete_matching_local_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            runtime = Path(temporary)
            with self.assertRaises(ValueError):
                validate_runtime(runtime)
            header = bytearray(64)
            header[:2] = b"MZ"
            struct.pack_into("<I", header, 60, 64)
            (runtime / "msedgewebview2.exe").write_bytes(header + b"PE\0\0" + struct.pack("<H", 0x8664))
            (runtime / "msedge.dll").write_bytes(b"fixture")
            with patch("platform.machine", return_value="AMD64"):
                self.assertEqual(validate_runtime(runtime), runtime.resolve())
            with patch("platform.machine", return_value="ARM64"), self.assertRaisesRegex(ValueError, "architecture"):
                validate_runtime(runtime)
