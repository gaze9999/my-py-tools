# My Py Tools

以 Python 3.10+ 執行的本機工具集合, 用於 Angular/Nx 程式碼盤點, 來源文件 audit 抽取, Markdown 安全更新, 開發產物清理與驗證證據整理

工具依用途分在不同資料夾, 從 repository 根目錄以 `python -m <分類>.<工具>` 執行, 輸入與輸出路徑由 CLI 提供或從明確輸入與目前目錄安全推導, 不依賴 `.env` 綁定特定專案或個人路徑

## 安裝

大多數工具只使用 Python 標準函式庫, 文件抽取與精確 token 計算需安裝選用套件

```powershell
python -m pip install --requirement .\requirements.txt
```

若 Windows 環境使用 Python Launcher, 可改用 `py -X utf8 -m pip install --requirement .\requirements.txt`

各格式的相依套件如下

| 功能 | 套件 |
| --- | --- |
| PDF audit | `pypdf`, `pdfplumber` |
| XLSX audit | `openpyxl` |
| DOCX audit | `python-docx` |
| PPTX audit | `python-pptx` |
| 精確 token 計算 | `tiktoken`, 缺少或 encoding 無效時自動改用估算 |
| CSV, TXT 與其他工具 | Python 標準函式庫 |

## 資料夾與工具

| 資料夾 | 工具 | 詳細文件 |
| --- | --- | --- |
| `angular/` | Nx component 盤點, form contract 檢查, generator collision preflight, Git change impact | [Angular 與 Nx 工具](docs/angular-tools.md) |
| `audit/` | PDF, XLSX, DOCX, PPTX, CSV, TXT audit, 欄位契約矩陣 | [來源文件 audit 工具](docs/audit-tools.md) |
| `markdown/` | Markdown semantic diff, SHA-256 guarded update | [Markdown 工具](docs/markdown-tools.md) |
| `maintenance/` | cache 隔離清理, Git history identity rewrite | [維護工具](docs/maintenance-tools.md) |
| `text/` | token 計數與 fallback 估算 | [文字與驗證工具](docs/text-validation-tools.md) |
| `validation/` | `run-*/results.json` 驗證證據索引 | [文字與驗證工具](docs/text-validation-tools.md) |
| `shared/` | fail-open `.env` 變數讀取與驗證 | [設定與 fallback](docs/configuration.md) |
| `tests/` | 標準函式庫 `unittest` 測試 | [測試方式](docs/testing.md) |

## 快速開始

單一文件輸入, 預設在來源旁產生同名 `.md`

```powershell
python -m audit.source_audit_extract "C:\path\spec.docx"
```

多個混合格式輸入, 各自輸出至同一資料夾

```powershell
python -m audit.source_audit_extract spec.pdf api.xlsx notes.txt --output-dir .\audit-output
```

多個來源合併成單一 audit

```powershell
python -m audit.source_audit_extract spec.pdf api.xlsx --combine-output .\combined-audit.md
```

盤點目前 Nx workspace 的 components

```powershell
python -m angular.component_inventory --root C:\path\workspace --json
```

預覽目前目錄可隔離的 cache, 不移動任何檔案

```powershell
python -m maintenance.cleanup_work_artifacts
```

每支工具都支援 `--help`

```powershell
python -m audit.source_audit_extract --help
```

## `.env`

`.env` 是選用設定, 只保存非路徑預設值, 目前支援 history marker namespace, 欄位矩陣標題, tokenizer encoding 與 fallback 比率

需要自訂時可先複製 `.env.example` 為 `.env`, `.env` 已由 Git 忽略

來源檔, 自訂輸出檔, repository root 與掃描目錄不從 `.env` 讀取, 詳細預設值、優先序與錯誤 fallback 見 [設定與 fallback](docs/configuration.md)

## 安全邊界

- 多數工具唯讀, 或只寫入明確指定的輸出檔
- `markdown.guarded_markdown_update` 預設 dry-run, 需 `--write` 才會更新單一目標檔
- `maintenance.cleanup_work_artifacts` 預設 preview, 需 `--apply` 才會移至 quarantine, purge 需另外明確指定
- `maintenance.rewrite_git_history` 會改寫 commit SHA, 執行前要求乾淨 worktree, 建立 Git bundle 並要求輸入 `REWRITE`, 不會自行 push
- audit Markdown 只供搜尋與稽核定位, 原始文件仍是權威來源

## 驗證

```powershell
python -m unittest discover -s tests -v
python -m compileall -q angular audit maintenance markdown shared text validation
```

已涵蓋 CLI help, `.env` fail-open, Angular/Nx fixture, Markdown dry-run, cleanup preview, tokenizer fallback, validation index, 單/多來源 audit 與 XLSX/DOCX/PPTX/CSV/TXT 輸出, PDF 另以真實文件 dry-run 驗證
