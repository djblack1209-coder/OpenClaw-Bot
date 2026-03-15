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

    async def cmd_hot(self, update, context):
        await self.cmd_hotpost(update, context)

    async def cmd_post_social(self, update, context):
        await self.cmd_post(update, context)

    async def cmd_post_x(self, update, context):
        await self.cmd_xpost(update, context)

    async def cmd_post_xhs(self, update, context):
        await self.cmd_xhspost(update, context)

    async def cmd_social_persona(self, update, context):
        if not self._is_authorized(update.effective_user.id):
            return
        ret = await asyncio.to_thread(execution_hub.get_social_persona_summary)
        if not ret.get("success"):
            await update.message.reply_text(f"社媒人设读取失败: {ret.get('error', '未知错误')}")
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

    async def cmd_social_launch(self, update, context):
        if not self._is_authorized(update.effective_user.id):
            return
        await update.message.reply_text("正在生成数字生命首发包并写入草稿...")
        ret = await asyncio.to_thread(execution_hub.create_social_launch_drafts)
        if not ret.get("success"):
            await update.message.reply_text(f"首发包读取失败: {ret.get('error', '未知错误')}")
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
                lines.append(f"- 自拍生成失败: {image_ret.get('error', '未知错误')}")
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

    async def cmd_dev(self, update, context):
        if not self._is_authorized(update.effective_user.id):
            return
        args = ["dev", *(context.args or [])]
        context.args = args
        await self.cmd_ops(update, context)

    async def cmd_brief(self, update, context):
        if not self._is_authorized(update.effective_user.id):
            return
        await update.message.reply_text("正在生成执行简报...")
        brief = await execution_hub.generate_daily_brief()
        await send_long_message(update.effective_chat.id, brief, context)

    async def cmd_lane(self, update, context):
        if not self._is_authorized(update.effective_user.id):
            return
        await self.cmd_lanes(update, context)

    async def cmd_cost(self, update, context):
        if not self._is_authorized(update.effective_user.id):
            return
        lines = ["成本 / 配额状态", ""]
        lines.append("请求节流:")
        lines.append(f"- 群聊 LLM 路由: {'开' if os.getenv('CHAT_ROUTER_ENABLE_GROUP_LLM', 'false').lower() in {'1','true','yes','on'} else '关'}")
        lines.append(f"- 群聊意图自动回复: {'开' if os.getenv('CHAT_ROUTER_ENABLE_GROUP_INTENT', 'false').lower() in {'1','true','yes','on'} else '关'}")
        lines.append(f"- 群聊兜底轮换: {'开' if os.getenv('CHAT_ROUTER_ENABLE_GROUP_FALLBACK', 'false').lower() in {'1','true','yes','on'} else '关'}")
        lines.append(f"- 自动交易仅保留成交通知: {'开' if os.getenv('AUTO_TRADE_NOTIFY_ONLY_FILLS', 'false').lower() in {'1','true','yes','on'} else '关'}")
        lines.append("")
        usage_rows = token_budget.get_all_status()
        if usage_rows:
            lines.append("今日 Token:")
            for bot_id, status in sorted(usage_rows.items()):
                lines.append(
                    f"- {bot_id}: {status.get('total_tokens', 0):,}/{status.get('daily_limit', 0):,} ({status.get('usage_pct', '0%')})"
                )
        else:
            lines.append("今日 Token: 暂无记录")
        lines.append("")
        rl_rows = rate_limiter.get_all_status()
        if rl_rows:
            lines.append("最近请求:")
            for bot_id, status in sorted(rl_rows.items()):
                lines.append(
                    f"- {bot_id}: min {status.get('requests_last_minute', 0)} / hour {status.get('requests_last_hour', 0)} / day {status.get('requests_today', 0)}"
                )
        else:
            lines.append("最近请求: 暂无记录")
        await send_long_message(update.effective_chat.id, "\n".join(lines), context)

    async def cmd_config(self, update, context):
        if not self._is_authorized(update.effective_user.id):
            return
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

    async def cmd_topic(self, update, context):
        if not self._is_authorized(update.effective_user.id):
            return
        topic = " ".join(context.args or []).strip() or "AI出海"
        await update.message.reply_text(f"正在研究题材：{topic}")
        ret = await execution_hub.research_social_topic(topic, limit=5)
        if not ret.get("success"):
            await update.message.reply_text(f"题材研究失败: {ret.get('error', '未知错误')}")
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

    async def cmd_xhs(self, update, context):
        if not self._is_authorized(update.effective_user.id):
            return
        topic = " ".join(context.args or []).strip()
        if not topic:
            await update.message.reply_text("正在拉起 OpenClaw 专用浏览器并一键发布小红书...")
            ret = await execution_hub.autopost_hot_content("xiaohongshu")
            package = (ret.get("results", {}) or {}).get("xiaohongshu", {})
            if not package:
                await update.message.reply_text(f"小红书热点自动发布失败: {package.get('error', ret.get('error', '未知错误'))}")
                return
            published = package.get("published", {}) or {}
            if not published.get("success"):
                await update.message.reply_text(
                    f"小红书发布未完成: {published.get('error', published.get('raw', '未知错误'))}"
                    f"{self._social_login_retry_hint(published, '/post_xhs')}"
                )
                return
            lines = [f"小红书已发布 | {package.get('topic', '')}", ""]
            lines.append(f"蹭热点: {package.get('trend_label', '')}")
            lines.append(f"标题: {package.get('title', '')}")
            lines.append(f"链接: {published.get('url', '')}")
            lines.append(f"学习存档: {package.get('memory_path', '')}")
            await send_long_message(update.effective_chat.id, "\n".join(lines), context)
            return

        await update.message.reply_text(f"正在拉起 OpenClaw 专用浏览器并发布小红书：{topic}")
        ret = await execution_hub.autopost_topic_content("xiaohongshu", topic)
        if not ret.get("success"):
            await update.message.reply_text(
                f"小红书自动发布失败: {ret.get('error', '未知错误')}"
                f"{self._social_login_retry_hint(ret.get('published', ret), '/post_xhs ' + topic if topic else '/post_xhs')}"
            )
            return
        published = ret.get("published", {}) or {}
        if not published.get("success"):
            await update.message.reply_text(
                f"小红书发布未完成: {published.get('error', published.get('raw', '未知错误'))}"
                f"{self._social_login_retry_hint(published, '/post_xhs ' + topic if topic else '/post_xhs')}"
            )
            return
        lines = [f"小红书已发布 | {topic}", ""]
        lines.append(f"标题: {ret.get('title', '')}")
        lines.append(f"链接: {published.get('url', '')}")
        lines.append(f"学习存档: {ret.get('memory_path', '')}")
        await send_long_message(update.effective_chat.id, "\n".join(lines), context)

    async def cmd_post(self, update, context):
        if not self._is_authorized(update.effective_user.id):
            return
        topic = " ".join(context.args or []).strip()
        if not topic:
            await self.cmd_hotpost(update, context)
            return
        await update.message.reply_text(f"正在拉起 OpenClaw 专用浏览器并双平台发文：{topic}")
        xhs = await execution_hub.autopost_topic_content("xiaohongshu", topic)
        xret = await execution_hub.autopost_topic_content("x", topic)
        lines = [f"双平台发文 | {topic}", ""]
        if xhs.get("published", {}).get("success"):
            lines.append(f"- 小红书: {xhs.get('published', {}).get('url', '')}")
        else:
            lines.append(f"- 小红书失败: {xhs.get('published', {}).get('error', xhs.get('error', '未知错误'))}")
        if xret.get("published", {}).get("success"):
            lines.append(f"- X: {xret.get('published', {}).get('url', '')}")
        else:
            lines.append(f"- X失败: {xret.get('published', {}).get('error', xret.get('error', '未知错误'))}")
        mem = xhs.get('memory_path') or xret.get('memory_path') or ''
        if mem:
            lines.append(f"- 学习存档: {mem}")
        hint = self._social_login_retry_hint(xhs.get('published', xhs), f"/post_social {topic}") or self._social_login_retry_hint(xret.get('published', xret), f"/post_social {topic}")
        if hint:
            lines.append(hint.strip())
        await send_long_message(update.effective_chat.id, "\n".join(lines), context)

    async def cmd_hotpost(self, update, context):
        if not self._is_authorized(update.effective_user.id):
            return
        args = context.args or []
        platform = "all"
        topic = ""
        if args and str(args[0]).lower() in {"x", "xhs", "xiaohongshu", "all", "both", "dual"}:
            raw_platform = str(args[0]).lower()
            platform = "xiaohongshu" if raw_platform in {"xhs", "xiaohongshu"} else raw_platform
            topic = " ".join(args[1:]).strip()
        else:
            topic = " ".join(args).strip()

        if topic:
            await update.message.reply_text(f"正在拉起 OpenClaw 专用浏览器，抓取“{topic}”相关热点并一键发文...")
        else:
            await update.message.reply_text("正在拉起 OpenClaw 专用浏览器，抓取今日热点并一键发文，默认优先 OpenClaw 实用教学...")

        ret = await execution_hub.autopost_hot_content(platform=platform, topic=topic)
        if not ret.get("results"):
            await update.message.reply_text(f"热点发文失败: {ret.get('error', '未知错误')}")
            return

        lines = [f"热点一键发文 | {ret.get('topic', topic or '自动选题')}", ""]
        if ret.get("trend_label"):
            lines.append(f"蹭热点: {ret.get('trend_label')}")
        for name in ["xiaohongshu", "x"]:
            package = (ret.get("results", {}) or {}).get(name)
            if not package:
                continue
            published = package.get("published", {}) or {}
            label = "小红书" if name == "xiaohongshu" else "X"
            if published.get("success"):
                lines.append(f"- {label}: {published.get('url', '')}")
            else:
                lines.append(f"- {label}失败: {published.get('error', package.get('error', '未知错误'))}")
        hint = self._social_login_retry_hint((ret.get("results", {}) or {}).get("xiaohongshu", {}).get("published", {}), "/hot") or self._social_login_retry_hint((ret.get("results", {}) or {}).get("x", {}).get("published", {}), "/hot")
        if hint:
            lines.append(hint.strip())
        await send_long_message(update.effective_chat.id, "\n".join(lines), context)

    async def cmd_social_plan(self, update, context):
        if not self._is_authorized(update.effective_user.id):
            return
        topic = " ".join(context.args or []).strip()
        if topic:
            await update.message.reply_text(f"正在生成题材发文计划：{topic}")
        else:
            await update.message.reply_text("正在生成今日社媒发文计划...")
        ret = await execution_hub.build_social_plan(topic=topic, limit=3)
        if not ret.get("success"):
            await update.message.reply_text(f"社媒发文计划生成失败: {ret.get('error', '未知错误')}")
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

    async def cmd_social_repost(self, update, context):
        if not self._is_authorized(update.effective_user.id):
            return
        topic = " ".join(context.args or []).strip()
        if topic:
            await update.message.reply_text(f"正在生成双平台改写草稿：{topic}")
        else:
            await update.message.reply_text("正在把今日热点改写成双平台草稿...")
        ret = await execution_hub.build_social_repost_bundle(topic=topic)
        if not ret.get("success"):
            await update.message.reply_text(f"双平台改写失败: {ret.get('error', '未知错误')}")
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
                lines.append(f"- {label}失败: {package.get('error', '未知错误')}")
        lines.append("")
        lines.append(f"下一步: /post_social {ret.get('topic', topic or '').strip()}".rstrip())
        await send_long_message(update.effective_chat.id, "\n".join(lines), context)

    async def cmd_ops(self, update, context):
        if not self._is_authorized(update.effective_user.id):
            return

        args = context.args or []
        if not args:
            await update.message.reply_text(self._ops_help())
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
                    f"开发流程失败: {result.get('error', '未知错误')}",
                    context,
                )
                return

            lines = ["开发流程结果", ""]
            for i, step in enumerate(result.get("steps", []), 1):
                ok = "OK" if step.get("ok") else "FAIL"
                lines.append(f"[{i}] {ok} {step.get('command', '')}")
                out = (step.get("stdout", "") or "").strip()
                err = (step.get("stderr", "") or "").strip()
                if out:
                    lines.append(f"stdout: {out[:300]}")
                if err:
                    lines.append(f"stderr: {err[:300]}")
                lines.append("")
            await send_long_message(update.effective_chat.id, "\n".join(lines).strip(), context)
            return

        await update.message.reply_text("未知子命令，请使用 /ops help")

    async def cmd_xwatch(self, update, context):
        if not self._is_authorized(update.effective_user.id):
            return
        source = " ".join(context.args or []).strip()
        if not source:
            await update.message.reply_text("用法: /xwatch <X合集推文链接>")
            return
        await self._ops_tweet(update, context, ["watch", source])

    async def cmd_xbrief(self, update, context):
        if not self._is_authorized(update.effective_user.id):
            return
        await update.message.reply_text("正在生成 X 博主更新摘要...")
        digest = await execution_hub.generate_x_monitor_brief()
        if not digest:
            await update.message.reply_text("当前没有 X 博主更新，先用 /xwatch 或 /ops monitor addx 添加监控")
            return
        await send_long_message(update.effective_chat.id, digest, context)

    async def cmd_xdraft(self, update, context):
        if not self._is_authorized(update.effective_user.id):
            return
        topic = " ".join(context.args or []).strip()
        await update.message.reply_text("正在生成 X 草稿...")
        ret = await execution_hub.create_social_draft("x", topic=topic, max_items=3)
        if not ret.get("success"):
            await update.message.reply_text(f"X 草稿生成失败: {ret.get('error', '未知错误')}")
            return
        lines = ["X 草稿", ""]
        lines.append(f"草稿ID: {ret.get('draft_id')}")
        if topic:
            lines.append(f"主题: {topic}")
        lines.append(ret.get("body", ""))
        await send_long_message(update.effective_chat.id, "\n".join(lines), context)

    async def cmd_xpost(self, update, context):
        if not self._is_authorized(update.effective_user.id):
            return
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
                await update.message.reply_text(f"X 自动发帖失败: {draft.get('error', '未知错误')}")
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

    async def cmd_xhsdraft(self, update, context):
        if not self._is_authorized(update.effective_user.id):
            return
        topic = " ".join(context.args or []).strip()
        await update.message.reply_text("正在生成小红书草稿...")
        ret = await execution_hub.create_social_draft("xiaohongshu", topic=topic, max_items=5)
        if not ret.get("success"):
            await update.message.reply_text(f"小红书草稿生成失败: {ret.get('error', '未知错误')}")
            return
        lines = ["小红书草稿", ""]
        lines.append(f"草稿ID: {ret.get('draft_id')}")
        lines.append(f"标题: {ret.get('title', '')}")
        lines.append("")
        lines.append(ret.get("body", ""))
        await send_long_message(update.effective_chat.id, "\n".join(lines), context)

    async def cmd_xhspost(self, update, context):
        if not self._is_authorized(update.effective_user.id):
            return
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
                await update.message.reply_text(f"小红书自动发帖失败: {draft.get('error', '未知错误')}")
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
            await update.message.reply_text(f"会议纪要生成失败: {result.get('error', '未知错误')}")
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
                await update.message.reply_text(f"创建失败: {ret.get('error', '未知错误')}")
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
                await update.message.reply_text(f"更新失败: {ret.get('error', '未知错误')}")
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
                await update.message.reply_text(f"添加失败: {ret.get('error', '未知错误')}")
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
                await update.message.reply_text(f"添加失败: {ret.get('error', '未知错误')}")
            return

        if sub == "list":
            rows = await asyncio.to_thread(execution_hub.list_monitors)
            if not rows:
                await update.message.reply_text("当前没有监控项")
                return
            lines = ["监控列表", ""]
            for r in rows:
                state = "ON" if int(r.get("enabled", 0) or 0) == 1 else "OFF"
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
                await update.message.reply_text(f"创建失败: {ret.get('error', '未知错误')}")
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
            "/ops xianyu start|stop|status|reload - 闲鱼 AI 客服控制"
        )

    # ---- 闲鱼 AI 客服控制 ----

    async def cmd_xianyu(self, update, context):
        """闲鱼 AI 客服远程控制"""
        if not self._is_authorized(update.effective_user.id):
            return
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
                await update.message.reply_text(f"❌ 启动失败: {r.stderr.strip()}")

        elif action == "stop":
            r = subprocess.run(["launchctl", "unload", PLIST], capture_output=True, text=True)
            if r.returncode == 0:
                await update.message.reply_text("🔴 闲鱼 AI 客服已停止")
            else:
                await update.message.reply_text(f"❌ 停止失败: {r.stderr.strip()}")

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
                log_path = os.path.expanduser("~/Desktop/OpenClaw Bot/clawbot/logs/com-clawbot-xianyu.stderr.log")
                last_log = ""
                try:
                    with open(log_path) as f:
                        last_lines = f.readlines()[-3:]
                        last_log = "\n".join(l.strip() for l in last_lines)
                except Exception:
                    pass
                msg = f"🟢 闲鱼 AI 客服运行中\n进程: {len(lines)} 个\n\n最近日志:\n{last_log}"
                await update.message.reply_text(msg[:4000])
            else:
                await update.message.reply_text("🔴 闲鱼 AI 客服未运行\n\n发送 /xianyu start 启动")

    # ---- 社媒内容日历 ----

    async def cmd_social_calendar(self, update, context):
        """生成未来 7 天的内容日历"""
        if not self._is_authorized(update.effective_user.id):
            return
        days = 7
        if context.args:
            try:
                days = int(context.args[0])
            except ValueError:
                pass
        await update.message.reply_text(f"📅 正在生成 {days} 天内容日历...")
        result = await execution_hub.generate_content_calendar(days=days)
        if not result.get("success"):
            await update.message.reply_text(f"❌ 生成失败: {result.get('error', '未知错误')}")
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
        await send_long_message(update, "\n".join(lines))

    # ---- 社媒发帖效果报告 ----

    async def cmd_social_report(self, update, context):
        """查看社媒发帖效果报告"""
        if not self._is_authorized(update.effective_user.id):
            return
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
        await send_long_message(update, "\n".join(lines))
