"""
券商选择器与懒加载单例模块

负责：
- IBKRBridge 单例的懒初始化（避免 import 时创建实例）
- 统一券商选择器（IBKR → Alpaca → 模拟盘）
- 向后兼容的 _LazyIBKR 代理对象

从 broker_bridge.py 提取，解耦"桥接实现"与"实例管理"职责。
"""
import logging
import os as _os
import threading

from src.broker_bridge import IBKRBridge, HAS_IB

logger = logging.getLogger(__name__)


# ── 懒加载单例 ─────────────────────────────────────────────
# P2#33: 避免 import 时创建实例（事件循环/环境变量可能未就绪）

_ibkr_instance = None
# 保护单例创建，防止并发线程（如 APScheduler）重复实例化
_ibkr_lock = threading.Lock()


def get_ibkr() -> IBKRBridge:
    """获取 IBKRBridge 单例（首次调用时创建，线程安全双重检查锁）"""
    global _ibkr_instance
    if _ibkr_instance is None:
        with _ibkr_lock:
            # 双重检查：拿锁后再确认一次，避免重复创建
            if _ibkr_instance is None:
                _ibkr_instance = IBKRBridge(
                    host=_os.environ.get("IBKR_HOST", "127.0.0.1"),
                    port=int(_os.environ.get("IBKR_PORT", "4002")),
                    client_id=int(_os.environ.get("IBKR_CLIENT_ID", "0")),
                    account=_os.environ.get("IBKR_ACCOUNT", ""),
                    budget=float(_os.environ.get("IBKR_BUDGET", "2000.0")),
                )
    return _ibkr_instance


# ── 向后兼容代理 ───────────────────────────────────────────
# 保留 ibkr 属性名，但延迟到首次访问时创建真实实例

class _LazyIBKR:
    """代理对象，首次属性访问时才创建真实实例"""
    def __getattr__(self, name):
        return getattr(get_ibkr(), name)

ibkr = _LazyIBKR()


# ── 统一券商选择器 (v1.1, 2026-03-23) ──────────────────────
# 自动检测可用券商: IBKR → Alpaca → 模拟盘
# trading_system.py 可直接用 get_broker() 获取最佳可用券商

def get_broker():
    """获取最佳可用券商实例。

    优先级: IBKR (已连接) → Alpaca (有API Key) → IBKR (模拟盘)

    返回的对象统一实现:
      buy(symbol, quantity) / sell(symbol, quantity)
      get_positions() / get_account_summary()
      get_open_orders() / cancel_order(order_id)
    """
    # 1. 检查 IBKR 是否已连接
    try:
        ib = get_ibkr()
        if HAS_IB and ib.is_connected():
            logger.debug("[BrokerSelector] 使用 IBKR (已连接)")
            return ib
    except Exception:
        logger.debug("Silenced exception", exc_info=True)

    # 2. 检查 Alpaca 是否有 API Key
    try:
        from src.alpaca_bridge import get_alpaca_bridge
        alpaca = get_alpaca_bridge()
        if alpaca.connected:
            logger.debug("[BrokerSelector] 使用 Alpaca")
            return alpaca
    except ImportError:
        pass

    # 3. 降级到 IBKR 模拟盘
    logger.debug("[BrokerSelector] 使用 IBKR (模拟盘)")
    return get_ibkr()
