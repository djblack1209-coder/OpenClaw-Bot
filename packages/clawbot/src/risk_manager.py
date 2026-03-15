"""
ClawBot 硬性风控引擎 v1.0
程序化强制执行的风控规则 - 不依赖AI prompt，代码级别拦截

核心规则：
1. 单笔风险上限：不超过总资金的2%
2. 日亏损上限：-$100 触发熔断，禁止新开仓
3. 仓位集中度：单只标的不超过总资金30%
4. 总敞口上限：不超过总资金80%
5. 风险收益比：低于1:2的交易直接否决
6. 最大持仓数：同时不超过5个持仓
7. 连续亏损熔断：连续3笔亏损后暂停30分钟
8. 交易时段检查：非交易时段禁止下单（可配置）
"""
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class RiskConfig:
    """风控参数配置"""
    # 资金管理
    total_capital: float = 2000.0           # 总资金
    max_risk_per_trade_pct: float = 0.02    # 单笔最大风险比例 (2%)
    daily_loss_limit: float = 100.0         # 日亏损上限 (USD)
    
    # 仓位控制
    max_position_pct: float = 0.30          # 单只标的最大仓位比例 (30%)
    max_total_exposure_pct: float = 0.80    # 总敞口上限 (80%)
    max_open_positions: int = 5             # 最大同时持仓数
    
    # 交易质量
    min_risk_reward_ratio: float = 2.0      # 最低风险收益比
    min_signal_score: int = 20              # 最低信号评分（绝对值）
    
    # 熔断机制
    max_consecutive_losses: int = 3         # 连续亏损熔断阈值
    cooldown_minutes: int = 30              # 熔断冷却时间（分钟）
    
    # 交易时段（美东时间 9:30-16:00，此处用UTC偏移简化）
    trading_hours_enabled: bool = False     # 是否启用交易时段限制
    trading_start_hour: int = 9             # 开盘小时（本地时间）
    trading_start_minute: int = 30
    trading_end_hour: int = 16
    trading_end_minute: int = 0
    
    # 标的黑名单
    blacklist: List[str] = field(default_factory=list)
    
    # 极端行情保护
    volatility_spike_threshold: float = 3.0       # ATR倍数，超过视为波动率飙升
    flash_crash_pct: float = 0.05                 # 单根K线跌幅超过5%视为闪崩
    max_spread_pct: float = 0.02                  # 最大允许买卖价差 (2%)
    circuit_breaker_vix_level: float = 35.0       # VIX超过35暂停新开仓
    extreme_market_cooldown_minutes: int = 60      # 极端事件后冷却时间（分钟）


@dataclass
class RiskCheckResult:
    """风控检查结果"""
    approved: bool                          # 是否通过
    reason: str = ""                        # 拒绝原因
    warnings: List[str] = field(default_factory=list)  # 警告信息
    adjusted_quantity: Optional[float] = None  # 建议调整后的数量
    max_position_value: float = 0           # 允许的最大仓位价值
    max_loss: float = 0                     # 该笔交易最大亏损
    risk_score: int = 0                     # 风险评分 0-100
    market_condition: str = "normal"        # "normal", "elevated", "extreme", "halted"

    def __str__(self) -> str:
        status = "APPROVED" if self.approved else "REJECTED"
        lines = [f"[RiskCheck] {status}"]
        if not self.approved:
            lines.append(f"  Reason: {self.reason}")
        if self.warnings:
            for w in self.warnings:
                lines.append(f"  Warning: {w}")
        if self.adjusted_quantity is not None:
            lines.append(f"  Adjusted qty: {self.adjusted_quantity}")
        lines.append(f"  Max loss: ${self.max_loss:.2f}")
        lines.append(f"  Risk score: {self.risk_score}/100")
        return "\n".join(lines)


class RiskManager:
    """
    硬性风控引擎
    
    所有交易必须通过 check_trade() 审核，未通过则禁止执行。
    这是代码级别的强制拦截，不依赖AI的"自觉"。
    """

    def __init__(self, config: RiskConfig = None, journal=None):
        self.config = config or RiskConfig()
        self.journal = journal  # TradingJournal 实例
        
        # 运行时状态
        self._consecutive_losses: int = 0
        self._cooldown_until: Optional[datetime] = None
        self._today_pnl: float = 0.0
        self._today_trades: int = 0
        self._last_pnl_update: Optional[str] = None  # 日期字符串
        self._last_refresh_ts: Optional[datetime] = None
        
        # 极端行情状态
        self._extreme_events: List[dict] = []
        self._last_extreme_time: Optional[datetime] = None
        
        logger.info(f"[RiskManager] 初始化完成 | 资金=${self.config.total_capital} "
                     f"| 单笔风险{self.config.max_risk_per_trade_pct*100}% "
                     f"| 日亏损限额${self.config.daily_loss_limit}")

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
        
        # === 检查0: 黑名单 ===
        if symbol in self.config.blacklist:
            return RiskCheckResult(
                approved=False,
                reason=f"{symbol} 在黑名单中，禁止交易"
            )
        
        # === 检查1: 熔断状态 ===
        if self._is_in_cooldown():
            remaining = int((self._cooldown_until - datetime.now()).total_seconds()) // 60
            return RiskCheckResult(
                approved=False,
                reason=f"熔断冷却中，还需等待{remaining}分钟 "
                       f"(连续{self._consecutive_losses}笔亏损触发)"
            )
        
        # === 检查1.5: 极端行情冷却期 ===
        if self.is_in_extreme_cooldown():
            remaining = int((self._last_extreme_time + timedelta(
                minutes=self.config.extreme_market_cooldown_minutes
            ) - datetime.now()).total_seconds() // 60)
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

    def record_trade_result(self, pnl: float):
        """记录交易结果，更新连续亏损计数和日PnL"""
        self._today_pnl += pnl
        self._today_trades += 1
        
        if pnl <= 0:
            self._consecutive_losses += 1
            logger.warning(f"[RiskManager] 亏损${pnl:.2f}，连续亏损{self._consecutive_losses}笔")
            
            # 触发熔断
            if self._consecutive_losses >= self.config.max_consecutive_losses:
                self._cooldown_until = datetime.now() + timedelta(
                    minutes=self.config.cooldown_minutes
                )
                logger.warning(
                    f"[RiskManager] 熔断触发！连续{self._consecutive_losses}笔亏损，"
                    f"冷却{self.config.cooldown_minutes}分钟"
                )
        else:
            self._consecutive_losses = 0
        
        # 日亏损限额检查
        if self._today_pnl <= -self.config.daily_loss_limit:
            logger.warning(
                f"[RiskManager] 日亏损限额触发！今日PnL=${self._today_pnl:.2f}，"
                f"限额=-${self.config.daily_loss_limit:.2f}，今日停止交易"
            )

    def update_capital(self, new_capital: float):
        """更新总资金（用于动态调整风控参数）"""
        old = self.config.total_capital
        self.config.total_capital = new_capital
        logger.info(f"[RiskManager] 资金更新: ${old:.2f} -> ${new_capital:.2f}")

    def reset_daily(self):
        """每日重置（新交易日开始时调用）"""
        self._today_pnl = 0.0
        self._today_trades = 0
        self._consecutive_losses = 0
        self._cooldown_until = None
        self._last_pnl_update = datetime.now().strftime('%Y-%m-%d')
        self._last_refresh_ts = None
        logger.info("[RiskManager] 日重置完成（含连续亏损和熔断清零）")

    def force_clear_cooldown(self):
        """强制解除熔断（管理员操作）"""
        self._cooldown_until = None
        self._consecutive_losses = 0
        logger.warning("[RiskManager] 熔断已被强制解除")

    # ============ 极端行情检测 ============

    def check_extreme_market(
        self,
        symbol: str,
        current_atr: float = 0,
        avg_atr: float = 0,
        price_change_pct: float = 0,
        vix: float = 0,
        spread_pct: float = 0,
    ) -> Tuple[str, List[str]]:
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
        now = datetime.now()
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
        if datetime.now() >= cooldown_end:
            logger.info("[RiskManager] 极端行情冷却期结束，恢复交易")
            self._last_extreme_time = None
            return False
        return True

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
        max_risk = cap * self.config.max_risk_per_trade_pct
        max_position = cap * self.config.max_position_pct
        
        risk_per_share = abs(entry_price - stop_loss)
        if risk_per_share <= 0:
            return {"error": "止损价不能等于入场价"}
        
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

    def get_status(self) -> Dict:
        """获取风控系统状态"""
        self._refresh_today_pnl()
        remaining_daily = self.config.daily_loss_limit + self._today_pnl
        
        return {
            "capital": self.config.total_capital,
            "today_pnl": round(self._today_pnl, 2),
            "today_trades": self._today_trades,
            "daily_loss_limit": self.config.daily_loss_limit,
            "remaining_daily_budget": round(max(0, remaining_daily), 2),
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
        }

    def format_status(self) -> str:
        """格式化风控状态"""
        s = self.get_status()
        lines = [
            "风控系统状态",
            "",
            f"总资金: ${s['capital']:,.2f}",
            f"今日PnL: ${s['today_pnl']:+.2f} / 限额-${s['daily_loss_limit']:.0f}",
            f"今日剩余额度: ${s['remaining_daily_budget']:.2f}",
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
        ]
        
        if s['in_cooldown']:
            lines.append(f"!! 熔断中，解除时间: {s['cooldown_until']} !!")
        else:
            lines.append("熔断状态: 正常")
        
        # 极端行情状态
        lines.append("")
        if self.is_in_extreme_cooldown():
            remaining = int((self._last_extreme_time + timedelta(
                minutes=self.config.extreme_market_cooldown_minutes
            ) - datetime.now()).total_seconds() // 60)
            lines.append(f"!! 极端行情冷却中，剩余{remaining}分钟 !!")
        else:
            lines.append("极端行情保护: 正常")
        lines.append(f"极端事件记录: {len(self._extreme_events)}次")
        if self._extreme_events:
            last = self._extreme_events[-1]
            lines.append(f"最近事件: [{last['type']}] {last['time']}")
        
        return "\n".join(lines)

    # ============ 内部方法 ============

    def _is_in_cooldown(self) -> bool:
        """检查是否在熔断冷却中"""
        if self._cooldown_until is None:
            return False
        if datetime.now() >= self._cooldown_until:
            self._cooldown_until = None
            self._consecutive_losses = 0
            logger.info("[RiskManager] 熔断冷却结束，恢复交易")
            return False
        return True

    def _is_trading_hours(self) -> bool:
        """检查是否在交易时段"""
        now = datetime.now()
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
        now = datetime.now()
        today = now.strftime('%Y-%m-%d')
        
        # 检测新交易日 -> 自动重置
        if self._last_pnl_update and self._last_pnl_update != today:
            logger.info("[RiskManager] 检测到新交易日，自动重置")
            self.reset_daily()
            return
        
        # 每5分钟刷新一次（而非每天只刷新一次）
        if hasattr(self, '_last_refresh_ts') and self._last_refresh_ts:
            elapsed = (now - self._last_refresh_ts).total_seconds()
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


# 全局实例
risk_manager = RiskManager()
