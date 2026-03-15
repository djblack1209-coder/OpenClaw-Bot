"""
ClawBot - 代码执行工具
安全沙箱执行 Python/Shell 代码
"""
import subprocess
import tempfile
import os
from typing import Dict, Any
from pathlib import Path
import logging

logger = logging.getLogger(__name__)


class CodeTool:
    """代码执行沙箱"""
    
    def __init__(self, timeout: int = 30):
        self.timeout = timeout
        self.temp_dir = Path(tempfile.gettempdir()) / "clawbot_code"
        self.temp_dir.mkdir(exist_ok=True)
    
    def execute_python(self, code: str) -> Dict[str, Any]:
        """执行 Python 代码"""
        try:
            # 写入临时文件
            filepath = self.temp_dir / "script.py"
            with open(filepath, 'w') as f:
                f.write(code)
            
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
            
        except subprocess.TimeoutExpired:
            return {"success": False, "error": f"执行超时 ({self.timeout}秒)"}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def execute_node(self, code: str) -> Dict[str, Any]:
        """执行 Node.js 代码"""
        try:
            filepath = self.temp_dir / "script.js"
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
            
        except subprocess.TimeoutExpired:
            return {"success": False, "error": f"执行超时 ({self.timeout}秒)"}
        except FileNotFoundError:
            return {"success": False, "error": "Node.js 未安装"}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def execute_shell(self, code: str) -> Dict[str, Any]:
        """执行 Shell 脚本"""
        try:
            filepath = self.temp_dir / "script.sh"
            with open(filepath, 'w') as f:
                f.write(code)
            
            os.chmod(filepath, 0o755)
            
            result = subprocess.run(
                ["bash", str(filepath)],
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
