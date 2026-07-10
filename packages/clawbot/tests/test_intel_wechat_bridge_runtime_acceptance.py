"""Weixin ClawBot 每日简报桥接证据验收测试。"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

from src.intel.wechat_bridge_runtime import (
    build_wechat_bridge_runtime_acceptance,
    summarize_wechat_bridge_status,
    wait_for_wechat_bridge_runtime_acceptance,
)


def _write_evidence(path, *, recorded_at: str, status: str = "handled", **overrides):
    """写入脱敏桥接证据样本。"""
    latest = {
        "schema_version": 1,
        "recorded_at": recorded_at,
        "source": "openclaw-weixin-intel-brief-bridge",
        "status": status,
        "reason": "sent_reply",
        "shortcut_class": "today",
        "sender_hash": "abcdef123456",
        "text_length": 4,
        "bridge_url": "http://127.0.0.1:18790/wechat/incoming",
        "api_token_present": True,
        "http_status": 200,
        "reply_present": True,
        "reply_length": 120,
        "reply_contains_menu": True,
        "reply_contains_status": False,
        "reply_contains_schedule_prompt": False,
        "reply_contains_tracking_prompt": False,
        "reply_fell_to_llm": False,
        "sent_reply_success": True,
        "error_name": "",
    }
    latest.update(overrides)
    path.write_text(json.dumps({"latest": latest, "recent_events": [latest]}, ensure_ascii=False), encoding="utf-8")


def test_wechat_bridge_runtime_acceptance_accepts_recent_handled_evidence(tmp_path):
    """最近的 handled + sent_reply 证据应通过验收。"""
    now = datetime(2026, 7, 8, 23, 0, tzinfo=UTC)
    evidence = tmp_path / "runtime.json"
    _write_evidence(evidence, recorded_at=(now - timedelta(seconds=30)).isoformat())

    result = build_wechat_bridge_runtime_acceptance(evidence_path=evidence, max_age_seconds=900, now=now)

    assert result["verified"] is True
    assert result["blockers"] == []
    assert result["latest"]["sender_hash_present"] is True
    assert result["privacy"]["stores_raw_wechat_text"] is False


def test_wechat_bridge_runtime_acceptance_rejects_stale_or_llm_evidence(tmp_path):
    """旧证据或疑似 LLM 闲聊证据不能当作真实闭环。"""
    now = datetime(2026, 7, 8, 23, 0, tzinfo=UTC)
    evidence = tmp_path / "runtime.json"
    _write_evidence(
        evidence,
        recorded_at=(now - timedelta(seconds=3600)).isoformat(),
        reply_fell_to_llm=True,
    )

    result = build_wechat_bridge_runtime_acceptance(evidence_path=evidence, max_age_seconds=900, now=now)

    assert result["verified"] is False
    assert any("超过 900 秒" in item for item in result["blockers"])
    assert any("普通 LLM" in item for item in result["blockers"])


def test_wechat_bridge_runtime_acceptance_rejects_missing_send_success(tmp_path):
    """没有成功回发微信的证据不能通过。"""
    now = datetime(2026, 7, 8, 23, 0, tzinfo=UTC)
    evidence = tmp_path / "runtime.json"
    _write_evidence(
        evidence,
        recorded_at=(now - timedelta(seconds=30)).isoformat(),
        status="skipped",
        reason="empty_reply",
        sent_reply_success=False,
        reply_present=False,
    )

    result = build_wechat_bridge_runtime_acceptance(evidence_path=evidence, max_age_seconds=900, now=now)

    assert result["verified"] is False
    assert any("不是 handled" in item for item in result["blockers"])
    assert any("没有记录已成功" in item for item in result["blockers"])


def test_wechat_bridge_wait_mode_returns_immediately_when_verified(tmp_path):
    """等待模式遇到已通过证据应立即返回，不误报超时。"""
    evidence = tmp_path / "runtime.json"
    _write_evidence(evidence, recorded_at=datetime.now(UTC).isoformat())

    result = wait_for_wechat_bridge_runtime_acceptance(
        evidence_path=evidence,
        max_age_seconds=900,
        wait_seconds=10,
        poll_seconds=0.2,
    )

    assert result["verified"] is True
    assert result["wait"]["attempts"] == 1
    assert result["wait"]["timed_out"] is False


def test_wechat_bridge_wait_mode_reports_missing_evidence_without_wait(tmp_path):
    """不等待时也要明确告诉老板还没看到真实微信入站。"""
    evidence = tmp_path / "missing-runtime.json"

    result = wait_for_wechat_bridge_runtime_acceptance(
        evidence_path=evidence,
        max_age_seconds=900,
        wait_seconds=0,
        poll_seconds=0.2,
    )

    assert result["verified"] is False
    assert result["wait"]["attempts"] == 1
    assert result["wait"]["timed_out"] is False
    assert any("未找到微信桥接证据文件" in item for item in result["blockers"])


def test_wechat_bridge_status_summary_is_boss_readable(tmp_path):
    """状态摘要要能直接给操作台展示，不暴露敏感信息。"""
    missing = build_wechat_bridge_runtime_acceptance(evidence_path=tmp_path / "missing.json")
    missing_summary = summarize_wechat_bridge_status(missing)
    assert missing_summary["state"] == "waiting_real_wechat_message"
    assert missing_summary["severity"] == "warning"
    assert "今日简报" in missing_summary["next_action"]

    now = datetime.now(UTC)
    evidence = tmp_path / "runtime.json"
    _write_evidence(evidence, recorded_at=now.isoformat())
    verified = build_wechat_bridge_runtime_acceptance(evidence_path=evidence, max_age_seconds=900, now=now)
    verified_summary = summarize_wechat_bridge_status(verified)
    assert verified_summary["state"] == "verified"
    assert verified_summary["severity"] == "ok"
    assert verified_summary["verified"] is True
    assert verified_summary["privacy"]["stores_raw_wechat_text"] is False
