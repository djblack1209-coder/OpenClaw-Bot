"""
OpenClaw 统一通知系统 — 搬运 Apprise (16.1k⭐)
支持 100+ 通知渠道（Telegram/Discord/Slack/WeChat/Email/Ntfy/Webhook 等）
通过 URL 配置，零代码添加新渠道。

用法:
    # 1. 设置环境变量（逗号分隔多个渠道）
    #    NOTIFY_URLS=tgram://bot_token/chat_id,discord://webhook_id/webhook_token
    #
    # 2. 或在 config/notifications.yaml 中配置:
    #    urls:
    #      - tgram://bot_token/chat_id
    #      - discord://webhook_id/webhook_token
    #    tag_routes:
    #      trading: [tgram://..., ntfy://trading-alerts]
    #      social:  [discord://...]
    #
    # 3. 代码中使用:
    #    from src.notifications import get_notification_manager
    #    nm = get_notification_manager()
    #    await nm.send("服务器重启完毕", level=NotifyLevel.HIGH, tags=["system"])

Apprise URL 格式参考: https://github.com/caronc/apprise/wiki
  Telegram:  tgram://bot_token/chat_id
  Discord:   discord://webhook_id/webhook_token
  Slack:     slack://token_a/token_b/token_c/#channel
  Email:     mailto://<user>:<password>@gmail.com
  Ntfy:      ntfy://topic
  Webhook:   json://hostname/path
  WeChat:    wecom://corp_id/secret/agent_id/@user
  Bark:      bark://server_key@hostname
  ...还有 100+ 更多渠道
"""
import asyncio
import logging
import os
from enum import IntEnum
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

logger = logging.getLogger(__name__)

# ── Apprise 可选导入（未安装时优雅降级） ──────────────────

try:
    import apprise

    APPRISE_AVAILABLE = True
except ImportError:
    apprise = None  # type: ignore[assignment]
    APPRISE_AVAILABLE = False
    logger.warning(
        "apprise 未安装，通知系统降级为仅日志模式。"
        "安装: pip install 'apprise>=1.9.0'"
    )

# ── 配置路径 ──────────────────────────────────────────────

_BASE_DIR = Path(__file__).resolve().parent.parent
_CONFIG_DIR = _BASE_DIR / "config"
_NOTIFY_CONFIG_PATH = _CONFIG_DIR / "notifications.yaml"


# ── 通知级别 ──────────────────────────────────────────────

class NotifyLevel(IntEnum):
    """通知优先级，数值越小越紧急"""

    CRITICAL = 1  # 资金安全、系统宕机 → 所有渠道 + 声音提醒
    HIGH = 2      # 交易成交、风控警报 → 主要渠道
    NORMAL = 5    # 日报、社媒发布成功 → 默认渠道
    LOW = 8       # 调试、信息性消息 → 仅日志渠道

    def to_apprise_type(self) -> str:
        """映射到 Apprise 的 NotifyType"""
        if not APPRISE_AVAILABLE:
            return "info"
        mapping = {
            NotifyLevel.CRITICAL: apprise.NotifyType.FAILURE,
            NotifyLevel.HIGH: apprise.NotifyType.WARNING,
            NotifyLevel.NORMAL: apprise.NotifyType.SUCCESS,
            NotifyLevel.LOW: apprise.NotifyType.INFO,
        }
        return mapping.get(self, apprise.NotifyType.INFO)


# ── 事件类型到通知级别的默认映射 ──────────────────────────

# 决定哪些 EventBus 事件应该被自动转发为通知
_EVENT_NOTIFY_MAP: Dict[str, Dict[str, Any]] = {
    # 事件类型 → {level, tags, title_template}
    "trade.risk_alert": {
        "level": NotifyLevel.CRITICAL,
        "tags": ["trading", "risk"],
        "title": "⚠️ 风控警报",
    },
    "trade.strategy_suspended": {
        "level": NotifyLevel.CRITICAL,
        "tags": ["trading", "risk"],
        "title": "🛑 策略暂停",
    },
    "system.security_alert": {
        "level": NotifyLevel.CRITICAL,
        "tags": ["system", "security"],
        "title": "🔒 安全警报",
    },
    "system.self_heal_failed": {
        "level": NotifyLevel.CRITICAL,
        "tags": ["system"],
        "title": "💔 自愈失败",
    },
    "trade.executed": {
        "level": NotifyLevel.HIGH,
        "tags": ["trading"],
        "title": "💰 交易成交",
    },
    "trade.signal": {
        "level": NotifyLevel.HIGH,
        "tags": ["trading"],
        "title": "📡 交易信号",
    },
    "system.cost_warning": {
        "level": NotifyLevel.HIGH,
        "tags": ["system", "cost"],
        "title": "💸 成本预警",
    },
    "system.bot_health": {
        "level": NotifyLevel.HIGH,
        "tags": ["system"],
        "title": "🏥 健康状态变更",
    },
    "social.published": {
        "level": NotifyLevel.NORMAL,
        "tags": ["social"],
        "title": "📱 社媒发布",
    },
    "evolution.proposal": {
        "level": NotifyLevel.NORMAL,
        "tags": ["evolution"],
        "title": "🧬 进化提案",
    },
    "system.cost_daily_report": {
        "level": NotifyLevel.NORMAL,
        "tags": ["system", "cost"],
        "title": "📊 每日成本报告",
    },
    "trade.daily_review": {
        "level": NotifyLevel.NORMAL,
        "tags": ["trading"],
        "title": "📋 每日交易复盘",
    },
    "system.self_heal": {
        "level": NotifyLevel.LOW,
        "tags": ["system"],
        "title": "💚 自愈成功",
    },
    "system.task_completed": {
        "level": NotifyLevel.LOW,
        "tags": ["system"],
        "title": "✅ 任务完成",
    },
}


# ── 配置加载 ──────────────────────────────────────────────

def _load_yaml_config(path: Path) -> Dict[str, Any]:
    """加载 YAML 配置文件，不存在则返回空字典"""
    if not path.exists():
        return {}
    try:
        import yaml  # PyYAML，已是常见依赖

        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        return data if isinstance(data, dict) else {}
    except ImportError:
        logger.debug("PyYAML 未安装，跳过 YAML 配置加载")
        return {}
    except Exception as e:
        logger.warning(f"加载通知配置失败 {path}: {e}")
        return {}


def _build_telegram_url() -> Optional[str]:
    """
    从现有 Telegram 环境变量构建 Apprise URL，作为兜底渠道。
    兼容项目中已有的 BOT_TOKEN / ADMIN_CHAT_ID 模式。
    """
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN") or os.environ.get("BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID") or os.environ.get("ADMIN_CHAT_ID")
    if bot_token and chat_id:
        return f"tgram://{bot_token}/{chat_id}"
    return None


# ── 通知管理器 ────────────────────────────────────────────

class NotificationManager:
    """
    统一通知管理器 — 包装 Apprise，提供多渠道通知能力。

    功能:
      - 从环境变量 / YAML / 代码加载渠道配置
      - 按标签路由：trading 事件发到交易群，social 事件发到运营群
      - 按级别过滤：LOW 级别不发到手机推送
      - 自动订阅 EventBus，关键事件自动转发
      - 未安装 Apprise 时降级为纯日志输出
    """

    def __init__(self):
        self._ap: Optional[Any] = None  # apprise.Apprise instance
        self._tag_routes: Dict[str, Any] = {}  # tag → 独立 Apprise 实例
        self._min_level: NotifyLevel = NotifyLevel.LOW
        self._initialized = False
        self._send_count = 0
        self._error_count = 0
        self._event_subscribed = False

    def initialize(
        self,
        urls: Optional[Sequence[str]] = None,
        config_path: Optional[Path] = None,
        min_level: NotifyLevel = NotifyLevel.LOW,
    ) -> "NotificationManager":
        """
        初始化通知渠道。

        优先级: 显式参数 urls > 环境变量 NOTIFY_URLS > YAML 配置 > Telegram 兜底

        Args:
            urls: 直接传入 Apprise URL 列表
            config_path: YAML 配置文件路径
            min_level: 最低通知级别（低于此级别的通知只写日志）
        """
        self._min_level = min_level

        if not APPRISE_AVAILABLE:
            logger.info("通知系统: Apprise 未安装，降级为日志模式")
            self._initialized = True
            return self

        self._ap = apprise.Apprise()

        # ── 收集渠道 URL ──
        all_urls: List[str] = []

        # 1. 显式传入
        if urls:
            all_urls.extend(urls)

        # 2. 环境变量 NOTIFY_URLS（逗号分隔）
        env_urls = os.environ.get("NOTIFY_URLS", "")
        if env_urls:
            all_urls.extend(
                u.strip() for u in env_urls.split(",") if u.strip()
            )

        # 3. YAML 配置
        cfg_path = config_path or _NOTIFY_CONFIG_PATH
        yaml_cfg = _load_yaml_config(cfg_path)
        if yaml_cfg.get("urls"):
            cfg_urls = yaml_cfg["urls"]
            if isinstance(cfg_urls, list):
                all_urls.extend(str(u) for u in cfg_urls if u)

        # 4. Telegram 兜底
        if not all_urls:
            tg_url = _build_telegram_url()
            if tg_url:
                all_urls.append(tg_url)
                logger.info("通知系统: 未配置 NOTIFY_URLS，使用 Telegram 作为兜底渠道")

        # ── 注册渠道 ──
        added = 0
        for url in all_urls:
            try:
                if self._ap.add(url):
                    added += 1
                else:
                    logger.warning(f"通知渠道 URL 无效: {url[:40]}...")
            except Exception as e:
                logger.warning(f"通知渠道注册失败: {url[:40]}... → {e}")

        # ── 标签路由（YAML 配置） ──
        tag_routes_cfg = yaml_cfg.get("tag_routes", {})
        if isinstance(tag_routes_cfg, dict):
            for tag, tag_urls in tag_routes_cfg.items():
                if not isinstance(tag_urls, list):
                    continue
                tag_ap = apprise.Apprise()
                for url in tag_urls:
                    try:
                        tag_ap.add(str(url), tag=tag)
                    except Exception as e:
                        logger.warning(f"标签路由 [{tag}] 渠道注册失败: {e}")
                if len(tag_ap) > 0:
                    self._tag_routes[tag] = tag_ap
                    logger.debug(f"标签路由 [{tag}]: {len(tag_ap)} 个渠道")

        # ── 最低级别（YAML 覆盖） ──
        yaml_min = yaml_cfg.get("min_level")
        if yaml_min is not None:
            try:
                self._min_level = NotifyLevel(int(yaml_min))
            except (ValueError, TypeError) as e:  # noqa: F841
                level_map = {
                    "critical": NotifyLevel.CRITICAL,
                    "high": NotifyLevel.HIGH,
                    "normal": NotifyLevel.NORMAL,
                    "low": NotifyLevel.LOW,
                }
                if isinstance(yaml_min, str) and yaml_min.lower() in level_map:
                    self._min_level = level_map[yaml_min.lower()]

        self._initialized = True
        logger.info(
            f"通知系统初始化完成: {added} 个默认渠道, "
            f"{len(self._tag_routes)} 个标签路由, "
            f"最低级别={self._min_level.name}"
        )
        return self

    # ── 发送 ──────────────────────────────────────────────

    async def send(
        self,
        body: str,
        title: str = "",
        level: NotifyLevel = NotifyLevel.NORMAL,
        tags: Optional[List[str]] = None,
        notify_type: Optional[str] = None,
    ) -> bool:
        """
        发送通知到所有已配置渠道。

        Args:
            body: 通知正文
            title: 通知标题（部分渠道会显示）
            level: 通知级别
            tags: 路由标签列表，匹配的标签路由会额外发送
            notify_type: 覆盖 Apprise NotifyType（可选）

        Returns:
            是否至少有一个渠道成功发送
        """
        if not self._initialized:
            self.initialize()

        # 级别过滤
        if level > self._min_level:
            logger.debug(f"通知被过滤 (级别 {level.name} > {self._min_level.name}): {title}")
            return False

        # 日志记录（无论是否有渠道）
        log_method = {
            NotifyLevel.CRITICAL: logger.critical,
            NotifyLevel.HIGH: logger.warning,
            NotifyLevel.NORMAL: logger.info,
            NotifyLevel.LOW: logger.debug,
        }.get(level, logger.info)
        log_method(f"[通知:{level.name}] {title or '(无标题)'} — {body[:120]}")

        if not APPRISE_AVAILABLE or self._ap is None:
            return False

        ap_type = notify_type or level.to_apprise_type()
        success = False

        # 默认渠道
        try:
            loop = asyncio.get_running_loop()
            result = await loop.run_in_executor(
                None,
                lambda: self._ap.notify(
                    body=body,
                    title=title or None,
                    notify_type=ap_type,
                ),
            )
            if result:
                success = True
                self._send_count += 1
        except Exception as e:
            self._error_count += 1
            logger.error(f"通知发送失败 (默认渠道): {e}")

        # 标签路由（额外发送到匹配的标签渠道）
        if tags:
            for tag in tags:
                tag_ap = self._tag_routes.get(tag)
                if tag_ap is None:
                    continue
                try:
                    result = await loop.run_in_executor(
                        None,
                        lambda _ap=tag_ap: _ap.notify(
                            body=body,
                            title=title or None,
                            notify_type=ap_type,
                        ),
                    )
                    if result:
                        success = True
                        self._send_count += 1
                except Exception as e:
                    self._error_count += 1
                    logger.error(f"通知发送失败 (标签 {tag}): {e}")

        # ── 微信同步推送 (与 Telegram 同颗粒度) ──
        try:
            from src.wechat_bridge import is_wechat_notify_enabled, send_to_wechat
            if is_wechat_notify_enabled():
                wx_text = f"{'🔴' if level == NotifyLevel.CRITICAL else '🟠' if level == NotifyLevel.HIGH else '📢'} {title}\n{body}" if title else body
                await send_to_wechat(wx_text)
        except Exception as e:
            logger.debug("[通知] 微信桥接异常: %s", e)

        return success

    # ── EventBus 集成 ─────────────────────────────────────

    async def register_event_handlers(self) -> None:
        """
        订阅 EventBus 关键事件，自动转发为通知。

        事件 → 通知的映射在 _EVENT_NOTIFY_MAP 中定义。
        """
        if self._event_subscribed:
            return

        try:
            from src.core.event_bus import get_event_bus

            bus = get_event_bus()

            # 为每种映射的事件注册 handler
            for event_type, config in _EVENT_NOTIFY_MAP.items():
                bus.subscribe(
                    event_type,
                    self._on_event,
                    subscriber_name=f"notify:{event_type}",
                    priority=9,  # 低优先级 — 通知不应阻塞业务逻辑
                )

            # 通配符订阅：捕获所有 CRITICAL 级别事件（兜底）
            bus.subscribe(
                "system.*",
                self._on_system_event_wildcard,
                subscriber_name="notify:system.*",
                priority=9,
            )

            self._event_subscribed = True
            logger.info(
                f"通知系统已订阅 {len(_EVENT_NOTIFY_MAP)} 个事件类型 + system.* 通配符"
            )

        except ImportError:
            logger.warning("无法导入 EventBus，通知系统不订阅事件")
        except Exception as e:
            logger.error(f"通知系统订阅事件失败: {e}")

    async def _on_event(self, event: Any) -> None:
        """处理已映射的 EventBus 事件"""
        config = _EVENT_NOTIFY_MAP.get(event.event_type)
        if not config:
            return

        level = config["level"]
        tags = config.get("tags", [])
        title = config.get("title", event.event_type)

        # 构建通知正文
        body = self._format_event_body(event)

        await self.send(body=body, title=title, level=level, tags=tags)

    async def _on_system_event_wildcard(self, event: Any) -> None:
        """
        通配符兜底：已在 _EVENT_NOTIFY_MAP 中明确映射的事件跳过
        （避免重复通知），只处理未映射的系统事件。
        """
        if event.event_type in _EVENT_NOTIFY_MAP:
            return  # 已有精确订阅，跳过

        # 未映射的系统事件默认按 LOW 级别发送
        body = self._format_event_body(event)
        await self.send(
            body=body,
            title=f"🔔 系统事件: {event.event_type}",
            level=NotifyLevel.LOW,
            tags=["system"],
        )

    @staticmethod
    def _format_event_body(event: Any) -> str:
        """将 EventBus 事件格式化为通知正文"""
        lines = []

        data = getattr(event, "data", {}) or {}
        source = getattr(event, "source", "")

        # 提取有意义的字段
        if "symbol" in data:
            lines.append(f"标的: {data['symbol']}")
        if "message" in data:
            lines.append(str(data["message"]))
        elif "reason" in data:
            lines.append(f"原因: {data['reason']}")
        elif "detail" in data:
            lines.append(str(data["detail"]))

        # 数值类字段
        for key in ("price", "amount", "cost", "score", "pnl"):
            if key in data:
                lines.append(f"{key}: {data[key]}")

        # 兜底：如果没提取到任何字段，dump 前几个 key
        if not lines and data:
            for k, v in list(data.items())[:5]:
                lines.append(f"{k}: {v}")

        if source:
            lines.append(f"来源: {source}")

        return "\n".join(lines) if lines else f"事件 {getattr(event, 'event_type', '?')} 已触发"

    # ── 查询 / 管理 ──────────────────────────────────────

    def get_stats(self) -> Dict[str, Any]:
        """获取通知系统统计"""
        channel_count = len(self._ap) if self._ap else 0
        return {
            "apprise_available": APPRISE_AVAILABLE,
            "initialized": self._initialized,
            "channel_count": channel_count,
            "tag_routes": list(self._tag_routes.keys()),
            "min_level": self._min_level.name,
            "send_count": self._send_count,
            "error_count": self._error_count,
            "event_subscribed": self._event_subscribed,
            "mapped_events": len(_EVENT_NOTIFY_MAP),
        }

    def add_channel(self, url: str, tag: Optional[str] = None) -> bool:
        """运行时动态添加通知渠道"""
        if not APPRISE_AVAILABLE:
            logger.warning("Apprise 未安装，无法添加渠道")
            return False

        if not self._initialized:
            self.initialize()

        if tag:
            if tag not in self._tag_routes:
                self._tag_routes[tag] = apprise.Apprise()
            try:
                return bool(self._tag_routes[tag].add(url, tag=tag))
            except Exception as e:
                logger.error(f"添加标签渠道失败 [{tag}]: {e}")
                return False
        else:
            try:
                return bool(self._ap.add(url)) if self._ap else False
            except Exception as e:
                logger.error(f"添加渠道失败: {e}")
                return False

    def clear_channels(self) -> None:
        """清空所有渠道（用于测试）"""
        if self._ap:
            self._ap.clear()
        self._tag_routes.clear()


# ── 全局单例 ──────────────────────────────────────────────

_notification_manager: Optional[NotificationManager] = None


def get_notification_manager() -> NotificationManager:
    """
    获取全局通知管理器单例。

    首次调用时自动初始化（从环境变量/配置文件加载渠道）。
    """
    global _notification_manager
    if _notification_manager is None:
        _notification_manager = NotificationManager()
        _notification_manager.initialize()
    return _notification_manager


def reset_notification_manager() -> None:
    """重置通知管理器（仅用于测试）"""
    global _notification_manager
    _notification_manager = None
