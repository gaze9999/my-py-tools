# Markdown 工具

## `markdown/markdown_semantic_diff.py`

比較兩份 Markdown 的 ATX heading, list item 與 table row set, 同時輸出兩檔 SHA-256

```powershell
python -m markdown.markdown_semantic_diff --left before.md --right after.md
```

輸出 JSON 的每種 token 都有 `only_left` 與 `only_right`, 差異存在時仍回傳 exit code `0`, 因為這是 report 工具而不是 pass/fail gate, 輸入不存在或無法讀取時回傳 `2`

限制: 不比較 paragraph 語意, token 順序, code block 語法或遠端文件狀態

## `markdown/guarded_markdown_update.py`

以明確目標檔, SHA-256 optimistic concurrency, dry-run, atomic replace 與寫後 readback 保護單一 Markdown 更新

global option 必須放在 subcommand 前

```powershell
python -m markdown.guarded_markdown_update --target-file progress.md inspect progress
python -m markdown.guarded_markdown_update --target-file progress.md inspect progress --section "## Current"
python -m markdown.guarded_markdown_update --target-file progress.md replace progress --content replacement.md --expect CURRENT_SHA --section "## Current"
python -m markdown.guarded_markdown_update --target-file history.md append history --content entry.md --expect CURRENT_SHA --entry-id task-001
```

### `inspect`

- target alias 可為 `context`, `progress`, `history`, alias 只描述用途, 實際路徑由 `--target-file` 決定
- 未指定 `--section` 時輸出 SHA-256 與 heading 清單
- 指定 `--section` 時要求 heading 完全且只出現一次
- `--out` 只可搭配 `--section`, 並以 exclusive create 匯出至新檔, 不覆寫既有檔案

### `replace`

- target alias 只允許 `context` 或 `progress`
- replacement 必須以完全相同 heading 開頭, 且不能包含同層或更高層的其他 section
- `--expect` 必須等於 inspect 取得的目前 SHA-256
- 預設只回報 `dry-run`, `--write` 才寫入

### `append`

- target alias 只允許 `history`
- `--entry-id` 必須唯一, 相同內容已存在時回傳 `unchanged`, 不同內容重複時拒絕
- marker namespace 優先使用 `--namespace`, 再使用 `TOOL_HISTORY_NAMESPACE`, 無效時 warning 並回退 `project-task`

預設寫入使用同目錄 temporary file + atomic replace + exact readback, 同步磁碟 placeholder 無法 atomic replace 時可明確加 `--in-place`, 工具會先建立 backup, guarded write 後 readback, 成功才刪除 backup, 失敗時保留 backup 路徑

exit code `0` 表示 inspect, unchanged, dry-run 或 verified write 完成, `2` 表示 SHA stale, heading/entry contract 不符, 路徑或 I/O 錯誤
