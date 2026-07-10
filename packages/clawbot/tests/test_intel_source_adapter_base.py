from __future__ import annotations

from src.intel.sources.base import IntelSourceResult
from src.intel.sources.congress_trading import SenateTransactionsAdapter


def test_source_result_carries_evidence_path():
    result = IntelSourceResult(
        source="senate_trading",
        worker="overseas",
        fetched_at="2026-07-06T00:00:00Z",
        items=[{"ticker": "BYND"}],
        raw_count=1,
        health_status="success",
        evidence_path="/tmp/evidence.json",
    )

    assert result.evidence_path.endswith("evidence.json")
    assert result.raw_count == 1


def test_senate_adapter_returns_source_result_from_payload():
    payload = b"""[
        {
            "transaction_date": "11/10/2020",
            "disclosure_date": "11/16/2020",
            "senator": "Ron L Wyden",
            "ticker": "BYND",
            "type": "Purchase",
            "amount": "$1,001 - $15,000"
        },
        {
            "transaction_date": "11/12/2020",
            "disclosure_date": "11/18/2020",
            "senator": "Jane Doe",
            "ticker": "AAPL",
            "type": "Sale",
            "amount": "$15,001 - $50,000"
        }
    ]"""

    adapter = SenateTransactionsAdapter(
        opener=lambda _request, timeout=20: _BytesResponse(payload),
        evidence_path="/tmp/senate-evidence.jsonl",
    )

    result = adapter.fetch(limit=1)

    assert result.source == "senate_trading"
    assert result.worker == "overseas"
    assert result.health_status == "success"
    assert result.raw_count == 1
    assert result.evidence_path.endswith("senate-evidence.jsonl")
    assert result.items == [
        {
            "source": "senate-stock-watcher-data",
            "transaction_date": "11/10/2020",
            "disclosure_date": "11/16/2020",
            "person": "Ron L Wyden",
            "owner": "",
            "ticker": "BYND",
            "asset_description": "",
            "asset_type": "",
            "transaction_type": "Purchase",
            "amount": "$1,001 - $15,000",
            "ptr_link": "",
        }
    ]


class _BytesResponse:
    def __init__(self, payload: bytes):
        self._payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self) -> bytes:
        return self._payload


def test_default_source_adapter_registry_includes_verified_senate_adapter():
    from src.intel.sources.registry import build_default_source_adapters

    adapters = build_default_source_adapters()

    assert "senate_trading" in adapters
    assert adapters["senate_trading"].source_name == "senate_trading"


def test_default_source_adapter_registry_includes_verified_akshare_adapter():
    from src.intel.sources.registry import build_default_source_adapters

    adapters = build_default_source_adapters()

    assert "akshare" in adapters
    assert adapters["akshare"].source_name == "akshare"


def test_default_source_adapter_registry_includes_verified_github_trending_adapter():
    from src.intel.sources.registry import build_default_source_adapters

    adapters = build_default_source_adapters()

    assert "github_trending" in adapters
    assert adapters["github_trending"].source_name == "github_trending"
    assert "github-trending-remote-verification-pending" not in adapters["github_trending"].evidence_path
    assert adapters["github_trending"].evidence_path.endswith(
        "20260707T190500Z-github-trending-oracle-sg-worker-parser-fixed.json"
    )


def test_default_source_adapter_registry_includes_ai_model_updates_adapter():
    from src.intel.sources.registry import build_default_source_adapters

    adapters = build_default_source_adapters()

    assert "ai_model_updates" in adapters
    assert adapters["ai_model_updates"].source_name == "ai_model_updates"
    assert "remote-verification-pending" not in adapters["ai_model_updates"].evidence_path
    assert adapters["ai_model_updates"].evidence_path.endswith(
        "20260707T193548Z-ai-model-updates-oracle-sg-worker-final.json"
    )


def test_default_source_adapter_registry_includes_institutional_13f_adapter():
    from src.intel.sources.registry import build_default_source_adapters

    adapters = build_default_source_adapters()

    assert "institutional_13f" in adapters
    assert adapters["institutional_13f"].source_name == "institutional_13f"


def test_default_source_adapter_registry_includes_weather_adapter():
    from src.intel.sources.registry import build_default_source_adapters

    adapters = build_default_source_adapters()

    assert "weather" in adapters
    assert adapters["weather"].source_name == "weather"
