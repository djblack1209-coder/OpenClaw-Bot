"""
MultiBot 核心类 — 组合所有 Mixin，提供 __init__ / run / stop
"""
import logging
from typing import Tuple, Optional

from src.bot.globals import (
    chat_router, health_checker, shared_memory,
    history_store, context_manager,
    bot_registry, ALLOWED_USER_IDS,
    BotCapability, get_bot_config,
)
from src.http_client import ResilientHTTPClient, RetryConfig, CircuitBreaker

from src.bot.api_mixin import APIMixin
from src.bot.cmd_basic_mixin import BasicCommandsMixin
from src.bot.cmd_invest_mixin import InvestCommandsMixin
from src.bot.cmd_analysis_mixin import AnalysisCommandsMixin
from src.bot.cmd_ibkr_mixin import IBKRCommandsMixin
from src.bot.cmd_trading_mixin import TradingCommandsMixin
from src.bot.cmd_collab_mixin import CollabCommandsMixin
from src.bot.cmd_execution_mixin import ExecutionCommandsMixin
from src.bot.message_mixin import MessageHandlerMixin
from src.error_handler import get_error_handler

logger = logging.getLogger(__name__)


class MultiBot(
    APIMixin,
    BasicCommandsMixin,
    InvestCommandsMixin,
    AnalysisCommandsMixin,
    IBKRCommandsMixin,
    TradingCommandsMixin,
    CollabCommandsMixin,
    ExecutionCommandsMixin,
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
        self._base_system_prompt = profile.get(
            "system_prompt", f"你是 {self.name}，一个友好的AI助手。"
        )

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
        chat_router.register_bot(BotCapability(
            bot_id=self.bot_id,
            name=self.name,
            username=self.username,
            keywords=config.get("keywords", []),
            domains=profile.get("domains", []),
        ))

        # 注册到健康检查
        health_checker.register_bot(self.bot_id)

    @property
    def system_prompt(self) -> str:
        memory_context = shared_memory.get_context_for_prompt(max_tokens=500)
        return self._base_system_prompt + memory_context

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

    async def _should_respond_async(self, text: str, chat_type: str,
                                     message_id: Optional[int] = None,
                                     from_user_id: Optional[int] = None) -> Tuple[bool, str]:
        return await chat_router.should_respond_async(
            self.bot_id, text, chat_type, message_id, from_user_id
        )

    def _should_respond(self, text: str, chat_type: str,
                        message_id: Optional[int] = None,
                        from_user_id: Optional[int] = None) -> Tuple[bool, str]:
        return chat_router.should_respond(
            self.bot_id, text, chat_type, message_id, from_user_id
        )

    # ============ 启动 / 停止 ============

    async def run_async(self):
        if not self.config["token"]:
            logger.warning(f"[{self.name}] 未配置 Token，跳过")
            return None

        from telegram import Update, BotCommand
        from telegram.ext import (
            ApplicationBuilder, CommandHandler,
            MessageHandler, CallbackQueryHandler, filters,
        )

        self.app = (
            ApplicationBuilder()
            .token(self.config["token"])
            .connect_timeout(30)
            .read_timeout(30)
            .build()
        )

        # 全局错误处理器 — 接入 error_handler.py
        error_handler = get_error_handler()
        if error_handler:
            self.app.add_error_handler(error_handler.telegram_error_handler)

        # 注册命令
        self.app.add_handler(CommandHandler("start", self.cmd_start))
        self.app.add_handler(CommandHandler("clear", self.cmd_clear))
        self.app.add_handler(CommandHandler("status", self.cmd_status))
        self.app.add_handler(CommandHandler("draw", self.cmd_draw))
        self.app.add_handler(CommandHandler("news", self.cmd_news))
        self.app.add_handler(CommandHandler("help", self.cmd_start))
        self.app.add_handler(CommandHandler("metrics", self.cmd_metrics))
        self.app.add_handler(CommandHandler("lanes", self.cmd_lanes))
        self.app.add_handler(CommandHandler("collab", self.cmd_collab))
        self.app.add_handler(CommandHandler("context", self.cmd_context))
        self.app.add_handler(CommandHandler("compact", self.cmd_compact))
        self.app.add_handler(CommandHandler("discuss", self.cmd_discuss))
        self.app.add_handler(CommandHandler("stop_discuss", self.cmd_stop_discuss))
        self.app.add_handler(CommandHandler("quote", self.cmd_quote))
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
        self.app.add_handler(CommandHandler("xianyu", self.cmd_xianyu))
        self.app.add_handler(CommandHandler("social_calendar", self.cmd_social_calendar))
        self.app.add_handler(CommandHandler("social_report", self.cmd_social_report))
        self.app.add_handler(CommandHandler("model", self.cmd_model))
        self.app.add_handler(CommandHandler("pool", self.cmd_pool))
        self.app.add_handler(CommandHandler("memory", self.cmd_memory))
        self.app.add_handler(CommandHandler("settings", self.cmd_settings))
        self.app.add_handler(CallbackQueryHandler(
            self.handle_trade_callback, pattern=r"^itrade"))
        self.app.add_handler(CallbackQueryHandler(
            self.handle_help_callback, pattern=r"^help:"))
        self.app.add_handler(CallbackQueryHandler(
            self.handle_help_callback, pattern=r"^onboard:"))
        self.app.add_handler(CallbackQueryHandler(
            self.handle_feedback_callback, pattern=r"^fb\|"))
        self.app.add_handler(CallbackQueryHandler(
            self.handle_memory_callback, pattern=r"^mem_"))
        self.app.add_handler(CallbackQueryHandler(
            self.handle_settings_callback, pattern=r"^settings\|"))
        self.app.add_handler(CallbackQueryHandler(
            self.handle_notify_action_callback, pattern=r"^cmd:"))
        self.app.add_handler(CallbackQueryHandler(
            self.handle_social_confirm_callback, pattern=r"^social_confirm:"))
        self.app.add_handler(CallbackQueryHandler(
            lambda u, c: u.callback_query.answer(), pattern=r"^noop$"))

        self.app.add_handler(MessageHandler(
            filters.TEXT & ~filters.COMMAND, self.handle_message))
        self.app.add_handler(MessageHandler(
            filters.PHOTO, self.handle_photo))
        self.app.add_handler(MessageHandler(
            filters.VOICE | filters.AUDIO, self.handle_voice))
        self.app.add_handler(MessageHandler(
            filters.Document.PDF | filters.Document.IMAGE, self.handle_document_ocr))

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

        logger.info(
            f"[{self.name}] 启动成功 - {self.role} ({self.model.split('/')[-1]})"
        )
        return self

    async def stop_async(self):
        if self.app:
            try:
                await self.app.updater.stop()
                await self.app.stop()
                await self.app.shutdown()
            except Exception as e:
                logger.debug(f"[{self.name}] 停止时出错: {e}")
