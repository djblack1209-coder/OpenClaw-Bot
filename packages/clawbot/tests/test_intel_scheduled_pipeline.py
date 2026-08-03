from __future__ import annotations

import json
from pathlib import Path

from src.intel.scheduled_pipeline import build_schedule_decision, run_scheduled_sandbox_pipeline


def _collect_payload() -> dict:
    return {
        "timestamp": "2026-07-07T00:22:08+00:00",
        "phase": "F-pre",
        "scope": "intel_collect_once_multi_source",
        "status": "success",
        "sources": ["senate_trading", "akshare"],
        "summary": {"success": 2, "failed": 0},
        "runs": [
            {
                "source": "senate_trading",
                "status": "success",
                "worker": "oracle-arm1-overseas-fallback",
                "evidence_path": "/evidence/senate.json",
                "response": {
                    "status": "success",
                    "fetched_at": "2026-07-07T00:20:41+00:00",
                    "raw_count": 1,
                    "items": [
                        {
                            "amount": "$50,001 - $100,000",
                            "asset_description": "Beyond Meat, Inc.",
                            "owner": "Spouse",
                            "person": "Ron L Wyden",
                            "source": "senate-stock-watcher-data",
                            "ticker": "BYND",
                            "transaction_date": "2026-07-06",
                            "disclosure_date": "2026-07-07",
                            "transaction_type": "Sale (Full)",
                        }
                    ],
                },
            },
            {
                "source": "akshare",
                "status": "success",
                "worker": "yanhuoyun-domestic",
                "evidence_path": "/evidence/akshare.json",
                "response": {
                    "status": "success",
                    "fetched_at": "2026-07-07T00:21:24+00:00",
                    "raw_count": 1,
                    "items": [
                        {
                            "close_price": "20.7",
                            "code": "000021",
                            "name": "深科技",
                            "reason": "1家机构买入，成功率46.03%",
                            "source": "akshare_stock_lhb_detail_em",
                            "trade_date": "2026-07-07",
                        }
                    ],
                },
            },
        ],
        "limits": ["One-shot collection only; no scheduler registration or service deployment."],
    }


def test_build_schedule_decision_triggers_after_time_once_per_day():
    due = build_schedule_decision(
        now_iso="2026-07-07T08:31:00+00:00",
        scheduled_time="08:30",
        enabled=True,
        last_run_date="2026-07-06",
    )
    before = build_schedule_decision(
        now_iso="2026-07-07T08:29:00+00:00",
        scheduled_time="08:30",
        enabled=True,
        last_run_date="2026-07-06",
    )
    duplicate = build_schedule_decision(
        now_iso="2026-07-07T09:00:00+00:00",
        scheduled_time="08:30",
        enabled=True,
        last_run_date="2026-07-07",
    )

    assert due["should_run"] is True
    assert before["should_run"] is False
    assert before["reason"] == "before_scheduled_time"
    assert duplicate["reason"] == "already_ran_today"


def test_run_scheduled_sandbox_pipeline_skips_when_not_due(tmp_path):
    collect_path = tmp_path / "collect.json"
    evidence_path = tmp_path / "scheduled.json"
    collect_path.write_text(json.dumps(_collect_payload(), ensure_ascii=False), encoding="utf-8")

    result = run_scheduled_sandbox_pipeline(
        collect_evidence_path=collect_path,
        output_dir=tmp_path / "out",
        evidence_path=evidence_path,
        now_iso="2026-07-07T08:00:00+00:00",
        scheduled_time="08:30",
        stamp="20260707T080000Z",
    )

    assert result["status"] == "skipped"
    assert result["schedule"]["reason"] == "before_scheduled_time"
    assert evidence_path.exists()
    assert not (tmp_path / "out" / "20260707T080000Z-brief-dry-run.json").exists()


def test_run_scheduled_sandbox_pipeline_chains_brief_llm_and_delivery(tmp_path):
    collect_path = tmp_path / "collect.json"
    evidence_path = tmp_path / "scheduled.json"
    collect_path.write_text(json.dumps(_collect_payload(), ensure_ascii=False), encoding="utf-8")

    result = run_scheduled_sandbox_pipeline(
        collect_evidence_path=collect_path,
        output_dir=tmp_path / "out",
        evidence_path=evidence_path,
        now_iso="2026-07-07T08:31:00+00:00",
        scheduled_time="08:30",
        stamp="20260707T083100Z",
        llm_mode="fallback-only",
    )

    assert result["status"] == "success"
    assert result["schedule"]["should_run"] is True
    assert result["steps"]["brief"]["status"] == "success"
    assert result["steps"]["llm_summary"]["llm"]["llm_attempted"] is False
    assert result["steps"]["delivery"]["delivery"]["summary"] == {"eligible": 1, "sent": 1, "failed": 0}
    assert Path(result["artifacts"]["brief_json"]).exists()
    assert Path(result["artifacts"]["llm_summary_json"]).exists()
    assert Path(result["artifacts"]["delivery_evidence"]).exists()
    saved = json.loads(evidence_path.read_text(encoding="utf-8"))
    assert saved["limits"][0] == "Scheduled sandbox only; no cron/systemd registration."


def test_intel_scheduled_sandbox_cli_writes_evidence(tmp_path):
    from scripts.intel_scheduled_sandbox import main

    collect_path = tmp_path / "collect.json"
    evidence_path = tmp_path / "scheduled.json"
    collect_path.write_text(json.dumps(_collect_payload(), ensure_ascii=False), encoding="utf-8")

    exit_code = main(
        [
            "--collect-evidence",
            str(collect_path),
            "--output-dir",
            str(tmp_path / "out"),
            "--output",
            str(evidence_path),
            "--now",
            "2026-07-07T08:31:00+00:00",
            "--time",
            "08:30",
            "--stamp",
            "20260707T083100Z",
            "--llm-mode",
            "fallback-only",
        ]
    )

    assert exit_code == 0
    saved = json.loads(evidence_path.read_text(encoding="utf-8"))
    assert saved["status"] == "success"
    assert saved["steps"]["delivery"]["network_calls"] == 0
