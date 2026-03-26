"""
执行场景命令 Mixin

统一入口: /ops
"""

import asyncio
import json
import logging
import os
from pathlib import Path

from src.bot.globals import execution_hub, send_long_message, image_tool, get_siliconflow_key
from src.bot.rate_limiter import rate_limiter, token_budget
from src.message_format import format_error
from src.bot.error_messages import error_service_failed
from src.bot.auth import requires_auth
from src.telegram_ux import with_typing
from src.notify_style import (
    format_social_published, format_social_dual_result,
    format_hotpost_result, format_cost_card, format_bounty_result,
    kv, bullet, divider, timestamp_tag, format_notice,
)

logger = logging.getLogger(__name__)


class ExecutionCommandsMixin:
    @staticmethod
    def _social_login_retry_hint(result, retry_command: str) -> str:
        if str(result.get("status", "") or "").strip().lower() != "login_required":
            return ""
        browser = result.get("browser", {}) or {}
        missing = []
        if browser.get("x_ready") is False:
            missing.append("X")
        if browser.get("xiaohongshu_ready") is False:
            missing.append("小红书")
        label = " / ".join(missing) if missing else "目标平台"
        return f"\nOpenClaw 专用浏览器已自动打开，请先登录{label}后重试 {retry_command}"

    @requires_auth
    async def cmd_hot(self, update, context):
        await self.cmd_hotpost(update, context)

    @requires_auth
    async def cmd_post_social(self, update, context):
        await self.cmd_post(update, context)

    @requires_auth
    async def cmd_post_x(self, update, context):
        await self.cmd_xpost(update, context)

    @requires_auth
    async def cmd_post_xhs(self, update, context):
        await self.cmd_xhspost(update, context)

    @requires_auth
    @with_typing
    async def cmd_social_persona(self, update, context):
        ret = await asyncio.to_thread(execution_hub.get_social_persona_summary)
        if not ret.get("success"):
            await update.message.reply_text(format_error(ret.get('error', '未知错误'), "读取社媒人设"))
            return
        lines = [f"当前社媒人设 | {ret.get('name', '')}", ""]
        if ret.get("headline"):
            lines.append(f"- 定位: {ret.get('headline')}")
        if ret.get("truth"):
            lines.append(f"- 真相声明: {ret.get('truth')}")
        if ret.get("background"):
            lines.append(f"- 外壳背景: {ret.get('background')}")
        keywords = ret.get("voice_keywords", []) or []
        if keywords:
            lines.append(f"- 声线关键词: {' / '.join(keywords[:6])}")
        must_keep = ret.get("must_keep", []) or []
        if must_keep:
            lines.append(f"- 必须保留: {'；'.join(must_keep[:3])}")
        avoid = ret.get("avoid", []) or []
        if avoid:
            lines.append(f"- 明确避免: {'；'.join(avoid[:3])}")
        if ret.get("x_style"):
            lines.append(f"- X 风格: {ret.get('x_style')}")
        if ret.get("xhs_style"):
            lines.append(f"- 小红书风格: {ret.get('xhs_style')}")
        if ret.get("path"):
            lines.append(f"- 人设文件: {ret.get('path')}")
        await send_long_message(update.effective_chat.id, "\n".join(lines), context)

    @requires_auth
    @with_typing
    async def cmd_social_launch(self, update, context):
        await update.message.reply_text("正在生成数字生命首发包并写入草稿...")
        ret = await asyncio.to_thread(execution_hub.create_social_launch_drafts)
        if not ret.get("success"):
            await update.message.reply_text(format_error(ret.get('error', '未知错误'), "生成首发包"))
            return
        persona = ret.get("persona", {}) or {}
        lines = [f"数字生命首发包 | {persona.get('name', '')}", ""]
        if persona.get("bio"):
            lines.append(f"- 简介: {persona.get('bio')}")
        x_ret = ret.get("x", {}) or {}
        xhs_ret = ret.get("xiaohongshu", {}) or {}
        lines.append(f"- X 草稿: {x_ret.get('draft_id') or x_ret.get('existing_id') or '未写入'}")
        lines.append(f"- X 首发: {x_ret.get('body', '')}")
        lines.append(f"- 小红书草稿: {xhs_ret.get('draft_id') or xhs_ret.get('existing_id') or '未写入'}")
        lines.append(f"- 小红书标题: {xhs_ret.get('title', '')}")
        lines.append(f"- 小红书正文: {xhs_ret.get('body', '')}")
        image_payload = ret.get("image", {}) or {}
        prompt = str(image_payload.get("prompt", "") or "").strip()
        negative_prompt = str(image_payload.get("negative_prompt", "") or "").strip()
        provider = ""
        generated_paths = []
        if prompt:
            key = get_siliconflow_key()
            image_tool.set_api_key(key or "")
            generation_prompt = f"{prompt}, avoid underage appearance, adult woman only"
            if negative_prompt:
                generation_prompt += f", negative prompt guidance: {negative_prompt}"
            image_ret = await image_tool.generate(generation_prompt, model="flux", size=str(image_payload.get("size", "1024x1024") or "1024x1024"))
            provider = str(image_ret.get("provider", "siliconflow") or "siliconflow")
            generated_paths = list(image_ret.get("paths", []) or [])
            if image_ret.get("success"):
                for path in generated_paths[:3]:
                    try:
                        with open(path, "rb") as f:
                            await context.bot.send_photo(chat_id=update.effective_chat.id, photo=f, caption=f"数字生命自拍 | {persona.get('name', '')}")
                    except Exception:
                        logger.exception("发送数字生命自拍失败: %s", path)
            else:
                lines.append(error_service_failed("自拍生成", image_ret.get('error', '')))
        lines.append(f"- 自拍 Prompt: {prompt}")
        lines.append(f"- 负面词: {(ret.get('image', {}) or {}).get('negative_prompt', '')}")
        if generated_paths:
            lines.append(f"- 自拍已生成: {generated_paths[0]}")
            lines.append(f"- 图片来源: {provider}")
        next_topics = ret.get("next_topics", []) or []
        if next_topics:
            lines.append(f"- 后续选题: {'；'.join(next_topics[:3])}")
        if x_ret.get("draft_id") or xhs_ret.get("draft_id") or x_ret.get("existing_id") or xhs_ret.get("existing_id"):
            lines.append("- 下一步: /post_x <X草稿ID> 或 /post_xhs <小红书草稿ID>")
        await send_long_message(update.effective_chat.id, "\n".join(lines), context)

    @requires_auth
    async def cmd_dev(self, update, context):
        args = ["dev", *(context.args or [])]
        context.args = args
        await self.cmd_ops(update, context)

    @requires_auth
    @with_typing
    async def cmd_brief(self, update, context):
        await update.message.reply_text("正在生成执行简报...")
        brief = await execution_hub.generate_daily_brief()
        await send_long_message(update.effective_chat.id, brief, context)

    @requires_auth
    async def cmd_lane(self, update, context):
        await self.cmd_lanes(update, context)

    @requires_auth
    @with_typing
    async def cmd_cost(self, update, context):
        throttle_flags = {
            "group_llm": os.getenv('CHAT_ROUTER_ENABLE_GROUP_LLM', 'false').lower() in {'1','true','yes','on'},
            "group_intent": os.getenv('CHAT_ROUTER_ENABLE_GROUP_INTENT', 'false').lower() in {'1','true','yes','on'},
            "group_fallback": os.getenv('CHAT_ROUTER_ENABLE_GROUP_FALLBACK', 'false').lower() in {'1','true','yes','on'},
            "fill_only": os.getenv('AUTO_TRADE_NOTIFY_ONLY_FILLS', 'false').lower() in {'1','true','yes','on'},
        }
        text = format_cost_card(
            throttle_flags=throttle_flags,
            token_rows=token_budget.get_all_status(),
            rate_rows=rate_limiter.get_all_status(),
        )
        await send_long_message(update.effective_chat.id, text, context)

    @requires_auth
    @with_typing
    async def cmd_config(self, update, context):
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

    @requires_auth
    @with_typing
    async def cmd_topic(self, update, context):
        topic = " ".join(context.args or []).strip() or "AI出海"
        await update.message.reply_text(f"正在研究题材：{topic}")
        ret = await execution_hub.research_social_topic(topic, limit=5)
        if not ret.get("success"):
            await update.message.reply_text(format_error(ret.get('error', '未知错误'), "题材研究"))
            return
        research = ret.get("research", {}) or {}
        strategy = ret.get("strategy", {}) or {}
        lines = [f"题材研究 | {topic}", ""]
        lines.append("热点来源:")
        for item in (research.get("x") or [])[:3]:
            lines.append(f"- [X] {item.get('title', '')}")
        for item in (research.get("xiaohongshu") or [])[:3]:
            lines.append(f"- [小红书] {item.get('title', '')}")
        lines.append("")
        lines.append("学习结论:")
        lines.append(f"- 实用价值分: {strategy.get('utility_score', 0)}/100")
        if strategy.get("positioning"):
            lines.append(f"- 内容定位: {strategy.get('positioning')}")
        if strategy.get("audience"):
            lines.append(f"- 目标受众: {strategy.get('audience')}")
        if strategy.get("primary_format"):
            lines.append(f"- 推荐形式: {strategy.get('primary_format')}")
        lines.append(f"- 结构: {' / '.join(strategy.get('patterns', [])[:3]) or '短结论 + 清单展开'}")
        if strategy.get("opportunity"):
            lines.append(f"- 信息差: {strategy.get('opportunity')}")
        if strategy.get("mvp_rule"):
            lines.append(f"- MVP原则: {strategy.get('mvp_rule')}")
        if strategy.get("x_warning"):
            lines.append(f"- X提醒: {strategy.get('x_warning')}")
        if strategy.get("x_tactic"):
            lines.append(f"- X打法: {strategy.get('x_tactic')}")
        if strategy.get("xhs_tactic"):
            lines.append(f"- 小红书打法: {strategy.get('xhs_tactic')}")
        if strategy.get("lead_magnet"):
            lines.append(f"- 诱饵/资料包: {strategy.get('lead_magnet')}")
        if strategy.get("cta"):
            lines.append(f"- CTA: {strategy.get('cta')}")
        proof_assets = strategy.get("proof_assets", []) or []
        if proof_assets:
            lines.append(f"- 证明材料: {'；'.join(proof_assets[:3])}")
        repurpose_path = strategy.get("repurpose_path", []) or []
        if repurpose_path:
            lines.append(f"- 发布路径: {' -> '.join(repurpose_path[:4])}")
        if strategy.get("measurement_window"):
            lines.append(f"- 观察窗口: {strategy.get('measurement_window')}")
        metrics = strategy.get("validation_metrics", []) or []
        if metrics:
            lines.append(f"- 验证指标: {'；'.join(metrics[:2])}")
        triggers = strategy.get("investment_triggers", []) or []
        if triggers:
            lines.append(f"- 加预算触发点: {'；'.join(triggers[:2])}")
        if strategy.get("stale_points"):
            lines.append(f"- 需避开: {'；'.join(strategy.get('stale_points', [])[:2])}")
        lines.append(f"- 学习存档: {ret.get('memory_path', '')}")
        await send_long_message(update.effective_chat.id, "\n".join(lines), context)

    @requires_auth
    @with_typing
    async def cmd_xhs(self, update, context):
        topic = " ".join(context.args or []).strip()
        if not topic:
            await update.message.reply_text("📕 小红书热点发布中...")
            ret = await execution_hub.autopost_hot_content("xiaohongshu")
            package = (ret.get("results", {}) or {}).get("xiaohongshu", {})
            if not package:
                await update.message.reply_text(error_service_failed("小红书热点发布", package.get('error', ret.get('error', ''))))
                return
            published = package.get("published", {}) or {}
            if not published.get("success"):
                await update.message.reply_text(
                    f"小红书发布未完成: {published.get('error', published.get('raw', '未知错误'))}"
                    f"{self._social_login_retry_hint(published, '/post_xhs')}"
                )
                return
            text = format_social_published(
                platform="xiaohongshu",
                topic=package.get("topic", ""),
                url=published.get("url", ""),
                title=package.get("title", ""),
                memory_path=package.get("memory_path", ""),
            )
            if package.get("trend_label"):
                text = f" 📈 蹭热点: {package.get('trend_label')}\n{text}"
            await send_long_message(update.effective_chat.id, text, context)
            return

        await update.message.reply_text(f"📕 小红书发布: {topic}")
        ret = await execution_hub.autopost_topic_content("xiaohongshu", topic)
        if not ret.get("success"):
            await update.message.reply_text(
                error_service_failed("小红书发帖", ret.get('error', ''))
                + f"\n{self._social_login_retry_hint(ret.get('published', ret), '/post_xhs ' + topic if topic else '/post_xhs')}"
            )
            return
        published = ret.get("published", {}) or {}
        if not published.get("success"):
            await update.message.reply_text(
                f"小红书发布未完成: {published.get('error', published.get('raw', '未知错误'))}"
                f"{self._social_login_retry_hint(published, '/post_xhs ' + topic if topic else '/post_xhs')}"
            )
            return
        text = format_social_published(
            platform="xiaohongshu",
            topic=topic,
            url=published.get("url", ""),
            title=ret.get("title", ""),
            memory_path=ret.get("memory_path", ""),
        )
        await send_long_message(update.effective_chat.id, text, context)

    @requires_auth
    @with_typing
    async def cmd_post(self, update, context):
        topic = " ".join(context.args or []).strip()
        if not topic:
            await self.cmd_hotpost(update, context)
            return
        await update.message.reply_text(f"📱 双平台发文: {topic}")
        xhs = await execution_hub.autopost_topic_content("xiaohongshu", topic)
        xret = await execution_hub.autopost_topic_content("x", topic)
        mem = xhs.get('memory_path') or xret.get('memory_path') or ''
        hint = self._social_login_retry_hint(xhs.get('published', xhs), f"/post {topic}") or self._social_login_retry_hint(xret.get('published', xret), f"/post {topic}")
        text = format_social_dual_result(
            topic=topic,
            xhs_result=xhs,
            x_result=xret,
            memory_path=mem,
        )
        if hint:
            text += f"\n{hint.strip()}"
        await send_long_message(update.effective_chat.id, text, context)

    @requires_auth
    @with_typing
    async def cmd_hotpost(self, update, context):
        args = context.args or []
        platform = "all"
        topic = ""
        preview_mode = False

        # 解析参数：支持 --preview 预览模式
        filtered_args = []
        for a in args:
            if a.lower() in {"--preview", "-p", "preview"}:
                preview_mode = True
            else:
                filtered_args.append(a)
        args = filtered_args

        # 用户偏好：如果设置了 social_preview=True，默认预览模式
        if not preview_mode:
            try:
                from src.bot.globals import user_prefs
                if user_prefs.get(update.effective_user.id, "social_preview", False):
                    preview_mode = True
            except Exception:
                logger.debug("Silenced exception", exc_info=True)

        if args and str(args[0]).lower() in {"x", "xhs", "xiaohongshu", "all", "both", "dual"}:
            raw_platform = str(args[0]).lower()
            platform = "xiaohongshu" if raw_platform in {"xhs", "xiaohongshu"} else raw_platform
            topic = " ".join(args[1:]).strip()
        else:
            topic = " ".join(args).strip()

        if preview_mode:
            # 预览模式 — 搬运自 ConversationHandler 向导模式
            # 生成内容但不发布，用户确认后才发
            await update.message.reply_text("🔥 生成内容预览中...")
            try:
                package = await execution_hub.create_hot_social_package(
                    platform=platform, topic=topic,
                )
                if not package or not package.get("results"):
                    await update.message.reply_text(
                        error_service_failed("内容生成", package.get('error', '') if package else '无结果'))
                    return

                # 构建预览文本
                preview_lines = ["📝 <b>发文预览</b>\n"]
                results = package.get("results", {})
                for plat, content in results.items():
                    icon = "𝕏" if plat == "x" else "📕"
                    if isinstance(content, dict):
                        title = content.get("title", "")
                        body = content.get("body", "") or content.get("text", "")
                        if title:
                            preview_lines.append(f"{icon} <b>{plat}</b>\n标题: {title}\n{body[:300]}{'...' if len(body) > 300 else ''}\n")
                        else:
                            preview_lines.append(f"{icon} <b>{plat}</b>\n{body[:300]}{'...' if len(body) > 300 else ''}\n")
                    elif isinstance(content, str):
                        preview_lines.append(f"{icon} <b>{plat}</b>\n{content[:300]}{'...' if len(content) > 300 else ''}\n")

                preview_lines.append("━━━━━━━━━━━━━━━")
                preview_lines.append("确认发布？点击下方按钮")

                # 存储 package 到 user_data，等待确认
                context.user_data["pending_social_package"] = package

                from telegram import InlineKeyboardButton, InlineKeyboardMarkup
                keyboard = InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton("✅ 确认发布", callback_data="social_confirm:publish"),
                        InlineKeyboardButton("❌ 取消", callback_data="social_confirm:cancel"),
                    ],
                    [
                        InlineKeyboardButton("🔄 重新生成", callback_data="social_confirm:regenerate"),
                    ],
                ])
                from telegram.constants import ParseMode
                await update.message.reply_text(
                    "\n".join(preview_lines),
                    parse_mode=ParseMode.HTML,
                    reply_markup=keyboard,
                )
            except Exception as e:
                from src.telegram_ux import send_error_with_retry
                await send_error_with_retry(update, context, e, retry_command="/hot --preview " + topic)
            return

        # 非预览模式 — 直接发布（原有逻辑）
        if topic:
            await update.message.reply_text(f"🔥 抓取「{topic}」热点并发文...")
        else:
            await update.message.reply_text("🔥 抓取今日热点并发文...")

        ret = await execution_hub.autopost_hot_content(platform=platform, topic=topic)
        if not ret.get("results"):
            await update.message.reply_text(format_error(ret.get('error', '未知错误'), "热点发文"))
            return

        # A/B 测试追踪 — 记录发布的内容变体
        try:
            from src.bot.globals import ab_test_manager
            if ab_test_manager:
                for plat, plat_result in (ret.get("results") or {}).items():
                    content = plat_result.get("content", "") or plat_result.get("title", "")
                    if content:
                        test = ab_test_manager.create_test(
                            name=f"hotpost_{plat}_{(topic or 'auto')[:20]}",
                            contents=[content],
                        )
                        variant_id, _ = ab_test_manager.get_content(test.test_id)
                        if plat_result.get("published", {}).get("success"):
                            ab_test_manager.record_engagement(test.test_id, variant_id, event="publish")
        except Exception:
            logger.debug("Silenced exception", exc_info=True)  # A/B 追踪不影响主流程

        hint = self._social_login_retry_hint(
            (ret.get("results", {}) or {}).get("xiaohongshu", {}).get("published", {}), "/hot"
        ) or self._social_login_retry_hint(
            (ret.get("results", {}) or {}).get("x", {}).get("published", {}), "/hot"
        )
        text = format_hotpost_result(
            topic=ret.get("topic", topic or "自动选题"),
            trend_label=ret.get("trend_label", ""),
            results=ret.get("results", {}),
            login_hint=hint or "",
        )
        await send_long_message(update.effective_chat.id, text, context)

    @requires_auth
    @with_typing
    async def cmd_social_plan(self, update, context):
        topic = " ".join(context.args or []).strip()
        if topic:
            await update.message.reply_text(f"正在生成题材发文计划：{topic}")
        else:
            await update.message.reply_text("正在生成今日社媒发文计划...")
        ret = await execution_hub.build_social_plan(topic=topic, limit=3)
        if not ret.get("success"):
            await update.message.reply_text(format_error(ret.get('error', '未知错误'), "生成发文计划"))
            return
        if ret.get("mode") == "topic":
            strategy = ret.get("strategy", {}) or {}
            lines = [f"社媒发文计划 | {ret.get('topic', topic)}", ""]
            lines.append(f"- 定位: {strategy.get('positioning', 'OpenClaw 实操内容')}" )
            if strategy.get("x_tactic"):
                lines.append(f"- X: {strategy.get('x_tactic')}")
            if strategy.get("xhs_tactic"):
                lines.append(f"- 小红书: {strategy.get('xhs_tactic')}")
            if strategy.get("cta"):
                lines.append(f"- CTA: {strategy.get('cta')}")
            if strategy.get("measurement_window"):
                lines.append(f"- 观察窗口: {strategy.get('measurement_window')}")
            for action in (ret.get("next_actions", []) or [])[:2]:
                lines.append(f"- 下一步: {action}")
            await send_long_message(update.effective_chat.id, "\n".join(lines), context)
            return

        lines = ["今日社媒发文计划", ""]
        for idx, item in enumerate((ret.get("plans", []) or [])[:3], 1):
            lines.append(f"{idx}. {item.get('topic', '')} | {item.get('trend_label', '')}")
            if item.get("hook"):
                lines.append(f"   切角: {item.get('hook')}")
            if item.get("x_tactic"):
                lines.append(f"   X: {item.get('x_tactic')}")
            if item.get("xhs_tactic"):
                lines.append(f"   小红书: {item.get('xhs_tactic')}")
        lines.append("")
        lines.append("下一步: /social_repost <题材> 或 /post_social <题材>")
        await send_long_message(update.effective_chat.id, "\n".join(lines), context)

    @requires_auth
    @with_typing
    async def cmd_social_repost(self, update, context):
        topic = " ".join(context.args or []).strip()
        if topic:
            await update.message.reply_text(f"正在生成双平台改写草稿：{topic}")
        else:
            await update.message.reply_text("正在把今日热点改写成双平台草稿...")
        ret = await execution_hub.build_social_repost_bundle(topic=topic)
        if not ret.get("success"):
            await update.message.reply_text(format_error(ret.get('error', '未知错误'), "双平台改写"))
            return
        lines = [f"双平台改写 | {ret.get('topic', topic or '自动选题')}", ""]
        for name in ["xiaohongshu", "x"]:
            package = (ret.get("results", {}) or {}).get(name, {}) or {}
            label = "小红书" if name == "xiaohongshu" else "X"
            if package.get("success"):
                if package.get("draft_id"):
                    lines.append(f"- {label}草稿ID: {package.get('draft_id')}")
                if package.get("title"):
                    lines.append(f"- {label}标题: {package.get('title')}")
                lines.append(f"- {label}预览: {str(package.get('body', '') or '')[:88]}")
            else:
                lines.append(f"- {error_service_failed(label, package.get('error', ''))}")
        lines.append("")
        lines.append(f"下一步: /post_social {ret.get('topic', topic or '').strip()}".rstrip())
        await send_long_message(update.effective_chat.id, "\n".join(lines), context)

    @requires_auth
    @with_typing
    async def cmd_ops(self, update, context):
        args = context.args or []
        if not args:
            from telegram import InlineKeyboardButton, InlineKeyboardMarkup
            keyboard = [
                [InlineKeyboardButton("📝 任务管理", callback_data="ops_task"),
                 InlineKeyboardButton("📊 项目报告", callback_data="ops_project")],
                [InlineKeyboardButton("🔥 热点扫描", callback_data="ops_hot"),
                 InlineKeyboardButton("✍️ 发帖", callback_data="ops_post")],
                [InlineKeyboardButton("📧 邮件", callback_data="ops_email"),
                 InlineKeyboardButton("📝 会议纪要", callback_data="ops_meeting")],
                [InlineKeyboardButton("🏠 生活提醒", callback_data="ops_life"),
                 InlineKeyboardButton("💰 赏金猎人", callback_data="ops_bounty")],
                [InlineKeyboardButton("📺 监控", callback_data="ops_monitor"),
                 InlineKeyboardButton("🔧 开发", callback_data="ops_dev")],
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
                    error_service_failed("开发流程", result.get('error', '')),
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

    @requires_auth
    @with_typing
    async def cmd_xwatch(self, update, context):
        source = " ".join(context.args or []).strip()
        if not source:
            await update.message.reply_text("用法: /xwatch <X合集推文链接>")
            return
        await self._ops_tweet(update, context, ["watch", source])

    @requires_auth
    @with_typing
    async def cmd_xbrief(self, update, context):
        await update.message.reply_text("正在生成 X 博主更新摘要...")
        digest = await execution_hub.generate_x_monitor_brief()
        if not digest:
            await update.message.reply_text("当前没有 X 博主更新，先用 /xwatch 或 /ops monitor addx 添加监控")
            return
        await send_long_message(update.effective_chat.id, digest, context)

    @requires_auth
    @with_typing
    async def cmd_xdraft(self, update, context):
        topic = " ".join(context.args or []).strip()
        await update.message.reply_text("正在生成 X 草稿...")
        ret = await execution_hub.create_social_draft("x", topic=topic, max_items=3)
        if not ret.get("success"):
            await update.message.reply_text(format_error(ret.get('error', '未知错误'), "X 草稿生成"))
            return
        lines = ["X 草稿", ""]
        lines.append(f"草稿ID: {ret.get('draft_id')}")
        if topic:
            lines.append(f"主题: {topic}")
        lines.append(ret.get("body", ""))
        await send_long_message(update.effective_chat.id, "\n".join(lines), context)

    @requires_auth
    @with_typing
    async def cmd_xpost(self, update, context):
        args = context.args or []
        draft_id = 0
        topic = ""
        if args and str(args[0]).isdigit():
            draft_id = int(args[0])
        else:
            topic = " ".join(args).strip()
        if draft_id <= 0:
            draft = await execution_hub.create_social_draft("x", topic=topic, max_items=3)
            if not draft.get("success"):
                await update.message.reply_text(error_service_failed("X 发帖", draft.get('error', '')))
                return
            draft_id = int(draft.get("draft_id", 0) or 0)
        await update.message.reply_text("正在拉起 OpenClaw 专用浏览器并自动发 X...")
        ret = await asyncio.to_thread(execution_hub.publish_social_draft, "x", draft_id)
        if ret.get("success"):
            await update.message.reply_text(f"X 已尝试自动发出，草稿ID: {ret.get('draft_id')}\n页面: {ret.get('url', '')}")
        else:
            await update.message.reply_text(
                f"X 自动发帖未完成: {ret.get('status', ret.get('error', '未知错误'))}\n"
                f"页面: {ret.get('url', '')}"
                f"{self._social_login_retry_hint(ret, '/post_x ' + topic if topic else '/post_x')}"
            )

    @requires_auth
    @with_typing
    async def cmd_xhsdraft(self, update, context):
        topic = " ".join(context.args or []).strip()
        await update.message.reply_text("正在生成小红书草稿...")
        ret = await execution_hub.create_social_draft("xiaohongshu", topic=topic, max_items=5)
        if not ret.get("success"):
            await update.message.reply_text(error_service_failed("小红书草稿", ret.get('error', '')))
            return
        lines = ["小红书草稿", ""]
        lines.append(f"草稿ID: {ret.get('draft_id')}")
        lines.append(f"标题: {ret.get('title', '')}")
        lines.append("")
        lines.append(ret.get("body", ""))
        await send_long_message(update.effective_chat.id, "\n".join(lines), context)

    @requires_auth
    @with_typing
    async def cmd_xhspost(self, update, context):
        args = context.args or []
        draft_id = 0
        topic = ""
        if args and str(args[0]).isdigit():
            draft_id = int(args[0])
        else:
            topic = " ".join(args).strip()
        if draft_id <= 0:
            draft = await execution_hub.create_social_draft("xiaohongshu", topic=topic, max_items=5)
            if not draft.get("success"):
                await update.message.reply_text(error_service_failed("小红书发帖", draft.get('error', '')))
                return
            draft_id = int(draft.get("draft_id", 0) or 0)
        await update.message.reply_text("正在拉起 OpenClaw 专用浏览器并自动发小红书...")
        ret = await asyncio.to_thread(execution_hub.publish_social_draft, "xiaohongshu", draft_id)
        if ret.get("success"):
            await update.message.reply_text(f"小红书已尝试自动发出，草稿ID: {ret.get('draft_id')}\n页面: {ret.get('url', '')}")
        else:
            await update.message.reply_text(
                f"小红书自动发帖未完成: {ret.get('status', ret.get('error', '未知错误'))}\n"
                f"页面: {ret.get('url', '')}"
                f"{self._social_login_retry_hint(ret, '/post_xhs ' + topic if topic else '/post_xhs')}"
            )

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
            await update.message.reply_text(error_service_failed("会议纪要", result.get('error', '')))
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
                await update.message.reply_text(error_service_failed("创建", ret.get('error', '')))
            return

        if sub == "done":
            if not rest:
                await update.message.reply_text("用法: /ops task done <任务ID>")
                return
            try:
                task_id = int(rest[0])
            except Exception:
                await update.message.reply_text("任务ID必须是数字")
                return
            ret = await asyncio.to_thread(execution_hub.update_task_status, task_id, "done")
            if ret.get("success"):
                await update.message.reply_text(f"任务已完成: #{task_id}")
            else:
                await update.message.reply_text(error_service_failed("更新", ret.get('error', '')))
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
                lines.append(
                    f"#{t.get('id')} [{t.get('status')}] P{t.get('priority', 3)} {t.get('title', '')}"
                )
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
                await update.message.reply_text(error_service_failed("添加", ret.get('error', '')))
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
                await update.message.reply_text(error_service_failed("添加", ret.get('error', '')))
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
            except Exception:
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
                    except Exception:
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

    @requires_auth
    @with_typing
    async def cmd_publish(self, update, context):
        """发布内容到社交媒体 — /publish <平台> <视频/图片路径> [标题]"""
        from src.sau_bridge import publish_video, publish_note, get_supported_platforms, format_publish_result, PLATFORMS

        args = context.args or []
        if len(args) < 2:
            platforms = get_supported_platforms()
            help_text = "📤 社媒发布\n\n用法:\n"
            help_text += "  /publish <平台> <文件路径> [标题]\n\n"
            help_text += "支持平台:\n"
            for key, info in platforms.items():
                caps = []
                if info["video"]: caps.append("视频")
                if info["note"]: caps.append("图文")
                help_text += f"  • {key} ({info['name']}) — {'/'.join(caps)}\n"
            help_text += "\n示例:\n  /publish douyin /path/to/video.mp4 我的视频标题"
            await update.message.reply_text(help_text)
            return

        platform = args[0].lower()
        file_path = args[1]
        title = " ".join(args[2:]) if len(args) > 2 else "OpenClaw 自动发布"

        if platform not in PLATFORMS:
            await update.message.reply_text(f"❓ 不支持的平台: {platform}\n支持: {', '.join(PLATFORMS.keys())}")
            return

        await update.message.reply_text(f"📤 正在发布到 {PLATFORMS[platform]['name']}...")

        if file_path.lower().endswith(('.mp4', '.mov', '.avi')):
            result = await publish_video(platform, file_path, title)
        else:
            result = await publish_note(platform, [file_path], title)

        if result.get("success"):
            await update.message.reply_text(f"✅ 发布到 {PLATFORMS[platform]['name']} 成功!")
        else:
            error = result.get("error", result.get("stderr", "未知错误"))
            await update.message.reply_text(f"⚠️ 发布失败: {error[:100]}")

    # ---- 闲鱼 AI 客服控制 ----

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
            except ValueError:
                pass
        days = min(max(days, 1), 90)  # 限制 1-90 天

        try:
            from src.xianyu.xianyu_context import XianyuContextManager
            xctx = XianyuContextManager()

            # 收入汇总
            profit = xctx.get_profit_summary(days=days) if hasattr(xctx, 'get_profit_summary') else {}
            # 今日统计
            today_stats = xctx.daily_stats() if hasattr(xctx, 'daily_stats') else {}
            # 待发货
            pending_ship = xctx.get_pending_shipments() if hasattr(xctx, 'get_pending_shipments') else []

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

            msg = "\n".join(lines)
            await update.message.reply_text(msg, parse_mode="HTML")

        except Exception as e:
            from src.bot.error_messages import error_service_failed
            await update.message.reply_text(error_service_failed("闲鱼报表", str(e)))

    async def cmd_xianyu(self, update, context):
        """闲鱼 AI 客服远程控制"""
        args = (context.args or [])
        action = args[0].lower() if args else "status"

        import subprocess

        LABEL = "ai.openclaw.xianyu"
        PLIST = os.path.expanduser("~/Library/LaunchAgents/ai.openclaw.xianyu.plist")

        if action == "start":
            r = subprocess.run(["launchctl", "load", PLIST], capture_output=True, text=True)
            if r.returncode == 0:
                await update.message.reply_text("🦞 闲鱼 AI 客服已启动")
            else:
                await update.message.reply_text(error_service_failed("服务启动"))

        elif action == "stop":
            r = subprocess.run(["launchctl", "unload", PLIST], capture_output=True, text=True)
            if r.returncode == 0:
                await update.message.reply_text("🔴 闲鱼 AI 客服已停止")
            else:
                await update.message.reply_text(error_service_failed("服务停止"))

        elif action == "reload":
            # 发送 SIGUSR1 热更新 Cookie
            import signal
            r = subprocess.run(["pgrep", "-f", "xianyu_main"], capture_output=True, text=True)
            pids = r.stdout.strip().split()
            if pids:
                for pid in pids:
                    os.kill(int(pid), signal.SIGUSR1)
                await update.message.reply_text(f"🔄 已发送 Cookie 热更新信号 (PID: {', '.join(pids)})")
            else:
                await update.message.reply_text("⚠️ 闲鱼客服进程未运行")

        else:  # status
            r = subprocess.run(["pgrep", "-fl", "xianyu_main"], capture_output=True, text=True)
            if r.stdout.strip():
                lines = r.stdout.strip().split("\n")
                log_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "logs", "com-clawbot-xianyu.stderr.log")
                last_log = ""
                try:
                    with open(log_path) as f:
                        last_lines = f.readlines()[-3:]
                        last_log = "\n".join(l.strip() for l in last_lines)
                except Exception:
                    logger.debug("Silenced exception", exc_info=True)
                msg = f"🟢 闲鱼 AI 客服运行中\n进程: {len(lines)} 个\n\n最近日志:\n{last_log}"
                await update.message.reply_text(msg[:4000])
            else:
                await update.message.reply_text("🔴 闲鱼 AI 客服未运行\n\n发送 /xianyu start 启动")

    # ---- 社媒内容日历 ----

    @requires_auth
    @with_typing
    async def cmd_social_calendar(self, update, context):
        """生成未来 7 天的内容日历"""
        days = 7
        if context.args:
            try:
                days = int(context.args[0])
            except ValueError:
                pass
        await update.message.reply_text(f"📅 正在生成 {days} 天内容日历...")
        result = await execution_hub.generate_content_calendar(days=days)
        if not result.get("success"):
            await update.message.reply_text(format_error(result.get('error', '未知错误'), "生成内容日历"))
            return
        calendar = result.get("calendar", [])
        trending = result.get("trending", [])
        lines = [f"📅 内容日历（{days}天）"]
        if trending:
            lines.append(f"🔥 热点参考: {', '.join(trending[:3])}")
        lines.append("")
        for item in calendar:
            platform = "𝕏" if item.get("platform") == "x" else "📕"
            lines.append(f"Day {item.get('day', '?')} {item.get('time', '')} {platform} {item.get('topic', '')}")
            lines.append(f"  → {item.get('hook', '')}")
        await send_long_message(update.effective_chat.id, "\n".join(lines), context)

    # ---- 社媒发帖效果报告 ----

    @requires_auth
    @with_typing
    async def cmd_social_report(self, update, context):
        """查看社媒发帖效果报告 + A/B 测试数据"""
        days = 7
        if context.args:
            try:
                days = int(context.args[0])
            except ValueError:
                pass
        result = execution_hub.get_post_performance_report(days=days)
        if not result.get("success"):
            await update.message.reply_text(f"❌ 报告生成失败: {result.get('error', '暂无数据')}")
            return
        lines = [f"📊 社媒效果报告（近 {days} 天）", ""]
        for platform, stats in result.get("by_platform", {}).items():
            icon = "𝕏" if platform == "x" else "📕"
            lines.append(f"{icon} {platform}: {stats['posts']} 篇 | ❤️ {stats['likes']} | 💬 {stats['comments']} | 👁 {stats['views']}")
        top = result.get("top_posts", [])
        if top:
            lines.append("\n🏆 Top 帖子:")
            for i, p in enumerate(top[:3], 1):
                lines.append(f"  {i}. [{p['platform']}] ❤️{p['likes']} 💬{p['comments']} {p.get('topic', '')[:30]}")
                if p.get("url"):
                    lines.append(f"     {p['url']}")

        # A/B 测试数据 — 展示活跃测试的效果对比
        try:
            from src.bot.globals import ab_test_manager
            if ab_test_manager:
                active_tests = ab_test_manager.get_active_tests()
                if active_tests:
                    lines.append("\n🧪 A/B 测试:")
                    for test in active_tests[:5]:
                        results_data = ab_test_manager.get_results(test.test_id)
                        if results_data:
                            winner = results_data.get("winner", "")
                            variants = results_data.get("variants", [])
                            status = "✅ 有赢家" if winner else "⏳ 进行中"
                            lines.append(f"  · {test.name} ({status})")
                            for v in variants[:3]:
                                ctr = v.get("ctr", 0)
                                imp = v.get("impressions", 0)
                                clk = v.get("clicks", 0)
                                lines.append(f"    变体{v.get('id', '?')[:6]}: {imp}曝光 {clk}点击 CTR={ctr:.1%}")
        except Exception:
            logger.debug("Silenced exception", exc_info=True)  # A/B 数据不影响主报告

        await send_long_message(update.effective_chat.id, "\n".join(lines), context)

    async def handle_social_confirm_callback(self, update, context):
        """处理社交发文预览的确认/取消/重新生成回调
        搬运自 ConversationHandler 向导模式 — 生成→预览→确认→发布
        """
        query = update.callback_query
        await query.answer()

        # 认证: 仅授权用户可操作
        if not self._is_authorized(update.effective_user.id):
            await query.answer("⛔ 未授权操作", show_alert=True)
            return

        data = query.data
        if not data.startswith("social_confirm:"):
            return

        action = data.split(":")[1]
        package = context.user_data.pop("pending_social_package", None)

        if action == "cancel":
            await query.edit_message_text("❌ 已取消发布。")
            return

        if action == "regenerate":
            await query.edit_message_text("🔄 重新生成中...")
            # 重新触发 /hot --preview
            context.args = ["--preview"]
            await self.cmd_hotpost(update, context)
            return

        if action == "publish":
            if not package:
                await query.edit_message_text("⚠️ 预览已过期，请重新执行 /hot --preview")
                return

            await query.edit_message_text("📤 正在发布...")
            try:
                ret = execution_hub._publish_social_package(package)
                if ret and ret.get("success"):
                    await query.edit_message_text(
                        "✅ 发布成功\n\n" +
                        "\n".join(
                            f"{'𝕏' if p == 'x' else '📕'} {p}: {r.get('url', '已发布')}"
                            for p, r in (ret.get("results") or {}).items()
                        )
                    )
                else:
                    error = ret.get("error", "未知错误") if ret else "无返回"
                    await query.edit_message_text(f"⚠️ 发布失败: {error}")
            except Exception as e:
                await query.edit_message_text(format_error(e, "发布内容"))

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
            "ops_task":    (["task", "top"],    "📝 加载任务 Top3..."),
            "ops_project": (["project"],        "📊 生成项目报告..."),
            "ops_hot":     (None,               None),  # 直接走 cmd_hotpost
            "ops_post":    (None,               None),  # 直接走 cmd_post
            "ops_email":   (["email"],           "📧 整理邮箱..."),
            "ops_meeting": (None,               "📝 请发送: /ops meeting <会议文本>"),
            "ops_life":    (["life", "remind"],  "🏠 请发送: /ops life remind <分钟> <内容>"),
            "ops_bounty":  (["bounty", "run"],   "💰 启动赏金猎人..."),
            "ops_monitor": (["monitor", "list"], "📺 加载监控列表..."),
            "ops_dev":     (["dev"],             "🔧 启动开发流程..."),
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

    # ---- 闲鱼卡券自动发货管理 ----

    @requires_auth
    @with_typing
    async def cmd_ship(self, update, context):
        """闲鱼卡券管理 — /ship <子命令>"""
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
                f"📊 发货统计:\n"
                f"  今日发货: {stats['today_shipped']}\n"
                f"  累计发货: {stats['total_shipped']}"
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

    # ---- AI 小说工坊 (novel_writer) ----

    @requires_auth
    async def cmd_novel(self, update, context):
        """AI小说写作 — /novel <子命令>"""
        from src.novel_writer import get_novel_writer
        
        writer = get_novel_writer()
        args = context.args or []
        sub = args[0] if args else "help"
        user_id = update.effective_user.id if update.effective_user else 0
        
        if sub == "help" or sub == "帮助":
            help_text = (
                "📖 AI 小说工坊\n\n"
                "子命令:\n"
                "  /novel new <题材> [风格] — 创建新小说\n"
                "  /novel continue <ID> — 续写下一章\n"
                "  /novel status <ID> — 查看进度\n"
                "  /novel list — 我的小说列表\n"
                "  /novel export <ID> — 导出 TXT\n"
                "  /novel tts <ID> <章节号> — 章节转语音\n\n"
                "示例:\n"
                "  /novel new 都市修仙 轻松搞笑\n"
                "  /novel new 末日生存\n"
                "  /novel continue 1"
            )
            await update.message.reply_text(help_text)
            return
        
        if sub == "new" or sub == "新建":
            if len(args) < 2:
                await update.message.reply_text("❓ 请指定题材: /novel new <题材> [风格]\n例: /novel new 都市修仙 轻松搞笑")
                return
            genre = args[1]
            style = " ".join(args[2:]) if len(args) > 2 else "轻松有趣"
            await update.message.reply_text(f"📖 正在构思《{genre}》小说，生成大纲中...")
            result = await writer.create_novel(genre, style, user_id)
            if "error" in result:
                await update.message.reply_text(f"⚠️ 创建失败: {result['error']}")
                return
            outline = result.get("outline", {})
            msg = (
                f"📖 新小说创建成功!\n\n"
                f"📕 《{result['title']}》\n"
                f"📝 {result.get('tagline', '')}\n"
                f"🆔 小说ID: {result['novel_id']}\n\n"
            )
            # 显示角色
            chars = outline.get("characters", [])
            if chars:
                msg += "👥 主要角色:\n"
                for c in chars[:5]:
                    msg += f"  • {c.get('name','')} ({c.get('role','')}): {c.get('personality','')}\n"
            # 显示章节数
            total_chapters = sum(len(act.get("chapters", [])) for act in outline.get("acts", []))
            if total_chapters:
                msg += f"\n📋 大纲: {len(outline.get('acts', []))}幕 {total_chapters}章\n"
            msg += f"\n发送 /novel continue {result['novel_id']} 开始写第一章"
            await update.message.reply_text(msg)
            return
        
        if sub == "continue" or sub == "续写":
            if len(args) < 2:
                await update.message.reply_text("❓ 请指定小说ID: /novel continue <ID>")
                return
            try:
                novel_id = int(args[1])
            except ValueError:
                await update.message.reply_text("❓ 小说ID必须是数字")
                return
            await update.message.reply_text("✍️ 正在续写中，请稍候（约30秒）...")
            result = await writer.write_next_chapter(novel_id)
            if "error" in result:
                await update.message.reply_text(f"⚠️ 续写失败: {result['error']}")
                return
            # Telegram 消息长度限制 4096
            content = result["content"]
            header = f"📖 《续写》第{result['chapter_num']}章 {result['title']}\n字数: {result['word_count']}\n\n"
            if len(header + content) > 4000:
                content = content[:3900] + "\n\n...(完整内容请导出 TXT)"
            await update.message.reply_text(header + content)
            return
        
        if sub == "status" or sub == "进度":
            if len(args) < 2:
                await update.message.reply_text("❓ 请指定小说ID: /novel status <ID>")
                return
            try:
                novel_id = int(args[1])
            except ValueError:
                await update.message.reply_text("❓ 小说ID必须是数字")
                return
            status = writer.get_novel_status(novel_id)
            if "error" in status:
                await update.message.reply_text(f"⚠️ {status['error']}")
                return
            msg = (
                f"📖 《{status['title']}》\n"
                f"📝 {status.get('tagline', '')}\n"
                f"🎭 {status['genre']} · {status['style']}\n"
                f"📊 {status['chapters']}章 / {status['total_words']}字\n\n"
            )
            if status["chapter_list"]:
                msg += "章节列表:\n"
                for ch in status["chapter_list"]:
                    msg += f"  第{ch['num']}章 {ch['title']} ({ch['words']}字)\n"
            await update.message.reply_text(msg)
            return
        
        if sub == "list" or sub == "列表":
            novels = writer.list_novels(user_id)
            if not novels:
                await update.message.reply_text("📖 还没有创建过小说\n发送 /novel new <题材> 开始创作")
                return
            msg = "📚 我的小说:\n\n"
            for n in novels:
                msg += f"  #{n['id']} 《{n['title']}》 {n['genre']} — {n['chapters']}章/{n['words']}字\n"
            await update.message.reply_text(msg)
            return
        
        if sub == "export" or sub == "导出":
            if len(args) < 2:
                await update.message.reply_text("❓ 请指定小说ID: /novel export <ID>")
                return
            try:
                novel_id = int(args[1])
            except ValueError:
                await update.message.reply_text("❓ 小说ID必须是数字")
                return
            path = writer.export_txt(novel_id)
            if not path:
                await update.message.reply_text("⚠️ 导出失败（小说不存在或无章节）")
                return
            try:
                with open(path, "rb") as f:
                    await update.message.reply_document(document=f, filename=Path(path).name)
            except Exception as e:
                await update.message.reply_text(f"⚠️ 文件发送失败: {e}")
            return
        
        if sub == "tts":
            if len(args) < 3:
                await update.message.reply_text("❓ 用法: /novel tts <小说ID> <章节号>")
                return
            try:
                novel_id = int(args[1])
                chapter_num = int(args[2])
            except ValueError:
                await update.message.reply_text("❓ ID和章节号必须是数字")
                return
            # 获取章节内容
            status = writer.get_novel_status(novel_id)
            if "error" in status:
                await update.message.reply_text(f"⚠️ {status['error']}")
                return
            # 读取章节
            with writer._conn() as conn:
                ch = conn.execute(
                    "SELECT content FROM chapters WHERE novel_id=? AND chapter_num=?",
                    (novel_id, chapter_num)
                ).fetchone()
            if not ch:
                await update.message.reply_text(f"⚠️ 第{chapter_num}章不存在")
                return
            await update.message.reply_text(f"🎤 正在将第{chapter_num}章转为语音...")
            from src.tools.tts_tool import text_to_speech
            audio = await text_to_speech(ch["content"][:5000])
            if audio:
                try:
                    with open(audio, "rb") as f:
                        await update.message.reply_voice(voice=f)
                    Path(audio).unlink(missing_ok=True)
                except Exception as e:
                    await update.message.reply_text(f"⚠️ 音频发送失败")
            else:
                await update.message.reply_text("⚠️ 语音生成失败")
            return
        
        await update.message.reply_text(f"❓ 未知子命令: {sub}\n发送 /novel help 查看帮助")
