# 文件處理工具

## `documents/convert_to_markdown.py`

接受單一或多個來源檔, 依副檔名自動使用對應轉換器, 產生可搜尋的 Markdown

支援格式

| 格式 | 抽取內容 | 必要套件 | 主要限制 |
| --- | --- | --- | --- |
| `.pdf` | 每頁文字層, 框線表格, 選用 Mermaid 覆寫 | `pypdf`, `pdfplumber` | 不執行 OCR, 圖片與沒有文字層的內容不會被推測 |
| `.xlsx` | 工作表, 原始列號, 公式文字, 有內容的儲存格 | `openpyxl` | 不計算公式, 圖形與格式需回看原檔 |
| `.docx` | 文件本文段落與表格 | `python-docx` | 圖片, 文字方塊, 頁首, 頁尾, 註解與版面可能缺漏 |
| `.pptx` | 投影片文字框與表格 | `python-pptx` | 圖片, 圖表, SmartArt, 媒體, 備忘稿與空間關係可能缺漏 |
| `.csv` | 依分隔符號解析的表格與原始列號 | 無 | 預設 UTF-8 BOM, 其他編碼用 `--text-encoding` |
| `.txt` | 原文 fenced code block 與行數 | 無 | 預設 UTF-8 BOM, 其他編碼用 `--text-encoding` |

原始文件始終是權威來源, 轉換後的 Markdown 只用於搜尋與定位

### 單輸入

預設在來源旁產生同名 `.md`

```powershell
python launch-cli.py documents.convert_to_markdown C:\path\spec.docx
python launch-cli.py documents.convert_to_markdown C:\path\spec.pdf --output C:\path\markdown\spec.md
```

`--output` 只允許搭配 1 個來源

### 多輸入, 多輸出

未指定輸出選項時, 每個來源各自在原目錄產生同名 `.md`, `--output-dir` 可集中輸出

```powershell
python launch-cli.py documents.convert_to_markdown spec.pdf api.xlsx slides.pptx
python launch-cli.py documents.convert_to_markdown spec.pdf api.xlsx slides.pptx --output-dir .\markdown-output
```

若多個來源在集中目錄會得到相同檔名, 工具回傳錯誤並要求改名, 合併或分次執行

### 多輸入, 單輸出

```powershell
python launch-cli.py documents.convert_to_markdown spec.pdf api.xlsx notes.txt --combine-output .\combined.md
```

合併檔保留各來源路徑, 格式, SHA-256, 擷取器中繼資料與限制, 原本的標題會降一層以維持合法階層

### 其他選項

- `--dry-run` 完成實際抽取並顯示統計, 不寫檔
- `--check` 重新轉換後逐位元組比對既有 Markdown, 相同回傳 `0`, 缺少或 stale 回傳 `1`, 未指定 `--extracted-at` 時會沿用既有輸出的時間, 避免只有時間不同就誤判 stale
- `--extracted-at YYYY-MM-DDTHH:MM:SS` 固定擷取時間, 輸出格式為 `YYYY-MM-DD HH:MM:SS`, 方便產生可重現的檢查結果
- 舊的 `--date` 保留為相容別名, 只提供日期時會使用 `00:00:00`
- `--text-encoding` 指定 CSV/TXT 編碼
- `--diagram-file` 只允許單一 PDF 來源, JSON 缺失, 無法讀取, 格式錯誤, 來源 hash 不符或項目無效時, 會略過 Mermaid 覆寫並繼續擷取

所有輸出必須使用 `.md`, 來源不存在, 格式不支援, 相依套件缺少或輸出可能覆寫來源時, 回傳結束代碼 `2`

正常模式會以同目錄暫存檔原子取代各輸出, 若既有同名 `.md` 需要先確認差異, 可先用 `--check` 或 `--dry-run`, 多輸出採逐檔原子寫入, 不保證整批全部成功或全部不寫入

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

## `documents/extract_field_matrix.py`

從 `convert_to_markdown` 產生的 PDF Markdown 中, 找出 `### Table` 內的欄位表格, 輸出頁碼, 區段, 欄位名稱, 格式, API 欄位與說明

```powershell
python launch-cli.py documents.extract_field_matrix .\spec.md
python launch-cli.py documents.extract_field_matrix .\spec.md --output .\matrix.md --title "欄位規格矩陣"
```

預設輸出檔名為 `SOURCE_STEM-欄位規格矩陣.md`, 標題優先使用 `--title`, 再使用 `TOOL_FIELD_MATRIX_TITLE`, 最後由來源檔名產生

支援 `欄位名稱`, `畫面欄位名稱`, `欄位`, `欄位格式`, `資料格式`, `型別`, `資料欄位名稱`, `API欄位`, `說明`, `欄位說明`, `備註` 等常見中文表頭, 不驗證必填, 長度, API 型別或業務規則, 原始 PDF 與正式 API 規格仍需分別核對

結束代碼 `0` 表示抽取完成, 即使沒有相符欄位也會輸出 0 筆統計, `2` 表示來源, 編碼或輸出路徑錯誤

## `documents/locate_markdown_extracts.py`

依來源絕對路徑與 SHA-256, 在一個或多個根目錄中尋找由文件轉換工具產生的 Markdown, 並區分 `current`, `stale` 與一般候選

```powershell
python launch-cli.py documents.locate_markdown_extracts --source C:\path\spec.pdf --root C:\path\markdown
python launch-cli.py documents.locate_markdown_extracts --source-sha256 <64位SHA-256> --root C:\path\one --root C:\path\two
```

工具只讀取 Markdown 前段的 `Source`, `Source SHA-256` 與 `Extracted on` metadata, 不修改檔案, 掃描預設最多 10000 份 Markdown, 結果預設最多 50 筆, 會跳過 Git 與常見快取資料夾
