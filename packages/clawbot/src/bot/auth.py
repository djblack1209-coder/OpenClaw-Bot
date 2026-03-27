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

from telegram import Update
from telegram.ext import ContextTypes


def requires_auth(func):
    """装饰器: 检查用户是否授权。未授权时静默返回 (与原行为一致)。"""
    @functools.wraps(func)
    async def wrapper(self, update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        if not self._is_authorized(update.effective_user.id):
            return
        return await func(self, update, context, *args, **kwargs)
    return wrapper
