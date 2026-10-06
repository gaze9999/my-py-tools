"""Extract a field matrix from converted source-document Markdown."""

from __future__ import annotations

import argparse
import os
import re
import sys
import tempfile
from pathlib import Path

if __package__ and __package__.startswith("my_py_document_core."):
    from ..shared.config import ToolConfig
else:
    from shared.config import ToolConfig


DEFAULT_TITLE_ENV_KEY = "TOOL_FIELD_MATRIX_TITLE"
FIELD_HEADERS = ("欄位名稱", "畫面欄位名稱", "欄位")
FORMAT_HEADERS = ("欄位格式", "資料格式", "格式", "型別")
API_HEADERS = (
    "資料欄位名稱(API對應名稱/程式對應名稱)",
    "資料欄位名稱",
    "API欄位名稱",
    "API欄位",
    "程式欄位名稱",
)
DESCRIPTION_HEADERS = ("說明", "欄位說明", "備註")


def normalize_header(value: str) -> str:
    if not value:
        return ""
    return re.sub(r"\s+", "", value.replace("<br>", "").strip())


def normalize_cell(value: str) -> str:
    if not value:
        return ""
    v = value.replace("<br>", " ").replace("\r", " ").replace("\n", " ")
    v = re.sub(r"\s+", " ", v).strip()
    return v.replace("|", "\\|")


def parse_table_line(line: str) -> list[str]:
    line = line.strip()
    if not line.startswith("|"):
        return []
    body = line[1:-1] if line.endswith("|") else line[1:]
    cells: list[str] = []
    current: list[str] = []
    escaped = False
    for character in body:
        if escaped:
            if character in {"|", "\\"}:
                current.append(character)
            else:
                current.extend(("\\", character))
            escaped = False
        elif character == "\\":
            escaped = True
        elif character == "|":
            cells.append("".join(current).strip())
            current = []
        else:
            current.append(character)
    if escaped:
        current.append("\\")
    cells.append("".join(current).strip())
    return cells


def find_header_index(header_map: dict[str, int], choices: tuple[str, ...]) -> int:
    return next((header_map[name] for name in choices if name in header_map), -1)


def write_text_atomic(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)


def is_separator_row(line: str) -> bool:
    cells = parse_table_line(line)
    return bool(cells) and all(
        re.fullmatch(r":?-{3,}:?", cell.replace(" ", "")) for cell in cells
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Extract field-matrix table rows from converted Markdown.")
    parser.add_argument("source_markdown", type=Path, help="Converted PDF Markdown source")
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        help="Output Markdown path (default: SOURCE_STEM-欄位規格矩陣.md beside source)",
    )
    parser.add_argument("--env-file", type=Path, help="Optional TOOL_* variable file")
    parser.add_argument(
        "--title",
        help="Output title; otherwise TOOL_FIELD_MATRIX_TITLE or a source-derived title",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    settings = ToolConfig(args.env_file)
    settings.emit_warnings()
    source_path = args.source_markdown.expanduser().resolve()
    output_path = (
        args.output.expanduser().resolve()
        if args.output
        else source_path.with_name(f"{source_path.stem}-欄位規格矩陣.md")
    )
    title = args.title or settings.value(
        DEFAULT_TITLE_ENV_KEY,
        f"{source_path.stem} - 欄位規格矩陣 (抽取版)",
    )

    if not source_path.is_file():
        print(f"error: source Markdown not found: {source_path}", file=sys.stderr)
        return 2
    if output_path == source_path:
        print("error: output must not overwrite the source Markdown", file=sys.stderr)
        return 2

    try:
        line_list = source_path.read_text(encoding="utf-8-sig").splitlines()
    except (OSError, UnicodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    page_no = ""
    section = ""
    entries: list[dict[str, str]] = []

    i = 0
    while i < len(line_list):
        line = line_list[i]

        if re.match(r"^##\s+PDF page\s+\d+", line):
            page_no = re.sub(r"^##\s+PDF page\s+", "", line).strip()
            section = ""
            i += 1
            continue

        if re.match(r"^##\s+(?!PDF page\s+).+", line):
            section = line.lstrip("#").strip()
            i += 1
            continue

        if re.match(r"^###\s+Table\s+\d+", line):
            j = i + 1
            while j < len(line_list) and not line_list[j].strip():
                j += 1
            if j >= len(line_list):
                i += 1
                continue

            table_lines: list[str] = []
            while j < len(line_list) and line_list[j].strip().startswith("|"):
                table_lines.append(line_list[j])
                j += 1
            i = j - 1

            if len(table_lines) < 3:
                i += 1
                continue

            header_index = -1
            for row_idx, row_text in enumerate(table_lines):
                cells = parse_table_line(row_text)
                if not cells:
                    continue
                normalized = [normalize_header(cell) for cell in cells]
                if any(cell in FIELD_HEADERS for cell in normalized) and any(
                    cell in DESCRIPTION_HEADERS for cell in normalized
                ):
                    header_index = row_idx
                    break

            if header_index < 0:
                i += 1
                continue

            header = parse_table_line(table_lines[header_index])
            if not header:
                i += 1
                continue

            header_map: dict[str, int] = {
                normalize_header(col): idx for idx, col in enumerate(header)
            }
            field_idx = find_header_index(header_map, FIELD_HEADERS)
            if field_idx < 0:
                i += 1
                continue

            format_idx = find_header_index(header_map, FORMAT_HEADERS)
            api_idx = find_header_index(header_map, API_HEADERS)
            desc_idx = find_header_index(header_map, DESCRIPTION_HEADERS)

            data_start = header_index + 1
            while (
                data_start < len(table_lines)
                and is_separator_row(table_lines[data_start])
            ):
                data_start += 1

            for row_idx in range(data_start, len(table_lines)):
                row = parse_table_line(table_lines[row_idx])
                if len(row) <= field_idx:
                    continue

                field = normalize_cell(row[field_idx])
                if not field or field == "欄位名稱" or field in {"A", "B", "C", "D", "E", "F"}:
                    continue
                if re.fullmatch(r"[A-Z]", field):
                    continue

                entries.append(
                    {
                        "Page": page_no or "未定位",
                        "Section": section or "未命名區段",
                        "Field": field,
                        "Format": normalize_cell(row[format_idx]) if format_idx >= 0 and len(row) > format_idx else "",
                        "ApiField": normalize_cell(row[api_idx]) if api_idx >= 0 and len(row) > api_idx else "",
                        "Description": normalize_cell(row[desc_idx]) if desc_idx >= 0 and len(row) > desc_idx else "",
                    }
                )

            i += 1
            continue

        i += 1

    lines_out: list[str] = []
    source_link = Path(os.path.relpath(source_path, output_path.parent)).as_posix()
    lines_out.append(f"# {title}")
    lines_out.append("")
    lines_out.append("## 來源")
    lines_out.append(f"- 本檔案由 [{source_path.name}]({source_link}) 的欄位表格萃取而來。")
    lines_out.append("- 萃取條件：欄位表頭含 `欄位名稱`、`欄位格式`、`說明`。")
    lines_out.append("")
    lines_out.append("| 頁碼 | 區段 | 欄位名稱 | 欄位格式 | 資料欄位名稱 | 說明 |")
    lines_out.append("| --- | --- | --- | --- | --- | --- |")

    for item in entries:
        lines_out.append(
            f"| {item['Page']} | {item['Section']} | {item['Field']} | {item['Format']} | {item['ApiField']} | {item['Description']} |"
        )

    lines_out.append("")
    lines_out.append("## 來源統計")
    lines_out.append(f"- 抽取欄位數：{len(entries)}")

    try:
        write_text_atomic(output_path, "\n".join(lines_out) + "\n")
    except OSError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(f"抽取完成：{len(entries)} 筆，輸出到 {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
