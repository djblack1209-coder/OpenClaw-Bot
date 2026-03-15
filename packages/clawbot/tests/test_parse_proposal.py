"""
Tests for parse_trade_proposal() - pure function, no mocking needed.
"""
import pytest

from src.auto_trader import parse_trade_proposal
from src.models import TradeProposal


class TestParseJSON:
    """JSON-based parsing."""

    def test_valid_json_buy(self):
        text = '''Here is my analysis: {"action": "BUY", "symbol": "AAPL", "quantity": 10, "entry_price": 150.0, "stop_loss": 145.0, "take_profit": 162.0, "reason": "breakout"}'''
        result = parse_trade_proposal(text, "AAPL")
        assert result is not None
        assert result.action == "BUY"
        assert result.symbol == "AAPL"
        assert result.quantity == 10
        assert result.entry_price == 150.0
        assert result.stop_loss == 145.0
        assert result.take_profit == 162.0

    def test_valid_json_hold(self):
        text = '{"action": "HOLD", "symbol": "TSLA", "reason": "too volatile"}'
        result = parse_trade_proposal(text, "TSLA")
        assert result.action == "HOLD"
        assert result.symbol == "TSLA"

    def test_json_with_missing_fields_uses_defaults(self):
        text = '{"action": "BUY", "symbol": "GOOG"}'
        result = parse_trade_proposal(text, "GOOG")
        assert result.action == "BUY"
        assert result.quantity == 0
        assert result.entry_price == 0

    def test_json_symbol_override(self):
        text = '{"action": "BUY", "symbol": "MSFT", "quantity": 5}'
        result = parse_trade_proposal(text, "AAPL")
        # JSON symbol takes precedence
        assert result.symbol == "MSFT"

    def test_json_no_symbol_uses_param(self):
        text = '{"action": "BUY", "quantity": 5}'
        result = parse_trade_proposal(text, "NVDA")
        assert result.symbol == "NVDA"


class TestParseKeywords:
    """Keyword-based fallback parsing."""

    def test_chinese_buy_keyword(self):
        text = "建议买入AAPL，入场价$150，止损$145，目标$162"
        result = parse_trade_proposal(text, "AAPL")
        assert result.action == "BUY"

    def test_chinese_sell_keyword(self):
        text = "建议卖出TSLA，当前价格过高"
        result = parse_trade_proposal(text, "TSLA")
        assert result.action == "SELL"

    def test_english_buy_keyword(self):
        text = "I recommend to buy AAPL at $150"
        result = parse_trade_proposal(text, "AAPL")
        assert result.action == "BUY"

    def test_hold_keyword(self):
        text = "建议观望，等待更好的入场时机"
        result = parse_trade_proposal(text, "AAPL")
        assert result.action == "HOLD"

    def test_long_keyword(self):
        text = "Go long on NVDA at current levels"
        result = parse_trade_proposal(text, "NVDA")
        assert result.action == "BUY"


class TestParsePriceExtraction:
    """Price extraction from text."""

    def test_three_prices_extracted(self):
        text = "Buy AAPL at $150.50, stop at $145.00, target $165.00"
        result = parse_trade_proposal(text, "AAPL")
        assert result.entry_price == 150.50
        assert result.stop_loss == 145.00
        assert result.take_profit == 165.00

    def test_single_price(self):
        text = "Buy at $150"
        result = parse_trade_proposal(text, "AAPL")
        assert result.entry_price == 150.0
        assert result.stop_loss == 0  # No second price

    def test_no_prices(self):
        text = "Buy AAPL now"
        result = parse_trade_proposal(text, "AAPL")
        assert result.entry_price == 0

    def test_symbol_uppercased(self):
        result = parse_trade_proposal("buy it", "aapl")
        assert result.symbol == "AAPL"


class TestParseEdgeCases:
    """Edge cases."""

    def test_empty_text(self):
        result = parse_trade_proposal("", "AAPL")
        assert result is not None
        assert result.action == "HOLD"

    def test_no_symbol(self):
        result = parse_trade_proposal("buy at $100", "")
        assert result.symbol == ""

    def test_reason_truncated(self):
        long_text = "Buy now! " * 100
        result = parse_trade_proposal(long_text, "AAPL")
        assert len(result.reason) <= 200

    def test_json_preferred_over_keywords(self):
        text = '卖出! {"action": "BUY", "symbol": "AAPL", "quantity": 5}'
        result = parse_trade_proposal(text, "AAPL")
        # JSON should win over keyword "卖出"
        assert result.action == "BUY"
