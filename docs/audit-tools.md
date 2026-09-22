# 來源文件 audit 工具

## `audit/source_audit_extract.py`

接受單一或多個來源檔, 依副檔名自動使用對應 extractor, 產生可搜尋的 Markdown audit

支援格式

| 格式 | 抽取內容 | 必要套件 | 主要限制 |
| --- | --- | --- | --- |
| `.pdf` | 每頁 text layer, ruled table, 選用 Mermaid override | `pypdf`, `pdfplumber` | 不執行 OCR, 圖片與無 text layer 內容不會被猜測 |
| `.xlsx` | worksheet, source row, formula text, populated cells | `openpyxl` | 不計算 formula, drawing 與格式需回看原檔 |
| `.docx` | document body paragraph 與 table | `python-docx` | 圖片, text box, header, footer, comments 與版面可能缺漏 |
| `.pptx` | slide text frame 與 table | `python-pptx` | 圖片, chart, SmartArt, media, notes 與空間關係可能缺漏 |
| `.csv` | delimiter-aware table 與 source row | 無 | 預設 UTF-8 BOM, 其他 encoding 用 `--text-encoding` |
| `.txt` | 原文 fenced text 與 line count | 無 | 預設 UTF-8 BOM, 其他 encoding 用 `--text-encoding` |

原始文件始終是權威來源, audit 只用於搜尋與定位

### 單輸入

預設在來源旁產生同名 `.md`

```powershell
python -m audit.source_audit_extract C:\path\spec.docx
python -m audit.source_audit_extract C:\path\spec.pdf --output C:\path\audit\spec-audit.md
```

`--output` 只允許搭配 1 個來源

### 多輸入, 多輸出

未指定 output option 時, 每個來源各自在原目錄產生同名 `.md`; `--output-dir` 可集中輸出

```powershell
python -m audit.source_audit_extract spec.pdf api.xlsx slides.pptx
python -m audit.source_audit_extract spec.pdf api.xlsx slides.pptx --output-dir .\audit-output
```

若多個來源在集中目錄會得到相同檔名, 工具回傳錯誤並要求改名, 合併或分次執行

### 多輸入, 單輸出

```powershell
python -m audit.source_audit_extract spec.pdf api.xlsx notes.txt --combine-output .\combined-audit.md
```

合併檔保留各來源路徑, 格式, SHA-256, extractor metadata 與限制, 原本 heading 會降一層以維持合法階層

### 其他 option

- `--dry-run` 完成實際抽取並顯示統計, 不寫檔
- `--check` 重新抽取後逐位元組比對既有 Markdown, 相同回傳 `0`, 缺少或 stale 回傳 `1`
- `--date YYYY-MM-DD` 固定 metadata 日期, 便於 deterministic check
- `--text-encoding` 指定 CSV/TXT encoding
- `--diagram-file` 只允許單一 PDF 來源, JSON 缺失、無法讀取、格式錯誤、source hash 不符或 entry 無效時 fail-open 為不套用 override

所有 output 必須使用 `.md`, source 不存在、格式不支援、相依套件缺少或輸出可能覆寫來源時回傳 exit code `2`

正常模式會以同目錄 temporary file atomic replace 各輸出, 若既有同名 `.md` 需要先確認差異, 可先用 `--check` 或 `--dry-run`; 多輸出是逐檔 atomic, 不保證整批 all-or-nothing

Mermaid override 格式

```json
{
  "source_sha256": "PDF_SHA256",
  "diagrams": [
    {
      "page": 3,
      "title": "Approval flow",
      "mermaid": "flowchart LR\nA-->B"
    }
  ]
}
```

## `audit/extract_field_contract_matrix.py`

從 `source_audit_extract` 產生的 PDF audit 中, 找出 `### Table` 內含 `欄位名稱` 與 `說明` 的表格, 輸出頁碼, 區段, 欄位名稱, 格式, API 欄位與說明

```powershell
python -m audit.extract_field_contract_matrix .\spec.md
python -m audit.extract_field_contract_matrix .\spec.md --output .\matrix.md --title "欄位契約矩陣"
```

預設輸出為來源旁的 `SOURCE_STEM-欄位契約矩陣.md`, title 優先使用 `--title`, 再使用 `TOOL_FIELD_MATRIX_TITLE`, 最後由來源檔名產生

此工具只辨識目前既有的中文表頭命名, 不驗證必填、長度、API 型別或業務規則, 原始 PDF 與正式 API 規格仍需分別核對

exit code `0` 表示抽取完成, 即使沒有相符欄位也會輸出 0 筆統計, `2` 表示來源、encoding 或輸出路徑錯誤
