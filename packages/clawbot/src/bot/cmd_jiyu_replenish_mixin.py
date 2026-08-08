"""JIYU 补号远程入口：只允许授权私聊提交严格号源格式。"""

from __future__ import annotations

from telegram import ReplyKeyboardMarkup

from src.bot.auth import requires_auth
from src.sub2_replenish.core import InputFormatError, ReplenishJob, parse_seller_payload
from src.sub2_replenish.runner import ReplenishRunner


class JiyuReplenishCommandsMixin:
    """把本机补号助手接到 Telegram，浏览器 OAuth 仍在本机执行。"""

    _REPLENISH_MENU = (
        ("🧾 一键补号", "start"),
        ("📊 补号状态", "status"),
        ("⏹ 停止补号", "stop"),
        ("❌ 取消补号", "cancel"),
    )

    def _jiyu_remote_runner(self) -> ReplenishRunner:
        """按 Bot 实例懒加载独立批次，避免启动 Bot 时读取管理员凭据。"""
        runner = getattr(self, "_remote_replenish_runner", None)
        if runner is None:
            runner = ReplenishRunner()
            self._remote_replenish_runner = runner
        return runner

    def _jiyu_replenish_waiting(self) -> set[int]:
        """返回等待号源文本的私聊集合；只存 Telegram chat id。"""
        waiting = getattr(self, "_remote_replenish_waiting_chats", None)
        if waiting is None:
            waiting = set()
            self._remote_replenish_waiting_chats = waiting
        return waiting

    @staticmethod
    def _jiyu_replenish_summary(runner: ReplenishRunner) -> str:
        """只输出任务数量、计划和状态，不输出邮箱或任何凭据。"""
        state = runner.public_state()
        jobs = state.get("jobs") or []
        counts: dict[str, int] = {}
        plans: set[str] = set()
        for job in jobs:
            status = str(job.get("status") or "unknown")
            counts[status] = counts.get(status, 0) + 1
            plan = str(job.get("plan_type") or "")
            if plan:
                plans.add(plan)
        count_text = "、".join(f"{key} {value}" for key, value in sorted(counts.items())) or "暂无任务"
        plan_text = "、".join(sorted(plans)) or "等待 OAuth 识别"
        return (
            "JIYU 补号助手\n"
            f"批次: {len(jobs)} 个\n"
            f"计划: {plan_text}\n"
            f"状态: {count_text}\n"
            f"运行中: {'是' if state.get('running') else '否'}"
        )

    @classmethod
    def _jiyu_replenish_keyboard(cls) -> ReplyKeyboardMarkup:
        """构造中文手机菜单；按钮文本不包含任何敏感状态。"""
        return ReplyKeyboardMarkup(
            [[label for label, _ in cls._REPLENISH_MENU[:2]], [label for label, _ in cls._REPLENISH_MENU[2:]]],
            resize_keyboard=True,
            is_persistent=True,
            input_field_placeholder="选择补号操作",
        )

    async def _jiyu_replenish_start_prompt(self, update) -> None:
        """进入等待号源状态并展示中文按钮菜单。"""
        self._jiyu_replenish_waiting().add(update.effective_chat.id)
        await update.message.reply_text(
            "请选择“一键补号”，然后发送卖家 JSON 或邮箱----密码----totp_secret。\n"
            "Bot 只在本机内存解析，遇到 CAPTCHA、短信或风控时需在本机浏览器人工完成。",
            reply_markup=self._jiyu_replenish_keyboard(),
        )

    @requires_auth
    async def cmd_jiyu_replenish(self, update, context):
        """手机端远程补号菜单：/jiyu_replenish [status|stop|cancel]。"""
        action = (context.args or [""])[0].casefold()
        runner = self._jiyu_remote_runner()
        waiting = self._jiyu_replenish_waiting()

        if action in {"status", "状态"}:
            await update.message.reply_text(
                self._jiyu_replenish_summary(runner),
                reply_markup=self._jiyu_replenish_keyboard(),
            )
            return
        if action in {"stop", "停止"}:
            await runner.stop()
            waiting.discard(update.effective_chat.id)
            await update.message.reply_text(
                "JIYU 补号批次已停止，进程内敏感内容已清除。",
                reply_markup=self._jiyu_replenish_keyboard(),
            )
            return
        if action in {"cancel", "取消"}:
            waiting.discard(update.effective_chat.id)
            await update.message.reply_text(
                "已取消等待号源，不会读取下一条普通消息。",
                reply_markup=self._jiyu_replenish_keyboard(),
            )
            return
        if action:
            await update.message.reply_text("用法：/jiyu_replenish，然后在同一私聊发送 JSON 号源；也可使用 status、stop、cancel。")
            return
        if update.effective_chat.type != "private":
            await update.message.reply_text("补号只允许授权管理员私聊使用，避免号源出现在群聊。")
            return
        if runner.running:
            await update.message.reply_text("当前已有补号批次运行中，请先 /jiyu_replenish status 或 stop。")
            return
        await self._jiyu_replenish_start_prompt(update)

    async def _handle_jiyu_replenish_text(self, update, raw_text: str) -> bool:
        """消费等待中的私聊号源；未等待时返回 False 交给普通对话处理。"""
        chat = update.effective_chat
        user = update.effective_user
        if chat is None or user is None or chat.type != "private":
            return False
        menu_action = dict(self._REPLENISH_MENU).get(raw_text.strip())
        if menu_action == "start":
            await self._jiyu_replenish_start_prompt(update)
            return True
        if menu_action == "status":
            await update.message.reply_text(
                self._jiyu_replenish_summary(self._jiyu_remote_runner()),
                reply_markup=self._jiyu_replenish_keyboard(),
            )
            return True
        if menu_action == "stop":
            await self._jiyu_remote_runner().stop()
            self._jiyu_replenish_waiting().discard(chat.id)
            await update.message.reply_text(
                "JIYU 补号批次已停止，进程内敏感内容已清除。",
                reply_markup=self._jiyu_replenish_keyboard(),
            )
            return True
        if menu_action == "cancel":
            self._jiyu_replenish_waiting().discard(chat.id)
            await update.message.reply_text(
                "已取消等待号源，不会读取下一条普通消息。",
                reply_markup=self._jiyu_replenish_keyboard(),
            )
            return True
        waiting = self._jiyu_replenish_waiting()
        if chat.id not in waiting:
            return False
        waiting.discard(chat.id)
        runner = self._jiyu_remote_runner()
        if runner.running:
            await update.message.reply_text("当前已有补号批次运行中，本条号源未读取。")
            return True
        try:
            credentials = parse_seller_payload(raw_text)
            runner.replace_jobs([ReplenishJob(credential=item) for item in credentials])
            runner.start()
        except InputFormatError as exc:
            await update.message.reply_text(f"号源格式不符合要求：{exc}")
            return True
        except (RuntimeError, ValueError):
            await update.message.reply_text("补号批次未启动，请检查当前任务状态后重试。")
            return True
        await update.message.reply_text(
            f"已接收 {len(credentials)} 个号源并启动本机补号。\n"
            "OAuth 会在本机隔离浏览器中执行，遇到人工风控时发送 /jiyu_replenish status 查看进度。"
        )
        return True
