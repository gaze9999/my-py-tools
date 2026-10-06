#!/usr/bin/env python3
"""Export or check the standalone validator snapshot from its canonical source."""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import re
import tempfile

ROOT = Path(__file__).resolve().parents[2]


def snapshot(root: Path = ROOT) -> bytes:
    source = (root / "src/markdown/validate_structure.py").read_bytes().replace(b"\r\n", b"\n")
    match = re.search(r'(?m)^version\s*=\s*"([^"]+)"\s*$', (root / "pyproject.toml").read_text(encoding="utf-8"))
    if not match:
        raise ValueError("Package version not found")
    checksum = hashlib.sha256(source).hexdigest()
    banner = (
        "#!/usr/bin/env python3\n"
        "# GENERATED - DO NOT EDIT; use launch-cli.py scripts.export_markdown_validator\n"
        "# Canonical source: my-py-tools/src/markdown/validate_structure.py\n"
        f"# Package: my-py-document-core {match.group(1)}; API_VERSION=1\n"
        f"# Source SHA-256 (LF): {checksum}\n"
    ).encode("ascii")
    body = source.split(b"\n", 1)[1] if source.startswith(b"#!") else source
    return banner + body


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--check", action="store_true", help="Compare only; do not write")
    args = parser.parse_args(argv)
    try:
        output = args.output.resolve()
        if output == (ROOT / "src/markdown/validate_structure.py").resolve():
            raise ValueError("Output must not replace canonical source")
        expected = snapshot()
        before = output.read_bytes() if output.exists() else None
        if args.check:
            if before is None or before.replace(b"\r\n", b"\n") != expected:
                print("FAIL: standalone snapshot differs from canonical source")
                return 1
            print("PASS: standalone snapshot matches canonical source and package version")
            return 0
        if before == expected:
            print("CURRENT: standalone snapshot")
            return 0
        output.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=output.parent, delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(expected)
        try:
            if (output.read_bytes() if output.exists() else None) != before:
                raise ValueError("Output changed during export")
            temporary.replace(output)
        finally:
            temporary.unlink(missing_ok=True)
        if output.read_bytes() != expected:
            raise ValueError("Snapshot readback mismatch")
        print("GENERATED: standalone snapshot")
        return 0
    except (OSError, ValueError) as exc:
        print("FAIL: " + str(exc))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
