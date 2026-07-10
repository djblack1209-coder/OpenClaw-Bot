"""常驻处理 Intel Brief Telegram 菜单消息。

这个脚本只负责把已经验证过的“一次处理 Telegram 新消息”循环起来：
- 收到 /start、/status、按钮点击时回复菜单/状态；
- 不保存原始聊天内容；
- 证据文件只写脱敏状态；
- 真实发送必须同时满足 token、ack、网络、sendMessage 四道闸。
"""

from __future__ import annotations

import argparse
import json
import signal
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = ROOT.parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.intel.private_env import default_private_env_path, load_private_env_file  # noqa: E402
from src.intel.telegram_delivery import TELEGRAM_SANDBOX_ACK_VALUE, TelegramBotApiSender, TelegramTransport  # noqa: E402
from src.intel.telegram_bot_runtime import TelegramBotApiRuntimeClient  # noqa: E402
from src.intel.telegram_update_processor import DEFAULT_BOT_PROFILE, process_telegram_updates_once  # noqa: E402

LISTENER_ACK_VALUE = "I_UNDERSTAND_REAL_TELEGRAM_LISTENER"

_STOP = False


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()  # noqa: UP017 - Python 3.10 worker compatibility


def _stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")  # noqa: UP017 - Python 3.10 worker compatibility


def _clean(value: Any) -> str:
    return str(value or "").strip()


def build_daemon_gate(
    env: dict[str, str] | None = None,
    *,
    allow_real_network: bool = False,
    allow_send_message: bool = False,
) -> dict[str, Any]:
    """返回常驻监听的脱敏安全闸结果。"""
    env_map = dict(env or {})
    token_present = bool(_clean(env_map.get("INTEL_BRIEF_TELEGRAM_BOT_TOKEN")))
    runtime_ack_ok = _clean(env_map.get("INTEL_BRIEF_TELEGRAM_SANDBOX_SEND_ACK")) == TELEGRAM_SANDBOX_ACK_VALUE
    listener_ack_ok = _clean(env_map.get("INTEL_BRIEF_TELEGRAM_LISTENER_ACK")) == LISTENER_ACK_VALUE
    missing: list[str] = []
    if not token_present:
        missing.append("telegram_bot_token_missing")
    if not runtime_ack_ok:
        missing.append("telegram_runtime_ack_missing")
    if not allow_real_network:
        missing.append("real_network_not_allowed")
    if not allow_send_message:
        missing.append("send_message_not_allowed")
    # 兼容旧私有环境：命令行显式开启真实网络和发送时，listener ack 可由 LaunchAgent 注入。
    if allow_real_network and allow_send_message and not listener_ack_ok:
        missing.append("telegram_listener_ack_missing")
    ready = not missing
    return {
        "status": "ready" if ready else "blocked",
        "ready": ready,
        "missing_gates": missing,
        "redacted_env": {
            "INTEL_BRIEF_TELEGRAM_BOT_TOKEN": token_present,
            "INTEL_BRIEF_TELEGRAM_SANDBOX_SEND_ACK": runtime_ack_ok,
            "INTEL_BRIEF_TELEGRAM_LISTENER_ACK": listener_ack_ok,
            "allow_real_network": bool(allow_real_network),
            "allow_send_message": bool(allow_send_message),
        },
    }


def _public_result(result: dict[str, Any]) -> dict[str, Any]:
    processor = result.get("processor") if isinstance(result.get("processor"), dict) else {}
    runtime = processor.get("runtime") if isinstance(processor.get("runtime"), dict) else {}
    return {
        "timestamp": result.get("timestamp") or _now_iso(),
        "status": result.get("status"),
        "bot_profile": result.get("bot_profile") or DEFAULT_BOT_PROFILE,
        "send_message_attempted": bool(result.get("send_message_attempted")),
        "send_success_count": int(result.get("send_success_count", 0) or 0),
        "network_calls": int(result.get("network_calls", 0) or 0),
        "previous_offset": processor.get("previous_offset"),
        "new_offset": processor.get("new_offset"),
        "fetched_update_count": int(processor.get("fetched_update_count", 0) or 0),
        "handled_count": int(runtime.get("handled_count", 0) or 0),
        "skipped_count": int(runtime.get("skipped_count", 0) or 0),
        "raw_updates_persisted": False,
    }


def _redact_processor(processor: dict[str, Any]) -> dict[str, Any]:
    """脱敏处理器结果，避免把 Telegram 用户标识写入证据文件。"""
    redacted = json.loads(json.dumps(processor, ensure_ascii=False))
    runtime = redacted.get("runtime") if isinstance(redacted.get("runtime"), dict) else {}
    handled = runtime.get("handled_updates") if isinstance(runtime.get("handled_updates"), list) else []
    for item in handled:
        if not isinstance(item, dict):
            continue
        value = item.pop("subscriber_user_id", "")
        item["subscriber_user_id_present"] = bool(_clean(value) or item.get("subscriber_user_id_present"))
    tracking_targets = runtime.get("tracking_targets") if isinstance(runtime.get("tracking_targets"), list) else []
    for target in tracking_targets:
        if isinstance(target, dict):
            target.pop("channel_user_id", None)
    return redacted


def _write_json(path: str | Path, payload: dict[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _read_json_dict(path: str | Path) -> dict[str, Any]:
    """读取已有 JSON 对象；读取失败时返回空对象。"""
    target = Path(path)
    if not target.exists():
        return {}
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _start_menu_success_from_processor(processor: dict[str, Any], *, timestamp: str) -> dict[str, Any]:
    """从脱敏 processor 里提取最近一次 /start 菜单发送成功证据。"""
    runtime = processor.get("runtime") if isinstance(processor.get("runtime"), dict) else {}
    handled = runtime.get("handled_updates") if isinstance(runtime.get("handled_updates"), list) else []
    for item in reversed(handled):
        if not isinstance(item, dict):
            continue
        if _clean(item.get("command")) != "start":
            continue
        if not bool(item.get("send_success")):
            continue
        if not bool(item.get("inline_keyboard_sent")):
            continue
        return {
            "last_start_menu_success_at": timestamp,
            "last_start_menu_reply_message_count": int(item.get("reply_message_count", 0) or 0),
            "last_start_menu_inline_keyboard_sent": bool(item.get("inline_keyboard_sent")),
            "last_start_menu_persistent_keyboard_sent": bool(item.get("persistent_keyboard_sent")),
            "last_start_menu_subscriber_user_id_present": bool(item.get("subscriber_user_id_present")),
            "last_start_menu_update_id_present": bool(item.get("update_id_present")),
            "last_start_menu_raw_content_persisted": False,
        }
    return {}


def _merge_heartbeat_with_start_menu_evidence(
    heartbeat_path: str | Path,
    payload: dict[str, Any],
    *,
    processor: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """写心跳前保留最近一次 /start 菜单成功证据。"""
    merged = dict(payload)
    previous = _read_json_dict(heartbeat_path)
    start_keys = [
        "last_start_menu_success_at",
        "last_start_menu_reply_message_count",
        "last_start_menu_inline_keyboard_sent",
        "last_start_menu_persistent_keyboard_sent",
        "last_start_menu_subscriber_user_id_present",
        "last_start_menu_update_id_present",
        "last_start_menu_raw_content_persisted",
    ]
    for key in start_keys:
        if key in previous and key not in merged:
            merged[key] = previous[key]
    if isinstance(processor, dict):
        current = _start_menu_success_from_processor(processor, timestamp=str(merged.get("updated_at") or _now_iso()))
        merged.update(current)
    return merged


def _blocked_result(*, db_path: str | Path, gate: dict[str, Any], bot_profile: str) -> dict[str, Any]:
    return {
        "timestamp": _now_iso(),
        "phase": "telegram-update-daemon",
        "scope": "intel_brief_realtime_start_menu_listener",
        "status": "blocked",
        "db_path": str(db_path),
        "bot_profile": _clean(bot_profile) or DEFAULT_BOT_PROFILE,
        "gate": gate,
        "processor": None,
        "network_calls": 0,
        "send_message_attempted": False,
        "send_success_count": 0,
        "raw_updates_persisted": False,
        "limits": [
            "不保存原始 Telegram 更新、聊天 ID、用户 ID 或消息正文。",
            "只有 token、运行确认、监听确认、真实网络和 sendMessage 开关同时存在才会发送。",
        ],
    }


def run_daemon_once(
    *,
    db_path: str | Path,
    env: dict[str, str],
    allow_real_network: bool,
    allow_send_message: bool,
    now: str,
    evidence_dir: str | Path,
    heartbeat_path: str | Path,
    transport: TelegramTransport | None = None,
    bot_profile: str = DEFAULT_BOT_PROFILE,
    limit: int = 20,
    timeout_seconds: int = 5,
) -> dict[str, Any]:
    """处理一轮 Telegram 更新并写入脱敏心跳。"""
    gate = build_daemon_gate(env, allow_real_network=allow_real_network, allow_send_message=allow_send_message)
    if not gate["ready"]:
        result = _blocked_result(db_path=db_path, gate=gate, bot_profile=bot_profile)
        heartbeat = _merge_heartbeat_with_start_menu_evidence(
            heartbeat_path,
            {"last_status": "blocked", "gate": gate, "updated_at": result["timestamp"]},
        )
        _write_json(heartbeat_path, heartbeat)
        _write_json(Path(evidence_dir) / "latest-real-update-daemon.json", result)
        return result

    token = _clean(env.get("INTEL_BRIEF_TELEGRAM_BOT_TOKEN"))
    client = TelegramBotApiRuntimeClient(token=token, transport=transport)
    sender = TelegramBotApiSender(token=token, transport=transport)
    processor = process_telegram_updates_once(
        db_path,
        client=client,
        sender=sender,
        now=now,
        bot_profile=bot_profile,
        limit=limit,
        timeout_seconds=timeout_seconds,
    )
    public_processor = _redact_processor(processor)
    runtime = processor.get("runtime") if isinstance(processor.get("runtime"), dict) else {}
    status = str(processor.get("status") or "failed")
    if status == "success" and int(runtime.get("handled_count", 0) or 0) == 0:
        status = "no_new_updates"
    result = {
        "timestamp": _now_iso(),
        "phase": "telegram-update-daemon",
        "scope": "intel_brief_realtime_start_menu_listener",
        "status": status,
        "db_path": str(db_path),
        "bot_profile": _clean(bot_profile) or DEFAULT_BOT_PROFILE,
        "gate": gate,
        "processor": public_processor,
        "network_calls": int(processor.get("network_calls", 0) or 0),
        "send_message_attempted": int(runtime.get("handled_count", 0) or 0) > 0,
        "send_success_count": int(runtime.get("send_success_count", 0) or 0),
        "raw_updates_persisted": False,
        "limits": [
            "Processes only Telegram updates above the persisted offset.",
            "Raw updates/chat ids/user ids/message text are not persisted in evidence.",
        ],
    }
    public = _public_result(result)
    _write_json(Path(evidence_dir) / "latest-real-update-daemon.json", result)
    _write_json(Path(evidence_dir) / f"{_stamp()}-real-update-daemon.json", public)
    heartbeat = _merge_heartbeat_with_start_menu_evidence(
        heartbeat_path,
        {
            "updated_at": public["timestamp"],
            "last_status": public["status"],
            "last_handled_count": public["handled_count"],
            "last_send_message_attempted": public["send_message_attempted"],
            "last_network_calls": public["network_calls"],
            "last_new_offset_present": public["new_offset"] not in (None, ""),
            "raw_updates_persisted": False,
        },
        processor=public_processor,
    )
    _write_json(heartbeat_path, heartbeat)
    return result


def build_launchagent_plist(
    *,
    project_root: str | Path,
    label: str = "ai.openclaw.intel-brief.telegram-listener",
    interval_seconds: int = 5,
    timeout_seconds: int = 5,
) -> str:
    """生成 macOS LaunchAgent plist 内容。"""
    root = Path(project_root).resolve()
    python = root / "packages" / "clawbot" / ".venv312" / "bin" / "python"
    script = root / "packages" / "clawbot" / "scripts" / "intel_telegram_update_daemon.py"
    db = root / "packages" / "clawbot" / "data" / "intel_brief.db"
    env_path = default_private_env_path(root)
    evidence_dir = root / "packages" / "clawbot" / "data" / "intel_evidence" / "phasefix" / "telegram-listener"
    heartbeat = evidence_dir / "heartbeat.json"
    stdout = Path.home() / "Library" / "Logs" / "OpenClaw" / "intel-brief-telegram-listener.stdout.log"
    stderr = Path.home() / "Library" / "Logs" / "OpenClaw" / "intel-brief-telegram-listener.stderr.log"
    interval = max(2, int(interval_seconds or 5))
    timeout = max(0, int(timeout_seconds or 5))
    return f'''<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>{label}</string>
  <key>ProgramArguments</key>
  <array>
    <string>{python}</string>
    <string>{script}</string>
    <string>--db</string>
    <string>{db}</string>
    <string>--env-path</string>
    <string>{env_path}</string>
    <string>--evidence-dir</string>
    <string>{evidence_dir}</string>
    <string>--heartbeat</string>
    <string>{heartbeat}</string>
    <string>--allow-real-network</string>
    <string>--allow-send-message</string>
    <string>--interval-seconds</string>
    <string>{interval}</string>
    <string>--timeout-seconds</string>
    <string>{timeout}</string>
  </array>
  <key>WorkingDirectory</key>
  <string>{root}</string>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <dict>
    <key>SuccessfulExit</key>
    <false/>
  </dict>
  <key>ThrottleInterval</key>
  <integer>10</integer>
  <key>EnvironmentVariables</key>
  <dict>
    <key>PATH</key>
    <string>{root}/packages/clawbot/.venv312/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>
    <key>LANG</key>
    <string>en_US.UTF-8</string>
    <key>PYTHONUNBUFFERED</key>
    <string>1</string>
    <key>INTEL_BRIEF_TELEGRAM_LISTENER_ACK</key>
    <string>{LISTENER_ACK_VALUE}</string>
  </dict>
  <key>StandardOutPath</key>
  <string>{stdout}</string>
  <key>StandardErrorPath</key>
  <string>{stderr}</string>
</dict>
</plist>
'''


def _install_launchagent(project_root: str | Path, *, label: str, interval_seconds: int, timeout_seconds: int) -> Path:
    plist_text = build_launchagent_plist(
        project_root=project_root,
        label=label,
        interval_seconds=interval_seconds,
        timeout_seconds=timeout_seconds,
    )
    launch_dir = Path.home() / "Library" / "LaunchAgents"
    launch_dir.mkdir(parents=True, exist_ok=True)
    plist_path = launch_dir / f"{label}.plist"
    plist_path.write_text(plist_text, encoding="utf-8")
    return plist_path


def _handle_signal(signum: int, frame: object) -> None:  # noqa: ARG001 - signal handler signature
    global _STOP
    _STOP = True


def run_loop(args: argparse.Namespace) -> int:
    env = load_private_env_file(args.env_path)
    env.update({k: v for k, v in {"INTEL_BRIEF_TELEGRAM_LISTENER_ACK": args.listener_ack}.items() if v})
    interval = max(2, int(args.interval_seconds or 5))
    print(json.dumps({"status": "listener_started", "interval_seconds": interval, "db": args.db}, ensure_ascii=False), flush=True)
    while not _STOP:
        result = run_daemon_once(
            db_path=args.db,
            env=env,
            allow_real_network=args.allow_real_network,
            allow_send_message=args.allow_send_message,
            now=_now_iso(),
            evidence_dir=args.evidence_dir,
            heartbeat_path=args.heartbeat,
            limit=args.limit,
            timeout_seconds=args.timeout_seconds,
        )
        public = _public_result(result)
        print(json.dumps(public, ensure_ascii=False, sort_keys=True), flush=True)
        if args.once:
            return 0 if public["status"] in {"success", "no_new_updates"} else 2
        time.sleep(interval)
    print(json.dumps({"status": "listener_stopped", "timestamp": _now_iso()}, ensure_ascii=False), flush=True)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run Intel Brief Telegram update listener daemon")
    parser.add_argument("--db", default=str(ROOT / "data" / "intel_brief.db"))
    parser.add_argument("--env-path", default=str(default_private_env_path(PROJECT_ROOT)))
    parser.add_argument("--evidence-dir", default=str(ROOT / "data" / "intel_evidence" / "phasefix" / "telegram-listener"))
    parser.add_argument("--heartbeat", default=str(ROOT / "data" / "intel_evidence" / "phasefix" / "telegram-listener" / "heartbeat.json"))
    parser.add_argument("--allow-real-network", action="store_true")
    parser.add_argument("--allow-send-message", action="store_true")
    parser.add_argument("--listener-ack", default=LISTENER_ACK_VALUE)
    parser.add_argument("--interval-seconds", type=int, default=5)
    parser.add_argument("--timeout-seconds", type=int, default=5)
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--install-launchagent", action="store_true")
    parser.add_argument("--label", default="ai.openclaw.intel-brief.telegram-listener")
    args = parser.parse_args(argv)

    if args.install_launchagent:
        plist = _install_launchagent(
            PROJECT_ROOT,
            label=args.label,
            interval_seconds=args.interval_seconds,
            timeout_seconds=args.timeout_seconds,
        )
        print(json.dumps({"status": "installed", "plist": str(plist), "label": args.label}, ensure_ascii=False, sort_keys=True))
        return 0

    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)
    return run_loop(args)


if __name__ == "__main__":
    raise SystemExit(main())
