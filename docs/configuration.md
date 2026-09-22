# 設定與 fallback

## 設計原則

輸入與輸出路徑不放在 `.env`, 每次執行由位置參數或 `--root`, `--output`, `--target-file` 等 CLI option 提供, 未指定時只使用文件中明載的目前目錄或來源同目錄預設

這可避免工具被單一專案, 使用者目錄或同步磁碟路徑綁定, 也讓同一份 checkout 可直接處理不同專案

## `.env` 支援欄位

repository 根目錄的 `.env` 為選用檔案

```powershell
Copy-Item .\.env.example .\.env
```

| 變數 | 使用工具 | 預設值 | 無效時行為 |
| --- | --- | --- | --- |
| `TOOL_HISTORY_NAMESPACE` | `markdown.guarded_markdown_update` | `project-task` | 警告後回退 `project-task` |
| `TOOL_FIELD_MATRIX_TITLE` | `audit.extract_field_contract_matrix` | 依來源檔名產生 | 空值時使用來源檔名 |
| `TOOL_TOKENIZER_ENCODING` | `text.tokenizer` | `cl100k_base` | tiktoken 無法使用時改採字元比率估算 |
| `TOOL_TOKENIZER_ASCII_CHARS_PER_TOKEN` | `text.tokenizer` | `4` | 非有限值或小於等於 0 時警告並回退 `4` |
| `TOOL_TOKENIZER_NONASCII_CHARS_PER_TOKEN` | `text.tokenizer` | `2` | 非有限值或小於等於 0 時警告並回退 `2` |

不需要 `.env` 時可直接刪除或忽略, CLI-only 操作仍可執行

## 優先序

1. CLI option, 例如 `--title`, `--encoding`, `--namespace`
2. process environment 的 `TOOL_*` 變數
3. `--env-file` 指定檔案或 repository 根目錄 `.env`
4. 工具內建安全預設值

路徑沒有 `.env` 優先序, 一律由 CLI 決定

## fail-open 規則

`shared/config.py` 對設定檔採 fail-open

- 預設 `.env` 不存在時安靜使用內建預設
- 明確指定的 `--env-file` 不存在或無法讀取時輸出 warning, 仍繼續使用 process environment 與內建預設
- 無效行, 非 `TOOL_*` key, 重複 key, 未閉合 quote, 找不到的 `${TOOL_NAME}` 或循環引用會被忽略並輸出 warning
- process environment 會覆蓋 `.env` 同名值
- CLI 明確傳入的錯誤值通常回傳 exit code `2`, 不會默默改成另一個路徑或檔案

## 自訂設定檔

支援設定變數的工具可用 `--env-file`

```powershell
python -m text.tokenizer --env-file .\profile.env --text "example"
python -m audit.extract_field_contract_matrix audit.md --env-file .\profile.env
python -m markdown.guarded_markdown_update --env-file .\profile.env --target-file history.md inspect history
```

`.env` 支援 UTF-8 BOM, 空白行, `#` 開頭註解, 單引號或雙引號包住的完整 value, 以及 `${TOOL_OTHER_KEY}` 變數引用, 不支援 shell command substitution 或行尾註解
