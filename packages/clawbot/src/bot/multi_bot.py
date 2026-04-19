"""
MultiBot 核心类 — 组合所有 Mixin，提供 __init__ / run / stop
"""

import logging
from typing import Tuple, Optional

from src.bot.globals import (
    chat_router,
    health_checker,
    shared_memory,
    ALLOWED_USER_IDS,
)

# 幻影导入修复: BotCapability/get_bot_config 从实际定义模块导入
from src.routing.models import BotCapability
from config.bot_profiles import get_bot_config
from config.prompts import SOUL_CORE
from src.http_client import ResilientHTTPClient, RetryConfig, CircuitBreaker

from src.bot.api_mixin import APIMixin
from src.bot.cmd_basic_mixin import BasicCommandsMixin
from src.bot.cmd_invest_mixin import InvestCommandsMixin
from src.bot.cmd_analysis_mixin import AnalysisCommandsMixin
from src.bot.cmd_ibkr_mixin import IBKRCommandsMixin
from src.bot.cmd_trading_mixin import TradingCommandsMixin
from src.bot.cmd_collab_mixin import CollabCommandsMixin
from src.bot.cmd_execution_mixin import ExecutionCommandsMixin
from src.bot.chinese_nlp_mixin import ChineseNLPMixin
from src.bot.ocr_mixin import OCRHandlerMixin
from src.bot.message_mixin import MessageHandlerMixin
from src.bot.cmd_intel_mixin import IntelCommandMixin
from src.error_handler import get_error_handler

logger = logging.getLogger(__name__)


# ── v2.0: 实时上下文注入 — 让 LLM 看到用户的真实数据 ─────────
# 每次对话自动注入 ~500 token 的用户实时状态到 system prompt
# 使得 "最近交易做得怎么样" 能得到基于真实 P&L 的回答

import time as _time
import threading as _threading

_live_context_cache = {"text": "", "ts": 0}
_LIVE_CONTEXT_TTL = 60  # 缓存60秒，避免每条消息都拉取
_live_context_lock = _threading.Lock()  # 线程锁：PTB concurrent_updates=True 下多线程访问保护（HI-467）


def _build_live_context() -> str:
    """构建用户实时状态摘要 — 注入 system prompt

    拉取: 持仓概览 / 交易绩效 / 待办事项 / 市场概要
    全部从内存/本地数据获取，不做网络请求 (< 10ms)
    """
    now = _time.monotonic()
    with _live_context_lock:
        if now - _live_context_cache["ts"] < _LIVE_CONTEXT_TTL:
            return _live_context_cache["text"]

    sections = []

    # 1. 持仓概览 (from position_monitor — 内存数据)
    try:
        from src.position_monitor import position_monitor

        if position_monitor and position_monitor.positions:
            status = position_monitor.get_status()
            lines = []
            total_pnl = status.get("total_unrealized_pnl", 0)
            lines.append(f"持仓{status.get('monitored_count', 0)}个, 总浮盈亏${total_pnl:+,.2f}")
            for p in status.get("positions", [])[:5]:
                sym = p["symbol"]
                pnl_pct = p.get("unrealized_pnl_pct", 0)
                cur = p.get("current_price", 0)
                sl = p.get("stop_loss", 0)
                line = f"  {sym} ${cur:.2f} ({pnl_pct:+.1f}%)"
                if sl > 0:
                    line += f" SL=${sl:.2f}"
                lines.append(line)
            sections.append("持仓: " + "; ".join(lines))
    except Exception as e:
        logger.debug("静默异常: %s", e)

    # 2. 交易绩效 (from trading_journal — SQLite本地数据)
    try:
        from src.trading_journal import journal

        if journal:
            today = journal.get_today_pnl()
            if today and today.get("trades", 0) > 0:
                sections.append(
                    f"今日交易: {today['trades']}笔 "
                    f"胜{today.get('wins', 0)} 负{today.get('losses', 0)} "
                    f"盈亏${today.get('pnl', 0):+,.2f}"
                )
            perf = journal.get_performance(days=7)
            if perf and perf.get("total_trades", 0) > 0:
                sections.append(
                    f"7日绩效: {perf['total_trades']}笔 "
                    f"胜率{perf.get('win_rate', 0):.0f}% "
                    f"盈亏${perf.get('total_pnl', 0):+,.2f}"
                )
    except Exception as e:
        logger.debug("静默异常: %s", e)

    # 3. 待办事项 (from task_mgmt — SQLite本地数据)
    try:
        from src.execution.task_mgmt import top_tasks

        tasks = top_tasks(limit=3)
        if tasks:
            task_str = ", ".join(t.get("title", "")[:20] for t in tasks)
            sections.append(f"待办: {task_str}")
    except Exception as e:
        logger.debug("静默异常: %s", e)

    # 4. 可用操作提示 (让 LLM 知道可以建议用户说什么)
    sections.append('用户可以说中文指令: "帮我买X股Y" "Y能买吗" "Y多少钱" "帮我找便宜的Z" "分析Y" 来触发实际操作')

    if not sections:
        with _live_context_lock:
            _live_context_cache["text"] = ""
            _live_context_cache["ts"] = now
        return ""

    text = "\n\n【实时状态】\n" + "\n".join(f"• {s}" for s in sections) + "\n"
    with _live_context_lock:
        _live_context_cache["text"] = text
        _live_context_cache["ts"] = now
    return text


class MultiBot(
    APIMixin,
    BasicCommandsMixin,
    InvestCommandsMixin,
    AnalysisCommandsMixin,
    IBKRCommandsMixin,
    TradingCommandsMixin,
    CollabCommandsMixin,
    ExecutionCommandsMixin,
    IntelCommandMixin,
    ChineseNLPMixin,
    OCRHandlerMixin,
    MessageHandlerMixin,
):
    """支持群聊的多机器人 — 使用共享基础设施 + Mixin 架构"""

    def __init__(self, config: dict):
        self.config = config
        self.bot_id = config["id"]
        self.model = config["model"]
        self.is_claude = config.get("is_claude", False)
        self.api_type = config.get("api_type", "siliconflow")
        self.username = config.get("username", "")

        # 从 bot_profiles 获取人设
        profile = get_bot_config(self.bot_id)
        self.name = profile.get("name", config["id"])
        self.emoji = profile.get("emoji", "\U0001f916")
        self.role = profile.get("personality", "AI助手")
        self._base_system_prompt = profile.get("system_prompt", SOUL_CORE)

        self.max_messages = 30
        self.app = None

        # HTTP 客户端超时（LiteLLM 可能触发 Fallback，给足够时间）
        if self.api_type in ("kiro", "g4f", "free_pool", "free_first"):
            api_timeout = 120.0
        else:
            api_timeout = 60.0

        self.http_client = ResilientHTTPClient(
            timeout=api_timeout,
            retry_config=RetryConfig(max_retries=2, base_delay=2.0),
            circuit_breaker=CircuitBreaker(failure_threshold=5, recovery_timeout=60.0),
            name=self.bot_id,
        )

        # 注册到路由器
        chat_router.register_bot(
            BotCapability(
                bot_id=self.bot_id,
                name=self.name,
                username=self.username,
                keywords=config.get("keywords", []),
                domains=profile.get("domains", []),
            )
        )

        # 注册到健康检查
        health_checker.register_bot(self.bot_id)

    @property
    def system_prompt(self) -> str:
        # v3.0: 缩减 shared_memory 500→200 tokens (live_context 已覆盖实时数据)
        memory_context = shared_memory.get_context_for_prompt(max_tokens=200)
        live_context = _build_live_context()
        return self._base_system_prompt + memory_context + live_context

    def _get_chat_mode_prompt(self, user_id: int) -> str:
        """根据用户 chat_mode 偏好返回额外的系统提示 — 搬运自 father-bot 的 chat_modes"""
        from src.bot.globals import user_prefs

        mode = user_prefs.get(user_id, "chat_mode", "assistant")
        if mode == "assistant":
            return ""  # 默认模式，不加额外提示
        mode_prompts = {
            "trader": (
                "\n\n[交易员模式] 你现在是一个专业的短线交易员。"
                "回答时优先关注：入场/出场时机、风险回报比、仓位管理、技术指标信号。"
                "用简洁的交易术语，给出明确的操作建议（买入/卖出/观望），附带具体价位。"
                "不要废话，直接给结论。"
            ),
            "analyst": (
                "\n\n[分析师模式] 你现在是一个深度研究分析师。"
                "回答时注重：数据支撑、多角度分析、风险因素、长期趋势。"
                "引用具体数据和指标，给出结构化的分析框架。"
                "保持客观中立，呈现多种可能性。"
            ),
            "creative": (
                "\n\n[创意模式] 你现在是一个社媒内容创作者。"
                "回答时注重：吸引力、传播性、情绪共鸣、故事性。"
                "用口语化的表达，像跟朋友聊天。"
                "给出多个创意方向，每个都要有钩子。"
            ),
        }
        return mode_prompts.get(mode, "")

    def _is_authorized(self, user_id: int) -> bool:
        if not ALLOWED_USER_IDS:
            return True
        return user_id in ALLOWED_USER_IDS

    async def delegate_tool_to_claude(self, tool_name: str, tool_input: dict) -> dict:
        """委托工具调用给 Claude（供其他 Bot 使用）"""
        from src.bot.globals import tool_executor

        return await tool_executor.execute(tool_name, tool_input)

    async def _should_respond_async(
        self, text: str, chat_type: str, message_id: Optional[int] = None, from_user_id: Optional[int] = None
    ) -> Tuple[bool, str]:
        return await chat_router.should_respond_async(self.bot_id, text, chat_type, message_id, from_user_id)

    def _should_respond(
        self, text: str, chat_type: str, message_id: Optional[int] = None, from_user_id: Optional[int] = None
    ) -> Tuple[bool, str]:
        return chat_router.should_respond(self.bot_id, text, chat_type, message_id, from_user_id)

    # ============ 启动 / 停止 ============

    async def run_async(self):
        if not self.config["token"]:
            logger.warning(f"[{self.name}] 未配置 Token，跳过")
            return None

        from telegram import Update
        from telegram.ext import (
            ApplicationBuilder,
            CommandHandler,
            MessageHandler,
            CallbackQueryHandler,
            filters,
        )

        self.app = (
            ApplicationBuilder()
            .token(self.config["token"])
            .connect_timeout(30)
            .read_timeout(30)
            .write_timeout(15)
            .pool_timeout(10.0)
            .connection_pool_size(256)
            .concurrent_updates(True)
            .build()
        )

        # 全局错误处理器 — 接入 error_handler.py
        error_handler = get_error_handler()
        if error_handler:
            self.app.add_error_handler(error_handler.telegram_error_handler)

        # 注册引导向导 ConversationHandler（必须第一个注册，优先于其他 CommandHandler）
        onboarding_conv = self.build_onboarding_handler()
        self.app.add_handler(onboarding_conv)

        # 注册命令
        self.app.add_handler(CommandHandler("clear", self.cmd_clear))
        self.app.add_handler(CommandHandler("status", self.cmd_status))
        self.app.add_handler(CommandHandler("draw", self.cmd_draw))
        self.app.add_handler(CommandHandler("news", self.cmd_news))
        self.app.add_handler(CommandHandler("help", self.cmd_help))
        self.app.add_handler(CommandHandler("metrics", self.cmd_metrics))
        self.app.add_handler(CommandHandler("lanes", self.cmd_lanes))
        self.app.add_handler(CommandHandler("collab", self.cmd_collab))
        self.app.add_handler(CommandHandler("context", self.cmd_context))
        self.app.add_handler(CommandHandler("compact", self.cmd_compact))
        self.app.add_handler(CommandHandler("discuss", self.cmd_discuss))
        self.app.add_handler(CommandHandler("stop_discuss", self.cmd_stop_discuss))
        self.app.add_handler(CommandHandler("quote", self.cmd_quote))
        self.app.add_handler(CommandHandler("calc", self.cmd_calc))
        self.app.add_handler(CommandHandler("market", self.cmd_market))
        self.app.add_handler(CommandHandler("portfolio", self.cmd_portfolio))
        self.app.add_handler(CommandHandler("buy", self.cmd_buy))
        self.app.add_handler(CommandHandler("sell", self.cmd_sell))
        self.app.add_handler(CommandHandler("watchlist", self.cmd_watchlist))
        self.app.add_handler(CommandHandler("invest", self.cmd_invest))
        self.app.add_handler(CommandHandler("trades", self.cmd_trades))
        self.app.add_handler(CommandHandler("reset_portfolio", self.cmd_reset_portfolio))
        self.app.add_handler(CommandHandler("ta", self.cmd_ta))
        self.app.add_handler(CommandHandler("scan", self.cmd_scan))
        self.app.add_handler(CommandHandler("signal", self.cmd_signal))
        self.app.add_handler(CommandHandler("performance", self.cmd_performance))
        self.app.add_handler(CommandHandler("review", self.cmd_review))
        self.app.add_handler(CommandHandler("journal", self.cmd_journal))
        self.app.add_handler(CommandHandler("accuracy", self.cmd_accuracy))
        self.app.add_handler(CommandHandler("equity", self.cmd_equity))
        self.app.add_handler(CommandHandler("targets", self.cmd_targets))
        self.app.add_handler(CommandHandler("chart", self.cmd_chart))
        self.app.add_handler(CommandHandler("drl", self.cmd_drl))
        self.app.add_handler(CommandHandler("factors", self.cmd_factors))
        self.app.add_handler(CommandHandler("ibuy", self.cmd_ibuy))
        self.app.add_handler(CommandHandler("isell", self.cmd_isell))
        self.app.add_handler(CommandHandler("ipositions", self.cmd_ipositions))
        self.app.add_handler(CommandHandler("iorders", self.cmd_iorders))
        self.app.add_handler(CommandHandler("iaccount", self.cmd_iaccount))
        self.app.add_handler(CommandHandler("icancel", self.cmd_icancel))
        self.app.add_handler(CommandHandler("autotrader", self.cmd_autotrader))
        self.app.add_handler(CommandHandler("risk", self.cmd_risk))
        self.app.add_handler(CommandHandler("monitor", self.cmd_monitor))
        self.app.add_handler(CommandHandler("tradingsystem", self.cmd_tradingsystem))
        self.app.add_handler(CommandHandler("backtest", self.cmd_backtest))
        self.app.add_handler(CommandHandler("rebalance", self.cmd_rebalance))
        self.app.add_handler(CommandHandler("ops", self.cmd_ops))
        self.app.add_handler(CommandHandler("dev", self.cmd_dev))
        self.app.add_handler(CommandHandler("brief", self.cmd_brief))
        self.app.add_handler(CommandHandler("hot", self.cmd_hot))
        self.app.add_handler(CommandHandler("hotpost", self.cmd_hotpost))
        self.app.add_handler(CommandHandler("lane", self.cmd_lane))
        self.app.add_handler(CommandHandler("cost", self.cmd_cost))
        self.app.add_handler(CommandHandler("config", self.cmd_config))
        self.app.add_handler(CommandHandler("topic", self.cmd_topic))
        self.app.add_handler(CommandHandler("xhs", self.cmd_xhs))
        self.app.add_handler(CommandHandler("post", self.cmd_post))
        self.app.add_handler(CommandHandler("social_plan", self.cmd_social_plan))
        self.app.add_handler(CommandHandler("social_repost", self.cmd_social_repost))
        self.app.add_handler(CommandHandler("social_launch", self.cmd_social_launch))
        self.app.add_handler(CommandHandler("social_persona", self.cmd_social_persona))
        self.app.add_handler(CommandHandler("post_social", self.cmd_post_social))
        self.app.add_handler(CommandHandler("post_x", self.cmd_post_x))
        self.app.add_handler(CommandHandler("post_xhs", self.cmd_post_xhs))
        self.app.add_handler(CommandHandler("xwatch", self.cmd_xwatch))
        self.app.add_handler(CommandHandler("xbrief", self.cmd_xbrief))
        self.app.add_handler(CommandHandler("xdraft", self.cmd_xdraft))
        self.app.add_handler(CommandHandler("xpost", self.cmd_xpost))
        self.app.add_handler(CommandHandler("xhsdraft", self.cmd_xhsdraft))
        self.app.add_handler(CommandHandler("xhspost", self.cmd_xhspost))
        self.app.add_handler(CommandHandler("dualpost", self.cmd_post))  # dualpost 是 post 的别名
        self.app.add_handler(CommandHandler("publish", self.cmd_publish))
        self.app.add_handler(CommandHandler("xianyu", self.cmd_xianyu))
        self.app.add_handler(CommandHandler("xianyu_report", self.cmd_xianyu_report))
        self.app.add_handler(CommandHandler("xianyu_style", self.cmd_xianyu_style))
        self.app.add_handler(CommandHandler("social_calendar", self.cmd_social_calendar))
        self.app.add_handler(CommandHandler("social_report", self.cmd_social_report))
        self.app.add_handler(CommandHandler("model", self.cmd_model))
        self.app.add_handler(CommandHandler("pool", self.cmd_pool))
        self.app.add_handler(CommandHandler("keyhealth", self.cmd_keyhealth))
        self.app.add_handler(CommandHandler("memory", self.cmd_memory))
        self.app.add_handler(CommandHandler("settings", self.cmd_settings))
        self.app.add_handler(CommandHandler("voice", self.cmd_voice))
        self.app.add_handler(CommandHandler("export", self.cmd_export))
        self.app.add_handler(CommandHandler("qr", self.cmd_qr))
        self.app.add_handler(CommandHandler("agent", self.cmd_agent))
        self.app.add_handler(CommandHandler("tts", self.cmd_tts))
        self.app.add_handler(CommandHandler("novel", self.cmd_novel))
        self.app.add_handler(CommandHandler("evolution", self.cmd_evolution))
        self.app.add_handler(CommandHandler("perf", self.cmd_perf))
        self.app.add_handler(CommandHandler("ship", self.cmd_ship))
        self.app.add_handler(CommandHandler("weekly", self.cmd_weekly))
        self.app.add_handler(CommandHandler("review_history", self.cmd_review_history))
        self.app.add_handler(CommandHandler("bill", self.cmd_bill))
        self.app.add_handler(CommandHandler("pricewatch", self.cmd_pricewatch))
        self.app.add_handler(CommandHandler("intel", self.cmd_intel))
        self.app.add_handler(CommandHandler("coupon", self.cmd_coupon))
        self.app.add_handler(CommandHandler("test_token", self.cmd_test_token))
        self.app.add_handler(CommandHandler("set_coupon_token", self.cmd_set_coupon_token))
        self.app.add_handler(CallbackQueryHandler(self.handle_trade_callback, pattern=r"^itrade"))
        self.app.add_handler(CallbackQueryHandler(self.handle_help_callback, pattern=r"^help:"))
        # onboard: 回调已由 ConversationHandler 内部处理，无需单独注册
        self.app.add_handler(CallbackQueryHandler(self.handle_feedback_callback, pattern=r"^fb\|"))
        self.app.add_handler(CallbackQueryHandler(self.handle_memory_callback, pattern=r"^mem_"))
        self.app.add_handler(CallbackQueryHandler(self.handle_settings_callback, pattern=r"^settings\|"))
        self.app.add_handler(CallbackQueryHandler(self.handle_notify_action_callback, pattern=r"^cmd:"))
        self.app.add_handler(CallbackQueryHandler(self.handle_social_confirm_callback, pattern=r"^social_confirm:"))
        self.app.add_handler(CallbackQueryHandler(self.handle_ops_menu_callback, pattern=r"^ops_"))
        self.app.add_handler(CallbackQueryHandler(self.handle_intel_callback, pattern=r"^intel_"))
        self.app.add_handler(CallbackQueryHandler(self.handle_quote_action_callback, pattern=r"^(ta_|buy_|watch_)"))
        self.app.add_handler(
            CallbackQueryHandler(
                self.handle_card_action_callback, pattern=r"^(trade:|bt:|ta:|analyze:|news:|evo:|retry:|shop:|post:)"
            )
        )
        self.app.add_handler(CallbackQueryHandler(self.handle_clarification_callback, pattern=r"^\d+:.+:.+$"))
        self.app.add_handler(CallbackQueryHandler(self.handle_suggest_callback, pattern=r"^suggest:"))
        self.app.add_handler(CallbackQueryHandler(lambda u, c: u.callback_query.answer(), pattern=r"^noop$"))

        self.app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message))
        self.app.add_handler(MessageHandler(filters.PHOTO, self.handle_photo))
        self.app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, self.handle_voice))
        self.app.add_handler(
            MessageHandler(
                filters.Document.PDF
                | filters.Document.IMAGE
                | filters.Document.MimeType(
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                )  # .docx
                | filters.Document.MimeType(
                    "application/vnd.openxmlformats-officedocument.presentationml.presentation"
                )  # .pptx
                | filters.Document.MimeType(
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )  # .xlsx
                | filters.Document.MimeType("application/msword")  # .doc
                | filters.Document.MimeType("application/vnd.ms-excel")  # .xls
                | filters.Document.MimeType("application/vnd.ms-powerpoint"),  # .ppt
                self.handle_document_ocr,
            )
        )

        # Inline Query — @bot 搜股票/记忆（搬运自 freqtrade + yym68686 模式）
        from telegram.ext import InlineQueryHandler

        self.app.add_handler(InlineQueryHandler(self.handle_inline_query))

        await self.app.initialize()
        try:
            await self.app.bot.set_my_commands(self.config.get("commands", []))
        except Exception as e:
            logger.debug("[%s] 设置命令菜单失败: %s", self.name, e)

        await self.app.start()
        await self.app.updater.start_polling(
            allowed_updates=Update.ALL_TYPES,
            drop_pending_updates=True,
        )

        logger.info(f"[{self.name}] 启动成功 - {self.role} ({self.model.split('/')[-1]})")
        return self

    async def stop_async(self):
        if self.app:
            try:
                await self.app.updater.stop()
                await self.app.stop()
                await self.app.shutdown()
            except Exception as e:
                logger.debug(f"[{self.name}] 停止时出错: {e}")
