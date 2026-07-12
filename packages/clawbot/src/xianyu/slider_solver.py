"""闲鱼验证码检测器。

本模块只负责识别页面是否出现滑块/验证码。检测到平台保护后立即停止，
不注入反检测脚本、不模拟轨迹、不自动拖动，必须由用户在可见浏览器中完成。
保留 ``SliderSolver`` / ``SliderSolverSync`` 名称是为了兼容旧调用方。
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


class SliderSolver:
    """异步验证码检测器；``solve`` 只做安全判断，不执行拖动。"""

    SLIDER_SELECTORS = [
        "#nc_1_n1z",
        "#nc_1__scale_text",
        ".nc-lang-cnt",
        "#nocaptcha",
        ".nc_wrapper",
        "#baxia-dialog-content",
        "iframe[src*='captcha']",
    ]
    SLIDER_BUTTON_SELECTORS = [
        "#nc_1_n1z",
        ".btn_slide",
        ".nc-lang-cnt .btn_slide",
        ".slider-btn",
    ]

    async def inject_stealth(self, page) -> None:
        """兼容旧接口；安全策略禁止注入反检测脚本。"""
        del page
        logger.info("验证码保护策略已启用：不注入反检测脚本")

    async def detect_slider(self, page) -> bool:
        """检测主页面和 iframe 中是否存在可见验证码。"""
        for selector in self.SLIDER_SELECTORS:
            try:
                element = await page.query_selector(selector)
                if element and await element.is_visible():
                    logger.warning("检测到平台验证码，需要用户手动完成: %s", selector)
                    return True
            except Exception:
                continue

        for frame in page.frames:
            try:
                for selector in self.SLIDER_BUTTON_SELECTORS:
                    element = await frame.query_selector(selector)
                    if element and await element.is_visible():
                        logger.warning("检测到 iframe 验证码，需要用户手动完成: %s", selector)
                        return True
            except Exception:
                continue
        return False

    async def solve(self, page, max_retries: int = 1) -> bool:
        """兼容旧接口：无验证码返回 True；有验证码安全停止并返回 False。"""
        del max_retries
        if await self.detect_slider(page):
            logger.warning("已停止自动化：请在可见浏览器中手动完成验证码")
            return False
        return True


def solve_slider_sync(page, max_retries: int = 1) -> bool:
    """同步兼容入口；不会自动拖动验证码。"""
    return SliderSolverSync().solve(page, max_retries=max_retries)


class SliderSolverSync:
    """同步验证码检测器；``solve`` 只做安全判断，不执行拖动。"""

    SLIDER_SELECTORS = SliderSolver.SLIDER_SELECTORS
    SLIDER_BUTTON_SELECTORS = SliderSolver.SLIDER_BUTTON_SELECTORS

    def detect_slider(self, page) -> bool:
        """检测主页面和 iframe 中是否存在可见验证码。"""
        for selector in self.SLIDER_SELECTORS:
            try:
                element = page.query_selector(selector)
                if element and element.is_visible():
                    logger.warning("检测到平台验证码，需要用户手动完成: %s", selector)
                    return True
            except Exception:
                continue

        for frame in page.frames:
            try:
                for selector in self.SLIDER_BUTTON_SELECTORS:
                    element = frame.query_selector(selector)
                    if element and element.is_visible():
                        logger.warning("检测到 iframe 验证码，需要用户手动完成: %s", selector)
                        return True
            except Exception:
                continue
        return False

    def solve(self, page, max_retries: int = 1) -> bool:
        """兼容旧接口：无验证码返回 True；有验证码安全停止并返回 False。"""
        del max_retries
        if self.detect_slider(page):
            logger.warning("已停止自动化：请在可见浏览器中手动完成验证码")
            return False
        return True
