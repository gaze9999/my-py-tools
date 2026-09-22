from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path


EXCLUDE_BEGIN = "# BEGIN git-history-rewrite-helper"
EXCLUDE_END = "# END git-history-rewrite-helper"


def run_git(
    *args: str,
    cwd: Path | None = None,
    capture: bool = False,
    check: bool = True,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=capture,
        check=check,
        env=env,
    )


def get_repo_root(start: Path) -> Path | None:
    result = run_git(
        "rev-parse",
        "--show-toplevel",
        cwd=start,
        capture=True,
        check=False,
    )

    if result.returncode != 0:
        return None

    return Path(result.stdout.strip()).resolve()


def get_git_common_dir(repo: Path) -> Path:
    result = run_git(
        "rev-parse",
        "--git-common-dir",
        cwd=repo,
        capture=True,
    )

    git_dir = Path(result.stdout.strip())

    if not git_dir.is_absolute():
        git_dir = repo / git_dir

    return git_dir.resolve()


def get_local_config(repo: Path, key: str) -> str:
    result = run_git(
        "config",
        "--local",
        "--get",
        key,
        cwd=repo,
        capture=True,
        check=False,
    )

    if result.returncode != 0:
        return ""

    return result.stdout.strip()


def update_git_exclude(repo: Path) -> Path:
    """
    自動管理 .git/info/exclude 中屬於本 script 的區塊

    只排除本工具建立的 repository-local .bundle 目錄
    """
    git_common_dir = get_git_common_dir(repo)

    exclude_path = git_common_dir / "info" / "exclude"
    exclude_path.parent.mkdir(parents=True, exist_ok=True)

    if exclude_path.exists():
        original = exclude_path.read_text(
            encoding="utf-8",
            errors="replace",
        )
    else:
        original = ""

    # 移除上一輪由本工具管理的區塊
    block_pattern = re.compile(
        rf"(?ms)"
        rf"^[ \t]*{re.escape(EXCLUDE_BEGIN)}[ \t]*\r?\n"
        rf".*?"
        rf"^[ \t]*{re.escape(EXCLUDE_END)}[ \t]*"
        rf"(?:\r?\n)?"
    )

    cleaned = block_pattern.sub("", original).rstrip("\r\n")

    managed_block = "\n".join(
        [
            EXCLUDE_BEGIN,
            "/.bundle/",
            EXCLUDE_END,
        ]
    )

    if cleaned:
        new_content = f"{cleaned}\n\n{managed_block}\n"
    else:
        new_content = f"{managed_block}\n"

    exclude_path.write_text(
        new_content,
        encoding="utf-8",
        newline="\n",
    )

    return exclude_path


def has_uncommitted_changes(repo: Path) -> bool:
    result = run_git(
        "status",
        "--porcelain",
        "--untracked-files=normal",
        cwd=repo,
        capture=True,
    )

    return bool(result.stdout.strip())


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Rewrite every commit author/committer to the selected repository's local Git identity."
    )
    parser.add_argument(
        "--repo",
        type=Path,
        default=Path.cwd(),
        help="Repository or a directory inside it (default: current directory)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    selected = args.repo.expanduser().resolve()
    if not selected.is_dir():
        print(f"錯誤: repository 路徑不存在或不是目錄: {selected}")
        return 1
    try:
        repo = get_repo_root(selected)
    except (OSError, subprocess.SubprocessError) as error:
        print(f"錯誤: 無法讀取 Git repository: {error}")
        return 1

    if repo is None:
        print("錯誤: 目前所在位置不是 Git repository")
        return 1

    script_path = Path(__file__).resolve()

    # ---------------------------------------------------------
    # 1. 優先設定 local exclude
    # ---------------------------------------------------------

    try:
        exclude_path = update_git_exclude(repo)
    except (OSError, RuntimeError, subprocess.SubprocessError) as error:
        print(f"錯誤: {error}")
        return 1

    # ---------------------------------------------------------
    # 2. 建立 bundle 目錄
    # ---------------------------------------------------------

    bundle_dir = repo / ".bundle"
    bundle_dir.mkdir(parents=True, exist_ok=True)

    print("Local exclude 已設定")
    print(f"Exclude    : {exclude_path}")
    print(f"Tool       : {script_path}")
    print("Bundle     : .bundle/")
    print()

    # ---------------------------------------------------------
    # 4. 讀取 repository local identity
    # ---------------------------------------------------------

    user_name = get_local_config(repo, "user.name")
    user_email = get_local_config(repo, "user.email")

    if not user_name:
        print("錯誤: 此 repository 沒有設定 local user.name")
        print()
        print('請先執行:')
        print('  git config --local user.name "Your Name"')
        return 1

    if not user_email:
        print("錯誤: 此 repository 沒有設定 local user.email")
        print()
        print("請先執行:")
        print('  git config --local user.email "you@example.com"')
        return 1

    # script 與 .bundle 已 exclude 後才檢查 working tree
    if has_uncommitted_changes(repo):
        print("錯誤: repository 有尚未 commit 的變更")
        print()
        print("請先使用以下指令確認:")
        print("  git status")
        print()
        print("將其他變更 commit 或 stash 後再執行")
        return 1

    print(f"Repository : {repo}")
    print(f"user.name  : {user_name}")
    print(f"user.email : {user_email}")
    print()
    print("將重寫所有 Git history:")
    print(f"Author    -> {user_name} <{user_email}>")
    print(f"Committer -> {user_name} <{user_email}>")
    print()
    print("所有受影響 commit SHA 都會改變")
    print()

    confirm = input('輸入 "REWRITE" 繼續: ').strip()

    if confirm != "REWRITE":
        print("已取消")
        return 0

    # ---------------------------------------------------------
    # 5. 建立 bundle 備份
    # ---------------------------------------------------------

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")

    backup_path = (
        bundle_dir
        / f"git-history-backup-{timestamp}.bundle"
    )

    print()
    print(f"建立備份: {backup_path}")

    run_git(
        "bundle",
        "create",
        str(backup_path),
        "--all",
        cwd=repo,
    )

    if not backup_path.exists():
        print("錯誤: bundle 備份建立失敗")
        return 1

    # ---------------------------------------------------------
    # 6. Rewrite identity
    # ---------------------------------------------------------

    filter_script = """
export GIT_AUTHOR_NAME="$NEW_GIT_NAME"
export GIT_AUTHOR_EMAIL="$NEW_GIT_EMAIL"
export GIT_COMMITTER_NAME="$NEW_GIT_NAME"
export GIT_COMMITTER_EMAIL="$NEW_GIT_EMAIL"
""".strip()

    env = os.environ.copy()

    env["NEW_GIT_NAME"] = user_name
    env["NEW_GIT_EMAIL"] = user_email

    # 關閉 filter-branch deprecation warning
    env["FILTER_BRANCH_SQUELCH_WARNING"] = "1"

    print()
    print("開始重寫 Git history...")

    try:
        run_git(
            "filter-branch",
            "--force",
            "--env-filter",
            filter_script,
            "--tag-name-filter",
            "cat",
            "--",
            "--all",
            cwd=repo,
            env=env,
        )

    except subprocess.CalledProcessError as error:
        print()
        print("Git history rewrite 失敗")
        print(f"Backup: {backup_path}")
        print(f"Exit code: {error.returncode}")
        return error.returncode

    # ---------------------------------------------------------
    # 7. 完成
    # ---------------------------------------------------------

    print()
    print("完成")
    print()
    print(f"Author    : {user_name} <{user_email}>")
    print(f"Committer : {user_name} <{user_email}>")
    print(f"Backup    : {backup_path}")
    print(f"Tool      : {script_path}")
    print(f"Exclude   : {exclude_path}")

    print()
    print("檢查目前 branches/tags:")
    print(
        '  git log '
        '--branches --tags '
        '--format="%h | Author: %an <%ae> | '
        'Committer: %cn <%ce>"'
    )

    print()
    print("確認無誤後若要更新 remote:")
    print("  git push --force-with-lease --all origin")
    print("  git push --force-with-lease --tags origin")

    return 0


if __name__ == "__main__":
    sys.exit(main())
