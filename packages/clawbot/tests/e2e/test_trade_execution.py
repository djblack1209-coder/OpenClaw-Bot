"""
交易执行路径 e2e 测试

覆盖完整链路: 用户中文输入 → NLP匹配 → 风控审核 → 券商下单 → 日志/监控

测试分三层:
1. TestTradeNLPMatch      — 中文自然语言匹配（买/卖）
2. TestTradeRiskGate      — 风控拦截与放行
3. TestTradePipelineExecution — 管道端到端执行
"""

import pytest
from unittest.mock import MagicMock, AsyncMock, patch

from src.bot.chinese_nlp_mixin import _match_chinese_command
from src.models import TradeProposal


# ============================================================================
# 1. 中文自然语言匹配
# ============================================================================


class TestTradeNLPMatch:
    """验证中文交易指令能被正确识别为 (action_type, arg) 元组"""

    def test_buy_command(self):
        """「买100股AAPL」应匹配为 buy 类型，参数含 AAPL 和 100"""
        result = _match_chinese_command("买100股AAPL")
        assert result is not None, "买入指令应被匹配"
        action_type, arg = result
        assert action_type == "buy", f"应为 buy 类型，实际: {action_type}"
        assert "AAPL" in arg, f"参数应包含 AAPL，实际: {arg}"
        assert "100" in arg, f"参数应包含数量 100，实际: {arg}"

    def test_sell_command(self):
        """「卖掉AAPL」应匹配为 sell 类型，参数含 AAPL"""
        result = _match_chinese_command("卖掉AAPL")
        assert result is not None, "卖出指令应被匹配"
        action_type, arg = result
        assert action_type == "sell", f"应为 sell 类型，实际: {action_type}"
        assert "AAPL" in arg, f"参数应包含 AAPL，实际: {arg}"


# ============================================================================
# 2. 风控拦截
# ============================================================================


class TestTradeRiskGate:
    """验证 RiskManager 的审批/拒绝逻辑"""

    def test_risk_rejects_oversized_position(self, risk_manager):
        """超大仓位（10000股 × $150 = $1,500,000）远超 $10k 资本 → 应被拒绝"""
        check = risk_manager.check_trade(
            symbol="AAPL",
            side="BUY",
            quantity=10000,
            entry_price=150.0,
            stop_loss=145.0,
            take_profit=162.0,
            signal_score=60,
            current_positions=[],
        )
        assert not check.approved, (
            f"10000股 × $150 = $1.5M 远超资本上限，应被拒绝。"
            f" reason={check.reason}"
        )

    def test_risk_approves_normal_trade(self, risk_manager, sample_proposal):
        """标准提案（5股 × $150 = $750）在 $10k 资本下应通过"""
        check = risk_manager.check_trade(
            symbol=sample_proposal.symbol,
            side=sample_proposal.action,
            quantity=sample_proposal.quantity,
            entry_price=sample_proposal.entry_price,
            stop_loss=sample_proposal.stop_loss,
            take_profit=sample_proposal.take_profit,
            signal_score=sample_proposal.signal_score,
            current_positions=[],
        )
        assert check.approved, (
            f"正常小仓位应通过风控。"
            f" reason={check.reason}"
        )


# ============================================================================
# 3. 管道端到端执行
# ============================================================================


class TestTradePipelineExecution:
    """验证 TradingPipeline.execute_proposal() 的完整流转"""

    @pytest.mark.asyncio
    async def test_full_buy_flow(
        self, pipeline, sample_proposal, mock_broker, mock_journal, mock_monitor
    ):
        """正常买入: 风控通过 → broker.buy 被调用 → journal 记录 → monitor 添加"""
        # broker.get_positions 返回空列表，避免被当作真实持仓列表
        mock_broker.get_positions.return_value = []

        result = await pipeline.execute_proposal(sample_proposal)

        # 管道应成功执行
        assert result["status"] in ("executed", "simulated"), (
            f"正常提案应执行成功，实际状态: {result['status']}，"
            f"原因: {result.get('reason', 'N/A')}"
        )

        # broker.buy 被调用
        mock_broker.buy.assert_called_once()
        call_kwargs = mock_broker.buy.call_args
        assert call_kwargs.kwargs["symbol"] == "AAPL", "下单标的应为 AAPL"

        # journal.open_trade 被调用（记录交易日志）
        mock_journal.open_trade.assert_called_once()

        # monitor.add_position 被调用（添加持仓监控）
        mock_monitor.add_position.assert_called_once()

    @pytest.mark.asyncio
    async def test_risk_rejection_stops_execution(
        self, pipeline, mock_broker
    ):
        """超大仓位被风控拒绝 → broker.buy 不应被调用"""
        # broker.get_positions 返回空列表
        mock_broker.get_positions.return_value = []

        oversized_proposal = TradeProposal(
            symbol="AAPL",
            action="BUY",
            quantity=10000,
            entry_price=150.0,
            stop_loss=145.0,
            take_profit=162.0,
            signal_score=60,
            confidence=0.7,
            reason="测试超大仓位",
            decided_by="TestBot",
        )

        result = await pipeline.execute_proposal(oversized_proposal)

        # 应被风控拒绝
        assert result["status"] == "rejected", (
            f"超大仓位应被拒绝，实际状态: {result['status']}"
        )

        # broker.buy 不应被调用
        mock_broker.buy.assert_not_called()
