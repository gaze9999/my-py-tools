# 可重用文件工具包

`my-py-document-core` 是文件擷取與 Markdown 保護更新的 Python distribution, 公開介面是 `my_py_document_core`, 目前 `API_VERSION=1`, MCP 或其他 Python 工具使用安裝到自身環境的版本, 不需要匯入此 repo 的實體路徑

## 建置與安裝

在 repo 根目錄使用具備 setuptools 與 wheel 的 Python 建置:

```text
python -m pip wheel --no-deps --no-build-isolation --wheel-dir /absolute/wheels .
python -m pip install /absolute/wheels/my_py_document_core-0.2.2-py3-none-any.whl
```

不是 editable install, 安裝後修改, 改名或搬移原 repo 都不會改變既有 runtime 的程式, 核心更新時重新建置 wheel, 檢查 SHA-256 與相容性後再安裝到需要更新的環境

wheel 只納入文件, Markdown 與 shared 的 Python 核心, 不包含 Angular, GUI, 測試, `.env`, 個人資料或其他 MCP 實作, 封裝使用 namespaced packages, 原有 CLI 檔案仍是單一來源, 不在 repo 另存一份核心副本

## 公開 API

```python
from pathlib import Path
from datetime import datetime
from my_py_document_core import API_VERSION, extraction, matching, updates, validation

assert API_VERSION == 1
source = Path("/absolute/documents/spec.txt")
result = extraction.build_markdown(source, Path("/absolute/output/spec.md"), datetime.now())
print(result.content)
```

此範例只產生本文, 不寫入 output, 若呼叫端需要實際寫入, 自行保留來源與目標範圍, preview, hash 與明確授權等資料邊界

| API | 用途 |
| --- | --- |
| `extraction.build_markdown` | 依來源格式產生 `GeneratedMarkdown`, 含 source, output, content 與 summary |
| `extraction.sha256` | 計算來源檔的 SHA-256 |
| `extraction.SUPPORTED_EXTENSIONS` | 查看原生文件支援格式 |
| `extraction.fenced_text` | 將原始文字放入安全的 Markdown fenced block |
| `matching.locate_extracts` | 依來源路徑與 SHA-256 尋找 current, stale 或候選 Markdown 抽出版 |
| `updates.read_target`, `headings`, `section` | 讀取 Markdown, 定位章節 |
| `updates.prepare`, `sha`, `write_guarded` | 準備內容, 比對 hash, 執行原子寫入與 readback |
| `validation.analyze(text)` | 唯讀檢查有限的 Markdown ATX 標題與 fence, 回傳 checks, failures, warnings, 不宣稱完整 Markdown parser |

原生 PDF, Office 擷取需要相關選用套件, OCR 由 Local Documents MCP 另外提供, API 不自行掃描 repo, 啟動 MCP, 取得 credentials 或授權寫入

## 給其他 MCP 使用

每個 MCP 在自己的 Python 環境安裝此 wheel, 經公開 API 取用功能, 可分別固定相容版本, 不使用 `sys.path` 插入另一個 working tree, 不複製私有函式庫, 不從資料夾名稱推斷版本

目前依賴 API 1 的 consumer 可先檢查 `API_VERSION`, 核心改變公開參數, 回傳資料或錯誤語意時需評估相容性並增加相應版本, 不以「同名檔案存在」代替相容性檢查

Package layout 與建置設定依 [setuptools package discovery](https://setuptools.pypa.io/en/stable/userguide/package_discovery.html) 與 [pyproject.toml 設定](https://setuptools.pypa.io/en/stable/userguide/pyproject_config.html)
