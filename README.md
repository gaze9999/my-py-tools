# My Py Tools

可攜式 Python 工具集合，不綁定特定交易碼或專案名稱。下載或 clone 此 repository 後，可直接從根目錄執行工具。需要共用路徑設定時，可在根目錄自行建立 `.env`；此檔僅保留在本機，命令列參數會覆蓋其中的預設值。

所有工具預設為唯讀。`guarded_markdown_update.py` 只有在明確提供 `--write` 後才會寫入單一本機 Markdown；`cleanup_work_artifacts.py` 只有在提供 `--apply` 後才會隔離候選檔案，永久清除隔離區還需另外使用 `--purge-quarantine`。工具不會呼叫遠端文件服務、不會自行安裝相依套件，也不會取代原生編譯、型別檢查或瀏覽器測試。

## 一次性安裝選用相依套件

`source_audit_extract.py` 與 `tokenizer.py` 需要第三方套件；其餘工具只使用 Python 標準函式庫。請先安裝 Python 3.10 以上，再於本目錄執行對應指令。

### Windows

```powershell
py -X utf8 -m pip install --requirement .\requirements.txt
```

若沒有 Python Launcher，請將 `py` 換成目標 `python.exe` 的完整路徑。

### macOS（Homebrew）

```sh
brew install python
python3 -m pip install --requirement ./requirements.txt
```

### Debian／Ubuntu Linux

```sh
sudo apt-get update
sudo apt-get install --yes python3 python3-pip
python3 -m pip install --user --requirement ./requirements.txt
```

### Fedora／RHEL Linux

```sh
sudo dnf install --assumeyes python3 python3-pip
python3 -m pip install --user --requirement ./requirements.txt
```

安裝後可驗證選用相依套件：

```sh
python3 -c "import openpyxl, pdfplumber, pypdf; print('dependencies OK')"
```

Windows 請將上例的 `python3` 換成 `py -X utf8`。

## 工具用途

| 工具 | 用途 | 主要輸入 | 結果與邊界 |
| --- | --- | --- | --- |
| `component_inventory.py` | 列出 Nx 元件、擁有專案、伴隨 HTML／SCSS、selector 與 custom element 註冊 | 查詢字、`--project`、`--changed` | 導航用清單；不判定業務契約或修改程式碼 |
| `change_impact_report.py` | 彙整 Git 未提交變更，標示 selector、Input／Output、CustomEvent 等公開契約候選 | `TOOL_GENERATOR_ROOT` 或 `--root` | JSON 摘要；標示候選不代表已確認相容性 |
| `form_contract_check.py` | 比對明確宣告的表單 control 名稱、TypeScript 與 HTML `formControlName` | `--contract` 或 `TOOL_CONTRACT_FILE` | 只驗證名稱存在；業務規則仍須由原始契約及測試確認 |
| `generator_preflight.py` | 在執行產生器前，搜尋跨目錄是否已有 identifier／selector | `--identifier`、選用 `--selector` | 發現碰撞即以 exit code 1 停止；不自行刪檔、合併或產生檔案 |
| `markdown_semantic_diff.py` | 比對兩份 Markdown 的標題、清單項目與表格列 | `--left`、`--right` | 結構化差異；無法判定散文語意或遠端服務狀態 |
| `validation_evidence_index.py` | 索引既有 `run-*/results.json` 的驗證狀態 | `TOOL_VALIDATION_ROOT` 或 `--root` | 僅重整既有證據，不重跑 build、test 或 browser |
| `guarded_markdown_update.py` | 以 SHA-256、dry-run、明確 `--write` 與寫後讀回保護 Markdown 區段替換／歷史追加 | 文件 aliases、內容檔、目前 SHA | 只寫單一本機檔案；不會同步 Notion 或其他遠端文件 |
| `source_audit_extract.py` | 由 PDF／XLSX 產生可搜尋的 Markdown audit | 原始檔路徑、輸出路徑、選用 Mermaid override | 有格線的 PDF 表格與 XLSX 工作表會輸出 Markdown 表格；經來源雜湊核對的流程圖可輸出 Mermaid；原始檔才是契約來源 |
| `extract_field_contract_matrix.py` | 從 `source-audit.md` 抽取欄位契約矩陣 | `--source-markdown`、`--output-markdown`、`--title`、`TOOL_FIELD_MATRIX_*` | 僅由 Markdown 表格抽取欄位資料；輸出為可讀、可追溯的欄位列表 |
| `tokenizer.py` | 計算文字檔、`--text` 文字，或 stdin 的 token 數，優先用 tiktoken 精算，缺套件時回退估算 | `--input` / `--text` / stdin、`--encoding` | 非 tiktoken 路徑提供估算區間，不會取代正式 token 計價 |
| `cleanup_work_artifacts.py` | 預覽、隔離並依保存天數清除開發快取與中間產物 | 目前目錄或一個以上 `--root`、選用 `--include-work-dirs`／`--include-build` | 白名單掃描；保留 Git 追蹤內容及巢狀 repository，預設只預覽 |

## 工作暫存清理

清理器只使用 Python 標準函式庫，支援 Windows、macOS 與 Linux 的路徑格式。預設只預覽至少一天未修改的標準 cache；`work`、`tmp`、`temp`、`build`、`dist` 與 `*.egg-info` 必須明確選入。

```sh
# 唯讀預覽目前目錄；單獨寫 --root 也有相同效果
python cleanup_work_artifacts.py
python cleanup_work_artifacts.py --root

# 唯讀預覽指定目錄
python cleanup_work_artifacts.py --root /path/to/project

# 將候選項目移到可復原的隔離區
python cleanup_work_artifacts.py --root /path/to/project --include-work-dirs --include-build --apply

# 永久刪除隔離超過七天的批次
python cleanup_work_artifacts.py --purge-quarantine --older-than-days 7
```

預設的 manifest、逐筆 JSONL log 與隔離內容位於 `~/.work-artifact-cleaner/`。可用 `--output-dir` 改到其他位置，或用 `--min-age-days 0` 納入剛產生的候選。隔離仍佔用磁碟空間，只有 purge 後才會真正釋放容量。

`form_contract_check.py` 的契約請從 `contracts/forms.example.json` 複製後建立。它刻意要求明確欄位清單，不會從 PDF、試算表或現有程式碼猜測規則。

影像型流程圖請以 `TOOL_DIAGRAM_FILE` 指定 JSON override。每筆需含 `page` 與完整 `mermaid` 字串；`source_sha256` 必須等於目前 PDF 雜湊。工具不會自行從圖片猜測節點或箭頭，來源改版時會拒絕套用舊圖。

## `.env` 欄位說明

| 欄位 | 說明 |
| --- | --- |
| `TOOL_COMPONENT_ROOT` | Nx workspace 根目錄，供元件盤點與表單契約檢查使用 |
| `TOOL_CONTEXT_FILE` | 受保護 Markdown 更新工具的 context 文件路徑 |
| `TOOL_PROGRESS_FILE` | 受保護 Markdown 更新工具的 progress 文件路徑 |
| `TOOL_HISTORY_FILE` | 受保護 Markdown 更新工具的 append-only history 文件路徑 |
| `TOOL_HISTORY_NAMESPACE` | History HTML marker 的命名空間，限英數、點、底線與連字號 |
| `TOOL_PDF_SOURCE` | 原始 PDF 路徑，供 audit 抽取使用 |
| `TOOL_XLSX_SOURCE` | 原始 XLSX 路徑，供 audit 抽取使用 |
| `TOOL_PDF_OUTPUT` | PDF audit Markdown 輸出路徑 |
| `TOOL_XLSX_OUTPUT` | XLSX audit Markdown 輸出路徑 |
| `TOOL_FIELD_MATRIX_SOURCE` | 欄位矩陣抽取來源 Markdown，預設 `../ref/source-audit.md` |
| `TOOL_FIELD_MATRIX_OUTPUT_DIR` | 欄位矩陣輸出目錄，預設 `../outputs` |
| `TOOL_FIELD_MATRIX_OUTPUT` | 欄位矩陣完整輸出檔案，會優先於 `OUTPUT_DIR` |
| `TOOL_FIELD_MATRIX_TITLE` | 欄位矩陣輸出標題預設文字 |
| `TOOL_DIAGRAM_FILE` | 選用 Mermaid override JSON；內容需對應目前 PDF SHA-256 |
| `TOOL_CONTRACT_FILE` | 選用的表單契約 JSON 路徑；未設定時需提供 `--contract` |
| `TOOL_GENERATOR_ROOT` | 產生器 preflight 與變更影響報告掃描的跨目錄根目錄 |
| `TOOL_VALIDATION_ROOT` | 驗證 evidence 的 `run-*` 目錄父層 |
| `TOOL_TOKENIZER_ENCODING` | `tokenizer.py` 的預設 tiktoken encoding；預設 `cl100k_base` |
| `TOOL_TOKENIZER_ASCII_CHARS_PER_TOKEN` | `tokenizer.py` fallback 估算的 ASCII 字元 / token 下界設定 |
| `TOOL_TOKENIZER_NONASCII_CHARS_PER_TOKEN` | `tokenizer.py` fallback 估算的非 ASCII 字元 / token 下界設定 |

相對路徑一律以 `.env` 所在目錄為基準；不支援 shell 展開、行尾註解或重複 key。
