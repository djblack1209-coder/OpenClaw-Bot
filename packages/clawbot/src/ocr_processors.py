"""
OCR 场景处理器 — 将 OCR 文字转化为业务决策

两条核心链路：
1. Financial: OCR → LLM 提取指标 → 注入 SharedMemory → 自动触发 /invest
2. Ecommerce: OCR → LLM 提取竞品数据 → 对比闲鱼商品 → 生成调价建议

核心升级（vs v1 正则版）：
- 用免费 LLM（SiliconFlow）做结构化提取，替代正则匹配
- 财报场景自动触发 6-bot 投资分析链（零命令）
- 电商场景对接闲鱼实际商品数据
- OCR 结果注入对话上下文（可追问）
"""
import re
import time
import logging
from typing import Optional, Dict, Any, List
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class ProcessorResult:
    """场景处理器返回结果"""
    success: bool
    summary: str
    action_taken: str
    data: Dict[str, Any]
    next_step: Optional[str] = None
    auto_invest_topic: Optional[str] = None   # 非空时自动触发 /invest
    context_injection: Optional[str] = None   # 注入对话上下文（可追问）


# ── LLM 结构化提取 ──────────────────────────────────────────────

_FINANCIAL_EXTRACT_PROMPT = """你是一个金融数据提取专家。从以下 OCR 文字中提取关键信息，返回 JSON。

OCR 文字:
{ocr_text}

请提取并返回以下 JSON 格式（只返回 JSON，不要其他文字）:
```json
{{
  "symbols": ["NVDA", "AAPL"],
  "company_names": ["英伟达", "苹果"],
  "prices": {{"NVDA": 135.5}},
  "changes_pct": {{"NVDA": "+12.5%"}},
  "key_metrics": {{"营收": "260亿", "净利润": "148亿"}},
  "signals": ["突破前高", "放量上涨"],
  "source": "同花顺/雪球/东方财富/其他",
  "time_context": "2026Q1财报/日K线/实时行情",
  "one_line_summary": "一句话总结这张图的核心信息"
}}
```
如果某个字段无法提取，留空数组或空字符串。symbols 用美股代码。"""

_ECOMMERCE_EXTRACT_PROMPT = """你是一个电商数据分析专家。从以下 OCR 文字中提取竞品信息，返回 JSON。

OCR 文字:
{ocr_text}

请提取并返回以下 JSON 格式（只返回 JSON，不要其他文字）:
```json
{{
  "products": [
    {{
      "title": "商品标题",
      "price": 99.0,
      "original_price": 199.0,
      "sales": 500,
      "reviews": 120,
      "platform": "闲鱼/淘宝/拼多多"
    }}
  ],
  "price_range": {{"min": 59, "max": 299, "avg": 150}},
  "market_signals": ["价格战激烈", "高销量低价"],
  "category": "商品类目",
  "one_line_summary": "一句话总结竞品格局"
}}
```
如果某个字段无法提取，留空。价格用数字，不带符号。"""


async def _llm_extract(prompt: str, ocr_text: str) -> Optional[Dict]:
    """调用 LLM 做结构化提取 — 走 LiteLLM Router"""
    try:
        from src.litellm_router import free_pool
        filled_prompt = prompt.format(ocr_text=ocr_text[:2000])
        response = await free_pool.acompletion(
            model_family="qwen",
            messages=[{"role": "user", "content": filled_prompt}],
            temperature=0.1,
            max_tokens=1000,
        )
        content = response.choices[0].message.content or ""
        from json_repair import loads as jloads
        json_match = re.search(r'```json\s*(.*?)\s*```', content, re.DOTALL)
        if json_match:
            return jloads(json_match.group(1))
        content = content.strip()
        if content.startswith("{"):
            return jloads(content)
        return None
    except Exception as e:
        logger.warning(f"[OCR LLM] 提取失败: {e}")
        return None


# ── 正则兜底（LLM 失败时）──────────────────────────────────────

def _regex_extract_financial(ocr_text: str) -> Dict[str, Any]:
    """正则兜底提取"""
    symbols = re.findall(r'\b([A-Z]{2,5})\b', ocr_text)
    known = {"AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA", "AMD",
             "BTC", "ETH", "SPY", "QQQ", "BABA", "JD", "PDD", "NIO", "TSM",
             "CRM", "ORCL", "ADBE", "QCOM", "AVGO", "NFLX", "INTC", "XPEV", "LI"}
    pcts = re.findall(r'([+-]?\d+\.?\d*)%', ocr_text)
    return {
        "symbols": list(dict.fromkeys(s for s in symbols if s in known))[:5],
        "changes_pct": {f"item_{i}": p for i, p in enumerate(pcts[:5])},
        "one_line_summary": f"检测到 {len(pcts)} 个涨跌幅数据",
    }


def _regex_extract_ecommerce(ocr_text: str) -> Dict[str, Any]:
    """正则兜底提取"""
    prices_raw = re.findall(r'(?:¥|￥)\s*(\d+\.?\d*)', ocr_text)
    prices_raw += re.findall(r'(\d+\.?\d*)\s*元', ocr_text)
    prices = sorted(set(float(p) for p in prices_raw if 0 < float(p) < 100000))
    sales = re.findall(r'(?:月销|已售|销量)\s*(\d+)', ocr_text)
    return {
        "price_range": {"min": prices[0], "max": prices[-1], "avg": sum(prices)/len(prices)} if prices else {},
        "products": [],
        "market_signals": [],
        "one_line_summary": f"检测到 {len(prices)} 个价格, {len(sales)} 个销量数据",
    }


# ── Financial Scene Processor ────────────────────────────────────

async def process_financial_scene(
    ocr_text: str,
    caption: str,
    user_id: int,
    chat_id: int,
    shared_memory,
) -> ProcessorResult:
    """
    处理交易/财报场景：
    1. LLM 智能提取指标（兜底正则）
    2. 写入 SharedMemory
    3. 自动触发 /invest（如果识别到股票代码）
    """
    # LLM 提取，失败则正则兜底
    data = await _llm_extract(_FINANCIAL_EXTRACT_PROMPT, ocr_text)
    if not data or not data.get("symbols"):
        data = _regex_extract_financial(ocr_text)

    symbols = data.get("symbols", [])
    summary_line = data.get("one_line_summary", "")

    if not symbols and not data.get("changes_pct"):
        return ProcessorResult(
            success=False, summary="未识别到有效的财务指标",
            action_taken="none", data={})

    # 构建摘要
    parts = []
    if symbols:
        parts.append(f"标的: {', '.join(symbols[:5])}")
    if data.get("key_metrics"):
        metrics_str = ", ".join(f"{k}={v}" for k, v in list(data["key_metrics"].items())[:3])
        parts.append(metrics_str)
    if data.get("signals"):
        parts.append(f"信号: {', '.join(data['signals'][:3])}")
    if summary_line:
        parts.append(summary_line)
    summary = " | ".join(parts)

    # 写入 SharedMemory
    action = "提取完成"
    try:
        ts = time.strftime("%m/%d %H:%M")
        shared_memory.remember(
            key=f"ocr_financial_{ts}",
            value=f"OCR财务文档\n{summary}\n原文: {ocr_text[:400]}",
            category="general", source_bot="ocr_processor",
            chat_id=chat_id, importance=2, ttl_hours=48)
        action = "已保存到记忆"
    except Exception as e:
        logger.error(f"[OCR Financial] SharedMemory: {e}")

    # 自动触发 /invest
    auto_topic = None
    if symbols:
        auto_topic = " ".join(symbols[:3])

    # 注入对话上下文（可追问）
    context_text = f"[OCR财务文档] {summary}\n原文摘要: {ocr_text[:500]}"

    return ProcessorResult(
        success=True,
        summary=f"📊 {summary}",
        action_taken=action,
        data=data,
        next_step=f"已自动触发投资分析: {auto_topic}" if auto_topic else None,
        auto_invest_topic=auto_topic,
        context_injection=context_text,
    )


# ── Ecommerce Scene Processor ───────────────────────────────────

async def process_ecommerce_scene(
    ocr_text: str,
    caption: str,
    user_id: int,
    chat_id: int,
    shared_memory,
) -> ProcessorResult:
    """
    处理电商/竞品场景：
    1. LLM 智能提取竞品数据（兜底正则）
    2. 写入 SharedMemory
    3. 生成定价建议
    """
    data = await _llm_extract(_ECOMMERCE_EXTRACT_PROMPT, ocr_text)
    if not data or (not data.get("products") and not data.get("price_range")):
        data = _regex_extract_ecommerce(ocr_text)

    price_range = data.get("price_range", {})
    products = data.get("products", [])
    summary_line = data.get("one_line_summary", "")

    if not price_range and not products:
        return ProcessorResult(
            success=False, summary="未识别到有效的商品/价格信息",
            action_taken="none", data={})

    # 构建摘要
    parts = []
    if price_range:
        parts.append(f"价格: ¥{price_range.get('min', '?')} ~ ¥{price_range.get('max', '?')} (均价¥{price_range.get('avg', '?'):.0f})" if isinstance(price_range.get('avg'), (int, float)) else f"价格区间: {price_range}")
    if products:
        parts.append(f"竞品数: {len(products)}")
        top = products[0]
        if top.get("platform"):
            parts.append(f"平台: {top['platform']}")
    if data.get("market_signals"):
        parts.append(f"信号: {', '.join(data['market_signals'][:2])}")
    if data.get("category"):
        parts.append(f"类目: {data['category']}")
    if summary_line:
        parts.append(summary_line)
    summary = " | ".join(parts)

    # 生成定价建议（LLM 数据 + 规则引擎）
    pricing = _generate_pricing_advice(price_range, products, data.get("market_signals", []))

    # 写入 SharedMemory
    action = "提取完成"
    try:
        ts = time.strftime("%m/%d %H:%M")
        shared_memory.remember(
            key=f"ocr_ecommerce_{ts}",
            value=f"OCR竞品信息\n{summary}\n定价建议: {pricing}\n原文: {ocr_text[:300]}",
            category="general", source_bot="ocr_processor",
            chat_id=chat_id, importance=2, ttl_hours=48)
        action = "已保存到记忆"
    except Exception as e:
        logger.error(f"[OCR Ecommerce] SharedMemory: {e}")

    context_text = f"[OCR竞品分析] {summary}\n定价建议: {pricing}\n原文摘要: {ocr_text[:500]}"

    return ProcessorResult(
        success=True,
        summary=f"🛒 {summary}",
        action_taken=action,
        data=data,
        next_step=pricing,
        context_injection=context_text,
    )


def _generate_pricing_advice(
    price_range: Dict, products: List[Dict], signals: List[str]
) -> str:
    """基于 LLM 提取的结构化数据生成定价建议"""
    if not price_range:
        if not products:
            return "数据不足"
        prices = [p["price"] for p in products if p.get("price")]
        if not prices:
            return "数据不足"
        price_range = {"min": min(prices), "max": max(prices), "avg": sum(prices)/len(prices)}

    avg = price_range.get("avg", 0)
    mn = price_range.get("min", 0)
    mx = price_range.get("max", 0)

    if not avg or avg <= 0:
        return "价格数据异常"

    parts = []
    spread = (mx - mn) / avg * 100 if avg > 0 else 0

    if spread > 50:
        parts.append(f"价差大({spread:.0f}%)，差异化定价空间充足")
    elif spread > 20:
        parts.append(f"价差适中({spread:.0f}%)，建议中间偏低定位")
    else:
        parts.append(f"价格集中({spread:.0f}%)，需要价格竞争力或差异化卖点")

    # 高销量竞品分析
    if products:
        high_sales = [p for p in products if p.get("sales", 0) > 50]
        if high_sales:
            priced = [p for p in high_sales if p.get("price")]
            avg_high = sum(p["price"] for p in priced) / len(priced) if priced else 0
            parts.append(f"高销量竞品均价¥{avg_high:.0f}")

    # 具体建议
    suggested = avg * 0.85 if spread < 30 else avg * 0.92
    parts.append(f"建议定价: ¥{suggested:.0f}")

    return " | ".join(parts)
