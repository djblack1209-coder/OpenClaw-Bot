"""
ClawBot 全市场标的池 v1.0
专业级交易标的管理 - 对标真实交易团队

标的池结构：
- S&P500 核心成分股 (按市值/流动性筛选前200)
- NASDAQ100 科技股
- 热门ETF (行业/主题/杠杆)
- 加密货币 Top20
- 中概股 ADR
- 总计 600+ 标的

多层筛选漏斗：
  全标的池 600+ → 流动性筛选 → 技术指标筛选 → 信号评分 → Top候选
"""
import asyncio
import logging
import os
import time
from typing import List, Dict, Optional
from src.utils import now_et

logger = logging.getLogger(__name__)

# ============ 标的池定义 ============

# S&P500 高流动性核心股（按行业分类，约200只）
SP500_CORE = [
    # 科技
    "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA", "AVGO", "ORCL", "CRM",
    "ADBE", "AMD", "INTC", "QCOM", "TXN", "AMAT", "LRCX", "KLAC", "MRVL", "SNPS",
    "CDNS", "FTNT", "PANW", "NOW", "INTU", "ISRG", "ADI", "MU", "NXPI", "MCHP",
    "ON", "MPWR", "SWKS", "KEYS", "CPRT", "CSGP", "PAYC", "EPAM", "AKAM",
    # 金融
    "JPM", "BAC", "WFC", "GS", "MS", "C", "BLK", "SCHW", "AXP", "USB",
    "PNC", "TFC", "COF", "BK", "STT", "FITB", "HBAN", "CFG", "KEY", "RF",
    "CME", "ICE", "SPGI", "MCO", "MSCI", "CBOE", "NDAQ", "FIS", "FISV", "GPN",
    # 医疗
    "UNH", "JNJ", "LLY", "PFE", "ABBV", "MRK", "TMO", "ABT", "DHR", "BMY",
    "AMGN", "GILD", "VRTX", "REGN", "MRNA", "BIIB", "ILMN", "DXCM", "IDXX", "ZTS",
    "SYK", "BDX", "MDT", "EW", "BSX", "HCA", "CI", "ELV", "HUM", "CNC",
    # 消费
    "WMT", "PG", "KO", "PEP", "COST", "MCD", "NKE", "SBUX", "TGT", "LOW",
    "HD", "TJX", "ROST", "DG", "DLTR", "YUM", "CMG", "DPZ", "EL",
    "CL", "KMB", "GIS", "HSY", "MNST", "STZ", "TAP", "BF-B", "PM",
    # 工业
    "CAT", "DE", "HON", "UNP", "UPS", "FDX", "BA", "RTX", "LMT", "NOC",
    "GD", "GE", "MMM", "EMR", "ETN", "ITW", "PH", "ROK", "SWK", "IR",
    # 能源
    "XOM", "CVX", "COP", "EOG", "SLB", "MPC", "PSX", "VLO", "OXY", "DVN",
    "HAL", "BKR", "FANG", "APA", "CTRA", "EQT", "OVV",
    # 通信
    "DIS", "NFLX", "CMCSA", "T", "VZ", "TMUS", "CHTR", "EA", "TTWO",
    "MTCH", "ZM", "SNAP", "PINS", "ROKU", "SPOT", "LYV", "WBD", "FOX",
    # 地产/公用
    "AMT", "PLD", "CCI", "EQIX", "PSA", "SPG", "O", "DLR", "WELL", "AVB",
    "NEE", "DUK", "SO", "D", "AEP", "SRE", "EXC", "XEL", "WEC", "ES",
    # 材料
    "LIN", "APD", "SHW", "ECL", "DD", "NEM", "FCX", "CTVA", "DOW", "NUE",
]

# 热门ETF（行业/主题/杠杆/反向）
ETFS = [
    # 大盘指数
    "SPY", "QQQ", "DIA", "IWM", "VOO", "VTI", "RSP",
    # 行业ETF
    "XLK", "XLF", "XLE", "XLV", "XLI", "XLC", "XLY", "XLP", "XLB", "XLU", "XLRE",
    "SMH", "SOXX", "IGV", "HACK", "ARKK", "ARKG", "ARKF", "ARKW",
    "XBI", "IBB", "XHB", "XRT", "KRE", "XOP", "OIH", "GDX", "GDXJ",
    # 主题ETF
    "TAN", "ICLN", "LIT", "DRIV", "BOTZ", "ROBO", "AIQ", "WCLD",
    # 杠杆/反向（超短线利器）
    "TQQQ", "SQQQ", "SPXL", "SPXS", "UPRO", "SDS", "TNA", "TZA",
    "SOXL", "SOXS", "LABU", "LABD", "FAS", "FAZ", "ERX", "ERY",
    "NUGT", "DUST", "JNUG", "JDST", "UVXY", "SVXY",
    # 债券/商品
    "TLT", "IEF", "SHY", "HYG", "LQD", "GLD", "SLV", "USO", "UNG",
]

# 加密货币 Top20
CRYPTO = [
    "BTC-USD", "ETH-USD", "SOL-USD", "BNB-USD", "XRP-USD",
    "ADA-USD", "DOGE-USD", "AVAX-USD", "DOT-USD",
    "LINK-USD", "ATOM-USD", "LTC-USD", "FIL-USD",
    "NEAR-USD", "ARB-USD", "OP-USD", "INJ-USD",
]

# 中概股 ADR
CHINA_ADR = [
    "BABA", "JD", "PDD", "NIO", "XPEV", "LI", "BIDU", "NTES", "TME", "BILI",
    "IQ", "FUTU", "TIGR", "ZH", "MNSO", "VNET", "YMM", "KC", "QFIN",
]

# 港股热门（通过IBKR可交易）
HK_STOCKS = [
    "9988.HK", "9618.HK", "3690.HK", "9999.HK", "1810.HK",
    "0700.HK", "9888.HK", "2318.HK", "0941.HK", "1211.HK",
    "2020.HK", "9961.HK", "1024.HK", "6060.HK", "0005.HK",
]


def get_full_universe() -> List[str]:
    """获取完整标的池（去重）"""
    all_symbols = SP500_CORE + ETFS + CRYPTO + CHINA_ADR + HK_STOCKS
    seen = set()
    result = []
    for s in all_symbols:
        if s not in seen:
            seen.add(s)
            result.append(s)
    return result


def get_universe_by_category() -> Dict[str, List[str]]:
    """按分类获取标的池"""
    return {
        "sp500_core": SP500_CORE,
        "etfs": ETFS,
        "crypto": CRYPTO,
        "china_adr": CHINA_ADR,
        "hk_stocks": HK_STOCKS,
    }


def get_universe_stats() -> str:
    """标的池统计"""
    full = get_full_universe()
    return (
        f"标的池统计\n\n"
        f"S&P500核心: {len(SP500_CORE)}\n"
        f"ETF: {len(ETFS)}\n"
        f"加密货币: {len(CRYPTO)}\n"
        f"中概ADR: {len(CHINA_ADR)}\n"
        f"港股: {len(HK_STOCKS)}\n"
        f"总计(去重): {len(full)}"
    )


# ============ 多层筛选漏斗 ============

_screen_cache: Dict[str, tuple] = {}  # cache_key -> (result, timestamp)
SCREEN_CACHE_TTL = 300  # 5分钟缓存


def _sync_quick_screen(symbol: str) -> Optional[dict]:
    """
    快速筛选单个标的（同步，在线程池执行）
    第一层：只看价格变动和成交量，淘汰无异动的
    """
    try:
        import yfinance as yf
        ticker = yf.Ticker(symbol)
        df = ticker.history(period="5d", interval="1d")
        if df is None or df.empty or len(df) < 2:
            return None

        price = float(df['Close'].iloc[-1])
        prev = float(df['Close'].iloc[-2])
        change_pct = (price - prev) / prev * 100 if prev else 0
        volume = float(df['Volume'].iloc[-1]) if 'Volume' in df.columns else 0
        avg_vol = float(df['Volume'].mean()) if 'Volume' in df.columns and len(df) >= 3 else volume

        # 第一层筛选条件（宽松，只淘汰完全没动静的）
        vol_ratio = volume / avg_vol if avg_vol > 0 else 0
        has_movement = abs(change_pct) > 1.0  # 涨跌超1%
        has_volume = vol_ratio > 1.2  # 量比超1.2

        if not (has_movement or has_volume):
            return None

        return {
            "symbol": symbol,
            "price": round(price, 2),
            "change_pct": round(change_pct, 2),
            "volume": int(volume),
            "vol_ratio": round(vol_ratio, 2),
        }
    except Exception as e:  # noqa: F841
        return None


async def full_market_scan(
    categories: Optional[List[str]] = None,
    max_workers: int = 20,
    top_n: int = 50,
    symbols: Optional[List[str]] = None,
) -> Dict:
    """
    全市场多层筛选漏斗

    层1: 快速筛选（价格变动+成交量）→ 淘汰80%无异动标的
    层2: 技术指标分析（RSI/MACD/布林带等）→ 精选有信号的
    层3: 信号评分排序 → 输出Top候选

    返回: {
        "total_scanned": int,
        "layer1_passed": int,
        "layer2_passed": int,
        "top_candidates": [dict],
        "scan_time": float,
        "timestamp": str,
    }
    """

    start_time = time.time()

    # 确定扫描范围
    universe = get_universe_by_category()
    if symbols:
        dedup = []
        seen = set()
        for sym in symbols:
            key = (sym or "").strip().upper()
            if not key or key in seen:
                continue
            seen.add(key)
            dedup.append(key)
        symbols = dedup
    elif categories:
        symbols = []
        for cat in categories:
            symbols.extend(universe.get(cat, []))
    else:
        symbols = get_full_universe()

    total = len(symbols)
    logger.info(f"[Scanner] 开始全市场扫描: {total} 个标的")

    # === 层1: 快速筛选（Semaphore 控制并发，比批次更高效） ===
    sem = asyncio.Semaphore(max_workers)
    layer1_passed = []

    async def _screen_one(sym: str):
        async with sem:
            return await asyncio.to_thread(_sync_quick_screen, sym)

    results = await asyncio.gather(
        *[_screen_one(sym) for sym in symbols],
        return_exceptions=True
    )
    for r in results:
        if isinstance(r, dict) and r is not None:
            layer1_passed.append(r)

    logger.info(f"[Scanner] 层1通过: {len(layer1_passed)}/{total}")

    # === 层2: 技术指标深度分析（只对层1通过的） ===
    from src.ta_engine import _sync_full_analysis
    layer2_results = []

    async def _analyze_one(item: dict):
        async with sem:
            return await asyncio.to_thread(_sync_full_analysis, item['symbol'])

    l2_results = await asyncio.gather(
        *[_analyze_one(item) for item in layer1_passed],
        return_exceptions=True
    )
    for item, r in zip(layer1_passed, l2_results):
            if isinstance(r, dict) and "error" not in r:
                sig = r.get("signal", {})
                score = sig.get("score", 0)
                if abs(score) >= 15:  # 有一定信号强度
                    _ind = r.get("indicators", {})
                    layer2_results.append({
                        **item,
                        "score": score,
                        "signal": sig.get("signal", "NEUTRAL"),
                        "signal_cn": sig.get("signal_cn", "中性"),
                        "reasons": sig.get("reasons", []),
                        "rsi_6": _ind.get("rsi_6", 50),
                        "rsi_14": _ind.get("rsi_14", 50),
                        "trend": _ind.get("trend", "sideways"),
                        "atr_pct": _ind.get("atr_pct", 0),
                        "bb_position": _ind.get("bb_position", 0.5),
                        "volume_surge": _ind.get("volume_surge", False),
                        "vol_avg_20": _ind.get("vol_avg_20", 0),
                        "adx": _ind.get("adx", 0),
                        "supports": r.get("support_resistance", {}).get("supports", []),
                        "resistances": r.get("support_resistance", {}).get("resistances", []),
                        "indicators": _ind,
                        # 保留完整分析数据，避免 pipeline 重复调用 get_full_analysis
                        "_full_analysis": r,
                    })

    logger.info(f"[Scanner] 层2通过: {len(layer2_results)}/{len(layer1_passed)}")

    # === 层3: 排序输出Top候选（加上限保护） ===
    layer2_results.sort(key=lambda x: abs(x['score']), reverse=True)
    final_top_n = max(5, int(top_n or 50))
    env_top_n = os.getenv("MAX_SCAN_CANDIDATES")
    if env_top_n:
        try:
            final_top_n = min(max(5, int(env_top_n)), 200)  # 上限200防止返回过多
        except ValueError as e:
            logger.debug("MAX_SCAN_CANDIDATES环境变量解析失败: %s", e)

    top_candidates = layer2_results[:final_top_n]

    scan_time = time.time() - start_time
    logger.info(
        f"[Scanner] 扫描完成: {scan_time:.1f}s, Top {len(top_candidates)} 候选"
    )

    return {
        "total_scanned": total,
        "layer1_passed": len(layer1_passed),
        "layer2_passed": len(layer2_results),
        "top_candidates": top_candidates,
        "buy_candidates": [c for c in top_candidates if c['score'] > 0],
        "sell_candidates": [c for c in top_candidates if c['score'] < 0],
        "scan_time": round(scan_time, 1),
        "timestamp": now_et().isoformat(),
    }


def format_full_scan(result: Dict) -> str:
    """格式化全市场扫描结果"""
    lines = [
        "全市场扫描报告",
        f"扫描: {result['total_scanned']}个标的 | "
        f"层1通过: {result['layer1_passed']} | "
        f"层2信号: {result['layer2_passed']} | "
        f"耗时: {result['scan_time']}s",
        "",
    ]

    buys = result.get("buy_candidates", [])
    sells = result.get("sell_candidates", [])

    if buys:
        lines.append("-- 买入机会 --")
        for c in buys[:10]:
            arrow = "+" if c['change_pct'] >= 0 else ""
            vol = " [放量]" if c.get('volume_surge') else ""
            star = "*" if abs(c['score']) >= 40 else " "
            lines.append(
                f"{star}{c['symbol']} ${c['price']} ({arrow}{c['change_pct']}%) "
                f"评分:{c['score']:+d} RSI6:{c['rsi_6']:.0f}{vol}"
            )
            if c.get('reasons'):
                lines.append(f"  {' | '.join(c['reasons'][:3])}")

    if sells:
        lines.append("\n-- 卖出/做空信号 --")
        for c in sells[:10]:
            arrow = "+" if c['change_pct'] >= 0 else ""
            vol = " [放量]" if c.get('volume_surge') else ""
            star = "*" if abs(c['score']) >= 40 else " "
            lines.append(
                f"{star}{c['symbol']} ${c['price']} ({arrow}{c['change_pct']}%) "
                f"评分:{c['score']:+d} RSI6:{c['rsi_6']:.0f}{vol}"
            )
            if c.get('reasons'):
                lines.append(f"  {' | '.join(c['reasons'][:3])}")

    if not buys and not sells:
        lines.append("暂无明显信号，市场平静。建议观望。")

    lines.append(f"\n* = 强信号(评分>=40) | 扫描时间: {result['timestamp'][:19]}")
    return "\n".join(lines)
