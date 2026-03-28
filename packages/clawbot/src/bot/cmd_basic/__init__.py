"""
基础命令子包 — 将原 cmd_basic_mixin.py 拆分为多个职责清晰的子 Mixin

通过 MRO 组装为最终的 BasicCommandsMixin，对外接口完全不变。
"""
from src.bot.cmd_basic.help_mixin import _HelpMixin, _build_help_main_keyboard  # noqa: F401
from src.bot.cmd_basic.status_mixin import _StatusMixin
from src.bot.cmd_basic.settings_mixin import _SettingsMixin
from src.bot.cmd_basic.memory_mixin import _MemoryMixin
from src.bot.cmd_basic.callback_mixin import _CallbackMixin
from src.bot.cmd_basic.tools_mixin import _ToolsMixin
from src.bot.cmd_basic.context_mixin import _ContextMixin


class BasicCommandsMixin(
    _HelpMixin,
    _StatusMixin,
    _SettingsMixin,
    _MemoryMixin,
    _CallbackMixin,
    _ToolsMixin,
    _ContextMixin,
):
    """基础 Telegram 命令 — 组合全部子 Mixin"""
    pass
