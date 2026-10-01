# Local Documents MCP

跨專案的本地文件擷取與 Markdown 更新工具, 使用官方 MCP Python SDK 的 stdio transport, 沿用 `audit.source_audit_extract` 與 `markdown.guarded_markdown_update`, 不依賴 Angular 或遠端 API

## 安裝與啟動

使用 Python 3.10+, 在 repository 根目錄建立獨立環境並安裝固定版本相依

```text
python -m venv .venv-documents
# Windows
.venv-documents\Scripts\python.exe -m pip install -r mcp_tools/requirements.txt
# macOS / Linux
.venv-documents/bin/python -m pip install -r mcp_tools/requirements.txt
```

以環境中的 Python 啟動, 每個允許的資料夾分別指定 `--read-root` 或 `--write-root`, 都必須是存在的絕對路徑; 未指定 write root 時只能擷取本文或檢查檔案, 無法寫入

```text
python -m mcp_tools.document_server --read-root /absolute/project --write-root /absolute/output
```

其他 MCP client 使用相同 command 與 args 即可, working directory 設為 repository 根目錄; 路徑與 Runtime 由每台電腦配置, 不寫入 source code

Codex 可使用 installer, 預設只顯示要註冊的設定, 明確加上 `--apply` 才備份並更新 `config.toml`; 不改動其他 MCP 與設定, 重複相同設定回傳 unchanged

```text
python -m mcp_tools.install_document_mcp --python /absolute/venv/python --read-root /absolute/project --write-root /absolute/output
```

## 操作

| Tool | 用途 |
| --- | --- |
| `document_status` | 查看套件版本, 格式, 讀寫範圍與檔案上限 |
| `extract_document` | 擷取 PDF/XLSX/DOCX/PPTX/CSV/TXT 或 raster image, 選用 OCR, 回傳來源 hash 與位置 |
| `inspect_markdown` | 查看 SHA-256 與章節, 選用單一章節內容 |
| `update_markdown` | 預覽或執行單一章節替換, 或以唯一 entry ID 追加紀錄 |

`extract_document` 預設不寫檔; `write_output=true` 必須明確指定 `.md` output, 既有 output 必須提供其 `expected_output_sha256`; 新檔使用同目錄 temporary file 與 exclusive hard link 原子發布, 檔案系統不支援時會回傳錯誤而不降級覆寫

`update_markdown` 預設 preview, 必須提供目前 SHA-256, 並在 `heading` 與 `entry_id` 中擇一; replacement 必須以相同 heading 開頭, 不得插入同層或更高層 section; `write=true` 才寫入, 保留既有 UTF-8 BOM 與換行格式, 寫後讀回核對; iCloud 等 placeholder 的非原子寫入需明確指定 `in_place=true`, 失敗保留 backup

## OCR 與限制

- RapidOCR + ONNX Runtime 使用本地 CPU, OCR 結果包含 engine, location, line confidence 與 box, 不上傳來源文件
- 固定使用 RapidOCR 3.9.2 隨附的 PP-OCRv6 det/rec 與方向分類模型, 明確指定本地 model paths, 缺少時回報錯誤, 不在工具呼叫時下載模型; `document_status` 回傳模型 SHA-256
- `ocr=auto` 只補 PDF 無原生文字的頁面與 OOXML 內嵌 raster images; 有文字但部分內容是圖片的 PDF 頁面需明確選 `ocr=force`
- `pages` 僅控制 PDF OCR 頁碼, 使用 1-based numbering; 原生擷取仍涵蓋整份文件
- OCR 預設最多 10 頁或圖片, 可設 1-100; 超出上限或失敗都回傳 partial 與明確原因
- 回傳文字預設最多 30000 字元, 可設 1-200000; 完整擷取內容可另寫入明確指定的 output
- 來源上限 128 MiB; OCR 是辨識文字, confidence 不等於欄位規格正確率, 表格關係與圖片版面仍需回看原始文件
- 不處理 Notion 同步, 不執行 Git 歷史操作, 不取代 compiler 或測試
- 原有 CLI 繼續使用, `source_audit_extract` 的預設行為維持不變

## 驗證

```text
python -m unittest discover -s tests -p test_document_mcp.py -v
python -m mcp_tools.verify_document_mcp
```

Windows/macOS/Linux 的 Runtime 與 wheels 需分別安裝; 實測結果以交付紀錄為準, 不因使用 pathlib 即宣稱已跨平台驗證
