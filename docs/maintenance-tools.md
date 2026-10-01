# 維護工具

## `maintenance/environment_consistency.py`

唯讀比對兩個非巢狀資料夾的相對路徑, 檔案大小與 SHA-256, 適合檢查 Skills, runtime 或安裝鏡像是否漂移

```powershell
python -m maintenance.environment_consistency --source C:\path\source --target C:\path\mirror
python -m maintenance.environment_consistency --source C:\path\source --target C:\path\mirror --include "*.py" --exclude "generated/**"
```

預設排除版本控制中繼資料, cache, `.env`, private key, credentials 與 secrets; 可重複提供 include / exclude pattern, 單側檔案上限預設 20000, 工具不執行複製, 刪除或同步

## `maintenance/cleanup_work_artifacts.py`

掃描可丟棄的開發快取與中間產物, 預設只產生預覽清單, `--apply` 才移至可復原的隔離區

```powershell
python -m maintenance.cleanup_work_artifacts
python -m maintenance.cleanup_work_artifacts --root C:\path\project --root C:\path\another
python -m maintenance.cleanup_work_artifacts --root C:\path\project --include-build --include-work-dirs --apply
python -m maintenance.cleanup_work_artifacts --output-dir C:\safe\cleanup --purge-quarantine --older-than-days 7
```

預設候選包含 `__pycache__`, pytest/mypy/ruff/tox/nox 快取, coverage 與常見暫存檔; `build`, `dist`, `*.egg-info`, `work`, `tmp`, `temp` 需明確用選項納入

安全檢查

- 拒絕檔案系統根目錄與不存在的根目錄
- 不進入 Git/Mercurial/Subversion 中繼資料, `.codex`, log, 備份或隔離區
- 不跟隨 symlink 資料夾
- 跳過包含巢狀 repository 或 Git 已追蹤內容的候選; Git worktree 使用的 `.git` 檔案也會辨識
- 預設只納入至少 1 天未修改的候選, 資料夾以內部最新檔案時間判斷, `--min-age-days` 可調整
- `--apply` 將項目移到隔離區, 不直接刪除
- `--apply` 搬移前會重新檢查巢狀 repository 與 Git 已追蹤內容, 降低掃描後狀態改變的風險
- `--purge-quarantine` 只永久刪除含本工具 ownership marker 且超過保存天數的批次, 不處理使用者自行放入的資料夾

清單, JSONL 事件紀錄與隔離區預設放在 `~/.work-artifact-cleaner`, 可用 `--output-dir` 變更; 天數選項必須是 0 到 365000 的有限數

結束代碼 `0` 表示預覽, 隔離或永久清除完成, `2` 表示安全檢查, I/O 或 Git 查詢錯誤

## `maintenance/rewrite_git_history.py`

將所選 repository 所有 refs 的 author 與 committer 身分改成該 repository 的 local `user.name` 與 `user.email`

```powershell
python -m maintenance.rewrite_git_history --repo C:\path\repository
```

執行流程

1. 解析真正的 Git 根目錄
2. 要求 local `user.name`, `user.email` 與乾淨 worktree
3. 顯示影響並要求手動輸入完全相符的 `REWRITE`; 取消或前置檢查失敗時不修改 repository
4. 在 `.git/info/exclude` 管理只包含 `/.bundle/` 的區塊
5. 在 repository 的 `.bundle/` 建立包含所有 refs 的備份; 建立失敗時不執行改寫
6. 以 `git filter-branch --all` 改寫 author, committer 與 tag refs
7. 顯示檢查方式及手動 `push --force-with-lease` 指令, 工具本身不會 push

這是破壞性歷史改寫, 所有受影響的 commit SHA 都會改變; 已共享的 branch/tag 需要先協調, bundle 只提供本機復原材料, 不表示遠端已有備份

結束代碼 `0` 表示使用者取消或改寫完成, `1` 表示前置條件不符; Git 失敗時回傳 Git 結束代碼
