"""
Social — 草稿管理 (从 execution_hub.py 迁移)

包含:
- save_social_draft: 保存草稿 (含去重检测)
- list_social_drafts: 列出草稿
- get_social_draft: 获取单个草稿
- update_social_draft_status: 更新草稿状态
- create_social_draft: 从监控帖子创建草稿
- publish_social_draft: 通过 browser worker 发布草稿

迁移自: execution_hub.py (反编译巨石) → HI-006/HI-008
持久化改造: HI-585 — 草稿持久化到 JSON 文件，防止重启丢失
"""
import json
import logging
import re
import threading
import uuid
from pathlib import Path
from typing import Dict, List, Optional

from src.utils import now_et

logger = logging.getLogger(__name__)


# ── 持久化草稿存储 ─────────────────────────────────────────────

# 草稿文件路径：~/.openclaw/drafts.json
_DRAFTS_DIR = Path.home() / ".openclaw"
_DRAFTS_FILE = _DRAFTS_DIR / "drafts.json"
_MAX_DRAFTS: int = 500

# 线程锁：保护并发读写（多 worker 进程内线程安全）
_lock = threading.Lock()


def _load_drafts() -> List[Dict]:
    """从 JSON 文件加载草稿列表，文件不存在或损坏时返回空列表"""
    try:
        if _DRAFTS_FILE.exists():
            raw = _DRAFTS_FILE.read_text(encoding="utf-8")
            data = json.loads(raw)
            if isinstance(data, list):
                return data
            logger.warning("[Drafts] drafts.json 格式异常（非列表），重置为空")
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("[Drafts] 加载 drafts.json 失败: %s，重置为空", e)
    return []


def _save_drafts(drafts: List[Dict]) -> None:
    """将草稿列表写入 JSON 文件，自动创建目录"""
    try:
        _DRAFTS_DIR.mkdir(parents=True, exist_ok=True)
        tmp_file = _DRAFTS_FILE.with_suffix(".tmp")
        tmp_file.write_text(json.dumps(drafts, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp_file.replace(_DRAFTS_FILE)
    except OSError as e:
        logger.error("[Drafts] 写入 drafts.json 失败: %s", e)


def _generate_draft_id() -> str:
    """生成唯一草稿 ID（uuid4 前 12 位，碰撞概率极低）"""
    return uuid.uuid4().hex[:12]


def _tokenize(text: str) -> set:
    """简单分词用于去重"""
    return set(re.findall(r"[\w\u4e00-\u9fff]+", str(text).lower()))


def _text_overlap_ratio(a: str, b: str) -> float:
    """计算两段文本的重叠率"""
    tokens_a = _tokenize(a)
    tokens_b = _tokenize(b)
    if not tokens_a or not tokens_b:
        return 0.0
    overlap = tokens_a & tokens_b
    return len(overlap) / min(len(tokens_a), len(tokens_b))


def _detect_duplicate(
    platform: str,
    title: str,
    body: str,
    topic: str = "",
    threshold: float = 0.7,
) -> Optional[Dict]:
    """检测与现有草稿的重复（调用前需持有 _lock）"""
    drafts = _load_drafts()
    # 只检查最近 50 条
    for draft in drafts[-50:]:
        if draft.get("platform") != platform:
            continue
        existing_body = draft.get("body", "")
        ratio = _text_overlap_ratio(body, existing_body)
        if ratio >= threshold:
            return {"duplicate": True, "existing": draft, "ratio": ratio}
    return None


def save_social_draft(
    platform: str = "both",
    title: str = "",
    body: str = "",
    sources: Optional[List] = None,
    topic: str = "",
) -> Dict:
    """保存社媒草稿 (含去重检测，持久化到文件)"""
    platform_name = str(platform or "").strip().lower()
    if platform_name not in frozenset({"x", "xiaohongshu", "both"}):
        return {"success": False, "error": "仅支持 x / xiaohongshu / both"}

    content = str(body or "").strip()
    if not content:
        return {"success": False, "error": "草稿内容不能为空"}

    title = title or ""
    topic = topic or title

    with _lock:
        # 去重检测
        duplicate = _detect_duplicate(platform_name, str(title), content, topic=topic)
        if duplicate and duplicate.get("duplicate"):
            existing = duplicate.get("existing", {})
            return {
                "success": False,
                "error": "内容与最近草稿过于相似",
                "duplicate": True,
                "existing_id": existing.get("id", ""),
            }

        draft_id = _generate_draft_id()
        row = {
            "id": draft_id,
            "success": True,
            "draft_id": draft_id,
            "platform": platform_name,
            "title": title,
            "body": content,
            "topic": topic,
            "updated_at": now_et().isoformat(),
        }

        drafts = _load_drafts()
        drafts.append(row)

        # 上限裁剪
        if len(drafts) > _MAX_DRAFTS:
            drafts = drafts[-_MAX_DRAFTS:]

        _save_drafts(drafts)

    return row


def list_social_drafts(
    platform: str = None,
    status: str = None,
    limit: int = 20,
) -> List[Dict]:
    """列出草稿"""
    with _lock:
        result = _load_drafts()
    if platform:
        result = [d for d in result if d.get("platform") == platform]
    if status:
        result = [d for d in result if d.get("status") == status]
    return result[-limit:]


def get_social_draft(draft_id) -> Optional[Dict]:
    """获取单个草稿（兼容字符串和整数 ID）"""
    with _lock:
        drafts = _load_drafts()
    # 兼容旧版整数 ID 和新版字符串 ID
    for draft in drafts:
        if draft.get("id") == draft_id or str(draft.get("id")) == str(draft_id):
            return draft
    return None


def update_social_draft_status(draft_id, status: str) -> Dict:
    """更新草稿状态"""
    with _lock:
        drafts = _load_drafts()
        for draft in drafts:
            if draft.get("id") == draft_id or str(draft.get("id")) == str(draft_id):
                draft["status"] = status
                draft["updated_at"] = now_et().isoformat()
                _save_drafts(drafts)
                return {"success": True, "draft_id": draft_id, "status": status}
    return {"success": False, "error": f"草稿 {draft_id} 不存在"}


def delete_social_draft(draft_id) -> Dict:
    """删除草稿"""
    with _lock:
        drafts = _load_drafts()
        original_len = len(drafts)
        drafts = [d for d in drafts if not (d.get("id") == draft_id or str(d.get("id")) == str(draft_id))]
        if len(drafts) < original_len:
            _save_drafts(drafts)
            return {"success": True, "draft_id": draft_id}
    return {"success": False, "error": f"草稿 {draft_id} 不存在"}


async def create_social_draft(
    platform: str = None,
    topic: str = None,
    max_items: int = 3,
    monitors: List[Dict] = None,
    fetch_posts_fn=None,
    news_fetcher=None,
    curate_fn=None,
) -> Dict:
    """从 X 监控帖子或新闻创建社媒草稿

    优先使用 monitors + fetch_posts_fn (从 X profile 监控收集)，
    回退到 news_fetcher (从 RSS 新闻收集)。
    """
    platform = platform or "x"
    topic = topic or "AI"
    max_items = max_items or 3

    all_items: List[Dict] = []

    # 路径1: 从 X profile monitors 收集
    if monitors and fetch_posts_fn:
        for monitor in monitors:
            keyword = monitor.get("keyword", "")
            source = monitor.get("source", "news")
            if source == "x_profile":
                try:
                    posts = await fetch_posts_fn(keyword, count=max_items)
                    if posts:
                        for post in posts:
                            post["handle"] = keyword
                        all_items.extend(posts)
                except Exception as e:
                    logger.warning(f"[CreateDraft] fetch {keyword} failed: {e}")
        all_items = all_items[:max_items]

    # 路径2: 从新闻源收集 (回退)
    if not all_items and news_fetcher:
        try:
            items = await news_fetcher.fetch_from_google_news_rss(topic, count=max_items)
            if items:
                all_items = items[:max_items]
        except Exception as e:
            logger.warning(f"[CreateDraft] news fetch failed: {e}")

    if not all_items:
        return {"success": False, "error": "没有找到相关内容"}

    # 按平台构建内容
    if platform == "xiaohongshu":
        title = _build_xiaohongshu_title(all_items, topic)
        body = _build_xiaohongshu_body(all_items, topic)
        return save_social_draft("xiaohongshu", title, body, topic=topic)
    else:
        body = _build_x_social_body(all_items, topic)
        return save_social_draft("x", "", body, topic=topic)


# ── 内容构建器 (从 execution_hub.py 迁移) ────────────────────

def _social_topic_tags(topic: str = "") -> List[str]:
    """从话题推导标签"""
    tags: List[str] = []
    if "AI" in topic or "ai" in topic:
        tags.extend(["AI", "效率"])
    if "OpenClaw" in topic:
        tags.extend(["OpenClaw", "自动化"])
    if "出海" in topic:
        tags.extend(["出海", "独立开发"])
    return tags or ["AI", "工具"]


def _build_x_social_body(items: List[Dict], topic: str = "") -> str:
    """构建 X 推文正文"""
    topic_label = topic or "AI/出海"
    tags = _social_topic_tags(topic)
    lines = [f"今天筛了 {len(items)} 条值得看的{topic_label}更新："]
    for i, item in enumerate(items[:3], 1):
        summary = item.get("title", "")
        if len(summary) > 32:
            summary = summary[:29] + "..."
        lines.append("{}. @{}：{}".format(i, item.get("handle", ""), summary))
    lines.append("想要原文链接和每日精选，来找 OpenClaw。")
    if tags:
        lines.append(" ".join(tags[:3]))
    return "\n".join(lines)[:278]


def _build_xiaohongshu_title(items: List[Dict], topic: str = "") -> str:
    """构建小红书标题"""
    topic_label = topic or "AI/出海"
    title = f"今日{topic_label}情报：{len(items)}位博主更新"
    return title[:20]


def _build_xiaohongshu_body(items: List[Dict], topic: str = "") -> str:
    """构建小红书正文"""
    topic_label = topic or "AI/出海/独立开发"
    tags = _social_topic_tags(topic)
    lines = [
        f"今天整理了 {len(items)} 条值得追踪的{topic_label}动态，适合做信息流输入：",
        "",
    ]
    for i, item in enumerate(items[:5], 1):
        summary = item.get("title", "")
        if len(summary) > 72:
            summary = summary[:69] + "..."
        lines.append(f"   {summary}")
        if item.get("url"):
            lines.append(f"   原文：{item.get('url', '')}")
    lines.append("如果你想让我每天自动筛这类信息源，可以直接用 OpenClaw 建监控。")
    return "\n".join(lines)


def publish_social_draft(
    platform: str = None,
    draft_id=None,
    worker_fn=None,
) -> Dict:
    """通过 browser worker 发布草稿"""
    draft = get_social_draft(draft_id) if draft_id else None
    if not draft:
        return {"success": False, "error": f"草稿 {draft_id} 不存在"}
    if not worker_fn:
        return {"success": False, "error": "browser worker 未配置"}

    platform = platform or draft.get("platform", "x")
    body = draft.get("body", "")
    title = draft.get("title", "")

    try:
        if platform == "x":
            result = worker_fn("publish_x", {"text": body, "images": []})
        elif platform == "xiaohongshu":
            result = worker_fn("publish_xhs", {
                "title": title, "body": body, "images": [],
            })
        else:
            return {"success": False, "error": f"不支持的平台: {platform}"}

        if result and result.get("success"):
            update_social_draft_status(draft_id, "published")

        return {"success": True, "platform": platform, "draft_id": draft_id, "result": result}
    except Exception as e:
        logger.error(f"[PublishDraft] failed: {e}")
        return {"success": False, "error": str(e)}
