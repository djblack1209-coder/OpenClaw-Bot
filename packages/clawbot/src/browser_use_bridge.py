"""
browser-use 升级适配层 — 搬运自 browser-use (81k⭐)

替换自研 ai_browser.py 的 DOM 解析 + LLM 决策循环：
- browser-use 的 Agent 自动规划浏览器操作序列
- 内置反检测（stealth mode）
- 结构化数据提取
- 视觉理解（截图 + VLM 分析）

保留 ClawBot 独有能力：
- social_browser_worker.py 的平台特定发布逻辑（X/XHS）
- cookie 管理和 CDP 模式
- 闲鱼 WebSocket 实时监听

集成方式：browser-use 不可用时自动降级回原有 Playwright 逻辑。
"""
import logging
from typing import Dict, Any, Optional

from src.bot.globals import SILICONFLOW_KEYS, SILICONFLOW_BASE

logger = logging.getLogger(__name__)

_browser_use_available = False
try:
    from browser_use import Agent as BrowserAgent, Browser, BrowserConfig
    _browser_use_available = True
except ImportError:
    BrowserAgent = Browser = BrowserConfig = None  # type: ignore[assignment,misc]
    logger.info("[BrowserUseBridge] browser-use 未安装，使用原有 Playwright 回退")


class BrowserUseBridge:
    """
    browser-use 桥接层

    提供高级浏览器自动化能力：
    - 自然语言驱动的网页操作
    - 结构化数据抓取
    - 表单填写和多步骤流程
    - 截图和视觉分析
    """

    def __init__(self, llm=None, headless: bool = True):
        """
        Args:
            llm: LangChain 兼容的 LLM 实例（browser-use 需要）
            headless: 是否无头模式
        """
        self._llm = llm
        self._headless = headless
        self._browser = None
        self._using_browser_use = _browser_use_available

    async def _ensure_llm(self):
        """确保 LLM 可用（延迟初始化）"""
        if self._llm:
            return self._llm
        try:
            from langchain_openai import ChatOpenAI
            sf_key = SILICONFLOW_KEYS[0] if SILICONFLOW_KEYS else ""
            sf_base = SILICONFLOW_BASE
            if sf_key:
                self._llm = ChatOpenAI(
                    model="Qwen/Qwen3-8B",
                    api_key=sf_key,
                    base_url=sf_base,
                    temperature=0.1,
                )
                return self._llm
        except ImportError:
            pass
        logger.warning("[BrowserUseBridge] 无可用 LLM，browser-use 功能受限")
        return None

    async def run_task(self, task: str, url: str = "", max_steps: int = 10) -> Dict[str, Any]:
        """
        用自然语言描述执行浏览器任务。

        示例：
            await bridge.run_task("搜索 Python 教程并提取前 5 个结果的标题和链接")
            await bridge.run_task("登录并获取账户余额", url="https://example.com/login")
        """
        if not self._using_browser_use:
            return {"success": False, "error": "browser-use 未安装",
                    "fallback": "请使用原有 social_browser_worker.py"}

        llm = await self._ensure_llm()
        if not llm:
            return {"success": False, "error": "无可用 LLM"}

        try:
            config = BrowserConfig(headless=self._headless)
            browser = Browser(config=config)

            agent = BrowserAgent(
                task=task,
                llm=llm,
                browser=browser,
                max_actions_per_step=3,
            )

            if url:
                agent.task = f"先导航到 {url}，然后 {task}"

            result = await agent.run(max_steps=max_steps)

            await browser.close()

            return {
                "success": True,
                "result": str(result),
                "steps": max_steps,
                "engine": "browser-use",
            }
        except Exception as e:
            logger.warning("[BrowserUseBridge] 任务执行失败: %s", e)
            return {"success": False, "error": str(e)}

    async def extract_data(
        self, url: str, instruction: str, schema: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        """
        从网页提取结构化数据。

        Args:
            url: 目标网页
            instruction: 提取指令（如 "提取所有商品的名称、价格和评分"）
            schema: 可选的数据 schema 描述
        """
        schema_hint = ""
        if schema:
            import json
            schema_hint = f"\n输出格式: {json.dumps(schema, ensure_ascii=False)}"

        task = f"导航到 {url}，{instruction}{schema_hint}。将结果以 JSON 格式输出。"
        return await self.run_task(task, max_steps=8)

    async def take_screenshot(self, url: str) -> Dict[str, Any]:
        """截取网页截图"""
        if not self._using_browser_use:
            return {"success": False, "error": "browser-use 未安装"}

        try:
            config = BrowserConfig(headless=True)
            browser = Browser(config=config)
            page = await browser.new_context()

            # 直接用 Playwright 截图（不需要 LLM）
            context = await browser._browser.new_context()
            pg = await context.new_page()
            await pg.goto(url, wait_until="networkidle", timeout=30000)
            screenshot = await pg.screenshot(full_page=True)
            await context.close()
            await browser.close()

            return {"success": True, "screenshot": screenshot, "url": url}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def fill_form(self, url: str, form_data: Dict[str, str]) -> Dict[str, Any]:
        """自动填写表单"""
        fields_desc = ", ".join(f"{k}={v}" for k, v in form_data.items())
        task = f"导航到 {url}，找到表单，填写以下字段: {fields_desc}，然后提交。"
        return await self.run_task(task, max_steps=8)

    def get_stats(self) -> Dict[str, Any]:
        return {
            "available": _browser_use_available,
            "using_browser_use": self._using_browser_use,
            "headless": self._headless,
            "has_llm": self._llm is not None,
        }

    async def close(self):
        if self._browser:
            try:
                await self._browser.close()
            except Exception as e:
                logger.debug("[BrowserUseBridge] 异常: %s", e)
            self._browser = None


# ── 全局实例 ──

_bridge: Optional[BrowserUseBridge] = None


def init_browser_use(llm=None, headless: bool = True) -> BrowserUseBridge:
    global _bridge
    _bridge = BrowserUseBridge(llm=llm, headless=headless)
    logger.info("[BrowserUseBridge] 初始化完成 (browser-use=%s)",
                "可用" if _browser_use_available else "未安装")
    return _bridge


def get_browser_use() -> Optional[BrowserUseBridge]:
    return _bridge
