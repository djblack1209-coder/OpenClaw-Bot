"""
ClawBot AI 决策验证层 v2.0
在 AI 团队给出交易建议后、风控审核前，增加一层系统性验证
防止 AI 幻觉、逻辑错误、数据不一致等问题

验证规则：
1. 价格合理性检查：AI给出的入场价/止损/止盈是否与实时行情一致
2. 方向一致性检查：AI建议的方向是否与技术指标信号一致
3. 数量合理性检查：建议数量是否在预算范围内
4. 重复交易检查：是否已持有该标的（避免重复建仓）
5. 逻辑一致性检查：止损必须低于入场价(做多)，止盈必须高于入场价(做多)
6. 信号强度验证：AI声称的信号评分是否与实际技术分析匹配
7. 时效性检查：行情数据是否过期（超过5分钟视为过期）
8. 决策频率限制：防止AI短时间内对同一标的连续下单
9. 极端波动检查：标的日内波动超阈值时拒绝交易
10. 置信度衰减：AI置信度过低时降级为警告或拒绝
"""
import logging
import time
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple

from src.models import TradeProposal

logger = logging.getLogger(__name__)


@dataclass
class ValidationResult:
    """决策验证结果"""
    approved: bool                                      # 是否通过验证
    issues: List[str] = field(default_factory=list)     # 硬性问题（导致拒绝）
    warnings: List[str] = field(default_factory=list)   # 软性警告（仅提示）
    adjusted_proposal: Optional[TradeProposal] = None   # 调整后的提案（如有）
    validation_confidence: float = 1.0                  # 验证结论的置信度 (0-1)，issue越多越低

    def __str__(self) -> str:
        status = "VALIDATED" if self.approved else "REJECTED"
        lines = [f"[DecisionValidator] {status} (confidence={self.validation_confidence:.2f})"]
        if self.issues:
            for issue in self.issues:
                lines.append(f"  Issue: {issue}")
        if self.warnings:
            for w in self.warnings:
                lines.append(f"  Warning: {w}")
        if self.adjusted_proposal is not None:
            lines.append("  (proposal adjusted)")
        return "\n".join(lines)


class DecisionValidator:
    """
    AI 决策验证器

    在 AI 团队产出 TradeProposal 之后、RiskManager 审核之前运行。
    通过多维度交叉验证，拦截 AI 幻觉和逻辑错误。
    """

    def __init__(
        self,
        get_quote_func: Callable,
        portfolio=None,
        journal=None,
        price_tolerance_pct: float = 0.03,
        max_price_age_seconds: int = 180,
        min_decision_interval_seconds: int = 120,
        extreme_volatility_pct: float = 0.08,
        min_confidence_threshold: float = 0.3,
    ):
        """
        Args:
            get_quote_func: 异步函数，接收 symbol 返回行情 dict（至少含 price 字段）
            portfolio: 组合管理实例（需提供 get_positions() 方法）
            journal: 交易日志实例（预留，暂未使用）
            price_tolerance_pct: 入场价与实时价的最大允许偏差比例（默认 3%，收紧防滑点）
            max_price_age_seconds: 行情数据最大有效期（秒，默认 180 即 3 分钟，收紧时效）
            min_decision_interval_seconds: 同一标的最小决策间隔（秒，默认 120）
            extreme_volatility_pct: 极端波动阈值（默认 8%，日内涨跌超此值拒绝交易）
            min_confidence_threshold: AI 最低置信度阈值（默认 0.3）
        """
        self.get_quote = get_quote_func
        self.portfolio = portfolio
        self.journal = journal
        self.price_tolerance_pct = price_tolerance_pct
        self.max_price_age_seconds = max_price_age_seconds
        self.min_decision_interval_seconds = min_decision_interval_seconds
        self.extreme_volatility_pct = extreme_volatility_pct
        self.min_confidence_threshold = min_confidence_threshold

        # 决策频率追踪: symbol -> last_decision_timestamp
        self._recent_decisions: Dict[str, float] = {}

        logger.info(
            "[DecisionValidator] 初始化 | 价格容差=%.1f%% | 数据有效期=%ds | "
            "决策间隔=%ds | 波动阈值=%.1f%% | 最低置信度=%.1f",
            price_tolerance_pct * 100,
            max_price_age_seconds,
            min_decision_interval_seconds,
            extreme_volatility_pct * 100,
            min_confidence_threshold,
        )

    # ================================================================
    # 主入口
    # ================================================================

    async def validate(
        self,
        proposal: TradeProposal,
        pre_fetched_analysis: Optional[Dict] = None,
    ) -> ValidationResult:
        """
        对 TradeProposal 执行全部验证检查。

        任何一项检查产生 issue 即判定为不通过（approved=False）。
        warnings 仅作为提示，不影响通过与否。

        Args:
            proposal: 待验证的交易提案
            pre_fetched_analysis: 已获取的技术分析数据（避免重复调用 yfinance）
        """
        all_issues: List[str] = []
        all_warnings: List[str] = []

        logger.info(
            "[DecisionValidator] 开始验证: %s %s x%d @ $%.2f",
            proposal.action, proposal.symbol,
            proposal.quantity, proposal.entry_price,
        )

        # -- 获取实时行情 --
        quote_data: Optional[Dict] = None
        try:
            quote_data = await self.get_quote(proposal.symbol)
        except Exception as e:
            logger.error(
                "[DecisionValidator] 获取 %s 行情失败: %s", proposal.symbol, e
            )
            all_issues.append(f"无法获取 {proposal.symbol} 实时行情: {e}")

        # -- 获取实时技术分析（用于方向/信号验证）--
        # P1#18: 优先使用调用方已获取的分析数据，避免重复调用 yfinance
        live_analysis: Optional[Dict] = None
        if pre_fetched_analysis and isinstance(pre_fetched_analysis, dict) and "error" not in pre_fetched_analysis:
            live_analysis = pre_fetched_analysis
            logger.debug("[DecisionValidator] 使用预获取的技术分析数据")
        else:
            try:
                from src.ta_engine import get_full_analysis
                live_analysis = await get_full_analysis(proposal.symbol)
                if isinstance(live_analysis, dict) and "error" in live_analysis:
                    logger.warning(
                        "[DecisionValidator] %s 技术分析失败: %s",
                        proposal.symbol, live_analysis["error"],
                    )
                    live_analysis = None
            except Exception as e:
                logger.warning("[DecisionValidator] 技术分析获取异常: %s", e)

        # -- 逐项检查 --
        checks = [
            ("price_sanity", self._check_price_sanity, (proposal, quote_data), True),
            ("direction_consistency", self._check_direction_consistency, (proposal, live_analysis), False),
            ("quantity_budget", self._check_quantity_budget, (proposal,), False),
            ("duplicate_position", self._check_duplicate_position, (proposal,), False),
            ("logical_consistency", self._check_logical_consistency, (proposal,), False),
            ("signal_strength", self._check_signal_strength, (proposal, live_analysis), False),
            ("data_freshness", self._check_data_freshness, (quote_data,), False),
            ("decision_frequency", self._check_decision_frequency, (proposal,), False),
            ("extreme_volatility", self._check_extreme_volatility, (proposal, quote_data), False),
            ("confidence_level", self._check_confidence_level, (proposal,), False),
        ]

        for name, check_func, args, is_async in checks:
            try:
                if is_async:
                    issues, warnings = await check_func(*args)
                else:
                    issues, warnings = check_func(*args)

                if issues:
                    logger.warning(
                        "[DecisionValidator] %s 发现问题: %s", name, issues
                    )
                all_issues.extend(issues)
                all_warnings.extend(warnings)
            except Exception as e:
                logger.error(
                    "[DecisionValidator] %s 检查异常: %s", name, e, exc_info=True
                )
                all_warnings.append(f"{name} 检查异常: {e}")

        approved = len(all_issues) == 0

        # 通过验证时记录决策时间戳（用于频率限制）
        if approved and proposal.action in ("BUY", "SELL"):
            self._recent_decisions[proposal.symbol.upper()] = time.time()

        # 根据问题和警告数量计算验证置信度
        validation_confidence = max(0.0, 1.0 - len(all_issues) * 0.2 - len(all_warnings) * 0.05)

        result = ValidationResult(
            approved=approved,
            issues=all_issues,
            warnings=all_warnings,
            adjusted_proposal=None,
            validation_confidence=validation_confidence,
        )

        log_fn = logger.info if approved else logger.warning
        log_fn(
            "[DecisionValidator] %s %s x%d -> %s | issues=%d warnings=%d",
            proposal.action, proposal.symbol, proposal.quantity,
            "PASS" if approved else "REJECT",
            len(all_issues), len(all_warnings),
        )

        return result

    # ================================================================
    # 检查 1: 价格合理性
    # ================================================================

    async def _check_price_sanity(
        self, proposal: TradeProposal, quote_data: Optional[Dict]
    ) -> Tuple[List[str], List[str]]:
        """
        验证 AI 给出的入场价是否与实时行情一致。
        偏差超过 price_tolerance_pct 视为问题。
        """
        issues: List[str] = []
        warnings: List[str] = []

        if quote_data is None or not isinstance(quote_data, dict):
            # 无行情时无法校验，已在 validate() 中记录 issue
            return issues, warnings

        live_price = quote_data.get("price", 0)
        if live_price <= 0:
            issues.append(f"实时价格异常: ${live_price}")
            return issues, warnings

        entry = proposal.entry_price
        if entry <= 0:
            warnings.append("入场价为 0，将由后续流程自动填充")
            return issues, warnings

        deviation = abs(entry - live_price) / live_price
        if deviation > self.price_tolerance_pct:
            issues.append(
                f"入场价 ${entry:.2f} 与实时价 ${live_price:.2f} 偏差 "
                f"{deviation:.1%}，超过容差 {self.price_tolerance_pct:.1%}"
            )
        elif deviation > self.price_tolerance_pct * 0.5:
            warnings.append(
                f"入场价 ${entry:.2f} 与实时价 ${live_price:.2f} 偏差 "
                f"{deviation:.1%}，接近容差上限"
            )

        # 止损价合理性（不应偏离实时价太远）
        if proposal.stop_loss > 0 and proposal.action == "BUY":
            sl_deviation = (live_price - proposal.stop_loss) / live_price
            if sl_deviation > 0.15:
                warnings.append(
                    f"止损价 ${proposal.stop_loss:.2f} 距实时价 ${live_price:.2f} "
                    f"偏离 {sl_deviation:.1%}，幅度偏大"
                )
            elif sl_deviation < 0:
                issues.append(
                    f"止损价 ${proposal.stop_loss:.2f} 高于实时价 ${live_price:.2f}，"
                    f"做多止损不合理"
                )

        # 止盈价合理性
        if proposal.take_profit > 0 and proposal.action == "BUY":
            tp_deviation = (proposal.take_profit - live_price) / live_price
            if tp_deviation > 0.30:
                warnings.append(
                    f"止盈价 ${proposal.take_profit:.2f} 距实时价 ${live_price:.2f} "
                    f"偏离 {tp_deviation:.1%}，目标可能过于乐观"
                )
            elif tp_deviation < 0:
                issues.append(
                    f"止盈价 ${proposal.take_profit:.2f} 低于实时价 ${live_price:.2f}，"
                    f"做多止盈不合理"
                )

        return issues, warnings

    # ================================================================
    # 检查 2: 方向一致性
    # ================================================================

    def _check_direction_consistency(
        self, proposal: TradeProposal, live_analysis: Optional[Dict]
    ) -> Tuple[List[str], List[str]]:
        """
        验证 AI 建议的方向是否与技术指标信号一致。
        严重矛盾（如强烈卖出信号却建议买入）视为 issue。
        """
        issues: List[str] = []
        warnings: List[str] = []

        if live_analysis is None:
            warnings.append("无法获取实时技术分析，跳过方向一致性检查")
            return issues, warnings

        signal_data = live_analysis.get("signal", {})
        ta_signal = signal_data.get("signal", "NEUTRAL")
        ta_score = signal_data.get("score", 0)

        action = proposal.action.upper()

        if action == "BUY":
            # 买入时，技术面给出强烈卖出信号 -> 严重矛盾
            if ta_signal == "STRONG_SELL" and ta_score <= -60:
                issues.append(
                    f"AI 建议买入，但技术分析为 {ta_signal}（评分 {ta_score}），"
                    f"方向严重矛盾"
                )
            elif ta_signal == "SELL" and ta_score <= -30:
                warnings.append(
                    f"AI 建议买入，但技术分析偏空 {ta_signal}（评分 {ta_score}），"
                    f"方向不一致，请谨慎"
                )
        elif action == "SELL":
            # 卖出时，技术面给出强烈买入信号 -> 严重矛盾
            if ta_signal == "STRONG_BUY" and ta_score >= 60:
                issues.append(
                    f"AI 建议卖出，但技术分析为 {ta_signal}（评分 {ta_score}），"
                    f"方向严重矛盾"
                )
            elif ta_signal == "BUY" and ta_score >= 30:
                warnings.append(
                    f"AI 建议卖出，但技术分析偏多 {ta_signal}（评分 {ta_score}），"
                    f"方向不一致，请谨慎"
                )

        return issues, warnings

    # ================================================================
    # 检查 3: 数量预算
    # ================================================================

    def _check_quantity_budget(
        self, proposal: TradeProposal
    ) -> Tuple[List[str], List[str]]:
        """
        验证建议数量是否在合理预算范围内。
        - 数量必须为正整数
        - 总成本不应超过合理上限
        """
        issues: List[str] = []
        warnings: List[str] = []

        if proposal.action in ("HOLD", "WAIT"):
            return issues, warnings

        if proposal.quantity <= 0:
            issues.append(f"交易数量 {proposal.quantity} 无效，必须为正整数")
            return issues, warnings

        if proposal.entry_price <= 0:
            # 入场价尚未确定，无法校验总成本
            return issues, warnings

        total_cost = proposal.quantity * proposal.entry_price

        # 单笔成本超过 $50,000 视为异常（防止 AI 幻觉产生天量订单）
        if total_cost > 50_000:
            issues.append(
                f"单笔总成本 ${total_cost:,.2f}"
                f"（{proposal.quantity} x ${proposal.entry_price:.2f}）"
                f"异常偏高，疑似 AI 幻觉"
            )
        elif total_cost > 10_000:
            warnings.append(
                f"单笔总成本 ${total_cost:,.2f}，金额较大，请确认资金充足"
            )

        # 数量异常大（超过 10000 股）
        if proposal.quantity > 10_000:
            issues.append(
                f"交易数量 {proposal.quantity} 异常偏大，疑似 AI 幻觉"
            )

        return issues, warnings

    # ================================================================
    # 检查 4: 重复持仓
    # ================================================================

    def _check_duplicate_position(
        self, proposal: TradeProposal
    ) -> Tuple[List[str], List[str]]:
        """
        检查是否已持有该标的，避免重复建仓。
        """
        issues: List[str] = []
        warnings: List[str] = []

        if proposal.action != "BUY":
            return issues, warnings

        if self.portfolio is None:
            warnings.append("无组合实例，跳过重复持仓检查")
            return issues, warnings

        try:
            positions = self.portfolio.get_positions()
        except Exception as e:
            warnings.append(f"获取持仓列表失败: {e}")
            return issues, warnings

        symbol = proposal.symbol.upper()
        for pos in positions:
            pos_symbol = pos.get("symbol", "").upper()
            pos_status = pos.get("status", "open")
            pos_qty = pos.get("quantity", 0)

            if pos_symbol == symbol and pos_status == "open" and pos_qty > 0:
                warnings.append(
                    f"已持有 {symbol} x{pos_qty}，本次为加仓操作，请确认意图"
                )
                break

        return issues, warnings

    # ================================================================
    # 检查 5: 逻辑一致性
    # ================================================================

    def _check_logical_consistency(
        self, proposal: TradeProposal
    ) -> Tuple[List[str], List[str]]:
        """
        验证止损/入场/止盈的逻辑关系：
        - BUY:  stop_loss < entry_price < take_profit
        - SELL: stop_loss > entry_price > take_profit
        """
        issues: List[str] = []
        warnings: List[str] = []

        action = proposal.action.upper()
        entry = proposal.entry_price
        sl = proposal.stop_loss
        tp = proposal.take_profit

        if action in ("HOLD", "WAIT"):
            return issues, warnings

        if entry <= 0:
            # 入场价尚未确定，跳过
            return issues, warnings

        if action == "BUY":
            if sl > 0 and sl >= entry:
                issues.append(
                    f"做多逻辑错误: 止损 ${sl:.2f} >= 入场价 ${entry:.2f}，"
                    f"止损必须低于入场价"
                )
            if tp > 0 and tp <= entry:
                issues.append(
                    f"做多逻辑错误: 止盈 ${tp:.2f} <= 入场价 ${entry:.2f}，"
                    f"止盈必须高于入场价"
                )
            if sl > 0 and tp > 0 and sl >= tp:
                issues.append(
                    f"逻辑错误: 止损 ${sl:.2f} >= 止盈 ${tp:.2f}"
                )

        elif action == "SELL":
            if sl > 0 and sl <= entry:
                issues.append(
                    f"做空逻辑错误: 止损 ${sl:.2f} <= 入场价 ${entry:.2f}，"
                    f"做空止损必须高于入场价"
                )
            if tp > 0 and tp >= entry:
                issues.append(
                    f"做空逻辑错误: 止盈 ${tp:.2f} >= 入场价 ${entry:.2f}，"
                    f"做空止盈必须低于入场价"
                )
            if sl > 0 and tp > 0 and sl <= tp:
                issues.append(
                    f"逻辑错误: 做空止损 ${sl:.2f} <= 止盈 ${tp:.2f}"
                )

        # 止损/止盈间距过小警告
        if action == "BUY" and sl > 0 and tp > 0 and entry > 0:
            risk = entry - sl
            reward = tp - entry
            if risk > 0 and reward > 0:
                spread_pct = (tp - sl) / entry
                if spread_pct < 0.02:
                    warnings.append(
                        f"止损止盈区间仅 {spread_pct:.1%}，空间过窄，"
                        f"可能频繁触发"
                    )

        return issues, warnings

    # ================================================================
    # 检查 6: 信号强度验证
    # ================================================================

    def _check_signal_strength(
        self, proposal: TradeProposal, live_analysis: Optional[Dict]
    ) -> Tuple[List[str], List[str]]:
        """
        验证 AI 声称的信号评分是否与实际技术分析匹配。
        偏差过大说明 AI 可能在"编造"信号。
        """
        issues: List[str] = []
        warnings: List[str] = []

        claimed_score = proposal.signal_score

        if live_analysis is None:
            if claimed_score != 0:
                warnings.append(
                    f"AI 声称信号评分 {claimed_score}，"
                    f"但无法获取实时技术分析进行验证"
                )
            return issues, warnings

        signal_data = live_analysis.get("signal", {})
        actual_score = signal_data.get("score", 0)

        if claimed_score == 0:
            # AI 未提供评分，不做校验
            return issues, warnings

        score_diff = abs(claimed_score - actual_score)

        # 偏差超过 40 分视为严重不一致
        if score_diff > 40:
            issues.append(
                f"AI 声称信号评分 {claimed_score}，"
                f"实际技术分析评分 {actual_score}，"
                f"偏差 {score_diff} 分，严重不一致（疑似 AI 幻觉）"
            )
        elif score_diff > 20:
            warnings.append(
                f"AI 声称信号评分 {claimed_score}，"
                f"实际技术分析评分 {actual_score}，"
                f"偏差 {score_diff} 分，存在一定差异"
            )

        # 方向矛盾：AI 给正分但实际为负（或反之）
        if claimed_score > 0 and actual_score < -20:
            warnings.append(
                f"AI 给出正向评分 {claimed_score}，"
                f"但实际技术面偏空 {actual_score}"
            )
        elif claimed_score < 0 and actual_score > 20:
            warnings.append(
                f"AI 给出负向评分 {claimed_score}，"
                f"但实际技术面偏多 {actual_score}"
            )

        return issues, warnings

    # ================================================================
    # 检查 7: 数据时效性
    # ================================================================

    def _check_data_freshness(
        self, quote_data: Optional[Dict]
    ) -> Tuple[List[str], List[str]]:
        """
        检查行情数据是否过期。
        quote_data 中应包含 timestamp 字段（Unix 秒）。
        超过 max_price_age_seconds 视为过期。
        """
        issues: List[str] = []
        warnings: List[str] = []

        if quote_data is None or not isinstance(quote_data, dict):
            # 无行情数据的 issue 已在 validate() 中记录
            return issues, warnings

        ts = (
            quote_data.get("timestamp")
            or quote_data.get("time")
            or quote_data.get("t")
        )
        if ts is None:
            warnings.append("行情数据缺少时间戳，无法验证时效性")
            return issues, warnings

        try:
            ts_float = float(ts)
        except (TypeError, ValueError) as e:  # noqa: F841
            warnings.append(f"行情时间戳格式异常: {ts}")
            return issues, warnings

        now = time.time()
        age_seconds = now - ts_float

        if age_seconds > self.max_price_age_seconds:
            age_minutes = age_seconds / 60
            issues.append(
                f"行情数据已过期: 数据时间距今 {age_minutes:.1f} 分钟，"
                f"超过有效期 {self.max_price_age_seconds / 60:.0f} 分钟"
            )
        elif age_seconds > self.max_price_age_seconds * 0.7:
            age_minutes = age_seconds / 60
            warnings.append(
                f"行情数据即将过期: 数据时间距今 {age_minutes:.1f} 分钟，"
                f"接近有效期上限"
            )
        elif age_seconds < 0:
            warnings.append(
                f"行情时间戳异常: 数据时间在未来 ({abs(age_seconds):.0f}s)"
            )

        return issues, warnings

    # ================================================================
    # 检查 8: 决策频率限制
    # ================================================================

    def _check_decision_frequency(
        self, proposal: TradeProposal
    ) -> Tuple[List[str], List[str]]:
        """
        防止 AI 短时间内对同一标的连续下单。
        同一标的在 min_decision_interval_seconds 内只允许一次决策。
        """
        issues: List[str] = []
        warnings: List[str] = []

        if proposal.action in ("HOLD", "WAIT"):
            return issues, warnings

        symbol = proposal.symbol.upper()
        now = time.time()

        # 清理过期记录（超过 1 小时的）
        expired = [s for s, t in self._recent_decisions.items() if now - t > 3600]
        for s in expired:
            del self._recent_decisions[s]

        last_time = self._recent_decisions.get(symbol)
        if last_time is not None:
            elapsed = now - last_time
            if elapsed < self.min_decision_interval_seconds:
                remaining = self.min_decision_interval_seconds - elapsed
                issues.append(
                    f"{symbol} 距上次决策仅 {elapsed:.0f}s，"
                    f"需等待 {remaining:.0f}s（最小间隔 {self.min_decision_interval_seconds}s）"
                )

        return issues, warnings

    # ================================================================
    # 检查 9: 极端波动检查
    # ================================================================

    def _check_extreme_volatility(
        self, proposal: TradeProposal, quote_data: Optional[Dict]
    ) -> Tuple[List[str], List[str]]:
        """
        标的日内波动超过阈值时拒绝交易。
        极端波动下价格不可预测，AI 的分析可能完全失效。
        """
        issues: List[str] = []
        warnings: List[str] = []

        if proposal.action in ("HOLD", "WAIT"):
            return issues, warnings

        if quote_data is None or not isinstance(quote_data, dict):
            return issues, warnings

        # 尝试从行情数据中获取日内涨跌幅
        change_pct = quote_data.get("change_pct", quote_data.get("changePct", None))

        if change_pct is None:
            # 尝试从 price 和 previousClose 计算
            price = quote_data.get("price", 0)
            prev_close = quote_data.get("previousClose", quote_data.get("prev_close", 0))
            if price > 0 and prev_close > 0:
                change_pct = (price - prev_close) / prev_close * 100
            else:
                return issues, warnings

        abs_change = abs(float(change_pct))
        threshold_pct = self.extreme_volatility_pct * 100  # 转为百分比

        if abs_change >= threshold_pct:
            direction = "暴涨" if change_pct > 0 else "暴跌"
            issues.append(
                f"{proposal.symbol} 日内{direction} {abs_change:.1f}%，"
                f"超过极端波动阈值 {threshold_pct:.0f}%，"
                f"拒绝交易（极端行情下 AI 分析不可靠）"
            )
        elif abs_change >= threshold_pct * 0.7:
            warnings.append(
                f"{proposal.symbol} 日内波动 {abs_change:.1f}%，"
                f"接近极端波动阈值 {threshold_pct:.0f}%，请谨慎"
            )

        return issues, warnings

    # ================================================================
    # 检查 10: 置信度验证
    # ================================================================

    def _check_confidence_level(
        self, proposal: TradeProposal
    ) -> Tuple[List[str], List[str]]:
        """
        验证 AI 的置信度是否达到最低阈值。
        置信度过低说明 AI 自身也不确定，不应执行交易。
        """
        issues: List[str] = []
        warnings: List[str] = []

        if proposal.action in ("HOLD", "WAIT"):
            return issues, warnings

        confidence = getattr(proposal, "confidence", None)
        if confidence is None or confidence == 0:
            warnings.append("AI 未提供置信度评分，无法验证决策确定性")
            return issues, warnings

        if confidence < self.min_confidence_threshold:
            issues.append(
                f"AI 置信度 {confidence:.2f} 低于最低阈值 "
                f"{self.min_confidence_threshold:.2f}，决策不够确定"
            )
        elif confidence < self.min_confidence_threshold * 1.5:
            warnings.append(
                f"AI 置信度 {confidence:.2f} 偏低，"
                f"建议减小仓位或观望"
            )

        return issues, warnings
