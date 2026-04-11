"""
IBKR 扫描器与合约搜索 Mixin

从 broker_bridge.py 提取，包含：
- BrokerScannerMixin：合约构建、Scanner 扫描、合约搜索、实时快照
- 依赖 ib_insync（通过 self.ib 访问 IB 连接）
"""
import asyncio
import re
import logging
import time as _time
from typing import Optional, List, Dict, TYPE_CHECKING

from src.utils import now_et

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from ib_insync import Stock, Forex, Crypto, Contract, ScannerSubscription

try:
    from ib_insync import Stock, Forex, Crypto, Contract, ScannerSubscription
    _HAS_IB_SCANNER = True
except ImportError:
    _HAS_IB_SCANNER = False
    # 定义占位类型，避免类定义时 NameError
    Stock = None  # type: ignore[assignment,misc]
    Forex = None  # type: ignore[assignment,misc]
    Crypto = None  # type: ignore[assignment,misc]
    Contract = None  # type: ignore[assignment,misc]
    ScannerSubscription = None  # type: ignore[assignment,misc]


class BrokerScannerMixin:
    """IBKR 扫描器与合约搜索功能 Mixin — 通过 self.ib 访问 IB 连接"""

    def _make_contract(self, symbol: str, sec_type: str = 'STK',
                       exchange: str = 'SMART', currency: str = 'USD') -> "Contract":
        """创建合约对象"""
        symbol = symbol.upper()

        # 加密货币特殊处理
        crypto_map = {
            'BTC': ('BTC', 'PAXOS', 'USD'),
            'ETH': ('ETH', 'PAXOS', 'USD'),
            'BTC-USD': ('BTC', 'PAXOS', 'USD'),
            'ETH-USD': ('ETH', 'PAXOS', 'USD'),
        }
        if symbol in crypto_map:
            sym, exch, cur = crypto_map[symbol]
            return Crypto(sym, exch, cur)

        # 港股特殊处理
        if symbol.isdigit() or symbol.endswith('.HK'):
            sym = symbol.replace('.HK', '')
            return Stock(sym, 'SEHK', 'HKD')

        # 默认美股
        return Stock(symbol, exchange, currency)

    def _normalize_scanner_symbol(self, contract: "Contract") -> str:
        """将 IBKR 合约标准化为统一 symbol（港股补 .HK）"""
        symbol = str(getattr(contract, "symbol", "") or "").upper().strip()
        if not symbol:
            return ""

        exchange = str(getattr(contract, "primaryExchange", "") or getattr(contract, "exchange", "") or "").upper()
        currency = str(getattr(contract, "currency", "") or "").upper()
        if exchange == "SEHK" or currency == "HKD":
            digits = re.sub(r"\D", "", symbol)
            if digits:
                return f"{digits.zfill(4)}.HK"
            if not symbol.endswith(".HK"):
                return f"{symbol}.HK"
        return symbol

    async def get_market_scanner_symbols(
        self,
        max_symbols: int = 800,
        include_us: bool = True,
        include_hk: bool = True,
    ) -> List[str]:
        """从 IBKR Scanner 拉取动态可交易标的池（近实时）"""
        if not await self.ensure_connected():
            return []
        if not _HAS_IB_SCANNER or ScannerSubscription is None:
            logger.warning("[IBKR] Scanner 不可用：ib_insync 缺失")
            return []

        max_symbols = max(50, int(max_symbols or 800))
        profiles = []
        if include_us:
            profiles.extend([
                {"location": "STK.US.MAJOR", "scan": "MOST_ACTIVE", "rows": 200},
                {"location": "STK.US.MAJOR", "scan": "HOT_BY_VOLUME", "rows": 200},
                {"location": "STK.US.MAJOR", "scan": "TOP_PERC_GAIN", "rows": 200},
                {"location": "STK.US.MAJOR", "scan": "TOP_PERC_LOSE", "rows": 200},
            ])
        if include_hk:
            profiles.extend([
                {"location": "STK.HK.SEHK", "scan": "MOST_ACTIVE", "rows": 120},
                {"location": "STK.HK.SEHK", "scan": "TOP_PERC_GAIN", "rows": 120},
            ])

        seen = set()
        symbols = []

        for profile in profiles:
            try:
                sub = ScannerSubscription(
                    instrument="STK",
                    locationCode=profile["location"],
                    scanCode=profile["scan"],
                    numberOfRows=profile["rows"],
                )
                rows = self.ib.reqScannerData(sub)
            except Exception as e:
                logger.debug(
                    "[IBKR] Scanner 请求失败 location=%s scan=%s: %s",
                    profile["location"],
                    profile["scan"],
                    e,
                )
                await asyncio.sleep(0.25)
                continue

            for row in rows or []:
                details = getattr(row, "contractDetails", None)
                contract = getattr(details, "contract", None) if details else None
                if contract is None:
                    continue
                symbol = self._normalize_scanner_symbol(contract)
                if not symbol or symbol in seen:
                    continue
                seen.add(symbol)
                symbols.append(symbol)
                if len(symbols) >= max_symbols:
                    break

            if len(symbols) >= max_symbols:
                break
            await asyncio.sleep(0.25)

        logger.info("[IBKR] Scanner 动态标的池: %d 个", len(symbols))
        return symbols

    async def search_matching_contracts(self, query: str, limit: int = 20) -> List[Dict]:
        """按关键字搜索 IBKR 可交易合约（用于任意标的发现）"""
        if not await self.ensure_connected():
            return []
        keyword = (query or "").strip()
        if not keyword:
            return []

        try:
            matches = self.ib.reqMatchingSymbols(keyword)
        except Exception as e:
            logger.warning("[IBKR] 合约搜索失败 %s: %s", keyword, e)
            return []

        items = []
        for m in matches[: max(1, int(limit or 20))]:
            contract = getattr(m, "contract", None)
            if contract is None:
                continue
            items.append({
                "symbol": self._normalize_scanner_symbol(contract),
                "raw_symbol": getattr(contract, "symbol", ""),
                "sec_type": getattr(contract, "secType", ""),
                "exchange": getattr(contract, "exchange", ""),
                "primary_exchange": getattr(contract, "primaryExchange", ""),
                "currency": getattr(contract, "currency", ""),
                "description": getattr(m, "description", ""),
                "derivative_sec_types": list(getattr(m, "derivativeSecTypes", []) or []),
            })
        return items

    async def get_realtime_snapshot(
        self,
        symbol: str,
        sec_type: str = "STK",
        exchange: str = "SMART",
        currency: str = "USD",
        timeout_seconds: float = 6.0,
    ) -> Dict:
        """获取单个标的 IBKR 实时快照（last/bid/ask/volume）"""
        if not await self.ensure_connected():
            return {"error": "未连接到IBKR"}

        try:
            contract = self._make_contract(symbol, sec_type=sec_type, exchange=exchange, currency=currency)
            qualified = await self.ib.qualifyContractsAsync(contract)
            if not qualified:
                return {"error": f"无法识别合约: {symbol}"}

            q_contract = qualified[0]
            ticker = self.ib.reqMktData(q_contract, "", True, False)

            deadline = _time.time() + max(1.0, float(timeout_seconds or 6.0))
            while _time.time() < deadline:
                last = float(getattr(ticker, "last", 0) or 0)
                close = float(getattr(ticker, "close", 0) or 0)
                bid = float(getattr(ticker, "bid", 0) or 0)
                ask = float(getattr(ticker, "ask", 0) or 0)
                if last > 0 or close > 0 or bid > 0 or ask > 0:
                    break
                await asyncio.sleep(0.2)

            last = float(getattr(ticker, "last", 0) or 0)
            close = float(getattr(ticker, "close", 0) or 0)
            bid = float(getattr(ticker, "bid", 0) or 0)
            ask = float(getattr(ticker, "ask", 0) or 0)
            volume = float(getattr(ticker, "volume", 0) or 0)

            if last <= 0 and bid > 0 and ask > 0:
                last = (bid + ask) / 2
            if last <= 0 and close > 0:
                last = close
            if close <= 0 and last > 0:
                close = last

            change = last - close if (last > 0 and close > 0) else 0.0
            change_pct = (change / close * 100) if close > 0 else 0.0

            return {
                "symbol": self._normalize_scanner_symbol(q_contract),
                "price": round(last, 4) if last > 0 else 0,
                "bid": round(bid, 4) if bid > 0 else 0,
                "ask": round(ask, 4) if ask > 0 else 0,
                "prev_close": round(close, 4) if close > 0 else 0,
                "change": round(change, 4),
                "change_pct": round(change_pct, 4),
                "volume": int(volume) if volume > 0 else 0,
                "currency": getattr(q_contract, "currency", currency),
                "exchange": getattr(q_contract, "primaryExchange", "") or getattr(q_contract, "exchange", ""),
                "timestamp": now_et().isoformat(),
            }
        except Exception as e:
            logger.exception("获取 IBKR 实时快照失败: %s", symbol)
            return {"error": f"获取快照失败: {e}"}
        finally:
            try:
                if 'q_contract' in locals():
                    self.ib.cancelMktData(q_contract)
            except Exception as e:
                logger.debug("Silenced exception", exc_info=True)
