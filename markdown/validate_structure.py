#!/usr/bin/env python3
"""Bounded Markdown structure checks; not a complete Markdown parser."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
FENCE_RE = re.compile(r"^\s*(`{3,}|~{3,})")
VERSION_RE = re.compile(r"文件版本\s*[:：]\s*v\d+\b", re.IGNORECASE)


def analyze(text: str) -> dict:
    """Return bounded ATX/fence checks without reading or changing files."""
    if not isinstance(text, str):
        raise TypeError("text must be a string")
    checks: list[dict[str, str]] = []

    def result(status: str, check: str, detail: str) -> None:
        checks.append({"status": status, "check": check, "detail": detail})

    failures = 0
    warnings = 0

    lines = text.splitlines()

    headings: list[tuple[int, int, str]] = []
    fence: tuple[str, int] | None = None

    for lineno, line in enumerate(lines, start=1):
        fence_match = FENCE_RE.match(line)
        if fence_match:
            token = fence_match.group(1)
            if fence is None:
                fence = (token[0], len(token))
            elif token[0] == fence[0] and len(token) >= fence[1] and not line[fence_match.end():].strip():
                fence = None
            continue

        if fence is not None:
            continue

        match = HEADING_RE.match(line)
        if match:
            headings.append((lineno, len(match.group(1)), match.group(2)))

    if headings:
        result("PASS", "headings", f"found {len(headings)} headings")
    else:
        warnings += 1
        result("WARN", "headings", "no ATX headings detected")

    jumps: list[str] = []
    previous_level = None
    for lineno, level, title in headings:
        if previous_level is not None and level > previous_level + 1:
            jumps.append(f"line {lineno}: H{previous_level} -> H{level} ({title})")
        previous_level = level

    if jumps:
        failures += 1
        result("FAIL", "heading-hierarchy", "; ".join(jumps[:5]))
    else:
        result("PASS", "heading-hierarchy", "no skipped heading levels detected")

    if fence is not None:
        failures += 1
        result("FAIL", "code-fences", "unclosed fenced code block")
    else:
        result("PASS", "code-fences", "fenced code blocks are balanced")

    trailing = []
    for lineno, line in enumerate(lines, start=1):
        spaces = len(line) - len(line.rstrip(" "))
        if line.endswith("\t") or spaces not in {0, 2}:
            trailing.append(str(lineno))
    if trailing:
        warnings += 1
        result("WARN", "trailing-whitespace", f"lines: {', '.join(trailing[:10])}")
    else:
        result("PASS", "trailing-whitespace", "none detected")

    if VERSION_RE.search(text):
        result("PASS", "document-version", "vX document version detected")
    else:
        result("INFO", "document-version", "no vX document version detected; acceptable unless the requested workflow requires one")

    return {"checks": checks, "failures": failures, "warnings": warnings}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate bounded Markdown structure without changing files.")
    parser.add_argument("file", type=Path)
    args = parser.parse_args(argv)
    path = args.file
    if not path.is_file():
        print("FAIL: file - file does not exist")
        return 2
    if path.suffix.lower() not in {".md", ".markdown"}:
        print("FAIL: extension - expected .md or .markdown")
        return 2
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        print("FAIL: file - unable to read UTF-8 file")
        return 2
    report = analyze(text)
    for check in report["checks"]:
        print(f"{check['status']}: {check['check']} - {check['detail']}".encode("ascii", "backslashreplace").decode("ascii"))
    print(f"SUMMARY: failures={report['failures']} warnings={report['warnings']}")
    return 1 if report["failures"] else 0


if __name__ == "__main__":
    sys.exit(main())
