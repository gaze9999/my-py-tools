from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from audit.extract_field_contract_matrix import main


class FieldContractMatrixTests(unittest.TestCase):
    def test_explicit_source_and_output_extract_data_without_separator_rows(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "audit.md"
            output = root / "out" / "matrix.md"
            source.write_text(
                """# Audit

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
            self.assertIn("../audit.md", content)


if __name__ == "__main__":
    unittest.main()
