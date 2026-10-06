# 本機網頁與桌面介面

My Py Tools 使用同一套 React + Workbench UI 網頁介面, `launch-web` 透過既有瀏覽器操作, `launch-gui` 透過 pywebview 桌面視窗操作, 兩者呼叫同一份 Python 工具 API, `launch-cli` 另保留終端機指令

原始碼集中在 `src/`, 工具依它底下第一層功能資料夾分類, 發行版在建置時固定工具清單與說明, 根目錄只提供 CLI 與 GUI 操作入口

`local_documents` MCP 由 `codex-setup` 管理, 文件處理 CLI 核心保留在 `my-py-tools`

## 一般使用者

Windows 與 macOS 都提供分開的 GUI 與 CLI 免安裝包, 本教學說明 GUI, CLI 操作與下載分類見 [發布教學](releases.md), Windows GUI 的使用者入口是單一 `launch-gui-<version>-windows-x64.exe`, 背景工具程序封在 EXE 內, 不需另外下載

正式產物由 GitHub Actions 的 `Release portable desktop applications` 在 Windows 與 Mac runner 分別建置, 所有平台的建置與原生 GUI 檢查通過後才一起上傳至已發布的 Release, 本機打包只用於測試

Windows EXE 內含 Python、文件處理套件及 Microsoft Fixed Version WebView2, 下載到本機磁碟後雙擊即可使用, 不需安裝相依套件, 不需搭配 CMD、PS1 或 VBS, 請勿使用系統管理員身分執行

每次啟動會先解壓到該次程序專用的暫存資料夾, 驗證內嵌 ZIP 的 SHA-256、CRC、必要檔案與安全路徑後啟動 GUI, 啟動器會等待 GUI 結束, 正常結束後由 PyInstaller 清理, 當機、強制終止或斷電可能留下暫存檔, 相較資料夾版會增加啟動時間, 詳見 [PyInstaller 單一執行檔機制](https://pyinstaller.org/en/stable/operating-mode.html#how-the-one-file-program-works)

請保留足夠本機暫存空間, 至少容納內嵌 ZIP、解壓後的工具與 WebView2, 資訊清單的 `payload.size` 與 `payload.unpacked_size` 分別記錄前兩項所需容量, 另外仍需預留啟動器及系統運作空間, 多個視窗會各自解壓, 暫存目錄不可設在網路磁碟或 UNC 路徑, 文件輸出仍在使用者指定位置, 不會放進程式暫存資料夾

Windows 10 的 Fixed Runtime 需要 AppContainer 讀取及執行權限, 啟動時只對包內 `WebView2` 資料夾授予 Microsoft 指定的兩個 AppContainer SID 權限, 失敗時會提示改放可寫入的本機資料夾, 不會安裝 Runtime 或修改系統 WebView2, 詳見 [Microsoft 散布規則](https://learn.microsoft.com/en-us/microsoft-edge/webview2/concepts/distribution)

macOS ZIP 內含 Python 與工具套件, 使用系統 WebKit, 解壓縮後開啟 `launch-gui.app`, Apple Silicon 與 Intel 分別下載 arm64 與 x64 版, 首次開啟未簽章的應用程式時, 請在 Finder 按右鍵並選擇 `打開`

本機記錄檔儲存在 Windows `%LOCALAPPDATA%/MyPyTools/logs`, macOS `~/Library/Logs/MyPyTools`, macOS 發行包分成 Apple Silicon 與 Intel 版本. 發行包目前未簽章與公證, 交付前應由維護者核對資訊清單中的 SHA-256

`v0.3.2` 是舊的系統 WebView2 版本, `v0.4.1` 已通過 Windows、macOS Apple Silicon 與 Intel 的雲端原生驗證, 但附件收集過多而停止發布, 新版修正只收正式成品, 不覆寫舊 Tag 或附件

## 原始碼啟動與本機測試包

開發環境需要 Python 3.10+、Node.js 22.12+、npm 及已授權的 `workbench-ui` 原始碼, 路徑由參數提供, 不寫進 `.env`, 建置資產不提交至 Git

```powershell
python -m pip install -r setup/requirements-gui.txt
node src/gui/frontend/sync-workbench.mjs --source C:\path\workbench-ui
npm --prefix src/gui/frontend ci
npm --prefix src/gui/frontend run build
python launch-gui.pyw
```

完成共用介面建置後, Windows 可選擇以下入口

```cmd
launch-cli.cmd --list
launch-web.cmd
launch-gui.cmd
```

`launch-cli.cmd` 是終端機工具, `launch-web.cmd` 是獨立的瀏覽器入口, 不必手動加 `--web`, `launch-gui.cmd` 是不另開主控台的桌面視窗入口, macOS 原始碼版分別使用 `python launch-cli.py <工具>`, `python launch-cli.py --web` 與 `python launch-gui.pyw`

瀏覽器介面包含與桌面視窗相同的工具清單、分類、用途說明、中英切換、參數與輸出, 原生檔案挑選視窗在本機 Python 程序執行, 文件不會上傳, Windows 使用系統 PowerShell / Windows Forms, macOS 使用系統 osascript, 挑選視窗失敗時可手動輸入完整本機路徑

### PowerShell 啟動

Windows PowerShell 5.1 與 PowerShell 7 可使用同名 PS1 入口, CMD 不變

```powershell
.\launch-cli.ps1 --list
.\launch-cli.ps1 documents.convert_to_markdown "C:\path with spaces\spec.docx"
.\launch-web.ps1
.\launch-gui.ps1
```

原始碼版優先使用專案 `.venv-gui` 的 Python, 其次使用 PATH, CLI 免安裝包內的 PS1 則直接使用同資料夾的執行檔, CLI 與瀏覽器入口保留呼叫端工作目錄及工具的結束代碼, 原始碼 GUI 在背景啟動且不另外開主控台, GUI 發行版直接執行單一 EXE

若個人的執行政策阻擋 PS1, 可改用 CMD, 或在確認檔案來源後使用以下單次啟動方式, 不修改 CurrentUser / LocalMachine 政策, 組織政策仍可能禁止執行

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\launch-cli.ps1 --list
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\launch-web.ps1
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\launch-gui.ps1
```

使用 PowerShell 7 時可將 `powershell.exe` 換成 `pwsh`, 不需要安裝額外啟動套件

網頁服務只綁定 `127.0.0.1`, 預設使用可用的隨機連接埠, 啟動後開啟預設瀏覽器, 開啟失敗時可手動使用終端機顯示的 URL, `launch-web.cmd --port 8765` 可指定連接埠, `--no-browser` 只啟動服務並印出 URL, `--cwd` 可設定工具的初始工作目錄

關閉瀏覽器分頁不會停止服務, 請按介面的 `停止網頁服務` 或回到啟動的終端機按 Ctrl+C, 正在執行的工具也會停止, 下次使用時重新啟動 `launch-web.cmd`

### 共用 UI 版本與載入方式

根目錄的 `workbench-ui.json` 使用共用格式記錄儲存庫與完整 commit SHA, `sync-workbench.mjs` 呼叫該版本的 `integrations/python/workbench_assets.py`, 將四個前端資產、共用載入器與 SHA-256 資訊清單準備至忽略的 `src/gui/resources/workbench/`, 不另行維護 vendor 副本, 不複製展示資料或應用程式 API

正式前端建置使用已準備且版本一致的離線資產, React 直接匯入共用 ES module 與 CSS, 不再同時執行瀏覽器按需載入器, 編譯後仍內嵌於同一份 HTML, 桌面與瀏覽器共用, 不增加網路載入或放寬 CSP, `--skip-frontend` 也會核對共用版本, 不接受舊版建置資產

本機前端開發使用 `npm --prefix src/gui/frontend run dev`, Vite 直接讀取相鄰 `workbench-ui/src`, 不產生副本, UI 修改後可重新整理頁面, Vite 只提供前端資產, 工具操作仍需既有 Python API, 完整 CLI / GUI 啟動方式維持上方入口

需要更新共用版本時, 先完成 Workbench UI 的提交與推送, 使用共用 helper 的明確更新入口, 不在一般啟動時下載或安裝, 更新失敗會保留原本的版本設定

```powershell
python ../workbench-ui/integrations/python/workbench_assets.py --project . --destination src/gui/resources/workbench --update
node src/gui/frontend/sync-workbench.mjs --source ../workbench-ui --python python
```

再提交更新後的 `workbench-ui.json`, 交由 Release CI 重新建置免安裝程式, `--update` 需要乾淨的 Workbench UI `main` 與正確的 origin, Git 認證由既有環境管理, Token 不寫入設定檔、前端或成品

本機 Windows 測試包需先從 [Microsoft 官方頁面](https://developer.microsoft.com/en-us/microsoft-edge/webview2/) 取得 x64 Fixed Version CAB, 記錄 SHA-256, 再使用安全下載與解壓縮入口, 這個入口不安裝系統元件

```powershell
python -m pip install -r setup/requirements-build.txt
python launch-cli.py gui.packaging.fetch_webview2 --url https://download.microsoft.com/path/runtime.cab --sha256 REPLACE_WITH_REVIEWED_SHA256 --output setup/runtime
python launch-cli.py gui.packaging.build --workbench-ui C:\path\workbench-ui --webview2-runtime setup/runtime/WebView2 --output-root .gui/portable-tests
```

上方 URL 與 SHA-256 是占位內容, 請改成官方實際下載連結與核對值, 已下載的 CAB 可用 `--cab C:\path\runtime.cab` 重用, 仍會核對 SHA-256, 輸出已存在時停止而不覆寫

Mac 測試包使用相同建置入口, 省略 `--webview2-runtime`, 必須在 Mac 上執行, 本機測試產物不作為正式發布附件

Windows 測試輸出只有 `launch-gui-<version>-windows-x64.exe` 與 `desktop-manifest.json`, 不保留中間 GUI 資料夾或 payload ZIP, 可在不含 Python 的 PATH 環境執行 EXE 的 `--smoke-test`, 驗證桌面顯示、串接與轉檔

正式雙平台發布設定與操作見 [發布教學](releases.md)

Windows 開發版可直接執行 `launch-gui.pyw` 或 `launch-gui.cmd`, GUI 會在背景開啟且啟動錯誤會寫入記錄檔, macOS 開發版可在終端機執行 `python launch-cli.py gui.launcher`

### 拖曳文件並在原目錄產生 Markdown

桌面視窗可從檔案總管或 Finder 將單一或多個 PDF, XLSX, DOCX, PPTX, CSV, TXT 拖到文件區, 可選擇在來源旁分別輸出, 指定資料夾分別輸出, 或合併成單一 Markdown. 也可勾選 dry-run 先檢查參數, 預設於來源旁產生同名 Markdown 檔

瀏覽器不提供拖入檔案的完整來源路徑, 因此拖入時會開啟本機挑選視窗, 請再選擇原始檔案確認路徑, 不會改成上傳暫存檔或下載 Markdown 的流程, 也可直接按 `選擇文件`

所有文件擷取都在本機完成, 拖曳不可用時仍可按 `選擇文件` 使用原生檔案挑選視窗

## 操作方式

### 選擇介面語言

首次啟動預設使用繁體中文, 可在右上角的 `語言` 選單切換為 `English`, 分類, 工具名稱, 用途說明, 表單與執行狀態會同步切換, 不會清空已選文件或執行參數

缺少中文翻譯的項目會顯示英文, 不會顯示空白. 語言選擇儲存在記錄檔資料夾的 `preferences.json`, 重啟後會沿用, 設定檔不存在, 格式錯誤或語言不支援時改回繁體中文. 儲存失敗時會顯示錯誤訊息, 當次仍可切換語言

CLI 原始輸出, 檔案內容與路徑保留原文, 作業系統的檔案挑選視窗依系統語言顯示

### 執行工具

1. 由左側分類選擇工具或搜尋工具, 主畫面會說明用途, 使用情境, 輸入, 輸出與必要套件
2. 設定工作目錄, 一般工具使用發行包內建執行環境
3. 文件轉換可拖曳或挑選多個檔案, 其他工具可在 CLI 參數區套用範例或按 `查看 Help` 閱讀說明
4. 按 `執行工具` 後, 即時輸出會顯示在下方, 有互動確認時使用 stdin 輸入欄
5. 執行時間較長時可停止處理程序, 輸出最多保留最新 2 MiB

GUI 同一時間只執行一個工具, 命令不經命令殼層執行, 模組只從掃描器建立的工具清單選擇

進度動畫表示工作仍在執行, 不代表完成百分比

## 新增工具至 GUI

在功能資料夾新增 Python CLI, 提供標準主程式執行入口, GUI 會用模組說明字串 (docstring) 的第一行作為預設摘要, 依第一層資料夾分類. 若要清楚說明實際用途, 輸入輸出與執行需求, 請在 `src/gui/catalog.py` 該工具的 `ToolSpec` 補齊 `purpose`, `inputs`, `outputs`, `requirements` 與 `warning`, 每次建置會重新產生發行版工具清單

1. 將 Python 檔放在 `src/` 的功能資料夾, 例如 `src/reports/convert_report.py` 或 `src/reports/converters/convert_report.py`
2. 提供 `main()` 或等價執行函式, 並加入標準的 `if __name__ == "__main__":` 執行入口
3. 模組頂端說明字串的第一行會成為 GUI 預設說明
4. 重新啟動 GUI, 工具會自動出現在以第一層資料夾命名的左側分類, 模組名稱會依相對路徑產生, 例如 `reports.convert_report` 或 `reports.converters.convert_report`
5. 執行 `python launch-cli.py reports.convert_report --help`, 確認 CLI 可獨立啟動且不會在顯示 Help 時執行實際工作

若新工具有語法錯誤, 編碼錯誤或檔案無法讀取, GUI 仍會啟動並在輸出區顯示未載入清單, 同時寫入 `.gui/my-py-tools-gui.log`

最小範例

```python
"""將報表轉換成指定格式"""

import argparse


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source")
    args = parser.parse_args(argv)
    print(args.source)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

需要自訂繁體中文名稱, 範例參數或風險警告時, 才在 `src/gui/catalog.py` 的 `_OVERRIDES` 增加 `ToolSpec`, 未提供覆寫資料時仍會自動出現在 GUI

工具可以在 `ToolSpec.translations` 提供 `en` 與 `zh-TW` 對應的 `name`, `description`, `purpose`, `inputs`, `outputs`, `requirements` 與 `warning`, 建置時會一起打包. 明確提供中文翻譯表時, 缺少或空白的欄位會使用英文, 範例如下

```python
ToolSpec(
    id="convert-report",
    module="reports.convert_report",
    category="Reports",
    name="報表轉換",
    description="轉換報表格式",
    translations={
        "en": {
            "name": "Convert report",
            "description": "Convert a report into the requested format",
            "purpose": "Prepare reports for another tool",
            "inputs": "Source report and output format",
            "outputs": "Converted report",
        },
        "zh-TW": {
            "name": "報表轉換",
            "description": "將報表轉換成指定格式",
        },
    },
)
```

介面共用文案集中於 `src/gui/frontend/src/i18n.js`, 英文訊息作為索引與備援文字, 中文翻譯放在 `zhTW`. 既有工具的英文說明位於 `src/gui/frontend/src/tool-translations.js`, 新工具可直接使用上述 Python 翻譯設定. 執行 `npm --prefix src/gui/frontend test` 可檢查預設語言, 中文缺漏備援與工具翻譯

以下內容不會列入 GUI

- `__init__.py`, `tests/`, `gui/`, `shared/` 與隱藏資料夾
- 沒有 `if __name__ == "__main__":` 執行入口的純函式庫
- `src/gui/catalog.py` 中 `EXCLUDED_MODULES` 明確排除的入口

開發時新增工具, 除確認 CLI 本身可用外, 也要檢查 GUI 工具清單的分類, 中文用途說明, 輸入輸出與必要條件. 使用者安裝版的工具清單在建置時固定, 重新建置發行包才會更新

已打包工具使用內建 Python. `準備 Release Assets` 與 `驗證與發布 Release` 需要完整儲存庫與開發用 Python, 因為它們會讀寫 Git / GitHub 發布相關資源, 這兩項會在工具畫面標示原始碼與執行環境需求

## 安全與備援機制

- 桌面視窗不啟動 HTTP 服務, 瀏覽器模式僅綁定本機 `127.0.0.1`, 以 HttpOnly / SameSite Cookie、Host / Origin 檢查及 API 白名單限制呼叫, 不開放區域網路存取或文件上傳
- GUI 只組合並啟動既有 CLI, 原本的 dry-run, 預覽, 雜湊檢查, 備份與確認機制仍保留, 停止按鈕會終止該次工具的子處理程序樹
- 輸出最多保留最新 2 MiB, 超過時會標示較早內容已截斷, 避免長時間工作耗盡記憶體
- 背景啟動與未處理的 GUI 回呼函式錯誤會寫入 `.gui/my-py-tools-gui.log`, 最多保留目前與前一份各 512 KiB
- Windows 單一 EXE 的解壓與啟動錯誤會寫入 `%LOCALAPPDATA%/MyPyTools/logs/portable-launcher.log`, 最多保留目前與前一份各 512 KiB, 啟動失敗另以系統視窗提示
- 拖曳無法使用時, 可改用 `選擇文件`, 包內 WebView2 缺失或 macOS WebKit 不可用時會顯示錯誤, CLI 仍可使用 `python launch-cli.py <package>.<module>` 執行
- Windows 啟動器使用無主控台模式, 執行中的 CLI 子處理程序不會另開小黑窗, 結果會顯示在 GUI 輸出區

## 本版驗證範圍

Windows 原生 GUI 自動驗證涵蓋 React 顯示, JavaScript/Python 串接, 文件轉 Markdown, 拖曳事件更新介面, 中英切換, 語言保存與已選文件保留, 兩種語言都檢查水平溢位. 前端語言測試涵蓋中文翻譯缺漏的英文備援, 本機設定測試涵蓋缺少或損壞設定檔的預設值

實際從檔案總管拖曳的完整流程與 macOS Apple Silicon / Intel 應用程式尚未實機驗證, macOS 建置工作流程提供建置入口, 本版尚未提供可下載的 macOS 發布產物, 發行包尚未簽章與公證
