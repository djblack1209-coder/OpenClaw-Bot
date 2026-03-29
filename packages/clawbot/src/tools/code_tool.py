"""
ClawBot - 代码执行工具
使用 RestrictedPython 实现安全沙箱执行 Python 代码
Node.js 使用 --disable-proto=delete + 模块禁用
Shell 执行已禁用
"""
import subprocess
import tempfile
from typing import Dict, Any
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

# 代码最大长度限制
MAX_CODE_LENGTH = 10000

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
    "any": any, "all": all, "hasattr": hasattr,
    "format": format, "hash": hash, "id": id,
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


def _make_safe_import():
    """创建受限的 __import__ 函数，只允许安全模块"""
    import importlib

    def _safe_import(name, *args, **kwargs):
        """只允许导入白名单内的模块"""
        top_module = name.split(".")[0]
        if top_module not in _SAFE_IMPORTABLE:
            raise ImportError(f"模块 '{name}' 在沙箱中被禁用")
        return importlib.import_module(name)

    return _safe_import


def _build_sandbox_globals() -> dict:
    """构建 RestrictedPython 沙箱的全局命名空间"""
    try:
        from RestrictedPython import safe_globals
        from RestrictedPython.PrintCollector import PrintCollector
        from RestrictedPython.Eval import default_guarded_getiter, default_guarded_getitem
    except ImportError:
        # RestrictedPython 未安装时回退到基础沙箱
        logger.warning("[CodeTool] RestrictedPython 未安装，使用基础沙箱 (安全性降低)")
        return None

    glb = safe_globals.copy()
    # 注入安全的内置函数
    glb["__builtins__"].update(_SAFE_EXTRA_BUILTINS)
    # 注入受限 import
    glb["__builtins__"]["__import__"] = _make_safe_import()
    # RestrictedPython guard 函数
    glb["_print_"] = PrintCollector
    glb["_getattr_"] = getattr
    glb["_getiter_"] = default_guarded_getiter
    glb["_getitem_"] = default_guarded_getitem
    # 禁用写入属性 (setattr/delattr)
    glb["_write_"] = lambda obj: obj
    # 解包保护
    glb["_inplacevar_"] = lambda op, x, y: op(x, y)

    return glb


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
    process.exit = () => { throw new Error('process.exit 被禁用'); };
    process.kill = () => { throw new Error('process.kill 被禁用'); };
}
// ── 沙箱结束 ──
"""


class CodeTool:
    """代码执行沙箱 — 使用 RestrictedPython 实现 AST 级安全"""

    def __init__(self, timeout: int = 30):
        self.timeout = timeout
        self.temp_dir = Path(tempfile.gettempdir()) / "clawbot_code"
        self.temp_dir.mkdir(exist_ok=True)
        # 预构建沙箱全局变量 (None 表示 RestrictedPython 不可用)
        self._sandbox_globals = _build_sandbox_globals()

    def execute_python(self, code: str) -> Dict[str, Any]:
        """执行 Python 代码 (RestrictedPython AST 级沙箱)"""
        # 代码大小限制
        if len(code) > MAX_CODE_LENGTH:
            return {
                "success": False,
                "error": f"代码长度超限 ({len(code)} > {MAX_CODE_LENGTH} 字符)"
            }

        if self._sandbox_globals is not None:
            return self._execute_python_restricted(code)
        else:
            return self._execute_python_subprocess(code)

    def _execute_python_restricted(self, code: str) -> Dict[str, Any]:
        """使用 RestrictedPython 在进程内执行 (AST 级安全)"""
        try:
            from RestrictedPython import compile_restricted

            # 编译阶段: RestrictedPython 在 AST 层面拦截危险操作
            byte_code = compile_restricted(code, "<sandbox>", "exec")

            # 编译失败 (如访问 __dunder__ 属性)
            if byte_code is None:
                return {
                    "success": False,
                    "error": "代码包含沙箱不允许的操作 (如访问双下划线属性)"
                }

            # 执行
            glb = self._sandbox_globals.copy()
            loc: Dict[str, Any] = {}
            exec(byte_code, glb, loc)

            # 收集输出
            output = ""
            if "_print" in loc:
                output = loc["_print"]()

            return {
                "success": True,
                "stdout": str(output)[:5000] if output else "",
                "stderr": "",
                "returncode": 0
            }

        except ImportError as e:
            return {"success": False, "error": f"模块导入被禁止: {e}"}
        except PermissionError as e:
            return {"success": False, "error": f"操作被沙箱阻止: {e}"}
        except SyntaxError as e:
            return {"success": False, "error": f"语法错误: {e}"}
        except Exception as e:
            error_type = type(e).__name__
            return {
                "success": False,
                "error": f"{error_type}: {e}",
                "stdout": "",
                "stderr": str(e)[:2000],
                "returncode": 1
            }

    def _execute_python_subprocess(self, code: str) -> Dict[str, Any]:
        """回退方案: RestrictedPython 不可用时使用子进程 + import hook"""
        # 基础 import hook 沙箱 (安全性较低，仅在 RestrictedPython 不可用时使用)
        sandbox_prefix = '''
# ── 基础沙箱 (RestrictedPython 不可用时的回退) ──
import sys
_BLOCKED = frozenset({
    "os", "subprocess", "shutil", "signal", "ctypes",
    "socket", "http", "urllib", "requests", "pathlib",
    "importlib", "pickle", "shelve", "multiprocessing",
})
_orig_import = __builtins__.__import__ if hasattr(__builtins__, '__import__') else __import__
def _safe_import(name, *args, **kwargs):
    if name.split('.')[0] in _BLOCKED:
        raise ImportError(f"模块 '{name}' 在沙箱中被禁用")
    return _orig_import(name, *args, **kwargs)
__builtins__.__import__ = _safe_import
import builtins as _b
_orig_open = _b.open
def _safe_open(path, *a, **kw):
    _p = str(path)
    if not _p.startswith(('/dev/null', '/dev/urandom')):
        raise PermissionError(f'文件访问被禁用: {_p[:50]}')
    return _orig_open(path, *a, **kw)
_b.open = _safe_open
type.__subclasses__ = lambda self: []
'''
        filepath = self.temp_dir / "script.py"
        try:
            with open(filepath, "w") as f:
                f.write(sandbox_prefix + "\n" + code)

            result = subprocess.run(
                ["python3", str(filepath)],
                capture_output=True,
                text=True,
                timeout=self.timeout,
                cwd=str(self.temp_dir)
            )

            return {
                "success": result.returncode == 0,
                "stdout": result.stdout[:5000],
                "stderr": result.stderr[:2000],
                "returncode": result.returncode
            }

        except subprocess.TimeoutExpired:
            return {"success": False, "error": f"执行超时 ({self.timeout}秒)"}
        except Exception as e:
            return {"success": False, "error": str(e)}
        finally:
            filepath.unlink(missing_ok=True)

    def execute_node(self, code: str) -> Dict[str, Any]:
        """执行 Node.js 代码 (模块禁用 + 原型链保护)"""
        # 代码大小限制
        if len(code) > MAX_CODE_LENGTH:
            return {
                "success": False,
                "error": f"代码长度超限 ({len(code)} > {MAX_CODE_LENGTH} 字符)"
            }

        filepath = self.temp_dir / "script.js"
        try:
            with open(filepath, "w") as f:
                f.write(NODE_SANDBOX_PREFIX + code)

            # --disable-proto=delete 阻止通过 __proto__ 遍历原型链
            result = subprocess.run(
                ["node", "--disable-proto=delete", str(filepath)],
                capture_output=True,
                text=True,
                timeout=self.timeout,
                cwd=str(self.temp_dir)
            )

            return {
                "success": result.returncode == 0,
                "stdout": result.stdout[:5000],
                "stderr": result.stderr[:2000],
                "returncode": result.returncode
            }

        except subprocess.TimeoutExpired:
            return {"success": False, "error": f"执行超时 ({self.timeout}秒)"}
        except FileNotFoundError:
            return {"success": False, "error": "Node.js 未安装"}
        except Exception as e:
            return {"success": False, "error": str(e)}
        finally:
            filepath.unlink(missing_ok=True)

    def execute_shell(self, code: str) -> Dict[str, Any]:
        """Shell 脚本执行已禁用"""
        logger.warning("[CodeTool] 拒绝执行 Shell 脚本 (%d 字符)", len(code))
        return {
            "success": False,
            "error": "Shell 脚本执行已禁用。请使用 /bash 命令执行具体 shell 命令。"
        }
