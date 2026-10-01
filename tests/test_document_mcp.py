from __future__ import annotations

import hashlib
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from mcp_tools.document_service import DocumentService


class DocumentServiceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.service = DocumentService([self.root], [self.root])
        self.source = self.root / "source.txt"
        self.source.write_text("來源文字 original text", encoding="utf-8")
        self.target = self.root / "target.md"
        self.target.write_bytes(b"\xef\xbb\xbf# Guide\r\n\r\n## Current\r\nold\r\n\r\n## Retained\r\nkeep\r\n")

    def test_native_preview_does_not_create_output(self):
        output = self.root / "audit.md"
        result = self.service.extract(str(self.source), str(output), ocr="off", max_chars=20)
        self.assertFalse(output.exists())
        self.assertTrue(result["truncated"])
        self.assertEqual(result["source_sha256"], hashlib.sha256(self.source.read_bytes()).hexdigest())

    def test_existing_output_requires_current_hash(self):
        output = self.root / "audit.md"
        first = self.service.extract(str(self.source), str(output), True, ocr="off")
        before = output.read_bytes()
        with self.assertRaisesRegex(ValueError, "current SHA"):
            self.service.extract(str(self.source), str(output), True, ocr="off")
        self.assertEqual(output.read_bytes(), before)
        updated = self.service.extract(str(self.source), str(output), True, first["output_sha256"], ocr="off")
        self.assertEqual(hashlib.sha256(output.read_bytes()).hexdigest(), updated["output_sha256"])

    def test_new_output_race_does_not_overwrite(self):
        output = self.root / "audit.md"
        original_link = __import__("os").link
        def race(source, target):
            Path(target).write_text("concurrent content", encoding="utf-8")
            original_link(source, target)
        with patch("mcp_tools.document_service.os.link", side_effect=race):
            with self.assertRaises(FileExistsError):
                self.service.extract(str(self.source), str(output), True, ocr="off")
        self.assertEqual(output.read_text(), "concurrent content")

    def test_roots_and_relative_paths_are_rejected(self):
        for source in ("source.txt", str(self.root.parent / "outside.txt")):
            with self.assertRaises(ValueError):
                self.service.extract(source, ocr="off")
        read_only = DocumentService([self.root], [])
        with self.assertRaisesRegex(ValueError, "roots"):
            read_only.update_markdown(str(self.target), "## Current\nnew", self.service.inspect_markdown(str(self.target))["sha256"], heading="## Current")

    def test_section_write_preserves_bom_crlf_and_unrelated_content(self):
        before = self.target.read_bytes()
        digest = self.service.inspect_markdown(str(self.target))["sha256"]
        result = self.service.update_markdown(str(self.target), "## Current\nnew", digest, heading="## Current")
        self.assertEqual(result["status"], "preview")
        self.assertEqual(self.target.read_bytes(), before)
        result = self.service.update_markdown(str(self.target), "## Current\nnew", digest, heading="## Current", write=True)
        after = self.target.read_bytes()
        self.assertTrue(after.startswith(b"\xef\xbb\xbf"))
        self.assertIn(b"## Current\r\nnew\r\n", after)
        self.assertTrue(after.endswith(b"## Retained\r\nkeep\r\n"))
        self.assertEqual(result["next_sha256"], hashlib.sha256(after).hexdigest())
        with self.assertRaisesRegex(ValueError, "Stale"):
            self.service.update_markdown(str(self.target), "## Current\nagain", digest, heading="## Current", write=True)

    def test_append_is_idempotent_and_rejects_different_duplicate(self):
        sha = self.service.inspect_markdown(str(self.target))["sha256"]
        self.service.update_markdown(str(self.target), "entry", sha, entry_id="check-001", write=True)
        sha = self.service.inspect_markdown(str(self.target))["sha256"]
        result = self.service.update_markdown(str(self.target), "entry", sha, entry_id="check-001", write=True)
        self.assertEqual(result["status"], "unchanged")
        with self.assertRaisesRegex(ValueError, "different content"):
            self.service.update_markdown(str(self.target), "other", sha, entry_id="check-001", write=True)

    def test_ocr_failure_is_explicit_partial_result(self):
        with patch.object(self.service, "_ocr", return_value={"status": "partial", "records": [], "errors": [{"reason": "missing engine"}], "omitted_items": 1}):
            result = self.service.extract(str(self.source))
        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["ocr"]["errors"][0]["reason"], "missing engine")

    def test_source_change_during_ocr_is_rejected_before_output(self):
        output = self.root / "audit.md"
        def mutate(*args):
            self.source.write_text("changed", encoding="utf-8")
            return {"status": "not_needed", "records": [], "errors": [], "omitted_items": 0}
        with patch.object(self.service, "_ocr", side_effect=mutate):
            with self.assertRaisesRegex(ValueError, "Source changed"):
                self.service.extract(str(self.source), str(output), True)
        self.assertFalse(output.exists())

    def test_duplicate_and_fenced_headings(self):
        self.target.write_text("# Guide\n```md\n## Hidden\n```\n## Current\none\n## Current\ntwo\n", encoding="utf-8")
        result = self.service.inspect_markdown(str(self.target))
        self.assertNotIn("## Hidden", result["headings"])
        with self.assertRaisesRegex(ValueError, "exactly once"):
            self.service.inspect_markdown(str(self.target), "## Current")

    def test_invalid_options_and_section_boundary_are_rejected(self):
        with self.assertRaises(ValueError):
            self.service.extract(str(self.source), ocr="off", pages=[1])
        with self.assertRaises(ValueError):
            self.service.extract(str(self.source), ocr_max_items=0)
        sha = self.service.inspect_markdown(str(self.target))["sha256"]
        with self.assertRaisesRegex(ValueError, "only the selected section"):
            self.service.update_markdown(str(self.target), "## Current\nnew\n## Other\nextra", sha, heading="## Current", write=True)


class InstallerTests(unittest.TestCase):
    def test_preview_apply_and_repeat_preserve_other_settings(self):
        from mcp_tools.install_document_mcp import main
        import sys
        try:
            import tomllib
        except ModuleNotFoundError:
            import tomli as tomllib
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = root / "config.toml"
            original = '[features]\nkeep = true\n\n[mcp_servers.other]\ncommand = "keep-command"\n'
            config.write_text(original, encoding="utf-8")
            args = ["install", "--python", sys.executable, "--config", str(config), "--read-root", str(root)]
            def run(extra):
                stream = io.StringIO()
                with patch("sys.argv", args + extra), patch("mcp_tools.install_document_mcp.subprocess.run"), contextlib.redirect_stdout(stream):
                    main()
                return json.loads(stream.getvalue())
            self.assertEqual(run([])["status"], "preview")
            self.assertEqual(config.read_text(), original)
            installed = run(["--apply"])
            self.assertEqual(installed["status"], "installed")
            self.assertEqual(Path(installed["backup"]).read_text(), original)
            data = tomllib.loads(config.read_text())
            self.assertEqual(data["features"], {"keep": True})
            self.assertEqual(data["mcp_servers"]["other"]["command"], "keep-command")
            self.assertEqual(run(["--apply"])["status"], "unchanged")
            self.assertEqual(len(list(root.glob("*.bak"))), 1)


if __name__ == "__main__":
    unittest.main()
