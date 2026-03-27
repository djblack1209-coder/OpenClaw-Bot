"""
ClawBot - 监控增强 v1.0
- g4f 服务健康检查（端口 18891）
- AlertManager → Telegram 通知回调
- 系统资源监控（CPU/内存/磁盘）

参考: prometheus_client 的 platform_collector + psutil（如可用）
不强依赖 psutil，降级到 /proc 或 subprocess 读取。
"""
import asyncio
import logging
import os
import time
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)


# ============ g4f 健康检查 ============

async def check_g4f_health(
    host: str = "127.0.0.1",
    port: int = 18891,
    timeout: float = 5.0,
) -> Dict[str, Any]:
    """检查 g4f 服务是否存活
    
    返回: {"alive": bool, "latency_ms": float, "error": str|None}
    """
    try:
        import httpx
        start = time.time()
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(f"http://{host}:{port}/v1/models")
            latency = (time.time() - start) * 1000
            if resp.status_code == 200:
                return {"alive": True, "latency_ms": round(latency, 1), "error": None}
            return {"alive": False, "latency_ms": round(latency, 1),
                    "error": f"HTTP {resp.status_code}"}
    except Exception as e:
        return {"alive": False, "latency_ms": -1, "error": str(e)}


# ============ Telegram 告警通知 ============

class TelegramAlertNotifier:
    """将 AlertManager 告警推送到 Telegram
    
    用法:
        notifier = TelegramAlertNotifier(bot_token="xxx", chat_id=123)
        alert_manager.on_alert(notifier.sync_callback)
    """

    def __init__(self, bot_token: str, chat_id: int, throttle_seconds: int = 60):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self._throttle = throttle_seconds
        self._last_sent: Dict[str, float] = {}
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    def sync_callback(self, rule_name: str, message: str):
        """同步回调 — 适配 AlertManager.on_alert() 的签名"""
        now = time.time()
        if now - self._last_sent.get(rule_name, 0) < self._throttle:
            return  # 限流
        self._last_sent[rule_name] = now

        # 在事件循环中异步发送
        try:
            loop = self._loop
            if loop is None:
                try:
                    loop = asyncio.get_running_loop()
                except RuntimeError as e:  # noqa: F841
                    loop = None
            if loop and loop.is_running():
                asyncio.ensure_future(self._send(rule_name, message))
            else:
                loop.run_until_complete(self._send(rule_name, message))
        except RuntimeError as e:  # noqa: F841
            # 没有事件循环，用线程发送
            import threading
            threading.Thread(
                target=self._send_sync, args=(rule_name, message), daemon=True
            ).start()

    async def _send(self, rule_name: str, message: str):
        try:
            import httpx
            text = f"⚠️ 告警: {rule_name}\n───────────────────\n{message}"
            async with httpx.AsyncClient(timeout=10) as client:
                await client.post(
                    f"https://api.telegram.org/bot{self.bot_token}/sendMessage",
                    json={"chat_id": self.chat_id, "text": text},
                )
        except Exception as e:
            logger.debug(f"[TelegramAlert] 发送失败: {e}")

    def _send_sync(self, rule_name: str, message: str):
        try:
            import httpx
            text = f"⚠️ 告警: {rule_name}\n───────────────────\n{message}"
            with httpx.Client(timeout=10) as client:
                client.post(
                    f"https://api.telegram.org/bot{self.bot_token}/sendMessage",
                    json={"chat_id": self.chat_id, "text": text},
                )
        except Exception as e:
            logger.debug(f"[TelegramAlert] 同步发送失败: {e}")


# ============ 系统资源监控 ============

def get_system_resources() -> Dict[str, Any]:
    """获取系统资源使用情况 — 不依赖 psutil，降级到系统命令"""
    result: Dict[str, Any] = {}

    # CPU 负载
    try:
        load = os.getloadavg()
        result["cpu_load_1m"] = round(load[0], 2)
        result["cpu_load_5m"] = round(load[1], 2)
        result["cpu_load_15m"] = round(load[2], 2)
    except (OSError, AttributeError) as e:  # noqa: F841
        result["cpu_load_1m"] = -1

    # 内存 — 尝试 psutil，降级到 sysctl (macOS) 或 /proc/meminfo (Linux)
    try:
        import psutil
        mem = psutil.virtual_memory()
        result["memory_total_gb"] = round(mem.total / (1024**3), 1)
        result["memory_used_gb"] = round(mem.used / (1024**3), 1)
        result["memory_percent"] = mem.percent
    except ImportError:
        try:
            import subprocess
            out = subprocess.check_output(["vm_stat"], text=True, timeout=5)
            # macOS vm_stat 粗略解析
            pages_free = 0
            pages_active = 0
            # 从 vm_stat 输出第一行解析实际 page size
            page_size = 16384  # fallback for ARM
            first_line = out.splitlines()[0] if out.splitlines() else ""
            if "page size of" in first_line:
                try:
                    page_size = int(first_line.split("page size of")[1].split("bytes")[0].strip())
                except (ValueError, IndexError) as e:  # noqa: F841
                    pass
            for line in out.splitlines():
                if "Pages free" in line:
                    pages_free = int(line.split(":")[1].strip().rstrip("."))
                elif "Pages active" in line:
                    pages_active = int(line.split(":")[1].strip().rstrip("."))
            result["memory_free_gb"] = round(pages_free * page_size / (1024**3), 1)
            result["memory_active_gb"] = round(pages_active * page_size / (1024**3), 1)
        except Exception as e:  # noqa: F841
            result["memory_percent"] = -1

    # 磁盘
    try:
        stat = os.statvfs("/")
        total = stat.f_blocks * stat.f_frsize
        free = stat.f_bavail * stat.f_frsize
        used_pct = round((1 - free / total) * 100, 1) if total > 0 else -1
        result["disk_total_gb"] = round(total / (1024**3), 1)
        result["disk_free_gb"] = round(free / (1024**3), 1)
        result["disk_used_percent"] = used_pct
    except (OSError, AttributeError) as e:  # noqa: F841
        result["disk_used_percent"] = -1

    return result
