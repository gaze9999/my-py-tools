# 版本與發布

repository 版本記錄於根目錄 `VERSION`, 使用 SemVer, Git Tag 加上 `v` 前綴, 例如 `VERSION=0.2.0` 對應 `v0.2.0`

`my-py-document-core` 與 `my-py-workspace-core` 是用途不同的 Python 套件, 各自以 `pyproject.toml` 管理套件版本, repository Tag 不強迫兩個 wheel 使用同一版本, release manifest 會記錄實際組合

## 準備發布

先執行完整來源驗證與暫存建置, 不寫入 `dist/`

```powershell
python launch-cli.py scripts.release prepare --dry-run
```

確認要準備目前版本或指定下一個 repository 版本

```powershell
python launch-cli.py scripts.release prepare
python launch-cli.py scripts.release prepare --version 0.3.0
python launch-cli.py scripts.release prepare --asset-root C:\path\release-assets
```

`prepare` 會執行 `unittest` 與不產生 bytecode 的 Python AST 語法檢查, 在隔離的暫存副本建置兩個 wheel, 驗證 wheel CRC 與 metadata, 再產生

```text
dist/v0.2.0/
├── my-py-tools-v0.2.0.zip
├── my_py_document_core-<package-version>-py3-none-any.whl
├── my_py_workspace_core-<package-version>-py3-none-any.whl
└── release-manifest.json
```

來源 ZIP 遵循 Git ignore, 排除 `.env`, credentials, private key, cache, log, build 與中間產物, 但保留 `.env.example`, manifest 記錄每個 asset 的大小與 SHA-256

工具原始碼位於 `src/`, 相依與選用設定位於 `setup/`, 測試程式碼保留於來源包, Workbench UI 的 vendor 檔、WebView2 CAB 與 Runtime 不納入來源 ZIP 或核心 wheel

同一版本只能取代由本工具管理且內容未被另行修改的輸出, 發現未知檔案或 hash 不符時會停止, 不覆寫現有資料

## 發布 GitHub Release

先檢查 diff 與 manifest, 自行 commit 預定發布的來源變更, helper 不會自動 commit

```powershell
python launch-cli.py scripts.release publish v0.2.0
python launch-cli.py scripts.release publish v0.2.0 --asset-root C:\path\release-assets
```

`--asset-root` 適合 sandbox 與 GitHub CLI 使用不同檔案權限的環境, 指定資料夾下仍使用 `<tag>/` 結構與同一份 manifest/hash 驗證, 不會放寬來源檢查

`publish` 要求乾淨 working tree, 目前 branch 追蹤同名 `origin` branch, 本機與遠端 Tag 尚不存在, GitHub CLI 已登入, 並重新執行來源驗證, 輸入完整 Tag 確認後才 push branch 與建立 GitHub Release, 最後核對遠端 asset 名稱與大小

`codex-setup` 仍保留自己的 Skills ZIP 與 Codex MCP 發布流程, 本流程負責可獨立使用的 `my-py-tools` 來源包、Python 核心 wheel 與 CLI / GUI 免安裝包

## Windows 與 macOS 免安裝 CLI / GUI

兩個平台各自提供獨立 CLI 與 GUI, 不需要同時下載, Windows GUI 是單一免安裝 EXE, macOS GUI 是 `.app` ZIP, CLI 另以 ZIP 提供, 原始碼 CLI、核心 wheel 與來源 ZIP 保留原本的發布方式, Windows EXE 內嵌 GUI、`_internal/launch-worker.exe` 與 WebView2, CLI 包支援終端機與瀏覽器模式, 內含共用 React + Workbench UI 頁面但不含 WebView2

正式 CLI / GUI 產物只由 `.github/workflows/desktop.yml` 的 `Release portable desktop applications` 建置, 本機 `gui.packaging.build` 與 `distribution.build_cli` 只用於測試, 不把本機測試 EXE 或 ZIP 上傳成正式版本

發布來源 Release 後, GUI 與 CLI 工作分開, 各自在 Windows x64、macOS arm64、macOS x64 runner 執行 `python launch-cli.py scripts.release desktop <tag>` 或 `python launch-cli.py scripts.release cli <tag>`, 共用 release helper 的完整 Python 測試、版本與打包檢查

| runner | 成品 | 相依 |
| --- | --- | --- |
| Windows x64 GUI | `launch-gui-<version>-windows-x64.exe` | 單一 EXE, 內含 Python、工具套件與 Fixed WebView2 |
| macOS Apple Silicon | `my-py-tools-<version>-macos-arm64.zip` | 內含 Python 與工具套件, 使用系統 WebKit |
| macOS Intel | `my-py-tools-<version>-macos-x64.zip` | 內含 Python 與工具套件, 使用系統 WebKit |
| Windows x64 CLI | `my-py-tools-<version>-cli-windows-x64.zip` | 內含 Python、工具套件與網頁介面, 使用既有瀏覽器 |
| macOS Apple Silicon CLI | `my-py-tools-<version>-cli-macos-arm64.zip` | 內含 Python、工具套件與網頁介面, 使用既有瀏覽器 |
| macOS Intel CLI | `my-py-tools-<version>-cli-macos-x64.zip` | 內含 Python、工具套件與網頁介面, 使用既有瀏覽器 |

GUI EXE / ZIP 搭配 `desktop-manifest-<os>-<architecture>.json`, 記錄格式、Python、工具、Workbench UI commit 與來源 hash、瀏覽器 Runtime 模式、大小及 SHA-256, Windows 另記錄內嵌 payload 的檔案數、壓縮 / 解壓容量與 SHA-256, 發布前直接讀取 EXE 內的 payload 驗證 CRC、必要檔案與安全路徑, 確認只有 GUI 對外入口, CLI ZIP 搭配 `cli-manifest-<os>-<architecture>.json`, 記錄工具清單、需原始碼的開發工具、終端機 / 瀏覽器模式、共用介面來源、入口與 hash, 所有平台的原生 GUI smoke test、CLI 執行與瀏覽器轉檔測試通過後, publish job 才上傳十二個附件並核對 GitHub 回傳的大小與 SHA-256, 已存在的附件不覆寫

### CLI 使用與本機測試

解壓縮完整 CLI 包後, 保留執行檔與 `_internal/`, 不需要另外安裝 Python 或文件套件

```powershell
# Windows
.\MyPyToolsCLI\launch-cli.cmd --list
.\MyPyToolsCLI\launch-cli.cmd documents.convert_to_markdown "C:\path\spec.docx"
.\MyPyToolsCLI\launch-web.cmd
```

```bash
# macOS, 依 CPU 選 arm64 或 x64
./MyPyToolsCLI/launch-cli --list
./MyPyToolsCLI/launch-cli documents.convert_to_markdown /path/spec.docx
./MyPyToolsCLI/launch-cli --web
```

CLI 的 stdout / stderr 統一使用 UTF-8, 適合管線與 JSON 輸出, Git 類工具仍需 Git, 發布與來源產物工具需要完整儲存庫與開發用 Python, CLI 免安裝版可查看它們的 `--help`, 執行時會清楚提示改用原始碼入口, 不嘗試在凍結的執行環境發布

Windows CLI 包內的 `launch-cli.cmd` 呼叫 `launch-cli.exe`, `launch-web.cmd` 呼叫同一執行檔的 `--web` 模式, 所有使用者入口都採 `launch-xxx` 命名, 瀏覽器與 GUI 共用相同介面與工具核心, 瀏覽器需要電腦已有的瀏覽器, 原地生成文件與服務停止方式見 [GUI 教學](gui.md)

Windows CLI 包另外附上 `launch-cli.ps1`、`launch-web.ps1`, 功能與同名 CMD 相同, 資訊清單記錄 PS1 入口, 發布檢查也會確認它們存在, 原始碼版的 `launch-gui.ps1` 保留, GUI 發行 EXE 不另外附啟動腳本, PowerShell 用法與執行政策說明見 [PowerShell 啟動](gui.md#powershell-啟動)

本機建置只供測試, 必須在目標平台執行, 建置共用頁面需要 Node.js / npm 與明確的 Workbench UI 路徑, 不讀 WebView2 設定, 已完成相同來源的前端建置時可用 `--skip-frontend`

```powershell
python -m pip install -r setup/requirements-cli-build.txt
python launch-cli.py distribution.build_cli --workbench-ui C:\path\workbench-ui --output-root .gui/cli-tests
python launch-cli.py distribution.smoke_cli .gui/cli-tests/my-py-tools-0.4.0-cli-windows-x64/MyPyToolsCLI/launch-cli.exe
```

### 首次設定

在 `my-py-tools` GitHub repository 的 Actions 設定新增以下值, 不放入 `.env`、原始碼或本機設定檔

| 類型 | 名稱 | 用途 |
| --- | --- | --- |
| Secret | `WORKBENCH_UI_READ_TOKEN` | 唯讀取得 private `gaze9999/workbench-ui` 的 fine-grained token |
| Variable | `WORKBENCH_UI_REF` | 已授權且已提交的 Workbench UI 完整 commit SHA |
| Variable | `WEBVIEW2_FIXED_URL` | Microsoft 官方 Fixed Version x64 CAB 下載 URL |
| Variable | `WEBVIEW2_FIXED_SHA256` | 維護者核對的 CAB SHA-256 |

Workbench UI 共用資產需要明確的散布授權, 工作流程固定 commit 而非使用浮動分支, release helper 拒絕未提交的 Workbench UI 修改, 本機測試可使用 working tree, 但不能當成正式發布輸入

自動模式由 `release: published` 觸發, 使用上述 Variables, 也可在 Actions 手動指定既有 Release Tag、Workbench UI SHA 與 Runtime URL/hash, Secret 仍需預先設定, Tag 的 `VERSION` 必須一致, 不會自動變更版本、commit 或替換舊 Tag

Fixed WebView2 不自動更新, 後續發布時須由維護者更新官方 Runtime URL 與核對值, 使用端不需要安裝 Runtime, Windows 10 的 AppContainer 權限及本機磁碟限制見 [GUI 教學](gui.md)

### 同一份資訊清單包含 GUI

來源 helper 可在測試時驗證並附加既有、版本一致的 desktop assets, 也可準備同一份完整資訊清單, 正式發布仍使用雲端建置產物

```powershell
python launch-cli.py scripts.release prepare --desktop --desktop-assets C:\path\cloud-desktop-assets --dry-run
```

省略 `--dry-run` 才寫入來源包資訊清單, 多個平台可由 `attach_desktop` 逐一附加, 附件會核對版本、CRC、SHA-256 與內含 Runtime, 不覆寫獨立產生或已修改的資料

正式免安裝附件須先完成上述 GitHub Actions 設定, macOS arm64/x64 啟動及三平台附件上傳仍須依實際 CI 結果驗收, 未簽章與公證的應用程式也仍受作業系統安全提示限制

本機最新 Windows GUI 封裝測試已通過介面操作與圖示資源檢查, 但單檔 EXE 在內部 GUI 結束後仍未正常退出, 等待 600 秒後終止測試並保留 WebView2 殘留, 原因尚未確認, 來源包及核心 wheel 可獨立發布, 不將這份本機測試 EXE 上傳成正式成品, CI 的原生退出驗證仍維持必要門檻
