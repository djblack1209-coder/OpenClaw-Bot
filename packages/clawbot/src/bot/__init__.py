"""
ClawBot Bot 模块 - 从 multi_main.py 拆分出的 MultiBot 组件

注意: 不在此处导入 MultiBot，避免触发全部 10 个 Mixin 的连锁加载。
之前的 `from src.bot.multi_bot import MultiBot` 导致:
  bot/__init__ → multi_bot → 10个Mixin → telegram_ux → bot/__init__ (循环)
使用方请直接: from src.bot.multi_bot import MultiBot

修复: HI-258 循环导入 (telegram_ux ↔ bot)
"""
