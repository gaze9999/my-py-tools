import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from gui.packaging import build
from scripts.prepare_release import source_snapshot


class WorkbenchIntegrationTests(unittest.TestCase):
    def test_source_snapshot_excludes_private_ui_checkout_without_git(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            (root / "VERSION").write_text("0.4.2\n", encoding="utf-8")
            (root / ".workbench-ui").mkdir()
            (root / ".workbench-ui/private.js").write_text("fixture", encoding="utf-8")
            snapshot = source_snapshot(root, "0.4.2")
            self.assertEqual(set(snapshot), {"VERSION"})

    def test_stale_frontend_fails_before_creating_packaging_resources(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            resources = root / "src/gui/resources"
            resources.mkdir(parents=True)
            (root / "workbench-ui.json").write_text(json.dumps({"revision": "a" * 40}), encoding="utf-8")
            (resources / "workbench-ui.json").write_text(json.dumps({"commit": "b" * 40, "dirty": False}), encoding="utf-8")
            with patch.object(build, "ROOT", root), patch.object(build, "SOURCE", root / "src"):
                with self.assertRaisesRegex(ValueError, "pinned Workbench UI"):
                    build.prepare_resources()
            self.assertFalse((resources / "icons").exists())
            self.assertFalse((resources / "tiktoken").exists())


if __name__ == "__main__":
    unittest.main()
