from __future__ import annotations

import json
import sqlite3

from src.intel.delivery import (
    FakeTelegramSender,
    build_delivery_message,
    build_delivery_sandbox,
    deliver_summary_to_subscribers,
    seed_sandbox_subscriber,
)


def _summary_payload() -> dict:
    return {
        "timestamp": "2026-07-07T00:57:36+00:00",
        "phase": "F-llm-summary-dry-run",
        "scope": "dry_run_items_to_llm_summary",
        "status": "success",
        "input_dry_run_evidence": "packages/clawbot/data/intel_evidence/phasef/brief.json",
        "llm": {
            "status": "success",
            "llm_attempted": True,
            "llm_success": True,
            "model_family": "intel_local",
            "summary_text": "### 总览\nRon L Wyden 出售 BYND。深科技（000021）上榜。",
            "usage": {"prompt_tokens": 353, "completion_tokens": 159, "total_tokens": 512},
        },
        "items": [
            {"source_label": "国会持仓", "title": "Ron L Wyden Sale (Full) BYND"},
            {"source_label": "A股龙虎榜", "title": "深科技（000021）：1家机构买入"},
        ],
        "limits": ["No Telegram push.", "No scheduler registration."],
    }


def test_seed_sandbox_subscriber_creates_active_subscription_and_preferences(tmp_path):
    db_path = tmp_path / "intel_sandbox.db"

    subscriber = seed_sandbox_subscriber(
        db_path,
        user_id="sandbox-user",
        channel_user_id="sandbox-chat",
        categories=["senate_trading", "akshare"],
    )

    assert subscriber["user_id"] == "sandbox-user"
    assert subscriber["channel_type"] == "telegram"
    with sqlite3.connect(db_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM subscribers").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM user_subscriptions WHERE status='active'").fetchone()[0] == 1
        prefs = [row[0] for row in conn.execute("SELECT category FROM source_preferences ORDER BY category")]
    assert prefs == ["akshare", "senate_trading"]


def test_build_delivery_message_uses_llm_summary_and_respects_telegram_limit():
    message = build_delivery_message(_summary_payload(), max_chars=260)

    assert "情报简报" in message
    assert "Ron L Wyden" in message
    assert "深科技" in message
    assert "intel_local" not in message
    assert "tokens=" not in message
    assert "今日重点" in message
    assert "精选情报（2条）" in message
    assert "sandbox fake Telegram sender" not in message
    assert "不构成投资建议" in message
    assert len(message) <= 260


def test_build_delivery_message_keeps_sandbox_boundary_when_requested():
    message = build_delivery_message(_summary_payload(), max_chars=500, delivery_context="sandbox")

    assert "Intel Brief 摘要沙盒" in message
    assert "sandbox fake Telegram sender" in message


def test_build_delivery_message_hides_fallback_internals_and_shows_all_eight_items():
    payload = _summary_payload()
    payload["status"] = "partial_fallback"
    payload["llm"] = {
        "llm_success": False,
        "model_family": "qwen",
        "summary_text": "已按你的订阅偏好筛选 8 条情报。",
        "usage": {"total_tokens": 0},
    }
    payload["items"] = [
        {"source_label": "AI模型动态", "title": f"AI 动态 {index}"}
        for index in range(1, 9)
    ]

    message = build_delivery_message(payload, max_chars=1200)

    assert "partial_fallback" not in message
    assert "LLM：" not in message
    assert "tokens=" not in message
    assert "输入条目" not in message
    assert "AI精炼暂时不可用" in message
    assert "精选情报（8条）" in message
    assert "8. 【AI模型动态】AI 动态 8" in message


def test_build_delivery_message_escapes_html_sensitive_titles():
    payload = _summary_payload()
    payload["items"] = [{"source_label": "AI & 安全", "title": "OpenAI <Agent> 更新"}]

    message = build_delivery_message(payload, max_chars=500)

    assert "AI &amp; 安全" in message
    assert "OpenAI &lt;Agent&gt; 更新" in message
    assert "OpenAI <Agent> 更新" not in message


def test_fake_telegram_sender_writes_jsonl_without_network(tmp_path):
    outbox = tmp_path / "outbox.jsonl"
    sender = FakeTelegramSender(outbox)

    result = sender.send("sandbox-chat", "hello", parse_mode="HTML")

    assert result["success"] is True
    assert result["provider"] == "fake_telegram"
    saved = [json.loads(line) for line in outbox.read_text(encoding="utf-8").splitlines()]
    assert saved[0]["channel_user_id"] == "sandbox-chat"
    assert saved[0]["text"] == "hello"
    assert saved[0]["network"] == "not_called"


def test_deliver_summary_to_subscribers_records_delivery_log_and_outbox(tmp_path):
    db_path = tmp_path / "intel_sandbox.db"
    outbox = tmp_path / "outbox.jsonl"
    summary_path = tmp_path / "summary.json"
    summary_path.write_text(json.dumps(_summary_payload(), ensure_ascii=False), encoding="utf-8")
    seed_sandbox_subscriber(db_path, user_id="sandbox-user", channel_user_id="sandbox-chat")

    result = deliver_summary_to_subscribers(
        db_path=db_path,
        summary_evidence_path=summary_path,
        sender=FakeTelegramSender(outbox),
    )

    assert result["status"] == "success"
    assert result["summary"] == {"eligible": 1, "sent": 1, "failed": 0}
    with sqlite3.connect(db_path) as conn:
        row = conn.execute("SELECT channel_type, success, content_summary FROM delivery_log").fetchone()
    assert row[0] == "telegram"
    assert row[1] == 1
    assert "Ron L Wyden" in row[2]
    assert "sandbox fake Telegram sender" in row[2]
    assert outbox.exists()


def test_build_delivery_sandbox_writes_evidence_with_rollback_boundary(tmp_path):
    summary_path = tmp_path / "summary.json"
    db_path = tmp_path / "intel_sandbox.db"
    outbox_path = tmp_path / "outbox.jsonl"
    evidence_path = tmp_path / "delivery-evidence.json"
    summary_path.write_text(json.dumps(_summary_payload(), ensure_ascii=False), encoding="utf-8")

    result = build_delivery_sandbox(
        summary_evidence_path=summary_path,
        db_path=db_path,
        outbox_path=outbox_path,
        evidence_path=evidence_path,
        stamp="20260707T011000Z",
    )

    assert result["status"] == "success"
    assert result["delivery"]["summary"]["sent"] == 1
    assert result["rollback"] == [str(db_path), str(outbox_path), str(evidence_path)]
    saved = json.loads(evidence_path.read_text(encoding="utf-8"))
    assert saved["fake_sender"] is True
    assert saved["network_calls"] == 0


def test_intel_delivery_sandbox_cli_writes_evidence(tmp_path):
    from scripts.intel_delivery_sandbox import main

    summary_path = tmp_path / "summary.json"
    db_path = tmp_path / "intel_sandbox.db"
    outbox_path = tmp_path / "outbox.jsonl"
    evidence_path = tmp_path / "delivery-evidence.json"
    summary_path.write_text(json.dumps(_summary_payload(), ensure_ascii=False), encoding="utf-8")

    exit_code = main(
        [
            "--summary-evidence",
            str(summary_path),
            "--db",
            str(db_path),
            "--outbox",
            str(outbox_path),
            "--output",
            str(evidence_path),
            "--stamp",
            "20260707T011100Z",
        ]
    )

    assert exit_code == 0
    saved = json.loads(evidence_path.read_text(encoding="utf-8"))
    assert saved["status"] == "success"
    assert saved["delivery"]["summary"]["eligible"] == 1
