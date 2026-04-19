"""
CollabCommandsMixin - Collaboration, discussion, and investment commands.
Extracted from multi_main.py.
"""

import asyncio
import logging
import re
import json

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from src.bot.auth import requires_auth
from src.bot.error_messages import error_service_failed
from src.telegram_ux import with_typing
from config.prompts import INVEST_DISCUSSION_ROLES
from src.utils import now_et
from src.bot.globals import (
    chat_router,
    collab_orchestrator,
    bot_registry,
    safe_edit,
    send_as_bot,
    shared_memory,
    _pending_trades,
)

# 幻影导入修复: 8 个符号从实际定义模块导入
from src.broker_selector import ibkr
from src.trading_journal import journal
from src.universe import get_full_universe, full_market_scan
from src.ta_engine import get_full_analysis, format_analysis
from src.invest_tools import format_quote, get_market_summary
from src.constants import TG_SAFE_LENGTH
from src.constants import (
    BOT_QWEN,
    BOT_DEEPSEEK,
    BOT_GPTOSS,
    BOT_CLAUDE_HAIKU,
    BOT_CLAUDE_SONNET,
    BOT_CLAUDE_OPUS,
)

logger = logging.getLogger(__name__)


def _parse_trade_recommendations(text: str) -> list:
    """从策略师回复中解析JSON交易建议

    寻找 ```json {...} ``` 代码块，提取trades数组
    返回: [{"action": "BUY", "symbol": "AAPL", "qty": 5, "entry_price": 150.0,
            "stop_loss": 145.0, "take_profit": 160.0, "reason": "..."}, ...]
    """
    if not text:
        return []

    # 尝试匹配 ```json ... ``` 代码块
    patterns = [
        r"```json\s*(\{.*?\})\s*```",
        r"```\s*(\{.*?\})\s*```",
        r'(\{"trades"\s*:\s*\[.*?\]\s*\})',
    ]

    for pattern in patterns:
        matches = re.findall(pattern, text, re.DOTALL)
        for match in matches:
            try:
                from json_repair import loads as jloads

                data = jloads(match)
                trades = data.get("trades", [])
                if not trades:
                    continue
                # 验证每个交易的格式
                valid_trades = []
                for t in trades:
                    action = str(t.get("action", "")).upper()
                    symbol = str(t.get("symbol", "")).upper().strip()
                    qty = t.get("qty", 0)
                    reason = str(t.get("reason", ""))
                    if action in ("BUY", "SELL") and symbol and qty > 0:
                        trade = {
                            "action": action,
                            "symbol": symbol,
                            "qty": int(qty) if float(qty) == int(qty) else float(qty),
                            "reason": reason[:100],
                            "entry_price": float(t.get("entry_price", 0) or 0),
                            "stop_loss": float(t.get("stop_loss", 0) or 0),
                            "take_profit": float(t.get("take_profit", 0) or 0),
                            "signal_score": int(t.get("signal_score", 0) or 0),
                        }
                        valid_trades.append(trade)
                if valid_trades:
                    logger.info("[Invest] 解析到 %s 条交易建议: %s", len(valid_trades), valid_trades)
                    return valid_trades
            except (json.JSONDecodeError, TypeError, ValueError) as e:
                logger.debug("[Invest] JSON解析失败: %s", e)
                continue

    logger.info("[Invest] 未解析到交易建议（策略师可能建议观望）")
    return []


class CollabCommandsMixin:
    """Mixin providing collaboration, discussion, and investment commands."""

    @requires_auth
    async def _auto_invest(self, update, context, user_text: str = ""):
        """
        全自动投资闭环：全市场扫描334标的 → 多层筛选 → AI团队分析 → 一键下单 → 交易日志
        """
        if chat_router.get_discuss_session(update.effective_chat.id):
            await update.message.reply_text("已有分析会议进行中，请等待完成或发送 /stop_discuss 中断")
            return

        # 检查日亏损限额
        today_pnl = journal.get_today_pnl()
        if today_pnl["hit_limit"]:
            await update.message.reply_text(
                f"{self.emoji} 今日已亏损 ${abs(today_pnl['pnl']):.2f}，触及日亏损限额 ${today_pnl['limit']:.0f}\n"
                "风控规则：停止交易，明天再来。"
            )
            return


        # === 阶段1: 全市场扫描 ===
        universe_count = len(get_full_universe())
        msg = await update.message.reply_text(
            f"{self.emoji} 全自动投资启动\n\n"
            f"阶段 1/3: 扫描全市场 {universe_count} 个标的...\n"
            "（S&P500核心 + ETF + 加密货币 + 中概股）\n"
            "多层筛选漏斗: 流动性→技术指标→信号评分\n\n"
            "预计耗时2-5分钟，请稍候..."
        )

        try:
            scan_result = await full_market_scan()
        except Exception as e:
            logger.error("协作市场扫描失败: %s", e)
            await safe_edit(msg, error_service_failed("市场扫描"))
            return

        top = scan_result.get("top_candidates", [])
        if not top:
            await safe_edit(
                msg,
                f"{self.emoji} 全市场扫描完成\n\n"
                f"扫描: {scan_result['total_scanned']}个标的\n"
                f"层1通过: {scan_result['layer1_passed']}\n"
                f"层2信号: {scan_result['layer2_passed']}\n"
                f"耗时: {scan_result['scan_time']}s\n\n"
                "结果: 暂无明显信号，市场平静。\n"
                "建议: 观望等待，不勉强交易。\n\n"
                "稍后可以再说「开始投资」重新扫描。",
            )
            return

        # 挑选最佳标的（前5个）
        top5 = top[:5]
        top_symbols = [s["symbol"] for s in top5]

        scan_summary = (
            f"阶段 1/3: 全市场扫描完成\n"
            f"扫描{scan_result['total_scanned']}个 → "
            f"层1:{scan_result['layer1_passed']}个 → "
            f"层2:{scan_result['layer2_passed']}个 → "
            f"Top{len(top5)}候选\n"
            f"耗时: {scan_result['scan_time']}s\n\n"
            "发现信号:\n"
        )
        for s in top5:
            arrow = "+" if s["change_pct"] >= 0 else ""
            vol = " [放量]" if s.get("volume_surge") else ""
            scan_summary += (
                f"  {s['signal_cn']} {s['symbol']} ${s['price']} "
                f"({arrow}{s['change_pct']}%) 评分:{s['score']:+d}{vol}\n"
            )

        await safe_edit(msg, f"{self.emoji} 全自动投资\n\n{scan_summary}\n阶段 2/3: 获取详细技术数据...\n")

        # === 阶段2: 获取详细技术分析 ===
        ta_tasks = [get_full_analysis(sym) for sym in top_symbols]
        ta_results = await asyncio.gather(*ta_tasks, return_exceptions=True)

        ta_text = ""
        for sym, data in zip(top_symbols, ta_results):
            if isinstance(data, dict) and "error" not in data:
                ta_text += f"\n{format_analysis(data)}\n"

        await safe_edit(
            msg,
            f"{self.emoji} 全自动投资\n\n"
            f"{scan_summary}\n"
            "阶段 2/3: 技术数据就绪\n"
            "阶段 3/3: AI超短线团队分析中...\n\n"
            "市场雷达 → 宏观猎手 → 图表狙击手 → 风控铁闸 → 交易指挥官",
        )

        # === 阶段3: 触发投资会议 ===
        topic = f"全市场扫描{scan_result['total_scanned']}个标的后，筛选出以下Top候选: {', '.join(top_symbols)}。请分析并给出交易决策"
        context.args = [topic]
        await self.cmd_invest(update, context)

    @requires_auth
    @with_typing
    async def cmd_invest(self, update, context):
        """投资讨论: /invest 现在该买什么？"""
        # 防止重复触发
        if chat_router.get_discuss_session(update.effective_chat.id):
            return

        args = context.args
        if not args:
            await update.message.reply_text(
                "投资讨论 - 6位AI分析师协作分析\n\n"
                "用法: `/invest <投资话题>`\n\n"
                "示例:\n"
                "`/invest 现在该买什么？`\n"
                "`/invest 比特币还能涨吗`\n"
                "`/invest 分析一下NVDA`\n\n"
                "流程: 情报收集 -> 基本面 -> 技术面 -> 风控 -> 最终决策 -> 终审确认\n"
                "发送 /stop_discuss 可中断",
                parse_mode="Markdown",
            )
            return

        topic = " ".join(args)
        chat_id = update.effective_chat.id
        message_id = update.message.message_id

        # 投资讨论顺序：Haiku情报 -> Qwen基本面 -> GPT技术面 -> DeepSeek风控 -> Sonnet决策
        invest_order = [BOT_CLAUDE_HAIKU, BOT_QWEN, BOT_GPTOSS, BOT_DEEPSEEK, BOT_CLAUDE_SONNET, BOT_CLAUDE_OPUS]

        # 先获取市场数据作为上下文
        await update.message.reply_text(f"{self.emoji} 正在获取市场数据和技术指标...")
        try:
            market_data = await get_market_summary()
        except Exception as e:  # noqa: F841
            market_data = "(市场数据获取失败)"

        # 如果话题提到具体标的，获取行情+技术分析
        target_quote = ""
        ta_data_text = ""
        potential_symbols = re.findall(r"\b([A-Z]{2,5})\b", topic.upper())
        known_symbols = {
            "AAPL",
            "MSFT",
            "GOOGL",
            "GOOG",
            "AMZN",
            "NVDA",
            "META",
            "TSLA",
            "AMD",
            "INTC",
            "NFLX",
            "BABA",
            "JD",
            "PDD",
            "NIO",
            "XPEV",
            "LI",
            "TSM",
            "ASML",
            "AVGO",
            "BTC",
            "ETH",
            "SOL",
            "BNB",
            "XRP",
            "DOGE",
            "SPY",
            "QQQ",
            "DIA",
            "IWM",
            "CRM",
            "ORCL",
            "ADBE",
            "QCOM",
        }
        target_syms = [sym for sym in potential_symbols if sym in known_symbols]
        # 并行获取行情+技术分析
        if target_syms:
            ta_tasks = []
            for sym in target_syms[:5]:  # 最多5个
                real_sym = f"{sym}-USD" if sym in {"BTC", "ETH", "SOL", "BNB", "XRP", "DOGE"} else sym
                ta_tasks.append(get_full_analysis(real_sym))
            ta_results = await asyncio.gather(*ta_tasks, return_exceptions=True)
            for sym, data in zip(target_syms[:5], ta_results):
                if isinstance(data, dict) and "error" not in data:
                    target_quote += f"\n{format_quote({'symbol': data['symbol'], 'name': data['name'], 'price': data['price'], 'change': data['change'], 'change_pct': data['change_pct'], 'high': data['indicators'].get('high_5d', 0), 'low': data['indicators'].get('low_5d', 0), 'volume': data['indicators'].get('volume', 0), 'currency': 'USD'})}\n"
                    ta_data_text += f"\n--- {data['symbol']} 技术指标 ---\n{format_analysis(data)}\n"

        # 注册到 discuss_sessions
        info = await chat_router.start_discuss(chat_id, topic, 1, invest_order, discuss_type="invest")
        if "已有进行中" in info:
            await context.bot.send_message(chat_id=chat_id, text=info, reply_to_message_id=message_id)
            return

        await context.bot.send_message(
            chat_id=chat_id,
            text=(
                "-- 超短线投资分析会议 --\n"
                f"议题: {topic}\n\n"
                f"{market_data}\n"
                f"{target_quote}\n"
                "分析顺序:\n"
                "1. Haiku (市场雷达) - 全市场扫描\n"
                "2. Qwen (宏观猎手) - 宏观方向判断\n"
                "3. GPT-OSS (图表狙击手) - 技术信号精准狙击\n"
                "4. DeepSeek (风控铁闸) - 仓位止损计算\n"
                "5. Claude Sonnet (交易指挥官) - 最终交易指令\n"
                "6. Claude Opus (首席策略师) - 终审确认/否决\n\n"
                "发送 /stop_discuss 可中断"
            ),
            reply_to_message_id=message_id,
        )

        # 构造每个Bot的投资分析提示
        invest_context = f"市场数据:\n{market_data}\n"
        if target_quote:
            invest_context += f"\n相关标的行情:\n{target_quote}\n"
        if ta_data_text:
            invest_context += f"\n实时技术分析数据:\n{ta_data_text}\n"
        invest_context += f"\nIBKR预算: ${ibkr.budget - ibkr.total_spent:.0f} / ${ibkr.budget:.0f}\n"

        # ── 血管 2: 注入历史分析上下文 ──
        try:
            history_hits = shared_memory.search(topic, limit=3)
            invest_history = [
                h
                for h in history_hits
                if "invest" in h.get("key", "").lower() or "ocr_financial" in h.get("key", "").lower()
            ]
            if invest_history:
                invest_context += "\n历史分析参考:\n"
                for h in invest_history[:2]:
                    invest_context += f"- [{h.get('key', '')}] {h.get('value', '')[:200]}\n"
                invest_context += "\n"
        except Exception as e:
            logger.debug("[Invest] 历史上下文注入失败(非致命): %s", e)

        previous_opinions = []
        from src.message_sender import _clean_for_telegram, _split_message

        # 投资讨论角色提示词 — 从中央注册表导入
        role_map = INVEST_DISCUSSION_ROLES

        # 实时进度消息 — 让用户看到每个 AI 的分析进度
        progress_icons = {"pending": "⏳", "running": "🔄", "done": "✅", "failed": "❌", "timeout": "⏰"}
        bot_status = {bid: "pending" for bid in invest_order}

        def _render_invest_progress():
            lines = [f"📊 {topic} 分析进度"]
            lines.append("───────────────────")
            for bid in invest_order:
                role_name_p = role_map.get(bid, ("分析师", ""))[0]
                icon = progress_icons.get(bot_status[bid], "❓")
                lines.append(f"{icon} {role_name_p}")
            done_count = sum(1 for s in bot_status.values() if s in ("done", "failed", "timeout"))
            pct = done_count / len(invest_order)
            bar_len = 16
            filled = int(pct * bar_len)
            bar = "▓" * filled + "░" * (bar_len - filled)
            lines.append(f"\n[{bar}] {done_count}/{len(invest_order)}")
            return "\n".join(lines)

        # 发送初始进度消息
        progress_msg = await context.bot.send_message(chat_id=chat_id, text=_render_invest_progress())

        async def _update_progress():
            try:
                await context.bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=progress_msg.message_id,
                    text=_render_invest_progress(),
                )
            except Exception:
                logger.debug("Silenced exception", exc_info=True)

        for i, bot_id in enumerate(invest_order):
            # 检查是否被中断
            if not chat_router.get_discuss_session(chat_id):
                await context.bot.send_message(
                    chat_id=chat_id, text="-- 投资分析会议已被中断 --", reply_to_message_id=message_id
                )
                return

            caller = collab_orchestrator._api_callers.get(bot_id)
            target_bot = bot_registry.get(bot_id)
            if not caller or not target_bot or not target_bot.app:
                logger.warning("[Invest] %s 未注册或未启动，跳过", bot_id)
                continue

            bot_telegram = target_bot.app.bot
            role_name, role_prompt = role_map.get(bot_id, ("分析师", "请给出你的分析。"))

            # 更新进度：当前 bot 正在分析
            bot_status[bot_id] = "running"
            await _update_progress()

            # 构造提示
            prompt = f"【投资分析会议】\n议题: {topic}\n\n{invest_context}\n你的角色: {role_name}\n{role_prompt}\n"
            if previous_opinions:
                prompt += "\n前面分析师的观点:\n" + "\n---\n".join(previous_opinions) + "\n"

            timeout_sec = 120
            last_response = ""
            try:
                response = await asyncio.wait_for(caller(chat_id, prompt), timeout=timeout_sec)
                previous_opinions.append(f"[{role_name}] {response[:800]}")
                chat_router.record_discuss_message(chat_id, role_name, response)
                # 保存最后一个Bot（Sonnet策略师）的完整回复用于解析交易建议
                if bot_id == invest_order[-1]:
                    last_response = response

                cleaned = _clean_for_telegram(response)
                parts = _split_message(cleaned, TG_SAFE_LENGTH)
                for pi, part in enumerate(parts):
                    reply_id = message_id if pi == 0 else None
                    try:
                        await bot_telegram.send_message(
                            chat_id=chat_id, text=part, parse_mode="Markdown", reply_to_message_id=reply_id
                        )
                    except Exception as e:  # noqa: F841
                        try:
                            await bot_telegram.send_message(chat_id=chat_id, text=part, reply_to_message_id=reply_id)
                        except Exception as e:  # noqa: F841
                            await bot_telegram.send_message(chat_id=chat_id, text=part)
                    if pi < len(parts) - 1:
                        await asyncio.sleep(0.3)
                await asyncio.sleep(1)
                bot_status[bot_id] = "done"
                await _update_progress()
            except asyncio.TimeoutError:
                bot_status[bot_id] = "timeout"
                await _update_progress()
                logger.warning("[Invest] %s 回复超时 (%ss)", bot_id, timeout_sec)
                try:
                    await bot_telegram.send_message(chat_id=chat_id, text=f"[{role_name} 回复超时，跳过]")
                except Exception:
                    logger.debug("[Invest] 发送超时通知失败(静默)")
            except Exception as e:
                bot_status[bot_id] = "failed"
                await _update_progress()
                logger.error("[Invest] %s 发言失败: %s", bot_id, e)
                try:
                    await bot_telegram.send_message(chat_id=chat_id, text=f"[{role_name} 暂时无法回复，已跳过]")
                except Exception as e:
                    logger.debug("[Invest] 发送失败通知失败(静默)")

        # 讨论结束
        await chat_router.stop_discuss(chat_id)

        # 解析策略师的交易建议并生成一键下单按钮
        trades = _parse_trade_recommendations(last_response)
        if trades:
            # 存储待确认交易到全局字典
            trade_key = f"invest_{chat_id}_{int(now_et().timestamp())}"
            _pending_trades[trade_key] = {
                "trades": trades,
                "chat_id": chat_id,
                "topic": topic,
                "timestamp": now_et().isoformat(),
            }

            # 构建交易摘要和确认按钮
            lines = ["-- 投资分析会议结束 --\n", "策略师建议执行以下交易:\n"]
            buttons = []
            for idx, t in enumerate(trades):
                action_cn = "买入" if t["action"] == "BUY" else "卖出"
                lines.append(f"{idx + 1}. {action_cn} {t['symbol']} x{t['qty']}  ({t['reason']})")
                btn_text = f"{'🟢' if t['action'] == 'BUY' else '🔴'} {action_cn} {t['symbol']} x{t['qty']}"
                callback_data = f"itrade:{trade_key}:{idx}"
                buttons.append([InlineKeyboardButton(btn_text, callback_data=callback_data)])

            # 添加全部执行和取消按钮
            buttons.append(
                [
                    InlineKeyboardButton("✅ 全部执行", callback_data=f"itrade_all:{trade_key}"),
                    InlineKeyboardButton("❌ 取消", callback_data=f"itrade_cancel:{trade_key}"),
                ]
            )
            lines.append(f"\n预算剩余: ${ibkr.budget - ibkr.total_spent:.2f} / ${ibkr.budget:.2f}")
            lines.append("\n点击按钮确认下单到IBKR模拟账户:")

            keyboard = InlineKeyboardMarkup(buttons)
            await context.bot.send_message(
                chat_id=chat_id,
                text="\n".join(lines),
                reply_markup=keyboard,
                reply_to_message_id=message_id,
            )
        else:
            await context.bot.send_message(
                chat_id=chat_id,
                text="-- 投资分析会议结束 --\n\n策略师建议观望，暂无交易操作\n\n使用 /buy /sell 手动执行交易\n使用 /portfolio 查看持仓",
                reply_to_message_id=message_id,
            )

        # ── 血管 2: 投资分析结果写入 SharedMemory ──
        try:
            invest_summary = "\n---\n".join(previous_opinions) if previous_opinions else "无分析结果"
            trade_summary = ""
            if trades:
                trade_lines = [
                    f"{t['action']} {t['symbol']} x{t['qty']} (止损{t.get('stop_loss', 'N/A')}, 目标{t.get('take_profit', 'N/A')})"
                    for t in trades
                ]
                trade_summary = f"\n交易建议: {'; '.join(trade_lines)}"
            else:
                trade_summary = "\n结论: 观望"

            timestamp = now_et().strftime("%m/%d %H:%M")
            shared_memory.remember(
                key=f"invest_{timestamp}_{topic[:30]}",
                value=f"投资分析会议: {topic}\n{trade_summary}\n\n各角色观点摘要:\n{invest_summary[:1500]}",
                category="general",
                source_bot="invest_pipeline",
                chat_id=chat_id,
                importance=3,
                ttl_hours=168,  # 保留 7 天
            )
            logger.info("[Invest] 分析结果已写入 SharedMemory: %s", topic)
        except Exception as e:
            logger.debug("[Invest] SharedMemory 写入失败(非致命): %s", e)

    @requires_auth
    @with_typing
    async def cmd_discuss(self, update, context):
        """讨论模式 - 多Bot多轮讨论，需人类明确指定轮数"""
        # 所有Bot都可以触发 /discuss，由第一个收到命令的Bot发起
        # 用 discuss_sessions 防止重复触发
        if chat_router.get_discuss_session(update.effective_chat.id):
            return

        args = context.args
        if not args:
            await update.message.reply_text(
                "**讨论模式** - 多Bot多轮讨论\n\n"
                "用法: `/discuss <轮数> <主题>`\n\n"
                "示例:\n"
                "`/discuss 3 AI会取代程序员吗`\n"
                "`/discuss 2 比特币未来走势分析`\n\n"
                "每轮所有Bot依次发言，人类可随时 /stop_discuss 结束。",
                parse_mode="Markdown",
            )
            return

        # 解析轮数
        try:
            rounds = int(args[0])
            if rounds < 1 or rounds > 10:
                await update.message.reply_text("轮数请设置在 1-10 之间")
                return
            topic = " ".join(args[1:])
        except ValueError as e:  # noqa: F841
            # 没指定轮数，默认2轮
            rounds = 2
            topic = " ".join(args)

        if not topic:
            await update.message.reply_text("请提供讨论主题")
            return

        chat_id = update.effective_chat.id

        # 启动讨论
        info = await chat_router.start_discuss(chat_id, topic, rounds)
        await update.message.reply_text(info)

        # 自动驱动讨论流程
        await self._run_discuss_loop(chat_id, context, update.message.message_id)

    @requires_auth
    @with_typing
    async def cmd_stop_discuss(self, update, context):
        """停止讨论模式"""
        try:
            chat_id = update.effective_chat.id
            discuss_result = await chat_router.stop_discuss(chat_id)
            workflow_result = await chat_router.stop_service_workflow(chat_id)
            await update.message.reply_text(f"{discuss_result}\n{workflow_result}")
        except Exception as e:
            logger.warning("[cmd_stop_discuss] 执行失败: %s", e)
            try:
                await update.message.reply_text("⚠️ 命令执行失败，请稍后重试")
            except Exception:
                pass

    async def _run_discuss_loop(self, chat_id, context, reply_to):
        """驱动讨论循环：依次让每个Bot用自己的Telegram账号发言"""
        from src.message_sender import _clean_for_telegram, _split_message

        while True:
            # 检查讨论是否仍然活跃（支持 /stop_discuss 中断）
            session = chat_router.get_discuss_session(chat_id)
            if not session or not session.get("active", False):
                logger.info("[Discuss] chat=%s 讨论已被中断", chat_id)
                return

            turn = await chat_router.next_discuss_turn(chat_id)
            if turn is None:
                # 讨论结束
                await context.bot.send_message(
                    chat_id=chat_id,
                    text="讨论结束。各位Bot已完成所有轮次发言。",
                    reply_to_message_id=reply_to,
                )
                await chat_router.stop_discuss(chat_id)
                return

            bot_id, prompt = turn
            bot_cap = chat_router.bots.get(bot_id)
            bot_name = bot_cap.name if bot_cap else bot_id

            # 找到对应 bot 的 API caller 和 Telegram 实例
            caller = collab_orchestrator._api_callers.get(bot_id)
            target_bot = bot_registry.get(bot_id)
            if not caller or not target_bot or not target_bot.app:
                logger.warning("[Discuss] %s 未注册或未启动，跳过", bot_id)
                continue

            bot_telegram = target_bot.app.bot  # 该 bot 自己的 Telegram 实例

            # 根据模型设置超时：R1 需要更长时间思考
            timeout_sec = 300 if bot_id == BOT_DEEPSEEK else 120

            try:
                response = await asyncio.wait_for(
                    caller(chat_id, prompt),
                    timeout=timeout_sec,
                )
                # 记录到讨论历史
                chat_router.record_discuss_message(chat_id, bot_name, response)
                # 用该 bot 自己的 Telegram 账号发送到群组
                cleaned = _clean_for_telegram(response)
                parts = _split_message(cleaned, TG_SAFE_LENGTH)
                for pi, part in enumerate(parts):
                    reply_id = reply_to if pi == 0 else None
                    try:
                        await bot_telegram.send_message(
                            chat_id=chat_id,
                            text=part,
                            parse_mode="Markdown",
                            reply_to_message_id=reply_id,
                        )
                    except Exception as e:  # noqa: F841
                        await bot_telegram.send_message(
                            chat_id=chat_id,
                            text=part,
                            reply_to_message_id=reply_id,
                        )
                    if pi < len(parts) - 1:
                        await asyncio.sleep(0.3)
                # 间隔1秒，避免消息刷屏太快
                await asyncio.sleep(1)
            except asyncio.TimeoutError:
                logger.warning("[Discuss] %s 回复超时 (%ss)，跳过", bot_id, timeout_sec)
                try:
                    await bot_telegram.send_message(
                        chat_id=chat_id,
                        text=f"[回复超时({timeout_sec}s)，跳过本轮发言]",
                    )
                except Exception:
                    logger.debug("[Discuss] 发送超时通知失败(静默)")
            except Exception as e:
                logger.error("[Discuss] %s 发言失败: %s", bot_id, e)
                try:
                    await bot_telegram.send_message(
                        chat_id=chat_id,
                        text="[发言暂时不可用，已跳过]",
                    )
                except Exception as e:
                    logger.debug("[Discuss] 发送失败通知失败(静默)")

    @requires_auth
    @with_typing
    async def cmd_collab(self, update, context):
        """协作模式命令 - 启动多模型协作流程"""
        # 所有Bot都可以触发 /collab，用 collab_tasks 防止重复
        if chat_router.get_discuss_session(update.effective_chat.id):
            return

        args = context.args
        if not args:
            await update.message.reply_text(
                "**协作模式** - 多模型协作完成复杂任务\n\n"
                "用法: `/collab <任务描述>`\n\n"
                "流程:\n"
                "1. 规划: DeepSeek-R1/Qwen 分析任务并制定计划\n"
                "2. 执行: Claude Opus 4.6 执行核心难点\n"
                "3. 汇总: ClawBot 整合输出最终结果\n\n"
                "可选参数:\n"
                "`/collab --planner r1 <任务>` 指定 DeepSeek-R1 规划\n"
                "`/collab --planner qwen <任务>` 指定 Qwen 规划\n\n"
                "示例:\n"
                "`/collab 帮我设计一个微服务架构的电商系统`\n"
                "`/collab 写一篇关于AI发展趋势的深度分析报告`",
                parse_mode="Markdown",
            )
            return

        # 防止并发：检查是否已有活跃的协作任务
        chat_id = update.effective_chat.id
        active_task = collab_orchestrator.get_active_task(chat_id)
        if active_task:
            await update.message.reply_text("当前已有进行中的协作任务，请等待完成后再启动新任务。")
            return

        # 防止并发：检查是否已有活跃的讨论
        if chat_router.get_discuss_session(chat_id):
            await update.message.reply_text("当前已有进行中的讨论，请先 /stop_discuss 结束后再启动协作。")
            return

        # 解析参数
        task_parts = []
        planner_override = None
        i = 0
        while i < len(args):
            if args[i] == "--planner" and i + 1 < len(args):
                planner_map = {"r1": BOT_DEEPSEEK, "deepseek": BOT_DEEPSEEK, "qwen": BOT_QWEN}
                planner_override = planner_map.get(args[i + 1].lower(), args[i + 1])
                i += 2
            else:
                task_parts.append(args[i])
                i += 1

        task_text = " ".join(task_parts)
        if not task_text:
            await update.message.reply_text("请提供任务描述")
            return

        # 启动协作任务
        task = await collab_orchestrator.start_collab(chat_id, task_text, planner_override)

        # 发送启动通知
        planner_name = {BOT_DEEPSEEK: "DeepSeek V3 🐉", BOT_QWEN: "Qwen 235B 🧠"}.get(task.planner_id, task.planner_id)
        status_msg = await update.message.reply_text(
            f"**🤝 协作模式启动**\n\n"
            f"任务: {task_text[:100]}{'...' if len(task_text) > 100 else ''}\n\n"
            f"**阶段 1/3** - 规划中...\n"
            f"规划师: {planner_name}\n"
            f"执行者: Claude Opus 4.6 ✨\n"
            f"汇总者: ClawBot 🤖",
            parse_mode="Markdown",
        )

        try:
            # 阶段1: 规划
            plan_result = await collab_orchestrator.run_planning(task)
            if task.error:
                await safe_edit(status_msg, f"协作失败（规划阶段）: {task.error}")
                return

            await safe_edit(
                status_msg,
                f"**🤝 协作模式**\n\n"
                f"**阶段 1/4** ✅ 规划完成 ({planner_name})\n"
                f"**阶段 2/4** - Claude Opus 4.6 执行中...\n"
                f"**阶段 3/4** - 待审查\n"
                f"**阶段 4/4** - 待汇总",
            )

            # 用规划者自己的 Telegram 账号发送规划结果
            await send_as_bot(
                task.planner_id, chat_id, f"📋 规划结果\n\n{plan_result}", reply_to_message_id=update.message.message_id
            )

            # 阶段2: 执行
            exec_result = await collab_orchestrator.run_execution(task)
            if task.error:
                await safe_edit(status_msg, f"协作失败（执行阶段）: {task.error}")
                return

            await safe_edit(
                status_msg,
                f"**🤝 协作模式**\n\n"
                f"**阶段 1/4** ✅ 规划完成\n"
                f"**阶段 2/4** ✅ 执行完成 (Claude Opus 4.6)\n"
                f"**阶段 3/4** - {planner_name} 审查中...\n"
                f"**阶段 4/4** - 待汇总",
            )

            # 用 Claude 自己的 Telegram 账号发送执行结果
            await send_as_bot(
                BOT_CLAUDE_SONNET,
                chat_id,
                f"⚡ 执行结果\n\n{exec_result}",
                reply_to_message_id=update.message.message_id,
            )

            # 阶段3: 审查（规划者审查执行结果）
            review_result = await collab_orchestrator.run_review(task)

            # 用审查者自己的 Telegram 账号发送审查结果
            review_icon = "✅" if task.review_passed else "🔄"
            await send_as_bot(
                task.reviewer_id,
                chat_id,
                f"{review_icon} 审查结果\n\n{review_result}",
                reply_to_message_id=update.message.message_id,
            )

            # 如果审查不通过且可以重试，进行修订
            if not task.review_passed and task.retry_count < task.max_retries:
                await safe_edit(
                    status_msg,
                    "**🤝 协作模式**\n\n"
                    "**阶段 1/4** ✅ 规划完成\n"
                    "**阶段 2/4** 🔄 修订执行中 (Claude Opus 4.6)\n"
                    "**阶段 3/4** - 待重新审查\n"
                    "**阶段 4/4** - 待汇总",
                )

                exec_result = await collab_orchestrator.run_revised_execution(task)
                if task.error:
                    await safe_edit(status_msg, f"协作失败（修订执行）: {task.error}")
                    return

                await send_as_bot(
                    BOT_CLAUDE_SONNET,
                    chat_id,
                    f"🔄 修订结果\n\n{exec_result}",
                    reply_to_message_id=update.message.message_id,
                )

            await safe_edit(
                status_msg,
                f"**🤝 协作模式**\n\n"
                f"**阶段 1/4** ✅ 规划完成\n"
                f"**阶段 2/4** ✅ 执行完成\n"
                f"**阶段 3/4** ✅ 审查{'通过' if task.review_passed else '(修订后继续)'}\n"
                f"**阶段 4/4** - ClawBot 汇总中...",
            )

            # 阶段4: 汇总
            summary_result = await collab_orchestrator.run_summary(task)
            if task.error:
                await safe_edit(status_msg, f"协作失败（汇总阶段）: {task.error}")
                return

            retry_note = f" (经{task.retry_count}次修订)" if task.retry_count > 0 else ""
            await safe_edit(
                status_msg,
                f"**🤝 协作模式 - 完成 ✅**{retry_note}\n\n"
                f"**阶段 1/4** ✅ 规划 ({planner_name})\n"
                f"**阶段 2/4** ✅ 执行 (Claude Opus 4.6)\n"
                f"**阶段 3/4** ✅ 审查 ({planner_name})\n"
                f"**阶段 4/4** ✅ 汇总 (ClawBot)",
            )

            # 用 ClawBot 自己的 Telegram 账号发送最终汇总
            await send_as_bot(
                BOT_QWEN, chat_id, f"📊 最终汇总\n\n{summary_result}", reply_to_message_id=update.message.message_id
            )

            # 保存协作结论到共享记忆
            try:
                shared_memory.save_collab_result(
                    task_text=task_text,
                    plan_result=plan_result,
                    exec_result=exec_result,
                    summary_result=summary_result,
                    planner_id=task.planner_id,
                    chat_id=chat_id,
                )
            except Exception as mem_err:
                logger.warning("[Collab] 保存共享记忆失败: %s", mem_err)

        except Exception:
            logger.exception("[%s] 协作任务出错", self.name)
            try:
                await status_msg.edit_text(error_service_failed("协作任务"))
            except Exception:
                logger.debug("[Collab] 编辑错误消息失败(静默)")
