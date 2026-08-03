"""
ClawBot - 代码执行工具
Python 代码通过 RestrictedPython 编译后在受限子进程中执行。
Node.js 与 Shell 执行默认禁用。
"""
import logging
import os
import signal
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# 代码最大长度限制
MAX_CODE_LENGTH = 10000

# ── 子进程安全环境变量白名单 ──
# 只传递运行时必需的环境变量，阻止泄漏 API Key、Token 等敏感信息
_SAFE_ENV_KEYS = frozenset({
    "PATH", "HOME", "USER", "LANG", "LC_ALL", "LC_CTYPE",
    "TERM", "TMPDIR", "TZ",
})

def _make_safe_env() -> dict:
    """构建安全的子进程环境变量 (只保留白名单内的 key)"""
    return {k: v for k, v in os.environ.items() if k in _SAFE_ENV_KEYS}


def _sandbox_preexec():
    """子进程预执行函数 — 设置 OS 级资源限制 (仅 Unix)"""
    import resource

    def _set_soft_limit(limit_name: int, value: int) -> None:
        """设置平台支持的软限制；不支持的单项不能阻断沙箱启动。"""
        try:
            _soft, hard = resource.getrlimit(limit_name)
            target = min(value, hard) if hard != resource.RLIM_INFINITY else value
            resource.setrlimit(limit_name, (target, hard))
        except (OSError, ValueError):
            return

    # 新进程组 — 超时时可杀掉整个进程树
    os.setsid()
    # CPU 时间上限 30 秒
    _set_soft_limit(resource.RLIMIT_CPU, 30)
    # 虚拟内存上限 256MB
    _set_soft_limit(resource.RLIMIT_AS, 256 * 1024 * 1024)
    # 禁止创建子进程 (fork bomb 防护)
    _set_soft_limit(resource.RLIMIT_NPROC, 0)
    # 文件写入大小上限 1MB
    _set_soft_limit(resource.RLIMIT_FSIZE, 1024 * 1024)
    # 禁止 core dump
    _set_soft_limit(resource.RLIMIT_CORE, 0)


def _try_compile_restricted(code: str) -> None:
    """
    使用 RestrictedPython 在 AST 层面验证代码安全性 (第一道防线)
    通过则返回；实际执行仍在子进程中重新编译并运行受限字节码。
    不通过则抛出异常
    """
    try:
        from RestrictedPython import compile_restricted
        byte_code = compile_restricted(code, "<sandbox>", "exec")
        if byte_code is None:
            raise SyntaxError("代码包含沙箱不允许的操作 (如访问双下划线属性)")
        return None
    except ImportError:
        # 安全沙箱缺失时禁止执行，不再静默降级
        raise RuntimeError("安全沙箱组件 RestrictedPython 未安装，代码执行已禁用") from None


# ── Python 子进程沙箱前导代码 ──
# 子进程必须执行 RestrictedPython 产出的字节码，禁止执行原始源码字节码。
_PYTHON_SANDBOX_PREFIX = '''\
# ── 子进程沙箱 (RestrictedPython + OS 资源限制) ──
import builtins as _builtins
from RestrictedPython import compile_restricted as _compile_restricted
from RestrictedPython.Eval import default_guarded_getitem as _guarded_getitem
from RestrictedPython.Eval import default_guarded_getiter as _guarded_getiter
from RestrictedPython.Guards import full_write_guard as _full_write_guard
from RestrictedPython.Guards import guarded_iter_unpack_sequence as _guarded_iter_unpack
from RestrictedPython.Guards import guarded_unpack_sequence as _guarded_unpack
from RestrictedPython.Guards import safe_builtins as _restricted_builtins
from RestrictedPython.Guards import safer_getattr as _safer_getattr
from RestrictedPython.PrintCollector import PrintCollector as _PrintCollector

class _LimitedPrintCollector(_PrintCollector):
    """将收集到的标准输出限制为 5000 个字符。"""

    def __init__(self, _getattr_=None):
        super().__init__(_getattr_)
        self._total = 0

    def write(self, text):
        remaining = max(0, 5000 - self._total)
        if remaining:
            chunk = str(text)[:remaining]
            self.txt.append(chunk)
            self._total += len(chunk)

# 不向用户代码提供 import/open/exec/eval，也移除可扩大反射面的内置函数。
_SAFE_BUILTINS = dict(_restricted_builtins)
for _name in ("setattr", "delattr", "id", "hash", "__build_class__", "_getattr_"):
    _SAFE_BUILTINS.pop(_name, None)
_SAFE_BUILTINS.update({
    "all": _builtins.all,
    "any": _builtins.any,
    "dict": _builtins.dict,
    "enumerate": _builtins.enumerate,
    "filter": _builtins.filter,
    "frozenset": _builtins.frozenset,
    "iter": _builtins.iter,
    "list": _builtins.list,
    "map": _builtins.map,
    "max": _builtins.max,
    "min": _builtins.min,
    "next": _builtins.next,
    "reversed": _builtins.reversed,
    "set": _builtins.set,
    "sum": _builtins.sum,
})

_USER_GLOBALS = {
    "__builtins__": _SAFE_BUILTINS,
    "__name__": "__sandbox__",
    "_print_": _LimitedPrintCollector,
    "_getattr_": _safer_getattr,
    "_getitem_": _guarded_getitem,
    "_getiter_": _guarded_getiter,
    "_iter_unpack_sequence_": _guarded_iter_unpack,
    "_unpack_sequence_": _guarded_unpack,
    "_write_": _full_write_guard,
}
'''


class CodeTool:
    """
    Python 代码执行沙箱；Node.js 与 Shell 默认禁用。

    安全架构:
    Layer 1: RestrictedPython AST 编译检查 (拦截已知危险模式)
    Layer 2: 子进程执行 RestrictedPython 字节码，不提供 import/open
    Layer 3: resource.setrlimit (OS 级资源限制: CPU/内存/进程数)
    Layer 4: 进程组隔离 + 环境变量清洗 (阻止信息泄漏)
    """

    def __init__(self, timeout: int = 30):
        self.timeout = timeout
        self.temp_dir = Path(tempfile.gettempdir()) / "clawbot_code"
        self.temp_dir.mkdir(exist_ok=True)
        # 检查 RestrictedPython 是否可用
        self._has_restricted_python = False
        try:
            from RestrictedPython import compile_restricted  # noqa: F401
            self._has_restricted_python = True
        except ImportError:
            logger.warning("[CodeTool] RestrictedPython 未安装，Python 代码执行已禁用")

    def execute_python(self, code: str) -> dict[str, Any]:
        """
        执行 Python 代码 (全部走子进程, 不在宿主进程内 exec)

        流程: AST 预检查 → 写入临时文件 → 子进程重新受限编译并执行
        """
        # 代码大小限制
        if len(code) > MAX_CODE_LENGTH:
            return {
                "success": False,
                "error": f"代码长度超限 ({len(code)} > {MAX_CODE_LENGTH} 字符)"
            }

        # Layer 1: RestrictedPython AST 预检查 (在宿主进程中只编译不执行)
        if not self._has_restricted_python:
            # 安全沙箱组件缺失，拒绝执行任何代码
            return {
                "success": False,
                "error": "安全沙箱组件 RestrictedPython 未安装，代码执行已禁用",
                "stdout": "",
                "stderr": "",
            }
        try:
            _try_compile_restricted(code)
        except SyntaxError as e:
            return {"success": False, "error": f"代码安全检查未通过: {e}"}
        except RuntimeError as e:
            # RestrictedPython 运行时缺失，拒绝执行
            return {"success": False, "error": str(e), "stdout": "", "stderr": ""}
        except Exception as e:
            logger.warning("[CodeTool] AST 安全检查异常，拒绝执行: %s", type(e).__name__)
            return {
                "success": False,
                "error": f"代码安全检查异常: {type(e).__name__}",
                "stdout": "",
                "stderr": "",
            }

        # Layer 2-4: 子进程执行 (OS 级隔离)
        return self._execute_in_subprocess(code, "python")

    def execute_node(self, code: str) -> dict[str, Any]:
        """Node.js 缺少可靠进程级沙箱，默认拒绝执行。"""
        logger.warning("[CodeTool] 拒绝执行 Node.js 代码 (%d 字符)", len(code))
        return {
            "success": False,
            "error": "Node.js 代码执行已禁用；当前环境没有可靠的隔离沙箱。",
        }

    def execute_shell(self, code: str) -> dict[str, Any]:
        """Shell 脚本执行已禁用"""
        logger.warning("[CodeTool] 拒绝执行 Shell 脚本 (%d 字符)", len(code))
        return {
            "success": False,
            "error": "Shell 脚本执行已禁用。请使用 /bash 命令执行具体 shell 命令。"
        }

    def _execute_in_subprocess(self, code: str, lang: str) -> dict[str, Any]:
        """
        在受限子进程中执行代码 (统一入口)

        安全措施:
        - resource.setrlimit: CPU 30s / 内存 256MB / 禁止 fork / 文件 1MB
        - 环境变量清洗: 只保留 PATH/HOME/LANG 等必需变量
        - 进程组隔离: 超时可杀掉整个进程树
        """
        if lang != "python":
            return {"success": False, "error": f"不支持的代码语言: {lang}"}

        ext = "py"
        # 使用唯一文件名避免并发写入的竞态条件
        import uuid as _uuid
        unique_id = _uuid.uuid4().hex[:12]
        filepath = self.temp_dir / f"script_{unique_id}.{ext}"

        try:
            # 写入带沙箱前导代码的临时文件
            with open(filepath, "w") as f:
                if lang == "python":
                    f.write(_PYTHON_SANDBOX_PREFIX)
                    f.write(f"\n_USER_CODE = {code!r}\n")
                    f.write(
                        "_BYTE_CODE = _compile_restricted(_USER_CODE, '<user-code>', 'exec')\n"
                        "if _BYTE_CODE is None:\n"
                        "    raise RuntimeError('代码安全检查未生成可执行字节码')\n"
                        "exec(_BYTE_CODE, _USER_GLOBALS)\n"
                        "_OUTPUT = _USER_GLOBALS.get('_print')\n"
                        "if _OUTPUT is not None:\n"
                        "    _builtins.print(_OUTPUT(), end='')\n"
                    )

            # 构建子进程命令
            cmd = [sys.executable, "-u", str(filepath)]

            # 选择 preexec_fn: Unix 使用 _sandbox_preexec 加资源限制
            preexec = _sandbox_preexec if os.name != "nt" else None

            # 执行 (安全环境变量 + 资源限制 + 进程组隔离)
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=str(self.temp_dir),
                env=_make_safe_env(),
                preexec_fn=preexec,
            )

            try:
                stdout, stderr = proc.communicate(timeout=self.timeout)
            except subprocess.TimeoutExpired:
                # 超时，杀掉整个进程组
                if os.name != "nt":
                    try:
                        os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                    except ProcessLookupError as e:
                        logger.debug("进程已退出: %s", e)
                else:
                    proc.kill()
                proc.wait()
                return {"success": False, "error": f"执行超时 ({self.timeout}秒)"}

            stdout_str = stdout.decode("utf-8", errors="replace")[:5000]
            stderr_str = stderr.decode("utf-8", errors="replace")[:2000]

            return {
                "success": proc.returncode == 0,
                "stdout": stdout_str,
                "stderr": stderr_str,
                "returncode": proc.returncode,
            }

        except FileNotFoundError:
            return {"success": False, "error": "Python 未安装"}
        except Exception as e:
            logger.debug("[CodeTool] 执行异常: %s", e)
            return {"success": False, "error": f"执行错误: {type(e).__name__}"}
        finally:
            filepath.unlink(missing_ok=True)
