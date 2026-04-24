"""
极端行情检测 Mixin

从 risk_manager.py 提取的极端行情相关方法：
- check_extreme_market(): 检测 ATR 飙升、闪崩、VIX 恐慌、价差过大
- record_extreme_event(): 记录极端行情事件并启动冷却
- is_in_extreme_cooldown(): 检查是否在极端行情冷却期
"""
import logging
from datetime import timedelta

from src.utils import now_et

logger = logging.getLogger(__name__)


class ExtremeMarketMixin:
    """极端行情检测混入类

    依赖 RiskManager.__init__ 中初始化的属性:
        self.config            — RiskConfig 实例
        self._extreme_events   — 极端事件列表
        self._last_extreme_time — 最近一次极端事件时间
    """

    def check_extreme_market(
        self,
        symbol: str,
        current_atr: float = 0,
        avg_atr: float = 0,
        price_change_pct: float = 0,
        vix: float = 0,
        spread_pct: float = 0,
    ) -> tuple[str, list[str]]:
        """
        检测极端行情条件

        返回: (condition_level, warnings)
            condition_level: "normal", "elevated", "extreme", "halted"
            warnings: 触发的警告列表
        """
        warnings = []
        condition = "normal"

        # 检查1: ATR波动率飙升
        if avg_atr > 0 and current_atr > avg_atr * self.config.volatility_spike_threshold:
            ratio = current_atr / avg_atr
            warnings.append(
                f"[{symbol}] 波动率飙升: ATR={current_atr:.4f}, "
                f"均值={avg_atr:.4f}, 倍数={ratio:.1f}x "
                f"(阈值{self.config.volatility_spike_threshold}x)"
            )
            condition = "extreme"
            logger.warning(f"[RiskManager] 波动率飙升检测: {symbol} ATR {ratio:.1f}x")

        # 检查2: 闪崩检测（单根K线大幅下跌）
        if abs(price_change_pct) > self.config.flash_crash_pct * 100:
            warnings.append(
                f"[{symbol}] 闪崩警报: 单K线变动{price_change_pct:+.2f}%, "
                f"阈值±{self.config.flash_crash_pct * 100:.1f}%"
            )
            condition = "extreme"
            logger.warning(
                f"[RiskManager] 闪崩检测: {symbol} 变动{price_change_pct:+.2f}%"
            )

        # 检查3: VIX恐慌指数熔断
        if vix > self.config.circuit_breaker_vix_level:
            warnings.append(
                f"VIX={vix:.1f} 超过熔断阈值{self.config.circuit_breaker_vix_level}, "
                f"暂停所有新开仓"
            )
            condition = "halted"
            logger.warning(f"[RiskManager] VIX熔断: VIX={vix:.1f}")
        elif vix > self.config.circuit_breaker_vix_level * 0.8:
            warnings.append(
                f"VIX={vix:.1f} 接近熔断阈值{self.config.circuit_breaker_vix_level}, "
                f"建议减仓"
            )
            if condition == "normal":
                condition = "elevated"

        # 检查4: 买卖价差过大
        if spread_pct > self.config.max_spread_pct:
            warnings.append(
                f"[{symbol}] 价差过大: {spread_pct*100:.2f}%, "
                f"阈值{self.config.max_spread_pct*100:.1f}%, "
                f"流动性不足"
            )
            if condition == "normal":
                condition = "elevated"
            logger.warning(
                f"[RiskManager] 价差过大: {symbol} spread={spread_pct*100:.2f}%"
            )

        # 如果检测到极端或暂停，自动记录事件
        if condition in ("extreme", "halted"):
            self.record_extreme_event(
                event_type=condition,
                details="; ".join(warnings)
            )

        return condition, warnings

    def record_extreme_event(self, event_type: str, details: str = ""):
        """记录极端行情事件并启动冷却"""
        now = now_et()
        event = {
            "time": now.isoformat(),
            "type": event_type,
            "details": details,
        }
        self._extreme_events.append(event)
        self._last_extreme_time = now
        logger.warning(
            f"[RiskManager] 极端行情事件记录: type={event_type}, "
            f"冷却{self.config.extreme_market_cooldown_minutes}分钟 | {details}"
        )

    def is_in_extreme_cooldown(self) -> bool:
        """检查是否在极端行情冷却期"""
        if self._last_extreme_time is None:
            return False
        cooldown_end = self._last_extreme_time + timedelta(
            minutes=self.config.extreme_market_cooldown_minutes
        )
        if now_et() >= cooldown_end:
            logger.info("[RiskManager] 极端行情冷却期结束，恢复交易")
            self._last_extreme_time = None
            return False
        return True
