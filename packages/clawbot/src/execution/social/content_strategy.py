"""
Social — 内容策略引擎

从 execution_hub.py 提取的社交内容策略逻辑:
- 热点话题发现
- 内容策略推导
- 自动发帖管道
- 人设驱动的内容生成
"""
import json
import logging
from pathlib import Path
from typing import Dict, List, Optional
from json_repair import loads as jloads

from src.execution._ai import ai_pool
from src.execution._utils import extract_json_object
from src.utils import scrub_secrets

logger = logging.getLogger(__name__)


async def discover_hot_topics(count: int = 5) -> List[Dict]:
    """发现当前热点话题 — 优先真实热搜，LLM 作为回退。

    数据源优先级:
      1. 真实平台热搜 (微博/百度/知乎) — 免费公开 API
      2. LLM 生成 — 仅在真实数据全部失败时使用
    """
    # 优先: 真实热搜数据
    try:
        from src.execution.social.real_trending import fetch_real_trending
        real_topics = await fetch_real_trending(limit=count)
        if real_topics and len(real_topics) >= 3:
            logger.info("[ContentStrategy] 使用真实热搜数据 (%d 条)", len(real_topics))
            return real_topics[:count]
    except Exception as e:
        logger.debug("[ContentStrategy] 真实热搜获取失败，回退到 LLM: %s", e)

    # 回退: LLM 生成
    prompt = (
        f"请列出当前最值得关注的 {count} 个科技/AI/加密货币热点话题，"
        "每个话题包含标题、简述、热度评分(1-10)。"
        f'以 JSON 数组返回: [{{"title":"...", "summary":"...", "score":8}}]'
    )
    try:
        result = await ai_pool.call(prompt)
        if result.get("success"):
            raw = result.get("raw", "")
            # 尝试解析 JSON 数组
            import re
            match = re.search(r'\[.*\]', raw, re.DOTALL)
            if match:
                topics = jloads(match.group())
                if isinstance(topics, list):
                    return topics[:count]
            parsed = extract_json_object(raw)
            if parsed and "topics" in parsed:
                return parsed["topics"][:count]
        return []
    except Exception as e:
        logger.error(f"[ContentStrategy] discover topics failed: {scrub_secrets(str(e))}")
        return []


async def derive_content_strategy(
    topic: str,
    platform: str = "x",
    persona: Optional[Dict] = None,
) -> Dict:
    """为指定话题推导内容策略"""
    persona_hint = ""
    if persona:
        name = persona.get("name", "")
        voice = persona.get("voice", "")
        persona_hint = f"\n人设: {name}, 风格: {voice}"

    prompt = (
        f"为以下话题制定{platform}平台的内容策略:\n"
        f"话题: {topic}{persona_hint}\n\n"
        "请返回 JSON: "
        '{"angle":"切入角度", "hook":"开头吸引语", '
        '"key_points":["要点1","要点2"], "cta":"行动号召", '
        '"hashtags":["标签1"], "estimated_engagement":"high/medium/low"}'
    )
    try:
        result = await ai_pool.call(prompt)
        if result.get("success"):
            parsed = extract_json_object(result.get("raw", ""))
            if parsed:
                return {"success": True, "strategy": parsed}
        return {"success": False, "error": "策略生成失败"}
    except Exception as e:
        return {"success": False, "error": str(e)}


async def compose_post(
    topic: str,
    platform: str = "x",
    strategy: Optional[Dict] = None,
    persona: Optional[Dict] = None,
    max_length: int = 280,
) -> Dict:
    """AI 生成社交媒体帖子"""
    constraints = []
    if platform == "x":
        constraints.append(f"不超过 {max_length} 字符")
        constraints.append("适合 Twitter/X 的简洁风格")
    elif platform == "xhs":
        constraints.append("小红书风格，标题吸引人")
        constraints.append("正文 300-800 字，分段清晰")

    strategy_hint = ""
    if strategy:
        angle = strategy.get("angle", "")
        hook = strategy.get("hook", "")
        if angle:
            strategy_hint += f"\n切入角度: {angle}"
        if hook:
            strategy_hint += f"\n开头: {hook}"

    persona_hint = ""
    if persona:
        persona_hint = f"\n以 {persona.get('name', '')} 的口吻撰写"

    prompt = (
        f"请为以下话题撰写一条{platform}帖子:\n"
        f"话题: {topic}{strategy_hint}{persona_hint}\n"
        f"要求: {'; '.join(constraints)}\n\n"
        "直接输出帖子内容，不要加任何解释。"
    )
    try:
        result = await ai_pool.call(prompt)
        if result.get("success"):
            text = result.get("raw", "").strip()
            if platform == "x" and len(text) > max_length:
                text = text[:max_length - 3] + "..."
            return {"success": True, "text": text, "platform": platform}
        return {"success": False, "error": "内容生成失败"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def load_persona(persona_dir: Optional[str] = None, name: str = "default") -> Optional[Dict]:
    """加载社交人设配置"""
    if not persona_dir:
        persona_dir = str(
            Path(__file__).resolve().parent.parent.parent.parent
            / "data" / "social_personas"
        )
    path = Path(persona_dir) / f"{name}.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:  # noqa: F841
        return None
