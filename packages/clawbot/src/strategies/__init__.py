"""
ClawBot 高级策略模块

搬运自:
- FinRL (AI4Finance, 11k⭐, MIT) — DRL 强化学习交易
- Qlib (Microsoft, 18k⭐, MIT) — Alpha 因子挖掘 + ML 信号

架构: 所有策略继承 BaseStrategy，通过 StrategyEngine.register() 注册参与加权投票。
"""

from src.strategies.drl_strategy import DRLStrategy
from src.strategies.factor_strategy import FactorStrategy

__all__ = ["DRLStrategy", "FactorStrategy"]
