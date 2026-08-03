"""
ClawBot - Bash命令执行工具
安全加固版: 白名单模式 + shell=False + 环境变量清洗
"""
import logging
import os
import shlex
import signal
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

# 安全的环境变量白名单 — 阻止 API Key / Token 泄漏
_SAFE_ENV_KEYS = frozenset({
    "PATH", "HOME", "USER", "LANG", "LC_ALL", "LC_CTYPE",
    "TERM", "TMPDIR", "TZ", "SHELL",
})


class BashTool:
    """执行Bash命令 (白名单模式)"""

    # 只保留只读命令；文件写入必须走显式确认的专用能力。
    ALLOWED_COMMANDS = frozenset({
        "ls", "cat", "head", "tail", "grep", "uniq",
        "echo", "pwd", "date", "whoami", "uname", "df",
        "which", "free",
    })
    PATH_COMMANDS = frozenset({
        "ls", "cat", "head", "tail", "grep", "uniq", "df",
    })
    SAFE_GREP_SHORT_FLAGS = frozenset("EFGHhilLnoqrsvwxc")
    SAFE_GREP_LONG_OPTIONS = frozenset({
        "--basic-regexp", "--extended-regexp", "--fixed-strings", "--perl-regexp",
        "--ignore-case", "--no-ignore-case", "--word-regexp", "--line-regexp",
        "--invert-match", "--line-number", "--with-filename", "--no-filename",
        "--files-with-matches", "--files-without-match", "--only-matching",
        "--quiet", "--silent", "--no-messages", "--text", "--binary",
        "--recursive", "--count",
    })

    def __init__(self, working_dir: str | None = None, timeout: int = 120):
        self.working_dir = str(Path(working_dir or Path.home()).resolve())
        self.timeout = timeout
        self.current_process: subprocess.Popen | None = None

    def is_allowed(self, command: str) -> bool:
        """检查命令、参数和路径是否满足只读白名单。"""
        allowed, _error, _args, _cwd = self._validate(command, None)
        return allowed

    @staticmethod
    def _is_within(path: Path, root: Path) -> bool:
        """判断解析后的路径是否位于配置根目录内。"""
        try:
            path.relative_to(root)
            return True
        except ValueError:
            return False

    def _resolve_workdir(self, workdir: str | None) -> tuple[Path | None, str]:
        """解析工作目录并阻断目录穿越和同前缀目录绕过。"""
        root = Path(self.working_dir).resolve()
        candidate = Path(workdir) if workdir else root
        if not candidate.is_absolute():
            candidate = root / candidate
        resolved = candidate.resolve()
        if not self._is_within(resolved, root):
            return None, "错误: 工作目录超出项目范围"
        if not resolved.is_dir():
            return None, "错误: 工作目录不存在或不是目录"
        return resolved, ""

    def _validate_path(self, token: str, cwd: Path) -> bool:
        """验证单个文件参数，现有软链接也必须解析在根目录内。"""
        if token in {"", "-"}:
            return True
        path = Path(token)
        if not path.is_absolute():
            path = cwd / path
        return self._is_within(path.resolve(), Path(self.working_dir).resolve())

    def _grep_path_operands(self, args: list[str]) -> list[str] | None:
        """只接受无需附加参数的 grep 选项，并返回显式文件操作数。"""
        positional: list[str] = []
        parsing_options = True
        for token in args[1:]:
            if parsing_options and token == "--":
                parsing_options = False
                continue
            if parsing_options and token.startswith("--"):
                if token not in self.SAFE_GREP_LONG_OPTIONS:
                    return None
                continue
            if parsing_options and token.startswith("-") and token != "-":
                if not token[1:] or not set(token[1:]).issubset(self.SAFE_GREP_SHORT_FLAGS):
                    return None
                continue
            positional.append(token)

        if not positional:
            return None
        return positional[1:]

    def _path_operands(self, command: str, args: list[str]) -> list[str]:
        """提取需要限制在工作目录内的路径参数。"""
        values = args[1:]
        if command == "uniq":
            positional = [token for token in values if not token.startswith("-")]
            # uniq 的第二个位置参数是输出文件，自动工具不允许该形式。
            return positional

        return [token for token in values if not token.startswith("-")]

    def _validate(
        self,
        command: str,
        workdir: str | None,
    ) -> tuple[bool, str, list[str], Path | None]:
        """统一验证命令，返回可直接交给 shell=False 的参数。"""
        if not command or len(command) > 4096 or any(char in command for char in ("\x00", "\r", "\n")):
            return False, "空命令或命令长度/字符不合法", [], None

        try:
            args = shlex.split(command)
        except ValueError as e:
            return False, f"命令解析失败: {e}", [], None
        if not args or len(args) > 128 or any(len(arg) > 2048 for arg in args):
            return False, "命令参数数量或长度超限", [], None

        executable = args[0]
        command_name = os.path.basename(executable)
        if executable != command_name or command_name not in self.ALLOWED_COMMANDS:
            return (
                False,
                f"命令 '{command_name}' 不在允许列表中。允许的命令: {', '.join(sorted(self.ALLOWED_COMMANDS))}",
                [],
                None,
            )

        cwd, workdir_error = self._resolve_workdir(workdir)
        if cwd is None:
            return False, workdir_error, [], None

        if command_name in {"pwd", "whoami", "date"} and len(args) != 1:
            return False, f"{command_name} 不接受自动工具参数", [], None
        if command_name == "which" and any(
            not token.replace("-", "").replace("_", "").replace(".", "").isalnum()
            for token in args[1:]
        ):
            return False, "which 仅接受简单命令名", [], None

        if command_name == "grep":
            grep_operands = self._grep_path_operands(args)
            if grep_operands is None:
                return False, "grep 参数不在只读安全选项列表中", [], None
            operands = grep_operands
        else:
            operands = self._path_operands(command_name, args) if command_name in self.PATH_COMMANDS else []
        if command_name == "uniq" and len(operands) > 1:
            return False, "uniq 输出文件参数已禁用", [], None
        if any(not self._validate_path(token, cwd) for token in operands):
            return False, "文件参数超出项目范围", [], None

        return True, "", args, cwd

    def execute(self, command: str, workdir: str | None = None, timeout: int | None = None) -> dict:
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
            cmd_timeout = timeout or self.timeout
            allowed, error, args, cwd = self._validate(command, workdir)
            if not allowed or cwd is None:
                return {
                    "success": False,
                    "blocked": True,
                    "error": error,
                    "command": command,
                }

            # 执行命令 (shell=False，安全模式)
            self.current_process = subprocess.Popen(
                args,
                shell=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=str(cwd),
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
                stdout_str = f"{stdout_str[:max_output]}\n... (输出已截断，共 {len(stdout)} 字节)"
            if len(stderr_str) > max_output:
                stderr_str = f"{stderr_str[:max_output]}\n... (错误输出已截断)"

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
    env = {k: v for k, v in os.environ.items() if k in _SAFE_ENV_KEYS and k != "PATH"}
    # 固定命令搜索路径，并禁止 Git 加载系统/用户配置或外部分页器。
    env.update({
        "PATH": os.defpath,
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_PAGER": "cat",
        "PAGER": "cat",
    })
    return env
