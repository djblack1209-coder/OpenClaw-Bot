"""Local Intel Brief worker runner.

This module is the worker-side execution seam: it accepts a JSON-safe
IntelWorkerRequest, runs a registered source adapter, returns an
IntelWorkerResponse, and optionally records source_health in a SQLite DB. It does
not open SSH sessions, deploy services, read credentials, or schedule jobs.
"""

from __future__ import annotations

import contextlib
import io
import json
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path

from src.intel.db.store import record_source_health
from src.intel.sources.base import IntelSourceAdapter
from src.intel.worker_contract import IntelWorkerRequest, IntelWorkerResponse


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()  # noqa: UP017 - Python 3.10 worker compatibility


def _record_health_if_requested(
    db_path: str | Path | None,
    source_name: str,
    status: str,
    error: str = "",
) -> None:
    if db_path is None:
        return
    record_source_health(db_path, source_name, status, failure_reason=error)


def execute_worker_request(
    request: IntelWorkerRequest,
    *,
    adapters: Mapping[str, IntelSourceAdapter],
    db_path: str | Path | None = None,
) -> IntelWorkerResponse:
    """Execute one Intel Brief source request against a registered adapter."""
    adapter = adapters.get(request.source)
    if adapter is None:
        error = f"unsupported_source: {request.source}"
        _record_health_if_requested(db_path, request.source, "failed", error)
        return IntelWorkerResponse(
            request_id=request.request_id,
            source=request.source,
            worker=request.worker,
            fetched_at=_now_iso(),
            status="failed",
            raw_count=0,
            items=[],
            evidence_path="",
            error=error,
        )

    try:
        with contextlib.redirect_stdout(io.StringIO()):
            result = adapter.fetch(limit=request.limit)
    except Exception as exc:
        error = str(exc) or exc.__class__.__name__
        _record_health_if_requested(db_path, request.source, "failed", error)
        return IntelWorkerResponse(
            request_id=request.request_id,
            source=request.source,
            worker=request.worker,
            fetched_at=_now_iso(),
            status="failed",
            raw_count=0,
            items=[],
            evidence_path="",
            error=error,
        )

    response = IntelWorkerResponse.from_source_result(request.request_id, result)
    _record_health_if_requested(db_path, request.source, response.status, response.error)
    return response

def _request_from_public_dict(payload: dict[str, object]) -> IntelWorkerRequest:
    return IntelWorkerRequest(
        request_id=str(payload.get("request_id") or ""),
        source=str(payload.get("source") or ""),
        worker=str(payload.get("worker") or ""),
        region_hint=str(payload.get("region_hint") or ""),
        limit=int(payload.get("limit") or 20),
        created_at=str(payload.get("created_at") or _now_iso()),
        dispatch_mode=str(payload.get("dispatch_mode") or "remote_worker_contract"),
        metadata=dict(payload.get("metadata") or {}),
    )


def execute_worker_request_json(
    payload: str | bytes | dict[str, object],
    *,
    adapters: Mapping[str, IntelSourceAdapter],
    db_path: str | Path | None = None,
) -> str:
    """Execute a JSON-safe worker request and return a JSON-safe response."""
    data = json.loads(payload.decode("utf-8") if isinstance(payload, bytes) else payload) if isinstance(payload, str | bytes) else payload
    request = _request_from_public_dict(data)
    response = execute_worker_request(request, adapters=adapters, db_path=db_path)
    return response.to_json()
