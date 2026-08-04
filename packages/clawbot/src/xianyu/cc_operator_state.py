"""CC中转本机运营开关状态。

这个模块只保存本机操作台的人工控制状态，例如“暂停自动发货”。
它不保存卡密、Token、买家信息或闲鱼 Cookie。
"""

from __future__ import annotations

import json
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from src.cross_process_lock import cross_process_file_lock


def _project_root() -> Path:
    """定位 OpenEverything 项目根目录。"""
    return Path(__file__).resolve().parents[4]


def operator_state_file() -> Path:
    """返回本机运营状态文件路径；测试可用环境变量隔离。"""
    override = os.getenv("CC_OPERATOR_STATE_FILE", "").strip()
    if override:
        return Path(override).expanduser()
    return _project_root() / ".openclaw" / "cc-zhongzhuan-operator-state.json"


def _env_pause_default() -> bool:
    """读取环境变量中的兜底暂停状态。"""
    raw = os.getenv("CC_XIANYU_AUTO_SHIP_PAUSED", "").strip().lower()
    return raw not in {"0", "false", "no", "off"}


def _operator_state_lock():
    """返回运营状态专用的跨线程、跨进程可重入锁。"""
    path = operator_state_file()
    return cross_process_file_lock(path.with_name(f".{path.name}.lock"))


def _now_iso() -> str:
    """返回用于状态记录的 UTC 时间。"""
    return datetime.now(UTC).isoformat(timespec="seconds")


def _parse_iso(value: str) -> datetime | None:
    """解析状态文件里的 UTC 时间，解析失败时返回空。"""
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def _write_operator_state(state: dict[str, Any]) -> dict[str, Any]:
    """在独占锁内原子替换运营状态文件。"""
    path = operator_state_file()
    with _operator_state_lock():
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        descriptor, temp_name = tempfile.mkstemp(
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
        )
        temp_path = Path(temp_name)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                json.dump(state, handle, ensure_ascii=False, indent=2)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_path, path)
            if os.name != "nt":
                directory_fd = os.open(path.parent, os.O_RDONLY)
                try:
                    os.fsync(directory_fd)
                finally:
                    os.close(directory_fd)
        finally:
            temp_path.unlink(missing_ok=True)
    return state


def _normalize_auto_resume_canary(value: Any) -> dict[str, Any]:
    """规整“恢复后首单观察票”，恢复自动发货后最多放行 1 单再自动暂停。"""
    payload = value if isinstance(value, dict) else {}
    remaining = int(payload.get("remaining") or 0)
    active = bool(payload.get("active")) and remaining > 0
    return {
        "active": active,
        "remaining": max(0, remaining),
        "armed_at": payload.get("armed_at") or None,
        "consumed_at": payload.get("consumed_at") or None,
        "last_order_id": str(payload.get("last_order_id") or "")[:120],
        "reason": str(payload.get("reason") or "")[:200],
        "updated_by": str(payload.get("updated_by") or "local-operator")[:80],
    }


def _normalize_one_shot(value: Any) -> dict[str, Any]:
    """规整“单次发卡放行票”，过期或次数用完时保持可读但标记 inactive。"""
    payload = value if isinstance(value, dict) else {}
    remaining = int(payload.get("remaining") or 0)
    expires_at = str(payload.get("expires_at") or "")
    expires_dt = _parse_iso(expires_at)
    active = remaining > 0 and bool(expires_dt and expires_dt > datetime.now(UTC))
    return {
        "active": active,
        "remaining": max(0, remaining),
        "expires_at": expires_at,
        "created_at": payload.get("created_at") or None,
        "consumed_at": payload.get("consumed_at") or None,
        "reason": str(payload.get("reason") or "")[:200],
        "updated_by": str(payload.get("updated_by") or "local-operator")[:80],
    }


def get_operator_state() -> dict[str, Any]:
    """读取本机运营状态，缺失或损坏时返回安全默认值。"""
    default = {
        "auto_ship_paused": _env_pause_default(),
        "pause_reason": "",
        "updated_at": None,
        "updated_by": "local-operator",
        "one_shot_delivery": _normalize_one_shot({}),
        "auto_resume_canary": _normalize_auto_resume_canary({}),
    }
    path = operator_state_file()
    with _operator_state_lock():
        try:
            if not path.exists():
                return default
            payload = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                return default
        except (OSError, json.JSONDecodeError):
            return default
    return {
        **default,
        "auto_ship_paused": bool(payload.get("auto_ship_paused", default["auto_ship_paused"])),
        "pause_reason": str(payload.get("pause_reason") or "")[:200],
        "updated_at": payload.get("updated_at") or default["updated_at"],
        "updated_by": str(payload.get("updated_by") or default["updated_by"])[:80],
        "one_shot_delivery": _normalize_one_shot(payload.get("one_shot_delivery")),
        "auto_resume_canary": _normalize_auto_resume_canary(payload.get("auto_resume_canary")),
    }


def is_auto_ship_paused() -> bool:
    """判断自动发货是否被本机操作台暂停。"""
    return bool(get_operator_state().get("auto_ship_paused"))


def set_auto_ship_paused(paused: bool, reason: str = "", resume_canary: bool = False) -> dict[str, Any]:
    """保存自动发货暂停/恢复状态；恢复时可开启首单观察票。"""
    with _operator_state_lock():
        existing = get_operator_state()
        one_shot = existing.get("one_shot_delivery") if paused else {}
        canary = {}
        if not paused and resume_canary:
            canary = {
                "active": True,
                "remaining": 1,
                "armed_at": _now_iso(),
                "consumed_at": None,
                "last_order_id": "",
                "reason": (reason or "恢复自动发货后首单自动暂停观察")[:200],
                "updated_by": "local-operator",
            }
        state = {
            "auto_ship_paused": bool(paused),
            "pause_reason": (reason or ("手动暂停" if paused else "手动恢复"))[:200],
            "updated_at": _now_iso(),
            "updated_by": "local-operator",
            "one_shot_delivery": _normalize_one_shot(one_shot),
            "auto_resume_canary": _normalize_auto_resume_canary(canary),
        }
        return _write_operator_state(state)


def consume_auto_resume_canary_after_sent(order_id: str = "") -> dict[str, Any]:
    """首单观察票被真正发卡成功消耗后，自动重新暂停常驻自动发货。"""
    with _operator_state_lock():
        state = get_operator_state()
        canary = _normalize_auto_resume_canary(state.get("auto_resume_canary"))
        if not canary.get("active"):
            return {"paused": False, "reason": "auto_resume_canary_not_active", "auto_resume_canary": canary}
        canary["remaining"] = max(0, int(canary.get("remaining") or 0) - 1)
        canary["active"] = canary["remaining"] > 0
        canary["consumed_at"] = _now_iso()
        canary["last_order_id"] = str(order_id or "")[:120]
        state["auto_ship_paused"] = True
        state["pause_reason"] = "恢复后首单已发送，系统自动暂停观察，防止连续发卡"
        state["updated_at"] = _now_iso()
        state["updated_by"] = "local-operator"
        state["one_shot_delivery"] = _normalize_one_shot({})
        state["auto_resume_canary"] = canary
        _write_operator_state(state)
        return {"paused": True, "reason": "auto_resume_canary_consumed", "auto_resume_canary": canary}


def authorize_one_shot_delivery(reason: str = "", ttl_seconds: int = 180) -> dict[str, Any]:
    """在暂停状态下放行一次浏览器发卡；过期后自动失效。"""
    ttl = max(30, min(int(ttl_seconds or 180), 600))
    now = datetime.now(UTC)
    with _operator_state_lock():
        state = get_operator_state()
        state.update(
            {
                "auto_ship_paused": True,
                "pause_reason": (state.get("pause_reason") or "保持暂停，仅单次放行")[:200],
                "updated_at": _now_iso(),
                "updated_by": "local-operator",
                "one_shot_delivery": {
                    "active": True,
                    "remaining": 1,
                    "expires_at": (now.replace(microsecond=0).timestamp() + ttl),
                    "created_at": _now_iso(),
                    "consumed_at": None,
                    "reason": (reason or "老板确认当前真实已付款页，单次发卡")[:200],
                    "updated_by": "local-operator",
                },
            }
        )
        # 先用时间戳计算，再转成 ISO，避免引入额外依赖。
        expires_at = datetime.fromtimestamp(
            float(state["one_shot_delivery"]["expires_at"]),
            UTC,
        ).isoformat(timespec="seconds")
        state["one_shot_delivery"]["expires_at"] = expires_at
        return _write_operator_state(state)


def peek_one_shot_delivery() -> dict[str, Any]:
    """只读查看当前是否存在有效的单次发卡放行票。"""
    return get_operator_state().get("one_shot_delivery") or _normalize_one_shot({})


def consume_one_shot_delivery(reason: str = "") -> dict[str, Any]:
    """消费一次单次放行票；没有有效票时返回 allowed=False。"""
    with _operator_state_lock():
        state = get_operator_state()
        one_shot = _normalize_one_shot(state.get("one_shot_delivery"))
        if not one_shot.get("active"):
            return {
                "allowed": False,
                "reason": "one_shot_delivery_not_active",
                "one_shot_delivery": one_shot,
            }
        one_shot["remaining"] = max(0, int(one_shot.get("remaining") or 0) - 1)
        one_shot["active"] = one_shot["remaining"] > 0
        one_shot["consumed_at"] = _now_iso()
        if reason:
            one_shot["reason"] = str(reason)[:200]
        state["one_shot_delivery"] = one_shot
        state["updated_at"] = _now_iso()
        state["updated_by"] = "local-operator"
        _write_operator_state(state)
        return {
            "allowed": True,
            "reason": "one_shot_delivery_consumed",
            "one_shot_delivery": one_shot,
        }
