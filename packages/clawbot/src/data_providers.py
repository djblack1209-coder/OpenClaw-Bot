"""
ClawBot 统一数据提供层 v1.0
- 多市场支持: 美股(yfinance) / A股(akshare) / 加密货币(ccxt)
- 自动市场检测: 根据 symbol 格式判断所属市场
- 统一列名: Open/High/Low/Close/Volume (pandas DataFrame)
- 延迟导入: akshare/ccxt 可选依赖，未安装时优雅降级
- 同步 + 异步双接口

搬运思路:
  - akshare: 东方财富/新浪等数据源的统一封装 (14k⭐, MIT)
  - ccxt:    108+ 交易所的统一 API (35k⭐, MIT)
  - yfinance: 美股/ETF 数据 (已有)
"""
import asyncio
import logging
import re
import time as _time
from datetime import timedelta
from enum import Enum

from src.utils import now_et

logger = logging.getLogger(__name__)

# ============ 市场枚举 ============

class Market(Enum):
    US = "us"           # 美股/ETF (yfinance)
    CN_A = "cn_a"       # A股 (akshare)
    CRYPTO = "crypto"   # 加密货币 (ccxt)


# ============ 市场自动检测 ============

# A股代码模式: 6位纯数字, 或 带 .SZ/.SH/.BJ 后缀
_CN_PATTERN = re.compile(
    r'^(?:'
    r'[036]\d{5}'              # 6位数字开头: 0/3(深圳) 6(上海)
    r'|[48]\d{5}'              # 4/8 开头(北交所/新三板)
    r'|\d{6}\.(?:SZ|SH|BJ)'   # 带后缀
    r')$',
    re.IGNORECASE
)

# 加密货币模式: XXX/USDT, BTC/USD, ETH-USDT 等
_CRYPTO_PATTERN = re.compile(
    r'^[A-Z0-9]{2,10}[/-](?:USDT?|BUSD|USDC|EUR|BTC|ETH)$',
    re.IGNORECASE
)


def detect_market(symbol: str) -> Market:
    """
    根据 symbol 格式自动检测所属市场

    - 000001, 600519, 300750.SZ → CN_A
    - BTC/USDT, ETH-USD         → CRYPTO
    - AAPL, MSFT, ^GSPC         → US (默认)
    """
    s = symbol.strip()

    if _CN_PATTERN.match(s):
        return Market.CN_A

    if _CRYPTO_PATTERN.match(s):
        return Market.CRYPTO

    return Market.US


# ============ 延迟导入管理 ============

_ak_module = None
_ccxt_module = None
_yf_module = None


def _ensure_akshare():
    """延迟加载 akshare，未安装时给出明确提示"""
    global _ak_module
    if _ak_module is None:
        try:
            import akshare as ak
            _ak_module = ak
        except ImportError:
            raise ImportError("akshare 未安装。请运行: pip install akshare")
    return _ak_module


def _ensure_ccxt():
    """延迟加载 ccxt，未安装时给出明确提示"""
    global _ccxt_module
    if _ccxt_module is None:
        try:
            import ccxt as _ccxt
            _ccxt_module = _ccxt
        except ImportError:
            raise ImportError("ccxt 未安装。请运行: pip install ccxt")
    return _ccxt_module


def _ensure_yfinance():
    """延迟加载 yfinance"""
    global _yf_module
    if _yf_module is None:
        try:
            import yfinance as yf
            _yf_module = yf
        except ImportError:
            raise ImportError("yfinance 未安装。请运行: pip install yfinance")
    return _yf_module


# ============ A股数据 (akshare) ============

def _normalize_cn_symbol(symbol: str) -> str:
    """标准化A股代码: 去掉 .SZ/.SH/.BJ 后缀，返回纯6位数字"""
    return re.sub(r'\.(SZ|SH|BJ)$', '', symbol.strip(), flags=re.IGNORECASE)


def akshare_get_history(symbol: str, period: str = "3mo",
                        interval: str = "1d") -> "pd.DataFrame":
    """
    获取A股历史K线 (akshare)

    Parameters:
        symbol: A股代码 (如 "000001", "600519.SH")
        period: 回溯周期 ("1mo"/"3mo"/"6mo"/"1y"/"2y")
        interval: K线周期 ("1d"/"1w"/"1mo")

    Returns:
        标准化 DataFrame (columns: Open/High/Low/Close/Volume, index: DatetimeIndex)
    """
    import pandas as pd
    ak = _ensure_akshare()

    code = _normalize_cn_symbol(symbol)

    # 计算起止日期
    period_map = {
        "1mo": 30, "3mo": 90, "6mo": 180,
        "1y": 365, "2y": 730, "5d": 5, "1w": 7,
    }
    days = period_map.get(period, 90)
    end_date = now_et().strftime("%Y%m%d")
    start_date = (now_et() - timedelta(days=days)).strftime("%Y%m%d")

    # akshare 日线接口
    # adjust="qfq" 前复权
    try:
        df = ak.stock_zh_a_hist(
            symbol=code,
            period="daily" if interval == "1d" else ("weekly" if interval == "1w" else "monthly"),
            start_date=start_date,
            end_date=end_date,
            adjust="qfq",
        )
    except Exception as e:
        logger.error("[DataProvider] akshare A股数据获取失败 %s: %s", symbol, e)
        raise

    if df is None or df.empty:
        raise ValueError(f"A股 {symbol} 无数据返回")

    # 列名标准化 (akshare 返回中文列名)
    col_map = {
        "日期": "Date",
        "开盘": "Open",
        "收盘": "Close",
        "最高": "High",
        "最低": "Low",
        "成交量": "Volume",
        "成交额": "Amount",
        "振幅": "Amplitude",
        "涨跌幅": "Change_pct",
        "涨跌额": "Change",
        "换手率": "Turnover",
    }
    df = df.rename(columns=col_map)

    # 设置时间索引
    if "Date" in df.columns:
        df["Date"] = pd.to_datetime(df["Date"])
        df = df.set_index("Date")

    # 确保数值类型
    for col in ["Open", "High", "Low", "Close", "Volume"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    return df


def akshare_get_quote(symbol: str) -> dict:
    """
    获取A股实时行情 (akshare)

    Returns:
        标准化 quote dict (与 yfinance 格式对齐)
    """
    ak = _ensure_akshare()
    code = _normalize_cn_symbol(symbol)

    try:
        # 使用东方财富实时行情接口
        df = ak.stock_zh_a_spot_em()

        if df is None or df.empty:
            return {"error": f"A股实时行情获取失败: {symbol}"}

        # 查找目标股票
        row = df[df["代码"] == code]
        if row.empty:
            return {"error": f"找不到A股代码: {code}"}

        row = row.iloc[0]

        price = float(row.get("最新价", 0) or 0)
        change = float(row.get("涨跌额", 0) or 0)
        change_pct = float(row.get("涨跌幅", 0) or 0)
        volume = int(float(row.get("成交量", 0) or 0))
        high = float(row.get("最高", 0) or 0)
        low = float(row.get("最低", 0) or 0)
        amount = float(row.get("成交额", 0) or 0)
        name = str(row.get("名称", code))

        # 市值 (单位: 元)
        market_cap = float(row.get("总市值", 0) or 0)
        pe = float(row.get("市盈率-动态", 0) or 0)
        high_52w = float(row.get("52周最高", 0) or 0)
        low_52w = float(row.get("52周最低", 0) or 0)

        return {
            "symbol": symbol.upper(),
            "name": name,
            "price": round(price, 2),
            "change": round(change, 2),
            "change_pct": round(change_pct, 2),
            "volume": volume,
            "high": round(high, 2),
            "low": round(low, 2),
            "market_cap": market_cap,
            "pe_ratio": round(pe, 2) if pe else 0,
            "52w_high": round(high_52w, 2) if high_52w else 0,
            "52w_low": round(low_52w, 2) if low_52w else 0,
            "currency": "CNY",
            "market": Market.CN_A.value,
            "amount": amount,
        }
    except ImportError:
        raise
    except Exception as e:
        return {"error": f"A股行情查询失败 {symbol}: {e}"}


# ============ 加密货币数据 (ccxt) ============

_default_exchange = None


def _get_exchange():
    """获取默认交易所实例 (binance)，带缓存"""
    global _default_exchange
    if _default_exchange is None:
        ccxt = _ensure_ccxt()
        _default_exchange = ccxt.binance({
            "enableRateLimit": True,
            "options": {"defaultType": "spot"},
        })
    return _default_exchange


def _normalize_crypto_symbol(symbol: str) -> str:
    """标准化加密货币交易对: ETH-USDT → ETH/USDT"""
    return symbol.strip().upper().replace("-", "/")


def ccxt_get_history(symbol: str, period: str = "3mo",
                     interval: str = "1d") -> "pd.DataFrame":
    """
    获取加密货币历史K线 (ccxt)

    Parameters:
        symbol: 交易对 (如 "BTC/USDT", "ETH-USD")
        period: 回溯周期
        interval: K线周期 ("1m"/"5m"/"1h"/"1d"/"1w")

    Returns:
        标准化 DataFrame (columns: Open/High/Low/Close/Volume)
    """
    import pandas as pd

    exchange = _get_exchange()
    pair = _normalize_crypto_symbol(symbol)

    # ccxt timeframe 映射
    tf_map = {
        "1m": "1m", "5m": "5m", "15m": "15m", "30m": "30m",
        "1h": "1h", "4h": "4h",
        "1d": "1d", "1w": "1w", "1mo": "1M",
    }
    timeframe = tf_map.get(interval, "1d")

    # 计算数据条数
    period_map = {
        "5d": 5, "1w": 7, "1mo": 30, "3mo": 90,
        "6mo": 180, "1y": 365, "2y": 730,
    }
    days = period_map.get(period, 90)

    # 根据 interval 计算需要多少根 K线
    interval_minutes = {
        "1m": 1, "5m": 5, "15m": 15, "30m": 30,
        "1h": 60, "4h": 240, "1d": 1440, "1w": 10080, "1mo": 43200,
    }
    mins_per_bar = interval_minutes.get(interval, 1440)
    limit = min(int(days * 1440 / mins_per_bar), 1000)  # ccxt 最多1000条

    since = int((now_et() - timedelta(days=days)).timestamp() * 1000)

    try:
        ohlcv = exchange.fetch_ohlcv(pair, timeframe=timeframe, since=since, limit=limit)
    except Exception as e:
        logger.error("[DataProvider] ccxt 加密货币数据获取失败 %s: %s", symbol, e)
        raise

    if not ohlcv:
        raise ValueError(f"加密货币 {symbol} 无数据返回")

    # 转换为 DataFrame
    df = pd.DataFrame(ohlcv, columns=["Timestamp", "Open", "High", "Low", "Close", "Volume"])
    df["Date"] = pd.to_datetime(df["Timestamp"], unit="ms")
    df = df.set_index("Date")
    df = df.drop(columns=["Timestamp"])

    # 确保数值类型
    for col in ["Open", "High", "Low", "Close", "Volume"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    return df


def ccxt_get_quote(symbol: str) -> dict:
    """
    获取加密货币实时行情 (ccxt)

    Returns:
        标准化 quote dict
    """
    try:
        exchange = _get_exchange()
        pair = _normalize_crypto_symbol(symbol)

        ticker = exchange.fetch_ticker(pair)

        price = float(ticker.get("last", 0) or 0)
        change = float(ticker.get("change", 0) or 0)
        change_pct = float(ticker.get("percentage", 0) or 0)
        volume = float(ticker.get("baseVolume", 0) or 0)
        high = float(ticker.get("high", 0) or 0)
        low = float(ticker.get("low", 0) or 0)

        return {
            "symbol": pair,
            "name": pair,
            "price": round(price, 6) if price < 1 else round(price, 2),
            "change": round(change, 6) if abs(change) < 1 else round(change, 2),
            "change_pct": round(change_pct, 2),
            "volume": int(volume),
            "high": round(high, 6) if high < 1 else round(high, 2),
            "low": round(low, 6) if low < 1 else round(low, 2),
            "market_cap": 0,
            "pe_ratio": 0,
            "52w_high": 0,
            "52w_low": 0,
            "currency": "USDT",
            "market": Market.CRYPTO.value,
        }
    except ImportError:
        raise
    except Exception as e:
        return {"error": f"加密货币行情查询失败 {symbol}: {e}"}


# ============ 统一同步接口 ============

def get_quote_sync(symbol: str) -> dict:
    """
    统一行情查询 (同步) — 自动检测市场并路由到对应数据源

    US    → yfinance
    CN_A  → akshare
    CRYPTO → ccxt
    """
    market = detect_market(symbol)

    if market == Market.CN_A:
        try:
            return akshare_get_quote(symbol)
        except ImportError as e:
            logger.warning("[DataProvider] %s, 回退到 yfinance", e)
            # A股无法用 yfinance 回退，返回错误
            return {"error": str(e)}

    elif market == Market.CRYPTO:
        try:
            return ccxt_get_quote(symbol)
        except ImportError as e:
            logger.warning("[DataProvider] %s, 尝试 yfinance 回退", e)
            # 加密货币可以用 yfinance 格式: BTC-USD
            yf_symbol = symbol.replace("/", "-").replace("USDT", "USD")
            return _yfinance_get_quote(yf_symbol)

    else:  # Market.US
        return _yfinance_get_quote(symbol)


def get_history_sync(symbol: str, period: str = "3mo",
                     interval: str = "1d") -> "pd.DataFrame":
    """
    统一历史K线查询 (同步) — 自动检测市场并路由

    Returns:
        标准化 DataFrame (columns: Open/High/Low/Close/Volume)
    """
    market = detect_market(symbol)

    if market == Market.CN_A:
        try:
            return akshare_get_history(symbol, period=period, interval=interval)
        except ImportError as e:
            logger.warning("[DataProvider] %s", e)
            raise

    elif market == Market.CRYPTO:
        try:
            return ccxt_get_history(symbol, period=period, interval=interval)
        except ImportError as e:
            logger.warning("[DataProvider] %s, 尝试 yfinance 回退", e)
            yf_symbol = symbol.replace("/", "-").replace("USDT", "USD")
            return _yfinance_get_history(yf_symbol, period=period, interval=interval)

    else:  # Market.US
        return _yfinance_get_history(symbol, period=period, interval=interval)


# ============ yfinance 行情缓存 ============

_quote_cache: dict[str, tuple[float, dict]] = {}  # symbol -> (timestamp, data)
QUOTE_CACHE_TTL = 60  # seconds


def _cached_yfinance_get_quote(symbol: str) -> dict:
    """带 TTL 缓存的 yfinance 行情查询，避免高频重复网络请求"""
    now = _time.time()
    cache_key = symbol.upper()

    if cache_key in _quote_cache:
        ts, data = _quote_cache[cache_key]
        if now - ts < QUOTE_CACHE_TTL:
            result = dict(data)  # shallow copy to avoid mutating cache
            result["_cached"] = True
            result["_cache_age_s"] = round(now - ts, 1)
            return result

    # Fetch fresh data via raw yfinance call
    result = _yfinance_get_quote_raw(symbol)
    result["_fetched_at"] = now
    result["_cached"] = False

    # Staleness detection: warn if data is from a different trading day
    try:
        today = now_et().date()
        # yfinance history index contains the last trade date
        if result.get("_last_trade_date"):
            data_date = result["_last_trade_date"]
            if data_date < today - timedelta(days=1):
                result["_stale_warning"] = f"Data from {data_date}, today is {today}"
    except Exception as e:
        pass  # staleness check is best-effort
        logger.debug("静默异常: %s", e)

    _quote_cache[cache_key] = (now, result)
    return result


# ============ yfinance 内部封装 ============

def _yfinance_get_quote(symbol: str) -> dict:
    """yfinance 行情查询 (内部使用) — 走缓存层"""
    return _cached_yfinance_get_quote(symbol)


def _yfinance_get_quote_raw(symbol: str) -> dict:
    """yfinance 行情查询 (原始网络调用, 无缓存)"""
    yf = _ensure_yfinance()
    try:
        ticker = yf.Ticker(symbol)
        hist = ticker.history(period="5d")

        if hist.empty:
            return {"error": f"找不到 {symbol} 的行情数据"}

        info = {}
        try:
            info = ticker.info
        except Exception as e:
            logger.debug("Silenced exception", exc_info=True)

        last_close = hist["Close"].iloc[-1]
        prev_close = hist["Close"].iloc[-2] if len(hist) > 1 else last_close
        change = last_close - prev_close
        change_pct = (change / prev_close) * 100 if prev_close else 0

        # Track the last trade date for staleness detection
        last_trade_date = None
        try:
            last_trade_date = hist.index[-1].date()
        except Exception as e:
            logger.debug("静默异常: %s", e)

        return {
            "symbol": symbol.upper(),
            "name": info.get("shortName", symbol),
            "price": round(float(last_close), 2),
            "change": round(float(change), 2),
            "change_pct": round(float(change_pct), 2),
            "volume": int(hist["Volume"].iloc[-1]) if "Volume" in hist else 0,
            "high": round(float(hist["High"].iloc[-1]), 2),
            "low": round(float(hist["Low"].iloc[-1]), 2),
            "market_cap": info.get("marketCap", 0),
            "pe_ratio": info.get("trailingPE", 0),
            "52w_high": info.get("fiftyTwoWeekHigh", 0),
            "52w_low": info.get("fiftyTwoWeekLow", 0),
            "currency": info.get("currency", "USD"),
            "market": Market.US.value,
            "_last_trade_date": last_trade_date,
        }
    except Exception as e:
        return {"error": f"查询 {symbol} 失败: {e}"}


def _yfinance_get_history(symbol: str, period: str = "3mo",
                          interval: str = "1d") -> "pd.DataFrame":
    """yfinance 历史K线 (内部使用)"""
    yf = _ensure_yfinance()
    ticker = yf.Ticker(symbol)
    df = ticker.history(period=period, interval=interval)
    if df is None or df.empty:
        raise ValueError(f"{symbol} 无历史数据")
    return df


# ============ 统一异步接口 ============

async def get_quote(symbol: str) -> dict:
    """统一行情查询 (异步) — asyncio.to_thread 包装"""
    return await asyncio.to_thread(get_quote_sync, symbol)


async def get_history(symbol: str, period: str = "3mo",
                      interval: str = "1d") -> "pd.DataFrame":
    """统一历史K线查询 (异步) — asyncio.to_thread 包装"""
    return await asyncio.to_thread(get_history_sync, symbol, period, interval)
