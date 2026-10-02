import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from markdown.validate_structure import analyze

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("validator_export", ROOT / "scripts/export_markdown_validator.py")
export = importlib.util.module_from_spec(spec)
spec.loader.exec_module(export)


class StructureTests(unittest.TestCase):
    def test_fences_hide_headings_and_require_matching_closer(self):
        report = analyze("# Title\n````python\n### hidden\n```\n~~~\n````\n## Next\n")
        self.assertEqual(report["failures"], 0)
        self.assertEqual(report["checks"][0]["detail"], "found 2 headings")
        self.assertEqual(analyze("# Title\n```\ncontent\n")["failures"], 1)

    def test_heading_jumps_and_optional_heading_version(self):
        self.assertEqual(analyze("# Title\n### Jump\n")["failures"], 1)
        report = analyze("plain text\n")
        self.assertEqual(report["failures"], 0)
        self.assertEqual(report["warnings"], 1)
        version = next(c for c in report["checks"] if c["check"] == "document-version")
        self.assertEqual(version["status"], "INFO")

    def test_hard_break_and_version_detection(self):
        report = analyze("# Title\ntext  \n文件版本: v2\n")
        self.assertEqual(report["warnings"], 0)
        self.assertEqual(report["checks"][-1]["status"], "PASS")
        report = analyze("# Title\ntext \ntext\t\n")
        self.assertEqual(report["warnings"], 1)
        self.assertEqual(next(c for c in report["checks"] if c["check"] == "trailing-whitespace")["detail"], "lines: 2, 3")

    def test_exported_file_runs_without_repository_or_installed_core(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            script = root / "standalone.py"
            script.write_bytes(export.snapshot())
            document = root / "sample.md"
            document.write_text("# Title\ntext  \n", encoding="utf-8")
            result = subprocess.run([sys.executable, "-I", "-S", str(script), str(document)], cwd=root, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("SUMMARY: failures=0 warnings=0", result.stdout)
            document.write_text("# Title\n### Jump\n", encoding="utf-8")
            result = subprocess.run([sys.executable, "-I", "-S", str(script), str(document)], cwd=root, capture_output=True, text=True)
            self.assertEqual(result.returncode, 1)
            document.unlink()
            result = subprocess.run([sys.executable, "-I", "-S", str(script), str(document)], cwd=root, capture_output=True, text=True)
            self.assertEqual(result.returncode, 2)

    def test_source_and_snapshot_line_endings_are_portable(self):
        expected = export.snapshot()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "markdown").mkdir()
            source = (ROOT / "markdown/validate_structure.py").read_bytes().replace(b"\r\n", b"\n")
            (root / "markdown/validate_structure.py").write_bytes(source.replace(b"\n", b"\r\n"))
            (root / "pyproject.toml").write_bytes((ROOT / "pyproject.toml").read_bytes())
            self.assertEqual(export.snapshot(root), expected)
            target = root / "snapshot.py"
            target.write_bytes(expected.replace(b"\n", b"\r\n"))
            before = target.read_bytes()
            self.assertEqual(export.main(["--output", str(target), "--check"]), 0)
            self.assertEqual(target.read_bytes(), before)

    def test_export_check_rejects_changed_snapshot_without_writing(self):
        with tempfile.TemporaryDirectory() as temporary:
            script = Path(temporary) / "standalone.py"
            expected = export.snapshot()
            script.write_bytes(expected)
            self.assertEqual(export.main(["--output", str(script), "--check"]), 0)
            script.write_bytes(expected + b"# independently changed\n")
            before = script.read_bytes()
            self.assertEqual(export.main(["--output", str(script), "--check"]), 1)
            self.assertEqual(script.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
