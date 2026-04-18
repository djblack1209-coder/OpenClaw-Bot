"""
Bot — 工作流 Mixin
保留实际使用中的方法: _cmd_smart_shop (购物比价) + _extract_json_object (JSON提取)。
链式讨论工作流的 22 个未接入方法已清理 (HI-530)。

> 最后更新: 2026-04-18
"""

import logging
import re

from src.bot.globals import send_long_message

logger = logging.getLogger(__name__)


class WorkflowMixin:
    """工作流 Mixin — 购物比价 + JSON 提取工具"""

    # ── v2.0: 自然语言购物比价 ─────────────────────────────────

    async def _cmd_smart_shop(self, update, context, product=""):
        """自然语言购物比价: 用户说"帮我找便宜的AirPods" → 多平台比价

        三级降级: Tavily (实时搜索) → crawl4ai (JD/SMZDM) → Jina+LLM → 纯LLM
        """
        if not product:
            await update.message.reply_text("请告诉我你想买什么，例如: 帮我找便宜的AirPods Pro")
            return

        await update.message.reply_text(f"🔍 正在为你搜索「{product}」的最佳价格...\n多平台比价中，请稍候...")

        try:
            # 尝试 Brain 的智能购物 (三级降级链)
            from src.core.brain import OmegaBrain

            brain = OmegaBrain()
            result = await brain._exec_smart_shopping({"product": product})
            if result and result.get("success") and result.get("data"):
                data = result["data"]
                # 格式化输出
                lines = [f"🛒 <b>{product} 比价结果</b>\n"]
                products = data.get("products", [])
                if products:
                    for i, p in enumerate(products[:8], 1):
                        name = p.get("name", p.get("title", ""))[:40]
                        price = p.get("price", "N/A")
                        platform = p.get("platform", p.get("source", ""))
                        url = p.get("url", "")
                        line = f"{i}. <b>{name}</b>"
                        if price:
                            line += f" — ¥{price}"
                        if platform:
                            line += f" ({platform})"
                        lines.append(line)
                        if url:
                            lines.append(f"   🔗 <a href='{url}'>链接</a>")

                best = data.get("best_deal") or data.get("recommendation", "")
                if best:
                    lines.append(f"\n💡 <b>推荐:</b> {best}")

                tips = data.get("tips", [])
                if tips:
                    lines.append("\n📌 <b>省钱技巧:</b>")
                    for tip in tips[:3]:
                        lines.append(f"  • {tip}")

                # 标注实际可用的搜索平台
                lines.append("\n📌 已搜索平台：京东、什么值得买 | 淘宝/天猫需登录暂不可用")

                msg = "\n".join(lines)
                await send_long_message(update.effective_chat.id, msg, parse_mode="HTML", context=context)
                return

            # 降级到纯文本
            summary = result.get("data", {}).get("raw", "") if result else ""
            if summary:
                await send_long_message(
                    update.effective_chat.id,
                    f"🛒 <b>{product} 比价</b>\n\n{summary}",
                    parse_mode="HTML",
                    context=context,
                )
                return

        except Exception as e:
            logger.warning("[SmartShop] Brain 购物失败, 降级到 LLM: %s", e)

        # 最终降级: 让当前 Bot 的 LLM 回答
        prompt = (
            f"用户想买「{product}」，请帮忙做一个简洁的多平台价格对比。"
            f"包括京东、淘宝、拼多多等主流平台的价格范围和购买建议。"
            f"如果有优惠券或促销活动也请提及。"
        )
        context.args = []
        # 走标准 LLM 流式响应
        async for content, status in self._call_api_stream(update.effective_chat.id, prompt, save_history=False):
            if status == "done" and content:
                await send_long_message(update.effective_chat.id, content, context=context)
                return

    def _extract_json_object(self, text=None):
        """从文本中提取 JSON 对象 — 支持 ```json``` 代码块和裸 JSON"""
        if not text:
            return None
        from json_repair import loads as jloads

        patterns = [r"```json\s*(\{.*?\})\s*```", r"```\s*(\{.*?\})\s*```"]
        for pattern in patterns:
            match = re.search(pattern, text, re.DOTALL)
            if not match:
                continue
            try:
                payload = jloads(match.group(1))
                if isinstance(payload, dict):
                    return payload
            except Exception:
                continue
        # 回退：直接找 JSON 对象
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            try:
                payload = jloads(text[start : end + 1])
                if isinstance(payload, dict):
                    return payload
            except Exception:
                logger.debug("JSON 提取失败", exc_info=True)
        return None
