import importlib.util
import json
import subprocess
import sys
from datetime import date
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT = REPO_ROOT / "scripts" / "check_renewals.py"
TEMPLATE = REPO_ROOT / "packages" / "clawbot" / "config" / "renewals.example.json"


def _load_module():
    spec = importlib.util.spec_from_file_location("openclaw_check_renewals", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _resource(resource_id: str, expires_on: str) -> dict:
    return {
        "id": resource_id,
        "name": resource_id,
        "purpose": "test",
        "provider": "unknown",
        "expires_on": expires_on,
        "auto_renew": "unknown",
        "estimated_cost": {"amount": "unknown", "currency": "unknown", "period": "unknown"},
        "action_url": "unknown",
        "notes": "",
    }


def _ledger(resources: list[dict]) -> dict:
    return {"version": 1, "reminder_days": [30, 14, 7, 3, 1], "resources": resources}


def test_tracked_renewal_template_is_safe_and_has_all_required_reminders() -> None:
    completed = subprocess.run(
        [sys.executable, str(SCRIPT), "--config", str(TEMPLATE), "--validate-template", "--json"],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
    report = json.loads(completed.stdout)
    assert report["status"] == "warning"
    assert report["reminder_days"] == [30, 14, 7, 3, 1]
    assert report["summary"]["unknown"] == report["summary"]["total"] >= 1
    assert report["safety"] == {
        "read_only": True,
        "payments_performed": False,
        "auto_renew_changed": False,
        "credentials_allowed": False,
    }


def test_renewal_statuses_are_deterministic_at_30_14_7_3_1_day_boundaries() -> None:
    renewals = _load_module()
    payload = _ledger(
        [
            _resource("expired", "2026-07-11"),
            _resource("today", "2026-07-12"),
            _resource("thirty", "2026-08-11"),
            _resource("fourteen", "2026-07-26"),
            _resource("seven", "2026-07-19"),
            _resource("three", "2026-07-15"),
            _resource("one", "2026-07-13"),
            _resource("later", "2026-08-12"),
            _resource("unknown", "unknown"),
        ]
    )

    report = renewals.evaluate_ledger(payload, today=date(2026, 7, 12))
    rows = {item["id"]: item for item in report["resources"]}

    assert report["status"] == "action_required"
    assert rows["expired"]["status"] == "expired"
    assert rows["today"]["status"] == "expires_today"
    for resource_id, threshold in (("thirty", 30), ("fourteen", 14), ("seven", 7), ("three", 3), ("one", 1)):
        assert rows[resource_id]["status"] == "due_soon"
        assert rows[resource_id]["reminder_threshold"] == threshold
    assert rows["later"]["status"] == "ok"
    assert rows["unknown"]["status"] == "unknown"


def test_renewal_ledger_rejects_duplicate_ids_and_sensitive_fields() -> None:
    renewals = _load_module()
    duplicate = _resource("same", "unknown")
    with pytest.raises(renewals.LedgerError, match="重复"):
        renewals.validate_ledger(_ledger([duplicate, dict(duplicate)]))

    unsafe = _ledger([_resource("unsafe", "unknown")])
    unsafe["resources"][0]["api_token"] = "must-not-be-here"
    with pytest.raises(renewals.LedgerError, match="敏感字段"):
        renewals.validate_ledger(unsafe)


def test_renewal_action_url_cannot_carry_credentials_or_query_tokens() -> None:
    renewals = _load_module()
    unsafe = _resource("unsafe-url", "unknown")
    unsafe["action_url"] = "https://user:password@example.com/billing?token=value"

    with pytest.raises(renewals.LedgerError, match="不得包含"):
        renewals.validate_ledger(_ledger([unsafe]))
