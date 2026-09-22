from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path


MODULES = (
    "angular.component_inventory",
    "angular.form_contract_check",
    "angular.generator_preflight",
    "angular.change_impact_report",
    "audit.source_audit_extract",
    "audit.extract_field_contract_matrix",
    "maintenance.cleanup_work_artifacts",
    "maintenance.rewrite_git_history",
    "markdown.guarded_markdown_update",
    "markdown.markdown_semantic_diff",
    "text.tokenizer",
    "validation.validation_evidence_index",
)


class CliSmokeTests(unittest.TestCase):
    def test_every_command_exposes_help_without_side_effects(self) -> None:
        repository = Path(__file__).resolve().parents[1]
        for module in MODULES:
            with self.subTest(module=module):
                result = subprocess.run(
                    [sys.executable, "-m", module, "--help"],
                    cwd=repository,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    check=False,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn("usage:", result.stdout.casefold())


if __name__ == "__main__":
    unittest.main()
