"""
OpenClaw 消息格式化层 — 统一 Telegram 输出
解决 Markdown/HTML 混用导致的渲染失败。

规则:
  - 所有用户消息使用 HTML parse_mode（Telegram HTML 更宽容）
  - AI 生成的内容通过 escape_html() 转义后插入 HTML 模板
  - 错误消息通过 format_error() 人话化
  - 结构化数据通过 format_info_card() 格式化

搬运参考:
  - telegram_ux.py 中的 format_trade_card / format_portfolio_card 已使用 HTML
  - 本模块统一所有消息格式，确保一致性

v2.0 新增 (2026-03-23):
  - markdown_to_telegram_html() — 搬运自 CoPaw (agentscope-ai, Apache-2.0)
    5 阶段管线: 保护代码块→转义→块级元素→行内格式→恢复占位符
    解决 LLM 生成 Markdown 在 Telegram 渲染失败的问题
  - strip_markdown() — 纯文本降级，发送失败时兜底
"""

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

# ── HTML 转义 ──────────────────────────────────────────────

_HTML_ESCAPE_TABLE = str.maketrans(
    {
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
    }
)


def escape_html(text: str) -> str:
    """转义 HTML 特殊字符，防止 Telegram HTML parse_mode 渲染失败。

    只转义 Telegram HTML 要求的三个字符: < > &
    引号不需要转义（Telegram HTML 不解析属性）。

    Args:
        text: 原始文本（可能包含用户输入、AI 生成内容等）

    Returns:
        转义后的安全 HTML 文本
    """
    if not text:
        return ""
    return str(text).translate(_HTML_ESCAPE_TABLE)


# ── 错误格式化 ──────────────────────────────────────────────

import asyncio  # noqa: E402

# 错误分类规则：(匹配函数, 用户可见消息)
# 按优先级排列，先匹配先返回
# 注意: s 是 str(error).lower()（保留空格），用于灵活匹配
_ERROR_PATTERNS: list[tuple[Any, str]] = [
    # LiteLLM 全链路降级失败（所有 provider 都挂了）
    (
        lambda e, s: "no healthy deployment" in s or "all deployments" in s or "no available deployment" in s,
        "🔧 AI 服务全线繁忙，正在自动切换备用通道，请稍后重试",
    ),
    # ConnectionError 家族
    (
        lambda e, s: (
            isinstance(e, ConnectionError)
            or "connection refused" in s
            or "connectionrefused" in s
            or "connect" in s
            or "network" in s
        ),
        "🔌 服务暂时无法连接，请稍后重试",
    ),
    # Timeout
    (
        lambda e, s: isinstance(e, (TimeoutError, asyncio.TimeoutError)) or "timeout" in s or "timed out" in s,
        "⏱ 操作超时，请稍后重试",
    ),
    # Rate limit (429)
    (
        lambda e, s: (
            "429" in s or "ratelimit" in s or "rate_limit" in s or "rate limit" in s or "too many requests" in s
        ),
        "⚡ 请求太频繁，请等待片刻",
    ),
    # Auth errors (401/403)
    (
        lambda e, s: (
            "401" in s or "403" in s or "unauthorized" in s or "forbidden" in s or ("auth" in s and "fail" in s)
        ),
        "🔑 认证失败，请联系管理员",
    ),
    # Server errors (5xx)
    (
        lambda e, s: (
            any(
                f" {code}" in s or f"_{code}" in s or f":{code}" in s or s.startswith(str(code))
                for code in range(500, 600)
            )
            or "internal server error" in s
            or "bad gateway" in s
            or "service unavailable" in s
            or "server error" in s
        ),
        "🔧 服务端故障，正在自动恢复",
    ),
]


def format_error(error: Exception | str, context: str = "") -> str:
    """将任何错误转换为用户友好的中文消息 (错误格式化的 SSOT)。

    与 error_messages.py 的关系:
      error_messages.py 提供简单的静态模板函数 (error_ai_busy 等)，
      本函数提供智能模式匹配分类。两者应逐步统一到此处。

    绝不暴露原始异常类名、traceback 或文件路径给用户。
    真实错误信息通过 logger 记录，供开发调试。

    Args:
        error: 异常对象或错误字符串
        context: 操作上下文（如 "分析茅台"），用于日志关联

    Returns:
        用户可见的 HTML 格式错误消息
    """
    # 记录真实错误（含完整信息）
    if isinstance(error, Exception):
        logger.error(
            "操作失败 [context=%s] [type=%s]: %s",
            context or "unknown",
            type(error).__name__,
            error,
            exc_info=error,
        )
        err_str = str(error).lower()
    else:
        logger.error("操作失败 [context=%s]: %s", context or "unknown", error)
        err_str = str(error).lower()

    # 按规则匹配
    for matcher, user_msg in _ERROR_PATTERNS:
        try:
            if matcher(error if isinstance(error, Exception) else None, err_str):
                return user_msg
        except Exception as e:  # noqa: F841
            continue

    # 兜底：不暴露任何技术细节
    return "⚠️ 操作未完成，请稍后重试"


# ── 信息卡片 ──────────────────────────────────────────────

_SEPARATOR = "━━━━━━━━━━━━━━━━━━━"


def format_info_card(
    title: str,
    sections: list[tuple[str, str]],
    footer: str = "",
) -> str:
    """生成统一的 HTML 信息卡片。

    适用于系统状态、分析报告、操作确认等结构化展示。

    Args:
        title: 卡片标题（会加粗+emoji前缀）
        sections: [(小标题, 内容), ...] 每个 section 独立显示
        footer: 底部备注文字（斜体显示）

    Returns:
        Telegram HTML 格式的卡片文本
    """
    parts: list[str] = []

    # 标题
    parts.append(f"<b>📊 {escape_html(title)}</b>")
    parts.append(_SEPARATOR)

    # 各 section
    for section_title, section_content in sections:
        parts.append(f"<b>{escape_html(section_title)}</b>")
        parts.append(escape_html(section_content))
        parts.append("")  # 空行分隔

    # 去掉最后一个空行，加分隔线
    if parts and parts[-1] == "":
        parts.pop()
    parts.append(_SEPARATOR)

    # Footer
    if footer:
        parts.append(f"<i>{escape_html(footer)}</i>")

    return "\n".join(parts)


# ── 任务结果格式化 ──────────────────────────────────────────

# 中文标签映射（常见字段 → 可读中文）
_LABEL_MAP = {
    "answer": "回答",
    "source": "来源",
    "decision": "决策",
    "confidence": "置信度",
    "reasoning": "理由",
    "recommendation": "建议",
    "best_deal": "最佳选择",
    "tips": "省钱技巧",
    "products": "商品列表",
    "positions": "持仓",
    "summary": "摘要",
    "text": "内容",
    "note": "备注",
    "draft": "草稿",
    "platform": "平台",
    "success": "状态",
    "result": "结果",
    "city": "城市",
    "forecasts": "预报",
    "action": "操作",
    "symbol": "标的",
    "product": "商品",
    "error": "错误",
    "card_type": "卡片类型",
    "raw": "原始内容",
    "data": "数据",
    "telegram_text": "分析文本",
    "vetoed": "是否否决",
}

# 决策值的中文映射
_DECISION_MAP = {
    "buy": "📈 买入",
    "sell": "📉 卖出",
    "hold": "⏸ 持有",
}


def format_result(result: dict, task_type: str = "") -> str:
    """将 Brain TaskResult.final_result 转换为人类可读的中文 HTML 消息。

    根据 task_type 使用不同的格式化策略：
      - synthesized → 合成后的对话式回复（优先）
      - investment → 买/卖/持有 + 置信度 + 理由
      - shopping  → 商品列表 + 最佳选择
      - social    → 已发布/已生成 + 平台 + 链接
      - error     → 调用 format_error()
      - generic   → key-value 显示

    Args:
        result: Brain 返回的结果字典（可能嵌套，包含多个节点结果）
        task_type: TaskType.value（如 "investment", "shopping"）

    Returns:
        Telegram HTML 格式的结果消息
    """
    if not result:
        return "✅ 操作已完成"

    # ★ 优先使用合成后的对话式回复 (ResponseSynthesizer 生成)
    if isinstance(result, dict) and result.get("synthesized_reply"):
        synthesized = result["synthesized_reply"]
        # 合成回复已经是自然语言，直接转换为 Telegram HTML
        try:
            return markdown_to_telegram_html(synthesized)
        except Exception as e:  # noqa: F841
            return escape_html(synthesized)

    # 错误结果（顶层）
    if isinstance(result, dict) and result.get("error"):
        return format_error(result["error"])

    # 扁平化嵌套结果（Brain 返回 {node_id: node_result, ...}）
    flat = _flatten_result(result)

    # 错误结果（嵌套节点中的错误）
    if flat.get("error"):
        return format_error(flat["error"])

    # 按任务类型分派
    formatters = {
        "investment": _format_investment,
        "shopping": _format_shopping,
        "social": _format_social,
    }
    formatter = formatters.get(task_type)
    if formatter:
        try:
            return formatter(flat)
        except Exception as e:
            logger.warning("格式化 %s 结果失败: %s", task_type, e)

    # 通用格式化
    return _format_generic(flat)


def _flatten_result(result: dict) -> dict:
    """扁平化 Brain 的嵌套结果。

    Brain 返回 {"node_id": {"source": ..., "data": ...}, ...}
    将所有节点结果合并为一个扁平字典，后面节点的值覆盖前面。
    """
    flat: dict[str, Any] = {}
    for key, value in result.items():
        if isinstance(value, dict):
            # 嵌套节点结果 — 展开
            flat.update(value)
        else:
            flat[key] = value
    return flat


def _format_investment(data: dict) -> str:
    """投资分析结果格式化 (纯文本降级路径)。

    渲染优先级:
      1. synthesized_reply (ResponseSynthesizer 对话式合成) ← format_result() 最先检查
      2. InvestmentAnalysisCard (response_cards.py 富卡片 + 按钮) ← gateway 层
      3. 本函数 (纯文本) ← 前两者都不可用时的最终降级
    """
    sections: list[tuple[str, str]] = []

    # 优先使用 Pydantic 引擎的 telegram_text
    telegram_text = data.get("telegram_text")
    if telegram_text and isinstance(telegram_text, str):
        # Pydantic 引擎生成的文本可能含 < > 字符，需要转义
        return escape_html(telegram_text)

    # 决策结果
    decision = data.get("decision", "")
    decision_display = _DECISION_MAP.get(str(decision).lower(), str(decision))

    confidence = data.get("confidence", 0)
    if isinstance(confidence, (int, float)):
        confidence_display = f"{float(confidence) * 100:.0f}%" if confidence <= 1 else f"{confidence:.0f}%"
    else:
        confidence_display = str(confidence)

    reasoning = data.get("reasoning", "")
    symbol = data.get("symbol", data.get("symbol_hint", ""))

    title = f"投资分析 — {symbol}" if symbol else "投资分析"

    if decision:
        sections.append(("决策", decision_display))
    if confidence_display and confidence_display != "0%":
        sections.append(("置信度", confidence_display))
    if reasoning:
        sections.append(("理由", str(reasoning)[:300]))

    # 风控状态
    approved = data.get("approved")
    if approved is not None:
        status = "✅ 通过" if approved else "❌ 风控拒绝"
        sections.append(("风控", status))
    vetoed = data.get("vetoed")
    if vetoed:
        sections.append(("否决", "⚠️ 已被风控否决"))

    # 位置建议
    position_pct = data.get("position_pct")
    if position_pct is not None:
        sections.append(("建议仓位", f"{position_pct}%"))

    if not sections:
        return _format_generic(data)

    footer = ""
    source = data.get("source", "")
    if source:
        footer = f"来源: {source}"

    return format_info_card(title, sections, footer=footer)


def _format_shopping(data: dict) -> str:
    """购物比价结果格式化。"""
    product = data.get("product", "商品")
    sections: list[tuple[str, str]] = []

    # 商品列表
    products = data.get("products", [])
    if products and isinstance(products, list):
        lines = []
        for i, item in enumerate(products[:8], 1):
            if isinstance(item, dict):
                name = item.get("name", "")
                price = item.get("price", "")
                platform = item.get("platform", "")
                note = item.get("note", "")
                line = f"{i}. {name}"
                if price:
                    line += f" — {price}"
                if platform:
                    line += f" ({platform})"
                if note:
                    line += f"\n   {note}"
                lines.append(line)
            else:
                lines.append(f"{i}. {item}")
        if lines:
            sections.append(("商品对比", "\n".join(lines)))

    # 最佳选择
    best = data.get("best_deal", "")
    if best:
        sections.append(("最佳选择", str(best)))

    # 推荐
    rec = data.get("recommendation", "")
    if rec:
        sections.append(("购买建议", str(rec)[:300]))

    # 省钱技巧
    tips = data.get("tips", "")
    if tips:
        sections.append(("省钱技巧", str(tips)[:200]))

    if not sections:
        # 可能是纯文本结果
        raw = data.get("raw", "")
        if raw:
            return f"<b>🛒 {escape_html(product)} 比价结果</b>\n\n{escape_html(str(raw)[:800])}"
        return _format_generic(data)

    return format_info_card(f"🛒 {product} 比价", sections)


def _format_social(data: dict) -> str:
    """社媒发布结果格式化。"""
    sections: list[tuple[str, str]] = []

    platform = data.get("platform", "")
    success = data.get("success")
    draft = data.get("draft", "")

    if success is True:
        title = "社媒发布 — 已发布"
        if platform:
            sections.append(("平台", str(platform).upper()))
    elif draft:
        title = "社媒内容 — 已生成"
        if platform:
            sections.append(("目标平台", str(platform).upper()))
    else:
        title = "社媒运营"

    if draft:
        preview = str(draft)[:300]
        if len(str(draft)) > 300:
            preview += "..."
        sections.append(("内容预览", preview))

    # 图片
    image_url = data.get("image_url")
    if image_url:
        sections.append(("配图", "已生成"))

    # 发布结果
    pub_result = data.get("result")
    if pub_result and isinstance(pub_result, dict):
        link = pub_result.get("url", pub_result.get("link", ""))
        if link:
            sections.append(("链接", str(link)))

    if not sections:
        return _format_generic(data)

    return format_info_card(title, sections)


def _format_generic(data: dict) -> str:
    """通用 key-value 格式化（兜底方案）。"""
    # 过滤掉内部字段和空值
    _SKIP_KEYS = {"source", "card_type", "_upstream_results"}

    # 如果有 answer 字段，直接返回（LLM 回答 / 信息查询）
    answer = data.get("answer")
    if answer and isinstance(answer, str):
        return escape_html(answer)

    # 如果有 text 字段（如天气），直接返回
    text = data.get("text")
    if text and isinstance(text, str):
        return escape_html(text)

    # 如果有 forward_to_chat（闲聊转发），不输出内部细节
    if data.get("action") == "forward_to_chat":
        return ""

    # 否则构建 key-value 列表
    lines: list[str] = []
    for key, value in data.items():
        if key in _SKIP_KEYS or key.startswith("_"):
            continue
        if value is None or value == "" or value == [] or value == {}:
            continue

        label = _LABEL_MAP.get(key, key)
        display_value = _format_value(value)
        if display_value:
            lines.append(f"<b>{escape_html(label)}</b>: {escape_html(display_value)}")

    if not lines:
        return "✅ 操作已完成"

    return "\n".join(lines)


def _format_value(value: Any) -> str:
    """将任意值转为可读字符串。"""
    if isinstance(value, bool):
        return "是" if value else "否"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        return value[:500]
    if isinstance(value, list):
        if not value:
            return ""
        # 简单列表：取前 5 项
        items = [str(v)[:100] for v in value[:5]]
        suffix = f" ...等{len(value)}项" if len(value) > 5 else ""
        return "、".join(items) + suffix
    if isinstance(value, dict):
        # 递归格式化字典的前几个字段
        parts = []
        for k, v in list(value.items())[:5]:
            label = _LABEL_MAP.get(k, k)
            parts.append(f"{label}: {str(v)[:80]}")
        return " | ".join(parts)
    return str(value)[:200]


# ── Markdown → Telegram HTML 转换 ────────────────────────────
# 搬运自 CoPaw (agentscope-ai/CoPaw, Apache-2.0 License)
# 5 阶段管线: 保护代码块→转义→块级元素→行内格式→恢复占位符
# 解决 LLM 生成 Markdown 在 Telegram 渲染失败的痛点


def markdown_to_telegram_html(text: str) -> str:
    """将标准 Markdown 转换为 Telegram Bot API HTML。

    搬运自 CoPaw (agentscope-ai, Apache-2.0)，适配 OpenClaw。

    处理:
    - 围栏代码块 (``` ```)     → <pre><code>
    - 内联代码 (` `)           → <code>
    - 链接 [text](url)        → <a href>
    - 标题 (# … ######)       → <b>
    - 水平线 (---, ***, ___)   → ———
    - 引用 (> …)              → <blockquote>
    - 无序列表 (* / -)         → •
    - 剧透 (||text||)          → <tg-spoiler>
    - 粗体 (**text**)          → <b>
    - 斜体 (*text*)            → <i>
    - 粗斜体 (***text***)      → <b><i>
    - 删除线 (~~text~~)         → <s>
    """
    if not text:
        return text

    placeholders: list = []

    def _ph(html_fragment: str) -> str:
        idx = len(placeholders)
        placeholders.append(html_fragment)
        return f"\x00PH{idx}\x00"

    # ── Phase 1: 保护代码块（不被后续转义破坏）──────────────

    # 围栏代码块  ```lang\n…\n```
    def _code_block(m: re.Match) -> str:
        lang = (m.group(1) or "").strip()
        code = escape_html(m.group(2))
        if lang:
            return _ph(
                f'<pre><code class="language-{escape_html(lang)}">{code}</code></pre>',
            )
        return _ph(f"<pre>{code}</pre>")

    text = re.sub(r"```(\w*)\n?(.*?)```", _code_block, text, flags=re.DOTALL)

    # 内联代码 `…`
    def _inline_code(m: re.Match) -> str:
        return _ph(f"<code>{escape_html(m.group(1))}</code>")

    text = re.sub(r"`([^`\n]+)`", _inline_code, text)

    # 链接 [text](url) — 保护 URL 不被转义
    def _link(m: re.Match) -> str:
        link_text = escape_html(m.group(1))
        url = m.group(2).replace("<", "%3C").replace(">", "%3E")
        return _ph(f'<a href="{url}">{link_text}</a>')

    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", _link, text)

    # ── Phase 2: 转义剩余文本中的 HTML 特殊字符 ────────────
    text = escape_html(text)

    # ── Phase 3: 块级元素 ──────────────────────────────────

    # 水平线
    text = re.sub(r"^[\*\-_]{3,}\s*$", "———", text, flags=re.MULTILINE)

    # 标题 → 粗体
    text = re.sub(r"^#{1,6}\s+(.+?)$", r"<b>\1</b>", text, flags=re.MULTILINE)

    # 引用块
    lines = text.split("\n")
    result_lines: list = []
    quote_buf: list = []

    def _flush_quote() -> None:
        if quote_buf:
            inner = "\n".join(quote_buf)
            result_lines.append(f"<blockquote>{inner}</blockquote>")
            quote_buf.clear()

    for line in lines:
        stripped = line.lstrip()
        if stripped.startswith("&gt; "):
            quote_buf.append(stripped[5:])
        elif stripped == "&gt;":
            quote_buf.append("")
        else:
            _flush_quote()
            result_lines.append(line)
    _flush_quote()
    text = "\n".join(result_lines)

    # 无序列表 → •
    text = re.sub(r"^(\s*)[\*\-]\s+", r"\1• ", text, flags=re.MULTILINE)

    # ── Phase 4: 行内格式 ──────────────────────────────────

    # 剧透
    text = re.sub(r"\|\|(.+?)\|\|", r"<tg-spoiler>\1</tg-spoiler>", text)
    # 粗斜体
    text = re.sub(r"\*{3}(.+?)\*{3}", r"<b><i>\1</i></b>", text)
    # 粗体
    text = re.sub(r"\*{2}(.+?)\*{2}", r"<b>\1</b>", text)
    text = re.sub(r"__(.+?)__", r"<b>\1</b>", text)
    # 斜体
    text = re.sub(r"(?<!\w)\*(.+?)\*(?!\w)", r"<i>\1</i>", text)
    text = re.sub(r"(?<!\w)_(.+?)_(?!\w)", r"<i>\1</i>", text)
    # 删除线
    text = re.sub(r"~~(.+?)~~", r"<s>\1</s>", text)

    # ── Phase 5: 恢复占位符 ────────────────────────────────
    for idx, content in enumerate(placeholders):
        text = text.replace(f"\x00PH{idx}\x00", content)

    return text


def strip_markdown(text: str) -> str:
    """去除 Markdown 格式标记，返回纯文本。

    搬运自 CoPaw (agentscope-ai, Apache-2.0)。
    当 HTML 和 MarkdownV2 发送都失败时用作纯文本降级。
    """
    if not text:
        return text
    text = re.sub(r"```\w*\n?", "", text)
    text = re.sub(r"`([^`]+)`", r"\1", text)
    text = re.sub(r"^#{1,6}\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"^[\*\-_]{3,}\s*$", "———", text, flags=re.MULTILINE)
    text = re.sub(r"\*{1,3}(.+?)\*{1,3}", r"\1", text)
    text = re.sub(r"_{1,2}(.+?)_{1,2}", r"\1", text)
    text = re.sub(r"~~(.+?)~~", r"\1", text)
    text = re.sub(r"\|\|(.+?)\|\|", r"\1", text)
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"\1 (\2)", text)
    text = re.sub(r"^>\s?", "", text, flags=re.MULTILINE)
    text = re.sub(r"^(\s*)[\*\-]\s+", r"\1• ", text, flags=re.MULTILINE)
    return text
