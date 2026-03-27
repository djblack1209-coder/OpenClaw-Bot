"""
OpenClaw — free-api.com 公共 API 集成
搬运自 fangzesheng/free-api (16k⭐) 中最有价值的接口。

零成本、零依赖：全部免费公开 API，不需要 key。

集成的功能:
  1. 天气预报（多城市、七日预报）
  2. 多源热榜（百度、知乎、头条、B站、抖音）
  3. 实时汇率
  4. 油价查询
  5. 快递查询

用法:
    weather = await get_weather("杭州")
    trending = await get_multi_trending()
"""
import logging
from typing import Dict, List

import httpx

logger = logging.getLogger(__name__)

_BASE = "https://api.pearktrue.cn/api"  # free-api.com 主域名备用
_TIMEOUT = 10.0
_HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}


# ── 天气 ──────────────────────────────────────────

# 天气描述翻译（wttr.in返回英文）
_WEATHER_DESC_ZH = {
    "Clear": "晴", "Sunny": "晴天", "Partly cloudy": "多云", "Cloudy": "阴天",
    "Overcast": "阴天", "Mist": "薄雾", "Fog": "大雾", "Freezing fog": "冻雾",
    "Light rain": "小雨", "Moderate rain": "中雨", "Heavy rain": "大雨",
    "Light drizzle": "小毛雨", "Drizzle": "毛毛雨", "Freezing drizzle": "冻雨",
    "Light snow": "小雪", "Moderate snow": "中雪", "Heavy snow": "大雪", "Blizzard": "暴风雪",
    "Thundery outbreaks": "雷阵雨", "Patchy rain": "局部小雨",
    "Torrential rain shower": "暴雨", "Light sleet": "雨夹雪",
    "Light rain shower": "小阵雨", "Moderate or heavy rain shower": "大阵雨",
}

def _translate_weather(desc: str) -> str:
    for en, zh in _WEATHER_DESC_ZH.items():
        if en.lower() in desc.lower():
            return zh
    return desc


async def get_weather(city: str) -> Dict:
    """获取城市天气预报（3日）— 使用 wttr.in（完全免费无 key）"""
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as c:
            r = await c.get(f"https://wttr.in/{city}?format=j1", headers=_HEADERS)
            if r.status_code == 200:
                d = r.json()
                cur = d.get("current_condition", [{}])[0]
                forecasts = d.get("weather", [])
                return {
                    "source": "wttr.in",
                    "city": city,
                    "current": {
                        "temp": cur.get("temp_C", ""),
                        "weather": _translate_weather(cur.get("weatherDesc", [{}])[0].get("value", "")),
                        "humidity": cur.get("humidity", ""),
                        "wind": cur.get("windspeedKmph", ""),
                    },
                    "forecasts": [
                        {
                            "date": f.get("date", ""),
                            "dayweather": _translate_weather(f.get("hourly", [{}])[4].get("weatherDesc", [{}])[0].get("value", "")) if len(f.get("hourly", [])) > 4 else "",
                            "nighttemp": f.get("mintempC", ""),
                            "daytemp": f.get("maxtempC", ""),
                        }
                        for f in forecasts[:4]
                    ],
                }
    except Exception as e:
        logger.debug(f"wttr.in 天气失败: {e}")
    return {"source": "error", "city": city, "note": "天气服务暂不可用"}


# ── 多源热榜 ──────────────────────────────────────

async def get_multi_trending() -> List[Dict]:
    """从多个平台获取热榜（并行）"""
    async with httpx.AsyncClient(timeout=_TIMEOUT, headers=_HEADERS) as c:
        tasks = [
            _fetch_baidu_trending(c),
            _fetch_toutiao_trending(c),
            _fetch_bilibili_trending(c),
        ]
        import asyncio
        results = await asyncio.gather(*tasks, return_exceptions=True)

    all_topics = []
    for r in results:
        if isinstance(r, list):
            all_topics.extend(r)

    return all_topics


async def _fetch_baidu_trending(c: httpx.AsyncClient) -> List[Dict]:
    """百度热搜"""
    try:
        r = await c.get("https://top.baidu.com/api/board?platform=wise&tab=realtime")
        if r.status_code == 200:
            d = r.json()
            cards = d.get("data", {}).get("cards", [])
            items = []
            if cards:
                content = cards[0].get("content", [])
                if content and isinstance(content[0], dict) and "content" in content[0]:
                    items = content[0].get("content", [])
                else:
                    items = content
            return [{"title": it.get("word", ""), "source": "baidu", "hot": it.get("hotScore", 0)}
                    for it in items[:15] if it.get("word")]
    except Exception as e:
        logger.debug(f"百度热搜失败: {e}")
    return []


async def _fetch_toutiao_trending(c: httpx.AsyncClient) -> List[Dict]:
    """今日头条热榜"""
    try:
        r = await c.get("https://www.toutiao.com/hot-event/hot-board/?origin=toutiao_pc&_signature=_02B4Z6wo00f01")
        if r.status_code == 200:
            d = r.json()
            items = d.get("data", [])
            return [{"title": it.get("Title", ""), "source": "toutiao", "hot": it.get("HotValue", 0)}
                    for it in items[:15] if it.get("Title")]
    except Exception as e:
        logger.debug(f"头条热榜失败: {e}")
    return []


async def _fetch_bilibili_trending(c: httpx.AsyncClient) -> List[Dict]:
    """B站热搜"""
    try:
        r = await c.get("https://app.bilibili.com/x/v2/search/trending/ranking")
        if r.status_code == 200:
            d = r.json()
            items = d.get("data", {}).get("list", [])
            return [{"title": it.get("keyword", ""), "source": "bilibili", "hot": it.get("heat_score", 0)}
                    for it in items[:15] if it.get("keyword")]
    except Exception as e:
        logger.debug(f"B站热搜失败: {e}")
    return []


# ── 汇率 ──────────────────────────────────────────

async def get_exchange_rate(from_currency: str = "USD", to_currency: str = "CNY") -> Dict:
    """实时汇率查询"""
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as c:
            r = await c.get(f"https://open.er-api.com/v6/latest/{from_currency}")
            if r.status_code == 200:
                d = r.json()
                rate = d.get("rates", {}).get(to_currency, 0)
                return {"from": from_currency, "to": to_currency, "rate": rate,
                        "time": d.get("time_last_update_utc", "")}
    except Exception as e:
        logger.debug(f"汇率查询失败: {e}")
    return {"from": from_currency, "to": to_currency, "rate": 0, "error": "查询失败"}


# ── IP 查询 ──────────────────────────────────────

# ── 快递查询 ──────────────────────────────────────

async def query_express(tracking_number: str) -> str:
    """快递单号查询 — 自动识别快递公司

    使用公开 API 查询快递物流轨迹，返回格式化文本。
    """
    if not tracking_number or not tracking_number.strip():
        return "请提供快递单号"
    tracking_number = tracking_number.strip()
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT, headers=_HEADERS) as c:
            # 使用 kuaidi100 免费查询接口（自动识别快递公司）
            r = await c.get(
                f"https://api.pearktrue.cn/api/express/",
                params={"number": tracking_number},
            )
            if r.status_code == 200:
                d = r.json()
                if d.get("code") == 200 or d.get("status") == 200:
                    company = d.get("company", d.get("com", "未知快递"))
                    state_map = {"0": "运输中", "1": "揽收", "2": "疑难", "3": "已签收",
                                 "4": "退签", "5": "派件中", "6": "退回"}
                    state = state_map.get(str(d.get("state", "")), str(d.get("state", "查询中")))
                    lines = [f"📦 快递: {company}", f"📋 单号: {tracking_number}", f"📌 状态: {state}", ""]
                    traces = d.get("data", d.get("traces", []))
                    if isinstance(traces, list):
                        for item in traces[:8]:
                            time_str = item.get("time", item.get("ftime", ""))
                            context_str = item.get("context", item.get("content", ""))
                            if context_str:
                                lines.append(f"  🕐 {time_str}")
                                lines.append(f"     {context_str}")
                    return "\n".join(lines) if len(lines) > 4 else f"📦 {company} | {tracking_number} | {state}\n暂无详细物流信息"
                else:
                    msg = d.get("msg", d.get("message", ""))
                    return f"📦 单号 {tracking_number} 查询失败: {msg or '未找到物流信息'}"
    except Exception as e:
        logger.debug(f"快递查询失败: {e}")
    return f"📦 单号 {tracking_number} 查询失败，请稍后再试"


async def get_ip_info(ip: str = "") -> Dict:
    """IP 归属地查询"""
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as c:
            url = f"https://ipinfo.io/{ip}/json" if ip else "https://ipinfo.io/json"
            r = await c.get(url)
            if r.status_code == 200:
                return r.json()
    except Exception as e:
        logger.debug(f"IP查询失败: {e}")
    return {"error": "查询失败"}
