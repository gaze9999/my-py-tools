"""Discover executable repository modules and provide optional GUI metadata."""

from __future__ import annotations

import ast
from dataclasses import asdict, dataclass
import os
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
EXCLUDED_FOLDERS = {"gui", "mcp_tools", "shared", "tests"}
EXCLUDED_MODULES: set[str] = set()
CATEGORY_NAMES = {
    "angular": "Angular / Nx",
    "documents": "文件處理",
    "maintenance": "維護",
    "markdown": "Markdown",
    "scripts": "版本與發布",
    "text": "文字",
    "validation": "驗證",
}


@dataclass(frozen=True)
class ToolSpec:
    id: str
    module: str
    category: str
    name: str
    description: str
    example_args: str = ""
    warning: str = ""

    def payload(self) -> dict[str, str]:
        return asdict(self)


_OVERRIDES = (
    ToolSpec(
        "component-inventory",
        "angular.component_inventory",
        "Angular / Nx",
        "Component 盤點",
        "盤點 Nx 工作區的 Angular 元件, selector, template, style 與 custom element",
        '--root "C:\\path\\workspace" --json',
    ),
    ToolSpec(
        "form-contract-check",
        "angular.form_contract_check",
        "Angular / Nx",
        "Form 欄位規格檢查",
        "依 JSON 欄位規格比對 TypeScript form control 與 HTML formControlName",
        '--root "C:\\path\\workspace" --contract "C:\\path\\forms.json" --json',
    ),
    ToolSpec(
        "generator-preflight",
        "angular.generator_preflight",
        "Angular / Nx",
        "Generator Preflight",
        "在產生檔案前搜尋既有 identifier 與 selector 衝突",
        '--root "C:\\path\\project" --identifier FEATURE_ID --selector app-feature',
    ),
    ToolSpec(
        "change-impact-report",
        "angular.change_impact_report",
        "Angular / Nx",
        "Git 變更影響報告",
        "彙整 staged, unstaged, untracked 檔案與公開介面候選標記",
        '--root "C:\\path\\repository"',
    ),
    ToolSpec(
        "document-to-markdown",
        "documents.convert_to_markdown",
        "文件處理",
        "文件轉 Markdown",
        "將 PDF, XLSX, DOCX, PPTX, CSV 或 TXT 轉換為可搜尋的 Markdown",
        '"C:\\path\\spec.pdf" --dry-run',
        "正常模式可能建立或取代 Markdown output; 可先使用 --dry-run 或 --check",
    ),
    ToolSpec(
        "field-matrix",
        "documents.extract_field_matrix",
        "文件處理",
        "欄位規格矩陣",
        "從 PDF 轉換後的 Markdown 表格擷取欄位規格矩陣",
        '"C:\\path\\converted.md" --output "C:\\path\\matrix.md"',
    ),
    ToolSpec(
        "locate-markdown-extracts",
        "documents.locate_markdown_extracts",
        "文件處理",
        "Markdown 抽出版定位",
        "依來源路徑與 SHA-256 尋找 current, stale 或候選 Markdown 抽出版",
        '--source "C:\\path\\spec.pdf" --root "C:\\path\\markdown"',
    ),
    ToolSpec(
        "markdown-guard",
        "markdown.guarded_markdown_update",
        "Markdown",
        "Guarded Markdown Update",
        "以 SHA-256, dry-run, 原子取代與讀回檢查保護 Markdown 更新",
        '--target-file "C:\\path\\document.md" inspect progress',
        "只有明確加上 --write 才會更新目標檔; --in-place 是會先建立備份的備援模式",
    ),
    ToolSpec(
        "markdown-diff",
        "markdown.markdown_semantic_diff",
        "Markdown",
        "Markdown 結構差異",
        "比較兩份 Markdown 的標題, 清單項目, 表格列與 SHA-256",
        '--left "C:\\path\\before.md" --right "C:\\path\\after.md"',
    ),
    ToolSpec(
        "cleanup-artifacts",
        "maintenance.cleanup_work_artifacts",
        "維護",
        "開發產物清理",
        "預覽或隔離快取, build 與工作目錄, 並管理隔離區",
        '--root "C:\\path\\project"',
        "預設只預覽; --apply 會移動檔案, --purge-quarantine 會永久刪除舊隔離區",
    ),
    ToolSpec(
        "rewrite-git-history",
        "maintenance.rewrite_git_history",
        "維護",
        "Git History Identity Rewrite",
        "將所有 refs 的 author 與 committer 改為 repository local 身分",
        '--repo "C:\\path\\repository"',
        "破壞性歷史改寫; 執行前會建立 bundle 並要求透過 stdin 輸入 REWRITE",
    ),
    ToolSpec(
        "environment-consistency",
        "maintenance.environment_consistency",
        "維護",
        "環境一致性檢查",
        "唯讀比對兩個 Skills, runtime 或鏡像資料夾的路徑, 大小與 SHA-256",
        '--source "C:\\path\\source" --target "C:\\path\\mirror"',
    ),
    ToolSpec(
        "tokenizer",
        "text.tokenizer",
        "文字",
        "Token 計算",
        "使用 tiktoken 精算; 套件或編碼無法使用時改用字元比率估算",
        '--text "要計算的文字" --json',
    ),
    ToolSpec(
        "validation-index",
        "validation.validation_evidence_index",
        "驗證",
        "驗證證據索引",
        "索引 run-*/results.json, 不重跑 build, test 或瀏覽器測試",
        '--root "C:\\path\\validation-runs" --limit 20',
    ),
    ToolSpec(
        "prepare-release",
        "scripts.prepare_release",
        "版本與發布",
        "準備 Release Assets",
        "建置來源 ZIP 與兩個獨立核心 wheel, 並產生含 SHA-256 的 manifest",
        "--dry-run",
        "不加 --dry-run 會寫入 dist/<tag>; 不會執行 commit, push 或建立 GitHub Release",
    ),
    ToolSpec(
        "release",
        "scripts.release",
        "版本與發布",
        "驗證與發布 Release",
        "執行完整驗證, 準備 assets, 或在明確確認後發布 GitHub Release",
        "prepare --dry-run",
        "publish 會 push 目前 branch 並建立 GitHub Release; 執行前需人工檢查 diff 並輸入完整 Tag",
    ),

)

_OVERRIDES_BY_MODULE = {tool.module: tool for tool in _OVERRIDES}


def _is_main_guard(test: ast.expr) -> bool:
    if not isinstance(test, ast.Compare) or len(test.ops) != 1 or not isinstance(test.ops[0], ast.Eq):
        return False
    values = (test.left, *test.comparators)
    has_name = any(isinstance(value, ast.Name) and value.id == "__name__" for value in values)
    has_main = any(isinstance(value, ast.Constant) and value.value == "__main__" for value in values)
    return has_name and has_main


def _default_spec(folder: str, path: Path, tree: ast.Module, module: str) -> ToolSpec:
    description = (ast.get_docstring(tree) or f"執行 {module}").splitlines()[0]
    return ToolSpec(
        id=module.replace(".", "-").replace("_", "-"),
        module=module,
        category=CATEGORY_NAMES.get(folder, folder.replace("_", " ").title()),
        name=path.stem.replace("_", " ").title(),
        description=description,
    )


def _python_files(root: Path) -> list[Path]:
    paths: list[Path] = []
    for current, directory_names, file_names in os.walk(root):
        relative_directory = Path(current).relative_to(root)
        if not relative_directory.parts:
            directory_names[:] = [
                name for name in directory_names if not name.startswith(".") and name not in EXCLUDED_FOLDERS
            ]
        else:
            directory_names[:] = [
                name
                for name in directory_names
                if not name.startswith(".") and name not in {"__pycache__", "node_modules", "venv"}
            ]
        paths.extend(Path(current, name) for name in file_names if name.endswith(".py"))
    return paths


def discover_tools(root: Path = REPOSITORY_ROOT, warnings: list[str] | None = None) -> tuple[ToolSpec, ...]:
    tools = []
    warning_list = warnings if warnings is not None else []
    for path in sorted(_python_files(root), key=lambda item: item.as_posix().casefold()):
        relative = path.relative_to(root)
        if len(relative.parts) < 2:
            continue
        folder = relative.parts[0]
        if (
            any(part.startswith(".") for part in relative.parts[:-1])
            or folder in EXCLUDED_FOLDERS
            or path.name == "__init__.py"
        ):
            continue
        module = ".".join(relative.with_suffix("").parts)
        if module in EXCLUDED_MODULES:
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
        except (OSError, SyntaxError, UnicodeError) as exc:
            warning_list.append(f"{relative.as_posix()}: {type(exc).__name__}: {exc}")
            continue
        if not any(isinstance(node, ast.If) and _is_main_guard(node.test) for node in ast.walk(tree)):
            continue
        tools.append(_OVERRIDES_BY_MODULE.get(module) or _default_spec(folder, path, tree, module))
    return tuple(tools)


DISCOVERY_WARNINGS: list[str] = []
TOOLS = discover_tools(warnings=DISCOVERY_WARNINGS)
TOOLS_BY_ID = {tool.id: tool for tool in TOOLS}

if len(TOOLS_BY_ID) != len(TOOLS):
    raise RuntimeError("Duplicate GUI tool id")
