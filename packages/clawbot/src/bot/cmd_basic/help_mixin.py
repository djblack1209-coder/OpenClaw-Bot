"""
帮助与引导 Mixin — /start, help 回调, onboarding 引导
"""
import logging

from src.bot.globals import (
    history_store, news_fetcher,
)
from src.bot.error_messages import error_service_failed
from src.telegram_ux import with_typing

logger = logging.getLogger(__name__)


def _build_help_main_keyboard():
    """构建帮助主菜单键盘 (去重: /start 老用户 + help:back 共用)"""
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🤖 AI 助手能力", callback_data="help:ai_assistant")],
        [InlineKeyboardButton("💬 日常对话", callback_data="help:daily"),
         InlineKeyboardButton("📱 社媒发文", callback_data="help:social")],
        [InlineKeyboardButton("📈 投资分析", callback_data="help:invest"),
         InlineKeyboardButton("🏦 IBKR实盘", callback_data="help:ibkr")],
        [InlineKeyboardButton("⚙️ 高级功能", callback_data="help:advanced"),
         InlineKeyboardButton("🔧 系统工具", callback_data="help:system")],
        [InlineKeyboardButton("🛒 闲鱼运营", callback_data="help:xianyu")],
        [InlineKeyboardButton("📋 全部命令", callback_data="help:all")],
    ])


class _HelpMixin:
    """帮助菜单与新用户引导"""

    @with_typing
    async def cmd_start(self, update, context):
        if not self._is_authorized(update.effective_user.id):
            await update.message.reply_text(
                "👋 你好！这是一个私有 Bot，暂未对你开放。\n"
                "如需使用请联系管理员获取授权。"
            )
            return

        from telegram import InlineKeyboardButton, InlineKeyboardMarkup

        user = update.effective_user
        chat_id = update.effective_chat.id

        # 首次使用检测 — 搬运自 father-bot/chatgpt_telegram_bot 的 register_user_if_not_exists
        is_first_time = not history_store.get_messages(self.bot_id, chat_id, limit=1)

        if is_first_time:
            # 首次用户：引导式 onboarding
            onboard = (
                f"👋 你好 {user.first_name}！我是 {self.name}\n"
                f"───────────────────\n"
                f"{self.role}\n\n"
                f"我能帮你做很多事，先试一个？\n"
                f"点下面的按钮，或者直接发消息给我聊天 👇"
            )
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("💬 直接聊天试试", callback_data="onboard:chat")],
                [InlineKeyboardButton("📰 看今日科技早报", callback_data="onboard:news"),
                 InlineKeyboardButton("🎨 AI 画一张图", callback_data="onboard:draw")],
                [InlineKeyboardButton("📈 分析一只股票", callback_data="onboard:invest"),
                 InlineKeyboardButton("📱 发一条社媒", callback_data="onboard:social")],
                [InlineKeyboardButton("📋 查看全部功能", callback_data="help:all")],
            ])
            await update.message.reply_text(onboard, reply_markup=keyboard)
        else:
            # 老用户：直接展示能力 + NL 示例
            welcome = (
                f"{self.emoji}  {self.name}\n"
                f"━━━━━━━━━━━━━━━━━━━\n"
                f"直接说中文就能操作：\n\n"
                f"  · \"帮我买100股苹果\"\n"
                f"  · \"特斯拉多少钱\"\n"
                f"  · \"帮我找便宜的AirPods\"\n"
                f"  · \"今日简报\"\n\n"
                f"或者展开下方菜单查看更多 👇"
            )
            await update.message.reply_text(welcome, reply_markup=_build_help_main_keyboard())

    async def handle_help_callback(self, update, context):
        """处理 /start 引导按钮和 onboarding 按钮的回调"""
        query = update.callback_query
        await query.answer()

        data = query.data

        # Onboarding 按钮处理
        if data.startswith("onboard:"):
            action = data.replace("onboard:", "")
            await self._handle_onboard_action(query, context, action)
            return

        section = data.replace("help:", "")

        HELP_SECTIONS = {
            "ai_assistant": (
                "🤖 AI 助手能力\n"
                "═══════════════════\n"
                "我不只是命令工具，我是你的 AI 助手。\n"
                "你可以直接说人话，不用记命令。\n\n"
                "💬 智能追问 — 每次回复后我会建议下一步\n"
                "💡 摘要先行 — 长回复我先说结论\n"
                "🎭 懂你风格 — 你喜欢简短我就简短\n"
                "📡 异动推送 — 自选股>3%波动主动通知\n"
                "🧠 记住偏好 — 说一次\"简短点\"我就记住\n"
                "🔗 跨域联想 — 分析股票时关联社交热点\n"
                "✏️ 知错就改 — 说\"不对\"我自动纠正\n"
                "⏰ 任务跟踪 — 买完股票2h后告诉你涨跌\n"
                "👋 离线摘要 — 你回来时告诉你发生了什么\n"
                "🌡️ 语气感知 — 你急我就直给结论\n"
                "🔗 多步编排 — \"分析然后发小红书\"一步搞定\n"
                "📊 行为洞察 — 发现你频繁查的标的\n"
                "📶 进度反馈 — 多步任务实时通知进度\n\n"
                "试试直接说：\n"
                "  • 帮我分析 TSLA\n"
                "  • 比价 AirPods Pro\n"
                "  • 分析TSLA然后发到小红书\n"
                "  • 简短点，以后回复别太长"
            ),
            "daily": (
                "💬 日常功能\n"
                "───────────────────\n"
                "直接发消息即可对话\n\n"
                "/clear  清空对话记录\n"
                "/status  查看 Bot 状态\n"
                "/draw <描述>  AI 生图\n"
                "/news  科技早报\n"
                "/context  查看上下文用量\n"
                "/compact  压缩上下文\n"
                "/weekly  综合周报\n"
                "/pricewatch  降价提醒\n"
                "/bill  话费水电费追踪"
            ),
            "social": (
                "📱 社媒一键发\n"
                "───────────────────\n"
                "/hot [题材]  抓热点 + 自动发文\n"
                "/hotpost  一键热点发文\n"
                "/post [题材]  双平台发文\n"
                "/post_x [题材]  发 X\n"
                "/post_xhs [题材]  发小红书\n"
                "/social_plan  查看发文计划\n"
                "/social_persona  查看人设\n"
                "/social_launch  数字生命首发包\n"
                "/social_repost  双平台改写\n"
                "/social_calendar  发文日历\n"
                "/social_report  社媒报告\n"
                "/topic <题材>  深度研究题材\n"
                "/xwatch  X 监控\n"
                "/xbrief  X 简报"
            ),
            "invest": (
                "📈 投资分析\n"
                "───────────────────\n"
                "/invest <话题>  5 位 AI 协作分析\n"
                "/quote <代码>  实时行情\n"
                "/market  市场概览\n"
                "/ta <代码>  技术分析\n"
                "/signal <代码>  交易信号\n"
                "/portfolio  查看组合\n"
                "/buy /sell  模拟交易\n"
                "/risk  风控检查\n"
                "/watchlist  自选股管理\n"
                "/trades  交易历史\n"
                "/backtest <代码>  策略回测\n"
                "/autotrader  自动交易\n"
                "/rebalance  组合再平衡\n"
                "/tradingsystem  交易系统状态\n"
                "/performance  投资绩效\n"
                "/review  交易复盘\n"
                "/journal  交易日志\n"
                "/accuracy  AI预测准确率\n"
                "/equity  权益曲线\n"
                "/targets  盈利目标进度"
            ),
            "ibkr": (
                "🏦 IBKR 实盘\n"
                "───────────────────\n"
                "/ibuy <代码> <数量>  实盘买入\n"
                "/isell <代码> <数量>  实盘卖出\n"
                "/ipositions  实盘持仓\n"
                "/iorders  实盘订单\n"
                "/iaccount  实盘账户"
            ),
            "advanced": (
                "⚙️ 高级功能\n"
                "───────────────────\n"
                "/agent <指令>  智能 Agent 多工具链\n"
                "/ops  自动化总入口\n"
                "/brief  执行简报\n"
                "/dev <任务>  开发流程\n"
                "/cost  成本配额\n"
                "/discuss <轮数> <主题>  多 Bot 讨论\n"
                "/lanes  群聊分流标签\n"
                "/config  运行配置"
            ),
            "xianyu": (
                "🛒 闲鱼运营\n"
                "───────────────────\n"
                "/xianyu  闲鱼AI客服 start/stop/status\n"
                "/xianyu_report  闲鱼运营报表"
            ),
            "system": (
                "🔧 系统工具\n"
                "───────────────────\n"
                "/memory  记忆管理\n"
                "/settings  偏好设置\n"
                "/voice  语音回复开关\n"
                "/export  导出数据\n"
                "/qr  生成二维码\n"
                "/model  切换模型\n"
                "/pool  API 池状态\n"
                "/collab  多 Bot 协作\n"
                "/discuss  多 Bot 讨论"
            ),
            "all": (
                f"{self.emoji} 我能帮你做什么\n"
                "━━━━━━━━━━━━━━━━━━━\n\n"
                "💡 不需要记命令，直接说中文：\n\n"
                "📈 投资交易\n"
                "  · \"帮我买100股苹果\"\n"
                "  · \"特斯拉能买吗\" → 技术分析\n"
                "  · \"英伟达多少钱\" → 实时报价\n"
                "  · \"帮我炒股\" → 6个AI开会分析\n"
                "  · \"我的持仓\" → 组合概览\n"
                "  · \"复盘\" → AI交易复盘\n\n"
                "🛒 购物比价\n"
                "  · \"帮我找便宜的AirPods\"\n"
                "  · \"降噪耳机哪里买最便宜\"\n\n"
                "📱 社媒运营\n"
                "  · \"热点发文\" → 自动写+发布\n"
                "  · \"发AI趋势到小红书\"\n"
                "  · \"社媒计划\" → 今日发文计划\n\n"
                "📋 日常效率\n"
                "  · \"今日简报\" → 智能日报\n"
                "  · \"整理邮箱\" → AI分类\n"
                "  · \"30分钟后提醒我开会\"\n"
                "  · \"新闻\" → 科技早报\n\n"
                "🤖 也支持命令 (高级)\n"
                "  /invest /quote /ta /buy /sell\n"
                "  /hot /post /social_plan\n"
                "  /ops /brief /agent\n\n"
                "━━━━━━━━━━━━━━━━━━━\n"
                "直接发消息开始对话 👆"
            ),
        }

        text = HELP_SECTIONS.get(section, "未知分类")

        from telegram import InlineKeyboardButton, InlineKeyboardMarkup
        back_btn = InlineKeyboardMarkup([
            [InlineKeyboardButton("← 返回", callback_data="help:back")]
        ]) if section != "all" else None

        if section == "back":
            # 返回主菜单
            welcome = (
                f"{self.emoji}  {self.name}\n"
                f"───────────────────\n"
                f"{self.role} · {self.model.split('/')[-1]}\n\n"
                f"直接发消息就能对话，群聊 @我 即可。\n"
                f"下面按场景展开更多功能 👇"
            )
            await query.edit_message_text(welcome, reply_markup=_build_help_main_keyboard())
            return

        await query.edit_message_text(text, reply_markup=back_btn)

    async def _handle_onboard_action(self, query, context, action):
        """处理 onboarding 引导按钮 — 引导用户完成第一个操作"""
        chat_id = query.message.chat_id

        if action == "chat":
            await query.edit_message_text(
                "💬 直接在这里打字就行！\n\n"
                "试试发一句：「帮我写一段自我介绍」\n"
                "或者问我任何问题，我会用流式输出实时回复你 ✨"
            )

        elif action == "news":
            await query.edit_message_text("📰 正在获取今日科技早报...")
            try:
                report = await news_fetcher.generate_morning_report()
                await context.bot.send_message(chat_id=chat_id, text=report)
            except Exception as e:
                logger.error("新闻获取失败: %s", e)
                await context.bot.send_message(chat_id=chat_id, text=error_service_failed("新闻获取"))

        elif action == "draw":
            await query.edit_message_text(
                "🎨 AI 画图\n\n"
                "发送 /draw 加上描述就行，比如：\n"
                "/draw 一只穿西装的龙虾在写代码\n\n"
                "支持 flux / sd3 / sdxl 模型"
            )

        elif action == "invest":
            await query.edit_message_text(
                "📈 投资分析\n\n"
                "发送 /quote AAPL 查看苹果实时行情\n"
                "发送 /invest 比特币 启动 5 位 AI 协作分析\n"
                "发送 /ta TSLA 查看特斯拉技术分析\n\n"
                "试试看？"
            )

        elif action == "social":
            await query.edit_message_text(
                "📱 社媒一键发\n\n"
                "发送 /hot 自动抓热点 + 发文\n"
                "发送 /post AI趋势 双平台发文\n"
                "发送 /social_persona 查看你的社媒人设\n\n"
                "需要先配置浏览器登录态才能发布"
            )
