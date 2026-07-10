from __future__ import annotations

from src.execution.intel_brief import build_intel_brief_run_plan, dispatch_source_job


def test_dispatch_uses_runtime_policy_for_domestic_source():
    result = dispatch_source_job("weibo")

    assert result["source"] == "weibo"
    assert result["worker"] == "domestic"
    assert result["region_hint"] == "cn"
    assert result["status"] == "planned"


def test_dispatch_uses_runtime_policy_for_overseas_source():
    result = dispatch_source_job("sec_edgar")

    assert result["source"] == "sec_edgar"
    assert result["worker"] == "overseas"
    assert result["region_hint"] == "global"
    assert result["status"] == "planned"


def test_run_plan_groups_sources_without_remote_execution():
    plan = build_intel_brief_run_plan(["weibo", "akshare", "github_trending", "unknown_feed"])

    assert [job["source"] for job in plan["jobs"]] == [
        "weibo",
        "akshare",
        "github_trending",
        "unknown_feed",
    ]
    assert plan["dispatch_mode"] == "plan_only"
    assert plan["worker_counts"] == {"controller": 1, "domestic": 2, "overseas": 1}


def test_dispatch_includes_json_safe_worker_request():
    result = dispatch_source_job("senate_trading", limit=3, request_id="req-dispatch")

    assert result["worker"] == "overseas"
    assert result["worker_request"] == {
        "request_id": "req-dispatch",
        "source": "senate_trading",
        "worker": "overseas",
        "region_hint": "global",
        "limit": 3,
        "created_at": result["worker_request"]["created_at"],
        "dispatch_mode": "remote_worker_contract",
        "metadata": {},
    }
