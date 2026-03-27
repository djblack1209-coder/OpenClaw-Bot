"""
基础命令 Mixin — 从 multi_main.py L792-L1032 提取
/start, /clear, /status, /draw, /news, /metrics, /context, /compact
"""
import asyncio
import logging
import os

from src.bot.globals import (
    history_store, context_manager, metrics, health_checker,
    news_fetcher, image_tool, get_siliconflow_key, get_total_balance,
    SILICONFLOW_KEYS, LOW_BALANCE_THRESHOLD,
    send_long_message, execution_hub,
)
from src.litellm_router import free_pool
from src.message_format import format_error
from src.bot.error_messages import error_generic, error_service_failed
from src.telegram_ux import with_typing, ProgressTracker
from src.bot.auth import requires_auth

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


class BasicCommandsMixin:
    """基础 Telegram 命令"""

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

    @requires_auth
    @with_typing
    async def cmd_lanes(self, update, context):
        """查看群聊显式分流标签"""
        await update.message.reply_text(
            "🏷  群聊分流标签\n"
            "───────────────────\n"
            "发消息时加标签，强制指定回复Bot：\n\n"
            " [RISK] #风控  → 💎 Sonnet（风险闸门）\n"
            " [ALPHA] #研究  → 🧠 Qwen（研究规划）\n"
            " [EXEC] #执行  → 🐉 DeepSeek（执行技术）\n"
            " [FAST] #快问  → ⚡ GPT-OSS（快速答复）\n"
            " [CN] #中文  → 🐉 DeepSeek（中文表达）\n"
            " [BRAIN] #终极  → 👑 Opus（深度推理）\n"
            " [CREATIVE] #创意  → 🚀 Haiku（文案创意）\n\n"
            "示例：[RISK] 今天持仓有没有超风险？\n"
            "提示：@bot 提及优先级高于标签"
        )

    @requires_auth
    async def cmd_clear(self, update, context):
        chat_id = update.effective_chat.id
        history_store.clear_messages(self.bot_id, chat_id)
        await update.message.reply_text(f"{self.emoji} 对话已清空")

    @requires_auth
    async def cmd_voice(self, update, context):
        """切换语音回复模式 — /voice 开启后短回复自动附带语音"""
        current = context.user_data.get("voice_reply", False)
        context.user_data["voice_reply"] = not current
        status = "开启" if not current else "关闭"
        await update.message.reply_text(f"语音回复已{status}")

    @requires_auth
    @with_typing
    async def cmd_status(self, update, context):
        from src.notify_style import format_status_card

        chat_id = update.effective_chat.id
        msg_count = history_store.get_message_count(self.bot_id, chat_id)
        total_balance = get_total_balance()
        stats = metrics.get_stats()
        health = health_checker.get_status()
        bot_health = health.get(self.bot_id, {})
        social_browser = await asyncio.to_thread(execution_hub.get_social_browser_status)
        social_persona = await asyncio.to_thread(execution_hub.get_social_persona_summary)

        balance_warning = ""
        if total_balance < LOW_BALANCE_THRESHOLD * len(SILICONFLOW_KEYS):
            balance_warning = "余额不足，请及时充值"

        x_state_raw = social_browser.get("x_ready")
        xhs_state_raw = social_browser.get("xiaohongshu_ready")
        x_state = "✅" if x_state_raw is True else ("🔑" if x_state_raw is False else "⏳")
        xhs_state = "✅" if xhs_state_raw is True else ("🔑" if xhs_state_raw is False else "⏳")

        # Gateway 连通性检测（超时延长到10秒，避免网络抖动误报）
        try:
            import httpx
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(f"http://localhost:{os.environ.get('GATEWAY_PORT', '18789')}/health")
                gateway_status = "在线" if resp.status_code == 200 else "异常"
        except Exception:
            gateway_status = "离线"

        # 免费 API 池状态
        pool_stats = free_pool.get_stats()
        pool_info = f"{pool_stats['active_sources']}/{pool_stats['total_sources']}源"

        api_type_label = {
            "free_pool": "LiteLLM Router",
            "free_first": "免费优先",
            "g4f": "g4f",
        }.get(getattr(self, "api_type", ""), "其他")

        text = format_status_card(
            name=self.name,
            emoji=self.emoji,
            role=self.role,
            model=self.model,
            api_type=api_type_label,
            msg_count=msg_count,
            pool_info=pool_info,
            healthy=bot_health.get('healthy', True),
            uptime_hours=stats['uptime_hours'],
            today_messages=stats['today_messages'],
            gateway_status=gateway_status,
            browser_running=social_browser.get("browser_running", False),
            x_state=x_state,
            xhs_state=xhs_state,
            persona_name=social_persona.get('name', '未配置'),
            balance_warning=balance_warning,
        )

        await update.message.reply_text(text)

    @requires_auth
    @with_typing
    async def cmd_draw(self, update, context):
        args = context.args
        if not args:
            await update.message.reply_text(
                "用法: `/draw 图片描述`\n可选: `/draw 描述 --model flux/sd3/sdxl`",
                parse_mode="Markdown"
            )
            return

        prompt_parts = []
        model = "flux"
        i = 0
        while i < len(args):
            if args[i] == "--model" and i + 1 < len(args):
                model = args[i + 1]
                i += 2
            else:
                prompt_parts.append(args[i])
                i += 1

        prompt = " ".join(prompt_parts)

        async with ProgressTracker(update.effective_chat.id, context, title=f"生成: {prompt[:30]}") as progress:
            await progress.update("准备 API Key")
            api_key = get_siliconflow_key()
            if not api_key:
                await update.message.reply_text("没有可用的 API Key")
                return

            await progress.update(f"调用 {model} 模型")
            image_tool.set_api_key(api_key)
            result = await image_tool.generate(prompt, model)

        if result["success"]:
            for path in result["paths"]:
                with open(path, "rb") as f:
                    await context.bot.send_photo(
                        chat_id=update.effective_chat.id,
                        photo=f,
                        caption=f"描述: {prompt[:100]}"
                    )
        else:
            await update.message.reply_text(f"生成失败: {result.get('error')}")

    @requires_auth
    @with_typing
    async def cmd_news(self, update, context):
        try:
            report = await news_fetcher.generate_morning_report()
            await update.message.reply_text(report)
        except Exception as e:
            await update.message.reply_text(format_error(e, "获取新闻"))

    @requires_auth
    @with_typing
    async def cmd_qr(self, update, context):
        """生成二维码: /qr [文本或URL]"""
        from src.tools.qr_service import HAS_QRCODE

        if not HAS_QRCODE:
            await update.message.reply_text(
                "二维码功能需要安装依赖:\n`pip install 'qrcode[pil]'`",
                parse_mode="Markdown",
            )
            return

        # 确定要编码的内容
        if context.args:
            text = " ".join(context.args)
        else:
            # 默认生成 Bot 邀请二维码
            bot_user = await context.bot.get_me()
            text = f"https://t.me/{bot_user.username}"

        try:
            from src.tools.qr_service import generate_qr
            buf = generate_qr(text)

            # 截断显示文本
            display = text if len(text) <= 60 else text[:57] + "..."
            await context.bot.send_photo(
                chat_id=update.effective_chat.id,
                photo=buf,
                caption=f"二维码: {display}",
                reply_to_message_id=update.message.message_id,
            )
        except Exception as e:
            logger.error("二维码生成失败: %s", e, exc_info=True)
            await update.message.reply_text(error_generic(str(e)))

    @requires_auth
    @with_typing
    async def cmd_metrics(self, update, context):
        """运行指标命令"""
        stats = metrics.get_stats()
        health = health_checker.get_status()
        db_stats = history_store.get_stats()

        lines = [
            "📊  运行指标",
            "───────────────────",
            f" · 运行  {stats['uptime_hours']}h",
            f" · 总消息  {stats['total_messages']} | 今日  {stats['today_messages']}",
            f" · API调用  {stats['total_api_calls']} | 错误率  {stats['error_rate']}%",
            f" · 平均延迟  {stats['avg_latency_ms']}ms",
            "",
            "▸ 存储",
            f"  数据库 {db_stats['db_size_kb']}KB | {db_stats['total_messages']}条 | {db_stats['total_chats']}个对话",
        ]

        model_usage = stats.get('model_usage', {})
        if model_usage:
            lines.extend(["", "▸ 模型使用"])
            for model, count in model_usage.items():
                lines.append(f"  {model.split('/')[-1]}: {count}")

        lines.extend(["", "▸ 健康"])
        for bot_id, status in health.items():
            icon = "💚" if status['healthy'] else "🔴"
            lines.append(f"  {icon} {bot_id}: 连续错误 {status['consecutive_errors']}")

        await send_long_message(update.effective_chat.id, "\n".join(lines), context)

    @requires_auth
    @with_typing
    async def cmd_model(self, update, context):
        """查看当前模型信息"""
        pool_stats = free_pool.get_stats()
        api_type_label = {
            "free_pool": "LiteLLM 动态路由",
            "free_first": "免费优先（私聊可降级付费）",
            "g4f": "g4f 本地",
            "kiro": "Kiro Gateway",
            "siliconflow": "硅基流动",
        }.get(getattr(self, "api_type", ""), "未知")

        text = (
            f"{self.emoji} **{self.name} 模型信息**\n\n"
            f"配置模型: `{self.model}`\n"
            f"路由方式: {api_type_label}\n"
            f"活跃模型数: {pool_stats['active_sources']}/{pool_stats['total_sources']}\n"
            f"模型族数: {pool_stats['model_families']}\n"
        )
        await update.message.reply_text(text, parse_mode="Markdown")

    @requires_auth
    @with_typing
    async def cmd_pool(self, update, context):
        """查看免费 API 池 + 智能路由状态"""
        pool_stats = free_pool.get_stats()
        text = f"🆓 **免费 API 池状态**\n\n"
        text += f"总源数: {pool_stats['total_sources']}\n"
        text += f"活跃源: {pool_stats['active_sources']}\n"
        text += f"模型族: {pool_stats['model_families']}\n\n"

        for family, info in pool_stats.get("families", {}).items():
            icon = "✅" if info["active"] > 0 else "❌"
            text += f"{icon} {family}: {info['active']}/{info['total']} 活跃\n"

        # AdaptiveRouter 智能路由状态
        from src.litellm_router import adaptive_router
        if adaptive_router:
            text += f"\n{adaptive_router.format_routing_status()}"

        await send_long_message(update.effective_chat.id, text, context)

    @requires_auth
    @with_typing
    async def cmd_context(self, update, context):
        """查看当前上下文状态"""
        chat_id = update.effective_chat.id
        messages = history_store.get_messages(self.bot_id, chat_id, limit=100)
        status = context_manager.get_context_status(messages)

        pct = status["usage_percent"]
        bar_len = 20
        filled = int(bar_len * pct / 100)
        bar = "█" * filled + "░" * (bar_len - filled)

        warning = ""
        if status["must_compress"]:
            warning = "\n⚠️ 上下文即将溢出，建议 /compact 或 /clear"
        elif status["needs_compression"]:
            warning = "\n💡 上下文较大，下次对话将自动压缩"

        await update.message.reply_text(
            f"{self.emoji} **上下文状态**\n\n"
            f"消息数: {status['message_count']}\n"
            f"Token: {status['estimated_tokens']:,} / {status['max_tokens']:,}\n"
            f"使用率: [{bar}] {pct}%\n"
            f"压缩阈值: {status['compress_threshold']:,}\n"
            f"已有摘要: {'是' if status['has_summary'] else '否'}\n"
            f"关键信息: {status['key_facts_count']} 条{warning}",
            parse_mode="Markdown"
        )

    @requires_auth
    @with_typing
    async def cmd_compact(self, update, context):
        """手动压缩上下文"""
        chat_id = update.effective_chat.id
        messages = history_store.get_messages(self.bot_id, chat_id, limit=100)

        if len(messages) < 6:
            await update.message.reply_text(f"{self.emoji} 对话太短，无需压缩")
            return

        before_tokens = context_manager.estimate_tokens(messages)
        compressed, summary = context_manager.compress_local(messages)
        after_tokens = context_manager.estimate_tokens(compressed)

        context_manager.update_history_store(
            history_store, self.bot_id, chat_id, compressed
        )

        saved_pct = round((1 - after_tokens / before_tokens) * 100) if before_tokens > 0 else 0

        await update.message.reply_text(
            f"{self.emoji} **上下文已压缩**\n\n"
            f"消息: {len(messages)} -> {len(compressed)}\n"
            f"Token: {before_tokens:,} -> {after_tokens:,}\n"
            f"节省: {saved_pct}%\n\n"
            f"关键信息和最近对话已保留。",
            parse_mode="Markdown"
        )

    # ── /settings 命令 — 搬运自 father-bot 的 per-user settings 模式 ──

    @requires_auth
    @with_typing
    async def cmd_settings(self, update, context):
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
        except Exception:
            logger.debug("Silenced exception", exc_info=True)

    # ── /memory 命令 — 搬运自 mem0 的用户记忆管理 + karfly 的分页模式 ──

    MEMORIES_PER_PAGE = 5

    @requires_auth
    @with_typing
    async def cmd_memory(self, update, context):
        """查看/管理 Bot 记住的关于你的信息"""
        from src.smart_memory import get_smart_memory
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup
        from telegram.constants import ParseMode

        user_id = update.effective_user.id
        sm = get_smart_memory()
        if not sm:
            await update.message.reply_text("记忆系统未启用")
            return

        # 获取用户相关记忆
        search_result = sm.memory.search(f"auto_{user_id}", limit=50)
        results = search_result.get("results", []) if isinstance(search_result, dict) else []

        # 也获取用户画像
        profile = sm.get_user_profile(user_id)

        if not results and not profile:
            await update.message.reply_text(
                "📭 还没有记住关于你的任何信息。\n"
                "和我聊天后，我会自动记住重要的事情。"
            )
            return

        text = "🧠 <b>我记住的关于你的信息</b>\n\n"

        if profile:
            text += "<b>用户画像:</b>\n"
            if profile.get("summary"):
                text += f"  {profile['summary']}\n"
            if profile.get("interests"):
                text += f"  兴趣: {', '.join(profile['interests'][:5])}\n"
            text += "\n"

        if results:
            text += f"<b>记忆 ({len(results)} 条):</b>\n\n"
            for i, mem in enumerate(results[:self.MEMORIES_PER_PAGE], 1):
                val = mem.get("value", "")[:100]
                text += f"{i}. {val}\n\n"

        keyboard = []
        if len(results) > self.MEMORIES_PER_PAGE:
            keyboard.append([InlineKeyboardButton("下一页 »", callback_data=f"mem_page|{user_id}|1")])
        keyboard.append([
            InlineKeyboardButton("🗑 清除所有记忆", callback_data=f"mem_clear|{user_id}"),
        ])

        await update.message.reply_text(
            text,
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(keyboard) if keyboard else None,
        )

    async def handle_feedback_callback(self, update, context):
        """处理 👍/👎/🔄 反馈按钮 — 搬运自 karfly 的 callback 模式"""
        from src.feedback import parse_feedback_data, get_feedback_store
        from src.litellm_router import adaptive_router
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup

        query = update.callback_query
        await query.answer()  # 立即响应，消除加载动画（karfly 关键模式）

        data = parse_feedback_data(query.data)
        if not data:
            return

        user_id = query.from_user.id
        action = data["action"]
        model = data["model"]
        bot_id = data["bot_id"]

        if action == "retry":
            # 移除按钮，提示重新生成
            await query.edit_message_reply_markup(reply_markup=None)
            await query.message.reply_text("🔄 请重新发送你的问题")
            return

        # 记录反馈
        rating = 1 if action == "up" else -1
        store = get_feedback_store()
        store.record(user_id, data["chat_id"], bot_id, model, rating)

        # 联动 AdaptiveRouter 质量评分（闭环）
        if adaptive_router:
            quality = 0.8 if rating > 0 else 0.2
            adaptive_router.record_result(model, "general", success=True, quality=quality)

        # 替换按钮为确认（karfly 模式）
        emoji = "👍" if action == "up" else "👎"
        await query.edit_message_reply_markup(
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton(f"{emoji} 已收到反馈", callback_data="noop")
            ]])
        )

    async def handle_memory_callback(self, update, context):
        """处理记忆管理的分页/删除回调"""
        from src.smart_memory import get_smart_memory
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup
        from telegram.constants import ParseMode

        query = update.callback_query
        await query.answer()

        parts = query.data.split("|")
        action = parts[0]

        if action == "mem_clear":
            user_id = int(parts[1])
            sm = get_smart_memory()
            if sm:
                # 删除该用户的所有自动记忆
                search_result = sm.memory.search(f"auto_{user_id}", limit=100)
                results = search_result.get("results", []) if isinstance(search_result, dict) else []
                for mem in results:
                    key = mem.get("key", "")
                    if key:
                        sm.memory.forget(key)
                # 也删除画像
                sm.memory.forget(f"user_profile_{user_id}")
            await query.edit_message_text("✅ 所有记忆已清除。")

        elif action == "mem_page":
            user_id = int(parts[1])
            page = int(parts[2])
            sm = get_smart_memory()
            if not sm:
                return

            search_result = sm.memory.search(f"auto_{user_id}", limit=50)
            results = search_result.get("results", []) if isinstance(search_result, dict) else []

            start = page * self.MEMORIES_PER_PAGE
            end = min(start + self.MEMORIES_PER_PAGE, len(results))
            page_items = results[start:end]

            text = f"🧠 <b>记忆 ({len(results)} 条) - 第 {page + 1} 页</b>\n\n"
            for i, mem in enumerate(page_items, start=start + 1):
                val = mem.get("value", "")[:100]
                text += f"{i}. {val}\n\n"

            nav = []
            if page > 0:
                nav.append(InlineKeyboardButton("« 上一页", callback_data=f"mem_page|{user_id}|{page - 1}"))
            if end < len(results):
                nav.append(InlineKeyboardButton("下一页 »", callback_data=f"mem_page|{user_id}|{page + 1}"))
            keyboard = [nav] if nav else []
            keyboard.append([InlineKeyboardButton("🗑 清除所有", callback_data=f"mem_clear|{user_id}")])

            try:
                await query.edit_message_text(
                    text, parse_mode=ParseMode.HTML,
                    reply_markup=InlineKeyboardMarkup(keyboard),
                )
            except Exception:
                logger.debug("Silenced exception", exc_info=True)

    async def handle_notify_action_callback(self, update, context):
        """处理交易通知中的 actionable 按钮 — 搬运 freqtrade 的 inline command 模式
        
        callback_data 格式: cmd:/command [args]
        点击按钮等同于执行对应命令，结果直接回复在通知下方。
        """
        query = update.callback_query
        await query.answer()

        # 认证: 仅授权用户可操作
        if not self._is_authorized(update.effective_user.id):
            await query.answer("⛔ 未授权操作", show_alert=True)
            return

        data = query.data
        if not data.startswith("cmd:"):
            return

        cmd_str = data[4:].strip()  # 去掉 "cmd:" 前缀
        if not cmd_str.startswith("/"):
            cmd_str = "/" + cmd_str  # Normalize: add / prefix if missing

        # 解析命令和参数
        parts = cmd_str.split()
        cmd_name = parts[0][1:]  # 去掉 "/"
        cmd_args = parts[1:]

        # 映射到对应的命令处理函数
        cmd_map = {
            "monitor": self.cmd_monitor,
            "risk": self.cmd_risk,
            "tradingsystem": self.cmd_tradingsystem,
            "brief": self.cmd_brief,
            "status": self.cmd_status,
            "autotrader": self.cmd_autotrader,
            "portfolio": self.cmd_portfolio,
            "cost": self.cmd_cost,
            "help": self.cmd_start,
            "quote": self.cmd_quote,
            "market": self.cmd_market,
            "backtest": self.cmd_backtest,
            "ta": self.cmd_ta,
            # v3.0: 扩展 cmd_map 支持智能行动建议按钮
            "sell": self.cmd_sell,
            "buy": self.cmd_buy,
            "performance": self.cmd_performance,
            "hotpost": self.cmd_hotpost,
            "social_plan": self.cmd_social_plan,
            "signal": self.cmd_signal,
            "journal": self.cmd_journal,
            "review": self.cmd_review,
            "invest": self.cmd_invest,
            "evolve": self.cmd_status,
            "tasks": self.cmd_ops,
            "bill": self.cmd_bill,
            "xianyu": self.cmd_xianyu,
        }

        handler = cmd_map.get(cmd_name)
        if not handler:
            await query.message.reply_text(f"未知命令: /{cmd_name}")
            return

        # 构造 context.args 并执行命令
        context.args = cmd_args
        try:
            await handler(update, context)
        except Exception as e:
            await query.message.reply_text(format_error(e, f"执行 /{cmd_name}"))

    # ── Inline Query — @bot 搜股票/记忆 ──
    # 搬运自 yym68686/ChatGPT-Telegram-Bot + freqtrade 的 inline 模式

    async def handle_inline_query(self, update, context):
        """处理 @bot <query> 内联搜索 — 在任何聊天中即时查股票/记忆"""
        from telegram import InlineQueryResultArticle, InputTextMessageContent

        query = update.inline_query
        text = (query.query or "").strip()
        if not text or len(text) < 1:
            return

        results = []
        text_upper = text.upper()

        # 1. 股票快速查询
        try:
            from src.invest_tools import get_stock_quote, get_crypto_quote
            from src.telegram_ux import format_quote_card

            # 判断是否像股票代码（1-5个字母）
            if text_upper.isalpha() and len(text_upper) <= 5:
                quote = await get_stock_quote(text_upper)
                if quote and isinstance(quote, dict) and "price" in quote:
                    card = format_quote_card(quote)
                    results.append(InlineQueryResultArticle(
                        id=f"stock_{text_upper}",
                        title=f"📈 {text_upper} — ${quote.get('price', 0):.2f}",
                        description=f"{quote.get('change_pct', 0):+.2f}% | Vol {quote.get('volume', 0):,.0f}",
                        input_message_content=InputTextMessageContent(
                            card, parse_mode="HTML",
                        ),
                    ))

                # 也试加密货币
                crypto_quote = await get_crypto_quote(text_upper)
                if crypto_quote and isinstance(crypto_quote, dict) and "price" in crypto_quote:
                    card = format_quote_card(crypto_quote)
                    results.append(InlineQueryResultArticle(
                        id=f"crypto_{text_upper}",
                        title=f"🪙 {text_upper} — ${crypto_quote.get('price', 0):.2f}",
                        description=f"{crypto_quote.get('change_pct', 0):+.2f}%",
                        input_message_content=InputTextMessageContent(
                            card, parse_mode="HTML",
                        ),
                    ))
        except Exception:
            logger.debug("Silenced exception", exc_info=True)

        # 2. 记忆搜索
        try:
            from src.smart_memory import get_smart_memory
            sm = get_smart_memory()
            if sm and len(text) >= 2:
                search_result = sm.memory.search(text, limit=5)
                memories = search_result.get("results", []) if isinstance(search_result, dict) else []
                for i, mem in enumerate(memories[:3]):
                    val = mem.get("value", "")[:200]
                    if val:
                        results.append(InlineQueryResultArticle(
                            id=f"mem_{i}",
                            title=f"🧠 记忆: {val[:50]}",
                            description=val[:100],
                            input_message_content=InputTextMessageContent(
                                f"🧠 {val}",
                            ),
                        ))
        except Exception:
            logger.debug("Silenced exception", exc_info=True)

        # 3. 命令快捷入口
        cmd_hints = {
            "回测": ("/backtest", "📊 回测策略"),
            "持仓": ("/monitor", "📊 查看持仓"),
            "风控": ("/risk", "🛡 风控状态"),
            "新闻": ("/news", "📰 科技早报"),
            "记忆": ("/memory", "🧠 查看记忆"),
            "发文": ("/hot", "🔥 热点发文"),
        }
        for keyword, (cmd, desc) in cmd_hints.items():
            if keyword in text or text in keyword:
                results.append(InlineQueryResultArticle(
                    id=f"cmd_{cmd}",
                    title=desc,
                    description=f"发送 {cmd} 命令",
                    input_message_content=InputTextMessageContent(cmd),
                ))

        try:
            await query.answer(results[:10], cache_time=30)
        except Exception:
            logger.debug("Silenced exception", exc_info=True)

    # ── /tts 命令 — 文字转语音 (edge-tts 10K⭐) ──

    @requires_auth
    @with_typing
    async def cmd_tts(self, update, context):
        """文字转语音 — /tts <文本> [音色]"""
        args = context.args or []
        if not args:
            from src.tools.tts_tool import format_voice_list, CHINESE_VOICES
            help_text = "🎤 文字转语音\n\n用法: /tts <文本> [音色]\n\n"
            help_text += format_voice_list()
            help_text += "\n\n示例:\n  /tts 今天天气真好\n  /tts 你好世界 云希"
            await update.message.reply_text(help_text)
            return

        # 检查最后一个参数是否是音色名
        from src.tools.tts_tool import text_to_speech, CHINESE_VOICES
        voice = None
        text_parts = list(args)
        if text_parts[-1] in CHINESE_VOICES:
            voice = text_parts.pop()
        text = " ".join(text_parts)

        if not text.strip():
            await update.message.reply_text("❓ 请输入要转换的文本")
            return

        await update.message.reply_text("🎤 正在生成语音...")
        audio_path = await text_to_speech(text, voice=voice or "zh-CN-XiaoxiaoNeural")

        if audio_path:
            from pathlib import Path
            try:
                with open(audio_path, "rb") as f:
                    await update.message.reply_voice(voice=f)
                # 清理临时文件
                Path(audio_path).unlink(missing_ok=True)
            except Exception as e:
                logger.error("[TTS] 发送音频失败: %s", e)
                await update.message.reply_text("⚠️ 音频生成成功但发送失败")
        else:
            await update.message.reply_text("⚠️ 语音生成失败，请稍后重试")

    # ── /agent 命令 — 搬运 smolagents (26.2k⭐) 自主 Agent ──

    @requires_auth
    @with_typing
    async def cmd_agent(self, update, context):
        """智能 Agent — 自然语言驱动多工具链"""
        query = " ".join(context.args) if context.args else ""
        if not query:
            await update.message.reply_text(
                "🤖 <b>智能 Agent</b>\n\n"
                "用自然语言描述你想做的事，Agent 会自动调用工具链完成。\n\n"
                "示例:\n"
                "• /agent 分析AAPL的技术面并给出买卖建议\n"
                "• /agent 搜索最新BTC新闻并分析情绪\n"
                "• /agent 检查持仓，对亏损超5%的标的建议止损\n"
                "• /agent 对比NVDA和AMD的技术指标\n"
                "• /agent 查看全球市场概览并分析风险\n\n"
                "Agent 可用工具: 行情查询、技术分析、新闻搜索、"
                "投资组合、市场概览、风控状态、情绪分析",
                parse_mode="HTML",
            )
            return

        msg = await update.message.reply_text("🤖 Agent 正在思考并执行...")

        try:
            from src.agent_tools import run_agent, HAS_SMOLAGENTS

            if not HAS_SMOLAGENTS:
                await msg.edit_text(
                    "⚠️ smolagents 未安装，Agent 功能不可用。\n"
                    "运行 <code>pip install 'smolagents&gt;=1.0.0'</code> 后重启。",
                    parse_mode="HTML",
                )
                return

            result = await run_agent(query)

            # Convert markdown to Telegram-safe HTML
            try:
                from src.telegram_markdown import md_to_html
                safe = md_to_html(result)
            except Exception:
                import html as _html
                safe = _html.escape(result)

            await send_long_message(
                update.effective_chat.id, safe, context, parse_mode="HTML"
            )
            # Delete the "thinking" message
            try:
                await msg.delete()
            except Exception:
                logger.debug("Silenced exception", exc_info=True)

        except Exception as e:
            await msg.edit_text(format_error(e, "Agent 执行"))

    async def handle_card_action_callback(self, update, context):
        """处理 OMEGA 响应卡片上的操作按钮（response_cards.py 生成的 callback_data）"""
        query = update.callback_query
        await query.answer()
        data = query.data

        if data.startswith("trade:buy:"):
            symbol = data.split(":")[-1]
            await query.message.reply_text(f"💡 请使用: /buy {symbol} 数量")
        elif data.startswith("trade:size:"):
            symbol = data.split(":")[-1]
            await query.message.reply_text(
                f"💡 调整仓位: /buy {symbol} 数量\n"
                f"例如: /buy {symbol} 100"
            )
        elif data.startswith("bt:"):
            parts = data.split(":")
            symbol = parts[-1] if len(parts) > 2 else ""
            context.args = [symbol] if symbol else []
            await self.cmd_backtest(update, context)
        elif data.startswith("ta:detail:"):
            symbol = data.split(":")[-1]
            context.args = [symbol]
            await self.cmd_ta(update, context)
        elif data.startswith("analyze:"):
            symbol = data.split(":")[-1]
            context.args = [symbol]
            await self.cmd_ta(update, context)
        elif data.startswith("news:"):
            symbol = data.split(":")[-1]
            context.args = [symbol]
            await self.cmd_news(update, context)
        elif data.startswith("evo:approve:") or data.startswith("evo:reject:"):
            action = "approve" if "approve" in data else "reject"
            pid = data.split(":")[-1]
            await query.message.reply_text(f"📋 进化提案 {pid} 已标记为 {action}")
        elif data.startswith("retry:"):
            await query.message.reply_text("🔄 请重试您之前的操作")
        elif data.startswith("shop:refresh:"):
            product = data.split(":", 2)[-1]
            await query.message.reply_text(f"🔄 正在刷新 {product} 的价格...")
        elif data.startswith("post:"):
            topic = data.split(":", 1)[-1]
            context.args = [topic]
            await self.cmd_post(update, context)
        else:
            await query.message.reply_text("💡 此操作暂不支持")

    async def handle_clarification_callback(self, update, context):
        """处理 ClarificationCard 追问按钮的回调 (callback_data: {tid}:{param}:{value})"""
        query = update.callback_query
        await query.answer()
        data = query.data or ""

        parts = data.split(":", 2)
        if len(parts) < 3:
            await query.message.reply_text("⚠️ 按钮数据格式异常，请重新提问。")
            return

        tid, param, value = parts[0], parts[1], parts[2]

        # 取消操作
        if param == "cancel":
            await query.edit_message_reply_markup(reply_markup=None)
            await query.message.reply_text("❌ 已取消。")
            return

        # 需要用户手动输入
        if value == "ask":
            await query.message.reply_text(f"请补充「{param}」信息，直接回复即可。")
            return

        # 用按钮值作为追加输入发送回 handle_message
        display = value
        if param and param != value:
            display = f"{param}: {value}"

        await query.message.reply_text(f"✅ 已选择: {display}\n请稍候，正在继续处理...")
