from __future__ import annotations

import json

from src.intel.sources.base import IntelSourceResult
from src.intel.worker_contract import (
    IntelWorkerRequest,
    IntelWorkerResponse,
    build_worker_request,
)


def test_worker_request_routes_source_and_is_json_safe():
    request = build_worker_request("xiaohongshu", limit=5, request_id="req-1")

    assert request.source == "xiaohongshu"
    assert request.worker == "domestic"
    assert request.limit == 5
    assert request.request_id == "req-1"

    payload = request.to_json()
    decoded = json.loads(payload)
    assert decoded["worker"] == "domestic"
    assert "token" not in payload.lower()
    assert "cookie" not in payload.lower()
    assert "secret" not in payload.lower()


def test_worker_request_rejects_secret_like_metadata_keys():
    request = IntelWorkerRequest(
        request_id="req-2",
        source="weibo",
        worker="domestic",
        region_hint="cn",
        limit=10,
        created_at="2026-07-06T00:00:00+00:00",
        metadata={"cookie": "should-not-serialize"},
    )

    try:
        request.to_public_dict()
    except ValueError as exc:
        assert "secret-like metadata key" in str(exc)
    else:  # pragma: no cover - keeps failure message explicit
        raise AssertionError("secret-like metadata key was accepted")


def test_worker_response_wraps_source_result():
    source_result = IntelSourceResult(
        source="senate_trading",
        worker="overseas",
        fetched_at="2026-07-06T00:00:00+00:00",
        items=[{"ticker": "BYND"}],
        raw_count=1,
        health_status="success",
        evidence_path="data/intel_evidence/phaseb/sample.jsonl",
    )

    response = IntelWorkerResponse.from_source_result("req-3", source_result)

    assert response.request_id == "req-3"
    assert response.status == "success"
    assert response.evidence_path.endswith("sample.jsonl")
    assert response.to_public_dict()["raw_count"] == 1
