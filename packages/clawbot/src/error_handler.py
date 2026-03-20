"""
ClawBot - 结构化错误处理 v1.0
参考: python-telegram-bot 的 error_handler 最佳实践
     + Sentry SDK 的错误分类/去重/限流思路（不引入 Sentry 依赖）

功能:
- 全局异常捕获 + 分类（网络/API/数据库/权限/未知）
- 错误去重（相同错误 N 分钟内只报一次）
- Telegram 通知（发给管理员）
- 与 monitoring.py StructuredLogger 集成
"""
import asyncio
import logging
import traceback
import time
from collections import defaultdict
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)


class ErrorCategory:
    """错误分类 — 参考 Sentry issue grouping"""
    NETWORK = "network"        # httpx/aiohttp/requests 超时、连接失败
    API = "api"                # LLM API 返回错误、rate limit
    DATABASE = "database"      # SQLite/连接池错误
    TELEGRAM = "telegram"      # Telegram API 错误（flood wait、权限等）
    AUTH = "auth"              # 授权/license 相关
    BUSINESS = "business"      # 业务逻辑错误（可预期）
    UNKNOWN = "unknown"


# 错误关键词 → 分类映射
_CATEGORY_RULES = [
    (ErrorCategory.NETWORK, ["timeout", "connect", "ConnectionError", "SSLError", "httpx"]),
    (ErrorCategory.API, ["rate_limit", "429", "quota", "insufficient", "api_error", "RateLimitError"]),
    (ErrorCategory.DATABASE, ["sqlite", "database", "OperationalError", "IntegrityError", "locked"]),
    (ErrorCategory.TELEGRAM, ["flood", "Forbidden", "ChatNotFound", "BadRequest", "telegram"]),
    (ErrorCategory.AUTH, ["unauthorized", "license", "permission", "403"]),
]


def classify_error(error: Exception) -> str:
    """根据异常类型和消息自动分类"""
    error_str = f"{type(error).__name__}: {error}".lower()
    for category, keywords in _CATEGORY_RULES:
        if any(kw.lower() in error_str for kw in keywords):
            return category
    return ErrorCategory.UNKNOWN


class ErrorThrottler:
    """错误去重/限流 — 相同指纹的错误在窗口期内只报一次
    
    参考 Sentry 的 fingerprint grouping，避免错误风暴刷屏。
    """

    def __init__(self, window_seconds: int = 300):
        self._window = window_seconds
        self._seen: Dict[str, float] = {}  # fingerprint -> last_reported_ts
        self._counts: Dict[str, int] = defaultdict(int)  # fingerprint -> suppressed count

    def fingerprint(self, error: Exception, context: str = "") -> str:
        """生成错误指纹"""
        return f"{type(error).__name__}:{context}:{str(error)[:100]}"

    def should_report(self, fp: str) -> bool:
        """是否应该上报（窗口期内去重）"""
        now = time.time()
        last = self._seen.get(fp, 0)
        if now - last < self._window:
            self._counts[fp] += 1
            return False
        self._seen[fp] = now
        self._counts[fp] = 0
        return True

    def get_suppressed_count(self, fp: str) -> int:
        return self._counts.get(fp, 0)

    def cleanup(self):
        """清理过期指纹"""
        now = time.time()
        expired = [fp for fp, ts in self._seen.items() if now - ts > self._window * 2]
        for fp in expired:
            self._seen.pop(fp, None)
            self._counts.pop(fp, None)


class ErrorHandler:
    """全局错误处理器
    
    用法:
        handler = ErrorHandler(admin_chat_id=123456, bot_token="xxx")
        
        # 作为 python-telegram-bot 的 error handler
        app.add_error_handler(handler.telegram_error_handler)
        
        # 手动上报
        await handler.report(error, bot_id="sonnet", context="cmd_invest")
    """

    def __init__(
        self,
        admin_chat_id: Optional[int] = None,
        bot_token: Optional[str] = None,
        throttle_window: int = 300,
        structured_logger=None,
    ):
        self.admin_chat_id = admin_chat_id
        self.bot_token = bot_token
        self._throttler = ErrorThrottler(throttle_window)
        self._structured_logger = structured_logger
        self._total_errors = 0
        self._category_counts: Dict[str, int] = defaultdict(int)

    async def report(
        self,
        error: Exception,
        bot_id: str = "system",
        context: str = "",
        user_id: Optional[int] = None,
        notify: bool = True,
    ):
        """上报错误 — 分类、去重、记录、通知"""
        self._total_errors += 1
        category = classify_error(error)
        self._category_counts[category] += 1

        fp = self._throttler.fingerprint(error, context)
        should_notify = self._throttler.should_report(fp)

        # 记录到结构化日志
        if self._structured_logger:
            try:
                self._structured_logger.log_error(bot_id, category, str(error))
            except Exception:
                pass

        # 记录到标准日志
        logger.error(
            f"[{category.upper()}] bot={bot_id} ctx={context} "
            f"err={type(error).__name__}: {error}",
            exc_info=True,
        )

        # Telegram 通知（去重后）
        if notify and should_notify and self.admin_chat_id and self.bot_token:
            suppressed = self._throttler.get_suppressed_count(fp)
            await self._notify_admin(error, category, bot_id, context, suppressed)

    async def _notify_admin(
        self, error: Exception, category: str, bot_id: str,
        context: str, suppressed: int,
    ):
        """发送错误通知到管理员 Telegram"""
        try:
            import httpx

            tb_lines = traceback.format_exception(type(error), error, error.__traceback__)
            tb_short = "".join(tb_lines[-3:])[:500]

            suppressed_note = f"\n(前 5 分钟内已抑制 {suppressed} 次相同错误)" if suppressed else ""

            text = (
                f"🔴 错误报告\n"
                f"───────────────────\n"
                f"分类: {category}\n"
                f"Bot: {bot_id}\n"
                f"场景: {context or '未知'}\n"
                f"错误: {type(error).__name__}: {str(error)[:200]}\n"
                f"───────────────────\n"
                f"{tb_short}{suppressed_note}"
            )

            async with httpx.AsyncClient(timeout=10) as client:
                await client.post(
                    f"https://api.telegram.org/bot{self.bot_token}/sendMessage",
                    json={"chat_id": self.admin_chat_id, "text": text},
                )
        except Exception as e:
            logger.debug(f"[ErrorHandler] 通知管理员失败: {e}")

    async def telegram_error_handler(self, update, context):
        """python-telegram-bot 的全局 error handler 回调
        
        用法: app.add_error_handler(handler.telegram_error_handler)
        """
        error = context.error
        bot_id = getattr(context.bot, '_bot_id', 'unknown') if context.bot else 'unknown'
        ctx = ""
        if update and update.effective_message:
            ctx = (update.effective_message.text or "")[:50]
        await self.report(error, bot_id=bot_id, context=f"telegram:{ctx}")

    def get_stats(self) -> Dict[str, Any]:
        """获取错误统计"""
        return {
            "total_errors": self._total_errors,
            "by_category": dict(self._category_counts),
        }


# 全局单例（延迟初始化）
_global_handler: Optional[ErrorHandler] = None


def init_error_handler(
    admin_chat_id: Optional[int] = None,
    bot_token: Optional[str] = None,
    structured_logger=None,
) -> ErrorHandler:
    """初始化全局错误处理器"""
    global _global_handler
    _global_handler = ErrorHandler(
        admin_chat_id=admin_chat_id,
        bot_token=bot_token,
        structured_logger=structured_logger,
    )
    return _global_handler


def get_error_handler() -> Optional[ErrorHandler]:
    return _global_handler
