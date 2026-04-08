"""通用登录弹窗工具 — macOS 桌面弹窗 + 浏览器自动打开 + 登录状态检测

当任何服务（闲鱼/X/小红书/微信等）需要用户手动登录时：
1. 弹出 macOS 通知和对话框，确保用户看到
2. 自动打开登录网页到前台
3. 轮询检测登录完成，自动恢复服务

使用示例:
    from src.tools.login_helper import LoginHelper
    helper = LoginHelper("闲鱼")
    helper.alert_and_open("https://login.taobao.com/...")
    ok = await helper.wait_for_condition(lambda: check_cookie(), timeout=600)
"""

import asyncio
import os
import subprocess
import sys
import time
from typing import Callable, Optional

from loguru import logger


class LoginHelper:
    """通用登录弹窗助手 — 适配 macOS 桌面环境"""

    def __init__(self, service_name: str):
        """初始化登录助手。

        Args:
            service_name: 服务名称，用于显示在通知和对话框中，如"闲鱼"、"X (Twitter)"
        """
        self.service_name = service_name
        self._is_macos = sys.platform == "darwin"

    def mac_notify(self, title: str, message: str, sound: str = "Ping") -> bool:
        """发送 macOS 通知中心通知。

        Args:
            title: 通知标题
            message: 通知内容
            sound: 通知声音名称 (Ping/Basso/Blow/Bottle/Frog/Funk/Glass/Hero/Morse/Pop/Purr/Sosumi/Submarine/Tink)

        Returns:
            是否发送成功
        """
        if not self._is_macos:
            logger.info(f"[{self.service_name}] {title}: {message}")
            return False
        try:
            script = (
                f'display notification "{message}" '
                f'with title "OpenClaw — {title}" '
                f'sound name "{sound}"'
            )
            subprocess.run(
                ["osascript", "-e", script],
                capture_output=True, timeout=5,
            )
            return True
        except Exception as e:
            logger.debug(f"macOS 通知发送失败: {e}")
            return False

    def mac_alert(self, title: str, message: str, button: str = "知道了") -> bool:
        """弹出 macOS 模态对话框（非阻塞，在后台线程运行）。

        对话框会悬浮在所有窗口之上，确保用户一定能看到。

        Args:
            title: 对话框标题
            message: 对话框内容
            button: 按钮文字

        Returns:
            是否弹出成功
        """
        if not self._is_macos:
            logger.info(f"[{self.service_name}] 弹窗: {title} - {message}")
            return False
        try:
            # 使用 System Events 弹出应用级对话框，会出现在最前面
            script = (
                f'tell application "System Events" to display dialog '
                f'"{message}" '
                f'with title "OpenClaw — {title}" '
                f'buttons {{"{button}"}} '
                f'default button "{button}" '
                f'with icon caution '
                f'giving up after 30'
            )
            # 非阻塞启动，不等待用户点击
            subprocess.Popen(
                ["osascript", "-e", script],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return True
        except Exception as e:
            logger.debug(f"macOS 对话框弹出失败: {e}")
            return False

    def play_sound(self, sound_name: str = "Ping", repeat: int = 3) -> None:
        """播放 macOS 系统提示音，重复多次引起注意。

        Args:
            sound_name: 声音名称
            repeat: 重复次数
        """
        if not self._is_macos:
            return
        try:
            for i in range(repeat):
                subprocess.Popen(
                    ["afplay", f"/System/Library/Sounds/{sound_name}.aiff"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                if i < repeat - 1:
                    time.sleep(0.5)
        except Exception as e:
            logger.debug(f"播放提示音失败: {e}")

    def open_url(self, url: str, bring_to_front: bool = True) -> bool:
        """在系统默认浏览器中打开 URL。

        Args:
            url: 要打开的 URL
            bring_to_front: 是否将浏览器窗口置于最前

        Returns:
            是否打开成功
        """
        try:
            if self._is_macos:
                subprocess.Popen(["open", url])
                if bring_to_front:
                    # 短暂等待浏览器启动后将其激活到前台
                    time.sleep(1)
                    self._activate_browser()
            elif sys.platform == "linux":
                subprocess.Popen(["xdg-open", url])
            else:
                subprocess.Popen(["python", "-m", "webbrowser", url])
            return True
        except Exception as e:
            logger.error(f"打开浏览器失败: {e}")
            return False

    def _activate_browser(self) -> None:
        """将浏览器窗口激活到最前台 (macOS)"""
        if not self._is_macos:
            return
        try:
            # 依次尝试激活常用浏览器
            for browser_app in ["Safari", "Google Chrome", "Microsoft Edge", "Firefox"]:
                script = (
                    f'tell application "System Events"\n'
                    f'  if exists process "{browser_app}" then\n'
                    f'    tell application "{browser_app}" to activate\n'
                    f'    return true\n'
                    f'  end if\n'
                    f'end tell'
                )
                result = subprocess.run(
                    ["osascript", "-e", script],
                    capture_output=True, text=True, timeout=3,
                )
                if result.returncode == 0 and "true" in result.stdout.lower():
                    break
        except Exception as e:
            logger.debug(f"激活浏览器失败: {e}")

    def alert_and_open(
        self,
        url: str,
        reason: str = "需要重新登录",
        extra_msg: str = "",
    ) -> bool:
        """完整的登录弹窗流程：通知 + 对话框 + 声音 + 打开浏览器。

        Args:
            url: 登录页面 URL
            reason: 需要登录的原因
            extra_msg: 额外说明

        Returns:
            是否成功弹出
        """
        title = f"{self.service_name} {reason}"
        body = f"{self.service_name}服务需要您手动登录。\n登录完成后系统会自动检测并恢复。"
        if extra_msg:
            body += f"\n{extra_msg}"

        logger.info(f"[登录弹窗] {title}")

        # 1. 通知中心通知
        self.mac_notify(title, body, sound="Basso")

        # 2. 播放提示音引起注意
        self.play_sound("Basso", repeat=2)

        # 3. 打开浏览器
        ok = self.open_url(url, bring_to_front=True)

        # 4. 弹出对话框（30秒自动关闭）
        self.mac_alert(
            title,
            f"{self.service_name}需要登录！\n\n"
            f"浏览器已打开登录页面，请完成登录。\n"
            f"登录后系统会自动恢复服务。",
        )

        return ok

    async def wait_for_condition(
        self,
        check_fn: Callable[[], bool],
        timeout: int = 600,
        poll_interval: int = 10,
        on_success: Optional[Callable] = None,
    ) -> bool:
        """异步轮询等待条件满足（如 Cookie 更新、Token 有效等）。

        Args:
            check_fn: 检查函数，返回 True 表示登录完成
            timeout: 最长等待时间（秒）
            poll_interval: 轮询间隔（秒）
            on_success: 登录成功时的回调

        Returns:
            是否在超时前完成
        """
        start = time.time()
        while time.time() - start < timeout:
            try:
                if check_fn():
                    logger.info(f"[{self.service_name}] 检测到登录成功")
                    self.mac_notify(
                        f"{self.service_name} 登录成功",
                        "服务正在自动恢复...",
                        sound="Glass",
                    )
                    if on_success:
                        on_success()
                    return True
            except Exception as e:
                logger.debug(f"[{self.service_name}] 登录检测异常: {e}")
            await asyncio.sleep(poll_interval)

        logger.warning(f"[{self.service_name}] 登录等待超时 ({timeout}s)")
        return False

    def open_browser_profile(
        self,
        profile_dir: str,
        urls: Optional[list] = None,
    ) -> bool:
        """打开带有特定用户数据目录的 Chrome 浏览器（用于 X/XHS 等需要浏览器 Cookie 的服务）。

        Args:
            profile_dir: Chrome 用户数据目录
            urls: 要打开的 URL 列表

        Returns:
            是否打开成功
        """
        if not self._is_macos:
            logger.info(f"[{self.service_name}] 非 macOS 平台，请手动打开浏览器登录")
            return False

        try:
            chrome_paths = [
                "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
                "/Applications/Chromium.app/Contents/MacOS/Chromium",
            ]
            chrome_path = None
            for p in chrome_paths:
                if os.path.exists(p):
                    chrome_path = p
                    break

            if not chrome_path:
                # 降级为用默认浏览器打开
                if urls:
                    for url in urls:
                        subprocess.Popen(["open", url])
                return True

            cmd = [
                chrome_path,
                f"--user-data-dir={profile_dir}",
                "--no-first-run",
                "--disable-default-apps",
            ]
            if urls:
                cmd.extend(urls)

            subprocess.Popen(cmd)
            return True
        except Exception as e:
            logger.error(f"打开浏览器 Profile 失败: {e}")
            return False
