import json

import pytest

import src.execution_hub as execution_hub_module
from src.execution_hub import ExecutionHub


class TestExecutionHubPayoutWatch:
    @pytest.mark.asyncio
    async def test_check_payout_watches_emits_hire_and_payment_alerts_once(self, monkeypatch, tmp_path):
        monkeypatch.setattr(execution_hub_module, "DB_PATH", tmp_path / "execution_hub.db")
        monkeypatch.setenv("OPS_PAYOUT_WATCH_ISSUES", "Expensify/App#84427")

        hub = ExecutionHub()

        issue = {
            "title": "Workspace expense redirects to search",
            "html_url": "https://github.com/Expensify/App/issues/84427",
            "state": "open",
            "labels": [{"name": "External"}],
            "assignees": [],
            "updated_at": "2026-03-07T00:00:00Z",
        }
        comments = [
            {
                "id": 101,
                "body": "@djblack1209-coder implement this",
                "html_url": "https://github.com/Expensify/App/issues/84427#issuecomment-101",
                "user": {"login": "reviewer"},
            },
            {
                "id": 102,
                "body": "This issue is eligible for payment via Upwork.",
                "html_url": "https://github.com/Expensify/App/issues/84427#issuecomment-102",
                "user": {"login": "payment-bot"},
            },
        ]

        def fake_run_cmd(cmd, cwd, timeout=60, stdout_limit=3000, stderr_limit=3000):
            if cmd[:2] != ["gh", "api"]:
                return {"ok": False, "stdout": "", "stderr": "unexpected command"}
            if cmd[2] == "repos/Expensify/App/issues/84427":
                return {"ok": True, "stdout": json.dumps(issue), "stderr": ""}
            if cmd[2] == "repos/Expensify/App/issues/84427/comments?per_page=100":
                return {"ok": True, "stdout": json.dumps(comments), "stderr": ""}
            return {"ok": False, "stdout": "", "stderr": "unknown endpoint"}

        monkeypatch.setattr(hub, "_run_cmd", fake_run_cmd)

        first = await hub.check_payout_watches_once()
        second = await hub.check_payout_watches_once()

        assert [item["event_type"] for item in first] == ["hire", "payment"]
        assert second == []
        assert "准备提现" in hub.format_payout_alert(first[1])

    def test_attempt_upwork_offer_auto_accept_uses_browser_click_result(self, monkeypatch, tmp_path):
        monkeypatch.setattr(execution_hub_module, "DB_PATH", tmp_path / "execution_hub.db")
        monkeypatch.setenv("OPS_UPWORK_AUTO_ACCEPT_OFFER", "true")

        hub = ExecutionHub()

        monkeypatch.setattr(
            hub,
            "_run_cmd",
            lambda cmd, cwd, timeout=60: {"ok": True, "stdout": "", "stderr": ""},
        )
        monkeypatch.setattr(
            hub,
            "_chrome_execute_active_tab_js",
            lambda javascript: {
                "ok": True,
                "stdout": json.dumps(
                    {
                        "ok": True,
                        "status": "clicked",
                        "text": "accept offer",
                        "url": "https://www.upwork.com/ab/proposals/offers",
                        "title": "Offers",
                    }
                ),
                "stderr": "",
            },
        )

        result = hub._attempt_upwork_offer_auto_accept()

        assert result["success"] is True
        assert result["button"] == "accept offer"

    @pytest.mark.asyncio
    async def test_check_payout_watches_ignores_melvinbot_hire_prompt(self, monkeypatch, tmp_path):
        monkeypatch.setattr(execution_hub_module, "DB_PATH", tmp_path / "execution_hub.db")
        monkeypatch.setenv("OPS_PAYOUT_WATCH_ISSUES", "Expensify/App#84449")

        hub = ExecutionHub()

        issue = {
            "title": "Compose box issue",
            "html_url": "https://github.com/Expensify/App/issues/84449",
            "state": "open",
            "labels": [{"name": "External"}],
            "assignees": [],
            "updated_at": "2026-03-07T00:00:00Z",
        }
        comments = [
            {
                "id": 201,
                "body": "Reply with @MelvinBot implement this to create a draft PR",
                "html_url": "https://github.com/Expensify/App/issues/84449#issuecomment-201",
                "user": {"login": "MelvinBot"},
            }
        ]

        def fake_run_cmd(cmd, cwd, timeout=60, stdout_limit=3000, stderr_limit=3000):
            if cmd[:2] != ["gh", "api"]:
                return {"ok": False, "stdout": "", "stderr": "unexpected command"}
            if cmd[2] == "repos/Expensify/App/issues/84449":
                return {"ok": True, "stdout": json.dumps(issue), "stderr": ""}
            if cmd[2] == "repos/Expensify/App/issues/84449/comments?per_page=100":
                return {"ok": True, "stdout": json.dumps(comments), "stderr": ""}
            return {"ok": False, "stdout": "", "stderr": "unknown endpoint"}

        monkeypatch.setattr(hub, "_run_cmd", fake_run_cmd)

        alerts = await hub.check_payout_watches_once()

        assert alerts == []
