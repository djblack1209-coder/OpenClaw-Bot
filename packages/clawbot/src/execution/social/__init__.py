"""
Social — 社交媒体子包

将 execution_hub.py 中 ~2400 行社交代码组织为模块化结构:
- social/platform_adapter.py   — 平台适配器基类 + 注册表（v3.0 新增）
- social/x_adapter.py          — X/Twitter 适配器（v3.0 新增）
- social/xhs_adapter.py        — 小红书适配器（v3.0 新增）
- social/x_platform.py         — X (Twitter) 平台底层操作
- social/xhs_platform.py       — 小红书平台底层操作
- social/content_strategy.py   — AI 内容策略引擎

新代码应通过适配器统一调度:
  from src.execution.social.platform_adapter import get_adapter
  adapter = get_adapter("x")
  result = await adapter.publish(content)

也可直接导入子模块:
  from src.execution.social.x_platform import publish_x_post
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
# 适配器注册表 — 导入即触发自动注册
from src.execution.social.platform_adapter import (
    get_adapter,
    get_all_adapters,
    list_supported_platforms,
    register_adapter,
    SocialPlatformAdapter,
)

__all__ = [
    # 底层平台函数（向后兼容）
    "fetch_x_profile_posts", "publish_x_post", "reply_to_x_post",
    "publish_xhs_article", "reply_to_xhs_comment", "update_xhs_profile",
    # 内容策略
    "discover_hot_topics", "derive_content_strategy", "compose_post", "load_persona",
    # 适配器接口（新代码推荐使用）
    "get_adapter", "get_all_adapters", "list_supported_platforms",
    "register_adapter", "SocialPlatformAdapter",
]
