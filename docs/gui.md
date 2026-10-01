# 本機 GUI

GUI 會自動找出 repository 內適合直接操作的 Python 工具, 並依第一層資料夾顯示分類 tab; 不需安裝桌面 GUI 套件, 啟動後會在預設瀏覽器開啟只監聽 `127.0.0.1` 的本機頁面

`local_documents` 的 MCP server, 安裝與驗證統一由 `codex-setup` 管理, 不放入本 GUI; 文件處理 CLI 核心仍保留在 `my-py-tools`

## 啟動方式

Windows 可直接雙擊 repository 根目錄的 `launch-gui.vbs`, GUI 會透過 `pythonw.exe` 或 `pyw.exe` 在背景執行, 不會保留命令提示字元視窗; 初始化失敗時會顯示訊息並將詳細資訊寫入 `.gui/startup-error.log`

`launch-gui.cmd` 保留為診斷入口; 背景入口無法啟動或初始化失敗時, 可使用它查看即時錯誤, 或開啟 `.gui/my-py-tools-gui.log`

也可在 PowerShell 執行

```powershell
python -m gui.launcher
```

只顯示網址而不自動開啟瀏覽器

```powershell
python -m gui.launcher --no-browser
```

指定本機連接埠

```powershell
python -m gui.launcher --port 8765
```

### 拖曳文件並在原目錄產生 Markdown

可從 Windows Explorer 將單一或多個 PDF, XLSX, DOCX, PPTX, CSV, TXT 直接拖到 `launch-gui.vbs`; GUI 會自動選取 `documents.convert_to_markdown` 並帶入完整路徑, 確認後按 `執行`, 預設會在每個來源旁產生同名 `.md`

瀏覽器本身基於安全限制不會提供拖入檔案的完整原始路徑, 因此要在原目錄輸出時, 必須拖到 `launch-gui.vbs`, 或使用 GUI 的 `加入檔案路徑` 選擇器; 不會把文件上傳到遠端服務

## 操作方式

1. 從左側選擇資料夾分類 tab, 再搜尋或選擇工具
2. 確認 Python 執行檔與工作目錄
3. 直接填入 CLI 參數, 或用 `加入檔案` 與 `加入資料夾` 選擇路徑
4. 可套用範例參數, 或先按 `顯示 Help` 查看該工具的完整參數
5. 按 `執行` 後, 標準輸出與錯誤輸出會即時顯示在輸出區
6. 互動式工具可在 stdin 欄位送出文字; 執行時間較長時可按 `停止`
7. 完成後按右上角 `關閉 GUI` 停止本機服務

GUI 同一時間只執行一個工具, 執行命令不經 shell, 且 module 只能從內建清單選擇, 不能透過 HTTP 要求執行任意 module

執行期間會顯示活動進度條; 由於既有 CLI 沒有提供可計算的總工作量, 進度條表示程序仍在執行, 不代表完成百分比

## 新增工具至 GUI

一般工具不需要修改 GUI 清單, 請依下列方式加入

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

新增後執行下列驗證; CLI smoke test 會直接使用 GUI 自動發現的相同清單, 不需再維護第二份 module 名單

```powershell
python -m unittest tests.test_gui_launcher tests.test_cli_smoke -v
```

## Python 環境

一般工具可沿用啟動 GUI 的 Python; 文件擷取或 tokenizer 需要選用套件時, 可選擇已安裝本 repo `requirements.txt` 的 Python, 例如

```text
C:\path\tool-runtime\Scripts\python.exe
```

切換 Python 執行檔只影響之後從 GUI 啟動的工具, 不會修改 `.env`, 系統 PATH 或 Codex 設定

## 安全與備援機制

- Server 只監聽 `127.0.0.1`, 每次啟動會產生新的隨機 token, API 必須帶入該 token
- 唯讀 API 遇到短暫連線中斷時最多自動重試 2 次; 執行, stdin, 停止與寫入類 POST 不會自動重送, 避免重複操作
- GUI 只組合並啟動既有 CLI, 原本的 dry-run, 預覽, hash 檢查, 備份與確認機制仍保留; 停止按鈕會終止該次工具的子程序樹
- 輸出最多保留最新 2 MiB, 超過時會標示較早內容已截斷, 避免長時間工作耗盡記憶體
- 背景啟動與未處理的 HTTP 錯誤會寫入 `.gui/my-py-tools-gui.log`, 最多保留目前與前一份各 512 KiB
- 使用診斷入口且瀏覽器沒有自動開啟時, 可複製終端顯示的完整 `http://127.0.0.1:.../?token=...` 網址
- GUI 無法啟動時, 所有工具仍可照各自文件使用 `python -m <package>.<module>` 執行
