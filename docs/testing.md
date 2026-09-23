# 測試方式

專案測試只使用 Python 標準函式庫 `unittest`, Office fixture 測試會使用 `requirements.txt` 中的 extractor 套件

```powershell
python -m unittest discover -s tests -v
```

目前自動測試涵蓋

- 12 支 CLI 的 `--help` 可安全執行
- `.env` 無效行, 重複 key, variable expansion, process environment override 與 fallback
- Angular/Nx component inventory, form contract, generator collision 與 Git change impact fixture
- Markdown semantic diff 與 guarded replace dry-run
- tokenizer 精確路徑失敗時的 fallback
- validation evidence index 與 cleanup preview
- 欄位契約矩陣的表頭與 separator row
- source audit 單輸入, 多輸入多輸出, 多輸入單輸出, output 衝突
- XLSX, DOCX, PPTX, CSV, TXT fixture 與 diagram override hash guard

語法與 import 檢查

```powershell
python -m compileall -q angular audit maintenance markdown shared text validation
```

PDF extractor 需用實際 PDF 做 `--dry-run`, 因為 text layer 與 table reconstruction 結果依來源結構而異

```powershell
python -m audit.source_audit_extract C:\path\spec.pdf --dry-run --extracted-at 2026-09-22T14:30:15
```

測試通過只代表這些明確案例, 不代表未提供的文件版面, OCR, Angular dynamic metadata 或 remote Git operation 已驗證
