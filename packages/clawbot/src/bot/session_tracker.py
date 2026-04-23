# session_tracker.py — 会话恢复检测 + 异步追问建议更新
# 从 message_mixin.py 拆分而来

import logging

from src.http_client import ResilientHTTPClient
from src.bot.input_processor import _build_smart_reply_keyboard

logger = logging.getLogger(__name__)

# 模块级别 HTTP 客户端（本地状态查询）
_http_status = ResilientHTTPClient(timeout=5.0, name="local_status")


class SessionTrackerMixin:
    """会话恢复 + 追问建议 Mixin — 提供会话恢复检测和异步建议更新。

    依赖宿主类提供: bot_id
    """

    # ── LLM 流式路径追问建议异步更新 ────────────────────────────
    # Brain 路径已有追问建议（第一轮交付），但 LLM 流式路径（80%对话）没有
    # 这里在消息发出后异步生成建议，再更新按钮

    async def _async_update_suggestions(
        self, context, chat_id, message_id, raw_content, display_html, parse_mode, model_used
    ):
        """异步生成追问建议并更新消息按钮 — 不阻塞主流程。"""
        try:
            from src.core.response_synthesizer import get_response_synthesizer

            synth = get_response_synthesizer()
            suggestions = await synth.generate_suggestions(raw_content)
            if not suggestions:
                return

            # 用建议重新构建键盘
            new_markup = _build_smart_reply_keyboard(
                raw_content,
                self.bot_id,
                model_used,
                chat_id,
                ai_suggestions=suggestions,
            )
            await context.bot.edit_message_reply_markup(
                chat_id=chat_id,
                message_id=message_id,
                reply_markup=new_markup,
            )
        except Exception as e:
            logger.debug(f"异步追问建议更新失败 (不影响主流程): {e}")

    # ── 会话恢复问候 — 搬运 Apple Intelligence 摘要 / Slack Catch Up ──────
    # 用户超过 SESSION_GAP_THRESHOLD 小时没互动，回来时生成离线摘要

    _SESSION_GAP_THRESHOLD = 4 * 3600  # 4 小时
    _last_interaction: dict = {}  # chat_id → monotonic timestamp (类级共享: 单进程单实例设计)

    async def _check_session_resumption(self, chat_id: int, user_id: int, update, context) -> bool:
        """检测用户是否从长时间离线中回来，如果是则发送离线摘要。

        搬运灵感: Apple Intelligence notification summary / Slack Catch Up
        返回 True 表示发送了恢复摘要。
        """
        import time as _t

        now = _t.monotonic()
        last = self._last_interaction.get(chat_id, 0)
        self._last_interaction[chat_id] = now

        # 首次互动或间隔不够长，跳过
        if last == 0 or (now - last) < self._SESSION_GAP_THRESHOLD:
            return False

        gap_hours = (now - last) / 3600

        # 收集离线期间的变化（异步、轻量）
        summary_parts = []
        try:
            # 1. 持仓变化
            from src.invest_tools import get_stock_quote
            from src.watchlist import get_watchlist_symbols

            symbols = get_watchlist_symbols()[:5]
            if symbols:
                movers = []
                import asyncio as _aio

                quotes = await _aio.gather(
                    *[get_stock_quote(s) for s in symbols],
                    return_exceptions=True,
                )
                for sym, q in zip(symbols, quotes):
                    if isinstance(q, Exception) or not q:
                        continue
                    pct = q.get("change_pct", 0)
                    if abs(pct) > 1.5:
                        movers.append(f"{sym} {pct:+.1f}%")
                if movers:
                    summary_parts.append(f"📊 自选股异动: {', '.join(movers)}")
        except Exception as e:
            logger.debug("静默异常: %s", e)

        try:
            # 2. 闲鱼未读消息 — 通过 FastAPI 内部 API 查询闲鱼进程状态
            import os as _os

            api_port = _os.environ.get("CLAWBOT_API_PORT", "18790")
            api_token = _os.environ.get("OPENCLAW_API_TOKEN", "")
            resp = await _http_status.get(
                f"http://127.0.0.1:{api_port}/api/v1/system/status",
                headers={"X-API-Token": api_token} if api_token else {},
            )
            if resp.status_code == 200:
                data = resp.json()
                # 从系统状态中提取闲鱼相关信息
                xianyu_status = data.get("components", {}).get("xianyu", {})
                unread = xianyu_status.get("unread_count", 0)
                if unread > 0:
                    summary_parts.append(f"🐟 闲鱼: {unread} 条未读消息")
        except Exception as e:
            logger.debug("闲鱼状态查询跳过: %s", e)

        if not summary_parts:
            return False

        # 发送恢复摘要
        try:
            gap_text = f"{gap_hours:.0f}小时" if gap_hours < 24 else f"{gap_hours / 24:.0f}天"
            greeting = f"👋 你离开了 {gap_text}，这期间发生了：\n" + "\n".join(summary_parts)
            await update.message.reply_text(greeting)
            return True
        except Exception:
            logger.exception("会话恢复摘要发送失败")
            return False
