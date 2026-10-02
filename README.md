# My Py Tools

目前版本 `0.3.0`; 這是一套以 Python 3.10+ 執行的本機工具, 用於 Angular/Nx 程式碼盤點, 常用文件轉 Markdown, Markdown 安全更新, 開發產物清理與驗證證據整理

工具依用途分在不同資料夾, 從 repository 根目錄以 `python -m <分類>.<工具>` 執行, 輸入與輸出路徑由 CLI 提供或從明確輸入與目前目錄安全推導, 不依賴 `.env` 綁定特定專案或個人路徑

## 安裝

CLI 工具的文件抽取與精確 token 計算需安裝選用套件

```powershell
python -m pip install --requirement .\requirements.txt
```

若 Windows 環境使用 Python Launcher, 可改用 `py -X utf8 -m pip install --requirement .\requirements.txt`

各格式的相依套件如下

| 功能 | 套件 |
| --- | --- |
| PDF 轉 Markdown | `pypdf`, `pdfplumber` |
| XLSX 轉 Markdown | `openpyxl` |
| DOCX 轉 Markdown | `python-docx` |
| PPTX 轉 Markdown | `python-pptx` |
| 精確 token 計算 | `tiktoken`, 缺少或 encoding 無效時自動改用估算 |
| CSV, TXT 與其他工具 | Python 標準函式庫 |

從原始碼執行 GUI 時另外安裝 `requirements-gui.txt`; 一般使用者可下載已包含 Python 執行環境的 Windows 或 macOS 發行包

## 資料夾與工具

| 資料夾 | 工具 | 詳細文件 |
| --- | --- | --- |
| `angular/` | Nx 元件盤點, 表單欄位規格檢查, generator 衝突預檢, Git 變更影響報告 | [Angular 與 Nx 工具](docs/angular-tools.md) |
| `documents/` | PDF, XLSX, DOCX, PPTX, CSV, TXT 轉 Markdown, 欄位矩陣擷取, Markdown 抽出版定位 | [文件處理工具](docs/document-tools.md) |
| `markdown/` | Markdown 結構檢查與差異, SHA-256 保護更新 | [Markdown 工具](docs/markdown-tools.md) |
| `maintenance/` | 快取隔離清理, 環境一致性檢查, Git 歷史身分改寫 | [維護工具](docs/maintenance-tools.md) |
| `text/` | token 計數與備援估算 | [文字與驗證工具](docs/text-validation-tools.md) |
| `validation/` | `run-*/results.json` 驗證證據索引 | [文字與驗證工具](docs/text-validation-tools.md) |
| `shared/` | 可容錯的 `.env` 變數讀取, 版本與核心載入 | [設定與備援機制](docs/configuration.md) |
| `packages/` | 用途獨立的可重用 Python 核心套件 | [工作區檢查工具包](docs/python-workspace-core.md) |
| `gui/` | React 桌面 GUI, Python 工具橋接與 Windows/macOS 發行包建置 | [本機 GUI](docs/gui.md) |
| `tests/` | 標準函式庫 `unittest` 測試 | [測試方式](docs/testing.md) |

## 可重用 Python 工具包

文件與 Markdown 核心可建置為 `my-py-document-core` wheel; 工作區一致性與驗證證據核心則建置為獨立的 `my-py-workspace-core` wheel, 兩者都提供固定 API 給 MCP 或其他 Python 工具使用, runtime 不依賴此 repo 的位置, 原有 CLI 繼續可用; 詳見 [可重用文件工具包](docs/python-document-core.md) 與 [工作區檢查工具包](docs/python-workspace-core.md)

## 快速開始

一般使用者請下載 Windows 或 macOS 發行包, 解壓後開啟 `MyPyTools.exe` 或 `My Py Tools.app`; 發行包內含 Python 與工具相依套件, 不需要另外安裝 Python; Windows 需有 Microsoft Edge WebView2 Runtime, macOS 使用系統 WebKit

開發者可從原始碼啟動; 先安裝 Python 3.10+ 與 Node.js 22+, 再安裝相依套件並建置 React 畫面; Windows 開發版可直接執行 `launch-gui.pyw` 在背景啟動, macOS 可由 Terminal 執行 `python -m gui.launcher`

```powershell
python -m pip install --requirement .\requirements-gui.txt
npm --prefix .\gui\frontend ci
npm --prefix .\gui\frontend run build
python -m gui.launcher
```

要在目前作業系統建置獨立發行包, 再安裝 `requirements-build.txt` 並執行 `python -m gui.packaging.build`; Windows 需在 Windows 建置, macOS 需在 Mac 建置

GUI 支援多文件拖曳, 預設在來源旁產生同名 `.md`; 也可指定輸出資料夾, 合併成單一 Markdown, 或先執行 dry-run; 每項工具在 GUI 都會說明用途, 輸入, 輸出與執行前注意事項; `local_documents` MCP 仍由 `codex-setup` 管理; 詳細操作與新增工具方式見 [本機 GUI](docs/gui.md)

單一文件輸入, 預設在來源旁產生同名 `.md`

```powershell
python -m documents.convert_to_markdown "C:\path\spec.docx"
```

多個混合格式輸入, 各自輸出至同一資料夾

```powershell
python -m documents.convert_to_markdown spec.pdf api.xlsx notes.txt --output-dir .\markdown-output
```

多個來源合併成單一 Markdown

```powershell
python -m documents.convert_to_markdown spec.pdf api.xlsx --combine-output .\combined.md
```

盤點目前 Nx 工作區的元件

```powershell
python -m angular.component_inventory --root C:\path\workspace --json
```

預覽目前目錄可隔離的快取, 不移動任何檔案

```powershell
python -m maintenance.cleanup_work_artifacts
```

每支工具都支援 `--help`

```powershell
python -m documents.convert_to_markdown --help
```

## `.env`

`.env` 是選用設定, 只保存非路徑預設值, 目前支援歷史標記命名空間, 欄位矩陣標題, tokenizer 編碼與備援估算比率

需要自訂時可先複製 `.env.example` 為 `.env`, `.env` 已由 Git 忽略

來源檔, 自訂輸出檔, repository 根目錄與掃描目錄不從 `.env` 讀取; 詳細預設值, 優先序與錯誤備援見 [設定與備援機制](docs/configuration.md)

## 安全邊界

- 多數工具唯讀, 或只寫入明確指定的輸出檔
- `markdown.guarded_markdown_update` 預設 dry-run, 需 `--write` 才會更新單一目標檔
- `maintenance.cleanup_work_artifacts` 預設只預覽, 需 `--apply` 才會移至隔離區, 永久清除需另外明確指定
- `maintenance.rewrite_git_history` 會改寫 commit SHA, 執行前要求乾淨 worktree, 建立 Git bundle 並要求輸入 `REWRITE`, 不會自行 push
- 轉換後的 Markdown 只供搜尋與定位, 原始文件仍是權威來源

## 版本與發布

repository 版本由 `VERSION` 管理; 文件核心與工作區核心依用途各自使用獨立套件版本, release manifest 會記錄實際組合

```powershell
python scripts/release.py prepare --dry-run
```

準備與 GitHub Release 的安全檢查, asset 結構及明確確認流程見 [版本與發布](docs/releases.md); `codex-setup` 的 Skills / MCP 發布用途不同, 保留獨立流程

## 驗證

```powershell
python -m unittest discover -s tests -v
python -m compileall -q angular documents gui maintenance markdown packages shared src text validation
```

已涵蓋 CLI help, GUI 工具清單與實際 subprocess 執行, `.env` 容錯處理, Angular/Nx 測試資料, Markdown dry-run, 清理預覽, tokenizer 備援估算, 驗證索引, 單一與多來源文件轉換, 以及 XLSX/DOCX/PPTX/CSV/TXT 輸出; PDF 另以真實文件 dry-run 驗證
