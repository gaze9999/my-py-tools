# 維護工具

## `maintenance/windows_process_audit.py`

稽核本機 Windows 的 Python、cmd、PowerShell、Git、Node、uv 等開發程序, 顯示 PID、建立時間、執行檔、Windows owner SID、session、父子關係、CPU / I/O 與分類理由, 適合在清理自己的臨時工作前確認身分, 不會把低 CPU、取樣期間無變化或父程序消失當成終止授權

使用 Python 標準函式庫、Windows 原生 API 及系統 PowerShell / CIM, 不需要安裝額外套件, 不會自動提權、安裝或建立排程, macOS / Linux 執行時回傳 `2`, 不操作程序

### 先稽核

```powershell
.\launch-cli.cmd windows-process-audit
.\launch-cli.cmd windows-process-audit --json --sample-seconds 0
```

CLI 模組名稱也可使用 `maintenance.windows_process_audit`, GUI 的「維護」分類提供相同工具, 透過 CLI 參數欄操作, 預設範例只稽核

`--sample-seconds` 預設 `1`, 範圍為 `0` 到 `10` 秒, `0` 不取樣變化, 取樣包含兩次本機查詢的時間, 不是精確的 CPU 百分比, 無變化只表示這段時間的 CPU / I/O 計數器未變, 不表示沒有工作、網路等待或仍需保留的狀態

分類

| 分類 | 意義 |
| --- | --- |
| `protected` | 現行稽核程序、它的父程序 / 子程序、已辨識的 Codex、MCP、服務、服務型命令或額外保護的程序關聯 |
| `retain` | 未聲明工作 ownership、Windows owner / session 不同、身分不完整、有子程序或其他安全條件不符 |
| `candidate` | 使用者明確聲明屬於自己的可丟棄工作, 身分與關聯核對完整, 且未碰到保護條件, 尚未終止 |

所有命令列參數與 inline 程式碼一律遮蔽, 不只遮蔽 `--token` 等常見參數, 報告保留命令 SHA-256 用於後續比對, ownership 理由也只記錄 hash, 原始命令只在本機記憶體中用於分類與核對, 不寫入快照或記錄檔

執行檔路徑、PID、SID 與程序關聯仍可能透露本機資訊, 快照應留在本機, `/.process-audit/` 已由 Git 排除, 工具預設不寫檔, `--output` 只建立新檔, 不覆寫舊快照

### 明確聲明 ownership, 再選取候選

同帳戶、同資料夾或看似孤立, 都不等於屬於這次工作, 只有已確認自己建立、可以丟棄、沒有其他工作依賴的程序才可聲明 ownership, `--owned-pid` 是使用者的明確聲明, 不是工具自動推論的事實, 工具仍會核對 Windows owner SID / session 及保護條件, 不能用聲明略過保護

以下的 `12345` 是範例 PID, 請替換成已自行確認 ownership 的程序, 不要直接照抄

```powershell
New-Item -ItemType Directory -Force .process-audit
.\launch-cli.cmd windows-process-audit --owned-pid 12345 --ownership-reason "自己建立且已不需要的臨時工作" --output .process-audit\audit.json

# 只重新核對及預覽, 不終止
.\launch-cli.cmd windows-process-audit --snapshot .process-audit\audit.json --pid 12345

# 明確套用, 終止不可復原
.\launch-cli.cmd windows-process-audit --snapshot .process-audit\audit.json --pid 12345 --apply
```

快照有效時間為 15 分鐘, 限同電腦、同 Windows owner / session 使用, `--owned-pid`、`--pid` 與 `--protect-pid` 可重複提供, 但不支援全部候選套用或遞迴終止, 要再稽核請使用新的輸出檔名

每個 PID 操作前重新查詢, 核對 PID、原生建立時間、命令 hash、執行檔、Windows owner、session、父程序鏈及子程序, 接著持有精確的 Windows process handle, 再次查詢關聯與身分後才終止, 不使用 `taskkill /T`, 有任何子程序就保留, 父 PID 重用、父程序命令不可讀或關聯改變也保留

父程序已消失且使用者有明確 ownership 聲明的隔離工作仍可能成為候選, 但「父程序消失」本身不提供清理資格, 原始快照與操作前的父程序狀態也必須一致

保護包含可辨識的 Codex / MCP、Windows 服務及其子程序、session 0、critical process、常見服務 / watch 命令與 PowerShell encoded command, 特殊名稱或未標示的自訂服務無法只靠名稱完整辨識, 已知必須保留的其他工作可加 `--protect-pid`, 不確定 ownership 時不要聲明, 不要清理

CIM 不可用時仍以原生 API 提供可取得的身分與活動, 命令或服務資訊不足時保留全部程序, 拒絕存取不會觸發提權, 操作失敗也不會改用較寬鬆的終止方式

Windows 不提供這些查詢與終止的原子操作, 持有 handle 可避免誤終止重用 PID 的新程序, 但不能排除最後一次查詢後又建立子程序或變更服務狀態的競態, 因此只處理明確確認為自己的可丟棄工作, 終止可能中斷寫入並遺失未保存資料, 工具不暫停其他程序來鎖住整台電腦

結束代碼 `0` 表示稽核、預覽或所選程序已確認終止, `2` 表示安全檢查失敗、資料不足、I/O 錯誤或終止後尚未確認退出, 每個 PID 的結果獨立列出, 一項失敗不會擴大清理範圍

## `maintenance/environment_consistency.py`

唯讀比對兩個非巢狀資料夾的相對路徑, 檔案大小與 SHA-256, 適合檢查 Skills, runtime 或安裝鏡像是否漂移

```powershell
python launch-cli.py maintenance.environment_consistency --source C:\path\source --target C:\path\mirror
python launch-cli.py maintenance.environment_consistency --source C:\path\source --target C:\path\mirror --include "*.py" --exclude "generated/**"
```

預設排除版本控制中繼資料, cache, `.env`, private key, credentials 與 secrets, 可重複提供 include / exclude pattern, 單側檔案上限預設 20000, 工具不執行複製, 刪除或同步

## `maintenance/cleanup_work_artifacts.py`

掃描可丟棄的開發快取與中間產物, 預設只產生預覽清單, `--apply` 才移至可復原的隔離區

```powershell
python launch-cli.py maintenance.cleanup_work_artifacts
python launch-cli.py maintenance.cleanup_work_artifacts --root C:\path\project --root C:\path\another
python launch-cli.py maintenance.cleanup_work_artifacts --root C:\path\project --include-build --include-work-dirs --apply
python launch-cli.py maintenance.cleanup_work_artifacts --output-dir C:\safe\cleanup --purge-quarantine --older-than-days 7
```

預設候選包含 `__pycache__`, pytest/mypy/ruff/tox/nox 快取, coverage 與常見暫存檔, `build`, `dist`, `*.egg-info`, `work`, `tmp`, `temp` 需明確用選項納入

安全檢查

- 拒絕檔案系統根目錄與不存在的根目錄
- 不進入 Git/Mercurial/Subversion 中繼資料, `.codex`, log, 備份或隔離區
- 不跟隨 symlink 資料夾
- 跳過包含巢狀 repository 或 Git 已追蹤內容的候選, Git worktree 使用的 `.git` 檔案也會辨識
- 預設只納入至少 1 天未修改的候選, 資料夾以內部最新檔案時間判斷, `--min-age-days` 可調整
- `--apply` 將項目移到隔離區, 不直接刪除
- `--apply` 搬移前會重新檢查巢狀 repository 與 Git 已追蹤內容, 降低掃描後狀態改變的風險
- `--purge-quarantine` 只永久刪除含本工具 ownership marker 且超過保存天數的批次, 不處理使用者自行放入的資料夾

清單, JSONL 事件紀錄與隔離區預設放在 `~/.work-artifact-cleaner`, 可用 `--output-dir` 變更, 天數選項必須是 0 到 365000 的有限數

結束代碼 `0` 表示預覽, 隔離或永久清除完成, `2` 表示安全檢查, I/O 或 Git 查詢錯誤

## `maintenance/rewrite_git_history.py`

將所選 repository 所有 refs 的 author 與 committer 身分改成該 repository 的 local `user.name` 與 `user.email`

```powershell
python launch-cli.py maintenance.rewrite_git_history --repo C:\path\repository
```

執行流程

1. 解析真正的 Git 根目錄
2. 要求 local `user.name`, `user.email` 與乾淨 worktree
3. 顯示影響並要求手動輸入完全相符的 `REWRITE`, 取消或前置檢查失敗時不修改 repository
4. 在 `.git/info/exclude` 管理只包含 `/.bundle/` 的區塊
5. 在 repository 的 `.bundle/` 建立包含所有 refs 的備份, 建立失敗時不執行改寫
6. 以 `git filter-branch --all` 改寫 author, committer 與 tag refs
7. 顯示檢查方式及手動 `push --force-with-lease` 指令, 工具本身不會 push

這是破壞性歷史改寫, 所有受影響的 commit SHA 都會改變, 已共享的 branch/tag 需要先協調, bundle 只提供本機復原材料, 不表示遠端已有備份

結束代碼 `0` 表示使用者取消或改寫完成, `1` 表示前置條件不符, Git 失敗時回傳 Git 結束代碼
