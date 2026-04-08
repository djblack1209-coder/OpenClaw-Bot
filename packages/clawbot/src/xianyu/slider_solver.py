"""闲鱼滑块验证码自动求解器 — Playwright + Perlin 噪声轨迹

搬运自 GuDong2003/xianyu-auto-reply-fix 的核心算法，适配 OpenClaw 项目。

核心技术：
1. Perlin 噪声生成连续平滑的非周期性随机轨迹（模拟人手抖动）
2. 三阶段拖动：加速 → 匀速 → 减速超调 → 修正回退
3. Stealth JS 注入：隐藏 webdriver 属性、伪造浏览器指纹
4. 全流程人类行为模拟：接近 → 悬停 → 按下 → 拖动 → 释放

使用示例：
    from src.xianyu.slider_solver import SliderSolver
    solver = SliderSolver()
    # 在 Playwright page 上注入 stealth 并自动处理滑块
    solved = await solver.solve(page, max_retries=5)
"""
import logging
import math
import random
import time
from typing import Optional

logger = logging.getLogger(__name__)

# ---- Perlin 噪声（1D）—— 生成连续平滑的随机抖动 ----
# 比 sin 叠加更自然，更难被检测

# 预计算排列表（标准 Perlin 噪声用 256 元素）
_PERM = list(range(256))
random.shuffle(_PERM)
_PERM = _PERM + _PERM  # 扩展到 512 避免溢出


def _perlin_fade(t: float) -> float:
    """6t^5 - 15t^4 + 10t^3 缓动函数，让过渡更平滑"""
    return t * t * t * (t * (t * 6 - 15) + 10)


def _perlin_lerp(a: float, b: float, t: float) -> float:
    """线性插值"""
    return a + t * (b - a)


def _perlin_grad(hash_val: int, x: float) -> float:
    """1D 梯度计算"""
    return x if (hash_val & 1) == 0 else -x


def perlin_noise_1d(x: float, seed_offset: int = 0) -> float:
    """1D Perlin 噪声，返回 [-1, 1] 的值"""
    xi = int(math.floor(x)) & 255
    xf = x - math.floor(x)
    u = _perlin_fade(xf)
    a = _PERM[(xi + seed_offset) & 511]
    b = _PERM[(xi + 1 + seed_offset) & 511]
    return _perlin_lerp(_perlin_grad(a, xf), _perlin_grad(b, xf - 1), u)


# ---- 反检测 Stealth JS 脚本 ----
# 注入到浏览器页面，隐藏自动化痕迹

STEALTH_JS = """
// 1. 隐藏 webdriver 属性（核心）
Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
try { delete navigator.__proto__.webdriver; } catch(e) {}

// 2. 伪造 plugins（随机数量，看起来像真实浏览器）
const pluginCount = 3 + Math.floor(Math.random() * 4);
const fakePlugins = Array.from({length: pluginCount}, (_, i) => ({
    name: ['Chrome PDF Plugin', 'Chrome PDF Viewer', 'Native Client',
           'Chromium PDF Plugin', 'Widevine Content Decryption Module',
           'Microsoft Edge PDF Plugin'][i % 6],
    description: 'Portable Document Format',
    filename: 'internal-pdf-viewer',
    length: 1
}));
Object.defineProperty(navigator, 'plugins', {
    get: () => {
        const arr = fakePlugins;
        arr.item = (i) => arr[i];
        arr.namedItem = (name) => arr.find(p => p.name === name);
        arr.refresh = () => {};
        return arr;
    }
});

// 3. 伪造 languages
Object.defineProperty(navigator, 'languages', {
    get: () => ['zh-CN', 'zh', 'en']
});

// 4. 伪造 Chrome 运行时对象
if (!window.chrome) {
    window.chrome = { runtime: {}, loadTimes: function(){}, csi: function(){} };
}

// 5. 隐藏自动化检测的 window 属性
['__webdriver_evaluate', '__selenium_evaluate', '__fxdriver_evaluate',
 '__driver_evaluate', '__webdriver_unwrapped', '__selenium_unwrapped',
 '__fxdriver_unwrapped', '__driver_unwrapped', '__lastWatirAlert',
 '__lastWatirConfirm', '__lastWatirPrompt', '_Selenium_IDE_Recorder',
 'callSelenium', '_selenium', 'calledSelenium', '_WEBDRIVER_ELEM_CACHE',
 'ChromeDriverw', 'driver-hierarchical', 'webdriver', '$chrome_asyncScriptInfo',
 '$cdc_asdjflasutopfhvcZLmcfl_'].forEach(prop => {
    try { delete window[prop]; } catch(e) {}
    Object.defineProperty(window, prop, {
        get: () => undefined,
        set: () => {},
        configurable: true
    });
});

// 6. 修正 permissions API（防止 Notification permission 暴露自动化）
const originalQuery = window.navigator.permissions?.query;
if (originalQuery) {
    window.navigator.permissions.query = (parameters) =>
        parameters.name === 'notifications'
            ? Promise.resolve({ state: Notification.permission })
            : originalQuery(parameters);
}

// 7. 伪造 WebGL 渲染器信息
const getParameter = WebGLRenderingContext.prototype.getParameter;
WebGLRenderingContext.prototype.getParameter = function(parameter) {
    if (parameter === 37445) return 'Intel Inc.';
    if (parameter === 37446) return 'Intel Iris OpenGL Engine';
    return getParameter.call(this, parameter);
};
"""


def _generate_trajectory(distance: int, steps: int = 30) -> list[dict]:
    """生成从起点到终点的人类化拖动轨迹。

    使用 Perlin 噪声生成 Y 轴微抖，模拟人手的不稳定性。
    X 轴使用三阶段运动：加速 → 匀速 → 减速超调 → 回退修正。

    Args:
        distance: 滑块需要移动的像素距离
        steps: 轨迹总步数

    Returns:
        轨迹点列表 [{"x": float, "y": float, "dt": float}, ...]
        dt 为每步间隔（毫秒）
    """
    # 超调比例：滑过目标再回来（3-10% 超调）
    overshoot_ratio = random.uniform(1.03, 1.10)
    overshoot_distance = distance * overshoot_ratio

    # 修正阶段步数（超调后回退的步数）
    correction_steps = random.randint(3, 7)
    main_steps = steps - correction_steps

    trajectory = []
    seed_y = random.randint(0, 255)  # Y 轴噪声种子

    # 主拖动阶段（加速 → 匀速 → 超调）
    for i in range(main_steps):
        progress = i / max(main_steps - 1, 1)  # 0 → 1

        # X 轴：ease-in-out 缓动（开始慢 → 中间快 → 结束慢）
        # 使用 smoothstep 函数
        smooth = progress * progress * (3 - 2 * progress)
        x = overshoot_distance * smooth

        # Y 轴：Perlin 噪声微抖（幅度 ±3 像素）
        y_noise = perlin_noise_1d(progress * 5, seed_y) * 3.0
        # 加上微小的整体漂移（人的手会轻微向上或向下偏）
        y_drift = math.sin(progress * math.pi) * random.uniform(-2, 2)

        # 时间间隔：中间快两头慢（模拟加速和减速）
        if progress < 0.2:
            # 加速阶段：间隔较大
            dt = random.uniform(15, 30)
        elif progress > 0.8:
            # 减速阶段：间隔逐渐变大
            dt = random.uniform(20, 40)
        else:
            # 匀速阶段：间隔较小（快速移动）
            dt = random.uniform(8, 18)

        trajectory.append({"x": x, "y": y_noise + y_drift, "dt": dt})

    # 修正阶段（从超调位置回退到目标位置）
    current_x = overshoot_distance
    for i in range(correction_steps):
        progress = (i + 1) / correction_steps
        # 线性回退到目标位置
        x = current_x + (distance - current_x) * progress
        # Y 轴逐渐归零
        y_noise = perlin_noise_1d((main_steps + i) * 0.5, seed_y) * 1.5 * (1 - progress)

        trajectory.append({
            "x": x,
            "y": y_noise,
            "dt": random.uniform(25, 50),  # 修正时速度较慢
        })

    return trajectory


class SliderSolver:
    """闲鱼滑块验证码求解器 — 使用 Playwright 自动识别并拖动滑块"""

    # 淘宝/闲鱼滑块的 CSS 选择器（多种变体）
    SLIDER_SELECTORS = [
        "#nc_1_n1z",              # 标准滑块按钮
        "#nc_1__scale_text",      # 滑块轨道文字
        ".nc-lang-cnt",           # 滑块容器
        "#nocaptcha",             # nocaptcha 容器
        ".nc_wrapper",            # 滑块包裹器
        "#baxia-dialog-content",  # 百姓验证弹窗
        "iframe[src*='captcha']", # 验证码 iframe
    ]

    # 滑块按钮选择器（用于实际拖动）
    SLIDER_BUTTON_SELECTORS = [
        "#nc_1_n1z",
        ".btn_slide",
        ".nc-lang-cnt .btn_slide",
        ".slider-btn",
    ]

    # 滑块轨道选择器（用于计算拖动距离）
    SLIDER_TRACK_SELECTORS = [
        "#nc_1__scale_text",
        ".nc-lang-cnt",
        ".slider-track",
        ".scale_text",
    ]

    def __init__(self):
        self._attempt_count = 0

    async def inject_stealth(self, page) -> None:
        """向页面注入反检测 JS 脚本。应在 page.goto() 之前调用。

        Args:
            page: Playwright Page 对象
        """
        try:
            await page.add_init_script(STEALTH_JS)
            logger.debug("Stealth JS 已注入")
        except Exception as e:
            logger.warning(f"Stealth JS 注入失败: {e}")

    async def detect_slider(self, page) -> bool:
        """检测页面上是否存在滑块验证码。

        Args:
            page: Playwright Page 对象

        Returns:
            是否存在滑块
        """
        # 先检查是否有验证码 iframe（常见于淘宝/闲鱼）
        for selector in self.SLIDER_SELECTORS:
            try:
                element = await page.query_selector(selector)
                if element and await element.is_visible():
                    logger.info(f"检测到滑块验证码: {selector}")
                    return True
            except Exception:
                continue

        # 检查 iframe 内部
        for frame in page.frames:
            try:
                for selector in self.SLIDER_BUTTON_SELECTORS:
                    element = await frame.query_selector(selector)
                    if element and await element.is_visible():
                        logger.info(f"检测到 iframe 内滑块验证码: {selector}")
                        return True
            except Exception:
                continue

        return False

    async def _find_slider_elements(self, page) -> tuple:
        """在页面和 iframe 中查找滑块按钮和轨道。

        Returns:
            (slider_button, slider_track, frame_or_page)
            任一为 None 表示未找到
        """
        # 先在主页面找
        targets = [page] + list(page.frames)

        for target in targets:
            try:
                slider_btn = None
                slider_track = None

                for sel in self.SLIDER_BUTTON_SELECTORS:
                    elem = await target.query_selector(sel)
                    if elem and await elem.is_visible():
                        slider_btn = elem
                        break

                for sel in self.SLIDER_TRACK_SELECTORS:
                    elem = await target.query_selector(sel)
                    if elem and await elem.is_visible():
                        slider_track = elem
                        break

                if slider_btn:
                    return slider_btn, slider_track, target
            except Exception:
                continue

        return None, None, None

    async def _slide_once(self, page, slider_btn, slider_track) -> bool:
        """执行一次滑块拖动操作。

        Args:
            page: Playwright Page 对象
            slider_btn: 滑块按钮元素
            slider_track: 滑块轨道元素（用于计算距离）

        Returns:
            是否成功（通过检测页面变化判断）
        """
        self._attempt_count += 1
        logger.info(f"滑块求解: 第 {self._attempt_count} 次尝试")

        try:
            # 获取滑块按钮和轨道的位置
            btn_box = await slider_btn.bounding_box()
            if not btn_box:
                logger.warning("无法获取滑块按钮位置")
                return False

            # 计算滑动距离
            if slider_track:
                track_box = await slider_track.bounding_box()
                if track_box:
                    slide_distance = int(track_box["width"] - btn_box["width"])
                else:
                    slide_distance = 300  # 默认距离
            else:
                slide_distance = 300

            logger.info(f"滑动距离: {slide_distance}px")

            # 生成人类化轨迹
            steps = random.randint(25, 40)
            trajectory = _generate_trajectory(slide_distance, steps=steps)

            # 起始点：滑块按钮中心
            start_x = btn_box["x"] + btn_box["width"] / 2
            start_y = btn_box["y"] + btn_box["height"] / 2

            # 模拟人类行为：先移动鼠标到滑块附近
            approach_x = start_x + random.uniform(-30, -10)
            approach_y = start_y + random.uniform(-5, 5)
            await page.mouse.move(approach_x, approach_y)
            await _async_sleep(random.uniform(0.1, 0.3))

            # 移动到滑块上
            await page.mouse.move(start_x, start_y)
            await _async_sleep(random.uniform(0.05, 0.15))

            # 按下鼠标
            await page.mouse.down()
            await _async_sleep(random.uniform(0.08, 0.2))

            # 沿轨迹拖动
            for point in trajectory:
                target_x = start_x + point["x"]
                target_y = start_y + point["y"]
                await page.mouse.move(target_x, target_y)
                await _async_sleep(point["dt"] / 1000.0)

            # 短暂停顿后释放
            await _async_sleep(random.uniform(0.01, 0.06))
            await page.mouse.up()

            # 等待验证结果
            await _async_sleep(random.uniform(1.0, 2.0))

            # 检查是否成功（多种检测方式）
            return await self._check_solved(page)

        except Exception as e:
            logger.warning(f"滑块拖动异常: {e}")
            return False

    async def _check_solved(self, page) -> bool:
        """检查滑块是否已成功通过。

        通过多种方式检测：
        1. 成功提示文字
        2. 滑块消失
        3. 页面跳转
        4. 错误提示（需要重试）
        """
        try:
            # 检查成功标志
            success_selectors = [
                ".nc-lang-cnt.nc_done",   # 标准成功状态
                "#nc_1__success",          # 成功提示
                ".nc_ok",                  # 成功 class
            ]
            for sel in success_selectors:
                elem = await page.query_selector(sel)
                if elem:
                    logger.info("滑块验证通过!")
                    return True

            # 检查错误/需要重试
            error_selectors = [
                ".nc-lang-cnt.nc_fail",
                "#nc_1__error",
                ".errloading",
            ]
            for sel in error_selectors:
                elem = await page.query_selector(sel)
                if elem and await elem.is_visible():
                    logger.info("滑块验证失败，需要重试")
                    return False

            # 检查滑块是否消失（可能被替换为其他验证或已通过）
            slider_gone = True
            for sel in self.SLIDER_BUTTON_SELECTORS:
                elem = await page.query_selector(sel)
                if elem and await elem.is_visible():
                    slider_gone = False
                    break

            if slider_gone:
                logger.info("滑块已消失，可能验证通过")
                return True

        except Exception as e:
            logger.debug(f"检查滑块状态异常: {e}")

        return False

    async def solve(self, page, max_retries: int = 5) -> bool:
        """自动检测并求解滑块验证码。

        Args:
            page: Playwright Page 对象
            max_retries: 最大重试次数

        Returns:
            是否成功
        """
        self._attempt_count = 0

        for attempt in range(max_retries):
            # 检测是否有滑块
            if not await self.detect_slider(page):
                if attempt == 0:
                    logger.debug("未检测到滑块验证码")
                else:
                    logger.info("滑块已消失，验证可能已通过")
                return True  # 没有滑块就是成功

            # 查找滑块元素
            slider_btn, slider_track, target = await self._find_slider_elements(page)
            if not slider_btn:
                logger.warning(f"第 {attempt + 1} 次: 检测到滑块但无法定位按钮")
                await _async_sleep(2)
                continue

            # 执行滑动
            solved = await self._slide_once(page, slider_btn, slider_track)
            if solved:
                return True

            # 失败后等待一段时间再重试（可能需要刷新验证码）
            wait = random.uniform(2, 4)
            logger.info(f"等待 {wait:.1f}s 后重试...")
            await _async_sleep(wait)

            # 尝试点击刷新/重试按钮
            try:
                refresh_selectors = [
                    ".nc-lang-cnt .errloading a",  # 错误后的重新加载链接
                    "#nc_1__refresh",               # 刷新按钮
                    ".errloading",                  # 点击错误区域重试
                ]
                for sel in refresh_selectors:
                    elem = await page.query_selector(sel)
                    if elem and await elem.is_visible():
                        await elem.click()
                        await _async_sleep(1.5)
                        break
            except Exception:
                pass

        logger.warning(f"滑块求解失败，已尝试 {max_retries} 次")
        return False


async def _async_sleep(seconds: float) -> None:
    """异步等待（兼容 sync 和 async 上下文）"""
    import asyncio
    await asyncio.sleep(seconds)


def solve_slider_sync(page, max_retries: int = 5) -> bool:
    """同步版滑块求解 — 用于 Playwright sync_api。

    Args:
        page: Playwright sync Page 对象
        max_retries: 最大重试次数

    Returns:
        是否成功
    """
    solver = SliderSolverSync()
    return solver.solve(page, max_retries=max_retries)


class SliderSolverSync:
    """同步版滑块求解器 — 用于 scripts/xianyu_login.py 的同步 Playwright"""

    SLIDER_BUTTON_SELECTORS = SliderSolver.SLIDER_BUTTON_SELECTORS
    SLIDER_TRACK_SELECTORS = SliderSolver.SLIDER_TRACK_SELECTORS
    SLIDER_SELECTORS = SliderSolver.SLIDER_SELECTORS

    def __init__(self):
        self._attempt_count = 0

    def detect_slider(self, page) -> bool:
        """检测页面上是否存在滑块验证码（同步版）"""
        for selector in self.SLIDER_SELECTORS:
            try:
                element = page.query_selector(selector)
                if element and element.is_visible():
                    logger.info(f"检测到滑块验证码: {selector}")
                    return True
            except Exception:
                continue

        # 检查 iframe 内部
        for frame in page.frames:
            try:
                for selector in self.SLIDER_BUTTON_SELECTORS:
                    element = frame.query_selector(selector)
                    if element and element.is_visible():
                        logger.info(f"检测到 iframe 内滑块: {selector}")
                        return True
            except Exception:
                continue

        return False

    def _find_slider_elements(self, page) -> tuple:
        """查找滑块按钮和轨道（同步版）"""
        targets = [page] + list(page.frames)
        for target in targets:
            try:
                slider_btn = None
                slider_track = None
                for sel in self.SLIDER_BUTTON_SELECTORS:
                    elem = target.query_selector(sel)
                    if elem and elem.is_visible():
                        slider_btn = elem
                        break
                for sel in self.SLIDER_TRACK_SELECTORS:
                    elem = target.query_selector(sel)
                    if elem and elem.is_visible():
                        slider_track = elem
                        break
                if slider_btn:
                    return slider_btn, slider_track, target
            except Exception:
                continue
        return None, None, None

    def _slide_once(self, page, slider_btn, slider_track) -> bool:
        """执行一次滑块拖动（同步版）"""
        self._attempt_count += 1
        logger.info(f"滑块求解: 第 {self._attempt_count} 次尝试")

        try:
            btn_box = slider_btn.bounding_box()
            if not btn_box:
                logger.warning("无法获取滑块按钮位置")
                return False

            if slider_track:
                track_box = slider_track.bounding_box()
                slide_distance = int(track_box["width"] - btn_box["width"]) if track_box else 300
            else:
                slide_distance = 300

            logger.info(f"滑动距离: {slide_distance}px")

            steps = random.randint(25, 40)
            trajectory = _generate_trajectory(slide_distance, steps=steps)

            start_x = btn_box["x"] + btn_box["width"] / 2
            start_y = btn_box["y"] + btn_box["height"] / 2

            # 接近滑块
            page.mouse.move(start_x + random.uniform(-30, -10),
                          start_y + random.uniform(-5, 5))
            time.sleep(random.uniform(0.1, 0.3))

            # 移到滑块上
            page.mouse.move(start_x, start_y)
            time.sleep(random.uniform(0.05, 0.15))

            # 按下
            page.mouse.down()
            time.sleep(random.uniform(0.08, 0.2))

            # 沿轨迹拖动
            for point in trajectory:
                page.mouse.move(start_x + point["x"], start_y + point["y"])
                time.sleep(point["dt"] / 1000.0)

            # 释放
            time.sleep(random.uniform(0.01, 0.06))
            page.mouse.up()

            # 等待验证结果
            time.sleep(random.uniform(1.0, 2.0))

            return self._check_solved(page)

        except Exception as e:
            logger.warning(f"滑块拖动异常: {e}")
            return False

    def _check_solved(self, page) -> bool:
        """检查滑块是否通过（同步版）"""
        try:
            success_selectors = [".nc-lang-cnt.nc_done", "#nc_1__success", ".nc_ok"]
            for sel in success_selectors:
                elem = page.query_selector(sel)
                if elem:
                    logger.info("滑块验证通过!")
                    return True

            error_selectors = [".nc-lang-cnt.nc_fail", "#nc_1__error", ".errloading"]
            for sel in error_selectors:
                elem = page.query_selector(sel)
                if elem and elem.is_visible():
                    return False

            # 滑块消失 = 通过
            for sel in self.SLIDER_BUTTON_SELECTORS:
                elem = page.query_selector(sel)
                if elem and elem.is_visible():
                    return False

            logger.info("滑块已消失，可能验证通过")
            return True

        except Exception as e:
            logger.debug(f"检查滑块状态异常: {e}")
            return False

    def solve(self, page, max_retries: int = 5) -> bool:
        """自动检测并求解滑块验证码（同步版）"""
        self._attempt_count = 0

        for attempt in range(max_retries):
            if not self.detect_slider(page):
                if attempt == 0:
                    logger.debug("未检测到滑块验证码")
                else:
                    logger.info("滑块已消失，验证可能已通过")
                return True

            slider_btn, slider_track, target = self._find_slider_elements(page)
            if not slider_btn:
                logger.warning(f"第 {attempt + 1} 次: 检测到滑块但无法定位按钮")
                time.sleep(2)
                continue

            solved = self._slide_once(page, slider_btn, slider_track)
            if solved:
                return True

            wait = random.uniform(2, 4)
            logger.info(f"等待 {wait:.1f}s 后重试...")
            time.sleep(wait)

            # 尝试刷新验证码
            try:
                for sel in [".nc-lang-cnt .errloading a", "#nc_1__refresh", ".errloading"]:
                    elem = page.query_selector(sel)
                    if elem and elem.is_visible():
                        elem.click()
                        time.sleep(1.5)
                        break
            except Exception:
                pass

        logger.warning(f"滑块求解失败，已尝试 {max_retries} 次")
        return False
