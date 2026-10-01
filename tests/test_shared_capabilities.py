from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from documents.locate_markdown_extracts import locate_extracts
from shared.workspace_core import load_workspace_core


class SharedCapabilityTests(unittest.TestCase):
    def test_locate_extracts_distinguishes_current_and_stale_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.txt"
            source.write_text("current", encoding="utf-8")
            digest = hashlib.sha256(source.read_bytes()).hexdigest()
            (root / "current.md").write_text(
                f"# TXT Converted Markdown\n\n- Source: `{source}`\n- Source SHA-256: `{digest}`\n- Extracted on: 2026-10-01 12:34:56\n",
                encoding="utf-8",
            )
            (root / "stale.md").write_text(
                f"# TXT Converted Markdown\n\n- Source path: {source}\n- Source SHA-256: {'0' * 64}\n",
                encoding="utf-8",
            )
            (root / "combined.md").write_text(
                f"# Combined\n\n## Sources\n- `{source}` (txt, SHA-256 `{digest}`)\n",
                encoding="utf-8",
            )

            result = locate_extracts([root], source=source)

            self.assertEqual([item["status"] for item in result["candidates"]], ["current", "current", "stale"])
            self.assertEqual(result["candidates"][0]["match_reasons"], ["source_path", "source_sha256", "source_filename"])

    def test_workspace_core_compares_trees_and_indexes_extended_evidence(self) -> None:
        core = load_workspace_core()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            target = root / "target"
            runs = root / "runs" / "run-001"
            source.mkdir()
            target.mkdir()
            runs.mkdir(parents=True)
            (source / "same.txt").write_text("same", encoding="utf-8")
            (target / "same.txt").write_text("same", encoding="utf-8")
            (source / "changed.txt").write_text("before", encoding="utf-8")
            (target / "changed.txt").write_text("after", encoding="utf-8")
            (source / ".env").write_text("TOKEN=source", encoding="utf-8")
            (target / ".env").write_text("TOKEN=target", encoding="utf-8")
            runs.joinpath("results.json").write_text(
                json.dumps(
                    {
                        "source": "working-tree",
                        "baseline": "abc123",
                        "results": [
                            {
                                "name": "unit",
                                "status": "passed",
                                "command": "python -m unittest",
                                "source": "HEAD",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            comparison = core.environment.compare_trees(source, target)
            evidence = core.validation.index_evidence(root / "runs")

            self.assertEqual(comparison["status"], "different")
            self.assertEqual([item["path"] for item in comparison["changed"]], ["changed.txt"])
            self.assertEqual(evidence["runs"][0]["baseline"], "abc123")
            self.assertEqual(evidence["runs"][0]["results"][0]["command"], "python -m unittest")


if __name__ == "__main__":
    unittest.main()
