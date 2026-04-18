"""
用户设置 Mixin — /settings 及其回调
"""
import logging

from src.telegram_ux import with_typing
from src.bot.auth import requires_auth

logger = logging.getLogger(__name__)


class _SettingsMixin:
    """用户个人偏好设置管理"""

    # ── /settings 命令 — 搬运自 father-bot 的 per-user settings 模式 ──

    @requires_auth
    @with_typing
    async def cmd_settings(self, update, context):
        """用户个人偏好设置管理"""
        try:
            return await self._cmd_settings_inner(update, context)
        except Exception as e:
            logger.exception("[Settings] 命令执行失败: %s", e)
            try:
                await update.message.reply_text("⚠️ 设置操作失败，请稍后重试")
            except Exception:
                pass

    async def _cmd_settings_inner(self, update, context):
        """设置管理 — 内部实现"""
        from src.bot.globals import user_prefs
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup
        from telegram.constants import ParseMode

        user_id = update.effective_user.id
        args = context.args or []

        # /settings key value — 直接设置
        if len(args) >= 2:
            key = args[0].lower()
            value = " ".join(args[1:])
            valid_keys = user_prefs.DEFAULTS.keys()
            if key not in valid_keys:
                await update.message.reply_text(
                    f"未知设置项: {key}\n可用: {', '.join(valid_keys)}")
                return
            # 类型转换
            if value.lower() in {"true", "on", "1", "yes"}:
                value = True
            elif value.lower() in {"false", "off", "0", "no"}:
                value = False
            user_prefs.set(user_id, key, value)
            await update.message.reply_text(f"✅ 已设置 {key} = {value}")
            return

        # /settings — 展示当前设置 + inline keyboard
        prefs = user_prefs.get_all(user_id)
        labels = {
            "notify_level": ("🔔 通知级别", {"silent": "静默", "normal": "正常", "verbose": "详细"}),
            "risk_tolerance": ("🛡 风险偏好", {"conservative": "保守", "moderate": "适中", "aggressive": "激进"}),
            "chat_mode": ("💬 对话模式", {"assistant": "助手", "trader": "交易员", "analyst": "分析师", "creative": "创意"}),
            "auto_trade_notify": ("📈 交易通知", {True: "开启", False: "关闭"}),
            "daily_report": ("📋 每日报告", {True: "开启", False: "关闭"}),
            "social_preview": ("📱 发文预览", {True: "开启", False: "关闭"}),
        }

        lines = ["⚙️ <b>个人设置</b>\n"]
        keyboard = []
        for key, (label, options) in labels.items():
            current = prefs.get(key, "?")
            display = options.get(current, str(current))
            lines.append(f"{label}: {display}")
            # 构建切换按钮 — 循环到下一个选项
            option_keys = list(options.keys())
            if current in option_keys:
                next_idx = (option_keys.index(current) + 1) % len(option_keys)
                next_val = option_keys[next_idx]
                next_display = options[next_val]
                keyboard.append([InlineKeyboardButton(
                    f"{label} → {next_display}",
                    callback_data=f"settings|{user_id}|{key}|{next_val}",
                )])

        lines.append("\n点击按钮切换，或用 /settings <key> <value> 直接设置")

        await update.message.reply_text(
            "\n".join(lines),
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(keyboard) if keyboard else None,
        )

    async def handle_settings_callback(self, update, context):
        """处理设置切换按钮的回调"""
        from src.bot.globals import user_prefs
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup
        from telegram.constants import ParseMode

        query = update.callback_query
        await query.answer()

        parts = query.data.split("|")
        if len(parts) < 4:
            return

        user_id = int(parts[1])
        # 安全校验：只允许用户修改自己的设置
        if query.from_user.id != user_id:
            await query.edit_message_text("⚠️ 无权修改他人设置")
            return
        key = parts[2]
        value = parts[3]

        # 类型转换
        if value == "True":
            value = True
        elif value == "False":
            value = False

        user_prefs.set(user_id, key, value)

        # 重新渲染设置面板
        prefs = user_prefs.get_all(user_id)
        labels = {
            "notify_level": ("🔔 通知级别", {"silent": "静默", "normal": "正常", "verbose": "详细"}),
            "risk_tolerance": ("🛡 风险偏好", {"conservative": "保守", "moderate": "适中", "aggressive": "激进"}),
            "chat_mode": ("💬 对话模式", {"assistant": "助手", "trader": "交易员", "analyst": "分析师", "creative": "创意"}),
            "auto_trade_notify": ("📈 交易通知", {True: "开启", False: "关闭"}),
            "daily_report": ("📋 每日报告", {True: "开启", False: "关闭"}),
            "social_preview": ("📱 发文预览", {True: "开启", False: "关闭"}),
        }

        lines = ["⚙️ <b>个人设置</b> ✅ 已更新\n"]
        keyboard = []
        for k, (label, options) in labels.items():
            current = prefs.get(k, "?")
            display = options.get(current, str(current))
            lines.append(f"{label}: {display}")
            option_keys = list(options.keys())
            if current in option_keys:
                next_idx = (option_keys.index(current) + 1) % len(option_keys)
                next_val = option_keys[next_idx]
                next_display = options[next_val]
                keyboard.append([InlineKeyboardButton(
                    f"{label} → {next_display}",
                    callback_data=f"settings|{user_id}|{k}|{next_val}",
                )])

        try:
            await query.edit_message_text(
                "\n".join(lines),
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup(keyboard),
            )
        except Exception as e:
            logger.debug("Silenced exception", exc_info=True)
