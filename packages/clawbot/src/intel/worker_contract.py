"""JSON-safe controller/worker contract for Intel Brief source jobs."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from src.intel.runtime_policy import resolve_runtime_policy
from src.intel.sources.base import IntelSourceResult

_SECRET_KEY_PARTS = ("token", "secret", "cookie", "password", "key")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()  # noqa: UP017 - Python 3.10 worker compatibility


def _ensure_public_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    public: dict[str, Any] = {}
    for key, value in (metadata or {}).items():
        key_text = str(key)
        lowered = key_text.lower()
        if any(part in lowered for part in _SECRET_KEY_PARTS):
            raise ValueError(f"secret-like metadata key is not allowed: {key_text}")
        if isinstance(value, str | int | float | bool) or value is None:
            public[key_text] = value
        else:
            public[key_text] = str(value)
    return public


@dataclass(frozen=True)
class IntelWorkerRequest:
    """Controller-to-worker source fetch request.

    This object intentionally carries routing and execution intent only. Secret
    material such as cookies, tokens, private keys, and passwords must stay in the
    worker's local secret store and must not cross this JSON boundary.
    """

    request_id: str
    source: str
    worker: str
    region_hint: str
    limit: int = 20
    created_at: str = field(default_factory=_now_iso)
    dispatch_mode: str = "remote_worker_contract"
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "source": self.source,
            "worker": self.worker,
            "region_hint": self.region_hint,
            "limit": max(0, int(self.limit)),
            "created_at": self.created_at,
            "dispatch_mode": self.dispatch_mode,
            "metadata": _ensure_public_metadata(self.metadata),
        }

    def to_json(self) -> str:
        return json.dumps(self.to_public_dict(), ensure_ascii=False, sort_keys=True)


@dataclass(frozen=True)
class IntelWorkerResponse:
    """Worker-to-controller normalized fetch response."""

    request_id: str
    source: str
    worker: str
    fetched_at: str
    status: str
    raw_count: int
    items: list[dict[str, Any]]
    evidence_path: str
    error: str = ""

    @classmethod
    def from_source_result(cls, request_id: str, result: IntelSourceResult) -> IntelWorkerResponse:
        return cls(
            request_id=request_id,
            source=result.source,
            worker=result.worker,
            fetched_at=result.fetched_at,
            status=result.health_status,
            raw_count=result.raw_count,
            items=result.items,
            evidence_path=result.evidence_path,
        )

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "source": self.source,
            "worker": self.worker,
            "fetched_at": self.fetched_at,
            "status": self.status,
            "raw_count": int(self.raw_count),
            "items": self.items,
            "evidence_path": self.evidence_path,
            "error": self.error,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_public_dict(), ensure_ascii=False, sort_keys=True)


def build_worker_request(
    source_name: str,
    *,
    limit: int = 20,
    request_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> IntelWorkerRequest:
    """Build a JSON-safe source fetch request for the preferred worker."""
    policy = resolve_runtime_policy(source_name)
    return IntelWorkerRequest(
        request_id=request_id or f"intel-{uuid.uuid4().hex}",
        source=policy.source_name,
        worker=policy.preferred_worker,
        region_hint=policy.region_hint,
        limit=limit,
        metadata=dict(metadata or {}),
    )
