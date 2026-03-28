"""
状态与系统信息 Mixin — /status, /metrics, /model, /pool, /keyhealth
"""
import asyncio
import logging
import os

from src.bot.globals import (
    history_store, metrics, health_checker,
    get_total_balance, SILICONFLOW_KEYS, LOW_BALANCE_THRESHOLD,
    send_long_message, execution_hub,
)
from src.litellm_router import free_pool
from src.telegram_ux import with_typing
from src.bot.auth import requires_auth

logger = logging.getLogger(__name__)


class _StatusMixin:
    """系统状态查询与运行指标"""

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
        except Exception as e:  # noqa: F841
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
        text = "🆓 **免费 API 池状态**\n\n"
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
    async def cmd_keyhealth(self, update, context):
        """API Key 健康检查: /keyhealth — 逐 key 验证所有 provider 的连通性"""
        msg = await update.message.reply_text(f"{self.emoji} 正在验证所有 API Key，请稍候...")
        try:
            report = await free_pool.validate_keys(timeout=15.0)

            providers = report.get("providers", {})
            total = report.get("total_providers", 0)
            healthy = report.get("healthy", 0)
            unhealthy = report.get("unhealthy", 0)
            elapsed = report.get("elapsed_s", 0)

            # 状态图标映射
            status_icons = {
                "ok": "✅", "partial": "⚠️",
                "auth_error": "🔴", "quota_exhausted": "🟠",
                "unreachable": "❌", "unknown_error": "❓",
            }

            lines = [
                "🔑 API Key 健康检查",
                "━━━━━━━━━━━━━━━━━━━━━━",
                f"总计: {total} 个 provider | ✅ {healthy} 健康 | ❌ {unhealthy} 异常",
                f"耗时: {elapsed:.1f}s",
                "",
            ]

            for name, info in sorted(providers.items()):
                status = info.get("status", "unknown")
                icon = status_icons.get(status, "❓")
                line = f"{icon} {name}: {status}"

                # 多 key provider 显示详细
                keys_tested = info.get("keys_tested", 0)
                if keys_tested > 1:
                    keys_ok = info.get("keys_ok", 0)
                    keys_dead = info.get("keys_dead", 0)
                    line += f" ({keys_ok}/{keys_tested} key 可用"
                    if keys_dead > 0:
                        dead_idx = info.get("dead_indices", [])
                        line += f", 失效: {dead_idx}"
                    line += ")"

                # 错误信息
                error = info.get("error", "")
                if error:
                    line += f"\n   └ {error[:80]}"

                errors = info.get("errors", [])
                if errors and not error:
                    for err in errors[:3]:
                        line += f"\n   └ {err[:80]}"

                lines.append(line)

            await send_long_message(
                update.effective_chat.id, "\n".join(lines), context,
                reply_to_message_id=update.message.message_id,
            )
            # 删除等待提示
            try:
                await msg.delete()
            except Exception as e:
                logger.debug("删除等待提示消息失败: %s", e)
        except Exception as e:
            logger.error("[KeyHealth] API Key 验证失败: %s", e)
            from src.bot.error_messages import error_service_failed
            await msg.edit_text(error_service_failed("API Key 健康检查"))
