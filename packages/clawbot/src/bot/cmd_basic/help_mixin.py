"""
帮助菜单 Mixin — /help, help 回调, 老用户 /start 欢迎

新用户引导向导在 onboarding_mixin.py 中实现 (ConversationHandler)。
本 Mixin 只处理:
  - 老用户 /start 欢迎（_show_returning_user_start）
  - /help 命令（cmd_help）
  - help:* 按钮回调（handle_help_callback）
"""

import logging

from src.bot.globals import history_store
from src.telegram_ux import with_typing

logger = logging.getLogger(__name__)


def _build_help_main_keyboard():
    """构建帮助主菜单键盘 (去重: /start 老用户 + help:back 共用)"""
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup

    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("🤖 AI 助手能力", callback_data="help:ai_assistant")],
            [
                InlineKeyboardButton("💬 日常对话", callback_data="help:daily"),
                InlineKeyboardButton("📱 社媒发文", callback_data="help:social"),
            ],
            [
                InlineKeyboardButton("📈 投资分析", callback_data="help:invest"),
                InlineKeyboardButton("🏦 IBKR实盘", callback_data="help:ibkr"),
            ],
            [
                InlineKeyboardButton("🏠 生活助手", callback_data="help:life"),
                InlineKeyboardButton("🛒 闲鱼运营", callback_data="help:xianyu"),
            ],
            [
                InlineKeyboardButton("⚙️ 高级功能", callback_data="help:advanced"),
                InlineKeyboardButton("🔧 系统工具", callback_data="help:system"),
            ],
            [InlineKeyboardButton("📋 全部命令", callback_data="help:all")],
        ]
    )


class _HelpMixin:
    """帮助菜单与老用户欢迎"""

    async def _show_returning_user_start(self, update, user):
        """老用户 /start — 智能记忆召回 + 帮助菜单

        由 OnboardingMixin.onboard_entry() 在检测到老用户时调用。
        """
        from src.smart_memory import get_smart_memory

        recent_task = ""
        try:
            sm = get_smart_memory()
            if sm:
                # 从记忆中召回用户最近关注的内容
                results = sm.memory.search(
                    query="用户正在做的事或者持仓或者关注的标的",
                    user_id=str(user.id),
                    limit=1,
                )
                if results:
                    recent_mem = results[0]["memory"]
                    recent_task = f"💡 我还记得：{recent_mem[:30]}...\n\n"
        except Exception as e:
            logger.debug("[Help] 记忆召回失败: %s", e)

        welcome = (
            f"{self.emoji}  {self.name} 已就绪\n"
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"{recent_task}"
            f"直接说中文就能操作，例如：\n"
            f'  · "帮我买100股苹果"\n'
            f'  · "特斯拉多少钱"\n'
            f'  · "帮我找便宜的AirPods"\n'
            f'  · "今日简报"\n\n'
            f"或者展开下方菜单查看更多 👇"
        )
        await update.message.reply_text(welcome, reply_markup=_build_help_main_keyboard())

    @with_typing
    async def cmd_help(self, update, context):
        """/help 命令 — 始终展示帮助菜单（不触发向导）"""
        if not self._is_authorized(update.effective_user.id):
            await update.message.reply_text("👋 你好！这是一个私有 Bot，暂未对你开放。\n如需使用请联系管理员获取授权。")
            return

        welcome = (
            f"{self.emoji}  {self.name}\n"
            f"───────────────────\n"
            f"{self.role} · {self.model.split('/')[-1]}\n\n"
            f"直接发消息就能对话，群聊 @我 即可。\n"
            f"下面按场景展开更多功能 👇"
        )
        await update.message.reply_text(welcome, reply_markup=_build_help_main_keyboard())

    async def handle_help_callback(self, update, context):
        """处理 help:* 按钮回调（帮助分类菜单）"""
        query = update.callback_query
        await query.answer()

        data = query.data
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
                '🧠 记住偏好 — 说一次"简短点"我就记住\n'
                "🔗 跨域联想 — 分析股票时关联社交热点\n"
                '✏️ 知错就改 — 说"不对"我自动纠正\n'
                "⏰ 任务跟踪 — 买完股票2h后告诉你涨跌\n"
                "👋 离线摘要 — 你回来时告诉你发生了什么\n"
                "🌡️ 语气感知 — 你急我就直给结论\n"
                '🔗 多步编排 — "分析然后发小红书"一步搞定\n'
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
                "/metrics  系统指标详情\n"
                "/draw <描述>  AI 生图\n"
                "/tts <文字>  文字转语音\n"
                "/news  科技早报\n"
                "/novel <描述>  AI 小说生成\n"
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
                "/xdraft  X 草稿预览\n"
                "/xpost  X 直接发布\n"
                "/xhsdraft  小红书草稿预览\n"
                "/xhspost  小红书直接发布\n"
                "/publish  发布草稿\n"
                "/social_plan  查看发文计划\n"
                "/social_persona  查看/切换人设\n"
                "/social_launch  数字生命首发包\n"
                "/social_repost  双平台改写\n"
                "/social_calendar  发文日历\n"
                "/social_report  社媒报告\n"
                "/topic <题材>  深度研究题材\n"
                "/xwatch  X 监控\n"
                "/xbrief  X 简报\n"
                "/xhs  小红书内容管理"
            ),
            "invest": (
                "📈 投资分析\n"
                "───────────────────\n"
                "/invest <话题>  6 位 AI 协作分析\n"
                "/quote <代码>  实时行情\n"
                "/market  市场概览\n"
                "/ta <代码>  技术分析\n"
                "/signal <代码>  交易信号\n"
                "/scan  全市场扫描\n"
                "/chart <代码>  K线走势图\n"
                "/calc <表达式>  金融计算器\n"
                "/portfolio  查看组合\n"
                "/buy /sell  模拟交易\n"
                "/risk  风控检查\n"
                "/monitor  持仓监控\n"
                "/watchlist  自选股管理\n"
                "/trades  交易历史\n"
                "/backtest <代码>  策略回测\n"
                "/autotrader  自动交易\n"
                "/rebalance  组合再平衡\n"
                "/tradingsystem  交易系统状态\n"
                "/performance  投资绩效\n"
                "/review  交易复盘\n"
                "/review_history  历史复盘\n"
                "/journal  交易日志\n"
                "/accuracy  AI预测准确率\n"
                "/equity  权益曲线\n"
                "/targets  盈利目标进度\n"
                "/drl  深度强化学习信号\n"
                "/factors  多因子分析\n"
                "/reset_portfolio  重置模拟组合"
            ),
            "ibkr": (
                "🏦 IBKR 实盘\n"
                "───────────────────\n"
                "/ibuy <代码> <数量>  实盘买入\n"
                "/isell <代码> <数量>  实盘卖出\n"
                "/icancel [订单号]  取消订单\n"
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
                "/stop_discuss  停止讨论\n"
                "/lanes  群聊分流标签\n"
                "/lane  分流标签管理\n"
                "/config  运行配置\n"
                "/evolution  进化引擎\n"
                "/intel  情报收集\n"
                "/keyhealth  API Key 健康检查"
            ),
            "xianyu": (
                "🛒 闲鱼运营\n"
                "───────────────────\n"
                "/xianyu  闲鱼AI客服 start/stop/status\n"
                "/xianyu_style  闲鱼客服话术风格\n"
                "/xianyu_report  闲鱼运营报表\n"
                "/ship <订单>  闲鱼发货\n"
                "/coupon  领券助手\n"
                "/set_coupon_token  设置领券 Token\n"
                "/test_token  测试 Token 有效性"
            ),
            "life": (
                "🏠 生活助手\n"
                "───────────────────\n"
                "⏰ 提醒\n"
                '  · "30分钟后提醒我开会"\n'
                '  · "每天早上9点提醒我吃药"\n'
                '  · "每周一提醒我交报告"\n\n'
                "💰 记账\n"
                '  · "花了35块买午饭"\n'
                '  · "收入5000块工资"\n'
                '  · "本月花了多少"\n'
                '  · "设置月预算8000"\n\n'
                "📱 话费水电\n"
                "  · /bill  查看话费余额追踪\n"
                "  · 低余额时自动提醒充值\n\n"
                "🛍️ 降价提醒\n"
                "  · /pricewatch  管理降价监控\n"
                '  · "帮我盯着 AirPods 降价"\n'
                "  · 6小时自动检查，降价即通知\n\n"
                "📰 智能简报\n"
                '  · "今日简报" → 每日综合日报\n'
                "  · /weekly → 本周战报"
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
                '  · "帮我买100股苹果"\n'
                '  · "特斯拉能买吗" → 技术分析\n'
                '  · "英伟达多少钱" → 实时报价\n'
                '  · "帮我炒股" → 6个AI开会分析\n'
                '  · "我的持仓" → 组合概览\n'
                '  · "复盘" → AI交易复盘\n\n'
                "🛒 购物比价\n"
                '  · "帮我找便宜的AirPods"\n'
                '  · "降噪耳机哪里买最便宜"\n\n'
                "📱 社媒运营\n"
                '  · "热点发文" → 自动写+发布\n'
                '  · "发AI趋势到小红书"\n'
                '  · "社媒计划" → 今日发文计划\n\n'
                "📋 日常效率\n"
                '  · "今日简报" → 智能日报\n'
                '  · "整理邮箱" → AI分类\n'
                '  · "30分钟后提醒我开会"\n'
                '  · "新闻" → 科技早报\n\n'
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

        back_btn = (
            InlineKeyboardMarkup([[InlineKeyboardButton("← 返回", callback_data="help:back")]])
            if section != "all"
            else None
        )

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
