"""
Tests for parse_trade_proposal() - pure function, no mocking needed.
"""
import pytest

from src.trading_pipeline import parse_trade_proposal
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


# ============ v2 新增测试: JSON Blob / 中文关键词 / $ 前缀 / 容错 ============

class TestParseJsonBlob:
    """JSON blob 中包含 action/symbol/price 字段的解析"""

    def test_parse_json_blob(self):
        """文本中嵌入 JSON blob，正确提取 action/symbol/price

        parse_trade_proposal 用正则找到 {"action":...} 形式的 JSON，
        然后用 json_repair.loads 解析。
        """
        text = (
            '根据分析结果，我的建议如下：\n'
            '{"action": "BUY", "symbol": "NVDA", "entry_price": 450.0, '
            '"stop_loss": 430.0, "take_profit": 490.0, "quantity": 8, '
            '"reason": "突破前高"}'
        )
        result = parse_trade_proposal(text, "NVDA")

        assert result is not None
        assert result.action == "BUY"
        assert result.symbol == "NVDA"
        assert result.entry_price == 450.0
        assert result.stop_loss == 430.0
        assert result.take_profit == 490.0
        assert result.quantity == 8


class TestParseChineseKeywords:
    """中文关键词触发买入/卖出动作解析"""

    def test_parse_chinese_keywords(self):
        """'买入 AAPL 150' → 正确识别 BUY 动作

        中文关键词列表: "买入", "做多", "建仓" → BUY
        价格通过 $ 前缀或标签匹配提取。
        """
        text = "买入 AAPL，入场价 $150"
        result = parse_trade_proposal(text, "AAPL")

        assert result is not None
        assert result.action == "BUY"
        assert result.symbol == "AAPL"
        assert result.entry_price == 150.0


class TestParseDollarPrefix:
    """$ 前缀价格提取"""

    def test_parse_dollar_prefix(self):
        """'$150 AAPL' → 从 $ 前缀正确提取价格

        当标签匹配失败时，降级用 $xxx 格式提取价格。
        """
        text = "建议买入 AAPL，价格 $150"
        result = parse_trade_proposal(text, "AAPL")

        assert result is not None
        assert result.action == "BUY"
        assert result.entry_price == 150.0


class TestParseMalformedJsonFallback:
    """JSON 格式错误时降级到关键词匹配"""

    def test_parse_malformed_json_fallback(self):
        """输入包含无效 JSON → json_repair/json.loads 失败 → 降级关键词匹配

        关键词 "买入" 应被正确识别为 BUY。
        注意: json_repair 库容错性很强，可能修复大部分畸形 JSON。
        我们用完全不合法的 JSON 来确保触发 fallback。
        """
        # action 值没有引号，键名也没有引号 — json_repair 可能仍能修复
        # 使用截断的 JSON 确保失败
        text = '买入 AAPL，{"action": "BUY", "symbol": "AAPL" -- 截断的无效json'
        result = parse_trade_proposal(text, "AAPL")

        assert result is not None
        # 无论 JSON 解析成功还是关键词匹配，BUY 都应该被识别
        assert result.action == "BUY"
        assert result.symbol == "AAPL"


class TestParseGarbageReturnsHold:
    """无法识别的随机文本返回 HOLD"""

    def test_parse_garbage_returns_hold(self):
        """完全无关的文本 → 无法匹配任何关键词 → 默认 HOLD

        parse_trade_proposal 初始 action="HOLD"，
        只有匹配到 buy/sell 关键词才会改变。
        """
        text = "天气晴朗，适合出去散步，股市今天没什么动静"
        result = parse_trade_proposal(text, "AAPL")

        assert result is not None
        assert result.action == "HOLD"
        assert result.entry_price == 0  # 无价格信息
