"""
Social — 社交媒体子包

将 execution_hub.py 中 ~2400 行社交代码组织为模块化结构:
- social/platform_adapter.py   — 平台适配器基类 + 注册表（v3.0 新增）
- social/x_adapter.py          — X/Twitter 适配器（v3.0 新增）
- social/xhs_adapter.py        — 小红书适配器（v3.0 新增）
- social/x_platform.py         — X (Twitter) 平台底层操作 + twikit Cookie 登录
- social/xhs_platform.py       — 小红书平台底层操作 + xhs Cookie 登录
- social/content_strategy.py   — AI 内容策略引擎
- social/x_auto_ops.py         — X 自动运营首发/排程最小闭环

新代码应通过适配器统一调度:
  from src.execution.social.platform_adapter import get_adapter
  adapter = get_adapter("x")
  result = await adapter.publish(content)

也可直接导入子模块:
  from src.execution.social.x_platform import publish_x_post
"""

from src.execution.social.content_strategy import (
    compose_post,
    derive_content_strategy,
    discover_hot_topics,
    load_persona,
)

# 适配器注册表 — 导入即触发自动注册
from src.execution.social.platform_adapter import (
    SocialPlatformAdapter,
    get_adapter,
    get_all_adapters,
    list_supported_platforms,
    register_adapter,
)
from src.execution.social.persona_review import (
    PERSONA_PROPOSAL,
    PERSONA_PROPOSAL_ID,
    get_persona_review,
    review_persona,
)
from src.execution.social.x_platform import (
    X_COOKIES_PATH,
    fetch_x_profile_posts,
    publish_x_post,
    reply_to_x_post,
    twikit_is_authenticated,
    # v3.0 新增: twikit Cookie 持久化登录
    twikit_login,
    twikit_post_tweet,
)
from src.execution.social.x_auto_ops import (
    DEFAULT_DAILY_TIMES,
    POST_ANGLES,
    TrendSeed,
    VideoSeed,
    build_daily_drafts,
    build_xhs_review_drafts,
    build_next_draft,
    choose_seed,
    choose_seeds,
    compose_x_post,
    compose_xhs_note,
    distill_seed,
    extract_youtube_caption_urls,
    fetch_all_content_seeds,
    fetch_all_video_seeds,
    fetch_bilibili_trending_seeds,
    fetch_free_api_trending_seeds,
    fetch_google_news_trending_seeds,
    fetch_hacker_news_trending_seeds,
    fetch_real_trending_seeds,
    fetch_youtube_rss_seeds,
    fetch_youtube_transcript,
    get_or_build_next_ready_draft,
    infer_tags,
    next_morning_at,
    next_scheduled_at,
    parse_daily_times,
    summarize_transcript,
    write_launchd_plist,
    x_weighted_length,
)
from src.execution.social.xhs_platform import (
    XHS_COOKIES_PATH,
    publish_xhs_article,
    reply_to_xhs_comment,
    update_xhs_profile,
    xhs_create_note,
    xhs_is_authenticated,
    # v2.0 新增: xhs Cookie 持久化登录
    xhs_login,
)

__all__ = [
    # 底层平台函数（向后兼容）
    "fetch_x_profile_posts", "publish_x_post", "reply_to_x_post",
    "publish_xhs_article", "reply_to_xhs_comment", "update_xhs_profile",
    # twikit Cookie 登录（v3.0 新增）
    "twikit_login", "twikit_is_authenticated", "twikit_post_tweet", "X_COOKIES_PATH",
    # xhs Cookie 登录（v2.0 新增）
    "xhs_login", "xhs_is_authenticated", "xhs_create_note", "XHS_COOKIES_PATH",
    # 内容策略
    "discover_hot_topics", "derive_content_strategy", "compose_post", "load_persona",
    # X 自动运营
    "fetch_youtube_rss_seeds", "fetch_youtube_transcript", "fetch_bilibili_trending_seeds",
    "fetch_real_trending_seeds", "fetch_free_api_trending_seeds", "fetch_google_news_trending_seeds", "fetch_hacker_news_trending_seeds",
    "fetch_all_content_seeds", "fetch_all_video_seeds", "extract_youtube_caption_urls", "distill_seed",
    "VideoSeed", "TrendSeed",
    "infer_tags", "summarize_transcript", "x_weighted_length", "choose_seed", "choose_seeds", "compose_x_post", "compose_xhs_note",
    "build_next_draft", "build_daily_drafts", "build_xhs_review_drafts", "get_or_build_next_ready_draft",
    "parse_daily_times", "next_morning_at", "next_scheduled_at", "write_launchd_plist",
    "DEFAULT_DAILY_TIMES", "POST_ANGLES",
    # 适配器接口（新代码推荐使用）
    "get_adapter", "get_all_adapters", "list_supported_platforms",
    "register_adapter", "SocialPlatformAdapter",
    # 人设确认
    "PERSONA_PROPOSAL", "PERSONA_PROPOSAL_ID", "get_persona_review", "review_persona",
]
