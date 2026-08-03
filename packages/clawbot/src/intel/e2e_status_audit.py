"""Redacted Intel Brief commercial MVP E2E status audit.

The audit is read-only: it inspects the production SQLite DB and evidence files
that were already produced by real runs.  It never sends Telegram messages,
modifies subscriptions, or runs remote workers.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.intel.db.store import initialize_intel_db

UNSUBSCRIBED_MARKERS_BY_CATEGORY = {
    "github_trending": ["GitHub", "github_trending"],
    "ai_model_updates": ["OpenAI", "Claude", "DeepSeek", "Deepseek", "AI模型动态"],
    "institutional_13f": ["机构13F", "Berkshire", "13F"],
    "weather": ["天气", "空气质量", "降雨", "湿度", "灾害预警"],
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()  # noqa: UP017 - Python 3.10 worker compatibility


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _load_json(path: str | Path) -> tuple[dict[str, Any] | None, str]:
    p = Path(path)
    if not p.exists():
        return None, "not_found"
    try:
        payload = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None, "invalid_json"
    return (payload, "ok") if isinstance(payload, dict) else (None, "not_object")


def _subscriber_rows(db_path: Path, *, now: str) -> list[dict[str, Any]]:
    initialize_intel_db(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT
                s.id AS subscriber_id,
                s.user_id,
                s.channel_type,
                s.channel_user_id,
                s.status AS subscriber_status,
                us.status AS subscription_status,
                us.starts_at,
                us.expires_at,
                sp.plan_name,
                dp.frequency,
                dp.delivery_time,
                dp.timezone
            FROM subscribers s
            LEFT JOIN user_subscriptions us ON us.subscriber_id=s.id AND us.status='active'
            LEFT JOIN subscription_plans sp ON sp.id=us.plan_id
            LEFT JOIN delivery_preferences dp ON dp.subscriber_id=s.id
            ORDER BY s.id
            """
        ).fetchall()
        prefs = {int(row[0]): [] for row in conn.execute("SELECT id FROM subscribers").fetchall()}
        for row in conn.execute(
            "SELECT subscriber_id, category FROM source_preferences WHERE enabled=1 ORDER BY category"
        ).fetchall():
            prefs.setdefault(int(row[0]), []).append(str(row[1]))
    subscribers: list[dict[str, Any]] = []
    for row in rows:
        expires_at = _clean(row["expires_at"])
        eligible = (
            _clean(row["subscriber_status"]) == "active"
            and _clean(row["subscription_status"]) == "active"
            and (not expires_at or expires_at > now)
        )
        subscribers.append(
            {
                "subscriber_id": int(row["subscriber_id"]),
                "user_id_present": bool(_clean(row["user_id"])),
                "channel_type": _clean(row["channel_type"]),
                "channel_user_id_present": bool(_clean(row["channel_user_id"])),
                "subscriber_status": _clean(row["subscriber_status"]),
                "subscription_status": _clean(row["subscription_status"]),
                "eligible": bool(eligible),
                "plan_name": _clean(row["plan_name"]),
                "starts_at": _clean(row["starts_at"]),
                "expires_at": expires_at,
                "enabled_categories": prefs.get(int(row["subscriber_id"]), []),
                "delivery_preferences": {
                    "frequency": _clean(row["frequency"]) or "daily",
                    "delivery_time": _clean(row["delivery_time"]) or "08:30",
                    "timezone": _clean(row["timezone"]) or "Asia/Singapore",
                },
            }
        )
    return subscribers


def _latest_delivery(db_path: Path, subscribers: list[dict[str, Any]]) -> dict[str, Any]:
    initialize_intel_db(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            """
            SELECT id, subscriber_id, delivered_at, content_summary, channel_type, success, error_message
            FROM delivery_log
            ORDER BY id DESC
            LIMIT 1
            """
        ).fetchone()
    if row is None:
        return {"exists": False}
    content = str(row["content_summary"] or "")
    subscriber = next((item for item in subscribers if int(item["subscriber_id"]) == int(row["subscriber_id"])), {})
    enabled = set(subscriber.get("enabled_categories") or [])
    unsubscribed_markers: list[str] = []
    for category, markers in UNSUBSCRIBED_MARKERS_BY_CATEGORY.items():
        if category in enabled:
            continue
        unsubscribed_markers.extend(marker for marker in markers if marker in content)
    return {
        "exists": True,
        "delivery_log_id": int(row["id"]),
        "subscriber_id": int(row["subscriber_id"]),
        "channel_type": _clean(row["channel_type"]),
        "success": bool(row["success"]),
        "delivered_at": _clean(row["delivered_at"]),
        "content_chars": len(content),
        "contains_sandbox_fake_copy": "sandbox fake Telegram sender" in content or "未调用真实 Bot API" in content,
        "contains_preference_filter_copy": "已按你的订阅偏好筛选" in content,
        "contains_public_info_disclaimer": "不构成投资建议" in content,
        "unsubscribed_marker_count": len(unsubscribed_markers),
        "unsubscribed_markers_present": sorted(set(unsubscribed_markers))[:20],
        "raw_content_written": False,
    }


def _readiness_summary(path: str | Path) -> dict[str, Any]:
    payload, state = _load_json(path)
    base: dict[str, Any] = {"path": str(path), "exists": state != "not_found", "state": state}
    if payload is None:
        return base
    return {
        **base,
        "status": _clean(payload.get("status")),
        "expected_sources": list(payload.get("expected_sources") or []),
        "missing": list(payload.get("missing") or []),
        "network_calls": int(payload.get("network_calls", 0) or 0),
    }


def _delivery_evidence_summary(path: str | Path) -> dict[str, Any]:
    payload, state = _load_json(path)
    base: dict[str, Any] = {"path": str(path), "exists": state != "not_found", "state": state}
    if payload is None:
        return base
    delivery = payload.get("delivery") if isinstance(payload.get("delivery"), dict) else {}
    return {
        **base,
        "status": _clean(payload.get("status")),
        "delivery_mode": _clean(payload.get("delivery_mode")),
        "summary": delivery.get("summary", {}) if isinstance(delivery, dict) else {},
        "network_calls": int(payload.get("network_calls", 0) or 0),
    }


def _launchagent_audit_summary(path: str | Path | None) -> dict[str, Any]:
    if path is None or not _clean(path):
        return {"path": "", "exists": False, "state": "not_provided"}
    payload, state = _load_json(path)
    base: dict[str, Any] = {"path": str(path), "exists": state != "not_found", "state": state}
    if payload is None:
        return base
    verification = payload.get("verification") if isinstance(payload.get("verification"), dict) else {}
    run_evidence = payload.get("run_evidence") if isinstance(payload.get("run_evidence"), dict) else {}
    return {
        **base,
        "status": _clean(payload.get("status")),
        "expected_sources_checked": bool(verification.get("expected_sources_checked")),
        "artifact_source_success": bool(verification.get("artifact_source_success")),
        "sources": list(run_evidence.get("sources") or []),
        "expected_sources": list(run_evidence.get("expected_sources") or []),
        "sources_match_expected": bool(run_evidence.get("sources_match_expected")),
        "collect_success_matches_expected": bool(run_evidence.get("collect_success_matches_expected")),
        "missing_expected_sources": list(run_evidence.get("missing_expected_sources") or []),
        "unexpected_sources": list(run_evidence.get("unexpected_sources") or []),
        "collect_summary": run_evidence.get("collect_summary", {}) if isinstance(run_evidence, dict) else {},
        "network_calls": int(payload.get("network_calls", 0) or 0),
    }


def build_intel_e2e_status_audit(
    *,
    db_path: str | Path,
    now: str,
    readiness_evidence_path: str | Path,
    latest_delivery_evidence_path: str | Path,
    launchagent_audit_evidence_path: str | Path | None = None,
) -> dict[str, Any]:
    """Build a read-only E2E status audit for current production state."""
    db = Path(db_path)
    subscribers = _subscriber_rows(db, now=now)
    latest_delivery = _latest_delivery(db, subscribers)
    active_eligible = [item for item in subscribers if item.get("eligible")]
    readiness = _readiness_summary(readiness_evidence_path)
    delivery_evidence = _delivery_evidence_summary(latest_delivery_evidence_path)
    launchagent_audit = _launchagent_audit_summary(launchagent_audit_evidence_path)
    natural_six_source_verified = (
        launchagent_audit.get("status") == "verified_success"
        and launchagent_audit.get("expected_sources_checked") is True
        and launchagent_audit.get("artifact_source_success") is True
        and launchagent_audit.get("sources_match_expected") is True
        and launchagent_audit.get("collect_success_matches_expected") is True
        and not launchagent_audit.get("missing_expected_sources")
    )
    checks = {
        "has_active_eligible_subscriber": bool(active_eligible),
        "subscriber_has_preferences": all(bool(item.get("enabled_categories")) for item in active_eligible),
        "latest_delivery_success": bool(latest_delivery.get("success")),
        "latest_delivery_user_facing_copy": latest_delivery.get("exists") is True
        and latest_delivery.get("contains_sandbox_fake_copy") is False
        and latest_delivery.get("contains_public_info_disclaimer") is True,
        "latest_delivery_filtered_to_preferences": latest_delivery.get("contains_preference_filter_copy") is True
        and int(latest_delivery.get("unsubscribed_marker_count", 0) or 0) == 0,
        "next_run_readiness_ready": readiness.get("status") == "ready" and not readiness.get("missing"),
        "latest_production_delivery_evidence_success": delivery_evidence.get("status") == "success"
        and delivery_evidence.get("delivery_mode") == "subscription_filtered",
        "natural_six_source_launchagent_verified": bool(natural_six_source_verified),
    }
    status = "verified" if all(checks.values()) else "needs_attention"
    return {
        "timestamp": _now_iso(),
        "phase": "BE-commercial-mvp-e2e-status-audit",
        "scope": "current_real_subscriber_preferences_delivery_and_next_run_readiness",
        "status": status,
        "now": now,
        "db_path": str(db),
        "summary": {
            "subscriber_count": len(subscribers),
            "active_eligible_subscriber_count": len(active_eligible),
            "delivery_log_latest_success": bool(latest_delivery.get("success")),
            "next_run_readiness_status": readiness.get("status"),
            "natural_launchagent_audit_status": launchagent_audit.get("status"),
        },
        "checks": checks,
        "subscribers": subscribers,
        "latest_delivery_log": latest_delivery,
        "readiness_evidence": readiness,
        "latest_delivery_evidence": delivery_evidence,
        "launchagent_audit_evidence": launchagent_audit,
        "network_calls": 0,
        "redaction": {
            "raw_telegram_token_written": False,
            "raw_chat_id_written": False,
            "raw_user_id_written": False,
            "raw_delivery_content_written": False,
        },
        "limits": [
            "Read-only audit; does not send Telegram messages or modify the DB.",
            "Uses latest delivery_log metadata and existing evidence files; raw chat ids and message text are not written.",
            "Verified status requires an existing natural 08:30 LaunchAgent post-run audit with expected six-source proof.",
        ],
    }
