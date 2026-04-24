"""
工具命令 Mixin — /draw, /news, /qr, /tts, /agent, /claude code, inline query
"""
import logging
import os

from src.bot.auth import requires_auth
from src.bot.error_messages import error_generic
from src.bot.globals import (
    get_siliconflow_key,
    image_tool,
    news_fetcher,
    send_long_message,
)
from src.constants import IMG_MODEL_FLUX
from src.message_format import format_error
from src.telegram_ux import ProgressTracker, with_typing

logger = logging.getLogger(__name__)


class _ToolsMixin:
    """AI 画图、新闻、二维码、TTS、Agent、Inline Query"""

    @requires_auth
    @with_typing
    async def cmd_draw(self, update, context):
        """AI绘图"""
        try:
            args = context.args
            if not args:
                await update.message.reply_text(
                    "用法: `/draw 图片描述`\n可选: `/draw 描述 --model flux/sd3/sdxl`",
                    parse_mode="Markdown"
                )
                return

            prompt_parts = []
            model = IMG_MODEL_FLUX
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
        except Exception as e:
            logger.warning("[cmd_draw] 执行失败: %s", e)
            try:
                await update.message.reply_text("⚠️ 命令执行失败，请稍后重试")
            except Exception as e:
                logger.debug("Telegram消息操作失败(用户可能已删除): %s", e)

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
                "二维码功能需要安装依赖：\n`pip install 'qrcode[pil]'`",
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

    # ── /tts 命令 — 文字转语音 (edge-tts 10K) ──

    @requires_auth
    @with_typing
    async def cmd_tts(self, update, context):
        """文字转语音 — /tts <文本> [音色]"""
        args = context.args or []
        if not args:
            from src.tools.tts_tool import CHINESE_VOICES, format_voice_list
            help_text = "🎤 文字转语音\n\n用法: /tts <文本> [音色]\n\n"
            help_text += format_voice_list()
            help_text += "\n\n示例：\n  /tts 今天天气真好\n  /tts 你好世界 云希"
            await update.message.reply_text(help_text)
            return

        # 检查最后一个参数是否是音色名
        from src.tools.tts_tool import CHINESE_VOICES, text_to_speech
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

    # ── /agent 命令 — 搬运 smolagents (26.2k) 自主 Agent ──

    @requires_auth
    @with_typing
    async def cmd_agent(self, update, context):
        """智能 Agent — 自然语言驱动多工具链"""
        query = " ".join(context.args) if context.args else ""
        if not query:
            await update.message.reply_text(
                "🤖 <b>智能 Agent</b>\n\n"
                "用自然语言描述你想做的事，Agent 会自动调用工具链完成。\n\n"
                "示例：\n"
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
            from src.agent_tools import HAS_SMOLAGENTS, run_agent

            if not HAS_SMOLAGENTS:
                await msg.edit_text(
                    "⚠️ smolagents 未安装，Agent 功能不可用。\n"
                    "运行 <code>pip install 'smolagents>=1.0.0'</code> 后重启。",
                    parse_mode="HTML",
                )
                return

            result = await run_agent(query)

            # 将 markdown 转为 Telegram 安全 HTML
            try:
                from src.telegram_markdown import md_to_html
                safe = md_to_html(result)
            except Exception as e:  # noqa: F841
                import html as _html
                safe = _html.escape(result)

            await send_long_message(
                update.effective_chat.id, safe, context, parse_mode="HTML"
            )
            # 删除"思考中"提示消息
            try:
                await msg.delete()
            except Exception:
                logger.debug("Silenced exception", exc_info=True)

        except Exception as e:
            await msg.edit_text(format_error(e, "Agent 执行"))

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
            from src.invest_tools import get_crypto_quote, get_stock_quote
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

    # ---- Claude Code CLI 桥接 ----

    @requires_auth
    @with_typing
    async def cmd_claude_code(self, update, context):
        """在桌面启动 Claude Code CLI 终端窗口。

        用法:
          /claude code           — 在项目目录打开 Claude Code 交互终端
          /claude code <消息>    — 打开终端并自动发送初始消息
        """
        import shutil
        import subprocess

        args = context.args or []

        # /claude code <消息> — 跳过 "code" 这个词
        if args and args[0].lower() == "code":
            args = args[1:]

        prompt = " ".join(args) if args else ""

        # 查找 claude 路径
        claude_path = shutil.which("claude")
        if not claude_path:
            for p in [
                os.path.expanduser("~/.npm-global/bin/claude"),
                "/usr/local/bin/claude",
                "/opt/homebrew/bin/claude",
            ]:
                if os.path.isfile(p) and os.access(p, os.X_OK):
                    claude_path = p
                    break
        if not claude_path:
            await update.message.reply_text("⚠️ Claude Code CLI 未安装。请先运行: npm install -g @anthropic-ai/claude-code")
            return

        # 构建终端命令
        project_dir = os.path.expanduser("~/Desktop/OpenEverything")
        if prompt:
            # 有初始消息：用 -p 执行后保持终端打开
            # 使用 --resume 避免"已在运行"冲突
            terminal_cmd = f'cd "{project_dir}" && "{claude_path}" --resume auto -p "{prompt.replace(chr(34), chr(92)+chr(34))}"'
        else:
            # 无消息：直接打开交互式 Claude Code
            terminal_cmd = f'cd "{project_dir}" && "{claude_path}" --resume auto'

        # 用 osascript 在桌面打开 Terminal 窗口
        applescript = f'''
tell application "Terminal"
    activate
    do script "{terminal_cmd}"
end tell
'''
        try:
            subprocess.Popen(["osascript", "-e", applescript])

            if prompt:
                await update.message.reply_text(
                    f"🖥 Claude Code 已在桌面终端启动\n\n"
                    f"> {prompt[:100]}{'...' if len(prompt) > 100 else ''}\n\n"
                    f"请切换到 Terminal 窗口查看执行结果"
                )
            else:
                await update.message.reply_text(
                    "🖥 Claude Code 已在桌面终端启动\n\n"
                    "请切换到 Terminal 窗口开始对话\n"
                    "项目目录: ~/Desktop/OpenEverything"
                )

            # 微信同步通知
            try:
                import asyncio

                from src.wechat_bridge import send_to_wechat
                asyncio.create_task(send_to_wechat(
                    "🖥 Claude Code 已在桌面启动" +
                    (f"\n> {prompt[:80]}" if prompt else "")
                ))
            except Exception:
                pass

        except Exception as e:
            logger.warning("[cmd_claude_code] 启动终端失败: %s", e)
            await update.message.reply_text(f"⚠️ Claude Code 启动失败: {e}")
