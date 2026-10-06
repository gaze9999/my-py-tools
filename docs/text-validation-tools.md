# 文字與驗證工具

## `text/tokenizer.py`

從單一文字檔, CLI 直接提供的文字或 stdin 計算 token, 優先使用 `tiktoken`, 套件缺少, 編碼不存在或 tokenizer 失敗時, 自動依 ASCII 與非 ASCII 字元比率估算區間

```powershell
python launch-cli.py text.tokenizer --input .\prompt.md
python launch-cli.py text.tokenizer --text "測試 text" --encoding cl100k_base --json
Get-Content .\prompt.md -Raw | python launch-cli.py text.tokenizer
```

`--input` 與 `--text` 互斥, 未提供時讀取 stdin, 互動式終端沒有 pipe 時回傳錯誤

CLI 的 `--ascii-chars-per-token` 與 `--non-ascii-chars-per-token` 必須是大於 0 的有限數, `.env` 對應值無效時顯示警告, 並改用 `4` 與 `2`

精確模式輸出單一 `tokens`, 備援估算模式輸出 `min_tokens`, `mid_tokens`, `max_tokens` 與 `fallback_reason`, 並明確標記 `method=fallback`, 小數比率會直接參與計算, 不會先取整數, 估算值不可當成正式計價依據

結束代碼 `0` 表示計算完成, `2` 表示來源或比率錯誤

## `validation/validation_evidence_index.py`

索引指定目錄下一層的 `run-*/results.json`, 依名稱反向排序, 並輸出每次執行的 started, source, baseline, 結果名稱, 狀態, command, 原因, log 參照與未驗證項目

```powershell
python launch-cli.py validation.validation_evidence_index --root C:\path\validation-runs
python launch-cli.py validation.validation_evidence_index --root C:\path\validation-runs --limit 50
python launch-cli.py validation.validation_evidence_index --root C:\path\validation-runs --current-baseline C:\path\current-baseline.json
```

`--limit` 預設 20 且必須大於 0, 根目錄必須存在, 每份 JSON 會檢查頂層物件, `results` 陣列與各結果物件, 格式錯誤的執行會放入 `errors`, 其他有效執行仍保留在 `runs`

此工具只重整既有驗證證據, 不重新執行 build, test, lint, type check 或瀏覽器測試, 沒有 `run-*/results.json` 時輸出空的 `runs` 陣列

提供 `--current-baseline` 時, 以 workspace core 0.2.0 的 `assess_evidence` 比較明確提供的來源與產物資訊, 不讀取其指向的原始碼或執行 command. 既有結果與狀態保留, 另加 `validity`, 缺少新版 core 時需先更新已安裝的 runtime

Baseline 可包含 `source_revision`、`source_diff_sha256`、`source_files` 路徑與 SHA-256 映射、`artifact_sha256`, 舊證據的 `covered_paths` 與本次的 `affected_paths`. Diff hash 應涵蓋當時未提交變更與未追蹤來源, 只核對 HEAD 不足以證明同一份來源

結果分為 `current`、`outdated`、`partial`、`unverified`: 來源 / 產物 hash 改變為 outdated, hash 相符但缺來源、產物或涵蓋範圍時為 partial, 來源身分不足為 unverified. 局部檔案 hash 相符可支持其明確範圍, 不把其他路徑或時間戳推論為已通過, 證據仍適用也不改變原本測試的 PASS / FAIL

結束代碼 `0` 表示索引完成且沒有格式問題, `1` 表示部分執行格式錯誤但已輸出其他有效結果, `2` 表示根目錄或筆數上限錯誤
