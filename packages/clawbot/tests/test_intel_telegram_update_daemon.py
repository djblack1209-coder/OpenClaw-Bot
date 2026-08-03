from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

from src.intel.telegram_delivery import TELEGRAM_SANDBOX_ACK_VALUE


def test_daemon_gate_requires_token_ack_network_and_send_flag(tmp_path):
    from scripts.intel_telegram_update_daemon import build_daemon_gate

    gate = build_daemon_gate(env={}, allow_real_network=False, allow_send_message=False)

    assert gate["ready"] is False
    assert gate["missing_gates"] == [
        "telegram_bot_token_missing",
        "telegram_runtime_ack_missing",
        "real_network_not_allowed",
        "send_message_not_allowed",
    ]


def test_daemon_once_processes_start_and_writes_heartbeat_without_leaking_secret(tmp_path):
    from scripts.intel_telegram_update_daemon import run_daemon_once
    from src.intel.telegram_update_processor import set_telegram_offset

    db_path = tmp_path / "intel.db"
    heartbeat = tmp_path / "heartbeat.json"
    evidence_dir = tmp_path / "evidence"
    token = "fake-daemon-token-secret"
    chat_id = "daemon-chat-secret"
    set_telegram_offset(db_path, 100)

    calls: list[dict[str, object]] = []

    def transport(url: str, payload: dict[str, object], timeout: int) -> dict[str, object]:
        calls.append({"url": url, "payload": payload, "timeout": timeout})
        if url.endswith("/getUpdates"):
            assert payload["offset"] == 101
            return {
                "ok": True,
                "result": [
                    {
                        "update_id": 101,
                        "message": {
                            "message_id": 201,
                            "text": "/start",
                            "from": {"id": "daemon-user", "username": "daemon"},
                            "chat": {"id": chat_id, "type": "private"},
                        },
                    }
                ],
            }
        if url.endswith("/sendMessage"):
            assert payload["chat_id"] == chat_id
            return {"ok": True, "result": {"message_id": 9001, "chat": {"id": chat_id}}}
        raise AssertionError(url)

    result = run_daemon_once(
        db_path=db_path,
        env={
            "INTEL_BRIEF_TELEGRAM_BOT_TOKEN": token,
            "INTEL_BRIEF_TELEGRAM_SANDBOX_SEND_ACK": TELEGRAM_SANDBOX_ACK_VALUE,
            "INTEL_BRIEF_TELEGRAM_LISTENER_ACK": "I_UNDERSTAND_REAL_TELEGRAM_LISTENER",
        },
        allow_real_network=True,
        allow_send_message=True,
        now="2026-07-08T16:30:00+00:00",
        evidence_dir=evidence_dir,
        heartbeat_path=heartbeat,
        transport=transport,
        limit=20,
        timeout_seconds=0,
    )

    assert result["status"] == "success"
    assert result["send_message_attempted"] is True
    assert result["processor"]["runtime"]["handled_count"] == 1
    assert heartbeat.exists()
    saved = heartbeat.read_text(encoding="utf-8")
    assert token not in saved
    assert chat_id not in saved
    payload = json.loads(saved)
    assert payload["last_status"] == "success"
    assert payload["last_handled_count"] == 1
    assert payload["last_start_menu_success_at"] == result["timestamp"]
    assert payload["last_start_menu_inline_keyboard_sent"] is True
    assert payload["last_start_menu_persistent_keyboard_sent"] is True
    assert payload["last_start_menu_raw_content_persisted"] is False
    assert (evidence_dir / "latest-real-update-daemon.json").exists()
    assert len(calls) == 3


def test_daemon_heartbeat_keeps_last_start_menu_success_after_empty_poll(tmp_path):
    from scripts.intel_telegram_update_daemon import run_daemon_once
    from src.intel.telegram_update_processor import set_telegram_offset

    db_path = tmp_path / "intel.db"
    heartbeat = tmp_path / "heartbeat.json"
    evidence_dir = tmp_path / "evidence"
    token = "fake-daemon-token-secret"
    chat_id = "daemon-chat-secret"
    set_telegram_offset(db_path, 200)

    updates_by_call: list[list[dict[str, object]]] = [
        [
            {
                "update_id": 201,
                "message": {
                    "message_id": 301,
                    "text": "/start",
                    "from": {"id": "daemon-user", "username": "daemon"},
                    "chat": {"id": chat_id, "type": "private"},
                },
            }
        ],
        [],
    ]

    def transport(url: str, payload: dict[str, object], timeout: int) -> dict[str, object]:
        if url.endswith("/getUpdates"):
            return {"ok": True, "result": updates_by_call.pop(0)}
        if url.endswith("/sendMessage"):
            return {"ok": True, "result": {"message_id": 9001, "chat": {"id": chat_id}}}
        raise AssertionError(url)

    env = {
        "INTEL_BRIEF_TELEGRAM_BOT_TOKEN": token,
        "INTEL_BRIEF_TELEGRAM_SANDBOX_SEND_ACK": TELEGRAM_SANDBOX_ACK_VALUE,
        "INTEL_BRIEF_TELEGRAM_LISTENER_ACK": "I_UNDERSTAND_REAL_TELEGRAM_LISTENER",
    }
    first = run_daemon_once(
        db_path=db_path,
        env=env,
        allow_real_network=True,
        allow_send_message=True,
        now="2026-07-08T16:30:00+00:00",
        evidence_dir=evidence_dir,
        heartbeat_path=heartbeat,
        transport=transport,
        limit=20,
        timeout_seconds=0,
    )
    second = run_daemon_once(
        db_path=db_path,
        env=env,
        allow_real_network=True,
        allow_send_message=True,
        now="2026-07-08T16:30:05+00:00",
        evidence_dir=evidence_dir,
        heartbeat_path=heartbeat,
        transport=transport,
        limit=20,
        timeout_seconds=0,
    )

    payload = json.loads(heartbeat.read_text(encoding="utf-8"))
    assert first["status"] == "success"
    assert second["status"] == "no_new_updates"
    assert payload["last_status"] == "no_new_updates"
    assert payload["last_start_menu_success_at"] == first["timestamp"]
    assert payload["last_start_menu_inline_keyboard_sent"] is True
    assert payload["last_start_menu_update_id_present"] is True
    saved = heartbeat.read_text(encoding="utf-8")
    assert token not in saved
    assert chat_id not in saved


def test_daemon_empty_polls_only_overwrite_atomic_snapshots(tmp_path):
    from scripts.intel_telegram_update_daemon import run_daemon_once

    db_path = tmp_path / "intel.db"
    heartbeat = tmp_path / "heartbeat.json"
    evidence_dir = tmp_path / "evidence"

    def transport(url: str, payload: dict[str, object], timeout: int) -> dict[str, object]:
        if url.endswith("/getUpdates"):
            return {"ok": True, "result": []}
        raise AssertionError(url)

    env = {
        "INTEL_BRIEF_TELEGRAM_BOT_TOKEN": "fake-token",
        "INTEL_BRIEF_TELEGRAM_SANDBOX_SEND_ACK": TELEGRAM_SANDBOX_ACK_VALUE,
        "INTEL_BRIEF_TELEGRAM_LISTENER_ACK": "I_UNDERSTAND_REAL_TELEGRAM_LISTENER",
    }
    for _ in range(2):
        result = run_daemon_once(
            db_path=db_path,
            env=env,
            allow_real_network=True,
            allow_send_message=True,
            now="2026-07-08T16:30:00+00:00",
            evidence_dir=evidence_dir,
            heartbeat_path=heartbeat,
            transport=transport,
            timeout_seconds=0,
        )
        assert result["status"] == "no_new_updates"

    events = [path for path in evidence_dir.iterdir() if path.name[0].isdigit()]
    assert events == []
    assert (evidence_dir / "latest-real-update-daemon.json").exists()
    assert json.loads(heartbeat.read_text(encoding="utf-8"))["last_status"] == "no_new_updates"
    assert list(evidence_dir.glob("*.tmp")) == []


def test_daemon_event_retention_expires_old_files_and_prioritizes_errors(tmp_path):
    from scripts.intel_telegram_update_daemon import (
        EVENT_MAX_FILES,
        EVENT_RETENTION_DAYS,
        _prune_event_files,
        _write_json,
    )

    evidence_dir = tmp_path / "evidence"
    now = datetime(2026, 8, 4, tzinfo=timezone.utc)  # noqa: UP017 - Python 3.10 worker compatibility
    fixtures = [
        ("20260601T000000000000Z-real-update-daemon.json", "failed", now - timedelta(days=31)),
        ("20260801T000000000001Z-real-update-daemon.json", "failed", now - timedelta(days=3)),
        ("20260802T000000000002Z-real-update-daemon.json", "blocked", now - timedelta(days=2)),
        ("20260803T000000000003Z-real-update-daemon.json", "failed", now - timedelta(days=1)),
        ("20260803T010000000004Z-real-update-daemon.json", "success", now - timedelta(hours=23)),
        ("20260803T020000000005Z-real-update-daemon.json", "success", now - timedelta(hours=22)),
    ]
    for name, status, modified_at in fixtures:
        path = evidence_dir / name
        _write_json(path, {"status": status})
        timestamp = modified_at.timestamp()
        os.utime(path, (timestamp, timestamp))

    result = _prune_event_files(evidence_dir, now=now, retention_days=30, max_files=3)

    remaining = {path.name for path in evidence_dir.iterdir()}
    assert EVENT_RETENTION_DAYS == 30
    assert EVENT_MAX_FILES == 2_000
    assert result == {"remaining": 3, "deleted_expired": 1, "deleted_overflow": 2}
    assert remaining == {
        "20260801T000000000001Z-real-update-daemon.json",
        "20260802T000000000002Z-real-update-daemon.json",
        "20260803T000000000003Z-real-update-daemon.json",
    }


def test_daemon_idle_log_is_throttled_but_status_changes_and_failures_are_logged():
    from scripts.intel_telegram_update_daemon import _should_log_poll

    idle = {"status": "no_new_updates"}
    assert _should_log_poll(idle, previous_status="no_new_updates", seconds_since_log=10, idle_log_seconds=300) is False
    assert _should_log_poll(idle, previous_status="success", seconds_since_log=10, idle_log_seconds=300) is True
    assert _should_log_poll(idle, previous_status="no_new_updates", seconds_since_log=300, idle_log_seconds=300) is True
    assert _should_log_poll({"status": "failed"}, previous_status="failed", seconds_since_log=1) is True


def test_daemon_lock_blocks_second_instance_before_loading_private_env(tmp_path, monkeypatch, capsys):
    from scripts import intel_telegram_update_daemon as daemon

    lock_path = tmp_path / "runtime" / "listener.lock"
    first = daemon.DaemonInstanceLock(lock_path)
    assert first.acquire() is True

    def fail_if_loaded(path: str) -> dict[str, str]:
        raise AssertionError(f"锁竞争时不得读取私有环境：{path}")

    monkeypatch.setattr(daemon, "load_private_env_file", fail_if_loaded)
    try:
        exit_code = daemon.run_loop(SimpleNamespace(lock_file=str(lock_path)))
    finally:
        first.release()

    blocked = json.loads(capsys.readouterr().out)
    assert exit_code == 3
    assert blocked == {
        "network_calls": 0,
        "reason": "listener_lock_held",
        "send_message_attempted": False,
        "status": "blocked",
    }
    assert stat.S_IMODE(lock_path.stat().st_mode) == 0o600
    assert lock_path.read_bytes() == b""


def test_daemon_lock_is_exclusive_across_processes_and_released_on_exit(tmp_path):
    lock_path = tmp_path / "runtime" / "listener.lock"
    clawbot_root = Path(__file__).resolve().parents[1]
    holder_code = "\n".join(
        [
            "import sys",
            "from scripts.intel_telegram_update_daemon import DaemonInstanceLock",
            "lock = DaemonInstanceLock(sys.argv[1])",
            "print('acquired' if lock.acquire() else 'blocked', flush=True)",
            "sys.stdin.readline()",
            "lock.release()",
        ]
    )
    contender_code = "\n".join(
        [
            "import sys",
            "from scripts.intel_telegram_update_daemon import DaemonInstanceLock",
            "lock = DaemonInstanceLock(sys.argv[1])",
            "acquired = lock.acquire()",
            "print('acquired' if acquired else 'blocked')",
            "lock.release()",
            "raise SystemExit(1 if acquired else 0)",
        ]
    )
    holder = subprocess.Popen(
        [sys.executable, "-c", holder_code, str(lock_path)],
        cwd=str(clawbot_root),
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        assert holder.stdout is not None
        assert holder.stdout.readline().strip() == "acquired"
        contender = subprocess.run(
            [sys.executable, "-c", contender_code, str(lock_path)],
            check=False,
            capture_output=True,
            cwd=str(clawbot_root),
            text=True,
            timeout=5,
        )
        assert contender.returncode == 0, contender.stderr
        assert contender.stdout.strip() == "blocked"
    finally:
        if holder.stdin is not None:
            holder.stdin.write("\n")
            holder.stdin.flush()
        holder.communicate(timeout=5)

    released = subprocess.run(
        [sys.executable, "-c", contender_code, str(lock_path)],
        check=False,
        capture_output=True,
        cwd=str(clawbot_root),
        text=True,
        timeout=5,
    )
    assert released.returncode == 1
    assert released.stdout.strip() == "acquired"


def test_daemon_launchagent_plist_uses_safe_paths(tmp_path):
    from scripts.intel_telegram_update_daemon import build_launchagent_plist

    plist = build_launchagent_plist(
        project_root=tmp_path,
        label="ai.openclaw.intel-brief.telegram-listener",
        interval_seconds=5,
        timeout_seconds=3,
    )

    assert "intel_telegram_update_daemon.py" in plist
    assert "ai.openclaw.intel-brief.telegram-listener" in plist
    assert "INTEL_BRIEF_TELEGRAM_LISTENER_ACK" in plist
    assert "intel-brief-telegram-listener.lock" in plist
    assert "KeepAlive" in plist
    assert str(tmp_path / "packages" / "clawbot" / ".venv312" / "bin" / "python") in plist
    assert str(tmp_path / ".openclaw" / "intel-brief.production.env") in plist
