"""CLI-Anything 桥接 — 集成港大 CLI-Anything (31K★) 到 OpenClaw

让用户通过 Telegram 命令控制桌面软件:
- /cli list          — 列出已安装的 CLI 工具
- /cli run <tool> <args>  — 执行 CLI 命令
- /cli install <tool>     — 安装新的 CLI 工具

CLI-Anything 可以把任何桌面 GUI 软件变成命令行工具，
OpenClaw 通过这个桥接层让用户在 Telegram 里远程控制桌面软件。

架构:
  Telegram /cli 命令 → CLIAnythingManager → asyncio.subprocess → cli-anything-*

降级: CLI-Anything 未安装时所有操作返回友好提示。
"""

import asyncio
import logging
import re
import shutil
import time
from typing import Any, Optional

logger = logging.getLogger(__name__)

# ── 工具名称合法性校验（只允许字母数字和连字符，防注入） ──
_TOOL_NAME_PATTERN = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9\-]*$")

# ── 已发现工具的缓存 ──
_cli_cache: list[dict[str, str]] = []
_cli_cache_ts: float = 0.0
_CLI_CACHE_TTL: float = 60.0  # 缓存 60 秒


def _is_valid_tool_name(name: str) -> bool:
    """检查工具名称是否合法（只允许字母数字和连字符，防止命令注入）"""
    if not name or len(name) > 64:
        return False
    return bool(_TOOL_NAME_PATTERN.match(name))


def discover_installed_clis() -> list[dict[str, str]]:
    """扫描 PATH 中已安装的 cli-anything-* 工具

    工作原理:
    1. 在 PATH 里搜索 cli-anything-* 开头的可执行文件
    2. 对每个找到的工具执行 --help 获取描述
    3. 结果缓存 60 秒避免频繁扫描

    返回: [{"name": "gimp", "path": "/usr/local/bin/cli-anything-gimp", "description": "..."}]
    """
    global _cli_cache, _cli_cache_ts

    # 缓存未过期，直接返回
    now = time.time()
    if _cli_cache and (now - _cli_cache_ts) < _CLI_CACHE_TTL:
        return _cli_cache

    import os
    import subprocess

    tools: list[dict[str, str]] = []
    seen_names: set = set()

    # 遍历 PATH 中的每个目录
    path_dirs = os.environ.get("PATH", "").split(os.pathsep)
    for dir_path in path_dirs:
        if not os.path.isdir(dir_path):
            continue
        try:
            for entry in os.listdir(dir_path):
                if not entry.startswith("cli-anything-"):
                    continue
                # 提取工具名（去掉 cli-anything- 前缀）
                tool_name = entry[len("cli-anything-"):]
                if tool_name in seen_names:
                    continue
                seen_names.add(tool_name)

                full_path = os.path.join(dir_path, entry)
                if not os.access(full_path, os.X_OK):
                    continue

                # 执行 --help 获取描述
                description = ""
                try:
                    result = subprocess.run(
                        [full_path, "--help"],
                        capture_output=True,
                        text=True,
                        timeout=5,
                    )
                    # 取 --help 输出的第一行作为描述
                    lines = (result.stdout or "").strip().split("\n")
                    description = lines[0] if lines else "无描述"
                except Exception:
                    # 任何异常都不应阻止工具发现（可能是权限、超时等）
                    description = "（无法获取描述）"

                tools.append({
                    "name": tool_name,
                    "path": full_path,
                    "description": description,
                })
        except PermissionError:
            continue

    # 更新缓存
    _cli_cache = tools
    _cli_cache_ts = now
    logger.info("[CLIAnything] 发现 %d 个已安装工具", len(tools))
    return tools


async def run_cli_command(
    tool_name: str,
    args: list[str] | None = None,
    timeout: int = 30,
) -> dict[str, Any]:
    """执行一个 CLI-Anything 工具命令

    安全措施:
    1. 工具名只允许字母数字+连字符，防止命令注入
    2. 验证工具确实在已安装列表中（不允许执行任意命令）
    3. 强制超时，防止卡住

    参数:
        tool_name: 工具名称（不含 cli-anything- 前缀）
        args: 传递给工具的参数列表
        timeout: 超时秒数，默认 30 秒

    返回: {"success": bool, "output": str, "exit_code": int, "duration_ms": int}
    """
    if args is None:
        args = []

    # 安全校验: 工具名合法性
    if not _is_valid_tool_name(tool_name):
        return {
            "success": False,
            "output": f"工具名 '{tool_name}' 格式不合法（只允许字母数字和连字符）",
            "exit_code": -1,
            "duration_ms": 0,
        }

    # 安全校验: 检查工具是否已安装
    installed = discover_installed_clis()
    tool_entry = next((t for t in installed if t["name"] == tool_name), None)
    if tool_entry is None:
        available = ", ".join(t["name"] for t in installed) or "（无）"
        return {
            "success": False,
            "output": f"工具 '{tool_name}' 未安装。已安装的工具: {available}",
            "exit_code": -1,
            "duration_ms": 0,
        }

    # 构建命令（自动追加 --json 获取机器可读输出）
    cmd = [tool_entry["path"]] + list(args) + ["--json"]

    start_ms = time.monotonic()
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(), timeout=timeout
        )
        duration_ms = int((time.monotonic() - start_ms) * 1000)

        output = (stdout or b"").decode("utf-8", errors="replace")
        err_output = (stderr or b"").decode("utf-8", errors="replace")

        # 合并 stderr 到输出（如果有的话）
        if err_output and proc.returncode != 0:
            output = output + "\n" + err_output if output else err_output

        return {
            "success": proc.returncode == 0,
            "output": output.strip(),
            "exit_code": proc.returncode or 0,
            "duration_ms": duration_ms,
        }

    except TimeoutError:
        duration_ms = int((time.monotonic() - start_ms) * 1000)
        # 超时后尝试终止进程
        try:
            proc.kill()  # type: ignore[possibly-undefined]
        except (ProcessLookupError, OSError) as e:
            logger.debug("终止超时进程时进程已退出: %s", e)
        return {
            "success": False,
            "output": f"命令执行超时（{timeout} 秒）",
            "exit_code": -1,
            "duration_ms": duration_ms,
        }
    except FileNotFoundError:
        return {
            "success": False,
            "output": f"工具可执行文件不存在: {tool_entry['path']}",
            "exit_code": -1,
            "duration_ms": 0,
        }
    except OSError as e:
        return {
            "success": False,
            "output": f"执行失败: {e}",
            "exit_code": -1,
            "duration_ms": 0,
        }


async def install_cli_tool(tool_name: str) -> dict[str, Any]:
    """通过 pip 安装一个 CLI-Anything 工具

    安全措施:
    1. 工具名只允许字母数字+连字符
    2. 通过 pip install cli-anything-<name> 安装

    参数:
        tool_name: 要安装的工具名称

    返回: {"success": bool, "message": str}
    """
    # 安全校验
    if not _is_valid_tool_name(tool_name):
        return {
            "success": False,
            "message": f"工具名 '{tool_name}' 格式不合法（只允许字母数字和连字符）",
        }

    package_name = f"cli-anything-{tool_name}"
    logger.info("[CLIAnything] 开始安装 %s", package_name)

    try:
        # 找到当前 Python 对应的 pip
        import sys
        python_path = sys.executable

        proc = await asyncio.create_subprocess_exec(
            python_path, "-m", "pip", "install", package_name,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(), timeout=120  # pip 安装可能较慢
        )

        _output = (stdout or b"").decode("utf-8", errors="replace")
        err_output = (stderr or b"").decode("utf-8", errors="replace")

        if proc.returncode == 0:
            # 清除缓存，下次 discover 时重新扫描
            global _cli_cache_ts
            _cli_cache_ts = 0.0
            logger.info("[CLIAnything] 安装成功: %s", package_name)
            return {
                "success": True,
                "message": f"✅ {package_name} 安装成功",
            }
        else:
            logger.warning(
                "[CLIAnything] 安装失败: %s, 退出码=%d",
                package_name, proc.returncode,
            )
            # 提取关键错误信息（不暴露完整堆栈）
            short_err = err_output.strip().split("\n")[-1] if err_output else "未知错误"
            return {
                "success": False,
                "message": f"❌ 安装 {package_name} 失败: {short_err}",
            }

    except TimeoutError:
        return {
            "success": False,
            "message": f"❌ 安装 {package_name} 超时（120 秒）",
        }
    except Exception as e:
        logger.error("[CLIAnything] 安装异常: %s", e)
        return {
            "success": False,
            "message": "❌ 安装过程出错",
        }


class CLIAnythingManager:
    """CLI-Anything 管理器 — 单例模式

    统一管理所有 CLI-Anything 工具的发现、执行、安装。
    线程安全，使用 asyncio 锁防止并发操作冲突。

    用法::

        mgr = CLIAnythingManager.get_instance()
        tools = mgr.discover()
        result = await mgr.run("gimp", ["project", "new"])
    """

    _instance: Optional["CLIAnythingManager"] = None
    _lock: asyncio.Lock | None = None

    @classmethod
    def get_instance(cls) -> "CLIAnythingManager":
        """获取单例实例"""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self):
        # asyncio.Lock 延迟创建（可能还没有事件循环）
        self._async_lock: asyncio.Lock | None = None

    def _get_lock(self) -> asyncio.Lock:
        """延迟获取 asyncio 锁（避免在事件循环外创建）"""
        if self._async_lock is None:
            self._async_lock = asyncio.Lock()
        return self._async_lock

    def discover(self) -> list[dict[str, str]]:
        """发现已安装的 CLI 工具（同步方法，带缓存）"""
        return discover_installed_clis()

    async def run(
        self,
        tool_name: str,
        args: list[str] | None = None,
        timeout: int = 30,
    ) -> dict[str, Any]:
        """执行 CLI 命令（线程安全）"""
        async with self._get_lock():
            return await run_cli_command(tool_name, args, timeout)

    async def install(self, tool_name: str) -> dict[str, Any]:
        """安装 CLI 工具（线程安全）"""
        async with self._get_lock():
            return await install_cli_tool(tool_name)

    def get_status(self) -> dict[str, Any]:
        """获取 CLI-Anything 整体状态"""
        tools = self.discover()
        # 检查 cli-anything 主命令是否存在
        has_cli_anything = shutil.which("cli-anything") is not None

        return {
            "available": has_cli_anything or len(tools) > 0,
            "cli_anything_installed": has_cli_anything,
            "tool_count": len(tools),
            "tools": [{"name": t["name"], "description": t["description"]} for t in tools],
        }
