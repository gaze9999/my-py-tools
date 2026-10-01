# 版本與發布

repository 版本記錄於根目錄 `VERSION`, 使用 SemVer, Git Tag 加上 `v` 前綴, 例如 `VERSION=0.2.0` 對應 `v0.2.0`

`my-py-document-core` 與 `my-py-workspace-core` 是用途不同的 Python 套件, 各自以 `pyproject.toml` 管理套件版本; repository Tag 不強迫兩個 wheel 使用同一版本, release manifest 會記錄實際組合

## 準備發布

先執行完整來源驗證與暫存建置, 不寫入 `dist/`

```powershell
python scripts/release.py prepare --dry-run
```

確認要準備目前版本或指定下一個 repository 版本

```powershell
python scripts/release.py prepare
python scripts/release.py prepare --version 0.3.0
```

`prepare` 會執行 `unittest` 與不產生 bytecode 的 Python AST 語法檢查, 在隔離的暫存副本建置兩個 wheel, 驗證 wheel CRC 與 metadata, 再產生

```text
dist/v0.2.0/
├── my-py-tools-v0.2.0.zip
├── my_py_document_core-<package-version>-py3-none-any.whl
├── my_py_workspace_core-<package-version>-py3-none-any.whl
└── release-manifest.json
```

來源 ZIP 遵循 Git ignore, 排除 `.env`, credentials, private key, cache, log, build 與中間產物, 但保留 `.env.example`; manifest 記錄每個 asset 的大小與 SHA-256

同一版本只能取代由本工具管理且內容未被另行修改的輸出; 發現未知檔案或 hash 不符時會停止, 不覆寫現有資料

## 發布 GitHub Release

先檢查 diff 與 manifest, 自行 commit 預定發布的來源變更; helper 不會自動 commit

```powershell
python scripts/release.py publish v0.2.0
```

`publish` 要求乾淨 working tree, 目前 branch 追蹤同名 `origin` branch, 本機與遠端 Tag 尚不存在, GitHub CLI 已登入, 並重新執行來源驗證; 輸入完整 Tag 確認後才 push branch 與建立 GitHub Release, 最後核對遠端 asset 名稱與大小

`codex-setup` 仍保留自己的 Skills ZIP 與 Codex MCP 發布流程; 本流程只負責可獨立使用的 `my-py-tools` 來源包與 Python 核心 wheel
