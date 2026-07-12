"""
browser-use 只读适配层。

该依赖默认不安装。即使以后在隔离环境安装，也只允许导航、搜索、滚动、
提取和截图；点击、输入、上传、下拉选择、Cookie 与文件写入动作会在工具层排除。
登录、提交表单、购买、预订、发布和删除必须由用户在可见页面中手动完成。
"""

import asyncio
import logging
from typing import Any

logger = logging.getLogger(__name__)

_browser_use_available = False
BrowserAgent = Browser = BrowserConfig = BrowserTools = None
try:
    from browser_use import Agent as BrowserAgent
    from browser_use import Browser
    from browser_use import Tools as BrowserTools

    try:
        from browser_use import BrowserConfig
    except ImportError:
        BrowserConfig = None
    _browser_use_available = True
except ImportError:
    logger.info("[BrowserUseBridge] browser-use 未安装，只读代理不可用")

# browser-use 官方 Tools(exclude_actions=...) 支持按动作名硬排除。
# 只保留 search/navigate/scroll/switch/close/extract/screenshot/find/done 等只读动作。
_READ_ONLY_EXCLUDED_ACTIONS = (
    "click",
    "input",
    "upload",
    "dropdown",
    "cookies",
    "read_file",
    "write_file",
    "replace_file",
)
_EXTERNAL_WRITE_TERMS = (
    "提交",
    "付款",
    "支付",
    "购买",
    "下单",
    "预订",
    "发布",
    "发送",
    "删除",
    "登录",
    "注册",
    "关注",
    "评论",
    "私信",
    "submit",
    "purchase",
    "checkout",
    "book",
    "publish",
    "send",
    "delete",
    "login",
    "sign in",
    "sign up",
)


def _contains_external_write_intent(task: str) -> bool:
    normalized = task.casefold()
    return any(term in normalized for term in _EXTERNAL_WRITE_TERMS)


class BrowserUseBridge:
    """只读 browser-use 桥接；不提供外部写操作绕行入口。"""

    def __init__(self, llm: Any = None, headless: bool = True):
        self._llm = llm
        self._headless = headless
        self._browser = None
        self._using_browser_use = _browser_use_available

    async def _ensure_llm(self) -> Any:
        """仅接受调用方显式注入的受控 LLM，不直接读取 Provider Key。"""
        if self._llm is None:
            logger.warning("[BrowserUseBridge] 未注入受控 LLM，拒绝启动浏览器代理")
        return self._llm

    def _create_browser(self) -> Any:
        """兼容旧版 BrowserConfig 与新版 Browser(headless=...) 初始化。"""
        if Browser is None:
            raise RuntimeError("browser-use Browser 不可用")
        if BrowserConfig is not None:
            return Browser(config=BrowserConfig(headless=self._headless, verbose=False))
        return Browser(headless=self._headless)

    async def run_task(self, task: str, url: str = "", max_steps: int = 10) -> dict[str, Any]:
        """执行受工具层约束的只读网页任务。"""
        if _contains_external_write_intent(task):
            return {
                "success": False,
                "blocked": True,
                "error": "external_write_requires_manual_action",
                "requires_manual_action": True,
            }
        if not self._using_browser_use or BrowserAgent is None or BrowserTools is None:
            return {
                "success": False,
                "error": "browser-use 未安装或缺少 Tools 动作闸门",
                "fallback": "使用项目现有只读 Playwright/HTTP 提取路径",
            }

        llm = await self._ensure_llm()
        if llm is None:
            return {"success": False, "error": "未注入受控 LLM"}

        browser = None
        try:
            browser = self._create_browser()
            tools = BrowserTools(exclude_actions=list(_READ_ONLY_EXCLUDED_ACTIONS))
            read_only_task = (
                "只读任务：只能导航、搜索、滚动、提取或截图；"
                "不得点击、输入、上传、读取 Cookie、本地文件或提交任何更改。\n"
                f"目标：{task}"
            )
            if url:
                read_only_task = f"先导航到 {url}。\n{read_only_task}"
            agent = BrowserAgent(
                task=read_only_task,
                llm=llm,
                browser=browser,
                tools=tools,
                max_actions_per_step=1,
            )
            result = await asyncio.wait_for(agent.run(max_steps=max_steps), timeout=120)
            return {
                "success": True,
                "result": str(result)[:10000],
                "steps": max_steps,
                "engine": "browser-use-read-only",
                "read_only": True,
            }
        except TimeoutError:
            logger.warning("[BrowserUseBridge] 只读任务超时(120s)")
            return {"success": False, "error": "浏览器只读任务超时(120秒)"}
        except Exception as exc:
            logger.warning("[BrowserUseBridge] 只读任务失败: %s", type(exc).__name__)
            return {"success": False, "error": "browser_read_only_failed"}
        finally:
            if browser is not None:
                try:
                    await browser.close()
                except Exception:
                    logger.debug("关闭 browser-use 实例失败", exc_info=True)

    async def extract_data(
        self,
        url: str,
        instruction: str,
        schema: dict | None = None,
    ) -> dict[str, Any]:
        """只读提取结构化网页数据。"""
        schema_hint = ""
        if schema:
            import json

            schema_hint = f"\n输出格式: {json.dumps(schema, ensure_ascii=False)}"
        return await self.run_task(
            f"提取以下信息并返回 JSON：{instruction}{schema_hint}",
            url=url,
            max_steps=8,
        )

    async def take_screenshot(self, url: str) -> dict[str, Any]:
        """通过只读代理获取截图描述；原始截图交给专用 Playwright 路径。"""
        return await self.run_task("截取当前页面并描述页面标题", url=url, max_steps=4)

    async def fill_form(self, url: str, form_data: dict[str, str]) -> dict[str, Any]:
        """保留兼容入口，但永不自动填写或提交表单。"""
        return {
            "success": False,
            "blocked": True,
            "error": "form_write_requires_manual_action",
            "requires_manual_action": True,
            "field_count": len(form_data),
            "url_supplied": bool(url),
        }

    def get_stats(self) -> dict[str, Any]:
        return {
            "available": _browser_use_available,
            "using_browser_use": self._using_browser_use,
            "mode": "read_only",
            "action_guard": BrowserTools is not None,
            "headless": self._headless,
            "has_llm": self._llm is not None,
        }

    async def close(self) -> None:
        if self._browser is not None:
            try:
                await self._browser.close()
            except Exception:
                logger.debug("关闭 browser-use 全局实例失败", exc_info=True)
            self._browser = None


_bridge: BrowserUseBridge | None = None


def init_browser_use(llm: Any = None, headless: bool = True) -> BrowserUseBridge:
    global _bridge
    _bridge = BrowserUseBridge(llm=llm, headless=headless)
    logger.info(
        "[BrowserUseBridge] 初始化完成 (available=%s, mode=read_only)",
        _browser_use_available,
    )
    return _bridge


def get_browser_use() -> BrowserUseBridge | None:
    """获取只读 bridge；未注入 LLM 时保持不可执行状态。"""
    global _bridge
    if _bridge is None:
        _bridge = init_browser_use(headless=True)
    return _bridge
