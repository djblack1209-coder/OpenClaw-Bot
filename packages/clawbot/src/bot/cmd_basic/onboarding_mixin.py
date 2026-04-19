"""
新用户引导向导 — 3步 ConversationHandler 交互式引导

流程:
  /start → 检测首次用户 → 选兴趣 → 选风格 → 个性化欢迎 + 推荐命令
  老用户 /start → 直接展示帮助菜单（跳过向导）

状态机:
  entry_points: CommandHandler("start")
  ONBOARD_INTERESTS → 用户选择感兴趣的功能领域
  ONBOARD_STYLE     → 用户选择沟通风格偏好
  → ConversationHandler.END (展示个性化欢迎)
"""

import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ConversationHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from src.bot.globals import history_store

logger = logging.getLogger(__name__)

# ── 向导状态 ──────────────────────────────────────────
ONBOARD_INTERESTS, ONBOARD_STYLE = range(2)

# ── 兴趣选项 → 推荐命令 ──────────────────────────────
INTEREST_OPTIONS = {
    "invest": {
        "label": "📈 投资理财",
        "commands": [
            "· /quote AAPL — 查苹果实时行情",
            "· /invest 比特币 — 5位AI协作分析",
            "· /ta TSLA — 特斯拉技术分析",
            '· "帮我买100股苹果" — 直接说中文',
        ],
        "demo": "发送 /quote AAPL 查看苹果实时股价",
    },
    "social": {
        "label": "📱 社媒运营",
        "commands": [
            "· /hot — 抓热点自动写文章",
            "· /post AI趋势 — 双平台发文",
            "· /social_plan — 今日发文计划",
            '· "热点发文" — 直接说中文',
        ],
        "demo": "发送 /news 看今日科技早报",
    },
    "shopping": {
        "label": "🛒 购物比价",
        "commands": [
            '· "帮我找便宜的AirPods" — 直接说',
            "· /pricewatch — 管理降价监控",
            '· "降噪耳机哪里买最便宜"',
        ],
        "demo": '直接发消息说 "帮我找便宜的AirPods"',
    },
    "life": {
        "label": "🏠 生活助手",
        "commands": [
            '· "30分钟后提醒我开会" — 设提醒',
            '· "花了35块买午饭" — 记账',
            "· /bill — 话费余额追踪",
            '· "今日简报" — 每日综合日报',
        ],
        "demo": '直接发消息说 "今日简报"',
    },
    "all": {
        "label": "🗂️ 全部功能",
        "commands": [
            '· "帮我分析TSLA" — 投资分析',
            '· "热点发文" — 社媒一键发',
            '· "帮我找便宜的AirPods" — 购物比价',
            '· "30分钟后提醒我开会" — 生活助手',
            '· "今日简报" — 每日综合日报',
        ],
        "demo": '直接发消息说 "今日简报"',
    },
}

# ── 沟通风格选项 ──────────────────────────────────────
STYLE_OPTIONS = {
    "concise": {"label": "⚡ 简洁直接", "desc": "先说结论，不废话"},
    "detailed": {"label": "📝 详细专业", "desc": "有理有据，数据说话"},
    "casual": {"label": "😊 轻松聊天", "desc": "像朋友一样聊"},
}


# ── 兴趣 → 即时体验按钮映射 ────────────────────────
# 引导完成后，根据用户选择的兴趣方向给一个"立即试试"的操作按钮
_INSTANT_TRY_BUTTONS = {
    "invest": ("📊 查看市场概览", "cmd:market"),
    "life": ("📋 看今日简报", "cmd:brief"),
    "shopping": ("🛒 试试比价", "cmd:compare"),
    "social": ("📰 看科技早报", "cmd:news"),
    "all": ("📋 看今日简报", "cmd:brief"),
}


def _build_instant_try_button(interest: str) -> "InlineKeyboardButton | None":
    """根据用户选择的兴趣方向，返回即时体验按钮（无匹配时返回 None）"""
    btn_info = _INSTANT_TRY_BUTTONS.get(interest)
    if not btn_info:
        return None
    label, callback = btn_info
    return InlineKeyboardButton(label, callback_data=callback)


class _OnboardingMixin:
    """新用户 ConversationHandler 引导向导"""

    # ── Step 0: 入口 ──────────────────────────────────

    async def onboard_entry(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """ConversationHandler 入口 — /start 命令

        首次用户 → 启动向导 (返回 ONBOARD_INTERESTS)
        老用户   → 展示帮助菜单 (返回 END)
        """
        # 权限检查
        if not self._is_authorized(update.effective_user.id):
            await update.message.reply_text("👋 你好！这是一个私有 Bot，暂未对你开放。\n如需使用请联系管理员获取授权。")
            return ConversationHandler.END

        user = update.effective_user
        chat_id = update.effective_chat.id

        # 检测是否首次使用
        # 优先检查 shared_memory 中的 onboarded 标记（DB 重建后不会误判老用户）
        # 如果 shared_memory 不可用，降级到历史消息检查
        is_first_time = self._check_is_first_time(user.id, chat_id)

        if not is_first_time:
            # 老用户走正常 /start 路径（在 _HelpMixin 中定义）
            await self._show_returning_user_start(update, user)
            return ConversationHandler.END

        # ── 新用户：启动引导向导 Step 1 ──
        welcome = (
            f"👋 你好 {user.first_name}！我是 {self.name}\n"
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"{self.role}\n\n"
            f"先帮我了解一下，你最想用哪个功能？\n"
            f"（选一个入门，后面随时可以用其他功能）"
        )
        keyboard = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton("📈 投资理财", callback_data="ob_i:invest"),
                    InlineKeyboardButton("📱 社媒运营", callback_data="ob_i:social"),
                ],
                [
                    InlineKeyboardButton("🛒 购物比价", callback_data="ob_i:shopping"),
                    InlineKeyboardButton("🏠 生活助手", callback_data="ob_i:life"),
                ],
                [InlineKeyboardButton("🗂️ 都想试试", callback_data="ob_i:all")],
                [InlineKeyboardButton("⏩ 跳过引导", callback_data="ob_i:skip")],
            ]
        )
        await update.message.reply_text(welcome, reply_markup=keyboard)
        return ONBOARD_INTERESTS

    # ── Step 1: 选择兴趣领域 ──────────────────────────

    async def onboard_interests(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """用户选择了感兴趣的功能领域"""
        query = update.callback_query
        await query.answer()

        interest = query.data.replace("ob_i:", "")

        # 跳过引导
        if interest == "skip":
            await self._onboard_finish_skip(query)
            return ConversationHandler.END

        # 保存选择到 context（后续 Step 2 使用）
        context.user_data["onboard_interest"] = interest

        # 写入记忆（异步友好，失败不阻塞）
        self._save_onboard_preference(
            update.effective_user.id,
            update.effective_chat.id,
            key=f"user_interest_{update.effective_user.id}",
            value=f"用户最感兴趣的功能领域: {INTEREST_OPTIONS[interest]['label']}",
        )

        # ── 进入 Step 2: 选沟通风格 ──
        interest_label = INTEREST_OPTIONS[interest]["label"]
        style_text = f"好的！{interest_label} 👍\n\n再问一个：你希望我怎么跟你说话？"
        keyboard = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        f"{v['label']} — {v['desc']}",
                        callback_data=f"ob_s:{k}",
                    )
                ]
                for k, v in STYLE_OPTIONS.items()
            ]
        )
        await query.edit_message_text(style_text, reply_markup=keyboard)
        return ONBOARD_STYLE

    # ── Step 2: 选择沟通风格 → 完成 ─────────────────

    async def onboard_style(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """用户选择了沟通风格 → 展示个性化欢迎，结束向导"""
        query = update.callback_query
        await query.answer()

        style = query.data.replace("ob_s:", "")
        interest = context.user_data.get("onboard_interest", "all")

        # 写入风格偏好到记忆
        style_label = STYLE_OPTIONS.get(style, STYLE_OPTIONS["concise"])["label"]
        self._save_onboard_preference(
            update.effective_user.id,
            update.effective_chat.id,
            key=f"comm_style_{update.effective_user.id}",
            value=f"用户偏好的沟通风格: {style_label}",
        )

        # 标记用户已完成引导（防止 DB 重建后误判）
        self._mark_user_onboarded(
            update.effective_user.id,
            update.effective_chat.id,
        )

        # 构建个性化欢迎消息
        info = INTEREST_OPTIONS.get(interest, INTEREST_OPTIONS["all"])
        commands_text = "\n".join(info["commands"])

        complete_text = (
            f"✅ 设置完成！\n"
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"兴趣: {info['label']}  ·  风格: {style_label}\n\n"
            f"推荐你先试这些：\n"
            f"{commands_text}\n\n"
            f"💡 {info['demo']}\n\n"
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"不用记命令，直接说中文就行！\n"
            f"随时输入 /help 查看全部功能。"
        )

        # 根据用户选择的兴趣方向，生成"立即试试"按钮
        try_btn = _build_instant_try_button(interest)
        keyboard_rows = []
        if try_btn:
            keyboard_rows.append([try_btn])
        keyboard_rows.append([InlineKeyboardButton("📋 查看全部功能", callback_data="help:all")])
        keyboard = InlineKeyboardMarkup(keyboard_rows)
        await query.edit_message_text(complete_text, reply_markup=keyboard)

        logger.info(
            "[引导] 用户 %s 完成引导 — 兴趣: %s, 风格: %s",
            update.effective_user.id,
            interest,
            style,
        )
        return ConversationHandler.END

    # ── 辅助方法 ──────────────────────────────────────

    def _check_is_first_time(self, user_id: int, chat_id: int) -> bool:
        """检测用户是否首次使用

        优先查 shared_memory 的 onboarded 标记（持久化、不受 DB 重建影响）。
        shared_memory 不可用时，降级到历史消息为空判断。
        """
        try:
            from src.bot.globals import shared_memory

            result = shared_memory.recall(
                key=f"onboarded_{user_id}",
                category="user_preference",
            )
            if result.get("success"):
                # shared_memory 中有标记 → 老用户
                return False
        except Exception as e:
            logger.debug("shared_memory 查询 onboarded 标记失败，降级到历史消息判断: %s", e)

        # 降级方案：历史消息为空 = 新用户
        return not history_store.get_messages(self.bot_id, chat_id, limit=1)

    def _mark_user_onboarded(self, user_id: int, chat_id: int) -> None:
        """在 shared_memory 中标记用户已完成引导（失败不阻塞）"""
        try:
            from src.bot.globals import shared_memory

            shared_memory.remember(
                key=f"onboarded_{user_id}",
                value="true",
                category="user_preference",
                source_bot=self.bot_id,
                chat_id=chat_id,
                importance=5,
            )
        except Exception as e:
            logger.debug("写入 onboarded 标记失败: %s", e)

    async def onboard_cancel(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """用户发送 /cancel → 跳过向导"""
        from src.bot.cmd_basic.help_mixin import _build_help_main_keyboard

        await update.message.reply_text(
            f"{self.emoji}  引导已跳过\n\n直接发消息就能对话，或者展开下方菜单查看功能 👇",
            reply_markup=_build_help_main_keyboard(),
        )
        return ConversationHandler.END

    async def _onboard_finish_skip(self, query) -> None:
        """点击"跳过引导"按钮 → 展示帮助菜单"""
        from src.bot.cmd_basic.help_mixin import _build_help_main_keyboard

        await query.edit_message_text(
            f"{self.emoji}  引导已跳过\n\n直接发消息就能对话，或者展开下方菜单查看功能 👇",
            reply_markup=_build_help_main_keyboard(),
        )

    async def _onboard_text_fallback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """用户在向导中途发了文字消息 → 提示完成或跳过"""
        await update.message.reply_text("👆 先点上面的按钮完成设置（就剩一步了），\n或者输入 /cancel 跳过引导。")
        # 返回 None 保持当前状态不变
        return None

    def _save_onboard_preference(self, user_id: int, chat_id: int, key: str, value: str) -> None:
        """将引导偏好写入共享记忆（失败不阻塞）"""
        try:
            from src.bot.globals import shared_memory

            shared_memory.remember(
                key=key,
                value=value,
                category="user_preference",
                source_bot=self.bot_id,
                chat_id=chat_id,
                importance=5,
            )
        except Exception as e:
            logger.debug("引导偏好写入记忆失败: %s", e)

    def build_onboarding_handler(self) -> ConversationHandler:
        """构建引导向导的 ConversationHandler 实例

        必须在 multi_bot.py 中第一个注册，优先于其他 CommandHandler。
        """
        return ConversationHandler(
            entry_points=[CommandHandler("start", self.onboard_entry)],
            states={
                ONBOARD_INTERESTS: [
                    CallbackQueryHandler(self.onboard_interests, pattern=r"^ob_i:"),
                ],
                ONBOARD_STYLE: [
                    CallbackQueryHandler(self.onboard_style, pattern=r"^ob_s:"),
                ],
            },
            fallbacks=[
                CommandHandler("cancel", self.onboard_cancel),
                CommandHandler("help", self.onboard_cancel),
                # 用户在向导中途发文字 → 提示点按钮
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    self._onboard_text_fallback,
                ),
            ],
            per_user=True,
            per_chat=True,
            per_message=False,
            allow_reentry=True,
            name="onboarding_wizard",
        )
