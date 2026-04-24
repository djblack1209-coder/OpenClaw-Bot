"""
社媒平台适配器 — 统一多平台发布接口

通过适配器模式替代 if/elif 分发链，新增平台只需：
1. 创建 XxxAdapter(SocialPlatformAdapter)
2. 在 _auto_register() 中注册
无需修改任何调用方代码。
"""
import logging
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


class SocialPlatformAdapter(ABC):
    """社媒平台适配器基类 — 每个平台实现此接口"""

    @property
    @abstractmethod
    def platform_id(self) -> str:
        """平台唯一标识（如 'x', 'xiaohongshu'）"""
        ...

    @property
    @abstractmethod
    def display_name(self) -> str:
        """平台显示名称（如 'X/Twitter', '小红书'）"""
        ...

    @property
    def aliases(self) -> list[str]:
        """平台名称别名列表（如 ['twitter', 'tw']）"""
        return []

    @abstractmethod
    async def publish(
        self,
        content: str,
        title: str = "",
        images: list[str] | None = None,
        worker_fn=None,
        **kwargs,
    ) -> dict:
        """发布内容到平台，返回结果字典"""
        ...

    def normalize_content(self, raw_content: str) -> tuple:
        """将原始内容规范化为 (title, body) — 子类可覆盖"""
        return "", raw_content

    def build_worker_payload(self, content: str, title: str = "", images: list[str] | None = None) -> dict:
        """构建 worker 调用参数 — 子类可覆盖"""
        return {"text": content}

    @property
    def worker_action(self) -> str:
        """worker_fn 调用时的 action 名称（如 'publish_x'）"""
        return f"publish_{self.platform_id}"


# ── 平台注册表 ──────────────────────────────────────────────

_ADAPTERS: dict[str, "SocialPlatformAdapter"] = {}


def register_adapter(adapter: SocialPlatformAdapter) -> None:
    """注册平台适配器（主键 + 别名都写入注册表）"""
    _ADAPTERS[adapter.platform_id] = adapter
    for alias in adapter.aliases:
        _ADAPTERS[alias.lower()] = adapter


def get_adapter(platform: str) -> SocialPlatformAdapter | None:
    """根据平台名称获取适配器（支持别名，大小写不敏感）"""
    return _ADAPTERS.get(platform.lower())


def get_all_adapters() -> dict[str, SocialPlatformAdapter]:
    """获取所有已注册的适配器（按 platform_id 去重）"""
    seen: set = set()
    result: dict[str, SocialPlatformAdapter] = {}
    for adapter in _ADAPTERS.values():
        if adapter.platform_id not in seen:
            seen.add(adapter.platform_id)
            result[adapter.platform_id] = adapter
    return result


def list_supported_platforms() -> list[str]:
    """返回所有支持的平台 ID 列表"""
    return list(get_all_adapters().keys())


# ── 自动注册已知平台 ──────────────────────────────────────────

def _auto_register() -> None:
    """模块加载时自动注册所有已知平台适配器"""
    try:
        from src.execution.social.x_adapter import XPlatformAdapter
        register_adapter(XPlatformAdapter())
    except ImportError:
        logger.warning("X 平台适配器加载失败")

    try:
        from src.execution.social.xhs_adapter import XhsPlatformAdapter
        register_adapter(XhsPlatformAdapter())
    except ImportError:
        logger.warning("小红书适配器加载失败")


_auto_register()
