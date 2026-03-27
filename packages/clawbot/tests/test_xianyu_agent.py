"""Tests for Xianyu AI Agent — customer service logic.

Covers: ContentSafetyFilter (DFA + regex), _extract_price, BaseAgent temperature
        scaling, and safety filter integration.
"""
import pytest
from unittest.mock import patch, MagicMock, AsyncMock

from src.xianyu.xianyu_agent import ContentSafetyFilter, BaseAgent, _safe_filter
from src.xianyu.xianyu_live import _extract_price


# ============ Fixtures ============

@pytest.fixture
def csf():
    """Fresh ContentSafetyFilter instance."""
    return ContentSafetyFilter()


# ============ ContentSafetyFilter ============

class TestContentSafetyFilter:

    def test_blocks_contact_info(self, csf):
        """Messages with contact info (微信/QQ) are flagged as unsafe."""
        assert csf.is_safe("加我微信 abc123") is False
        assert csf.is_safe("我的QQ号是 12345678") is False

    def test_blocks_payment_bypass(self, csf):
        """Messages with payment bypass terms are flagged."""
        assert csf.is_safe("我们走支付宝转账吧") is False
        assert csf.is_safe("线下交易更方便") is False
        assert csf.is_safe("私下转账给你") is False

    def test_allows_normal_product_description(self, csf):
        """Normal product descriptions pass the filter."""
        assert csf.is_safe("这个商品质量很好，全新未拆封") is True
        assert csf.is_safe("原装正品，功能完好") is True

    def test_blocks_phone_number_regex(self, csf):
        """Phone number patterns are caught by regex."""
        violations = csf.get_violations("请打电话 13812345678 联系我")
        assert len(violations) > 0

    def test_blocks_url_regex(self, csf):
        """URL patterns are caught by regex."""
        violations = csf.get_violations("点击 https://example.com/pay 付款")
        assert len(violations) > 0

    def test_empty_text_is_safe(self, csf):
        """Empty string is considered safe."""
        assert csf.is_safe("") is True
        assert csf.get_violations("") == []


# ============ _extract_price ============

class TestExtractPrice:

    def test_extracts_yuan_suffix(self):
        """Extracts price from '100元' format."""
        assert _extract_price("100元可以吗") == 100.0

    def test_extracts_yen_sign(self):
        """Extracts price from '¥50' format."""
        assert _extract_price("¥50") == 50.0

    def test_extracts_fullwidth_yen(self):
        """Extracts price from '￥30' (fullwidth yen sign)."""
        assert _extract_price("￥30") == 30.0

    def test_returns_none_for_non_price_text(self):
        """Returns None when no price pattern is found."""
        assert _extract_price("这个商品怎么样") is None
        assert _extract_price("你好") is None

    def test_extracts_decimal_price(self):
        """Handles decimal prices like '15.5元'."""
        assert _extract_price("15.5元") == 15.5

    def test_extracts_bare_number(self):
        """A standalone number is treated as a price."""
        assert _extract_price("50") == 50.0

    def test_handles_zero(self):
        """'0元' is extracted as 0."""
        assert _extract_price("0元") == 0.0


# ============ BaseAgent temperature scaling ============

class TestBaseAgentTemperature:

    async def test_temperature_scales_with_bargain_count(self):
        """Temperature increases with bargain_count, capped at 0.9."""
        agent = BaseAgent(system_prompt="test prompt", model_family="qwen")

        captured_temps = []

        async def mock_acall(messages, system="", temperature=0.4):
            captured_temps.append(temperature)
            return "OK reply"

        agent._acall = mock_acall

        # bargain_count=0 → temp = 0.3 + 0*0.15 = 0.3
        await agent.agenerate("hi", "item desc", "ctx", bargain_count=0)
        assert captured_temps[-1] == pytest.approx(0.3)

        # bargain_count=2 → temp = 0.3 + 2*0.15 = 0.6
        await agent.agenerate("hi", "item desc", "ctx", bargain_count=2)
        assert captured_temps[-1] == pytest.approx(0.6)

        # bargain_count=10 → temp = min(0.3 + 10*0.15, 0.9) = 0.9
        await agent.agenerate("hi", "item desc", "ctx", bargain_count=10)
        assert captured_temps[-1] == pytest.approx(0.9)


# ============ _safe_filter integration ============

class TestSafeFilter:

    def test_safe_filter_passes_clean_text(self):
        """_safe_filter returns the original text if it's clean."""
        text = "这个商品很不错，全新的"
        assert _safe_filter(text) == text

    def test_safe_filter_blocks_violations(self):
        """_safe_filter returns safety reminder for violating text."""
        text = "加我微信号 abc123 交易"
        result = _safe_filter(text)
        assert "安全提醒" in result
        assert "微信" not in result  # Original violation should be replaced
