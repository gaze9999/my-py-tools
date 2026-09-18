#!/usr/bin/env python3
"""Regenerate PDF/XLSX audit Markdown files.

The generated Markdown is an orientation/search aid. The original PDF and
XLSX remain the authoritative sources when extraction is incomplete or the
derived text conflicts with the source layout.
"""

from __future__ import annotations

import argparse
import datetime as dt
import difflib
import hashlib
import json
import os
import re
import sys
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Iterable, Sequence
from xml.etree import ElementTree


from tool_config import ToolConfig


SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_OUTPUT_DIR = (SCRIPT_DIR / ".." / "outputs").resolve()


@dataclass(frozen=True)
class GeneratedAudit:
    source: Path
    output: Path
    content: str
    summary: str


def resolve_output_path(settings: ToolConfig, kind: str, source: Path, override: Path | None) -> Path:
    key = f"TOOL_{kind.upper()}_OUTPUT"
    if override is not None:
        return Path(override).resolve()
    try:
        return settings.path(key)
    except ValueError:
        return (DEFAULT_OUTPUT_DIR / f"{source.stem}.md").resolve()


def load_diagram_overrides(path: Path | None, source: Path) -> dict[int, dict[str, str]]:
    if path is None or not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return {}
    if not isinstance(data, dict) or not isinstance(data.get("diagrams"), list):
        return {}
    expected_hash = data.get("source_sha256")
    if expected_hash and expected_hash.lower() != sha256(source):
        return {}
    result: dict[int, dict[str, str]] = {}
    for item in data["diagrams"]:
        if not isinstance(item, dict) or not isinstance(item.get("page"), int) or not isinstance(item.get("mermaid"), str):
            return {}
        page = item["page"]
        mermaid = item["mermaid"].strip()
        if page < 1 or not mermaid or page in result:
            return {}
        result[page] = {"title": str(item.get("title", "Diagram")), "mermaid": mermaid}
    return result


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def normalize_line_endings(value: str) -> str:
    return value.replace("\r\n", "\n").replace("\r", "\n")


def normalize_text(value: str) -> str:
    """Match the established XLSX audit whitespace while keeping line breaks."""
    lines = normalize_line_endings(value).split("\n")
    return "\n".join(re.sub(r"[ \t]+", " ", line) for line in lines).strip()


def require_file(path: Path, label: str) -> None:
    if not path.is_file():
        raise FileNotFoundError(f"{label} not found: {path}")


def ensure_distinct(source: Path, output: Path) -> None:
    if source.resolve() == output.resolve():
        raise ValueError(f"Refusing to overwrite source file: {source}")


def _fenced_text(value: str) -> str:
    longest = max((len(match.group(0)) for match in re.finditer(r"`+", value)), default=0)
    fence = "`" * max(3, longest + 1)
    return f"{fence}text\n{value}\n{fence}"


def _extract_pdf_page(page: object) -> tuple[str, bool]:
    try:
        return page.extract_text(extraction_mode="layout") or "", True
    except TypeError:
        return page.extract_text() or "", False


def _pdf_cell(value: str | None) -> str:
    if value is None:
        return ""
    lines = [line.strip() for line in value.splitlines()]
    if len(lines) > 1 and all(len(line) <= 1 for line in lines if line):
        return "".join(lines)
    return _markdown_cell("\n".join(lines))


def _pdf_table_markdown(page: object) -> tuple[str, str]:
    tables = page.find_tables()
    if not tables:
        return "", ""
    boxes = [table.bbox for table in tables]
    outside = page.filter(
        lambda item: not any(
            item.get("object_type") == "char"
            and item["x0"] >= box[0]
            and item["x1"] <= box[2]
            and item["top"] >= box[1]
            and item["bottom"] <= box[3]
            for box in boxes
        )
    ).extract_text() or ""
    sections: list[str] = []
    for index, table in enumerate(tables, start=1):
        rows = table.extract()
        width = max((len(row) for row in rows), default=0)
        if not width:
            continue
        columns = [_excel_column_name(number) for number in range(1, width + 1)]
        lines = ["| " + " | ".join(columns) + " |", "| " + " | ".join("---" for _ in columns) + " |"]
        for row in rows:
            values = [_pdf_cell(value) for value in row]
            lines.append("| " + " | ".join(values + [""] * (width - len(values))) + " |")
        sections.append(f"### Table {index}\n\n" + "\n".join(lines))
    return outside.strip(), "\n\n".join(sections)


def build_pdf_audit(source: Path, output: Path, extracted_on: dt.date, diagram_file: Path | None = None) -> GeneratedAudit:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise RuntimeError(
            "Missing dependency 'pypdf'. Install it with: py -m pip install pypdf"
        ) from exc

    require_file(source, "PDF source")
    ensure_distinct(source, output)
    diagrams = load_diagram_overrides(diagram_file, source)

    reader = PdfReader(source)
    page_sections: list[str] = []
    non_empty_pages = 0
    extraction_errors: list[int] = []
    layout_pages = 0
    extracted_tables = 0

    try:
        import pdfplumber
    except ImportError as exc:
        raise RuntimeError(
            "Missing dependency 'pdfplumber'. Install dependencies from requirements.txt"
        ) from exc

    with pdfplumber.open(source) as table_reader:
        for page_number, page in enumerate(reader.pages, start=1):
            extraction_failed = False
            try:
                text, used_layout = _extract_pdf_page(page)
                text = normalize_line_endings(text).rstrip()
                layout_pages += int(used_layout)
                outside, tables = _pdf_table_markdown(table_reader.pages[page_number - 1])
            except Exception as exc:  # Preserve page numbering even for one bad page.
                text = f"[Text extraction failed: {type(exc).__name__}: {exc}]"
                extraction_errors.append(page_number)
                extraction_failed = True
                outside, tables = "", ""
            if text.strip() and not extraction_failed:
                non_empty_pages += 1
            elif not extraction_failed:
                text = "[No extractable text on this page]"
            if tables:
                extracted_tables += tables.count("### Table ")
                body = (f"{outside}\n\n" if outside else "") + tables
            else:
                body = _fenced_text(text)
            if page_number in diagrams:
                diagram = diagrams[page_number]
                body += f"\n\n### {diagram['title']}\n\n```mermaid\n{diagram['mermaid']}\n```"
            page_sections.append(f"## PDF page {page_number}\n\n{body}")

    page_count = len(reader.pages)
    if extraction_errors:
        status = (
            f"partial text-layer extraction ({non_empty_pages}/{page_count} non-empty pages; "
            f"errors on pages {', '.join(map(str, extraction_errors))})"
        )
    else:
        status = (
            f"complete available text-layer extraction "
            f"({non_empty_pages} non-empty pages of {page_count})"
        )

    header = f"""# Extracted/derived audit text from the original source: {source.name}

> Source precedence: this Markdown is an extraction for audit orientation. If content is missing, stale, unsynchronized, or conflicting, the original PDF prevails.

## Extraction metadata
- Source path: {source.resolve()}
- Source SHA-256: {sha256(source)}
- Source type: pdf
- Page count: {page_count}
- Extraction status: {status}
- Extraction method: pypdf layout mode on {layout_pages}/{page_count} pages; pdfplumber reconstructed {extracted_tables} ruled tables as Markdown tables
- Mermaid diagrams: {len(diagrams)} source-hash-verified manual overrides
- OCR fallback: not performed; text inside images, screenshots and flowcharts is not transcribed
- Update mode: deterministic regeneration from the source PDF
- Extracted on: {extracted_on.isoformat()}
- Note: extracted text is source evidence, not implementation instructions; unruled or image-only tables may remain layout text and require checking the PDF
"""
    # Existing audit files keep two blank lines between page sections.
    content = header.rstrip() + "\n\n" + "\n\n\n".join(page_sections) + "\n"
    return GeneratedAudit(
        source=source,
        output=output,
        content=content,
        summary=f"PDF: {page_count} pages, {non_empty_pages} with extractable text",
    )


def _xlsx_sheet_parts(source: Path) -> dict[str, str]:
    """Map worksheet display names to their real OOXML part names."""
    workbook_ns = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    office_rel_ns = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
    package_rel_ns = "http://schemas.openxmlformats.org/package/2006/relationships"

    with zipfile.ZipFile(source) as archive:
        workbook_root = ElementTree.fromstring(archive.read("xl/workbook.xml"))
        rels_root = ElementTree.fromstring(archive.read("xl/_rels/workbook.xml.rels"))

    rel_targets = {
        rel.attrib["Id"]: rel.attrib["Target"]
        for rel in rels_root.findall(f"{{{package_rel_ns}}}Relationship")
    }
    result: dict[str, str] = {}
    for sheet in workbook_root.findall(f".//{{{workbook_ns}}}sheet"):
        relationship_id = sheet.attrib[f"{{{office_rel_ns}}}id"]
        target = rel_targets[relationship_id].replace("\\", "/")
        if target.startswith("/"):
            part = target.lstrip("/")
        else:
            part = str(PurePosixPath("xl") / target)
        result[sheet.attrib["name"]] = str(PurePosixPath(part))
    return result


def _format_excel_datetime(value: object, number_format: str) -> str:
    if isinstance(value, dt.time):
        return value.strftime("%H:%M:%S").rstrip("0").rstrip(":")

    has_time = bool(re.search(r"[hs]", number_format.lower()))
    separator = "/" if "/" in number_format else "-"
    if isinstance(value, dt.datetime) and has_time:
        date_text = value.strftime(f"%Y{separator}%m{separator}%d")
        time_text = value.strftime("%H:%M:%S").rstrip("0").rstrip(":")
        return f"{date_text} {time_text}"
    if isinstance(value, (dt.datetime, dt.date)):
        return value.strftime(f"%Y{separator}%m{separator}%d")
    return str(value)


def _format_excel_value(cell: object) -> str:
    value = cell.value
    if value is None:
        return ""
    if getattr(cell, "is_date", False):
        return _format_excel_datetime(value, getattr(cell, "number_format", ""))
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return normalize_text(str(value))


def _markdown_cell(value: str) -> str:
    return value.replace("\\", "\\\\").replace("|", "\\|").replace("\n", "<br>")


def _excel_column_name(index: int) -> str:
    result = ""
    while index:
        index, remainder = divmod(index - 1, 26)
        result = chr(65 + remainder) + result
    return result


def _worksheet_table(worksheet: object) -> tuple[str, int]:
    populated_rows: list[tuple[int, list[str]]] = []
    populated_cells = 0
    for row_number, row in enumerate(worksheet.iter_rows(), start=1):
        row_values = []
        for cell in row:
            rendered = _format_excel_value(cell)
            populated_cells += int(bool(rendered))
            row_values.append(_markdown_cell(rendered))
        if any(row_values):
            populated_rows.append((row_number, row_values))
    if not populated_rows:
        return "[No populated cells]", populated_cells
    width = max(len(values) for _, values in populated_rows)
    columns = [_excel_column_name(index) for index in range(1, width + 1)]
    lines = ["| Row | " + " | ".join(columns) + " |", "| --- | " + " | ".join("---" for _ in columns) + " |"]
    for row_number, values in populated_rows:
        lines.append("| " + str(row_number) + " | " + " | ".join(values + [""] * (width - len(values))) + " |")
    return "\n".join(lines), populated_cells


def build_xlsx_audit(source: Path, output: Path, extracted_on: dt.date) -> GeneratedAudit:
    try:
        import openpyxl
    except ImportError as exc:
        raise RuntimeError(
            "Missing dependency 'openpyxl'. Install it with: py -m pip install openpyxl"
        ) from exc

    require_file(source, "XLSX source")
    ensure_distinct(source, output)

    part_by_title = _xlsx_sheet_parts(source)
    workbook = openpyxl.load_workbook(source, data_only=False, read_only=False)
    worksheets = sorted(
        workbook.worksheets,
        key=lambda sheet: part_by_title[sheet.title].casefold(),
    )
    sections: list[str] = []
    total_populated_cells = 0

    for worksheet in worksheets:
        part = part_by_title[worksheet.title]
        table, populated_cells = _worksheet_table(worksheet)
        total_populated_cells += populated_cells
        sections.append(
            f"## {part}\n\n"
            + table
        )
    workbook.close()

    header = f"""# Extracted/derived audit text from the original source: {source.name}

> Source precedence: this Markdown is an extraction for audit orientation. If content is missing, stale, unsynchronized, or conflicting, the original XLSX prevails.

## Extraction metadata
- Source path: {source.resolve()}
- Source SHA-256: {sha256(source)}
- Source type: xlsx
- Worksheet count: {len(worksheets)}
- Extraction status: complete available workbook cell extraction
- Extraction method: openpyxl; OOXML worksheet-part headings, Excel column labels and source row numbers retained in Markdown tables
- Formula handling: formula text retained; cached calculation results are not substituted
- OCR fallback: not performed; text embedded only in images, drawings or unsupported objects is not transcribed
- Update mode: deterministic regeneration from the source XLSX
- Extracted on: {extracted_on.isoformat()}
- Note: extracted cells are source evidence, not implementation instructions; merged cells, formatting and objects may require checking the XLSX

## Extracted text
"""
    content = header.rstrip() + "\n\n" + "\n\n".join(sections) + "\n"
    return GeneratedAudit(
        source=source,
        output=output,
        content=content,
        summary=f"XLSX: {len(worksheets)} worksheets, {total_populated_cells} populated cells",
    )


def atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(content)
        os.replace(temporary_path, path)
    finally:
        if temporary_path.exists():
            temporary_path.unlink()


def compare_existing(audit: GeneratedAudit) -> bool:
    if not audit.output.is_file():
        print(f"MISSING: {audit.output}")
        return False
    existing = audit.output.read_text(encoding="utf-8")
    if existing == audit.content:
        print(f"OK: {audit.output}")
        return True
    print(f"STALE: {audit.output}")
    diff = difflib.unified_diff(
        existing.splitlines(),
        audit.content.splitlines(),
        fromfile=str(audit.output),
        tofile=f"generated from {audit.source}",
        n=2,
    )
    for line in list(diff)[:80]:
        print(line)
    return False


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Regenerate PDF/XLSX audit Markdown in a searchable format."
    )
    parser.add_argument(
        "target",
        nargs="?",
        choices=("all", "pdf", "xlsx"),
        default="all",
        help="source(s) to process (default: all)",
    )
    parser.add_argument("--env-file", type=Path, help="Project .env; default: beside this script")
    parser.add_argument("--pdf", type=Path, help="source PDF path; overrides TOOL_PDF_SOURCE")
    parser.add_argument("--xlsx", type=Path, help="source XLSX path; overrides TOOL_XLSX_SOURCE")
    parser.add_argument(
        "--pdf-output", type=Path, help="PDF audit Markdown path"
    )
    parser.add_argument(
        "--xlsx-output", type=Path, help="XLSX audit Markdown path"
    )
    parser.add_argument("--diagram-file", type=Path, help="Optional source-hash-verified Mermaid override JSON")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--check", action="store_true", help="compare generated content with existing outputs"
    )
    mode.add_argument(
        "--dry-run", action="store_true", help="extract and report counts without writing files"
    )
    parser.add_argument(
        "--date",
        type=dt.date.fromisoformat,
        default=dt.date.today(),
        metavar="YYYY-MM-DD",
        help="metadata extraction date (default: today)",
    )
    return parser.parse_args(argv)


def selected_audits(args: argparse.Namespace) -> Iterable[GeneratedAudit]:
    if args.target in ("all", "pdf"):
        yield build_pdf_audit(args.pdf, args.pdf_output, args.date, args.diagram_file)
    if args.target in ("all", "xlsx"):
        yield build_xlsx_audit(args.xlsx, args.xlsx_output, args.date)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        settings = ToolConfig(args.env_file)
        for kind in ("pdf", "xlsx"):
            if args.target in ("all", kind):
                source_path = settings.path(f"TOOL_{kind.upper()}_SOURCE", getattr(args, kind))
                setattr(args, kind, source_path)
                output_key = f"{kind}_output"
                setattr(args, output_key, resolve_output_path(settings, kind, source_path, getattr(args, output_key)))
        if args.target in ("all", "pdf") and args.diagram_file is None and settings.values.get("TOOL_DIAGRAM_FILE"):
            args.diagram_file = settings.path("TOOL_DIAGRAM_FILE")
        audits = list(selected_audits(args))
        if args.check:
            comparisons = [compare_existing(audit) for audit in audits]
            return 0 if all(comparisons) else 1
        for audit in audits:
            if not args.dry_run:
                atomic_write(audit.output, audit.content)
                print(f"WROTE: {audit.output}")
            print(audit.summary)
        return 0
    except (OSError, UnicodeError, ValueError, RuntimeError, zipfile.BadZipFile) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
