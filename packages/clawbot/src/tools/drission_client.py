"""
DrissionPage 反爬级浏览器控制层
搬运 DrissionPage (11.6k⭐) — 比 Playwright 更难被反爬检测

核心优势：
- 不基于 WebDriver，无 navigator.webdriver 指纹
- 自研 CDP 内核，无需下载对应版本 chromedriver
- 跨 iframe 查找，无需 switch
- 内置自动重试和等待

适用场景：
- 闲鱼商品操作（反爬严格）
- 电商平台比价（需要登录态）
- 社交平台内容操作（需要真实浏览器环境）

pip install DrissionPage
"""
import logging
import time
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

# 持久化 session 的 profile 目录
_PROFILE_DIR = Path(__file__).parent.parent.parent / "data" / "browser_profiles" / "drission"


class DrissionBrowser:
    """反检测浏览器客户端 — 基于 DrissionPage (11.6k⭐)

    相比 Playwright/Selenium:
    - 不注入 webdriver 标记，反检测天然优势
    - 自研 CDP 协议，不依赖 chromedriver 版本
    - 支持 profile 持久化（登录态保持）

    用法::

        with DrissionBrowser(headless=True) as browser:
            browser.navigate("https://example.com")
            text = browser.get_text("h1")
            print(text)
    """

    def __init__(
        self,
        headless: bool = True,
        profile: str = "default",
        proxy: Optional[str] = None,
        user_agent: Optional[str] = None,
    ):
        """
        Args:
            headless: 无头模式（不显示浏览器窗口）
            profile: 浏览器 profile 名称，用于持久化 cookies / 登录态
            proxy: 代理地址，如 "http://127.0.0.1:7890"
            user_agent: 自定义 User-Agent
        """
        self._page = None
        self._headless = headless
        self._profile = profile
        self._proxy = proxy
        self._user_agent = user_agent
        self._profile_dir = _PROFILE_DIR / profile
        self._profile_dir.mkdir(parents=True, exist_ok=True)

    def _ensure_page(self):
        """懒初始化浏览器（首次调用时启动）"""
        if self._page is not None:
            return self._page
        try:
            from DrissionPage import ChromiumPage, ChromiumOptions
        except ImportError:
            raise ImportError(
                "DrissionPage 未安装。请运行: pip install DrissionPage"
            )

        co = ChromiumOptions()
        co.set_user_data_path(str(self._profile_dir))
        if self._headless:
            co.headless()

        # 反检测核心参数
        co.set_argument("--disable-blink-features", "AutomationControlled")
        co.set_argument("--no-sandbox")
        co.set_argument("--disable-infobars")
        co.set_argument("--disable-dev-shm-usage")

        if self._proxy:
            co.set_proxy(self._proxy)
        if self._user_agent:
            co.set_user_agent(self._user_agent)

        # 自动分配端口，避免与其他实例冲突
        co.auto_port()

        self._page = ChromiumPage(co)
        logger.info(
            "[DrissionBrowser] 浏览器已启动 headless=%s profile=%s",
            self._headless,
            self._profile,
        )
        return self._page

    # ── 导航 ──────────────────────────────────────────

    def navigate(self, url: str, wait: float = 2.0) -> str:
        """导航到 URL，返回页面 HTML。

        Args:
            url: 目标地址
            wait: 导航后额外等待秒数（等待动态内容加载）

        Returns:
            页面完整 HTML
        """
        page = self._ensure_page()
        page.get(url)
        if wait > 0:
            time.sleep(wait)
        return page.html

    # ── 元素交互 ──────────────────────────────────────

    def click(self, selector: str) -> bool:
        """点击元素。

        DrissionPage 定位语法:
        - CSS: "#id", ".class", "tag"
        - 文本: "@text()=登录", "text:登录"
        - XPath: "xpath://div[@class='btn']"

        Args:
            selector: DrissionPage 定位符

        Returns:
            是否点击成功
        """
        page = self._ensure_page()
        try:
            el = page.ele(selector)
            if el:
                el.click()
                return True
        except Exception as e:
            logger.debug("Click failed for %s: %s", selector, e)
        return False

    def type_text(self, selector: str, text: str, clear: bool = True) -> bool:
        """向输入框输入文本。

        Args:
            selector: 元素定位符
            text: 要输入的文本
            clear: 是否先清空输入框

        Returns:
            是否输入成功
        """
        page = self._ensure_page()
        try:
            el = page.ele(selector)
            if el:
                if clear:
                    el.clear()
                el.input(text)
                return True
        except Exception as e:
            logger.debug("Type failed for %s: %s", selector, e)
        return False

    def get_text(self, selector: Optional[str] = None) -> str:
        """获取元素文本或整个页面 HTML。

        Args:
            selector: 元素定位符，None 则返回整页 HTML

        Returns:
            元素文本或页面 HTML
        """
        page = self._ensure_page()
        if selector:
            try:
                el = page.ele(selector)
                return el.text if el else ""
            except Exception as e:  # noqa: F841
                return ""
        return page.html

    def get_attribute(self, selector: str, attr: str) -> Optional[str]:
        """获取元素属性值。

        Args:
            selector: 元素定位符
            attr: 属性名（如 "href", "src", "value"）

        Returns:
            属性值，找不到返回 None
        """
        page = self._ensure_page()
        try:
            el = page.ele(selector)
            if el:
                return el.attr(attr)
        except Exception as e:
            logger.debug("Silenced exception", exc_info=True)
        return None

    def find_elements(self, selector: str) -> list:
        """查找所有匹配的元素，返回文本列表。

        Args:
            selector: 元素定位符

        Returns:
            匹配元素的文本列表
        """
        page = self._ensure_page()
        try:
            elements = page.eles(selector)
            return [el.text for el in elements if el]
        except Exception as e:  # noqa: F841
            return []

    # ── 截图与调试 ─────────────────────────────────────

    def screenshot(self, path: Optional[str] = None, full_page: bool = False) -> str:
        """页面截图。

        Args:
            path: 保存路径，None 则自动生成
            full_page: 是否截取完整页面（含滚动区域）

        Returns:
            截图文件路径
        """
        page = self._ensure_page()
        if not path:
            save_dir = Path(__file__).parent.parent.parent / "data" / "screenshots"
            save_dir.mkdir(parents=True, exist_ok=True)
            path = str(save_dir / f"drission_{int(time.time())}.png")
        page.get_screenshot(path=path, full_page=full_page)
        return path

    # ── 会话管理 ──────────────────────────────────────

    def get_cookies(self, all_info: bool = False) -> list:
        """获取当前会话的所有 cookies。

        Args:
            all_info: 是否返回完整 cookie 信息（含 domain, path, expires 等）

        Returns:
            cookie 列表
        """
        page = self._ensure_page()
        return list(page.cookies(all_info=all_info))

    def get_url(self) -> str:
        """获取当前页面 URL。"""
        page = self._ensure_page()
        return page.url

    def get_title(self) -> str:
        """获取当前页面标题。"""
        page = self._ensure_page()
        return page.title

    # ── JS 执行 ───────────────────────────────────────

    def execute_js(self, script: str, *args) -> Any:
        """在浏览器上下文中执行 JavaScript。

        Args:
            script: JS 脚本（支持 return 语句）
            *args: 传递给脚本的参数

        Returns:
            JS 执行结果
        """
        page = self._ensure_page()
        return page.run_js(script, *args)

    # ── 生命周期 ──────────────────────────────────────

    def close(self):
        """关闭浏览器，释放资源。"""
        if self._page:
            try:
                self._page.quit()
            except Exception as e:
                logger.debug("Silenced exception", exc_info=True)
            self._page = None
            logger.info("[DrissionBrowser] 浏览器已关闭 profile=%s", self._profile)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def __repr__(self) -> str:
        status = "connected" if self._page else "idle"
        return f"<DrissionBrowser profile={self._profile!r} status={status}>"


# ═══════════════ 便捷函数 ═══════════════════════════════


def quick_scrape(
    url: str,
    selector: Optional[str] = None,
    headless: bool = True,
) -> str:
    """一行代码抓取 — 打开 URL，提取文本，自动关闭。

    Args:
        url: 目标地址
        selector: 元素定位符，None 则返回整页 HTML
        headless: 是否无头模式

    Returns:
        页面文本或 HTML

    用法::

        text = quick_scrape("https://example.com", "h1")
    """
    with DrissionBrowser(headless=headless) as browser:
        browser.navigate(url)
        return browser.get_text(selector)


async def async_scrape(
    url: str,
    selector: Optional[str] = None,
) -> str:
    """异步版本的 quick_scrape — 在线程池中运行，不阻塞事件循环。

    Args:
        url: 目标地址
        selector: 元素定位符

    Returns:
        页面文本或 HTML
    """
    import asyncio

    return await asyncio.to_thread(quick_scrape, url, selector, True)
