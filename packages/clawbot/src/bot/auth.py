"""
权限装饰器 — 替代 75 处重复的 _is_authorized 检查。

用法::

    from src.bot.auth import requires_auth

    class SomeMixin:
        @requires_auth
        async def cmd_foo(self, update, context):
            ...  # 只有授权用户才会到这里

注意: cmd_start 等需要向未授权用户发送自定义消息的方法不使用本装饰器。
"""
import functools
import logging

from telegram import Update
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)


def requires_auth(func):
    """装饰器: 检查用户是否授权，并对命令参数做安全消毒。
    
    安全措施:
      1. 未授权时静默返回（与原行为一致）
      2. 对 context.args 中的每个参数执行 sanitize_input（防 XSS/SQL注入/命令注入）
    """
    @functools.wraps(func)
    async def wrapper(self, update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        if not self._is_authorized(update.effective_user.id):
            return
        # 对命令参数做安全消毒 — 所有 /cmd arg1 arg2 的参数都经过过滤
        if context.args:
            try:
                from src.core.security import get_security_gate
                _sec = get_security_gate()
                context.args = [_sec.sanitize_input(a) for a in context.args]
            except Exception as e:
                logger.warning("命令参数消毒失败（fail-close）: %s", e)
                if update.message:
                    await update.message.reply_text("⚠️ 参数安全检查异常，请稍后重试。")
                return
        return await func(self, update, context, *args, **kwargs)
    return wrapper
