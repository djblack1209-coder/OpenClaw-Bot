"""
ClawBot - 拟人化桌面控制器
基于 pyautogui + 自定义贝塞尔曲线鼠标运动

macOS 权限需求:
  - System Settings > Privacy & Security > Accessibility  (鼠标/键盘控制)
  - System Settings > Privacy & Security > Screen Recording (截图功能)

安装:
  pip3 install pyautogui pyobjc-core pyobjc-framework-Quartz
"""

import logging
import math
import os
import random
import time
from dataclasses import dataclass
from typing import List, Optional, Tuple

import pyautogui

logger = logging.getLogger(__name__)

# ── 安全设置 ───────────────────────────────────────────────
# 鼠标移到屏幕左上角时自动中止 (pyautogui 内置安全机制)
pyautogui.FAILSAFE = True
# 每次 pyautogui 动作后的默认暂停(秒) — 我们用自己的随机延迟覆盖
pyautogui.PAUSE = 0.0


# ── 配置 ──────────────────────────────────────────────────

@dataclass
class HumanConfig:
    """拟人化行为参数"""

    # 鼠标移动
    mouse_speed_min: float = 0.3        # 最短移动耗时(秒)
    mouse_speed_max: float = 1.2        # 最长移动耗时(秒)
    mouse_curve_spread: float = 80.0    # 贝塞尔曲线控制点偏移量(像素)
    mouse_jitter_px: int = 3            # 终点抖动范围(像素)
    mouse_step_interval: float = 0.012  # 每步间隔(秒), ~83fps

    # 点击
    click_delay_min: float = 0.03       # 按下→释放 最短间隔
    click_delay_max: float = 0.12       # 按下→释放 最长间隔

    # 动作间延迟
    action_delay_min: float = 0.08      # 连续动作间最短等待
    action_delay_max: float = 0.35      # 连续动作间最长等待

    # 打字
    typing_speed_min: float = 0.04      # 每键最短间隔(秒)  ~25 WPM peak
    typing_speed_max: float = 0.16      # 每键最长间隔(秒)  ~7 WPM valley
    typing_burst_len: tuple = (3, 8)    # 快速连打字符数范围
    typing_pause_min: float = 0.2       # 打字"思考"暂停 最短
    typing_pause_max: float = 0.6       # 打字"思考"暂停 最长
    typo_probability: float = 0.02      # 每个字符出错概率 (2%)
    typo_correct_delay: float = 0.3     # 发现错误后的反应时间

    # 滚动
    scroll_step_min: int = 1            # 每次滚动最少行数
    scroll_step_max: int = 5            # 每次滚动最多行数
    scroll_delay_min: float = 0.05      # 滚动步间延迟 最短
    scroll_delay_max: float = 0.15      # 滚动步间延迟 最长


# ── 贝塞尔曲线工具 ────────────────────────────────────────

def _cubic_bezier(
    p0: Tuple[float, float],
    p1: Tuple[float, float],
    p2: Tuple[float, float],
    p3: Tuple[float, float],
    num_points: int = 60,
) -> List[Tuple[int, int]]:
    """
    生成三次贝塞尔曲线上的离散点。

    P0 = 起点, P1/P2 = 控制点, P3 = 终点
    B(t) = (1-t)^3*P0 + 3*(1-t)^2*t*P1 + 3*(1-t)*t^2*P2 + t^3*P3
    """
    points = []
    for i in range(num_points + 1):
        t = i / num_points
        inv = 1.0 - t
        x = (inv ** 3 * p0[0]
             + 3 * inv ** 2 * t * p1[0]
             + 3 * inv * t ** 2 * p2[0]
             + t ** 3 * p3[0])
        y = (inv ** 3 * p0[1]
             + 3 * inv ** 2 * t * p1[1]
             + 3 * inv * t ** 2 * p2[1]
             + t ** 3 * p3[1])
        points.append((int(round(x)), int(round(y))))
    return points


def _random_control_point(
    start: Tuple[float, float],
    end: Tuple[float, float],
    spread: float,
    bias: float = 0.33,
) -> Tuple[float, float]:
    """
    在起点→终点连线的 bias 位置处，向垂直方向随机偏移 spread 像素，
    生成一个自然的贝塞尔控制点。
    """
    mx = start[0] + (end[0] - start[0]) * bias
    my = start[1] + (end[1] - start[1]) * bias

    dx = end[0] - start[0]
    dy = end[1] - start[1]
    dist = math.hypot(dx, dy) or 1.0

    # 垂直于运动方向的单位向量
    nx = -dy / dist
    ny = dx / dist

    offset = random.gauss(0, spread * 0.5)
    return (mx + nx * offset, my + ny * offset)


# ── 键盘邻居映射 (QWERTY) ────────────────────────────────

_NEARBY_KEYS = {
    'a': 'sqwz', 'b': 'vghn', 'c': 'xdfv', 'd': 'serfcx',
    'e': 'wsdfr', 'f': 'drtgvc', 'g': 'ftyhbv', 'h': 'gyujnb',
    'i': 'ujklo', 'j': 'huiknm', 'k': 'jiolm', 'l': 'kop',
    'm': 'njk', 'n': 'bhjm', 'o': 'iklp', 'p': 'ol',
    'q': 'wa', 'r': 'edft', 's': 'awedxz', 't': 'rfgy',
    'u': 'yhjki', 'v': 'cfgb', 'w': 'qase', 'x': 'zsdc',
    'y': 'tghu', 'z': 'asx',
}


# ── 主控制器 ─────────────────────────────────────────────

class HumanizedController:
    """
    拟人化桌面操控器。

    所有动作模拟真人操作节奏:
    - 鼠标沿贝塞尔曲线移动（非瞬移）
    - 打字速度波动，偶发拼写错误后回删修正
    - 动作间随机延迟
    - 点击有按下/释放间隔
    """

    def __init__(self, config: Optional[HumanConfig] = None):
        self.cfg = config or HumanConfig()
        self._screen_w, self._screen_h = pyautogui.size()

    # ── 内部工具 ──────────────────────────────────────────

    def _random_delay(self, lo: Optional[float] = None, hi: Optional[float] = None):
        """随机等待"""
        lo = lo if lo is not None else self.cfg.action_delay_min
        hi = hi if hi is not None else self.cfg.action_delay_max
        time.sleep(random.uniform(lo, hi))

    def _clamp(self, x: int, y: int) -> Tuple[int, int]:
        """确保坐标在屏幕范围内"""
        return (
            max(0, min(x, self._screen_w - 1)),
            max(0, min(y, self._screen_h - 1)),
        )

    def _add_jitter(self, x: int, y: int) -> Tuple[int, int]:
        """给目标坐标加微小抖动"""
        j = self.cfg.mouse_jitter_px
        return self._clamp(
            x + random.randint(-j, j),
            y + random.randint(-j, j),
        )

    # ── 鼠标移动 ──────────────────────────────────────────

    def move_to(self, x: int, y: int, duration: Optional[float] = None):
        """
        沿贝塞尔曲线将鼠标移动到 (x, y)。

        Args:
            x: 目标 x 坐标
            y: 目标 y 坐标
            duration: 移动耗时(秒), None 则随机生成
        """
        start_x, start_y = pyautogui.position()
        end_x, end_y = self._add_jitter(x, y)

        dist = math.hypot(end_x - start_x, end_y - start_y)
        if dist < 2:
            # 距离太近，不需要曲线
            pyautogui.moveTo(end_x, end_y, _pause=False)
            return

        if duration is None:
            # 距离越远耗时越长，但有上下限
            base = dist / 1500.0
            duration = max(self.cfg.mouse_speed_min,
                           min(base + random.uniform(0.1, 0.3),
                               self.cfg.mouse_speed_max))

        # 生成双控制点贝塞尔曲线
        cp1 = _random_control_point(
            (start_x, start_y), (end_x, end_y),
            self.cfg.mouse_curve_spread, bias=0.3)
        cp2 = _random_control_point(
            (start_x, start_y), (end_x, end_y),
            self.cfg.mouse_curve_spread, bias=0.7)

        num_steps = max(20, int(duration / self.cfg.mouse_step_interval))
        path = _cubic_bezier(
            (start_x, start_y), cp1, cp2, (end_x, end_y),
            num_points=num_steps)

        step_sleep = duration / len(path)
        for px, py in path:
            px, py = self._clamp(px, py)
            pyautogui.moveTo(px, py, _pause=False)
            time.sleep(step_sleep)

    def move_relative(self, dx: int, dy: int, duration: Optional[float] = None):
        """相对当前位置移动"""
        cx, cy = pyautogui.position()
        self.move_to(cx + dx, cy + dy, duration)

    # ── 点击 ──────────────────────────────────────────────

    def click(
        self,
        x: Optional[int] = None,
        y: Optional[int] = None,
        button: str = "left",
        clicks: int = 1,
    ):
        """
        拟人化点击。先移动到目标位置，再按下并释放。

        Args:
            x, y: 目标坐标, None 表示当前位置
            button: "left" / "right" / "middle"
            clicks: 点击次数 (2 = 双击)
        """
        if x is not None and y is not None:
            self.move_to(x, y)
            self._random_delay()

        for i in range(clicks):
            pyautogui.mouseDown(button=button, _pause=False)
            time.sleep(random.uniform(
                self.cfg.click_delay_min, self.cfg.click_delay_max))
            pyautogui.mouseUp(button=button, _pause=False)
            if i < clicks - 1:
                # 连续点击间的间隔 (双击约 0.05-0.10s)
                time.sleep(random.uniform(0.04, 0.10))

    def double_click(self, x: Optional[int] = None, y: Optional[int] = None):
        """双击"""
        self.click(x, y, clicks=2)

    def right_click(self, x: Optional[int] = None, y: Optional[int] = None):
        """右键单击"""
        self.click(x, y, button="right")

    # ── 拖拽 ──────────────────────────────────────────────

    def drag_to(
        self,
        start_x: int, start_y: int,
        end_x: int, end_y: int,
        button: str = "left",
        duration: Optional[float] = None,
    ):
        """
        拟人化拖拽: 移到起点 → 按下 → 沿曲线移到终点 → 释放。
        """
        self.move_to(start_x, start_y)
        self._random_delay()
        pyautogui.mouseDown(button=button, _pause=False)
        time.sleep(random.uniform(0.08, 0.15))

        # 拖拽路径也走贝塞尔
        self.move_to(end_x, end_y, duration=duration)
        time.sleep(random.uniform(0.05, 0.10))
        pyautogui.mouseUp(button=button, _pause=False)

    # ── 滚动 ──────────────────────────────────────────────

    def scroll(
        self,
        amount: int,
        x: Optional[int] = None,
        y: Optional[int] = None,
    ):
        """
        拟人化滚动。正数向上，负数向下。
        分多步执行，每步间有随机延迟。
        """
        if x is not None and y is not None:
            self.move_to(x, y)
            self._random_delay()

        remaining = abs(amount)
        direction = 1 if amount > 0 else -1

        while remaining > 0:
            step = min(remaining, random.randint(
                self.cfg.scroll_step_min, self.cfg.scroll_step_max))
            pyautogui.scroll(step * direction, _pause=False)
            remaining -= step
            if remaining > 0:
                time.sleep(random.uniform(
                    self.cfg.scroll_delay_min, self.cfg.scroll_delay_max))

    # ── 键盘输入 ──────────────────────────────────────────

    def type_text(self, text: str, correct_typos: bool = True):
        """
        拟人化打字:
        - 速度波动 (burst 连打 + 思考暂停)
        - 偶发邻键错误并回删修正
        - 支持中英文 (中文通过 pyperclip 粘贴)

        Args:
            text: 要输入的文本
            correct_typos: 是否自动修正错误 (False = 留着错误)
        """
        burst_remaining = random.randint(*self.cfg.typing_burst_len)

        for char in text:
            # 周期性"思考"暂停
            burst_remaining -= 1
            if burst_remaining <= 0:
                time.sleep(random.uniform(
                    self.cfg.typing_pause_min, self.cfg.typing_pause_max))
                burst_remaining = random.randint(*self.cfg.typing_burst_len)

            # 模拟打字错误
            if (correct_typos
                    and char.lower() in _NEARBY_KEYS
                    and random.random() < self.cfg.typo_probability):
                wrong = random.choice(_NEARBY_KEYS[char.lower()])
                if char.isupper():
                    wrong = wrong.upper()
                pyautogui.press(wrong, _pause=False)
                time.sleep(random.uniform(
                    self.cfg.typing_speed_min, self.cfg.typing_speed_max))

                # 反应时间 + 退格修正
                time.sleep(random.uniform(
                    self.cfg.typo_correct_delay * 0.5,
                    self.cfg.typo_correct_delay * 1.5))
                pyautogui.press('backspace', _pause=False)
                time.sleep(random.uniform(0.05, 0.12))

            # 输入正确字符
            if char == '\n':
                pyautogui.press('enter', _pause=False)
            elif char == '\t':
                pyautogui.press('tab', _pause=False)
            else:
                pyautogui.press(char, _pause=False)

            # 字符间延迟
            time.sleep(random.uniform(
                self.cfg.typing_speed_min, self.cfg.typing_speed_max))

    def press_key(self, key: str, presses: int = 1):
        """
        按下单个键 (支持 'enter', 'tab', 'escape', 'f1' 等)。
        """
        for i in range(presses):
            pyautogui.keyDown(key, _pause=False)
            time.sleep(random.uniform(
                self.cfg.click_delay_min, self.cfg.click_delay_max))
            pyautogui.keyUp(key, _pause=False)
            if i < presses - 1:
                self._random_delay(0.05, 0.15)

    def hotkey(self, *keys: str):
        """
        组合键 (如 hotkey('command', 'c'))。
        按键之间有微小延迟模拟真人。
        """
        for key in keys:
            pyautogui.keyDown(key, _pause=False)
            time.sleep(random.uniform(0.02, 0.08))
        for key in reversed(keys):
            pyautogui.keyUp(key, _pause=False)
            time.sleep(random.uniform(0.02, 0.06))

    def paste_text(self, text: str):
        """
        通过剪贴板粘贴文本 (适用于中文等 pyautogui.press 无法直接输入的字符)。
        使用 macOS pbcopy + Cmd+V。
        """
        import subprocess
        process = subprocess.Popen(
            ['pbcopy'], stdin=subprocess.PIPE)
        process.communicate(text.encode('utf-8'))

        self._random_delay(0.1, 0.25)
        self.hotkey('command', 'v')
        self._random_delay(0.05, 0.15)

    # ── 截图与定位 ────────────────────────────────────────

    def screenshot(self, region: Optional[Tuple[int, int, int, int]] = None):
        """
        截屏并返回 PIL Image。

        Args:
            region: (x, y, width, height) 可选区域
        Returns:
            PIL.Image.Image
        """
        return pyautogui.screenshot(region=region)

    def locate_on_screen(
        self,
        image_path: str,
        confidence: float = 0.85,
        grayscale: bool = True,
    ) -> Optional[Tuple[int, int]]:
        """
        在屏幕上查找图片并返回中心坐标。

        Args:
            image_path: 参考图片路径
            confidence: 匹配置信度 (需要 opencv-python)
            grayscale: 灰度匹配加速
        Returns:
            (x, y) 中心坐标, 或 None
        """
        try:
            location = pyautogui.locateCenterOnScreen(
                image_path, confidence=confidence, grayscale=grayscale)
            return location
        except pyautogui.ImageNotFoundException:
            return None
        except Exception as e:
            # opencv 未安装时 confidence 参数不可用
            logger.debug("[HumanizedController] 异常: %s", e)
            try:
                location = pyautogui.locateCenterOnScreen(
                    image_path, grayscale=grayscale)
                return location
            except Exception as e:
                logger.debug("[HumanizedController] 异常: %s", e)
                return None

    def click_image(
        self,
        image_path: str,
        confidence: float = 0.85,
        button: str = "left",
    ) -> bool:
        """
        找到屏幕上的图片并点击其中心。

        Returns:
            True 如果找到并点击, False 如果未找到
        """
        pos = self.locate_on_screen(image_path, confidence)
        if pos:
            self.click(pos[0], pos[1], button=button)
            return True
        return False

    # ── 复合动作 ──────────────────────────────────────────

    def click_and_type(
        self,
        x: int, y: int,
        text: str,
        clear_first: bool = False,
    ):
        """
        点击输入框后打字。

        Args:
            x, y: 输入框坐标
            text: 输入内容
            clear_first: 是否先全选清空
        """
        self.click(x, y)
        self._random_delay(0.1, 0.3)

        if clear_first:
            self.hotkey('command', 'a')
            self._random_delay(0.05, 0.15)
            self.press_key('backspace')
            self._random_delay(0.1, 0.2)

        self.type_text(text)

    def wait_and_click_image(
        self,
        image_path: str,
        timeout: float = 10.0,
        interval: float = 0.5,
        confidence: float = 0.85,
    ) -> bool:
        """
        等待图片出现在屏幕上，然后点击。

        Args:
            image_path: 参考图片
            timeout: 最大等待时间(秒)
            interval: 检查间隔(秒)
            confidence: 匹配置信度
        Returns:
            True 如果成功, False 如果超时
        """
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self.click_image(image_path, confidence):
                return True
            time.sleep(interval)
        return False

    # ── 权限检查 ──────────────────────────────────────────

    @staticmethod
    def check_accessibility_permission() -> bool:
        """
        检查当前进程是否有 macOS Accessibility 权限。
        Returns:
            True 表示已授权
        """
        if os.uname().sysname != "Darwin":
            return True  # 非 macOS 无需此权限

        try:
            import Quartz
            # 尝试创建一个 CGEvent，如果没有权限会返回 None
            event = Quartz.CGEventCreateMouseEvent(
                None, Quartz.kCGEventMouseMoved, (0, 0), 0)
            if event is None:
                return False
            return True
        except Exception as e:
            logger.debug("[HumanizedController] 异常: %s", e)
            return False

    @staticmethod
    def request_accessibility_prompt():
        """
        弹出 macOS 系统提示请求 Accessibility 权限。
        用户需要手动在 System Settings 中授权。
        """
        if os.uname().sysname != "Darwin":
            return

        import subprocess
        subprocess.run([
            "osascript", "-e",
            'tell application "System Events" to keystroke ""'
        ], capture_output=True, timeout=5)

    # ── 上下文管理 ────────────────────────────────────────

    def get_position(self) -> Tuple[int, int]:
        """获取当前鼠标位置"""
        return pyautogui.position()

    def get_screen_size(self) -> Tuple[int, int]:
        """获取屏幕分辨率"""
        return self._screen_w, self._screen_h
