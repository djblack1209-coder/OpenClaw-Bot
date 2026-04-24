"""
小红书平台适配器 — 包装 xhs_platform.py 的发布函数
"""

from src.execution.social.platform_adapter import SocialPlatformAdapter


class XhsPlatformAdapter(SocialPlatformAdapter):
    """小红书平台适配器"""

    @property
    def platform_id(self) -> str:
        return "xiaohongshu"

    @property
    def display_name(self) -> str:
        return "小红书"

    @property
    def aliases(self) -> list[str]:
        return ["xhs", "小红书"]

    def normalize_content(self, raw_content: str) -> tuple:
        """小红书需要标题 — 从内容第一行提取"""
        lines = raw_content.strip().splitlines()
        title = lines[0].strip() if lines else "无标题"
        body = "\n".join(lines[1:]).strip() if len(lines) > 1 else raw_content
        return title, body

    def build_worker_payload(
        self, content: str, title: str = "", images: list[str] | None = None
    ) -> dict:
        """构建小红书发布的 worker 参数"""
        payload: dict = {"title": title, "body": content}
        if images:
            payload["images"] = images
        return payload

    @property
    def worker_action(self) -> str:
        return "publish_xhs"

    async def publish(
        self,
        content: str,
        title: str = "",
        images: list[str] | None = None,
        worker_fn=None,
        **kwargs,
    ) -> dict:
        """发布到小红书 — 委托给 xhs_platform.publish_xhs_article"""
        from src.execution.social.xhs_platform import publish_xhs_article

        # 如果没传标题，从内容第一行提取
        if not title:
            title, content = self.normalize_content(content)

        image_path = images[0] if images else None
        return await publish_xhs_article(
            title=title,
            body=content,
            worker_fn=worker_fn,
            image_path=image_path,
        )
