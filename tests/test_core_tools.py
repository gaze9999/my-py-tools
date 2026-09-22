from __future__ import annotations

import contextlib
import hashlib
import io
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from angular.change_impact_report import main as change_impact_main
from angular.component_inventory import main as component_inventory_main
from angular.form_contract_check import main as form_contract_main
from angular.generator_preflight import main as generator_preflight_main
from maintenance.cleanup_work_artifacts import main as cleanup_main
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


if __name__ == "__main__":
    unittest.main()
