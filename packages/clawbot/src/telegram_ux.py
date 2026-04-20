"""
ClawBot - Telegram UX 增强层 v1.0
参考: python-telegram-bot 最佳实践 + grammY (Telegram bot framework 15k⭐) 的 UX 模式
提供: typing 指示器、进度反馈、流式消息编辑、操作确认
"""

import asyncio
import time
import logging
from contextlib import asynccontextmanager
from typing import Optional

from telegram.constants import ChatAction
from telegram import Update
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)


class TypingIndicator:
    """持续发送 typing 指示器直到操作完成

    参考 grammY autoRetry + auto-chat-action 插件模式
    用法:
        async with TypingIndicator(chat_id, context):
            result = await long_operation()
    """

    def __init__(self, chat_id: int, context: ContextTypes.DEFAULT_TYPE, interval: float = 4.0):
        self.chat_id = chat_id
        self.context = context
        self.interval = interval  # Telegram typing expires after 5s
        self._task: Optional[asyncio.Task] = None

    async def _keep_typing(self):
        try:
            while True:
                await self.context.bot.send_chat_action(chat_id=self.chat_id, action=ChatAction.TYPING)
                await asyncio.sleep(self.interval)
        except asyncio.CancelledError as e:  # noqa: F841
            pass
        except Exception as e:
            logger.debug(f"[TypingIndicator] stopped: {e}")

    async def __aenter__(self):
        from src.core.async_utils import create_monitored_task
        self._task = create_monitored_task(
            self._keep_typing(), name="typing_indicator"
        )
        return self

    async def __aexit__(self, *exc):
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError as e:  # noqa: F841
                pass


@asynccontextmanager
async def typing_action(chat_id: int, context: ContextTypes.DEFAULT_TYPE):
    """便捷的 typing 指示器上下文管理器"""
    indicator = TypingIndicator(chat_id, context)
    async with indicator:
        yield indicator


class ProgressTracker:
    """长操作进度反馈器

    发送一条消息并持续更新进度，避免用户在长操作中看到静默。
    参考 tqdm 的进度条思路，适配 Telegram 消息编辑。
    """

    PROGRESS_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]

    def __init__(
        self, chat_id: int, context: ContextTypes.DEFAULT_TYPE, title: str = "处理中", edit_interval: float = 2.0
    ):
        self.chat_id = chat_id
        self.context = context
        self.title = title
        self.edit_interval = edit_interval
        self._message = None
        self._steps: list = []
        self._current_step = ""
        self._frame_idx = 0
        self._task: Optional[asyncio.Task] = None
        self._start_time = 0.0

    async def __aenter__(self):
        self._start_time = time.time()
        try:
            self._message = await self.context.bot.send_message(
                chat_id=self.chat_id, text=f"{self.PROGRESS_FRAMES[0]} {self.title}..."
            )
        except Exception as e:
            logger.debug(f"[ProgressTracker] send failed: {e}")
        from src.core.async_utils import create_monitored_task
        self._task = create_monitored_task(
            self._animate(), name="progress_animate"
        )
        return self

    async def __aexit__(self, exc_type, *exc):
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError as e:  # noqa: F841
                pass
        # Final update
        if self._message:
            elapsed = time.time() - self._start_time
            status = "✅" if not exc_type else "❌"
            steps_text = "\n".join(f"  ✓ {s}" for s in self._steps)
            final = f"{status} {self.title} ({elapsed:.1f}s)"
            if steps_text:
                final += f"\n{steps_text}"
            try:
                await self._message.edit_text(final)
            except Exception:
                logger.debug("Silenced exception", exc_info=True)

    async def update(self, step: str):
        """更新当前步骤"""
        if self._current_step:
            self._steps.append(self._current_step)
        self._current_step = step

    async def _animate(self):
        try:
            while True:
                await asyncio.sleep(self.edit_interval)
                if not self._message:
                    continue
                self._frame_idx = (self._frame_idx + 1) % len(self.PROGRESS_FRAMES)
                elapsed = time.time() - self._start_time
                frame = self.PROGRESS_FRAMES[self._frame_idx]
                steps_text = "\n".join(f"  ✓ {s}" for s in self._steps)
                current = f"  → {self._current_step}" if self._current_step else ""
                text = f"{frame} {self.title} ({elapsed:.1f}s)"
                if steps_text:
                    text += f"\n{steps_text}"
                if current:
                    text += f"\n{current}"
                try:
                    await self._message.edit_text(text)
                except Exception:
                    logger.debug("Silenced exception", exc_info=True)
        except asyncio.CancelledError as e:  # noqa: F841
            pass


class StreamingEditor:
    """流式消息编辑器 — 将 LLM 流式输出实时推送到 Telegram

    对标 ChatGPT/Claude 的打字机效果。
    基于已有的 routing/streaming.py，封装为更易用的 API。
    """

    def __init__(
        self, chat_id: int, context: ContextTypes.DEFAULT_TYPE, edit_interval: float = 1.2, min_chars: int = 40
    ):
        self.chat_id = chat_id
        self.context = context
        self.edit_interval = edit_interval
        self.min_chars = min_chars
        self._message = None
        self._full_text = ""
        self._last_edit_ts = 0.0
        self._last_edit_len = 0
        self._cursor = " ▌"

    async def start(self, initial_text: str = ""):
        """发送初始消息"""
        try:
            display = initial_text or f"{self._cursor}"
            self._message = await self.context.bot.send_message(chat_id=self.chat_id, text=display)
        except Exception as e:
            logger.debug(f"[StreamingEditor] start failed: {e}")

    async def push(self, chunk: str):
        """推送新的文本块"""
        self._full_text += chunk
        now = time.time()
        new_chars = len(self._full_text) - self._last_edit_len

        if new_chars >= self.min_chars and (now - self._last_edit_ts) >= self.edit_interval:
            await self._edit(self._full_text + self._cursor)

    async def finish(self) -> str:
        """完成流式输出，去掉光标"""
        if self._full_text:
            await self._edit(self._full_text)
        return self._full_text

    async def _edit(self, text: str):
        if not self._message:
            return
        try:
            await self._message.edit_text(text)
            self._last_edit_ts = time.time()
            self._last_edit_len = len(self._full_text)
        except Exception as e:
            # Telegram "message is not modified" is expected
            if "not modified" not in str(e).lower():
                logger.debug(f"[StreamingEditor] edit failed: {e}")


# ============ 便捷装饰器 ============


def with_typing(func):
    """装饰器：自动为命令处理器添加 typing 指示器

    用法:
        @with_typing
        async def cmd_news(self, update, context):
            ...
    """

    async def wrapper(self, update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        chat_id = update.effective_chat.id
        async with TypingIndicator(chat_id, context):
            return await func(self, update, context, *args, **kwargs)

    wrapper.__name__ = func.__name__
    wrapper.__doc__ = func.__doc__
    return wrapper


# ============ 进度条 — 搬运自 telebar 模式 ============


class TelegramProgressBar:
    """长操作进度条 — 搬运自 telebar + tqdm 思路

    用法:
        bar = TelegramProgressBar(total=8, label="回测", message=sent_msg, context=context)
        for sym in symbols:
            await process(sym)
            await bar.advance(detail=sym)
        await bar.finish("回测完成")
    """

    PHASES = ("░", "▒", "▓", "█")
    WIDTH = 10

    def __init__(self, total: int, label: str, message, context, throttle_seconds: float = 1.5):
        self.total = max(total, 1)
        self.label = label
        self.message = message
        self.context = context
        self.throttle = throttle_seconds
        self.current = 0
        self._last_edit = 0.0

    def _render(self, detail: str = "") -> str:
        pct = self.current / self.total
        filled = int(pct * self.WIDTH)
        bar = self.PHASES[3] * filled + self.PHASES[0] * (self.WIDTH - filled)
        line = f"{self.label}  {bar}  {self.current}/{self.total} ({pct:.0%})"
        if detail:
            line += f"\n  → {detail}"
        return line

    async def advance(self, step: int = 1, detail: str = ""):
        self.current = min(self.current + step, self.total)
        now = time.time()
        if now - self._last_edit >= self.throttle or self.current >= self.total:
            try:
                await self.context.bot.edit_message_text(
                    chat_id=self.message.chat_id,
                    message_id=self.message.message_id,
                    text=self._render(detail),
                )
                self._last_edit = now
            except Exception:
                logger.debug("Silenced exception", exc_info=True)

    async def finish(self, summary: str = ""):
        text = summary or f"✅ {self.label}完成 ({self.total}/{self.total})"
        try:
            await self.context.bot.edit_message_text(
                chat_id=self.message.chat_id,
                message_id=self.message.message_id,
                text=text,
            )
        except Exception:
            logger.debug("Silenced exception", exc_info=True)


# ============ 错误恢复 — 搬运自 n3d1117/chatgpt-telegram-bot ============


async def send_error_with_retry(update, context, error: Exception, retry_command: str = ""):
    """出错时显示重试按钮，而不是死胡同

    搬运自 n3d1117 的 error recovery 模式:
    - 分类错误类型，给用户可读的提示
    - 附加重试按钮，一键重新执行
    """
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup

    # 延迟导入: 打破 telegram_ux ↔ bot 的循环依赖
    from src.bot.error_messages import error_ai_busy, error_rate_limit, error_network, error_auth, error_generic

    err_str = str(error).lower()
    if "timeout" in err_str or "timed out" in err_str:
        user_msg = error_ai_busy()
    elif "rate" in err_str or "429" in err_str:
        user_msg = error_rate_limit()
    elif "connect" in err_str or "network" in err_str:
        user_msg = error_network()
    elif "auth" in err_str or "401" in err_str:
        user_msg = error_auth()
    else:
        user_msg = error_generic(str(error))

    keyboard = None
    if retry_command:
        keyboard = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton("🔄 重试", callback_data=f"cmd:{retry_command}"),
                    InlineKeyboardButton("📊 系统状态", callback_data="cmd:/status"),
                ]
            ]
        )

    try:
        await update.effective_message.reply_text(
            user_msg,
            reply_markup=keyboard,
        )
    except Exception:
        logger.debug("Silenced exception", exc_info=True)


# ============ 通知批量合并 — 防止 auto_trader 刷屏 ============


class NotificationBatcher:
    """智能通知合并器 — 搬运自 freqtrade 的通知节流思路

    同一 chat_id 的通知在 flush_interval 内合并为一条，
    避免自动交易循环连发 10+ 条消息。

    用法:
        batcher = NotificationBatcher(bot_send_func)
        await batcher.add(chat_id, "扫描完成: 50 个标的")
        await batcher.add(chat_id, "候选: AAPL, NVDA, TSLA")
        # 30秒后自动合并发送，或手动 flush
    """

    def __init__(self, send_func, flush_interval: float = 30.0, max_batch: int = 10):
        self.send_func = send_func
        self.flush_interval = flush_interval
        self.max_batch = max_batch
        self._buffers: dict = {}
        self._timers: dict = {}
        self._lock = asyncio.Lock()

    async def add(self, chat_id: int, text: str, force: bool = False):
        """添加通知。force=True 立即发送不合并（用于关键告警）"""
        if force:
            await self.send_func(text)
            return

        async with self._lock:
            if chat_id not in self._buffers:
                self._buffers[chat_id] = []
            self._buffers[chat_id].append(text)

            if len(self._buffers[chat_id]) >= self.max_batch:
                await self._flush(chat_id)
            elif chat_id not in self._timers:
                task = asyncio.create_task(self._delayed_flush(chat_id))

                def _flush_done(t):
                    if not t.cancelled() and t.exception():
                        logger.debug("[TelegramUX] flush 异常: %s", t.exception())

                task.add_done_callback(_flush_done)
                self._timers[chat_id] = task

    async def _delayed_flush(self, chat_id: int):
        await asyncio.sleep(self.flush_interval)
        async with self._lock:
            await self._flush(chat_id)

    async def _flush(self, chat_id: int):
        items = self._buffers.pop(chat_id, [])
        timer = self._timers.pop(chat_id, None)
        if timer and not timer.done():
            timer.cancel()
        if not items:
            return

        if len(items) == 1:
            await self.send_func(items[0])
        else:
            merged = f"📋 {len(items)} 条更新\n{'─' * 20}\n"
            merged += "\n\n".join(f"• {t[:200]}" for t in items)
            await self.send_func(merged)


# ============ 结构化卡片 — 搬运自 father-bot 的格式化模式 ============


def format_trade_card(trade: dict) -> str:
    """交易通知卡片 — 搬运自 freqtrade 的通知格式

    支持两种数据源:
    - 自动交易信号: entry_price, stop_loss, take_profit, confidence
    - 手动交易结果: price, total, remaining_cash, profit
    """
    side = trade.get("action", "BUY")
    emoji = "🟢" if side == "BUY" else "🔴"
    side_label = "买入" if side in ("BUY", "买入") else "卖出"
    symbol = trade.get("symbol", "???")
    qty = trade.get("quantity", 0)

    # 兼容两种字段名: entry_price (信号) vs price (手动)
    entry = trade.get("entry_price") or trade.get("price", 0)
    stop = trade.get("stop_loss", 0)
    target = trade.get("take_profit", 0)
    reason = trade.get("reason", "")[:80]
    confidence = trade.get("confidence", 0)

    # 置信度标准化：统一到 0-10 显示
    if confidence <= 1.0:
        confidence_display = confidence * 10
    else:
        confidence_display = confidence

    # 入场价格：0 时显示"待定"
    entry_str = f"${entry:.2f}" if entry > 0 else "待定"

    lines = [
        f"{emoji} <b>{side_label} {symbol}</b> x{qty}",
        "━━━━━━━━━━━━━━━━━━━",
        f"📈 价格: {entry_str}",
    ]

    # 自动交易信号: 显示目标/止损/R:R
    if target and stop and entry:
        rr = abs(target - entry) / abs(entry - stop) if abs(entry - stop) > 0.01 else 0
        lines.append(f"🎯 目标: ${target:.2f} ({(target / entry - 1) * 100:+.1f}%)")
        lines.append(f"🛑 止损: ${stop:.2f} ({(stop / entry - 1) * 100:+.1f}%)")
        lines.append(f"📊 R:R = {rr:.1f} | 信心: {confidence_display:.0f}/10")

    # 手动交易结果: 显示总额/盈亏/余额
    total = trade.get("total", 0)
    if total:
        lines.append(f"💵 总额: ${total:,.2f}")
    profit = trade.get("profit")
    if profit is not None:
        sign = "+" if profit >= 0 else ""
        lines.append(f"📊 盈亏: {sign}${profit:,.2f}")
    remaining = trade.get("remaining_cash")
    if remaining is not None:
        lines.append(f"💰 余额: ${remaining:,.2f}")

    lines.append("━━━━━━━━━━━━━━━━━━━")
    if reason:
        lines.append(f"💡 {reason}")

    return "\n".join(lines)


def format_portfolio_card(positions: list, cash: float = 0) -> str:
    """持仓概览卡片 — 搬运自 father-bot 的 balance 格式"""
    if not positions:
        return "📊 <b>持仓概览</b>\n\n空仓，等待机会..."

    total_value = sum(abs(p.get("market_value", 0)) for p in positions) + cash
    lines = ["📊 <b>持仓概览</b>\n"]

    for pos in positions:
        sym = pos.get("symbol", "?")
        qty = pos.get("quantity", 0)
        cost = pos.get("avg_cost", 0)
        mkt_val = abs(pos.get("market_value", 0))
        pnl_pct = pos.get("pnl_pct", 0)

        emoji = "🟢" if pnl_pct >= 0 else "🔴"
        pct_of_total = (mkt_val / total_value * 100) if total_value > 0 else 0
        bar_len = int(pct_of_total / 10)  # 0% 显示全空，100% 显示全满
        bar = "█" * bar_len + "░" * (10 - bar_len)

        lines.append(
            f"{emoji} <b>{sym}</b> x{qty}\n   {bar} {pct_of_total:.1f}%\n   成本 ${cost:.2f} | PnL {pnl_pct:+.1f}%"
        )

    lines.append(f"\n💰 <b>总值: ${total_value:,.2f}</b> (现金 ${cash:,.2f})")
    return "\n".join(lines)


def format_quote_card(data: dict) -> str:
    """行情卡片 — 简洁的股票/加密货币行情展示"""
    symbol = data.get("symbol", "?")
    price = data.get("price", 0)
    change = data.get("change", 0)
    change_pct = data.get("change_pct", 0)
    volume = data.get("volume", 0)
    high = data.get("high", 0)
    low = data.get("low", 0)

    emoji = "🟢" if change >= 0 else "🔴"
    arrow = "▲" if change >= 0 else "▼"

    return (
        f"{emoji} <b>{symbol}</b>  ${price:,.2f}  {arrow}{change_pct:+.2f}%\n"
        f"   H ${high:,.2f} | L ${low:,.2f} | Vol {volume:,.0f}"
    )


# ============ 图表可视化 — 搬运自 freqtrade + PampCop 的 Telegram 图表模式 ============

import io


def _setup_chart_style():
    """设置 Telegram 友好的暗色图表风格"""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.style.use("dark_background")
    plt.rcParams.update(
        {
            "font.size": 13,
            "axes.titlesize": 15,
            "axes.labelsize": 12,
            "xtick.labelsize": 10,
            "ytick.labelsize": 10,
            "figure.facecolor": "#1a1a2e",
            "axes.facecolor": "#16213e",
            "grid.color": "#333333",
            "grid.alpha": 0.3,
        }
    )
    return plt


def generate_equity_chart(equity_curve: list, title: str = "权益曲线") -> io.BytesIO:
    """回测权益曲线图 — 搬运自 freqtrade 的 plot_profit 模式

    Args:
        equity_curve: 权益值列表 [10000, 10050, 9980, ...]
        title: 图表标题
    Returns:
        BytesIO PNG 图片，可直接 send_photo
    """
    # Try plotly version first (richer charts with drawdown shading)
    try:
        from src.charts import generate_equity_curve as plotly_equity

        png_bytes = plotly_equity(equity_curve, title=title)
        if png_bytes:
            return io.BytesIO(png_bytes)
    except Exception:
        logger.debug("Silenced exception", exc_info=True)
    # Fall through to matplotlib version below
    plt = _setup_chart_style()
    fig, ax = plt.subplots(figsize=(10, 5), dpi=150)

    ax.plot(equity_curve, color="#00d4aa", linewidth=2, alpha=0.9)
    ax.fill_between(range(len(equity_curve)), equity_curve, equity_curve[0], alpha=0.15, color="#00d4aa")

    # 标注最高点和最低点
    if equity_curve:
        max_idx = equity_curve.index(max(equity_curve))
        min_idx = equity_curve.index(min(equity_curve))
        ax.annotate(
            f"${max(equity_curve):,.0f}",
            xy=(max_idx, max(equity_curve)),
            fontsize=10,
            color="#2ecc71",
            ha="center",
            xytext=(0, 10),
            textcoords="offset points",
        )
        ax.annotate(
            f"${min(equity_curve):,.0f}",
            xy=(min_idx, min(equity_curve)),
            fontsize=10,
            color="#e74c3c",
            ha="center",
            xytext=(0, -15),
            textcoords="offset points",
        )

    ax.set_title(title, pad=12, color="#e0e0e0")
    ax.set_xlabel("交易日")
    ax.set_ylabel("权益 ($)")
    ax.grid(True)
    fig.tight_layout()

    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close(fig)
    buf.seek(0)
    buf.name = "equity.png"
    return buf


def generate_pnl_chart(trades: list, title: str = "交易盈亏") -> io.BytesIO:
    """交易 PnL 柱状图 — 搬运自 freqtrade 的 trade_list 可视化

    Args:
        trades: [{"symbol": "AAPL", "pnl": 50.0}, {"symbol": "NVDA", "pnl": -20.0}, ...]
    """
    # Try plotly version first (waterfall chart, richer visualization)
    try:
        from src.charts import generate_pnl_waterfall as plotly_pnl

        png_bytes = plotly_pnl(trades, title=title)
        if png_bytes:
            return io.BytesIO(png_bytes)
    except Exception:
        logger.debug("Silenced exception", exc_info=True)
    # Fall through to matplotlib version below
    plt = _setup_chart_style()
    fig, ax = plt.subplots(figsize=(10, 5), dpi=150)

    symbols = [t.get("symbol", "?") for t in trades]
    pnls = [t.get("pnl", 0) for t in trades]
    colors = ["#2ecc71" if p >= 0 else "#e74c3c" for p in pnls]

    bars = ax.bar(range(len(pnls)), pnls, color=colors, alpha=0.85, width=0.7)

    # 在柱子上标注数值
    for bar, pnl in zip(bars, pnls):
        y = bar.get_height()
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            y,
            f"${pnl:+.0f}",
            ha="center",
            va="bottom" if pnl >= 0 else "top",
            fontsize=9,
            color="#e0e0e0",
        )

    ax.set_xticks(range(len(symbols)))
    ax.set_xticklabels(symbols, rotation=45, ha="right")
    ax.set_title(title, pad=12, color="#e0e0e0")
    ax.set_ylabel("盈亏 ($)")
    ax.axhline(y=0, color="#666666", linewidth=0.8)
    ax.grid(True, axis="y")
    fig.tight_layout()

    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close(fig)
    buf.seek(0)
    buf.name = "pnl.png"
    return buf


def generate_portfolio_pie(positions: list, title: str = "持仓分布") -> io.BytesIO:
    """持仓分布饼图 — 简洁版，适合 Telegram 移动端

    Args:
        positions: [{"symbol": "AAPL", "market_value": 5000}, ...]
    """
    # Try plotly version first (interactive-style pie with pull-out)
    try:
        from src.charts import generate_portfolio_pie as plotly_pie

        png_bytes = plotly_pie(positions, title=title)
        if png_bytes:
            return io.BytesIO(png_bytes)
    except Exception:
        logger.debug("Silenced exception", exc_info=True)
    # Fall through to matplotlib version below
    plt = _setup_chart_style()
    fig, ax = plt.subplots(figsize=(8, 8), dpi=150)

    symbols = [p.get("symbol", "?") for p in positions]
    values = [abs(p.get("market_value", 0)) for p in positions]
    total = sum(values) or 1

    # 颜色方案
    chart_colors = ["#00d4aa", "#3498db", "#e74c3c", "#f39c12", "#9b59b6", "#1abc9c", "#e67e22", "#2ecc71"]
    colors = [chart_colors[i % len(chart_colors)] for i in range(len(symbols))]

    wedges, texts, autotexts = ax.pie(
        values,
        labels=symbols,
        autopct=lambda p: f"{p:.1f}%" if p > 3 else "",
        colors=colors,
        startangle=90,
        pctdistance=0.8,
        textprops={"color": "#e0e0e0", "fontsize": 12},
    )
    for t in autotexts:
        t.set_fontsize(10)
        t.set_color("#ffffff")

    ax.set_title(f"{title}\n总值 ${total:,.0f}", pad=15, color="#e0e0e0", fontsize=14)
    fig.tight_layout()

    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close(fig)
    buf.seek(0)
    buf.name = "portfolio.png"
    return buf


def generate_sector_pie(sector_values: dict, title: str = "行业分布") -> io.BytesIO:
    """行业分布饼图 — 按 sector 聚合市值后展示

    Args:
        sector_values: {"Technology": 5000, "Healthcare": 3000, ...}
        title: 图表标题
    Returns:
        BytesIO PNG 图片
    """
    plt = _setup_chart_style()
    fig, ax = plt.subplots(figsize=(8, 8), dpi=150)

    # 按市值降序排列
    sorted_items = sorted(sector_values.items(), key=lambda x: x[1], reverse=True)
    sectors = [s for s, _ in sorted_items]
    values = [v for _, v in sorted_items]
    total = sum(values) or 1

    # 行业名中英对照（常见行业翻译）
    sector_cn = {
        "Technology": "科技",
        "Healthcare": "医疗",
        "Financial Services": "金融",
        "Consumer Cyclical": "可选消费",
        "Communication Services": "通信",
        "Industrials": "工业",
        "Consumer Defensive": "必需消费",
        "Energy": "能源",
        "Utilities": "公用事业",
        "Real Estate": "房地产",
        "Basic Materials": "基础材料",
        "未知": "未知",
    }
    labels = [sector_cn.get(s, s) for s in sectors]

    # 颜色方案（行业风格配色）
    sector_colors = [
        "#00d4aa",
        "#3498db",
        "#e74c3c",
        "#f39c12",
        "#9b59b6",
        "#1abc9c",
        "#e67e22",
        "#2ecc71",
        "#ff6b6b",
        "#4ecdc4",
        "#45b7d1",
        "#96ceb4",
    ]
    colors = [sector_colors[i % len(sector_colors)] for i in range(len(sectors))]

    wedges, texts, autotexts = ax.pie(
        values,
        labels=labels,
        autopct=lambda p: f"{p:.1f}%" if p > 3 else "",
        colors=colors,
        startangle=90,
        pctdistance=0.8,
        textprops={"color": "#e0e0e0", "fontsize": 12},
    )
    for t in autotexts:
        t.set_fontsize(10)
        t.set_color("#ffffff")

    ax.set_title(f"{title}\n总值 ${total:,.0f}", pad=15, color="#e0e0e0", fontsize=14)
    fig.tight_layout()

    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close(fig)
    buf.seek(0)
    buf.name = "sector.png"
    return buf


async def send_chart(update, context, chart_buf: io.BytesIO, caption: str = ""):
    """发送图表到 Telegram — 带降级（matplotlib 不可用时发文字）"""
    try:
        await update.message.reply_photo(
            photo=chart_buf,
            caption=caption,
            reply_to_message_id=update.message.message_id,
        )
    except Exception as e:
        logger.warning("[Chart] 图片发送失败: %s, 降级为文字", e)
        if caption:
            await update.message.reply_text(caption)


# ══════════════════════════════════════════════════════
# P3-2: Telegram 卡片 Builder 链式 API
# 借鉴 aiogram (5.5k⭐) InlineKeyboardBuilder 模式
# ══════════════════════════════════════════════════════

from telegram import InlineKeyboardButton, InlineKeyboardMarkup


class CardBuilder:
    """Telegram 消息卡片链式构建器

    借鉴 aiogram 的 InlineKeyboardBuilder 链式 API:
    - 所有方法返回 self，支持链式调用
    - 自动处理 Markdown 转义
    - 内置按钮行管理

    用法:
        card = (CardBuilder("📊 AAPL 技术分析")
            .line("价格: $175.50")
            .line("RSI: 65.3 | MACD: 看涨")
            .separator()
            .line("信号: ⬆️ 买入 (评分 72/100)")
            .button("详细分析", "detail_AAPL")
            .button("加自选", "watch_AAPL")
            .button_row()
            .button("取消", "cancel")
        )
        await card.send(update)
    """

    def __init__(self, title: str = ""):
        self._title = title
        self._lines: list = []
        self._buttons: list = []  # 当前行的按钮
        self._button_rows: list = []  # 所有按钮行
        self._parse_mode = "Markdown"

    def title(self, text: str) -> "CardBuilder":
        """设置标题（加粗）"""
        self._title = text
        return self

    def line(self, text: str) -> "CardBuilder":
        """添加一行文本"""
        self._lines.append(text)
        return self

    def lines(self, texts: list) -> "CardBuilder":
        """批量添加多行文本"""
        self._lines.extend(texts)
        return self

    def separator(self, char: str = "─", length: int = 20) -> "CardBuilder":
        """添加分隔线"""
        self._lines.append(char * length)
        return self

    def blank(self) -> "CardBuilder":
        """添加空行"""
        self._lines.append("")
        return self

    def kv(self, key: str, value: str) -> "CardBuilder":
        """添加键值对行"""
        self._lines.append(f"{key}: `{value}`")
        return self

    def kvs(self, pairs: dict) -> "CardBuilder":
        """批量添加键值对"""
        for k, v in pairs.items():
            self._lines.append(f"{k}: `{v}`")
        return self

    def button(self, text: str, callback_data: str = "", url: str = "") -> "CardBuilder":
        """添加一个按钮到当前行"""
        if url:
            self._buttons.append(InlineKeyboardButton(text=text, url=url))
        else:
            self._buttons.append(InlineKeyboardButton(text=text, callback_data=callback_data or text))
        return self

    def button_row(self) -> "CardBuilder":
        """结束当前按钮行，开始新行"""
        if self._buttons:
            self._button_rows.append(self._buttons)
            self._buttons = []
        return self

    def build_text(self) -> str:
        """构建消息文本"""
        parts = []
        if self._title:
            parts.append(f"*{self._title}*")
        if self._lines:
            parts.append("\n".join(self._lines))
        return "\n".join(parts)

    def build_keyboard(self) -> Optional[InlineKeyboardMarkup]:
        """构建键盘"""
        # 自动结束最后一行
        if self._buttons:
            self._button_rows.append(self._buttons)
            self._buttons = []
        if not self._button_rows:
            return None
        return InlineKeyboardMarkup(self._button_rows)

    async def send(self, update: Update, **kwargs) -> None:
        """发送构建好的卡片"""
        text = self.build_text()
        keyboard = self.build_keyboard()
        try:
            await update.message.reply_text(
                text=text,
                parse_mode=self._parse_mode,
                reply_markup=keyboard,
                **kwargs,
            )
        except Exception:
            # Markdown 解析失败时降级为纯文本
            await update.message.reply_text(
                text=text.replace("*", "").replace("`", ""),
                reply_markup=keyboard,
                **kwargs,
            )

    async def edit(self, query, **kwargs) -> None:
        """编辑已有消息（用于 callback query 场景）"""
        text = self.build_text()
        keyboard = self.build_keyboard()
        try:
            await query.edit_message_text(
                text=text,
                parse_mode=self._parse_mode,
                reply_markup=keyboard,
                **kwargs,
            )
        except Exception:
            await query.edit_message_text(
                text=text.replace("*", "").replace("`", ""),
                reply_markup=keyboard,
                **kwargs,
            )
