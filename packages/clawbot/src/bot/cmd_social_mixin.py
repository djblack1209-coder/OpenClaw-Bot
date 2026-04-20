"""
Bot — 社媒发布 / 热点 / 人设 / 日历 命令 Mixin

包含功能:
  - 社媒发布 (X / 小红书 / 双平台)
  - 热点选题与 AI 草稿
  - 社媒人设管理
  - 社媒日历与报表
  - 预览确认回调
"""

import asyncio
import logging

from src.bot.globals import execution_hub, send_long_message, image_tool, get_siliconflow_key
from src.message_format import format_error
from src.bot.error_messages import error_service_failed
from src.bot.auth import requires_auth
from src.telegram_ux import with_typing
from src.constants import IMG_MODEL_FLUX
from src.notify_style import (
    format_social_published, format_social_dual_result,
    format_hotpost_result,
)

logger = logging.getLogger(__name__)


class SocialCommandsMixin:
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
        try:
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
        except Exception as e:
            logger.warning("[cmd_social_persona] 执行失败: %s", e)
            try:
                await update.message.reply_text("⚠️ 命令执行失败，请稍后重试")
            except Exception as e:
                logger.debug("消息发送失败: %s", e)

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
            image_ret = await image_tool.generate(generation_prompt, model=IMG_MODEL_FLUX, size=str(image_payload.get("size", "1024x1024") or "1024x1024"))
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
    @with_typing
    async def cmd_topic(self, update, context):
        try:
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
        except Exception as e:
            logger.warning("[cmd_topic] 执行失败: %s", e)
            try:
                await update.message.reply_text("⚠️ 命令执行失败，请稍后重试")
            except Exception as e:
                logger.debug("消息发送失败: %s", e)

    @requires_auth
    @with_typing
    async def cmd_xhs(self, update, context):
        try:
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
        except Exception as e:
            logger.warning("[cmd_xhs] 执行失败: %s", e)
            try:
                await update.message.reply_text("⚠️ 命令执行失败，请稍后重试")
            except Exception as e:
                logger.debug("消息发送失败: %s", e)

    @requires_auth
    @with_typing
    async def cmd_post(self, update, context):
        try:
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
        except Exception as e:
            logger.warning("[cmd_post] 执行失败: %s", e)
            try:
                await update.message.reply_text("⚠️ 命令执行失败，请稍后重试")
            except Exception as e:
                logger.debug("消息发送失败: %s", e)

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
        try:
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
        except Exception as e:
            logger.warning("[cmd_social_plan] 执行失败: %s", e)
            try:
                await update.message.reply_text("⚠️ 命令执行失败，请稍后重试")
            except Exception as e:
                logger.debug("消息发送失败: %s", e)

    @requires_auth
    @with_typing
    async def cmd_social_repost(self, update, context):
        try:
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
        except Exception as e:
            logger.warning("[cmd_social_repost] 执行失败: %s", e)
            try:
                await update.message.reply_text("⚠️ 命令执行失败，请稍后重试")
            except Exception as e:
                logger.debug("消息发送失败: %s", e)


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
        try:
            await update.message.reply_text("正在生成 X 博主更新摘要...")
            digest = await execution_hub.generate_x_monitor_brief()
            if not digest:
                await update.message.reply_text("当前没有 X 博主更新，先用 /xwatch 或 /ops monitor addx 添加监控")
                return
            await send_long_message(update.effective_chat.id, digest, context)
        except Exception as e:
            logger.warning("[cmd_xbrief] 执行失败: %s", e)
            try:
                await update.message.reply_text("⚠️ 命令执行失败，请稍后重试")
            except Exception as e:
                logger.debug("消息发送失败: %s", e)

    @requires_auth
    @with_typing
    async def cmd_xdraft(self, update, context):
        try:
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
        except Exception as e:
            logger.warning("[cmd_xdraft] 执行失败: %s", e)
            try:
                await update.message.reply_text("⚠️ 命令执行失败，请稍后重试")
            except Exception as e:
                logger.debug("消息发送失败: %s", e)

    @requires_auth
    @with_typing
    async def cmd_xpost(self, update, context):
        try:
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
        except Exception as e:
            logger.warning("[cmd_xpost] 执行失败: %s", e)
            try:
                await update.message.reply_text("⚠️ 命令执行失败，请稍后重试")
            except Exception as e:
                logger.debug("消息发送失败: %s", e)

    @requires_auth
    @with_typing
    async def cmd_xhsdraft(self, update, context):
        try:
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
        except Exception as e:
            logger.warning("[cmd_xhsdraft] 执行失败: %s", e)
            try:
                await update.message.reply_text("⚠️ 命令执行失败，请稍后重试")
            except Exception as e:
                logger.debug("消息发送失败: %s", e)

    @requires_auth
    @with_typing
    async def cmd_xhspost(self, update, context):
        try:
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
        except Exception as e:
            logger.warning("[cmd_xhspost] 执行失败: %s", e)
            try:
                await update.message.reply_text("⚠️ 命令执行失败，请稍后重试")
            except Exception as e:
                logger.debug("消息发送失败: %s", e)

    @requires_auth
    @with_typing
    async def cmd_publish(self, update, context):
        """发布内容到社交媒体 — /publish <平台> <视频/图片路径> [标题]"""
        try:
            from src.sau_bridge import publish_video, publish_note, get_supported_platforms, PLATFORMS

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
        except Exception as e:
            logger.warning("[cmd_publish] 执行失败: %s", e)
            try:
                await update.message.reply_text("⚠️ 命令执行失败，请稍后重试")
            except Exception as e:
                logger.debug("消息发送失败: %s", e)

    # ---- 闲鱼 AI 客服控制 ----

    @requires_auth
    @with_typing
    async def cmd_social_calendar(self, update, context):
        """生成/查看内容日历，支持 /social_calendar done N 标记完成"""
        args = context.args or []

        # 子命令: /social_calendar done 3 — 标记第3天已完成
        if args and args[0].lower() == "done":
            day_offset = 1
            if len(args) > 1:
                try:
                    day_offset = int(args[1])
                except ValueError as e:  # noqa: F841
                    logger.debug("用户输入解析失败: %s", e)
            result = execution_hub.mark_calendar_done(day_offset=day_offset)
            if result.get("success"):
                await update.message.reply_text(
                    f"✅ 第 {day_offset} 天（{result.get('date', '')}）已标记完成，"
                    f"更新 {result.get('updated', 0)} 条"
                )
            else:
                await update.message.reply_text(f"❌ {result.get('error', '标记失败')}")
            return

        days = 7
        if args:
            try:
                days = int(args[0])
            except ValueError as e:  # noqa: F841
                logger.debug("用户输入解析失败: %s", e)

        # 先查DB已有计划
        result = await execution_hub.generate_content_calendar(days=days)
        if not result.get("success"):
            await update.message.reply_text(format_error(result.get('error', '未知错误'), "生成内容日历"))
            return

        # 如果是从数据库返回的已有计划
        if result.get("from_db"):
            items = result.get("calendar_items", [])
            lines = [f"📅 内容日历（{days}天，已有计划）"]
            lines.append("")
            status_icon = {"planned": "⬜", "drafted": "📝", "published": "✅", "skipped": "⏭"}
            for item in items:
                icon = status_icon.get(item.get("status", "planned"), "⬜")
                plat = "𝕏" if item.get("platform") == "x" else ("📕" if item.get("platform") == "xhs" else "📱")
                time_str = item.get("scheduled_time", "")
                lines.append(
                    f"{icon} {item.get('plan_date', '')} {time_str} {plat} "
                    f"{item.get('topic', '')} [{item.get('content_type', '')}]"
                )
            lines.append("")
            lines.append("💡 用 /social_calendar done N 标记第N天已完成")
            await send_long_message(update.effective_chat.id, "\n".join(lines), context)
            return

        # AI 新生成的日历
        calendar = result.get("calendar", result.get("days", []))
        trending = result.get("trending", [])
        lines = [f"📅 内容日历（{days}天，新生成）"]
        if trending:
            lines.append(f"🔥 热点参考: {', '.join(trending[:3])}")
        lines.append("")
        for item in calendar:
            platform = "𝕏" if item.get("platform") == "x" else "📕"
            lines.append(f"Day {item.get('day', item.get('date', '?'))} {item.get('time', '')} {platform} {item.get('topic', '')}")
            lines.append(f"  → {item.get('hook', item.get('type', ''))}")
        lines.append("")
        lines.append("💡 用 /social_calendar done N 标记第N天已完成")
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
            except ValueError as e:  # noqa: F841
                logger.debug("用户输入解析失败: %s", e)
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

