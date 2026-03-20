"""
ClawBot 投资工具集 v2.1
- yfinance 异步化（asyncio.to_thread 避免阻塞事件循环）
- 并行行情查询（asyncio.gather）
- 行情缓存（60秒TTL，避免重复查询）
- 启动预热（后台预加载yfinance模块）
- SQLite 连接使用 context manager 防泄漏
- 动态读取 initial_capital
- 新增 remove_watchlist / reset_portfolio / get_trade_summary
"""
import asyncio
import logging
import sqlite3
import os
import time as _time
from contextlib import contextmanager
from datetime import datetime
from typing import Optional, Dict, Tuple

logger = logging.getLogger(__name__)

# ============ 行情缓存（统一代理到 QuoteCache） ============

_quote_cache: Dict[str, Tuple[dict, float]] = {}  # 本地回退缓存
CACHE_TTL = 60  # 缓存60秒


def _get_global_quote_cache():
    """获取全局 QuoteCache 实例（延迟导入避免循环依赖）"""
    try:
        from src.trading_system import get_quote_cache
        return get_quote_cache()
    except Exception:
        return None


def _get_cached_quote(symbol: str) -> Optional[dict]:
    """获取缓存的行情 — 优先从 QuoteCache 读取，回退到本地缓存"""
    key = symbol.upper()

    # 优先从全局 QuoteCache 获取（持仓监控也用这个）
    qc = _get_global_quote_cache()
    if qc is not None:
        price = qc.get(key)
        if price is not None and price > 0:
            # QuoteCache 只存 price，本地缓存存完整 dict
            if key in _quote_cache:
                quote, ts = _quote_cache[key]
                if _time.time() - ts < CACHE_TTL:
                    return quote

    # 回退到本地缓存
    if key in _quote_cache:
        quote, ts = _quote_cache[key]
        if _time.time() - ts < CACHE_TTL:
            return quote
    return None


def _set_cached_quote(symbol: str, quote: dict):
    """写入缓存 — 同时写入本地缓存和全局 QuoteCache"""
    key = symbol.upper()
    _quote_cache[key] = (quote, _time.time())

    # 同步写入全局 QuoteCache，让持仓监控也能用到最新价格
    qc = _get_global_quote_cache()
    if qc is not None:
        price = quote.get("price", 0)
        if price and price > 0:
            qc.put(key, float(price), source="invest_tools")


# ============ yfinance 同步封装 ============

_yf_module = None  # 延迟加载，预热后复用


def _env_bool(key: str, default: bool) -> bool:
    from src.utils import env_bool
    return env_bool(key, default)


def _ensure_yf():
    """确保 yfinance 已加载"""
    global _yf_module
    if _yf_module is None:
        try:
            import yfinance as yf
            _yf_module = yf
        except ImportError:
            return None
    return _yf_module


# ============ yfinance 同步封装 ============

def _sync_get_quote(symbol: str) -> dict:
    """同步获取行情（在线程池中执行，不阻塞事件循环）"""
    # 先查缓存
    cached = _get_cached_quote(symbol)
    if cached:
        return cached

    yf = _ensure_yf()
    if yf is None:
        return {"error": "yfinance 未安装，请运行: pip install yfinance"}

    try:
        ticker = yf.Ticker(symbol)
        # P1#12: 先获取历史数据（关键），再获取 info（可选）
        hist = ticker.history(period="5d")

        if hist.empty:
            return {"error": f"找不到 {symbol} 的行情数据"}

        # ticker.info 可能超时/限流，单独容错不影响核心行情
        info = {}
        try:
            info = ticker.info
        except Exception as e:
            logger.debug("[InvestTools] %s ticker.info 获取失败(不影响行情): %s", symbol, e)

        last_close = hist['Close'].iloc[-1]
        prev_close = hist['Close'].iloc[-2] if len(hist) > 1 else last_close
        change = last_close - prev_close
        change_pct = (change / prev_close) * 100 if prev_close else 0

        result = {
            "symbol": symbol.upper(),
            "name": info.get("shortName", symbol),
            "price": round(float(last_close), 2),
            "change": round(float(change), 2),
            "change_pct": round(float(change_pct), 2),
            "volume": int(hist['Volume'].iloc[-1]) if 'Volume' in hist else 0,
            "high": round(float(hist['High'].iloc[-1]), 2),
            "low": round(float(hist['Low'].iloc[-1]), 2),
            "market_cap": info.get("marketCap", 0),
            "pe_ratio": info.get("trailingPE", 0),
            "52w_high": info.get("fiftyTwoWeekHigh", 0),
            "52w_low": info.get("fiftyTwoWeekLow", 0),
            "currency": info.get("currency", "USD"),
        }
        _set_cached_quote(symbol, result)
        return result
    except Exception as e:
        return {"error": f"查询 {symbol} 失败: {str(e)}"}


# ============ 异步行情查询 ============

async def get_stock_quote(symbol: str) -> dict:
    """查询股票/ETF实时行情（异步，不阻塞事件循环，60秒缓存）"""
    symbol = symbol.upper().strip()
    cached = _get_cached_quote(symbol)
    if cached:
        return cached

    if _env_bool("PREFER_IBKR_QUOTES", True):
        try:
            from src.broker_bridge import ibkr as _ibkr
            if hasattr(_ibkr, "ensure_connected"):
                connected = await _ibkr.ensure_connected()
                if connected and hasattr(_ibkr, "get_realtime_snapshot"):
                    snap = await _ibkr.get_realtime_snapshot(symbol)
                    if isinstance(snap, dict) and "error" not in snap and snap.get("price", 0) > 0:
                        price = float(snap.get("price", 0) or 0)
                        bid = float(snap.get("bid", 0) or 0)
                        ask = float(snap.get("ask", 0) or 0)
                        result = {
                            "symbol": snap.get("symbol", symbol),
                            "name": snap.get("symbol", symbol),
                            "price": round(price, 2),
                            "change": round(float(snap.get("change", 0) or 0), 2),
                            "change_pct": round(float(snap.get("change_pct", 0) or 0), 2),
                            "volume": int(float(snap.get("volume", 0) or 0)),
                            "high": round(ask, 2) if ask > 0 else round(price, 2),
                            "low": round(bid, 2) if bid > 0 else round(price, 2),
                            "market_cap": 0,
                            "pe_ratio": 0,
                            "52w_high": 0,
                            "52w_low": 0,
                            "currency": snap.get("currency", "USD"),
                        }
                        _set_cached_quote(symbol, result)
                        return result
        except Exception as e:
            logger.debug("[InvestTools] IBKR实时报价回退到yfinance: %s", e)

    return await asyncio.to_thread(_sync_get_quote, symbol)


async def warmup():
    """预热 yfinance 模块（后台加载，避免首次查询29秒延迟）"""
    try:
        await asyncio.to_thread(_ensure_yf)
        logger.info("[invest_tools] yfinance 预热完成")
    except Exception as e:
        logger.warning(f"[invest_tools] yfinance 预热失败: {e}")


async def get_crypto_quote(symbol: str) -> dict:
    """查询加密货币行情（通过yfinance，格式如BTC-USD）"""
    if not symbol.endswith("-USD"):
        symbol = f"{symbol}-USD"
    return await get_stock_quote(symbol)


async def get_market_summary() -> str:
    """获取市场概览（并行查询9个指数/资产，速度提升约5-8倍）"""
    symbols = {
        "^GSPC": "标普500",
        "^IXIC": "纳斯达克",
        "^DJI": "道琼斯",
        "^HSI": "恒生指数",
        "000001.SS": "上证指数",
        "BTC-USD": "比特币",
        "ETH-USD": "以太坊",
        "GC=F": "黄金",
        "CL=F": "原油",
    }

    # 并行查询所有行情
    sym_list = list(symbols.keys())
    name_list = list(symbols.values())
    quotes = await asyncio.gather(
        *[get_stock_quote(sym) for sym in sym_list],
        return_exceptions=True
    )

    results = []
    for name, quote in zip(name_list, quotes):
        if isinstance(quote, Exception):
            results.append(f"{name}: 查询异常")
        elif "error" not in quote:
            arrow = "↑" if quote["change"] >= 0 else "↓"
            sign = "+" if quote["change"] >= 0 else ""
            results.append(
                f"{name}: {quote['price']} {arrow} {sign}{quote['change_pct']}%"
            )
        else:
            results.append(f"{name}: 数据获取失败")

    return "市场概览\n" + "\n".join(results)


def format_quote(quote: dict) -> str:
    """格式化行情数据为可读文本"""
    if "error" in quote:
        return quote["error"]

    arrow = "↑" if quote["change"] >= 0 else "↓"
    sign = "+" if quote["change"] >= 0 else ""

    lines = [
        f"{quote['name']} ({quote['symbol']})",
        f"价格: {quote['price']} {quote['currency']}",
        f"涨跌: {sign}{quote['change']} ({sign}{quote['change_pct']}%) {arrow}",
        f"最高/最低: {quote['high']} / {quote['low']}",
    ]

    if quote.get("volume"):
        vol = quote["volume"]
        if vol > 1_000_000:
            lines.append(f"成交量: {vol/1_000_000:.1f}M")
        else:
            lines.append(f"成交量: {vol:,}")

    if quote.get("market_cap"):
        mc = quote["market_cap"]
        if mc > 1_000_000_000_000:
            lines.append(f"市值: {mc/1_000_000_000_000:.2f}T")
        elif mc > 1_000_000_000:
            lines.append(f"市值: {mc/1_000_000_000:.2f}B")

    if quote.get("pe_ratio"):
        lines.append(f"PE: {quote['pe_ratio']:.1f}")

    if quote.get("52w_high"):
        lines.append(f"52周: {quote['52w_low']} ~ {quote['52w_high']}")

    return "\n".join(lines)


# ============ 模拟投资组合 ============

class Portfolio:
    """模拟投资组合管理器（SQLite context manager + 动态 initial_capital）"""

    def __init__(self, db_path: str = None):
        if db_path is None:
            db_path = os.path.join(
                os.path.dirname(os.path.abspath(__file__)),
                "..", "data", "portfolio.db"
            )
        self.db_path = db_path
        self._init_db()

    @contextmanager
    def _conn(self):
        """SQLite 连接 context manager，自动提交/关闭，防泄漏"""
        conn = sqlite3.connect(self.db_path)
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_db(self):
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        with self._conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS positions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT NOT NULL,
                    quantity REAL NOT NULL,
                    avg_price REAL NOT NULL,
                    side TEXT DEFAULT 'long',
                    opened_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    opened_by TEXT DEFAULT '',
                    reason TEXT DEFAULT '',
                    status TEXT DEFAULT 'open'
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS trades (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT NOT NULL,
                    action TEXT NOT NULL,
                    quantity REAL NOT NULL,
                    price REAL NOT NULL,
                    total REAL NOT NULL,
                    executed_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    decided_by TEXT DEFAULT '',
                    reason TEXT DEFAULT ''
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS watchlist (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT NOT NULL UNIQUE,
                    added_by TEXT DEFAULT '',
                    reason TEXT DEFAULT '',
                    target_price REAL DEFAULT 0,
                    stop_loss REAL DEFAULT 0,
                    added_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS portfolio_config (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )
            """)
            conn.execute(
                "INSERT OR IGNORE INTO portfolio_config (key, value) VALUES ('initial_capital', '100000')"
            )
            conn.execute(
                "INSERT OR IGNORE INTO portfolio_config (key, value) VALUES ('cash', '100000')"
            )

    def _get_config(self, key: str, default: float = 0) -> float:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT value FROM portfolio_config WHERE key=?", (key,)
            ).fetchone()
        return float(row[0]) if row else default

    def _set_config(self, key: str, value: float):
        with self._conn() as conn:
            conn.execute(
                "UPDATE portfolio_config SET value=? WHERE key=?",
                (str(value), key)
            )

    def get_cash(self) -> float:
        return self._get_config('cash', 100000.0)

    def get_initial_capital(self) -> float:
        return self._get_config('initial_capital', 100000.0)

    def buy(self, symbol: str, quantity: float, price: float,
            decided_by: str = "", reason: str = "") -> dict:
        """买入"""
        total = quantity * price
        cash = self.get_cash()
        if total > cash:
            return {"error": f"资金不足: 需要${total:.2f}, 可用${cash:.2f}"}

        with self._conn() as conn:
            existing = conn.execute(
                "SELECT id, quantity, avg_price FROM positions WHERE symbol=? AND status='open'",
                (symbol.upper(),)
            ).fetchone()

            if existing:
                old_qty, old_avg = existing[1], existing[2]
                new_qty = old_qty + quantity
                new_avg = (old_qty * old_avg + quantity * price) / new_qty
                conn.execute(
                    "UPDATE positions SET quantity=?, avg_price=? WHERE id=?",
                    (new_qty, new_avg, existing[0])
                )
            else:
                conn.execute(
                    "INSERT INTO positions (symbol, quantity, avg_price, opened_by, reason) VALUES (?,?,?,?,?)",
                    (symbol.upper(), quantity, price, decided_by, reason)
                )

            conn.execute(
                "INSERT INTO trades (symbol, action, quantity, price, total, decided_by, reason) VALUES (?,?,?,?,?,?,?)",
                (symbol.upper(), "BUY", quantity, price, total, decided_by, reason)
            )

        self._set_config('cash', cash - total)
        return {
            "action": "BUY",
            "symbol": symbol.upper(),
            "quantity": quantity,
            "price": price,
            "total": round(total, 2),
            "remaining_cash": round(cash - total, 2),
        }

    def sell(self, symbol: str, quantity: float, price: float,
             decided_by: str = "", reason: str = "") -> dict:
        """卖出"""
        with self._conn() as conn:
            existing = conn.execute(
                "SELECT id, quantity, avg_price FROM positions WHERE symbol=? AND status='open'",
                (symbol.upper(),)
            ).fetchone()

            if not existing:
                return {"error": f"没有 {symbol} 的持仓"}

            if quantity > existing[1]:
                return {"error": f"持仓不足: 持有{existing[1]}股, 要卖{quantity}股"}

            total = quantity * price
            profit = (price - existing[2]) * quantity

            new_qty = existing[1] - quantity
            if new_qty <= 0:
                conn.execute("UPDATE positions SET status='closed' WHERE id=?", (existing[0],))
            else:
                conn.execute("UPDATE positions SET quantity=? WHERE id=?", (new_qty, existing[0]))

            conn.execute(
                "INSERT INTO trades (symbol, action, quantity, price, total, decided_by, reason) VALUES (?,?,?,?,?,?,?)",
                (symbol.upper(), "SELL", quantity, price, total, decided_by, reason)
            )

        cash = self.get_cash()
        self._set_config('cash', cash + total)
        return {
            "action": "SELL",
            "symbol": symbol.upper(),
            "quantity": quantity,
            "price": price,
            "total": round(total, 2),
            "profit": round(profit, 2),
            "remaining_cash": round(cash + total, 2),
        }

    def get_positions(self) -> list:
        """获取所有持仓"""
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT symbol, quantity, avg_price, opened_by, reason, opened_at FROM positions WHERE status='open'"
            ).fetchall()
        return [
            {"symbol": r[0], "quantity": r[1], "avg_price": r[2],
             "opened_by": r[3], "reason": r[4], "opened_at": r[5]}
            for r in rows
        ]

    def get_trades(self, limit: int = 10) -> list:
        """获取最近交易记录"""
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT symbol, action, quantity, price, total, decided_by, reason, executed_at FROM trades ORDER BY id DESC LIMIT ?",
                (limit,)
            ).fetchall()
        return [
            {"symbol": r[0], "action": r[1], "quantity": r[2], "price": r[3],
             "total": r[4], "decided_by": r[5], "reason": r[6], "executed_at": r[7]}
            for r in rows
        ]

    def get_trade_summary(self) -> dict:
        """获取交易统计摘要"""
        with self._conn() as conn:
            total_trades = conn.execute("SELECT COUNT(*) FROM trades").fetchone()[0]
            buy_count = conn.execute("SELECT COUNT(*) FROM trades WHERE action='BUY'").fetchone()[0]
            sell_count = conn.execute("SELECT COUNT(*) FROM trades WHERE action='SELL'").fetchone()[0]
            total_buy_amount = conn.execute("SELECT COALESCE(SUM(total), 0) FROM trades WHERE action='BUY'").fetchone()[0]
            total_sell_amount = conn.execute("SELECT COALESCE(SUM(total), 0) FROM trades WHERE action='SELL'").fetchone()[0]
            closed_positions = conn.execute("SELECT COUNT(*) FROM positions WHERE status='closed'").fetchone()[0]
            open_positions = conn.execute("SELECT COUNT(*) FROM positions WHERE status='open'").fetchone()[0]
        return {
            "total_trades": total_trades,
            "buy_count": buy_count,
            "sell_count": sell_count,
            "total_buy_amount": round(total_buy_amount, 2),
            "total_sell_amount": round(total_sell_amount, 2),
            "realized_pnl": round(total_sell_amount - total_buy_amount, 2) if sell_count > 0 else 0,
            "closed_positions": closed_positions,
            "open_positions": open_positions,
        }

    def add_watchlist(self, symbol: str, added_by: str = "", reason: str = "",
                      target_price: float = 0, stop_loss: float = 0) -> dict:
        """添加自选股"""
        try:
            with self._conn() as conn:
                conn.execute(
                    "INSERT OR REPLACE INTO watchlist (symbol, added_by, reason, target_price, stop_loss) VALUES (?,?,?,?,?)",
                    (symbol.upper(), added_by, reason, target_price, stop_loss)
                )
            return {"symbol": symbol.upper(), "status": "added"}
        except Exception as e:
            return {"error": str(e)}

    def remove_watchlist(self, symbol: str) -> dict:
        """移除自选股"""
        with self._conn() as conn:
            cursor = conn.execute(
                "DELETE FROM watchlist WHERE symbol=?", (symbol.upper(),)
            )
            if cursor.rowcount == 0:
                return {"error": f"{symbol.upper()} 不在自选股中"}
        return {"symbol": symbol.upper(), "status": "removed"}

    def get_watchlist(self) -> list:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT symbol, added_by, reason, target_price, stop_loss FROM watchlist"
            ).fetchall()
        return [
            {"symbol": r[0], "added_by": r[1], "reason": r[2],
             "target_price": r[3], "stop_loss": r[4]}
            for r in rows
        ]

    def reset_portfolio(self, initial_capital: float = 100000) -> dict:
        """重置投资组合（清空持仓、交易记录、恢复初始资金）"""
        with self._conn() as conn:
            conn.execute("DELETE FROM positions")
            conn.execute("DELETE FROM trades")
            conn.execute(
                "UPDATE portfolio_config SET value=? WHERE key='cash'",
                (str(initial_capital),)
            )
            conn.execute(
                "UPDATE portfolio_config SET value=? WHERE key='initial_capital'",
                (str(initial_capital),)
            )
        return {
            "status": "reset",
            "initial_capital": initial_capital,
            "cash": initial_capital,
        }

    async def get_portfolio_summary(self) -> str:
        """生成投资组合摘要（并行查询所有持仓行情）"""
        positions = self.get_positions()
        cash = self.get_cash()
        initial_capital = self.get_initial_capital()

        if not positions:
            return f"投资组合\n\n现金: ${cash:,.2f}\n持仓: 无\n总资产: ${cash:,.2f}"

        # 并行查询所有持仓行情
        quotes = await asyncio.gather(
            *[get_stock_quote(pos["symbol"]) for pos in positions],
            return_exceptions=True
        )

        lines = ["投资组合\n"]
        total_value = cash

        for pos, quote in zip(positions, quotes):
            if isinstance(quote, Exception) or "error" in quote:
                lines.append(f"{pos['symbol']}: {pos['quantity']}股 @ ${pos['avg_price']:.2f} (行情获取失败)")
                total_value += pos["quantity"] * pos["avg_price"]
            else:
                current_price = quote["price"]
                market_value = pos["quantity"] * current_price
                cost = pos["quantity"] * pos["avg_price"]
                pnl = market_value - cost
                pnl_pct = (pnl / cost) * 100 if cost else 0
                total_value += market_value

                sign = "+" if pnl >= 0 else ""
                lines.append(
                    f"{pos['symbol']}: {pos['quantity']}股 @ ${pos['avg_price']:.2f}"
                    f" -> ${current_price:.2f} ({sign}{pnl_pct:.1f}%) "
                    f"盈亏: {sign}${pnl:.2f}"
                )

        total_pnl = total_value - initial_capital
        total_pnl_pct = (total_pnl / initial_capital) * 100 if initial_capital else 0
        sign = "+" if total_pnl >= 0 else ""

        lines.append(f"\n现金: ${cash:,.2f}")
        lines.append(f"持仓市值: ${total_value - cash:,.2f}")
        lines.append(f"总资产: ${total_value:,.2f}")
        lines.append(f"总盈亏: {sign}${total_pnl:,.2f} ({sign}{total_pnl_pct:.1f}%)")

        return "\n".join(lines)


# 全局实例
portfolio = Portfolio()
