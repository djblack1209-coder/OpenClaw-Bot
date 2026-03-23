"""
OpenClaw OMEGA — Telegram 主控台网关
用户的唯一交互界面。接收所有消息，路由到 Brain，实时推送进度。

与现有系统共存:
  - 现有 7 个 MultiBot 继续运行（处理各自群聊/频道）
  - GatewayBot 是第 8 个 Bot，专门作为 OMEGA 统一入口
  - 通过 EventBus 接收所有模块事件
"""
import asyncio
import logging
import os
from typing import Dict, List, Optional

from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    BotCommand,
)
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, filters,
)

logger = logging.getLogger(__name__)


class OpenClawGateway:
    """
    Telegram 主控台 — OpenClaw 的唯一门脸。

    用法:
        gw = OpenClawGateway(token="...", admin_user_ids=[123456])
        await gw.start()
    """

    def __init__(self, token: str, admin_user_ids: Optional[List[int]] = None):
        self._token = token
        self._admin_ids = set(admin_user_ids or [])
        self._app: Optional[Application] = None
        self._progress_messages: Dict[int, int] = {}  # chat_id → message_id（用于编辑进度消息）

        if not token:
            logger.warning("OMEGA Gateway Bot Token 未设置")

    async def start(self) -> None:
        """启动 Gateway Bot"""
        if not self._token:
            logger.info("Gateway Bot 未配置Token，跳过启动")
            return

        self._app = (
            Application.builder()
            .token(self._token)
            .build()
        )

        # 注册handlers
        self._app.add_handler(CommandHandler("start", self._cmd_start))
        self._app.add_handler(CommandHandler("status", self._cmd_status))
        self._app.add_handler(CommandHandler("tasks", self._cmd_tasks))
        self._app.add_handler(CommandHandler("cost", self._cmd_cost))
        self._app.add_handler(CommandHandler("evolve", self._cmd_evolve))
        self._app.add_handler(CommandHandler("cancel", self._cmd_cancel))
        self._app.add_handler(CallbackQueryHandler(self._on_callback))
        self._app.add_handler(MessageHandler(
            filters.ALL & ~filters.COMMAND, self._on_message
        ))

        # 设置Bot命令菜单
        commands = [
            BotCommand("start", "开始使用 / 帮助"),
            BotCommand("status", "系统状态"),
            BotCommand("tasks", "当前任务列表"),
            BotCommand("cost", "今日费用"),
            BotCommand("evolve", "触发进化扫描"),
            BotCommand("cancel", "取消当前任务"),
        ]

        await self._app.initialize()
        await self._app.bot.set_my_commands(commands)
        await self._app.start()
        await self._app.updater.start_polling(drop_pending_updates=True)

        logger.info(f"OpenClaw Gateway Bot 已启动 (白名单: {len(self._admin_ids)} 用户)")

        # 订阅 EventBus 事件
        self._subscribe_events()

    async def stop(self) -> None:
        """优雅关闭"""
        if self._app:
            await self._app.updater.stop()
            await self._app.stop()
            await self._app.shutdown()
            logger.info("Gateway Bot 已停止")

    def _check_authorized(self, user_id: int) -> bool:
        """白名单检查"""
        if not self._admin_ids:
            return True  # 未配置白名单则允许所有
        return user_id in self._admin_ids

    def _subscribe_events(self) -> None:
        """订阅 EventBus 事件"""
        try:
            from src.core.event_bus import get_event_bus

            bus = get_event_bus()

            async def on_progress(event):
                await self._broadcast_progress(event.data)

            async def on_task_complete(event):
                await self._broadcast_result(event.data)

            async def on_alert(event):
                await self._broadcast_alert(event.data)

            bus.subscribe("brain.progress", on_progress, "gateway_progress")
            bus.subscribe("system.task_completed", on_task_complete, "gateway_result")
            bus.subscribe("trade.risk_alert", on_alert, "gateway_risk_alert")
            bus.subscribe("system.self_heal_failed", on_alert, "gateway_heal_alert")

        except Exception as e:
            logger.warning(f"EventBus 订阅失败: {e}")

    # ── 命令处理 ──────────────────────────────────────

    async def _cmd_start(self, update: Update, context) -> None:
        user = update.effective_user
        if not self._check_authorized(user.id):
            await update.message.reply_text("未授权访问。")
            return

        text = (
            "━━━ OpenClaw OMEGA ━━━\n\n"
            "我是你在数字世界中的完整替身。\n"
            "直接告诉我你需要什么，我来执行。\n\n"
            "你可以说：\n"
            "  \"帮我分析茅台今天能买吗\"\n"
            "  \"帮我比价一台MacBook Pro\"\n"
            "  \"帮我订个周末的好餐厅\"\n"
            "  \"发一条关于AI趋势的推文\"\n\n"
            "输入 /status 查看系统状态\n"
            "输入 /cost 查看今日费用"
        )
        await update.message.reply_text(text)

    async def _cmd_status(self, update: Update, context) -> None:
        if not self._check_authorized(update.effective_user.id):
            return
        try:
            from src.api.rpc import ClawBotRPC
            status = ClawBotRPC._rpc_system_status()
            bots = status.get("bots", [])
            alive = sum(1 for b in bots if b.get("alive"))
            text = (
                f"━━━ 系统状态 ━━━\n"
                f"Bot: {alive}/{len(bots)} 在线\n"
                f"API池: {status.get('api_pool', {}).get('total_sources', 0)} 个模型\n"
                f"记忆: {status.get('memory', {}).get('total_entries', 0)} 条\n"
                f"券商: {'已连接' if status.get('broker', {}).get('connected') else '未连接'}"
            )
        except Exception as e:
            text = f"获取状态失败: {e}"
        await update.message.reply_text(text)

    async def _cmd_tasks(self, update: Update, context) -> None:
        if not self._check_authorized(update.effective_user.id):
            return
        try:
            from src.core.brain import get_brain
            brain = get_brain()
            tasks = brain.get_active_tasks()
            if not tasks:
                await update.message.reply_text("当前没有活跃任务。")
                return
            lines = ["━━━ 活跃任务 ━━━"]
            for t in tasks:
                status = "✅" if t.get("success") else "⏳"
                lines.append(f"{status} {t.get('goal', '未知')} [{t.get('elapsed', 0):.1f}s]")
            await update.message.reply_text("\n".join(lines))
        except Exception as e:
            await update.message.reply_text(f"查询失败: {e}")

    async def _cmd_cost(self, update: Update, context) -> None:
        if not self._check_authorized(update.effective_user.id):
            return
        try:
            from src.core.cost_control import get_cost_controller
            cc = get_cost_controller()
            spend = cc.get_daily_spend()
            budget = cc._daily_budget
            text = (
                f"━━━ 今日费用 ━━━\n"
                f"已花费: ${spend:.4f}\n"
                f"日预算: ${budget:.2f}\n"
                f"剩余: ${max(0, budget - spend):.4f}\n"
                f"用量: {spend/budget:.1%}" if budget > 0 else ""
            )
        except Exception as e:
            text = f"费用查询失败: {e}"
        await update.message.reply_text(text)

    async def _cmd_evolve(self, update: Update, context) -> None:
        if not self._check_authorized(update.effective_user.id):
            return
        await update.message.reply_text("进化扫描已触发，请稍候...")
        try:
            from src.core.brain import get_brain
            brain = get_brain()
            result = await brain.process_message(
                "telegram", "进化扫描",
                context={"chat_id": update.effective_chat.id}
            )
            if result.success:
                await update.message.reply_text(f"扫描完成: {result.final_result}")
            else:
                await update.message.reply_text(f"扫描失败: {result.error}")
        except Exception as e:
            await update.message.reply_text(f"扫描异常: {e}")

    async def _cmd_cancel(self, update: Update, context) -> None:
        if not self._check_authorized(update.effective_user.id):
            return
        await update.message.reply_text("已取消当前任务。")

    # ── 消息处理 ──────────────────────────────────────

    async def _on_message(self, update: Update, context) -> None:
        """处理所有非命令消息"""
        user = update.effective_user
        if not self._check_authorized(user.id):
            return

        message = update.message
        chat_id = update.effective_chat.id

        # 提取内容
        if message.text:
            content = message.text
            msg_type = "text"
        elif message.voice:
            # 语音消息 → Deepgram STT 转文字
            try:
                from src.tools.deepgram_stt import transcribe_audio
                voice_file = await message.voice.get_file()
                audio_bytes = await voice_file.download_as_bytearray()
                content = await transcribe_audio(bytes(audio_bytes))
                if content:
                    msg_type = "text"  # 转录成功，当文字处理
                    await message.reply_text(f"🎤 识别: {content}")
                else:
                    await message.reply_text("语音识别失败，请重新发送或发送文字消息。")
                    return
            except Exception as e:
                logger.warning(f"语音转文字失败: {e}")
                await message.reply_text(f"语音识别暂不可用: {e}")
                return
        elif message.photo:
            content = message.caption or "[图片]"
            msg_type = "image"
        elif message.document:
            content = message.caption or f"[文件: {message.document.file_name}]"
            msg_type = "file"
        else:
            return

        # 发送"处理中"消息
        progress_msg = await message.reply_text("正在思考...")

        try:
            from src.core.brain import get_brain
            brain = get_brain()

            result = await brain.process_message(
                source="telegram",
                message=content,
                message_type=msg_type,
                context={
                    "user_id": user.id,
                    "chat_id": chat_id,
                    "username": user.username,
                },
            )

            # 处理结果 — 使用 ResponseCard 统一渲染
            try:
                from src.core.response_cards import card_from_brain_result
                card = card_from_brain_result(result)
                text = card.to_telegram()
                keyboard = card.action_buttons()

                try:
                    await progress_msg.edit_text(
                        text, parse_mode="HTML", reply_markup=keyboard
                    )
                except Exception:
                    # HTML 解析失败时降级为纯文本
                    await progress_msg.edit_text(
                        text.replace("<b>", "").replace("</b>", "")
                        .replace("<i>", "").replace("</i>", ""),
                        reply_markup=keyboard,
                    )
            except ImportError:
                # response_cards 不可用时降级
                if result.needs_clarification:
                    text = self._format_clarification(result)
                    keyboard = self._build_clarification_keyboard(
                        result.task_id, result.clarification_params
                    )
                    await progress_msg.edit_text(text, reply_markup=keyboard)
                elif result.success:
                    text = self._format_result(result)
                    try:
                        await progress_msg.edit_text(text, parse_mode="HTML")
                    except Exception:
                        # HTML 解析失败时降级为纯文本
                        await progress_msg.edit_text(text)
                else:
                    await progress_msg.edit_text(f"执行失败: {result.error}")

        except Exception as e:
            logger.error(f"Gateway 消息处理失败: {e}", exc_info=True)
            await progress_msg.edit_text(f"处理异常: {e}")

    async def _on_callback(self, update: Update, context) -> None:
        """处理 Inline Keyboard 回调"""
        query = update.callback_query
        await query.answer()

        if not self._check_authorized(query.from_user.id):
            return

        data = query.data  # 格式: "task_id:action:value"
        parts = data.split(":", 2)
        if len(parts) < 2:
            return

        task_id = parts[0]
        callback_data = ":".join(parts[1:])

        try:
            from src.core.brain import get_brain
            brain = get_brain()
            result = await brain.handle_callback(task_id, callback_data)

            if result.success:
                text = self._format_result(result)
            else:
                text = f"操作失败: {result.error}"

            try:
                await query.edit_message_text(text, parse_mode="HTML")
            except Exception:
                await query.edit_message_text(text)

        except Exception as e:
            await query.edit_message_text(f"回调处理失败: {e}")

    # ── 格式化 ──────────────────────────────────────

    def _format_clarification(self, result) -> str:
        """格式化追问消息"""
        intent = result.intent
        lines = [f"了解，你需要: {intent.goal}"]
        if result.clarification_params:
            lines.append("\n请补充以下信息：")
        return "\n".join(lines)

    def _format_result(self, result) -> str:
        """格式化最终结果 — 优先使用 message_format 统一格式化层"""
        # 优先使用 TaskResult.to_user_message()（委托 message_format 模块）
        try:
            user_msg = result.to_user_message()
            if user_msg:
                return user_msg
        except Exception:
            logger.debug("Silenced exception", exc_info=True)  # 降级到原始格式化

        # 降级: 手动拼接
        intent = result.intent
        lines = []

        if intent:
            lines.append(f"━━━ {intent.goal} ━━━")
        lines.append("")

        if isinstance(result.final_result, dict):
            for key, value in result.final_result.items():
                if isinstance(value, dict):
                    answer = value.get("answer") or value.get("note") or value.get("status", "")
                    if answer:
                        lines.append(str(answer)[:500])
                else:
                    lines.append(f"{key}: {str(value)[:200]}")
        else:
            lines.append(str(result.final_result)[:1000])

        lines.append(f"\n耗时: {result.elapsed_seconds:.1f}s")
        return "\n".join(lines)

    def _build_clarification_keyboard(
        self, task_id: str, params: List[str]
    ) -> InlineKeyboardMarkup:
        """构建追问键盘"""
        buttons = []
        # 根据参数类型生成按钮
        for param in params[:4]:  # 最多4行
            if "time" in param or "date" in param:
                buttons.append([
                    InlineKeyboardButton("今天", callback_data=f"{task_id}:{param}:today"),
                    InlineKeyboardButton("明天", callback_data=f"{task_id}:{param}:tomorrow"),
                    InlineKeyboardButton("周末", callback_data=f"{task_id}:{param}:weekend"),
                ])
            elif "count" in param or "人" in param:
                buttons.append([
                    InlineKeyboardButton("1人", callback_data=f"{task_id}:{param}:1"),
                    InlineKeyboardButton("2人", callback_data=f"{task_id}:{param}:2"),
                    InlineKeyboardButton("3-4人", callback_data=f"{task_id}:{param}:4"),
                    InlineKeyboardButton("5+", callback_data=f"{task_id}:{param}:5"),
                ])
            else:
                buttons.append([
                    InlineKeyboardButton(f"补充{param}", callback_data=f"{task_id}:{param}:ask"),
                ])

        buttons.append([
            InlineKeyboardButton("取消", callback_data=f"{task_id}:cancel:0"),
        ])
        return InlineKeyboardMarkup(buttons)

    # ── 广播（EventBus消费者）──────────────────────────

    async def _broadcast_progress(self, data: Dict) -> None:
        """向所有管理员广播进度"""
        if not self._app or not self._admin_ids:
            return
        text = self._format_progress(data)
        for uid in self._admin_ids:
            try:
                if uid in self._progress_messages:
                    await self._app.bot.edit_message_text(
                        text, chat_id=uid,
                        message_id=self._progress_messages[uid],
                    )
                else:
                    msg = await self._app.bot.send_message(uid, text)
                    self._progress_messages[uid] = msg.message_id
            except Exception:
                logger.debug("Silenced exception", exc_info=True)

    async def _broadcast_result(self, data: Dict) -> None:
        """广播任务完成"""
        if not self._app or not self._admin_ids:
            return
        goal = data.get("goal", "任务")
        text = f"✅ {goal} 已完成 ({data.get('elapsed', 0):.1f}s)"
        for uid in self._admin_ids:
            try:
                await self._app.bot.send_message(uid, text)
                self._progress_messages.pop(uid, None)
            except Exception:
                logger.debug("Silenced exception", exc_info=True)

    async def _broadcast_alert(self, data: Dict) -> None:
        """广播告警"""
        if not self._app or not self._admin_ids:
            return
        text = f"⚠️ 告警: {data.get('error_msg') or data.get('note', '未知告警')}"
        for uid in self._admin_ids:
            try:
                await self._app.bot.send_message(uid, text)
            except Exception:
                logger.debug("Silenced exception", exc_info=True)

    def _format_progress(self, progress: Dict) -> str:
        """格式化进度消息"""
        total = progress.get("total", 0)
        completed = progress.get("completed", 0)
        pct = progress.get("progress_pct", 0)

        lines = [f"[进度 {completed}/{total}] {pct:.0f}%"]
        nodes = progress.get("nodes", [])
        for node in nodes:
            status = node.get("status", "pending")
            icon = {"success": "✅", "running": "⏳", "failed": "❌",
                    "pending": "⬜", "skipped": "⏭"}.get(status, "⬜")
            lines.append(f"  {icon} {node.get('name', '?')}")

        return "\n".join(lines)


# ── 启动入口 ──────────────────────────────────────────────

_gateway: Optional[OpenClawGateway] = None


async def start_gateway() -> Optional[OpenClawGateway]:
    """启动 Gateway Bot（从环境变量读取配置）"""
    global _gateway
    token = os.environ.get("OMEGA_GATEWAY_BOT_TOKEN", "")
    admin_ids_str = os.environ.get("OMEGA_ADMIN_USER_IDS", "")
    admin_ids = [int(x.strip()) for x in admin_ids_str.split(",") if x.strip().isdigit()]

    if not token:
        logger.info("OMEGA_GATEWAY_BOT_TOKEN 未设置，Gateway 未启动")
        return None

    _gateway = OpenClawGateway(token=token, admin_user_ids=admin_ids)
    await _gateway.start()
    return _gateway


async def stop_gateway() -> None:
    global _gateway
    if _gateway:
        await _gateway.stop()
        _gateway = None
