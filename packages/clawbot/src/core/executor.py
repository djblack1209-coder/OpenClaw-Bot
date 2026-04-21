"""
OpenClaw OMEGA — 多路径执行引擎 (Executor)
按优先级尝试: API直连 → 浏览器自动化 → AI电话 → Composio外部服务 → 人工通知。

设计原则:
  1. 每个路径独立，一个失败不影响其他
  2. 内置熔断机制（连续失败自动跳过）
  3. 执行结果统一数据结构
  4. 所有执行记录到审计日志
"""
import asyncio
import logging
import os
import time
import warnings
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import httpx
from src.utils import now_et, scrub_secrets

logger = logging.getLogger(__name__)


# ── 数据结构 ──────────────────────────────────────────

@dataclass
class ExecutionResult:
    """执行结果"""
    success: bool = False
    data: Any = None
    execution_path: str = ""    # api / browser / voice_call / composio / skyvern / human
    elapsed_seconds: float = 0.0
    cost_usd: float = 0.0
    error: Optional[str] = None
    attempts: List[Dict] = field(default_factory=list)

    def to_dict(self) -> Dict:
        return {
            "success": self.success,
            "path": self.execution_path,
            "elapsed": round(self.elapsed_seconds, 2),
            "cost_usd": round(self.cost_usd, 4),
            "error": self.error,
            "attempts": len(self.attempts),
        }


# ── 平台注册表 ──────────────────────────────────────────

PLATFORM_REGISTRY: Dict[str, Dict] = {
    "dianping": {"browser_url": "https://www.dianping.com", "phone": True},
    "meituan": {"browser_url": "https://www.meituan.com", "phone": True},
    "jd": {"browser_url": "https://www.jd.com"},
    "taobao": {"browser_url": "https://www.taobao.com"},
    "pdd": {"browser_url": "https://www.pinduoduo.com"},
    "smzdm": {"api": "https://www.smzdm.com/rss", "browser_url": "https://www.smzdm.com"},
    "xianyu": {"browser_url": "https://www.goofish.com"},
    "composio": {"composio": True},  # 250+ 外部服务 (Gmail/Calendar/Slack/GitHub 等)
}


# ── 熔断器 ──────────────────────────────────────────

class PlatformCircuitBreaker:
    """平台级熔断器 — 连续失败后暂时跳过"""

    def __init__(self, failure_threshold: int = 3, recovery_seconds: int = 300):
        self._failure_threshold = failure_threshold
        self._recovery_seconds = recovery_seconds
        self._failures: Dict[str, int] = defaultdict(int)
        self._tripped_at: Dict[str, float] = {}

    def record_failure(self, platform: str) -> None:
        self._failures[platform] += 1
        if self._failures[platform] >= self._failure_threshold:
            self._tripped_at[platform] = time.time()
            logger.warning(f"熔断器触发: {platform} (连续 {self._failures[platform]} 次失败)")

    def record_success(self, platform: str) -> None:
        self._failures[platform] = 0
        self._tripped_at.pop(platform, None)

    def is_available(self, platform: str) -> bool:
        if platform not in self._tripped_at:
            return True
        elapsed = time.time() - self._tripped_at[platform]
        if elapsed > self._recovery_seconds:
            self._failures[platform] = 0
            self._tripped_at.pop(platform, None)
            logger.info(f"熔断器恢复: {platform}")
            return True
        return False

    def get_status(self) -> Dict:
        return {
            "failures": dict(self._failures),
            "tripped": {
                k: f"剩余 {self._recovery_seconds - (time.time() - v):.0f}s"
                for k, v in self._tripped_at.items()
            },
        }


# ── 多路径执行引擎 ──────────────────────────────────────

class MultiPathExecutor:
    """
    多路径执行引擎。

    对于每个任务，按优先级尝试不同执行路径:
      1. API 直连（httpx）
      2. 浏览器自动化（Playwright / DrissionPage）
      3. AI 语音电话（Retell / Twilio）
      4. Composio 外部服务（250+ 应用: Gmail/Calendar/Slack/GitHub 等）
      5. Skyvern 视觉 RPA（截图 + LLM 理解页面，无需 selector）
      6. 通知用户人工处理

    用法:
        executor = MultiPathExecutor()
        result = await executor.execute_with_fallback([
            {"type": "api", "endpoint": "...", "params": {...}},
            {"type": "browser", "url": "...", "actions": [...]},
            {"type": "composio", "action": "GMAIL_SEND_EMAIL", "params": {...}},
            {"type": "skyvern", "url": "...", "goal": "...", "max_steps": 10},
            {"type": "voice_call", "phone": "...", "objective": "..."},
        ])
    """

    def __init__(self):
        self._circuit_breaker = PlatformCircuitBreaker()
        # 懒初始化 httpx 客户端，首次使用时创建，避免未关闭导致 TCP 连接泄漏 (HI-159/160)
        self._http_client: Optional[httpx.AsyncClient] = None
        self._closed = False
        self._stats = defaultdict(int)
        logger.info("MultiPathExecutor 初始化完成")

    def _get_http_client(self) -> httpx.AsyncClient:
        """获取 httpx 客户端，首次调用时懒创建"""
        if self._closed:
            raise RuntimeError("MultiPathExecutor 已关闭，不能再发送请求")
        if self._http_client is None or self._http_client.is_closed:
            self._http_client = httpx.AsyncClient(
                timeout=30.0, follow_redirects=True
            )
        return self._http_client

    async def close(self):
        """关闭 HTTP 客户端，释放 TCP 连接。幂等操作，可安全多次调用。"""
        if self._http_client is not None and not self._http_client.is_closed:
            await self._http_client.aclose()
            logger.debug("MultiPathExecutor: httpx 客户端已关闭")
        self._http_client = None
        self._closed = True

    async def __aenter__(self):
        """支持 async with 上下文管理器用法"""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """退出上下文时自动关闭客户端"""
        await self.close()
        return False

    def __del__(self):
        """析构时检查是否有未关闭的客户端，发出警告"""
        if self._http_client is not None and not self._http_client.is_closed:
            warnings.warn(
                "MultiPathExecutor 被垃圾回收但 httpx 客户端未关闭，"
                "可能导致 TCP 连接泄漏。请调用 await executor.close() 或使用 "
                "async with 管理生命周期。(HI-159/160)",
                ResourceWarning,
                stacklevel=2,
            )

    async def execute_with_fallback(
        self, strategies: List[Dict], platform: str = "unknown"
    ) -> ExecutionResult:
        """
        按顺序尝试多个执行策略。

        Args:
            strategies: 执行策略列表，如 [{"type": "api", ...}, {"type": "browser", ...}]
            platform: 平台名称（用于熔断器）

        Returns:
            ExecutionResult
        """
        result = ExecutionResult()
        start = time.time()

        for strategy in strategies:
            exec_type = strategy.get("type", "unknown")

            # 熔断器检查
            breaker_key = f"{platform}:{exec_type}"
            if not self._circuit_breaker.is_available(breaker_key):
                result.attempts.append({
                    "type": exec_type, "skipped": True, "reason": "熔断器已触发"
                })
                continue

            try:
                if exec_type == "api":
                    data = await self.execute_via_api(
                        strategy.get("endpoint", ""),
                        strategy.get("method", "GET"),
                        strategy.get("params", {}),
                        strategy.get("headers", {}),
                    )
                elif exec_type == "browser":
                    data = await self.execute_via_browser(
                        strategy.get("url", ""),
                        strategy.get("actions", []),
                    )
                elif exec_type == "voice_call":
                    data = await self.execute_via_voice_call(
                        strategy.get("phone", ""),
                        strategy.get("objective", ""),
                        strategy.get("script_hints", ""),
                    )
                elif exec_type == "human":
                    await self.fallback_to_human(
                        strategy.get("description", "需要人工处理"),
                        strategy,
                    )
                    data = {"action": "human_notified"}
                elif exec_type == "composio":
                    data = await self.execute_via_composio(
                        strategy.get("action", ""),
                        strategy.get("params", {}),
                        strategy.get("entity_id"),
                        strategy.get("connected_account_id"),
                    )
                elif exec_type == "skyvern":
                    data = await self.execute_via_skyvern(
                        strategy.get("url", ""),
                        strategy.get("goal", ""),
                        strategy.get("max_steps", 10),
                        strategy.get("data_extraction_schema"),
                    )
                else:
                    continue

                result.success = True
                result.data = data
                result.execution_path = exec_type
                self._circuit_breaker.record_success(breaker_key)
                self._stats[f"{exec_type}_success"] += 1
                result.attempts.append({"type": exec_type, "success": True})
                break

            except Exception as e:
                self._circuit_breaker.record_failure(breaker_key)
                self._stats[f"{exec_type}_failure"] += 1
                result.attempts.append({
                    "type": exec_type, "success": False, "error": str(e)
                })
                logger.warning(f"执行路径 {exec_type} 失败: {scrub_secrets(str(e))}")

        result.elapsed_seconds = time.time() - start
        if not result.success:
            result.error = "所有执行路径均失败"
        return result

    async def execute_via_api(
        self,
        endpoint: str,
        method: str = "GET",
        params: Optional[Dict] = None,
        headers: Optional[Dict] = None,
    ) -> Any:
        """API 直连 — 最优先的执行路径"""
        if not endpoint:
            raise ValueError("API endpoint 为空")

        # SSRF 防护：对外部 URL 做安全检查（阻止访问内网/元数据服务）
        from src.core.security import check_ssrf
        if not check_ssrf(endpoint):
            raise ValueError(f"API endpoint SSRF 检查未通过: {endpoint[:100]}")

        headers = headers or {}
        params = params or {}
        client = self._get_http_client()

        if method.upper() == "GET":
            resp = await client.get(endpoint, params=params, headers=headers)
        elif method.upper() == "POST":
            resp = await client.post(endpoint, json=params, headers=headers)
        else:
            resp = await client.request(method, endpoint, json=params, headers=headers)

        resp.raise_for_status()

        content_type = resp.headers.get("content-type", "")
        if "json" in content_type:
            return resp.json()
        return resp.text

    async def execute_via_browser(
        self, url: str, actions: List[Dict]
    ) -> Any:
        """浏览器自动化 — API不可用时的备选"""
        if not url:
            raise ValueError("URL 为空")

        # SSRF 防护：阻止浏览器访问内网地址
        from src.core.security import check_ssrf
        if not check_ssrf(url):
            raise ValueError(f"浏览器目标 URL SSRF 检查未通过: {url[:100]}")

        # 尝试 Playwright
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            # 降级到 DrissionPage
            try:
                return await self._execute_via_drission(url, actions)
            except ImportError:
                raise RuntimeError("Playwright 和 DrissionPage 均未安装")

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()

            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=30000)

                results = []
                for action in actions:
                    act_type = action.get("type", "")
                    if act_type == "click":
                        await page.click(action["selector"])
                    elif act_type == "fill":
                        await page.fill(action["selector"], action["value"])
                    elif act_type == "wait":
                        await page.wait_for_selector(
                            action.get("selector", "body"),
                            timeout=action.get("timeout", 10000),
                        )
                    elif act_type == "extract":
                        text = await page.text_content(action["selector"])
                        results.append(text)
                    elif act_type == "screenshot":
                        screenshot = await page.screenshot()
                        results.append({"screenshot": len(screenshot)})

                content = await page.content()
                return {
                    "url": url,
                    "title": await page.title(),
                    "content_length": len(content),
                    "action_results": results,
                }
            finally:
                await browser.close()

    async def _execute_via_drission(self, url: str, actions: List[Dict]) -> Any:
        """DrissionPage 备选浏览器（反检测更好）"""
        from DrissionPage import ChromiumPage

        def _run():
            page = ChromiumPage()
            page.get(url)
            title = page.title
            text = page.html[:5000]
            page.quit()
            return {"url": url, "title": title, "content_preview": text[:500]}

        return await asyncio.to_thread(_run)

    async def execute_via_voice_call(
        self,
        phone: str,
        objective: str,
        script_hints: str = "",
    ) -> Dict:
        """AI 语音拨号 — 只有电话渠道时的最后手段"""
        if not phone:
            raise ValueError("电话号码为空")

        # 尝试 Retell AI
        try:
            import retell
            client = retell.Retell(api_key=os.environ.get("RETELL_API_KEY", ""))
            call = client.call.create(
                from_number=os.environ.get("RETELL_FROM_NUMBER", ""),
                to_number=phone,
            )
            return {
                "call_id": call.call_id,
                "status": "initiated",
                "objective": objective,
            }
        except ImportError:
            logger.info("Retell AI 未安装，尝试 Twilio")
        except Exception as e:
            logger.warning(f"Retell 拨号失败: {scrub_secrets(str(e))}")

        # 降级到 Twilio
        try:
            from twilio.rest import Client
            client = Client(
                os.environ.get("TWILIO_ACCOUNT_SID", ""),
                os.environ.get("TWILIO_AUTH_TOKEN", ""),
            )
            call = client.calls.create(
                to=phone,
                from_=os.environ.get("TWILIO_FROM_NUMBER", ""),
                # TwiML 应答 URL — 默认使用 Twilio 官方 demo，
                # 生产环境应配置 TWILIO_TWIML_URL 为自己的通知语音
                url=os.environ.get(
                    "TWILIO_TWIML_URL",
                    "https://demo.twilio.com/docs/voice.xml",
                ),
            )
            return {"call_sid": call.sid, "status": "initiated"}
        except ImportError:
            raise RuntimeError("Retell AI 和 Twilio 均未安装")
        except Exception as e:
            raise RuntimeError(f"电话拨号失败: {e}")

    async def execute_via_composio(
        self,
        action: str,
        params: Optional[Dict] = None,
        entity_id: Optional[str] = None,
        connected_account_id: Optional[str] = None,
    ) -> Any:
        """Composio 外部服务 — 250+ 应用集成 (Gmail/Calendar/Slack/GitHub 等)"""
        if not action:
            raise ValueError("Composio action 为空")

        try:
            from src.integrations.composio_bridge import get_composio_bridge
        except ImportError:
            raise RuntimeError("composio_bridge 模块不可用")

        bridge = get_composio_bridge()
        if not bridge.is_available():
            raise RuntimeError("Composio 不可用 (SDK 未安装或 API Key 未设置)")

        # ComposioToolSet.execute_action 是同步方法，放到线程池避免阻塞事件循环
        result = await asyncio.to_thread(
            bridge.execute_action,
            action,
            params or {},
            entity_id,
            connected_account_id,
        )

        if not result.get("success"):
            raise RuntimeError(f"Composio 执行失败: {result.get('error', 'unknown')}")

        return result.get("data")

    async def execute_via_skyvern(
        self,
        url: str,
        goal: str,
        max_steps: int = 10,
        data_extraction_schema: Optional[Dict] = None,
    ) -> Any:
        """Skyvern 视觉 RPA — 通过截图 + LLM 理解页面，无需 CSS selector"""
        if not url:
            raise ValueError("URL 为空")
        if not goal:
            raise ValueError("goal 为空")

        # SSRF 防护：阻止 Skyvern 访问内网地址
        from src.core.security import check_ssrf
        if not check_ssrf(url):
            raise ValueError(f"Skyvern 目标 URL SSRF 检查未通过: {url[:100]}")

        try:
            from src.integrations.skyvern_bridge import get_skyvern_bridge
        except ImportError:
            raise RuntimeError("skyvern_bridge 模块不可用")

        bridge = get_skyvern_bridge()
        if not bridge.is_available():
            raise RuntimeError("Skyvern 不可用 (SDK 未安装或 API Key 未设置)")

        result = await bridge.run_task(
            url=url,
            goal=goal,
            max_steps=max_steps,
            data_extraction_schema=data_extraction_schema,
        )

        if not result.get("success"):
            raise RuntimeError(f"Skyvern 执行失败: {result.get('error', 'unknown')}")

        return result.get("data")

    async def fallback_to_human(
        self, task_description: str, context: Dict
    ) -> None:
        """通知用户需要人工处理"""
        try:
            from src.core.event_bus import get_event_bus, EventType
            bus = get_event_bus()
            await bus.publish(
                EventType.HUMAN_REQUIRED,
                {
                    "description": task_description,
                    "context_keys": list(context.keys()),
                    "timestamp": now_et().isoformat(),
                },
                source="executor",
            )
        except Exception as e:
            logger.warning(f"人工通知推送失败: {scrub_secrets(str(e))}")

    def get_stats(self) -> Dict:
        """获取执行统计"""
        return {
            "execution_stats": dict(self._stats),
            "circuit_breaker": self._circuit_breaker.get_status(),
        }


# ── 全局单例 ──────────────────────────────────────────────

_executor: Optional[MultiPathExecutor] = None


def get_executor() -> MultiPathExecutor:
    global _executor
    if _executor is None or _executor._closed:
        _executor = MultiPathExecutor()
    return _executor


async def close_executor() -> None:
    """关闭全局 executor 单例，释放 httpx 连接。应在应用退出时调用。"""
    global _executor
    if _executor is not None:
        await _executor.close()
        _executor = None
        logger.info("全局 MultiPathExecutor 已关闭")
