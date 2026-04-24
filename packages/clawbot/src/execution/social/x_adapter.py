"""
X/Twitter 平台适配器 — 包装 x_platform.py 的发布函数
"""

from src.execution.social.platform_adapter import SocialPlatformAdapter


class XPlatformAdapter(SocialPlatformAdapter):
    """X/Twitter 平台适配器"""

    @property
    def platform_id(self) -> str:
        return "x"

    @property
    def display_name(self) -> str:
        return "X/Twitter"

    @property
    def aliases(self) -> list[str]:
        return ["twitter", "tw"]

    def normalize_content(self, raw_content: str) -> tuple:
        """X 不需要标题，直接返回空标题 + 全文"""
        return "", raw_content

    def build_worker_payload(
        self, content: str, title: str = "", images: list[str] | None = None
    ) -> dict:
        """构建 X 发布的 worker 参数"""
        payload: dict = {"text": content}
        if images:
            payload["images"] = images
        return payload

    @property
    def worker_action(self) -> str:
        return "publish_x"

    async def publish(
        self,
        content: str,
        title: str = "",
        images: list[str] | None = None,
        worker_fn=None,
        **kwargs,
    ) -> dict:
        """发布到 X — 委托给 x_platform.publish_x_post"""
        from src.execution.social.x_platform import publish_x_post

        image_path = images[0] if images else None
        return await publish_x_post(
            content=content,
            worker_fn=worker_fn,
            image_path=image_path,
        )
