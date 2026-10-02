# 本機 GUI

My Py Tools GUI 使用 React 顯示操作介面, 並透過 pywebview 呼叫既有 Python CLI; Windows 使用 WebView2, macOS 使用系統 WebKit; PyInstaller 發行包內含 Python 與文件處理相依套件, 使用端不必安裝 Python

開發版會依第一層功能資料夾自動分類工具; 發行版會在建置時把分類與用途說明寫入程式資源, 支援 Windows x64, macOS Apple Silicon 與 macOS Intel

`local_documents` MCP 由 `codex-setup` 管理; 文件處理 CLI 核心保留在 `my-py-tools`

## 一般使用者

到 GitHub Actions 的「Build desktop applications」手動執行建置工作, 下載符合作業系統與 CPU 的 artifact; 其中 ZIP 包含可攜執行檔與內建 Python / 文件處理套件, `desktop-manifest.json` 是另一個檔案, 記錄版本, CPU, Python, 內含工具與 ZIP 的 SHA-256

Windows 需要 Microsoft Edge WebView2 Runtime; Windows 11 已內建, 大多數 Windows 10 電腦也已安裝, 缺少時請安裝 [Microsoft WebView2 Runtime](https://developer.microsoft.com/microsoft-edge/webview2/); macOS 首次開啟未簽署的 app 時, 請在 Finder 對 app 按右鍵並選擇「打開」

本機記錄放在 Windows `%LOCALAPPDATA%/MyPyTools/logs`, macOS `~/Library/Logs/MyPyTools`; macOS 發行包分成 Apple Silicon 與 Intel 版本; 發行包目前未簽章與 notarize, 交付前應由維護者核對 manifest 的 SHA-256

從原始碼執行 GUI 需要 Python 3.10+, Node.js 22+ 與 npm; 先安裝 `requirements-gui.txt`, 再執行 `npm --prefix gui/frontend ci` 與 `npm --prefix gui/frontend run build`; 建置獨立發行包需另外安裝 `requirements-build.txt` 並執行 `python -m gui.packaging.build`; Windows 與 macOS 發行包必須分別在對應作業系統建置

Windows 開發版可直接執行 `launch-gui.pyw` 或 `launch-gui.cmd`, GUI 會在背景開啟且啟動錯誤會寫入 log; macOS 開發版可在 Terminal 執行 `python -m gui.launcher`

### 拖曳文件並在原目錄產生 Markdown

從檔案總管或 Finder 將單一或多個 PDF, XLSX, DOCX, PPTX, CSV, TXT 拖到文件區; 可選擇在來源旁分別輸出, 指定資料夾分別輸出, 或合併成單一 Markdown; 也可勾選 dry-run 先檢查參數; 預設於來源旁產生同名 Markdown 檔

所有文件擷取都在本機完成; 拖曳不可用時仍可按「選擇文件」使用原生檔案挑選視窗

## 操作方式

1. 由左側分類或搜尋工具; 主畫面會說明用途, 使用情境, 輸入, 輸出與必要套件
2. 設定工作目錄; 一般工具使用發行包內建執行環境
3. 文件轉換可拖曳或挑選多個檔案; 其他工具可在 CLI 參數區套用範例或 Help
4. 按「執行工具」後, 即時輸出會顯示在下方; 有互動確認時使用 stdin 輸入欄
5. 執行時間較長時可停止程序; 輸出最多保留最新 2 MiB

GUI 同一時間只執行一個工具, 命令不經 shell; module 只從掃描器建立的工具清單選擇

進度動畫表示工作仍在執行, 不代表完成百分比

## 新增工具至 GUI

在功能資料夾新增 Python CLI, 提供標準 main entrypoint; GUI 會用 module docstring 第一行作為預設摘要, 依第一層資料夾分類; 若要清楚說明實際用途, 輸入輸出與執行需求, 請在 gui/catalog.py 該工具的 ToolSpec 補齊 purpose, inputs, outputs, requirements 與 warning; 每次建置會重新產生發行版工具清單

1. 將 Python 檔放在功能資料夾內, 例如 `reports/convert_report.py` 或 `reports/converters/convert_report.py`
2. 提供 `main()` 或等價執行函式, 並加入標準的 `if __name__ == "__main__":` 執行入口
3. module 頂端 docstring 的第一行會成為 GUI 預設說明
4. 重新啟動 GUI; 工具會自動出現在以第一層資料夾命名的分類 tab, module 會依相對路徑產生, 例如 `reports.convert_report` 或 `reports.converters.convert_report`
5. 執行 `python -m reports.convert_report --help`, 確認 CLI 可獨立啟動且不會在顯示 Help 時執行實際工作

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

需要自訂繁體中文名稱, 範例參數或風險警告時, 才在 `gui/catalog.py` 的 `_OVERRIDES` 增加 `ToolSpec`; 未提供覆寫資料時仍會自動出現在 GUI

以下內容不會列入 GUI

- `__init__.py`, `tests/`, `gui/`, `shared/` 與隱藏資料夾
- 沒有 `if __name__ == "__main__":` 執行入口的純函式庫
- `gui/catalog.py` 中 `EXCLUDED_MODULES` 明確排除的入口

開發時新增工具, 除確認 CLI 本身可用外, 也要檢查 GUI 工具清單的分類, 中文用途說明, 輸入輸出與必要條件; 使用者安裝版的工具清單在建置時固定, 重新建置發行包才會更新

已打包工具使用內建 Python; `準備 Release Assets` 與 `驗證與發布 Release` 需要完整 repository 與開發用 Python, 因為它們會讀寫 Git / GitHub 發布相關資源; 這兩項會在工具畫面標示需求, 不會假裝已包含在通用桌面包裡

## 安全與備援機制

- GUI 不啟動本機 HTTP server, 不開放網路連接埠, 也不會將文件傳送至瀏覽器或遠端服務
- GUI 只組合並啟動既有 CLI, 原本的 dry-run, 預覽, hash 檢查, 備份與確認機制仍保留; 停止按鈕會終止該次工具的子程序樹
- 輸出最多保留最新 2 MiB, 超過時會標示較早內容已截斷, 避免長時間工作耗盡記憶體
- 背景啟動與未處理的 GUI callback 錯誤會寫入 `.gui/my-py-tools-gui.log`, 最多保留目前與前一份各 512 KiB
- 拖曳無法使用時, 可改用「選擇文件」; Windows WebView2 或 macOS WebKit 不可用時, GUI 無法啟動, 但 CLI 仍可照各自文件使用 `python -m <package>.<module>` 執行
- Windows 啟動器使用無主控台模式; 執行中的 CLI 子程序不會另開小黑窗, 結果會顯示在 GUI 輸出區

## 本版驗證範圍

Windows x64 React build 與 PyInstaller ZIP 已建置並核對 SHA-256, CLI process manager 的 focused tests 已驗證; native GUI 互動, WebView2 拖曳與 macOS Apple Silicon / Intel app 尚未實機驗證. macOS workflow 是建置入口, 不代表本版已有可下載的 macOS release asset; 未簽章與 notarize
