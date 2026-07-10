"""
ClawBot RPC Bridge
搬运自 freqtrade/rpc/rpc.py 模式
统一的业务逻辑聚合层 — API 和 Telegram 共享同一套方法

Design principles:
  1. Every method is @staticmethod — no instance state, easy to call from anywhere
  2. Lazy imports inside each method — avoids circular dependency hell
  3. Every external call wrapped in try/except — one broken subsystem never crashes the API
  4. Sync methods for fast reads, async methods only when calling async subsystems
"""

import json
import logging
import os
import re
import time
from datetime import UTC
from pathlib import Path

logger = logging.getLogger(__name__)

_PACKAGE_ROOT = Path(__file__).resolve().parents[2]
_SOCIAL_EXTENSION_STATUS_FILE = Path(
    os.getenv(
        "OPENCLAW_SOCIAL_EXTENSION_STATUS_FILE",
        str(_PACKAGE_ROOT / "data" / "social_extension_status.json"),
    )
)
_SOCIAL_EXTENSION_PLATFORMS = {"x", "xhs", "xianyu", "unsupported"}
_SOCIAL_EXTENSION_SETTING_KEYS = {
    "strategyPreset",
    "personaTags",
    "contentModel",
    "imageModel",
    "trendSources",
    "automationLevel",
    "interactionLevel",
    "apiBaseUrl",
}

_SOCIAL_EXTENSION_DRAFT_PLATFORMS = {"x", "xhs", "xianyu"}
_SOCIAL_STRATEGY_PRESETS = {
    "auto_mcn_growth",
    "x_wealth_frontier",
    "x_absurd_growth",
    "xhs_lifestyle_tutorial",
    "xianyu_deal_closer",
}

_SOCIAL_STRATEGY_PRESET_META = {
    "auto_mcn_growth": {
        "label": "自动匹配平台涨粉打法",
        "short_label": "自动匹配",
        "platform_style": "按当前平台自动选择 X 财富前沿 / 小红书生活攻略 / 闲鱼成交客服",
        "audience": "按平台切换：X 年轻创业者，小红书生活方式，闲鱼交易用户",
        "growth_loop": "先按平台最佳实践生成待审内容，再用增长复盘调整下一轮选题权重。",
        "content_focus": "少参数 no-code，优先让插件识别当前页面并套用平台默认打法。",
    },
    "x_wealth_frontier": {
        "label": "X 财富前沿实操",
        "short_label": "财富前沿",
        "platform_style": "X 年轻创业者热点实操短帖",
        "audience": "大学生 / 年轻创业者 / 出海 / AI 工具 / Web3 人群",
        "growth_loop": "收藏率优先：前沿信息差 + 3步可执行清单 + 风险边界，复盘高收藏话题。",
        "content_focus": "把中英文热点拆成可执行清单、工具路线、机会观察和低风险讨论。",
    },
    "x_absurd_growth": {
        "label": "X 抽象热点涨粉",
        "short_label": "抽象热点",
        "platform_style": "X 抽象热点涨粉短帖",
        "audience": "大学生 / 年轻打工人 / 年轻创业者 / 抽象梗用户",
        "growth_loop": "评论率优先：抽象梗开场 + 现实反差 + 低门槛接梗问题，复盘高回复梗。",
        "content_focus": "追热点但不复读新闻，用反差、梗和年轻人真实处境提高评论率。",
    },
    "xhs_lifestyle_tutorial": {
        "label": "小红书生活攻略",
        "short_label": "生活攻略",
        "platform_style": "小红书女性向生活攻略图文",
        "audience": "女性生活方式用户 / 学生党 / 收藏型用户",
        "growth_loop": "收藏率优先：封面结果感 + 步骤清单 + 评论区补材料，后续复盘高收藏标题。",
        "content_focus": "把热点包装成夏日饮品、生活教程、省钱清单、健身/穿搭等可收藏图文。",
    },
    "xianyu_deal_closer": {
        "label": "闲鱼成交客服",
        "short_label": "成交客服",
        "platform_style": "闲鱼成交话术与商品优化",
        "audience": "闲鱼买家 / 卖家 / 学生党 / 二手数码用户",
        "growth_loop": "成交率优先：提高回复速度、降低疑虑、记录高转化话术，不做站外导流。",
        "content_focus": "把商品/聊天信号转成标题优化、砍价回复、成色证据和温和催拍话术。",
    },
}

_SOCIAL_STRATEGY_PLATFORM_DEFAULTS = {
    "x": "x_wealth_frontier",
    "twitter": "x_wealth_frontier",
    "xhs": "xhs_lifestyle_tutorial",
    "xiaohongshu": "xhs_lifestyle_tutorial",
    "xianyu": "xianyu_deal_closer",
}


def _default_social_extension_status() -> dict:
    """返回 Chrome 社媒插件的安全默认状态。"""
    return {
        "success": True,
        "source": "chrome_extension",
        "online": False,
        "running": False,
        "platform": "unsupported",
        "url": "",
        "detected_platform": {"id": "unsupported", "label": "未识别页面", "supported": False},
        "settings": {},
        "tasks": [],
        "extension": {
            "manifest_version": "",
            "cc_delivery_helper_version": "",
            "capabilities": {},
        },
        "page_calibration": {},
        "auto_publish_enabled": False,
        "external_actions_locked": True,
        "updated_at": "",
    }


def _load_social_extension_status(path: Path = _SOCIAL_EXTENSION_STATUS_FILE) -> dict:
    """读取 Chrome 社媒插件状态；读取失败时保持离线安全态。"""
    default = _default_social_extension_status()
    if not path.exists():
        default["strategy_summary"] = _social_strategy_summary(default.get("settings"), default.get("platform", "x"))
        return default
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        logger.debug("读取 Chrome 社媒插件状态失败: %s", e)
        default["strategy_summary"] = _social_strategy_summary(default.get("settings"), default.get("platform", "x"))
        return default
    if not isinstance(data, dict):
        default["strategy_summary"] = _social_strategy_summary(default.get("settings"), default.get("platform", "x"))
        return default
    default.update(data)
    default["success"] = True
    if not isinstance(default.get("page_calibration"), dict):
        default["page_calibration"] = {}
    default["auto_publish_enabled"] = False
    default["external_actions_locked"] = True
    default["strategy_summary"] = _social_strategy_summary(default.get("settings"), default.get("platform", "x"))
    return default


def _sanitize_social_extension_payload(payload: dict) -> dict:
    """只保留插件状态白名单字段，避免落盘密钥或任意外部输入。"""
    if not isinstance(payload, dict):
        payload = {}
    detected = payload.get("detected_platform") if isinstance(payload.get("detected_platform"), dict) else {}
    platform = str(payload.get("platform") or detected.get("id") or "unsupported").strip().lower()
    if platform not in _SOCIAL_EXTENSION_PLATFORMS:
        platform = "unsupported"

    settings_in = payload.get("settings") if isinstance(payload.get("settings"), dict) else {}
    settings: dict = {}
    for key in _SOCIAL_EXTENSION_SETTING_KEYS:
        value = settings_in.get(key)
        if isinstance(value, list):
            settings[key] = [str(item)[:80] for item in value[:12]]
        elif isinstance(value, (str, int, float, bool)):
            settings[key] = str(value)[:240] if not isinstance(value, bool) else value
    preset = str(settings.get("strategyPreset") or "auto_mcn_growth").strip()
    settings["strategyPreset"] = preset if preset in _SOCIAL_STRATEGY_PRESETS else "auto_mcn_growth"

    tasks_in = payload.get("tasks") if isinstance(payload.get("tasks"), list) else []
    tasks = [str(item)[:160] for item in tasks_in[:8]]
    extension_in = payload.get("extension") if isinstance(payload.get("extension"), dict) else {}
    capabilities_in = extension_in.get("capabilities") if isinstance(extension_in.get("capabilities"), dict) else {}
    capability_keys = {
        "xianyu_delivery_scan",
        "xianyu_delivery_send",
        "current_chat_watch",
        "all_open_xianyu_tabs_watch",
        "target_tab_preflight",
        "single_pending_global_gate",
        "background_heartbeat",
        "xianyu_confirm_shipment",
        "xianyu_relist_item",
        "relist_queue_watch",
        "paid_page_dispatch",
    }
    capabilities = {key: bool(capabilities_in.get(key)) for key in capability_keys}

    return {
        "success": True,
        "source": "chrome_extension",
        "online": True,
        "running": bool(payload.get("running", False)),
        "platform": platform,
        "url": str(payload.get("url") or "")[:500],
        "detected_platform": {
            "id": platform,
            "label": str(detected.get("label") or platform)[:80],
            "host": str(detected.get("host") or "")[:120],
            "supported": bool(detected.get("supported", platform != "unsupported")),
            "tone": str(detected.get("tone") or "")[:160],
        },
        "settings": settings,
        "strategy_summary": _social_strategy_summary(settings, platform),
        "tasks": tasks,
        "extension": {
            "manifest_version": _bounded_str(extension_in.get("manifest_version"), 32),
            "cc_delivery_helper_version": _bounded_str(extension_in.get("cc_delivery_helper_version"), 80),
            "capabilities": capabilities,
        },
        "auto_publish_enabled": False,
        "external_actions_locked": True,
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    }


def _save_social_extension_status(status: dict, path: Path = _SOCIAL_EXTENSION_STATUS_FILE) -> None:
    """持久化 Chrome 社媒插件状态。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and isinstance(status, dict):
        try:
            current = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            current = {}
        current_extension = (
            current.get("extension")
            if isinstance(current, dict) and isinstance(current.get("extension"), dict)
            else {}
        )
        next_extension = status.get("extension") if isinstance(status.get("extension"), dict) else {}
        next_capabilities = (
            next_extension.get("capabilities")
            if isinstance(next_extension.get("capabilities"), dict)
            else {}
        )
        has_next_capability = any(bool(value) for value in next_capabilities.values())
        has_next_version = bool(next_extension.get("manifest_version") or next_extension.get("cc_delivery_helper_version"))
        if current_extension and not has_next_capability and not has_next_version:
            status["extension"] = current_extension
    path.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")


def _sanitize_social_extension_probe_payload(payload: dict) -> dict:
    """规整 Chrome 插件页面填入点探测结果，只保留安全摘要。"""
    if not isinstance(payload, dict):
        payload = {}
    platform = str(payload.get("platform") or "unsupported").strip().lower()
    if platform in {"twitter"}:
        platform = "x"
    if platform in {"xiaohongshu"}:
        platform = "xhs"
    if platform not in _SOCIAL_EXTENSION_DRAFT_PLATFORMS:
        platform = "unsupported"

    raw_fields = payload.get("availableFields") or payload.get("available_fields")
    if not isinstance(raw_fields, list):
        raw_fields = []
    fields: list[dict] = []
    for field in raw_fields[:8]:
        if not isinstance(field, dict):
            continue
        fields.append({
            "name": _bounded_str(field.get("name"), 40),
            "kind": _bounded_str(field.get("kind"), 40),
            "tag": _bounded_str(field.get("tag"), 24),
        })
    ready = bool(payload.get("ready", bool(fields)))
    reason = _bounded_str(payload.get("reason") or ("" if ready else "no_supported_input_found"), 120)
    return {
        "success": True,
        "source": "chrome_extension_page_probe",
        "platform": platform,
        "url": _bounded_str(payload.get("url"), 500),
        "ready": ready,
        "field_names": [field["name"] for field in fields if field.get("name")],
        "available_fields": fields,
        "reason": reason,
        "auto_publish_enabled": False,
        "external_actions_locked": True,
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    }



def _bounded_metric_int(value, max_value: int = 999_999_999) -> int:
    """把网页可见指标规整为非负整数，支持 12K / 1.2万 / 128。"""
    if isinstance(value, bool):
        return 0
    if isinstance(value, (int, float)):
        if value != value:  # NaN
            return 0
        return max(0, min(max_value, round(value)))
    raw = str(value or "").strip().lower().replace(",", "")
    if not raw:
        return 0
    match = re.search(r"([0-9]+(?:\.[0-9]+)?)(\s*[kmw万])?", raw)
    if not match:
        return 0
    number = float(match.group(1))
    suffix = (match.group(2) or "").strip().lower()
    if suffix == "k":
        number *= 1_000
    elif suffix == "m":
        number *= 1_000_000
    elif suffix in {"w", "万"}:
        number *= 10_000
    return max(0, min(max_value, round(number)))


def _sanitize_social_performance_payload(payload: dict) -> dict:
    """规整插件只读表现采集结果；只写增长复盘，不触发外部动作。"""
    if not isinstance(payload, dict):
        payload = {}
    performance = payload.get("performance") if isinstance(payload.get("performance"), dict) else {}
    platform = str(payload.get("platform") or performance.get("platform") or "x").strip().lower()
    if platform == "twitter":
        platform = "x"
    if platform == "xiaohongshu":
        platform = "xhs"
    if platform not in _SOCIAL_EXTENSION_DRAFT_PLATFORMS:
        platform = "x"

    raw_metrics = performance.get("metrics") if isinstance(performance.get("metrics"), dict) else {}
    likes = _bounded_metric_int(raw_metrics.get("likes"))
    comments = _bounded_metric_int(raw_metrics.get("comments") or raw_metrics.get("replies"))
    shares = _bounded_metric_int(raw_metrics.get("shares") or raw_metrics.get("reposts") or raw_metrics.get("retweets"))
    impressions = _bounded_metric_int(raw_metrics.get("impressions") or raw_metrics.get("views"))
    saves = _bounded_metric_int(raw_metrics.get("saves") or raw_metrics.get("collects"))
    followers = _bounded_metric_int(raw_metrics.get("followers") or raw_metrics.get("fans"))
    engagements = _bounded_metric_int(raw_metrics.get("engagements")) or likes + comments + shares + saves
    engagement_rate = round(engagements / impressions, 6) if impressions else 0
    outcome = _bounded_str(performance.get("outcome"), 40)
    if not outcome:
        outcome = "high_signal" if impressions >= 10_000 or likes >= 100 or comments >= 10 else "baseline"
    learning = _bounded_str(performance.get("learning"), 300)
    if not learning:
        learning = (
            "继续放大当前 hook、选题标签和可执行步骤；下一条复用同类结构。"
            if outcome == "high_signal"
            else "作为基线记录，下一条优先强化开头、标题利益点和互动问题。"
        )
    tags_raw = performance.get("tags") if isinstance(performance.get("tags"), list) else []
    return {
        "source": "chrome_extension_performance_snapshot",
        "platform": platform,
        "draft_id": _bounded_str(payload.get("draft_id") or performance.get("draft_id"), 120),
        "url": _bounded_str(performance.get("url") or payload.get("url"), 500),
        "title": _bounded_str(performance.get("title") or payload.get("title"), 160),
        "metrics": {
            "likes": likes,
            "comments": comments,
            "shares": shares,
            "impressions": impressions,
            "saves": saves,
            "followers": followers,
            "engagements": engagements,
            "engagement_rate": engagement_rate,
        },
        "tags": [_bounded_str(item, 40) for item in tags_raw[:8] if _bounded_str(item, 40)],
        "note": _bounded_str(performance.get("note"), 220),
        "outcome": outcome,
        "learning": learning,
        "captured_at": _bounded_str(performance.get("captured_at"), 80) or time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "recorded_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "auto_publish_enabled": False,
        "external_actions_locked": True,
        "publishIntent": False,
    }

def _bounded_str(value, limit: int) -> str:
    """把外部传入文本规整为单行安全摘要。"""
    return " ".join(str(value or "").split())[:limit]


def _social_strategy_summary(settings: dict | None, platform: str = "x") -> dict:
    """把插件 no-code 运营打法设置整理成 App/Telegram 可读摘要。"""
    safe_settings = settings if isinstance(settings, dict) else {}
    platform_key = str(platform or "x").strip().lower()
    raw_preset = _bounded_str(safe_settings.get("strategyPreset"), 80) or "auto_mcn_growth"
    if raw_preset not in _SOCIAL_STRATEGY_PRESETS:
        raw_preset = "auto_mcn_growth"
    effective_preset = raw_preset
    if raw_preset == "auto_mcn_growth":
        effective_preset = _SOCIAL_STRATEGY_PLATFORM_DEFAULTS.get(platform_key, "x_wealth_frontier")
    meta = dict(_SOCIAL_STRATEGY_PRESET_META.get(effective_preset, _SOCIAL_STRATEGY_PRESET_META["x_wealth_frontier"]))
    label = _SOCIAL_STRATEGY_PRESET_META.get(raw_preset, meta).get("label", meta.get("label", effective_preset))
    persona_tags = safe_settings.get("personaTags") if isinstance(safe_settings.get("personaTags"), list) else []
    return {
        "preset": raw_preset,
        "effective_preset": effective_preset,
        "label": label,
        "short_label": meta.get("short_label", label),
        "platform": platform_key,
        "platform_style": meta.get("platform_style", "平台化热点运营"),
        "audience": meta.get("audience", "按平台匹配目标人群"),
        "growth_loop": meta.get("growth_loop", "先审核内容，再用表现反哺下一轮选题。"),
        "content_focus": meta.get("content_focus", "追热点但不自动外发。"),
        "persona_tags": [_bounded_str(item, 40) for item in persona_tags[:8] if _bounded_str(item, 40)],
        "review_required": True,
        "auto_publish_enabled": False,
        "external_actions_locked": True,
    }


def _extension_page_context(payload: dict) -> dict:
    """提取插件当前页上下文，只保留可用于选题的短文本。"""
    raw = payload.get("page_context") if isinstance(payload.get("page_context"), dict) else {}
    headings = raw.get("headings") if isinstance(raw.get("headings"), list) else []
    trends = raw.get("trends") if isinstance(raw.get("trends"), list) else []
    return {
        "title": _bounded_str(raw.get("title") or payload.get("title"), 160),
        "selection": _bounded_str(raw.get("selection"), 800),
        "bodyText": _bounded_str(raw.get("bodyText"), 1200),
        "headings": [_bounded_str(item, 120) for item in headings[:8] if _bounded_str(item, 120)],
        "trends": [_bounded_str(item, 80) for item in trends[:12] if _bounded_str(item, 80)],
    }


def _extension_topic_from_context(context: dict, fallback: str) -> str:
    """从当前页上下文中提取最适合做草稿标题的主题。"""
    for key in ("selection", "title"):
        value = _bounded_str(context.get(key), 90)
        if value:
            return value
    for key in ("trends", "headings"):
        items = context.get(key) if isinstance(context.get(key), list) else []
        if items:
            return _bounded_str(items[0], 90)
    body = _bounded_str(context.get("bodyText"), 90)
    return body or fallback


def _extension_compose_draft(platform: str, topic: str, context: dict, settings: dict, url: str) -> dict:
    """基于插件当前页信号生成待审草稿；不调用外部模型、不发布。"""
    tags = settings.get("personaTags") if isinstance(settings.get("personaTags"), list) else []
    persona = " / ".join(str(tag) for tag in tags[:3]) or "热点观察"
    trends = context.get("trends") if isinstance(context.get("trends"), list) else []
    trend_line = "、".join(trends[:3]) if trends else "当前页信号"
    time.strftime("%Y-%m-%dT%H:%M:%S%z")

    if platform == "xhs":
        title = _bounded_str(topic if "夏日" in topic or "教程" in topic else f"今天这个话题值得收藏：{topic}", 28)
        body = "\n\n".join([
            f"家人们，刚在当前页刷到「{topic}」，我觉得可以做成一篇很轻松的图文攻略。",
            f"适合人设：{persona}。",
            f"可用热点信号：{trend_line}。",
            "建议结构：1）先给结论 2）列 3 个步骤 3）配一张统一风格封面 4）最后引导收藏。",
            "⚠️ 这只是待审草稿，发布前请确认标题、封面和敏感词。",
        ])
        return {"title": title, "body": body, "text": f"{title}\n\n{body}"}

    if platform == "xianyu":
        title = _bounded_str(f"闲鱼成交优化：{topic}", 48)
        body = "\n".join([
            f"当前商品/聊天线索：{topic}",
            "运营建议：先判断买家意图，再用「价格锚点 + 使用场景 + 小让步」回复。",
            f"可用信号：{trend_line}。",
            "待审回复：这个价格我已经压得比较低了，如果你今天能拍，我可以帮你优先发出/包好一点。",
        ])
        return {"title": title, "body": body, "text": body}

    title = _bounded_str(topic, 80)
    text = "\n".join([
        f"我会把「{topic}」当成今天的一个小机会信号，而不是新闻本身。",
        f"可执行角度：从 {trend_line} 里挑一个最有反差/最有钱味/最能引发评论的问题。",
        "写法：先一句抓人标题，再给 3 个可操作步骤，最后留一个低风险讨论问题。",
        f"人设：{persona}。",
        "⚠️ 待审草稿：不要写收益承诺，不要变成投资建议。",
    ])
    return {"title": title, "body": text, "text": text}


def _extension_content_asset_plan(platform: str, topic: str, context: dict, settings: dict) -> dict:
    """为插件草稿生成平台化内容计划和素材计划；只给提示词，不自动生图。"""
    tags = settings.get("personaTags") if isinstance(settings.get("personaTags"), list) else []
    persona = " / ".join(str(tag) for tag in tags[:3]) or "热点观察"
    trends = context.get("trends") if isinstance(context.get("trends"), list) else []
    trend_line = "、".join(_bounded_str(item, 40) for item in trends[:3] if _bounded_str(item, 40)) or "当前页热点信号"
    clean_topic = _bounded_str(topic, 90) or "当前话题"
    content_model = _bounded_str(settings.get("contentModel"), 80) or "web-gemini"
    image_model = _bounded_str(settings.get("imageModel"), 80) or "gpt-image"
    strategy_preset = _bounded_str(settings.get("strategyPreset"), 80) or "auto_mcn_growth"
    if strategy_preset not in _SOCIAL_STRATEGY_PRESETS:
        strategy_preset = "auto_mcn_growth"
    if strategy_preset == "auto_mcn_growth":
        strategy_preset = {
            "x": "x_wealth_frontier",
            "xhs": "xhs_lifestyle_tutorial",
            "xianyu": "xianyu_deal_closer",
        }.get(platform, "x_wealth_frontier")
    prefer_web_quota = content_model.startswith("web-") or image_model.startswith("web-")

    base_safety = [
        "不自动发布、发送、评论、点赞、关注或取关",
        "发布前人工确认标题、正文、图片和敏感词",
        "不使用 Cookie 绕过或平台风控规避话术",
        "遵守平台规则，不做刷量、诱导互动或自动化骚扰",
    ]
    cost_route = {
        "content_model": content_model,
        "image_model": image_model,
        "prefer_web_quota": prefer_web_quota,
        "model_route_hint": "优先使用已登录网页额度；API Key 仅作为人工确认后的备用生成通道",
    }

    if platform == "xhs":
        return {
            "platform_style": "小红书女性向生活攻略图文",
            "content_plan": {
                "format": "xhs_note",
                "strategy_preset": strategy_preset,
                "audience": "女性生活方式用户 / 学生党 / 收藏型用户",
                "hook": f"家人们，这个「{clean_topic}」真的建议夏天收藏",
                "growth_loop": "收藏率优先：封面结果感 + 步骤清单 + 评论区补材料，后续复盘高收藏标题。",
                "structure": [
                    "标题直给结果：3 分钟/低成本/可收藏",
                    "开头用生活化共鸣，不要像新闻摘要",
                    "正文拆成 3-5 步教程，步骤短、可照做",
                    "结尾加收藏引导和低风险话题互动",
                ],
                "topic_signal": trend_line,
                "persona": persona,
            },
            "image_plan": {
                "auto_generate": False,
                "image_model": image_model,
                "cover_prompt": (
                    f"小红书封面图，主题「{clean_topic}」，夏日清爽生活方式，明亮自然光，"
                    "精致饮品/桌面教程氛围，3:4 构图，留出中文大标题区域，干净高级，不含真实品牌 Logo"
                ),
                "asset_prompts": [
                    f"步骤图：围绕「{clean_topic}」展示材料清单，清爽浅色背景，适合小红书图文教程",
                    "过程图：3-5 个步骤分镜，手作生活感，画面统一，不出现夸张功效承诺",
                    "收尾图：成品展示 + 收藏提示，和封面保持同一色调，适合女性向生活攻略",
                ],
                "visual_style": "明亮、干净、可收藏、茶饮/生活方式品牌感",
            },
            "format_checklist": [
                "标题 20 字左右，先给结果再给情绪",
                "正文含 3-5 个步骤和 emoji，但不堆砌",
                "封面提示词和正文主题一致",
                "发布前人工确认图片、标题、正文和敏感词",
            ],
            "safety_checklist": [
                *base_safety,
                "不写医疗、减肥、功效或绝对化承诺",
                "不盗用茶颜悦色/霸王茶姬等真实品牌 Logo 或商标元素",
            ],
            "cost_route": cost_route,
        }

    if platform == "xianyu":
        return {
            "platform_style": "闲鱼成交话术与商品优化",
            "content_plan": {
                "format": "xianyu_reply_or_listing",
                "strategy_preset": strategy_preset,
                "audience": "闲鱼买家 / 卖家 / 学生党 / 二手数码用户",
                "hook": f"这个买家的真实需求可能是：{clean_topic}",
                "growth_loop": "成交率优先：提高回复速度、降低疑虑、记录高转化话术，不做站外导流。",
                "structure": [
                    "先判断买家是砍价、催发货还是确认成色",
                    "回复用价格锚点 + 成色证据 + 小让步",
                    "商品标题突出品牌/型号/成色/配件，不堆关键词",
                    "结尾温和引导下单或继续追问需求",
                ],
                "topic_signal": trend_line,
                "persona": persona,
            },
            "image_plan": {
                "auto_generate": False,
                "image_model": image_model,
                "cover_prompt": (
                    f"闲鱼商品图优化建议，主题「{clean_topic}」，真实二手物品拍摄参考，"
                    "白天自然光、清楚展示成色和配件，不生成虚假瑕疵或不存在配件"
                ),
                "asset_prompts": [
                    "商品主图建议：正面、清晰、无遮挡，展示真实成色",
                    "细节图建议：边角、配件、瑕疵位置单独拍摄，不修饰成全新",
                    "发货图建议：包装材料和配件清单，增强信任但不虚构库存",
                ],
                "visual_style": "真实、清楚、可信，不做虚假精修",
            },
            "format_checklist": [
                "回复先回应买家问题，再给成交理由",
                "商品标题包含型号/成色/配件/使用场景",
                "价格让步必须可执行，不写无法兑现承诺",
                "发布前人工确认商品事实和聊天上下文",
            ],
            "safety_checklist": [
                *base_safety,
                "不要虚构成色、配件、保修、物流、库存或原价",
                "不诱导站外交易，不发送联系方式或支付信息",
            ],
            "cost_route": cost_route,
        }

    if strategy_preset == "x_absurd_growth":
        x_style = "X 抽象热点涨粉短帖"
        x_hook = f"最近「{clean_topic}」最抽象的地方：大家不是在讨论热点，是在给焦虑找表情包"
        x_growth_loop = "评论率优先：抽象梗开场 + 现实反差 + 低门槛接梗问题，复盘高回复梗。"
        x_structure = [
            "第一句用抽象梗或反差类比，不复读新闻",
            "第二段把梗落到年轻人真实处境",
            "第三段给 1-3 个轻量可执行动作",
            "结尾留一个容易接梗的评论问题",
        ]
        x_visual_style = "梗图感、克制黑白橙、适合评论区接龙"
    else:
        x_style = "X 年轻创业者热点实操短帖"
        x_hook = f"最近「{clean_topic}」最有意思的地方不是新闻本身，而是机会信号"
        x_growth_loop = "收藏率优先：前沿信息差 + 3步可执行清单 + 风险边界，复盘高收藏话题。"
        x_structure = [
            "第一句给反差 hook，避免新闻复读",
            "中段给 3步 可执行动作或观察清单",
            "补一句风险边界，避免收益承诺",
            "结尾留一个容易被回复的问题",
        ]
        x_visual_style = "高信息密度、克制科技感、适合收藏转发"

    return {
        "platform_style": x_style,
        "content_plan": {
            "format": "x_hotspot_short_post",
            "strategy_preset": strategy_preset,
            "audience": "大学生 / 年轻创业者 / 财富出海 / AI 工具 / Web3 人群",
            "hook": x_hook,
            "growth_loop": x_growth_loop,
            "structure": x_structure,
            "topic_signal": trend_line,
            "persona": persona,
        },
        "image_plan": {
            "auto_generate": False,
            "image_model": image_model,
            "cover_prompt": (
                f"可选信息图封面，主题「{clean_topic}」，黑白橙科技风，3 个行动步骤，"
                "适合 X 贴文配图；默认不强制配图，发布前人工确认"
            ),
            "asset_prompts": [
                f"信息图：把「{clean_topic}」拆成 3 个可执行步骤，适合年轻创业者收藏",
                "对比图：机会信号 vs 风险边界，强调不是投资建议",
            ],
            "visual_style": x_visual_style,
        },
        "format_checklist": [
            "开头 1 句必须有反差或钱味，但不夸大",
            "正文至少 3 个可执行步骤",
            "包含风险边界：不是投资建议/收益承诺",
            "发布前人工确认事实来源和敏感词",
        ],
        "safety_checklist": [
            *base_safety,
            "不构成投资建议，不写确定收益、内幕消息或未经证实爆料",
            "不蹭灾难、战争、枪击、政治口号等高风险热点",
        ],
        "cost_route": cost_route,
    }


def _extension_mcn_operating_card(platform: str, title: str, source: str, tags: list[str], heat_reason: str) -> dict:
    """把热点补成 MCN 选题卡，帮助插件直接判断人群、打法、涨粉点和风险。"""
    text = " ".join([title, source, heat_reason, " ".join(tags)]).lower()
    high_risk_keywords = ("战争", "枪击", "伤亡", "核电", "政治", "选举", "terror", "war")
    medium_risk_keywords = ("美股", "币", "web3", "空投", "暴跌", "银行", "收益", "money", "stock")
    risk_level = "high" if any(keyword in text for keyword in high_risk_keywords) else "medium" if any(keyword in text for keyword in medium_risk_keywords) else "low"

    if platform == "xhs":
        content_angle = "把热点包装成女性向生活攻略、教程清单或可收藏模板"
        if any(keyword in text for keyword in ("冷饮", "美食", "教程", "低卡")):
            content_angle = "做成步骤化图文教程：材料、做法、替代方案和封面提示词"
        return {
            "audience": "女性生活方式 / 学生党 / 收藏型用户",
            "content_angle": content_angle,
            "platform_playbook": "小红书图文：标题直给结果 + 3-5 步教程 + emoji + 收藏引导",
            "growth_reason": "生活攻略和教程类内容更容易获得收藏、搜索长尾和二次转发",
            "risk_level": risk_level,
            "risk_note": "避免医疗/功效承诺，封面和标题不要夸大效果",
            "execution_steps": ["先写收藏型标题", "拆 3-5 个步骤", "生成统一封面提示词", "发布前检查敏感词和品牌调性"],
            "hook_template": "家人们，这个真的建议夏天收藏：",
        }

    if platform == "xianyu":
        return {
            "audience": "闲鱼买家 / 卖家 / 二手数码和学生党",
            "content_angle": "转成商品标题优化、砍价回复或成交话术，不做内容号灌水",
            "platform_playbook": "闲鱼成交：价格锚点 + 成色证据 + 小让步 + 催拍",
            "growth_reason": "提高回复速度和成交确定性，比单纯追热点更适合闲鱼场景",
            "risk_level": risk_level,
            "risk_note": "不要虚构成色、物流、保修或库存",
            "execution_steps": ["提炼买家意图", "给出价格锚点", "补充成色/配件证据", "用温和方式引导下单"],
            "hook_template": "这个买家的真实需求可能是：",
        }

    content_angle = "拆成可执行工具清单、机会观察表或低风险讨论问题"
    if any(keyword in text for keyword in ("github", "工具", "ai", "skill", "codex", "claude")):
        content_angle = "把前沿热点拆成可执行、可收藏、可复盘的工具清单"
    elif any(keyword in text for keyword in ("美股", "stock", "就业", "利率")):
        content_angle = "把市场波动拆成观察清单，不给买卖建议"
    return {
        "audience": "大学生 / 年轻创业者 / 出海与 AI 工具人群",
        "content_angle": content_angle,
        "platform_playbook": "X 短帖：反差开头 + 3 个可执行步骤 + 一个低风险讨论问题",
        "growth_reason": "前沿、赚钱想象和抽象反差更容易触发收藏、转发和评论",
        "risk_level": risk_level,
        "risk_note": "避免收益承诺、投资建议、灾难/政治蹭热点和未经证实爆料",
        "execution_steps": ["先写一句反差 hook", "列 3 个今天能做的小动作", "补一句风险边界", "结尾留一个容易回复的问题"],
        "hook_template": "最近这个热点最有意思的地方不是新闻本身，而是：",
    }


def _extension_seed_to_trend(seed, platform: str) -> dict:
    """把后端热点种子压缩成 Chrome 插件可展示的安全热点卡片。"""
    title = _bounded_str(getattr(seed, "title", ""), 120)
    if not title:
        return {}
    source = _bounded_str(getattr(seed, "source", "") or getattr(seed, "channel", ""), 60)
    tags = getattr(seed, "tags", []) if isinstance(getattr(seed, "tags", []), list) else []
    heat_reason = _bounded_str(getattr(seed, "heat_reason", "") or getattr(seed, "summary", ""), 180)
    language = _bounded_str(getattr(seed, "language", ""), 12)
    raw_score = int(getattr(seed, "raw_score", 0) or 0)
    raw_rank = int(getattr(seed, "raw_rank", 0) or 0)
    platform_label = {"x": "X", "xhs": "小红书", "xianyu": "闲鱼"}.get(platform, "当前平台")
    safe_tags = [_bounded_str(item, 40) for item in tags[:6] if _bounded_str(item, 40)]
    if platform == "xhs":
        call_to_action = "生成女性向/生活化图文草稿"
    elif platform == "xianyu":
        call_to_action = "生成商品优化或砍价回复草稿"
    else:
        call_to_action = "生成 X 热点短帖草稿"
    operating_card = _extension_mcn_operating_card(platform, title, source, safe_tags, heat_reason)
    return {
        "id": _bounded_str(f"{source}:{title}", 180),
        "title": title,
        "source": source or "trend_pool",
        "channel": _bounded_str(getattr(seed, "channel", ""), 80),
        "url": _bounded_str(getattr(seed, "url", ""), 500),
        "language": language,
        "tags": safe_tags,
        "score": raw_score,
        "rank": raw_rank,
        "heat_reason": heat_reason,
        "draft_platform": platform,
        "platform_label": platform_label,
        "call_to_action": call_to_action,
        "safe_for_autopublish": False,
        **operating_card,
    }



def _extension_growth_feedback_profiles(state: dict, platform: str) -> list[dict]:
    """从历史表现快照提取可用于热点重排的高信号画像。"""
    if not isinstance(state, dict):
        return []
    raw_records = state.get("extension_performance") if isinstance(state.get("extension_performance"), list) else []
    profiles: list[dict] = []
    for record in raw_records[-120:]:
        if not isinstance(record, dict):
            continue
        if str(record.get("platform") or "").strip().lower() != platform:
            continue
        metrics = record.get("metrics") if isinstance(record.get("metrics"), dict) else {}
        likes = _bounded_metric_int(metrics.get("likes"))
        comments = _bounded_metric_int(metrics.get("comments"))
        shares = _bounded_metric_int(metrics.get("shares"))
        saves = _bounded_metric_int(metrics.get("saves"))
        impressions = _bounded_metric_int(metrics.get("impressions"))
        high_signal = (
            str(record.get("outcome") or "") == "high_signal"
            or likes >= 100
            or comments >= 10
            or impressions >= 10_000
        )
        if not high_signal:
            continue
        title = _bounded_str(record.get("title"), 120)
        tags = [_bounded_str(item, 40) for item in (record.get("tags") if isinstance(record.get("tags"), list) else [])]
        tags = [item for item in tags if item]
        learning = _bounded_str(record.get("learning"), 180)
        term_source = " ".join([title, learning, " ".join(tags)]).lower()
        ascii_terms = set(re.findall(r"[a-z0-9][a-z0-9_+.#-]{1,}", term_source))
        tag_terms = {tag.lower() for tag in tags if len(tag) >= 2}
        terms = sorted((ascii_terms | tag_terms) - {"https", "http", "com", "news", "the"})[:20]
        if not terms and not title:
            continue
        boost = 420 + min(420, likes + comments * 8 + shares * 12 + saves * 5 + impressions // 800)
        profiles.append({
            "title": title,
            "tags": tags,
            "terms": terms,
            "learning": learning,
            "boost": boost,
            "metrics": {
                "likes": likes,
                "comments": comments,
                "shares": shares,
                "impressions": impressions,
            },
        })
    return profiles[-30:]


def _extension_apply_growth_feedback(trends: list[dict], platform: str, state: dict) -> bool:
    """把历史高信号内容转成热点候选加权；只影响排序，不授权发布。"""
    profiles = _extension_growth_feedback_profiles(state, platform)
    if not profiles:
        for trend in trends:
            trend.setdefault("growth_feedback_boost", 0)
            trend.setdefault("growth_feedback_reason", "")
        return False

    applied = False
    for trend in trends:
        title = _bounded_str(trend.get("title"), 160)
        trend_tags = [_bounded_str(item, 40) for item in (trend.get("tags") if isinstance(trend.get("tags"), list) else [])]
        trend_text = " ".join([
            title,
            _bounded_str(trend.get("source"), 80),
            _bounded_str(trend.get("heat_reason"), 220),
            _bounded_str(trend.get("content_angle"), 220),
            " ".join(trend_tags),
        ]).lower()
        best_boost = 0
        best_reason = ""
        best_terms: list[str] = []
        for profile in profiles:
            matched = [term for term in profile.get("terms", []) if term and term in trend_text]
            profile_title = str(profile.get("title") or "").lower()
            if not matched and profile_title:
                trend_title = title.lower()
                if profile_title in trend_title or trend_title in profile_title:
                    matched = [title[:30] or "title"]
            if not matched:
                continue
            boost = int(profile.get("boost") or 0)
            if boost > best_boost:
                best_boost = boost
                best_terms = matched[:4]
                label = profile.get("title") or " / ".join(profile.get("tags") or []) or "相似选题"
                best_reason = f"历史高信号：{_bounded_str(label, 60)}；匹配 {'/'.join(best_terms)}"
        trend["growth_feedback_boost"] = best_boost
        trend["growth_feedback_reason"] = best_reason
        if best_boost > 0:
            applied = True
    return applied

def _extension_platform_trend_score(trend: dict, platform: str) -> int:
    """按平台给热点排序：插件展示需要少而准，不把所有热榜直接灌给用户。"""
    text = " ".join([
        str(trend.get("title") or ""),
        str(trend.get("source") or ""),
        " ".join(trend.get("tags") or []),
        str(trend.get("heat_reason") or ""),
    ]).lower()
    score = int(trend.get("score") or 0)
    if platform == "x":
        for keyword in ("github", "hn", "ai", "web3", "美股", "创业", "出海", "工具", "money"):
            if keyword.lower() in text:
                score += 200
    elif platform == "xhs":
        for keyword in ("小红书", "生活", "女性", "冷饮", "教程", "学生", "健身", "省钱", "穿搭", "美食"):
            if keyword.lower() in text:
                score += 240
        if str(trend.get("language") or "").lower() == "zh":
            score += 100
    elif platform == "xianyu":
        for keyword in ("闲鱼", "二手", "成交", "商品", "砍价", "省钱", "数码", "租房", "学生"):
            if keyword.lower() in text:
                score += 220
    score += int(trend.get("growth_feedback_boost") or 0)
    return score


def _safe_error(e: Exception) -> str:
    """脱敏异常信息,隐藏内部路径和技术细节"""
    msg = str(e)
    # 移除文件路径
    import re

    msg = re.sub(r"[/\\][\w/\\.-]+\.py", "[内部模块]", msg)
    msg = re.sub(r"line \d+", "", msg)
    # 截断过长信息
    if len(msg) > 200:
        msg = f"{msg[:200]}..."
    return msg


def _fetch_yfinance_prices(symbols: list[str]) -> dict[str, float]:
    """批量获取 yfinance 最新价，单个标的失败时返回 0.0。"""
    unique_symbols = list(dict.fromkeys(sym for sym in symbols if sym))
    if not unique_symbols:
        return {}

    try:
        import yfinance as yf
    except ImportError:
        logger.debug("yfinance 未安装，跳过价格补齐")
        return {sym: 0.0 for sym in unique_symbols}

    try:
        tickers = yf.Tickers(" ".join(unique_symbols))
    except Exception as e:
        logger.warning("yfinance price fetch failed (degraded to zeros): %s", e)
        return {sym: 0.0 for sym in unique_symbols}

    prices: dict[str, float] = {}
    for sym in unique_symbols:
        try:
            info = tickers.tickers[sym].fast_info
            price = float(getattr(info, "last_price", 0) or 0)
            if price <= 0:
                price = float(getattr(info, "previous_close", 0) or 0)
            prices[sym] = price if price > 0 else 0.0
        except Exception as e:
            logger.debug("yfinance price fetch failed for %s: %s", sym, e)
            prices[sym] = 0.0
    return prices


def _is_social_cookie_ready(platform: str, *, allow_xhs_a1: bool = True) -> bool:
    """检查社媒 Cookie 文件是否存在且包含有效登录信息。"""
    cookie_files = {
        "x": Path.home() / ".openclaw" / "x_cookies.json",
        "xhs": Path.home() / ".openclaw" / "xhs_cookies.json",
    }
    path = cookie_files.get(platform)
    if not path or not path.exists():
        return False

    try:
        import json as _json

        data = _json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        logger.debug("读取%s Cookie文件异常: %s", platform, e)
        return False

    if platform == "x":
        return bool(data)
    if platform == "xhs" and isinstance(data, dict):
        has_cookie = bool(data.get("cookie", ""))
        has_a1 = allow_xhs_a1 and bool(data.get("a1", ""))
        return has_cookie or has_a1
    return False


def _active_x_auto_status(status: str) -> bool:
    """判断 X 自动运营草稿是否应显示在人工确认队列。"""
    return status in {"ready", "needs_review", "approved", "edited", "failed", "publishing"}


def _is_social_review_display_safe(draft: dict) -> bool:
    """过滤旧策略和报错草稿，避免污染用户确认入口。"""
    text = str(draft.get("text") or draft.get("content") or draft.get("body") or "")
    title = str(draft.get("title") or draft.get("topic") or "")
    seed = draft.get("seed") if isinstance(draft.get("seed"), dict) else {}
    combined = f"{title} {text} {seed.get('title', '')}".lower()
    bad_fragments = [
        "严总",
        "请求没处理成功",
        "治国",
        "总书记",
        "高考",
        "查分",
        "分数线",
        "雨水",
        "姆巴佩",
        "世界杯",
        "法国vs",
        "世界波",
        "涉毒",
        "网警",
        "乌克兰",
        "全球资产",
        "openclaw 自动蒸馏",
    ]
    return not any(fragment.lower() in combined for fragment in bad_fragments)


def _merged_social_draft_refs() -> list[dict]:
    """合并通用社媒草稿与 X 自动运营草稿，供桌面端统一审核。"""
    refs: list[dict] = []

    try:
        from src.social_scheduler import _load_state

        state = _load_state()
        for idx, draft in enumerate(state.get("drafts", []) or []):
            if not _is_social_review_display_safe(draft):
                continue
            item = dict(draft)
            item.setdefault("_state_source", "social_autopilot")
            item.setdefault("_state_index", idx)
            refs.append({"source": "social_autopilot", "index": idx, "draft": item})
    except Exception as e:
        logger.debug("读取社媒自动驾驶草稿失败: %s", e)

    try:
        from src.execution.social import x_auto_ops

        state = x_auto_ops._load_state(x_auto_ops._STATE_FILE)
        for idx, draft in enumerate(state.get("drafts", []) or []):
            if draft.get("platform") not in {"x", "xhs"} or not _active_x_auto_status(str(draft.get("status") or "")):
                continue
            if not _is_social_review_display_safe(draft):
                continue
            item = dict(draft)
            item.setdefault("review_status", "pending")
            item["_state_source"] = "x_auto_ops"
            item["_state_index"] = idx
            refs.append({"source": "x_auto_ops", "index": idx, "draft": item})
    except Exception as e:
        logger.debug("读取 X 自动运营草稿失败: %s", e)

    return sorted(refs, key=lambda ref: str(ref["draft"].get("created_at") or ""), reverse=True)


def _resolve_social_draft_ref(index: int) -> dict | None:
    """按桌面端展示索引解析真实草稿来源。"""
    refs = _merged_social_draft_refs()
    if 0 <= index < len(refs):
        return refs[index]
    return None


def _persona_review_payload() -> dict:
    """读取热点抽象号人设确认状态。"""
    try:
        from src.execution.social import persona_review

        return persona_review.get_persona_review(persona_review._STATE_FILE)
    except Exception as e:
        logger.debug("读取社媒人设确认状态失败: %s", e)
        return {
            "success": False,
            "approved": False,
            "needs_confirmation": True,
            "proposal": {},
            "state": {},
            "verdict": "人设确认状态不可用，默认禁止自动外发。",
            "error": _safe_error(e),
        }


def _ensure_social_review_drafts(x_count: int = 6, xhs_count: int = 2) -> dict:
    """确保工作台有一包可审核的 X / 小红书草稿，不触发发布。"""
    try:
        from src.execution.social import x_auto_ops

        state = x_auto_ops._load_state(x_auto_ops._STATE_FILE)

        def _active(draft: dict, platform: str) -> bool:
            status = str(draft.get("status") or "").lower()
            review_status = str(draft.get("review_status") or "pending").lower()
            return (
                draft.get("platform") == platform
                and status in {"ready", "needs_review", "edited", "failed"}
                and review_status != "approved"
            )

        x_existing = [draft for draft in state.get("drafts", []) or [] if _active(draft, "x")]
        xhs_existing = [draft for draft in state.get("drafts", []) or [] if _active(draft, "xhs")]
        created_x: list[dict] = []
        created_xhs: list[dict] = []
        if len(x_existing) < max(1, x_count):
            created_x = x_auto_ops.build_daily_drafts(
                count=max(1, x_count),
                state_path=x_auto_ops._STATE_FILE,
                fetch_transcript=False,
            )
        if len(xhs_existing) < max(1, xhs_count):
            created_xhs = x_auto_ops.build_xhs_review_drafts(
                count=max(1, xhs_count),
                state_path=x_auto_ops._STATE_FILE,
                fetch_transcript=False,
            )
        return {
            "success": True,
            "created_x": len(created_x),
            "created_xhs": len(created_xhs),
        }
    except Exception as e:
        logger.debug("确保社媒待审核草稿失败: %s", e)
        return {"success": False, "error": _safe_error(e), "created_x": 0, "created_xhs": 0}


def _social_review_pack_payload(limit: int = 8, ensure: bool = True) -> dict:
    """生成给用户确认的人设 + 样稿 + 运营判断包。"""
    if ensure:
        _ensure_social_review_drafts()
    persona_review = _persona_review_payload()
    drafts = [ref["draft"] for ref in _merged_social_draft_refs()]

    def _active(draft: dict) -> bool:
        status = str(draft.get("status") or "").lower()
        return status not in {"published", "publishing", "rejected", "superseded"}

    def _sample_safe(draft: dict) -> bool:
        text = str(draft.get("text") or draft.get("content") or draft.get("body") or "")
        title = str(draft.get("title") or draft.get("topic") or "")
        seed = draft.get("seed") if isinstance(draft.get("seed"), dict) else {}
        combined = f"{title} {text} {seed.get('title', '')}".lower()
        bad_fragments = [
            "严总",
            "请求没处理成功",
            "治国",
            "总书记",
            "高考",
            "查分",
            "分数线",
            "雨水",
            "姆巴佩",
            "世界杯",
            "法国vs",
            "进球",
            "世界波",
            "涉毒",
            "网警",
            "乌克兰",
            "全球资产",
        ]
        if any(fragment.lower() in combined for fragment in bad_fragments):
            return False
        return not text.startswith("OpenClaw 自动蒸馏")

    samples: list[dict] = []
    indexed_drafts = sorted(
        list(enumerate(drafts)),
        key=lambda item: str(item[1].get("created_at") or ""),
        reverse=True,
    )
    for idx, draft in indexed_drafts:
        if not _active(draft) or draft.get("review_status") == "approved" or not _sample_safe(draft):
            continue
        platform = str(draft.get("platform") or "").lower()
        if platform not in {"x", "twitter", "xhs", "xiaohongshu"}:
            continue
        seed = draft.get("seed") if isinstance(draft.get("seed"), dict) else {}
        samples.append({
            "index": idx,
            "id": draft.get("id") or f"draft-{idx}",
            "platform": "xhs" if platform in {"xhs", "xiaohongshu"} else "x",
            "title": draft.get("title") or draft.get("topic") or seed.get("title") or "",
            "text": draft.get("text") or draft.get("content") or draft.get("body") or "",
            "source": seed.get("source") or seed.get("channel") or draft.get("_state_source") or "",
            "language": seed.get("language") or "",
            "heat_reason": seed.get("heat_reason") or draft.get("review_required_reason") or "",
            "review_status": draft.get("review_status") or "pending",
        })
        if len(samples) >= max(1, limit):
            break

    skill_findings = [
        {
            "name": "social-autopilot Skill",
            "verdict": "已存在，但旧 SOP 偏全自动发布/评论；当前已被审核模式锁住。",
            "action": "保留调度能力，只允许产出待审稿。",
        },
        {
            "name": "social-persona.md",
            "verdict": "旧人设偏 AI/程序员/效率工具号，不符合用户想要的热点抽象涨粉号。",
            "action": "先用“热点抽象观察员”提案让用户确认。",
        },
        {
            "name": "开源轮子复用",
            "verdict": "项目已具备 sau 桥接、MediaCrawler 桥接、Playwright worker 和 X/XHS 适配器。",
            "action": "不从零重写发布器，继续复用成熟浏览器/CLI 链路。",
        },
    ]

    return {
        "success": True,
        "mode": "persona_and_content_review_pack",
        "auto_publish_enabled": False,
        "requires_owner_confirmation": True,
        "requires_owner_review": True,
        "persona": persona_review.get("proposal", {}),
        "persona_state": persona_review.get("state", {}),
        "persona_approved": bool(persona_review.get("approved", False)),
        "samples": samples,
        "sample_count": len(samples),
        "skill_findings": skill_findings,
        "content_verdict": (
            "当前方向已从 AI 垂直号切到中英热点抽象号；但样稿仍需用户确认口味，"
            "确认前不会发布、评论、点赞或加载自动发帖任务。"
        ),
        "guardrails": [
            "不碰政治、灾难、伤亡、战争、枪击、造谣和敏感考试焦虑。",
            "不自动评论、点赞、关注，不做刷量或平台风控绕过。",
            "人设确认不等于允许发布；每条内容仍需逐条确认和最终发布确认。",
        ],
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    }


# Track process startup time for uptime calculation
_start_time = time.time()


class ClawBotRPC:
    """
    Central RPC class — bridges internal state to external consumers.

    Pattern: freqtrade's RPC abstraction where one class serves both
    REST API and Telegram handler.  All business logic lives here;
    transport layers (FastAPI routes, Telegram handlers) are thin wrappers.
    """

    # ──────────────────────────────────────────────
    #  System
    # ──────────────────────────────────────────────

    @staticmethod
    def _rpc_ping() -> dict:
        """Health-check ping — always succeeds."""
        return {"status": "pong", "version": "5.0"}

    @staticmethod
    def _rpc_system_status() -> dict:
        """Aggregate full system status for dashboard display."""
        from src.bot.globals import (
            bot_registry,
            shared_memory,
        )
        from src.broker_selector import ibkr
        from src.litellm_router import free_pool

        uptime = time.time() - _start_time

        # ── Bot statuses ──
        bot_statuses = []
        for bot_id, bot in bot_registry.items():
            try:
                alive = bool(bot.app and bot.app.updater and bot.app.updater.running)
            except Exception as e:  # noqa: F841
                alive = False
            bot_statuses.append(
                {
                    "bot_id": bot_id,
                    "username": getattr(bot, "username", ""),
                    "model": getattr(bot, "model", ""),
                    "alive": alive,
                    "api_type": getattr(bot, "api_type", ""),
                    "message_count": getattr(bot, "_message_count", 0),
                    "error_count": getattr(bot, "_error_count", 0),
                }
            )

        # ── Free API pool stats ──
        pool_stats: dict = {}
        try:
            pool_stats = free_pool.get_stats()
        except Exception:
            logger.debug("Silenced exception", exc_info=True)

        # ── IBKR broker status ──
        ibkr_connected = False
        ibkr_account = ""
        try:
            # 优先通过 IBKRBridge 实例检测（运行时有效）
            ibkr_connected = getattr(ibkr, "_connected", False) if ibkr else False
            ibkr_account = getattr(ibkr, "account", "") or ""
        except Exception:
            logger.debug("Silenced exception", exc_info=True)
        # 兜底：如果 IBKRBridge 实例不可用，直接检测 4002 端口
        if not ibkr_connected:
            try:
                import socket as _socket

                _ibkr_port = int(os.environ.get("IBKR_PORT", "4002"))
                with _socket.create_connection(("127.0.0.1", _ibkr_port), timeout=1):
                    ibkr_connected = True
            except Exception as e:
                logger.debug("[RPC] IBKR连接检测失败: %s", e)

        # ── Shared memory stats ──
        mem_entries = 0
        try:
            mem_stats = shared_memory.get_stats()
            mem_entries = mem_stats.get("total_entries", 0)
        except Exception:
            logger.debug("Silenced exception", exc_info=True)

        # ── 闲鱼客服状态检测 ──
        xianyu_online = False
        xianyu_detail: dict = {"online": False, "service": "xianyu_live"}
        try:
            import subprocess

            result = subprocess.run(["pgrep", "-f", "xianyu_main"], capture_output=True, text=True, timeout=3)
            xianyu_online = result.returncode == 0 and bool(result.stdout.strip())
            xianyu_detail["online"] = xianyu_online

            # 如果闲鱼进程在线，通过内部 admin API 拉取详细状态
            if xianyu_online:
                try:
                    import httpx
                    _xy_headers = {"X-API-Token": os.environ.get("OPENCLAW_API_TOKEN", "")}
                    # 拉取 WS 连接 + Cookie 状态
                    _xy_r = httpx.get("http://127.0.0.1:18800/api/status", timeout=3, headers=_xy_headers)
                    if _xy_r.status_code == 200:
                        _xs = _xy_r.json()
                        xianyu_detail["cookie_ok"] = _xs.get("cookie_ok", False)
                        xianyu_detail["auto_reply_active"] = _xs.get("ws_connected", False) and _xs.get("cookie_ok", False)
                    # 拉取今日咨询数
                    _xy_r2 = httpx.get("http://127.0.0.1:18800/api/dashboard", timeout=3, headers=_xy_headers)
                    if _xy_r2.status_code == 200:
                        _xy_dash = _xy_r2.json()
                        _xy_today = _xy_dash.get("today", {})
                        xianyu_detail["conversations_today"] = _xy_today.get("consultations", 0)
                        xianyu_detail["unread_chats"] = _xy_today.get("consultations", 0)
                except Exception:
                    # 闲鱼 admin 不可用时静默降级
                    logger.debug("闲鱼 admin API 不可用，使用基础状态")
        except Exception as e:
            logger.debug("闲鱼状态检测失败: %s", e)

        return {
            "uptime_seconds": uptime,
            "bots": bot_statuses,
            "ibkr_connected": ibkr_connected,
            "ibkr_account": ibkr_account,
            "pool_active_sources": pool_stats.get("active_sources", 0),
            "pool_total_sources": pool_stats.get("total_sources", 0),
            "pool_routing_strategy": pool_stats.get("routing_strategy", "balanced"),
            "total_api_calls": pool_stats.get("total_requests", 0),
            "total_cost_usd": pool_stats.get("total_cost_usd", 0.0),
            "avg_latency_ms": pool_stats.get("avg_latency_ms", 0.0),
            "memory_entries": mem_entries,
            "xianyu": xianyu_detail,
        }

    # ──────────────────────────────────────────────
    #  Trading — Positions
    # ──────────────────────────────────────────────

    @staticmethod
    async def _rpc_trading_positions() -> dict:
        """Get current positions from IBKR or local portfolio fallback.

        Returns dict with keys: connected, positions (list), account_summary.
        IBKR bridge methods (get_positions, get_account_summary) are async.
        """
        from src.broker_selector import ibkr
        from src.invest_tools import portfolio

        connected = False
        positions: list[dict] = []
        account_summary: dict = {}

        try:
            connected = ibkr.connected if ibkr else False
        except Exception:
            logger.debug("Silenced exception", exc_info=True)

        if connected:
            # ── Live IBKR positions ──
            try:
                raw_positions = await ibkr.get_positions()
                for p in raw_positions or []:
                    qty = float(p.get("quantity", 0) or 0)
                    positions.append(
                        {
                            "symbol": p.get("symbol", ""),
                            "quantity": qty,
                            "avg_price": float(p.get("avg_price", 0) or p.get("avg_cost", 0) or 0),
                            "current_price": float(p.get("market_price", 0) or 0),
                            "unrealized_pnl": float(p.get("unrealized_pnl", 0) or 0),
                            "unrealized_pnl_pct": float(p.get("unrealized_pnl_pct", 0) or 0),
                            "market_value": float(p.get("market_value", 0) or 0),
                            "side": "short" if qty < 0 else "long",
                        }
                    )
                # 兜底：如果 IBKR 没返回实时价格，用 yfinance 补齐
                symbols_needing_price = [p["symbol"] for p in positions if not p.get("current_price")]
                if symbols_needing_price:
                    live_prices = _fetch_yfinance_prices(symbols_needing_price)
                    for p in positions:
                        price = live_prices.get(p["symbol"], 0.0)
                        if price > 0:
                            p["current_price"] = price
                            p["market_value"] = p["quantity"] * price
                            cost = p["quantity"] * p["avg_price"]
                            p["unrealized_pnl"] = p["market_value"] - cost
            except Exception as e:
                logger.warning("Failed to get IBKR positions: %s", e)

            try:
                account_summary = await ibkr.get_account_summary() or {}
            except Exception:
                logger.debug("Silenced exception", exc_info=True)
        else:
            # ── Fallback: local Portfolio (sync) + yfinance live prices ──
            try:
                local_positions = portfolio.get_positions() if portfolio else []
                symbols = [p.get("symbol", "") for p in local_positions or [] if p.get("symbol")]

                # Batch-fetch current prices via yfinance (already a project dependency)
                live_prices: dict = {}
                if symbols:
                    live_prices = _fetch_yfinance_prices(symbols)

                for p in local_positions or []:
                    qty = float(p.get("quantity", 0) or 0)
                    avg_price = float(p.get("avg_price", 0) or p.get("avg_cost", 0) or 0)
                    sym = p.get("symbol", "")
                    current_price = live_prices.get(sym, 0.0)
                    market_value = qty * current_price if qty and current_price else 0.0
                    cost_basis = qty * avg_price if qty and avg_price else 0.0
                    unrealized_pnl = market_value - cost_basis
                    unrealized_pnl_pct = (unrealized_pnl / cost_basis * 100) if cost_basis else 0.0
                    positions.append(
                        {
                            "symbol": sym,
                            "quantity": qty,
                            "avg_price": avg_price,
                            "current_price": round(current_price, 2),
                            "unrealized_pnl": round(unrealized_pnl, 2),
                            "unrealized_pnl_pct": round(unrealized_pnl_pct, 2),
                            "market_value": round(market_value, 2),
                            "side": "short" if qty < 0 else "long",
                        }
                    )
            except Exception as e:
                logger.warning("Failed to get local positions: %s", e)

        return {
            "connected": connected,
            "positions": positions,
            "account_summary": (account_summary if isinstance(account_summary, dict) else {}),
        }

    # ──────────────────────────────────────────────
    #  Trading — PnL
    # ──────────────────────────────────────────────

    @staticmethod
    async def _rpc_trading_pnl() -> dict:
        """Get PnL summary from trading journal + IBKR account.

        修复: 当 IBKR 离线时，从本地持仓+yfinance 实时价格计算未实现盈亏，
        与 portfolio-summary 共享同一数据源，避免全部返回零。
        """
        from src.broker_selector import ibkr
        from src.trading_journal import journal

        result = {
            "total_pnl": 0.0,
            "total_pnl_pct": 0.0,
            "daily_pnl": 0.0,
            "winning_trades": 0,
            "losing_trades": 0,
            "win_rate": 0.0,
            "sharpe_ratio": 0.0,
            "max_drawdown": 0.0,
            "total_trades": 0,
            "account_value": 0.0,
            "cash": 0.0,
            "buying_power": 0.0,
        }

        # ── From local trading journal ──
        try:
            if journal:
                stats = journal.get_stats() if hasattr(journal, "get_stats") else {}
                result["total_trades"] = stats.get("total_trades", 0)
                result["winning_trades"] = stats.get("winning_trades", 0)
                result["losing_trades"] = stats.get("losing_trades", 0)
                result["win_rate"] = stats.get("win_rate", 0.0)
                result["total_pnl"] = stats.get("total_pnl", 0.0)
                result["sharpe_ratio"] = stats.get("sharpe_ratio", 0.0)
                result["max_drawdown"] = stats.get("max_drawdown", 0.0)
        except Exception as e:
            logger.warning("Failed to get journal stats: %s", e)

        # ── From IBKR account summary (async) ──
        ibkr_connected = False
        try:
            ibkr_connected = ibkr.connected if ibkr else False
            if ibkr_connected:
                summary = await ibkr.get_account_summary() or {}
                result["account_value"] = float(summary.get("NetLiquidation", 0) or 0)
                result["cash"] = float(summary.get("TotalCashValue", 0) or 0)
                result["buying_power"] = float(summary.get("BuyingPower", 0) or 0)
                result["daily_pnl"] = float(summary.get("RealizedPnL", 0) or summary.get("DailyPnL", 0) or 0)
        except Exception as e:
            logger.warning("Failed to get IBKR account summary: %s", e)

        # ── 兜底: 无论 IBKR 是否连接，只要 account_value 和 total_pnl 都为 0，就从持仓计算 ──
        # 场景1: IBKR 离线 → ibkr_connected=False
        # 场景2: IBKR 在线但 get_account_summary 失败(event loop 冲突) → 数据全零
        if result["account_value"] == 0.0 and result["total_pnl"] == 0.0:
            try:
                # 复用 _rpc_trading_positions 获取持仓（含 yfinance 实时价格）
                positions_data = await ClawBotRPC._rpc_trading_positions()
                positions_list = positions_data.get("positions", [])
                total_value = 0.0
                total_cost = 0.0
                for pos in positions_list:
                    qty = pos.get("quantity", 0)
                    avg_price = pos.get("avg_price", 0)
                    current_price = pos.get("current_price", 0)
                    market_value = qty * current_price if qty and current_price else 0
                    cost_basis = qty * avg_price if qty and avg_price else 0
                    total_value += market_value
                    total_cost += cost_basis
                if total_cost > 0:
                    result["total_pnl"] = round(total_value - total_cost, 2)
                    result["total_pnl_pct"] = round((total_value - total_cost) / total_cost * 100, 2)
                    result["account_value"] = round(total_value, 2)
            except Exception as e:
                logger.warning("Failed to compute PnL from local positions: %s", e)

        return result

    # ──────────────────────────────────────────────
    #  Trading — Dashboard (图表+资产)
    # ──────────────────────────────────────────────

    @staticmethod
    async def _rpc_trading_dashboard() -> dict:
        """盈利仪表盘数据：图表+资产+连接状态

        修复: IBKR 离线时从本地持仓+yfinance 获取资产列表，
        避免 dashboard 永远返回空 assets 和 value=0。
        """
        from src.broker_selector import ibkr
        from src.trading_journal import journal

        try:
            # 获取最近 30 天的每日净值数据
            chart_data: list = []
            assets: list = []
            connected = False

            # 检查 IBKR 连接状态
            try:
                connected = ibkr.connected if ibkr else False
            except Exception as e:
                logger.debug("[RPC] IBKR 连接状态检查失败: %s", e)

            # 尝试获取持仓作为资产列表
            try:
                if connected and ibkr:
                    positions = await ibkr.get_positions()
                    for pos in positions or []:
                        assets.append(
                            {
                                "name": pos.get("symbol", "Unknown"),
                                "value": float(pos.get("market_value", 0)),
                                "pnl": float(pos.get("unrealized_pnl", 0)),
                            }
                        )
            except Exception as e:
                logger.debug("[RPC] IBKR 持仓查询失败: %s", e)

            # 兜底: assets 为空或 value 全零时，从 _rpc_trading_positions 获取（含 yfinance 价格）
            has_real_values = any(a.get("value", 0) > 0 for a in assets)
            if not assets or not has_real_values:
                try:
                    # 清空之前的空数据，用兜底数据替换
                    assets.clear()
                    positions_data = await ClawBotRPC._rpc_trading_positions()
                    for pos in positions_data.get("positions", []):
                        market_value = pos.get("market_value", 0)
                        pnl = pos.get("unrealized_pnl", 0)
                        assets.append({
                            "name": pos.get("symbol", "Unknown"),
                            "value": round(float(market_value), 2),
                            "pnl": round(float(pnl), 2),
                        })
                except Exception as e:
                    logger.debug("[RPC] 本地持仓查询失败: %s", e)

            # 用真实交易日志生成净值曲线，避免前端长期看到空图
            try:
                equity_values, date_labels = journal.get_equity_curve(days=30)
                chart_data = [{"name": label, "value": value} for label, value in zip(date_labels, equity_values)]
            except Exception as e:
                logger.debug("[RPC] 交易净值曲线生成失败: %s", e)

            return {"chart_data": chart_data, "assets": assets, "connected": connected}
        except Exception as e:
            logger.debug("[RPC] 交易面板数据获取失败: %s", e)
            return {"chart_data": [], "assets": [], "connected": False}

    # ──────────────────────────────────────────────
    #  Trading — Strategy Signals
    # ──────────────────────────────────────────────

    @staticmethod
    def _rpc_trading_signals() -> list:
        """Get recent strategy engine signal history."""
        import src.bot.globals as g

        signals: list = []
        engine = g.strategy_engine_instance
        if not engine:
            return signals

        try:
            history = engine.get_history(limit=20)
            for entry in history or []:
                signals.append(
                    {
                        "symbol": entry.get("symbol", ""),
                        "signal": entry.get("signal", "HOLD"),
                        "score": entry.get("score", 0),
                        "confidence": entry.get("confidence", 0.0),
                        "strategy_name": entry.get("strategy_name", ""),
                        "reason": entry.get("reason", ""),
                        "timestamp": entry.get("ts", ""),
                    }
                )
        except Exception as e:
            logger.warning("Failed to get strategy signals: %s", e)

        return signals

    # ──────────────────────────────────────────────
    #  Trading — System Status
    # ──────────────────────────────────────────────

    @staticmethod
    def _rpc_trading_system_status() -> dict:
        """Get auto-trading system status (risk manager, pipeline, etc.).

        修复: get_system_status() 返回的是格式化字符串而非 dict，
        需要包装为 dict 结构，并提取关键状态字段。
        """
        from src.trading_system import get_system_status

        try:
            raw = get_system_status()
            # get_system_status 返回字符串（用于 Telegram 展示），包装为 dict
            if isinstance(raw, dict):
                return raw
            if isinstance(raw, str):
                # 解析字符串中的关键信息
                text = raw.strip()
                if not text or text == "交易系统未初始化":
                    return {
                        "status": "offline",
                        "status_text": text or "交易系统未初始化",
                        "initialized": False,
                    }
                return {
                    "status": "running",
                    "status_text": text,
                    "initialized": True,
                }
            return {"status": "unknown"}
        except Exception as e:
            logger.warning("Failed to get trading system status: %s", e)
            return {"status": "error", "error": str(e)}

    # ──────────────────────────────────────────────
    #  Trading — AI Team Vote
    # ──────────────────────────────────────────────

    @staticmethod
    async def _rpc_trigger_team_vote(
        symbol: str,
        analysis: dict,
        *,
        timeout_per_bot: float = 60,
        account_context: str = "",
    ) -> dict:
        """Trigger AI team vote for a symbol.

        ``analysis`` must be the pre-computed technical-analysis dict
        (from ``get_full_analysis``).  The caller is responsible for
        preparing it before invoking this RPC.

        Args:
            symbol: Ticker / symbol code.
            analysis: Technical analysis data dict.
            timeout_per_bot: Per-bot timeout in seconds.
            account_context: Optional account context string.

        Returns:
            VoteResult dict on success, or ``{"error": "..."}`` on failure.
        """
        from src.ai_team_voter import run_team_vote
        from src.trading_system import _ai_team_api_callers

        if not _ai_team_api_callers:
            return {"error": "AI team callers not initialized"}

        try:
            result = await run_team_vote(
                symbol=symbol,
                analysis=analysis,
                api_callers=_ai_team_api_callers,
                timeout_per_bot=timeout_per_bot,
                account_context=account_context,
            )
            # VoteResult is a dataclass — convert to dict if needed
            if hasattr(result, "__dict__") and not isinstance(result, dict):
                return vars(result)
            return result or {}
        except Exception as e:
            logger.error("Team vote failed for %s: %s", symbol, e)
            return {"error": _safe_error(e)}

    # ──────────────────────────────────────────────
    #  Social
    # ──────────────────────────────────────────────

    @staticmethod
    def _rpc_social_status() -> dict:
        """Get social-media autopilot status via browser worker.

        Calls the social_browser_worker "status" action to retrieve real
        browser/cookie connection status for each platform.  Falls back
        to cookie-file detection, then placeholder data if the worker
        is unavailable.

        使用线程超时保护（2秒），防止 worker 子进程启动慢导致前端超时。
        """
        _placeholder = {
            "autopilot_running": False,
            "running": False,
            "platforms": [
                {
                    "platform": "x",
                    "connected": _is_social_cookie_ready("x"),
                    "last_post_time": "",
                    "posts_today": 0,
                    "total_posts": 0,
                },
                {
                    "platform": "xhs",
                    "connected": _is_social_cookie_ready("xhs"),
                    "last_post_time": "",
                    "posts_today": 0,
                    "total_posts": 0,
                },
            ],
            "next_scheduled_action": "",
            "next_scheduled_time": "",
            "content_queue_size": 0,
            "source": "placeholder",
        }

        # 使用线程超时保护：最多等 2 秒，超时直接返回 placeholder
        import concurrent.futures

        def _fetch_worker_status():
            """在子线程中调用 worker，防止阻塞主线程过久"""
            from src.execution.social.worker_bridge import run_social_worker
            return run_social_worker("status", {})

        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(_fetch_worker_status)
                try:
                    result = future.result(timeout=2.0)
                except concurrent.futures.TimeoutError:
                    logger.warning("Social status worker 超时(2s)，返回 Cookie 文件状态兜底")
                    _placeholder["source"] = "timeout_fallback"
                    return _placeholder
            if not result.get("success"):
                logger.warning("Social status worker failed: %s", result.get("error"))
                # Worker 不可用时，用 Cookie 文件状态兜底
                return _placeholder

            # Map worker response to API schema
            x_status = result.get("x", {})
            xhs_status = result.get("xhs", {})

            # Worker 返回的 connected 和 Cookie 文件检测 取 OR（任一为真即认为已连接）
            x_connected = x_status.get("connected", False) or _is_social_cookie_ready("x")
            xhs_connected = xhs_status.get("connected", False) or _is_social_cookie_ready("xhs")

            # 同时提供 running 字段，兼容前端读取 r.running ?? r.active
            _autopilot_running = result.get("autopilot_running", False)
            # 修复: worker 不知道 scheduler 状态，额外检查 autopilot status endpoint
            if not _autopilot_running:
                try:
                    ap_status = ClawBotRPC._rpc_autopilot_status()
                    _autopilot_running = ap_status.get("running", False)
                except Exception as e:
                    logger.debug("社媒自动驾驶状态兜底失败: %s", e)
            return {
                "autopilot_running": _autopilot_running,
                "running": _autopilot_running,
                "platforms": [
                    {
                        "platform": "x",
                        "connected": x_connected,
                        "last_post_time": x_status.get("last_post_time", ""),
                        "posts_today": x_status.get("posts_today", 0),
                        "total_posts": x_status.get("total_posts", 0),
                    },
                    {
                        "platform": "xhs",
                        "connected": xhs_connected,
                        "last_post_time": xhs_status.get("last_post_time", ""),
                        "posts_today": xhs_status.get("posts_today", 0),
                        "total_posts": xhs_status.get("total_posts", 0),
                    },
                ],
                "next_scheduled_action": result.get("next_scheduled_action", ""),
                "next_scheduled_time": result.get("next_scheduled_time", ""),
                "content_queue_size": result.get("content_queue_size", 0),
            }
        except Exception as e:
            logger.warning("Social status check failed, using cookie-file fallback: %s", e)
            return _placeholder

    @staticmethod
    def _rpc_social_browser_status() -> dict:
        """Get browser session readiness for X / 小红书.

        综合检查: browser worker 状态 + Cookie 文件状态。
        任一路径可用即视为 ready。
        """
        try:
            from src.bot.globals import execution_hub

            status = execution_hub.get_social_browser_status() or {}
            x_ready = status.get("x_ready")
            xhs_ready = status.get("xiaohongshu_ready")

            # 额外检查 Cookie 文件（twikit / xhs 持久化登录）
            x_cookie_ok = _is_social_cookie_ready("x")
            xhs_cookie_ok = _is_social_cookie_ready("xhs")

            def _map_ready(value, cookie_ok: bool):
                if value is True or cookie_ok:
                    return "ready"
                if value is False:
                    return "login_needed"
                return "unknown"

            return {
                "browser_running": bool(status.get("browser_running", False)),
                "x": _map_ready(x_ready, x_cookie_ok),
                "xhs": _map_ready(xhs_ready, xhs_cookie_ok),
            }
        except Exception as e:
            logger.warning("Social browser status failed: %s", e)
            # 即使主逻辑失败，也检查 Cookie 文件
            x_cookie = "ready" if _is_social_cookie_ready("x") else "unknown"
            xhs_cookie = "ready" if _is_social_cookie_ready("xhs", allow_xhs_a1=False) else "unknown"
            return {
                "browser_running": False,
                "x": x_cookie,
                "xhs": xhs_cookie,
                "error": _safe_error(e),
            }

    @staticmethod
    def _rpc_social_browser_control(action: str, platform: str = "all") -> dict:
        """执行社媒工作台里的安全浏览器控制动作。

        该入口只允许打开/检查/登录类动作；发布、回复、删除等外部变更动作必须
        继续走草稿审核和最终发布确认，不能从浏览器控制卡片绕过。
        """
        normalized_action = str(action or "").strip().lower()
        normalized_platform = str(platform or "all").strip().lower()
        blocked_prefixes = ("publish", "reply", "delete", "auto_reply", "scout")
        if normalized_action.startswith(blocked_prefixes):
            return {
                "success": False,
                "blocked": True,
                "requires_review": True,
                "error": "浏览器控制入口不允许发布/回复/删除；请先确认草稿，再点最终发布确认",
            }

        platform_map = {
            "x": ["x"],
            "twitter": ["x"],
            "xhs": ["xiaohongshu"],
            "xiaohongshu": ["xiaohongshu"],
            "all": ["x", "xiaohongshu"],
        }
        platforms = platform_map.get(normalized_platform, platform_map["all"])
        safe_actions: dict[str, tuple[str, dict]] = {
            "bootstrap": ("bootstrap", {"platforms": platforms}),
            "open": ("bootstrap", {"platforms": platforms}),
            "open_x": ("bootstrap", {"platforms": ["x"]}),
            "open_xhs": ("bootstrap", {"platforms": ["xiaohongshu"]}),
            "status": ("status", {}),
            "login": ("login", {"platforms": platforms, "timeout": 300}),
            "login_x": ("login", {"platforms": ["x"], "timeout": 300}),
            "login_xhs": ("login", {"platforms": ["xiaohongshu"], "timeout": 300}),
        }
        if normalized_action not in safe_actions:
            return {
                "success": False,
                "blocked": True,
                "error": f"不支持的浏览器控制动作: {normalized_action or 'empty'}",
            }

        worker_action, payload = safe_actions[normalized_action]
        try:
            from src.execution.social.worker_bridge import run_social_worker

            result = run_social_worker(worker_action, payload)
            if not isinstance(result, dict):
                result = {"success": False, "raw": result}
            result.setdefault("success", bool(result.get("success", False)))
            result["safe"] = True
            result["action"] = worker_action
            result["requested_action"] = normalized_action
            result["platform"] = normalized_platform
            return result
        except Exception as e:
            logger.warning("Social browser control failed: %s", e)
            return {
                "success": False,
                "safe": True,
                "action": worker_action,
                "requested_action": normalized_action,
                "platform": normalized_platform,
                "error": _safe_error(e),
            }

    @staticmethod
    def _rpc_social_persona_review() -> dict:
        """获取热点抽象号人设提案和确认状态。"""
        return _persona_review_payload()

    @staticmethod
    def _rpc_social_persona_review_update(approved: bool, reviewer: str = "owner", notes: str = "") -> dict:
        """确认或打回热点抽象号人设；不会触发任何外部发布。"""
        try:
            from src.execution.social import persona_review

            return persona_review.review_persona(
                approved=approved,
                reviewer=reviewer,
                notes=notes,
                path=persona_review._STATE_FILE,
            )
        except Exception as e:
            logger.error("Social persona review update failed: %s", e)
            return {"success": False, "error": _safe_error(e)}

    @staticmethod
    def _rpc_social_review_pack(limit: int = 8) -> dict:
        """返回待用户确认的人设和内容样稿包；只读且不触发发布。"""
        return _social_review_pack_payload(limit=limit, ensure=True)

    @staticmethod
    def _rpc_social_extension_status() -> dict:
        """读取 Chrome 社媒运营插件状态，供 App/Telegram 中控同步。"""
        return _load_social_extension_status(_SOCIAL_EXTENSION_STATUS_FILE)

    @staticmethod
    def _rpc_social_extension_status_update(payload: dict) -> dict:
        """接收 Chrome 插件上报的当前平台、启动态和安全设置摘要。"""
        status = _sanitize_social_extension_payload(payload)
        _save_social_extension_status(status, _SOCIAL_EXTENSION_STATUS_FILE)
        return status


    @staticmethod
    def _rpc_social_extension_strategy_update(payload: dict) -> dict:
        """从 App/Telegram 中控更新插件 no-code 运营打法；只改安全设置摘要，不触发外部动作。"""
        if not isinstance(payload, dict):
            payload = {}
        current = _load_social_extension_status(_SOCIAL_EXTENSION_STATUS_FILE)
        platform = str(payload.get("platform") or current.get("platform") or "x").strip().lower()
        if platform in {"twitter"}:
            platform = "x"
        if platform in {"xiaohongshu"}:
            platform = "xhs"
        if platform not in _SOCIAL_EXTENSION_DRAFT_PLATFORMS:
            platform = "x"
        raw_preset = _bounded_str(payload.get("strategyPreset") or payload.get("strategy_preset"), 80)
        if raw_preset not in _SOCIAL_STRATEGY_PRESETS:
            raw_preset = "auto_mcn_growth"
        settings = current.get("settings") if isinstance(current.get("settings"), dict) else {}
        settings = dict(settings)
        settings["strategyPreset"] = raw_preset
        current["platform"] = platform
        current["settings"] = settings
        current["strategy_summary"] = _social_strategy_summary(settings, platform)
        current["online"] = bool(current.get("online", False))
        current["running"] = bool(current.get("running", False))
        current["tasks"] = [
            "App 中控已更新 no-code 运营打法",
            "新草稿会按当前打法生成内容计划",
            "确认前不会发布或评论",
        ]
        current["auto_publish_enabled"] = False
        current["external_actions_locked"] = True
        current["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
        _save_social_extension_status(current, _SOCIAL_EXTENSION_STATUS_FILE)
        return {
            "success": True,
            "source": "app_social_strategy_update",
            "platform": platform,
            "settings": settings,
            "strategy_summary": current["strategy_summary"],
            "auto_publish_enabled": False,
            "external_actions_locked": True,
            "next_action": "已更新运营打法；后续只生成待审草稿，不自动发布、不自动评论。",
        }

    @staticmethod
    def _rpc_social_extension_page_probe_update(payload: dict) -> dict:
        """保存 Chrome 插件真实页面填入点探测结果；只登记校准状态，不发布。"""
        probe = _sanitize_social_extension_probe_payload(payload)
        status = _load_social_extension_status(_SOCIAL_EXTENSION_STATUS_FILE)
        calibration = status.get("page_calibration") if isinstance(status.get("page_calibration"), dict) else {}
        calibration[probe["platform"]] = probe
        status["page_calibration"] = calibration
        status["online"] = True
        status["platform"] = probe["platform"]
        if probe.get("url"):
            status["url"] = probe["url"]
        status["auto_publish_enabled"] = False
        status["external_actions_locked"] = True
        status["updated_at"] = probe["updated_at"]
        _save_social_extension_status(status, _SOCIAL_EXTENSION_STATUS_FILE)
        return probe

    @staticmethod
    def _rpc_social_extension_trends(platform: str = "x", limit: int = 8) -> dict:
        """返回 Chrome 插件可直接展示的本地/云端热点池；只读，不触发发布。"""
        normalized_platform = str(platform or "x").strip().lower()
        if normalized_platform in {"twitter"}:
            normalized_platform = "x"
        if normalized_platform in {"xiaohongshu"}:
            normalized_platform = "xhs"
        if normalized_platform not in _SOCIAL_EXTENSION_DRAFT_PLATFORMS:
            normalized_platform = "x"
        bounded_limit = min(12, max(1, int(limit or 8)))
        try:
            from src.execution.social import x_auto_ops

            seeds = x_auto_ops.fetch_all_content_seeds(include_video_fallback=False)
            if not seeds:
                seeds = x_auto_ops.fetch_all_content_seeds(include_video_fallback=True)
            trends = [
                trend
                for trend in (_extension_seed_to_trend(seed, normalized_platform) for seed in seeds)
                if trend
            ]
            growth_feedback_applied = False
            try:
                state = x_auto_ops._load_state(x_auto_ops._STATE_FILE)
                growth_feedback_applied = _extension_apply_growth_feedback(trends, normalized_platform, state)
            except Exception as feedback_error:
                logger.debug("Chrome 插件热点增长反馈加权失败: %s", feedback_error)
            seen: set[str] = set()
            deduped: list[dict] = []
            for trend in sorted(
                trends,
                key=lambda item: _extension_platform_trend_score(item, normalized_platform),
                reverse=True,
            ):
                key = str(trend.get("title") or "").strip().lower()
                if not key or key in seen:
                    continue
                seen.add(key)
                trend["platform_score"] = _extension_platform_trend_score(trend, normalized_platform)
                deduped.append(trend)
                if len(deduped) >= bounded_limit:
                    break
            if not deduped:
                deduped = [
                    _extension_seed_to_trend(seed, normalized_platform)
                    for seed in x_auto_ops._FALLBACK_SEEDS[:bounded_limit]
                ]
            return {
                "success": True,
                "source": "social_hotspot_pool",
                "platform": normalized_platform,
                "count": len(deduped),
                "trends": deduped,
                "growth_feedback_applied": growth_feedback_applied,
                "auto_publish_enabled": False,
                "external_actions_locked": True,
                "next_action": "选择一个热点生成待审草稿；确认前不会外发。",
                "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            }
        except Exception as e:
            logger.warning("Chrome 插件热点池读取失败: %s", e)
            return {
                "success": False,
                "source": "social_hotspot_pool",
                "platform": normalized_platform,
                "count": 0,
                "trends": [],
                "growth_feedback_applied": False,
                "auto_publish_enabled": False,
                "external_actions_locked": True,
                "error": _safe_error(e),
            }

    @staticmethod
    def _rpc_social_extension_draft_create(payload: dict) -> dict:
        """把 Chrome 插件当前页/热点信号转成待审草稿；不发布、不评论。"""
        if not isinstance(payload, dict):
            payload = {}
        detected = payload.get("detected_platform") if isinstance(payload.get("detected_platform"), dict) else {}
        platform = str(payload.get("platform") or detected.get("id") or "unsupported").strip().lower()
        if platform not in _SOCIAL_EXTENSION_DRAFT_PLATFORMS:
            return {
                "success": False,
                "blocked": True,
                "requires_owner_review": True,
                "auto_publish_enabled": False,
                "external_actions_locked": True,
                "error": "当前页面不是 X / 小红书 / 闲鱼，不能生成运营草稿",
            }

        settings_in = payload.get("settings") if isinstance(payload.get("settings"), dict) else {}
        settings = _sanitize_social_extension_payload({"platform": platform, "settings": settings_in})["settings"]
        context = _extension_page_context(payload)
        fallback = {"x": "当前 X 热点", "xhs": "当前小红书话题", "xianyu": "当前闲鱼商品/聊天"}.get(platform, "当前页面")
        topic = _extension_topic_from_context(context, fallback=fallback)
        url = _bounded_str(payload.get("url"), 500)
        source = _bounded_str(payload.get("source"), 80) or "chrome_extension"
        if source not in {"chrome_extension", "chrome_extension_trend_pool", "chrome_extension_interaction_scan", "chrome_extension_growth_feedback"}:
            source = "chrome_extension"
        content = _extension_compose_draft(platform, topic, context, settings, url)
        asset_plan = _extension_content_asset_plan(platform, topic, context, settings)

        from src.execution.social import x_auto_ops

        state = x_auto_ops._load_state(x_auto_ops._STATE_FILE)
        digest_raw = json.dumps(
            {
                "platform": platform,
                "topic": topic,
                "url": url,
                "settings": settings,
                "context": context,
                "created": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        import hashlib

        digest = hashlib.sha256(digest_raw.encode("utf-8")).hexdigest()[:16]
        created_at = time.strftime("%Y-%m-%dT%H:%M:%S%z")
        draft = {
            "id": f"ext-{platform}-{digest}",
            "platform": platform,
            "status": "needs_review",
            "review_status": "pending",
            "angle": "extension_current_page",
            "title": content["title"],
            "body": content["body"],
            "text": content["text"],
            "platform_style": asset_plan["platform_style"],
            "content_plan": asset_plan["content_plan"],
            "image_plan": asset_plan["image_plan"],
            "format_checklist": asset_plan["format_checklist"],
            "safety_checklist": asset_plan["safety_checklist"],
            "cost_route": asset_plan["cost_route"],
            "seed": {
                "title": topic,
                "channel": "Chrome Social Pilot",
                "url": url,
                "source": source,
                "summary": context.get("bodyText", ""),
                "tags": settings.get("personaTags", []),
                "heat_reason": (
                    "来自插件热点池候选选题"
                    if source == "chrome_extension_trend_pool"
                    else (
                        "来自增长复盘高信号反哺选题"
                        if source == "chrome_extension_growth_feedback"
                        else (
                            "来自当前页互动扫描候选"
                            if source == "chrome_extension_interaction_scan"
                            else "来自用户当前浏览器标签页/热点页信号"
                        )
                    )
                ),
            },
            "settings": settings,
            "page_context": context,
            "digest": digest,
            "created_at": created_at,
            "review_required_reason": "Chrome 插件生成的草稿必须先确认内容，再进入最终发布确认",
            "auto_publish_enabled": False,
            "external_actions_locked": True,
            "publishIntent": False,
        }
        drafts = list(state.get("drafts", []) or [])
        drafts.append(draft)
        state["drafts"] = drafts[-100:]
        state["last_run"] = created_at
        x_auto_ops._save_state(state, x_auto_ops._STATE_FILE)

        status = _sanitize_social_extension_payload({
            **payload,
            "platform": platform,
            "running": True,
            "settings": settings,
            "tasks": ["已根据当前页生成待审草稿", "等待 App/插件内确认内容", "确认前不会发布"],
        })
        _save_social_extension_status(status, _SOCIAL_EXTENSION_STATUS_FILE)
        return {
            "success": True,
            "source": "chrome_extension",
            "draft": draft,
            "requires_owner_review": True,
            "auto_publish_enabled": False,
            "external_actions_locked": True,
            "next_action": "请在插件或 OpenEverything Social 工作台确认/编辑草稿；确认前不会外发。",
        }

    @staticmethod
    def _rpc_social_extension_draft_update(draft_id: str, text: str = "", title: str = "") -> dict:
        """按草稿 ID 更新插件生成的待审草稿；确认前仍不外发。"""
        clean_id = str(draft_id or "").strip()
        if not clean_id:
            return {"success": False, "error": "draft_id required"}
        from src.execution.social import x_auto_ops

        state = x_auto_ops._load_state(x_auto_ops._STATE_FILE)
        drafts = list(state.get("drafts", []) or [])
        for draft in drafts:
            if str(draft.get("id") or "") != clean_id:
                continue
            if text:
                draft["text"] = str(text)[:4000]
                draft["body"] = str(text)[:4000]
            if title:
                draft["title"] = str(title)[:160]
            draft["status"] = "edited"
            draft["review_status"] = "pending"
            draft["edited_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
            state["drafts"] = drafts
            x_auto_ops._save_state(state, x_auto_ops._STATE_FILE)
            return {
                "success": True,
                "draft": draft,
                "requires_owner_review": True,
                "auto_publish_enabled": False,
                "external_actions_locked": True,
            }
        return {"success": False, "error": "draft not found"}

    @staticmethod
    def _rpc_social_extension_draft_review(draft_id: str, approved: bool, reviewer: str = "owner") -> dict:
        """按草稿 ID 审核插件草稿；只改变审核状态，不触发发布。"""
        clean_id = str(draft_id or "").strip()
        if not clean_id:
            return {"success": False, "error": "draft_id required"}
        from src.execution.social import x_auto_ops

        state = x_auto_ops._load_state(x_auto_ops._STATE_FILE)
        drafts = list(state.get("drafts", []) or [])
        for draft in drafts:
            if str(draft.get("id") or "") != clean_id:
                continue
            draft["review_status"] = "approved" if approved else "rejected"
            draft["status"] = "approved" if approved else "rejected"
            draft["reviewed_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
            draft["approved_by"] = reviewer if approved else ""
            state["drafts"] = drafts
            x_auto_ops._save_state(state, x_auto_ops._STATE_FILE)
            return {
                "success": True,
                "draft": draft,
                "requires_owner_review": not approved,
                "auto_publish_enabled": False,
                "external_actions_locked": True,
                "next_action": "已确认内容，但仍不会自动发布；最终外发需要后续明确授权。",
            }
        return {"success": False, "error": "draft not found"}


    @staticmethod
    def _rpc_social_extension_draft_schedule(draft_id: str, scheduled_at: str = "", reviewer: str = "owner") -> dict:
        """把已确认的插件草稿加入待发布排程；只登记队列，不触发外部发布。"""
        clean_id = str(draft_id or "").strip()
        if not clean_id:
            return {
                "success": False,
                "error": "draft_id required",
                "requires_review": True,
                "auto_publish_enabled": False,
                "external_actions_locked": True,
            }

        from datetime import datetime, timedelta

        from src.execution.social import x_auto_ops

        state = x_auto_ops._load_state(x_auto_ops._STATE_FILE)
        drafts = list(state.get("drafts", []) or [])
        now_iso = time.strftime("%Y-%m-%dT%H:%M:%S%z")
        clean_scheduled_at = _bounded_str(scheduled_at, 80)
        if not clean_scheduled_at:
            clean_scheduled_at = (datetime.now() + timedelta(hours=1)).astimezone().isoformat(timespec="minutes")

        for draft in drafts:
            if str(draft.get("id") or "") != clean_id:
                continue
            if draft.get("review_status") != "approved":
                draft["status"] = "needs_review"
                state["drafts"] = drafts
                x_auto_ops._save_state(state, x_auto_ops._STATE_FILE)
                return {
                    "success": False,
                    "requires_review": True,
                    "error": "排程前请先确认人设和内容；未审核草稿不会进入发布时间表",
                    "draft": draft,
                    "auto_publish_enabled": False,
                    "external_actions_locked": True,
                    "next_action": "先点击“确认内容”，再加入排程；仍不会自动外发。",
                }

            schedule_item = {
                "id": f"schedule-{clean_id}",
                "draft_id": clean_id,
                "platform": _bounded_str(draft.get("platform") or "x", 24),
                "title": _bounded_str(draft.get("title") or draft.get("text") or "未命名草稿", 120),
                "text_preview": _bounded_str(draft.get("text") or draft.get("body") or "", 220),
                "scheduled_at": clean_scheduled_at,
                "status": "queued_for_owner_publish",
                "review_status": "approved",
                "reviewer": _bounded_str(reviewer, 80) or "owner",
                "created_at": now_iso,
                "auto_publish_enabled": False,
                "external_actions_locked": True,
                "publishIntent": False,
                "next_action": "到点后提醒用户最终确认；本接口不会发布。",
            }
            queue = [item for item in list(state.get("extension_schedule", []) or []) if str(item.get("draft_id") or "") != clean_id]
            queue.append(schedule_item)
            state["extension_schedule"] = queue[-100:]
            draft["status"] = "scheduled"
            draft["scheduled_at"] = clean_scheduled_at
            draft["scheduled_by"] = _bounded_str(reviewer, 80) or "owner"
            draft["schedule_status"] = "queued_for_owner_publish"
            state["drafts"] = drafts
            state["last_run"] = now_iso
            x_auto_ops._save_state(state, x_auto_ops._STATE_FILE)
            return {
                "success": True,
                "draft": draft,
                "schedule_item": schedule_item,
                "auto_publish_enabled": False,
                "external_actions_locked": True,
                "next_action": "已加入待发布排程；到点仍需要最终确认，不会自动发布。",
            }
        return {
            "success": False,
            "error": "draft not found",
            "auto_publish_enabled": False,
            "external_actions_locked": True,
        }



    @staticmethod
    def _rpc_social_extension_schedule_queue(limit: int = 20) -> dict:
        """读取 Chrome 插件排程队列；到点只标记待最终确认，不触发发布。"""
        try:
            from datetime import datetime

            from src.execution.social import x_auto_ops

            def _parse_time(value: str):
                raw = str(value or "").strip()
                if not raw:
                    return None
                normalized = raw.replace("Z", "+00:00")
                try:
                    parsed = datetime.fromisoformat(normalized)
                    if parsed.tzinfo is None:
                        parsed = parsed.replace(tzinfo=UTC)
                    return parsed.astimezone(UTC)
                except ValueError:
                    return None

            state = x_auto_ops._load_state(x_auto_ops._STATE_FILE)
            raw_queue = state.get("extension_schedule", [])
            if not isinstance(raw_queue, list):
                raw_queue = []
            drafts = list(state.get("drafts", []) or [])
            draft_by_id = {str(draft.get("id") or ""): draft for draft in drafts if isinstance(draft, dict)}
            bounded_limit = min(max(1, int(limit or 20)), 100)
            now_utc = datetime.now(UTC)
            changed = False
            queue = []
            due_count = 0
            for item in raw_queue[-bounded_limit:]:
                if not isinstance(item, dict):
                    continue
                scheduled_dt = _parse_time(str(item.get("scheduled_at") or ""))
                status = str(item.get("status") or "queued_for_owner_publish")
                due = bool(scheduled_dt and scheduled_dt <= now_utc and status == "queued_for_owner_publish")
                if due:
                    status = "awaiting_final_confirmation"
                    item["status"] = status
                    item["due_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
                    item["requires_final_confirmation"] = True
                    draft = draft_by_id.get(str(item.get("draft_id") or ""))
                    if draft:
                        draft["status"] = "awaiting_final_confirmation"
                        draft["schedule_status"] = "awaiting_final_confirmation"
                        draft["due_at"] = item["due_at"]
                    changed = True
                if status == "awaiting_final_confirmation":
                    due_count += 1
                draft_ref = draft_by_id.get(str(item.get("draft_id") or "")) or {}
                draft_preview = {
                    "id": _bounded_str(draft_ref.get("id") or item.get("draft_id"), 120),
                    "platform": _bounded_str(draft_ref.get("platform") or item.get("platform"), 24),
                    "title": _bounded_str(draft_ref.get("title") or item.get("title"), 120),
                    "text": _bounded_str(draft_ref.get("text") or draft_ref.get("body") or item.get("text_preview"), 4000),
                    "review_status": _bounded_str(draft_ref.get("review_status") or item.get("review_status") or "approved", 40),
                    "status": _bounded_str(draft_ref.get("status") or status, 60),
                    "schedule_status": _bounded_str(draft_ref.get("schedule_status") or status, 60),
                }
                for key in (
                    "platform_style",
                    "content_plan",
                    "image_plan",
                    "format_checklist",
                    "safety_checklist",
                    "cost_route",
                ):
                    if key in draft_ref:
                        draft_preview[key] = draft_ref[key]
                queue.append({
                    "id": _bounded_str(item.get("id"), 120),
                    "draft_id": _bounded_str(item.get("draft_id"), 120),
                    "platform": _bounded_str(item.get("platform"), 24),
                    "title": _bounded_str(item.get("title"), 120),
                    "text_preview": _bounded_str(item.get("text_preview"), 220),
                    "scheduled_at": _bounded_str(item.get("scheduled_at"), 80),
                    "status": _bounded_str(status, 60),
                    "review_status": _bounded_str(item.get("review_status") or "approved", 40),
                    "due": status == "awaiting_final_confirmation",
                    "requires_final_confirmation": status == "awaiting_final_confirmation",
                    "draft": draft_preview,
                    "external_actions_locked": True,
                    "auto_publish_enabled": False,
                })
            if changed:
                state["extension_schedule"] = raw_queue
                state["drafts"] = drafts
                state["last_run"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
                x_auto_ops._save_state(state, x_auto_ops._STATE_FILE)
            queue.sort(key=lambda item: item.get("scheduled_at") or "")
            return {
                "success": True,
                "count": len(queue),
                "due_count": due_count,
                "queue": queue,
                "auto_publish_enabled": False,
                "external_actions_locked": True,
                "next_action": "到点后提醒用户最终确认；不会自动发布。",
            }
        except Exception as e:
            logger.warning("读取 Chrome 插件排程队列失败: %s", e)
            return {
                "success": False,
                "count": 0,
                "due_count": 0,
                "queue": [],
                "error": _safe_error(e),
                "auto_publish_enabled": False,
                "external_actions_locked": True,
            }

    @staticmethod
    def _rpc_social_extension_schedule_final_confirm(draft_id: str, reviewer: str = "owner") -> dict:
        """排程到点后的最终确认；只标记可手动发布，不调用发布 worker。"""
        clean_id = str(draft_id or "").strip()
        if not clean_id:
            return {
                "success": False,
                "error": "draft_id required",
                "manual_publish_ready": False,
                "auto_publish_enabled": False,
                "external_actions_locked": True,
            }
        from src.execution.social import x_auto_ops

        state = x_auto_ops._load_state(x_auto_ops._STATE_FILE)
        drafts = list(state.get("drafts", []) or [])
        queue = list(state.get("extension_schedule", []) or [])
        draft = next((item for item in drafts if str(item.get("id") or "") == clean_id), None)
        schedule_item = next((item for item in queue if str(item.get("draft_id") or "") == clean_id), None)
        if not draft or not schedule_item:
            return {
                "success": False,
                "error": "scheduled draft not found",
                "manual_publish_ready": False,
                "auto_publish_enabled": False,
                "external_actions_locked": True,
            }
        if draft.get("review_status") != "approved" or schedule_item.get("review_status") != "approved":
            return {
                "success": False,
                "requires_review": True,
                "error": "最终确认前草稿仍必须先审核通过",
                "draft": draft,
                "schedule_item": schedule_item,
                "manual_publish_ready": False,
                "auto_publish_enabled": False,
                "external_actions_locked": True,
            }
        if schedule_item.get("status") not in {"awaiting_final_confirmation", "ready_for_manual_publish"}:
            return {
                "success": False,
                "requires_due_schedule": True,
                "error": "排程尚未到点，不能进入最终发布确认",
                "draft": draft,
                "schedule_item": schedule_item,
                "manual_publish_ready": False,
                "auto_publish_enabled": False,
                "external_actions_locked": True,
            }
        now_iso = time.strftime("%Y-%m-%dT%H:%M:%S%z")
        schedule_item["status"] = "ready_for_manual_publish"
        schedule_item["final_confirmed_at"] = now_iso
        schedule_item["final_confirmed_by"] = _bounded_str(reviewer, 80) or "owner"
        schedule_item["manual_publish_ready"] = True
        schedule_item["auto_publish_enabled"] = False
        schedule_item["external_actions_locked"] = True
        draft["status"] = "ready_for_manual_publish"
        draft["schedule_status"] = "ready_for_manual_publish"
        draft["final_confirmed_at"] = now_iso
        draft["final_confirmed_by"] = _bounded_str(reviewer, 80) or "owner"
        state["drafts"] = drafts
        state["extension_schedule"] = queue
        state["last_run"] = now_iso
        x_auto_ops._save_state(state, x_auto_ops._STATE_FILE)
        return {
            "success": True,
            "draft": draft,
            "schedule_item": schedule_item,
            "manual_publish_ready": True,
            "auto_publish_enabled": False,
            "external_actions_locked": True,
            "next_action": "已完成最终确认；请在真实页面手动点击发布，或后续显式授权发布器。",
        }



    @staticmethod
    def _rpc_social_extension_growth_feedback(platform: str = "x", limit: int = 6) -> dict:
        """返回 Chrome 插件增长复盘摘要；只读展示，不触发发布或互动。"""
        normalized_platform = str(platform or "x").strip().lower()
        if normalized_platform == "twitter":
            normalized_platform = "x"
        if normalized_platform == "xiaohongshu":
            normalized_platform = "xhs"
        if normalized_platform not in _SOCIAL_EXTENSION_DRAFT_PLATFORMS:
            normalized_platform = "x"
        bounded_limit = min(12, max(1, int(limit or 6)))

        from src.execution.social import x_auto_ops

        state = x_auto_ops._load_state(x_auto_ops._STATE_FILE)
        records = state.get("extension_performance") if isinstance(state.get("extension_performance"), list) else []
        candidates: list[dict] = []
        baseline_count = 0
        for record in reversed(records[-200:]):
            if not isinstance(record, dict):
                continue
            if str(record.get("platform") or "").strip().lower() != normalized_platform:
                continue
            metrics = record.get("metrics") if isinstance(record.get("metrics"), dict) else {}
            likes = _bounded_metric_int(metrics.get("likes"))
            comments = _bounded_metric_int(metrics.get("comments"))
            shares = _bounded_metric_int(metrics.get("shares"))
            impressions = _bounded_metric_int(metrics.get("impressions"))
            saves = _bounded_metric_int(metrics.get("saves"))
            high_signal = (
                str(record.get("outcome") or "") == "high_signal"
                or likes >= 100
                or comments >= 10
                or impressions >= 10_000
            )
            if not high_signal:
                baseline_count += 1
                continue
            tags = [_bounded_str(item, 40) for item in (record.get("tags") if isinstance(record.get("tags"), list) else [])]
            tags = [item for item in tags if item][:6]
            title = _bounded_str(record.get("title") or "未命名高信号内容", 140)
            learning = _bounded_str(record.get("learning"), 220) or "复用该内容的 hook、标签和可执行步骤。"
            reason = _bounded_str(record.get("growth_feedback_reason"), 180) or f"历史高信号：{title}"
            candidates.append({
                "title": title,
                "draft_id": _bounded_str(record.get("draft_id"), 120),
                "url": _bounded_str(record.get("url"), 500),
                "tags": tags,
                "metrics": {
                    "likes": likes,
                    "comments": comments,
                    "shares": shares,
                    "impressions": impressions,
                    "saves": saves,
                    "engagements": _bounded_metric_int(metrics.get("engagements")) or likes + comments + shares + saves,
                },
                "outcome": "high_signal",
                "learning": learning,
                "growth_feedback_reason": reason,
                "captured_at": _bounded_str(record.get("captured_at") or record.get("recorded_at"), 80),
                "auto_publish_enabled": False,
                "external_actions_locked": True,
            })
            if len(candidates) >= bounded_limit:
                break
        tag_counts: dict[str, int] = {}
        for item in candidates:
            for tag in item.get("tags", []):
                tag_counts[tag] = tag_counts.get(tag, 0) + 1
        top_tags = [tag for tag, _count in sorted(tag_counts.items(), key=lambda kv: (-kv[1], kv[0]))[:5]]
        recommendations = []
        if candidates:
            first = candidates[0]
            if top_tags:
                recommendations.append(f"下一轮优先抓 {'/'.join(top_tags[:3])} 相似热点。")
            recommendations.append(_bounded_str(first.get("learning"), 160) or "复用最近高信号内容结构。")
            recommendations.append("继续保持草稿审核：复盘只调权重，不自动发布。")
        else:
            recommendations = ["暂无高信号样本；先发布少量已审核内容，再用采表现建立基线。", "继续抓热点但不要自动外发。"]
        return {
            "success": True,
            "source": "chrome_extension_growth_feedback",
            "platform": normalized_platform,
            "high_signal_count": len(candidates),
            "baseline_count": baseline_count,
            "top_tags": top_tags,
            "signals": candidates,
            "recommendations": recommendations[:4],
            "auto_publish_enabled": False,
            "external_actions_locked": True,
            "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "next_action": "复用高信号选题结构生成下一批待审草稿；仍不自动发布。",
        }

    @staticmethod
    def _rpc_social_extension_growth_draft_batch(platform: str = "x", limit: int = 3) -> dict:
        """基于增长复盘和热点池生成下一批待审草稿；不发布、不评论。"""
        normalized_platform = str(platform or "x").strip().lower()
        if normalized_platform == "twitter":
            normalized_platform = "x"
        if normalized_platform == "xiaohongshu":
            normalized_platform = "xhs"
        if normalized_platform not in _SOCIAL_EXTENSION_DRAFT_PLATFORMS:
            normalized_platform = "x"
        bounded_limit = min(6, max(1, int(limit or 3)))

        trends_payload = ClawBotRPC._rpc_social_extension_trends(normalized_platform, max(bounded_limit, 3))
        trends = trends_payload.get("trends") if isinstance(trends_payload, dict) else []
        if not isinstance(trends, list):
            trends = []

        created: list[dict] = []
        seen_titles: set[str] = set()
        for trend in trends:
            if not isinstance(trend, dict):
                continue
            title = _bounded_str(trend.get("title"), 120)
            if not title or title.lower() in seen_titles:
                continue
            seen_titles.add(title.lower())
            tags = trend.get("tags") if isinstance(trend.get("tags"), list) else []
            page_context = {
                "title": title,
                "selection": title,
                "bodyText": _bounded_str(
                    " ".join([
                        str(trend.get("heat_reason") or ""),
                        str(trend.get("growth_feedback_reason") or ""),
                        str(trend.get("content_angle") or ""),
                        str(trend.get("growth_reason") or ""),
                    ]),
                    1000,
                ),
                "trends": [
                    _bounded_str(item, 80)
                    for item in [*tags[:4], trend.get("source"), trend.get("platform_playbook")]
                    if _bounded_str(item, 80)
                ],
            }
            settings = {
                "personaTags": tags[:6],
                "automationLevel": "draft_only",
                "interactionLevel": "review_only",
                "contentModel": "web-gemini",
                "imageModel": "gpt-image",
            }
            draft_result = ClawBotRPC._rpc_social_extension_draft_create(
                {
                    "platform": normalized_platform,
                    "url": _bounded_str(trend.get("url"), 500),
                    "source": "chrome_extension_growth_feedback",
                    "page_context": page_context,
                    "settings": settings,
                }
            )
            if draft_result.get("success") and isinstance(draft_result.get("draft"), dict):
                draft = draft_result["draft"]
                draft["angle"] = "growth_feedback_reuse"
                draft["growth_feedback_reason"] = _bounded_str(trend.get("growth_feedback_reason"), 180)
                draft["growth_feedback_boost"] = int(trend.get("growth_feedback_boost") or 0)
                draft["platform_score"] = int(trend.get("platform_score") or _extension_platform_trend_score(trend, normalized_platform))
                draft["auto_publish_enabled"] = False
                draft["external_actions_locked"] = True
                draft["publishIntent"] = False
                created.append(draft)
            if len(created) >= bounded_limit:
                break

        return {
            "success": True,
            "source": "chrome_extension_growth_feedback",
            "platform": normalized_platform,
            "created_count": len(created),
            "drafts": created,
            "growth_feedback_applied": bool(trends_payload.get("growth_feedback_applied") if isinstance(trends_payload, dict) else False),
            "requires_owner_review": True,
            "auto_publish_enabled": False,
            "external_actions_locked": True,
            "next_action": "已生成下一批待审热点草稿；请在 App/插件/Telegram 审核，确认前不会外发。",
            "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        }


    @staticmethod
    def _rpc_social_extension_performance_record(payload: dict) -> dict:
        """记录 Chrome 插件只读表现快照；写入增长反馈，不发布、不互动。"""
        record = _sanitize_social_performance_payload(payload)
        from src.execution.social import x_auto_ops

        state = x_auto_ops._load_state(x_auto_ops._STATE_FILE)
        performance_log = list(state.get("extension_performance", []) or [])
        performance_log.append(record)
        state["extension_performance"] = performance_log[-300:]

        growth_feedback = {
            "platform": record["platform"],
            "draft_id": record["draft_id"],
            "outcome": record["outcome"],
            "learning": record["learning"],
            "metrics": record["metrics"],
            "updated_at": record["recorded_at"],
            "next_action": "把高信号选题结构加入后续热点权重；仍不自动发布或互动。",
        }
        drafts = list(state.get("drafts", []) or [])
        for draft in drafts:
            if str(draft.get("id") or "") != record["draft_id"]:
                continue
            snapshots = list(draft.get("performance_snapshots", []) or [])
            snapshots.insert(0, record)
            draft["performance_snapshots"] = snapshots[:20]
            draft["growth_feedback"] = growth_feedback
            break
        state["drafts"] = drafts
        state["growth_feedback"] = growth_feedback
        state["last_run"] = record["recorded_at"]
        x_auto_ops._save_state(state, x_auto_ops._STATE_FILE)

        status = _load_social_extension_status(_SOCIAL_EXTENSION_STATUS_FILE)
        status["online"] = True
        status["platform"] = record["platform"]
        status["last_performance"] = record
        status["growth_feedback"] = growth_feedback
        status["auto_publish_enabled"] = False
        status["external_actions_locked"] = True
        status["updated_at"] = record["recorded_at"]
        _save_social_extension_status(status, _SOCIAL_EXTENSION_STATUS_FILE)
        return {
            "success": True,
            "record": record,
            "growth_feedback": growth_feedback,
            "auto_publish_enabled": False,
            "external_actions_locked": True,
            "next_action": "表现已写入增长反馈池；下一轮选题会参考高信号结构，但不会自动发布/评论/刷量。",
        }

    @staticmethod
    def _rpc_xianyu_compact_status() -> dict:
        """获取闲鱼在统一社媒工作台中的轻量状态。

        这里不复用 FastAPI router，避免 RPC 层反向依赖路由层；只读取系统状态和
        CookieCloud 状态，失败时降级为空状态，保证社媒页不会因为闲鱼子系统异常而崩。
        """
        try:
            status_data = ClawBotRPC._rpc_system_status()
            detail = status_data.get("xianyu", {}) or {}
            result = {
                "running": bool(detail.get("online", False)),
                "online": bool(detail.get("online", False)),
                "cookie_ok": bool(detail.get("cookie_ok", False)),
                "auto_reply_active": bool(detail.get("auto_reply_active", False)),
                "conversations_today": int(detail.get("conversations_today", 0) or 0),
                "unread_chats": int(detail.get("unread_chats", 0) or 0),
            }

            try:
                from src.xianyu.cookie_cloud import get_cookie_cloud_manager

                manager = get_cookie_cloud_manager()
                cc_status = manager.status
                result["cookiecloud_enabled"] = bool(cc_status.get("enabled", False))
                result["cookiecloud_last_sync"] = cc_status.get("last_sync")
            except Exception as e:
                logger.debug("闲鱼 CookieCloud 状态读取失败: %s", e)
                result["cookiecloud_enabled"] = False
            return result
        except Exception as e:
            logger.warning("Xianyu compact status failed: %s", e)
            return {
                "running": False,
                "online": False,
                "cookie_ok": False,
                "auto_reply_active": False,
                "conversations_today": 0,
                "unread_chats": 0,
                "error": _safe_error(e),
            }

    @staticmethod
    def _rpc_xianyu_recent_conversations(limit: int = 10) -> dict:
        """读取闲鱼最近对话摘要，供统一运营工作台展示数量与最近消息。"""
        limit = min(max(1, int(limit or 10)), 50)
        try:
            from src.xianyu.xianyu_context import XianyuContextManager

            ctx = XianyuContextManager()
            with ctx._conn() as c:
                rows = c.execute(
                    """
                    SELECT chat_id, MAX(ts) as last_ts, COUNT(*) as msg_count,
                           (SELECT content FROM messages m2
                            WHERE m2.chat_id = m.chat_id
                            ORDER BY id DESC LIMIT 1) as last_msg
                    FROM messages m
                    GROUP BY chat_id
                    ORDER BY last_ts DESC
                    LIMIT ?
                    """,
                    (limit,),
                ).fetchall()

            conversations = [
                {
                    "chat_id": row[0],
                    "last_ts": row[1],
                    "msg_count": int(row[2] or 0),
                    "last_msg": (row[3] or "")[:100],
                }
                for row in rows
            ]
            return {"conversations": conversations, "total": len(conversations)}
        except ImportError:
            return {"conversations": [], "total": 0}
        except Exception as e:
            logger.debug("读取闲鱼最近对话失败: %s", e)
            return {"conversations": [], "total": 0, "error": _safe_error(e)}

    @staticmethod
    def _rpc_social_ops_workspace() -> dict:
        """统一浏览器运营工作台。

        给桌面端提供一个商业 SaaS 风格的聚合接口：X / 小红书 / 闲鱼统一状态、
        草稿审核计数、人设确认、浏览器登录态和安全闸口。此接口只读，不触发发布。
        """
        _ensure_social_review_drafts()

        def _safe_call(fn, fallback):
            try:
                return fn()
            except Exception as e:
                logger.warning("Social ops workspace sub-call failed: %s", e)
                return fallback

        def _ready_state(value) -> bool:
            if isinstance(value, bool):
                return value
            return str(value or "").lower() in {"ready", "connected", "ok", "true"}

        def _is_publishable(draft: dict) -> bool:
            status = str(draft.get("status") or "").lower()
            return status not in {"published", "publishing", "rejected", "superseded"}

        def _is_approved(draft: dict) -> bool:
            return draft.get("review_status") == "approved" or draft.get("status") == "approved"

        def _draft_counts(platform_aliases: set[str], drafts: list[dict]) -> dict:
            platform_drafts = [
                draft
                for draft in drafts
                if str(draft.get("platform") or "").lower() in platform_aliases and _is_publishable(draft)
            ]
            return {
                "drafts": len(platform_drafts),
                "needs_review": sum(1 for draft in platform_drafts if not _is_approved(draft)),
                "ready_to_publish": sum(1 for draft in platform_drafts if _is_approved(draft)),
            }

        def _draft_review_samples(drafts: list[dict], limit: int = 6) -> list[dict]:
            """把真实待审草稿整理成人设确认样稿。"""
            def _sample_safe(draft: dict, text: str) -> bool:
                seed = draft.get("seed") if isinstance(draft.get("seed"), dict) else {}
                combined = f"{draft.get('title', '')} {draft.get('topic', '')} {text} {seed.get('title', '')}".lower()
                bad_fragments = [
                    "严总",
                    "请求没处理成功",
                    "治国",
                    "总书记",
                    "高考",
                    "查分",
                    "分数线",
                    "雨水",
                    "姆巴佩",
                    "世界杯",
                    "法国vs",
                    "进球",
                    "世界波",
                    "涉毒",
                    "网警",
                    "乌克兰",
                    "全球资产",
                    "openclaw 自动蒸馏",
                ]
                return not any(fragment.lower() in combined for fragment in bad_fragments)

            samples: list[dict] = []
            sorted_drafts = sorted(
                drafts,
                key=lambda item: str(item.get("created_at") or ""),
                reverse=True,
            )
            for draft in sorted_drafts:
                if not _is_publishable(draft) or _is_approved(draft):
                    continue
                platform = str(draft.get("platform") or "x").lower()
                if platform not in {"x", "twitter", "xhs", "xiaohongshu"}:
                    continue
                text = draft.get("text") or draft.get("content") or draft.get("body") or draft.get("title") or ""
                text = str(text).strip()
                if not text:
                    continue
                if not _sample_safe(draft, text):
                    continue
                seed = draft.get("seed") if isinstance(draft.get("seed"), dict) else {}
                samples.append({
                    "id": draft.get("id") or f"sample-{len(samples) + 1}",
                    "platform": "xhs" if platform in {"xhs", "xiaohongshu"} else "x",
                    "status": draft.get("status") or "needs_review",
                    "review_status": draft.get("review_status") or "pending",
                    "title": draft.get("title") or draft.get("topic") or seed.get("title") or text.splitlines()[0][:48],
                    "text": text,
                    "source": seed.get("source") or seed.get("channel") or draft.get("_state_source") or "",
                    "language": seed.get("language") or "",
                    "heat_reason": seed.get("heat_reason") or "",
                })
                if len(samples) >= limit:
                    break
            return samples

        def _first_sample_text(platform_aliases: set[str], samples: list[dict]) -> str:
            """返回平台卡片可直接预览的一条真实样稿。"""
            for sample in samples:
                if str(sample.get("platform") or "").lower() in platform_aliases:
                    return str(sample.get("text") or sample.get("title") or "")[:80]
            return ""

        social_status = _safe_call(ClawBotRPC._rpc_social_status, {"platforms": [], "autopilot_running": False})
        browser_status = _safe_call(ClawBotRPC._rpc_social_browser_status, {"browser_running": False, "x": "unknown", "xhs": "unknown"})
        drafts_payload = _safe_call(ClawBotRPC._rpc_social_drafts, {"drafts": [], "count": 0})
        personas = _safe_call(ClawBotRPC._rpc_social_personas, [])
        persona_review = _safe_call(_persona_review_payload, {
            "approved": False,
            "needs_confirmation": True,
            "proposal": {},
            "state": {},
            "verdict": "人设确认状态不可用，默认禁止自动外发。",
        })
        autopilot_status = _safe_call(ClawBotRPC._rpc_autopilot_status, {"running": False})
        xianyu_status = _safe_call(ClawBotRPC._rpc_xianyu_compact_status, {
            "running": False,
            "online": False,
            "cookie_ok": False,
            "auto_reply_active": False,
            "conversations_today": 0,
            "unread_chats": 0,
        })
        xianyu_recent = _safe_call(lambda: ClawBotRPC._rpc_xianyu_recent_conversations(10), {"conversations": [], "total": 0})
        extension_status = _safe_call(ClawBotRPC._rpc_social_extension_status, _default_social_extension_status())
        if not isinstance(extension_status, dict):
            extension_status = _default_social_extension_status()
        extension_platform = str(extension_status.get("platform") or "x").lower()
        extension_settings = extension_status.get("settings") if isinstance(extension_status.get("settings"), dict) else {}
        strategy_summary = _social_strategy_summary(extension_settings, extension_platform)
        extension_status["strategy_summary"] = strategy_summary
        extension_status["auto_publish_enabled"] = False
        extension_status["external_actions_locked"] = True

        drafts = drafts_payload.get("drafts", []) if isinstance(drafts_payload, dict) else []
        if not isinstance(drafts, list):
            drafts = []
        extension_schedule = _safe_call(ClawBotRPC._rpc_social_extension_schedule_queue, {
            "success": True,
            "count": 0,
            "due_count": 0,
            "queue": [],
            "auto_publish_enabled": False,
            "external_actions_locked": True,
        })
        growth_feedback = _safe_call(lambda: ClawBotRPC._rpc_social_extension_growth_feedback("x", 6), {
            "success": False,
            "platform": "x",
            "signals": [],
            "recommendations": ["暂无增长复盘样本；先积累已审核内容表现。"],
            "auto_publish_enabled": False,
            "external_actions_locked": True,
        })
        if isinstance(growth_feedback, dict):
            growth_feedback["auto_publish_enabled"] = False
            growth_feedback["external_actions_locked"] = True
        else:
            growth_feedback = {
                "success": False,
                "platform": "x",
                "signals": [],
                "recommendations": ["暂无增长复盘样本；先积累已审核内容表现。"],
                "auto_publish_enabled": False,
                "external_actions_locked": True,
            }
        schedule_queue = extension_schedule.get("queue", []) if isinstance(extension_schedule, dict) else []
        if not isinstance(schedule_queue, list):
            schedule_queue = []
        scheduled_counts = {"x": 0, "xhs": 0, "xianyu": 0}
        for item in schedule_queue:
            platform_key = str(item.get("platform") or "x").lower()
            if platform_key in {"x", "twitter"}:
                scheduled_counts["x"] += 1
            elif platform_key in {"xhs", "xiaohongshu"}:
                scheduled_counts["xhs"] += 1
            elif platform_key == "xianyu":
                scheduled_counts["xianyu"] += 1
        review_samples = _draft_review_samples(drafts)
        x_sample_preview = _first_sample_text({"x", "twitter"}, review_samples)
        xhs_sample_preview = _first_sample_text({"xhs", "xiaohongshu"}, review_samples)

        platform_rows = {
            str(item.get("platform") or "").lower(): item
            for item in (social_status.get("platforms", []) if isinstance(social_status, dict) else [])
            if isinstance(item, dict)
        }

        x_counts = _draft_counts({"x", "twitter"}, drafts)
        xhs_counts = _draft_counts({"xhs", "xiaohongshu"}, drafts)
        x_row = platform_rows.get("x") or platform_rows.get("twitter") or {}
        xhs_row = platform_rows.get("xhs") or platform_rows.get("xiaohongshu") or {}
        x_browser_value = browser_status.get("x_ready", browser_status.get("x")) if isinstance(browser_status, dict) else None
        xhs_browser_value = browser_status.get("xiaohongshu_ready", browser_status.get("xhs")) if isinstance(browser_status, dict) else None
        x_ready = bool(x_row.get("connected")) or _ready_state(x_browser_value) or _is_social_cookie_ready("x")
        xhs_ready = bool(xhs_row.get("connected")) or _ready_state(xhs_browser_value) or _is_social_cookie_ready("xhs")
        xianyu_ready = bool(
            xianyu_status.get("cookie_ok")
            or xianyu_status.get("running")
            or xianyu_status.get("online")
        )
        xianyu_metric_count = int(
            xianyu_status.get("conversations_today")
            or xianyu_status.get("unread_chats")
            or xianyu_recent.get("total", 0)
            or 0
        )

        current_persona = personas[0] if personas else {
            "persona_id": "zhou-yuheng",
            "display_name": "待确认热点抽象号人设",
        }
        project_root = Path(__file__).resolve().parents[4]
        skill_files = [
            ("social-autopilot", project_root / "apps/openclaw/skills/social-autopilot/SKILL.md"),
            ("social-persona", project_root / "apps/openclaw/tools/social-persona.md"),
            ("social-topic-library", project_root / "apps/openclaw/tools/social-topic-library.md"),
            ("social-interaction-strategy", project_root / "apps/openclaw/tools/social-interaction-strategy.md"),
        ]
        skill_audit = [
            {"id": skill_id, "path": str(path.relative_to(project_root)), "exists": path.exists()}
            for skill_id, path in skill_files
        ]

        return {
            "success": True,
            "mode": "browser_saas_review_workspace",
            "review_required": True,
            "auto_publish_enabled": False,
            "persona_review_required": bool(persona_review.get("needs_confirmation", True)),
            "review_gate": {
                "enabled": True,
                "policy": "所有 X / 小红书外发草稿必须先由用户确认人设和内容；本接口只读，不触发发布。",
                "needs_review": x_counts["needs_review"] + xhs_counts["needs_review"],
                "ready_to_publish": x_counts["ready_to_publish"] + xhs_counts["ready_to_publish"],
                "scheduled": scheduled_counts["x"] + scheduled_counts["xhs"],
                "due_for_final_confirmation": int(extension_schedule.get("due_count", 0) or 0),
                "growth_feedback_applied": bool(growth_feedback.get("signals")),
            },
            "growth_draft_action": {
                "id": "generate_growth_review_drafts",
                "platform": "x",
                "label": "基于增长复盘生成下一批待审热点草稿",
                "enabled": True,
                "fallback_mode": "growth_feedback_reuse" if growth_feedback.get("signals") else "cold_start_hotspot_pool",
                "limit": 3,
                "requires_owner_review": True,
                "auto_publish_enabled": False,
                "external_actions_locked": True,
                "next_action": (
                    "生成后只进入待审草稿，不自动发布、不自动评论。"
                    if growth_feedback.get("signals")
                    else "暂无增长样本时会冷启动读取热点池生成待审草稿，不自动发布、不自动评论。"
                ),
            },
            "browser_control": {
                "safe_only": True,
                "blocked_prefixes": ["publish", "reply", "delete", "auto_reply", "scout"],
                "actions": [
                    {"id": "open_x", "platform": "x", "label": "打开 X 浏览器"},
                    {"id": "login_x", "platform": "x", "label": "登录 X"},
                    {"id": "open_xhs", "platform": "xhs", "label": "打开小红书浏览器"},
                    {"id": "login_xhs", "platform": "xhs", "label": "登录小红书"},
                    {"id": "status", "platform": "all", "label": "刷新浏览器状态"},
                ],
            },
            "browser_status": browser_status,
            "social_status": social_status,
            "extension_status": extension_status,
            "strategy_summary": strategy_summary,
            "autopilot_status": autopilot_status,
            "drafts": drafts,
            "draft_count": len(drafts),
            "extension_schedule": extension_schedule,
            "growth_feedback": growth_feedback,
            "personas": personas,
            "persona_review": persona_review,
            "review_pack": _social_review_pack_payload(limit=8, ensure=False),
            "persona_check": {
                "needs_confirmation": bool(persona_review.get("needs_confirmation", True)),
                "approved": bool(persona_review.get("approved", False)),
                "current": current_persona,
                "proposal": persona_review.get("proposal", {}),
                "review_samples": review_samples,
                "sample_count": len(review_samples),
                "thesis": persona_review.get("proposal", {}).get(
                    "one_liner",
                    "中文/英文热点观察员 + 抽象吐槽 + 低风险追梗，先积累关注，再沉淀系列内容。",
                ),
                "verdict": persona_review.get("verdict") or "现有人设偏 AI/程序员，需要用户确认后再恢复自动外发。",
            },
            "skill_audit": {
                "exists": all(item["exists"] for item in skill_audit),
                "files": skill_audit,
                "verdict": "已有社媒自动运营 Skill 和人设/选题/互动文件，但需要按热点抽象号方向重写或确认。",
            },
            "platforms": [
                {
                    "id": "x",
                    "name": "X",
                    "title": "X 热点追踪",
                    "subtitle": "中英热点 · 抽象短推",
                    "ready": x_ready,
                    "needs_login": not x_ready,
                    "browser_state": "ready" if x_ready else str(x_browser_value or "unknown"),
                    "status": "已登录" if x_ready else "需登录",
                    "metric": f"{x_counts['needs_review']} 待确认 / {x_counts['ready_to_publish']} 可发布",
                    "detail": "抓中文/英文趋势，生成低风险、好玩、可互动的 X 草稿，发布前必须确认。",
                    "strategy_preset": strategy_summary.get("effective_preset") if strategy_summary.get("effective_preset", "").startswith("x_") else "x_wealth_frontier",
                    "strategy_label": strategy_summary.get("short_label") if strategy_summary.get("effective_preset", "").startswith("x_") else "财富前沿",
                    "growth_loop": strategy_summary.get("growth_loop") if strategy_summary.get("effective_preset", "").startswith("x_") else _SOCIAL_STRATEGY_PRESET_META["x_wealth_frontier"]["growth_loop"],
                    "next_step": "先确认人设与 1 条内容，再点最终发布",
                    "sample_preview": x_sample_preview,
                    "posts_today": int(x_row.get("posts_today", 0) or 0),
                    "total_posts": int(x_row.get("total_posts", 0) or 0),
                    "scheduled": scheduled_counts["x"],
                    **x_counts,
                },
                {
                    "id": "xhs",
                    "name": "小红书",
                    "title": "小红书种草笔记",
                    "subtitle": "标题 · 正文 · 标签",
                    "ready": xhs_ready,
                    "needs_login": not xhs_ready,
                    "browser_state": "ready" if xhs_ready else str(xhs_browser_value or "unknown"),
                    "status": "已登录" if xhs_ready else "需登录",
                    "metric": f"{xhs_counts['needs_review']} 待确认 / {xhs_counts['ready_to_publish']} 可发布",
                    "detail": "复用浏览器发布适配器，图文笔记先在统一审核页确认后再外发。",
                    "strategy_preset": "xhs_lifestyle_tutorial",
                    "strategy_label": "生活攻略",
                    "growth_loop": _SOCIAL_STRATEGY_PRESET_META["xhs_lifestyle_tutorial"]["growth_loop"],
                    "next_step": "先确认人设与笔记内容，再点最终发布",
                    "sample_preview": xhs_sample_preview,
                    "posts_today": int(xhs_row.get("posts_today", 0) or 0),
                    "total_posts": int(xhs_row.get("total_posts", 0) or 0),
                    "scheduled": scheduled_counts["xhs"],
                    **xhs_counts,
                },
                {
                    "id": "xianyu",
                    "name": "闲鱼",
                    "title": "闲鱼自动客服",
                    "subtitle": "客服 · 议价 · 自动发货",
                    "ready": xianyu_ready,
                    "needs_login": not bool(xianyu_status.get("cookie_ok")),
                    "browser_state": "ready" if xianyu_ready else "stopped",
                    "status": "运行中" if xianyu_ready else "未运行",
                    "metric": f"{xianyu_metric_count} 对话",
                    "detail": "复用现有闲鱼客服链路，在统一插件入口查看状态并跳转深度管理。",
                    "strategy_preset": "xianyu_deal_closer",
                    "strategy_label": "成交客服",
                    "growth_loop": _SOCIAL_STRATEGY_PRESET_META["xianyu_deal_closer"]["growth_loop"],
                    "next_step": "打开闲鱼管理页处理客服会话",
                    "sample_preview": "",
                    "conversations_today": xianyu_metric_count,
                    "unread_chats": int(xianyu_status.get("unread_chats", 0) or 0),
                    "auto_reply_active": bool(xianyu_status.get("auto_reply_active", False)),
                    "drafts": 0,
                    "needs_review": 0,
                    "ready_to_publish": 0,
                    "scheduled": scheduled_counts["xianyu"],
                },
            ],
            "xianyu_status": xianyu_status,
            "xianyu_conversations": xianyu_recent.get("conversations", []),
            "recommendation": "先在此工作台确认热点抽象号人设和样稿，再恢复任何自动外发任务。",
            "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        }

    @staticmethod
    def _rpc_social_analytics(days: int = 7) -> dict:
        """Get analytics data used by the desktop social dashboard.

        修复: 避免从 src.bot.globals 导入 execution_hub（可能因循环依赖失败），
        直接调用底层的 content_pipeline.get_post_performance_report。
        """
        try:
            from src.execution.social.content_pipeline import get_post_performance_report
            from src.execution.social.drafts import _draft_store

            report = get_post_performance_report(days=days, draft_store=_draft_store) or {}
            by_platform = report.get("by_platform", {}) or {}
            top_posts = report.get("top_posts", []) or []

            engagement = {
                platform: {
                    "total_likes": int(stats.get("likes", 0) or 0),
                    "total_comments": int(stats.get("comments", 0) or 0),
                    "total_shares": int(stats.get("shares", 0) or 0),
                }
                for platform, stats in by_platform.items()
            }
            follower_growth = {
                platform: {
                    "current": int(stats.get("posts", 0) or 0),
                    "net_change": 0,
                }
                for platform, stats in by_platform.items()
            }

            normalized_top_posts = [
                {
                    "preview": post.get("topic") or post.get("url") or "无标题",
                    "title": post.get("topic") or "",
                    "likes": int(post.get("likes", 0) or 0),
                    "comments": int(post.get("comments", 0) or 0),
                    "shares": int(post.get("shares", 0) or 0),
                }
                for post in top_posts
            ]

            return {
                "days": days,
                "engagement": engagement,
                "follower_growth": follower_growth,
                "top_posts": normalized_top_posts,
                "success": bool(report.get("success", True)),
            }
        except Exception as e:
            logger.warning("Social analytics failed: %s", e)
            return {
                "days": days,
                "engagement": {},
                "follower_growth": {},
                "top_posts": [],
                "success": False,
                "error": _safe_error(e),
            }

    @staticmethod
    async def _rpc_social_discover_topics(count: int = 5) -> dict:
        """Discover hot topics for content creation."""
        try:
            from src.execution.social.content_strategy import discover_hot_topics

            topics = await discover_hot_topics(count=count)
            return {"topics": topics or [], "status": "ok"}
        except Exception as e:
            logger.error("Topic discovery failed: %s", e)
            return {"topics": [], "status": "error", "error": _safe_error(e)}

    @staticmethod
    async def _rpc_social_compose(
        topic: str,
        platform: str = "x",
        persona_name: str = "default",
    ) -> dict:
        """AI content generation pipeline (搬运 content_strategy.py 的 compose 链).

        Full pipeline: load persona -> derive strategy -> compose post.
        Returns generated text ready for user review or direct publish.
        """
        try:
            from src.execution.social.content_strategy import (
                compose_post,
                derive_content_strategy,
                load_persona,
            )

            # Load persona
            persona = load_persona(name=persona_name)

            # Derive strategy
            strategy_result = await derive_content_strategy(
                topic=topic,
                platform=platform,
                persona=persona,
            )
            strategy = strategy_result.get("strategy") if strategy_result.get("success") else None

            # Compose post
            max_len = 280 if platform == "x" else 800
            result = await compose_post(
                topic=topic,
                platform=platform,
                strategy=strategy,
                persona=persona,
                max_length=max_len,
            )

            if result.get("success"):
                return {
                    "success": True,
                    "text": result["text"],
                    "platform": platform,
                    "strategy": strategy,
                    "char_count": len(result["text"]),
                }
            return {"success": False, "error": result.get("error", "Content generation failed")}

        except Exception as e:
            logger.error("Social compose failed: %s", e)
            return {"success": False, "error": _safe_error(e)}

    @staticmethod
    async def _rpc_social_publish(
        platform: str,
        content: str,
    ) -> dict:
        """Publish content to a social platform via adapter pattern.

        通过适配器注册表统一分发，支持 "both" 同时发布到所有平台。
        """
        from src.execution.social.platform_adapter import get_adapter, get_all_adapters
        from src.execution.social.worker_bridge import run_social_worker_async

        try:
            if platform == "both":
                # 同时发布到所有已注册平台
                results = {}
                any_success = False
                for pid, adapter in get_all_adapters().items():
                    try:
                        title, body = adapter.normalize_content(content)
                        payload = adapter.build_worker_payload(body, title)
                        result = await run_social_worker_async(adapter.worker_action, payload)
                        results[pid] = result
                        if result.get("success"):
                            any_success = True
                    except Exception as e:
                        logger.warning("发布到 %s 失败: %s", adapter.display_name, e)
                        results[pid] = {"success": False, "error": str(e)}
                results["success"] = any_success
                return results

            # 单平台发布
            adapter = get_adapter(platform)
            if adapter:
                title, body = adapter.normalize_content(content)
                payload = adapter.build_worker_payload(body, title)
                return await run_social_worker_async(adapter.worker_action, payload)
            else:
                return {"success": False, "error": f"Unknown platform: {platform}"}
        except Exception as e:
            logger.error("Social publish failed: %s", e)
            return {"success": False, "error": _safe_error(e)}

    @staticmethod
    async def _rpc_social_research(topic: str, count: int = 10) -> dict:
        """Deep topic research via browser worker.

        Delegates to the social_browser_worker "research" action which
        scrapes platform data and aggregates insights for the given topic.
        """
        from src.execution.social.worker_bridge import run_social_worker_async

        try:
            result = await run_social_worker_async("research", {"topic": topic, "count": count})
            return result
        except Exception as e:
            logger.error("Social research failed: %s", e)
            return {"success": False, "error": _safe_error(e)}

    @staticmethod
    async def _rpc_social_metrics() -> dict:
        """Get social metrics/analytics via browser worker.

        Returns follower counts, engagement stats, and growth data
        from the social_browser_worker "metrics" action.
        同时注入 running 字段，兼容前端读取 r.running ?? r.active。
        """
        from src.execution.social.worker_bridge import run_social_worker_async

        try:
            result = await run_social_worker_async("metrics", {})
            # 兼容前端：如果 worker 返回了 autopilot_running，同步到 running 字段
            if isinstance(result, dict) and "autopilot_running" in result:
                result.setdefault("running", result["autopilot_running"])
            return result
        except Exception as e:
            logger.error("Social metrics failed: %s", e)
            return {"success": False, "error": _safe_error(e)}

    # ──────────────────────────────────────────────
    #  Social — Drafts
    # ──────────────────────────────────────────────

    @staticmethod
    def _rpc_social_drafts() -> dict:
        """List all social drafts from shared review queue."""
        drafts = [ref["draft"] for ref in _merged_social_draft_refs()]
        return {"drafts": drafts, "count": len(drafts)}

    @staticmethod
    def _rpc_social_draft_update(index: int, text: str) -> dict:
        """Update a draft's text content."""
        ref = _resolve_social_draft_ref(index)
        if not ref:
            return {"success": False, "error": "Invalid draft index"}

        if ref["source"] == "x_auto_ops":
            from src.execution.social import x_auto_ops

            state = x_auto_ops._load_state(x_auto_ops._STATE_FILE)
            drafts = state.get("drafts", [])
            idx = ref["index"]
            if 0 <= idx < len(drafts):
                drafts[idx]["text"] = text
                drafts[idx]["status"] = "edited"
                drafts[idx]["review_status"] = "pending"
                drafts[idx]["edited_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
                state["drafts"] = drafts
                x_auto_ops._save_state(state, x_auto_ops._STATE_FILE)
                return {"success": True}

        from src.social_scheduler import _load_state, _save_state

        state = _load_state()
        drafts = state.get("drafts", [])
        idx = ref["index"]
        if 0 <= idx < len(drafts):
            drafts[idx]["text"] = text
            drafts[idx]["status"] = "edited"
            drafts[idx]["review_status"] = "pending"
            state["drafts"] = drafts
            _save_state(state)
            return {"success": True}
        return {"success": False, "error": "Invalid draft index"}

    @staticmethod
    def _rpc_social_draft_delete(index: int) -> dict:
        """Delete a draft by index."""
        ref = _resolve_social_draft_ref(index)
        if not ref:
            return {"success": False, "error": "Invalid draft index"}

        if ref["source"] == "x_auto_ops":
            from src.execution.social import x_auto_ops

            state = x_auto_ops._load_state(x_auto_ops._STATE_FILE)
            drafts = state.get("drafts", [])
            idx = ref["index"]
            if 0 <= idx < len(drafts):
                drafts[idx]["status"] = "rejected"
                drafts[idx]["review_status"] = "rejected"
                drafts[idx]["rejected_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
                state["drafts"] = drafts
                x_auto_ops._save_state(state, x_auto_ops._STATE_FILE)
                return {"success": True}

        from src.social_scheduler import _load_state, _save_state

        state = _load_state()
        drafts = state.get("drafts", [])
        idx = ref["index"]
        if 0 <= idx < len(drafts):
            drafts.pop(idx)
            state["drafts"] = drafts
            _save_state(state)
            return {"success": True}
        return {"success": False, "error": "Invalid draft index"}

    @staticmethod
    def _rpc_social_draft_review(index: int, approved: bool, reviewer: str = "owner") -> dict:
        """审核社媒草稿：只有 approved 草稿允许进入发布。"""
        ref = _resolve_social_draft_ref(index)
        if not ref:
            return {"success": False, "error": "Invalid draft index"}

        if ref["source"] == "x_auto_ops":
            from src.execution.social import x_auto_ops

            draft_id = str(ref["draft"].get("id") or "")
            return x_auto_ops.mark_draft_review(
                draft_id,
                approved=approved,
                reviewer=reviewer,
                state_path=x_auto_ops._STATE_FILE,
            )

        from src.social_scheduler import _load_state, _save_state
        from src.utils import now_et

        state = _load_state()
        drafts = state.get("drafts", [])
        idx = ref["index"]
        if not (0 <= idx < len(drafts)):
            return {"success": False, "error": "Invalid draft index"}

        draft = drafts[idx]
        draft["review_status"] = "approved" if approved else "rejected"
        draft["reviewed_at"] = now_et().isoformat()
        draft["approved_by"] = reviewer if approved else ""
        if approved and draft.get("status") in {"draft", "ready", "edited", "needs_review", "rejected", "failed"}:
            draft["status"] = "approved"
        elif not approved:
            draft["status"] = "rejected"
        state["drafts"] = drafts
        _save_state(state)
        return {"success": True, "draft": draft}

    @staticmethod
    async def _rpc_social_draft_publish(index: int) -> dict:
        """Publish a reviewed draft immediately.

        安全闸口：社媒外部发布属于高风险动作，必须先由用户在人设/内容确认页
        将草稿标记为 approved，禁止后台任务或旧 UI 直接绕过审核发布。
        """
        import asyncio

        from src.execution.social.worker_bridge import run_social_worker

        ref = _resolve_social_draft_ref(index)
        if not ref:
            return {"success": False, "error": "Invalid draft index"}

        if ref["source"] == "x_auto_ops":
            draft = ref["draft"]
            if draft.get("review_status") != "approved":
                from src.execution.social import x_auto_ops

                return x_auto_ops.require_draft_review(draft, state_path=x_auto_ops._STATE_FILE)
            platform = str(draft.get("platform") or "x").lower()
            content = draft.get("text") or draft.get("content") or draft.get("body") or ""
            if platform in {"xhs", "xiaohongshu"}:
                title = draft.get("title") or content.split("\n")[0][:50]
                body = draft.get("body") or content[len(str(title)) :].strip() or content
                result = await asyncio.to_thread(run_social_worker, "publish_xhs", {"title": title, "body": body})
            else:
                result = await asyncio.to_thread(run_social_worker, "publish_x", {"text": content})
            if result.get("success"):
                from src.execution.social import x_auto_ops

                x_auto_ops.mark_published(draft, result, state_path=x_auto_ops._STATE_FILE)
            else:
                from src.execution.social import x_auto_ops

                x_auto_ops.mark_failed(
                    draft,
                    result.get("error") or result.get("status") or "unknown",
                    state_path=x_auto_ops._STATE_FILE,
                )
            return result

        from src.social_scheduler import _load_state, _save_state

        state = _load_state()
        drafts = state.get("drafts", [])
        idx = ref["index"]
        if not (0 <= idx < len(drafts)):
            return {"success": False, "error": "Invalid draft index"}

        draft = drafts[idx]
        if draft.get("review_status") != "approved":
            draft["status"] = "needs_review"
            state["drafts"] = drafts
            _save_state(state)
            return {
                "success": False,
                "requires_review": True,
                "error": "发布前请先确认人设和内容，草稿审核通过后才允许发布",
                "draft": draft,
            }

        platform = draft.get("platform", "x")
        content = draft.get("text") or draft.get("content") or draft.get("body") or ""
        draft["status"] = "publishing"
        state["drafts"] = drafts
        _save_state(state)

        if platform in ("x", "twitter"):
            result = await asyncio.to_thread(run_social_worker, "publish_x", {"text": content})
        elif platform in ("xhs", "xiaohongshu"):
            title = content.split("\n")[0][:50] if "\n" in content else content[:50]
            body = content[len(title) :].strip() if "\n" in content else content
            result = await asyncio.to_thread(run_social_worker, "publish_xhs", {"title": title, "body": body})
        else:
            result = {"success": False, "error": f"Unknown platform: {platform}"}

        latest_state = _load_state()
        latest_drafts = latest_state.get("drafts", [])
        if 0 <= idx < len(latest_drafts):
            latest_drafts[idx]["status"] = "published" if result.get("success") else "failed"
            latest_drafts[idx]["publish_result"] = result
            latest_state["drafts"] = latest_drafts
            _save_state(latest_state)

        return result

    # ──────────────────────────────────────────────
    #  Social — Autopilot
    # ──────────────────────────────────────────────

    @staticmethod
    def _rpc_autopilot_status() -> dict:
        """Get social autopilot scheduler status."""
        try:
            from src.social_scheduler import SocialAutopilot

            return SocialAutopilot().status()
        except Exception as e:
            logger.warning("Autopilot status failed: %s", e)
            return {"running": False, "error": _safe_error(e)}

    @staticmethod
    def _rpc_autopilot_start() -> dict:
        """Start the social autopilot scheduler."""
        try:
            from src.social_scheduler import SocialAutopilot

            return SocialAutopilot().start()
        except Exception as e:
            logger.error("Autopilot start failed: %s", e)
            return {"status": "error", "error": _safe_error(e)}

    @staticmethod
    def _rpc_autopilot_stop() -> dict:
        """Stop the social autopilot scheduler."""
        try:
            from src.social_scheduler import SocialAutopilot

            return SocialAutopilot().stop()
        except Exception as e:
            logger.error("Autopilot stop failed: %s", e)
            return {"status": "error", "error": _safe_error(e)}

    @staticmethod
    def _rpc_autopilot_trigger(job_id: str) -> dict:
        """Manually trigger a specific autopilot job."""
        try:
            from src.social_scheduler import SocialAutopilot

            return SocialAutopilot().trigger_job(job_id)
        except Exception as e:
            logger.error("Autopilot trigger failed: %s", e)
            return {"success": False, "error": _safe_error(e)}

    @staticmethod
    def _rpc_social_personas() -> list:
        """List available social personas from data/social_personas/.

        Reads JSON files from the personas directory and returns a summary
        list with id, name, active status, and platform_style for each.
        """
        import json
        from pathlib import Path

        personas: list = []
        persona_dir = Path(__file__).resolve().parent.parent.parent / "data" / "social_personas"
        if not persona_dir.is_dir():
            return personas

        try:
            for f in sorted(persona_dir.glob("*.json")):
                try:
                    data = json.loads(f.read_text(encoding="utf-8"))
                    personas.append(
                        {
                            "id": f.stem,
                            "name": data.get("name", f.stem),
                            "active": data.get("active", True),
                            "platform_style": data.get("platform_style", {}),
                        }
                    )
                except Exception as e:  # noqa: F841
                    continue
        except Exception as e:
            logger.warning("Failed to list personas: %s", e)

        return personas

    @staticmethod
    async def _rpc_social_calendar(days: int = 7) -> dict:
        """Generate a content calendar for the next N days.

        Uses discover_hot_topics to gather trending topics and formats
        them into a simple day-by-day content plan.
        """
        try:
            from src.execution.social.content_strategy import discover_hot_topics

            topics = await discover_hot_topics(count=days * 2)
            calendar: list = []
            for i in range(days):
                day_topics = topics[i * 2 : i * 2 + 2] if topics else []
                calendar.append(
                    {
                        "day": i + 1,
                        "topics": day_topics,
                        "slots": ["morning", "evening"],
                    }
                )
            return {"success": True, "days": days, "calendar": calendar}
        except Exception as e:
            logger.error("Social calendar generation failed: %s", e)
            return {"success": False, "error": _safe_error(e), "calendar": []}

    # ──────────────────────────────────────────────
    #  Image Generation (ComfyUI + Cloud Fallback)
    # ──────────────────────────────────────────────

    @staticmethod
    async def _rpc_generate_image(prompt: str, **kwargs) -> dict:
        """Generate image via ComfyUI or cloud fallback.

        Tries local ComfyUI first (free, fast, full workflow control),
        then falls back to SiliconFlow/Pollinations cloud APIs.
        """
        try:
            from src.tools.comfyui_client import generate_image

            path = await generate_image(prompt, **kwargs)
            return {"success": bool(path), "path": path}
        except Exception as e:
            logger.error("Image generation RPC failed: %s", e)
            return {"success": False, "error": _safe_error(e)}

    @staticmethod
    async def _rpc_generate_persona_photo(persona: str, scenario: str, mood: str = "natural") -> dict:
        """Generate persona-consistent photo for social media.

        Uses persona visual identity for prompt construction.
        ComfyUI local first, cloud fallback.
        """
        try:
            from src.tools.comfyui_client import generate_persona_photo

            path = await generate_persona_photo(persona, scenario, mood)
            return {"success": bool(path), "path": path}
        except Exception as e:
            logger.error("Persona photo RPC failed: %s", e)
            return {"success": False, "error": _safe_error(e)}

    # ──────────────────────────────────────────────
    #  Memory
    # ──────────────────────────────────────────────

    @staticmethod
    def _rpc_memory_search(
        query: str,
        limit: int = 10,
        mode: str = "hybrid",
        category: str | None = None,
    ) -> dict:
        """Search shared memory (hybrid / semantic / keyword).

        Returns dict with query, mode, results list, and total_count.
        """
        from src.bot.globals import shared_memory

        results: list = []
        try:
            if mode == "semantic":
                # semantic_search returns List[Dict]
                raw_list = shared_memory.semantic_search(
                    query=query,
                    limit=limit,
                    category=category,
                )
                raw_results = raw_list or []
            else:
                # search() returns Dict with "results" key
                raw_dict = shared_memory.search(
                    query=query,
                    limit=limit,
                    mode=mode,
                )
                raw_results = (raw_dict or {}).get("results", [])

            for r in raw_results:
                results.append(
                    {
                        "key": r.get("key", ""),
                        "value": r.get("value", ""),
                        "category": r.get("category", ""),
                        "importance": r.get("importance", 1),
                        "access_count": r.get("access_count", 0),
                        "similarity": r.get("similarity", r.get("score", 0.0)),
                        "match_type": r.get("match_type", ""),
                        "source_bot": r.get("source_bot", ""),
                    }
                )
        except Exception as e:
            logger.warning("Memory search failed: %s", e)

        return {
            "query": query,
            "mode": mode,
            "results": results,
            "total_count": len(results),
        }

    @staticmethod
    def _rpc_memory_stats() -> dict:
        """Get memory system statistics."""
        from src.bot.globals import shared_memory

        _empty = {
            "total_entries": 0,
            "by_category": {},
            "total_relations": 0,
            "avg_importance": 0.0,
            "engine": "sqlite",
        }
        try:
            stats = shared_memory.get_stats()
            return {
                "total_entries": stats.get("total_entries", 0),
                "by_category": stats.get("by_category", {}),
                "total_relations": stats.get("total_relations", 0),
                "avg_importance": stats.get("avg_importance", 0.0),
                "engine": stats.get("engine", "sqlite"),
            }
        except Exception as e:
            logger.warning("Failed to get memory stats: %s", e)
            return _empty

    @staticmethod
    def _rpc_memory_delete(key: str) -> dict:
        """Delete a memory entry by key."""
        from src.bot.globals import shared_memory

        try:
            result = shared_memory.forget(key)
            if result.get("success"):
                return {"success": True, "deleted": result.get("deleted", 1), "key": key}
            return {"success": False, "error": result.get("error", f"未找到: {key}")}
        except Exception as e:
            logger.warning("Memory delete failed: %s", e)
            return {"success": False, "error": _safe_error(e)}

    @staticmethod
    def _rpc_memory_update(key: str, value: str) -> dict:
        """Update a memory entry value by re-writing the same key."""
        from src.bot.globals import shared_memory

        try:
            search_result = shared_memory.search(key, limit=20)
            existing = next(
                (item for item in (search_result or {}).get("results", []) if item.get("key") == key),
                None,
            )
            if not existing:
                return {"success": False, "error": f"未找到: {key}"}

            remember_result = shared_memory.remember(
                key=key,
                value=value,
                category=existing.get("category") or "general",
                source_bot=existing.get("source_bot") or "manager",
                importance=int(existing.get("importance", 1) or 1),
            )
            return {
                "success": bool(remember_result.get("success", False)),
                "key": key,
                "value": value,
            }
        except Exception as e:
            logger.warning("Memory update failed: %s", e)
            return {"success": False, "error": _safe_error(e)}

    # ──────────────────────────────────────────────
    #  API Pool
    # ──────────────────────────────────────────────

    @staticmethod
    def _rpc_pool_stats() -> dict:
        """Get free API pool (LiteLLM router) statistics.

        额外注入 today_cost / week_cost / month_cost / budget 字段，
        供前端 AIConfig 面板展示成本统计。
        """
        from src.litellm_router import free_pool

        try:
            stats = free_pool.get_stats()
        except Exception as e:
            logger.warning("Failed to get pool stats: %s", e)
            stats = {}

        # 注入成本统计字段（从 CostAnalyzer 读取）
        try:
            from src.monitoring import cost_analyzer
            # 今日成本：最近 24 小时
            daily_data = cost_analyzer.analyze_by_bot(hours=24)
            stats["today_cost"] = round(
                sum(v.get("cost_usd", 0) for v in daily_data.values()), 4
            )
            # 本周成本：最近 7 天
            weekly_data = cost_analyzer.analyze_by_bot(hours=168)
            stats["week_cost"] = round(
                sum(v.get("cost_usd", 0) for v in weekly_data.values()), 4
            )
            # 本月成本：最近 30 天
            monthly_data = cost_analyzer.analyze_by_bot(hours=720)
            stats["month_cost"] = round(
                sum(v.get("cost_usd", 0) for v in monthly_data.values()), 4
            )
        except Exception as e:
            logger.warning("注入成本统计失败，使用默认值: %s", e)
            stats.setdefault("today_cost", 0.0)
            stats.setdefault("week_cost", 0.0)
            stats.setdefault("month_cost", 0.0)

        # 注入预算字段（从环境变量或 CostController 读取）
        try:
            import os
            # 日预算 * 30 = 月预算估算
            daily_budget = float(os.environ.get("OMEGA_DAILY_BUDGET", "50.0"))
            stats["budget"] = round(daily_budget * 30, 2)
        except Exception:
            stats.setdefault("budget", 0.0)

        return stats

    # ──────────────────────────────────────────────
    #  Metrics
    # ──────────────────────────────────────────────

    @staticmethod
    def _rpc_prometheus_metrics() -> str:
        """Get Prometheus metrics in text exposition format."""
        from src.monitoring import prom

        try:
            return prom.render()
        except Exception as e:  # noqa: F841
            return ""

    # ──────────────────────────────────────────────
    #  Shopping — 比价引擎
    # ──────────────────────────────────────────────

    @staticmethod
    async def _rpc_compare_prices(
        query: str,
        limit_per_platform: int = 5,
        use_ai_summary: bool = True,
    ) -> dict:
        """Compare prices across multiple platforms.

        搬运 什么值得买 + 京东公开搜索 + AI 分析总结。
        Layer 4 (商务层) gap fill — no login required.
        """
        from src.shopping.price_engine import compare_prices

        try:
            report = await compare_prices(
                query,
                use_ai_summary=use_ai_summary,
                limit_per_platform=limit_per_platform,
            )
            return {
                "success": True,
                "query": report.query,
                "results": report.results,
                "best_deal": report.best_deal,
                "ai_summary": report.ai_summary,
                "platforms": report.searched_platforms,
                "count": len(report.results),
            }
        except Exception as e:
            logger.error("Price comparison failed for '%s': %s", query, e)
            return {"success": False, "error": _safe_error(e)}
