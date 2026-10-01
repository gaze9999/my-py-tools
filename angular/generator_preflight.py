#!/usr/bin/env python3
"""Find existing feature identifiers and selectors before a generator changes either tree."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

SKIP = {"node_modules", "dist", ".git", ".nx", ".angular", "coverage"}
TEXT_EXTENSIONS = {
    ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".html", ".scss", ".sass", ".less", ".css",
    ".json", ".xml", ".properties", ".md", ".markdown", ".yaml", ".yml", ".toml", ".ini", ".gradle",
    ".java", ".kt", ".kts", ".graphql", ".gql", ".vue", ".svelte",
}


def files(root: Path):
    for base, directories, names in os.walk(root):
        directories[:] = [name for name in directories if name.casefold() not in SKIP]
        for name in names:
            path = Path(base, name)
            if path.suffix.casefold() in TEXT_EXTENSIONS:
                yield path


def occurrences(root: Path, value: str) -> tuple[list[str], list[str]]:
    matches = []
    warnings = []
    for path in files(root):
        try:
            if value.casefold() in path.read_text(encoding="utf-8", errors="replace").casefold():
                matches.append(path.relative_to(root).as_posix())
        except OSError as exc:
            warnings.append(f"{path.relative_to(root).as_posix()}: {exc}")
    return matches, warnings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="Cross-tree root (default: current directory)")
    parser.add_argument("--identifier", required=True, help="Proposed transaction or feature identifier")
    parser.add_argument("--selector", help="Proposed custom-element selector")
    parser.add_argument("--allow-existing", action="store_true", help="Report collisions without a non-zero exit")
    args = parser.parse_args(argv)
    try:
        root = args.root.expanduser().resolve()
        if not root.is_dir():
            raise ValueError(f"Generator root does not exist: {root}")
        identifier = args.identifier.strip()
        if not identifier:
            raise ValueError("--identifier must not be empty")
        if args.selector is not None and not args.selector.strip():
            raise ValueError("--selector must not be empty")
        identifier_matches, warnings = occurrences(root, identifier)
        checks = {"identifier": identifier_matches}
        selector = args.selector.strip() if args.selector is not None else None
        if selector:
            selector_matches, selector_warnings = occurrences(root, selector)
            checks["selector"] = selector_matches
            warnings.extend(item for item in selector_warnings if item not in warnings)
        collisions = {name: paths for name, paths in checks.items() if paths}
        print(json.dumps({"root": str(root), "proposed": {"identifier": identifier, "selector": selector},
                          "collisions": collisions, "warnings": warnings}, ensure_ascii=False, indent=2))
        return 0 if not collisions or args.allow_existing else 1
    except (OSError, UnicodeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
