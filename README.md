# My Py Tools

目前儲存庫版本 `0.4.1`, 提供可獨立使用的 Python 工具, 涵蓋常用文件轉 Markdown、Markdown 安全更新、Angular/Nx 程式碼盤點、開發產物清理與驗證證據整理

根目錄的操作入口統一使用 `launch-xxx` 命名, 工具原始碼集中在 `src/`, 相依清單與選用設定集中在 `setup/`, README、版本、Python 套件與 Git 設定仍保留在根目錄

| 使用方式 | Windows 原始碼版 | Windows 免安裝版 | macOS 免安裝版 |
| --- | --- | --- | --- |
| 終端機工具 | `launch-cli.cmd <工具> <參數>` | `MyPyToolsCLI/launch-cli.cmd <工具> <參數>` | `MyPyToolsCLI/launch-cli <工具> <參數>` |
| 瀏覽器介面 | `launch-web.cmd` | `MyPyToolsCLI/launch-web.cmd` | `MyPyToolsCLI/launch-cli --web` |
| 桌面視窗 | `launch-gui.cmd` | `launch-gui-<version>-windows-x64.exe` | `launch-gui.app` |

Windows 原始碼版提供同名 PowerShell 入口 `launch-cli.ps1`、`launch-web.ps1`、`launch-gui.ps1`, CMD 仍保留, CLI 免安裝包另外附上 CLI / Web 的 PS1, GUI 發行版直接開啟單一 EXE, 詳見 [PowerShell 啟動教學](docs/gui.md#powershell-啟動)

## CLI 入口

Windows 與 macOS 各自提供獨立的 CLI、GUI 免安裝包, 兩者分開下載與啟動, CLI 包支援終端機及瀏覽器, 內含共用網頁介面但不含 WebView2, 瀏覽器模式使用電腦既有的瀏覽器

CLI 免安裝包需保留整個 `MyPyToolsCLI/` 資料夾, Windows 在終端機執行 `MyPyToolsCLI\launch-cli.exe --list`, macOS 執行 `./MyPyToolsCLI/launch-cli --list`, 工具參數與下方的原始碼入口相同

原始碼版需要 Python 3.10+, Windows 也可使用 Python 3.14

```powershell
.\launch-cli.cmd --list
.\launch-cli.cmd documents.convert_to_markdown "C:\path\spec.docx"
.\launch-cli.cmd document-to-markdown --help
```

Windows 本機 CLI 使用 `launch-cli.cmd`, 優先使用專案的 `.venv-gui` Python, 不存在時使用 PATH 中的 Python, macOS 原始碼版使用 `python launch-cli.py`, 呼叫時可以在任意工作目錄使用啟動檔的完整路徑, 輸入與輸出仍依目前工作目錄及明確參數解析

PDF、Office 文件及精確 token 計算需要選用相依套件, 由開發環境安裝, 不在每次啟動時自動下載

```powershell
python -m pip install -r setup/requirements.txt
```

多個來源可分別輸出或合併成單一 Markdown

```powershell
python launch-cli.py documents.convert_to_markdown spec.pdf api.xlsx --output-dir markdown-output
python launch-cli.py documents.convert_to_markdown spec.pdf api.xlsx --combine-output combined.md
```

## GUI 入口

瀏覽器與桌面視窗使用同一套 React + Workbench UI 介面, 工具用途、分類、語言與執行能力相同, Windows 原始碼版雙擊 `launch-web.cmd` 開啟瀏覽器, `launch-gui.cmd` 開啟桌面視窗, `launch-cli.cmd` 保留終端機操作

瀏覽器模式僅在 `127.0.0.1` 提供本機服務, 不上傳文件, 使用原生檔案挑選視窗取得來源路徑, 挑選視窗不可用時可輸入完整路徑, 瀏覽器拖曳會請使用者再挑選原始檔, 桌面視窗可直接拖曳原地轉換, 詳見 [GUI 教學](docs/gui.md)

從原始碼執行使用 `launch-gui.pyw`, Windows 可雙擊 `launch-gui.cmd`, macOS 可執行 `python launch-gui.pyw`, 開發環境需要先依 [GUI 教學](docs/gui.md) 安裝與建置

介面的共用樣式與元件由獨立的 `workbench-ui` 儲存庫提供, `my-py-tools` 只保留工具操作流程、Python 串接及打包入口, 建置時從明確指定的 Workbench UI 路徑讀取資產, 成品不依賴這個路徑

Windows GUI 提供 `launch-gui-<version>-windows-x64.exe`, 單一 EXE 內含 Python、工具相依套件與 Fixed Version WebView2, 雙擊即可使用, 不需要安裝 Python、Node.js 或 WebView2, 不會另開 CLI 主控台視窗, macOS 打包版內含 Python 與套件, 使用系統 WebKit

Windows EXE 啟動時會解壓到自己的暫存資料夾, 正常結束後清理, 需要本機可寫入的暫存空間, 請勿使用系統管理員身分執行, GUI 只提供視窗入口, 命令列使用者另外下載 CLI 包

本機最新封裝測試的 GUI 轉檔與語言切換已通過, 但單檔 EXE 的退出清理逾時並留下 WebView2 檔案, 尚未確認原因, 不提供這份本機測試 EXE 作為正式下載, 正式 CLI / GUI 附件須通過各平台 Release CI 驗證

正式來源 ZIP、核心 wheel 與 CLI / GUI 免安裝產物都由 Release CI 建置, 所有工作通過驗證後才上傳附件, 本機可只做相關單元測試與設定檢查, 不需要封裝測試, 自動發布所需的 Workbench UI 讀取權限與固定版 Runtime 設定見 [發布教學](docs/releases.md)

[v0.3.2 的 Windows GUI 包](https://github.com/gaze9999/my-py-tools/releases/tag/v0.3.2) 仍使用系統 WebView2, 新的內含 Runtime 打包方式不會改寫既有發布檔, 獨立 CLI 與 macOS 新包須完成 CI 設定及原生驗證後才提供下載, 來源 ZIP 與核心 wheel 可獨立發布

網頁與桌面介面預設繁體中文, 可切換英文並記住選擇, 中文翻譯缺漏時使用英文備援, 保留來源旁輸出、指定資料夾及合併輸出選項

## 分類與教學

| 原始碼 | 用途 | 教學 |
| --- | --- | --- |
| `src/angular/` | 元件盤點、表單欄位規格檢查、generator 預檢與 Git 變更影響 | [Angular / Nx](docs/angular-tools.md) |
| `src/documents/` | 文件轉 Markdown、欄位矩陣擷取與抽出版定位 | [文件處理](docs/document-tools.md) |
| `src/markdown/` | 結構檢查、差異與 SHA-256 保護更新 | [Markdown](docs/markdown-tools.md) |
| `src/maintenance/` | 產物隔離清理、環境比對與 Git 歷史身分改寫 | [維護](docs/maintenance-tools.md) |
| `src/text/`, `src/validation/` | token 計數與既有驗證證據索引 | [文字與驗證](docs/text-validation-tools.md) |
| `src/shared/` | 選用變數、版本與核心載入 | [設定](docs/configuration.md) |
| `src/gui/` | 工具操作流程、Workbench UI 串接與打包 | [GUI](docs/gui.md) |
| `src/scripts/` | 來源 ZIP、核心 wheel 與明確確認的發布流程 | [發布](docs/releases.md) |
| `src/distribution/` | 獨立 CLI 免安裝包的原生建置 | [發布](docs/releases.md) |
| `src/my_py_document_core/`, `packages/workspace_core/` | 用途獨立的可重用 Python 核心 | [文件核心](docs/python-document-core.md), [工作區核心](docs/python-workspace-core.md) |
| `tests/` | 可重現的測試程式碼, 保留於 Git | [測試](docs/testing.md) |
| `setup/` | CLI、GUI、打包相依清單與 `.env.example` | [設定](docs/configuration.md) |

新增工具放在 `src/<用途>/`, 模組名稱仍是 `<用途>.<工具>`, CLI 與 GUI 共用工具清單, 不再從根目錄使用舊的 `python -m <用途>.<工具>` 命令, 新增與翻譯方式見 [GUI 教學](docs/gui.md)

## 設定與安全

`setup/.env` 是選用的非路徑變數設定, 缺少或無效時使用安全預設值, 可複製 `setup/.env.example` 後自訂, 輸入、輸出及專案路徑仍以 CLI 參數為準

多數工具唯讀或只寫入指定輸出, Markdown 更新需要 `--write`, 產物清理預設預覽, Git 歷史改寫會建立備份並再次要求確認, 轉換後的 Markdown 供搜尋與定位, 原始文件仍是權威來源

Git 工具需要 Git, 發布工具需要完整原始碼、開發用 Python 與已登入的 GitHub CLI, 免安裝 GUI 不會把這些開發工具偽裝成內建功能, MCP 與 Skills 仍由 `codex-setup` 管理

## 驗證與發布

```powershell
python -m unittest discover -s tests -t . -v
python launch-cli.py scripts.release prepare --dry-run
```

儲存庫版本由 `VERSION` 管理, 文件核心及工作區核心維持獨立套件版本, 詳細安全檢查與發布操作見 [發布教學](docs/releases.md), 本機產物不會自動 commit、push 或發布
