"""
Social — 社交媒体子包

将 execution_hub.py 中 ~2400 行社交代码组织为模块化结构:
- social/x_platform.py        — X (Twitter) 平台操作
- social/xhs_platform.py      — 小红书平台操作
- social/content_strategy.py   — AI 内容策略引擎

原 execution_hub.py 中的社交方法通过 facade 保持向后兼容。
新代码应直接导入子模块:
  from src.execution.social.x_platform import publish_x_post
  from src.execution.social.content_strategy import compose_post
"""

from src.execution.social.x_platform import (
    fetch_x_profile_posts,
    publish_x_post,
    reply_to_x_post,
)
from src.execution.social.xhs_platform import (
    publish_xhs_article,
    reply_to_xhs_comment,
    update_xhs_profile,
)
from src.execution.social.content_strategy import (
    discover_hot_topics,
    derive_content_strategy,
    compose_post,
    load_persona,
)

__all__ = [
    "fetch_x_profile_posts", "publish_x_post", "reply_to_x_post",
    "publish_xhs_article", "reply_to_xhs_comment", "update_xhs_profile",
    "discover_hot_topics", "derive_content_strategy", "compose_post", "load_persona",
]
