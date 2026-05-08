"""
统一插件商店 API — 扫描本地技能和扩展目录。

该路由服务桌面端 Bot 商店页面，返回本地已安装的 NPM Skills、
NPM Extensions 和 Bot Skills 目录，不执行安装或卸载动作。
"""

import json
import logging
import re
from pathlib import Path
from typing import Any

from fastapi import APIRouter

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/store")

# 从 src/api/routers/store.py 推导到 packages/clawbot，再到项目根目录。
_CLAWBOT_ROOT = Path(__file__).resolve().parents[3]
_PROJECT_ROOT = _CLAWBOT_ROOT.parents[1]

_NPM_SKILLS_DIR = _PROJECT_ROOT / "packages" / "openclaw-npm" / "skills"
_NPM_EXTENSIONS_DIR = _PROJECT_ROOT / "packages" / "openclaw-npm" / "extensions"
_BOT_SKILLS_DIR = _PROJECT_ROOT / "apps" / "openclaw" / "skills"


def _parse_skill_md_frontmatter(path: Path) -> dict[str, Any]:
    """解析 SKILL.md 顶部 frontmatter，失败时返回空字典。"""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        logger.warning("读取 Skill 元数据失败: %s", exc)
        return {}

    match = re.match(r"^---\s*\n(.*?)\n---", text, re.DOTALL)
    if not match:
        return {}

    result: dict[str, Any] = {}
    lines = match.group(1).splitlines()
    index = 0
    while index < len(lines):
        raw_line = lines[index]
        line = raw_line.strip()
        index += 1
        if not line or line.startswith("#") or ":" not in line:
            continue

        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip()
        if value in {"|", ">"}:
            multi_lines: list[str] = []
            while index < len(lines) and lines[index].startswith((" ", "\t")):
                multi_lines.append(lines[index].strip())
                index += 1
            value = " ".join(multi_lines)
        elif (value.startswith('"') and value.endswith('"')) or (
            value.startswith("'") and value.endswith("'")
        ):
            value = value[1:-1]
        result[key] = value

    return result


def _parse_package_json(path: Path) -> dict[str, Any]:
    """解析 package.json，失败时返回空字典。"""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("读取扩展 package.json 失败: %s", exc)
        return {}


def _decode_metadata(raw_metadata: Any) -> dict[str, Any]:
    """解析 Skill frontmatter 中可能存在的 metadata JSON 字段。"""
    if not isinstance(raw_metadata, str):
        return {}

    value = raw_metadata.strip()
    if not value.startswith("{"):
        return {}

    try:
        return json.loads(value.replace("'", '"'))
    except json.JSONDecodeError:
        return {}


def _scan_npm_skills() -> list[dict[str, Any]]:
    """扫描 NPM Skills 目录。"""
    category_map = {
        "discord": "通讯社交",
        "slack": "通讯社交",
        "bluebubbles": "通讯社交",
        "himalaya": "通讯社交",
        "apple-notes": "笔记效率",
        "apple-reminders": "笔记效率",
        "bear-notes": "笔记效率",
        "notion": "笔记效率",
        "things-mac": "笔记效率",
        "trello": "笔记效率",
        "openai-image-gen": "AI 生成",
        "openai-whisper": "AI 生成",
        "openai-whisper-api": "AI 生成",
        "gemini": "AI 生成",
        "sherpa-onnx-tts": "AI 生成",
        "sag": "AI 生成",
        "summarize": "AI 生成",
        "model-usage": "AI 生成",
        "github": "开发工具",
        "gh-issues": "开发工具",
        "skill-creator": "开发工具",
        "clawhub": "开发工具",
        "mcporter": "开发工具",
        "tmux": "开发工具",
        "eightctl": "开发工具",
        "blucli": "开发工具",
        "spotify-player": "媒体娱乐",
        "video-frames": "媒体娱乐",
        "gifgrep": "媒体娱乐",
        "songsee": "媒体娱乐",
        "gog": "媒体娱乐",
        "weather": "信息获取",
        "blogwatcher": "信息获取",
        "xurl": "信息获取",
        "goplaces": "信息获取",
        "nano-pdf": "文档处理",
        "nano-banana-pro": "文档处理",
        "peekaboo": "文档处理",
        "1password": "安全密码",
        "openhue": "硬件 IoT",
        "camsnap": "硬件 IoT",
        "healthcheck": "系统监控",
        "voice-call": "语音通话",
        "ordercli": "电商工具",
    }

    items: list[dict[str, Any]] = []
    if not _NPM_SKILLS_DIR.exists():
        return items

    for skill_dir in sorted(_NPM_SKILLS_DIR.iterdir()):
        if not skill_dir.is_dir():
            continue
        skill_md = skill_dir / "SKILL.md"
        if not skill_md.exists():
            continue

        meta = _parse_skill_md_frontmatter(skill_md)
        metadata = _decode_metadata(meta.get("metadata"))
        openclaw_meta = metadata.get("openclaw", {}) if isinstance(metadata, dict) else {}
        skill_id = skill_dir.name
        items.append(
            {
                "id": skill_id,
                "name": meta.get("name", skill_id),
                "description": meta.get("description", ""),
                "emoji": openclaw_meta.get("emoji", "🧩"),
                "type": "skill",
                "category": category_map.get(skill_id, "其他"),
                "status": "installed",
                "homepage": meta.get("homepage", ""),
                "requires": openclaw_meta.get("requires", {}),
            }
        )

    return items


def _scan_npm_extensions() -> list[dict[str, Any]]:
    """扫描 NPM Extensions 目录。"""
    category_map = {
        "telegram": "聊天平台",
        "discord": "聊天平台",
        "slack": "聊天平台",
        "feishu": "聊天平台",
        "msteams": "聊天平台",
        "googlechat": "聊天平台",
        "line": "聊天平台",
        "mattermost": "聊天平台",
        "matrix": "聊天平台",
        "irc": "聊天平台",
        "signal": "聊天平台",
        "nextcloud-talk": "聊天平台",
        "synology-chat": "聊天平台",
        "nostr": "聊天平台",
        "tlon": "聊天平台",
        "twitch": "聊天平台",
        "zalo": "聊天平台",
        "zalouser": "聊天平台",
        "lobster": "聊天平台",
        "imessage": "Apple 消息",
        "bluebubbles": "Apple 消息",
        "voice-call": "语音通话",
        "talk-voice": "语音通话",
        "phone-control": "语音通话",
        "llm-task": "AI 核心",
        "copilot-proxy": "AI 核心",
        "open-prose": "AI 核心",
        "acpx": "AI 核心",
        "memory-core": "记忆系统",
        "memory-lancedb": "记忆系统",
        "device-pair": "设备连接",
        "shared": "基础设施",
        "test-utils": "基础设施",
        "thread-ownership": "基础设施",
        "diffs": "基础设施",
        "diagnostics-otel": "诊断监控",
        "google-gemini-cli-auth": "认证模块",
        "minimax-portal-auth": "认证模块",
        "qwen-portal-auth": "认证模块",
    }

    items: list[dict[str, Any]] = []
    if not _NPM_EXTENSIONS_DIR.exists():
        return items

    for ext_dir in sorted(_NPM_EXTENSIONS_DIR.iterdir()):
        if not ext_dir.is_dir():
            continue
        package_json = ext_dir / "package.json"
        if not package_json.exists():
            continue

        package = _parse_package_json(package_json)
        ext_id = ext_dir.name
        items.append(
            {
                "id": ext_id,
                "name": package.get("name", ext_id).replace("@openclaw/", ""),
                "description": package.get("description", ""),
                "emoji": "🔌",
                "type": "extension",
                "category": category_map.get(ext_id, "其他"),
                "version": package.get("version", ""),
                "status": "installed",
            }
        )

    return items


def _scan_bot_skills() -> list[dict[str, Any]]:
    """扫描 Bot Skills 目录。"""
    category_map = {
        "alpha-research-pipeline": "交易金融",
        "drawdown-kill-switch": "交易金融",
        "execution-risk-gate": "交易金融",
        "money": "交易金融",
        "pnl-daily-brief": "交易金融",
        "profit-war-room": "交易金融",
        "recovery-retrain-loop": "交易金融",
        "free-ride": "交易金融",
        "social-autopilot": "社媒运营",
        "channel-command-center": "社媒运营",
        "telegram-lane-router": "社媒运营",
        "cli-anything": "开发 DevOps",
        "dev-todo-mode": "开发 DevOps",
        "gstack-review": "开发 DevOps",
        "spec-generate": "开发 DevOps",
        "frontend-design": "开发 DevOps",
        "web-artifacts-builder": "开发 DevOps",
        "superpowers-workflow": "开发 DevOps",
        "clawbot-self-heal": "AI 自治",
        "self-improving-agent": "AI 自治",
        "find-skills": "AI 自治",
        "usecase-playbook-router": "AI 自治",
        "pm-debate": "产品协作",
        "product-team": "产品协作",
        "doc-coauthoring": "产品协作",
        "guide": "产品协作",
        "ux-walkthrough": "产品协作",
        "playwright": "浏览器爬虫",
        "page-agent": "浏览器爬虫",
        "crawl4ai": "浏览器爬虫",
        "openclaw-tavily-search": "浏览器爬虫",
        "openclaw-backup": "系统运维",
        "cost-quota-dashboard": "系统运维",
        "glmocr": "系统运维",
        "openviking": "系统运维",
    }

    items: list[dict[str, Any]] = []
    if not _BOT_SKILLS_DIR.exists():
        return items

    for skill_dir in sorted(_BOT_SKILLS_DIR.iterdir()):
        if not skill_dir.is_dir():
            continue
        skill_md = skill_dir / "SKILL.md"
        if not skill_md.exists():
            continue

        meta = _parse_skill_md_frontmatter(skill_md)
        metadata = _decode_metadata(meta.get("metadata"))
        skill_id = skill_dir.name
        version = ""
        category = category_map.get(skill_id, "其他")
        if isinstance(metadata, dict):
            version = str(metadata.get("version", ""))
            category = str(metadata.get("category", category))

        meta_json = skill_dir / "_meta.json"
        if meta_json.exists():
            parsed_meta = _parse_package_json(meta_json)
            version = version or str(parsed_meta.get("version", ""))

        items.append(
            {
                "id": skill_id,
                "name": meta.get("name", skill_id),
                "description": meta.get("description", ""),
                "emoji": "🤖",
                "type": "bot-skill",
                "category": category,
                "version": version,
                "status": "installed",
            }
        )

    return items


@router.get("/catalog")
async def get_store_catalog() -> dict[str, Any]:
    """获取统一商店目录。"""
    skills = _scan_npm_skills()
    extensions = _scan_npm_extensions()
    bot_skills = _scan_bot_skills()

    all_items = skills + extensions + bot_skills
    categories: dict[str, int] = {}
    for item in all_items:
        category = str(item.get("category", "其他"))
        categories[category] = categories.get(category, 0) + 1

    return {
        "skills": skills,
        "extensions": extensions,
        "bot_skills": bot_skills,
        "summary": {
            "total_skills": len(skills),
            "total_extensions": len(extensions),
            "total_bot_skills": len(bot_skills),
            "total": len(all_items),
            "categories": categories,
        },
    }


@router.get("/categories")
async def get_store_categories() -> dict[str, Any]:
    """获取商店所有分类及计数。"""
    catalog = await get_store_catalog()
    return {"categories": catalog["summary"]["categories"]}
