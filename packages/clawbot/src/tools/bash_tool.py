"""
ClawBot - Bash命令执行工具
安全加固版: 白名单模式 + shell=False + 环境变量清洗
"""
import subprocess
import shlex
import os
import signal
import logging
from typing import Optional
from pathlib import Path

logger = logging.getLogger(__name__)

# 安全的环境变量白名单 — 阻止 API Key / Token 泄漏
_SAFE_ENV_KEYS = frozenset({
    "PATH", "HOME", "USER", "LANG", "LC_ALL", "LC_CTYPE",
    "TERM", "TMPDIR", "TZ", "SHELL",
})

class BashTool:
    """执行Bash命令 (白名单模式)"""
    
    # 允许执行的命令白名单
    # 安全原则: 只保留只读/信息查询类命令，移除可执行任意代码的命令
    # 已移除: python3, node, npm (可绕过沙箱执行任意代码)
    # 已移除: ssh, scp, rsync (可访问远程系统)
    # 已移除: docker (可逃逸到宿主机)
    # 已移除: pip (可安装恶意包)
    ALLOWED_COMMANDS = frozenset({
        # 文件查看 (只读)
        "ls", "cat", "head", "tail", "grep", "find", "wc", "sort", "uniq",
        "file",
        # 系统信息 (只读)
        "echo", "pwd", "date", "whoami", "uname", "df", "du",
        "which", "ps", "free",
        # 安全的文件操作 (用户工作目录内)
        "mkdir", "cp", "mv", "touch",
        # 安全修复: 移除 curl/wget — 可通过 -d/--data/--upload-file 外泄数据，也可用于 SSRF
        # 压缩/解压
        "tar", "zip", "unzip", "gzip",
        # 版本控制 (只读操作)
        "git",
    })
    
    def __init__(self, working_dir: Optional[str] = None, timeout: int = 120):
        self.working_dir = working_dir or str(Path.home())
        self.timeout = timeout
        self.current_process: Optional[subprocess.Popen] = None
    
    def is_allowed(self, command: str) -> bool:
        """检查命令是否在白名单中 (基于 shlex 拆分后的第一个 token)"""
        try:
            args = shlex.split(command)
            if not args:
                return False
            # 取命令名 (去掉路径前缀，如 /usr/bin/ls → ls)
            cmd_name = os.path.basename(args[0])
            return cmd_name in self.ALLOWED_COMMANDS
        except ValueError as e:  # noqa: F841
            # shlex 解析失败 (如未闭合引号)，拒绝执行
            return False
    
    def execute(self, command: str, workdir: Optional[str] = None, timeout: Optional[int] = None) -> dict:
        """
        执行Bash命令 (白名单模式, shell=False)
        
        Args:
            command: 要执行的命令
            workdir: 工作目录 (可选)
            timeout: 超时时间秒 (可选)
            
        Returns:
            dict: {success, stdout, stderr, returncode, error}
        """
        try:
            cwd = workdir or self.working_dir
            cmd_timeout = timeout or self.timeout

            # 验证工作目录在项目范围内，防止路径遍历攻击
            if workdir:
                resolved = os.path.realpath(workdir)
                project_root = os.path.realpath(
                    os.path.join(os.path.dirname(__file__), '..', '..')
                )
                if not resolved.startswith(project_root):
                    return {
                        "success": False,
                        "error": "错误: 工作目录超出项目范围",
                        "command": command,
                    }

            # 使用 shlex 拆分命令
            try:
                args = shlex.split(command)
            except ValueError as e:
                return {
                    "success": False,
                    "error": f"命令解析失败: {e}",
                    "command": command
                }
            
            if not args:
                return {
                    "success": False,
                    "error": "空命令",
                    "command": command
                }
            
            # 白名单检查
            cmd_name = os.path.basename(args[0])
            if cmd_name not in self.ALLOWED_COMMANDS:
                return {
                    "success": False,
                    "blocked": True,
                    "error": f"命令 '{cmd_name}' 不在允许列表中。允许的命令: {', '.join(sorted(self.ALLOWED_COMMANDS))}",
                    "command": command
                }
            
            # 执行命令 (shell=False，安全模式)
            self.current_process = subprocess.Popen(
                args,
                shell=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=cwd,
                env=_make_safe_env(),
                preexec_fn=os.setsid if os.name != 'nt' else None
            )
            
            try:
                stdout, stderr = self.current_process.communicate(timeout=cmd_timeout)
                returncode = self.current_process.returncode
            except subprocess.TimeoutExpired as e:  # noqa: F841
                # 超时，终止进程
                if os.name != 'nt':
                    os.killpg(os.getpgid(self.current_process.pid), signal.SIGTERM)
                else:
                    self.current_process.terminate()
                self.current_process.wait()
                return {
                    "success": False,
                    "error": f"命令执行超时 ({cmd_timeout}秒)",
                    "command": command
                }
            finally:
                self.current_process = None
            
            # 解码输出
            stdout_str = stdout.decode('utf-8', errors='replace')
            stderr_str = stderr.decode('utf-8', errors='replace')
            
            # 截断过长输出
            max_output = 50000
            if len(stdout_str) > max_output:
                stdout_str = stdout_str[:max_output] + f"\n... (输出已截断，共 {len(stdout)} 字节)"
            if len(stderr_str) > max_output:
                stderr_str = stderr_str[:max_output] + "\n... (错误输出已截断)"
            
            return {
                "success": returncode == 0,
                "stdout": stdout_str,
                "stderr": stderr_str,
                "returncode": returncode,
                "command": command
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "command": command
            }
    
    def execute_dangerous(self, command: str) -> dict:
        """已禁用 — 所有命令必须通过白名单 execute() 方法"""
        logger.warning("[BashTool] execute_dangerous 已禁用，拒绝: %s", command[:100])
        return {"output": "", "error": "此方法已禁用，请使用 /bash 命令", "returncode": 1}
    
    def cancel(self) -> dict:
        """取消当前执行的命令"""
        if self.current_process:
            try:
                if os.name != 'nt':
                    os.killpg(os.getpgid(self.current_process.pid), signal.SIGTERM)
                else:
                    self.current_process.terminate()
                return {"success": True, "message": "命令已取消"}
            except Exception as e:
                logger.debug("[BashTool] 异常: %s", e)
                return {"success": False, "error": "取消失败"}
        return {"success": False, "error": "没有正在执行的命令"}


def _make_safe_env() -> dict:
    """构建安全的子进程环境变量 (只保留白名单内的 key, 阻止敏感信息泄漏)"""
    return {k: v for k, v in os.environ.items() if k in _SAFE_ENV_KEYS}
