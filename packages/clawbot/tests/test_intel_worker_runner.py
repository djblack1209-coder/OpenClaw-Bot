from __future__ import annotations

from src.intel.db.store import get_source_health
from src.intel.sources.base import IntelSourceResult
from src.intel.worker_contract import build_worker_request
from src.intel.worker_runner import execute_worker_request, execute_worker_request_json


class _SuccessfulAdapter:
    source_name = "senate_trading"

    def fetch(self, *, limit: int = 20) -> IntelSourceResult:
        return IntelSourceResult(
            source=self.source_name,
            worker="overseas",
            fetched_at="2026-07-06T23:20:00+00:00",
            items=[{"ticker": "BYND"}][:limit],
            raw_count=min(1, limit),
            health_status="success",
            evidence_path="data/intel_evidence/phaseb/senate.jsonl",
        )


class _FailingAdapter:
    source_name = "github_trending"

    def fetch(self, *, limit: int = 20) -> IntelSourceResult:
        raise RuntimeError("rate limited")


def test_execute_worker_request_returns_response_and_records_success(tmp_path):
    db_path = tmp_path / "intel.db"
    request = build_worker_request("senate_trading", limit=1, request_id="req-success")

    response = execute_worker_request(
        request,
        adapters={"senate_trading": _SuccessfulAdapter()},
        db_path=db_path,
    )

    assert response.request_id == "req-success"
    assert response.status == "success"
    assert response.items == [{"ticker": "BYND"}]
    assert response.evidence_path.endswith("senate.jsonl")
    assert get_source_health(db_path, "senate_trading")["failure_count"] == 0


def test_execute_worker_request_records_adapter_failure(tmp_path):
    db_path = tmp_path / "intel.db"
    request = build_worker_request("github_trending", limit=1, request_id="req-fail")

    response = execute_worker_request(
        request,
        adapters={"github_trending": _FailingAdapter()},
        db_path=db_path,
    )

    assert response.status == "failed"
    assert response.error == "rate limited"
    health = get_source_health(db_path, "github_trending")
    assert health["failure_count"] == 1
    assert health["last_failure_reason"] == "rate limited"


def test_execute_worker_request_rejects_unregistered_source(tmp_path):
    db_path = tmp_path / "intel.db"
    request = build_worker_request("unknown_feed", limit=1, request_id="req-unknown")

    response = execute_worker_request(request, adapters={}, db_path=db_path)

    assert response.status == "failed"
    assert response.error == "unsupported_source: unknown_feed"
    assert get_source_health(db_path, "unknown_feed")["failure_count"] == 1


def test_execute_worker_request_json_round_trip(tmp_path):
    db_path = tmp_path / "intel.db"
    request = build_worker_request("senate_trading", limit=1, request_id="req-json")

    response_json = execute_worker_request_json(
        request.to_json(),
        adapters={"senate_trading": _SuccessfulAdapter()},
        db_path=db_path,
    )

    assert '"request_id": "req-json"' in response_json
    assert '"status": "success"' in response_json
    assert get_source_health(db_path, "senate_trading")["failure_count"] == 0


class _NoisyAdapter:
    source_name = "akshare"

    def fetch(self, *, limit: int = 20) -> IntelSourceResult:
        print("progress noise that must not reach worker stdout")
        return IntelSourceResult(
            source=self.source_name,
            worker="domestic",
            fetched_at="2026-07-06T23:58:00+00:00",
            items=[{"code": "000021"}],
            raw_count=1,
            health_status="success",
            evidence_path="phaseb/akshare.jsonl",
        )


def test_execute_worker_request_json_suppresses_adapter_stdout(capsys):
    request = build_worker_request("akshare", limit=1, request_id="noisy")

    response_json = execute_worker_request_json(
        request.to_json(),
        adapters={"akshare": _NoisyAdapter()},
    )

    captured = capsys.readouterr()
    assert captured.out == ""
    assert "progress noise" not in response_json
