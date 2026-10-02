# 測試方式

專案測試使用 Python 標準函式庫 `unittest`; Office 測試資料會使用 `requirements.txt` 中的文件擷取套件

```powershell
python -m unittest discover -s tests -v
```

目前自動測試涵蓋

- GUI 自動發現的全部可執行 module 之 `--help` 可安全執行; `local_documents` 的 MCP 層與驗證由 `codex-setup` 管理, 不納入本 GUI
- GUI 工具清單, 路徑參數解析與實際 subprocess 輸出
- `.env` 無效行, 重複 key, 變數展開, process environment 覆寫與備援處理
- Angular/Nx 元件盤點, 表單欄位規格, generator 衝突與 Git 變更影響測試資料
- Markdown 結構差異與保護取代的 dry-run
- tokenizer 精確計算失敗時的備援估算
- 驗證證據索引與清理預覽
- 欄位規格矩陣的表頭與分隔列
- 文件轉 Markdown 工具的單一輸入, 多輸入多輸出, 多輸入單輸出與輸出衝突
- XLSX, DOCX, PPTX, CSV, TXT 測試資料與圖表覆寫 hash 檢查

語法與 import 檢查

```powershell
python -m compileall -q angular documents gui maintenance markdown packages shared src text validation
```

PDF 擷取器需用實際 PDF 做 `--dry-run`, 因為文字層與表格重建結果會依來源結構而異

```powershell
python -m documents.convert_to_markdown C:\path\spec.pdf --dry-run --extracted-at 2026-09-22T14:30:15
```

測試通過只代表這些明確案例, 不表示未提供的文件版面, OCR, Angular 動態中繼資料或遠端 Git 操作已驗證

Markdown validator focused checks:

```powershell
python -m unittest discover -s tests -p test_validate_structure.py -v
python -m markdown.validate_structure --help
```

涵蓋標題跳號, fence closing, hard break, 版本 INFO, exit codes, `-I -S` standalone 執行及 snapshot 產生一致性; 不代表所有 Markdown syntax 已驗證
