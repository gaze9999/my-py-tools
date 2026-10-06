"""稽核 Windows 開發程序, 只在明確選取及重新核對後終止自己的候選"""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import socket
import time

from maintenance._windows_process import Observation, Process, SafetyError, WindowsBackend


SCHEMA = "my-py-tools.windows-process-audit/1"
MAX_AGE_SECONDS = 900
RELATED = re.compile(r"^(?:python(?:w|\d+(?:\.\d+)?)?|pip\d*|cmd|powershell|pwsh|git(?:-.+)?|"
                     r"bash|sh|conhost|node|uvx?|codex(?:-.+)?)(?:\.exe)?$", re.I)
PROTECTED = re.compile(
    r"codex|(?:^|[\s/\\_.-])mcp(?:$|[\s/\\_.-])|local[-_]documents|local[-_]activity|"
    r"modelcontextprotocol|webview|my_py_tools|mypytools(?:runner)?|launch-(?:gui|web)|"
    r"uvicorn|gunicorn|waitress|http\.server|jupyter|celery|(?:^|[\s-])(?:serve|server|watch)(?:[\s=]|$)|"
    r"-enc(?:odedcommand)?(?:\s|$)|(?:^|\s)(?:ssh|sshd)(?:\s|$)", re.I,
)


def digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8", errors="surrogatepass")).hexdigest()


def command_summary(process: Process) -> str:
    # No denylist can recognize arbitrary credentials, code, URLs or positional secrets.
    # Show the executable's name and mask ALL arguments, including inline shell payloads.
    return f"{process.name} [arguments redacted]" if process.command else "[command unavailable]"


def creation_timestamp(ticks: int) -> str | None:
    if ticks <= 0:
        return None
    try:
        return (datetime(1601, 1, 1, tzinfo=timezone.utc) + timedelta(microseconds=ticks // 10)).isoformat()
    except OverflowError:
        return None


def identity(process: Process) -> dict[str, object]:
    return {"pid": process.pid, "created": process.created, "executable": process.executable,
            "sid": process.sid, "session": process.session,
            "command_sha256": digest(process.command) if process.command else None}


def parent_state(process: Process, processes: dict[int, Process]) -> dict[str, object]:
    if process.ppid == 0:
        return {"status": "none", "pid": 0}
    parent = processes.get(process.ppid)
    if parent is None:
        return {"status": "missing", "pid": process.ppid}
    if not process.created or not parent.created:
        return {"status": "unknown", "pid": process.ppid}
    if parent.created > process.created:
        return {"status": "pid_reused", "pid": process.ppid, "identity": identity(parent)}
    return {"status": "verified", "pid": process.ppid, "identity": identity(parent)}


def relationships(process: Process, processes: dict[int, Process]) -> dict[str, object]:
    chain = []
    seen = {process.pid}
    current = process
    while True:
        parent = parent_state(current, processes)
        chain.append(parent)
        if parent["status"] != "verified":
            break
        pid = int(parent["pid"])
        if pid in seen:
            chain.append({"status": "cycle", "pid": pid})
            break
        seen.add(pid)
        current = processes[pid]
    # Include ambiguous/reused-parent links too: they must not authorize tree cleanup.
    children = [identity(child) for child in processes.values() if child.ppid == process.pid]
    return {"parent_chain": chain, "children": sorted(children, key=lambda row: row["pid"])}


def protected_pids(observation: Observation, actor_pid: int, extra: set[int]) -> set[int]:
    processes = observation.processes
    roots = set(observation.services) | extra | {actor_pid}
    roots.update(pid for pid, process in processes.items()
                 if PROTECTED.search(process.name + " " + (process.command or ""))
                 or process.critical is True or process.session == 0)
    # Propagate raw parent links conservatively, even if their birth time is unavailable.
    protected = set(roots)
    while True:
        added = {pid for pid, process in processes.items() if process.ppid in protected} - protected
        if not added:
            break
        protected.update(added)
    # Protect ancestors themselves, not every unrelated sibling launched by Explorer.
    current = processes.get(actor_pid)
    seen = set()
    while current and current.pid not in seen:
        seen.add(current.pid)
        protected.add(current.pid)
        current = processes.get(current.ppid)
    return protected


def activity(process: Process, before: Process | None) -> dict[str, object]:
    same = before is not None and before.created == process.created and bool(process.created)
    cpu_delta = process.cpu - before.cpu if same and process.cpu is not None and before.cpu is not None else None
    io_delta = process.io - before.io if same and process.io is not None and before.io is not None else None
    if cpu_delta is None or io_delta is None or cpu_delta < 0 or io_delta < 0:
        status = "unknown"
    else:
        status = "observed_activity" if cpu_delta or io_delta else "no_change_in_sample"
    return {"status": status, "cpu_seconds_total": None if process.cpu is None else process.cpu / 10_000_000,
            "io_bytes_total": process.io, "cpu_seconds_delta": None if cpu_delta is None else cpu_delta / 10_000_000,
            "io_bytes_delta": io_delta, "note": "Sampling is not a termination criterion"}


def classify(process: Process, observation: Observation, actor: Process, owned: set[int],
             protected: set[int]) -> tuple[str, list[str]]:
    reasons = []
    relation = relationships(process, observation.processes)
    if process.pid in protected:
        reasons.append("protected_current_tool_codex_mcp_service_or_related_tree")
    if not observation.services_known:
        reasons.append("service_inventory_unavailable")
    if (not process.created or not process.executable or not process.sid or not process.command
            or process.critical is None or process.errors):
        reasons.append("incomplete_identity_or_command_evidence")
    if not actor.sid or process.sid != actor.sid or actor.session <= 0 or process.session != actor.session:
        reasons.append("different_or_unknown_owner_or_session")
    if not RELATED.fullmatch(process.name):
        reasons.append("outside_development_process_scope")
    if relation["children"]:
        reasons.append("has_children_no_recursive_termination")
    if any(parent["status"] in {"unknown", "cycle", "pid_reused"} for parent in relation["parent_chain"]):
        reasons.append("ambiguous_parent_relationship")
    if any(parent["status"] == "verified" and not parent["identity"]["command_sha256"]
           for parent in relation["parent_chain"]):
        reasons.append("ancestor_command_evidence_unavailable")
    if process.pid not in owned:
        reasons.append("no_explicit_work_ownership_declaration")
    if reasons:
        return ("protected" if process.pid in protected else "retain"), reasons
    return "candidate", ["explicit_work_ownership_and_matching_windows_owner_session",
                         "identity_and_relationship_evidence_complete",
                         "parent_absence_and_idle_are_not_authorization"]


def make_audit(observation: Observation, actor_pid: int, owned: set[int], reason: str,
               extra: set[int], before: Observation | None = None) -> dict[str, object]:
    actor = observation.processes.get(actor_pid) or Process(actor_pid, 0, "unknown")
    warnings = list(observation.warnings)
    if not actor.sid or actor.session <= 0:
        warnings.append("Current owner/session unknown; audit only, cleanup disabled")
    protected = protected_pids(observation, actor_pid, extra)
    included = {pid for pid, process in observation.processes.items()
                if RELATED.fullmatch(process.name) or pid in owned or pid in extra}
    for pid in tuple(included):
        included.update(int(row["pid"]) for row in relationships(observation.processes[pid], observation.processes)["parent_chain"]
                        if row["status"] == "verified")
    records = []
    for pid in sorted(included):
        process = observation.processes[pid]
        classification, reasons = classify(process, observation, actor, owned, protected)
        records.append({**identity(process), "name": process.name, "parent_pid": process.ppid,
                        "created_at": creation_timestamp(process.created),
                        "command": command_summary(process), "classification": classification,
                        "reasons": reasons, "relationships": relationships(process, observation.processes),
                        "activity": activity(process, before.processes.get(pid) if before else None)})
    return {"schema": SCHEMA, "captured_at": datetime.now(timezone.utc).isoformat(),
            "host_sha256": digest(socket.gethostname()), "actor_sid": actor.sid, "actor_session": actor.session,
            "owned_pids": sorted(owned), "ownership_reason_sha256": digest(reason) if reason else None,
            "ownership_note": "Caller explicitly declares exclusive work ownership; Windows SID alone is insufficient",
            "protected_pids": sorted(extra), "warnings": warnings, "processes": records}


def load_snapshot(path: Path) -> dict[str, object]:
    if path.stat().st_size > 10 * 1024 * 1024:
        raise SafetyError("Audit snapshot exceeds the size limit")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        if (value.get("schema") != SCHEMA or value.get("host_sha256") != digest(socket.gethostname())
                or not isinstance(value.get("processes"), list)
                or not isinstance(value.get("owned_pids"), list)
                or not isinstance(value.get("protected_pids"), list)):
            raise ValueError
        if (not isinstance(value.get("actor_sid"), str) or not value["actor_sid"]
                or type(value.get("actor_session")) is not int or value["actor_session"] <= 0):
            raise ValueError
        age = (datetime.now(timezone.utc) - datetime.fromisoformat(value["captured_at"])).total_seconds()
        if not 0 <= age <= MAX_AGE_SECONDS:
            raise SafetyError("Audit snapshot expired or has a future timestamp; audit again")
        pids = [row["pid"] for row in value["processes"]]
        if len(set(pids)) != len(pids) or any(type(pid) is not int or pid <= 0 for pid in pids):
            raise ValueError
        for row in value["processes"]:
            for key in ("created", "executable", "sid", "session", "command_sha256", "relationships", "classification"):
                if key not in row:
                    raise ValueError
        if any(type(pid) is not int or pid <= 0 for pid in value["owned_pids"] + value["protected_pids"]):
            raise ValueError
        return value
    except (ValueError, TypeError, KeyError, AttributeError, OverflowError, RecursionError):
        raise SafetyError("Invalid audit snapshot; audit again") from None


def recheck(snapshot: dict[str, object], pid: int, observation: Observation, actor_pid: int,
            extra: set[int]) -> dict[str, object]:
    age = (datetime.now(timezone.utc) - datetime.fromisoformat(snapshot["captured_at"])).total_seconds()
    if not 0 <= age <= MAX_AGE_SECONDS:
        raise SafetyError("Audit snapshot expired during selection; retained")
    actor = observation.processes.get(actor_pid)
    if actor is None or actor.sid != snapshot["actor_sid"] or actor.session != snapshot["actor_session"]:
        raise SafetyError("Current Windows owner/session differs from audit; retained")
    baseline = next((row for row in snapshot["processes"] if row["pid"] == pid), None)
    if (baseline is None or baseline["classification"] != "candidate" or pid not in snapshot["owned_pids"]
            or not snapshot.get("ownership_reason_sha256")):
        raise SafetyError("Selected PID is not an explicitly owned audit candidate; retained")
    process = observation.processes.get(pid)
    if process is None:
        raise SafetyError("Selected PID has exited; no termination attempted")
    if any(baseline[key] != value for key, value in identity(process).items()):
        raise SafetyError("PID, creation time, command, executable or ownership changed; retained")
    if relationships(process, observation.processes) != baseline["relationships"]:
        raise SafetyError("Parent/child relationships changed; retained")
    protected = protected_pids(observation, actor_pid, extra | set(snapshot["protected_pids"]))
    classification, _ = classify(process, observation, actor, set(snapshot["owned_pids"]), protected)
    if classification != "candidate":
        raise SafetyError("Fresh protection/ownership evidence does not allow termination; retained")
    return baseline


def apply_selection(snapshot: dict[str, object], selected: list[int], backend: WindowsBackend,
                    actor_pid: int, extra: set[int], apply: bool) -> tuple[list[dict[str, object]], int]:
    results = []
    for pid in dict.fromkeys(selected):
        handle = None
        try:
            # Check each selection independently, never taskkill /T or a broad PID sweep.
            baseline = recheck(snapshot, pid, backend.collect(), actor_pid, extra)
            if not apply:
                results.append({"pid": pid, "status": "preview_only", "reason": "--apply was not supplied"})
                continue
            handle = backend.open_target(pid)
            backend.verify_handle(handle, baseline)
            # Re-query command/ownership/services/relations while holding the exact process object.
            recheck(snapshot, pid, backend.collect(), actor_pid, extra)
            backend.verify_handle(handle, baseline)
            status = backend.terminate(handle)
            results.append({"pid": pid, "status": status})
        except SafetyError as exc:
            results.append({"pid": pid, "status": "retained", "reason": str(exc)})
        finally:
            if handle is not None:
                backend.close(handle)
    success = {"preview_only", "terminated"}
    return results, 0 if all(row["status"] in success for row in results) else 2


def render(value: dict[str, object], as_json: bool) -> None:
    if as_json:
        print(json.dumps(value, ensure_ascii=False, indent=2))
        return
    for warning in value.get("warnings", []):
        print(f"WARNING: {warning}")
    if "results" in value:
        for row in value["results"]:
            print(f"PID {row['pid']}: {row['status']} {row.get('reason', '')}")
        return
    for row in value["processes"]:
        print(f"PID {row['pid']} <- {row['parent_pid']} {row['name']}: {row['classification']}")
        print(f"  SID {row['sid'] or 'unknown'}, session {row['session']}, created {row['created_at']} (FILETIME {row['created']})")
        print(f"  executable: {row['executable'] or 'unknown'}")
        print(f"  command: {row['command']}, SHA-256: {row['command_sha256'] or 'unknown'}")
        print(f"  activity: {json.dumps(row['activity'])}")
        print(f"  relations: {json.dumps(row['relationships'])}")
        print(f"  reasons: {', '.join(row['reasons'])}")
    print("Audit only. No processes terminated. Idle/parent absence are not cleanup permission.")


def positive_pid(value: str) -> int:
    try:
        pid = int(value)
        if 0 < pid <= 0xFFFFFFFF:
            return pid
    except ValueError:
        pass
    raise argparse.ArgumentTypeError("PID must be a positive 32-bit integer")


def sample_seconds(value: str) -> float:
    try:
        seconds = float(value)
        if math.isfinite(seconds) and 0 <= seconds <= 10:
            return seconds
    except ValueError:
        pass
    raise argparse.ArgumentTypeError("Sample interval must be finite, between 0 and 10 seconds")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="Output redacted JSON")
    parser.add_argument("--output", type=Path, help="Create a NEW redacted audit snapshot; never overwrite")
    parser.add_argument("--sample-seconds", type=sample_seconds, default=1.0, help="Activity sample interval, 0 disables deltas")
    parser.add_argument("--owned-pid", type=positive_pid, action="append", default=[], help="Audit: explicitly declare exclusive work ownership of this PID; repeatable")
    parser.add_argument("--ownership-reason", default="", help="Audit: why these processes belong exclusively to this cleanup; only its hash is recorded")
    parser.add_argument("--protect-pid", type=positive_pid, action="append", default=[], help="Additionally protect this PID and descendants; repeatable")
    parser.add_argument("--snapshot", type=Path, help="Use an audit snapshot no older than 15 minutes")
    parser.add_argument("--pid", type=positive_pid, action="append", default=[], help="Explicitly select a snapshot candidate; repeatable")
    parser.add_argument("--apply", action="store_true", help="Terminate selected verified candidates, never the whole tree")
    args = parser.parse_args(argv)
    if bool(args.snapshot) != bool(args.pid) or (args.apply and not args.snapshot):
        parser.error("--snapshot and explicit --pid are required together; --apply alone is forbidden")
    if args.snapshot and (args.output or args.owned_pid or args.ownership_reason):
        parser.error("Selection cannot add ownership or replace audit evidence")
    if bool(args.owned_pid) != bool(args.ownership_reason.strip()):
        parser.error("--owned-pid requires an explicit --ownership-reason, and vice versa")
    try:
        backend = WindowsBackend()
        extra = set(args.protect_pid)
        if args.snapshot:
            snapshot = load_snapshot(args.snapshot)
            results, code = apply_selection(snapshot, args.pid, backend, os.getpid(), extra, args.apply)
            render({"results": results, "apply": args.apply}, args.json)
            return code
        before = backend.collect() if args.sample_seconds else None
        if before:
            time.sleep(args.sample_seconds)
        observation = backend.collect()
        if set(args.owned_pid) - observation.processes.keys():
            raise SafetyError("An ownership PID is absent; audit again without stale PID declarations")
        value = make_audit(observation, os.getpid(), set(args.owned_pid), args.ownership_reason, extra, before)
        if args.output:
            with args.output.open("x", encoding="utf-8") as stream:
                json.dump(value, stream, ensure_ascii=False, indent=2)
                stream.write("\n")
        render(value, args.json)
        return 0
    except SafetyError as exc:
        print(f"Safety check: {exc}")
        return 2
    except OSError:
        print("Audit I/O failed; no automatic elevation or fallback termination was attempted")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
