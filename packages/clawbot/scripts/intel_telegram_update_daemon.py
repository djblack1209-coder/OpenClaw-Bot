"""常驻处理 Intel Brief Telegram 菜单消息。

这个脚本只负责把已经验证过的“一次处理 Telegram 新消息”循环起来：
- 收到 /start、/status、按钮点击时回复菜单/状态；
- 不保存原始聊天内容；
- 证据文件只写脱敏状态；
- 真实发送必须同时满足 token、ack、网络、sendMessage 四道闸。
"""

from __future__ import annotations

import argparse
import errno
import json
import os
import signal
import sys
import tempfile
import threading
import time
from contextlib import suppress
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, BinaryIO

ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = ROOT.parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.intel.private_env import default_private_env_path, load_private_env_file  # noqa: E402
from src.intel.telegram_bot_runtime import TelegramBotApiRuntimeClient  # noqa: E402
from src.intel.telegram_delivery import (  # noqa: E402
    TELEGRAM_SANDBOX_ACK_VALUE,
    TelegramBotApiSender,
    TelegramTransport,
)
from src.intel.telegram_update_processor import DEFAULT_BOT_PROFILE, process_telegram_updates_once  # noqa: E402

LISTENER_ACK_VALUE = "I_UNDERSTAND_REAL_TELEGRAM_LISTENER"
EVENT_FILE_SUFFIX = "-real-update-daemon.json"
EVENT_RETENTION_DAYS = 30
EVENT_MAX_FILES = 2_000
RETENTION_CHECK_SECONDS = 3_600
IDLE_LOG_SECONDS = 300
HEALTHY_STATUSES = {"success", "no_new_updates"}
LISTENER_LOCK_FILENAME = "intel-brief-telegram-listener.lock"

_STOP = False
_HELD_LOCK_PATHS: set[Path] = set()
_HELD_LOCK_PATHS_GUARD = threading.Lock()


def default_listener_lock_path() -> Path:
    """返回仅当前系统用户可访问的 listener 运行锁路径。"""
    return Path.home() / ".openclaw" / "locks" / LISTENER_LOCK_FILENAME


def _try_acquire_native_lock(handle: BinaryIO) -> bool:
    """非阻塞获取原生文件锁；锁已被占用时立即返回。"""
    if os.name == "nt":
        import msvcrt

        handle.seek(0, os.SEEK_END)
        if handle.tell() == 0:
            handle.write(b"\0")
            handle.flush()
        try:
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError as exc:
            if exc.errno in {errno.EACCES, errno.EAGAIN, errno.EDEADLK}:
                return False
            raise
        return True

    import fcntl

    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as exc:
        if exc.errno in {errno.EACCES, errno.EAGAIN}:
            return False
        raise
    return True


def _release_native_lock(handle: BinaryIO) -> None:
    """释放当前平台的 listener 原生文件锁。"""
    if os.name == "nt":
        import msvcrt

        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        return

    import fcntl

    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


class DaemonInstanceLock:
    """用非阻塞文件锁保证每位系统用户只有一个 Telegram listener。"""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path).expanduser().resolve()
        self._handle: BinaryIO | None = None

    def acquire(self) -> bool:
        """立即尝试获取独占锁，不等待另一个 listener 退出。"""
        with _HELD_LOCK_PATHS_GUARD:
            if self.path in _HELD_LOCK_PATHS:
                return False
            _HELD_LOCK_PATHS.add(self.path)

        descriptor: int | None = None
        handle: BinaryIO | None = None
        try:
            self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            descriptor = os.open(self.path, os.O_CREAT | os.O_RDWR, 0o600)
            os.fchmod(descriptor, 0o600)
            handle = os.fdopen(descriptor, "r+b", buffering=0)
            descriptor = None
            if not _try_acquire_native_lock(handle):
                handle.close()
                handle = None
                with _HELD_LOCK_PATHS_GUARD:
                    _HELD_LOCK_PATHS.discard(self.path)
                return False
            self._handle = handle
            return True
        except Exception:
            if handle is not None:
                handle.close()
            elif descriptor is not None:
                os.close(descriptor)
            with _HELD_LOCK_PATHS_GUARD:
                _HELD_LOCK_PATHS.discard(self.path)
            raise

    def release(self) -> None:
        """释放已持有的 listener 锁；重复释放保持幂等。"""
        handle = self._handle
        if handle is None:
            return
        try:
            _release_native_lock(handle)
        finally:
            handle.close()
            self._handle = None
            with _HELD_LOCK_PATHS_GUARD:
                _HELD_LOCK_PATHS.discard(self.path)

    def __enter__(self) -> DaemonInstanceLock:
        if not self.acquire():
            raise RuntimeError("listener_lock_held")
        return self

    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> None:
        self.release()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()  # noqa: UP017 - Python 3.10 worker compatibility


def _stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")  # noqa: UP017 - Python 3.10 worker compatibility


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
    """在目标目录内原子替换 JSON，避免读方看到半写文件。"""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=str(target.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, target)
    except Exception:
        with suppress(OSError):
            os.unlink(temp_name)
        raise


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


def _event_files(evidence_dir: str | Path) -> list[Path]:
    """返回时间戳事件文件，不把 latest 快照算入事件。"""
    root = Path(evidence_dir)
    if not root.exists():
        return []
    return [
        path
        for path in root.iterdir()
        if path.is_file() and path.name != "latest-real-update-daemon.json" and path.name.endswith(EVENT_FILE_SUFFIX)
    ]


def _is_error_event(path: Path) -> bool:
    """损坏或非健康状态按错误事件处理，优先保留用于排障。"""
    payload = _read_json_dict(path)
    return _clean(payload.get("status")) not in HEALTHY_STATUSES


def _prune_event_files(
    evidence_dir: str | Path,
    *,
    now: datetime | None = None,
    retention_days: int = EVENT_RETENTION_DAYS,
    max_files: int = EVENT_MAX_FILES,
) -> dict[str, int]:
    """删除过期事件并按错误优先策略把事件总量压到上限。"""
    current = now or datetime.now(timezone.utc)  # noqa: UP017 - Python 3.10 worker compatibility
    cutoff = current.timestamp() - timedelta(days=max(1, int(retention_days))).total_seconds()
    deleted_expired = 0
    deleted_overflow = 0
    survivors: list[Path] = []
    for path in _event_files(evidence_dir):
        try:
            modified_at = path.stat().st_mtime
        except OSError:
            continue
        if modified_at < cutoff:
            try:
                path.unlink()
                deleted_expired += 1
            except OSError:
                continue
        else:
            survivors.append(path)

    file_limit = max(1, int(max_files))
    if len(survivors) > file_limit:
        errors = sorted(
            (path for path in survivors if _is_error_event(path)), key=lambda path: path.stat().st_mtime, reverse=True
        )
        normal = sorted(
            (path for path in survivors if path not in errors), key=lambda path: path.stat().st_mtime, reverse=True
        )
        keep = set(errors[:file_limit])
        keep.update(normal[: max(0, file_limit - len(keep))])
        for path in survivors:
            if path in keep:
                continue
            try:
                path.unlink()
                deleted_overflow += 1
            except OSError:
                continue
        survivors = list(keep)
    return {
        "remaining": len(survivors),
        "deleted_expired": deleted_expired,
        "deleted_overflow": deleted_overflow,
    }


def _should_write_event(public: dict[str, Any], previous_heartbeat: dict[str, Any]) -> bool:
    """只为状态变化、真实更新或失败建立不可变事件。"""
    status = _clean(public.get("status"))
    previous_status = _clean(previous_heartbeat.get("last_status"))
    status_changed = bool(previous_status) and status != previous_status
    has_updates = int(public.get("fetched_update_count", 0) or 0) > 0 or int(public.get("handled_count", 0) or 0) > 0
    is_failure = status not in HEALTHY_STATUSES
    return status_changed or has_updates or is_failure


def _retention_due(previous_heartbeat: dict[str, Any], *, now: datetime) -> bool:
    """事件清理最多每小时扫描一次，避免空轮询反复遍历目录。"""
    value = _clean(previous_heartbeat.get("last_retention_at"))
    if not value:
        return True
    try:
        previous = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return True
    if previous.tzinfo is None:
        previous = previous.replace(tzinfo=timezone.utc)  # noqa: UP017 - Python 3.10 worker compatibility
    return (now - previous.astimezone(timezone.utc)).total_seconds() >= RETENTION_CHECK_SECONDS  # noqa: UP017 - Python 3.10 worker compatibility


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
    preserved_keys = [
        "last_start_menu_success_at",
        "last_start_menu_reply_message_count",
        "last_start_menu_inline_keyboard_sent",
        "last_start_menu_persistent_keyboard_sent",
        "last_start_menu_subscriber_user_id_present",
        "last_start_menu_update_id_present",
        "last_start_menu_raw_content_persisted",
        "last_event_at",
        "last_event_status",
        "last_retention_at",
        "event_file_count",
        "last_retention_deleted_expired",
        "last_retention_deleted_overflow",
    ]
    for key in preserved_keys:
        if key in previous and key not in merged:
            merged[key] = previous[key]
    if isinstance(processor, dict):
        current = _start_menu_success_from_processor(processor, timestamp=str(merged.get("updated_at") or _now_iso()))
        merged.update(current)
    return merged


def _persist_daemon_artifacts(
    *,
    result: dict[str, Any],
    evidence_dir: str | Path,
    heartbeat_path: str | Path,
    processor: dict[str, Any] | None = None,
) -> None:
    """原子覆盖 latest/heartbeat，并按治理规则写入和清理事件。"""
    evidence_root = Path(evidence_dir)
    previous_heartbeat = _read_json_dict(heartbeat_path)
    public = _public_result(result)
    _write_json(evidence_root / "latest-real-update-daemon.json", result)
    event_written = _should_write_event(public, previous_heartbeat)
    event_timestamp = _clean(public.get("timestamp")) or _now_iso()
    if event_written:
        _write_json(evidence_root / f"{_stamp()}{EVENT_FILE_SUFFIX}", public)

    current_time = datetime.now(timezone.utc)  # noqa: UP017 - Python 3.10 worker compatibility
    retention: dict[str, int] | None = None
    if event_written or _retention_due(previous_heartbeat, now=current_time):
        retention = _prune_event_files(evidence_root, now=current_time)

    heartbeat_payload: dict[str, Any] = {
        "updated_at": event_timestamp,
        "last_status": public["status"],
        "last_handled_count": public["handled_count"],
        "last_send_message_attempted": public["send_message_attempted"],
        "last_network_calls": public["network_calls"],
        "last_new_offset_present": public["new_offset"] not in (None, ""),
        "raw_updates_persisted": False,
    }
    if result.get("gate"):
        heartbeat_payload["gate"] = result["gate"]
    if event_written:
        heartbeat_payload["last_event_at"] = event_timestamp
        heartbeat_payload["last_event_status"] = public["status"]
    if retention is not None:
        heartbeat_payload.update(
            {
                "last_retention_at": current_time.isoformat(),
                "event_file_count": retention["remaining"],
                "last_retention_deleted_expired": retention["deleted_expired"],
                "last_retention_deleted_overflow": retention["deleted_overflow"],
            }
        )
    heartbeat = _merge_heartbeat_with_start_menu_evidence(
        heartbeat_path,
        heartbeat_payload,
        processor=processor,
    )
    _write_json(heartbeat_path, heartbeat)


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
        _persist_daemon_artifacts(
            result=result,
            evidence_dir=evidence_dir,
            heartbeat_path=heartbeat_path,
        )
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
    _persist_daemon_artifacts(
        result=result,
        evidence_dir=evidence_dir,
        heartbeat_path=heartbeat_path,
        processor=public_processor,
    )
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
    lock_file = default_listener_lock_path()
    stdout = Path.home() / "Library" / "Logs" / "OpenClaw" / "intel-brief-telegram-listener.stdout.log"
    stderr = Path.home() / "Library" / "Logs" / "OpenClaw" / "intel-brief-telegram-listener.stderr.log"
    interval = max(2, int(interval_seconds or 5))
    timeout = max(0, int(timeout_seconds or 5))
    return f"""<?xml version="1.0" encoding="UTF-8"?>
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
    <string>--lock-file</string>
    <string>{lock_file}</string>
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
"""


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


def _handle_signal(signum: int, frame: object) -> None:
    global _STOP
    _STOP = True


def _should_log_poll(
    public: dict[str, Any],
    *,
    previous_status: str,
    seconds_since_log: float,
    idle_log_seconds: int = IDLE_LOG_SECONDS,
) -> bool:
    """空轮询只在状态变化或节流窗口到期时输出一行日志。"""
    status = _clean(public.get("status"))
    if status != "no_new_updates":
        return True
    if status != _clean(previous_status):
        return True
    return seconds_since_log >= max(1, int(idle_log_seconds))


def run_loop(args: argparse.Namespace) -> int:
    lock_path = getattr(args, "lock_file", None) or default_listener_lock_path()
    instance_lock = DaemonInstanceLock(lock_path)
    if not instance_lock.acquire():
        print(
            json.dumps(
                {
                    "status": "blocked",
                    "reason": "listener_lock_held",
                    "network_calls": 0,
                    "send_message_attempted": False,
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
            flush=True,
        )
        return 3

    try:
        env = load_private_env_file(args.env_path)
        env.update({k: v for k, v in {"INTEL_BRIEF_TELEGRAM_LISTENER_ACK": args.listener_ack}.items() if v})
        interval = max(2, int(args.interval_seconds or 5))
        idle_log_seconds = max(1, int(getattr(args, "idle_log_seconds", IDLE_LOG_SECONDS) or IDLE_LOG_SECONDS))
        last_log_at = time.monotonic()
        last_status = ""
        print(
            json.dumps({"status": "listener_started", "interval_seconds": interval, "db": args.db}, ensure_ascii=False),
            flush=True,
        )
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
            current_monotonic = time.monotonic()
            if _should_log_poll(
                public,
                previous_status=last_status,
                seconds_since_log=current_monotonic - last_log_at,
                idle_log_seconds=idle_log_seconds,
            ):
                print(json.dumps(public, ensure_ascii=False, sort_keys=True), flush=True)
                last_log_at = current_monotonic
            last_status = _clean(public.get("status"))
            if args.once:
                return 0 if public["status"] in {"success", "no_new_updates"} else 2
            time.sleep(interval)
        print(json.dumps({"status": "listener_stopped", "timestamp": _now_iso()}, ensure_ascii=False), flush=True)
        return 0
    finally:
        instance_lock.release()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run Intel Brief Telegram update listener daemon")
    parser.add_argument("--db", default=str(ROOT / "data" / "intel_brief.db"))
    parser.add_argument("--env-path", default=str(default_private_env_path(PROJECT_ROOT)))
    parser.add_argument(
        "--evidence-dir", default=str(ROOT / "data" / "intel_evidence" / "phasefix" / "telegram-listener")
    )
    parser.add_argument(
        "--heartbeat",
        default=str(ROOT / "data" / "intel_evidence" / "phasefix" / "telegram-listener" / "heartbeat.json"),
    )
    parser.add_argument("--lock-file", default=str(default_listener_lock_path()))
    parser.add_argument("--allow-real-network", action="store_true")
    parser.add_argument("--allow-send-message", action="store_true")
    parser.add_argument("--listener-ack", default=LISTENER_ACK_VALUE)
    parser.add_argument("--interval-seconds", type=int, default=5)
    parser.add_argument("--timeout-seconds", type=int, default=5)
    parser.add_argument("--idle-log-seconds", type=int, default=IDLE_LOG_SECONDS)
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
        print(
            json.dumps(
                {"status": "installed", "plist": str(plist), "label": args.label}, ensure_ascii=False, sort_keys=True
            )
        )
        return 0

    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)
    return run_loop(args)


if __name__ == "__main__":
    raise SystemExit(main())
