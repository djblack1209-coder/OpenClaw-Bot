"""
此模块已拆分为 cmd_basic/ 子包，此文件保留向后兼容。

原 BasicCommandsMixin (1358行, 28方法) 按职责拆分为:
  - help_mixin.py    — /start, 帮助回调, onboarding
  - status_mixin.py  — /status, /metrics, /model, /pool, /keyhealth
  - settings_mixin.py — /settings 及回调
  - memory_mixin.py  — /memory, 记忆分页, 反馈回调
  - callback_mixin.py — 通知/卡片/追问按钮回调
  - tools_mixin.py   — /draw, /news, /qr, /tts, /agent, inline query
  - context_mixin.py — /context, /compact, /clear, /voice, /lanes
"""
from src.bot.cmd_basic import BasicCommandsMixin  # noqa: F401
from src.bot.cmd_basic.help_mixin import _build_help_main_keyboard  # noqa: F401
