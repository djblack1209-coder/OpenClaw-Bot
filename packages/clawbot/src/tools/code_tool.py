"""
ClawBot - 代码执行工具
所有代码执行均通过子进程实现 (OS级隔离)
Python: RestrictedPython AST编译(第一道防线) → 子进程执行(OS隔离)
Node.js: 模块禁用 + --disable-proto=delete + 子进程执行
Shell: 已禁用
"""
import os
import signal
import subprocess
import tempfile
from typing import Dict, Any
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

# 代码最大长度限制
MAX_CODE_LENGTH = 10000

# ── 子进程安全环境变量白名单 ──
# 只传递运行时必需的环境变量，阻止泄漏 API Key、Token 等敏感信息
_SAFE_ENV_KEYS = frozenset({
    "PATH", "HOME", "USER", "LANG", "LC_ALL", "LC_CTYPE",
    "TERM", "TMPDIR", "TZ", "PYTHONPATH", "NODE_PATH",
})

# ── RestrictedPython 沙箱配置 ──
# 允许用户代码使用的安全内置函数
_SAFE_EXTRA_BUILTINS = {
    "sum": sum, "min": min, "max": max, "abs": abs,
    "round": round, "len": len, "range": range, "enumerate": enumerate,
    "zip": zip, "map": map, "filter": filter, "sorted": sorted,
    "reversed": reversed, "list": list, "dict": dict, "set": set,
    "tuple": tuple, "str": str, "int": int, "float": float,
    "bool": bool, "isinstance": isinstance, "issubclass": issubclass,
    "repr": repr, "chr": chr, "ord": ord,
    "hex": hex, "oct": oct, "bin": bin, "pow": pow, "divmod": divmod,
    "any": any, "all": all,
    "format": format,
}

# 允许在沙箱中 import 的安全模块
_SAFE_IMPORTABLE = frozenset({
    "math", "random", "statistics", "collections",
    "itertools", "functools", "operator", "string",
    "re", "json", "datetime", "time", "decimal",
    "fractions", "textwrap", "unicodedata", "copy",
    "pprint", "dataclasses", "enum", "typing",
    "base64", "hashlib", "hmac", "csv",
})


def _make_safe_env() -> dict:
    """构建安全的子进程环境变量 (只保留白名单内的 key)"""
    return {k: v for k, v in os.environ.items() if k in _SAFE_ENV_KEYS}


def _sandbox_preexec():
    """子进程预执行函数 — 设置 OS 级资源限制 (仅 Unix)"""
    import resource
    # 新进程组 — 超时时可杀掉整个进程树
    os.setsid()
    # CPU 时间上限 30 秒 (硬限制)
    resource.setrlimit(resource.RLIMIT_CPU, (30, 30))
    # 虚拟内存上限 256MB
    resource.setrlimit(resource.RLIMIT_AS, (256 * 1024 * 1024, 256 * 1024 * 1024))
    # 禁止创建子进程 (fork bomb 防护)
    resource.setrlimit(resource.RLIMIT_NPROC, (0, 0))
    # 文件写入大小上限 1MB
    resource.setrlimit(resource.RLIMIT_FSIZE, (1024 * 1024, 1024 * 1024))
    # 禁止 core dump
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))


def _try_compile_restricted(code: str) -> str:
    """
    使用 RestrictedPython 在 AST 层面验证代码安全性 (第一道防线)
    通过则返回原始代码 (实际执行在子进程中)
    不通过则抛出异常
    """
    try:
        from RestrictedPython import compile_restricted
        byte_code = compile_restricted(code, "<sandbox>", "exec")
        if byte_code is None:
            raise SyntaxError("代码包含沙箱不允许的操作 (如访问双下划线属性)")
        # AST 编译通过，返回原始代码供子进程执行
        return code
    except ImportError:
        # RestrictedPython 未安装，跳过 AST 检查 (子进程 import hook 仍会拦截)
        logger.warning("[CodeTool] RestrictedPython 未安装，跳过 AST 预检查")
        return code


# ── Python 子进程沙箱前导代码 ──
# 在子进程中注入 import hook + 文件访问限制 + 危险属性封锁
_PYTHON_SANDBOX_PREFIX = '''\
# ── 子进程沙箱 (OS级隔离 + import hook) ──
import sys as _sys

# 1. 阻止导入危险模块
_BLOCKED_MODULES = frozenset({
    "os", "subprocess", "shutil", "signal", "ctypes", "_ctypes",
    "socket", "http", "urllib", "requests", "pathlib",
    "importlib", "pickle", "shelve", "multiprocessing",
    "threading", "concurrent", "asyncio",
    "gc", "inspect", "dis", "code", "codeop", "compileall",
    "py_compile", "zipimport", "pkgutil", "runpy",
})
_orig_import = __import__
def _safe_import(name, *args, **kwargs):
    top = name.split(".")[0]
    if top in _BLOCKED_MODULES:
        raise ImportError(f"模块 \\'{name}\\' 在沙箱中被禁用")
    return _orig_import(name, *args, **kwargs)
import builtins as _b
_b.__import__ = _safe_import

# 2. 禁止文件访问 (只允许 /dev/null 和 /dev/urandom)
_orig_open = _b.open
def _safe_open(path, *a, **kw):
    _p = str(path)
    if not _p.startswith(("/dev/null", "/dev/urandom")):
        raise PermissionError(f"文件访问被禁用: {_p[:50]}")
    return _orig_open(path, *a, **kw)
_b.open = _safe_open

# 3. 封锁危险的类型内省
type.__subclasses__ = lambda self: []

# 4. 移除可用于逃逸的内置函数
for _fn in ("exec", "eval", "compile", "__build_class__", "globals",
            "locals", "vars", "dir", "getattr", "setattr", "delattr",
            "hasattr", "id", "hash", "breakpoint", "exit", "quit"):
    if hasattr(_b, _fn):
        try:
            delattr(_b, _fn)
        except (AttributeError, TypeError):
            pass

# 5. 限制输出长度
class _LimitedPrint:
    def __init__(self, max_chars=5000):
        self._buf = []
        self._total = 0
        self._max = max_chars
    def __call__(self, *args, **kwargs):
        text = " ".join(str(a) for a in args)
        end = kwargs.get("end", "\\n")
        text += end
        remaining = self._max - self._total
        if remaining > 0:
            self._buf.append(text[:remaining])
            self._total += min(len(text), remaining)
        elif not self._buf or self._buf[-1] != "\\n... (输出已截断)\\n":
            self._buf.append("\\n... (输出已截断)\\n")
_b.print = _LimitedPrint()

del _sys, _b, _orig_import, _orig_open, _BLOCKED_MODULES
# ── 沙箱初始化完成 ──
'''

# Node.js 沙箱前导代码: 禁用危险模块 + 原型链保护
NODE_SANDBOX_PREFIX = """\
// ── 沙箱安全限制 ──
'use strict';
const _origRequire = typeof require !== 'undefined' ? require : null;
if (_origRequire) {
    const _blocked = new Set([
        'child_process','fs','net','dgram','dns','tls','cluster',
        'worker_threads','v8','vm','os','http','https','http2',
        'crypto','zlib','stream','path','readline','repl',
        'inspector','perf_hooks','async_hooks','trace_events',
    ]);
    globalThis.require = function(mod) {
        if (_blocked.has(mod)) throw new Error('模块 ' + mod + ' 在沙箱中被禁用');
        return _origRequire(mod);
    };
}
// 禁用 process 危险方法
if (typeof process !== 'undefined') {
    delete process.env;
    Object.defineProperty(process, 'env', { get: () => ({}) });
    process.exit = () => { throw new Error('process.exit 被禁用'); };
    process.kill = () => { throw new Error('process.kill 被禁用'); };
    // 封锁原生模块加载
    if (process.dlopen) process.dlopen = () => { throw new Error('process.dlopen 被禁用'); };
    if (process.binding) process.binding = () => { throw new Error('process.binding 被禁用'); };
    if (process._linkedBinding) process._linkedBinding = () => { throw new Error('process._linkedBinding 被禁用'); };
}
// ── 沙箱结束 ──
"""


class CodeTool:
    """
    代码执行沙箱 — 全部通过子进程执行 (OS 级隔离)

    安全架构:
    Layer 1: RestrictedPython AST 编译检查 (拦截已知危险模式)
    Layer 2: 子进程 import hook + 文件访问限制 (运行时拦截)
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
            logger.warning("[CodeTool] RestrictedPython 未安装，仅使用子进程沙箱")

    def execute_python(self, code: str) -> Dict[str, Any]:
        """
        执行 Python 代码 (全部走子进程, 不在宿主进程内 exec)

        流程: AST预检查(可选) → 写入临时文件 → 子进程执行(带资源限制)
        """
        # 代码大小限制
        if len(code) > MAX_CODE_LENGTH:
            return {
                "success": False,
                "error": f"代码长度超限 ({len(code)} > {MAX_CODE_LENGTH} 字符)"
            }

        # Layer 1: RestrictedPython AST 预检查 (在宿主进程中只编译不执行)
        if self._has_restricted_python:
            try:
                _try_compile_restricted(code)
            except SyntaxError as e:
                return {"success": False, "error": f"代码安全检查未通过: {e}"}
            except Exception as e:
                # AST 检查失败不阻止执行 (子进程 import hook 仍会拦截)
                logger.debug("[CodeTool] AST 预检查异常 (继续执行): %s", e)

        # Layer 2-4: 子进程执行 (OS 级隔离)
        return self._execute_in_subprocess(code, "python")

    def execute_node(self, code: str) -> Dict[str, Any]:
        """执行 Node.js 代码 (模块禁用 + 原型链保护 + 子进程隔离)"""
        # 代码大小限制
        if len(code) > MAX_CODE_LENGTH:
            return {
                "success": False,
                "error": f"代码长度超限 ({len(code)} > {MAX_CODE_LENGTH} 字符)"
            }

        return self._execute_in_subprocess(code, "node")

    def execute_shell(self, code: str) -> Dict[str, Any]:
        """Shell 脚本执行已禁用"""
        logger.warning("[CodeTool] 拒绝执行 Shell 脚本 (%d 字符)", len(code))
        return {
            "success": False,
            "error": "Shell 脚本执行已禁用。请使用 /bash 命令执行具体 shell 命令。"
        }

    def _execute_in_subprocess(self, code: str, lang: str) -> Dict[str, Any]:
        """
        在受限子进程中执行代码 (统一入口)

        安全措施:
        - resource.setrlimit: CPU 30s / 内存 256MB / 禁止 fork / 文件 1MB
        - 环境变量清洗: 只保留 PATH/HOME/LANG 等必需变量
        - 进程组隔离: 超时可杀掉整个进程树
        """
        ext = "py" if lang == "python" else "js"
        filepath = self.temp_dir / f"script.{ext}"

        try:
            # 写入带沙箱前导代码的临时文件
            with open(filepath, "w") as f:
                if lang == "python":
                    f.write(_PYTHON_SANDBOX_PREFIX + "\n" + code)
                else:
                    f.write(NODE_SANDBOX_PREFIX + code)

            # 构建子进程命令
            if lang == "python":
                cmd = ["python3", "-u", str(filepath)]
            else:
                # --disable-proto=delete 阻止通过 __proto__ 遍历原型链
                cmd = ["node", "--disable-proto=delete", str(filepath)]

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
                    except ProcessLookupError:
                        pass
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
            runtime = "Python" if lang == "python" else "Node.js"
            return {"success": False, "error": f"{runtime} 未安装"}
        except Exception as e:
            logger.debug("[CodeTool] 执行异常: %s", e)
            return {"success": False, "error": f"执行错误: {type(e).__name__}"}
        finally:
            filepath.unlink(missing_ok=True)
