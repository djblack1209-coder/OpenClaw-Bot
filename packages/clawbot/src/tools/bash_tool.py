"""
ClawBot - Bash命令执行工具
"""
import subprocess
import os
import signal
from typing import Optional
from pathlib import Path

class BashTool:
    """执行Bash命令"""
    
    # 危险命令列表
    DANGEROUS_PATTERNS = [
        "rm -rf /",
        "rm -rf ~",
        "rm -rf /*",
        "mkfs",
        "dd if=",
        "> /dev/sd",
        "chmod -R 777 /",
        ":(){ :|:& };:",  # fork bomb
    ]
    
    def __init__(self, working_dir: Optional[str] = None, timeout: int = 120):
        self.working_dir = working_dir or str(Path.home())
        self.timeout = timeout
        self.current_process: Optional[subprocess.Popen] = None
    
    def is_dangerous(self, command: str) -> bool:
        """检查命令是否危险"""
        cmd_lower = command.lower().strip()
        for pattern in self.DANGEROUS_PATTERNS:
            if pattern.lower() in cmd_lower:
                return True
        return False
    
    def execute(self, command: str, workdir: Optional[str] = None, timeout: Optional[int] = None) -> dict:
        """
        执行Bash命令
        
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
            
            # 检查危险命令
            if self.is_dangerous(command):
                return {
                    "success": False,
                    "dangerous": True,
                    "error": "检测到危险命令，需要确认后执行",
                    "command": command
                }
            
            # 执行命令
            self.current_process = subprocess.Popen(
                command,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=cwd,
                env=os.environ.copy(),
                preexec_fn=os.setsid if os.name != 'nt' else None
            )
            
            try:
                stdout, stderr = self.current_process.communicate(timeout=cmd_timeout)
                returncode = self.current_process.returncode
            except subprocess.TimeoutExpired:
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
    
    def execute_dangerous(self, command: str, workdir: Optional[str] = None) -> dict:
        """强制执行危险命令 (需要用户确认后调用)"""
        try:
            cwd = workdir or self.working_dir
            
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                cwd=cwd,
                timeout=self.timeout
            )
            
            return {
                "success": result.returncode == 0,
                "stdout": result.stdout.decode('utf-8', errors='replace'),
                "stderr": result.stderr.decode('utf-8', errors='replace'),
                "returncode": result.returncode,
                "command": command,
                "forced": True
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "command": command
            }
    
    def cancel(self) -> dict:
        """取消当前执行的命令"""
        if self.current_process:
            try:
                if os.name != 'nt':
                    os.killpg(os.getpgid(self.current_process.pid), signal.SIGTERM)
                else:
                    self.current_process.terminate()
                return {"success": True, "message": "命令已取消"}
            except Exception:
                return {"success": False, "error": "取消失败"}
        return {"success": False, "error": "没有正在执行的命令"}
