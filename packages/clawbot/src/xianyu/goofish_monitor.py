"""
闲鱼竞品监控集成层 — 搬运自 ai-goofish-monitor (9.7k⭐)

功能：
- 竞品价格追踪 + 市场趋势分析（你的闲鱼模块缺的核心能力）
- 多账号管理 + 代理轮换（提升稳定性）
- AI 多模态商品分析（图片+文字）
- 与现有 XianyuLive（WebSocket 客服）互补，不替换

架构：
  XianyuLive（你的）→ 实时消息 + AI客服 + 订单
  GoofishMonitor（本模块）→ 竞品监控 + 市场分析 + 多账号

集成方式：
  1. Docker 部署 ai-goofish-monitor（独立服务，端口 8000）
  2. 本模块通过 HTTP API 与其交互
  3. 监控结果推送到 Telegram + 写入 SharedMemory
"""
import logging
import os
import asyncio
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# ai-goofish-monitor 默认地址
MONITOR_BASE_URL = os.getenv("GOOFISH_MONITOR_URL", "http://localhost:8000")
MONITOR_USER = os.getenv("GOOFISH_MONITOR_USER", "admin")
# 安全修复: 移除硬编码默认密码，未配置时为空字符串（强制用户通过环境变量设置）
MONITOR_PASS = os.getenv("GOOFISH_MONITOR_PASS", "")


@dataclass
class MonitorTask:
    """监控任务定义"""
    name: str
    keywords: List[str]
    min_price: float = 0
    max_price: float = 99999
    ai_prompt: str = ""
    interval_minutes: int = 30
    account_id: Optional[str] = None
    enabled: bool = True


@dataclass
class MonitorResult:
    """监控结果"""
    task_name: str
    item_id: str
    title: str
    price: float
    seller: str
    ai_analysis: str = ""
    images: List[str] = field(default_factory=list)
    url: str = ""
    found_at: str = ""


class GoofishMonitor:
    """
    ai-goofish-monitor 集成客户端

    通过 HTTP API 与独立部署的 ai-goofish-monitor 服务交互。
    搬运其核心能力：竞品监控、AI分析、多账号管理。
    """

    def __init__(self, base_url: str = MONITOR_BASE_URL):
        self.base_url = base_url.rstrip("/")
        self._session = None
        self._authenticated = False

    async def _get_session(self):
        if self._session is None:
            try:
                import httpx
                self._session = httpx.AsyncClient(timeout=30.0)
            except ImportError:
                logger.error("[GoofishMonitor] httpx 未安装")
                return None
        return self._session

    async def close(self):
        """关闭 httpx 会话，防止连接泄漏"""
        if self._session:
            await self._session.aclose()
            self._session = None

    async def authenticate(self) -> bool:
        """登录 ai-goofish-monitor Web UI"""
        session = await self._get_session()
        if not session:
            return False
        try:
            resp = await session.post(
                f"{self.base_url}/auth/status",
                json={"username": MONITOR_USER, "password": MONITOR_PASS},
            )
            if resp.status_code == 200:
                self._authenticated = True
                logger.info("[GoofishMonitor] 认证成功")
                return True
            logger.warning("[GoofishMonitor] 认证失败: %s", resp.status_code)
        except Exception as e:
            logger.warning("[GoofishMonitor] 连接失败: %s", e)
        return False

    async def create_task(self, task: MonitorTask) -> Optional[Dict]:
        """创建监控任务"""
        if not self._authenticated:
            await self.authenticate()
        session = await self._get_session()
        if not session:
            return None
        try:
            payload = {
                "name": task.name,
                "keywords": task.keywords,
                "min_price": task.min_price,
                "max_price": task.max_price,
                "interval_minutes": task.interval_minutes,
                "enabled": task.enabled,
            }
            if task.ai_prompt:
                payload["ai_prompt"] = task.ai_prompt
            if task.account_id:
                payload["account_id"] = task.account_id

            resp = await session.post(
                f"{self.base_url}/api/tasks/generate",
                json=payload,
            )
            if resp.status_code in (200, 201, 202):
                data = resp.json()
                logger.info("[GoofishMonitor] 任务创建成功: %s", task.name)
                return data
            logger.warning("[GoofishMonitor] 创建任务失败: %s %s", resp.status_code, resp.text[:200])
        except Exception as e:
            logger.warning("[GoofishMonitor] 创建任务异常: %s", e)
        return None

    async def get_tasks(self) -> List[Dict]:
        """获取所有监控任务"""
        if not self._authenticated:
            await self.authenticate()
        session = await self._get_session()
        if not session:
            return []
        try:
            resp = await session.get(f"{self.base_url}/api/tasks")
            if resp.status_code == 200:
                return resp.json()
        except Exception as e:
            logger.warning("[GoofishMonitor] 获取任务列表失败: %s", e)
        return []

    async def get_results(self, task_id: str = "", limit: int = 20) -> List[Dict]:
        """获取监控结果"""
        if not self._authenticated:
            await self.authenticate()
        session = await self._get_session()
        if not session:
            return []
        try:
            url = f"{self.base_url}/api/results"
            params = {"limit": limit}
            if task_id:
                params["task_id"] = task_id
            resp = await session.get(url, params=params)
            if resp.status_code == 200:
                return resp.json()
        except Exception as e:
            logger.warning("[GoofishMonitor] 获取结果失败: %s", e)
        return []

    async def get_accounts(self) -> List[Dict]:
        """获取账号列表"""
        if not self._authenticated:
            await self.authenticate()
        session = await self._get_session()
        if not session:
            return []
        try:
            resp = await session.get(f"{self.base_url}/api/accounts")
            if resp.status_code == 200:
                return resp.json()
        except Exception as e:
            logger.warning("[GoofishMonitor] 获取账号列表失败: %s", e)
        return []

    async def health_check(self) -> Dict[str, Any]:
        """检查 ai-goofish-monitor 服务状态"""
        session = await self._get_session()
        if not session:
            return {"status": "error", "message": "httpx 未安装"}
        try:
            resp = await session.get(f"{self.base_url}/docs", timeout=5.0)
            return {
                "status": "ok" if resp.status_code == 200 else "error",
                "code": resp.status_code,
                "url": self.base_url,
            }
        except Exception as e:
            return {"status": "offline", "message": str(e), "url": self.base_url}


class XianyuMonitorBridge:
    """
    桥接层：将 ai-goofish-monitor 的监控结果接入 ClawBot 生态

    功能：
    - 定期拉取监控结果 → 写入 SharedMemory
    - 竞品价格变动 → 推送 Telegram 通知
    - 市场趋势分析 → 注入到闲鱼客服的定价策略
    """

    def __init__(self, monitor: GoofishMonitor, shared_memory=None, notify_fn=None):
        """
        Args:
            monitor: GoofishMonitor 实例
            shared_memory: SharedMemory 实例（写入监控结果）
            notify_fn: async (text: str) -> None，Telegram 通知函数
        """
        self.monitor = monitor
        self.memory = shared_memory
        self.notify_fn = notify_fn
        self._last_check: Dict[str, str] = {}  # task_id -> last_result_id
        self._running = False

    async def start_polling(self, interval_seconds: int = 300):
        """启动定期轮询监控结果"""
        self._running = True
        logger.info("[XianyuMonitorBridge] 开始轮询监控结果 (间隔 %ds)", interval_seconds)
        while self._running:
            try:
                await self._poll_results()
            except Exception as e:
                logger.warning("[XianyuMonitorBridge] 轮询异常: %s", e)
            await asyncio.sleep(interval_seconds)

    def stop_polling(self):
        self._running = False

    async def _poll_results(self):
        """拉取新结果，写入记忆，推送通知"""
        results = await self.monitor.get_results(limit=10)
        new_count = 0

        for r in results:
            result_id = str(r.get("id", ""))
            task_name = r.get("task_name", "unknown")

            # 跳过已处理的结果
            if self._last_check.get(task_name) == result_id:
                continue

            self._last_check[task_name] = result_id
            new_count += 1

            # 写入 SharedMemory
            if self.memory:
                title = r.get("title", "")[:80]
                price = r.get("price", 0)
                analysis = r.get("ai_analysis", "")[:300]
                self.memory.remember(
                    key=f"xianyu_monitor_{task_name}_{result_id}",
                    value=f"商品: {title} | 价格: ¥{price} | AI分析: {analysis}",
                    category="xianyu_monitor",
                    source_bot="goofish_monitor",
                    importance=2,
                    ttl_hours=24 * 7,
                )

            # 推送 Telegram 通知
            if self.notify_fn and r.get("ai_analysis"):
                msg = (
                    f"🦞 闲鱼监控 [{task_name}]\n"
                    f"商品: {r.get('title', '')[:60]}\n"
                    f"价格: ¥{r.get('price', '?')}\n"
                    f"AI: {r.get('ai_analysis', '')[:200]}"
                )
                try:
                    await self.notify_fn(msg)
                except Exception as e:
                    logger.debug("Silenced exception", exc_info=True)

        if new_count:
            logger.info("[XianyuMonitorBridge] 处理了 %d 条新监控结果", new_count)

    async def get_market_insights(self, keyword: str) -> str:
        """获取市场洞察（供闲鱼客服定价参考）"""
        if not self.memory:
            return ""
        results = self.memory.search(f"xianyu_monitor {keyword}", limit=5)
        items = results.get("results", []) if isinstance(results, dict) else []
        if not items:
            return ""
        lines = [f"【闲鱼市场参考 - {keyword}】"]
        for item in items[:3]:
            lines.append(f"- {item.get('value', '')[:120]}")
        return "\n".join(lines)

    def get_stats(self) -> Dict[str, Any]:
        return {
            "monitor_url": self.monitor.base_url,
            "tracked_tasks": len(self._last_check),
            "polling": self._running,
        }


# ── 全局实例 ──

_monitor: Optional[GoofishMonitor] = None
_bridge: Optional[XianyuMonitorBridge] = None


def init_goofish_monitor(shared_memory=None, notify_fn=None) -> XianyuMonitorBridge:
    """初始化闲鱼竞品监控"""
    global _monitor, _bridge
    _monitor = GoofishMonitor()
    _bridge = XianyuMonitorBridge(_monitor, shared_memory, notify_fn)
    logger.info("[GoofishMonitor] 初始化完成 (服务地址: %s)", _monitor.base_url)
    return _bridge


def get_monitor() -> Optional[GoofishMonitor]:
    return _monitor


def get_bridge() -> Optional[XianyuMonitorBridge]:
    return _bridge
