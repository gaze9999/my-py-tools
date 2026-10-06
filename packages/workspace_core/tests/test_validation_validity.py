"""Check evidence freshness independently from the installed runtime or test status."""
import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location("validation_source", Path(__file__).resolve().parents[1] / "my_py_workspace_core/validation.py")
validation = importlib.util.module_from_spec(spec)
spec.loader.exec_module(validation)


class ValidityChecks(unittest.TestCase):
    def setUp(self):
        self.recorded = {"source_files": {"src/a.py": "a" * 64}, "covered_paths": ["src/a.py"], "artifact_sha256": "b" * 64}
        self.current = {"source_files": {"src/a.py": "a" * 64}, "affected_paths": ["src/a.py"], "artifact_sha256": "b" * 64}

    def test_current_scoped_source(self):
        self.assertEqual(validation.assess_evidence(self.recorded, self.current)["status"], "current")

    def test_changed_source_and_artifact_are_outdated(self):
        for changed in ({"source_files": {"src/a.py": "c" * 64}}, {"artifact_sha256": "c" * 64}):
            with self.subTest(changed=changed):
                self.assertEqual(validation.assess_evidence(self.recorded, {**self.current, **changed})["status"], "outdated")

    def test_uncovered_path_is_partial(self):
        result = validation.assess_evidence(self.recorded, {**self.current, "affected_paths": ["src/a.py", "src/b.py"]})
        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["uncovered_paths"], ["src/b.py"])

    def test_missing_hash_is_not_promoted(self):
        self.assertEqual(validation.assess_evidence(self.recorded, {**self.current, "source_files": {}})["status"], "unverified")

    def test_timestamp_does_not_prove_current_source(self):
        self.assertEqual(validation.assess_evidence({"timestamp": "2026-10-06"}, self.current)["status"], "unverified")

    def test_coverage_without_source_hash_is_partial(self):
        recorded = {**self.recorded, "covered_paths": ["src/a.py", "src/b.py"]}
        current = {**self.current, "affected_paths": ["src/a.py", "src/b.py"]}
        self.assertEqual(validation.assess_evidence(recorded, current)["status"], "partial")

    def test_global_source_change_is_outdated(self):
        recorded = {"source_revision": "a" * 40, "source_diff_sha256": "b" * 64}
        self.assertEqual(validation.assess_evidence(recorded, {**recorded, "source_diff_sha256": "c" * 64})["status"], "outdated")

    def test_revision_and_diff_need_both(self):
        self.assertEqual(validation.assess_evidence({"source_revision": "a" * 40}, {"source_revision": "a" * 40})["status"], "unverified")
        recorded = {"source_revision": "a" * 40, "source_diff_sha256": "b" * 64, "covered_paths": ["src/a.py"]}
        current = {**recorded, "affected_paths": ["src/a.py"]}
        self.assertEqual(validation.assess_evidence(recorded, current)["status"], "current")

    def test_bad_current_baseline_is_rejected(self):
        with self.assertRaises(ValueError):
            validation.assess_evidence(self.recorded, {"artifact_sha256": 123})

    def test_bad_historical_baseline_is_unverified(self):
        self.assertEqual(validation.assess_evidence({"source_files": []}, self.current)["status"], "unverified")


if __name__ == "__main__":
    unittest.main()
