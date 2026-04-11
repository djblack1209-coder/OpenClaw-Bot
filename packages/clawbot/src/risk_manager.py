"""
ClawBot 硬性风控引擎 v2.0
程序化强制执行的风控规则 - 不依赖AI prompt，代码级别拦截

对标项目: freqtrade (47.7k⭐)

核心规则：
1. 单笔风险上限：不超过总资金的2%
2. 日亏损上限：-$100 触发熔断，禁止新开仓
3. 仓位集中度：单只标的不超过总资金30%
4. 总敞口上限：不超过总资金80%
5. 风险收益比：低于1:2的交易直接否决
6. 最大持仓数：同时不超过5个持仓
7. 连续亏损熔断：连续3笔亏损后暂停30分钟
8. 交易时段检查：非交易时段禁止下单（可配置）

v2.0 新增（对标 freqtrade）：
9.  动态回撤保护：滚动窗口回撤超阈值自动降仓
10. 凯利公式仓位：基于历史胜率/盈亏比动态计算最优仓位
11. 相关性风险检测：避免持有高度相关标的
12. 阶梯式熔断：三级降级（警告→半仓→停止）
13. 滚动窗口风控：不只看当天，看滚动N天表现
14. 盈利回吐保护：浮盈回撤超阈值自动减仓提醒
15. 交易频率限制：防止过度交易

模块拆分说明（HI-358）：
- risk_extreme_market.py — 极端行情检测 (ExtremeMarketMixin)
- risk_kelly.py          — 凯利公式仓位计算 (KellyMixin)
- risk_sector.py         — 板块集中度与风险敞口 (SectorMixin)
- risk_config.py         — 配置与检查结果类型 (RiskConfig, RiskCheckResult)
"""
import logging
import threading
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from src.utils import now_et
from collections import deque

# 风控配置和检查结果类型已提取到 risk_config.py
from src.risk_config import RiskConfig, RiskCheckResult  # noqa: F401 — 向后兼容重新导出

# Mixin 模块：极端行情、凯利公式、板块集中度
from src.risk_extreme_market import ExtremeMarketMixin  # noqa: F401
from src.risk_kelly import KellyMixin  # noqa: F401
from src.risk_sector import SectorMixin  # noqa: F401

logger = logging.getLogger(__name__)


class RiskManager(ExtremeMarketMixin, KellyMixin, SectorMixin):
    """
    硬性风控引擎

    所有交易必须通过 check_trade() 审核，未通过则禁止执行。
    这是代码级别的强制拦截，不依赖AI的"自觉"。

    通过 Mixin 组合：
    - ExtremeMarketMixin: check_extreme_market / record_extreme_event / is_in_extreme_cooldown
    - KellyMixin: calc_kelly_quantity / _get_trade_stats
    - SectorMixin: _check_sector_concentration / lookup_sectors / get_risk_exposure_summary
    """

    def __init__(self, config: RiskConfig = None, journal=None):
        self.config = config or RiskConfig()
        self.journal = journal  # TradingJournal 实例

        # 运行时状态
        self._state_lock = threading.Lock()
        self._consecutive_losses: int = 0
        self._cooldown_until: Optional[datetime] = None
        self._today_pnl: float = 0.0
        self._today_trades: int = 0
        self._last_pnl_update: Optional[str] = None  # 日期字符串
        self._last_refresh_ts: Optional[datetime] = None

        # 极端行情状态
        self._extreme_events: List[dict] = []
        self._last_extreme_time: Optional[datetime] = None

        # === v2.0 新增状态 ===

        # 交易历史（用于凯利公式、滚动窗口）
        self._trade_history: deque = deque(maxlen=200)  # 最近200笔交易
        self._hourly_trade_times: deque = deque(maxlen=100)  # 交易时间戳

        # 回撤追踪
        self._peak_capital: float = self.config.total_capital  # 资金峰值
        self._rolling_pnl: deque = deque(maxlen=self.config.rolling_loss_window_trades)

        # 阶梯式熔断状态
        self._current_tier: int = 0  # 0=正常, 1=警告, 2=半仓, 3=停止
        self._position_scale: float = 1.0  # 仓位缩放因子

        # 板块/相关性追踪
        self._symbol_sectors: Dict[str, str] = {}

        # 盈利回吐追踪
        self._position_peak_pnl: Dict[str, float] = {}  # symbol -> 最高浮盈

        logger.info(f"[RiskManager] v2.0 初始化完成 | 资金=${self.config.total_capital} "
                     f"| 单笔风险{self.config.max_risk_per_trade_pct*100}% "
                     f"| 日亏损限额${self.config.daily_loss_limit} "
                     f"| 凯利公式={'开' if self.config.kelly_enabled else '关'} "
                     f"| 阶梯熔断={'开' if self.config.tiered_cooldown_enabled else '关'}")

    # ============ 核心：交易审核 ============

    def check_trade(
        self,
        symbol: str,
        side: str,           # BUY / SELL
        quantity: float,
        entry_price: float,
        stop_loss: float = 0,
        take_profit: float = 0,
        signal_score: int = 0,
        current_positions: List[Dict] = None,
    ) -> RiskCheckResult:
        """
        交易前风控审核 - 所有交易必须通过此检查

        返回 RiskCheckResult，approved=False 则禁止执行
        """
        result = RiskCheckResult(approved=True)
        warnings = []

        symbol = symbol.upper()
        side = side.upper()

        # === 检查-1: 参数合法性 ===
        if entry_price <= 0:
            return RiskCheckResult(
                approved=False,
                reason=f"入场价必须大于零 (got {entry_price})"
            )
        if quantity <= 0:
            return RiskCheckResult(
                approved=False,
                reason=f"交易数量必须大于零 (got {quantity})"
            )

        # === 检查0: 黑名单 ===
        if symbol in self.config.blacklist:
            return RiskCheckResult(
                approved=False,
                reason=f"{symbol} 在黑名单中，禁止交易"
            )

        # === 检查1: 熔断状态 ===
        if self._is_in_cooldown():
            remaining = int((self._cooldown_until - now_et()).total_seconds()) // 60
            return RiskCheckResult(
                approved=False,
                reason=f"熔断冷却中，还需等待{remaining}分钟 "
                       f"(连续{self._consecutive_losses}笔亏损触发)"
            )

        # === 检查1.5: 极端行情冷却期 ===
        if self.is_in_extreme_cooldown():
            remaining = int((self._last_extreme_time + timedelta(
                minutes=self.config.extreme_market_cooldown_minutes
            ) - now_et()).total_seconds() // 60)
            return RiskCheckResult(
                approved=False,
                reason=f"极端行情冷却期，暂停交易 (剩余{remaining}min)"
            )

        # === 检查2: 日亏损限额 ===
        self._refresh_today_pnl()
        if self._today_pnl <= -self.config.daily_loss_limit:
            return RiskCheckResult(
                approved=False,
                reason=f"已触及日亏损限额: 今日PnL=${self._today_pnl:.2f}, "
                       f"限额=-${self.config.daily_loss_limit:.2f}，今日禁止新开仓"
            )

        # === 检查3: 交易时段 ===
        if self.config.trading_hours_enabled and not self._is_trading_hours():
            return RiskCheckResult(
                approved=False,
                reason="当前非交易时段，禁止下单"
            )

        # === 检查4: 止损必须设定（买入时） ===
        if side == 'BUY' and stop_loss <= 0:
            return RiskCheckResult(
                approved=False,
                reason="买入必须设定止损价（stop_loss > 0）"
            )

        # === 检查5: 止损方向合理性 ===
        if side == 'BUY' and stop_loss > 0:
            if stop_loss >= entry_price:
                return RiskCheckResult(
                    approved=False,
                    reason=f"止损价({stop_loss})必须低于入场价({entry_price})"
                )
            # 止损幅度不能超过10%
            sl_pct = (entry_price - stop_loss) / entry_price
            if sl_pct > 0.10:
                warnings.append(f"止损幅度{sl_pct*100:.1f}%偏大(>10%)，超短线建议2-5%")

        # === 检查6: 风险收益比 ===
        if side == 'BUY' and stop_loss > 0 and take_profit > 0:
            risk = entry_price - stop_loss
            reward = take_profit - entry_price
            if risk > 0:
                rr_ratio = reward / risk
                if rr_ratio < self.config.min_risk_reward_ratio:
                    return RiskCheckResult(
                        approved=False,
                        reason=f"风险收益比{rr_ratio:.2f}:1 低于最低要求"
                               f"{self.config.min_risk_reward_ratio}:1 "
                               f"(风险${risk:.2f} vs 收益${reward:.2f})"
                    )
        elif side == 'BUY' and take_profit <= 0:
            warnings.append("未设定止盈价，建议设定以锁定利润")

        # === 检查7: 单笔风险金额 ===
        max_risk_amount = self.config.total_capital * self.config.max_risk_per_trade_pct
        if side == 'BUY' and stop_loss > 0:
            risk_per_share = entry_price - stop_loss
            actual_risk = quantity * risk_per_share
            if actual_risk > max_risk_amount:
                # 计算建议数量
                suggested_qty = int(max_risk_amount / risk_per_share)
                if suggested_qty <= 0:
                    return RiskCheckResult(
                        approved=False,
                        reason=f"单笔风险${actual_risk:.2f}超过上限"
                               f"${max_risk_amount:.2f}(资金的"
                               f"{self.config.max_risk_per_trade_pct*100}%)，"
                               f"且无法调整到合理数量"
                    )
                result.adjusted_quantity = suggested_qty
                warnings.append(
                    f"数量从{quantity}调整为{suggested_qty}，"
                    f"以控制风险在${max_risk_amount:.2f}以内"
                )
                quantity = suggested_qty

        # === 检查8: 仓位集中度 ===
        position_value = quantity * entry_price
        max_position_value = self.config.total_capital * self.config.max_position_pct
        if position_value > max_position_value:
            suggested_qty = int(max_position_value / entry_price)
            if suggested_qty <= 0:
                return RiskCheckResult(
                    approved=False,
                    reason=f"仓位价值${position_value:.2f}超过单只上限"
                           f"${max_position_value:.2f}(资金的"
                           f"{self.config.max_position_pct*100}%)"
                )
            if result.adjusted_quantity is None or suggested_qty < result.adjusted_quantity:
                result.adjusted_quantity = suggested_qty
            warnings.append(
                f"仓位价值${position_value:.2f}超过上限"
                f"${max_position_value:.2f}，建议减少数量"
            )

        # === 检查9: 总敞口 ===
        if current_positions:
            total_exposure = sum(
                p.get('quantity', 0) * (p.get('avg_price', 0) or p.get('avg_cost', 0))
                for p in current_positions
                if p.get('status', 'open') == 'open' or 'status' not in p
            )
            new_total = total_exposure + position_value
            max_exposure = self.config.total_capital * self.config.max_total_exposure_pct
            if new_total > max_exposure:
                return RiskCheckResult(
                    approved=False,
                    reason=f"总敞口${new_total:.2f}将超过上限"
                           f"${max_exposure:.2f}(资金的"
                           f"{self.config.max_total_exposure_pct*100}%)"
                )

        # === 检查10: 最大持仓数 ===
        if current_positions and side == 'BUY':
            open_count = len([
                p for p in current_positions
                if p.get('status', 'open') == 'open' or 'status' not in p
            ])
            # 检查是否是加仓（已有该标的持仓）
            has_existing = any(
                p.get('symbol', '').upper() == symbol
                for p in current_positions
                if p.get('status', 'open') == 'open' or 'status' not in p
            )
            if not has_existing and open_count >= self.config.max_open_positions:
                return RiskCheckResult(
                    approved=False,
                    reason=f"已有{open_count}个持仓，达到上限"
                           f"{self.config.max_open_positions}个，禁止新开仓"
                )

        # === 检查11: 信号强度 ===
        if abs(signal_score) < self.config.min_signal_score and signal_score != 0:
            warnings.append(
                f"信号评分{signal_score}偏弱(阈值±{self.config.min_signal_score})，"
                f"建议谨慎"
            )

        # === 检查12: 剩余日亏损额度 ===
        remaining_daily = self.config.daily_loss_limit + self._today_pnl
        if side == 'BUY' and stop_loss > 0:
            potential_loss = quantity * (entry_price - stop_loss)
            if potential_loss > remaining_daily:
                warnings.append(
                    f"该笔最大亏损${potential_loss:.2f}可能触及日亏损限额"
                    f"(剩余额度${remaining_daily:.2f})"
                )

        # === v2.0 检查13: 阶梯式熔断仓位缩放 ===
        if self.config.tiered_cooldown_enabled and self._position_scale < 1.0:
            original_qty = result.adjusted_quantity or quantity
            scaled_qty = max(1, int(original_qty * self._position_scale))
            if scaled_qty < original_qty:
                result.adjusted_quantity = scaled_qty
                warnings.append(
                    f"阶梯熔断Tier{self._current_tier}: 仓位缩放至"
                    f"{self._position_scale*100:.0f}%，"
                    f"数量{original_qty}->{scaled_qty}"
                )
                quantity = scaled_qty

        # === v2.0 检查14: 动态回撤保护 ===
        drawdown_level = self._get_drawdown_level()
        if drawdown_level == "halt":
            return RiskCheckResult(
                approved=False,
                reason=f"滚动{self.config.drawdown_window_days}天回撤超过"
                       f"{self.config.drawdown_halt_pct*100}%，暂停交易"
            )
        elif drawdown_level == "warn":
            original_qty = result.adjusted_quantity or quantity
            scaled_qty = max(1, int(original_qty * 0.5))
            if scaled_qty < original_qty:
                result.adjusted_quantity = scaled_qty
                warnings.append(
                    f"回撤保护: 近{self.config.drawdown_window_days}天回撤超"
                    f"{self.config.drawdown_warn_pct*100}%，仓位减半"
                )
                quantity = scaled_qty

        # === v2.0 检查15: 滚动窗口亏损 ===
        if len(self._rolling_pnl) >= 5:
            rolling_total = sum(self._rolling_pnl)
            rolling_max_loss = self.config.total_capital * self.config.rolling_loss_max_pct
            if rolling_total < -rolling_max_loss:
                return RiskCheckResult(
                    approved=False,
                    reason=f"最近{len(self._rolling_pnl)}笔交易累计亏损"
                           f"${abs(rolling_total):.2f}，超过滚动窗口限额"
                           f"${rolling_max_loss:.2f}"
                )

        # === v2.0 检查16: 交易频率限制 ===
        freq_check = self._check_trade_frequency()
        if freq_check:
            return RiskCheckResult(approved=False, reason=freq_check)

        # === v2.0 检查17: 相关性/板块集中度 ===
        if current_positions and side == 'BUY':
            sector_warning = self._check_sector_concentration(
                symbol, quantity * entry_price, current_positions
            )
            if sector_warning:
                warnings.append(sector_warning)

        # 计算最终风险指标
        final_qty = result.adjusted_quantity or quantity
        if side == 'BUY' and stop_loss > 0:
            result.max_loss = final_qty * (entry_price - stop_loss)
        result.max_position_value = final_qty * entry_price
        result.risk_score = self._calc_risk_score(
            symbol, side, final_qty, entry_price, stop_loss,
            take_profit, signal_score, current_positions
        )
        result.warnings = warnings

        # 高风险评分警告
        if result.risk_score >= 70:
            warnings.append(f"综合风险评分{result.risk_score}/100，风险较高")

        logger.info(f"[RiskManager] {symbol} {side} x{quantity} @ {entry_price} -> "
                     f"{'APPROVED' if result.approved else 'REJECTED'} "
                     f"(risk_score={result.risk_score})")

        return result

    # ============ 交易后更新 ============

    def record_trade_result(self, pnl: float, symbol: str = ""):
        """记录交易结果，更新连续亏损计数、日PnL、滚动窗口、阶梯熔断"""
        with self._state_lock:
            self._record_trade_result_inner(pnl, symbol)

    def _record_trade_result_inner(self, pnl: float, symbol: str = ""):
        """内部实现 — 由 _state_lock 保护"""
        self._today_pnl += pnl
        self._today_trades += 1

        # v2.0: 记录到交易历史和滚动窗口
        trade_record = {
            "pnl": pnl,
            "symbol": symbol,
            "time": now_et().isoformat(),
        }
        self._trade_history.append(trade_record)
        self._rolling_pnl.append(pnl)
        self._hourly_trade_times.append(now_et())

        # v2.0: 更新资金峰值（用于回撤计算）
        current_capital = self.config.total_capital + self._today_pnl
        if current_capital > self._peak_capital:
            self._peak_capital = current_capital

        if pnl <= 0:
            self._consecutive_losses += 1
            logger.warning(f"[RiskManager] 亏损${pnl:.2f}，连续亏损{self._consecutive_losses}笔")

            # v2.0: 阶梯式熔断（替代原有一刀切）
            if self.config.tiered_cooldown_enabled:
                self._update_tiered_cooldown()
            else:
                # 原有逻辑：一刀切熔断
                if self._consecutive_losses >= self.config.max_consecutive_losses:
                    self._cooldown_until = now_et() + timedelta(
                        minutes=self.config.cooldown_minutes
                    )
                    logger.warning(
                        f"[RiskManager] 熔断触发！连续{self._consecutive_losses}笔亏损，"
                        f"冷却{self.config.cooldown_minutes}分钟"
                    )
        else:
            self._consecutive_losses = 0
            # v2.0: 盈利时恢复阶梯状态
            if self._current_tier > 0:
                self._current_tier = max(0, self._current_tier - 1)
                self._position_scale = 1.0 if self._current_tier == 0 else self.config.tier1_position_scale
                logger.info(f"[RiskManager] 盈利恢复，阶梯降至Tier{self._current_tier}")

        # 日亏损限额检查
        if self._today_pnl <= -self.config.daily_loss_limit:
            logger.warning(
                f"[RiskManager] 日亏损限额触发！今日PnL=${self._today_pnl:.2f}，"
                f"限额=-${self.config.daily_loss_limit:.2f}，今日停止交易"
            )

    def reset_daily(self):
        """每日重置（新交易日开始时调用）"""
        self._today_pnl = 0.0
        self._today_trades = 0
        self._consecutive_losses = 0
        self._cooldown_until = None
        # FIX 9: 同步重置分层状态，确保每日干净启动
        self._current_tier = 0
        self._position_scale = 1.0
        self._last_pnl_update = now_et().strftime('%Y-%m-%d')
        self._last_refresh_ts = None
        logger.info("[RiskManager] 日重置完成（含连续亏损、熔断、分层状态清零）")

    # ============ 仓位计算 ============

    def calc_safe_quantity(
        self,
        entry_price: float,
        stop_loss: float,
        capital: float = None,
    ) -> Dict:
        """
        基于风控规则计算安全仓位大小

        返回: {shares, total_cost, max_loss, risk_pct}
        """
        cap = capital or self.config.total_capital
        if cap <= 0:
            return {"error": "资金为零，无法计算仓位", "shares": 0}
        if entry_price is None or entry_price <= 0:
            return {"error": "入场价必须大于零", "shares": 0}
        if stop_loss is None:
            return {"error": "止损价不能为空", "shares": 0}

        max_risk = cap * self.config.max_risk_per_trade_pct
        max_position = cap * self.config.max_position_pct

        risk_per_share = abs(entry_price - stop_loss)
        if risk_per_share <= 0:
            return {"error": "止损价不能等于入场价", "shares": 0}

        # 基于风险的数量
        shares_by_risk = int(max_risk / risk_per_share)
        # 基于仓位上限的数量
        shares_by_position = int(max_position / entry_price)
        # 取较小值
        shares = min(shares_by_risk, shares_by_position)

        if shares <= 0:
            return {"error": "计算出的安全仓位为0，价格或止损设置不合理"}

        total_cost = shares * entry_price
        max_loss = shares * risk_per_share

        return {
            "shares": shares,
            "entry_price": entry_price,
            "stop_loss": stop_loss,
            "total_cost": round(total_cost, 2),
            "max_loss": round(max_loss, 2),
            "risk_pct": round(max_loss / cap * 100, 2),
            "position_pct": round(total_cost / cap * 100, 2),
        }

    # ============ 状态查询 ============

    def format_status(self) -> str:
        """格式化风控状态（v2.0增强版）"""
        s = self.get_status()
        lines = [
            "风控系统状态 v2.0",
            "",
            f"总资金: ${s['capital']:,.2f}  |  峰值: ${s['peak_capital']:,.2f}",
            f"今日PnL: ${s['today_pnl']:+.2f} / 限额-${s['daily_loss_limit']:.0f}",
            f"今日剩余额度: ${s['remaining_daily_loss_budget']:.2f}",
            f"今日交易: {s['today_trades']}笔",
            "",
            f"单笔最大风险: ${s['max_risk_per_trade']:.2f} "
            f"({self.config.max_risk_per_trade_pct*100}%)",
            f"单只最大仓位: ${s['max_position_value']:.2f} "
            f"({self.config.max_position_pct*100}%)",
            f"总敞口上限: ${s['max_total_exposure']:.2f} "
            f"({self.config.max_total_exposure_pct*100}%)",
            f"最大持仓数: {self.config.max_open_positions}",
            f"最低风险收益比: 1:{self.config.min_risk_reward_ratio}",
            "",
            f"连续亏损: {s['consecutive_losses']}/{self.config.max_consecutive_losses}",
            f"回撤: {s['drawdown_pct']}%",
            f"滚动窗口PnL: ${s['rolling_pnl']:+.2f}",
            f"历史胜率: {s['win_rate']}% ({s['total_history_trades']}笔)",
        ]

        # 阶梯熔断状态
        tier = s['tiered_cooldown_tier']
        if tier > 0:
            lines.append(f"阶梯熔断: Tier{tier} (仓位缩放{s['position_scale']*100:.0f}%)")

        if s['in_cooldown']:
            lines.append(f"!! 熔断中，解除时间: {s['cooldown_until']} !!")
        else:
            lines.append("熔断状态: 正常")

        # 极端行情状态
        lines.append("")
        if self.is_in_extreme_cooldown():
            remaining = int((self._last_extreme_time + timedelta(
                minutes=self.config.extreme_market_cooldown_minutes
            ) - now_et()).total_seconds() // 60)
            lines.append(f"!! 极端行情冷却中，剩余{remaining}分钟 !!")
        else:
            lines.append("极端行情保护: 正常")
        lines.append(f"极端事件记录: {len(self._extreme_events)}次")
        if self._extreme_events:
            last = self._extreme_events[-1]
            lines.append(f"最近事件: [{last['type']}] {last['time']}")

        # 凯利公式
        if self.config.kelly_enabled:
            lines.append(f"\n凯利公式: 开启 (保守系数{self.config.kelly_fraction})")

        return "\n".join(lines)

    def get_status(self) -> Dict:
        """获取风控系统状态（v2.0增强版）"""
        self._refresh_today_pnl()
        remaining_daily = self.config.daily_loss_limit + self._today_pnl
        stats = self._get_trade_stats()

        # 回撤计算
        current_capital = self.config.total_capital + self._today_pnl
        drawdown = 0
        if self._peak_capital > 0:
            drawdown = (self._peak_capital - current_capital) / self._peak_capital

        return {
            "capital": self.config.total_capital,
            "today_pnl": round(self._today_pnl, 2),
            "today_trades": self._today_trades,
            "daily_loss_limit": self.config.daily_loss_limit,
            "remaining_daily_loss_budget": round(max(0, remaining_daily), 2),
            "consecutive_losses": self._consecutive_losses,
            "in_cooldown": self._is_in_cooldown(),
            "cooldown_until": self._cooldown_until.isoformat() if self._cooldown_until else None,
            "max_risk_per_trade": round(
                self.config.total_capital * self.config.max_risk_per_trade_pct, 2
            ),
            "max_position_value": round(
                self.config.total_capital * self.config.max_position_pct, 2
            ),
            "max_total_exposure": round(
                self.config.total_capital * self.config.max_total_exposure_pct, 2
            ),
            # v2.0 新增
            "tiered_cooldown_tier": self._current_tier,
            "position_scale": self._position_scale,
            "drawdown_pct": round(drawdown * 100, 2),
            "peak_capital": round(self._peak_capital, 2),
            "rolling_pnl": round(sum(self._rolling_pnl), 2) if self._rolling_pnl else 0,
            "win_rate": round(stats["win_rate"] * 100, 1),
            "total_history_trades": stats["total_trades"],
            "kelly_enabled": self.config.kelly_enabled,
        }

    # ============ 内部方法 ============

    def _is_in_cooldown(self) -> bool:
        """检查是否在熔断冷却中"""
        if self._cooldown_until is None:
            return False
        if now_et() >= self._cooldown_until:
            self._cooldown_until = None
            self._consecutive_losses = 0
            logger.info("[RiskManager] 熔断冷却结束，恢复交易")
            return False
        return True

    def _is_trading_hours(self) -> bool:
        """检查是否在交易时段"""
        now = now_et()
        start = now.replace(
            hour=self.config.trading_start_hour,
            minute=self.config.trading_start_minute,
            second=0
        )
        end = now.replace(
            hour=self.config.trading_end_hour,
            minute=self.config.trading_end_minute,
            second=0
        )
        return start <= now <= end

    def _refresh_today_pnl(self):
        """从交易日志刷新今日PnL（每5分钟刷新一次）"""
        now = now_et()
        today = now.strftime('%Y-%m-%d')

        # 检测新交易日 -> 自动重置
        if self._last_pnl_update and self._last_pnl_update != today:
            logger.info("[RiskManager] 检测到新交易日，自动重置")
            self.reset_daily()
            return

        # 每5分钟刷新一次（而非每天只刷新一次）
        if hasattr(self, '_last_refresh_ts') and self._last_refresh_ts:
            try:
                elapsed = (now - self._last_refresh_ts).total_seconds()
            except TypeError as e:  # noqa: F841
                # naive vs aware datetime mismatch — 强制刷新
                elapsed = 999
            if elapsed < 300:  # 5分钟内不重复刷新
                return

        if self.journal:
            try:
                today_data = self.journal.get_today_pnl()
                self._today_pnl = today_data.get('pnl', 0)
                self._today_trades = today_data.get('trades', 0)
            except Exception as e:
                logger.error(f"[RiskManager] 刷新今日PnL失败: {e}")

        self._last_pnl_update = today
        self._last_refresh_ts = now

    def _calc_risk_score(
        self,
        symbol: str,
        side: str,
        quantity: float,
        entry_price: float,
        stop_loss: float,
        take_profit: float,
        signal_score: int,
        current_positions: List[Dict] = None,
    ) -> int:
        """
        计算综合风险评分 0-100（越高越危险）
        """
        score = 0
        cap = self.config.total_capital

        # 仓位占比风险 (0-25分)
        position_value = quantity * entry_price
        pos_pct = position_value / cap if cap > 0 else 1
        score += min(25, int(pos_pct / self.config.max_position_pct * 25))

        # 止损幅度风险 (0-20分)
        if side == 'BUY' and stop_loss > 0 and entry_price > 0:
            sl_pct = (entry_price - stop_loss) / entry_price
            if sl_pct > 0.05:
                score += min(20, int(sl_pct * 200))
            else:
                score += int(sl_pct * 100)
        elif side == 'BUY' and stop_loss <= 0:
            score += 20  # 无止损 = 高风险

        # 信号强度风险 (0-15分) - 信号越弱风险越高
        if signal_score != 0:
            strength = abs(signal_score)
            if strength < 20:
                score += 15
            elif strength < 40:
                score += 8
            elif strength < 60:
                score += 3
        else:
            score += 10  # 无信号

        # 日亏损接近限额 (0-20分)
        remaining = self.config.daily_loss_limit + self._today_pnl
        if remaining < self.config.daily_loss_limit * 0.3:
            score += 20
        elif remaining < self.config.daily_loss_limit * 0.5:
            score += 12
        elif remaining < self.config.daily_loss_limit * 0.7:
            score += 5

        # 连续亏损风险 (0-20分)
        if self._consecutive_losses >= 2:
            score += 20
        elif self._consecutive_losses >= 1:
            score += 10

        return min(100, score)

    # ============ v2.0 阶梯式熔断 ============

    def _update_tiered_cooldown(self):
        """阶梯式熔断：根据连续亏损次数逐步升级限制"""
        losses = self._consecutive_losses

        if losses >= self.config.tier3_losses:
            self._current_tier = 3
            self._position_scale = 0.0  # 完全停止
            self._cooldown_until = now_et() + timedelta(
                minutes=self.config.tier3_cooldown_minutes
            )
            logger.warning(
                f"[RiskManager] 阶梯熔断 Tier3: 连续{losses}笔亏损，"
                f"停止交易{self.config.tier3_cooldown_minutes}分钟"
            )
        elif losses >= self.config.tier2_losses:
            self._current_tier = 2
            self._position_scale = 0.0
            self._cooldown_until = now_et() + timedelta(
                minutes=self.config.tier2_cooldown_minutes
            )
            logger.warning(
                f"[RiskManager] 阶梯熔断 Tier2: 连续{losses}笔亏损，"
                f"暂停{self.config.tier2_cooldown_minutes}分钟"
            )
        elif losses >= self.config.tier1_losses:
            self._current_tier = 1
            self._position_scale = self.config.tier1_position_scale
            logger.warning(
                f"[RiskManager] 阶梯熔断 Tier1: 连续{losses}笔亏损，"
                f"仓位缩放至{self._position_scale*100:.0f}%"
            )

    # ============ v2.0 回撤与频率 ============

    def _get_drawdown_level(self) -> str:
        """
        计算滚动窗口回撤水平
        返回: "normal" / "warn" / "halt"
        """
        if self._peak_capital <= 0:
            return "normal"

        current_capital = self.config.total_capital + self._today_pnl
        drawdown = (self._peak_capital - current_capital) / self._peak_capital

        if drawdown >= self.config.drawdown_halt_pct:
            logger.warning(
                f"[RiskManager] 回撤保护-停止: 回撤{drawdown*100:.1f}% "
                f"(峰值${self._peak_capital:.2f} -> 当前${current_capital:.2f})"
            )
            return "halt"
        elif drawdown >= self.config.drawdown_warn_pct:
            logger.warning(
                f"[RiskManager] 回撤保护-警告: 回撤{drawdown*100:.1f}% "
                f"(峰值${self._peak_capital:.2f} -> 当前${current_capital:.2f})"
            )
            return "warn"
        return "normal"

    def _check_trade_frequency(self) -> Optional[str]:
        """检查交易频率是否超限，返回拒绝原因或None"""
        now = now_et()

        # 每日交易次数
        if self._today_trades >= self.config.max_trades_per_day:
            return (f"今日已交易{self._today_trades}笔，达到上限"
                    f"{self.config.max_trades_per_day}笔")

        # 每小时交易次数
        one_hour_ago = now - timedelta(hours=1)
        recent_count = sum(
            1 for t in self._hourly_trade_times if t > one_hour_ago
        )
        if recent_count >= self.config.max_trades_per_hour:
            return (f"最近1小时已交易{recent_count}笔，达到上限"
                    f"{self.config.max_trades_per_hour}笔，请稍后再试")

        return None

    # ============ v2.0 盈利回吐保护 ============

    def update_position_pnl(self, symbol: str, unrealized_pnl: float):
        """
        更新持仓浮盈，用于盈利回吐保护
        在每次行情更新时调用
        """
        symbol = symbol.upper()
        if not self.config.profit_drawdown_enabled:
            return None

        # 更新峰值
        current_peak = self._position_peak_pnl.get(symbol, 0)
        if unrealized_pnl > current_peak:
            self._position_peak_pnl[symbol] = unrealized_pnl
            return None

        # 检查回吐
        if current_peak > 0:
            drawdown = (current_peak - unrealized_pnl) / current_peak
            if drawdown >= self.config.profit_drawdown_pct:
                logger.warning(
                    f"[RiskManager] 盈利回吐警告: {symbol} 浮盈从"
                    f"${current_peak:.2f}回撤至${unrealized_pnl:.2f} "
                    f"(回撤{drawdown*100:.1f}%)"
                )
                return {
                    "symbol": symbol,
                    "peak_pnl": current_peak,
                    "current_pnl": unrealized_pnl,
                    "drawdown_pct": round(drawdown * 100, 1),
                    "action": "建议部分止盈或移动止损",
                }
        return None


# 全局实例
risk_manager = RiskManager()
