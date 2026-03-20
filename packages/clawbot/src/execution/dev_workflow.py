"""
Execution Hub — 开发流程自动化
场景10: 运行自定义开发工作流命令
"""
import os
import logging
from pathlib import Path

from src.execution._utils import run_cmd

logger = logging.getLogger(__name__)


def run_dev_workflow(project_dir=None) -> dict:
    """运行开发流程自动化命令"""
    root = Path(project_dir or ".").expanduser().resolve()
    if not root.exists():
        return {"success": False, "error": f"目录不存在: {root}"}

    custom = os.getenv("OPS_DEV_WORKFLOW_COMMANDS", "").strip()
    if not custom:
        # 默认工作流: lint + test
        commands = [
            ["python", "-m", "pytest", "--tb=short", "-q"],
        ]
    else:
        commands = [cmd.strip().split() for cmd in custom.split(";") if cmd.strip()]

    results = []
    for cmd in commands:
        output = run_cmd(cmd, cwd=str(root), timeout=120)
        results.append({
            "command": " ".join(cmd),
            "output": output[:2000] if output else "(no output)",
            "success": bool(output),
        })

    all_ok = all(r["success"] for r in results)
    return {
        "success": all_ok,
        "project": root.name,
        "results": results,
        "summary": f"{len(results)} 个命令执行完毕，{'全部成功' if all_ok else '部分失败'}",
    }
