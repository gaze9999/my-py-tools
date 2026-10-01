# 可重用工作區檢查工具包

`my-py-workspace-core` 是唯讀工作區檢查用的獨立 Python distribution, 公開介面為 `my_py_workspace_core`, 目前 `API_VERSION=1`; 它與文件擷取用途不同, 因此擁有獨立套件版本

## 建置與安裝

```text
python -m pip wheel --no-deps --no-build-isolation --wheel-dir /absolute/wheels packages/workspace_core
python -m pip install /absolute/wheels/my_py_workspace_core-0.1.0-py3-none-any.whl
```

## 公開 API

| API | 用途 |
| --- | --- |
| `environment.compare_trees` | 依相對路徑, 檔案大小與 SHA-256 比對兩個非巢狀資料夾, 預設排除 Secret 與快取 |
| `validation.read_run` | 驗證並正規化單一 `results.json` |
| `validation.index_evidence` | 索引 `run-*/results.json`, 保留命令, 來源基準與未驗證項目 |

核心不執行同步, 安裝, build, test 或 Git 寫入; CLI 分別由 `maintenance.environment_consistency` 與 `validation.validation_evidence_index` 提供, Codex 的受限 MCP adapter 由 `codex-setup` 維護
