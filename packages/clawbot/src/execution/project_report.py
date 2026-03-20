"""
Execution Hub — 项目协作周报
场景9: 基于 git log 生成项目周报
"""
import logging
from pathlib import Path

from src.execution._utils import run_cmd

logger = logging.getLogger(__name__)


def generate_project_report(project_dir=None, days=7) -> str:
    """基于 git log 生成项目周报"""
    root = Path(project_dir or ".").expanduser().resolve()
    if not root.exists():
        return f"项目目录不存在: {root}"
    cmd = [
        "git", "log",
        f"--since={days} days ago",
        "--pretty=format:%h|%an|%ad|%s",
        "--date=short",
    ]
    commits = run_cmd(cmd, cwd=str(root), timeout=20)
    lines = [f"项目周报 ({root.name})", ""]
    if not commits:
        lines.append(f"最近 {days} 天无提交记录")
        return "\n".join(lines)

    commit_list = commits.strip().splitlines()
    lines.append(f"最近 {days} 天共 {len(commit_list)} 次提交:")
    lines.append("")

    # 按作者分组
    by_author = {}
    for line in commit_list:
        parts = line.split("|", 3)
        if len(parts) < 4:
            continue
        sha, author, date, msg = parts
        by_author.setdefault(author, []).append({"sha": sha, "date": date, "msg": msg})

    for author, items in by_author.items():
        lines.append(f"  {author} ({len(items)} 次提交):")
        for item in items[:5]:
            lines.append(f"    - [{item['sha']}] {item['msg']} ({item['date']})")
        if len(items) > 5:
            lines.append(f"    ... 及其他 {len(items) - 5} 次提交")
        lines.append("")

    return "\n".join(lines)
