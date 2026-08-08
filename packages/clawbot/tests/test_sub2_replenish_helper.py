"""JIYU Sub2 本地补号助手的最小安全合同。"""

from __future__ import annotations

import asyncio
import json
import time
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from src.sub2_replenish.app import ORIGIN, SESSION_COOKIE, create_app
from src.sub2_replenish.core import InputFormatError, ReplenishJob, parse_seller_payload
from src.sub2_replenish.runner import _OTP_SELECTORS, ReplenishRunner
from src.sub2_replenish.sub2_client import (
    Sub2AdminClient,
    find_duplicate_account,
    group_rate_candidates,
    manual_openai_group_options,
    matching_plan_groups,
)

SELLER_LINE = "person@example.test----never-log-password----JBSWY3DPEHPK3PXP"


def test_parser_accepts_fixed_labeled_and_json_formats_and_public_state_is_redacted():
    payloads = (
        SELLER_LINE,
        "邮箱：person@example.test\n密码：never-log-password\n2FA 密钥：JBSWY3DPEHPK3PXP",
        '{"email":"person@example.test","password":"never-log-password","totp":"JBSWY3DPEHPK3PXP"}',
        '[{"email":"person@example.test","password":"never-log-password","secret":"JBSWY3DPEHPK3PXP"}]',
    )
    for payload in payloads:
        credential = parse_seller_payload(payload)[0]
        job = ReplenishJob(credential=credential)
        public = json.dumps(job.public(), ensure_ascii=False)

        assert job.credential.password == "never-log-password"
        assert job.credential.totp_secret == "JBSWY3DPEHPK3PXP"
        assert "p***@example.test" in public
        assert "person@example.test" not in public
        assert "never-log-password" not in public
        assert "JBSWY3DPEHPK3PXP" not in public


@pytest.mark.parametrize(
    "raw",
    [
        "bad-format",
        "not-an-email----password----JBSWY3DPEHPK3PXP",
        "person@example.test--------JBSWY3DPEHPK3PXP",
        "person@example.test----password----invalid!",
        SELLER_LINE + "\n" + SELLER_LINE,
    ],
)
def test_parser_rejects_invalid_or_duplicate_lines_without_echoing_secrets(raw):
    with pytest.raises(InputFormatError) as exc_info:
        parse_seller_payload(raw)
    message = str(exc_info.value)
    assert "never-log-password" not in message
    assert "JBSWY3DPEHPK3PXP" not in message


def test_plan_matching_and_duplicate_detection_respect_self_hosted_pool():
    groups = [
        {"id": 1, "name": "JIYU OpenAI Plus 自营号池", "platform": "openai", "status": "active"},
        {"id": 2, "name": "JIYU OpenAI Pro 自营号池", "platform": "openai", "status": "active"},
        {"id": 3, "name": "JIYU 渠道A · OpenAI Plus", "platform": "openai", "status": "active"},
    ]
    assert [group["id"] for group in matching_plan_groups(groups, "plus")] == [1]
    assert [group["id"] for group in matching_plan_groups(groups, "pro")] == [2]
    assert matching_plan_groups(groups, "team") == []
    assert [group["id"] for group in manual_openai_group_options(groups)] == [1, 2]
    assert group_rate_candidates([{"rate_multiplier": 0.08}, {"rate_multiplier": 0.08}]) == [0.08]
    assert group_rate_candidates([{"rate_multiplier": 0.08}, {"rate_multiplier": 0.1}]) == [0.08, 0.1]
    assert group_rate_candidates([]) == []

    accounts = [{"id": 9, "name": "person@example.test", "credentials": {}}]
    assert find_duplicate_account(accounts, {"email": "PERSON@example.test"})["id"] == 9


@pytest.mark.asyncio
async def test_account_creation_explicitly_inherits_template_rate(monkeypatch):
    client = Sub2AdminClient()
    request = AsyncMock(return_value={"id": 12})
    monkeypatch.setattr(client, "_request", request)

    await client.create_openai_oauth_account(
        {"access_token": "fake-access-token", "email": "person@example.test"},
        group_id=8,
        rate_multiplier=0.08,
        idempotency_key="job-1",
    )

    payload = request.await_args.kwargs["json_body"]
    assert payload["rate_multiplier"] == 0.08
    assert payload["group_ids"] == [8]
    assert payload["upstream_billing_probe_enabled"] is False


@pytest.mark.asyncio
async def test_start_immediately_reserves_single_batch_task(monkeypatch):
    runner = ReplenishRunner(dry_run=True)
    runner.replace_jobs([ReplenishJob(parse_seller_payload(SELLER_LINE)[0])])
    gate = asyncio.Event()
    runs = 0

    async def controlled_batch():
        nonlocal runs
        runs += 1
        await gate.wait()
        runner.running = False

    monkeypatch.setattr(runner, "_run_batch", controlled_batch)
    runner.start()
    first_task = runner._batch_task
    runner.start()

    assert runner.running is True
    assert runner._batch_task is first_task
    gate.set()
    await first_task
    assert runs == 1


def test_group_and_rate_actions_reserve_state_before_queueing():
    runner = ReplenishRunner(dry_run=True)
    job = ReplenishJob(parse_seller_payload(SELLER_LINE)[0])
    runner.replace_jobs([job])
    job.status = "group_required"
    job.group_options = [{"id": 8, "name": "JIYU OpenAI Plus 自营号池"}]

    runner.choose_group(job.id, 8)
    assert job.status == "group_selected"
    with pytest.raises(ValueError):
        runner.choose_group(job.id, 8)

    job.status = "rate_required"
    runner.choose_rate(job.id, 0.08)
    assert job.status == "rate_selected"
    with pytest.raises(ValueError):
        runner.choose_rate(job.id, 0.08)

    assert all("inputmode" not in selector for selector in _OTP_SELECTORS)
    assert all(
        any(term in selector.casefold() for term in ("one-time-code", "otp", "mfa", "verification code", "2fa"))
        for selector in _OTP_SELECTORS
    )


def test_dry_run_ui_requires_same_origin_session_and_never_persists_secrets(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    app = create_app(dry_run=True)
    with TestClient(app, base_url=ORIGIN) as client:
        root = client.get("/")
        assert root.status_code == 200
        csrf = app.state.csrf_token
        headers = {"Origin": ORIGIN, "X-JIYU-CSRF": csrf}
        parsed = client.post(
            "/api/parse",
            headers=headers,
            json={"raw": SELLER_LINE, "target_pool": "self_hosted"},
        )
        assert parsed.status_code == 200
        assert parsed.json()["target_pool"] == "self_hosted"
        response_text = parsed.text
        assert "never-log-password" not in response_text
        assert "JBSWY3DPEHPK3PXP" not in response_text
        assert "person@example.test" not in response_text

        started = client.post("/api/start", headers=headers, json={})
        assert started.status_code == 200
        assert started.json()["running"] is True
        deadline = time.monotonic() + 2
        completed = started.json()
        while completed["running"] and time.monotonic() < deadline:
            time.sleep(0.01)
            completed = client.get("/api/state").json()
        assert completed["jobs"][0]["status"] == "dry_run"
        assert completed["jobs"][0]["email"] == "p***@example.test"

        unauthenticated = TestClient(app, base_url=ORIGIN)
        denied = unauthenticated.post(
            "/api/parse",
            headers={"Origin": ORIGIN, "X-JIYU-CSRF": csrf},
            json={"raw": SELLER_LINE},
        )
        assert denied.status_code == 403
        assert SESSION_COOKIE not in denied.headers.get("set-cookie", "")

    files = [path for path in tmp_path.rglob("*") if path.is_file()]
    assert files == []
