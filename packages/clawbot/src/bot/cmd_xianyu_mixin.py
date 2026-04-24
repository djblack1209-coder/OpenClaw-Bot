"""
Bot — 闲鱼客服 / 风格 / 报表 / 发货 命令 Mixin

包含功能:
  - 闲鱼 AI 客服远程控制
  - 商品风格管理
  - 收入报表
  - 自动发货 (AutoShipper)
"""

import asyncio
import logging
import os

from src.bot.globals import send_long_message
from src.bot.error_messages import error_service_failed
from src.bot.auth import requires_auth
from src.telegram_ux import with_typing

logger = logging.getLogger(__name__)


class XianyuCommandsMixin:
    @requires_auth
    async def cmd_xianyu(self, update, context):
        """闲鱼 AI 客服远程控制"""
        args = context.args or []
        action = args[0].lower() if args else ""

        # 白名单校验：仅允许已知子命令，防止命令注入
        _VALID_ACTIONS = {"", "start", "stop", "reload", "status"}
        if action and action not in _VALID_ACTIONS:
            action = "status"  # 未知命令回退到状态查看

        PLIST = os.path.expanduser("~/Library/LaunchAgents/ai.openclaw.xianyu.plist")

        # 启动/停止前检查 plist 文件是否存在
        if action in ("start", "stop") and not os.path.isfile(PLIST):
            await update.message.reply_text("⚠️ 闲鱼客服配置文件不存在，请先配置")
            return

        # 无参数时展示帮助菜单 + 一行状态概要
        if not action:
            try:
                # 使用异步子进程避免阻塞事件循环
                proc = await asyncio.create_subprocess_exec(
                    "pgrep",
                    "-f",
                    "xianyu_main",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, _ = await proc.communicate()
                status_line = "🟢 运行中" if stdout.decode().strip() else "🔴 未运行"
            except Exception:
                logger.exception("闲鱼客服进程状态检测失败")
                status_line = "⚪ 状态未知"
            help_msg = (
                "🐟 闲鱼 AI 客服管理\n"
                "━━━━━━━━━━━━━━━\n"
                "/xianyu start    — 启动 AI 客服\n"
                "/xianyu stop     — 停止 AI 客服\n"
                "/xianyu status   — 查看运行状态\n"
                "/xianyu reload   — 重载配置\n"
                "\n"
                "📊 运营数据:\n"
                "/xianyu_report   — 运营报表 (含热销排行/高峰时段/转化漏斗)\n"
                "/xianyu_style    — AI 回复风格/FAQ/商品规则管理\n"
                "\n"
                f"当前状态: {status_line}\n"
                "\n"
                '💡 也可以说中文: "闲鱼数据" "商品排行" "转化率" "闲鱼风格" "闲鱼FAQ"'
            )
            await update.message.reply_text(help_msg)
            return

        if action == "start":
            proc = await asyncio.create_subprocess_exec(
                "launchctl",
                "load",
                PLIST,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, _ = await proc.communicate()
            if proc.returncode == 0:
                await update.message.reply_text("🦞 闲鱼 AI 客服已启动")
            else:
                await update.message.reply_text(error_service_failed("服务启动"))

        elif action == "stop":
            proc = await asyncio.create_subprocess_exec(
                "launchctl",
                "unload",
                PLIST,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, _ = await proc.communicate()
            if proc.returncode == 0:
                await update.message.reply_text("🔴 闲鱼 AI 客服已停止")
            else:
                await update.message.reply_text(error_service_failed("服务停止"))

        elif action == "reload":
            # 发送 SIGUSR1 热更新 Cookie
            import signal

            proc = await asyncio.create_subprocess_exec(
                "pgrep",
                "-f",
                "xianyu_main",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await proc.communicate()
            pids = stdout.decode().strip().split()
            # 校验 pid 必须是纯数字，防止异常输出导致安全问题
            valid_pids = [p for p in pids if p.isdigit()]
            if valid_pids:
                for pid in valid_pids:
                    os.kill(int(pid), signal.SIGUSR1)
                await update.message.reply_text("🔄 已发送配置热更新信号，稍等几秒生效")
            else:
                await update.message.reply_text("⚠️ 闲鱼客服进程未运行")

        else:  # status (显式传 status 或其他未知参数)
            try:
                proc = await asyncio.create_subprocess_exec(
                    "pgrep",
                    "-fl",
                    "xianyu_main",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, _ = await proc.communicate()
                output = stdout.decode().strip()
                reply_func = getattr(update, 'effective_message', update.message)
                if reply_func is None:
                    reply_func = update.message
                if output:
                    lines = output.split("\n")
                    msg = f"🟢 闲鱼 AI 客服运行中\n进程: {len(lines)} 个"
                    await reply_func.reply_text(msg)
                else:
                    await reply_func.reply_text("🔴 闲鱼 AI 客服未运行\n\n发送 /xianyu start 启动")
            except Exception as e:
                logger.warning("[cmd_xianyu] status 查询失败: %s", e)
                reply_func = getattr(update, 'effective_message', None) or update.message
                if reply_func:
                    await reply_func.reply_text(f"⚠️ 闲鱼状态查询失败: {e}")

    # ---- 社媒内容日历 ----

    @requires_auth
    @with_typing
    async def cmd_xianyu_style(self, update, context):
        """闲鱼 AI 客服回复风格 / FAQ / 商品规则管理

        /xianyu_style set 热情活泼，多用emoji    — 设置回复风格
        /xianyu_style faq add 发货 拍下后24小时内自动发货  — 添加FAQ
        /xianyu_style faq list                  — 查看所有FAQ
        /xianyu_style faq remove 发货            — 删除FAQ
        /xianyu_style rule 商品ID 这个商品强调正版授权  — 商品规则
        /xianyu_style rule_remove 商品ID         — 删除商品规则
        /xianyu_style show                      — 查看当前配置
        """
        from src.xianyu.xianyu_context import XianyuContextManager

        xctx = XianyuContextManager()
        args = context.args or []
        sub = args[0].lower() if args else "show"

        # ── /xianyu_style show — 查看当前配置 ──
        if sub in {"show", "查看", "status"}:
            try:
                config = xctx.get_reply_config()
                lines = ["🐟 闲鱼 AI 客服回复配置", "━━━━━━━━━━━━━━━"]

                # 风格
                style = config.get("style")
                lines.append(f"\n🎨 回复风格: {style or '默认（未设置）'}")

                # FAQ
                faqs = config.get("faqs", [])
                lines.append(f"\n❓ 常见问题 ({len(faqs)}/{xctx._FAQ_LIMIT}):")
                if faqs:
                    for i, faq in enumerate(faqs, 1):
                        lines.append(
                            f"  {i}. 「{faq['key']}」→ {faq['value'][:50]}{'...' if len(faq['value']) > 50 else ''}"
                        )
                else:
                    lines.append("  （暂无）")

                # 商品规则
                rules = config.get("item_rules", {})
                lines.append(f"\n📦 商品规则 ({len(rules)}/{xctx._ITEM_RULE_LIMIT}):")
                if rules:
                    for item_id, rule in list(rules.items())[:10]:
                        lines.append(f"  • {item_id}: {rule[:50]}{'...' if len(rule) > 50 else ''}")
                else:
                    lines.append("  （暂无）")

                await send_long_message(update.effective_chat.id, "\n".join(lines), context)
            except Exception:
                logger.exception("闲鱼回复配置读取失败")
                await update.message.reply_text("❌ 严总，读取配置失败了，请稍后再试")
            return

        # ── /xianyu_style set <风格> — 设置回复风格 ──
        if sub in {"set", "设置", "style"}:
            tone = " ".join(args[1:]).strip()
            if not tone:
                await update.message.reply_text(
                    "用法: /xianyu_style set <风格描述>\n\n"
                    "示例:\n"
                    "  /xianyu_style set 热情活泼，多用emoji\n"
                    "  /xianyu_style set 专业简洁，直奔主题\n"
                    "  /xianyu_style set 可爱卖萌，用颜文字"
                )
                return
            try:
                xctx.set_reply_style(tone)
                await update.message.reply_text(f"✅ 回复风格已设置: {tone}")
            except Exception:
                logger.exception("闲鱼回复风格设置失败")
                await update.message.reply_text("❌ 严总，风格设置失败了，请稍后再试")
            return

        # ── /xianyu_style faq <子命令> — FAQ 管理 ──
        if sub == "faq":
            faq_sub = args[1].lower() if len(args) > 1 else "list"

            if faq_sub in {"list", "列表", "ls"}:
                try:
                    faqs = xctx.get_faqs()
                    if not faqs:
                        await update.message.reply_text(
                            "❓ 暂无 FAQ\n\n"
                            "添加: /xianyu_style faq add <关键词> <回复内容>\n"
                            "示例: /xianyu_style faq add 发货 拍下后24小时内自动发货"
                        )
                        return
                    lines = [f"❓ 闲鱼 FAQ ({len(faqs)}/{xctx._FAQ_LIMIT})", ""]
                    for i, faq in enumerate(faqs, 1):
                        lines.append(f"{i}. 关键词: 「{faq['key']}」")
                        lines.append(f"   回复: {faq['value']}")
                    await send_long_message(update.effective_chat.id, "\n".join(lines), context)
                except Exception:
                    logger.exception("闲鱼 FAQ 列表读取失败")
                    await update.message.reply_text("❌ 严总，FAQ 列表读取失败了，请稍后再试")
                return

            if faq_sub in {"add", "添加", "新增"}:
                if len(args) < 4:
                    await update.message.reply_text(
                        "用法: /xianyu_style faq add <关键词> <回复内容>\n\n"
                        "示例:\n"
                        "  /xianyu_style faq add 发货 拍下后24小时内自动发货到您的账号\n"
                        "  /xianyu_style faq add 退款 部署前可全额退款，部署后7天免费售后"
                    )
                    return
                keyword = args[2]
                answer = " ".join(args[3:])
                try:
                    ok = xctx.add_faq(keyword, answer)
                    if ok:
                        await update.message.reply_text(f"✅ FAQ 已添加\n\n关键词: 「{keyword}」\n回复: {answer}")
                    else:
                        await update.message.reply_text(f"❌ FAQ 已达上限 ({xctx._FAQ_LIMIT} 条)")
                except Exception:
                    logger.exception("闲鱼 FAQ 添加失败")
                    await update.message.reply_text("❌ 严总，FAQ 添加失败了，请稍后再试")
                return

            if faq_sub in {"remove", "删除", "rm", "del"}:
                if len(args) < 3:
                    await update.message.reply_text("用法: /xianyu_style faq remove <关键词>")
                    return
                keyword = args[2]
                try:
                    ok = xctx.remove_faq(keyword)
                    if ok:
                        await update.message.reply_text(f"✅ FAQ 已删除: 「{keyword}」")
                    else:
                        await update.message.reply_text(f"❌ 未找到关键词「{keyword}」")
                except Exception:
                    logger.exception("闲鱼 FAQ 删除失败")
                    await update.message.reply_text("❌ 严总，FAQ 删除失败了，请稍后再试")
                return

            await update.message.reply_text("未知 FAQ 子命令，用法: add | list | remove")
            return

        # ── /xianyu_style rule <商品ID> <规则> — 商品规则 ──
        if sub in {"rule", "规则"}:
            if len(args) < 3:
                await update.message.reply_text(
                    "用法: /xianyu_style rule <商品ID> <特殊规则>\n\n"
                    "示例:\n"
                    "  /xianyu_style rule item_001 这个商品重点强调正版授权\n"
                    "  /xianyu_style rule item_002 不支持win7系统，提前告知买家"
                )
                return
            item_id = args[1]
            rule = " ".join(args[2:])
            try:
                ok = xctx.set_item_rule(item_id, rule)
                if ok:
                    await update.message.reply_text(f"✅ 商品规则已设置\n\n商品: {item_id}\n规则: {rule}")
                else:
                    await update.message.reply_text(f"❌ 商品规则已达上限 ({xctx._ITEM_RULE_LIMIT} 条)")
            except Exception:
                logger.exception("闲鱼商品规则设置失败")
                await update.message.reply_text("❌ 严总，商品规则设置失败了，请稍后再试")
            return

        # ── /xianyu_style rule_remove <商品ID> — 删除商品规则 ──
        if sub in {"rule_remove", "删除规则"}:
            if len(args) < 2:
                await update.message.reply_text("用法: /xianyu_style rule_remove <商品ID>")
                return
            item_id = args[1]
            try:
                ok = xctx.remove_item_rule(item_id)
                if ok:
                    await update.message.reply_text(f"✅ 商品规则已删除: {item_id}")
                else:
                    await update.message.reply_text(f"❌ 未找到商品「{item_id}」的规则")
            except Exception:
                logger.exception("闲鱼商品规则删除失败")
                await update.message.reply_text("❌ 严总，商品规则删除失败了，请稍后再试")
            return

        # ── 未知子命令 — 显示帮助 ──
        await update.message.reply_text(
            "🐟 闲鱼 AI 客服回复管理\n\n"
            "/xianyu_style show                    — 查看当前配置\n"
            "/xianyu_style set <风格>               — 设置回复风格\n"
            "/xianyu_style faq add <关键词> <回复>   — 添加FAQ\n"
            "/xianyu_style faq list                — 查看FAQ列表\n"
            "/xianyu_style faq remove <关键词>      — 删除FAQ\n"
            "/xianyu_style rule <商品ID> <规则>      — 商品规则\n"
            "/xianyu_style rule_remove <商品ID>     — 删除商品规则\n\n"
            '也可以说中文: "闲鱼风格" "闲鱼FAQ"'
        )

    @requires_auth
    @with_typing
    async def cmd_xianyu_report(self, update, context):
        """闲鱼收入报表: /xianyu_report [天数]

        搬运 Shopify Analytics Dashboard 的日报/周报/月报模式。
        默认展示最近 7 天的收入、利润、订单数、客单价、爆款排行。
        """
        args = context.args or []
        days = 7
        if args:
            try:
                days = int(args[0])
            except ValueError as e:
                logger.debug("用户输入解析失败: %s", e)
        days = min(max(days, 1), 90)  # 限制 1-90 天

        try:
            from src.xianyu.xianyu_context import XianyuContextManager

            xctx = XianyuContextManager()

            # 收入汇总
            profit = xctx.get_profit_summary(days=days) if hasattr(xctx, "get_profit_summary") else {}
            # 今日统计
            today_stats = xctx.daily_stats() if hasattr(xctx, "daily_stats") else {}
            # 待发货
            pending_ship = xctx.get_pending_shipments() if hasattr(xctx, "get_pending_shipments") else []

            lines = [f"🐟 <b>闲鱼收入报表 — 最近 {days} 天</b>", ""]

            if profit and profit.get("revenue", 0) > 0:
                revenue = profit["revenue"]
                cost = profit.get("cost", 0)
                net_profit = profit.get("profit", 0)
                orders = profit.get("orders", 0)
                avg_price = revenue / orders if orders > 0 else 0
                margin = (net_profit / revenue * 100) if revenue > 0 else 0

                lines.append("━━━ 💰 营收概览 ━━━")
                lines.append(f"营收: <b>¥{revenue:,.0f}</b>")
                lines.append(f"成本: ¥{cost:,.0f}")
                lines.append(f"利润: <b>¥{net_profit:,.0f}</b> ({margin:.0f}%)")
                lines.append(f"订单: {orders} 笔 | 客单价: ¥{avg_price:.0f}")

                if days > 1:
                    daily_avg = revenue / days
                    lines.append(f"日均: ¥{daily_avg:,.0f}")
            else:
                lines.append("📊 暂无营收数据")

            if today_stats:
                lines.append("")
                lines.append("━━━ 📊 今日数据 ━━━")
                if today_stats.get("messages", 0) > 0:
                    lines.append(f"咨询: {today_stats['messages']} 条")
                if today_stats.get("orders", 0) > 0:
                    lines.append(f"下单: {today_stats['orders']} 笔")
                if today_stats.get("conversion_rate"):
                    lines.append(f"转化率: {today_stats['conversion_rate']}")

            if pending_ship:
                lines.append("")
                lines.append(f"━━━ ⚠️ 待发货 {len(pending_ship)} 笔 ━━━")
                for ship in pending_ship[:5]:
                    lines.append(f"  • {ship.get('item_id', '?')} ({ship.get('hours_ago', '?')}h 前付款)")

            # ── BI 板块1: 商品热度排行 ──
            try:
                rankings = xctx.get_item_rankings(days=days, limit=5)
                if rankings:
                    lines.append("")
                    lines.append(f"━━━ 🏆 热销排行 (近{days}天) ━━━")
                    for i, item in enumerate(rankings, 1):
                        title = item.get("title", "未知商品")[:12]
                        consult = item.get("consultations", 0)
                        convert = item.get("conversions", 0)
                        rate = item.get("conversion_rate", "0%")
                        lines.append(f"{i}. {title} | 咨询 {consult}次 | 成交 {convert}单 | 转化率 {rate}")
            except Exception as e:
                pass  # BI 数据获取失败不影响主报表
                logger.debug("静默异常: %s", e)

            # ── BI 板块2: 咨询高峰时段 (文本柱状图, 取前5) ──
            try:
                peak_hours = xctx.get_peak_hours(days=days)
                if peak_hours:
                    # 按消息量降序取前5个时段
                    sorted_hours = sorted(peak_hours, key=lambda x: x["messages"], reverse=True)[:5]
                    max_msgs = sorted_hours[0]["messages"] if sorted_hours else 1
                    if max_msgs > 0:
                        lines.append("")
                        lines.append("━━━ ⏰ 咨询高峰时段 ━━━")
                        for h in sorted_hours:
                            hour_str = h["hour"]
                            msgs = h["messages"]
                            # 柱状图: 最长12格, 按比例缩放
                            bar_len = round(msgs / max_msgs * 12) if max_msgs > 0 else 0
                            bar = "█" * bar_len
                            # 前2名标🔥
                            fire = "🔥" if sorted_hours.index(h) < 2 else "  "
                            next_hour = f"{int(hour_str) + 1:02d}" if int(hour_str) < 23 else "00"
                            lines.append(f"{fire} {hour_str}:00-{next_hour}:00  {bar} {msgs}条")
            except Exception as e:
                pass  # BI 数据获取失败不影响主报表
                logger.debug("静默异常: %s", e)

            # ── BI 板块3: 转化漏斗 ──
            try:
                funnel = xctx.get_conversion_funnel(days=days)
                if funnel and funnel.get("total_consultations", 0) > 0:
                    lines.append("")
                    lines.append("━━━ 🔄 转化漏斗 ━━━")
                    total = funnel["total_consultations"]
                    replied = funnel.get("replied", 0)
                    converted = funnel.get("converted", 0)
                    shipped = funnel.get("shipped", 0)
                    lines.append(f"👀 总咨询:    {total}人")
                    lines.append(f"💬 有回复:    {replied}人 ({funnel.get('replied_rate', '0%')})")
                    lines.append(f"💰 成交:      {converted}人 ({funnel.get('overall_rate', '0%')})")
                    lines.append(f"📦 发货:      {shipped}人 ({funnel.get('shipped_rate', '0%')})")
            except Exception as e:
                pass  # BI 数据获取失败不影响主报表
                logger.debug("静默异常: %s", e)

            msg = "\n".join(lines)
            await update.message.reply_text(msg, parse_mode="HTML")

        except Exception:
            logger.exception("闲鱼报表生成失败")
            await update.message.reply_text(error_service_failed("闲鱼报表"))

    @requires_auth
    @with_typing
    async def cmd_ship(self, update, context):
        """闲鱼卡券管理 — /ship <子命令>"""
        try:
            import time as _time
            from src.xianyu.auto_shipper import AutoShipper

            shipper = AutoShipper()
            args = context.args or []
            sub = args[0] if args else "help"

            if sub == "help" or sub == "帮助":
                help_text = (
                    "📦 闲鱼自动发货管理\n\n"
                    "子命令:\n"
                    "  /ship add <商品ID> <卡券内容> — 添加单张卡券\n"
                    "  /ship batch <商品ID> — 批量添加(下一条消息每行一个)\n"
                    "  /ship stock [商品ID] — 查看库存\n"
                    "  /ship rule <商品ID> [延时秒数] — 设置发货规则\n"
                    "  /ship stats [商品ID] — 发货统计\n"
                    "  /ship test <商品ID> — 模拟发货测试\n\n"
                    "示例:\n"
                    "  /ship add item_001 ABCD-EFGH-1234\n"
                    "  /ship stock\n"
                    "  /ship rule item_001 60"
                )
                await update.message.reply_text(help_text)
                return

            if sub == "add" or sub == "添加":
                if len(args) < 3:
                    await update.message.reply_text("❓ 用法: /ship add <商品ID> <卡券内容>")
                    return
                item_id = args[1]
                card = " ".join(args[2:])
                result = shipper.add_cards(item_id, [card])
                if result["added"] > 0:
                    remaining = shipper._get_remaining(item_id)
                    await update.message.reply_text(f"✅ 卡券已添加\n商品: {item_id}\n当前库存: {remaining}")
                else:
                    await update.message.reply_text("⚠️ 卡券已存在（重复）")
                return

            if sub == "stock" or sub == "库存":
                item_id = args[1] if len(args) > 1 else None
                inv = shipper.get_inventory(item_id)
                if not inv:
                    await update.message.reply_text("📦 暂无库存")
                    return
                msg = "📦 卡券库存:\n\n"
                for item in inv:
                    msg += f"  {item['item_id']}"
                    if item.get("spec"):
                        msg += f" ({item['spec']})"
                    msg += f": {item['available']}可用 / {item['used']}已用 / {item['total']}总计\n"
                await update.message.reply_text(msg)
                return

            if sub == "rule" or sub == "规则":
                if len(args) < 2:
                    await update.message.reply_text("❓ 用法: /ship rule <商品ID> [延时秒数]")
                    return
                item_id = args[1]
                delay = int(args[2]) if len(args) > 2 else 30
                shipper.set_rule(item_id, auto_ship=True, delay_seconds=delay)
                rule = shipper.get_rule(item_id)
                await update.message.reply_text(
                    f"✅ 发货规则已设置\n"
                    f"商品: {item_id}\n"
                    f"自动发货: {'开启' if rule['auto_ship'] else '关闭'}\n"
                    f"延时: {rule['delay_seconds']}秒\n"
                    f"日上限: {rule['max_daily_ship']}单"
                )
                return

            if sub == "stats" or sub == "统计":
                item_id = args[1] if len(args) > 1 else None
                stats = shipper.get_shipping_stats(item_id)
                await update.message.reply_text(
                    f"📊 发货统计:\n  今日发货: {stats['today_shipped']}\n  累计发货: {stats['total_shipped']}"
                )
                return

            if sub == "test" or sub == "测试":
                if len(args) < 2:
                    await update.message.reply_text("❓ 用法: /ship test <商品ID>")
                    return
                item_id = args[1]
                inv = shipper.get_inventory(item_id)
                if not inv or inv[0]["available"] == 0:
                    await update.message.reply_text(f"⚠️ 商品 {item_id} 无可用卡券")
                    return
                result = shipper.process_order(f"test_{int(_time.time())}", item_id, "test_buyer")
                if result["success"]:
                    await update.message.reply_text(
                        f"✅ 模拟发货成功\n"
                        f"卡券: {result['card_content'][:50]}...\n"
                        f"发送消息:\n{result['message'][:200]}\n"
                        f"剩余库存: {result['remaining']}"
                    )
                else:
                    await update.message.reply_text(f"⚠️ 模拟失败: {result['reason']}")
                return

            await update.message.reply_text(f"❓ 未知子命令: {sub}\n发送 /ship help 查看帮助")
        except Exception as e:
            logger.warning("[cmd_ship] 执行失败: %s", e)
            try:
                await update.message.reply_text("⚠️ 命令执行失败，请稍后重试")
            except Exception as e:
                logger.debug("Telegram消息操作失败(用户可能已删除): %s", e)

    # ---- AI 小说工坊 (novel_writer) ----
