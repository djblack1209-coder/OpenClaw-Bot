"""Local guidance for retired news commands; never fetch or deliver a report."""

import os
import re

_BOT_USERNAME = re.compile(r"[A-Za-z][A-Za-z0-9_]{4,31}")
_LEGACY_NEWS_COMMAND = re.compile(
    r"(?:/news|(?:帮我|给我|请|麻烦|我想|想要)?"
    r"(?:看看|查看|看一下|查一下|看|来个|来条|打开)?(?:今天的?|今日的?)?"
    r"(?:新闻|科技早报|早报|今日新闻|最新消息|今天新闻)"
    r"(?:吧|啊|呢|呀|一下|看看)?[。！!?？]?)",
    re.IGNORECASE,
)


def is_legacy_news_command(text: str) -> bool:
    """Keep historical exact commands without swallowing topic news queries."""
    return bool(_LEGACY_NEWS_COMMAND.fullmatch(text.strip()))


def global_intelligence_news_guidance(*, channel: str = "telegram") -> str:
    """Point to the dedicated Bot using only an explicitly configured username."""
    username = os.environ.get("INTEL_BRIEF_TELEGRAM_BOT_USERNAME", "").strip()
    if username.startswith("@"):
        username = username[1:]
    valid_username = bool(_BOT_USERNAME.fullmatch(username)) and username.lower().endswith("bot")
    lines = ["科技早报已归并至 Global Intelligence Bot。", ""]
    if valid_username:
        lines.append(f"打开 @{username}：https://t.me/{username}")
    else:
        lines.append("当前未配置有效的 Bot 用户名；请打开你已添加的 Global Intelligence Bot。")
    lines.extend([
        "在该 Bot 使用：",
        "/today 今日简报",
        "/ai AI 科技",
        "/market 市场资金",
    ])
    if channel == "wechat":
        lines.extend(["", "微信也可发送 700 查看每日简报菜单。"])
    return "\n".join(lines)
