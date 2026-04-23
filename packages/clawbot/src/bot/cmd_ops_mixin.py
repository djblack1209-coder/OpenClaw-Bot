"""
Bot — 运维中枢 / 邮件 / 会议 / 任务 / 监控 命令 Mixin

包含功能:
  - 运维统一入口 (cmd_ops)
  - 开发流程 / 简报 / 泳道 / 成本 / 配置
  - 文档 / 会议 / 任务 / 系统监控子命令
  - 帮助文本 (_ops_help)
  - 交互菜单回调 (handle_ops_menu_callback)
"""

import asyncio
import logging
import os
from pathlib import Path

from src.bot.globals import execution_hub, send_long_message
from src.bot.rate_limiter import rate_limiter, token_budget
from src.bot.error_messages import error_service_failed
from src.bot.auth import requires_auth
from src.telegram_ux import with_typing
from src.notify_style import format_cost_card

logger = logging.getLogger(__name__)


class OpsCommandsMixin:
    @requires_auth
    @with_typing
    async def cmd_ops(self, update, context):
        try:
            args = context.args or []
            if not args:
                from telegram import InlineKeyboardButton, InlineKeyboardMarkup

                keyboard = [
                    [
                        InlineKeyboardButton("📝 任务管理", callback_data="ops_task"),
                        InlineKeyboardButton("📊 项目报告", callback_data="ops_project"),
                    ],
                    [
                        InlineKeyboardButton("🔥 热点扫描", callback_data="ops_hot"),
                        InlineKeyboardButton("✍️ 发帖", callback_data="ops_post"),
                    ],
                    [
                        InlineKeyboardButton("📧 邮件", callback_data="ops_email"),
                        InlineKeyboardButton("📝 会议纪要", callback_data="ops_meeting"),
                    ],
                    [
                        InlineKeyboardButton("🏠 生活提醒", callback_data="ops_life"),
                        InlineKeyboardButton("💰 赏金猎人", callback_data="ops_bounty"),
                    ],
                    [
                        InlineKeyboardButton("📺 监控", callback_data="ops_monitor"),
                        InlineKeyboardButton("🔧 开发", callback_data="ops_dev"),
                    ],
                ]
                await update.message.reply_text(
                    "<b>🎯 自动化工作台</b>\n选择要执行的操作：",
                    parse_mode="HTML",
                    reply_markup=InlineKeyboardMarkup(keyboard),
                )
                return

            main = args[0].lower().strip()
            rest = args[1:]

            if main in {"help", "h", "-h", "--help"}:
                await update.message.reply_text(self._ops_help())
                return

            if main == "email":
                await update.message.reply_text("正在整理邮箱...")
                only_unread = True
                if rest and rest[0].lower() in {"all", "--all"}:
                    only_unread = False
                triage = await asyncio.to_thread(execution_hub.triage_email, 120, only_unread)
                text = execution_hub.format_email_triage(triage)
                await send_long_message(update.effective_chat.id, text, context)
                return

            if main == "brief":
                await update.message.reply_text("正在生成执行简报...")
                text = await execution_hub.generate_daily_brief()
                await send_long_message(update.effective_chat.id, text, context)
                return

            if main == "docs":
                await self._ops_docs(update, context, rest)
                return

            if main == "meeting":
                await self._ops_meeting(update, context, rest)
                return

            if main == "task":
                await self._ops_task(update, context, rest)
                return

            if main == "content":
                keyword = " ".join(rest).strip() or "AI"
                await update.message.reply_text(f"正在生成「{keyword}」选题...")
                ideas = await execution_hub.generate_content_ideas(keyword=keyword, count=5)
                lines = [f"社媒选题 ({keyword})", ""]
                for i, it in enumerate(ideas, 1):
                    lines.append(f"{i}. {it}")
                await update.message.reply_text("\n".join(lines))
                return

            if main == "bounty":
                await self._ops_bounty(update, context, rest)
                return

            if main == "tweet":
                await self._ops_tweet(update, context, rest)
                return

            if main == "monitor":
                await self._ops_monitor(update, context, rest)
                return

            if main == "life":
                await self._ops_life(update, context, rest)
                return

            if main == "project":
                target = " ".join(rest).strip() or "."
                await update.message.reply_text(f"正在生成项目报告: {target}")
                report = await asyncio.to_thread(execution_hub.generate_project_report, target, 7)
                await send_long_message(update.effective_chat.id, report, context)
                return

            if main == "dev":
                target = " ".join(rest).strip() or "."
                await update.message.reply_text(f"正在执行开发流程: {target}")
                result = await asyncio.to_thread(execution_hub.run_dev_workflow, target)
                if not result.get("success"):
                    await send_long_message(
                        update.effective_chat.id,
                        error_service_failed("开发流程", result.get("error", "")),
                        context,
                    )
                    return

                lines = ["开发流程结果", ""]
                for i, step in enumerate(result.get("steps", []), 1):
                    ok = "成功" if step.get("ok") else "失败"
                    lines.append(f"[{i}] {ok} {step.get('command', '')}")
                    out = (step.get("stdout", "") or "").strip()
                    err = (step.get("stderr", "") or "").strip()
                    if out:
                        lines.append(f"输出: {out[:300]}")
                    if err:
                        lines.append(f"错误: {err[:300]}")
                    lines.append("")
                await send_long_message(update.effective_chat.id, "\n".join(lines).strip(), context)
                return

            await update.message.reply_text("❓ 未知子命令，请使用 /ops help 查看可用操作")
        except Exception as e:
            logger.warning("[cmd_ops] 执行失败: %s", e)
            try:
                await update.message.reply_text("⚠️ 命令执行失败，请稍后重试")
            except Exception as e:
                logger.debug("Telegram消息操作失败(用户可能已删除): %s", e)

    @requires_auth
    async def cmd_dev(self, update, context):
        try:
            args = ["dev", *(context.args or [])]
            context.args = args
            await self.cmd_ops(update, context)
        except Exception as e:
            logger.warning("[cmd_dev] 执行失败: %s", e)
            try:
                await update.message.reply_text("⚠️ 命令执行失败，请稍后重试")
            except Exception as e:
                logger.debug("Telegram消息操作失败(用户可能已删除): %s", e)

    @requires_auth
    @with_typing
    async def cmd_brief(self, update, context):
        try:
            await update.message.reply_text("正在生成执行简报...")
            brief = await execution_hub.generate_daily_brief()
            await send_long_message(update.effective_chat.id, brief, context)
            # 同步推送到微信（手动触发也要送达微信）
            try:
                from src.wechat_bridge import send_to_wechat
                import asyncio
                _t = asyncio.create_task(send_to_wechat(brief))
                _t.add_done_callback(lambda t: logger.debug("[cmd_brief] 微信推送完成") if not t.exception() else logger.warning("[cmd_brief] 微信推送失败: %s", t.exception()))
            except Exception as e:
                logger.debug("[cmd_brief] 微信同步跳过: %s", e)
        except Exception as e:
            logger.warning("[cmd_brief] 执行失败: %s", e)
            try:
                await update.message.reply_text("⚠️ 命令执行失败，请稍后重试")
            except Exception as e:
                logger.debug("Telegram消息操作失败(用户可能已删除): %s", e)

    @requires_auth
    async def cmd_lane(self, update, context):
        await self.cmd_lanes(update, context)

    @requires_auth
    @with_typing
    async def cmd_cost(self, update, context):
        try:
            throttle_flags = {
                "group_llm": os.getenv("CHAT_ROUTER_ENABLE_GROUP_LLM", "false").lower() in {"1", "true", "yes", "on"},
                "group_intent": os.getenv("CHAT_ROUTER_ENABLE_GROUP_INTENT", "false").lower() in {"1", "true", "yes", "on"},
                "group_fallback": os.getenv("CHAT_ROUTER_ENABLE_GROUP_FALLBACK", "false").lower()
                in {"1", "true", "yes", "on"},
                "fill_only": os.getenv("AUTO_TRADE_NOTIFY_ONLY_FILLS", "false").lower() in {"1", "true", "yes", "on"},
            }
            text = format_cost_card(
                throttle_flags=throttle_flags,
                token_rows=token_budget.get_all_status(),
                rate_rows=rate_limiter.get_all_status(),
            )
            await send_long_message(update.effective_chat.id, text, context)
        except Exception as e:
            logger.warning("[cmd_cost] 执行失败: %s", e)
            try:
                await update.message.reply_text("⚠️ 命令执行失败，请稍后重试")
            except Exception as e:
                logger.debug("Telegram消息操作失败(用户可能已删除): %s", e)

    @requires_auth
    @with_typing
    async def cmd_config(self, update, context):
        try:
            lines = ["当前执行配置", ""]
            lines.append("自动调度:")
            lines.append(f"- 执行简报: {os.getenv('OPS_BRIEF_ENABLED', 'false')}")
            lines.append(f"- 任务 Top3: {os.getenv('OPS_TASK_TOP3_ENABLED', 'false')}")
            lines.append(f"- 资讯监控: {os.getenv('OPS_MONITOR_ENABLED', 'false')}")
            lines.append(f"- 赏金播报: {os.getenv('OPS_BOUNTY_ENABLED', 'false')}")
            lines.append(f"- 变现 watcher: {os.getenv('OPS_PAYOUT_WATCH_ENABLED', 'true')}")
            lines.append("")
            lines.append("模型 / 路由:")
            lines.append(f"- 群聊免费 LLM 路由: {os.getenv('CHAT_ROUTER_ENABLE_GROUP_LLM', 'false')}")
            lines.append(f"- 群聊意图自动回复: {os.getenv('CHAT_ROUTER_ENABLE_GROUP_INTENT', 'false')}")
            lines.append(f"- 群聊兜底轮换: {os.getenv('CHAT_ROUTER_ENABLE_GROUP_FALLBACK', 'false')}")
            lines.append(f"- Upwork 自动接单: {os.getenv('OPS_UPWORK_AUTO_ACCEPT_OFFER', 'false')}")
            lines.append(f"- 社媒浏览器: OpenClaw 专用浏览器 (port {os.getenv('OPENCLAW_SOCIAL_BROWSER_PORT', '19222')})")
            persona = execution_hub.get_social_persona_summary()
            if persona.get("success"):
                lines.append(f"- 当前社媒人设: {persona.get('name', '')} / {persona.get('headline', '')}")
            lines.append("")
            lines.append("高频入口:")
            lines.append("- /dev <路径> -> 开发/配置流程")
            lines.append("- /brief -> 手动生成执行简报")
            lines.append("- /hot [x|xhs|all] [题材] -> 抓热点并一键发文")
            lines.append("- /post_social [题材] -> 自动拉起专用浏览器并双发")
            lines.append("- /social_plan [题材] -> 生成发文计划")
            lines.append("- /social_repost [题材] -> 生成双平台草稿")
            lines.append("- /social_launch -> 查看数字生命首发包")
            lines.append("- /social_persona -> 查看当前社媒人设")
            lines.append("- /cost -> 查看请求/Token/节流状态")
            lines.append("- /ops -> 全量自动化入口")
            await send_long_message(update.effective_chat.id, "\n".join(lines), context)
        except Exception as e:
            logger.warning("[cmd_config] 执行失败: %s", e)
            try:
                await update.message.reply_text("⚠️ 命令执行失败，请稍后重试")
            except Exception as e:
                logger.debug("Telegram消息操作失败(用户可能已删除): %s", e)

    async def _ops_docs(self, update, context, args):
        if not args:
            await update.message.reply_text("用法: /ops docs index <路径> | /ops docs search <关键词>")
            return
        sub = args[0].lower().strip()
        rest = args[1:]

        if sub == "index":
            target = " ".join(rest).strip() or "."
            await update.message.reply_text(f"正在建立文档索引: {target}")
            result = await asyncio.to_thread(execution_hub.build_doc_index, [target], 2000)
            await update.message.reply_text(
                "文档索引完成\n"
                f"扫描: {result.get('scanned', 0)}\n"
                f"入库: {result.get('indexed', 0)}\n"
                f"跳过: {result.get('skipped', 0)}"
            )
            return

        if sub == "search":
            query = " ".join(rest).strip()
            if not query:
                await update.message.reply_text("用法: /ops docs search <关键词>")
                return
            rows = await asyncio.to_thread(execution_hub.search_docs, query, 8)
            if not rows:
                await update.message.reply_text("未找到相关文档")
                return
            lines = [f"文档检索: {query}", ""]
            for i, item in enumerate(rows, 1):
                lines.append(f"{i}. {item.get('name')} ({item.get('ext')}, {item.get('size', 0)} bytes)")
                lines.append(f"   {item.get('path')}")
                pv = (item.get("preview", "") or "").strip()
                if pv:
                    lines.append(f"   {pv[:120]}")
            await send_long_message(update.effective_chat.id, "\n".join(lines), context)
            return

        await update.message.reply_text("未知 docs 子命令，用法: /ops docs index|search")

    async def _ops_meeting(self, update, context, args):
        if not args:
            await update.message.reply_text("用法: /ops meeting <会议纪要文本或文件路径>")
            return
        payload = " ".join(args).strip()
        if not payload:
            await update.message.reply_text("会议文本不能为空")
            return

        path = Path(payload).expanduser()
        if path.exists() and path.is_file():
            result = await asyncio.to_thread(execution_hub.summarize_meeting, "", str(path))
        else:
            result = await asyncio.to_thread(execution_hub.summarize_meeting, payload, "")

        if not result.get("success"):
            await update.message.reply_text(error_service_failed("会议纪要", result.get("error", "")))
            return
        lines = ["自动会议纪要", ""]
        lines.append(f"文本行数: {result.get('line_count', 0)}")
        lines.append(f"摘要: {result.get('summary', '')}")
        if result.get("decisions"):
            lines.append("\n决策:")
            for i, d in enumerate(result.get("decisions", [])[:5], 1):
                lines.append(f"{i}. {d}")
        if result.get("actions"):
            lines.append("\n行动项:")
            for i, a in enumerate(result.get("actions", [])[:8], 1):
                lines.append(f"{i}. {a}")
        await send_long_message(update.effective_chat.id, "\n".join(lines), context)

    async def _ops_task(self, update, context, args):
        if not args:
            await update.message.reply_text("用法: /ops task add|top|list|done")
            return
        sub = args[0].lower().strip()
        rest = args[1:]

        if sub == "add":
            title = " ".join(rest).strip()
            if not title:
                await update.message.reply_text("用法: /ops task add <任务标题>")
                return
            ret = await asyncio.to_thread(execution_hub.add_task, title)
            if ret.get("success"):
                await update.message.reply_text(f"任务已创建: #{ret.get('task_id')} {title}")
            else:
                await update.message.reply_text(error_service_failed("创建", ret.get("error", "")))
            return

        if sub == "done":
            if not rest:
                await update.message.reply_text("用法: /ops task done <任务ID>")
                return
            try:
                task_id = int(rest[0])
            except Exception as e:  # noqa: F841
                await update.message.reply_text("任务ID必须是数字")
                return
            ret = await asyncio.to_thread(execution_hub.update_task_status, task_id, "done")
            if ret.get("success"):
                await update.message.reply_text(f"任务已完成: #{task_id}")
            else:
                await update.message.reply_text(error_service_failed("更新", ret.get("error", "")))
            return

        if sub == "top":
            top = await asyncio.to_thread(execution_hub.top_tasks, 3)
            if not top:
                await update.message.reply_text("当前没有待办任务")
                return
            lines = ["今日最重要 3 件事", ""]
            for i, t in enumerate(top, 1):
                lines.append(f"{i}. #{t.get('id')} P{t.get('priority', 3)} {t.get('title', '')}")
            await update.message.reply_text("\n".join(lines))
            return

        if sub == "list":
            rows = await asyncio.to_thread(execution_hub.list_tasks, "")
            if not rows:
                await update.message.reply_text("当前没有任务")
                return
            lines = ["任务列表", ""]
            for t in rows[:20]:
                lines.append(f"#{t.get('id')} [{t.get('status')}] P{t.get('priority', 3)} {t.get('title', '')}")
            await send_long_message(update.effective_chat.id, "\n".join(lines), context)
            return

        await update.message.reply_text("未知 task 子命令，用法: add|done|top|list")

    async def _ops_monitor(self, update, context, args):
        if not args:
            await update.message.reply_text("用法: /ops monitor add|addx|list|run")
            return
        sub = args[0].lower().strip()
        rest = args[1:]

        if sub == "add":
            keyword = " ".join(rest).strip()
            if not keyword:
                await update.message.reply_text("用法: /ops monitor add <关键词>")
                return
            ret = await asyncio.to_thread(execution_hub.add_monitor, keyword, "news")
            if ret.get("success"):
                await update.message.reply_text(f"监控已添加: {keyword}")
            else:
                await update.message.reply_text(error_service_failed("添加", ret.get("error", "")))
            return

        if sub == "addx":
            handle = " ".join(rest).strip()
            if not handle:
                await update.message.reply_text("用法: /ops monitor addx <@账号或X链接>")
                return
            normalized = execution_hub._normalize_x_handle(handle)
            if not normalized:
                await update.message.reply_text("无法识别 X 账号，请检查链接或 @handle")
                return
            ret = await asyncio.to_thread(execution_hub.add_monitor, normalized, "x_profile")
            if ret.get("success"):
                await update.message.reply_text(f"X博主监控已添加: @{normalized}")
            else:
                await update.message.reply_text(error_service_failed("添加", ret.get("error", "")))
            return

        if sub == "list":
            rows = await asyncio.to_thread(execution_hub.list_monitors)
            if not rows:
                await update.message.reply_text("当前没有监控项")
                return
            lines = ["监控列表", ""]
            for r in rows:
                state = "开启" if int(r.get("enabled", 0) or 0) == 1 else "关闭"
                lines.append(f"#{r.get('id')} [{state}] {r.get('keyword')} ({r.get('source')})")
            await update.message.reply_text("\n".join(lines))
            return

        if sub == "run":
            await update.message.reply_text("正在执行一次监控扫描...")
            alerts = await execution_hub.run_monitors_once()
            if not alerts:
                await update.message.reply_text("监控完成：无新增")
                return
            lines = ["监控结果", ""]
            for al in alerts:
                lines.append(execution_hub.format_monitor_alert(al))
                lines.append("")
            await send_long_message(update.effective_chat.id, "\n".join(lines), context)
            return

        await update.message.reply_text("未知 monitor 子命令，用法: add|addx|list|run")

    def _ops_help(self) -> str:
        return (
            "执行场景命令\n\n"
            "社媒默认走 OpenClaw 专用浏览器；首次会自动拉起并复用登录态。\n"
            "/ops email [all] - 自动整理邮箱\n"
            "/ops brief - 每日行业简报\n"
            "/ops docs index <路径> - 建立本地文档索引\n"
            "/ops docs search <关键词> - 搜索本地文档\n"
            "/ops meeting <文件路径> - 自动会议纪要\n"
            "/ops task add <标题> - 新建任务\n"
            "/ops task top - 今日最重要3件事\n"
            "/ops task list - 任务列表\n"
            "/ops task done <ID> - 完成任务\n"
            "/ops content [关键词] - 社媒选题\n"
            "/social_plan [题材] - 生成双平台发文计划\n"
            "/social_repost [题材] - 生成双平台草稿\n"
            "/social_launch - 查看数字生命首发包\n"
            "/social_persona - 查看当前社媒人设\n"
            "/post_social [题材] - 自动拉起专用浏览器并双发\n"
            "/post_x [题材] - 自动拉起专用浏览器发 X\n"
            "/post_xhs [题材] - 自动拉起专用浏览器发小红书\n"
            "/hot [x|xhs|all] [题材] - 抓热点并一键发文\n"
            "/hotpost [x|xhs|all] [题材] - 抓热点并一键发文\n"
            "/ops bounty scan [关键词1,关键词2] - 扫描赏金线索\n"
            "/ops bounty run [关键词1,关键词2] - 自动评估ROI并止损筛选\n"
            "/ops bounty list [status] - 查看赏金线索\n"
            "/ops bounty top - 查看高ROI机会\n"
            "/ops bounty open [数量] - 自动打开高ROI机会链接\n"
            "/ops tweet plan <X链接或@账号> - 把推文转成执行计划\n"
            "/ops tweet run <X链接或@账号> - 按推文信号直接跑赚钱流程\n"
            "/ops tweet watch <X链接> - 从推文导入博主并监控更新\n"
            "/ops monitor add <关键词> - 新增监控\n"
            "/ops monitor addx <@账号或X链接> - 新增X博主监控\n"
            "/ops monitor list - 监控列表\n"
            "/ops monitor run - 立即扫描监控\n"
            "/ops life remind <分钟> <内容> - 生活提醒\n"
            "/ops life action <动作> [JSON] - 触发本机动作/设备Webhook\n"
            "/ops project [路径] - 项目协作周报\n"
            "/ops dev [路径] - 开发流程自动化\n"
            "/ops xianyu start|stop|status|reload - 闲鱼 AI 客服控制\n"
            "/publish <平台> <文件路径> [标题] - 社媒多平台发布 (抖音/B站/小红书/快手)"
        )

    # ---- 社媒多平台发布 (sau_bridge) ----

    async def handle_ops_menu_callback(self, update, context):
        """处理 /ops 交互菜单按钮回调"""
        query = update.callback_query
        await query.answer()

        # 认证: 仅授权用户可操作
        if not self._is_authorized(update.effective_user.id):
            await query.answer("⛔ 未授权操作", show_alert=True)
            return

        data = query.data
        if not data.startswith("ops_"):
            return

        # 映射按钮 callback_data → cmd_ops 子命令
        _OPS_MENU_MAP = {
            "ops_task": (["task", "top"], "📝 加载任务 Top3..."),
            "ops_project": (["project"], "📊 生成项目报告..."),
            "ops_hot": (None, None),  # 直接走 cmd_hotpost
            "ops_post": (None, None),  # 直接走 cmd_post
            "ops_email": (["email"], "📧 整理邮箱..."),
            "ops_meeting": (None, "📝 请发送: /ops meeting <会议文本>"),
            "ops_life": (["life", "remind"], "🏠 请发送: /ops life remind <分钟> <内容>"),
            "ops_bounty": (["bounty", "run"], "💰 启动赏金猎人..."),
            "ops_monitor": (["monitor", "list"], "📺 加载监控列表..."),
            "ops_dev": (["dev"], "🔧 启动开发流程..."),
        }

        entry = _OPS_MENU_MAP.get(data)
        if not entry:
            return

        args, hint = entry

        # 无参数提示型按钮 — 直接展示用法
        if args is None and hint is None:
            # 特殊路由
            if data == "ops_hot":
                await query.edit_message_text("🔥 抓取热点中...")
                context.args = []
                await self.cmd_hotpost(update, context)
            elif data == "ops_post":
                await query.edit_message_text("✍️ 准备发帖...")
                context.args = []
                await self.cmd_post(update, context)
            return

        if args is None:
            # 提示用户手动输入
            await query.edit_message_text(hint)
            return

        await query.edit_message_text(hint or "⏳ 执行中...")
        try:
            context.args = args
            await self.cmd_ops(update, context)
        except Exception as e:
            logger.warning("[OpsMenu] 执行 %s 失败: %s", data, e)

    # ---- 性能指标报告 ----

    @requires_auth
    @with_typing
    async def cmd_perf(self, update, context):
        """显示性能指标报告 — 展示所有被追踪函数的耗时统计"""
        try:
            from src.perf_metrics import get_tracker

            tracker = get_tracker()
            report = tracker.format_report()
            await send_long_message(update.effective_chat.id, report, context)
        except Exception as e:
            logger.warning("[cmd_perf] 执行失败: %s", e)
            try:
                await update.message.reply_text("⚠️ 获取性能指标失败，请稍后重试")
            except Exception as e:
                logger.debug("Telegram消息操作失败(用户可能已删除): %s", e)

    # ---- 进化引擎 Telegram 命令入口 ----

    @requires_auth
    @with_typing
    async def cmd_evolution(self, update, context):
        """触发进化引擎扫描 — 搜索 GitHub 高星开源项目，评估集成价值"""
        from src.bot.globals import send_long_message

        processing_msg = await update.message.reply_text("⏳ 进化引擎扫描中，预计 30-60 秒...")
        try:
            from src.evolution.engine import EvolutionEngine

            engine = EvolutionEngine()
            result = await engine.daily_scan()

            # 格式化扫描结果
            if not result or not result.get("proposals"):
                text = "🧬 <b>进化扫描完成</b>\n\n本次未发现新的高价值开源项目。"
            else:
                proposals = result["proposals"]
                lines = [f"🧬 <b>进化扫描完成</b> — 发现 {len(proposals)} 个候选项目\n"]
                for p in proposals[:5]:
                    name = p.get("repo_name", "未知")
                    stars = p.get("stars", 0)
                    value = p.get("value_score", 0)
                    desc = p.get("description", "")[:60]
                    lines.append(f"  ⭐ <b>{name}</b> ({stars:,}⭐)\n    价值: {value:.0f}/100 | {desc}")
                if len(proposals) > 5:
                    lines.append(f"\n  ... 还有 {len(proposals) - 5} 个，详见桌面端进化引擎页面")
                text = "\n".join(lines)

            await processing_msg.delete()
            await send_long_message(update.effective_chat.id, text, context, parse_mode="HTML")

        except Exception as e:
            logger.error("[Evolution] 扫描失败: %s", e, exc_info=True)
            await processing_msg.delete()
            await update.message.reply_text(f"❌ 进化扫描失败: {error_service_failed()}")

    # ---- 闲鱼卡券自动发货管理 ----
