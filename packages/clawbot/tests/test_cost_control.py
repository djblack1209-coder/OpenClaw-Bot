"""
Tests for src/core/cost_control.py — CostController.

Covers:
  - record_cost() — normal recording, accumulation
  - is_over_budget() — within / over budget
  - get_daily_spend() — today's cost retrieval
  - get_weekly_report() — weekly report structure
  - estimate_cost() — pricing calculation
  - suggest_model() — cost-aware model suggestion
  - Boundary: date rollover, negative cost, zero budget
"""
import json
import time
import pytest
from pathlib import Path
from unittest.mock import patch

from src.core.cost_control import CostController, MODEL_COSTS


# ── Fixtures ────────────────────────────────────────────


@pytest.fixture
def cc(tmp_path, monkeypatch):
    """CostController with $50 budget, daily log in tmp_path."""
    monkeypatch.setattr("src.core.cost_control.DAILY_LOG", tmp_path / "daily_costs.jsonl")
    monkeypatch.setattr("src.core.cost_control.COST_DIR", tmp_path)
    return CostController(daily_budget_usd=50.0)


@pytest.fixture
def cc_zero(tmp_path, monkeypatch):
    """CostController with $0 budget."""
    monkeypatch.setattr("src.core.cost_control.DAILY_LOG", tmp_path / "daily_costs.jsonl")
    monkeypatch.setattr("src.core.cost_control.COST_DIR", tmp_path)
    return CostController(daily_budget_usd=0.0)


# ── record_cost ─────────────────────────────────────────


class TestRecordCost:
    """record_cost() — normal recording and accumulation."""

    def test_single_record(self, cc):
        cc.record_cost("gpt-4o", 0.05, task_type="chat")
        assert cc.get_daily_spend() == pytest.approx(0.05)

    def test_accumulates_multiple_records(self, cc):
        cc.record_cost("gpt-4o", 0.05, "chat")
        cc.record_cost("claude-sonnet-4", 0.10, "analysis")
        cc.record_cost("gpt-4o-mini", 0.01, "chat")
        assert cc.get_daily_spend() == pytest.approx(0.16)

    def test_tracks_by_model(self, cc):
        cc.record_cost("gpt-4o", 0.05, "chat")
        cc.record_cost("gpt-4o", 0.03, "chat")
        cc.record_cost("claude-sonnet-4", 0.10, "analysis")
        stats = cc.get_stats()
        assert stats["by_model"]["gpt-4o"] == pytest.approx(0.08)
        assert stats["by_model"]["claude-sonnet-4"] == pytest.approx(0.10)

    def test_tracks_by_task(self, cc):
        cc.record_cost("gpt-4o", 0.05, "chat")
        cc.record_cost("gpt-4o", 0.03, "analysis")
        stats = cc.get_stats()
        assert stats["by_task"]["chat"] == pytest.approx(0.05)
        assert stats["by_task"]["analysis"] == pytest.approx(0.03)

    def test_persists_to_file(self, cc, tmp_path):
        cc.record_cost("gpt-4o", 0.05, "chat")
        log_file = tmp_path / "daily_costs.jsonl"
        assert log_file.exists()
        lines = log_file.read_text().strip().split("\n")
        assert len(lines) == 1
        record = json.loads(lines[0])
        assert record["model"] == "gpt-4o"
        assert record["cost_usd"] == 0.05
        assert record["task_type"] == "chat"


# ── is_over_budget / check_budget ───────────────────────


class TestBudgetCheck:
    """is_over_budget() — budget enforcement."""

    def test_within_budget(self, cc):
        cc.record_cost("gpt-4o", 10.0, "chat")
        assert cc.is_over_budget() is False

    def test_exactly_at_budget(self, cc):
        cc.record_cost("gpt-4o", 50.0, "chat")
        assert cc.is_over_budget() is True

    def test_over_budget(self, cc):
        cc.record_cost("gpt-4o", 60.0, "chat")
        assert cc.is_over_budget() is True

    def test_zero_budget_always_over(self, cc_zero):
        """Zero budget means any spend triggers over-budget."""
        cc_zero.record_cost("gpt-4o", 0.001, "chat")
        assert cc_zero.is_over_budget() is True

    def test_zero_budget_no_spend(self, cc_zero):
        """Zero budget with zero spend is exactly at budget."""
        assert cc_zero.is_over_budget() is True  # 0.0 >= 0.0


# ── get_daily_spend ─────────────────────────────────────


class TestGetDailySpend:
    """get_daily_spend() — today's cost statistic."""

    def test_initial_spend_zero(self, cc):
        assert cc.get_daily_spend() == 0.0

    def test_spend_after_records(self, cc):
        cc.record_cost("gpt-4o", 1.23, "chat")
        cc.record_cost("gpt-4o-mini", 0.77, "chat")
        assert cc.get_daily_spend() == pytest.approx(2.0)


# ── get_weekly_report ───────────────────────────────────


class TestGetWeeklyReport:
    """get_weekly_report() — weekly report generation."""

    def test_report_structure(self, cc):
        cc.record_cost("gpt-4o", 5.0, "chat")
        report = cc.get_weekly_report()
        assert "weekly_total_usd" in report
        assert "daily_budget_usd" in report
        assert "today_spend_usd" in report
        assert "by_model" in report
        assert "by_task" in report
        assert "daily_breakdown" in report

    def test_report_includes_today(self, cc):
        cc.record_cost("gpt-4o", 5.0, "chat")
        report = cc.get_weekly_report()
        assert report["weekly_total_usd"] == pytest.approx(5.0)
        assert report["today_spend_usd"] == pytest.approx(5.0)

    def test_report_empty_when_no_records(self, cc):
        report = cc.get_weekly_report()
        assert report["weekly_total_usd"] == 0.0
        assert report["today_spend_usd"] == 0.0


# ── estimate_cost ───────────────────────────────────────


class TestEstimateCost:
    """estimate_cost() — pricing calculation."""

    def test_known_model_pricing(self, cc):
        # gpt-4o: input=$2.5/M, output=$10.0/M
        cost = cc.estimate_cost("gpt-4o", 1_000_000, 1_000_000)
        assert cost == pytest.approx(12.5)

    def test_partial_token_pricing(self, cc):
        # gpt-4o: 1000 input + 500 output
        cost = cc.estimate_cost("gpt-4o", 1000, 500)
        expected = (1000 * 2.5 + 500 * 10.0) / 1_000_000
        assert cost == pytest.approx(expected)

    def test_unknown_model_returns_zero(self, cc):
        cost = cc.estimate_cost("unknown-model-xyz", 10000, 5000)
        assert cost == 0.0

    def test_free_model_returns_zero(self, cc):
        cost = cc.estimate_cost("qwen3-235b", 100000, 50000)
        assert cost == 0.0


# ── suggest_model ───────────────────────────────────────


class TestSuggestModel:
    """suggest_model() — cost-aware model recommendation."""

    def test_simple_task_uses_free_model(self, cc):
        model = cc.suggest_model("simple")
        assert model == "qwen3-235b"

    def test_critical_task_uses_premium(self, cc):
        model = cc.suggest_model("critical")
        assert model == "claude-opus-4"

    def test_near_budget_downgrades_to_free(self, cc):
        cc._today_spend = 46.0  # 92% of $50 budget
        model = cc.suggest_model("critical")
        assert model == "qwen3-235b"

    def test_moderate_budget_downgrades_critical(self, cc):
        cc._today_spend = 36.0  # 72% of $50 budget
        model = cc.suggest_model("critical")
        assert model == "claude-sonnet-4"  # downgraded from opus


# ── Boundary: date rollover ─────────────────────────────


class TestDateRollover:
    """Cross-day reset behavior."""

    def test_date_rollover_resets_spend(self, cc):
        cc.record_cost("gpt-4o", 10.0, "chat")
        assert cc.get_daily_spend() == pytest.approx(10.0)
        # Simulate date change
        cc._today_date = "1999-01-01"  # A date that's definitely not today
        cc._check_date_rollover()
        assert cc.get_daily_spend() == 0.0


# ── Boundary: negative cost ─────────────────────────────


class TestNegativeCost:
    """Negative cost input behavior."""

    def test_negative_cost_subtracts(self, cc):
        cc.record_cost("gpt-4o", 10.0, "chat")
        cc.record_cost("gpt-4o", -3.0, "refund")
        assert cc.get_daily_spend() == pytest.approx(7.0)


# ── get_stats ───────────────────────────────────────────


class TestGetStats:
    """get_stats() — structure and correctness."""

    def test_stats_structure(self, cc):
        stats = cc.get_stats()
        assert "today_spend" in stats
        assert "daily_budget" in stats
        assert "budget_used_pct" in stats
        assert "over_budget" in stats

    def test_stats_budget_pct(self, cc):
        cc.record_cost("gpt-4o", 25.0, "chat")
        stats = cc.get_stats()
        assert stats["budget_used_pct"] == pytest.approx(50.0)

    def test_stats_zero_budget_pct(self, cc_zero):
        stats = cc_zero.get_stats()
        assert stats["budget_used_pct"] == 0  # Division by zero handled
