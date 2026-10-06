"""Discover executable repository modules and provide optional GUI metadata."""

from __future__ import annotations

import ast
from dataclasses import asdict, dataclass, field
import json
import os
from pathlib import Path

from gui.runtime import is_bundled, resource_root


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
EXCLUDED_FOLDERS = {"gui", "distribution", "mcp_tools", "shared", "tests", "build", "dist", "packages", "src"}
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
    purpose: str = ""
    inputs: str = ""
    outputs: str = ""
    requirements: str = ""
    source_only: bool = False
    translations: dict[str, dict[str, str]] = field(default_factory=dict)

    def payload(self) -> dict[str, object]:
        details = _TOOL_DETAILS.get(self.id, {})
        return {
            **asdict(self),
            "purpose": self.purpose or details.get("purpose", self.description),
            "inputs": self.inputs or details.get("inputs", "依工具參數選擇檔案, 資料夾或文字"),
            "outputs": self.outputs or details.get("outputs", "結果顯示於執行輸出區; 寫入行為依 CLI 參數決定"),
            "requirements": self.requirements or details.get("requirements", "使用內建 Python 核心"),
            "source_only": self.source_only or self.module.startswith("scripts."),
        }


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
        "windows-process-audit",
        "maintenance.windows_process_audit",
        "維護",
        "Windows 程序稽核 / 清理",
        "唯讀列出開發程序身分、活動與父子關係, 只有明選且重新核對的自有候選才能終止",
        "--sample-seconds 1",
        "閒置或父程序消失不是清理授權; 終止不可復原, 必須提供稽核快照、--pid 及 --apply",
        purpose="確認 Python、cmd、PowerShell、Git 是否屬於自己的工作, 避免誤停 Codex、MCP、服務或其他工作",
        inputs="預設不需參數; 候選需明確 ownership 聲明, 清理需 15 分鐘內的快照及逐一 PID",
        outputs="遮蔽參數的身分、父子關係、CPU / I/O 與分類理由, 或逐項保留 / 終止結果",
        requirements="僅支援 Windows, 使用 Python 標準函式庫及系統 PowerShell / CIM, 不自動提權或安裝",
        translations={"en": {
            "name": "Windows process audit / cleanup",
            "description": "Audit developer process identity, activity and relationships; terminate only explicitly selected, reverified owned candidates",
            "warning": "Idle or missing parents are not cleanup permission. Termination is irreversible and requires a snapshot, --pid and --apply",
            "purpose": "Distinguish your disposable work from Codex, MCP, services and other active work",
            "inputs": "No arguments for audit; explicit work ownership for candidates, a fresh snapshot and individual PIDs for cleanup",
            "outputs": "Redacted identity, parent/child relationships, CPU / I/O, classification reasons and per-PID results",
            "requirements": "Windows only; Python standard library and system PowerShell / CIM, no automatic elevation or installation",
        }},
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

_TOOL_DETAILS = {
    "component-inventory": {
        "purpose": "接手或重整 Angular/Nx 專案時, 快速掌握元件位置與公開識別資訊",
        "inputs": "Nx 或 Angular workspace 根目錄",
        "outputs": "元件, selector, template, style 與 custom element 清單; 可輸出 JSON",
    },
    "form-contract-check": {
        "purpose": "修改表單前核對 TypeScript 與 HTML 是否符合已整理的欄位規格",
        "inputs": "專案根目錄與 JSON 欄位規格檔",
        "outputs": "缺少, 多餘或不一致的 form control 與 formControlName 報告",
    },
    "generator-preflight": {
        "purpose": "執行 generator 前先避免 identifier, selector 或檔名撞名",
        "inputs": "專案根目錄與預計使用的 identifier / selector",
        "outputs": "衝突候選與來源位置; 不會建立或修改專案檔案",
    },
    "change-impact-report": {
        "requirements": "需安裝 Git, 並選擇 Git repository",
        "purpose": "Review 或提交前快速整理目前 Git 變更可能影響的公開介面",
        "inputs": "Git repository 根目錄",
        "outputs": "staged, unstaged, untracked 檔案與公開介面候選報告",
    },
    "document-to-markdown": {
        "purpose": "把常用文件轉成可搜尋, 可比對且方便交給其他工具處理的 Markdown",
        "inputs": "一個或多個 PDF, XLSX, DOCX, PPTX, CSV 或 TXT; 可直接拖曳",
        "outputs": "預設在每個來源旁產生同名 .md, 並記錄來源與精確到秒的擷取時間",
    },
    "field-matrix": {
        "purpose": "從已轉成 Markdown 的表格整理欄位名稱, 型別與說明, 方便規格核對",
        "inputs": "包含表格的 Markdown 抽出版與輸出路徑",
        "outputs": "欄位規格矩陣 Markdown",
    },
    "locate-markdown-extracts": {
        "purpose": "同一來源有多份 Markdown 時, 找出目前版本與過期候選",
        "inputs": "原始文件與要搜尋的 Markdown 根目錄",
        "outputs": "依來源 metadata 與 SHA-256 分類的 current, stale 與候選清單",
    },
    "markdown-guard": {
        "purpose": "只更新指定 Markdown 範圍, 並避免來源在處理期間被其他程序改動",
        "inputs": "目標 Markdown, 操作名稱, 內容與選用的預期 SHA-256",
        "outputs": "預覽或受保護的更新結果; 寫入後會讀回驗證",
    },
    "markdown-diff": {
        "purpose": "比較兩份 Markdown 的結構差異, 不被單純空白或版面差異干擾",
        "inputs": "修改前與修改後的 Markdown",
        "outputs": "標題, 清單, 表格列與 SHA-256 差異",
    },
    "cleanup-artifacts": {
        "purpose": "清理測試快取與中途產物前先預覽, 降低誤刪風險",
        "inputs": "要檢查的專案根目錄與選用範圍",
        "outputs": "預覽清單, 隔離結果或隔離區清理結果",
    },
    "rewrite-git-history": {
        "requirements": "需安裝 Git, 並在目標 repository 設定 local user.name 與 user.email",
        "purpose": "修正整個 Git 歷史中的 author / committer 身分, 僅適合明確需要重寫歷史時使用",
        "inputs": "Git repository 與 repository local 身分設定",
        "outputs": "備份 bundle 與重寫後的 refs; 執行時必須再次輸入 REWRITE",
    },
    "environment-consistency": {
        "purpose": "確認兩份 Skills, runtime 或鏡像資料夾是否一致, 不直接同步內容",
        "inputs": "來源與目標資料夾",
        "outputs": "路徑, 大小與 SHA-256 差異報告",
    },
    "tokenizer": {
        "purpose": "估算 Prompt, 文件或 API payload 的 token 使用量",
        "inputs": "直接文字, 檔案或 stdin, 以及選用 encoding",
        "outputs": "字元數與 token 數; 套件不可用時清楚標示 fallback 估算",
    },
    "validation-index": {
        "purpose": "彙整既有驗證結果, 方便查找哪些項目已通過或仍未驗證",
        "inputs": "包含 run-*/results.json 的驗證資料夾",
        "outputs": "命令, 結果, 來源基準與未驗證項目的索引摘要",
    },
    "prepare-release": {
        "requirements": "需完整 my-py-tools 原始碼, 開發用 Python, pip, setuptools 與 wheel",
        "purpose": "發布前建立可核對的來源 ZIP, Python wheel 與 manifest",
        "inputs": "my-py-tools source checkout, 版本與選用輸出資料夾",
        "outputs": "Release assets 與 SHA-256 manifest; standalone GUI 需指向完整 source checkout",
    },
    "release": {
        "requirements": "需完整 my-py-tools 原始碼, 開發用 Python, Git 與已登入的 GitHub CLI",
        "purpose": "驗證已準備的 assets, 並在人工確認後發布 GitHub Release",
        "inputs": "乾淨且已提交的 my-py-tools source checkout, Tag 與 GitHub CLI 登入狀態",
        "outputs": "驗證結果或已發布的 GitHub Release; publish 會變更遠端狀態",
    },
}


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


def load_bundled_catalog() -> tuple[ToolSpec, ...]:
    values = json.loads((resource_root() / "gui/resources/catalog.json").read_text(encoding="utf-8"))
    return tuple(ToolSpec(**value) for value in values)


DISCOVERY_WARNINGS: list[str] = []
TOOLS = load_bundled_catalog() if is_bundled() else discover_tools(warnings=DISCOVERY_WARNINGS)
TOOLS_BY_ID = {tool.id: tool for tool in TOOLS}

if len(TOOLS_BY_ID) != len(TOOLS):
    raise RuntimeError("Duplicate GUI tool id")
