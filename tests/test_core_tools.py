from __future__ import annotations

import contextlib
import hashlib
import io
import json
import os
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

from angular.change_impact_report import main as change_impact_main
from angular.component_inventory import main as component_inventory_main
from angular.form_contract_check import main as form_contract_main
from angular.generator_preflight import main as generator_preflight_main
from maintenance.cleanup_work_artifacts import main as cleanup_main
from maintenance.rewrite_git_history import main as rewrite_history_main
from markdown.guarded_markdown_update import main as guarded_markdown_main
from markdown.markdown_semantic_diff import main as markdown_diff_main
from text.tokenizer import main as tokenizer_main
from validation.validation_evidence_index import main as validation_index_main


@contextlib.contextmanager
def captured_output():
    stdout = io.StringIO()
    stderr = io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        yield stdout, stderr


class CoreToolTests(unittest.TestCase):
    def test_angular_inventory_contract_and_generator_tools(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = root / "apps" / "demo"
            component = project / "src" / "demo.component.ts"
            template = project / "src" / "demo.component.html"
            project.joinpath("src").mkdir(parents=True)
            (root / "nx.json").write_text("{}", encoding="utf-8")
            (project / "project.json").write_text(
                json.dumps({"name": "demo", "sourceRoot": "apps/demo/src"}),
                encoding="utf-8",
            )
            component.write_text(
                """@Component({selector: 'app-demo', templateUrl: './demo.component.html'})
export class DemoComponent {
  form = this.fb.group({ customerId: [''] });
}
""",
                encoding="utf-8",
            )
            template.write_text('<input formControlName="customerId">', encoding="utf-8")
            contract = root / "contract.json"
            contract.write_text(
                json.dumps(
                    {
                        "components": [
                            {
                                "source": "apps/demo/src/demo.component.ts",
                                "template": "apps/demo/src/demo.component.html",
                                "controls": ["customerId"],
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )

            with captured_output() as (stdout, _):
                self.assertEqual(component_inventory_main(["--root", str(root), "--json"]), 0)
            self.assertIn('"class_name": "DemoComponent"', stdout.getvalue())

            with captured_output() as (stdout, _):
                self.assertEqual(
                    form_contract_main(["--root", str(root), "--contract", str(contract)]),
                    0,
                )
            self.assertEqual(stdout.getvalue().strip(), "OK")

            with captured_output():
                self.assertEqual(
                    generator_preflight_main(
                        ["--root", str(root), "--identifier", "DemoComponent"]
                    ),
                    1,
                )
                self.assertEqual(
                    generator_preflight_main(
                        [
                            "--root",
                            str(root),
                            "--identifier",
                            "DemoComponent",
                            "--allow-existing",
                        ]
                    ),
                    0,
                )

    def test_git_change_report_reads_untracked_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            subprocess.run(["git", "init", "--quiet", str(root)], check=True)
            (root / "component.ts").write_text("@Input() value = '';", encoding="utf-8")

            with captured_output() as (stdout, _):
                self.assertEqual(change_impact_main(["--root", str(root)]), 0)
            payload = json.loads(stdout.getvalue())
            self.assertEqual(payload["changed_files"][0]["path"], "component.ts")
            self.assertIn("@Input", payload["changed_files"][0]["public_contract_markers"])

    def test_component_inventory_supports_custom_project_roots_and_multiple_components(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = root / "packages" / "widgets"
            project.mkdir(parents=True)
            (root / "nx.json").write_text("{}", encoding="utf-8")
            (project / "project.json").write_text(
                json.dumps({"name": "widgets", "sourceRoot": "packages/widgets"}),
                encoding="utf-8",
            )
            (project / "widgets.ts").write_text(
                """@Component({selector: 'app-one'})
export class OneComponent {}

@Component({selector: 'app-two'})
export class TwoComponent {}
""",
                encoding="utf-8",
            )

            with captured_output() as (stdout, _):
                self.assertEqual(component_inventory_main(["--root", str(root), "--json"]), 0)

            payload = json.loads(stdout.getvalue())
            self.assertEqual(payload["count"], 2)
            self.assertEqual(
                {item["class_name"] for item in payload["components"]},
                {"OneComponent", "TwoComponent"},
            )

    def test_form_contract_reports_missing_template_and_generator_rejects_empty_identifier(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "component.ts"
            source.write_text("form = fb.group({'customerId': fb.control('')});", encoding="utf-8")
            contract = root / "contract.json"
            contract.write_text(
                json.dumps(
                    {
                        "components": [
                            {
                                "source": "component.ts",
                                "template": "missing.html",
                                "controls": ["customerId"],
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )

            with captured_output() as (stdout, _):
                self.assertEqual(form_contract_main(["--root", str(root), "--contract", str(contract), "--json"]), 1)
            findings = json.loads(stdout.getvalue())["findings"]
            self.assertEqual([item["kind"] for item in findings], ["missing-template"])

            with captured_output() as (_, stderr):
                self.assertEqual(generator_preflight_main(["--root", str(root), "--identifier", ""]), 2)
            self.assertIn("must not be empty", stderr.getvalue())

    def test_markdown_tools_support_explicit_files_and_dry_run(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            left = root / "left.md"
            right = root / "right.md"
            replacement = root / "replacement.md"
            left.write_text("# A\n\n- old\n", encoding="utf-8")
            right.write_text("# A\n\n- new\n", encoding="utf-8")
            replacement.write_text("# A\n\n- replacement\n", encoding="utf-8")

            with captured_output() as (stdout, _):
                self.assertEqual(
                    markdown_diff_main(["--left", str(left), "--right", str(right)]),
                    0,
                )
            self.assertIn("only_left", stdout.getvalue())

            before = left.read_bytes()
            expected = hashlib.sha256(before).hexdigest()
            with captured_output() as (stdout, _):
                self.assertEqual(
                    guarded_markdown_main(
                        [
                            "--target-file",
                            str(left),
                            "replace",
                            "context",
                            "--content",
                            str(replacement),
                            "--expect",
                            expected,
                            "--section",
                            "# A",
                        ]
                    ),
                    0,
                )
            self.assertEqual(json.loads(stdout.getvalue())["status"], "dry-run")
            self.assertEqual(left.read_bytes(), before)

    def test_markdown_diff_ignores_fences_and_reports_duplicate_or_order_changes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            left = root / "left.md"
            right = root / "right.md"
            left.write_text("# A\n\n- first\n- second\n- second\n```md\n# ignored\n```\n", encoding="utf-8")
            right.write_text("# A\n\n- second\n- first\n```md\n# different ignored\n```\n", encoding="utf-8")

            with captured_output() as (stdout, _):
                self.assertEqual(markdown_diff_main(["--left", str(left), "--right", str(right)]), 0)

            changes = json.loads(stdout.getvalue())["changes"]
            self.assertEqual(changes["headings"]["only_left"], [])
            self.assertEqual(changes["list_items"]["only_left"], ["- second"])

    def test_tokenizer_validation_index_and_cleanup_preview(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with captured_output() as (stdout, _):
                self.assertEqual(
                    tokenizer_main(["--text", "測試 text", "--encoding", "missing-encoding", "--json"]),
                    0,
                )
            self.assertEqual(json.loads(stdout.getvalue())["method"], "fallback")

            result_dir = root / "run-001"
            result_dir.mkdir()
            result_dir.joinpath("results.json").write_text(
                json.dumps(
                    {
                        "started": "2026-09-22T00:00:00Z",
                        "results": [{"name": "typecheck", "status": "passed"}],
                    }
                ),
                encoding="utf-8",
            )
            with captured_output() as (stdout, _):
                self.assertEqual(validation_index_main(["--root", str(root)]), 0)
            self.assertIn("run-001", stdout.getvalue())

            cache = root / "project" / "__pycache__"
            cache.mkdir(parents=True)
            cache.joinpath("sample.pyc").write_bytes(b"cache")
            output = root / "cleanup-output"
            with captured_output() as (stdout, _):
                self.assertEqual(
                    cleanup_main(
                        [
                            "--root",
                            str(root / "project"),
                            "--min-age-days",
                            "0",
                            "--output-dir",
                            str(output),
                        ]
                    ),
                    0,
                )
            self.assertIn('"mode": "preview"', stdout.getvalue())
            self.assertTrue(cache.is_dir())

    def test_validation_index_keeps_valid_runs_when_one_schema_is_invalid(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            valid = root / "run-002"
            invalid = root / "run-001"
            valid.mkdir()
            invalid.mkdir()
            valid.joinpath("results.json").write_text(
                json.dumps({"results": [{"name": "test", "status": "passed"}]}),
                encoding="utf-8",
            )
            invalid.joinpath("results.json").write_text(
                json.dumps({"results": ["invalid"]}),
                encoding="utf-8",
            )

            with captured_output() as (stdout, _):
                self.assertEqual(validation_index_main(["--root", str(root)]), 1)

            payload = json.loads(stdout.getvalue())
            self.assertEqual([item["run"] for item in payload["runs"]], ["run-002"])
            self.assertEqual([item["run"] for item in payload["errors"]], ["run-001"])

    def test_cleanup_preserves_unowned_quarantine_and_nested_worktree(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "cleanup-output"
            unrelated = output / "quarantine" / "personal-backup"
            unrelated.mkdir(parents=True)
            unrelated.joinpath("keep.txt").write_text("keep", encoding="utf-8")

            with captured_output():
                self.assertEqual(
                    cleanup_main(
                        [
                            "--output-dir",
                            str(output),
                            "--purge-quarantine",
                            "--older-than-days",
                            "0",
                        ]
                    ),
                    0,
                )
            self.assertTrue(unrelated.is_dir())

            nested_worktree = root / "project" / "tmp"
            nested_worktree.mkdir(parents=True)
            nested_worktree.joinpath(".git").write_text("gitdir: elsewhere", encoding="utf-8")
            old = 1_600_000_000
            os.utime(nested_worktree, (old, old))
            with captured_output() as (stdout, _):
                self.assertEqual(
                    cleanup_main(
                        [
                            "--root",
                            str(root / "project"),
                            "--include-work-dirs",
                            "--min-age-days",
                            "0",
                            "--output-dir",
                            str(output),
                        ]
                    ),
                    0,
                )
            self.assertEqual(json.loads(stdout.getvalue().split("Manifest:", 1)[0])["candidate_count"], 0)

    def test_cleanup_purges_only_owned_quarantine_runs(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = root / "project"
            cache = project / "__pycache__"
            cache.mkdir(parents=True)
            cache.joinpath("sample.pyc").write_bytes(b"cache")
            output = root / "cleanup-output"

            with captured_output():
                self.assertEqual(
                    cleanup_main(
                        [
                            "--root",
                            str(project),
                            "--min-age-days",
                            "0",
                            "--output-dir",
                            str(output),
                            "--apply",
                        ]
                    ),
                    0,
                )
            runs = list((output / "quarantine").glob("cache-cleanup-*"))
            self.assertEqual(len(runs), 1)
            self.assertTrue(runs[0].joinpath(".my-py-tools-quarantine.json").is_file())

            with captured_output() as (stdout, _):
                self.assertEqual(
                    cleanup_main(
                        [
                            "--output-dir",
                            str(output),
                            "--purge-quarantine",
                            "--older-than-days",
                            "0",
                        ]
                    ),
                    0,
                )
            self.assertEqual(json.loads(stdout.getvalue())["removed_runs"], 1)
            self.assertFalse(runs[0].exists())

    def test_history_rewrite_cancel_does_not_modify_repository(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            subprocess.run(["git", "init", "--quiet", str(root)], check=True)
            subprocess.run(["git", "-C", str(root), "config", "user.name", "Test User"], check=True)
            subprocess.run(["git", "-C", str(root), "config", "user.email", "test@example.com"], check=True)

            with patch("builtins.input", return_value="CANCEL"), captured_output():
                self.assertEqual(rewrite_history_main(["--repo", str(root)]), 0)

            self.assertFalse((root / ".bundle").exists())
            exclude = root / ".git" / "info" / "exclude"
            if exclude.is_file():
                self.assertNotIn("git-history-rewrite-helper", exclude.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
