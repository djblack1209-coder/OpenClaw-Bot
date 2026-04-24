"""
Core — 节点执行器 Mixin 聚合入口

从各领域子模块组合所有 _exec_* 方法，供 Brain 类多继承使用。
对外接口完全不变 — Brain 只需继承 BrainExecutorMixin。

拆分说明 (MRU分析 P1-1, 2026-04-16):
  原 brain_executors.py (653行, 扇出20+模块) 按领域拆分为:
  - brain_exec_invest.py  — 投资/交易/风控/持仓 (6方法)
  - brain_exec_social.py  — 热点/采集/策划/生成/发布 (5方法)
  - brain_exec_life.py    — 购物/比价/预订/天气/提醒 (10方法)
  - brain_exec_tools.py   — LLM查询/代码/系统/进化 (4方法)
"""

from src.core.brain_exec_invest import InvestExecutorMixin
from src.core.brain_exec_life import LifeExecutorMixin
from src.core.brain_exec_social import SocialExecutorMixin
from src.core.brain_exec_tools import ToolsExecutorMixin


class BrainExecutorMixin(
    InvestExecutorMixin,
    SocialExecutorMixin,
    LifeExecutorMixin,
    ToolsExecutorMixin,
):
    """节点执行器 Mixin — 聚合所有领域执行器

    每个子 Mixin 独立负责一个领域的 _exec_* 方法，
    降低单文件扇出复杂度，提升可维护性。
    """
