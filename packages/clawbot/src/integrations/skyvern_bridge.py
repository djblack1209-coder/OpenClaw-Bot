"""
Skyvern 视觉 RPA 桥接

搬运 Skyvern-AI/skyvern (11k⭐) — 基于视觉理解的浏览器自动化
- 无需 CSS selector，通过截图 + LLM 理解页面
- 自动处理表单填写、按钮点击、数据提取
- 比传统 Playwright/DrissionPage 更抗页面变化

降级: skyvern 未安装时回退到现有 browser-use/DrissionPage
"""
import logging
import os
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# ── Skyvern SDK 导入 (graceful degradation) ──────────────────
_HAS_SKYVERN = False
try:
    from skyvern import Skyvern as SkyvernClient
    _HAS_SKYVERN = True
    logger.info("[SkyvernBridge] skyvern SDK 已加载")
except ImportError:
    SkyvernClient = None  # type: ignore[assignment,misc]
    logger.info("[SkyvernBridge] skyvern 未安装 (pip install skyvern)")


class SkyvernBridge:
    """Skyvern 视觉 RPA 桥接层

    搬运 Skyvern-AI/skyvern (11k⭐) — 通过截图 + LLM 理解页面，
    无需 CSS selector 即可执行浏览器自动化任务。

    与 ComposioBridge 模式一致 — skyvern 未安装时所有操作安全降级。

    用法::

        bridge = SkyvernBridge()
        if bridge.is_available():
            result = await bridge.run_task(
                url="https://example.com",
                goal="点击登录按钮并填写用户名",
            )
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
    ):
        self._available = False
        self._client: Optional[SkyvernClient] = None  # type: ignore[type-arg]

        if not _HAS_SKYVERN:
            logger.warning(
                "[SkyvernBridge] skyvern 未安装，所有操作将返回 not_available"
            )
            return

        key = api_key or os.getenv("SKYVERN_API_KEY", "")
        if not key:
            logger.warning("[SkyvernBridge] SKYVERN_API_KEY 未设置，跳过初始化")
            return

        try:
            kwargs: Dict[str, Any] = {"api_key": key}

            # 支持自定义 base_url (自托管 Skyvern 实例)
            url = base_url or os.getenv("SKYVERN_BASE_URL", "")
            if url:
                kwargs["base_url"] = url

            self._client = SkyvernClient(**kwargs)
            self._available = True
            logger.info(
                "[SkyvernBridge] 初始化成功 (base_url=%s)",
                url or "cloud (default)",
            )
        except Exception as e:
            logger.error("[SkyvernBridge] 初始化失败: %s", e)

    # ── 状态查询 ──────────────────────────────────────────

    def is_available(self) -> bool:
        """检查 Skyvern 是否可用 (SDK 已安装且 API Key 有效)"""
        return self._available and self._client is not None

    def get_status(self) -> Dict[str, Any]:
        """健康检查 — 返回连接状态"""
        if not self.is_available():
            return {
                "available": False,
                "reason": (
                    "skyvern 未安装"
                    if not _HAS_SKYVERN
                    else "SKYVERN_API_KEY 未设置"
                ),
                "sdk_installed": _HAS_SKYVERN,
            }

        return {
            "available": True,
            "sdk_installed": True,
        }

    # ── 核心方法 ──────────────────────────────────────────

    async def run_task(
        self,
        url: str,
        goal: str,
        max_steps: int = 10,
        data_extraction_schema: Optional[Dict[str, Any]] = None,
        wait_for_completion: bool = True,
        timeout: float = 600,
    ) -> Dict[str, Any]:
        """核心方法: 导航到 URL，通过视觉理解实现目标。

        Args:
            url: 目标页面 URL
            goal: 自然语言描述的目标 (如 "点击登录按钮并填写邮箱")
            max_steps: 最大操作步数
            data_extraction_schema: 可选的数据提取 schema
            wait_for_completion: 是否等待任务完成
            timeout: 超时秒数 (默认 600s)

        Returns:
            包含 success / data / error 的结果字典
        """
        if not self.is_available():
            return {
                "success": False,
                "error": "skyvern_not_available",
                "data": None,
            }

        try:
            kwargs: Dict[str, Any] = {
                "prompt": goal,
                "url": url,
                "max_steps": max_steps,
                "wait_for_completion": wait_for_completion,
                "timeout": timeout,
            }
            if data_extraction_schema:
                kwargs["data_extraction_schema"] = data_extraction_schema

            response = await self._client.run_task(**kwargs)  # type: ignore[union-attr]

            # 解析 TaskRunResponse
            result_data: Dict[str, Any] = {
                "run_id": response.run_id,
                "status": response.status,
                "output": response.output,
                "recording_url": response.recording_url,
                "screenshot_urls": response.screenshot_urls,
                "failure_reason": response.failure_reason,
                "step_count": response.step_count,
            }

            succeeded = response.status == "completed"
            return {
                "success": succeeded,
                "data": result_data,
                "error": response.failure_reason if not succeeded else None,
            }
        except Exception as e:
            logger.error("[SkyvernBridge] run_task 失败: %s", e)
            return {
                "success": False,
                "error": str(e),
                "data": None,
            }

    async def extract_data(
        self,
        url: str,
        schema: Dict[str, Any],
        prompt: Optional[str] = None,
        max_steps: int = 5,
    ) -> Dict[str, Any]:
        """从页面提取结构化数据。

        Args:
            url: 目标页面 URL
            schema: JSON Schema 描述期望的数据结构
            prompt: 可选的额外提示 (默认自动生成)
            max_steps: 最大操作步数

        Returns:
            包含 success / data / error 的结果字典
        """
        goal = prompt or "Extract the requested data from this page."
        return await self.run_task(
            url=url,
            goal=goal,
            max_steps=max_steps,
            data_extraction_schema=schema,
        )

    async def fill_form(
        self,
        url: str,
        fields: Dict[str, str],
        submit: bool = True,
        max_steps: int = 10,
    ) -> Dict[str, Any]:
        """填写页面表单。

        Args:
            url: 表单页面 URL
            fields: 字段名→值映射 (如 {"邮箱": "a@b.com", "密码": "***"})
            submit: 填写后是否提交
            max_steps: 最大操作步数

        Returns:
            包含 success / data / error 的结果字典
        """
        field_desc = ", ".join(
            f'"{k}" 填写 "{v}"' for k, v in fields.items()
        )
        goal = f"在页面上找到表单，{field_desc}"
        if submit:
            goal += "，然后提交表单"

        return await self.run_task(
            url=url,
            goal=goal,
            max_steps=max_steps,
        )

    async def close(self) -> None:
        """关闭 Skyvern 客户端，释放资源"""
        if self._client is not None:
            try:
                await self._client.aclose()
            except Exception:
                logger.debug("[SkyvernBridge] 关闭客户端异常", exc_info=True)
            self._client = None
            self._available = False


# ── 全局单例 ──────────────────────────────────────────────

_bridge: Optional[SkyvernBridge] = None


def get_skyvern_bridge() -> SkyvernBridge:
    """获取 SkyvernBridge 全局单例 (懒初始化)"""
    global _bridge
    if _bridge is None:
        _bridge = SkyvernBridge()
    return _bridge
