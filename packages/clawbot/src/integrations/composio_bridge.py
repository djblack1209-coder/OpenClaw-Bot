"""
Composio 250+ 外部服务集成桥接

搬运 ComposioHQ/composio (20k⭐) — 统一的外部服务 SDK
- Gmail 邮件读写
- Google Calendar 日程管理
- Slack/Discord 消息
- GitHub Issues/PRs
- Notion 文档
- 等 250+ 服务

降级: composio-core 未安装时所有操作返回 not_available
"""
import logging
import os
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ── Composio SDK 导入 (graceful degradation) ──────────────────
_HAS_COMPOSIO = False
try:
    from composio import ComposioToolSet, Action, App
    _HAS_COMPOSIO = True
    logger.info("[ComposioBridge] composio-core SDK 已加载")
except ImportError:
    ComposioToolSet = None  # type: ignore[assignment,misc]
    Action = None  # type: ignore[assignment,misc]
    App = None  # type: ignore[assignment,misc]
    logger.info("[ComposioBridge] composio-core 未安装 (pip install composio-core)")


class ComposioBridge:
    """Composio 250+ 外部服务桥接层

    搬运 ComposioHQ/composio (20k⭐) — 统一 SDK 调用 Gmail / Calendar /
    Slack / GitHub / Notion 等 250+ 服务。

    与 AlpacaBridge 模式一致 — composio-core 未安装时所有操作安全降级。

    用法:
        bridge = ComposioBridge()
        if bridge.is_available():
            apps = bridge.list_apps()
            result = bridge.execute_action("GITHUB_STAR_A_REPOSITORY", {"owner": "...", "repo": "..."})
    """

    def __init__(self, api_key: Optional[str] = None, entity_id: str = "default"):
        self._available = False
        self._toolset: Optional[ComposioToolSet] = None  # type: ignore[type-arg]
        self._entity_id = entity_id

        if not _HAS_COMPOSIO:
            logger.warning("[ComposioBridge] composio-core 未安装，所有操作将返回 not_available")
            return

        key = api_key or os.getenv("COMPOSIO_API_KEY", "")
        if not key:
            logger.warning("[ComposioBridge] COMPOSIO_API_KEY 未设置，跳过初始化")
            return

        try:
            self._toolset = ComposioToolSet(
                api_key=key,
                entity_id=entity_id,
                logging_level="WARNING",
            )
            self._available = True
            logger.info("[ComposioBridge] 初始化成功 (entity=%s)", entity_id)
        except Exception as e:
            logger.error("[ComposioBridge] 初始化失败: %s", e)

    # ── 状态查询 ──────────────────────────────────────────

    def is_available(self) -> bool:
        """检查 Composio 是否可用 (SDK 已安装且 API Key 有效)"""
        return self._available and self._toolset is not None

    def get_status(self) -> Dict[str, Any]:
        """健康检查 — 返回连接状态、已连接应用等"""
        if not self.is_available():
            return {
                "available": False,
                "reason": "composio-core 未安装" if not _HAS_COMPOSIO else "API Key 未设置",
                "sdk_installed": _HAS_COMPOSIO,
            }

        try:
            apps = self._toolset.get_apps()  # type: ignore[union-attr]
            connected = self._toolset.get_connected_accounts()  # type: ignore[union-attr]
            return {
                "available": True,
                "sdk_installed": True,
                "entity_id": self._entity_id,
                "total_apps": len(apps),
                "connected_accounts": len(connected) if connected else 0,
            }
        except Exception as e:
            return {
                "available": True,
                "sdk_installed": True,
                "error": str(e),
            }

    # ── 应用 & 动作枚举 ──────────────────────────────────

    def list_apps(self) -> List[str]:
        """列出所有可用的应用集成

        Returns:
            应用名称列表 (如 ["github", "gmail", "slack", ...])
        """
        if not self.is_available():
            return []

        try:
            apps = self._toolset.get_apps()  # type: ignore[union-attr]
            return [app.name for app in apps if hasattr(app, "name")]
        except Exception as e:
            logger.error("[ComposioBridge] list_apps 失败: %s", e)
            return []

    def list_actions(self, app_name: str) -> List[Dict[str, Any]]:
        """列出指定应用的所有可用动作

        Args:
            app_name: 应用名称 (如 "github", "gmail")

        Returns:
            动作列表, 每项含 name / description / parameters
        """
        if not self.is_available():
            return []

        try:
            schemas = self._toolset.get_action_schemas(  # type: ignore[union-attr]
                apps=[app_name],
                check_connected_accounts=False,
            )
            result = []
            for schema in schemas:
                entry: Dict[str, Any] = {"name": ""}
                if hasattr(schema, "name"):
                    entry["name"] = schema.name
                if hasattr(schema, "description"):
                    entry["description"] = schema.description
                if hasattr(schema, "parameters"):
                    entry["parameters"] = schema.parameters
                result.append(entry)
            return result
        except Exception as e:
            logger.error("[ComposioBridge] list_actions(%s) 失败: %s", app_name, e)
            return []

    def find_actions(self, *apps: str, use_case: str) -> List[str]:
        """按用例描述搜索最匹配的动作 (语义搜索)

        Args:
            apps: 限定搜索的应用 (如 "github")
            use_case: 自然语言描述 (如 "star a repository")

        Returns:
            匹配的动作名称列表
        """
        if not self.is_available():
            return []

        try:
            actions = self._toolset.find_actions_by_use_case(  # type: ignore[union-attr]
                *apps,
                use_case=use_case,
            )
            return [str(a) for a in actions]
        except Exception as e:
            logger.error("[ComposioBridge] find_actions 失败: %s", e)
            return []

    # ── 执行动作 ──────────────────────────────────────────

    def execute_action(
        self,
        action_name: str,
        params: Optional[Dict[str, Any]] = None,
        entity_id: Optional[str] = None,
        connected_account_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """执行一个 Composio 动作

        Args:
            action_name: 动作标识 (如 "GITHUB_STAR_A_REPOSITORY", "GMAIL_SEND_EMAIL")
            params: 动作参数字典
            entity_id: 用户实体 ID (覆盖默认)
            connected_account_id: 指定连接账户 ID

        Returns:
            执行结果字典，包含 success / data / error 字段
        """
        if not self.is_available():
            return {
                "success": False,
                "error": "composio_not_available",
                "data": None,
            }

        params = params or {}
        eid = entity_id or self._entity_id

        try:
            result = self._toolset.execute_action(  # type: ignore[union-attr]
                action=action_name,
                params=params,
                entity_id=eid,
                connected_account_id=connected_account_id,
            )
            return {
                "success": True,
                "data": result,
                "error": None,
            }
        except Exception as e:
            logger.error(
                "[ComposioBridge] execute_action(%s) 失败: %s",
                action_name, e,
            )
            return {
                "success": False,
                "error": str(e),
                "data": None,
            }


# ── 全局单例 ──────────────────────────────────────────────

_bridge: Optional[ComposioBridge] = None


def get_composio_bridge() -> ComposioBridge:
    """获取 ComposioBridge 全局单例 (懒初始化)"""
    global _bridge
    if _bridge is None:
        _bridge = ComposioBridge()
    return _bridge
