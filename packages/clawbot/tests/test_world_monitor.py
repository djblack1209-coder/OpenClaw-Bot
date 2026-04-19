"""
WorldMonitor 全球情报模块 — 单元测试

覆盖: NewsFetcher / RiskScorer / FinanceRadar
"""
import asyncio
import time
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.monitoring.world_monitor import (
    CountryRisk,
    FinanceRadar,
    MarketQuote,
    NewsCategory,
    NewsFetcher,
    NewsItem,
    RSSFeed,
    RiskScorer,
    RiskSeverity,
    get_finance_radar,
    get_news_fetcher,
    get_risk_scorer,
)


# ============================================================
# NewsFetcher 测试
# ============================================================

class TestNewsFetcher:
    """新闻聚合器测试"""

    def test_default_feeds_exist(self):
        """默认 RSS 源列表应该非空"""
        fetcher = NewsFetcher()
        assert len(fetcher.feeds) > 0

    def test_default_feeds_cover_categories(self):
        """默认源应覆盖多个分类"""
        fetcher = NewsFetcher()
        categories = {f.category for f in fetcher.feeds}
        assert len(categories) >= 5

    def test_parse_rss_basic(self):
        """RSS 2.0 基础解析"""
        fetcher = NewsFetcher()
        xml = """<?xml version="1.0"?>
        <rss version="2.0">
          <channel>
            <item>
              <title>测试新闻标题</title>
              <link>https://example.com/news/1</link>
              <description>这是一条测试新闻的摘要</description>
              <pubDate>Mon, 01 Jan 2024 00:00:00 GMT</pubDate>
            </item>
            <item>
              <title>第二条新闻</title>
              <link>https://example.com/news/2</link>
            </item>
          </channel>
        </rss>"""
        feed = RSSFeed("Test", "https://test.com/rss", NewsCategory.GENERAL)
        items = fetcher._parse_rss(xml, feed)
        assert len(items) == 2
        assert items[0].title == "测试新闻标题"
        assert items[0].url == "https://example.com/news/1"
        assert items[0].source == "Test"
        assert items[0].category == NewsCategory.GENERAL

    def test_parse_rss_atom(self):
        """Atom 格式解析"""
        fetcher = NewsFetcher()
        xml = """<?xml version="1.0"?>
        <feed xmlns="http://www.w3.org/2005/Atom">
          <entry>
            <title>Atom 新闻</title>
            <link href="https://example.com/atom/1"/>
          </entry>
        </feed>"""
        feed = RSSFeed("Atom Test", "https://test.com/atom", NewsCategory.TECHNOLOGY)
        items = fetcher._parse_rss(xml, feed)
        assert len(items) == 1
        assert items[0].title == "Atom 新闻"

    def test_parse_rss_invalid_xml(self):
        """无效 XML 应返回空列表"""
        fetcher = NewsFetcher()
        feed = RSSFeed("Bad", "https://bad.com", NewsCategory.GENERAL)
        items = fetcher._parse_rss("这不是 XML", feed)
        assert items == []

    def test_parse_rss_empty_titles_skipped(self):
        """空标题的条目应被跳过"""
        fetcher = NewsFetcher()
        xml = """<?xml version="1.0"?>
        <rss version="2.0">
          <channel>
            <item><title></title><link>https://x.com</link></item>
            <item><title>有标题</title><link>https://y.com</link></item>
          </channel>
        </rss>"""
        feed = RSSFeed("Test", "https://t.com", NewsCategory.GENERAL)
        items = fetcher._parse_rss(xml, feed)
        assert len(items) == 1

    def test_max_items_per_feed(self):
        """应限制每个源的最大条目数"""
        fetcher = NewsFetcher(max_items_per_feed=2)
        xml = """<?xml version="1.0"?>
        <rss version="2.0">
          <channel>
            <item><title>A</title><link>https://a.com</link></item>
            <item><title>B</title><link>https://b.com</link></item>
            <item><title>C</title><link>https://c.com</link></item>
          </channel>
        </rss>"""
        feed = RSSFeed("Test", "https://t.com", NewsCategory.GENERAL)
        items = fetcher._parse_rss(xml, feed)
        assert len(items) == 2

    def test_news_item_fields(self):
        """NewsItem 数据类字段完整"""
        item = NewsItem(
            title="Test",
            url="https://test.com",
            source="TestSource",
            category=NewsCategory.FINANCE,
            published_at=datetime.now(timezone.utc),
            summary="Summary",
            threat_level="high",
        )
        assert item.title == "Test"
        assert item.threat_level == "high"
        assert item.sentiment == 0.0

    def test_rss_feed_defaults(self):
        """RSSFeed 默认值"""
        feed = RSSFeed("Name", "https://url", NewsCategory.GENERAL)
        assert feed.language == "zh"
        assert feed.priority == 1


# ============================================================
# RiskScorer 测试
# ============================================================

class TestRiskScorer:
    """国家风险指数测试"""

    def test_compute_all_returns_countries(self):
        """应返回所有国家的评分"""
        scorer = RiskScorer()
        risks = scorer.compute_all()
        assert len(risks) > 0
        assert len(risks) == 30  # COUNTRY_BASELINES 有 30 个国家

    def test_risk_sorted_descending(self):
        """结果应按风险分数降序排列"""
        scorer = RiskScorer()
        risks = scorer.compute_all()
        scores = [r.composite_score for r in risks]
        assert scores == sorted(scores, reverse=True)

    def test_risk_score_range(self):
        """所有评分应在 0-100 范围内"""
        scorer = RiskScorer()
        risks = scorer.compute_all()
        for r in risks:
            assert 0 <= r.composite_score <= 100
            assert 0 <= r.unrest_score <= 100
            assert 0 <= r.conflict_score <= 100
            assert 0 <= r.economic_score <= 100
            assert 0 <= r.cyber_score <= 100
            assert 0 <= r.climate_score <= 100

    def test_severity_mapping(self):
        """风险等级应正确映射到分数"""
        scorer = RiskScorer()
        risks = scorer.compute_all()
        for r in risks:
            if r.composite_score >= 85:
                assert r.severity == RiskSeverity.CRITICAL
            elif r.composite_score >= 70:
                assert r.severity == RiskSeverity.HIGH
            elif r.composite_score >= 50:
                assert r.severity == RiskSeverity.ELEVATED
            elif r.composite_score >= 30:
                assert r.severity == RiskSeverity.MODERATE
            else:
                assert r.severity == RiskSeverity.LOW

    def test_high_risk_countries(self):
        """已知高风险国家（如乌克兰、也门）评分应较高"""
        scorer = RiskScorer()
        risks = scorer.compute_all()
        risk_map = {r.country_code: r for r in risks}
        # 乌克兰基线 50，应该分数较高
        assert risk_map["UA"].composite_score > 20
        # 日本基线 4，应该分数较低
        assert risk_map["JP"].composite_score < 30

    def test_global_risk(self):
        """全球风险评分结构正确"""
        scorer = RiskScorer()
        result = scorer.get_global_risk()
        assert "global_score" in result
        assert "severity" in result
        assert "top_risks" in result
        assert len(result["top_risks"]) == 5
        assert result["severity"] in ["LOW", "MEDIUM", "HIGH"]

    def test_cache_works(self):
        """缓存应在 TTL 内返回相同结果"""
        scorer = RiskScorer()
        first = scorer.compute_all()
        second = scorer.compute_all()
        # 缓存内应返回相同数量和相同国家
        first_codes = {r.country_code for r in first}
        second_codes = {r.country_code for r in second}
        assert first_codes == second_codes
        # 同一个国家的分数应一致
        first_map = {r.country_code: r.composite_score for r in first}
        second_map = {r.country_code: r.composite_score for r in second}
        for code in first_codes:
            assert first_map[code] == second_map[code]

    def test_country_risk_dataclass(self):
        """CountryRisk 数据类字段完整"""
        risk = CountryRisk(
            country_code="US",
            country_name="美国",
            composite_score=15.5,
            severity=RiskSeverity.LOW,
        )
        assert risk.change_24h == 0.0
        assert risk.unrest_score == 0.0


# ============================================================
# FinanceRadar 测试
# ============================================================

class TestFinanceRadar:
    """金融雷达测试"""

    def test_quote_to_dict(self):
        """MarketQuote 转 dict 格式正确"""
        q = MarketQuote(
            symbol="AAPL",
            name="Apple",
            price=178.5,
            change_pct=1.23,
            volume=50_000_000,
            category="stock",
            exchange="NASDAQ",
        )
        d = FinanceRadar._quote_to_dict(q)
        assert d["symbol"] == "AAPL"
        assert d["price"] == 178.5
        assert d["change_pct"] == 1.23
        assert d["category"] == "stock"

    def test_market_quote_defaults(self):
        """MarketQuote 默认值"""
        q = MarketQuote(
            symbol="BTC",
            name="Bitcoin",
            price=65000,
            change_pct=2.5,
        )
        assert q.volume == 0
        assert q.market_cap == 0
        assert q.category == "stock"

    def test_singleton(self):
        """单例模式应返回相同实例"""
        r1 = get_finance_radar()
        r2 = get_finance_radar()
        assert r1 is r2

    def test_news_singleton(self):
        """新闻聚合器单例"""
        f1 = get_news_fetcher()
        f2 = get_news_fetcher()
        assert f1 is f2

    def test_risk_singleton(self):
        """风险评分器单例"""
        s1 = get_risk_scorer()
        s2 = get_risk_scorer()
        assert s1 is s2


# ============================================================
# NewsCategory 枚举测试
# ============================================================

class TestNewsCategory:
    """新闻分类枚举测试"""

    def test_all_categories_exist(self):
        """应有 15 个分类"""
        assert len(NewsCategory) == 15

    def test_category_values(self):
        """分类值应为小写字符串"""
        for cat in NewsCategory:
            assert cat.value == cat.value.lower()
            assert cat.value.isalpha()

    def test_finance_category(self):
        """金融分类可正常使用"""
        assert NewsCategory("finance") == NewsCategory.FINANCE
        assert NewsCategory.FINANCE.value == "finance"
