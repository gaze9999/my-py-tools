#!/usr/bin/env python3
"""Guarded Markdown section edits; no network or remote-service credentials. See --help."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile


from tool_config import ToolConfig

TARGETS = ("context", "progress", "history")


def sha(data):
    return hashlib.sha256(data).hexdigest()


def headings(text):
    """ATX headings outside fenced code; offsets preserve unrelated bytes."""
    result, offset, fence = [], 0, None
    for line in text.splitlines(keepends=True):
        marker = re.match(r"^ {0,3}(`{3,}|~{3,})(.*)$", line.rstrip("\r\n"))
        if marker:
            run, tail = marker.groups()
            if fence is None:
                fence = (run[0], len(run))
            elif run[0] == fence[0] and len(run) >= fence[1] and not tail.strip():
                fence = None
        elif fence is None:
            match = re.match(r"^(#{1,6})[ \t]+(.+?)[ \t]*$", line.rstrip("\r\n"))
            if match:
                title = re.sub(r"[ \t]+#+$", "", match[2])
                result.append((len(match[1]), title, offset))
        offset += len(line)
    return result


def section(text, heading):
    found = headings(text)
    matches = [(i, h) for i, h in enumerate(found) if "#" * h[0] + " " + h[1] == heading]
    if len(matches) != 1:
        raise ValueError("Section heading must match exactly once; inspect headings first")
    index, (level, _, start) = matches[0]
    end = next((h[2] for h in found[index + 1:] if h[0] <= level), len(text))
    return start, end


def read_target(path):
    raw = path.read_bytes()
    bom = raw.startswith(b"\xef\xbb\xbf")
    return raw, raw.decode("utf-8-sig"), bom


def prepare(raw, text, bom, content, heading=None, entry_id=None, namespace=None):
    if namespace is None:
        namespace = "project-task"
    nl = "\r\n" if "\r\n" in text else "\n"
    content = content.replace("\r\n", "\n").replace("\r", "\n").strip() + "\n"
    if not content.strip():
        raise ValueError("Empty content is not allowed")
    if heading:
        start, end = section(text, heading)
        hs = headings(content)
        if not hs or hs[0][2] != 0 or "#" * hs[0][0] + " " + hs[0][1] != heading:
            raise ValueError("Replacement must start with the exact section heading")
        if any(h[0] <= hs[0][0] for h in hs[1:]):
            raise ValueError("Replacement must contain only the selected section")
        replacement = content.replace("\n", nl) + (nl if end < len(text) else "")
        output = text[:start] + replacement + text[end:]
    else:
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,100}", entry_id or ""):
            raise ValueError("entry-id must be 1-101 ASCII letters/digits/dots/dashes/underscores")
        if re.search(r"<!-- /?[A-Za-z0-9._-]+:", content):
            raise ValueError("Content must not supply task markers")
        # 舊紀錄保留原標記，切換設定時仍檢查既有識別碼
        existing = re.findall(r"<!-- ([A-Za-z0-9._-]+):" + re.escape(entry_id) + r" -->", text)
        if len(existing) > 1:
            raise ValueError("entry-id occurs more than once; inspect history")
        if existing:
            namespace = existing[0]
        marker = f"<!-- {namespace}:{entry_id} -->"
        close = f"<!-- /{namespace}:{entry_id} -->"
        block = marker + nl + content.replace("\n", nl) + close + nl
        if marker in text:
            if text.count(marker) == 1 and text.count(close) == 1 and block in text:
                return raw
            raise ValueError("entry-id already exists with different content; do not duplicate it")
        gap = "" if not text or text.endswith(nl + nl) else (nl if text.endswith(nl) else nl + nl)
        output = text + gap + block
    return (b"\xef\xbb\xbf" if bom else b"") + output.encode("utf-8")


def write_in_place(path, before, after):
    """Explicit fallback for cloud placeholders; retain backup on any failure."""
    with tempfile.NamedTemporaryFile(prefix=path.name + ".backup-", dir=path.parent, delete=False) as handle:
        backup = Path(handle.name)
        handle.write(before)
        handle.flush()
        os.fsync(handle.fileno())
    try:
        with path.open("r+b") as handle:
            if handle.read() != before:
                raise ValueError("Target changed; re-inspect and merge")
            handle.seek(0)
            handle.write(after)
            handle.truncate()
            handle.flush()
            os.fsync(handle.fileno())
        if path.read_bytes() != after:
            raise ValueError("Post-write mismatch")
    except (OSError, ValueError) as exc:
        raise ValueError(f"In-place write unverified; inspect target before retry. Backup: {backup}; {exc}") from exc
    backup.unlink()


def write_guarded(path, before, after, in_place=False):
    """Optimistic guard, atomic single-file replacement, then exact readback."""
    if in_place:
        write_in_place(path, before, after)
        return
    temp = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as handle:
            temp = Path(handle.name)
            handle.write(after)
            handle.flush()
            os.fsync(handle.fileno())
        if path.read_bytes() != before:
            raise ValueError("Target changed during preparation; re-inspect and merge")
        os.replace(temp, path)
        temp = None
        if path.read_bytes() != after:
            raise ValueError("Post-write mismatch: write may have occurred; inspect before retry")
    finally:
        if temp is not None:
            temp.unlink(missing_ok=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, help="Project .env; place before subcommand")
    sub = parser.add_subparsers(dest="command", required=True)
    inspect = sub.add_parser("inspect", help="Emit SHA and headings, or one full section")
    inspect.add_argument("target", choices=TARGETS)
    inspect.add_argument("--section", help="Exact heading including ##")
    inspect.add_argument("--out", type=Path, help="Export section to a NEW UTF-8 file; omit full content in stdout")
    for name in ("replace", "append"):
        p = sub.add_parser(name, help="Dry-run by default; --write commits one local target")
        p.add_argument("target", choices=("history",) if name == "append" else ("context", "progress"))
        p.add_argument("--content", type=Path, required=True, help="UTF-8 Markdown content file")
        p.add_argument("--expect", required=True, help="Current target SHA-256 from inspect")
        p.add_argument("--write", action="store_true")
        p.add_argument("--in-place", action="store_true", help="Explicit cloud-file fallback: backup, guarded non-atomic write, readback")
        p.add_argument("--entry-id" if name == "append" else "--section", required=True)
    args = parser.parse_args(argv)
    try:
        settings = ToolConfig(args.env_file)
        path = settings.path(f"TOOL_{args.target.upper()}_FILE")
        configured = [settings.path(f"TOOL_{target.upper()}_FILE") for target in TARGETS
                      if settings.values.get(f"TOOL_{target.upper()}_FILE")]
        if len(configured) != len(set(configured)):
            raise ValueError("Document target paths must be distinct")
        raw, text, bom = read_target(path)
        payload = {"target": args.target, "sha256": sha(raw)}
        if args.command == "inspect":
            if args.out and not args.section:
                raise ValueError("--out requires --section")
            if args.section:
                start, end = section(text, args.section)
                selected = text[start:end]
                if args.out:
                    with args.out.open("x", encoding="utf-8", newline="") as handle:
                        handle.write(selected)
                    payload["exported"] = str(args.out)
                else:
                    payload["content"] = selected
            else:
                payload["headings"] = ["#" * h[0] + " " + h[1] for h in headings(text)]
        else:
            if args.expect.lower() != sha(raw):
                raise ValueError("Stale SHA-256: re-inspect and merge before writing")
            after = prepare(raw, text, bom, args.content.read_text(encoding="utf-8-sig"),
                            getattr(args, "section", None), getattr(args, "entry_id", None),
                            settings.namespace())
            changed = raw != after
            if args.write and changed:
                write_guarded(path, raw, after, args.in_place)
            payload.update(status="written" if args.write and changed else ("unchanged" if not changed else "dry-run"),
                           next_sha256=sha(after), byte_delta=len(after) - len(raw),
                           notion="not_performed")
        print(json.dumps(payload, ensure_ascii=False))
        return 0
    except (OSError, UnicodeError, ValueError) as exc:
        print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    sys.exit(main())
