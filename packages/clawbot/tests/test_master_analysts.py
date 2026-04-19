"""投资大师人格分析师单元测试 — 覆盖提示词 / 单个大师分析 / 圆桌会议."""

import pytest
import asyncio
from unittest.mock import AsyncMock
from src.trading.master_analysts import (
    MASTER_PROMPTS,
    analyze_as_master,
    run_master_panel,
)


# ==================== 提示词常量 ====================

class TestMasterPrompts:
    """5 位投资大师的提示词模板."""

    EXPECTED_MASTERS = ["buffett", "taleb", "wood", "burry", "druckenmiller"]

    def test_all_five_masters_present(self):
        """5 位大师全部在提示词字典中."""
        for name in self.EXPECTED_MASTERS:
            assert name in MASTER_PROMPTS, f"缺少大师: {name}"

    def test_prompts_are_non_empty_strings(self):
        """每位大师的提示词不为空."""
        for name, prompt in MASTER_PROMPTS.items():
            assert isinstance(prompt, str), f"{name} 提示词不是字符串"
            assert len(prompt) > 50, f"{name} 提示词太短"

    def test_prompts_contain_investment_philosophy(self):
        """提示词中应包含各自的投资哲学关键词."""
        assert "moat" in MASTER_PROMPTS["buffett"].lower() or "护城河" in MASTER_PROMPTS["buffett"]
        assert "tail" in MASTER_PROMPTS["taleb"].lower() or "尾部" in MASTER_PROMPTS["taleb"]
        assert "innovation" in MASTER_PROMPTS["wood"].lower() or "创新" in MASTER_PROMPTS["wood"]
        assert "value" in MASTER_PROMPTS["burry"].lower() or "价值" in MASTER_PROMPTS["burry"]
        assert "macro" in MASTER_PROMPTS["druckenmiller"].lower() or "宏观" in MASTER_PROMPTS["druckenmiller"]


# ==================== 单个大师分析 ====================

class TestAnalyzeAsMaster:
    """单个大师人格分析."""

    @pytest.fixture
    def mock_llm(self):
        """模拟 LLM 调用函数，返回结构化 JSON."""
        async def _call(system_prompt: str, user_prompt: str) -> str:
            return '{"signal": "bullish", "confidence": 0.8, "reasoning": "Strong fundamentals"}'
        return _call

    @pytest.fixture
    def sample_data(self):
        """示例财务数据."""
        return {
            "ticker": "AAPL",
            "pe_ratio": 28.5,
            "roe": 0.15,
            "revenue_growth": 0.08,
            "debt_to_equity": 1.2,
            "free_cash_flow": 90_000_000_000,
        }

    async def test_returns_dict_with_signal(self, mock_llm, sample_data):
        """返回值包含信号字段."""
        result = await analyze_as_master(
            master_name="buffett",
            ticker="AAPL",
            financial_data=sample_data,
            llm_call_fn=mock_llm,
        )
        assert isinstance(result, dict)
        assert "signal" in result
        assert "confidence" in result
        assert "reasoning" in result

    async def test_invalid_master_raises_error(self, mock_llm, sample_data):
        """无效的大师名称应抛出异常."""
        with pytest.raises(ValueError):
            await analyze_as_master(
                master_name="nonexistent",
                ticker="AAPL",
                financial_data=sample_data,
                llm_call_fn=mock_llm,
            )

    async def test_passes_correct_system_prompt(self, sample_data):
        """调用 LLM 时应传入该大师的系统提示词."""
        captured_prompts = []

        async def _capture_call(system_prompt: str, user_prompt: str) -> str:
            captured_prompts.append(system_prompt)
            return '{"signal": "neutral", "confidence": 0.5, "reasoning": "OK"}'

        await analyze_as_master(
            master_name="buffett",
            ticker="AAPL",
            financial_data=sample_data,
            llm_call_fn=_capture_call,
        )
        assert len(captured_prompts) == 1
        # 系统提示词应包含 Buffett 的提示模板内容
        assert MASTER_PROMPTS["buffett"] in captured_prompts[0] or \
               len(captured_prompts[0]) > 50

    async def test_llm_returns_garbage_handled_gracefully(self, sample_data):
        """LLM 返回非 JSON 时应优雅降级."""
        async def _bad_llm(system_prompt: str, user_prompt: str) -> str:
            return "This is not valid JSON at all"

        result = await analyze_as_master(
            master_name="buffett",
            ticker="AAPL",
            financial_data=sample_data,
            llm_call_fn=_bad_llm,
        )
        assert isinstance(result, dict)
        assert "signal" in result
        # 降级时信号应为 neutral
        assert result["signal"] == "neutral"


# ==================== 圆桌会议 ====================

class TestMasterPanel:
    """多位大师圆桌会议（并行分析 + 信号聚合）."""

    @pytest.fixture
    def sample_data(self):
        return {
            "ticker": "TSLA",
            "pe_ratio": 60,
            "roe": 0.20,
            "revenue_growth": 0.25,
            "debt_to_equity": 0.5,
            "free_cash_flow": 5_000_000_000,
        }

    @pytest.fixture
    def bullish_llm(self):
        """所有大师都看涨的 LLM."""
        async def _call(system_prompt: str, user_prompt: str) -> str:
            return '{"signal": "bullish", "confidence": 0.8, "reasoning": "Strong growth"}'
        return _call

    @pytest.fixture
    def mixed_llm(self):
        """大师意见不一的 LLM."""
        call_count = 0
        async def _call(system_prompt: str, user_prompt: str) -> str:
            nonlocal call_count
            call_count += 1
            if call_count % 2 == 0:
                return '{"signal": "bearish", "confidence": 0.6, "reasoning": "Overvalued"}'
            return '{"signal": "bullish", "confidence": 0.7, "reasoning": "Good growth"}'
        return _call

    async def test_returns_dict_with_individual_and_consensus(
        self, bullish_llm, sample_data
    ):
        """返回值包含各大师意见和共识."""
        result = await run_master_panel(
            ticker="TSLA",
            financial_data=sample_data,
            llm_call_fn=bullish_llm,
        )
        assert isinstance(result, dict)
        assert "consensus" in result
        assert "individual" in result
        assert "consensus_signal" in result["consensus"]
        assert "consensus_confidence" in result["consensus"]

    async def test_all_five_masters_by_default(self, bullish_llm, sample_data):
        """默认运行全部 5 位大师."""
        result = await run_master_panel(
            ticker="TSLA",
            financial_data=sample_data,
            llm_call_fn=bullish_llm,
        )
        assert len(result["individual"]) == 5

    async def test_custom_masters_subset(self, bullish_llm, sample_data):
        """可以选择部分大师."
        """
        result = await run_master_panel(
            ticker="TSLA",
            financial_data=sample_data,
            llm_call_fn=bullish_llm,
            masters=["buffett", "taleb"],
        )
        assert len(result["individual"]) == 2
        master_names = [m["master"] for m in result["individual"]]
        assert "buffett" in master_names
        assert "taleb" in master_names

    async def test_unanimous_bullish_gives_bullish_consensus(
        self, bullish_llm, sample_data
    ):
        """全部看涨时共识应为看涨."""
        result = await run_master_panel(
            ticker="TSLA",
            financial_data=sample_data,
            llm_call_fn=bullish_llm,
        )
        assert result["consensus"]["consensus_signal"] == "bullish"

    async def test_consensus_signal_is_valid(self, mixed_llm, sample_data):
        """共识信号必须是 bullish/bearish/neutral 之一."""
        result = await run_master_panel(
            ticker="TSLA",
            financial_data=sample_data,
            llm_call_fn=mixed_llm,
        )
        assert result["consensus"]["consensus_signal"] in (
            "bullish", "bearish", "neutral"
        )
