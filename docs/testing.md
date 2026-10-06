# 測試方式

專案測試使用 Python 標準函式庫 `unittest`, Office 測試資料會使用 `setup/requirements.txt` 中的文件擷取套件

```powershell
python -m unittest discover -s tests -t . -v
```

目前自動測試涵蓋

- GUI 自動發現的全部可執行 module 之 `--help` 可安全執行, `local_documents` 的 MCP 層與驗證由 `codex-setup` 管理, 不納入本 GUI
- GUI 工具清單, 路徑參數解析與實際 subprocess 輸出
- `launch-cli.cmd` / `launch-web.cmd` 在任意工作目錄的參數轉送與 exit code
- PowerShell 5.1 / 7 的 PS1 入口, 包含繁中、空白、引號與尾端反斜線參數, GUI 的 Hidden / 不等待設定使用 mock 檢查
- 瀏覽器的共用頁面、本機 session / Host / Origin 檢查、API 白名單、原始檔案路徑轉檔與停止服務
- `.env` 無效行, 重複 key, 變數展開, process environment 覆寫與備援處理
- Angular/Nx 元件盤點, 表單欄位規格, generator 衝突與 Git 變更影響測試資料
- Markdown 結構差異與保護取代的 dry-run
- tokenizer 精確計算失敗時的備援估算
- 驗證證據索引與清理預覽
- 欄位規格矩陣的表頭與分隔列
- 文件轉 Markdown 工具的單一輸入, 多輸入多輸出, 多輸入單輸出與輸出衝突
- XLSX, DOCX, PPTX, CSV, TXT 測試資料與圖表覆寫 hash 檢查

語法與 import 檢查

```powershell
python -m compileall -q src packages tests launch-cli.py launch-gui.pyw
```

PDF 擷取器需用實際 PDF 做 `--dry-run`, 因為文字層與表格重建結果會依來源結構而異

```powershell
python launch-cli.py documents.convert_to_markdown C:\path\spec.pdf --dry-run --extracted-at 2026-09-22T14:30:15
```

測試通過只代表這些明確案例, 不表示未提供的文件版面, OCR, Angular 動態中繼資料或遠端 Git 操作已驗證

## Windows 程序稽核 / 清理

```powershell
python -m unittest tests.test_windows_process_audit -v
```

預設只執行模擬資料測試, 涵蓋預設稽核、所有參數遮蔽、PID 重用、ownership / session 變化、父子關係變動、Codex / MCP / 服務保護、快照期限、覆寫保護、缺漏保留、未加 `--apply` 不開啟終止 handle, 以及兩次核對後才終止的呼叫順序

只有明確開啟下列測試才建立並終止真實隔離程序, 不操作電腦上既有的程序, 不需要系統管理員權限

```powershell
$env:MY_PY_TOOLS_PROCESS_LIVE_TEST = '1'
try {
    python -m unittest tests.test_windows_process_audit.IsolatedWindowsProcessTests -v
} finally {
    Remove-Item Env:MY_PY_TOOLS_PROCESS_LIVE_TEST
}
```

真實測試建立短暫 bootstrap 及自己專用的 sleep worker, bootstrap 正常退出後稽核 worker, 驗證無 ownership 不成為候選、預覽仍存活、明確選取及套用後退出, 最後只用已持有的自建 worker handle 清理, 不做整棵程序樹終止, 不驗證第三方服務的所有命令形式或跨平台封裝

Markdown validator focused checks:

```powershell
python -m unittest discover -s tests -t . -p test_validate_structure.py -v
python launch-cli.py markdown.validate_structure --help
```

涵蓋標題跳號, fence closing, hard break, 版本 INFO, exit codes, `-I -S` standalone 執行及 snapshot 產生一致性, 不代表所有 Markdown syntax 已驗證

## 共用網頁介面與免安裝入口

```powershell
python -m unittest tests.test_browser_app tests.test_entrypoints_packaging tests.test_release_tools -v
python -m unittest tests.test_portable_packaging -v
npm --prefix src/gui/frontend test
python launch-cli.py distribution.smoke_cli C:\path\MyPyToolsCLI\launch-cli.exe
```

前端測試包含瀏覽器 RPC、挑選視窗失敗時的路徑輸入備援與語言翻譯, `distribution.smoke_cli` 以移除 Python 環境變數及縮減 PATH 的環境啟動免安裝 CLI, 驗證共用頁面、內建工具程序轉檔及正常停止, 不啟動互動式檔案挑選視窗

Release CI 分別驗證三平台 CLI 的終端機、瀏覽器與 GUI 桌面入口, 本機只驗證目前平台, 桌面拖曳事件與瀏覽器挑選視窗的模擬測試不等於檔案總管 / Finder 實際拖曳或原生檔案挑選的端到端驗證

Windows 單一 EXE 測試涵蓋內嵌 payload SHA-256 / CRC、必要 GUI / worker / WebView2 / 頁面、安全路徑、重複與大小寫衝突、符號連結、覆寫保護、x64 無主控台格式, 啟動器測試確認等待內部 GUI 結束及重設子程序 DLL 環境, EXE 結構測試需要 `setup/requirements-build.txt` 的 PyInstaller, 未安裝時會明確略過

本機可執行 `launch-gui-<version>-windows-x64.exe --smoke-test`, 檢查 `%LOCALAPPDATA%/MyPyTools/logs/desktop-smoke.json` 的時間與 `passed`, 並依 `portable-launcher.log` 本次記錄的解壓路徑確認結束後已清理, 不用舊的驗證結果當成本次成功, 不發布本機測試產物
