"""
GitHub 自动更新检测器

定期检查 GitHub 仓库是否有新版本，通知用户更新。
支持:
- 检查远程 HEAD 与本地 HEAD 差异
- 检查 release/tag 版本号
- 通知回调
"""
import os
import logging
import subprocess
from pathlib import Path
from typing import Callable, Dict, Optional

logger = logging.getLogger(__name__)


def get_local_head(repo_dir: str = None) -> str:
    """获取本地 HEAD commit hash"""
    cwd = repo_dir or str(Path(__file__).resolve().parent.parent)
    try:
        cp = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=cwd, capture_output=True, text=True, timeout=10, check=False,
        )
        return cp.stdout.strip() if cp.returncode == 0 else ""
    except Exception:
        return ""


def get_remote_head(repo_dir: str = None, remote: str = "origin", branch: str = "main") -> str:
    """获取远程 HEAD commit hash (不 fetch)"""
    cwd = repo_dir or str(Path(__file__).resolve().parent.parent)
    try:
        cp = subprocess.run(
            ["git", "ls-remote", remote, f"refs/heads/{branch}"],
            cwd=cwd, capture_output=True, text=True, timeout=15, check=False,
        )
        if cp.returncode == 0 and cp.stdout.strip():
            return cp.stdout.strip().split()[0]
        return ""
    except Exception:
        return ""


def get_local_version(repo_dir: str = None) -> str:
    """获取本地最新 tag 版本号"""
    cwd = repo_dir or str(Path(__file__).resolve().parent.parent)
    try:
        cp = subprocess.run(
            ["git", "describe", "--tags", "--abbrev=0"],
            cwd=cwd, capture_output=True, text=True, timeout=10, check=False,
        )
        return cp.stdout.strip() if cp.returncode == 0 else "unknown"
    except Exception:
        return "unknown"


def get_commits_behind(repo_dir: str = None, remote: str = "origin", branch: str = "main") -> int:
    """计算本地落后远程多少个 commit"""
    cwd = repo_dir or str(Path(__file__).resolve().parent.parent)
    try:
        # 先 fetch
        subprocess.run(
            ["git", "fetch", remote, branch, "--quiet"],
            cwd=cwd, capture_output=True, timeout=20, check=False,
        )
        cp = subprocess.run(
            ["git", "rev-list", "--count", f"HEAD..{remote}/{branch}"],
            cwd=cwd, capture_output=True, text=True, timeout=10, check=False,
        )
        if cp.returncode == 0:
            return int(cp.stdout.strip())
        return 0
    except Exception:
        return 0


def check_for_updates(repo_dir: str = None) -> Dict:
    """检查是否有可用更新"""
    local_head = get_local_head(repo_dir)
    remote_head = get_remote_head(repo_dir)
    local_version = get_local_version(repo_dir)

    if not local_head or not remote_head:
        return {
            "has_update": False,
            "error": "无法获取版本信息",
            "local_version": local_version,
        }

    has_update = local_head != remote_head
    result = {
        "has_update": has_update,
        "local_head": local_head[:8],
        "remote_head": remote_head[:8],
        "local_version": local_version,
    }

    if has_update:
        behind = get_commits_behind(repo_dir)
        result["commits_behind"] = behind
        result["message"] = f"有 {behind} 个新提交可用 (当前: {local_version})"

    return result


async def auto_check_and_notify(
    notify_fn: Callable = None,
    repo_dir: str = None,
) -> Dict:
    """自动检查更新并通知"""
    result = check_for_updates(repo_dir)
    if result.get("has_update") and notify_fn:
        msg = (
            f"🔄 ClawBot 有新版本可用\n"
            f"当前: {result.get('local_version', '?')} ({result.get('local_head', '?')})\n"
            f"远程: {result.get('remote_head', '?')}\n"
            f"落后: {result.get('commits_behind', '?')} 个提交\n"
            f"运行 `git pull` 更新"
        )
        try:
            await notify_fn(msg)
        except Exception as e:
            logger.debug(f"[Updater] notify failed: {e}")
    return result
