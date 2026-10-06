#!/usr/bin/env python3
"""Check declared form controls against TypeScript and template files without editing them."""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

CONTROL_RE = re.compile(
    r"(?:^|[,{]\s*)(?:(?P<bare>[A-Za-z_$][\w$]*)|(?P<quote>['\"])(?P<quoted>[^'\"]+)\2)\s*:\s*"
    r"(?:new\s+(?:Untyped)?FormControl(?:\s*<[^>]+>)?|(?:this\.)?[\w$.]+\.control|\[)",
    re.MULTILINE,
)
TEMPLATE_CONTROL_RE = re.compile(r"\bformControlName\s*=\s*(['\"])([^'\"]+)\1")


def read_json(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict) or not isinstance(data.get("components"), list):
        raise ValueError("Contract must be an object with a components array")
    return data


def controls_in_source(text: str) -> set[str]:
    return {(match.group("bare") or match.group("quoted")) for match in CONTROL_RE.finditer(text)}


def controls_in_template(text: str) -> set[str]:
    return {match.group(2) for match in TEMPLATE_CONTROL_RE.finditer(text)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="Root for contract-relative paths (default: current directory)")
    parser.add_argument("--contract", type=Path, required=True, help="JSON contract file")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        root = args.root.expanduser().resolve()
        contract_path = args.contract.expanduser().resolve()
        contract = read_json(contract_path)
        findings: list[dict[str, str]] = []
        checked = 0
        for entry in contract["components"]:
            if not isinstance(entry, dict) or not isinstance(entry.get("source"), str):
                raise ValueError("Each component needs a source path")
            source = root / entry["source"]
            template = root / entry.get("template", "") if entry.get("template") else None
            expected = entry.get("controls", [])
            if not isinstance(expected, list) or not all(isinstance(item, str) for item in expected):
                raise ValueError(f"controls must be a string array: {entry['source']}")
            checked += 1
            if not source.is_file():
                findings.append({"kind": "missing-source", "component": entry["source"], "control": ""})
                continue
            source_controls = controls_in_source(source.read_text(encoding="utf-8"))
            template_exists = template is not None and template.is_file()
            if template is not None and not template_exists:
                findings.append(
                    {"kind": "missing-template", "component": entry["template"], "control": ""}
                )
            template_controls = (
                controls_in_template(template.read_text(encoding="utf-8"))
                if template_exists
                else set()
            )
            for control in expected:
                if control not in source_controls:
                    findings.append({"kind": "missing-source-control", "component": entry["source"], "control": control})
                if template_exists and control not in template_controls:
                    findings.append({"kind": "missing-template-control", "component": entry["source"], "control": control})
            for control in template_controls - source_controls:
                findings.append({"kind": "template-control-without-source", "component": entry["source"], "control": control})
        output = {"contract": str(contract_path), "checked_components": checked, "findings": findings}
        print(json.dumps(output, ensure_ascii=False, indent=2) if args.json else "\n".join(
            f"{item['kind']}: {item['component']} {item['control']}" for item in findings
        ) or "OK")
        return 1 if findings else 0
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
