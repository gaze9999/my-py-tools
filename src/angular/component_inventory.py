#!/usr/bin/env python3
"""Locate Angular components in this Nx workspace and explain their file mapping."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, Sequence


SKIP_PARTS = {
    "node_modules", "dist", "build", "coverage", ".angular", ".nx", ".git", ".hg", ".svn", ".venv", "venv"
}
COMPONENT_CLASS_RE = re.compile(r"export\s+class\s+(\w+Component)\b")
SELECTOR_RE = re.compile(r"\bselector\s*:\s*(['\"])(.*?)\1")
TEMPLATE_URL_RE = re.compile(r"\btemplateUrl\s*:\s*(['\"])(.*?)\1")
STYLE_URL_RE = re.compile(r"\bstyleUrl\s*:\s*(['\"])(.*?)\1")
STYLE_URLS_RE = re.compile(r"\bstyleUrls\s*:\s*\[([^\]]*)\]", re.DOTALL)
QUOTED_RE = re.compile(r"(['\"])(.*?)\1")
IMPORT_RE = re.compile(
    r"import\s*\{([^}]+)\}\s*from\s*(['\"])(.*?)\2",
    re.DOTALL,
)
MAPPING_RE = re.compile(
    r"selector\s*:\s*(['\"])(.*?)\1\s*,\s*component\s*:\s*(\w+)",
    re.DOTALL,
)


@dataclass(frozen=True)
class Project:
    name: str
    root: Path
    source_root: Path


@dataclass(frozen=True)
class Component:
    project: str
    class_name: str
    selector: str
    custom_elements: tuple[str, ...]
    source: str
    project_relative: str
    template: str | None
    styles: tuple[str, ...]
    standalone: bool
    description: str


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Map Angular components to workspace/project-relative source, template, "
            "style, selector, custom-element registration, and a short description."
        ),
        epilog=(
            "examples:\n"
            "  python -m angular.component_inventory customer --project customer-ui\n"
            "  python -m angular.component_inventory order-summary\n"
            "  python -m angular.component_inventory --changed --json"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("query", nargs="*", help="Terms matched against path, selector, class, or description")
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="Nx workspace root (default: current directory)")
    parser.add_argument("--project", help="Limit results to one Nx project name")
    parser.add_argument("--changed", action="store_true", help="Show only components with changed companion files")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    parser.add_argument("--limit", type=int, default=50, help="Maximum results; use 0 for unlimited (default: 50)")
    return parser.parse_args(argv)


def relative(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def workspace_files(root: Path) -> Iterable[Path]:
    for current, directory_names, file_names in os.walk(root):
        directory_names[:] = [name for name in directory_names if name.casefold() not in SKIP_PARTS]
        for name in file_names:
            yield Path(current, name)


def load_projects(root: Path, warnings: list[str] | None = None) -> list[Project]:
    projects: list[Project] = []
    for project_file in (path for path in workspace_files(root) if path.name == "project.json"):
        try:
            data = json.loads(project_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            if warnings is not None:
                warnings.append(f"Unable to read {relative(project_file, root)}: {exc}")
            continue
        if not isinstance(data, dict):
            if warnings is not None:
                warnings.append(f"Project file is not a JSON object: {relative(project_file, root)}")
            continue
        project_root = project_file.parent.resolve()
        source_value = data.get("sourceRoot")
        source_root = (root / source_value).resolve() if isinstance(source_value, str) else project_root
        name = data.get("name")
        projects.append(Project(name if isinstance(name, str) else project_root.name, project_root, source_root))
    return sorted(projects, key=lambda item: len(item.source_root.parts), reverse=True)


def owning_project(path: Path, projects: Iterable[Project], root: Path) -> Project:
    resolved = path.resolve()
    for project in projects:
        if resolved == project.source_root or project.source_root in resolved.parents:
            return project
    return Project("(workspace)", root.resolve(), root.resolve())


def resolve_import(source: Path, module_path: str) -> Path | None:
    if not module_path.startswith("."):
        return None
    target = (source.parent / module_path).resolve()
    for candidate in (Path(f"{target}.ts"), target / "index.ts"):
        if candidate.is_file():
            return candidate
    return Path(f"{target}.ts")


def custom_element_map(root: Path, warnings: list[str] | None = None) -> dict[Path, set[str]]:
    result: dict[Path, set[str]] = {}
    for mapping_file in (path for path in workspace_files(root) if path.name == "component-mapping.ts"):
        try:
            text = mapping_file.read_text(encoding="utf-8")
        except OSError as exc:
            if warnings is not None:
                warnings.append(f"Unable to read {relative(mapping_file, root)}: {exc}")
            continue
        imports: dict[str, Path] = {}
        for match in IMPORT_RE.finditer(text):
            resolved = resolve_import(mapping_file, match.group(3))
            if resolved is None:
                continue
            for imported in match.group(1).split(","):
                name = imported.strip().split(" as ")[-1].strip()
                if name:
                    imports[name] = resolved
        for match in MAPPING_RE.finditer(text):
            target = imports.get(match.group(3))
            if target is not None:
                result.setdefault(target.resolve(), set()).add(match.group(2))
    return result


def clean_comment(raw: str) -> str:
    lines = []
    for line in raw.splitlines():
        value = re.sub(r"^\s*(?:/\*\*?|\*/|\*)\s?", "", line).strip()
        if value and not value.startswith("@"):
            lines.append(value)
    return " ".join(lines)


def inferred_description(text: str, component_at: int, class_name: str) -> str:
    prefix = text[:component_at].rstrip()
    block = re.search(r"/\*\*([\s\S]*?)\*/\s*$", prefix)
    if block:
        value = clean_comment(block.group(0))
        if value:
            return value
    name = re.sub(r"Component$", "", class_name)
    words = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", name).strip()
    return words or class_name


def companion_path(source: Path, value: str, root: Path) -> str:
    return relative((source.parent / value).resolve(), root)


def scan_components(
    root: Path,
    projects: Sequence[Project],
    warnings: list[str] | None = None,
) -> list[Component]:
    custom = custom_element_map(root, warnings)
    components: list[Component] = []
    for source in (path for path in workspace_files(root) if path.suffix.casefold() == ".ts"):
        if source.name.endswith((".spec.ts", ".test.ts", ".d.ts")):
            continue
        try:
            text = source.read_text(encoding="utf-8")
        except OSError as exc:
            if warnings is not None:
                warnings.append(f"Unable to read {relative(source, root)}: {exc}")
            continue
        search_at = 0
        while True:
            component_at = text.find("@Component", search_at)
            if component_at < 0:
                break
            class_match = COMPONENT_CLASS_RE.search(text, component_at)
            if not class_match:
                break
            search_at = class_match.end()
            metadata = text[component_at:class_match.start()]
            selector_match = SELECTOR_RE.search(metadata)
            template_match = TEMPLATE_URL_RE.search(metadata)
            style_values: list[str] = []
            style_match = STYLE_URL_RE.search(metadata)
            if style_match:
                style_values.append(style_match.group(2))
            styles_match = STYLE_URLS_RE.search(metadata)
            if styles_match:
                style_values.extend(match.group(2) for match in QUOTED_RE.finditer(styles_match.group(1)))
            project = owning_project(source, projects, root)
            components.append(Component(
                project=project.name,
                class_name=class_match.group(1),
                selector=selector_match.group(2) if selector_match else "",
                custom_elements=tuple(sorted(custom.get(source.resolve(), set()))),
                source=relative(source, root),
                project_relative=relative(source, project.root),
                template=companion_path(source, template_match.group(2), root) if template_match else None,
                styles=tuple(companion_path(source, value, root) for value in style_values),
                standalone=bool(re.search(r"\bstandalone\s*:\s*true\b", metadata)),
                description=inferred_description(text, component_at, class_match.group(1)),
            ))
    return sorted(components, key=lambda item: (item.project.casefold(), item.source.casefold()))


def git_changed(root: Path) -> set[str]:
    commands = (
        ["git", "-C", str(root), "diff", "--name-only", "--relative", "-z"],
        ["git", "-C", str(root), "diff", "--cached", "--name-only", "--relative", "-z"],
        ["git", "-C", str(root), "ls-files", "--others", "--exclude-standard", "-z"],
    )
    changed: set[str] = set()
    for command in commands:
        try:
            process = subprocess.run(command, check=True, capture_output=True)
        except (OSError, subprocess.CalledProcessError) as error:
            raise RuntimeError(f"Unable to read Git changes: {error}") from error
        changed.update(
            os.fsdecode(raw).replace("\\", "/")
            for raw in process.stdout.split(b"\0")
            if raw
        )
    return changed


def matches(component: Component, terms: Sequence[str]) -> bool:
    haystack = "\n".join((
        component.project,
        component.class_name,
        component.selector,
        *component.custom_elements,
        component.source,
        component.project_relative,
        component.template or "",
        *component.styles,
        component.description,
    )).casefold()
    return all(term.casefold() in haystack for term in terms)


def changed_component(component: Component, changed: set[str]) -> bool:
    companions = {component.source, component.template or "", *component.styles}
    mapping_changed = component.custom_elements and any(Path(path).name == "component-mapping.ts" for path in changed)
    return bool(companions & changed) or bool(mapping_changed)


def print_text(components: Sequence[Component], total: int) -> None:
    for item in components:
        custom = ", ".join(item.custom_elements) if item.custom_elements else "-"
        styles = ", ".join(item.styles) if item.styles else "-"
        print(f"[{item.project}] {item.class_name}")
        print(f"  selector: {item.selector or '-'}")
        print(f"  custom-element: {custom}")
        print(f"  source: {item.source}")
        print(f"  project-relative: {item.project_relative}")
        print(f"  template: {item.template or '-'}")
        print(f"  styles: {styles}")
        print(f"  standalone: {'yes' if item.standalone else 'no'}")
        print(f"  description: {item.description}")
    if total > len(components):
        print(f"... {total - len(components)} more result(s); raise --limit or use --limit 0", file=sys.stderr)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    try:
        root = args.root.expanduser().resolve()
    except (OSError, RuntimeError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    if not (root / "nx.json").is_file():
        print(f"error: not an Nx workspace root: {root}", file=sys.stderr)
        return 2
    if args.limit < 0:
        print("error: --limit must be 0 or greater", file=sys.stderr)
        return 2

    warnings: list[str] = []
    projects = load_projects(root, warnings)
    results = [item for item in scan_components(root, projects, warnings) if matches(item, args.query)]
    if args.project:
        results = [item for item in results if item.project.casefold() == args.project.casefold()]
    if args.changed:
        try:
            changed = git_changed(root)
        except RuntimeError as error:
            print(f"error: {error}", file=sys.stderr)
            return 2
        results = [item for item in results if changed_component(item, changed)]

    total = len(results)
    shown = results if args.limit == 0 else results[:args.limit]
    if args.json:
        print(json.dumps({"workspace": str(root), "count": total, "components": [asdict(item) for item in shown],
                          "warnings": warnings},
                         ensure_ascii=False, indent=2))
    else:
        print_text(shown, total)
        for warning in warnings:
            print(f"warning: {warning}", file=sys.stderr)
    return 0 if total else 1


if __name__ == "__main__":
    raise SystemExit(main())
