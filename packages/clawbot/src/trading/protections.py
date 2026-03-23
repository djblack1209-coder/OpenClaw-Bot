"""
Trading — 保护系统 (借鉴 freqtrade Protections)

可链式组合的交易保护机制:
- StoplossGuard: N次止损后暂停交易
- MaxDrawdownGuard: 最大回撤保护
- CooldownGuard: 交易后冷却期
- LowProfitGuard: 低收益标的锁定

与现有 risk_manager.py 互补:
- risk_manager 做单笔交易的准入检查（17层）
- protections 做系统级的熔断保护（跨交易）
"""
import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from src.utils import now_et

logger = logging.getLogger(__name__)


@dataclass
class ProtectionResult:
    """保护检查结果"""
    allowed: bool = True
    reason: str = ""
    locked_until: Optional[datetime] = None
    protection_name: str = ""


class BaseProtection(ABC):
    """保护机制基类"""
    name: str = "base"
    enabled: bool = True

    @abstractmethod
    def check(self, symbol: str = "", trade_history: List[Dict] = None) -> ProtectionResult:
        ...

    @abstractmethod
    def reset(self):
        ...


class StoplossGuard(BaseProtection):
    """止损守卫: N次止损后暂停交易指定时间

    借鉴 freqtrade StoplossGuard:
    - 在 lookback_period 内触发 max_allowed 次止损后暂停
    - 暂停 stop_duration 分钟
    """
    name = "stoploss_guard"

    def __init__(
        self, max_allowed: int = 3, lookback_minutes: int = 60,
        stop_duration_minutes: int = 30,
    ):
        self.max_allowed = max_allowed
        self.lookback_minutes = lookback_minutes
        self.stop_duration_minutes = stop_duration_minutes
        self._locked_until: Optional[datetime] = None

    def check(self, symbol: str = "", trade_history: List[Dict] = None) -> ProtectionResult:
        now = now_et()
        if self._locked_until and now < self._locked_until:
            remaining = (self._locked_until - now).total_seconds() / 60
            return ProtectionResult(
                allowed=False,
                reason=f"止损守卫: 暂停交易中，剩余 {remaining:.0f} 分钟",
                locked_until=self._locked_until,
                protection_name=self.name,
            )
        cutoff = now - timedelta(minutes=self.lookback_minutes)
        sl_count = 0
        for t in (trade_history or []):
            exit_reason = str(t.get("exit_reason", "")).lower()
            exit_time = t.get("exit_time")
            if "stop" in exit_reason or "sl" in exit_reason:
                if exit_time and isinstance(exit_time, datetime) and exit_time >= cutoff:
                    sl_count += 1
                elif exit_time is None:
                    sl_count += 1
        if sl_count >= self.max_allowed:
            self._locked_until = now + timedelta(minutes=self.stop_duration_minutes)
            logger.warning(
                f"[StoplossGuard] {sl_count} 次止损触发，暂停 {self.stop_duration_minutes} 分钟"
            )
            return ProtectionResult(
                allowed=False,
                reason=f"止损守卫: {sl_count}次止损，暂停{self.stop_duration_minutes}分钟",
                locked_until=self._locked_until,
                protection_name=self.name,
            )
        return ProtectionResult(allowed=True, protection_name=self.name)

    def reset(self):
        self._locked_until = None


class MaxDrawdownGuard(BaseProtection):
    """最大回撤保护: 回撤超过阈值后暂停交易

    借鉴 freqtrade MaxDrawdown:
    - 监控滚动窗口内的累计亏损
    - 超过 max_drawdown_pct 后暂停
    """
    name = "max_drawdown"

    def __init__(
        self, max_drawdown_pct: float = 10.0,
        lookback_trades: int = 20,
        stop_duration_minutes: int = 120,
    ):
        self.max_drawdown_pct = max_drawdown_pct
        self.lookback_trades = lookback_trades
        self.stop_duration_minutes = stop_duration_minutes
        self._locked_until: Optional[datetime] = None

    def check(self, symbol: str = "", trade_history: List[Dict] = None) -> ProtectionResult:
        now = now_et()
        if self._locked_until and now < self._locked_until:
            remaining = (self._locked_until - now).total_seconds() / 60
            return ProtectionResult(
                allowed=False,
                reason=f"回撤保护: 暂停中，剩余 {remaining:.0f} 分钟",
                locked_until=self._locked_until,
                protection_name=self.name,
            )
        recent = (trade_history or [])[-self.lookback_trades:]
        if not recent:
            return ProtectionResult(allowed=True, protection_name=self.name)
        total_pnl_pct = sum(float(t.get("pnl_pct", 0)) for t in recent)
        if total_pnl_pct <= -self.max_drawdown_pct:
            self._locked_until = now + timedelta(minutes=self.stop_duration_minutes)
            logger.warning(
                f"[MaxDrawdownGuard] 回撤 {total_pnl_pct:.1f}% 超过阈值 "
                f"-{self.max_drawdown_pct}%，暂停 {self.stop_duration_minutes} 分钟"
            )
            return ProtectionResult(
                allowed=False,
                reason=f"回撤保护: 累计亏损{total_pnl_pct:.1f}%，暂停{self.stop_duration_minutes}分钟",
                locked_until=self._locked_until,
                protection_name=self.name,
            )
        return ProtectionResult(allowed=True, protection_name=self.name)

    def reset(self):
        self._locked_until = None


class CooldownGuard(BaseProtection):
    """冷却期: 交易后强制等待一段时间

    借鉴 freqtrade CooldownPeriod:
    - 防止同一标的立即重入
    """
    name = "cooldown"

    def __init__(self, cooldown_minutes: int = 15):
        self.cooldown_minutes = cooldown_minutes
        self._last_trade_time: Dict[str, datetime] = {}

    def record_trade(self, symbol: str):
        self._last_trade_time[symbol] = now_et()

    def check(self, symbol: str = "", trade_history: List[Dict] = None) -> ProtectionResult:
        if not symbol or symbol not in self._last_trade_time:
            return ProtectionResult(allowed=True, protection_name=self.name)
        last = self._last_trade_time[symbol]
        elapsed = (now_et() - last).total_seconds() / 60
        if elapsed < self.cooldown_minutes:
            remaining = self.cooldown_minutes - elapsed
            return ProtectionResult(
                allowed=False,
                reason=f"冷却期: {symbol} 需等待 {remaining:.0f} 分钟",
                protection_name=self.name,
            )
        return ProtectionResult(allowed=True, protection_name=self.name)

    def reset(self):
        self._last_trade_time.clear()


class LowProfitGuard(BaseProtection):
    """低收益标的锁定: 连续亏损的标的暂时锁定

    借鉴 freqtrade LowProfitPairs
    """
    name = "low_profit"

    def __init__(
        self, min_profit_pct: float = -5.0,
        lookback_trades: int = 5,
        lock_duration_minutes: int = 240,
    ):
        self.min_profit_pct = min_profit_pct
        self.lookback_trades = lookback_trades
        self.lock_duration_minutes = lock_duration_minutes
        self._locked_symbols: Dict[str, datetime] = {}

    def check(self, symbol: str = "", trade_history: List[Dict] = None) -> ProtectionResult:
        if not symbol:
            return ProtectionResult(allowed=True, protection_name=self.name)
        now = now_et()
        if symbol in self._locked_symbols:
            if now < self._locked_symbols[symbol]:
                remaining = (self._locked_symbols[symbol] - now).total_seconds() / 60
                return ProtectionResult(
                    allowed=False,
                    reason=f"低收益锁定: {symbol} 剩余 {remaining:.0f} 分钟",
                    protection_name=self.name,
                )
            else:
                del self._locked_symbols[symbol]
        symbol_trades = [
            t for t in (trade_history or [])
            if t.get("symbol") == symbol
        ][-self.lookback_trades:]
        if len(symbol_trades) >= self.lookback_trades:
            avg_pnl = sum(float(t.get("pnl_pct", 0)) for t in symbol_trades) / len(symbol_trades)
            if avg_pnl < self.min_profit_pct:
                self._locked_symbols[symbol] = now + timedelta(minutes=self.lock_duration_minutes)
                return ProtectionResult(
                    allowed=False,
                    reason=f"低收益锁定: {symbol} 平均亏损{avg_pnl:.1f}%",
                    protection_name=self.name,
                )
        return ProtectionResult(allowed=True, protection_name=self.name)

    def reset(self):
        self._locked_symbols.clear()


class ProtectionManager:
    """保护系统管理器 — 链式执行所有保护检查"""

    def __init__(self):
        self._protections: List[BaseProtection] = []

    def add(self, protection: BaseProtection) -> "ProtectionManager":
        self._protections.append(protection)
        return self

    def check_all(
        self, symbol: str = "", trade_history: List[Dict] = None
    ) -> ProtectionResult:
        """依次检查所有保护，任一拒绝则拒绝"""
        for p in self._protections:
            if not p.enabled:
                continue
            result = p.check(symbol, trade_history)
            if not result.allowed:
                return result
        return ProtectionResult(allowed=True)

    def reset_all(self):
        for p in self._protections:
            p.reset()

    def get_status(self) -> List[Dict]:
        return [
            {"name": p.name, "enabled": p.enabled, "type": type(p).__name__}
            for p in self._protections
        ]


def create_default_protections() -> ProtectionManager:
    """创建默认保护系统"""
    mgr = ProtectionManager()
    mgr.add(StoplossGuard(max_allowed=3, lookback_minutes=60, stop_duration_minutes=30))
    mgr.add(MaxDrawdownGuard(max_drawdown_pct=10.0, lookback_trades=20, stop_duration_minutes=120))
    mgr.add(CooldownGuard(cooldown_minutes=15))
    mgr.add(LowProfitGuard(min_profit_pct=-5.0, lookback_trades=5, lock_duration_minutes=240))
    return mgr
