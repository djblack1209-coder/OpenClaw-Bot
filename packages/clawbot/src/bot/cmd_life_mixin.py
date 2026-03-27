"""
Bot — 账单 / 比价 / 生活自动化 / 赏金猎人 命令 Mixin

包含功能:
  - 生活记账 (cmd_bill)
  - 比价监控 (cmd_pricewatch)
  - 生活自动化工作流 (_ops_life)
  - AI 赏金猎人 (_ops_bounty)
  - 推文执行流 (_ops_tweet)
"""

import asyncio
import json
import logging

from src.bot.globals import execution_hub, send_long_message
from src.bot.error_messages import error_service_failed
from src.bot.auth import requires_auth
from src.telegram_ux import with_typing

logger = logging.getLogger(__name__)


class LifeCommandsMixin:
    async def _ops_life(self, update, context, args):
        if not args:
            await update.message.reply_text("用法: /ops life remind|action")
            return
        sub = args[0].lower().strip()
        rest = args[1:]

        if sub == "remind":
            if len(rest) < 2:
                await update.message.reply_text("用法: /ops life remind <分钟> <提醒内容>")
                return
            try:
                minutes = int(rest[0])
            except Exception as e:  # noqa: F841
                await update.message.reply_text("分钟必须是数字")
                return
            message = " ".join(rest[1:]).strip()
            ret = await execution_hub.create_reminder(message=message, delay_minutes=minutes)
            if ret.get("success"):
                await update.message.reply_text(
                    f"提醒已创建: #{ret.get('reminder_id')}\n触发时间: {ret.get('trigger_at')}"
                )
            else:
                await update.message.reply_text(error_service_failed("创建", ret.get('error', '')))
            return

        if sub == "action":
            if not rest:
                await update.message.reply_text("用法: /ops life action <动作名> [JSON参数]")
                return
            action = rest[0]
            payload = {}
            if len(rest) > 1:
                raw = " ".join(rest[1:]).strip()
                if raw:
                    try:
                        payload = json.loads(raw)
                    except Exception as e:  # noqa: F841
                        payload = {"raw": raw}
            ret = await execution_hub.trigger_home_action(action=action, payload=payload)
            if ret.get("success"):
                lines = [f"动作已发送: {action}"]
                if ret.get("mode"):
                    lines.append(f"模式: {ret.get('mode')}")
                if ret.get("status_code") is not None:
                    lines.append(f"状态码: {ret.get('status_code')}")
                resp = (ret.get("response") or "").strip()
                if resp:
                    lines.append(f"响应: {resp[:120]}")
                await update.message.reply_text("\n".join(lines))
            else:
                await update.message.reply_text(f"动作失败: {ret.get('error', '未知错误')}")
            return

        await update.message.reply_text("未知 life 子命令，用法: remind|action")

    async def _ops_bounty(self, update, context, args):
        if not args:
            await update.message.reply_text("用法: /ops bounty scan|run|list|top|open")
            return
        sub = args[0].lower().strip()
        rest = args[1:]

        if sub == "scan":
            raw = " ".join(rest).strip()
            keywords = [x.strip() for x in raw.split(",") if x.strip()] if raw else []
            await update.message.reply_text("正在扫描全网 bounty 机会...")
            ret = await execution_hub.scan_bounties(keywords=keywords, per_query=8)
            saved = ret.get("saved", {})
            src = ret.get("sources", {})
            await update.message.reply_text(
                "赏金扫描完成\n"
                f"关键词: {', '.join(ret.get('keywords', [])) or '默认'}\n"
                f"GitHub: {src.get('github', 0)}\n"
                f"Web: {src.get('web', 0)}\n"
                f"入库: {saved.get('total', 0)} (新增{saved.get('inserted', 0)}/更新{saved.get('updated', 0)})"
            )
            return

        if sub in {"run", "hunt", "auto"}:
            raw = " ".join(rest).strip()
            keywords = [x.strip() for x in raw.split(",") if x.strip()] if raw else []
            await update.message.reply_text("正在执行 AI 赏金猎人流程（扫描 + ROI + 止损）...")
            ret = await execution_hub.run_bounty_hunter(keywords=keywords, shortlist_limit=5)
            lines = ["AI 赏金猎人结果", ""]
            lines.append(f"评估数量: {ret.get('evaluated', 0)}")
            lines.append(f"接受单数: {ret.get('accepted', 0)}")
            lines.append(f"拒绝单数: {ret.get('rejected', 0)}")
            lines.append(f"当日成本: ${ret.get('daily_cost_used', 0):.2f} / ${ret.get('daily_cost_cap', 0):.2f}")
            lines.append(f"最小ROI阈值: ${ret.get('min_roi', 0):.2f} | 最小信号分: {ret.get('min_signal', 0)}")
            allowed = ret.get("allowed_platforms", [])
            if allowed:
                lines.append(f"平台白名单: {', '.join(allowed)}")
            lines.append(f"要求明确赏金: {'是' if ret.get('require_explicit_reward') else '否'}")
            if ret.get("reused_shortlist"):
                lines.append("本次命中不足，已回退到最近已验证 shortlist")
            decision_stats = ret.get("decision_stats", {}) or {}
            if decision_stats:
                parts = [f"{k}:{v}" for k, v in decision_stats.items()]
                lines.append(f"拒绝原因: {' / '.join(parts[:6])}")

            shortlist = ret.get("shortlist", [])
            if shortlist:
                lines.append("\n候选Top:")
                for i, row in enumerate(shortlist[:5], 1):
                    roi = float(row.get("expected_roi_usd", 0) or 0)
                    lines.append(f"{i}. [{row.get('platform', 'web')}] ROI ${roi:.2f}")
                    lines.append(f"   {row.get('title', '')[:90]}")
                    lines.append(f"   {row.get('url', '')[:120]}")
            else:
                watchlist = ret.get("watchlist", [])
                if watchlist:
                    lines.append("\n观察列表:")
                    for i, row in enumerate(watchlist[:5], 1):
                        lines.append(f"{i}. [{row.get('reason', '未通过')}] {row.get('title', '')[:88]}")
                        lines.append(f"   {row.get('url', '')[:120]}")

            await send_long_message(update.effective_chat.id, "\n".join(lines), context)
            return

        if sub == "list":
            status = (rest[0].strip().lower() if rest else "")
            rows = await asyncio.to_thread(execution_hub.list_bounty_leads, status, 20)
            if not rows:
                await update.message.reply_text("当前没有赏金线索")
                return
            lines = [f"赏金线索列表{f' ({status})' if status else ''}", ""]
            for i, row in enumerate(rows[:20], 1):
                roi = float(row.get("expected_roi_usd", 0) or 0)
                reward = float(row.get("reward_usd", 0) or 0)
                lines.append(
                    f"{i}. #{row.get('id')} [{row.get('platform', 'web')}] [{row.get('status', 'new')}] ROI ${roi:.1f}"
                )
                lines.append(f"   奖励估算: ${reward:.1f} | {row.get('title', '')[:88]}")
            await send_long_message(update.effective_chat.id, "\n".join(lines), context)
            return

        if sub == "top":
            rows = await asyncio.to_thread(execution_hub.list_bounty_leads, "accepted", 10)
            if not rows:
                rows = await asyncio.to_thread(execution_hub.list_bounty_leads, "new", 10)
            if not rows:
                await update.message.reply_text("当前没有可用的赏金机会")
                return
            lines = ["赏金机会 Top", ""]
            for i, row in enumerate(rows[:10], 1):
                roi = float(row.get("expected_roi_usd", 0) or 0)
                lines.append(f"{i}. [{row.get('platform', 'web')}] ROI ${roi:.2f} | {row.get('title', '')[:75]}")
                lines.append(f"   {row.get('url', '')[:110]}")
            await send_long_message(update.effective_chat.id, "\n".join(lines), context)
            return

        if sub == "open":
            limit = 3
            if rest and rest[0].isdigit():
                limit = max(1, min(8, int(rest[0])))
            await update.message.reply_text(f"正在打开前 {limit} 个高ROI机会...")
            ret = await asyncio.to_thread(execution_hub.open_bounty_links, "accepted", limit)
            opened = ret.get("opened", [])
            failed = ret.get("failed", [])
            lines = ["赏金机会已打开", ""]
            lines.append(f"成功: {len(opened)}")
            lines.append(f"失败: {len(failed)}")
            for i, u in enumerate(opened[:8], 1):
                lines.append(f"{i}. {u[:120]}")
            if failed:
                lines.append("\n失败详情:")
                for f in failed[:3]:
                    lines.append(f"- {str(f.get('url', ''))[:90]} | {str(f.get('error', ''))[:80]}")
            await send_long_message(update.effective_chat.id, "\n".join(lines), context)
            return

        await update.message.reply_text("未知 bounty 子命令，用法: scan|run|list|top|open")

    async def _ops_tweet(self, update, context, args):
        if not args:
            await update.message.reply_text("用法: /ops tweet plan|run|watch <X链接或@账号>")
            return

        sub = args[0].lower().strip()
        rest = args[1:]
        if sub not in {"plan", "run", "watch"}:
            source = " ".join(args).strip() or "https://x.com/IndieDevHailey"
            sub = "run"
        else:
            source = " ".join(rest).strip() or "https://x.com/IndieDevHailey"

        if sub == "plan":
            await update.message.reply_text("正在抓取推文并生成执行计划...")
            ret = await execution_hub.analyze_tweet_execution(source)
            if not ret.get("success"):
                await update.message.reply_text(f"推文计划失败: {ret.get('error', '未知错误')}")
                return

            lines = ["推文执行计划", ""]
            lines.append(f"来源: {ret.get('source_url', '')}")
            lines.append(f"策略: {ret.get('strategy_name', '未知')}")
            keys = ret.get("keywords", [])
            if keys:
                lines.append(f"关键词: {', '.join(keys)}")
            lines.append(f"摘要: {str(ret.get('preview', '') or '')[:220]}")
            lines.append("")
            lines.append("执行步骤:")
            for i, step in enumerate(ret.get("plan", []), 1):
                lines.append(f"{i}. {step}")
            await send_long_message(update.effective_chat.id, "\n".join(lines), context)
            return

        if sub == "run":
            await update.message.reply_text("正在按推文信号执行赚钱流程...")
            ret = await execution_hub.run_tweet_execution(source)
            if not ret.get("success"):
                await update.message.reply_text(f"推文执行失败: {ret.get('error', '未知错误')}")
                return

            lines = ["推文执行结果", ""]
            lines.append(f"来源: {ret.get('source_url', '')}")
            lines.append(f"策略: {ret.get('strategy_name', '未知')}")
            keys = ret.get("keywords", [])
            if keys:
                lines.append(f"关键词: {', '.join(keys)}")
            lines.append(f"抓取摘要: {str(ret.get('preview', '') or '')[:220]}")

            bounty = ret.get("bounty") or {}
            if bounty:
                lines.append("")
                lines.append(f"评估数量: {bounty.get('evaluated', 0)}")
                lines.append(f"接受单数: {bounty.get('accepted', 0)}")
                lines.append(f"拒绝单数: {bounty.get('rejected', 0)}")
                lines.append(f"当日成本: ${bounty.get('daily_cost_used', 0):.2f} / ${bounty.get('daily_cost_cap', 0):.2f}")
                lines.append(f"最小ROI: ${bounty.get('min_roi', 0):.2f} | 最小信号分: {bounty.get('min_signal', 0)}")
                if bounty.get("reused_shortlist"):
                    lines.append("本次命中不足，已回退到最近已验证 shortlist")

                decision_stats = bounty.get("decision_stats", {}) or {}
                if decision_stats:
                    parts = [f"{k}:{v}" for k, v in decision_stats.items()]
                    lines.append(f"拒绝原因: {' / '.join(parts[:6])}")

                shortlist = bounty.get("shortlist", [])
                watchlist = bounty.get("watchlist", [])
                if shortlist:
                    lines.append("")
                    lines.append("赚钱 shortlist:")
                    for i, row in enumerate(shortlist[:3], 1):
                        lines.append(
                            f"{i}. ROI ${float(row.get('expected_roi_usd', 0) or 0):.2f} | 奖励 ${float(row.get('reward_usd', 0) or 0):.2f}"
                        )
                        lines.append(f"   {row.get('title', '')[:90]}")
                        lines.append(f"   {row.get('url', '')[:120]}")
                elif watchlist:
                    lines.append("")
                    lines.append("观察列表:")
                    for i, row in enumerate(watchlist[:3], 1):
                        lines.append(f"{i}. {row.get('reason', '未通过')} | {row.get('title', '')[:88]}")
                        lines.append(f"   {row.get('url', '')[:120]}")

            await send_long_message(update.effective_chat.id, "\n".join(lines), context)
            return

        if sub == "watch":
            await update.message.reply_text("正在从推文提取博主并建立X监控...")
            ret = await execution_hub.import_x_monitors_from_tweet(source)
            if not ret.get("success"):
                await update.message.reply_text(f"推文监控导入失败: {ret.get('error', '未知错误')}")
                return

            lines = ["推文监控导入结果", ""]
            lines.append(f"来源: {ret.get('source_url', '')}")
            lines.append(f"新增监控: {ret.get('count', 0)}")
            note = str(ret.get('note', '') or '').strip()
            if note:
                lines.append(f"说明: {note}")
            handles = ret.get("added", []) or ret.get("handles", []) or []
            if handles:
                lines.append("")
                lines.append("Handle 列表:")
                for i, handle in enumerate(handles[:20], 1):
                    lines.append(f"{i}. @{handle}")
            await send_long_message(update.effective_chat.id, "\n".join(lines), context)
            return

        await update.message.reply_text("未知 tweet 子命令，用法: plan|run|watch")

    # ---- 生活账单追踪 (话费/水电费余额检测提醒) ----

    @requires_auth
    @with_typing
    async def cmd_bill(self, update, context):
        """生活账单管理 — 话费/水电费余额追踪与低余额提醒

        用法:
        /bill add 话费 移动138xxx 30    — 添加追踪，低于30元提醒
        /bill update 1 45.5             — 更新第1个账单余额为45.5元
        /bill list                      — 查看我的账单列表
        /bill remove 2                  — 删除第2个追踪
        """
        import time as _time
        from src.execution.life_automation import (
            add_bill_account, update_bill_balance, list_bill_accounts,
            remove_bill_account, resolve_bill_type,
            BILL_TYPE_EMOJI, BILL_TYPE_LABEL,
        )

        user = update.effective_user
        chat_id = update.effective_chat.id if update.effective_chat else 0
        args = context.args or []
        sub = args[0].lower() if args else "list"

        # ── /bill list — 账单列表 ──
        if sub in {"list", "列表", "ls"}:
            accounts = list_bill_accounts(user.id)
            if not accounts:
                await update.message.reply_text(
                    "📋 还没有追踪任何账单\n\n"
                    "快速添加:\n"
                    "  /bill add 话费 移动138xxx 30\n"
                    "  /bill add 电费 南方电网 50\n\n"
                    "也可以直接说中文:\n"
                    "  「帮我盯着话费，低于30块提醒我」"
                )
                return
            lines = ["📱 我的账单追踪", "━━━━━━━━━━━━━━━"]
            for idx, acct in enumerate(accounts, 1):
                emoji = BILL_TYPE_EMOJI.get(acct["account_type"], "📄")
                label = BILL_TYPE_LABEL.get(acct["account_type"], acct["account_type"])
                name_part = f" — {acct['account_name']}" if acct.get("account_name") else ""
                # 余额显示
                balance = acct["balance"]
                threshold = acct["low_threshold"]
                is_low = balance <= threshold and acct.get("last_updated", 0) > 0
                balance_str = f"¥{balance:.1f}"
                if is_low:
                    balance_str += " ‼️ 低于阈值!"
                # 更新时间
                last_updated = acct.get("last_updated", 0)
                if last_updated > 0:
                    days_ago = int((_time.time() - last_updated) / 86400)
                    if days_ago == 0:
                        time_str = "今天"
                    elif days_ago == 1:
                        time_str = "1天前"
                    else:
                        time_str = f"{days_ago}天前"
                else:
                    time_str = "未更新"
                lines.append(f"\n{idx}. {emoji} {label}{name_part}")
                lines.append(f"   💰 余额: {balance_str} | ⚠️ 阈值: ¥{threshold:.0f}")
                lines.append(f"   📅 上次更新: {time_str}")
                if acct.get("remind_day", 0) > 0:
                    lines.append(f"   🔔 每月{acct['remind_day']}号提醒查询")
            await send_long_message(update.effective_chat.id, "\n".join(lines), context)
            return

        # ── /bill add <类型> [名称] [阈值] [每月提醒日] ──
        if sub in {"add", "添加", "新增"}:
            if len(args) < 2:
                await update.message.reply_text(
                    "用法: /bill add <类型> [名称] [阈值]\n\n"
                    "类型: 话费/电费/水费/燃气费/宽带\n"
                    "示例:\n"
                    "  /bill add 话费 移动138xxx 30\n"
                    "  /bill add 电费 南方电网 50 15"
                )
                return
            raw_type = args[1]
            account_type = resolve_bill_type(raw_type)
            if not account_type:
                await update.message.reply_text(
                    f"❌ 不认识「{raw_type}」\n"
                    "支持: 话费/电费/水费/燃气费/宽带"
                )
                return
            account_name = ""
            threshold = 30
            remind_day = 0
            # 解析后续参数: 名称(非数字) 阈值(数字) 提醒日(数字)
            remaining = args[2:]
            numbers_found = []
            names_found = []
            for a in remaining:
                try:
                    numbers_found.append(float(a))
                except ValueError as e:  # noqa: F841
                    names_found.append(a)
            if names_found:
                account_name = " ".join(names_found)
            if len(numbers_found) >= 1:
                threshold = numbers_found[0]
            if len(numbers_found) >= 2:
                remind_day = int(numbers_found[1])
            result = add_bill_account(
                user_id=user.id, chat_id=chat_id,
                account_type=account_type, account_name=account_name,
                low_threshold=threshold, remind_day=remind_day,
            )
            if result.get("success"):
                emoji = BILL_TYPE_EMOJI.get(account_type, "📄")
                label = BILL_TYPE_LABEL.get(account_type, account_type)
                msg = (
                    f"✅ 账单追踪已添加\n\n"
                    f"{emoji} {label}"
                    f"{' — ' + account_name if account_name else ''}\n"
                    f"⚠️ 低于 ¥{threshold:.0f} 时提醒\n"
                )
                if remind_day > 0:
                    msg += f"🔔 每月{remind_day}号提醒查询\n"
                msg += f"\n💡 说「{label}还剩xx块」可更新余额"
                await update.message.reply_text(msg)
            else:
                await update.message.reply_text(f"❌ {result.get('error', '添加失败')}")
            return

        # ── /bill update <ID> <余额> ──
        if sub in {"update", "更新", "set"}:
            if len(args) < 3:
                await update.message.reply_text("用法: /bill update <编号> <余额>\n示例: /bill update 1 45.5")
                return
            try:
                acct_id = int(args[1])
                balance = float(args[2])
            except (ValueError, IndexError) as e:  # noqa: F841
                await update.message.reply_text("❌ 格式错误，示例: /bill update 1 45.5")
                return
            # 通过列表序号查找真实 ID
            accounts = list_bill_accounts(user.id)
            if acct_id < 1 or acct_id > len(accounts):
                await update.message.reply_text(f"❌ 编号 {acct_id} 不存在，先用 /bill list 查看")
                return
            real_id = accounts[acct_id - 1]["id"]
            result = update_bill_balance(real_id, balance, user_id=user.id)
            if result.get("success"):
                emoji = BILL_TYPE_EMOJI.get(result["account_type"], "📄")
                label = BILL_TYPE_LABEL.get(result["account_type"], result["account_type"])
                name = result.get("account_name", "")
                msg = f"✅ 余额已更新\n\n{emoji} {label}"
                if name:
                    msg += f" — {name}"
                msg += f"\n💰 余额: ¥{result['balance']:.1f}"
                if result.get("is_low"):
                    msg += f"\n⚠️ 低于阈值 ¥{result['threshold']:.0f}，请注意充值！"
                    # 发布 BILL_DUE 事件
                    try:
                        from src.core.event_bus import get_event_bus, EventType
                        import asyncio
                        bus = get_event_bus()
                        asyncio.ensure_future(bus.publish(
                            EventType.BILL_DUE,
                            {
                                "user_id": str(user.id), "chat_id": str(chat_id),
                                "account_type": result["account_type"],
                                "account_name": name,
                                "balance": result["balance"],
                                "threshold": result["threshold"],
                            },
                            source="cmd_bill",
                        ))
                    except Exception as e:
                        logger.debug("Silenced exception", exc_info=True)
                await update.message.reply_text(msg)
            else:
                await update.message.reply_text(f"❌ {result.get('error', '更新失败')}")
            return

        # ── /bill remove <ID> ──
        if sub in {"remove", "删除", "rm", "del"}:
            if len(args) < 2:
                await update.message.reply_text("用法: /bill remove <编号>\n示例: /bill remove 2")
                return
            try:
                acct_id = int(args[1])
            except ValueError as e:  # noqa: F841
                await update.message.reply_text("❌ 编号必须是数字")
                return
            accounts = list_bill_accounts(user.id)
            if acct_id < 1 or acct_id > len(accounts):
                await update.message.reply_text(f"❌ 编号 {acct_id} 不存在")
                return
            real_id = accounts[acct_id - 1]["id"]
            acct = accounts[acct_id - 1]
            if remove_bill_account(real_id, user.id):
                emoji = BILL_TYPE_EMOJI.get(acct["account_type"], "📄")
                label = BILL_TYPE_LABEL.get(acct["account_type"], acct["account_type"])
                await update.message.reply_text(f"✅ 已删除 {emoji} {label} 的追踪")
            else:
                await update.message.reply_text("❌ 删除失败")
            return

        # ── 未知子命令 ──
        await update.message.reply_text(
            "📱 账单管理\n\n"
            "/bill list          — 查看追踪列表\n"
            "/bill add 话费 名称 30  — 添加追踪\n"
            "/bill update 1 45.5 — 更新余额\n"
            "/bill remove 2      — 删除追踪\n\n"
            "也可以直接说中文:\n"
            "「话费还剩30块」→ 自动更新余额\n"
            "「帮我盯着电费」→ 添加追踪"
        )

    @requires_auth
    @with_typing
    async def cmd_pricewatch(self, update, context):
        """降价提醒管理

        用法:
        /pricewatch add AirPods Pro 800  — 盯着这个商品，降到800通知我
        /pricewatch list               — 查看我的监控列表
        /pricewatch remove 3           — 删除第3个监控
        """
        from src.execution.life_automation import (
            add_price_watch, list_price_watches, remove_price_watch,
        )

        user = update.effective_user
        user_id = user.id
        chat_id = update.effective_chat.id
        args = context.args or []
        sub = args[0].lower() if args else "help"

        # ── 帮助 ──
        if sub in ("help", "帮助", "h"):
            help_text = (
                "🔔 降价提醒管理\n\n"
                "子命令:\n"
                "  /pricewatch add <商品> <目标价>  — 添加监控\n"
                "  /pricewatch list               — 我的监控\n"
                "  /pricewatch remove <编号>       — 删除监控\n\n"
                "示例:\n"
                "  /pricewatch add AirPods Pro 800\n"
                "  /pricewatch add iPhone 16 5000\n\n"
                "也可以直接说:\n"
                "  「帮我盯着AirPods，降到800告诉我」\n"
                "  「AirPods降价提醒 800」\n\n"
                f"📌 每人最多 10 个监控，每 6 小时检查一次"
            )
            await update.message.reply_text(help_text)
            return

        # ── 添加监控 ──
        if sub in ("add", "添加", "盯着", "a"):
            if len(args) < 3:
                await update.message.reply_text(
                    "❓ 用法: /pricewatch add <商品关键词> <目标价>\n"
                    "例: /pricewatch add AirPods Pro 800"
                )
                return
            # 最后一个参数是目标价，前面的都是商品关键词
            try:
                target_price = float(args[-1])
            except ValueError as e:  # noqa: F841
                await update.message.reply_text("❓ 最后一个参数必须是目标价格（数字）")
                return
            keyword = " ".join(args[1:-1])
            if not keyword:
                await update.message.reply_text("❓ 请输入商品关键词")
                return

            result = add_price_watch(user_id, chat_id, keyword, target_price)
            if result.get("success"):
                await update.message.reply_text(
                    f"✅ 降价监控已添加！\n\n"
                    f"📦 商品: {keyword}\n"
                    f"🎯 目标价: ¥{target_price}\n"
                    f"🔔 降到这个价格会自动通知你\n"
                    f"⏰ 每 6 小时检查一次\n\n"
                    f"💡 发送 /pricewatch list 查看所有监控"
                )
            else:
                await update.message.reply_text(
                    f"⚠️ 添加失败: {result.get('error', '未知错误')}"
                )
            return

        # ── 列表 ──
        if sub in ("list", "列表", "ls", "l"):
            watches = list_price_watches(user_id)
            if not watches:
                await update.message.reply_text(
                    "📋 暂无降价监控\n\n"
                    "发送 /pricewatch add <商品> <目标价> 开始监控\n"
                    "或直接说：帮我盯着AirPods，降到800告诉我"
                )
                return
            lines = ["🔔 我的降价监控:\n"]
            for i, w in enumerate(watches, 1):
                status_icon = "🟢" if w["status"] == "active" else "⏸️"
                price_info = ""
                if w["current_price"] > 0:
                    price_info = f"  当前 ¥{w['current_price']}"
                    if w["lowest_price"] > 0:
                        price_info += f" | 最低 ¥{w['lowest_price']}"
                lines.append(
                    f"{status_icon} #{w['id']} {w['keyword']}\n"
                    f"  🎯 目标价 ¥{w['target_price']}{price_info}"
                )
            lines.append(f"\n💡 /pricewatch remove <编号> 删除监控")
            await update.message.reply_text("\n".join(lines))
            return

        # ── 删除 ──
        if sub in ("remove", "delete", "rm", "del", "删除"):
            if len(args) < 2:
                await update.message.reply_text("❓ 请指定监控编号: /pricewatch remove 3")
                return
            try:
                watch_id = int(args[1])
            except ValueError as e:  # noqa: F841
                await update.message.reply_text("❓ 编号必须是数字")
                return
            if remove_price_watch(watch_id, user_id):
                await update.message.reply_text(f"✅ 监控 #{watch_id} 已删除")
            else:
                await update.message.reply_text(f"❌ 删除失败 — 编号不存在或无权限")
            return

        await update.message.reply_text(
            f"❓ 未知子命令: {sub}\n发送 /pricewatch help 查看帮助"
        )
