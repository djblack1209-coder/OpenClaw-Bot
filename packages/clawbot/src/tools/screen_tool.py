"""
ClawBot - 屏幕截图工具
"""
import subprocess
import tempfile
import base64
import os
from pathlib import Path
from datetime import datetime
from src.utils import now_et

class ScreenTool:
    """屏幕截图和GUI操作"""
    
    def __init__(self, quality: int = 80):
        self.quality = quality
        self.screenshot_dir = Path(tempfile.gettempdir()) / "clawbot_screenshots"
        self.screenshot_dir.mkdir(exist_ok=True)
    
    def capture(self, region: str = "") -> dict:
        """
        截取屏幕
        
        Args:
            region: 截图区域 (可选，格式: "x,y,width,height")
            
        Returns:
            dict: {success, path, base64, error}
        """
        try:
            timestamp = now_et().strftime("%Y%m%d_%H%M%S")
            filename = f"screen_{timestamp}.png"
            filepath = self.screenshot_dir / filename
            
            # macOS 使用 screencapture
            if os.uname().sysname == "Darwin":
                cmd = ["screencapture", "-x"]  # -x 静默模式
                if region:
                    # 格式: x,y,width,height
                    parts = region.split(",")
                    if len(parts) == 4:
                        x, y, w, h = parts
                        cmd.extend(["-R", f"{x},{y},{w},{h}"])
                cmd.append(str(filepath))
            else:
                # Linux 使用 scrot 或 import
                cmd = ["scrot", str(filepath)]
            
            subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            
            if not filepath.exists():
                return {
                    "success": False,
                    "error": "截图失败，请检查屏幕录制权限"
                }
            
            # 读取并转换为 base64
            with open(filepath, "rb") as f:
                img_data = f.read()
            
            img_base64 = base64.b64encode(img_data).decode('utf-8')
            
            return {
                "success": True,
                "path": str(filepath),
                "base64": img_base64,
                "size": len(img_data)
            }
            
        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "error": "截图超时"
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }
    
    def get_window_list(self) -> dict:
        """获取当前窗口列表"""
        try:
            if os.uname().sysname == "Darwin":
                # macOS 使用 AppleScript
                script = '''
                tell application "System Events"
                    set windowList to {}
                    repeat with proc in (every process whose visible is true)
                        set procName to name of proc
                        repeat with win in (every window of proc)
                            set winName to name of win
                            set end of windowList to procName & ": " & winName
                        end repeat
                    end repeat
                    return windowList
                end tell
                '''
                result = subprocess.run(
                    ["osascript", "-e", script],
                    capture_output=True,
                    text=True,
                    timeout=10
                )
                
                windows = result.stdout.strip().split(", ")
                return {
                    "success": True,
                    "windows": [w for w in windows if w]
                }
            else:
                return {
                    "success": False,
                    "error": "仅支持 macOS"
                }
                
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }
    
    def open_app(self, app_name: str) -> dict:
        """打开应用程序"""
        try:
            if os.uname().sysname == "Darwin":
                result = subprocess.run(
                    ["open", "-a", app_name],
                    capture_output=True,
                    text=True,
                    timeout=10
                )
                
                if result.returncode == 0:
                    return {
                        "success": True,
                        "message": f"已打开: {app_name}"
                    }
                else:
                    return {
                        "success": False,
                        "error": result.stderr or f"无法打开: {app_name}"
                    }
            else:
                return {
                    "success": False,
                    "error": "仅支持 macOS"
                }
                
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }
    
    def cleanup_old_screenshots(self, max_age_hours: int = 24) -> dict:
        """清理旧截图"""
        try:
            import time
            now = time.time()
            max_age_seconds = max_age_hours * 3600
            
            count = 0
            for f in self.screenshot_dir.glob("screen_*.png"):
                if now - f.stat().st_mtime > max_age_seconds:
                    f.unlink()
                    count += 1
            
            return {"cleaned": count}
        except Exception:
            return {"cleaned": 0}
