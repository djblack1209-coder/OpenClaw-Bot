# nlp_dispatch_handlers.py — 中文 NLP 分发处理器
# 从 chinese_nlp_mixin.py 拆分 (HI-358)
# 每个 handler 是独立的 async 函数，接收 (mixin, update, context, action_arg)
# mixin 是 ChineseNLPMixin 实例，用于调用 self.cmd_xxx

import logging

logger = logging.getLogger(__name__)


# ── 快递查询 ──────────────────────────────────────────────
async def handle_express(mixin, update, context, action_arg):
    """快递单号查询"""
    try:
        from src.tools.free_apis import query_express
        result = await query_express(action_arg)
        await update.message.reply_text(result if isinstance(result, str) else str(result))
    except ImportError:
        await update.message.reply_text("快递查询功能暂未配置")
    except Exception:
        await update.message.reply_text("查询失败，请稍后再试")


# ── 记账系统 ──────────────────────────────────────────────
async def handle_expense_add(mixin, update, context, action_arg):
    """记录一笔支出"""
    user = update.effective_user
    chat_id = update.effective_chat.id if update.effective_chat else 0
    parts = action_arg.split("|||", 1)
    amount = float(parts[0])
    note = parts[1] if len(parts) > 1 else ""
    from src.execution.life_automation import add_expense
    result = add_expense(user.id, amount, note, chat_id=chat_id)
    if result.get("success"):
        await update.message.reply_text(
            f"✅ 已记录: ¥{amount} {note}\n💡 说「我的账单」查看汇总"
        )
    else:
        await update.message.reply_text("记账失败，请稍后再试")


async def handle_expense_summary(mixin, update, context, action_arg):
    """查看支出汇总"""
    user = update.effective_user
    from src.execution.life_automation import get_expense_summary
    summary = get_expense_summary(user.id)
    if not summary.get("success") or summary.get("total_count", 0) == 0:
        await update.message.reply_text("📊 还没有记录，试试说「午饭 35」开始记账")
        return
    lines = [f"📊 近{summary['days']}天支出 | 共 ¥{summary['total_amount']}"]
    if summary.get("categories"):
        lines.append("")
        for cat in summary["categories"][:5]:
            lines.append(f"  {cat['name']}: ¥{cat['amount']} ({cat['count']}笔)")
    if summary.get("recent"):
        lines.append("\n📝 最近记录:")
        for r in summary["recent"]:
            lines.append(f"  {r['time']} ¥{r['amount']} {r['note']}")
    await update.message.reply_text("\n".join(lines))


async def handle_expense_undo(mixin, update, context, action_arg):
    """撤销最近一笔记账"""
    user = update.effective_user
    from src.execution.life_automation import delete_last_expense
    if delete_last_expense(user.id):
        await update.message.reply_text("✅ 已删除最近一笔记录")
    else:
        await update.message.reply_text("没有可删除的记录")


# ── 导出记账/闲鱼 ──────────────────────────────────────────
async def handle_export_expenses(mixin, update, context, action_arg):
    """导出记账数据"""
    context.args = ["expenses", action_arg]
    await mixin.cmd_export(update, context)


async def handle_export_xianyu(mixin, update, context, action_arg):
    """导出闲鱼订单数据"""
    context.args = ["xianyu", action_arg]
    await mixin.cmd_export(update, context)


# ── 收入记录 ──────────────────────────────────────────────
async def handle_income_add(mixin, update, context, action_arg):
    """记录一笔收入"""
    user = update.effective_user
    chat_id = update.effective_chat.id if update.effective_chat else 0
    parts = action_arg.split("|||", 1)
    amount = float(parts[0])
    note = parts[1] if len(parts) > 1 else ""
    from src.execution.life_automation import add_income
    result = add_income(user.id, amount, note, chat_id=chat_id)
    if result.get("success"):
        cat = result.get("category", "其他")
        await update.message.reply_text(
            f"✅ 已记录收入: ¥{amount} {note}\n"
            f"📂 分类: {cat}\n"
            f"💡 说「本月账单」查看月度报告"
        )
    else:
        await update.message.reply_text(
            result.get("error", "收入记录失败，请稍后再试")
        )


# ── 月预算 ──────────────────────────────────────────────
async def handle_budget_set(mixin, update, context, action_arg):
    """设定月预算"""
    user = update.effective_user
    budget = float(action_arg)
    from src.execution.life_automation import set_monthly_budget
    result = set_monthly_budget(user.id, budget)
    if result.get("success"):
        await update.message.reply_text(
            f"✅ 月预算已设为 ¥{budget:,.0f}\n"
            f"💡 每天 20:00 自动检查超支情况"
        )
    else:
        await update.message.reply_text(
            result.get("error", "设定预算失败")
        )


# ── 月度财务汇总 ──────────────────────────────────────────
async def handle_monthly_summary(mixin, update, context, action_arg):
    """月度收支报告"""
    user = update.effective_user
    from src.execution.life_automation import (
        format_monthly_report,
        get_monthly_summary,
    )
    # 解析月份参数
    year_month = None
    if action_arg:
        from datetime import datetime as _dt
        try:
            month_num = int(action_arg)
            year = _dt.now().year
            year_month = f"{year}-{month_num:02d}"
        except (ValueError, TypeError):
            year_month = None
    summary = get_monthly_summary(user.id, year_month=year_month)
    if not summary.get("success") or (
        summary.get("total_expense", 0) == 0 and
        summary.get("total_income", 0) == 0
    ):
        await update.message.reply_text(
            "📊 本月还没有收支记录\n"
            "💡 试试说「午饭 35」记支出，「收入5000」记收入"
        )
        return
    report = format_monthly_report(summary)
    await update.message.reply_text(report)


# ── 预算检查 ──────────────────────────────────────────────
async def handle_budget_check(mixin, update, context, action_arg):
    """查看预算剩余情况"""
    user = update.effective_user
    from src.execution.life_automation import check_budget_alert
    is_over, msg = check_budget_alert(user.id)
    await update.message.reply_text(msg)


# ── 账单追踪 NLP ──────────────────────────────────────────
async def handle_bill_update_nlp(mixin, update, context, action_arg):
    """自然语言更新账单余额: '话费还剩30块'"""
    user = update.effective_user
    chat_id = update.effective_chat.id if update.effective_chat else 0
    parts = action_arg.split("|||", 1)
    bill_type_cn = parts[0]
    balance = float(parts[1]) if len(parts) > 1 else 0
    from src.execution.life_automation import (
        BILL_TYPE_EMOJI,
        BILL_TYPE_LABEL,
        add_bill_account,
        find_bill_by_type,
        resolve_bill_type,
        update_bill_balance,
    )
    acct_type = resolve_bill_type(bill_type_cn)
    if not acct_type:
        await update.message.reply_text(f"❌ 不认识「{bill_type_cn}」类型")
        return
    # 查找已有追踪
    existing = find_bill_by_type(user.id, acct_type)
    if existing:
        result = update_bill_balance(existing["id"], balance, user_id=user.id)
        if result.get("success"):
            emoji = BILL_TYPE_EMOJI.get(acct_type, "📄")
            label = BILL_TYPE_LABEL.get(acct_type, acct_type)
            msg = f"✅ {emoji} {label}余额已更新: ¥{balance:.1f}"
            if result.get("is_low"):
                msg += f"\n⚠️ 低于阈值 ¥{result['threshold']:.0f}，请注意充值！"
                # 发布 BILL_DUE 事件
                try:
                    import asyncio

                    from src.core.event_bus import EventType, get_event_bus
                    bus = get_event_bus()
                    asyncio.ensure_future(bus.publish(
                        EventType.BILL_DUE,
                        {
                            "user_id": str(user.id), "chat_id": str(chat_id),
                            "account_type": acct_type,
                            "account_name": existing.get("account_name", ""),
                            "balance": balance,
                            "threshold": result["threshold"],
                        },
                        source="nlp_bill_update",
                    ))
                except Exception as e:
                    logger.debug("静默异常: %s", e)
            await update.message.reply_text(msg)
        else:
            await update.message.reply_text(f"❌ 更新失败: {result.get('error', '')}")
    else:
        # 没有追踪，自动创建一个
        result = add_bill_account(
            user_id=user.id, chat_id=chat_id,
            account_type=acct_type, low_threshold=30,
        )
        if result.get("success"):
            update_bill_balance(result["account_id"], balance, user_id=user.id)
            emoji = BILL_TYPE_EMOJI.get(acct_type, "📄")
            label = BILL_TYPE_LABEL.get(acct_type, acct_type)
            await update.message.reply_text(
                f"✅ 自动创建了{emoji} {label}追踪，余额: ¥{balance:.1f}\n"
                f"⚠️ 默认低于 ¥30 提醒，可用 /bill 调整"
            )
        else:
            await update.message.reply_text(f"❌ {result.get('error', '失败')}")


async def handle_bill_add_nlp(mixin, update, context, action_arg):
    """自然语言添加账单追踪: '帮我盯着话费'"""
    user = update.effective_user
    chat_id = update.effective_chat.id if update.effective_chat else 0
    parts = action_arg.split("|||", 1)
    bill_type_cn = parts[0]
    threshold = float(parts[1]) if len(parts) > 1 else 30
    from src.execution.life_automation import (
        BILL_TYPE_EMOJI,
        BILL_TYPE_LABEL,
        add_bill_account,
        resolve_bill_type,
    )
    acct_type = resolve_bill_type(bill_type_cn)
    if not acct_type:
        await update.message.reply_text(f"❌ 不认识「{bill_type_cn}」类型")
        return
    result = add_bill_account(
        user_id=user.id, chat_id=chat_id,
        account_type=acct_type, low_threshold=threshold,
    )
    if result.get("success"):
        emoji = BILL_TYPE_EMOJI.get(acct_type, "📄")
        label = BILL_TYPE_LABEL.get(acct_type, acct_type)
        await update.message.reply_text(
            f"✅ {emoji} {label}追踪已添加\n"
            f"⚠️ 低于 ¥{threshold:.0f} 时提醒\n\n"
            f"💡 说「{label}还剩xx块」可更新余额"
        )
    else:
        await update.message.reply_text(f"❌ {result.get('error', '添加失败')}")


async def handle_bill_query(mixin, update, context, action_arg):
    """查询指定类型账单余额: '查话费'"""
    user = update.effective_user
    from src.execution.life_automation import (
        BILL_TYPE_EMOJI,
        BILL_TYPE_LABEL,
        find_bill_by_type,
        resolve_bill_type,
    )
    acct_type = resolve_bill_type(action_arg)
    if not acct_type:
        await update.message.reply_text(f"❌ 不认识「{action_arg}」类型")
        return
    existing = find_bill_by_type(user.id, acct_type)
    emoji = BILL_TYPE_EMOJI.get(acct_type, "📄")
    label = BILL_TYPE_LABEL.get(acct_type, acct_type)
    if existing:
        balance = existing["balance"]
        is_low = balance <= existing["low_threshold"]
        msg = f"{emoji} {label}余额: ¥{balance:.1f}"
        if is_low:
            msg += " ⚠️ 低于阈值!"
        msg += f"\n💡 说「{label}还剩xx块」可更新"
        await update.message.reply_text(msg)
    else:
        await update.message.reply_text(
            f"📋 还没有追踪{emoji} {label}\n\n"
            f"说「帮我盯着{label}」添加追踪"
        )


async def handle_bill_tips(mixin, update, context, action_arg):
    """账单优惠查询: '话费怎么充最划算'"""
    from src.execution.life_automation import resolve_bill_type
    acct_type = resolve_bill_type(action_arg) if action_arg else ""
    if acct_type:
        context.args = ["tips", action_arg]
    else:
        context.args = ["tips"]
    await mixin.cmd_bill(update, context)


async def handle_bill_predict(mixin, update, context, action_arg):
    """账单消耗预测: '话费还能用多久'"""
    context.args = ["predict"]
    await mixin.cmd_bill(update, context)


# ── 提醒系统 v2.0 ──────────────────────────────────────────
async def handle_ops_life_remind(mixin, update, context, action_arg):
    """提醒系统: 列表/取消/重复/自然语言时间/经典延迟"""
    from src.execution.life_automation import cancel_reminder, create_reminder, list_reminders
    chat_id = update.effective_chat.id if update.effective_chat else 0
    parts = action_arg.split("|||") if action_arg else []
    reply = ""

    if action_arg == "list":
        # 列出所有待触发的提醒
        reminders = list_reminders(status="pending")
        if not reminders:
            reply = "📋 暂无待触发的提醒"
        else:
            lines = ["📋 待触发的提醒:"]
            for r in reminders:
                lines.append(f"  #{r['id']} — {r['message']} (⏰ {r['remind_at'][:16]})")
            reply = "\n".join(lines)

    elif parts[0] == "cancel" and len(parts) >= 2:
        rid = int(parts[1])
        ok = cancel_reminder(rid)
        reply = f"✅ 提醒 #{rid} 已取消" if ok else "❌ 取消失败"

    elif parts[0] == "recur" and len(parts) >= 4:
        rule, time_part, content = parts[1], parts[2], parts[3]
        result = await create_reminder(
            message=content,
            time_text=time_part or None,
            recurrence_rule=rule,
            user_chat_id=chat_id,
        )
        if result.get("success"):
            reply = f"✅ 重复提醒已设置:\n📝 {content}\n🔄 {rule}\n⏰ 首次: {result['display']}"
        else:
            reply = f"❌ 设置失败: {result.get('error', '未知错误')}"

    elif parts[0] == "time" and len(parts) >= 3:
        time_text, content = parts[1], parts[2]
        result = await create_reminder(
            message=content,
            time_text=time_text,
            user_chat_id=chat_id,
        )
        if result.get("success"):
            reply = f"✅ 提醒已设置:\n📝 {content}\n⏰ {result['display']}"
        else:
            reply = f"❌ 设置失败: {result.get('error', '未知错误')}"

    else:
        # 兼容旧格式: "30|||开会"
        delay = int(parts[0]) if parts and parts[0].isdigit() else 30
        content = parts[1] if len(parts) > 1 else action_arg
        result = await create_reminder(
            message=content,
            delay_minutes=delay,
            user_chat_id=chat_id,
        )
        if result.get("success"):
            reply = f"✅ 提醒已设置:\n📝 {content}\n⏰ {result['display']}"
        else:
            reply = f"❌ 设置失败: {result.get('error', '未知错误')}"

    if reply and update.effective_message:
        await update.effective_message.reply_text(reply)


# ── Ops 子命令路由 ──────────────────────────────────────────
# 这些 action 只是设置 context.args 后调用 mixin.cmd_ops

_OPS_ARGS_MAP: dict[str, list[str]] = {
    "ops_email": ["email"],
    "ops_task_top": ["task", "top"],
    "ops_bounty_run": ["bounty", "run"],
    "ops_bounty_list": ["bounty", "list"],
    "ops_bounty_top": ["bounty", "top"],
    "ops_bounty_open": ["bounty", "open"],
    "ops_monitor_list": ["monitor", "list"],
    "ops_monitor_run": ["monitor", "run"],
}

# 带 action_arg 拼接的 ops 子命令
_OPS_ARGS_WITH_ARG_MAP: dict[str, list[str]] = {
    "ops_bounty_scan": ["bounty", "scan"],
    "ops_tweet_plan": ["tweet", "plan"],
    "ops_tweet_run": ["tweet", "run"],
    "ops_docs_search": ["docs", "search"],
    "ops_docs_index": ["docs", "index"],
    "ops_monitor_add": ["monitor", "add"],
}

# 可选 action_arg 的 ops 子命令
_OPS_ARGS_OPTIONAL_MAP: dict[str, str] = {
    "ops_meeting": "meeting",
    "ops_content": "content",
    "ops_project": "project",
    "ops_dev": "dev",
}


async def handle_ops_route(mixin, update, context, action_type, action_arg):
    """通用 ops 子命令路由，返回 True 表示已处理"""
    # 固定参数的 ops 子命令
    if action_type in _OPS_ARGS_MAP:
        context.args = _OPS_ARGS_MAP[action_type]
        await mixin.cmd_ops(update, context)
        return True
    # 需要拼接 action_arg 的 ops 子命令
    if action_type in _OPS_ARGS_WITH_ARG_MAP:
        base = _OPS_ARGS_WITH_ARG_MAP[action_type]
        context.args = base + ([action_arg] if action_arg else [])
        await mixin.cmd_ops(update, context)
        return True
    # 可选 action_arg 的 ops 子命令
    if action_type in _OPS_ARGS_OPTIONAL_MAP:
        sub = _OPS_ARGS_OPTIONAL_MAP[action_type]
        context.args = [sub, action_arg] if action_arg else [sub]
        await mixin.cmd_ops(update, context)
        return True
    return False


# ── 闲鱼风格/FAQ ──────────────────────────────────────────
async def handle_xianyu_style_show(mixin, update, context, action_arg):
    """显示闲鱼回复风格"""
    context.args = ["show"]
    await mixin.cmd_xianyu_style(update, context)


async def handle_xianyu_style_faq_list(mixin, update, context, action_arg):
    """列出闲鱼常见问题"""
    context.args = ["faq", "list"]
    await mixin.cmd_xianyu_style(update, context)


# ── 自动交易 ──────────────────────────────────────────────
async def handle_autotrader_start(mixin, update, context, action_arg):
    """启动自动交易"""
    context.args = ["start"]
    await mixin.cmd_autotrader(update, context)


async def handle_autotrader_stop(mixin, update, context, action_arg):
    """停止自动交易"""
    context.args = ["stop"]
    await mixin.cmd_autotrader(update, context)


# ── 自然语言交易 ──────────────────────────────────────────
async def handle_buy(mixin, update, context, action_arg):
    """自然语言买入: '帮我买100股苹果'"""
    context.args = action_arg.split() if action_arg else []
    await mixin.cmd_buy(update, context)


async def handle_sell(mixin, update, context, action_arg):
    """自然语言卖出: '卖掉AAPL'"""
    context.args = action_arg.split() if action_arg else []
    await mixin.cmd_sell(update, context)


# ── 自然语言购物 ──────────────────────────────────────────
async def handle_smart_shop(mixin, update, context, action_arg):
    """自然语言购物比价: '帮我找便宜的AirPods'"""
    await mixin._cmd_smart_shop(update, context, product=action_arg)


# ── 降价监控 ──────────────────────────────────────────────
async def handle_pricewatch_add(mixin, update, context, action_arg):
    """添加降价监控: '帮我盯着AirPods，降到800告诉我'"""
    parts = action_arg.split("|||", 1)
    if len(parts) == 2:
        keyword, price = parts[0].strip(), parts[1].strip()
        context.args = ["add"] + keyword.split() + [price]
        await mixin.cmd_pricewatch(update, context)
    else:
        await update.message.reply_text(
            "❓ 格式不对，试试: 帮我盯着AirPods，降到800告诉我"
        )


# ── 模糊建议 ──────────────────────────────────────────────
async def handle_suggest(mixin, update, context, action_arg):
    """'你是不是想说…' 模糊命令建议"""
    parts = action_arg.split("|||")
    if len(parts) == 3:
        suggested_action, keyword, label = parts
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton(f"✅ {label}", callback_data=f"nlp:{suggested_action}"),
        ]])
        await update.message.reply_text(
            f"你是不是想说「{keyword}」？",
            reply_markup=keyboard,
        )


# ── 统一分发入口 ──────────────────────────────────────────
# action_type → handler 映射表
_SPECIAL_HANDLERS: dict[str, object] = {
    "express": handle_express,
    "expense_add": handle_expense_add,
    "expense_summary": handle_expense_summary,
    "expense_undo": handle_expense_undo,
    "export_expenses": handle_export_expenses,
    "export_xianyu": handle_export_xianyu,
    "income_add": handle_income_add,
    "budget_set": handle_budget_set,
    "monthly_summary": handle_monthly_summary,
    "budget_check": handle_budget_check,
    "bill_update_nlp": handle_bill_update_nlp,
    "bill_add_nlp": handle_bill_add_nlp,
    "bill_query": handle_bill_query,
    "bill_tips": handle_bill_tips,
    "bill_predict": handle_bill_predict,
    "ops_life_remind": handle_ops_life_remind,
    "xianyu_style_show": handle_xianyu_style_show,
    "xianyu_style_faq_list": handle_xianyu_style_faq_list,
    "autotrader_start": handle_autotrader_start,
    "autotrader_stop": handle_autotrader_stop,
    "buy": handle_buy,
    "sell": handle_sell,
    "smart_shop": handle_smart_shop,
    "pricewatch_add": handle_pricewatch_add,
    "suggest": handle_suggest,
}


async def dispatch_special(mixin, update, context, action_type: str, action_arg: str) -> bool:
    """分发非 dispatch_map 中的特殊命令

    返回 True 表示已处理，False 表示无匹配的 handler
    """
    # 先查直接映射的 handler
    handler = _SPECIAL_HANDLERS.get(action_type)
    if handler:
        await handler(mixin, update, context, action_arg)
        return True
    # 再查 ops 路由
    if await handle_ops_route(mixin, update, context, action_type, action_arg):
        return True
    return False
