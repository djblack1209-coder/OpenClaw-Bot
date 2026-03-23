"""
OpenClaw OMEGA — 多路径执行引擎 (Executor)
按优先级尝试: API直连 → 浏览器自动化 → AI电话 → 人工通知。

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
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)


# ── 数据结构 ──────────────────────────────────────────

@dataclass
class ExecutionResult:
    """执行结果"""
    success: bool = False
    data: Any = None
    execution_path: str = ""    # api / browser / voice_call / human
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
      4. 通知用户人工处理

    用法:
        executor = MultiPathExecutor()
        result = await executor.execute_with_fallback([
            {"type": "api", "endpoint": "...", "params": {...}},
            {"type": "browser", "url": "...", "actions": [...]},
            {"type": "voice_call", "phone": "...", "objective": "..."},
        ])
    """

    def __init__(self):
        self._circuit_breaker = PlatformCircuitBreaker()
        self._http_client = httpx.AsyncClient(timeout=30.0, follow_redirects=True)
        self._stats = defaultdict(int)
        logger.info("MultiPathExecutor 初始化完成")

    async def close(self):
        """关闭 HTTP 客户端"""
        await self._http_client.aclose()

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
                logger.warning(f"执行路径 {exec_type} 失败: {e}")

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

        headers = headers or {}
        params = params or {}

        if method.upper() == "GET":
            resp = await self._http_client.get(endpoint, params=params, headers=headers)
        elif method.upper() == "POST":
            resp = await self._http_client.post(endpoint, json=params, headers=headers)
        else:
            resp = await self._http_client.request(method, endpoint, json=params, headers=headers)

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
            logger.warning(f"Retell 拨号失败: {e}")

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
                url="http://demo.twilio.com/docs/voice.xml",
            )
            return {"call_sid": call.sid, "status": "initiated"}
        except ImportError:
            raise RuntimeError("Retell AI 和 Twilio 均未安装")
        except Exception as e:
            raise RuntimeError(f"电话拨号失败: {e}")

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
                    "timestamp": datetime.now().isoformat(),
                },
                source="executor",
            )
        except Exception as e:
            logger.warning(f"人工通知推送失败: {e}")

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
    if _executor is None:
        _executor = MultiPathExecutor()
    return _executor
