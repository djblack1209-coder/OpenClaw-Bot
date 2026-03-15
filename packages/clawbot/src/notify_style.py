"""统一的 Telegram/推送文案排版。"""

from typing import Iterable, Optional, Sequence, Tuple


def clean_text(value: object) -> str:
    return " ".join(str(value or "").strip().split())


def shorten(value: object, max_len: int = 80) -> str:
    text = clean_text(value)
    if max_len <= 0 or len(text) <= max_len:
        return text
    return text[: max_len - 3].rstrip() + "..."


def bullet(text: object) -> str:
    value = clean_text(text)
    return f"- {value}" if value else ""


def kv(label: str, value: object, max_len: int = 120) -> str:
    text = shorten(value, max_len=max_len)
    return bullet(f"{label}: {text}") if text else ""


def format_notice(
    title: str,
    bullets: Optional[Iterable[str]] = None,
    links: Optional[Iterable[str]] = None,
    footer: str = "",
) -> str:
    lines = [clean_text(title)]
    for item in bullets or []:
        if item:
            lines.append(item)
    for link in links or []:
        value = clean_text(link)
        if value:
            lines.append(value)
    tail = clean_text(footer)
    if tail:
        lines.append(tail)
    return "\n".join(line for line in lines if line).strip()


def format_digest(
    title: str,
    intro: str = "",
    sections: Optional[Sequence[Tuple[str, Sequence[str]]]] = None,
    footer: str = "",
) -> str:
    return format_announcement(title=title, intro=intro, sections=sections, footer=footer)


def format_announcement(
    title: str,
    intro: str = "",
    paragraphs: Optional[Sequence[str]] = None,
    sections: Optional[Sequence[Tuple[str, Sequence[str]]]] = None,
    links: Optional[Sequence[str]] = None,
    footer: str = "",
) -> str:
    lines = [clean_text(title)]

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
        lines.extend(["", clean_text(heading)])
        lines.extend(cleaned_entries)

    cleaned_links = [clean_text(link) for link in links or [] if clean_text(link)]
    if cleaned_links:
        lines.extend(["", "【直达链接】"])
        lines.extend(cleaned_links)

    tail = clean_text(footer)
    if tail:
        lines.extend(["", tail])

    return "\n".join(line for line in lines if line or line == "").strip()


def format_trade_submitted(action: str, symbol: str, quantity: int, order_id: object, status: str = "Submitted") -> str:
    return format_notice(
        "交易待成交",
        bullets=[
            kv("动作", f"{clean_text(action).upper()} {clean_text(symbol).upper()} x{int(quantity)}"),
            kv("订单", f"#{order_id}"),
            kv("状态", status),
            bullet("后续由回写校验器自动同步成交"),
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
    bullets = [
        kv("动作", f"{clean_text(action).upper()} {clean_text(symbol).upper()} x{int(quantity)} @ ${float(fill_price):.2f}"),
        kv("止损 / 止盈", f"${float(stop_loss):.2f} / ${float(take_profit):.2f}"),
        kv("信号 / 决策", f"{int(signal_score)} / {clean_text(decided_by)}"),
        kv("理由", reason, max_len=96),
    ]
    extra = clean_text(extra_flag)
    if extra:
        bullets.append(bullet(extra))
    return format_notice("交易已成交", bullets=bullets)


def format_trade_fill_reconciled(trade_id: int, order_id: object, symbol: str, quantity: float, price: float) -> str:
    return format_notice(
        "成交回写完成",
        bullets=[
            kv("Trade / Order", f"#{int(trade_id)} / #{order_id}"),
            kv("成交", f"{clean_text(symbol).upper()} x{float(quantity):.4f} @ ${float(price):.4f}"),
        ],
    )


def format_pending_reentry(symbol: str, quantity: int, price: float, status: str) -> str:
    return format_notice(
        "次日重挂已提交",
        bullets=[
            kv("标的", f"{clean_text(symbol).upper()} x{int(quantity)} @ ${float(price):.2f}"),
            kv("状态", status),
        ],
    )


def format_ibkr_connectivity(title: str, detail: str) -> str:
    return format_notice(title, bullets=[bullet(detail)])
