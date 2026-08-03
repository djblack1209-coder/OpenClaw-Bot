from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from src.execution.intel_brief import PRODUCTION_ACK_VALUE
from src.intel.db.store import initialize_intel_db
from src.intel.telegram_delivery import TELEGRAM_SANDBOX_ACK_VALUE


def _ready_env() -> dict[str, str]:
    return {
        "INTEL_BRIEF_ENABLED": "true",
        "INTEL_BRIEF_SCHEDULER_TIMEZONE": "UTC",
        "INTEL_BRIEF_TELEGRAM_BOT_TOKEN": "123456:SECRET-DO-NOT-LEAK",
        "INTEL_BRIEF_TELEGRAM_CHAT_ID": "987654321",
        "INTEL_BRIEF_TELEGRAM_SANDBOX_SEND_ACK": TELEGRAM_SANDBOX_ACK_VALUE,
        "INTEL_BRIEF_WORKER_PLACEMENT_CONFIRMED": "true",
    }


def _write_collect_payload(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "timestamp": "2026-07-07T08:31:00+00:00",
                "status": "success",
                "summary": {"success": 2, "failed": 0},
                "runs": [
                    {
                        "source": "senate_trading",
                        "status": "success",
                        "worker": "oracle-sg-west-preferred-overseas",
                        "evidence_path": "child-senate.json",
                        "response": {
                            "fetched_at": "2026-07-07T08:30:10+00:00",
                            "raw_count": 1,
                            "items": [
                                {
                                    "person": "Ron L Wyden",
                                    "ticker": "BYND",
                                    "transaction_type": "Sale",
                                    "amount": "$15,001 - $50,000",
                                    "transaction_date": "2026-06-30",
                                    "disclosure_date": "2026-07-07",
                                }
                            ],
                        },
                    },
                    {
                        "source": "akshare",
                        "status": "success",
                        "worker": "yanhuoyun-domestic",
                        "evidence_path": "child-akshare.json",
                        "response": {
                            "fetched_at": "2026-07-07T08:30:20+00:00",
                            "raw_count": 1,
                            "items": [
                                {
                                    "trade_date": "2026-07-07",
                                    "code": "000021",
                                    "name": "深科技",
                                    "reason": "日涨幅偏离值达7%",
                                    "close_price": "18.88",
                                }
                            ],
                        },
                    },
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def test_production_cycle_blocks_without_production_ack_before_collection(tmp_path):
    from src.intel.production_cycle import run_intel_production_cycle

    calls: list[str] = []

    def collect_runner(**kwargs):  # pragma: no cover - must not be called
        calls.append("collect")
        raise AssertionError("collect should not run when production ack is missing")

    result = run_intel_production_cycle(
        output_dir=tmp_path / "cycle-artifacts",
        evidence_path=tmp_path / "cycle.json",
        now=datetime(2026, 7, 7, 8, 31, tzinfo=UTC),
        env=_ready_env(),
        collect_runner=collect_runner,
    )

    assert result["status"] == "blocked"
    assert result["network_calls"] == 0
    assert result["steps"] == {}
    assert calls == []
    assert "production_ack_missing" in result["preflight"]["missing_gates"]


def test_production_cycle_default_sources_include_ai_model_updates():
    from src.intel.production_cycle import DEFAULT_PRODUCTION_CYCLE_SOURCES

    assert DEFAULT_PRODUCTION_CYCLE_SOURCES == (
        "senate_trading",
        "akshare",
        "github_trending",
        "ai_model_updates",
        "institutional_13f",
        "weather",
    )


def test_production_cycle_collects_summarizes_and_delivers_with_injected_runners(tmp_path):
    from src.intel.production_cycle import run_intel_production_cycle

    collect_calls = []
    delivery_calls = []

    def collect_runner(**kwargs):
        collect_calls.append(kwargs)
        output_path = Path(kwargs["output_path"])
        _write_collect_payload(output_path)
        return json.loads(output_path.read_text(encoding="utf-8"))

    def production_once_runner(**kwargs):
        delivery_calls.append(kwargs)
        evidence_path = Path(kwargs["evidence_path"])
        payload = {
            "status": "success",
            "gate": {"reason": "production_ready", "missing_gates": []},
            "network_calls": 1,
            "delivery": {"status": "success", "send_result": {"success": True, "message_id": "42"}},
        }
        evidence_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        return payload

    lifecycle_db = tmp_path / "intel_brief.db"
    initialize_intel_db(lifecycle_db)
    env = {
        **_ready_env(),
        "INTEL_BRIEF_SCHEDULER_PRODUCTION_ACK": PRODUCTION_ACK_VALUE,
        "INTEL_BRIEF_DB_PATH": str(lifecycle_db),
    }
    result = run_intel_production_cycle(
        output_dir=tmp_path / "cycle-artifacts",
        evidence_path=tmp_path / "cycle.json",
        now=datetime(2026, 7, 7, 8, 31, tzinfo=UTC),
        env=env,
        stamp="20260707T083100Z",
        llm_mode="fallback-only",
        collect_runner=collect_runner,
        production_once_runner=production_once_runner,
    )

    assert result["status"] == "success"
    assert len(collect_calls) == 1
    assert len(delivery_calls) == 1
    assert result["steps"]["collect"]["summary"] == {"success": 2, "failed": 0}
    assert result["steps"]["llm_summary"]["llm"]["llm_attempted"] is False
    assert result["steps"]["production_once"]["network_calls"] == 1
    assert result["subscription_lifecycle"]["status"] == "success"
    assert result["subscription_lifecycle"]["reason"] == "readonly_audit_complete"
    assert result["subscription_lifecycle"]["audit"]["summary"]["expired_active_found"] == 0
    assert result["subscription_lifecycle"]["audit"]["summary"]["expiring_active_found"] == 0
    assert result["subscription_lifecycle"]["audit"]["apply_expiry"] is False
    assert result["subscription_lifecycle"]["audit"]["send_reminders"] is False
    assert Path(result["artifacts"]["collect_evidence"]).exists()
    assert Path(result["artifacts"]["llm_summary_json"]).exists()
    saved_text = Path(tmp_path / "cycle.json").read_text(encoding="utf-8")
    assert "SECRET" not in saved_text
    assert "987654321" not in saved_text


def test_intel_production_cycle_cli_writes_blocked_evidence(tmp_path, monkeypatch):
    from scripts.intel_production_cycle import main

    monkeypatch.delenv("INTEL_BRIEF_SCHEDULER_PRODUCTION_ACK", raising=False)
    output = tmp_path / "cycle.json"

    exit_code = main(
        [
            "--output-dir",
            str(tmp_path / "cycle-artifacts"),
            "--evidence",
            str(output),
            "--now",
            "2026-07-07T08:31:00+00:00",
            "--source",
            "senate_trading",
        ]
    )

    assert exit_code == 2
    saved = json.loads(output.read_text(encoding="utf-8"))
    assert saved["status"] == "blocked"
    assert saved["network_calls"] == 0


def test_production_cycle_lifecycle_audit_skips_without_db_path(tmp_path):
    from src.intel.production_cycle import run_intel_production_cycle

    collect_calls = []
    delivery_calls = []

    def collect_runner(**kwargs):
        collect_calls.append(kwargs)
        output_path = Path(kwargs["output_path"])
        _write_collect_payload(output_path)
        return json.loads(output_path.read_text(encoding="utf-8"))

    def production_once_runner(**kwargs):
        delivery_calls.append(kwargs)
        payload = {"status": "success", "network_calls": 0, "delivery": {"status": "success"}}
        Path(kwargs["evidence_path"]).write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        return payload

    result = run_intel_production_cycle(
        output_dir=tmp_path / "cycle-artifacts",
        evidence_path=tmp_path / "cycle.json",
        now=datetime(2026, 7, 7, 8, 31, tzinfo=UTC),
        env={**_ready_env(), "INTEL_BRIEF_SCHEDULER_PRODUCTION_ACK": PRODUCTION_ACK_VALUE},
        stamp="20260707T083100Z",
        collect_runner=collect_runner,
        production_once_runner=production_once_runner,
    )

    assert result["status"] == "success"
    assert result["subscription_lifecycle"] == {
        "status": "skipped",
        "reason": "intel_brief_db_path_missing",
        "network_calls": 0,
        "redacted_env": {"INTEL_BRIEF_DB_PATH": False},
        "limits": [
            "Lifecycle audit is read-only and skipped when INTEL_BRIEF_DB_PATH is not configured.",
            "No subscription status mutation and no Telegram reminder send.",
        ],
    }
    assert len(collect_calls) == 1
    assert len(delivery_calls) == 1


def test_production_cycle_uses_ttl_cache_and_records_central_source_health(tmp_path):
    from src.intel.db.store import put_source_last_good
    from src.intel.production_cycle import run_intel_production_cycle

    db_path = tmp_path / "intel.db"
    initialize_intel_db(db_path)
    put_source_last_good(
        db_path,
        source_name="akshare",
        captured_at="2026-08-04T08:00:00+00:00",
        expires_at="2026-08-05T08:00:00+00:00",
        payload={
            "status": "success",
            "fetched_at": "2026-08-04T08:00:00+00:00",
            "items": [
                {
                    "trade_date": "2026-08-04",
                    "code": "000021",
                    "name": "深科技",
                    "reason": "机构净买入",
                }
            ],
        },
    )

    def collect_runner(**kwargs):
        payload = {
            "timestamp": "2026-08-04T08:31:00+00:00",
            "status": "failed",
            "summary": {"success": 1, "failed": 1},
            "runs": [
                {
                    "source": "ai_model_updates",
                    "status": "success",
                    "worker": "overseas",
                    "response": {
                        "status": "success",
                        "fetched_at": "2026-08-04T08:30:00+00:00",
                        "items": [
                            {
                                "provider": "openai",
                                "title": "Fresh model update",
                                "published_at": "2026-08-04T07:00:00+00:00",
                                "url": "https://openai.com/news/fresh",
                            }
                        ],
                    },
                },
                {
                    "source": "akshare",
                    "status": "failed",
                    "worker": "domestic",
                    "error": "temporary upstream failure",
                    "response": {"status": "failed", "items": []},
                },
            ],
        }
        Path(kwargs["output_path"]).write_text(json.dumps(payload), encoding="utf-8")
        return payload

    def delivery_runner(**kwargs):
        Path(kwargs["evidence_path"]).write_text('{"status":"success"}', encoding="utf-8")
        return {"status": "success", "network_calls": 0, "delivery": {"status": "success"}}

    result = run_intel_production_cycle(
        output_dir=tmp_path / "runs",
        evidence_path=tmp_path / "cycle.json",
        now=datetime(2026, 8, 4, 8, 31, tzinfo=UTC),
        env={
            **_ready_env(),
            "INTEL_BRIEF_SCHEDULER_PRODUCTION_ACK": PRODUCTION_ACK_VALUE,
            "INTEL_BRIEF_DB_PATH": str(db_path),
        },
        collect_runner=collect_runner,
        production_once_runner=delivery_runner,
    )

    assert result["status"] == "success"
    assert result["steps"]["collect"]["status"] == "partial_success"
    assert result["source_coverage"] == {
        "fresh_sources": ["ai_model_updates"],
        "cached_sources": ["akshare"],
        "failed_sources": [],
        "available_item_count": 2,
    }
    with sqlite3.connect(db_path) as conn:
        health = conn.execute(
            "SELECT source_name, last_status, fallback_used FROM source_health ORDER BY source_name"
        ).fetchall()
        attempts = conn.execute("SELECT COUNT(*) FROM source_attempts").fetchone()[0]
    assert health == [("ai_model_updates", "success", 0), ("akshare", "cached", 1)]
    assert attempts == 2


def test_production_cycle_applies_github_entity_cooldown_across_days(tmp_path):
    from src.intel.db.store import set_content_pipeline_state
    from src.intel.production_cycle import run_intel_production_cycle

    db_path = tmp_path / "intel.db"
    initialize_intel_db(db_path)
    set_content_pipeline_state(
        db_path,
        "content_v2_baseline_completed",
        json.dumps(
            {
                "run_key": "seed-baseline",
                "sources": ["github_trending", "institutional_13f"],
                "fresh_sources": ["github_trending", "institutional_13f"],
                "observation_counts": {"github_trending": 1, "institutional_13f": 1},
            }
        ),
    )
    collected_days = iter(("2026-08-04", "2026-08-05"))

    def collect_runner(**kwargs):
        day = next(collected_days)
        payload = {
            "timestamp": f"{day}T08:31:00+00:00",
            "status": "success",
            "summary": {"success": 1, "failed": 0},
            "runs": [
                {
                    "source": "github_trending",
                    "status": "success",
                    "worker": "overseas",
                    "response": {
                        "status": "success",
                        "fetched_at": f"{day}T08:30:00+00:00",
                        "items": [
                            {
                                "repo": "openclaw/openclaw",
                                "title": "openclaw/openclaw",
                                "url": "https://github.com/openclaw/openclaw",
                                "description": "Agent toolkit",
                                "stars_today": "500",
                            }
                        ],
                    },
                }
            ],
        }
        Path(kwargs["output_path"]).write_text(json.dumps(payload), encoding="utf-8")
        return payload

    def delivery_runner(**kwargs):
        Path(kwargs["evidence_path"]).write_text('{"status":"success"}', encoding="utf-8")
        return {"status": "success", "network_calls": 0, "delivery": {"status": "success"}}

    env = {
        **_ready_env(),
        "INTEL_BRIEF_SCHEDULER_PRODUCTION_ACK": PRODUCTION_ACK_VALUE,
        "INTEL_BRIEF_DB_PATH": str(db_path),
    }
    first = run_intel_production_cycle(
        output_dir=tmp_path / "day-1",
        evidence_path=tmp_path / "day-1.json",
        now=datetime(2026, 8, 4, 8, 31, tzinfo=UTC),
        env=env,
        stamp="20260804T083100Z",
        collect_runner=collect_runner,
        production_once_runner=delivery_runner,
    )
    second = run_intel_production_cycle(
        output_dir=tmp_path / "day-2",
        evidence_path=tmp_path / "day-2.json",
        now=datetime(2026, 8, 5, 8, 31, tzinfo=UTC),
        env=env,
        stamp="20260805T083100Z",
        collect_runner=collect_runner,
        production_once_runner=delivery_runner,
    )

    assert first["steps"]["brief"]["summary"]["rendered_count"] == 1
    assert second["steps"]["brief"]["summary"]["rendered_count"] == 0
    assert second["steps"]["brief"]["content_quality"]["recent_entity_observation_count"] == 1
    assert any(item["reason"] == "entity_cooldown" for item in second["steps"]["brief"]["content_quality"]["rejected"])


def test_production_cycle_empty_success_uses_cache_without_overwriting_last_good(tmp_path):
    from src.intel.db.store import get_source_last_good, put_source_last_good
    from src.intel.production_cycle import run_intel_production_cycle

    db_path = tmp_path / "intel.db"
    initialize_intel_db(db_path)
    cached_payload = {
        "status": "success",
        "fetched_at": "2026-08-04T08:00:00+00:00",
        "items": [
            {
                "trade_date": "2026-08-04",
                "code": "000021",
                "name": "深科技",
                "reason": "机构净买入",
            }
        ],
    }
    put_source_last_good(
        db_path,
        source_name="akshare",
        captured_at="2026-08-04T08:00:00+00:00",
        expires_at="2026-08-05T08:00:00+00:00",
        payload=cached_payload,
    )
    before = get_source_last_good(db_path, source_name="akshare", now="2026-08-04T08:31:00+00:00")

    def collect_runner(**kwargs):
        payload = {
            "timestamp": "2026-08-04T08:31:00+00:00",
            "status": "success",
            "summary": {"success": 1, "failed": 0},
            "runs": [
                {
                    "source": "akshare",
                    "status": "success",
                    "worker": "domestic",
                    "response": {
                        "status": "success",
                        "fetched_at": "2026-08-04T08:30:00+00:00",
                        "items": [],
                    },
                }
            ],
        }
        Path(kwargs["output_path"]).write_text(json.dumps(payload), encoding="utf-8")
        return payload

    def delivery_runner(**kwargs):
        Path(kwargs["evidence_path"]).write_text('{"status":"success"}', encoding="utf-8")
        return {"status": "success", "network_calls": 0, "delivery": {"status": "success"}}

    result = run_intel_production_cycle(
        output_dir=tmp_path / "runs",
        evidence_path=tmp_path / "cycle.json",
        now=datetime(2026, 8, 4, 8, 31, tzinfo=UTC),
        env={
            **_ready_env(),
            "INTEL_BRIEF_SCHEDULER_PRODUCTION_ACK": PRODUCTION_ACK_VALUE,
            "INTEL_BRIEF_DB_PATH": str(db_path),
        },
        collect_runner=collect_runner,
        production_once_runner=delivery_runner,
    )

    run = result["steps"]["collect"]["runs"][0]
    after = get_source_last_good(db_path, source_name="akshare", now="2026-08-04T08:31:00+00:00")
    assert result["steps"]["collect"]["status"] == "partial_success"
    assert run["status"] == "cached"
    assert run["collection_status"] == "empty_success"
    assert result["source_coverage"] == {
        "fresh_sources": [],
        "cached_sources": ["akshare"],
        "failed_sources": [],
        "available_item_count": 1,
    }
    assert after["payload_hash"] == before["payload_hash"]
    assert after["captured_at"] == before["captured_at"]
    assert after["payload"] == cached_payload


def test_production_cycle_retries_baseline_until_both_sources_have_fresh_observations(tmp_path):
    from src.intel.db.store import get_content_pipeline_state, set_content_pipeline_state
    from src.intel.production_cycle import run_intel_production_cycle

    db_path = tmp_path / "intel.db"
    initialize_intel_db(db_path)
    legacy_state = json.dumps(
        {
            "run_key": "legacy-incomplete-baseline",
            "sources": ["github_trending", "institutional_13f"],
        },
        sort_keys=True,
    )
    set_content_pipeline_state(db_path, "content_v2_baseline_completed", legacy_state)
    collection_round = 0

    def collect_runner(**kwargs):
        nonlocal collection_round
        collection_round += 1
        day = f"2026-08-0{3 + collection_round}"
        github_run = {
            "source": "github_trending",
            "status": "success",
            "worker": "overseas",
            "response": {
                "status": "success",
                "fetched_at": f"{day}T08:30:00+00:00",
                "items": [
                    {
                        "repo": f"openclaw/openclaw-{collection_round}",
                        "title": f"openclaw/openclaw-{collection_round}",
                        "url": f"https://github.com/openclaw/openclaw-{collection_round}",
                        "description": "Agent toolkit",
                        "stars_today": "500",
                    }
                ],
            },
        }
        institutional_items = []
        if collection_round == 2:
            institutional_items = [
                {
                    "fund_name": "Example Capital",
                    "cik": "0000123456",
                    "accession_number": "0000123456-26-000001",
                    "filing_date": day,
                    "issuer": "Example Corp",
                    "cusip": "123456789",
                }
            ]
        payload = {
            "timestamp": f"{day}T08:31:00+00:00",
            "status": "success",
            "summary": {"success": 2, "failed": 0},
            "runs": [
                github_run,
                {
                    "source": "institutional_13f",
                    "status": "success",
                    "worker": "overseas",
                    "response": {
                        "status": "success",
                        "fetched_at": f"{day}T08:30:00+00:00",
                        "items": institutional_items,
                    },
                },
            ],
        }
        Path(kwargs["output_path"]).write_text(json.dumps(payload), encoding="utf-8")
        return payload

    def delivery_runner(**kwargs):
        Path(kwargs["evidence_path"]).write_text('{"status":"success"}', encoding="utf-8")
        return {"status": "success", "network_calls": 0, "delivery": {"status": "success"}}

    env = {
        **_ready_env(),
        "INTEL_BRIEF_SCHEDULER_PRODUCTION_ACK": PRODUCTION_ACK_VALUE,
        "INTEL_BRIEF_DB_PATH": str(db_path),
    }
    first = run_intel_production_cycle(
        output_dir=tmp_path / "day-1",
        evidence_path=tmp_path / "day-1.json",
        now=datetime(2026, 8, 4, 8, 31, tzinfo=UTC),
        env=env,
        stamp="20260804T083100Z",
        collect_runner=collect_runner,
        production_once_runner=delivery_runner,
    )

    assert get_content_pipeline_state(db_path, "content_v2_baseline_completed") == legacy_state
    assert first["steps"]["brief"]["content_quality"]["pipeline_counts"]["selected"] == 0
    empty_run = first["steps"]["collect"]["runs"][1]
    assert empty_run["status"] == "failed"
    assert empty_run["collection_status"] == "empty_success"
    assert first["source_coverage"]["failed_sources"] == ["institutional_13f"]
    assert first["content_v2_baseline"] == {
        "status": "pending",
        "required_sources": ["github_trending", "institutional_13f"],
        "fresh_sources": ["github_trending"],
        "observation_counts": {"github_trending": 1, "institutional_13f": 0},
    }
    with sqlite3.connect(db_path) as conn:
        first_observed = conn.execute(
            """
            SELECT ci.source_name, COUNT(*)
            FROM content_observations co
            JOIN content_items ci ON ci.id=co.content_item_id
            WHERE co.run_key=?
            GROUP BY ci.source_name
            ORDER BY ci.source_name
            """,
            ("20260804T083100Z",),
        ).fetchall()
    assert first_observed == [("github_trending", 1)]

    second = run_intel_production_cycle(
        output_dir=tmp_path / "day-2",
        evidence_path=tmp_path / "day-2.json",
        now=datetime(2026, 8, 5, 8, 31, tzinfo=UTC),
        env=env,
        stamp="20260805T083100Z",
        collect_runner=collect_runner,
        production_once_runner=delivery_runner,
    )

    baseline_state = json.loads(get_content_pipeline_state(db_path, "content_v2_baseline_completed"))
    assert baseline_state["run_key"] == "20260805T083100Z"
    assert baseline_state["sources"] == ["github_trending", "institutional_13f"]
    assert baseline_state["fresh_sources"] == ["github_trending", "institutional_13f"]
    assert baseline_state["observation_counts"] == {"github_trending": 1, "institutional_13f": 1}
    assert second["content_v2_baseline"]["status"] == "completed"
    assert second["steps"]["brief"]["content_quality"]["pipeline_counts"]["selected"] == 0


def test_production_cycle_baseline_blocks_old_repo_and_accession_but_allows_new_accession(tmp_path):
    from src.intel.production_cycle import run_intel_production_cycle

    db_path = tmp_path / "intel.db"
    initialize_intel_db(db_path)
    collection_round = 0

    def collect_runner(**kwargs):
        nonlocal collection_round
        collection_round += 1
        day = f"2026-08-0{3 + collection_round}"
        institutional_items = [
            {
                "fund_name": "Example Capital",
                "cik": "0000123456",
                "accession_number": "0000123456-26-000001",
                "filing_date": "2026-08-04",
                "issuer": "Existing Corp",
                "cusip": "123456789",
            }
        ]
        if collection_round == 3:
            institutional_items.append(
                {
                    "fund_name": "Example Capital",
                    "cik": "0000123456",
                    "accession_number": "0000123456-26-000002",
                    "filing_date": day,
                    "issuer": "New Corp",
                    "cusip": "987654321",
                }
            )
        payload = {
            "timestamp": f"{day}T08:31:00+00:00",
            "status": "success",
            "summary": {"success": 2, "failed": 0},
            "runs": [
                {
                    "source": "github_trending",
                    "status": "success",
                    "worker": "overseas",
                    "response": {
                        "status": "success",
                        "fetched_at": f"{day}T08:30:00+00:00",
                        "items": [
                            {
                                "repo": "openclaw/openclaw",
                                "title": "openclaw/openclaw",
                                "url": "https://github.com/openclaw/openclaw",
                                "description": "Agent toolkit",
                                "stars_today": "500",
                            }
                        ],
                    },
                },
                {
                    "source": "institutional_13f",
                    "status": "success",
                    "worker": "overseas",
                    "response": {
                        "status": "success",
                        "fetched_at": f"{day}T08:30:00+00:00",
                        "items": institutional_items,
                    },
                },
            ],
        }
        Path(kwargs["output_path"]).write_text(json.dumps(payload), encoding="utf-8")
        return payload

    def delivery_runner(**kwargs):
        Path(kwargs["evidence_path"]).write_text('{"status":"success"}', encoding="utf-8")
        return {"status": "success", "network_calls": 0, "delivery": {"status": "success"}}

    env = {
        **_ready_env(),
        "INTEL_BRIEF_SCHEDULER_PRODUCTION_ACK": PRODUCTION_ACK_VALUE,
        "INTEL_BRIEF_DB_PATH": str(db_path),
    }
    results = [
        run_intel_production_cycle(
            output_dir=tmp_path / f"day-{day_index}",
            evidence_path=tmp_path / f"day-{day_index}.json",
            now=datetime(2026, 8, 3 + day_index, 8, 31, tzinfo=UTC),
            env=env,
            stamp=f"2026080{3 + day_index}T083100Z",
            collect_runner=collect_runner,
            production_once_runner=delivery_runner,
        )
        for day_index in range(1, 4)
    ]

    assert results[0]["content_v2_baseline"]["status"] == "completed"
    assert results[0]["steps"]["brief"]["summary"]["rendered_count"] == 0
    assert results[1]["steps"]["brief"]["summary"]["rendered_count"] == 0
    day_two_rejections = {
        (item["source"], item["reason"]) for item in results[1]["steps"]["brief"]["content_quality"]["rejected"]
    }
    assert ("github_trending", "entity_cooldown") in day_two_rejections
    assert ("institutional_13f", "already_delivered") in day_two_rejections
    assert results[2]["steps"]["brief"]["summary"]["rendered_count"] == 1
    assert results[2]["steps"]["brief"]["items"][0]["payload"]["accession_number"] == "0000123456-26-000002"
    day_three_rejections = {
        (item["source"], item["reason"]) for item in results[2]["steps"]["brief"]["content_quality"]["rejected"]
    }
    assert ("github_trending", "entity_cooldown") in day_three_rejections
    assert ("institutional_13f", "already_delivered") in day_three_rejections
