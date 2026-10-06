from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace

from maintenance._windows_process import Observation, Process, SafetyError, WindowsBackend
from maintenance.windows_process_audit import (
    activity, apply_selection, command_summary, load_snapshot, main, make_audit,
    parent_state, recheck,
)


ACTOR = Process(100, 0, "python.exe", 1000, "C:/python.exe", "S-1-test", 1,
                "python audit.py", 0, 0, False)
PARENT = Process(200, 0, "cmd.exe", 2000, "C:/cmd.exe", "S-1-test", 1,
                 "cmd /c python job.py", 0, 0, False)
WORKER = Process(300, 200, "python.exe", 3000, "C:/python.exe", "S-1-test", 1,
                 "python job.py --token SUPER_SECRET positional-secret", 0, 0, False)


def observation(*processes: Process, known: bool = True, services: set[int] | None = None) -> Observation:
    return Observation({process.pid: process for process in (ACTOR, PARENT, WORKER, *processes)},
                       services or set(), known)


def audit(view: Observation | None = None, owned: bool = True) -> dict:
    return make_audit(view or observation(), ACTOR.pid, {WORKER.pid} if owned else set(),
                      "my exclusive disposable worker" if owned else "", set())


def worker_row(value: dict) -> dict:
    return next(row for row in value["processes"] if row["pid"] == WORKER.pid)


class FakeBackend:
    def __init__(self, views: list[Observation] | None = None, fail_handle: bool = False) -> None:
        self.views = iter(views or [observation(), observation()])
        self.fail_handle = fail_handle
        self.calls = []

    def collect(self):
        self.calls.append("collect")
        return next(self.views)

    def open_target(self, pid):
        self.calls.append("open")
        return 777

    def verify_handle(self, handle, expected):
        self.calls.append("verify")
        if self.fail_handle:
            raise SafetyError("Handle identity changed; retained")

    def terminate(self, handle):
        self.calls.append("terminate")
        return "terminated"

    def close(self, handle):
        self.calls.append("close")


class ProcessAuditTests(unittest.TestCase):
    def test_default_audit_has_no_candidates(self):
        self.assertTrue(all(row["classification"] != "candidate" for row in audit(owned=False)["processes"]))

    def test_owned_complete_leaf_is_candidate_even_with_observed_activity(self):
        view = observation(replace(WORKER, cpu=100, io=400))
        value = make_audit(view, 100, {300}, "exclusive worker", set(), observation())
        self.assertEqual(worker_row(value)["classification"], "candidate")
        self.assertEqual(worker_row(value)["activity"]["status"], "observed_activity")

    def test_idle_and_missing_parent_are_not_permission(self):
        view = observation(replace(WORKER, ppid=999))
        row = worker_row(audit(view, owned=False))
        self.assertEqual(row["classification"], "retain")
        self.assertEqual(row["relationships"]["parent_chain"][0]["status"], "missing")

    def test_redacts_every_argument_and_freeform_reason(self):
        value = make_audit(observation(), 100, {300}, "token=OWNERSHIP_SECRET", set())
        text = json.dumps(value)
        for secret in ("SUPER_SECRET", "positional-secret", "OWNERSHIP_SECRET", "--token"):
            self.assertNotIn(secret, text)
        self.assertIn("arguments redacted", text)
        self.assertEqual(command_summary(replace(WORKER, command=None)), "[command unavailable]")

    def test_related_scope_includes_versioned_python_and_git_helper(self):
        for name in ("python3.14.exe", "pythonw.exe", "git-remote-https.exe", "pwsh.exe", "uvx.exe"):
            with self.subTest(name=name):
                self.assertEqual(worker_row(audit(observation(replace(WORKER, name=name))))["classification"], "candidate")

    def test_unknown_owner_session_command_or_critical_retains(self):
        for change in ({"sid": "other"}, {"sid": ""}, {"session": 2}, {"session": 0},
                       {"command": None}, {"critical": None}, {"created": 0}, {"executable": ""}):
            with self.subTest(change=change):
                self.assertNotEqual(worker_row(audit(observation(replace(WORKER, **change))))["classification"], "candidate")

    def test_unknown_services_retains_all(self):
        self.assertEqual(worker_row(audit(observation(known=False)))["classification"], "retain")

    def test_unknown_actor_owner_still_audits_but_cannot_authorize_cleanup(self):
        value = audit(observation(replace(ACTOR, sid="", session=-1)))
        self.assertTrue(value["warnings"])
        self.assertEqual(worker_row(value)["classification"], "retain")

    def test_service_codex_mcp_watch_and_encoded_shell_protect_descendants(self):
        for command in ("codex exec", "python -m local_documents_mcp", "node mcp-server", "uvicorn app:app",
                        "python -m http.server", "powershell -EncodedCommand private", "npm run watch"):
            with self.subTest(command=command):
                value = audit(observation(replace(PARENT, command=command)))
                self.assertEqual(worker_row(value)["classification"], "protected")
        self.assertEqual(worker_row(audit(observation(services={200})))["classification"], "protected")

    def test_self_ancestors_and_current_tool_children_protected(self):
        value = make_audit(observation(replace(WORKER, ppid=100)), 100, {100, 200, 300}, "mine", set())
        self.assertEqual(worker_row(value)["classification"], "protected")
        self.assertEqual(next(row for row in value["processes"] if row["pid"] == 100)["classification"], "protected")
        value = make_audit(observation(replace(ACTOR, ppid=200)), 100, {200}, "mine", set())
        self.assertEqual(next(row for row in value["processes"] if row["pid"] == 200)["classification"], "protected")

    def test_extra_protection_is_preserved_from_snapshot(self):
        view = observation()
        baseline = audit()
        baseline["protected_pids"] = [200]
        with self.assertRaises(SafetyError):
            recheck(baseline, 300, view, 100, set())

    def test_children_or_ambiguous_parent_retain(self):
        child = replace(WORKER, pid=400, ppid=300, created=4000)
        self.assertEqual(worker_row(audit(observation(child)))["classification"], "retain")
        for change in ({"created": 5000}, {"created": 0}, {"command": None}, {"ppid": 300}):
            with self.subTest(change=change):
                self.assertEqual(worker_row(audit(observation(replace(PARENT, **change))))["classification"], "retain")
        self.assertEqual(parent_state(WORKER, observation(replace(PARENT, created=5000)).processes)["status"], "pid_reused")

    def test_activity_missing_reused_or_negative_counters_unknown(self):
        for previous in (None, replace(WORKER, created=1), replace(WORKER, io=None), replace(WORKER, cpu=99)):
            self.assertEqual(activity(WORKER, previous)["status"], "unknown")
        self.assertEqual(activity(WORKER, WORKER)["status"], "no_change_in_sample")

    def test_recheck_identity_change_refuses_every_field(self):
        baseline = audit()
        for change in ({"created": 9999}, {"command": "changed"}, {"executable": "different"},
                       {"sid": "different"}, {"session": 5}):
            with self.subTest(change=change), self.assertRaises(SafetyError):
                recheck(baseline, 300, observation(replace(WORKER, **change)), 100, set())

    def test_recheck_parent_child_service_and_owner_changes(self):
        baseline = audit()
        child = replace(WORKER, pid=400, ppid=300, created=4000)
        for view in (observation(replace(PARENT, command="changed")), observation(replace(PARENT, created=1)),
                     observation(child), observation(services={300}), observation(replace(ACTOR, session=2))):
            with self.subTest(view=view), self.assertRaises(SafetyError):
                recheck(baseline, 300, view, 100, set())

    def test_no_apply_never_opens_termination_handle(self):
        backend = FakeBackend()
        results, code = apply_selection(audit(), [300], backend, 100, set(), False)
        self.assertEqual(code, 0)
        self.assertEqual(results[0]["status"], "preview_only")
        self.assertEqual(backend.calls, ["collect"])

    def test_apply_order_and_exact_handle_cleanup(self):
        backend = FakeBackend()
        results, code = apply_selection(audit(), [300, 300], backend, 100, set(), True)
        self.assertEqual(code, 0)
        self.assertEqual(results[0]["status"], "terminated")
        self.assertEqual(backend.calls, ["collect", "open", "verify", "collect", "verify", "terminate", "close"])

    def test_change_after_open_or_wrong_handle_never_terminates(self):
        for backend in (FakeBackend([observation(), observation(replace(WORKER, command="changed"))]),
                        FakeBackend(fail_handle=True)):
            results, code = apply_selection(audit(), [300], backend, 100, set(), True)
            self.assertEqual(code, 2)
            self.assertEqual(results[0]["status"], "retained")
            self.assertNotIn("terminate", backend.calls)
            self.assertEqual(backend.calls[-1], "close")

    def test_apply_rejects_unclaimed_notcandidate_or_absent(self):
        for value, pid in ((audit(owned=False), 300), (audit(), 12345), (audit(), 100)):
            results, code = apply_selection(value, [pid], FakeBackend(), 100, set(), True)
            self.assertEqual(code, 2)
            self.assertEqual(results[0]["status"], "retained")

    def test_snapshot_schema_expiry_duplicates_and_host_guard(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory, "audit.json")
            value = audit()
            path.write_text(json.dumps(value), encoding="utf-8")
            self.assertEqual(load_snapshot(path), value)
            for change in ({"schema": "unknown"}, {"host_sha256": "elsewhere"}, {"owned_pids": [True]},
                           {"processes": value["processes"] * 2}, {"processes": [{}]},
                           {"captured_at": datetime.now(timezone.utc).replace(tzinfo=None).isoformat()},
                           {"captured_at": (datetime.now(timezone.utc) - timedelta(minutes=16)).isoformat()},
                           {"captured_at": (datetime.now(timezone.utc) + timedelta(minutes=1)).isoformat()}):
                with self.subTest(change=change):
                    path.write_text(json.dumps({**value, **change}), encoding="utf-8")
                    with self.assertRaises(SafetyError):
                        load_snapshot(path)

    def test_expiry_during_batch_keeps_process(self):
        value = audit()
        value["captured_at"] = (datetime.now(timezone.utc) - timedelta(minutes=16)).isoformat()
        with self.assertRaises(SafetyError):
            recheck(value, 300, observation(), 100, set())

    @unittest.skipUnless(os.name == "nt", "Windows collector adapter")
    def test_collector_failure_invalid_bytes_and_bad_evidence_use_native_fallback(self):
        for result in (SimpleNamespace(returncode=1, stdout=b"", stderr=b"\xa5PRIVATE_ERROR"),
                       SimpleNamespace(returncode=0, stdout=b"\xa5PRIVATE_ERROR"),
                       SimpleNamespace(returncode=0, stdout=b'{"rows":[{"pid":300,"created":"bad"}],"services_known":true}')):
            with self.subTest(result=result), patch("maintenance._windows_process.WindowsApi") as api, \
                    patch("maintenance._windows_process.subprocess.run", return_value=result), \
                    patch("sys.stderr", new_callable=io.StringIO) as errors:
                api.return_value.enumerate.return_value = observation().processes
                view = WindowsBackend().collect()
                self.assertFalse(view.services_known)
                self.assertTrue(view.warnings)
                self.assertIsNone(view.processes[300].command)
                self.assertEqual(worker_row(audit(view))["classification"], "retain")
                self.assertNotIn("PRIVATE_ERROR", errors.getvalue())

    @unittest.skipUnless(os.name == "nt", "Windows collector adapter")
    def test_cim_pid_reuse_never_attaches_another_command(self):
        result = SimpleNamespace(returncode=0, stdout=json.dumps({"rows": [
            {"pid": 300, "created": "9999", "command": "not this process"}],
            "services": [], "services_known": True}).encode())
        with patch("maintenance._windows_process.WindowsApi") as api, \
                patch("maintenance._windows_process.subprocess.run", return_value=result):
            api.return_value.enumerate.return_value = observation().processes
            view = WindowsBackend().collect()
            self.assertIsNone(view.processes[300].command)

    def test_partial_results_and_unconfirmed_exit_do_not_claim_success(self):
        backend = FakeBackend([observation(), observation(), observation()])
        with patch.object(backend, "terminate", return_value="termination_requested_exit_unconfirmed"):
            results, code = apply_selection(audit(), [300, 999], backend, 100, set(), True)
        self.assertEqual(code, 2)
        self.assertEqual([row["status"] for row in results], ["termination_requested_exit_unconfirmed", "retained"])

    def test_cli_invalid_apply_selection_and_sample_are_rejected_before_collection(self):
        for arguments in (["--apply"], ["--pid", "300"], ["--snapshot", "audit.json"],
                          ["--owned-pid", "300"], ["--ownership-reason", "mine"],
                          ["--sample-seconds", "nan"], ["--sample-seconds", "-1"], ["--pid", "0"],
                          ["--snapshot", "audit.json", "--pid", "300", "--owned-pid", "300"]):
            with self.subTest(arguments=arguments), patch("sys.stderr", new_callable=io.StringIO), \
                    patch("maintenance.windows_process_audit.WindowsBackend") as backend:
                with self.assertRaises(SystemExit) as result:
                    main(arguments)
                self.assertEqual(result.exception.code, 2)
                backend.assert_not_called()

    def test_audit_output_never_overwrites_existing_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory, "audit.json")
            path.write_text("keep me", encoding="utf-8")
            with patch("maintenance.windows_process_audit.WindowsBackend") as backend, \
                    patch("maintenance.windows_process_audit.os.getpid", return_value=100), \
                    patch("sys.stdout", new_callable=io.StringIO):
                backend.return_value.collect.return_value = observation()
                self.assertEqual(main(["--output", str(path), "--sample-seconds", "0"]), 2)
                backend.return_value.terminate.assert_not_called()
            self.assertEqual(path.read_text(encoding="utf-8"), "keep me")

    def test_windows_only_backend_fails_closed_elsewhere(self):
        with patch("maintenance._windows_process.os.name", "posix"):
            with self.assertRaises(SafetyError):
                WindowsBackend()

    def test_catalog_exposes_tool_and_english_purpose(self):
        from gui.catalog import TOOLS_BY_ID
        tool = TOOLS_BY_ID["windows-process-audit"]
        self.assertEqual(tool.category, "維護")
        self.assertEqual(tool.module, "maintenance.windows_process_audit")
        self.assertIn("Windows", tool.payload()["requirements"])
        self.assertTrue(tool.translations["en"]["purpose"])


@unittest.skipUnless(os.name == "nt" and os.environ.get("MY_PY_TOOLS_PROCESS_LIVE_TEST") == "1",
                     "Explicit opt-in required; real termination uses only this test's isolated worker")
class IsolatedWindowsProcessTests(unittest.TestCase):
    def test_native_audit_preview_and_handle_bound_termination_of_own_worker(self):
        backend = WindowsBackend()
        handle = None
        pid = None
        with tempfile.TemporaryDirectory(prefix="my-py-process-test-") as directory:
            script = Path(directory, "disposable_worker.py")
            script.write_text("import time\ntime.sleep(180)\n", encoding="utf-8")
            # A short-lived bootstrap owns the child. Its deliberate exit detaches ONLY
            # our worker from the agent/test tree, without touching any existing process.
            bootstrap = (
                "import subprocess,sys; p=subprocess.Popen([getattr(sys,'_base_executable',sys.executable),sys.argv[1]],"
                "stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,"
                "creationflags=subprocess.DETACHED_PROCESS|subprocess.CREATE_NEW_PROCESS_GROUP); print(p.pid)"
            )
            result = subprocess.run([sys.executable, "-c", bootstrap, str(script)],
                                    capture_output=True, encoding="utf-8", timeout=15, check=True)
            pid = int(result.stdout.strip())
            try:
                handle = backend.open_target(pid)
                handle_identity = backend.api.identity(handle)
                view = backend.collect()
                self.assertIn(pid, view.processes)
                self.assertIn(str(script), view.processes[pid].command)
                self.assertEqual(view.processes[pid].created, handle_identity["created"])
                default_audit = make_audit(view, os.getpid(), set(), "", set())
                self.assertNotEqual(next(row for row in default_audit["processes"] if row["pid"] == pid)["classification"], "candidate")
                value = make_audit(view, os.getpid(), {pid}, "exclusive isolated unittest worker", set())
                row = next(row for row in value["processes"] if row["pid"] == pid)
                self.assertEqual(row["classification"], "candidate", row["reasons"])
                self.assertEqual(row["relationships"]["parent_chain"][0]["status"], "missing")
                preview, code = apply_selection(value, [pid], backend, os.getpid(), set(), False)
                self.assertEqual(code, 0, preview)
                self.assertEqual(backend.api.kernel.WaitForSingleObject(handle, 0), 258)
                results, code = apply_selection(value, [pid], backend, os.getpid(), set(), True)
                self.assertEqual(code, 0, results)
                self.assertEqual(results[0]["status"], "terminated")
                self.assertEqual(backend.api.kernel.WaitForSingleObject(handle, 0), 0)
            finally:
                if handle is not None:
                    # Exact held handle was obtained from the child we just created,
                    # never an arbitrary existing PID or taskkill tree.
                    if backend.api.kernel.WaitForSingleObject(handle, 0) == 258:
                        backend.api.kernel.TerminateProcess(handle, 1)
                        backend.api.kernel.WaitForSingleObject(handle, 5000)
                    backend.close(handle)


if __name__ == "__main__":
    unittest.main()
