from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from documents.extract_field_matrix import main


class FieldMatrixTests(unittest.TestCase):
    def test_explicit_source_and_output_extract_data_without_separator_rows(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "converted.md"
            output = root / "out" / "matrix.md"
            source.write_text(
                """# Converted document

## PDF page 3

### Table 1

| A | B | C | D |
| --- | --- | --- | --- |
| 欄位名稱 | 欄位格式 | 資料欄位名稱 | 說明 |
| 客戶代號 | 文字 | customerId | 必填 |
""",
                encoding="utf-8",
            )

            self.assertEqual(
                main([str(source), "--output", str(output), "--title", "Matrix"]),
                0,
            )
            content = output.read_text(encoding="utf-8")
            self.assertIn("| 3 |", content)
            self.assertIn("| 客戶代號 | 文字 | customerId | 必填 |", content)
            self.assertNotIn("| --- | 未命名區段 |", content)
            self.assertIn("../converted.md", content)

    def test_escaped_pipes_and_page_sections_remain_aligned(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "converted.md"
            output = root / "matrix.md"
            source.write_text(
                """## PDF page 1

## 基本資料

### Table 1

| 欄位名稱 | 欄位格式 | 資料欄位名稱 | 說明 |
| --- | --- | --- | --- |
| 狀態 A\\|B | 文字 | status | 顯示 A\\|B |

## PDF page 2

### Table 1

| 畫面欄位名稱 | 型別 | API欄位 | 備註 |
| --- | --- | --- | --- |
| 客戶 | string | customer | 必填 |
""",
                encoding="utf-8",
            )

            self.assertEqual(main([str(source), "--output", str(output)]), 0)

            content = output.read_text(encoding="utf-8")
            self.assertIn("| 1 | 基本資料 | 狀態 A\\|B | 文字 | status | 顯示 A\\|B |", content)
            self.assertIn("| 2 | 未命名區段 | 客戶 | string | customer | 必填 |", content)


if __name__ == "__main__":
    unittest.main()
