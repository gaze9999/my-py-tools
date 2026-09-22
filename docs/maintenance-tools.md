# 維護工具

## `maintenance/cleanup_work_artifacts.py`

掃描可丟棄的開發 cache 與中間產物, 預設只產生 preview manifest, `--apply` 才移至可復原 quarantine

```powershell
python -m maintenance.cleanup_work_artifacts
python -m maintenance.cleanup_work_artifacts --root C:\path\project --root C:\path\another
python -m maintenance.cleanup_work_artifacts --root C:\path\project --include-build --include-work-dirs --apply
python -m maintenance.cleanup_work_artifacts --output-dir C:\safe\cleanup --purge-quarantine --older-than-days 7
```

預設候選包含 `__pycache__`, pytest/mypy/ruff/tox/nox cache, coverage 與常見 temporary files, `build`, `dist`, `*.egg-info`, `work`, `tmp`, `temp` 需明確用 option 納入

安全檢查

- 拒絕 filesystem root 與不存在的 root
- 不進入 Git/Mercurial/Subversion metadata, `.codex`, log, backup 或 quarantine
- 不跟隨 symlink directory
- 跳過含 nested repository 或 Git tracked content 的候選
- 預設只納入至少 1 天未修改的候選, `--min-age-days` 可調整
- `--apply` 使用 move 到 quarantine, 不直接刪除
- `--purge-quarantine` 才永久刪除超過保存天數的批次

manifest, JSONL event log 與 quarantine 預設放在 `~/.work-artifact-cleaner`, 可用 `--output-dir` 改變, day option 必須是 0 到 365000 的有限數

exit code `0` 表示 preview, quarantine 或 purge 完成, `2` 表示安全檢查、I/O 或 Git 查詢錯誤

## `maintenance/rewrite_git_history.py`

將所選 repository 所有 refs 的 author 與 committer identity 改成該 repository 的 local `user.name` 與 `user.email`

```powershell
python -m maintenance.rewrite_git_history --repo C:\path\repository
```

執行流程

1. 解析真正 Git root, 在 `.git/info/exclude` 管理只包含 `/.bundle/` 的區塊
2. 要求 local `user.name` 與 `user.email`
3. 要求 worktree 沒有 tracked 或 untracked 變更
4. 顯示影響並要求手動輸入完全相符的 `REWRITE`
5. 在 repository 的 `.bundle/` 建立包含所有 refs 的備份
6. 以 `git filter-branch --all` 改寫 author, committer 與 tag refs
7. 顯示檢查及手動 `push --force-with-lease` 指令, 工具本身不 push

這是破壞性歷史改寫, 所有受影響 commit SHA 都會改變, 已共享的 branch/tag 需要先協調, bundle 只提供本機復原材料, 不代表 remote 已備份

exit code `0` 表示使用者取消或 rewrite 完成, `1` 表示前置條件不符, Git 失敗時回傳 Git exit code
