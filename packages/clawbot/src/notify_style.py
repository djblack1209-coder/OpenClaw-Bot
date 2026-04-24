"""
统一的 Telegram/推送文案排版 v2.1

设计原则：
- 每条通知一眼扫完，信息密度高但不拥挤
- emoji 做视觉锚点，不滥用
- 分隔线用细线 ─── 而非粗重符号
- 关键数字突出，废话砍掉

v2.1 变更 (2026-03-23):
  - 搬运 humanize (2.9k⭐) — 自然语言时间/文件大小/数字格式
  - 新增 natural_time(): "3分钟前" / "2 hours ago"
  - 新增 natural_size(): "1.2 MB" / "340 KB"
  - 新增 natural_number(): "1,234,567" / "1.2 million"
"""

import logging
from collections.abc import Iterable, Sequence

logger = logging.getLogger(__name__)

# 全局统一分隔线常量（19 个全角粗划线 U+2501）
SEPARATOR = "━━━━━━━━━━━━━━━━━━━"

# ── humanize (2.9k⭐) — 自然语言格式化 ──────────────────────
_HAS_HUMANIZE = False
try:
    import humanize

    # 激活中文支持
    try:
        humanize.activate("zh_CN")
    except Exception as e:
        logger.warning("静默异常: %s", e)
    _HAS_HUMANIZE = True
except ImportError:
    humanize = None  # type: ignore[assignment]


# ── 基础工具 ──────────────────────────────────────


def clean_text(value: object) -> str:
    return " ".join(str(value or "").strip().split())


def shorten(value: object, max_len: int = 80) -> str:
    text = clean_text(value)
    if max_len <= 0 or len(text) <= max_len:
        return text
    return text[: max_len - 3].rstrip() + "…"


def bullet(text: object, icon: str = "·") -> str:
    value = clean_text(text)
    return f" {icon} {value}" if value else ""


def kv(label: str, value: object, max_len: int = 120) -> str:
    text = shorten(value, max_len=max_len)
    return f" · {label}  {text}" if text else ""


def divider(style: str = "thin") -> str:
    if style == "double":
        return "═══════════════════"
    return SEPARATOR


def timestamp_tag() -> str:
    try:
        from src.utils import now_et

        return now_et().strftime("%H:%M ET")
    except Exception:
        from datetime import datetime

        return datetime.now().strftime("%H:%M")


def natural_time(dt=None, future: bool = False) -> str:
    """自然语言时间 — 搬运 humanize (2.9k⭐)。

    natural_time(some_datetime)  →  "3分钟前" / "2 hours ago"
    natural_time(None)           →  "刚刚"
    humanize 不可用时降级到 strftime。
    """
    if _HAS_HUMANIZE and humanize is not None:
        try:
            if dt is None:
                return humanize.naturaltime(0)
            if isinstance(dt, (int, float)):
                from datetime import datetime as _dt

                dt = _dt.fromtimestamp(dt)
            return humanize.naturaltime(dt, future=future)
        except Exception as e:
            logger.debug("静默异常: %s", e)
    # 降级
    if dt is None:
        return "刚刚"
    if isinstance(dt, (int, float)):
        from datetime import datetime as _dt

        dt = _dt.fromtimestamp(dt)
    try:
        return dt.strftime("%m-%d %H:%M")
    except Exception as e:  # noqa: F841
        return str(dt)


def natural_size(num_bytes: int) -> str:
    """自然语言文件大小 — 搬运 humanize。

    natural_size(1234567)  →  "1.2 MB"
    """
    if _HAS_HUMANIZE and humanize is not None:
        try:
            return humanize.naturalsize(num_bytes)
        except Exception as e:
            logger.debug("静默异常: %s", e)
    # 降级
    for unit in ["B", "KB", "MB", "GB"]:
        if num_bytes < 1024:
            return f"{num_bytes:.1f} {unit}"
        num_bytes /= 1024
    return f"{num_bytes:.1f} TB"


def natural_number(n) -> str:
    """自然语言数字 — 搬运 humanize。

    natural_number(1234567)  →  "1.2 million"
    natural_number(1234)     →  "1,234"
    """
    if _HAS_HUMANIZE and humanize is not None:
        try:
            if isinstance(n, float) and n >= 1_000_000:
                return humanize.intword(int(n))
            return humanize.intcomma(n)
        except Exception as e:
            logger.debug("静默异常: %s", e)
    return f"{n:,}" if isinstance(n, (int, float)) else str(n)


# ── 通知卡片 ──────────────────────────────────────


def format_notice(
    title: str,
    bullets: Iterable[str] | None = None,
    links: Iterable[str] | None = None,
    footer: str = "",
    icon: str = "",
) -> str:
    """单条通知卡片：标题 + 要点 + 链接 + 脚注"""
    header = f"{icon}  {clean_text(title)}" if icon else clean_text(title)
    lines = [header, divider()]
    for item in bullets or []:
        if item:
            lines.append(item)
    for link in links or []:
        value = clean_text(link)
        if value:
            lines.append(f" 🔗 {value}")
    tail = clean_text(footer)
    if tail:
        lines.extend(["", f"  {tail}  ⏱ {timestamp_tag()}"])
    else:
        lines.append(f"  ⏱ {timestamp_tag()}")
    return "\n".join(line for line in lines if line or line == "").strip()


def format_digest(
    title: str,
    intro: str = "",
    sections: Sequence[tuple[str, Sequence[str]]] | None = None,
    footer: str = "",
) -> str:
    # icon="" 避免 format_announcement 默认加 📢 前缀，调用方标题已自带 emoji
    return format_announcement(title=title, intro=intro, sections=sections, footer=footer, icon="")


def format_announcement(
    title: str,
    intro: str = "",
    paragraphs: Sequence[str] | None = None,
    sections: Sequence[tuple[str, Sequence[str]]] | None = None,
    links: Sequence[str] | None = None,
    footer: str = "",
    icon: str = "📢",
) -> str:
    """长通知/公告：标题 + 简介 + 分段 + 链接 + 脚注"""
    header = f"{icon}  {clean_text(title)}" if icon else clean_text(title)
    lines = [header, divider("double")]

    intro_text = clean_text(intro)
    if intro_text:
        lines.extend(["", intro_text])

    for paragraph in paragraphs or []:
        text = clean_text(paragraph)
        if text:
            lines.extend(["", text])

    for heading, entries in sections or []:
        cleaned_entries = [clean_text(item) for item in entries if clean_text(item)]
        if not cleaned_entries:
            continue
        lines.extend(["", f"▸ {clean_text(heading)}"])
        for entry in cleaned_entries:
            lines.append(f"  {entry}")

    cleaned_links = [clean_text(link) for link in links or [] if clean_text(link)]
    if cleaned_links:
        lines.extend(["", "🔗 直达"])
        for link in cleaned_links:
            lines.append(f"  {link}")

    tail = clean_text(footer)
    if tail:
        lines.extend(["", f"  {tail}"])

    return "\n".join(line for line in lines if line or line == "").strip()


# ── 交易通知（高频，必须一眼看懂）──────────────────


def format_trade_submitted(action: str, symbol: str, quantity: int, order_id: object, status: str = "Submitted") -> str:
    act = clean_text(action).upper()
    sym = clean_text(symbol).upper()
    icon = "🟢" if act == "BUY" else "🔴"
    return format_notice(
        f"{act} {sym} x{int(quantity)}",
        icon=f"{icon} 挂单",
        bullets=[
            kv("订单号", f"#{order_id}"),
            kv("状态", status),
            bullet("回写校验器将自动同步成交", icon="⏳"),
        ],
    )


def format_trade_executed(
    action: str,
    symbol: str,
    quantity: int,
    fill_price: float,
    stop_loss: float,
    take_profit: float,
    signal_score: int,
    decided_by: str,
    reason: str,
    extra_flag: str = "",
) -> str:
    act = clean_text(action).upper()
    sym = clean_text(symbol).upper()
    icon = "🟢" if act == "BUY" else "🔴"
    risk = abs(fill_price - stop_loss)
    reward = abs(take_profit - fill_price)
    rr = f"{reward / risk:.1f}" if risk > 0 else "∞"
    bullets = [
        kv("成交", f"{sym} x{int(quantity)} @ ${float(fill_price):.2f}"),
        kv("止损/止盈", f"${float(stop_loss):.2f} → ${float(take_profit):.2f}  (R:R {rr})"),
        kv("信号", f"{int(signal_score)}分 | 决策: {clean_text(decided_by)}"),
        kv("逻辑", reason, max_len=96),
    ]
    extra = clean_text(extra_flag)
    if extra:
        bullets.append(bullet(extra, icon="📌"))
    return format_notice(
        f"{act} {sym} 已成交",
        icon=icon,
        bullets=bullets,
    )


def format_trade_fill_reconciled(trade_id: int, order_id: object, symbol: str, quantity: float, price: float) -> str:
    return format_notice(
        f"{clean_text(symbol).upper()} 成交回写",
        icon="✅",
        bullets=[
            kv("Trade/Order", f"#{int(trade_id)} / #{order_id}"),
            kv("成交", f"x{float(quantity):.4f} @ ${float(price):.4f}"),
        ],
    )


def format_pending_reentry(symbol: str, quantity: int, price: float, status: str) -> str:
    return format_notice(
        f"{clean_text(symbol).upper()} 次日重挂",
        icon="🔄",
        bullets=[
            kv("挂单", f"x{int(quantity)} @ ${float(price):.2f}"),
            kv("状态", status),
        ],
    )


def format_ibkr_connectivity(title: str, detail: str) -> str:
    return format_notice(title, icon="🔌", bullets=[bullet(detail, icon="→")])


# ── 社媒通知 ──────────────────────────────────────


def format_social_published(platform: str, topic: str, url: str = "", title: str = "", memory_path: str = "") -> str:
    """社媒发布成功通知"""
    plat_icon = {"x": "𝕏", "xiaohongshu": "📕"}.get(platform, "📱")
    plat_name = {"x": "X", "xiaohongshu": "小红书"}.get(platform, platform)
    bullets = []
    if title:
        bullets.append(kv("标题", title, max_len=60))
    if url:
        bullets.append(f" 🔗 {url}")
    if memory_path:
        bullets.append(bullet(f"已存档 → {memory_path}", icon="💾"))
    return format_notice(
        f"{plat_name} 已发布 | {clean_text(topic)}",
        icon=plat_icon,
        bullets=bullets,
    )


def format_social_dual_result(topic: str, xhs_result: dict, x_result: dict, memory_path: str = "") -> str:
    """双平台发文结果"""
    lines = [f"📱  双平台发文 | {clean_text(topic)}", divider()]
    for name, result, icon in [("小红书", xhs_result, "📕"), ("X", x_result, "𝕏")]:
        pub = result.get("published", result) if isinstance(result, dict) else {}
        if isinstance(pub, dict) and pub.get("success"):
            lines.append(f" {icon} {name}: {pub.get('url', '已发布')}")
        else:
            err = ""
            if isinstance(pub, dict):
                err = pub.get("error", "")
            if not err and isinstance(result, dict):
                err = result.get("error", "未知错误")
            lines.append(f" {icon} {name}: ❌ {err}")
    if memory_path:
        lines.append(f" 💾 存档: {memory_path}")
    lines.append(f"  ⏱ {timestamp_tag()}")
    return "\n".join(lines)


def format_hotpost_result(topic: str, trend_label: str, results: dict, login_hint: str = "") -> str:
    """热点一键发文结果"""
    lines = [f"🔥  热点发文 | {clean_text(topic or '自动选题')}", divider()]
    if trend_label:
        lines.append(f" 📈 蹭热点: {clean_text(trend_label)}")
    for name in ["xiaohongshu", "x"]:
        package = (results or {}).get(name)
        if not package:
            continue
        published = package.get("published", {}) or {}
        label = "📕 小红书" if name == "xiaohongshu" else "𝕏 X"
        if published.get("success"):
            lines.append(f" {label}: {published.get('url', '已发布')}")
        else:
            lines.append(f" {label}: ❌ {published.get('error', package.get('error', '未知错误'))}")
    if login_hint:
        lines.append(f"\n{clean_text(login_hint)}")
    lines.append(f"  ⏱ {timestamp_tag()}")
    return "\n".join(lines)


# ── 系统状态通知 ──────────────────────────────────


def format_status_card(
    name: str,
    emoji: str,
    role: str,
    model: str,
    api_type: str,
    msg_count: int,
    pool_info: str,
    healthy: bool,
    uptime_hours: float,
    today_messages: int,
    gateway_status: str,
    browser_running: bool,
    x_state: str,
    xhs_state: str,
    persona_name: str,
    balance_warning: str = "",
) -> str:
    """Bot 状态卡片"""
    health_icon = "💚" if healthy else "🔴"
    gw_icon = "🟢" if gateway_status == "在线" else "🔴"
    br_icon = "🟢" if browser_running else "⚪"
    lines = [
        f"{emoji}  {name}",
        divider(),
        f" · 角色  {role}",
        f" · 模型  {model.split('/')[-1]}",
        f" · 路由  {api_type}",
        f" · 对话  {msg_count // 2} 轮 | 今日 {today_messages} 条",
        f" · 免费池  {pool_info}",
        divider(),
        f" {health_icon} 健康 | {gw_icon} Gateway | {br_icon} 浏览器",
        f" 𝕏 {x_state} | 📕 {xhs_state}",
        f" 👤 {persona_name} | ⏱ 运行 {uptime_hours}h",
    ]
    if balance_warning:
        lines.append(f"\n⚠️ {balance_warning}")
    return "\n".join(lines)


# ── 成本/配额通知 ──────────────────────────────────


def format_cost_card(
    throttle_flags: dict,
    token_rows: dict,
    rate_rows: dict,
) -> str:
    """成本/配额状态卡片"""
    lines = ["💰  成本 / 配额", divider()]

    lines.append("")
    lines.append("▸ 请求节流")
    flag_labels = {
        "group_llm": "群聊LLM路由",
        "group_intent": "群聊意图回复",
        "group_fallback": "群聊兜底轮换",
        "fill_only": "仅成交通知",
    }
    for key, label in flag_labels.items():
        on = throttle_flags.get(key, False)
        lines.append(f"  {'🟢' if on else '⚪'} {label}")

    if token_rows:
        lines.append("")
        lines.append("▸ 今日 Token")
        for bot_id, status in sorted(token_rows.items()):
            total = status.get("total_tokens", 0)
            limit = status.get("daily_limit", 0)
            pct = status.get("usage_pct", "0%")
            bar_len = 10
            filled = int(bar_len * total / limit) if limit > 0 else 0
            bar = "█" * min(filled, bar_len) + "░" * (bar_len - min(filled, bar_len))
            lines.append(f"  {bot_id}: [{bar}] {total:,}/{limit:,} ({pct})")

    if rate_rows:
        lines.append("")
        lines.append("▸ 请求频率")
        for bot_id, status in sorted(rate_rows.items()):
            m = status.get("requests_last_minute", 0)
            h = status.get("requests_last_hour", 0)
            d = status.get("requests_today", 0)
            lines.append(f"  {bot_id}: {m}/min  {h}/hr  {d}/day")

    lines.append(f"\n  ⏱ {timestamp_tag()}")
    return "\n".join(lines)


# ── 任务/赏金通知 ──────────────────────────────────


def format_bounty_result(
    evaluated: int,
    accepted: int,
    rejected: int,
    daily_cost: float,
    daily_cap: float,
    shortlist: list,
    watchlist: list = None,
    decision_stats: dict = None,
    reused: bool = False,
) -> str:
    """赏金猎人结果"""
    lines = [
        "🎯  AI 赏金猎人",
        divider(),
        f" · 评估 {evaluated} | 接受 {accepted} | 拒绝 {rejected}",
        f" · 今日成本 ${daily_cost:.2f} / ${daily_cap:.2f}",
    ]
    if reused:
        lines.append(" · ⚠️ 命中不足，回退到已验证 shortlist")
    if decision_stats:
        parts = [f"{k}:{v}" for k, v in list(decision_stats.items())[:6]]
        lines.append(f" · 拒绝原因: {' / '.join(parts)}")

    if shortlist:
        lines.extend(["", "▸ 候选 Top"])
        for i, row in enumerate(shortlist[:5], 1):
            roi = float(row.get("expected_roi_usd", 0) or 0)
            lines.append(f"  {i}. [{row.get('platform', 'web')}] ROI ${roi:.2f}")
            lines.append(f"     {shorten(row.get('title', ''), 80)}")
            if row.get("url"):
                lines.append(f"     🔗 {shorten(row.get('url', ''), 100)}")
    elif watchlist:
        lines.extend(["", "▸ 观察列表"])
        for i, row in enumerate(watchlist[:5], 1):
            lines.append(f"  {i}. [{row.get('reason', '未通过')}] {shorten(row.get('title', ''), 80)}")

    lines.append(f"\n  ⏱ {timestamp_tag()}")
    return "\n".join(lines)


# ── 长消息自动分割（Telegram 单消息上限 4096 字符）──────────


def split_long_message(text: str, max_len: int = 4096) -> list[str]:
    """将超长文本按 section 边界智能分割为多条消息。

    分割策略（按优先级）：
    1. 按 section 分隔符（━━━ 或 ▸ 开头行）分割
    2. 如果单个 section 仍超长，按换行符分割
    3. 最后兜底强制截断，保证不在行中间断开

    Args:
        text: 原始文本
        max_len: 单条消息最大字符数，默认 4096（Telegram 限制）

    Returns:
        分割后的消息列表，每条不超过 max_len
    """
    if len(text) <= max_len:
        return [text]

    import re

    # 按 section 分隔符拆分（━━━ 分隔线 或 ▸ 开头的标题行前断开）
    parts = re.split(r"(?=\n━━━|\n▸ )", text)

    chunks: list[str] = []
    current = ""

    for part in parts:
        # 当前块加上新 part 不超限，合并
        if len(current) + len(part) <= max_len:
            current += part
        else:
            # 当前块已满，保存并开始新块
            if current.strip():
                chunks.append(current.strip())
            # 单个 part 本身就超长，按换行符进一步分割
            if len(part) > max_len:
                sub_chunks = _split_by_lines(part, max_len)
                chunks.extend(sub_chunks[:-1])
                current = sub_chunks[-1] if sub_chunks else ""
            else:
                current = part

    if current.strip():
        chunks.append(current.strip())

    # 多页时添加分页标记
    if len(chunks) > 1:
        total = len(chunks)
        chunks = [f"{chunk}\n\n📄 ({i + 1}/{total})" for i, chunk in enumerate(chunks)]

    return chunks if chunks else [text[:max_len]]


def _split_by_lines(text: str, max_len: int) -> list[str]:
    """按换行符分割超长文本，保证不在行中间断开"""
    lines = text.split("\n")
    chunks: list[str] = []
    current = ""

    for line in lines:
        candidate = current + "\n" + line if current else line
        if len(candidate) <= max_len:
            current = candidate
        else:
            if current.strip():
                chunks.append(current.strip())
            # 单行超长（极端情况），强制截断
            if len(line) > max_len:
                chunks.append(line[:max_len])
                current = ""
            else:
                current = line

    if current.strip():
        chunks.append(current.strip())

    return chunks if chunks else [text[:max_len]]
