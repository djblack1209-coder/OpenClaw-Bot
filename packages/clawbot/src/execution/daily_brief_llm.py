"""
每日日报 — LLM 辅助分析模块

提供新闻分析、执行摘要、每日建议的 LLM 生成功能。
所有 LLM 调用均有 try/except 降级，确保日报不因 AI 失败中断。
"""

import logging
import re

from src.constants import FAMILY_QWEN

logger = logging.getLogger(__name__)


def _strip_think_tags(text: str) -> str:
    """去除 LLM 输出中的 <think>...</think> 推理标签（Qwen 等模型常带）"""
    return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()


async def _analyze_news_with_llm(headlines: list[str], holdings: list[str]) -> list[str]:
    """用最便宜的 LLM 对新闻标题做一句话分析 + 持仓影响关联。

    成本控制: 用免费的 qwen 模型，max_tokens=300，prompt 限制100字回复。
    失败时返回 None，由调用方降级到纯标题列表。
    """
    try:
        from src.litellm_router import free_pool

        if not free_pool:
            return None

        # 构建新闻列表文本
        news_text = "\n".join(f"{i + 1}. {t}" for i, t in enumerate(headlines))

        # 构建 prompt — 精简控制 token 成本
        holdings_part = ""
        if holdings:
            holdings_part = f"用户持有: {', '.join(holdings[:10])}\n"

        prompt = (
            f"你是金融新闻分析师。{holdings_part}"
            f"以下是今日科技新闻标题:\n{news_text}\n\n"
            f"请用中文，每条新闻一句话分析（15字以内），"
            f"标注对用户持仓的影响（利好/利空/中性）。"
            f"如果没有直接影响就标注中性。总共不超过100字。"
            f"格式: 每行一条，用 • 开头，影响用 → 标注。"
            f"直接输出分析结果，不要有推理过程或解释。"
        )

        resp = await free_pool.acompletion(
            model_family=FAMILY_QWEN,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=300,
            cache_ttl=1800,  # 缓存30分钟，避免重复调用
        )
        text = (resp.choices[0].message.content or "").strip()
        text = _strip_think_tags(text)

        if not text:
            return None

        # 解析 LLM 输出为行列表
        lines = [ln.strip() for ln in text.split("\n") if ln.strip() and not ln.strip().startswith("```")]
        if not lines:
            return None

        # 确保每行以 • 开头
        result = []
        for ln in lines:
            ln = ln.lstrip("- ·•*0123456789.、）)")
            ln = ln.strip()
            if ln:
                result.append(f"• {ln}")

        return result if result else None

    except Exception as e:
        logger.debug("[DailyBrief] LLM 新闻分析失败，降级到纯标题: %s", e)
        return None


async def _generate_executive_summary(sections_data: dict) -> str:
    """用 LLM 生成 2 句话的每日执行摘要。

    从各模块的关键指标中提炼当天全局态势。
    LLM 失败时降级为模板摘要，保证日报不中断。

    Args:
        sections_data: 包含 portfolio_pnl, xianyu_orders, social_posts 等关键指标的字典
    Returns:
        格式化的执行摘要文本，以「📊 今日概况」开头
    """
    # 提取关键指标用于 LLM prompt 和模板降级
    pnl = sections_data.get("portfolio_pnl", 0)
    pnl_label = f"浮盈${pnl:+,.2f}" if pnl >= 0 else f"浮亏${pnl:+,.2f}"
    xianyu_consult = sections_data.get("xianyu_consultations", 0)
    xianyu_orders = sections_data.get("xianyu_orders", 0)
    social_posts = sections_data.get("social_posts", 0)
    api_cost = sections_data.get("api_daily_cost", 0)
    market_sentiment = sections_data.get("market_sentiment", "")
    # 昨日对比 delta（如果有）
    deltas = sections_data.get("deltas", {})

    try:
        from src.litellm_router import free_pool

        if not free_pool:
            raise RuntimeError("free_pool 不可用")

        # 构建指标文本，只包含有数据的指标
        metrics_parts = []
        if pnl != 0:
            metrics_parts.append(f"投资组合{pnl_label}")
        if xianyu_consult > 0 or xianyu_orders > 0:
            metrics_parts.append(f"闲鱼咨询{xianyu_consult}条/下单{xianyu_orders}笔")
        if social_posts > 0:
            metrics_parts.append(f"社媒发帖{social_posts}篇")
        if api_cost > 0:
            metrics_parts.append(f"API日均成本${api_cost:.2f}")
        if market_sentiment:
            metrics_parts.append(f"市场情绪: {market_sentiment}")

        # delta 信息
        delta_parts = []
        for key, val in deltas.items():
            if val != 0:
                sign = "↑" if val > 0 else "↓"
                delta_parts.append(f"{key} {sign}{abs(val)}")

        metrics_text = "；".join(metrics_parts) if metrics_parts else "暂无数据"
        delta_text = f"\n趋势变化: {', '.join(delta_parts)}" if delta_parts else ""

        prompt = (
            f"你是一位私人财务管家。以下是用户今日的关键数据:\n"
            f"{metrics_text}{delta_text}\n\n"
            f"请用中文写 2 句话总结今天的整体状况。\n"
            f"第一句概括全局（好/坏/平稳），第二句点出最值得关注的一件事。\n"
            f"必须引用具体数字（如「市场情绪46偏恐惧」而非「市场情绪谨慎」）。\n"
            f"语气亲切简洁，不超过 80 字。不要加标题、emoji、推理过程。\n"
            f"直接输出 2 句话，不要有任何前缀或解释。"
        )

        resp = await free_pool.acompletion(
            model_family=FAMILY_QWEN,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.4,
            max_tokens=200,
            cache_ttl=1800,
        )
        text = (resp.choices[0].message.content or "").strip()
        text = _strip_think_tags(text)
        if text:
            return text

    except Exception as e:
        logger.debug("[DailyBrief] 执行摘要 LLM 调用失败，降级为模板: %s", e)

    # 降级: 模板摘要 — 不依赖 LLM
    parts = []
    if pnl != 0:
        trend = "盈利" if pnl > 0 else "亏损"
        parts.append(f"投资组合今日{trend} ${abs(pnl):,.2f}")
    if xianyu_orders > 0:
        parts.append(f"闲鱼成交 {xianyu_orders} 单")
    if not parts:
        parts.append("各项业务运行平稳")
    summary = "，".join(parts) + "。"

    # 第二句: 找最值得关注的指标
    attention = ""
    pnl_delta = deltas.get("持仓盈亏", 0)
    if abs(pnl_delta) > 100:
        direction = "上升" if pnl_delta > 0 else "下降"
        attention = f"持仓盈亏较昨日{direction} ${abs(pnl_delta):,.0f}，需留意。"
    elif xianyu_consult > 10:
        attention = f"闲鱼咨询量 {xianyu_consult} 条，转化情况值得关注。"
    else:
        attention = "暂无需要特别关注的异常。"

    return f"{summary}{attention}"


async def _generate_daily_recommendations(sections_data: dict) -> str:
    """用 LLM 生成 3 条基于数据的可操作建议。

    每条建议必须引用具体数据作为依据，避免空泛建议。
    LLM 失败时返回空字符串（建议是可选的锦上添花功能）。

    Args:
        sections_data: 包含关键指标的字典
    Returns:
        格式化的建议文本，以「💡 今日建议」开头；失败时返回空列表
    """
    # 提取关键指标
    pnl = sections_data.get("portfolio_pnl", 0)
    xianyu_consult = sections_data.get("xianyu_consultations", 0)
    xianyu_orders = sections_data.get("xianyu_orders", 0)
    social_posts = sections_data.get("social_posts", 0)
    api_cost = sections_data.get("api_daily_cost", 0)
    market_sentiment = sections_data.get("market_sentiment", "")
    positions_count = sections_data.get("positions_count", 0)
    deltas = sections_data.get("deltas", {})

    try:
        from src.litellm_router import free_pool

        if not free_pool:
            return []

        # 组装数据摘要供 LLM 推理
        data_lines = []
        if pnl != 0:
            data_lines.append(f"投资组合浮盈亏: ${pnl:+,.2f}, 持仓 {positions_count} 个")
        if xianyu_consult > 0:
            conv = f"{xianyu_orders}/{xianyu_consult}" if xianyu_consult > 0 else "N/A"
            data_lines.append(f"闲鱼: 咨询 {xianyu_consult} 条, 下单 {xianyu_orders} 笔, 转化 {conv}")
        if social_posts > 0:
            data_lines.append(f"社媒: 今日发帖 {social_posts} 篇")
        if api_cost > 0:
            data_lines.append(f"API 日均成本: ${api_cost:.2f}")
        if market_sentiment:
            data_lines.append(f"市场情绪: {market_sentiment}")
        for key, val in deltas.items():
            if val != 0:
                sign = "+" if val > 0 else ""
                data_lines.append(f"较昨日变化 — {key}: {sign}{val}")

        if not data_lines:
            return []

        data_text = "\n".join(data_lines)
        prompt = (
            f"你是一位私人财务管家和运营顾问。以下是用户今日的业务数据:\n"
            f"{data_text}\n\n"
            f"请给出恰好 3 条今日可操作建议。要求:\n"
            f"1. 每条建议必须引用具体数据（如「闲鱼咨询 15 条但下单仅 2 笔，建议优化话术」）\n"
            f"2. 建议要具体可执行，不要空泛（如「注意市场风险」这种无用建议）\n"
            f"3. 用中文，每条一行，每条不超过 30 字\n"
            f"4. 涵盖不同领域（投资/电商/运营中选 2-3 个有数据的领域）\n"
            f"5. 没有数据支撑的领域不要硬凑建议\n"
            f"直接输出 3 条建议，不要有推理过程、前缀或解释。"
        )

        resp = await free_pool.acompletion(
            model_family=FAMILY_QWEN,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.5,
            max_tokens=300,
            cache_ttl=1800,
        )
        text = (resp.choices[0].message.content or "").strip()
        text = _strip_think_tags(text)
        if not text:
            return []

        # 解析 LLM 输出为建议列表
        lines = [ln.strip() for ln in text.split("\n") if ln.strip() and not ln.strip().startswith("```")]
        # 清理编号前缀，统一格式
        result = []
        for ln in lines:
            ln = ln.lstrip("0123456789.、）) -·•*")
            ln = ln.strip()
            if ln:
                result.append(ln)

        return result[:3] if result else []

    except Exception as e:
        logger.warning("[DailyBrief] 今日建议 LLM 调用失败: %s", e)
        # 降级模板：基于已有数据生成基础建议，不让整个 section 消失
        fallback = []
        if sections_data:
            if sections_data.get("xianyu_consultations", 0) > 0:
                fallback.append(f"闲鱼今日{sections_data['xianyu_consultations']}条咨询，留意高频问题优化话术")
            if sections_data.get("positions_count", 0) > 0:
                fallback.append("检查持仓止损位是否需要调整")
            if sections_data.get("social_posts", 0) > 0:
                fallback.append("查看社媒互动数据，关注高互动内容类型")
        if not fallback:
            fallback.append("今日数据较少，建议关注核心业务指标")
        return fallback[:3]
