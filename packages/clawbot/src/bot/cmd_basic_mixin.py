"""
基础命令 Mixin — 从 multi_main.py L792-L1032 提取
/start, /clear, /status, /draw, /news, /metrics, /context, /compact
"""
import asyncio
import logging

from src.bot.globals import (
    history_store, context_manager, metrics, health_checker,
    news_fetcher, image_tool, get_siliconflow_key, get_total_balance,
    SILICONFLOW_KEYS, LOW_BALANCE_THRESHOLD,
    send_long_message, execution_hub,
)

logger = logging.getLogger(__name__)


class BasicCommandsMixin:
    """基础 Telegram 命令"""

    async def cmd_start(self, update, context):
        if not self._is_authorized(update.effective_user.id):
            await update.message.reply_text("无权限")
            return

        await update.message.reply_text(
            f"{self.emoji} **{self.name}** - {self.role}\n\n"
            f"模型: `{self.model.split('/')[-1]}`\n\n"
            f"直接发消息开始对话！\n"
            f"群聊中 @我 或提到我的名字即可\n\n"
            f"社媒默认使用 OpenClaw 专用浏览器；首次会自动拉起，登录一次后可持续复用。\n\n"
            f"**常用命令**\n"
            f"/clear - 清空对话\n"
            f"/status - 状态\n"
            f"/hot - 抓热点并一键发文（兼容 /hotpost）\n"
            f"/post\_social [题材] - 自动拉起专用浏览器并双发（兼容 /post）\n"
            f"/post\_x [题材] - 自动拉起专用浏览器发 X（兼容 /xpost）\n"
            f"/post\_xhs [题材] - 自动拉起专用浏览器发小红书（兼容 /xhspost、/xhs）\n"
            f"/social\_plan [题材] - 生成发文计划\n"
            f"/social\_repost [题材] - 生成双平台草稿\n"
            f"/social\_launch - 查看数字生命首发包\n"
            f"/social\_persona - 查看当前社媒人设\n"
            f"/topic <题材> - 研究题材并写入学习笔记\n"
            f"/dev <任务> - 开发/配置流程\n"
            f"/config - 查看当前运行配置\n"
            f"/cost - 查看请求/配额\n"
            f"/ops - 高级入口总菜单\n\n"

            f"**辅助命令**\n"
            f"/context - 上下文状态\n"
            f"/compact - 压缩上下文\n"
            f"/draw <描述> - 生成图片\n"
            f"/news - 科技早报\n\n"
            f"**投资命令**\n"
            f"/invest <话题> - 5位AI分析师协作\n"
            f"/quote <代码> - 查询行情\n"
            f"/market - 市场概览\n"
            f"/ta <代码> - 技术分析\n"
            f"/scan - 全市场扫描\n"
            f"/signal <代码> - 交易信号\n"
            f"/portfolio - 投资组合\n"
            f"/buy <代码> <数量> - 模拟买入\n"
            f"/sell <代码> <数量> - 模拟卖出\n"
            f"/trades - 交易记录\n"
            f"/watchlist - 自选股\n"
            f"/backtest <代码> - 策略回测\n"
            f"/rebalance - 组合再平衡\n\n"
            f"**交易系统**\n"
            f"/risk - 风控状态\n"
            f"/monitor - 持仓监控\n"
            f"/autotrader - 自动交易\n"
            f"/tradingsystem - 系统总览\n"
            f"/journal - 交易日志\n"
            f"/performance - 绩效统计\n"
            f"/review - 复盘报告\n\n"
            f"**协作命令**\n"
            f"/discuss <轮数> <主题> - 多Bot讨论\n"
            f"/collab <任务> - 多模型协作\n"
            f"/lanes - 查看群聊分流标签\n\n"
            f"**高级执行**\n"
            f"/brief - 手动生成执行简报\n"
            f"/lane - 查看群聊分流规则\n"
            f"/xwatch <X合集推文链接> - 导入博主监控\n"
            f"/xbrief - 查看X更新摘要+原文链接\n"
            f"/xdraft [主题] - 生成X流量草稿\n"
            f"/xpost [草稿ID或主题] - 自动发X\n"
            f"/xhsdraft [主题] - 生成小红书草稿\n"
            f"/xhspost [草稿ID或主题] - 自动发小红书\n\n"
            f"**IBKR实盘**\n"
            f"/ibuy <代码> <数量> - IBKR买入\n"
            f"/isell <代码> <数量> - IBKR卖出\n"
            f"/ipositions - IBKR持仓\n"
            f"/iorders - IBKR订单\n"
            f"/iaccount - IBKR账户\n"
            f"/icancel - 取消订单",
            parse_mode="Markdown"
        )

    async def cmd_lanes(self, update, context):
        """查看群聊显式分流标签"""
        if not self._is_authorized(update.effective_user.id):
            return

        await update.message.reply_text(
            "**群聊分流标签（替代 Telegram Topic）**\n\n"
            "在群里发消息时加上标签，可强制指定回复 Bot：\n"
            "- `[RISK]` / `#风控` -> Claude Sonnet（风险闸门）\n"
            "- `[ALPHA]` / `#研究` -> Qwen 235B（研究与规划）\n"
            "- `[EXEC]` / `#执行` -> DeepSeek V3（执行与技术）\n"
            "- `[FAST]` / `#快问` -> GPT-OSS（快速答复）\n"
            "- `[CN]` / `#中文` -> DeepSeek V3（中文表达）\n"
            "- `[BRAIN]` / `#终极` -> Claude Opus（深度推理）\n"
            "- `[CREATIVE]` / `#创意` -> Claude Haiku（文案创意）\n\n"
            "示例：`[RISK] 今天持仓有没有超风险？`\n"
            "提示：`@bot` 提及优先级仍高于标签。",
            parse_mode="Markdown"
        )

    async def cmd_clear(self, update, context):
        if not self._is_authorized(update.effective_user.id):
            return
        chat_id = update.effective_chat.id
        history_store.clear_messages(self.bot_id, chat_id)
        await update.message.reply_text(f"{self.emoji} 对话已清空")

    async def cmd_status(self, update, context):
        if not self._is_authorized(update.effective_user.id):
            return

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
            balance_warning = "\n⚠️ **余额不足，请及时充值！**"

        browser_running = "运行中" if social_browser.get("browser_running") else "未启动"
        x_state_raw = social_browser.get("x_ready")
        xhs_state_raw = social_browser.get("xiaohongshu_ready")
        x_state = "已登录" if x_state_raw is True else ("待登录" if x_state_raw is False else "待检查")
        xhs_state = "已登录" if xhs_state_raw is True else ("待登录" if xhs_state_raw is False else "待检查")

        await update.message.reply_text(
            f"{self.emoji} **{self.name}** 状态\n\n"
            f"角色: {self.role}\n"
            f"模型: `{self.model.split('/')[-1]}`\n"
            f"当前对话: {msg_count // 2} 轮\n"
            f"API Keys: {len(SILICONFLOW_KEYS)} 个\n"
            f"总余额: {total_balance:.2f} 元\n"
            f"健康: {'正常' if bot_health.get('healthy', True) else '异常'}\n"
            f"运行: {stats['uptime_hours']}h\n"
            f"今日消息: {stats['today_messages']}\n"
            f"社媒浏览器: 专用模式 / {browser_running}\n"
            f"X 登录: {x_state}\n"
            f"小红书登录: {xhs_state}\n"
            f"社媒人设: {social_persona.get('name', '未配置')} / {social_persona.get('headline', '')}{balance_warning}",
            parse_mode="Markdown"
        )

    async def cmd_draw(self, update, context):
        if not self._is_authorized(update.effective_user.id):
            return

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
        await update.message.reply_text(f"{self.emoji} 正在生成: {prompt}...")

        api_key = get_siliconflow_key()
        if not api_key:
            await update.message.reply_text("没有可用的 API Key")
            return

        image_tool.set_api_key(api_key)
        result = await image_tool.generate(prompt, model)

        if result["success"]:
            for path in result["paths"]:
                with open(path, "rb") as f:
                    await context.bot.send_photo(
                        chat_id=update.effective_chat.id,
                        photo=f,
                        caption=f"Prompt: {prompt[:100]}"
                    )
        else:
            await update.message.reply_text(f"生成失败: {result.get('error')}")

    async def cmd_news(self, update, context):
        if not self._is_authorized(update.effective_user.id):
            return
        await update.message.reply_text(f"{self.emoji} 正在获取新闻...")
        try:
            report = await news_fetcher.generate_morning_report()
            await update.message.reply_text(report)
        except Exception as e:
            await update.message.reply_text(f"获取失败: {e}")

    async def cmd_metrics(self, update, context):
        """运行指标命令"""
        if not self._is_authorized(update.effective_user.id):
            return

        stats = metrics.get_stats()
        health = health_checker.get_status()
        db_stats = history_store.get_stats()

        text = f"**运行指标**\n\n"
        text += f"运行时间: {stats['uptime_hours']}h\n"
        text += f"总消息: {stats['total_messages']}\n"
        text += f"今日消息: {stats['today_messages']}\n"
        text += f"API 调用: {stats['total_api_calls']}\n"
        text += f"错误率: {stats['error_rate']}%\n"
        text += f"平均延迟: {stats['avg_latency_ms']}ms\n\n"

        text += f"**存储**\n"
        text += f"数据库: {db_stats['db_size_kb']}KB\n"
        text += f"总消息: {db_stats['total_messages']}\n"
        text += f"对话数: {db_stats['total_chats']}\n\n"

        text += f"**模型使用**\n"
        for model, count in stats.get('model_usage', {}).items():
            text += f"- {model.split('/')[-1]}: {count}\n"

        text += f"\n**健康状态**\n"
        for bot_id, status in health.items():
            icon = "✅" if status['healthy'] else "❌"
            text += f"{icon} {bot_id}: 错误{status['consecutive_errors']}\n"

        await update.message.reply_text(text, parse_mode="Markdown")

    async def cmd_context(self, update, context):
        """查看当前上下文状态"""
        if not self._is_authorized(update.effective_user.id):
            return

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

    async def cmd_compact(self, update, context):
        """手动压缩上下文"""
        if not self._is_authorized(update.effective_user.id):
            return

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
