"""
ClawBot 超短线技术分析引擎 v1.0
- RSI / MACD / 布林带 / VWAP / EMA / ATR
- 成交量异动检测
- 支撑位阻力位自动识别
- 综合信号评分 (-100 到 +100)
- 超短线扫描器：盘前异动 / 放量突破 / 关键位突破
"""
import asyncio
import logging
import time as _time
from typing import Dict, List, Optional, Tuple
from datetime import datetime

logger = logging.getLogger(__name__)

# ============ 技术指标计算 ============

def compute_indicators(df) -> dict:
    """计算全套超短线技术指标，输入pandas DataFrame(OHLCV)"""
    import ta
    import numpy as np

    if df is None or len(df) < 20:
        return {"error": "数据不足，至少需要20根K线"}

    close = df['Close']
    high = df['High']
    low = df['Low']
    volume = df['Volume'] if 'Volume' in df.columns else None

    result = {}

    # --- 趋势指标 ---
    # EMA 5/10/20/50
    for period in [5, 10, 20, 50]:
        ema = ta.trend.EMAIndicator(close, window=period)
        result[f'ema_{period}'] = round(float(ema.ema_indicator().iloc[-1]), 4)

    # MACD (12, 26, 9)
    import math
    macd = ta.trend.MACD(close, window_slow=26, window_fast=12, window_sign=9)
    macd_val = macd.macd().iloc[-1]
    macd_sig = macd.macd_signal().iloc[-1]
    macd_diff = macd.macd_diff().iloc[-1]
    result['macd'] = round(float(macd_val), 4) if not math.isnan(macd_val) else 0
    result['macd_signal'] = round(float(macd_sig), 4) if not math.isnan(macd_sig) else 0
    result['macd_hist'] = round(float(macd_diff), 4) if not math.isnan(macd_diff) else 0
    # MACD柱状图方向
    hist_series = macd.macd_diff().dropna()
    if len(hist_series) >= 2:
        result['macd_hist_rising'] = bool(hist_series.iloc[-1] > hist_series.iloc[-2])

    # --- 动量指标 ---
    # RSI (14)
    rsi = ta.momentum.RSIIndicator(close, window=14)
    result['rsi_14'] = round(float(rsi.rsi().iloc[-1]), 2)
    # RSI (6) 超短线
    rsi6 = ta.momentum.RSIIndicator(close, window=6)
    result['rsi_6'] = round(float(rsi6.rsi().iloc[-1]), 2)

    # Stochastic RSI
    stoch_rsi = ta.momentum.StochRSIIndicator(close, window=14, smooth1=3, smooth2=3)
    result['stoch_rsi_k'] = round(float(stoch_rsi.stochrsi_k().iloc[-1]), 2)
    result['stoch_rsi_d'] = round(float(stoch_rsi.stochrsi_d().iloc[-1]), 2)

    # --- 波动率指标 ---
    # 布林带 (20, 2)
    bb = ta.volatility.BollingerBands(close, window=20, window_dev=2)
    result['bb_upper'] = round(float(bb.bollinger_hband().iloc[-1]), 4)
    result['bb_middle'] = round(float(bb.bollinger_mavg().iloc[-1]), 4)
    result['bb_lower'] = round(float(bb.bollinger_lband().iloc[-1]), 4)
    result['bb_width'] = round(float(bb.bollinger_wband().iloc[-1]), 4)
    # 价格在布林带中的位置 (0=下轨, 1=上轨)
    bb_range = result['bb_upper'] - result['bb_lower']
    if bb_range > 0:
        result['bb_position'] = round((float(close.iloc[-1]) - result['bb_lower']) / bb_range, 2)
    else:
        result['bb_position'] = 0.5

    # ATR (14) - 平均真实波幅
    atr = ta.volatility.AverageTrueRange(high, low, close, window=14)
    result['atr_14'] = round(float(atr.average_true_range().iloc[-1]), 4)
    # ATR百分比
    price = float(close.iloc[-1])
    result['atr_pct'] = round(result['atr_14'] / price * 100, 2) if price > 0 else 0

    # --- ADX (趋势强度) ---
    if len(df) >= 20:
        adx_indicator = ta.trend.ADXIndicator(high, low, close, window=14)
        adx_val = adx_indicator.adx().iloc[-1]
        result['adx'] = round(float(adx_val), 2) if not math.isnan(adx_val) else 0
        adx_pos = adx_indicator.adx_pos().iloc[-1]
        adx_neg = adx_indicator.adx_neg().iloc[-1]
        result['adx_pos'] = round(float(adx_pos), 2) if not math.isnan(adx_pos) else 0
        result['adx_neg'] = round(float(adx_neg), 2) if not math.isnan(adx_neg) else 0

    # --- 成交量指标 ---
    # P2#34: 均量排除当日不完整数据（用 iloc[-21:-1] 而非 tail(20)）
    if volume is not None and len(volume) >= 21:
        vol_now = float(volume.iloc[-1])
        vol_avg_20 = float(volume.iloc[-21:-1].mean())
        vol_avg_5 = float(volume.iloc[-6:-1].mean()) if len(volume) >= 6 else vol_avg_20
        result['volume'] = int(vol_now)
        result['vol_avg_20'] = int(vol_avg_20)
        result['vol_ratio'] = round(vol_now / vol_avg_20, 2) if vol_avg_20 > 0 else 0
        result['vol_ratio_5'] = round(vol_now / vol_avg_5, 2) if vol_avg_5 > 0 else 0
        # 放量判定: >1.5倍20日均量
        result['volume_surge'] = vol_now > vol_avg_20 * 1.5

        # OBV
        obv = ta.volume.OnBalanceVolumeIndicator(close, volume)
        obv_series = obv.on_balance_volume()
        result['obv'] = int(obv_series.iloc[-1])
        if len(obv_series) >= 2:
            result['obv_rising'] = bool(obv_series.iloc[-1] > obv_series.iloc[-2])

    # --- VWAP ---
    # 注意: VWAP 是日内指标，仅在日内数据(interval < 1d)时有意义
    # 日线级别的 VWAP 是整个周期的累积均价，不具备交易参考价值
    # 此处仍计算但标记 is_intraday，评分时不使用日线 VWAP
    if volume is not None and len(volume) > 0:
        typical_price = (high + low + close) / 3
        cum_tp_vol = (typical_price * volume).cumsum()
        cum_vol = volume.cumsum()
        vwap_series = cum_tp_vol / cum_vol
        result['vwap'] = round(float(vwap_series.iloc[-1]), 4)
        result['price_vs_vwap'] = round(price - result['vwap'], 4)

    # --- 价格位置 ---
    result['price'] = round(price, 4)
    if len(close) >= 5:
        result['high_5d'] = round(float(high.tail(5).max()), 4)
        result['low_5d'] = round(float(low.tail(5).min()), 4)
    if len(close) >= 20:
        result['high_20d'] = round(float(high.tail(20).max()), 4)
        result['low_20d'] = round(float(low.tail(20).min()), 4)

    # --- 趋势判定 ---
    result['trend'] = _judge_trend(result)

    return result


def _judge_trend(ind: dict) -> str:
    """根据EMA排列判定趋势"""
    ema5 = ind.get('ema_5', 0)
    ema10 = ind.get('ema_10', 0)
    ema20 = ind.get('ema_20', 0)
    ema50 = ind.get('ema_50', 0)
    if ema5 > ema10 > ema20 > ema50:
        return "strong_up"
    elif ema5 > ema10 > ema20:
        return "up"
    elif ema5 < ema10 < ema20 < ema50:
        return "strong_down"
    elif ema5 < ema10 < ema20:
        return "down"
    else:
        return "sideways"


# ============ 支撑位阻力位 ============

def find_support_resistance(df, n_levels: int = 3) -> dict:
    """自动识别支撑位和阻力位（基于近期高低点聚类）"""
    import numpy as np

    if df is None or len(df) < 20:
        return {"supports": [], "resistances": []}

    close = df['Close']
    high = df['High']
    low = df['Low']
    price = float(close.iloc[-1])

    # 收集近期高低点
    pivots = []
    for i in range(2, len(df) - 2):
        # 局部高点
        if float(high.iloc[i]) > float(high.iloc[i-1]) and float(high.iloc[i]) > float(high.iloc[i+1]):
            pivots.append(float(high.iloc[i]))
        # 局部低点
        if float(low.iloc[i]) < float(low.iloc[i-1]) and float(low.iloc[i]) < float(low.iloc[i+1]):
            pivots.append(float(low.iloc[i]))

    if not pivots:
        return {"supports": [], "resistances": []}

    # 简单聚类：按价格排序，合并相近的点
    pivots.sort()
    clusters = []
    current_cluster = [pivots[0]]
    threshold = price * 0.01  # 1%范围内合并

    for p in pivots[1:]:
        if p - current_cluster[-1] < threshold:
            current_cluster.append(p)
        else:
            clusters.append(np.mean(current_cluster))
            current_cluster = [p]
    clusters.append(np.mean(current_cluster))

    # 分为支撑和阻力
    supports = sorted([round(c, 2) for c in clusters if c < price], reverse=True)[:n_levels]
    resistances = sorted([round(c, 2) for c in clusters if c > price])[:n_levels]

    return {"supports": supports, "resistances": resistances}


# ============ 综合信号评分 ============

def _detect_regime(ind: dict) -> str:
    """检测市场状态: trending / ranging / volatile"""
    adx = ind.get('adx', 0)
    bb_width = ind.get('bb_width', 0)
    atr_pct = ind.get('atr_pct', 0)

    # 高波动 + 无趋势 = volatile
    if atr_pct > 3.0 and adx < 20:
        return "volatile"
    # ADX >= 25 = trending
    if adx >= 25:
        return "trending"
    # 布林带收窄 + 低ADX = ranging
    if bb_width > 0 and bb_width < 0.04 and adx < 25:
        return "ranging"
    return "ranging" if adx < 20 else "trending"


def compute_signal_score(ind: dict) -> dict:
    """
    综合评分 -100(强烈卖出) 到 +100(强烈买入)
    自适应市场状态：趋势市加重动量权重，震荡市加重均值回归权重
    返回: {"score": int, "signal": str, "reasons": [str], "regime": str}
    """
    score = 0
    reasons = []

    regime = _detect_regime(ind)

    # 权重因子：趋势市 vs 震荡市
    if regime == "trending":
        w_trend, w_momentum, w_reversion = 1.3, 1.2, 0.6
    elif regime == "volatile":
        w_trend, w_momentum, w_reversion = 0.7, 0.8, 0.5  # 高波动时全面降权
    else:  # ranging
        w_trend, w_momentum, w_reversion = 0.7, 0.8, 1.4

    # 1. RSI信号 (均值回归类)
    rsi = ind.get('rsi_14', 50)
    rsi6 = ind.get('rsi_6', 50)
    if rsi < 30:
        score += int(15 * w_reversion)
        reasons.append(f"RSI14={rsi:.0f} 超卖")
    elif rsi < 40:
        score += int(8 * w_reversion)
    elif rsi > 70:
        score -= int(15 * w_reversion)
        reasons.append(f"RSI14={rsi:.0f} 超买")
    elif rsi > 60:
        score -= int(5 * w_reversion)

    if rsi6 < 20:
        score += int(10 * w_reversion)
        reasons.append(f"RSI6={rsi6:.0f} 极度超卖")
    elif rsi6 > 80:
        score -= int(10 * w_reversion)
        reasons.append(f"RSI6={rsi6:.0f} 极度超买")

    # 2. MACD信号 (动量类)
    macd_hist = ind.get('macd_hist', 0)
    macd_rising = ind.get('macd_hist_rising', False)
    if macd_hist > 0 and macd_rising:
        score += int(15 * w_momentum)
        reasons.append("MACD金叉且柱状图扩大")
    elif macd_hist > 0:
        score += int(8 * w_momentum)
    elif macd_hist < 0 and not macd_rising:
        score -= int(15 * w_momentum)
        reasons.append("MACD死叉且柱状图扩大")
    elif macd_hist < 0:
        score -= int(8 * w_momentum)

    # 3. 趋势信号 (趋势类)
    trend = ind.get('trend', 'sideways')
    if trend == 'strong_up':
        score += int(20 * w_trend)
        reasons.append("EMA多头排列(强)")
    elif trend == 'up':
        score += int(12 * w_trend)
        reasons.append("EMA多头排列")
    elif trend == 'strong_down':
        score -= int(20 * w_trend)
        reasons.append("EMA空头排列(强)")
    elif trend == 'down':
        score -= int(12 * w_trend)
        reasons.append("EMA空头排列")

    # 4. 布林带信号 (均值回归类)
    bb_pos = ind.get('bb_position', 0.5)
    if bb_pos < 0.1:
        score += int(12 * w_reversion)
        reasons.append(f"触及布林下轨(位置{bb_pos:.0%})")
    elif bb_pos < 0.2:
        score += int(6 * w_reversion)
    elif bb_pos > 0.9:
        score -= int(12 * w_reversion)
        reasons.append(f"触及布林上轨(位置{bb_pos:.0%})")
    elif bb_pos > 0.8:
        score -= int(6 * w_reversion)

    # 5. 成交量信号 (动量类)
    vol_surge = ind.get('volume_surge', False)
    vol_ratio = ind.get('vol_ratio', 1.0)
    price = ind.get('price', 0)
    ema5 = ind.get('ema_5', 0)
    if vol_surge and price > ema5:
        score += int(15 * w_momentum)
        reasons.append(f"放量上涨(量比{vol_ratio:.1f}x)")
    elif vol_surge and price < ema5:
        score -= int(10 * w_momentum)
        reasons.append(f"放量下跌(量比{vol_ratio:.1f}x)")

    # 6. ADX趋势强度信号 (趋势类)
    adx = ind.get('adx', 0)
    if adx >= 40:
        if trend in ('strong_up', 'up'):
            score += int(10 * w_trend)
            reasons.append(f"ADX={adx:.0f} 强趋势+顺势")
        elif trend in ('strong_down', 'down'):
            score -= int(10 * w_trend)
            reasons.append(f"ADX={adx:.0f} 强趋势+逆势")
    elif adx >= 25:
        if trend in ('strong_up', 'up'):
            score += int(5 * w_trend)
        elif trend in ('strong_down', 'down'):
            score -= int(5 * w_trend)
    elif adx > 0 and adx < 20:
        score -= 3  # 轻微扣分，不再硬扣5分
        if regime == "ranging":
            reasons.append(f"ADX={adx:.0f} 震荡市(均值回归加权)")
        else:
            reasons.append(f"ADX={adx:.0f} 震荡市(信号弱)")

    # 7. StochRSI 背离检测（新增）
    stoch_k = ind.get('stoch_rsi_k', 50)
    stoch_d = ind.get('stoch_rsi_d', 50)
    if stoch_k < 20 and stoch_d < 20 and stoch_k > stoch_d:
        score += 5
        reasons.append("StochRSI超卖金叉")
    elif stoch_k > 80 and stoch_d > 80 and stoch_k < stoch_d:
        score -= 5
        reasons.append("StochRSI超买死叉")

    # 限制范围
    score = max(-100, min(100, score))

    # 信号判定
    if score >= 60:
        signal = "STRONG_BUY"
        signal_cn = "强烈买入"
    elif score >= 30:
        signal = "BUY"
        signal_cn = "买入"
    elif score >= 10:
        signal = "WEAK_BUY"
        signal_cn = "偏多"
    elif score <= -60:
        signal = "STRONG_SELL"
        signal_cn = "强烈卖出"
    elif score <= -30:
        signal = "SELL"
        signal_cn = "卖出"
    elif score <= -10:
        signal = "WEAK_SELL"
        signal_cn = "偏空"
    else:
        signal = "NEUTRAL"
        signal_cn = "中性"

    return {
        "score": score,
        "signal": signal,
        "signal_cn": signal_cn,
        "reasons": reasons,
        "regime": regime,
    }


# ============ 异步获取技术分析 ============

def _sync_full_analysis(symbol: str, period: str = "3mo", interval: str = "1d") -> dict:
    """同步获取完整技术分析（在线程池中执行）— 统一数据提供层，支持 US/CN_A/CRYPTO"""
    try:
        # 优先使用统一数据提供层 (自动检测 US/CN_A/CRYPTO)
        df = None
        try:
            from src.data_providers import get_history_sync, detect_market
            df = get_history_sync(symbol, period=period, interval=interval)
        except ImportError:
            # 回退到 yfinance-only
            pass

        if df is None:
            import yfinance as yf
            ticker = yf.Ticker(symbol)
            df = ticker.history(period=period, interval=interval)

        if df is None or df.empty or len(df) < 20:
            return {"error": f"{symbol} 数据不足(仅{len(df) if df is not None else 0}根K线)"}

        indicators = compute_indicators(df)
        if "error" in indicators:
            return indicators

        sr = find_support_resistance(df)
        signal = compute_signal_score(indicators)

        # 基本行情
        price = float(df['Close'].iloc[-1])
        prev_close = float(df['Close'].iloc[-2]) if len(df) > 1 else price
        change = price - prev_close
        change_pct = (change / prev_close * 100) if prev_close else 0

        # ticker.info (仅 yfinance 有效，其他市场跳过)
        name = symbol
        try:
            from src.data_providers import detect_market, Market
            market = detect_market(symbol)
            if market == Market.US:
                import yfinance as yf
                info = yf.Ticker(symbol).info
                name = info.get('shortName', symbol)
        except ImportError:
            # 无 data_providers，直接用 yfinance
            try:
                import yfinance as yf
                info = yf.Ticker(symbol).info
                name = info.get('shortName', symbol)
            except Exception as _info_err:
                logger.warning("[TA] %s ticker.info 获取失败(不影响分析): %s", symbol, _info_err)
        except Exception as _info_err:
            logger.warning("[TA] %s ticker.info 获取失败(不影响分析): %s", symbol, _info_err)

        return {
            "symbol": symbol.upper(),
            "name": name,
            "price": round(price, 2),
            "change": round(change, 2),
            "change_pct": round(change_pct, 2),
            "indicators": indicators,
            "support_resistance": sr,
            "signal": signal,
            "period": period,
            "interval": interval,
            "bars": len(df),
            # 原始价格序列 — 供 strategy_engine 等下游模块使用
            "closes": df['Close'].tolist(),
            "volumes": df['Volume'].tolist() if 'Volume' in df.columns else [],
        }
    except Exception as e:
        return {"error": f"{symbol} 技术分析失败: {e}"}


async def get_full_analysis(symbol: str, period: str = "1mo", interval: str = "1d") -> dict:
    """异步获取完整技术分析"""
    return await asyncio.to_thread(_sync_full_analysis, symbol, period, interval)


# ============ 超短线扫描器 ============

# 默认扫描列表 — 美股
SCAN_WATCHLIST = [
    "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA", "AMD",
    "NFLX", "AVGO", "CRM", "ORCL", "ADBE", "INTC", "QCOM",
    "BABA", "JD", "PDD", "NIO", "XPEV", "LI",
    "SPY", "QQQ", "IWM",
    "BTC-USD", "ETH-USD", "SOL-USD",
]

# A股扫描列表
SCAN_WATCHLIST_CN = [
    "000001", "600519", "000858", "601318", "600036",  # 大盘蓝筹
    "300750", "002594", "300059", "688981", "688012",  # 科技/新能源
]

# 加密货币扫描列表
SCAN_WATCHLIST_CRYPTO = [
    "BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT",
    "XRP/USDT", "ADA/USDT", "DOGE/USDT", "AVAX/USDT",
]


def _sync_scan_single(symbol: str) -> Optional[dict]:
    """扫描单个标的（同步）— 统一数据提供层，支持 US/CN_A/CRYPTO"""
    try:
        # 优先使用统一数据提供层
        df = None
        try:
            from src.data_providers import get_history_sync
            df = get_history_sync(symbol, period="3mo", interval="1d")
        except ImportError:
            pass

        if df is None:
            import yfinance as yf
            ticker = yf.Ticker(symbol)
            df = ticker.history(period="3mo", interval="1d")

        if df is None or df.empty or len(df) < 20:
            return None

        ind = compute_indicators(df)
        if "error" in ind:
            return None

        signal = compute_signal_score(ind)
        price = float(df['Close'].iloc[-1])
        prev = float(df['Close'].iloc[-2]) if len(df) > 1 else price
        change_pct = (price - prev) / prev * 100 if prev else 0

        # 只返回有信号的（score绝对值>=20 或 有异动）
        has_signal = abs(signal['score']) >= 20
        has_volume_surge = ind.get('volume_surge', False)
        has_extreme_rsi = ind.get('rsi_6', 50) < 25 or ind.get('rsi_6', 50) > 75

        if not (has_signal or has_volume_surge or has_extreme_rsi):
            return None

        return {
            "symbol": symbol.upper(),
            "price": round(price, 2),
            "change_pct": round(change_pct, 2),
            "score": signal['score'],
            "signal": signal['signal'],
            "signal_cn": signal['signal_cn'],
            "reasons": signal['reasons'],
            "rsi_6": ind.get('rsi_6', 0),
            "rsi_14": ind.get('rsi_14', 0),
            "vol_ratio": ind.get('vol_ratio', 0),
            "vol_avg_20": ind.get('vol_avg_20', 0),
            "volume_surge": ind.get('volume_surge', False),
            "trend": ind.get('trend', 'sideways'),
            "bb_position": ind.get('bb_position', 0.5),
            "atr_pct": ind.get('atr_pct', 0),
            "adx": ind.get('adx', 0),
        }
    except Exception as e:
        logger.debug(f"[Scan] {symbol} 扫描失败: {e}")
        return None


async def scan_market(symbols: List[str] = None) -> List[dict]:
    """并行扫描市场，返回有信号的标的列表（按score排序）"""
    if symbols is None:
        symbols = SCAN_WATCHLIST

    results = await asyncio.gather(
        *[asyncio.to_thread(_sync_scan_single, sym) for sym in symbols],
        return_exceptions=True
    )

    signals = []
    for r in results:
        if isinstance(r, dict) and r is not None:
            signals.append(r)

    # 按信号强度排序（绝对值大的在前）
    signals.sort(key=lambda x: abs(x['score']), reverse=True)
    return signals


# ============ 格式化输出 ============

def format_analysis(data: dict) -> str:
    """格式化完整技术分析为可读文本"""
    if "error" in data:
        return data["error"]

    ind = data.get("indicators", {})
    sr = data.get("support_resistance", {})
    sig = data.get("signal", {})

    arrow = "+" if data['change'] >= 0 else ""
    trend_map = {
        "strong_up": "强势上涨",
        "up": "上涨趋势",
        "sideways": "横盘震荡",
        "down": "下跌趋势",
        "strong_down": "强势下跌",
    }

    lines = [
        f"{data['name']} ({data['symbol']})",
        f"价格: ${data['price']} ({arrow}{data['change_pct']}%)",
        "",
        "-- 技术指标 --",
        f"趋势: {trend_map.get(ind.get('trend', ''), '未知')}",
        f"EMA: 5={ind.get('ema_5',0)} | 10={ind.get('ema_10',0)} | 20={ind.get('ema_20',0)}",
        f"RSI: 6={ind.get('rsi_6',0)} | 14={ind.get('rsi_14',0)}",
        f"MACD: {ind.get('macd',0)} | 信号线: {ind.get('macd_signal',0)} | 柱: {ind.get('macd_hist',0)}",
        f"布林带: 上={ind.get('bb_upper',0)} | 中={ind.get('bb_middle',0)} | 下={ind.get('bb_lower',0)}",
        f"布林位置: {ind.get('bb_position',0):.0%}",
        f"ATR(14): {ind.get('atr_14',0)} ({ind.get('atr_pct',0)}%)",
    ]

    if ind.get('vol_ratio'):
        vol_flag = " [放量!]" if ind.get('volume_surge') else ""
        lines.append(f"量比: {ind['vol_ratio']}x (20日){vol_flag}")

    if ind.get('vwap'):
        vs = "上方" if ind.get('price_vs_vwap', 0) > 0 else "下方"
        lines.append(f"VWAP: {ind['vwap']} (价格在{vs})")

    # 支撑阻力
    if sr.get('supports') or sr.get('resistances'):
        lines.append("")
        lines.append("-- 关键价位 --")
        if sr.get('resistances'):
            lines.append(f"阻力位: {' | '.join(str(r) for r in sr['resistances'])}")
        if sr.get('supports'):
            lines.append(f"支撑位: {' | '.join(str(s) for s in sr['supports'])}")

    # 信号
    lines.append("")
    lines.append("-- 交易信号 --")
    score = sig.get('score', 0)
    bar = _score_bar(score)
    lines.append(f"综合评分: {score:+d}/100 {bar}")
    lines.append(f"信号: {sig.get('signal_cn', '中性')}")
    if sig.get('reasons'):
        for r in sig['reasons']:
            lines.append(f"  - {r}")

    return "\n".join(lines)


def format_scan_results(signals: List[dict]) -> str:
    """格式化扫描结果"""
    if not signals:
        return "市场扫描完成\n\n暂无明显信号，市场平静。"

    lines = [f"市场扫描 ({len(signals)}个信号)\n"]

    buy_signals = [s for s in signals if s['score'] > 0]
    sell_signals = [s for s in signals if s['score'] < 0]

    if buy_signals:
        lines.append("-- 买入信号 --")
        for s in buy_signals[:8]:
            arrow = "+" if s['change_pct'] >= 0 else ""
            vol_flag = " [放量]" if s.get('volume_surge') else ""
            lines.append(
                f"{'*' if s['score']>=40 else ' '} {s['symbol']}: ${s['price']} "
                f"({arrow}{s['change_pct']}%) "
                f"评分:{s['score']:+d} RSI6:{s['rsi_6']:.0f}{vol_flag}"
            )
            if s.get('reasons'):
                lines.append(f"    {' | '.join(s['reasons'][:3])}")

    if sell_signals:
        lines.append("\n-- 卖出信号 --")
        for s in sell_signals[:8]:
            arrow = "+" if s['change_pct'] >= 0 else ""
            vol_flag = " [放量]" if s.get('volume_surge') else ""
            lines.append(
                f"{'*' if s['score']<=-40 else ' '} {s['symbol']}: ${s['price']} "
                f"({arrow}{s['change_pct']}%) "
                f"评分:{s['score']:+d} RSI6:{s['rsi_6']:.0f}{vol_flag}"
            )
            if s.get('reasons'):
                lines.append(f"    {' | '.join(s['reasons'][:3])}")

    lines.append(f"\n* = 强信号 | 扫描{len(SCAN_WATCHLIST)}个标的")
    return "\n".join(lines)


def _score_bar(score: int) -> str:
    """生成评分条"""
    normalized = (score + 100) / 200  # 0~1
    filled = int(normalized * 10)
    return "[" + "=" * filled + "-" * (10 - filled) + "]"


# ============ 仓位计算器 ============

def calc_position_size(capital: float, risk_pct: float, entry: float,
                       stop_loss: float) -> dict:
    """
    基于风险的仓位计算
    capital: 总资金
    risk_pct: 单笔风险比例 (如0.02 = 2%)
    entry: 入场价
    stop_loss: 止损价
    """
    risk_amount = capital * risk_pct
    risk_per_share = abs(entry - stop_loss)

    if risk_per_share <= 0:
        return {"error": "止损价不能等于入场价"}

    shares = int(risk_amount / risk_per_share)
    total_cost = shares * entry
    max_loss = shares * risk_per_share

    return {
        "shares": shares,
        "entry": entry,
        "stop_loss": stop_loss,
        "total_cost": round(total_cost, 2),
        "risk_amount": round(risk_amount, 2),
        "max_loss": round(max_loss, 2),
        "risk_pct": risk_pct,
        "risk_reward_note": f"风险${max_loss:.0f} (资金的{risk_pct*100:.1f}%)",
    }
