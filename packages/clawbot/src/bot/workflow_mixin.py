"""
Bot — 链式讨论工作流 Mixin
包含多模型协作的服务需求分析工作流方法。
从 message_mixin.py 拆分以改善可维护性。

> 最后更新: 2026-03-29
"""

import json
import logging
import re

from src.bot.globals import bot_registry, collab_orchestrator, send_long_message
from src.notify_style import format_digest

logger = logging.getLogger(__name__)


class WorkflowMixin:
    """链式讨论工作流 Mixin — 服务需求分析的多模型协作"""

    def _pick_workflow_bot(self, candidates=None, exclude=None):
        """选择工作流 Bot — 返回 (candidates, bot_id) 元组"""
        exclude_set = set(exclude or [])
        if candidates:
            for bot_id in candidates:
                if bot_id in exclude_set:
                    continue
                if bot_id in bot_registry:
                    return candidates, bot_id
        for bot_id in bot_registry:
            if bot_id in exclude_set:
                continue
            return None, bot_id
        # 全部被排除时兜底返回自身 — 保持返回类型一致为 tuple
        return None, self.bot_id

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

    def _workflow_team_catalog(self):
        strengths = {
            "qwen235b": "中文解释、方案讲解、文案整理、对小白友好",
            "gptoss": "快问快答、信息提取、轻量补充",
            "deepseek_v3": "中文深度推理、复杂逻辑、量化与风控",
            "claude_haiku": "快速改写、轻文案、补充说明",
            "claude_sonnet": "复杂任务总控、代码与架构、深度分析",
            "claude_opus": "高难任务、终审、复杂代码与大上下文",
            "chatgpt54": "综合总监、复杂任务编排、强全局把控",
            "gpt5_4": "综合总监、复杂任务编排、强全局把控",
            "gpt5_3_codex": "复杂代码执行、工程修复、编码落地",
            "codex": "复杂代码执行、工程修复、编码落地",
        }
        catalog = []
        for bot_id in collab_orchestrator._api_callers.keys():
            target_bot = bot_registry.get(bot_id)
            if not target_bot:
                continue
            catalog.append(
                {
                    "bot_id": bot_id,
                    "name": getattr(target_bot, "name", bot_id),
                    "strength": strengths.get(bot_id, "通用协作与补充执行"),
                }
            )
        return catalog

    def _extract_json_object(self, text=None):
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
            except Exception as e:  # noqa: F841
                continue
        # 回退：直接找 JSON 对象
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            try:
                payload = jloads(text[start : end + 1])
                if isinstance(payload, dict):
                    return payload
            except Exception as e:
                logger.debug("Silenced exception", exc_info=True)
        return None

    def _fallback_service_options(self, text=None):
        task_text = (text or "").strip()
        return {
            "customer_summary": task_text[:120],
            "missing_info": ["如果你暂时说不清细节，也可以先按默认假设推进。"],
            "options": [
                {
                    "id": 1,
                    "title": "极速落地版",
                    "fit": "适合想先快速看到结果的小白",
                    "benefits": "先按合理默认假设推进，最快给出第一版结果",
                    "tradeoffs": "细节不全时，后面可能需要再补一轮修正",
                    "default_assumption": "未补充信息时按当前上下文和常见默认值推进",
                    "recommended": True,
                },
                {
                    "id": 2,
                    "title": "稳妥确认版",
                    "fit": "适合担心返工、想把关键条件说清的人",
                    "benefits": "先把关键问题问清楚，再给较稳的执行方案",
                    "tradeoffs": "前置确认会多一步，整体速度稍慢",
                    "default_assumption": "优先补齐关键条件，再开始执行",
                    "recommended": False,
                },
                {
                    "id": 3,
                    "title": "专家深挖版",
                    "fit": "适合高风险、高复杂度或需要长期迭代的任务",
                    "benefits": "先做评审、风险拆解和分工，再给更完整的结论",
                    "tradeoffs": "耗时最长，但信息最完整、后续扩展更顺",
                    "default_assumption": "优先完整性与风险控制，不追求最快交付",
                    "recommended": False,
                },
            ],
        }

    def _build_service_intake_prompt(self, text: str = None, feedback_context: str = None) -> str:
        return f"""你现在是一个多模型团队里的专业客服接待官，面对的是中文小白用户。\n\n你的任务不是直接开工，而是先把需求接稳、讲明白，再给用户 3 个可选方案。\n\n输出要求：\n1. 用中文，口语化、好懂，不要堆术语。\n2. 先用 1-2 句话复述用户要做什么。\n3. 如果缺信息，只指出最关键的 1-3 条；如果不阻塞，就写“可先按默认假设推进”。\n4. 必须给出 3 个编号方案，每个方案包含：title、fit、benefits、tradeoffs、default_assumption。\n5. 选出一个 recommended=true 的推荐方案。\n6. 最后明确提醒用户只需要回复 1 / 2 / 3 即可继续。\n\n请务必在结尾附上 JSON 代码块，格式如下：\n```json\n{{\n  "customer_summary": "",\n  "missing_info": [""],\n  "options": [\n    {{"id": 1, "title": "", "fit": "", "benefits": "", "tradeoffs": "", "default_assumption": "", "recommended": true}},\n    {{"id": 2, "title": "", "fit": "", "benefits": "", "tradeoffs": "", "default_assumption": "", "recommended": false}},\n    {{"id": 3, "title": "", "fit": "", "benefits": "", "tradeoffs": "", "default_assumption": "", "recommended": false}}\n  ]\n}}\n```\n\n历史评分反馈：{"暂无历史评分，按标准客服流程接待。"}\n\n用户原话：{text}"""

    def _render_service_intake(self, session=None):
        options = session.options if session and session.options else []
        sections = []
        intake_summary = session.intake_summary if session and session.intake_summary else ""
        sections.append(("【需求确认】", [intake_summary or (session.original_text if session else "")]))
        if session and session.missing_info:
            sections.append(("【必要信息】", session.missing_info[:3]))
        recommended = 1
        for item in options[:3]:
            option_id = int(item.get("id", 0))
            if item.get("recommended"):
                recommended = option_id
            sections.append(
                (
                    f"【方案 {option_id}】",
                    [
                        f"标题：{item.get('title', '')}",
                        f"适合谁：{item.get('fit', '')}",
                        f"优点：{item.get('benefits', '')}",
                        f"代价/风险：{item.get('tradeoffs', '')}",
                        f"默认假设：{item.get('default_assumption', '')}",
                    ],
                )
            )
        return format_digest(
            title="OpenClaw「链式讨论」专业客服接单",
            intro="先把需求接稳，再给你 3 个方案。你只需要选编号，我就继续往下推进。",
            sections=sections,
            footer=f"""推荐优先选方案 {recommended}。请直接回复 1 / 2 / 3。""",
        )

    def _parse_workflow_choice(self, text=None, option_count=None):
        if not text:
            return (0, "")
        match = re.search(r"(?:选|方案)?\s*([1-9])\b", text)
        if not match:
            return (0, "")
        choice = int(match.group(1))
        if choice < 1 or choice > max(1, option_count or 3):
            return (0, "")
        note = re.sub(r"(?:选|方案)?\s*[1-9]\b", "", text, count=1).strip(" ：:，,；;")
        return (choice, note)

    def _build_expert_review_prompt(
        self, session=None, selected_option: dict = None, feedback_context: str = None
    ) -> str:
        return f"""你现在是相关领域的专家评审官，面对的是一个中文小白用户。\n\n请基于用户原始需求和已选方案，完成：\n1. 判断该方案是否适合当前需求。\n2. 补充必要假设、交付物、风险和小白注意事项。\n3. 将后续执行拆成 2-4 个可并行 workstreams，每个 workstream 标明 type（code / logic / copy / research / qa）。\n\n结尾必须附上 JSON：\n```json\n{{\n  "expert_role": "",\n  "assessment": "",\n  "assumptions": [""],\n  "deliverables": [""],\n  "risks": [""],\n  "beginner_notes": [""],\n  "workstreams": [\n    {{"id": "ws1", "title": "", "goal": "", "type": "logic", "done_when": ""}}\n  ]\n}}\n```\n\n历史评分反馈：{"暂无历史评分。"}\n\n用户原话：{session.original_text}\n用户选中的方案：{json.dumps(selected_option, ensure_ascii=False)}\n用户补充说明：{"无"}"""

    def _fallback_expert_plan(self, session=None, selected_option=None):
        logger.debug("Chain discuss: _fallback_expert_plan not yet implemented")
        return {
            "expert_role": "通用顾问",
            "assessment": "方案基本可行，建议按步骤执行。",
            "assumptions": ["基于当前上下文的合理默认假设"],
            "deliverables": ["初步结果"],
            "risks": ["暂无已知风险"],
            "beginner_notes": ["如有疑问可随时追问"],
            "workstreams": [
                {
                    "id": "ws1",
                    "title": "执行任务",
                    "goal": str(getattr(session, "original_text", ""))[:80],
                    "type": "logic",
                    "done_when": "完成用户需求",
                }
            ],
        }

    def _render_expert_review(self, plan=None):
        logger.debug("Chain discuss: _render_expert_review not yet implemented")
        if not plan:
            return ""
        assessment = plan.get("assessment", "")
        assumptions = plan.get("assumptions", [])
        parts = []
        if assessment:
            parts.append(f"📋 评估: {assessment}")
        if assumptions:
            parts.append("📌 假设: " + "、".join(str(a) for a in assumptions[:3]))
        return "\n".join(parts)

    def _pick_lane_bot(self, lane=None, exclude=None):
        exclude_set = set(exclude or [])
        lane_map = {
            "code": ["gpt5_3_codex", "codex", "claude_opus", "claude_sonnet", "deepseek_v3", "gptoss"],
            "logic": ["deepseek_v3", "claude_sonnet", "qwen235b", "gpt5_4", "chatgpt54"],
            "copy": ["qwen235b", "claude_haiku", "deepseek_v3", "gptoss"],
            "research": ["qwen235b", "deepseek_v3", "claude_sonnet", "claude_haiku"],
            "qa": ["claude_sonnet", "qwen235b", "deepseek_v3", "claude_opus", "gptoss"],
        }
        return self._pick_workflow_bot(lane_map.get(lane, lane_map["logic"]), exclude=exclude_set)

    def _build_director_prompt(self, session=None, team_catalog=None, feedback_context: str = None) -> str:
        return f"""你现在是多模型团队的总监，需要根据专家复核后的方案，把任务按模型特长分配给现有团队并行执行。\n\n要求：\n1. 必须从可用 bot_id 中选择 2-4 个 assignment。\n2. 尽量并行，不要把所有任务都压给同一个模型。\n3. 代码优先交给 code 强的模型，中文解释优先交给 Qwen/中文强模型，复杂逻辑优先交给 DeepSeek/强推理模型。\n4. 再选 1-2 个 validators 做交叉验证。\n\n可用模型：{json.dumps(team_catalog, ensure_ascii=False)}\n专家方案：{json.dumps(session.expert_plan, ensure_ascii=False)}\n历史评分反馈：{"暂无历史评分。"}\n\n请只在结尾附上 JSON：\n```json\n{{\n  "director_summary": "",\n  "assignments": [\n    {{"bot_id": "", "task_id": "ws1", "subtask": "", "reason": ""}}\n  ],\n  "validators": [\n    {{"bot_id": "", "focus": ""}}\n  ]\n}}\n```"""

    def _fallback_team_plan(self, session, team_catalog):
        logger.debug("Chain discuss: _fallback_team_plan not yet implemented")
        return {
            "director_summary": "默认分配: 使用当前可用模型执行任务",
            "assignments": [],
            "validators": [],
        }

    def _render_team_plan(self, team_plan=None, team_catalog=None):
        logger.debug("Chain discuss: _render_team_plan not yet implemented")
        if not team_plan:
            return ""
        summary = team_plan.get("director_summary", "")
        return f"🎯 {summary}" if summary else ""

    def _merge_assignments_by_bot(self, assignments):
        grouped = {}
        for item in assignments or []:
            bot_id = str(item.get("bot_id", "")).strip()
            if not bot_id:
                continue
            bucket = grouped.setdefault(bot_id, {"bot_id": bot_id, "tasks": [], "reasons": []})
            task_text = str(item.get("subtask", "")).strip()
            if task_text:
                bucket["tasks"].append(task_text)
            reason_text = str(item.get("reason", "")).strip()
            if not reason_text:
                continue
            bucket["reasons"].append(reason_text)
        return list(grouped.values())

    def _workflow_timeout(self, bot_id=None):
        if bot_id in frozenset(
            {"codex", "gpt5_4", "chatgpt54", "claude_opus", "deepseek_v3", "gpt5_3_codex", "claude_sonnet"}
        ):
            return 180
        return 120

    def _build_worker_prompt(self, session=None, grouped_assignment=None):
        logger.debug("Chain discuss: _build_worker_prompt not yet implemented")
        tasks = grouped_assignment.get("tasks", []) if grouped_assignment else []
        task_desc = "\n".join(f"- {t}" for t in tasks) if tasks else "- 完成分配的任务"
        return f"""请根据以下任务指令完成工作。

用户原始需求: {getattr(session, "original_text", "未知")}

你的任务:
{task_desc}

请直接给出结果，不需要解释分配过程。"""

    def _build_validation_prompt(self, session=None, focus: str = None, combined_text: str = None) -> str:
        return f"""你现在负责交叉验证。请检查下面这轮团队并行结果，重点关注：{"遗漏、冲突、风险和对小白是否友好"}。\n\n用户原话：{session.original_text}\n已选方案：{session.selected_option_id}\n专家复核：{json.dumps(session.expert_plan, ensure_ascii=False)}\n团队执行结果：\n{combined_text[:5000]}\n\n请在结尾附上 JSON：\n```json\n{{\n  "verdict": "pass",\n  "highlights": [""],\n  "missing": [""],\n  "beginner_notes": [""],\n  "next_iterations": [""]\n}}\n```"""

    def _build_summary_prompt(self, session=None, combined_text: str = None, validation_text: str = None) -> str:
        logger.debug("Chain discuss: _build_summary_prompt not yet implemented")
        return f"""请为以下多模型协作结果生成一份用户友好的总结报告。

用户原始需求: {getattr(session, "original_text", "未知")}

团队执行结果:
{str(combined_text)[:3000] if combined_text else "暂无结果"}

验证反馈:
{str(validation_text)[:1000] if isinstance(validation_text, str) else "暂无验证"}

请输出:
1. 一句话总结
2. 关键结论 (3-5条)
3. 后续建议"""

    def _fallback_summary_payload(self, session=None):
        """生成降级摘要数据 — 从讨论结果中提取结构化摘要。"""
        status_items = []
        all_text = []
        for item in session.execution_results:
            bot_name = item.get("bot_name", item.get("bot_id", "AI"))
            task_summary = item.get("task_summary", "已提交结果")
            status_items.append(f"{bot_name} 已完成：{task_summary}")
            # 收集所有回复文本用于摘要
            content = item.get("content", item.get("result", ""))
            if content:
                all_text.append(f"【{bot_name}】{str(content)[:500]}")
        beginner_notes = session.expert_plan.get("beginner_notes", []) if session.expert_plan else []
        # 生成简要摘要
        summary = ""
        if all_text:
            summary = "\n".join(all_text[:5])  # 最多取前5条回复
        return {
            "status_items": status_items,
            "beginner_notes": beginner_notes,
            "summary": summary,
            "result": summary,
        }

    def _render_final_workflow_report(self, session=None, summary_payload=None):
        logger.debug("Chain discuss: _render_final_workflow_report not yet implemented")
        if not summary_payload:
            return "📋 工作流已完成，暂无详细报告。"
        if isinstance(summary_payload, dict):
            summary = summary_payload.get("summary", summary_payload.get("result", ""))
            if summary:
                return f"📋 工作流报告\n━━━━━━━━━━━━━━━\n{str(summary)[:2000]}"
        return f"📋 工作流报告\n━━━━━━━━━━━━━━━\n{str(summary_payload)[:2000]}"

    def _parse_workflow_ratings(self, text: str = None):
        """从用户反馈文本中解析评分（支持数字评分和emoji评分）。

        支持格式:
        - "3 4 5" 或 "3, 4, 5"  → [3, 4, 5]
        - "⭐⭐⭐ ⭐⭐⭐⭐ ⭐⭐⭐⭐⭐" → [3, 4, 5]
        - "客服3分 方案4分 交付5分" → [3, 4, 5]
        """
        import re

        if not text:
            return None
        text = text.strip()
        # 方式1: 提取所有 1-5 的数字
        numbers = re.findall(r"\b([1-5])\b", text)
        if len(numbers) >= 3:
            return [int(n) for n in numbers[:3]]
        # 方式2: 数星星 ⭐
        star_groups = re.findall(r"(⭐+)", text)
        if len(star_groups) >= 3:
            return [len(g) for g in star_groups[:3]]
        # 方式3: 单个数字视为整体评价
        if len(numbers) == 1:
            score = int(numbers[0])
            return [score, score, score]
        return None

    def _workflow_improvement_focus(self, ratings) -> str:
        """根据评分确定需要改进的环节。"""
        labels = ["客服接待", "方案评审", "任务交付"]
        if not ratings:
            return "持续优化整体链路。"
        min_value = min(ratings)
        # 找到最低分对应的环节
        min_idx = ratings.index(min_value)
        if min_idx < len(labels):
            return f"重点改进「{labels[min_idx]}」环节（当前评分最低: {min_value}）。"
        return "持续优化整体链路。"

    async def _continue_service_workflow(self, update=None, context=None, session=None, text: str = None):
        logger.debug("Chain discuss: _continue_service_workflow not yet implemented")
        try:
            await update.message.reply_text(
                "🚧 此功能正在开发中，暂时无法继续工作流。\n请直接描述您的需求，我会用标准模式为您服务。"
            )
        except Exception as e:
            logger.debug("回复工作流提示消息失败: %s", e)
