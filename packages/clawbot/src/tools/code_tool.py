"""
ClawBot - 代码执行工具
安全沙箱执行 Python/Node.js 代码 (Shell 已禁用)
"""
import subprocess
import tempfile
from typing import Dict, Any
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

# Python 沙箱前导代码: 禁用危险模块的 import
PYTHON_SANDBOX_PREFIX = '''
# ── 沙箱安全限制 ──
import sys
_BLOCKED_MODULES = frozenset({
    "os", "subprocess", "shutil", "signal", "ctypes",
    "socket", "http", "urllib", "requests", "pathlib",
    "importlib", "pickle", "shelve", "multiprocessing",
})
_original_import = __builtins__.__import__ if hasattr(__builtins__, '__import__') else __import__
def _safe_import(name, *args, **kwargs):
    if name.split('.')[0] in _BLOCKED_MODULES:
        raise ImportError(f"模块 '{name}' 在沙箱中被禁用")
    return _original_import(name, *args, **kwargs)
__builtins__.__import__ = _safe_import
# 额外防护: 禁用 open() 文件访问和 subclasses 遍历
import builtins as _builtins
_original_open = _builtins.open
def _safe_open(path, *args, **kwargs):
    _allowed = ('/dev/null', '/dev/urandom')
    _p = str(path)
    if not any(_p.startswith(a) for a in _allowed):
        raise PermissionError(f'文件访问在沙箱中被禁用: {_p[:50]}')
    return _original_open(path, *args, **kwargs)
_builtins.open = _safe_open
# 禁用 subclasses 遍历
type.__subclasses__ = lambda self: []
'''

# 代码最大长度限制
MAX_CODE_LENGTH = 10000


class CodeTool:
    """代码执行沙箱"""
    
    def __init__(self, timeout: int = 30):
        self.timeout = timeout
        self.temp_dir = Path(tempfile.gettempdir()) / "clawbot_code"
        self.temp_dir.mkdir(exist_ok=True)
    
    def execute_python(self, code: str) -> Dict[str, Any]:
        """执行 Python 代码 (带沙箱保护)"""
        # 代码大小限制
        if len(code) > MAX_CODE_LENGTH:
            return {
                "success": False,
                "error": f"代码长度超限 ({len(code)} > {MAX_CODE_LENGTH} 字符)"
            }
        
        filepath = self.temp_dir / "script.py"
        try:
            # 注入沙箱前导代码
            sandboxed_code = PYTHON_SANDBOX_PREFIX + "\n" + code
            
            with open(filepath, 'w') as f:
                f.write(sandboxed_code)
            
            # 执行
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
            
        except subprocess.TimeoutExpired as e:  # noqa: F841
            return {"success": False, "error": f"执行超时 ({self.timeout}秒)"}
        except Exception as e:
            return {"success": False, "error": str(e)}
        finally:
            # 清理临时文件
            filepath.unlink(missing_ok=True)
    
    def execute_node(self, code: str) -> Dict[str, Any]:
        """执行 Node.js 代码"""
        # 代码大小限制
        if len(code) > MAX_CODE_LENGTH:
            return {
                "success": False,
                "error": f"代码长度超限 ({len(code)} > {MAX_CODE_LENGTH} 字符)"
            }
        
        filepath = self.temp_dir / "script.js"
        try:
            # Node.js 沙箱: 禁用危险模块
            node_sandbox = """
// 沙箱: 禁用危险 Node.js 模块
const _origRequire = require;
require = function(mod) {
    const blocked = ['child_process','fs','net','dgram','dns','tls','cluster','worker_threads','v8','vm','os','process'];
    if (blocked.includes(mod)) throw new Error('模块 ' + mod + ' 在沙箱中被禁用');
    return _origRequire(mod);
};
delete process.env;
process.exit = () => { throw new Error('process.exit 被禁用'); };
// 沙箱结束
"""
            code = node_sandbox + code
            with open(filepath, 'w') as f:
                f.write(code)
            
            result = subprocess.run(
                ["node", str(filepath)],
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
            
        except subprocess.TimeoutExpired as e:  # noqa: F841
            return {"success": False, "error": f"执行超时 ({self.timeout}秒)"}
        except FileNotFoundError as e:  # noqa: F841
            return {"success": False, "error": "Node.js 未安装"}
        except Exception as e:
            return {"success": False, "error": str(e)}
        finally:
            # 清理临时文件
            filepath.unlink(missing_ok=True)
    
    def execute_shell(self, code: str) -> Dict[str, Any]:
        """Shell 脚本执行已禁用"""
        logger.warning(f"[CodeTool] 拒绝执行 Shell 脚本 ({len(code)} 字符)")
        return {
            "success": False,
            "error": "Shell 脚本执行已禁用。请使用 /bash 命令执行具体 shell 命令。"
        }
