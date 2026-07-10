from __future__ import annotations

import json
from pathlib import Path

from scripts.intel_collect_once import collect_once, default_worker_profiles
from scripts.intel_worker_remote_run import RemoteRunResult


def test_default_worker_profiles_route_verified_sources():
    profiles = default_worker_profiles()

    assert profiles["senate_trading"].worker_label == "oracle-sg-west-preferred-overseas"
    assert profiles["senate_trading"].ssh_target == "oracle-sg-west"
    assert "-o" in profiles["senate_trading"].ssh_args
    assert "ConnectTimeout=12" in profiles["senate_trading"].ssh_args
    assert profiles["senate_trading"].fallback_profiles[0].worker_label == "oracle-arm1-overseas-fallback"
    assert profiles["akshare"].worker_label == "yanhuoyun-domestic"
    assert "akshare==1.18.64" in profiles["akshare"].pip_packages
    assert profiles["github_trending"].worker_label == "oracle-sg-west-preferred-overseas"
    assert profiles["github_trending"].ssh_target == "oracle-sg-west"
    assert profiles["github_trending"].limit == 3
    assert profiles["github_trending"].fallback_profiles[0].source == "github_trending"
    assert profiles["ai_model_updates"].worker_label == "oracle-sg-west-preferred-overseas"
    assert profiles["ai_model_updates"].ssh_target == "oracle-sg-west"
    assert profiles["ai_model_updates"].limit == 6
    assert profiles["ai_model_updates"].fallback_profiles[0].source == "ai_model_updates"
    assert profiles["institutional_13f"].worker_label == "oracle-sg-west-preferred-overseas"
    assert profiles["institutional_13f"].ssh_target == "oracle-sg-west"
    assert profiles["institutional_13f"].limit == 10
    assert profiles["institutional_13f"].fallback_profiles[0].source == "institutional_13f"
    assert profiles["weather"].worker_label == "oracle-sg-west-preferred-overseas"
    assert profiles["weather"].ssh_target == "oracle-sg-west"
    assert profiles["weather"].limit == 6
    assert profiles["weather"].fallback_profiles[0].source == "weather"


def test_collect_once_aggregates_success_and_writes_evidence(tmp_path):
    calls: list[dict[str, object]] = []

    def fake_remote_run(**kwargs):
        calls.append(kwargs)
        source = kwargs["source"]
        evidence_path = Path(kwargs["output_path"])
        evidence_path.write_text(
            json.dumps(
                {
                    "status": "success",
                    "source": source,
                    "worker": kwargs["worker_label"],
                    "response": {"status": "success", "raw_count": 1, "items": [{"source": source}]},
                    "cleanup": "cleanup_ok",
                    "cleanup_verify": "remote_stage_absent",
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        return RemoteRunResult(
            status="success",
            evidence_path=str(evidence_path),
            cleanup="cleanup_ok",
            cleanup_verify="remote_stage_absent",
        )

    output_path = tmp_path / "collect-evidence.json"
    result = collect_once(
        sources=["senate_trading", "akshare"],
        output_path=output_path,
        evidence_dir=tmp_path / "runs",
        remote_run=fake_remote_run,
        stamp="20260707T002000Z",
    )

    assert result["status"] == "success"
    assert result["summary"] == {"success": 2, "failed": 0}
    assert [call["source"] for call in calls] == ["senate_trading", "akshare"]
    assert calls[0]["worker_label"] == "oracle-sg-west-preferred-overseas"
    assert calls[1]["worker_label"] == "yanhuoyun-domestic"
    assert calls[0]["limit"] == 1
    assert calls[1]["limit"] == 1
    saved = json.loads(output_path.read_text(encoding="utf-8"))
    assert saved["runs"][0]["cleanup_verify"] == "remote_stage_absent"


def test_collect_once_uses_source_specific_limits_for_github_and_ai(tmp_path):
    calls: list[dict[str, object]] = []

    def fake_remote_run(**kwargs):
        calls.append(kwargs)
        evidence_path = Path(kwargs["output_path"])
        evidence_path.write_text(
            json.dumps(
                {
                    "status": "success",
                    "source": kwargs["source"],
                    "worker": kwargs["worker_label"],
                    "response": {"status": "success", "raw_count": kwargs["limit"], "items": []},
                    "cleanup": "cleanup_ok",
                    "cleanup_verify": "remote_stage_absent",
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        return RemoteRunResult(
            status="success",
            evidence_path=str(evidence_path),
            cleanup="cleanup_ok",
            cleanup_verify="remote_stage_absent",
        )

    collect_once(
        sources=["github_trending", "ai_model_updates", "institutional_13f", "weather"],
        output_path=tmp_path / "collect-evidence.json",
        evidence_dir=tmp_path / "runs",
        remote_run=fake_remote_run,
        stamp="20260707T002200Z",
    )

    assert [(call["source"], call["limit"]) for call in calls] == [
        ("github_trending", 3),
        ("ai_model_updates", 6),
        ("institutional_13f", 10),
        ("weather", 6),
    ]


def test_collect_once_falls_back_to_oracle_arm1_when_sgw_senate_fails(tmp_path):
    calls: list[dict[str, object]] = []

    def fake_remote_run(**kwargs):
        calls.append(kwargs)
        evidence_path = Path(kwargs["output_path"])
        if kwargs["worker_label"] == "oracle-sg-west-preferred-overseas":
            evidence_path.write_text(
                json.dumps(
                    {
                        "status": "failed",
                        "worker": kwargs["worker_label"],
                        "source": kwargs["source"],
                        "remote_returncode": 255,
                        "stderr_excerpt": "ssh: connect to host 149.118.53.164 port 22: Operation timed out",
                        "response": {},
                        "cleanup": "",
                        "cleanup_verify": "",
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            return RemoteRunResult(
                status="failed",
                evidence_path=str(evidence_path),
                cleanup="",
                cleanup_verify="",
            )

        evidence_path.write_text(
            json.dumps(
                {
                    "status": "success",
                    "worker": kwargs["worker_label"],
                    "source": kwargs["source"],
                    "response": {"status": "success", "raw_count": 1, "items": [{"symbol": "BYND"}]},
                    "cleanup": "cleanup_ok",
                    "cleanup_verify": "remote_stage_absent",
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        return RemoteRunResult(
            status="success",
            evidence_path=str(evidence_path),
            cleanup="cleanup_ok",
            cleanup_verify="remote_stage_absent",
        )

    output_path = tmp_path / "collect-evidence.json"
    result = collect_once(
        sources=["senate_trading"],
        output_path=output_path,
        evidence_dir=tmp_path / "runs",
        remote_run=fake_remote_run,
        stamp="20260707T123000Z",
    )

    assert result["status"] == "success"
    assert result["summary"] == {"success": 1, "failed": 0}
    assert [call["worker_label"] for call in calls] == [
        "oracle-sg-west-preferred-overseas",
        "oracle-arm1-overseas-fallback",
    ]
    run = result["runs"][0]
    assert run["worker"] == "oracle-arm1-overseas-fallback"
    assert run["fallback"]["used"] is True
    assert run["fallback"]["primary_worker"] == "oracle-sg-west-preferred-overseas"
    assert run["fallback"]["final_worker"] == "oracle-arm1-overseas-fallback"
    assert [attempt["role"] for attempt in run["attempts"]] == ["primary", "fallback_1"]
    assert run["attempts"][0]["status"] == "failed"
    assert run["attempts"][0]["remote_returncode"] == 255
    assert "Operation timed out" in run["attempts"][0]["stderr_excerpt"]
    assert run["attempts"][1]["status"] == "success"
    assert run["cleanup_verify"] == "remote_stage_absent"


def test_collect_once_marks_unknown_source_failed_without_remote_call(tmp_path):
    calls: list[dict[str, object]] = []

    result = collect_once(
        sources=["unknown_feed"],
        output_path=tmp_path / "collect.json",
        evidence_dir=tmp_path / "runs",
        remote_run=lambda **kwargs: calls.append(kwargs),
        stamp="20260707T002100Z",
    )

    assert calls == []
    assert result["status"] == "failed"
    assert result["summary"] == {"success": 0, "failed": 1}
    assert result["runs"][0]["error"] == "unsupported_collect_source: unknown_feed"
