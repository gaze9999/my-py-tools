# 文字與驗證工具

## `text/tokenizer.py`

從單一文字檔, inline text 或 stdin 計算 token, 優先使用 `tiktoken`, 套件缺少、encoding 不存在或 tokenizer 失敗時自動改用 ASCII/非 ASCII 字元比率估算區間

```powershell
python -m text.tokenizer --input .\prompt.md
python -m text.tokenizer --text "測試 text" --encoding cl100k_base --json
Get-Content .\prompt.md -Raw | python -m text.tokenizer
```

`--input` 與 `--text` 互斥, 未提供時讀 stdin, interactive terminal 沒有 pipe 則回傳錯誤

CLI 的 `--ascii-chars-per-token` 與 `--non-ascii-chars-per-token` 必須是大於 0 的有限數, `.env` 對應值無效時 warning 後使用 `4` 與 `2`

精確模式輸出單一 `tokens`, fallback 模式輸出 `min_tokens`, `mid_tokens`, `max_tokens` 並明確標記 `method=fallback`, 估算值不可當成正式計價依據

exit code `0` 表示計算完成, `2` 表示來源或 ratio 錯誤

## `validation/validation_evidence_index.py`

索引指定目錄下一層 `run-*/results.json`, 依名稱反向排序並輸出每次 run 的 started, result name, status, reason 與 log reference

```powershell
python -m validation.validation_evidence_index --root C:\path\validation-runs
python -m validation.validation_evidence_index --root C:\path\validation-runs --limit 50
```

`--limit` 預設 20 且必須大於 0, root 必須存在, malformed JSON 會使該次執行回傳錯誤而不是被當成 passed

此工具只重整既有 evidence, 不重跑 build, test, lint, type check 或 browser, 沒有 `run-*/results.json` 時輸出空 `runs` array

exit code `0` 表示索引完成, `2` 表示 root, limit, JSON 或 I/O 錯誤
