"""
ClawBot Alpaca 券商桥接层 v1.0
搬运自 alpaca-py (1k⭐, Apache-2.0) — Alpaca Markets 官方 Python SDK

与 IBKRBridge 接口兼容 — auto_trader.py 可无缝切换券商。

Alpaca 优势:
  - 免费纸盘 (paper trading)，无需 IBKR 账户
  - 零佣金美股/ETF 交易
  - 简单 API Key 认证（不需要 TWS/Gateway）
  - 支持分数股（fractional shares）
  - 实时 WebSocket 行情（免费）

用法:
  1. 注册 Alpaca 账户: https://app.alpaca.markets/signup
  2. 获取 API Key + Secret
  3. 设置环境变量:
     ALPACA_API_KEY=your_key
     ALPACA_API_SECRET=your_secret
     ALPACA_PAPER=true  (纸盘模式)

接口:
  bridge = AlpacaBridge()
  await bridge.buy("AAPL", 10)
  await bridge.sell("AAPL", 5)
  positions = await bridge.get_positions()
  account = await bridge.get_account_summary()
"""
import asyncio
import logging
import os
from typing import Dict, List, Optional
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# ── Alpaca SDK 导入 (graceful degradation) ──────────────────
_HAS_ALPACA = False
try:
    from alpaca.trading.client import TradingClient
    from alpaca.trading.requests import (
        MarketOrderRequest,
        LimitOrderRequest,
        GetOrdersRequest,
    )
    from alpaca.trading.enums import OrderSide, TimeInForce, QueryOrderStatus
    _HAS_ALPACA = True
    logger.info("[AlpacaBridge] alpaca-py SDK 已加载")
except ImportError:
    TradingClient = None  # type: ignore[assignment,misc]
    logger.info("[AlpacaBridge] alpaca-py 未安装 (pip install alpaca-py)")


class AlpacaBridge:
    """Alpaca Markets 券商桥接 — 与 IBKRBridge 接口兼容

    搬运自 alpaca-py (1k⭐) + AmpyFin (MIT) 交易模式。
    """

    def __init__(
        self,
        api_key: str = "",
        api_secret: str = "",
        paper: bool = True,
        budget: float = 2000.0,
    ):
        self.budget = budget
        self._spent = 0.0
        self._connected = False
        self._client: Optional[TradingClient] = None  # type: ignore[type-arg]

        if not _HAS_ALPACA:
            logger.warning("[AlpacaBridge] alpaca-py 未安装，所有操作将返回模拟数据")
            return

        key = api_key or os.getenv("ALPACA_API_KEY", "")
        secret = api_secret or os.getenv("ALPACA_API_SECRET", "")
        is_paper = paper or os.getenv("ALPACA_PAPER", "true").lower() == "true"

        if not key or not secret:
            logger.warning("[AlpacaBridge] ALPACA_API_KEY/SECRET 未设置，降级模拟模式")
            return

        try:
            self._client = TradingClient(key, secret, paper=is_paper)
            self._connected = True
            mode = "纸盘" if is_paper else "实盘"
            logger.info(f"[AlpacaBridge] 已连接 Alpaca ({mode})")
        except Exception as e:
            logger.error(f"[AlpacaBridge] 连接失败: {e}")

    @property
    def connected(self) -> bool:
        return self._connected and self._client is not None

    # ── 账户 ────────────────────────────────────────────────

    async def get_account_summary(self) -> Dict:
        """获取账户摘要 — 兼容 IBKRBridge.get_account_summary()"""
        if not self.connected:
            return self._mock_account()
        try:
            def _get():
                acct = self._client.get_account()  # type: ignore[union-attr]
                return {
                    "equity": float(acct.equity),
                    "cash": float(acct.cash),
                    "buying_power": float(acct.buying_power),
                    "portfolio_value": float(acct.portfolio_value or 0),
                    "day_pnl": float(acct.equity) - float(acct.last_equity),
                    "day_pnl_pct": round(
                        (float(acct.equity) - float(acct.last_equity))
                        / float(acct.last_equity) * 100, 2
                    ) if float(acct.last_equity) > 0 else 0,
                    "status": acct.status.value if hasattr(acct.status, "value") else str(acct.status),
                    "source": "alpaca",
                }
            return await asyncio.to_thread(_get)
        except Exception as e:
            logger.error(f"[AlpacaBridge] 账户查询失败: {e}")
            return {"error": str(e), "source": "alpaca"}

    # ── 持仓 ────────────────────────────────────────────────

    async def get_positions(self) -> List[Dict]:
        """获取当前持仓 — 兼容 IBKRBridge.get_positions()"""
        if not self.connected:
            return []
        try:
            def _get():
                positions = self._client.get_all_positions()  # type: ignore[union-attr]
                return [
                    {
                        "symbol": p.symbol,
                        "quantity": float(p.qty),
                        "avg_cost": float(p.avg_entry_price),
                        "market_value": float(p.market_value or 0),
                        "unrealized_pnl": float(p.unrealized_pl or 0),
                        "unrealized_pnl_pct": float(p.unrealized_plpc or 0) * 100,
                        "current_price": float(p.current_price or 0),
                        "side": p.side.value if hasattr(p.side, "value") else "long",
                        "source": "alpaca",
                    }
                    for p in positions
                ]
            return await asyncio.to_thread(_get)
        except Exception as e:
            logger.error(f"[AlpacaBridge] 持仓查询失败: {e}")
            return []

    # ── 下单 ────────────────────────────────────────────────

    async def buy(
        self,
        symbol: str,
        quantity: float,
        order_type: str = "market",
        limit_price: Optional[float] = None,
    ) -> Dict:
        """买入 — 兼容 IBKRBridge.buy()"""
        return await self._place_order("BUY", symbol, quantity, order_type, limit_price)

    async def sell(
        self,
        symbol: str,
        quantity: float,
        order_type: str = "market",
        limit_price: Optional[float] = None,
    ) -> Dict:
        """卖出 — 兼容 IBKRBridge.sell()"""
        return await self._place_order("SELL", symbol, quantity, order_type, limit_price)

    async def _place_order(
        self,
        side: str,
        symbol: str,
        quantity: float,
        order_type: str = "market",
        limit_price: Optional[float] = None,
    ) -> Dict:
        if not self.connected:
            return {"status": "simulated", "symbol": symbol, "side": side,
                    "quantity": quantity, "source": "alpaca_mock"}

        try:
            def _exec():
                order_side = OrderSide.BUY if side == "BUY" else OrderSide.SELL

                if order_type == "limit" and limit_price:
                    req = LimitOrderRequest(
                        symbol=symbol,
                        qty=quantity,
                        side=order_side,
                        time_in_force=TimeInForce.DAY,
                        limit_price=limit_price,
                    )
                else:
                    req = MarketOrderRequest(
                        symbol=symbol,
                        qty=quantity,
                        side=order_side,
                        time_in_force=TimeInForce.DAY,
                    )

                order = self._client.submit_order(req)  # type: ignore[union-attr]
                return {
                    "status": "submitted",
                    "order_id": str(order.id),
                    "symbol": order.symbol,
                    "side": side,
                    "quantity": float(order.qty or quantity),
                    "type": order.type.value if hasattr(order.type, "value") else order_type,
                    "source": "alpaca",
                }
            return await asyncio.to_thread(_exec)
        except Exception as e:
            logger.error(f"[AlpacaBridge] 下单失败: {e}")
            return {"status": "error", "error": str(e), "source": "alpaca"}

    # ── 订单管理 ────────────────────────────────────────────

    async def get_open_orders(self) -> List[Dict]:
        """获取未成交订单"""
        if not self.connected:
            return []
        try:
            def _get():
                req = GetOrdersRequest(status=QueryOrderStatus.OPEN)
                orders = self._client.get_orders(req)  # type: ignore[union-attr]
                return [
                    {
                        "order_id": str(o.id),
                        "symbol": o.symbol,
                        "side": o.side.value,
                        "quantity": float(o.qty or 0),
                        "filled_qty": float(o.filled_qty or 0),
                        "type": o.type.value if hasattr(o.type, "value") else "",
                        "status": o.status.value if hasattr(o.status, "value") else "",
                        "source": "alpaca",
                    }
                    for o in orders
                ]
            return await asyncio.to_thread(_get)
        except Exception as e:
            logger.error(f"[AlpacaBridge] 订单查询失败: {e}")
            return []

    async def cancel_order(self, order_id: str) -> Dict:
        """取消订单"""
        if not self.connected:
            return {"status": "simulated", "order_id": order_id}
        try:
            def _cancel():
                self._client.cancel_order_by_id(order_id)  # type: ignore[union-attr]
                return {"status": "cancelled", "order_id": order_id, "source": "alpaca"}
            return await asyncio.to_thread(_cancel)
        except Exception as e:
            return {"status": "error", "error": str(e)}

    async def cancel_all_orders(self) -> Dict:
        """取消所有订单"""
        if not self.connected:
            return {"status": "simulated", "cancelled": 0}
        try:
            def _cancel_all():
                self._client.cancel_orders()  # type: ignore[union-attr]
                return {"status": "cancelled_all", "source": "alpaca"}
            return await asyncio.to_thread(_cancel_all)
        except Exception as e:
            return {"status": "error", "error": str(e)}

    # ── 模拟数据 ────────────────────────────────────────────

    @staticmethod
    def _mock_account() -> Dict:
        return {
            "equity": 100000.0,
            "cash": 100000.0,
            "buying_power": 200000.0,
            "portfolio_value": 0.0,
            "day_pnl": 0.0,
            "day_pnl_pct": 0.0,
            "status": "simulated",
            "source": "alpaca_mock",
        }

    # ── trading_system 兼容方法 ─────────────────────────────
    # 以下方法让 AlpacaBridge 能被 trading_system.py 无缝替换 IBKRBridge

    def is_connected(self) -> bool:
        """兼容 IBKRBridge.is_connected()"""
        return self.connected

    async def sync_capital(self) -> float:
        """同步实际资金 — 兼容 IBKRBridge.sync_capital()"""
        acct = await self.get_account_summary()
        return float(acct.get("equity", 0))

    def reset_budget(self):
        """重置每日预算追踪 — 兼容 IBKRBridge.reset_budget()"""
        self._spent = 0.0

    async def ensure_connected(self) -> bool:
        """确保连接 — 兼容 IBKRBridge.ensure_connected()"""
        if self.connected:
            return True
        # Alpaca 无状态 HTTP，重新初始化即可
        try:
            key = os.getenv("ALPACA_API_KEY", "")
            secret = os.getenv("ALPACA_API_SECRET", "")
            if key and secret and _HAS_ALPACA:
                is_paper = os.getenv("ALPACA_PAPER", "true").lower() == "true"
                self._client = TradingClient(key, secret, paper=is_paper)
                self._connected = True
                return True
        except Exception as e:
            logger.error(f"[AlpacaBridge] 重连失败: {e}")
        return False

    async def get_recent_fills(self, lookback_hours: int = 48) -> list:
        """获取最近成交记录 — 兼容 IBKRBridge.get_recent_fills()"""
        if not self.connected:
            return []
        try:
            from datetime import timedelta
            from src.utils import now_et

            def _get_fills():
                req = GetOrdersRequest(
                    status=QueryOrderStatus.CLOSED,
                    after=now_et() - timedelta(hours=lookback_hours),
                )
                orders = self._client.get_orders(req)  # type: ignore[union-attr]
                return [
                    {
                        "symbol": o.symbol,
                        "side": o.side.value,
                        "quantity": float(o.filled_qty or 0),
                        "avg_fill_price": float(o.filled_avg_price or 0),
                        "filled_time": str(o.filled_at) if o.filled_at else "",
                        "order_id": str(o.id),
                        "source": "alpaca",
                    }
                    for o in orders
                    if float(o.filled_qty or 0) > 0
                ]
            return await asyncio.to_thread(_get_fills)
        except Exception as e:
            logger.warning(f"[AlpacaBridge] 成交查询失败: {e}")
            return []

    def get_connection_status(self) -> str:
        """连接状态文本 — 兼容 IBKRBridge.get_connection_status()"""
        if self.connected:
            mode = "纸盘" if os.getenv("ALPACA_PAPER", "true").lower() == "true" else "实盘"
            return f"Alpaca: 已连接 ({mode})"
        return "Alpaca: 未连接"

    @property
    def total_spent(self) -> float:
        return self._spent


# ── 全局单例 ──────────────────────────────────────────────

_bridge: Optional[AlpacaBridge] = None


def get_alpaca_bridge() -> AlpacaBridge:
    global _bridge
    if _bridge is None:
        _bridge = AlpacaBridge()
    return _bridge
