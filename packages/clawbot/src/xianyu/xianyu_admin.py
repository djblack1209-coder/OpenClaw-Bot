"""闲鱼 Web 管理面板 — 搬运自 GuDong2003/xianyu-auto-reply-fix

功能:
- 对话历史查看 (按 chat_id 分组)
- 每日统计 dashboard
- 商品管理 (查看缓存的商品信息)
- 订单列表
- 实时状态 (WebSocket 连接状态、Cookie 健康)
- Prompt 热更新

搬运适配:
- 复用现有 XianyuContextManager (SQLite)
- 复用现有 XianyuReplyBot (prompt reload)
- 不引入新数据库，零额外依赖 (FastAPI 已在 kiro-gateway 中使用)
"""

import contextlib
import hashlib
import hmac
import json
import logging
import os
import re
import secrets
import subprocess
import threading
import time
from collections.abc import Mapping
from datetime import timedelta
from pathlib import Path
from urllib.parse import parse_qsl, unquote, urlsplit

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from src.api.auth import log_token_status
from src.api.error_utils import safe_error as _safe_error
from src.core.loop_owner import OwnerLoopNotReady, OwnerLoopTimeout
from src.utils import now_et, scrub_secrets
from src.xianyu.cc_operator_state import (
    authorize_one_shot_delivery,
    consume_auto_resume_canary_after_sent,
    consume_one_shot_delivery,
    get_operator_state,
    peek_one_shot_delivery,
    set_auto_ship_paused,
)

from .operations_projection import project_operations
from .xianyu_apis import XianyuApis

logger = logging.getLogger(__name__)
_EMPTY_LIVE_RUNTIME_SNAPSHOT = {
    "ws_connected": False,
    "cookie_ok": False,
    "last_heartbeat": 0.0,
    "token_ts": 0.0,
    "manual_chats": 0,
}
_ADMIN_SESSION_COOKIE = "xianyu_admin_session"
_ADMIN_SESSION_TTL_SECONDS = 900
_ADMIN_SESSION_MAX_ACTIVE = 128
_admin_sessions: dict[str, float] = {}
_admin_sessions_lock = threading.Lock()
_last_cc_strict_audit: dict = {}
_last_cc_readiness_audit: dict = {}
_strict_audit_loop_started = False
_strict_audit_loop_lock = threading.Lock()
_strict_audit_run_lock = threading.Lock()
_readiness_audit_loop_started = False
_readiness_audit_loop_lock = threading.Lock()
_readiness_audit_run_lock = threading.Lock()
_ops_notify_loop_started = False
_ops_notify_loop_lock = threading.Lock()
_ops_notify_run_lock = threading.Lock()
_last_background_strict_audit_at = 0.0
_last_background_strict_audit_result: dict = {}
_last_background_readiness_audit_at = 0.0
_last_ops_notify_signature = ""
_last_ops_notify_at = 0.0
_last_ops_notify_result: dict = {}
_SOCIAL_EXTENSION_STATUS_FILE = Path(
    os.getenv(
        "OPENCLAW_SOCIAL_EXTENSION_STATUS_FILE",
        str(Path(__file__).resolve().parents[2] / "data" / "social_extension_status.json"),
    )
)
_SOCIAL_PILOT_EXTENSION_NAME = "OpenEverything Social Pilot"
_SOCIAL_PILOT_EXTENSION_DIR = Path(__file__).resolve().parents[3] / "openclaw-npm" / "assets" / "chrome-extension"

app = FastAPI(
    title="闲鱼管理面板",
    version="1.0",
)
app.state.bind_host = None
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:1420", "tauri://localhost"],
    allow_origin_regex=r"^chrome-extension://[a-p]{32}$",
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
    allow_headers=["X-API-Token", "Content-Type", "Authorization"],
)
_XIANYU_STATIC_DIR = Path(__file__).resolve().parent / "static"
if _XIANYU_STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(_XIANYU_STATIC_DIR)), name="xianyu-static")


def _expected_api_token() -> str:
    """读取当前进程内 API Token；兼容测试里直接 monkeypatch 的 auth 模块变量。"""
    try:
        from src.api import auth

        return getattr(auth, "_API_TOKEN", "") or os.getenv("OPENCLAW_API_TOKEN", "")
    except Exception:
        return os.getenv("OPENCLAW_API_TOKEN", "")


def _issue_admin_session() -> tuple[str, int]:
    """签发仅供闲鱼管理面使用的短时随机会话。"""
    now = time.monotonic()
    session_token = secrets.token_urlsafe(32)
    with _admin_sessions_lock:
        expired = [token for token, expires_at in _admin_sessions.items() if expires_at <= now]
        for token in expired:
            _admin_sessions.pop(token, None)
        if len(_admin_sessions) >= _ADMIN_SESSION_MAX_ACTIVE:
            raise HTTPException(status_code=429, detail="短时管理会话已达上限，请稍后重试")
        _admin_sessions[session_token] = now + _ADMIN_SESSION_TTL_SECONDS
    return session_token, _ADMIN_SESSION_TTL_SECONDS


def _admin_session_is_valid(session_token: str) -> bool:
    """校验短时管理会话并清理过期记录，不做滑动续期。"""
    if not session_token:
        return False
    now = time.monotonic()
    with _admin_sessions_lock:
        expires_at = _admin_sessions.get(session_token, 0.0)
        if expires_at <= now:
            _admin_sessions.pop(session_token, None)
            return False
        return True


def _admin_session_write_is_same_origin(request: Request) -> bool:
    """Cookie 会话的写请求必须携带与当前管理面完全一致的 Origin。"""
    if request.method in {"GET", "HEAD", "OPTIONS"}:
        return True
    origin = request.headers.get("origin", "").strip().rstrip("/").lower()
    expected = f"{request.url.scheme}://{request.url.netloc}".rstrip("/").lower()
    return bool(origin and hmac.compare_digest(origin, expected))


def _live_runtime_snapshot() -> dict[str, bool | float | int]:
    """只通过 owner 边界读取闲鱼实时状态；失败时按离线状态关闭售卖门。"""
    live = _live
    if live is None:
        return dict(_EMPTY_LIVE_RUNTIME_SNAPSHOT)
    snapshot_reader = getattr(live, "runtime_snapshot_sync", None)
    if not callable(snapshot_reader):
        logger.warning("[XianyuAdmin] 闲鱼实时服务未提供 owner 运行快照，按离线处理")
        return dict(_EMPTY_LIVE_RUNTIME_SNAPSHOT)
    try:
        snapshot = snapshot_reader(timeout=5.0)
    except (OwnerLoopNotReady, OwnerLoopTimeout) as e:
        logger.warning("[XianyuAdmin] 闲鱼 owner 运行快照暂不可用，按离线处理: %s", e)
        return dict(_EMPTY_LIVE_RUNTIME_SNAPSHOT)
    except Exception as e:
        logger.warning(
            "[XianyuAdmin] 读取闲鱼 owner 运行快照失败，按离线处理: %s",
            scrub_secrets(str(e)),
        )
        return dict(_EMPTY_LIVE_RUNTIME_SNAPSHOT)
    if not isinstance(snapshot, Mapping):
        logger.warning("[XianyuAdmin] 闲鱼 owner 运行快照格式无效，按离线处理")
        return dict(_EMPTY_LIVE_RUNTIME_SNAPSHOT)
    return {
        "ws_connected": bool(snapshot.get("ws_connected")),
        "cookie_ok": bool(snapshot.get("cookie_ok")),
        "last_heartbeat": float(snapshot.get("last_heartbeat") or 0.0),
        "token_ts": float(snapshot.get("token_ts") or 0.0),
        "manual_chats": max(0, int(snapshot.get("manual_chats") or 0)),
    }


def _normalize_cc_item_mapping_item_id(value: str) -> str:
    """把老板粘贴的闲鱼分享文本规整成稳定的商品绑定键。"""
    raw = str(value or "").strip()
    if not raw:
        return ""

    def _clean_simple_candidate(candidate: object) -> str:
        text = str(candidate or "").strip()
        if re.fullmatch(r"[A-Za-z0-9_-]{4,120}", text):
            return text
        return ""

    # 第一优先级：如果分享链接里已经有真实 itemId，就直接用真实 itemId。
    variants = [raw]
    decoded = unquote(raw)
    if decoded != raw:
        variants.append(decoded)
    supported_item_keys = {"itemid", "item_id", "itemidstr", "item_id_str", "id"}
    item_param_pattern = re.compile(
        r"(?:^|[?&#])(?:itemId|item_id|itemIdStr|item_id_str|id)=([A-Za-z0-9_-]{4,120})(?:$|[&#\s\"'<>\\)\\]])",
        re.IGNORECASE,
    )
    for variant in variants:
        query_candidates: list[str] = []
        with contextlib.suppress(Exception):
            parsed_query = urlsplit(variant).query
            if parsed_query:
                query_candidates.append(parsed_query)
        if "?" in variant:
            query_candidates.append(variant.split("?", 1)[1])
        else:
            query_candidates.append(variant)
        for query in query_candidates:
            for key, candidate in parse_qsl(query, keep_blank_values=False):
                normalized_key = key.strip().lower().replace("-", "_")
                compact_key = normalized_key.replace("_", "")
                if normalized_key not in supported_item_keys and compact_key not in supported_item_keys:
                    continue
                cleaned = _clean_simple_candidate(candidate)
                if cleaned:
                    return cleaned
        for match in item_param_pattern.finditer(variant):
            cleaned = _clean_simple_candidate(match.group(1))
            if cleaned:
                return cleaned

    # 第二优先级：闲鱼常见短链接分享文本，保存为“短链接 + 分享码”，去掉前后中文说明。
    url_pattern = re.compile(r"https?://[^\s\]\)「」<>\"']+", re.IGNORECASE)
    matches = list(url_pattern.finditer(raw))
    if matches:
        normalized_urls: list[tuple[str, int]] = []
        for match in matches:
            url = match.group(0).rstrip("，。；;,.")
            if not url:
                continue
            normalized_urls.append((url, match.end()))

        selected_url = ""
        last_selected_end = 0
        for url, end in normalized_urls:
            if any(domain in url.lower() for domain in ("m.tb.cn", "goofish.com", "2.taobao.com", "item.taobao.com")):
                selected_url = url
                last_selected_end = end
                break
        if not selected_url and normalized_urls:
            selected_url, last_selected_end = normalized_urls[0]

        # Markdown 分享会出现两次同一链接，分享码通常在最后一个链接后面。
        for url, end in normalized_urls:
            if url == selected_url:
                last_selected_end = max(last_selected_end, end)

        suffix = raw[last_selected_end:]
        code_match = re.search(r"\b(?=[A-Z0-9_-]*[A-Z])(?=[A-Z0-9_-]*\d)[A-Z0-9_-]{4,20}\b", suffix)
        if selected_url and code_match:
            return f"{selected_url} {code_match.group(0)}"
        if selected_url:
            return selected_url

    # 第三优先级：兼容旧输入，数字商品 ID 或人工输入的短码原样保存。
    numeric_matches = re.findall(r"[0-9]{6,}", raw)
    if numeric_matches:
        return numeric_matches[-1]
    return raw


def _cc_auto_ship_status() -> dict:
    """返回 CC中转自动发货运行配置摘要，不回显 token。"""
    enabled_raw = os.getenv("CC_XIANYU_AUTO_SHIP_ENABLED", "").strip().lower()
    endpoint = os.getenv("CC_XIANYU_WEBHOOK_URL", "").strip()
    token = os.getenv("CC_XIANYU_WEBHOOK_TOKEN", "").strip()
    disabled = enabled_raw in {"0", "false", "no", "off"}
    operator_state = get_operator_state()
    paused = bool(operator_state.get("auto_ship_paused"))
    one_shot = operator_state.get("one_shot_delivery") or {}
    webhook_configured = (not disabled) and bool(endpoint and token)
    return {
        "enabled": not disabled,
        "configured": webhook_configured,
        "operational": webhook_configured and not paused,
        "paused": paused,
        "pause_reason": operator_state.get("pause_reason") or "",
        "pause_updated_at": operator_state.get("updated_at"),
        "one_shot_delivery": one_shot,
        "endpoint": endpoint,
        "token_present": bool(token),
        "delay_seconds": int(os.getenv("CC_XIANYU_AUTO_SHIP_DELAY_SECONDS", "10") or "10"),
        "paid_order_poll_enabled": os.getenv("CC_XIANYU_PAID_ORDER_POLL_ENABLED", "1").strip().lower()
        not in {"0", "false", "no", "off"},
        "paid_order_poll_interval_seconds": int(os.getenv("CC_XIANYU_PAID_ORDER_POLL_INTERVAL_SECONDS", "60") or "60"),
        "default_plan_id_present": bool(os.getenv("CC_XIANYU_DEFAULT_PLAN_ID", "").strip()),
        "default_plan_id": os.getenv("CC_XIANYU_DEFAULT_PLAN_ID", "").strip(),
        "default_item_id_present": bool(os.getenv("CC_XIANYU_DEFAULT_ITEM_ID", "").strip()),
    }


def _cc_auto_plan_routing_summary(enabled_mappings: int | None = None) -> dict:
    """说明无商品映射订单会如何选套餐；只暴露 planId，不包含 token/卡密。"""
    auto = _cc_auto_ship_status()
    if enabled_mappings is None:
        mappings = []
        if _ctx and hasattr(_ctx, "list_cc_item_mappings"):
            try:
                mappings = _ctx.list_cc_item_mappings(include_disabled=True)
            except Exception:
                mappings = []
        enabled_mappings = len([m for m in mappings if m.get("enabled")])
    default_plan_id = str(auto.get("default_plan_id") or "").strip()
    if int(enabled_mappings or 0) > 0 and default_plan_id:
        mode = "item_mapping_then_default"
        label = "优先按商品映射发货；无映射时使用默认套餐"
        risk = "low"
    elif int(enabled_mappings or 0) > 0:
        mode = "item_mapping_only"
        label = "优先按商品映射发货；无映射时由运营台按可用库存兜底"
        risk = "medium"
    elif default_plan_id:
        mode = "default_plan"
        label = "当前单商品内测按默认套餐发货"
        risk = "low"
    else:
        mode = "fallback_inventory"
        label = "未配置默认套餐或商品映射，会由运营台按可用库存兜底"
        risk = "high"
    return {
        "mode": mode,
        "label": label,
        "risk": risk,
        "enabled_item_mappings": int(enabled_mappings or 0),
        "default_plan_id_present": bool(default_plan_id),
        "default_plan_id": default_plan_id,
        "can_ship_unmapped_order": bool(default_plan_id or int(enabled_mappings or 0) == 0),
    }


def _cc_social_pilot_install_summary() -> dict:
    """只读检查浏览器配置里是否已加载本项目的 Social Pilot 扩展。"""
    runtime_extension_dir = Path(
        os.getenv(
            "CC_XIANYU_CHROME_EXTENSION_RUNTIME_DIR",
            str(Path.home() / ".openclaw" / "cc-social-pilot-runtime-extension"),
        )
    )
    expected_paths = [str(_SOCIAL_PILOT_EXTENSION_DIR), str(runtime_extension_dir)]
    expected_path = str(runtime_extension_dir if runtime_extension_dir.exists() else _SOCIAL_PILOT_EXTENSION_DIR)
    dedicated_profile = Path(
        os.getenv(
            "CC_XIANYU_CHROME_PROFILE_DIR",
            str(Path.home() / ".openclaw" / "cc-zhongzhuan-seller-chrome"),
        )
    )
    chrome_bases = [
        dedicated_profile,
        Path.home() / "Library" / "Application Support" / "Google" / "Chrome",
        Path.home() / "Library" / "Application Support" / "Chromium",
        Path.home() / "Library" / "Application Support" / "BraveSoftware" / "Brave-Browser",
        Path.home() / "Library" / "Application Support" / "Microsoft Edge",
        Path.home() / "Library" / "Application Support" / "Arc" / "User Data",
    ]
    try:
        ps_output = subprocess.check_output(["ps", "aux"], text=True, timeout=3)
    except Exception:
        ps_output = ""
    for candidate_path in expected_paths:
        if f"--load-extension={candidate_path}" in ps_output or f"--load-extension={candidate_path}," in ps_output:
            return {
                "detected": True,
                "source": "running_chrome_process",
                "profile": str(dedicated_profile)[:160],
                "extension_id": "",
                "expected_path": candidate_path,
            }
    checked_profiles: list[str] = []
    for base in chrome_bases:
        if not base.exists():
            continue
        preference_files = list(base.glob("Preferences"))
        preference_files.extend(base.glob("Default/Preferences"))
        preference_files.extend(base.glob("Profile */Preferences"))
        preference_files.extend(base.glob("Secure Preferences"))
        preference_files.extend(base.glob("Default/Secure Preferences"))
        preference_files.extend(base.glob("Profile */Secure Preferences"))
        for pref_file in preference_files[:40]:
            checked_profiles.append(str(pref_file.parent.name)[:80])
            try:
                prefs = json.loads(pref_file.read_text(encoding="utf-8"))
            except Exception:
                continue
            settings = (prefs.get("extensions") or {}).get("settings") or {}
            if not isinstance(settings, dict):
                continue
            for extension_id, info in settings.items():
                if not isinstance(info, dict):
                    continue
                manifest = info.get("manifest") if isinstance(info.get("manifest"), dict) else {}
                name = str(manifest.get("name") or info.get("display_name") or "")
                path = str(info.get("path") or "")
                if (
                    _SOCIAL_PILOT_EXTENSION_NAME in name
                    or path in expected_paths
                    or path.endswith("/openclaw-npm/assets/chrome-extension")
                    or path.endswith("/cc-social-pilot-runtime-extension")
                ):
                    return {
                        "detected": True,
                        "source": "chrome_preferences",
                        "profile": str(pref_file.parent.name)[:80],
                        "extension_id": str(extension_id)[:80],
                        "expected_path": expected_path,
                    }
        for manifest_file in list(base.glob("*/Extensions/*/*/manifest.json"))[:120]:
            try:
                manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
            except Exception:
                continue
            if str(manifest.get("name") or "") == _SOCIAL_PILOT_EXTENSION_NAME:
                return {
                    "detected": True,
                    "source": "chrome_extension_cache",
                    "profile": str(manifest_file.parts[-5])[:80],
                    "extension_id": str(manifest_file.parts[-3])[:80],
                    "expected_path": expected_path,
                }
    return {
        "detected": False,
        "source": "not_found",
        "profile": "",
        "extension_id": "",
        "checked_profiles": sorted(set(checked_profiles))[:12],
        "expected_path": expected_path,
    }


def _cc_chrome_extension_summary() -> dict:
    """读取 Chrome 插件上报的 CC 发货助手能力；不依赖浏览器在线控制。"""
    max_status_age_seconds = 900
    install_summary = _cc_social_pilot_install_summary()
    expected_extension_path = str(
        install_summary.get("expected_path") or "~/.openclaw/cc-social-pilot-runtime-extension"
    )
    load_extension_action = (
        "未检测到 OpenEverything Social Pilot 扩展；请先运行 make cc-seller-chrome，"
        f"再在 chrome://extensions 加载运行版插件目录：{expected_extension_path}。"
    )
    install_fields = {
        "social_pilot_installed": bool(install_summary.get("detected")),
        "social_pilot_source": str(install_summary.get("source") or "")[:80],
        "social_pilot_expected_path": expected_extension_path[:240],
    }
    if not _SOCIAL_EXTENSION_STATUS_FILE.exists():
        return {
            "status_file_exists": False,
            "online": False,
            "status_age_seconds": None,
            "updated_at": "",
            "platform": "unsupported",
            "manifest_version": "",
            "cc_delivery_helper_version": "",
            "supports_global_watch": False,
            "supports_target_tab_preflight": False,
            "supports_paid_page_dispatch": False,
            "supports_relist_queue": False,
            "needs_refresh_for_global_watch": True,
            **install_fields,
            "next_action": (
                load_extension_action
                if not install_fields["social_pilot_installed"]
                else "刷新 Chrome 插件，然后打开一次插件弹窗完成能力上报。"
            ),
        }
    try:
        data = json.loads(_SOCIAL_EXTENSION_STATUS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {
            "status_file_exists": True,
            "online": False,
            "status_age_seconds": None,
            "updated_at": "",
            "platform": "unsupported",
            "manifest_version": "",
            "cc_delivery_helper_version": "",
            "supports_global_watch": False,
            "supports_target_tab_preflight": False,
            "supports_paid_page_dispatch": False,
            "supports_relist_queue": False,
            "needs_refresh_for_global_watch": True,
            **install_fields,
            "next_action": (
                f"插件状态文件损坏，且未检测到 OpenEverything Social Pilot 扩展；{load_extension_action}"
                if not install_fields["social_pilot_installed"]
                else "插件状态文件损坏，刷新 Chrome 插件后重新打开弹窗。"
            ),
        }
    if not isinstance(data, dict):
        data = {}
    extension = data.get("extension") if isinstance(data.get("extension"), dict) else {}
    manifest_version = str(extension.get("manifest_version") or "")[:32]
    bridge_active = manifest_version == "bridge"
    capabilities = extension.get("capabilities") if isinstance(extension.get("capabilities"), dict) else {}
    supports_global = bool(
        capabilities.get("all_open_xianyu_tabs_watch") and capabilities.get("single_pending_global_gate")
    )
    supports_preflight = bool(capabilities.get("target_tab_preflight"))
    supports_paid_page_dispatch = bool(capabilities.get("paid_page_dispatch"))
    supports_relist_queue = bool(capabilities.get("relist_queue_watch") and capabilities.get("xianyu_relist_item"))
    try:
        status_age_seconds = max(0, int(time.time() - _SOCIAL_EXTENSION_STATUS_FILE.stat().st_mtime))
    except Exception:
        status_age_seconds = None
    heartbeat_fresh = status_age_seconds is not None and status_age_seconds <= max_status_age_seconds
    online = bool(data.get("online")) and heartbeat_fresh
    needs_refresh = not (
        supports_global and supports_preflight and supports_paid_page_dispatch and supports_relist_queue and online
    )
    return {
        "status_file_exists": True,
        "online": online,
        "status_age_seconds": status_age_seconds,
        "updated_at": str(data.get("updated_at") or ""),
        "platform": str(data.get("platform") or "unsupported")[:40],
        "manifest_version": manifest_version,
        "cc_delivery_helper_version": str(extension.get("cc_delivery_helper_version") or "")[:80],
        "supports_global_watch": supports_global,
        "supports_target_tab_preflight": supports_preflight,
        "supports_paid_page_dispatch": supports_paid_page_dispatch,
        "supports_relist_queue": supports_relist_queue,
        "needs_refresh_for_global_watch": needs_refresh,
        **install_fields,
        "next_action": (
            "Chrome 插件心跳已过期，请刷新扩展；新版会自动后台上报，无需反复打开弹窗。"
            if not online
            and supports_global
            and supports_preflight
            and supports_paid_page_dispatch
            and supports_relist_queue
            else load_extension_action
            if needs_refresh and not install_fields["social_pilot_installed"]
            else "已启动 Social Pilot，但尚未上报新版发货能力；打开插件弹窗，在高级设置粘贴本机 Token 后保存。"
            if needs_refresh and install_fields["social_pilot_source"] == "running_chrome_process"
            else "刷新 Chrome 插件并打开一次插件弹窗，同步新版“付款页自动发卡/恢复上架队列”能力。"
            if needs_refresh
            else "本机卖家桥接器已接管自动发货；保持卖家专用 Chromium 登录闲鱼并打开。"
            if bridge_active
            else "插件已上报新版发货助手能力；打开买家聊天页后可使用当前页/全局看守。"
        ),
    }


def _env_flag(name: str, default: str = "1") -> bool:
    """读取布尔环境变量，统一支持 0/false/no/off 关闭写法。"""
    return os.getenv(name, default).strip().lower() not in {"0", "false", "no", "off"}


def _auto_strict_audit_config() -> dict:
    """返回后台严格门观察配置；只控制只读审计，不触发发货或库存写入。"""
    try:
        interval_ms = max(
            60_000,
            int(os.getenv("CC_XIANYU_AUTO_STRICT_AUDIT_INTERVAL_MS", "600000") or "600000"),
        )
    except ValueError:
        interval_ms = 600_000
    try:
        scan_seconds = max(
            30,
            int(os.getenv("CC_XIANYU_AUTO_STRICT_AUDIT_SCAN_SECONDS", "60") or "60"),
        )
    except ValueError:
        scan_seconds = 60
    return {
        "enabled": _env_flag("CC_XIANYU_AUTO_STRICT_AUDIT_ENABLED", "1"),
        "interval_ms": interval_ms,
        "scan_seconds": scan_seconds,
    }


def _auto_readiness_audit_config() -> dict:
    """返回后台只读巡检配置，用于自动刷新库存/兑换码/渠道证据。"""
    try:
        interval_ms = max(
            300_000,
            int(os.getenv("CC_XIANYU_AUTO_READINESS_AUDIT_INTERVAL_MS", "900000") or "900000"),
        )
    except ValueError:
        interval_ms = 900_000
    try:
        scan_seconds = max(
            30,
            int(os.getenv("CC_XIANYU_AUTO_READINESS_AUDIT_SCAN_SECONDS", "60") or "60"),
        )
    except ValueError:
        scan_seconds = 60
    return {
        "enabled": _env_flag("CC_XIANYU_AUTO_READINESS_AUDIT_ENABLED", "1"),
        "interval_ms": interval_ms,
        "scan_seconds": scan_seconds,
    }


def _ops_notify_config() -> dict:
    """返回本机运营提醒配置；只做提醒，不发货、不改库存、不触发外部副作用。"""
    try:
        interval_ms = max(
            30_000,
            int(os.getenv("CC_XIANYU_OPS_NOTIFY_INTERVAL_MS", "120000") or "120000"),
        )
    except ValueError:
        interval_ms = 120_000
    try:
        scan_seconds = max(
            10,
            int(os.getenv("CC_XIANYU_OPS_NOTIFY_SCAN_SECONDS", "30") or "30"),
        )
    except ValueError:
        scan_seconds = 30
    try:
        low_inventory_threshold = max(
            0,
            int(os.getenv("CC_XIANYU_LOW_INVENTORY_THRESHOLD", "2") or "2"),
        )
    except ValueError:
        low_inventory_threshold = 2
    return {
        "enabled": _env_flag("CC_XIANYU_OPS_NOTIFY_ENABLED", "1"),
        "interval_ms": interval_ms,
        "scan_seconds": scan_seconds,
        "low_inventory_threshold": low_inventory_threshold,
    }


def _project_root() -> Path:
    """定位 OpenEverything 项目根目录，供本机 GUI 调用闭环审计脚本。"""
    return Path(__file__).resolve().parents[4]


def _run_cc_readiness_audit(mode: str = "read_only") -> dict:
    """运行 CC中转闭环审计，只支持无生产写入的只读/严格模式。"""
    normalized = (mode or "read_only").strip().lower().replace("-", "_")
    if normalized not in {"read_only", "strict"}:
        raise HTTPException(400, "只支持 read_only 或 strict 审计模式")
    root = _project_root()
    script = root / "scripts" / "cc_zhongzhuan_readiness_audit.mjs"
    if not script.exists():
        raise HTTPException(503, "闭环审计脚本不存在")
    args = ["node", str(script), "--json"]
    if normalized == "strict":
        args.insert(2, "--require-real-order")
    try:
        result = subprocess.run(
            args,
            cwd=str(root),
            text=True,
            capture_output=True,
            timeout=45,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        result = {
            "ok": False,
            "mode": normalized,
            "exit_code": -1,
            "message": "闭环审计超时，请稍后重试",
            "stdout": (exc.stdout or "")[-1200:],
            "stderr": scrub_secrets((exc.stderr or "")[-1200:]),
        }
        if normalized == "strict":
            _remember_strict_audit(result)
        return result
    payload = {}
    try:
        payload = json.loads(result.stdout or "{}")
    except Exception:
        payload = {}
    response = {
        "ok": result.returncode == 0 and bool(payload.get("ok", result.returncode == 0)),
        "mode": normalized,
        "exit_code": result.returncode,
        "summary": _summarize_cc_readiness_payload(payload),
        "checks": payload.get("checks", {}),
        "next_human_gate": payload.get("nextHumanGate", ""),
        "stdout": (result.stdout or "")[-4000:],
        "stderr": scrub_secrets((result.stderr or "")[-1200:]),
    }
    _remember_readiness_audit(response)
    if normalized == "strict":
        _remember_strict_audit(response)
    return response


def _remember_readiness_audit(audit: dict) -> None:
    """缓存最近一次只读/严格巡检摘要，供上架锁使用；不保存敏感原文。"""
    global _last_cc_readiness_audit
    summary = audit.get("summary") if isinstance(audit, dict) else {}
    if not isinstance(summary, dict):
        summary = {}
    _last_cc_readiness_audit = {
        "ok": bool(audit.get("ok")),
        "mode": audit.get("mode") or "read_only",
        "exit_code": audit.get("exit_code"),
        "updated_at": now_et().isoformat(),
        "redeem_available": int(summary.get("redeem_available") or 0),
        "sub2api_active_channels": int(summary.get("sub2api_active_channels") or 0),
        "sub2api_enabled_monitors": int(summary.get("sub2api_enabled_monitors") or 0),
        "config_contract_ok": bool(summary.get("config_contract_ok")),
        "pending_rescue": int(summary.get("pending_rescue") or 0),
        "oracle": bool(summary.get("oracle")),
        "local_gui": bool(summary.get("local_gui")),
        "chrome_bookmarks": bool(summary.get("chrome_bookmarks")),
        "buyer_self_service_ok": bool(summary.get("buyer_self_service_ok")),
        "webhook_public_locked": bool(summary.get("webhook_public_locked")),
        "public_main_http": int(summary.get("public_main_http") or 0),
        "public_models_no_auth_http": int(summary.get("public_models_no_auth_http") or 0),
        "public_webhook_no_token_http": int(summary.get("public_webhook_no_token_http") or 0),
        "ccswitch_entry_ok": bool(summary.get("ccswitch_entry_ok")),
        "ccswitch_entry_http": int(summary.get("ccswitch_entry_http") or 0),
        "ccswitch_has_cc_switch_text": bool(summary.get("ccswitch_has_cc_switch_text")),
        "ccswitch_has_ccswitch_marker": bool(summary.get("ccswitch_has_ccswitch_marker")),
        "ccswitch_has_import_link_marker": bool(summary.get("ccswitch_has_import_link_marker")),
        "redeemed_delta": int(summary.get("redeemed_delta") or 0),
        "active_token_delta": int(summary.get("active_token_delta") or 0),
        "model_log_delta": int(summary.get("model_log_delta") or 0),
    }


def _sanitize_strict_audit_summary(summary: dict) -> dict:
    """提取严格门里可展示的同单闭环摘要，不保存卡密、Token 或 API Key。"""
    if not isinstance(summary, dict):
        summary = {}
    latest = summary.get("same_order_latest") or []
    if not isinstance(latest, list):
        latest = []
    safe_latest = []
    allowed_keys = {
        "orderIdPrefix",
        "orderIdHash",
        "fulfillmentStatus",
        "cardStatus",
        "balanceRedeemed",
        "usedUserIdPresent",
        "activeTokens",
        "modelLogsAfterRedeem",
        "ready",
    }
    for item in latest[:5]:
        if not isinstance(item, dict):
            continue
        safe_item = {key: item.get(key) for key in allowed_keys if key in item}
        if "balanceRedeemed" not in safe_item and "newApiRedeemed" in item:
            safe_item["balanceRedeemed"] = bool(item.get("newApiRedeemed"))
        safe_latest.append(safe_item)
    trusted_real_orders = len(
        [
            item
            for item in safe_latest
            if item.get("ready") and str(item.get("orderIdPrefix") or "").startswith("xy_oid_")
        ]
    )
    raw_real_orders = int(summary.get("real_orders") or 0)
    sanitized = {
        "same_order_ready": int(summary.get("same_order_ready") or 0) if trusted_real_orders > 0 else 0,
        "same_order_matched": int(summary.get("same_order_matched") or 0),
        "real_orders": trusted_real_orders,
        "redeemed_delta": int(summary.get("redeemed_delta") or 0),
        "active_token_delta": int(summary.get("active_token_delta") or 0),
        "model_log_delta": int(summary.get("model_log_delta") or 0),
        "same_order_latest": safe_latest,
    }
    if raw_real_orders > trusted_real_orders:
        sanitized["display_note"] = "manual_or_browser_orders_are_internal_test_only"
    return sanitized


def _remember_strict_audit(audit: dict) -> None:
    """缓存最近一次严格门结果，便于 GUI 自动展示正式售卖状态。"""
    global _last_cc_strict_audit
    summary = _sanitize_strict_audit_summary(audit.get("summary") if isinstance(audit, dict) else {})
    _last_cc_strict_audit = {
        "ok": bool(audit.get("ok")),
        "exit_code": audit.get("exit_code"),
        "updated_at": now_et().isoformat(),
        "same_order_ready": int(summary.get("same_order_ready") or 0),
        "same_order_matched": int(summary.get("same_order_matched") or 0),
        "real_orders": int(summary.get("real_orders") or 0),
        "summary": summary,
    }
    if _ctx and hasattr(_ctx, "record_cc_strict_audit"):
        try:
            saved = _ctx.record_cc_strict_audit(audit)
            if isinstance(saved, dict):
                saved_summary = _sanitize_strict_audit_summary(saved.get("summary") or summary)
                _last_cc_strict_audit.update(
                    {
                        "persisted": True,
                        "audit_id": saved.get("id"),
                        "source": "sqlite",
                        "real_orders": int(saved_summary.get("real_orders") or 0),
                        "same_order_ready": int(saved_summary.get("same_order_ready") or 0),
                        "same_order_matched": int(saved_summary.get("same_order_matched") or 0),
                        "summary": saved_summary,
                    }
                )
        except Exception as e:
            logger.warning(f"[XianyuAdmin] 严格门审计摘要持久化失败: {scrub_secrets(str(e))}")


def _latest_strict_audit() -> dict:
    """读取最近严格门结果；优先内存，缺失时从本机 SQLite 恢复。"""
    if _last_cc_strict_audit:
        return _last_cc_strict_audit
    if _ctx and hasattr(_ctx, "latest_cc_strict_audit"):
        try:
            latest = _ctx.latest_cc_strict_audit()
        except Exception as e:
            logger.warning(f"[XianyuAdmin] 读取严格门审计摘要失败: {scrub_secrets(str(e))}")
            latest = None
        if isinstance(latest, dict) and latest:
            summary = _sanitize_strict_audit_summary(
                latest.get("summary") if isinstance(latest.get("summary"), dict) else {}
            )
            restored = {
                "ok": bool(latest.get("ok")),
                "exit_code": latest.get("exit_code"),
                "updated_at": latest.get("updated_at"),
                "same_order_ready": int(summary.get("same_order_ready") or 0),
                "same_order_matched": int(summary.get("same_order_matched") or 0),
                "real_orders": int(summary.get("real_orders") or 0),
                "summary": summary,
                "persisted": True,
                "audit_id": latest.get("id"),
                "source": latest.get("source") or "sqlite",
            }
            _last_cc_strict_audit.update(restored)
            return restored
    return {}


def _strict_audit_has_real_ready_match(latest: dict | None = None) -> bool:
    """确认严格门摘要里至少有一条真实闲鱼自动订单闭环，而不是手工/浏览器补救单。"""
    latest = latest or _latest_strict_audit()
    summary = latest.get("summary") if isinstance(latest, dict) else {}
    if not isinstance(summary, dict):
        return False
    matches = summary.get("same_order_latest") or []
    if not isinstance(matches, list):
        return False
    for item in matches:
        if not isinstance(item, dict) or not item.get("ready"):
            continue
        if str(item.get("orderIdPrefix") or "").startswith("xy_oid_"):
            return True
    return False


def _strict_audit_ready() -> bool:
    """只有真实自动订单严格审计通过且同单闭环完成，才允许显示正式可售。"""
    latest = _latest_strict_audit()
    if not (
        latest.get("ok") and int(latest.get("same_order_ready") or 0) > 0 and _strict_audit_has_real_ready_match(latest)
    ):
        return False
    if _ctx and hasattr(_ctx, "cc_final_sale_gate_summary"):
        gate = _ctx.cc_final_sale_gate_summary()
        return bool(
            int((gate or {}).get("sent_real_orders") or 0) > 0
            and int((gate or {}).get("buyer_chain_verified_orders") or 0) > 0
            and int((gate or {}).get("pending_rescue") or 0) == 0
        )
    return False


def _cc_operations_projection_snapshot(
    runtime_snapshot: Mapping[str, object] | None = None,
    *,
    include_readiness: bool,
) -> dict[str, object]:
    """把有状态运行对象收口为纯投影模块可消费的普通快照。"""
    live_snapshot = dict(runtime_snapshot) if runtime_snapshot is not None else _live_runtime_snapshot()
    shipments: Mapping[str, object] = {}
    gate: Mapping[str, object] = {}
    mappings: list[Mapping[str, object]] = []
    if _ctx and hasattr(_ctx, "cc_shipment_summary"):
        shipments = _ctx.cc_shipment_summary() or {}
    if _ctx and hasattr(_ctx, "cc_final_sale_gate_summary"):
        gate = _ctx.cc_final_sale_gate_summary() or {}
    if _ctx and hasattr(_ctx, "list_cc_item_mappings"):
        mappings = _ctx.list_cc_item_mappings(include_disabled=True) or []
    enabled_mappings = len([mapping for mapping in mappings if mapping.get("enabled")])
    latest_strict_audit = _latest_strict_audit()
    return {
        "auto_ship": _cc_auto_ship_status(),
        "runtime": live_snapshot,
        "shipments": shipments,
        "sale_gate": gate,
        "enabled_item_mappings": enabled_mappings,
        "plan_routing": _cc_auto_plan_routing_summary(enabled_mappings) if include_readiness else {},
        "readiness_audit": dict(_last_cc_readiness_audit or {}) if include_readiness else {},
        "chrome_extension": _cc_chrome_extension_summary() if include_readiness else {},
        "strict_ready": _strict_audit_ready(),
        "latest_strict_audit": latest_strict_audit,
        "auto_strict_audit": _auto_strict_audit_config(),
        "last_background_strict_audit_at": _last_background_strict_audit_at,
        "last_background_strict_audit": dict(_last_background_strict_audit_result),
    }


def _cc_public_sale_lock_summary(refresh: bool = False) -> dict:
    """给老板看的上架锁；默认只读缓存，refresh=True 时跑一次只读巡检刷新库存/渠道。"""
    audit_error = ""
    if refresh:
        try:
            _run_cc_readiness_audit("read_only")
        except Exception as e:
            audit_error = _safe_error(e)
            logger.warning(f"[XianyuAdmin] 上架锁刷新只读巡检失败: {scrub_secrets(str(e))}")

    runtime_snapshot = _live_runtime_snapshot()
    sale = _cc_sale_readiness_summary(runtime_snapshot)
    loop_watch = _cc_loop_watch_summary(runtime_snapshot)
    checks = sale.get("checks") if isinstance(sale.get("checks"), dict) else {}
    audit = _last_cc_readiness_audit or {}
    readiness_auto = _auto_readiness_audit_config()
    inventory_known = bool(audit.get("updated_at"))
    pending_rescue = int(checks.get("pending_rescue") or 0)
    inventory_unused = int(audit.get("redeem_available") or 0)
    enabled_channels = int(audit.get("sub2api_active_channels") or 0)
    enabled_monitors = int(audit.get("sub2api_enabled_monitors") or 0)
    config_contract_ok = bool(audit.get("config_contract_ok"))
    buyer_self_service_known = bool(audit.get("public_main_http") or audit.get("public_models_no_auth_http"))
    buyer_self_service_ready = (not buyer_self_service_known) or bool(audit.get("buyer_self_service_ok"))
    webhook_public_locked = (not buyer_self_service_known) or bool(audit.get("webhook_public_locked"))
    ccswitch_import_known = ("ccswitch_entry_ok" in audit) or bool(audit.get("ccswitch_entry_http"))
    ccswitch_import_ready = (not ccswitch_import_known) or bool(audit.get("ccswitch_entry_ok"))

    auto_ship_paused = bool(checks.get("auto_ship_paused"))
    webhook_configured = checks.get("webhook_configured")
    ws_connected = checks.get("ws_connected")
    cookie_ok = checks.get("cookie_ok")

    gates = {
        "auto_ship_ready": bool(sale.get("can_auto_ship_paid_orders")),
        "auto_ship_paused": auto_ship_paused,
        "webhook_configured": webhook_configured,
        "ws_connected": ws_connected,
        "cookie_ok": cookie_ok,
        "pending_rescue_clear": pending_rescue == 0,
        "inventory_known": inventory_known,
        "inventory_ready": inventory_known and inventory_unused > 0,
        "redemptions_ready": inventory_known and inventory_unused > 0,
        "channels_ready": inventory_known and config_contract_ok and enabled_channels == 10 and enabled_monitors == 10,
        "buyer_self_service_ready": buyer_self_service_ready,
        "webhook_public_locked": webhook_public_locked,
        "ccswitch_import_ready": ccswitch_import_ready,
        "strict_real_order_ready": bool(sale.get("ready_for_public_sale")),
    }
    inventory_display_ready = not inventory_known or (
        gates["inventory_ready"] and gates["redemptions_ready"] and gates["channels_ready"]
    )
    strict_pause_display_ready = bool(
        auto_ship_paused
        and gates["strict_real_order_ready"]
        and gates["pending_rescue_clear"]
        and gates["buyer_self_service_ready"]
        and gates["webhook_public_locked"]
        and gates["ccswitch_import_ready"]
        and inventory_display_ready
    )
    blockers = []
    if not gates["auto_ship_ready"]:
        if auto_ship_paused:
            blockers.append("自动发货被手动暂停保护（防重复发卡）")
        elif webhook_configured is False:
            blockers.append("自动发货 webhook 未配置")
        elif ws_connected is False:
            blockers.append("闲鱼助手 WebSocket 未在线")
        elif cookie_ok is False:
            blockers.append("闲鱼 Cookie 需要恢复")
        else:
            blockers.append("自动发货链路未完全就绪")
    if not gates["pending_rescue_clear"]:
        blockers.append("发货补救队列未清零")
    if not gates["inventory_known"]:
        if not strict_pause_display_ready:
            blockers.append("库存/渠道证据未刷新，请点“刷新上架锁”")
    else:
        if not gates["inventory_ready"]:
            blockers.append("未售兑换码库存为 0")
        if not gates["redemptions_ready"]:
            blockers.append("Sub2API 可售兑换码库存为 0")
        if not gates["channels_ready"]:
            blockers.append("Sub2API 10 渠道 / 10 监控合同未满足")
        if not gates["buyer_self_service_ready"]:
            blockers.append("买家主站或 API 网关公网入口异常")
        if not gates["webhook_public_locked"]:
            blockers.append("闲鱼发货 webhook 未授权访问未被正确拦截")
        if not gates["ccswitch_import_ready"]:
            blockers.append("CC Switch 导入入口异常")
    if not gates["strict_real_order_ready"]:
        blockers.append("尚未通过真实闲鱼小额单的兑换/API/调模型严格门")

    non_auto_internal_ready = all(
        gates[name]
        for name in (
            "pending_rescue_clear",
            "inventory_known",
            "inventory_ready",
            "redemptions_ready",
            "channels_ready",
            "buyer_self_service_ready",
            "webhook_public_locked",
            "ccswitch_import_ready",
        )
    )
    display_internal_ready = bool(non_auto_internal_ready or strict_pause_display_ready)
    can_internal_test = bool(display_internal_ready and (gates["auto_ship_ready"] or auto_ship_paused))
    can_public_sale = bool(gates["auto_ship_ready"] and non_auto_internal_ready and gates["strict_real_order_ready"])
    if can_public_sale:
        state = "public_sale_unlocked"
        label = "正式售卖已放行"
        next_action = "可以小批量正式售卖，同时继续观察库存、上游余额、补救队列和渠道状态。"
    elif auto_ship_paused and display_internal_ready and gates["strict_real_order_ready"]:
        state = "paused_after_strict_gate"
        label = "严格门已通过，自动发货暂停保护"
        next_action = "严格门已通过，当前只是防重复发卡的人工暂停。确认准备正式售卖后，在操作台点“恢复自动发货”；建议先保持小流量观察。"
    elif auto_ship_paused and display_internal_ready:
        state = "paused_internal_test_ready"
        label = "生产内测条件已齐，自动发货暂停保护"
        next_action = (
            "系统基础条件正常，但自动发货被手动暂停。建议先用“只放行一次发卡”跑当前测试单，确认不会重复发卡后再恢复。"
        )
    elif can_internal_test:
        state = "internal_test_ready"
        label = "生产内测可发货，正式售卖仍锁定"
        next_action = "先跑 1 单真实闲鱼小额付款，并让买家完成兑换、创建 API Key、CC Switch 导入和模型调用。"
    else:
        state = "locked"
        label = "暂不建议上架"
        next_action = blockers[0] if blockers else "先刷新上架锁并处理红色项。"

    return {
        "state": state,
        "state_label": label,
        "can_internal_test": can_internal_test,
        "can_public_sale": can_public_sale,
        "next_action": next_action,
        "blockers": blockers,
        "gates": gates,
        "audit_error": audit_error,
        "inventory": {
            "unused_cards": inventory_unused if inventory_known else None,
            "redeem_available": inventory_unused if inventory_known else None,
            "active_channels": enabled_channels if inventory_known else None,
            "enabled_monitors": enabled_monitors if inventory_known else None,
            "config_contract_ok": config_contract_ok if inventory_known else None,
            "buyer_self_service_ok": audit.get("buyer_self_service_ok") if buyer_self_service_known else None,
            "webhook_public_locked": audit.get("webhook_public_locked") if buyer_self_service_known else None,
            "public_main_http": audit.get("public_main_http") if buyer_self_service_known else None,
            "public_models_no_auth_http": audit.get("public_models_no_auth_http") if buyer_self_service_known else None,
            "public_webhook_no_token_http": audit.get("public_webhook_no_token_http")
            if buyer_self_service_known
            else None,
            "ccswitch_entry_ok": audit.get("ccswitch_entry_ok") if ccswitch_import_known else None,
            "ccswitch_entry_http": audit.get("ccswitch_entry_http") if ccswitch_import_known else None,
            "ccswitch_has_cc_switch_text": audit.get("ccswitch_has_cc_switch_text") if ccswitch_import_known else None,
            "ccswitch_has_ccswitch_marker": audit.get("ccswitch_has_ccswitch_marker")
            if ccswitch_import_known
            else None,
            "ccswitch_has_import_link_marker": audit.get("ccswitch_has_import_link_marker")
            if ccswitch_import_known
            else None,
            "updated_at": audit.get("updated_at"),
        },
        "auto_readiness_audit": {
            "enabled": readiness_auto["enabled"],
            "interval_ms": readiness_auto["interval_ms"],
            "scan_seconds": readiness_auto["scan_seconds"],
            "last_background_at": (
                _last_background_readiness_audit_at if _last_background_readiness_audit_at > 0 else None
            ),
        },
        "loop_stage": loop_watch.get("stage"),
        "last_strict_audit": sale.get("last_strict_audit") or {},
    }


def _summarize_cc_readiness_payload(payload: dict) -> dict:
    """把审计 JSON 压缩成老板看板可读摘要。"""
    checks = payload.get("checks") if isinstance(payload, dict) else {}
    if not isinstance(checks, dict):
        checks = {}
    oracle = checks.get("oracle") or {}
    gui = checks.get("localXianyuGui") or {}
    proof = checks.get("realXianyuOrderProof") or {}
    contract = oracle.get("config_contract") or {}
    inventory = oracle.get("inventory") or {}
    public = oracle.get("public") or {}
    public_main_http = int((public.get("home") or {}).get("http") or 0)
    public_models_no_auth_http = int((public.get("models") or {}).get("http") or 0)
    public_webhook_no_token_http = int((public.get("webhook_no_token") or {}).get("http") or 0)
    docs_route_http = int((public.get("docs_route") or {}).get("http") or 0)
    return {
        "schema_version": int(payload.get("schema_version") or 0),
        "overall_ok": bool(payload.get("ok")),
        "software_ready": bool(payload.get("software_ready")),
        "chrome_bookmarks": bool((checks.get("chromeBookmarks") or {}).get("ok")),
        "local_xianyu": bool((checks.get("localXianyu") or {}).get("ok")),
        "local_gui": bool(gui.get("ok")),
        "oracle": bool(oracle.get("ok")),
        "buyer_self_service_ok": public_main_http == 200 and public_models_no_auth_http == 401,
        "webhook_public_locked": public_webhook_no_token_http in {401, 403, 404},
        "public_main_http": public_main_http,
        "public_models_no_auth_http": public_models_no_auth_http,
        "public_webhook_no_token_http": public_webhook_no_token_http,
        "ccswitch_entry_ok": docs_route_http == 200,
        "ccswitch_entry_http": docs_route_http,
        "ws_connected": bool(gui.get("wsConnected")),
        "cookie_ok": bool(gui.get("cookieOk")),
        "auto_ship_configured": bool(gui.get("autoShipConfigured")),
        "pending_rescue": int(gui.get("pendingRescue") or 0),
        "redeem_available": int(inventory.get("redeem_available") or 0),
        "sub2api_active_channels": int(contract.get("active_channels") or 0),
        "sub2api_enabled_monitors": int(contract.get("enabled_monitors") or 0),
        "config_contract_ok": bool(contract.get("ok")),
        "provider_health": list(oracle.get("provider_health") or [])[:10],
        "real_orders": int(proof.get("sentRealOrders") or 0),
        "same_order_ready": int(proof.get("sentRealOrders") or 0),
        "same_order_matched": int(proof.get("sentRealOrders") or 0),
        "same_order_latest": [],
        "redeemed_delta": 0,
        "active_token_delta": int(inventory.get("active_keys") or 0),
        "model_log_delta": int(inventory.get("usage_logs") or 0),
    }


def _build_cc_product_template(title: str = "", plan_id: str = "", price: str = "") -> dict:
    """生成极简闲鱼商品模板，只保留履约必要信息，不写营销话术。"""
    safe_title = (title or "").strip()[:80] or "CC中转兑换码"
    safe_plan = (plan_id or "").strip()[:80] or "按商品映射/默认套餐发货"
    safe_price = (price or "").strip()[:40]
    lines = [
        f"标题：{safe_title}",
        f"规格：{safe_plan}",
    ]
    if safe_price:
        lines.append(f"价格：{safe_price}")
    lines.extend(
        [
            "发货方式：付款后系统自动发送兑换入口和一次性兑换码。",
            "使用步骤：1. 打开兑换入口；2. 注册或登录；3. 输入兑换码到账；4. 创建 API Key；5. 进入 CC Switch 导入并选择模型测试。",
            "售后规则：未使用兑换码可联系客服处理；已使用兑换码不支持退换。",
            "提醒：请勿公开分享自己的 API Key。",
        ]
    )
    return {
        "title": safe_title,
        "plan_id": safe_plan,
        "price": safe_price,
        "template": "\n".join(lines),
    }


def _cc_sale_readiness_summary(runtime_snapshot: Mapping[str, object] | None = None) -> dict:
    """汇总当前自动化运营水位，告诉操作者还能自动化到哪一步。"""
    snapshot = _cc_operations_projection_snapshot(runtime_snapshot, include_readiness=True)
    return project_operations(snapshot)["sale_readiness"]


def _cc_loop_watch_summary(runtime_snapshot: Mapping[str, object] | None = None) -> dict:
    """轻量观察真实订单闭环进度；不跑远程审计、不泄露卡密。"""
    snapshot = _cc_operations_projection_snapshot(runtime_snapshot, include_readiness=False)
    return project_operations(snapshot)["loop_watch"]


def _cc_buyer_chain_progress_summary() -> dict:
    """汇总买家从已发货到兑换/API/调模型的进度；只读、不触发审计。"""
    snapshot = {
        "loop_watch": _cc_loop_watch_summary(),
        "latest_strict_audit": _latest_strict_audit(),
        "strict_ready": _strict_audit_ready(),
    }
    return project_operations(snapshot)["buyer_progress"]


def _cc_operator_next_action_summary() -> dict:
    """统一给老板看的下一步行动建议；只读，不触发审计或发货。"""
    lock = _cc_public_sale_lock_summary(refresh=False)
    loop_watch = _cc_loop_watch_summary()
    progress = _cc_buyer_chain_progress_summary()
    buyer_smoke = _cc_buyer_site_smoke_summary()
    buyer_smoke_plan = _cc_buyer_site_smoke_plan_summary()
    blockers = lock.get("blockers") if isinstance(lock.get("blockers"), list) else []
    checks = loop_watch.get("checks") if isinstance(loop_watch.get("checks"), dict) else {}

    if lock.get("can_public_sale"):
        state = "public_sale_ready"
        severity = "ok"
        title = "正式售卖已放行"
        primary_action = "可以小批量正式售卖，同时继续观察库存、上游余额、补救队列和渠道状态。"
    elif int(checks.get("pending_rescue") or 0) > 0:
        state = "rescue_required"
        severity = "danger"
        title = "先处理发货补救队列"
        if int(checks.get("manual_delivery_ready") or 0) > 0:
            primary_action = (
                "刷新 Chrome 插件，打开对应买家聊天页；点“看守当前聊天页”，或在只有 1 条待发货时点“看守所有闲鱼页”。"
            )
        else:
            primary_action = "打开本机闲鱼 GUI 的“CC中转发货补救队列”，等待自动补发或手动重试/标记已处理。"
    elif lock.get("can_internal_test") and lock.get("state") in {
        "paused_after_strict_gate",
        "paused_internal_test_ready",
    }:
        state = lock.get("state")
        severity = "warning"
        title = lock.get("state_label") or "自动发货暂停保护"
        primary_action = (
            lock.get("next_action") or loop_watch.get("next_action") or "确认准备继续售卖后，在操作台点“恢复自动发货”。"
        )
    elif not loop_watch.get("can_auto_ship_paid_orders"):
        state = "auto_ship_not_ready"
        severity = "danger"
        title = "自动发货还没完全就绪"
        primary_action = loop_watch.get("next_action") or "先处理 WebSocket、Cookie、webhook 或库存红色项。"
    elif lock.get("can_internal_test") and progress.get("stage") == "waiting_paid_order":
        state = "run_real_small_order"
        severity = "warning"
        title = "生产内测可发货，等待真实小额单"
        primary_action = "发布 1 个小额闲鱼测试商品，完成真实付款；系统会自动发卡。"
    elif progress.get("stage") in {"waiting_redeem", "waiting_api_key", "waiting_model_call"}:
        state = progress.get("stage")
        severity = "warning"
        title = "买家自助链路未跑完"
        primary_action = progress.get("next_action") or "让买家按发货话术完成兑换、创建 API Key 和模型测试。"
    elif progress.get("stage") == "waiting_strict_audit":
        state = "waiting_strict_audit"
        severity = "warning"
        title = "等待严格门确认同单闭环"
        primary_action = "后台会自动观察；也可在本机 GUI 点击“运行正式售卖严格门”。"
    else:
        state = lock.get("state") or loop_watch.get("stage") or "unknown"
        severity = "warning" if lock.get("can_internal_test") else "danger"
        title = lock.get("state_label") or loop_watch.get("stage_label") or "继续观察"
        if not lock.get("can_internal_test") and blockers:
            primary_action = blockers[0]
        else:
            primary_action = (
                progress.get("next_action")
                or lock.get("next_action")
                or loop_watch.get("next_action")
                or (blockers[0] if blockers else "打开本机闲鱼 GUI 查看状态。")
            )

    checklist = [
        {"key": "auto_ship_ready", "label": "自动发货就绪", "ok": bool(loop_watch.get("can_auto_ship_paid_orders"))},
        {"key": "pending_rescue_clear", "label": "补救队列清零", "ok": int(checks.get("pending_rescue") or 0) == 0},
        {"key": "inventory_ready", "label": "库存/兑换码/渠道可用", "ok": bool(lock.get("can_internal_test"))},
        {"key": "buyer_site_smoke", "label": "站内兑换/Key/调模型烟测", "ok": bool(buyer_smoke.get("ok"))},
        {"key": "real_paid_order", "label": "真实闲鱼小额付款单", "ok": int(checks.get("sent_real_orders") or 0) > 0},
        {
            "key": "buyer_chain_verified",
            "label": "买家兑换/API/调模型闭环",
            "ok": bool(progress.get("steps", {}).get("same_order_verified")),
        },
    ]
    return {
        "state": state,
        "severity": severity,
        "title": title,
        "primary_action": primary_action,
        "checklist": checklist,
        "blockers": blockers,
        "addresses": {
            "ops_links": "http://127.0.0.1:18800/ops-links",
            "xianyu_gui": "http://127.0.0.1:18800/",
            "user_site": "https://jiyu.245334.xyz/",
            "jiyu_console": "https://jiyu.245334.xyz/admin/dashboard",
            "jiyu_health": "https://jiyu.245334.xyz/api/health",
        },
        "lock_state": lock.get("state"),
        "loop_stage": loop_watch.get("stage"),
        "buyer_stage": progress.get("stage"),
        "buyer_site_smoke": buyer_smoke,
        "buyer_site_smoke_plan": buyer_smoke_plan,
    }


def _cc_auto_ship_resume_preflight() -> dict:
    """恢复常驻自动发货前的安全预检；不发货、不分配卡密。"""
    lock = _cc_public_sale_lock_summary(refresh=False)
    gates = lock.get("gates") if isinstance(lock.get("gates"), dict) else {}
    refreshed_inventory = False
    if gates.get("inventory_known") is False:
        # 恢复前检查要替老板自动跑一次只读刷新，避免老板多记“先刷新上架锁”这一步。
        lock = _cc_public_sale_lock_summary(refresh=True)
        gates = lock.get("gates") if isinstance(lock.get("gates"), dict) else {}
        refreshed_inventory = True
    blockers: list[str] = []

    if gates.get("webhook_configured") is False:
        blockers.append("自动发货 webhook 未配置，不能恢复常驻自动发货")
    if gates.get("ws_connected") is False:
        blockers.append("闲鱼助手不在线，先打开卖家 Chromium 并确认已登录")
    if gates.get("cookie_ok") is False:
        blockers.append("闲鱼登录状态异常，先扫码/刷新 Cookie")
    if not gates.get("pending_rescue_clear"):
        blockers.append("补救队列还没清空，先处理未发出的卡密")
    if not gates.get("inventory_known"):
        blockers.append("库存/渠道证据未刷新，先点“刷新上架锁”")
    else:
        if not gates.get("inventory_ready"):
            blockers.append("可售卡密库存为 0，先补库存")
        if not gates.get("redemptions_ready"):
            blockers.append("Sub2API 可售兑换码为 0，先补兑换码")
        if not gates.get("channels_ready"):
            blockers.append("Sub2API 10 渠道 / 10 监控合同未满足")
        if not gates.get("buyer_self_service_ready"):
            blockers.append("买家主站或 API 网关异常，先修复公网入口")
        if not gates.get("webhook_public_locked"):
            blockers.append("闲鱼发货 webhook 未授权拦截异常，先修复安全门")
        if not gates.get("ccswitch_import_ready"):
            blockers.append("CC Switch 导入入口异常，先修复导入页")
    if not gates.get("strict_real_order_ready"):
        blockers.append("真实小额单严格门未通过，先用“只放行一次发卡”继续内测")

    ok = len(blockers) == 0
    return {
        "ok": ok,
        "safe_to_resume": ok,
        "state": lock.get("state"),
        "state_label": lock.get("state_label"),
        "blockers": blockers,
        "nextAction": "可以恢复自动发货；恢复后建议先小流量观察。" if ok else blockers[0],
        "can_public_sale_after_resume": ok,
        "refreshed_inventory": refreshed_inventory,
        "lock": {
            "can_public_sale": bool(lock.get("can_public_sale")),
            "can_internal_test": bool(lock.get("can_internal_test")),
            "blockers": lock.get("blockers") or [],
        },
    }


def _cc_operator_mode_summary() -> dict:
    """返回老板操作台需要的人工控制状态。"""
    auto = _cc_auto_ship_status()
    sale = _cc_sale_readiness_summary()
    watch = _cc_loop_watch_summary()
    shipments = {}
    mappings = []
    if _ctx and hasattr(_ctx, "cc_shipment_summary"):
        with contextlib.suppress(Exception):
            shipments = _ctx.cc_shipment_summary()
    if _ctx and hasattr(_ctx, "list_cc_item_mappings"):
        with contextlib.suppress(Exception):
            mappings = _ctx.list_cc_item_mappings(include_disabled=True)
    enabled_mappings = len([m for m in mappings if m.get("enabled")])
    operator_state = get_operator_state()
    one_shot = operator_state.get("one_shot_delivery") or {}
    return {
        "auto_ship_paused": bool(operator_state.get("auto_ship_paused")),
        "pause_reason": operator_state.get("pause_reason") or "",
        "pause_updated_at": operator_state.get("updated_at"),
        "one_shot_delivery": one_shot,
        "one_shot_delivery_active": bool(one_shot.get("active")),
        "auto_resume_canary": operator_state.get("auto_resume_canary") or {},
        "auto_resume_canary_active": bool((operator_state.get("auto_resume_canary") or {}).get("active")),
        "webhook_configured": bool(auto.get("configured")),
        "auto_ship_operational": bool(auto.get("operational")),
        "paid_order_poll_enabled": bool(auto.get("paid_order_poll_enabled")),
        "paid_order_poll_interval_seconds": int(auto.get("paid_order_poll_interval_seconds") or 60),
        "can_auto_ship_paid_orders": bool(sale.get("can_auto_ship_paid_orders")),
        "stage": watch.get("stage"),
        "stage_label": watch.get("stage_label"),
        "next_action": watch.get("next_action"),
        "pending_rescue": int((shipments or {}).get("pending_rescue") or 0),
        "sent_shipments": int((shipments or {}).get("sent") or 0),
        "resolved_shipments": int((shipments or {}).get("resolved") or 0),
        "enabled_item_mappings": enabled_mappings,
        "total_item_mappings": len(mappings),
        "operator_steps": [
            {"label": "打开闲鱼并保持登录", "ok": bool((watch.get("checks") or {}).get("ws_connected"))},
            {"label": "绑定商品 ID 到套餐", "ok": enabled_mappings > 0},
            {
                "label": "恢复自动发货或单次放行",
                "ok": (not bool(operator_state.get("auto_ship_paused"))) or bool(one_shot.get("active")),
            },
            {"label": "补救队列清零", "ok": int((shipments or {}).get("pending_rescue") or 0) == 0},
        ],
    }


def _cc_real_order_test_pack_summary() -> dict:
    """生成真实小额单验收包；只读，不发货、不分配卡密；缺少证据时只读刷新一次。"""
    audit_error = ""
    if not (_last_cc_readiness_audit or {}).get("updated_at"):
        try:
            _run_cc_readiness_audit("read_only")
        except Exception as e:
            audit_error = _safe_error(e)
            logger.warning(f"[XianyuAdmin] 实单验收包只读刷新失败: {scrub_secrets(str(e))}")
    lock = _cc_public_sale_lock_summary(refresh=False)
    loop_watch = _cc_loop_watch_summary()
    buyer_progress = _cc_buyer_chain_progress_summary()
    next_action = _cc_operator_next_action_summary()
    readiness = _cc_sale_readiness_summary()
    buyer_site_smoke = _cc_buyer_site_smoke_summary()
    buyer_site_smoke_plan = _cc_buyer_site_smoke_plan_summary()
    product_template = _build_cc_product_template(
        title="CC中转测试卡",
        plan_id=str((readiness.get("plan_routing") or {}).get("default_plan_id") or "默认套餐"),
        price="小额测试价",
    )
    steps = buyer_progress.get("steps") if isinstance(buyer_progress.get("steps"), dict) else {}
    gates = lock.get("gates") if isinstance(lock.get("gates"), dict) else {}
    can_start_real_order_test = bool(
        lock.get("can_internal_test")
        and not lock.get("can_public_sale")
        and loop_watch.get("stage") == "waiting_paid_order"
    )
    checkpoints = [
        {
            "key": "preflight",
            "label": "上架前安全锁",
            "owner": "system",
            "ok": bool(lock.get("can_internal_test")),
            "action": "确认内测发货已放行，正式售卖仍保持锁定。",
        },
        {
            "key": "publish_paid_order",
            "label": "发布小额测试商品并真实付款",
            "owner": "operator",
            "ok": int((loop_watch.get("checks") or {}).get("sent_real_orders") or 0) > 0,
            "action": "你在闲鱼发布 1 个小额测试商品，并完成真实付款；系统不能伪造这一步。",
        },
        {
            "key": "auto_ship",
            "label": "自动分配卡密并发送话术",
            "owner": "system",
            "ok": bool(steps.get("paid_order_shipped")),
            "action": "闲鱼助手检测到已付款后自动调用 webhook、分配未使用卡密并发送发货话术。",
        },
        {
            "key": "redeem",
            "label": "买家注册/登录并兑换",
            "owner": "buyer",
            "ok": bool(steps.get("card_redeemed")),
            "action": "买家打开用户主站，注册或登录后输入兑换码到账。",
        },
        {
            "key": "api_key",
            "label": "买家创建 API Key",
            "owner": "buyer",
            "ok": bool(steps.get("api_key_created")),
            "action": "买家在用户主站创建 API Key。",
        },
        {
            "key": "ccswitch_import",
            "label": "买家导入 CC Switch",
            "owner": "buyer",
            "ok": bool(gates.get("ccswitch_import_ready")) and bool(steps.get("api_key_created")),
            "action": "买家进入 CC Switch 导入入口，导入后选择模型。",
        },
        {
            "key": "model_call",
            "label": "买家调一次模型",
            "owner": "buyer",
            "ok": bool(steps.get("model_called")),
            "action": "买家用创建的 Key 调一次模型；严格门会读取同单模型调用证据。",
        },
        {
            "key": "buyer_site_smoke",
            "label": "站内买家烟测",
            "owner": "system",
            "ok": bool(buyer_site_smoke.get("ok")),
            "action": "只读证据：兑换、API Key 和模型调用三个增量都为正才算完整；它不替代真实闲鱼同单严格门。",
        },
        {
            "key": "strict_gate",
            "label": "正式售卖严格门",
            "owner": "system",
            "ok": bool(steps.get("same_order_verified")),
            "action": "后台自动观察；也可手动运行正式售卖严格门确认同一真实订单闭环。",
        },
    ]
    return {
        "ok": True,
        "generated_at": now_et().isoformat(),
        "state": next_action.get("state") or lock.get("state"),
        "title": "真实小额单验收包",
        "can_start_real_order_test": can_start_real_order_test,
        "can_public_sale": bool(lock.get("can_public_sale")),
        "primary_action": next_action.get("primary_action") or lock.get("next_action"),
        "audit_error": audit_error,
        "current_blockers": lock.get("blockers") if isinstance(lock.get("blockers"), list) else [],
        "checkpoints": checkpoints,
        "buyer_site_smoke": buyer_site_smoke,
        "buyer_site_smoke_plan": buyer_site_smoke_plan,
        "product_template": product_template,
        "addresses": {
            "ops_links": "http://127.0.0.1:18800/ops-links",
            "xianyu_gui": "http://127.0.0.1:18800/",
            "user_site": "https://jiyu.245334.xyz/",
            "jiyu_console": "https://jiyu.245334.xyz/admin/dashboard",
            "jiyu_health": "https://jiyu.245334.xyz/api/health",
            "ccswitch_entry": "https://jiyu.245334.xyz/",
            "model_gateway": "https://jiyu.245334.xyz/v1",
        },
        "auto_watch": {
            "readiness_audit_auto_enabled": _auto_readiness_audit_config()["enabled"],
            "strict_audit_auto_enabled": _auto_strict_audit_config()["enabled"],
            "ops_notify_enabled": _ops_notify_config()["enabled"],
            "loop_stage": loop_watch.get("stage"),
            "buyer_stage": buyer_progress.get("stage"),
        },
        "safety_boundaries": [
            "不自动砍价",
            "不批量私信",
            "不绕过闲鱼风控",
            "不伪造付款订单",
        ],
    }


def _cc_auto_strict_audit_status(lock: dict, loop_watch: dict, auto_strict_result: dict | None = None) -> dict:
    """返回严格门自动观察的只读状态，供覆盖清单、统一快照和提醒复用。"""
    auto_strict_result = auto_strict_result or {}
    auto_strict_config = _auto_strict_audit_config()
    loop_stage = str((loop_watch or {}).get("stage") or "")
    if (lock or {}).get("can_public_sale"):
        auto_strict_state = "verified"
        auto_strict_label = "真实单严格门已通过"
        auto_strict_reason = "public_sale_ready"
    elif not auto_strict_config["enabled"]:
        auto_strict_state = "disabled"
        auto_strict_label = "严格门自动观察已关闭"
        auto_strict_reason = "disabled"
    elif auto_strict_result:
        auto_strict_state = "ran"
        auto_strict_label = "刚刚自动运行了严格门只读观察"
        auto_strict_reason = str(auto_strict_result.get("stage") or loop_stage or "unknown")
    elif loop_stage == "waiting_buyer_chain":
        auto_strict_state = "armed"
        auto_strict_label = "已检测到真实订单，后台会自动观察兑换/API/调模型严格门"
        auto_strict_reason = "waiting_buyer_chain"
    elif loop_stage == "waiting_paid_order":
        auto_strict_state = "waiting_paid_order"
        auto_strict_label = "严格门自动观察已开启，正在等待真实已付款订单"
        auto_strict_reason = "waiting_paid_order"
    else:
        auto_strict_state = "waiting_prerequisite"
        auto_strict_label = "严格门自动观察已开启，正在等待前置链路满足"
        auto_strict_reason = loop_stage or "unknown"
    return {
        "enabled": bool(auto_strict_config["enabled"]),
        "state": auto_strict_state,
        "label": auto_strict_label,
        "reason": auto_strict_reason,
        "interval_ms": auto_strict_config["interval_ms"],
        "last_background_at": (_last_background_strict_audit_at if _last_background_strict_audit_at > 0 else None),
    }


def _cc_buyer_site_smoke_summary() -> dict:
    """返回买家站内链路的只读烟测证据；不替代真实闲鱼同单严格门。"""
    audit = _last_cc_readiness_audit or {}
    redeemed_delta = int(audit.get("redeemed_delta") or 0)
    active_token_delta = int(audit.get("active_token_delta") or 0)
    model_log_delta = int(audit.get("model_log_delta") or 0)
    strict_ready = _strict_audit_ready()
    complete = strict_ready or (redeemed_delta > 0 and active_token_delta > 0 and model_log_delta > 0)
    partial = not complete and any(value > 0 for value in (redeemed_delta, active_token_delta, model_log_delta))
    if strict_ready:
        state = "verified_by_real_order"
        label = "真实订单严格门已证明买家链路完整"
    elif complete:
        state = "complete"
        label = "站内买家链路已有完整烟测证据"
    elif partial:
        state = "partial"
        label = "站内买家链路只有部分烟测证据"
    else:
        state = "no_recent_proof"
        label = "暂无最近完整站内买家链路烟测证据"
    return {
        "ok": complete,
        "partial": partial,
        "state": state,
        "label": label,
        "redeemed_delta": redeemed_delta,
        "active_token_delta": active_token_delta,
        "model_log_delta": model_log_delta,
        "updated_at": audit.get("updated_at"),
        "note": "只读计数证明；正式售卖仍以真实闲鱼同单严格门为准。",
    }


def _cc_buyer_site_smoke_plan_summary() -> dict:
    """说明站内买家烟测是否可准备执行；本函数只读，不创建用户、不兑换、不调模型。"""
    lock = _cc_public_sale_lock_summary(refresh=False)
    smoke = _cc_buyer_site_smoke_summary()
    inventory = lock.get("inventory") if isinstance(lock.get("inventory"), dict) else {}
    blockers = lock.get("blockers") if isinstance(lock.get("blockers"), list) else []
    can_prepare = bool(
        lock.get("can_internal_test")
        and int(inventory.get("unused_cards") or 0) > 0
        and int(inventory.get("redeem_available") or 0) > 0
        and int(inventory.get("active_channels") or 0) == 10
        and int(inventory.get("enabled_monitors") or 0) == 10
        and inventory.get("buyer_self_service_ok") is not False
        and inventory.get("ccswitch_entry_ok") is not False
    )
    if smoke.get("ok"):
        state = "already_proven"
        title = "站内买家烟测已有完整证据"
        primary_action = "不需要额外跑站内烟测；继续等待真实闲鱼小额单严格门。"
    elif can_prepare:
        state = "ready_requires_confirmation"
        title = "可准备站内买家烟测，但需要老板确认"
        primary_action = (
            "自动站内烟测会写入生产用户、兑换码、API Key 和可能的模型调用日志；未获明确确认前只展示计划，不执行。"
        )
    else:
        state = "not_ready"
        title = "站内买家烟测前置条件不足"
        primary_action = blockers[0] if blockers else "先刷新上架锁并处理库存、兑换码、渠道或买家入口异常。"
    return {
        "ok": bool(smoke.get("ok")),
        "state": state,
        "title": title,
        "primary_action": primary_action,
        "can_prepare": can_prepare,
        "requires_owner_confirmation": True,
        "executes_now": False,
        "current_smoke": smoke,
        "would_write": [
            "创建临时买家账号",
            "消耗 1 张临时兑换码并写入 Sub2API 兑换记录",
            "创建 1 个临时 API Key",
            "可选：发起 1 次最小模型调用并写入调用日志",
        ],
        "cleanup_required": [
            "禁用或删除临时 API Key",
            "清理临时买家账号或标记为内测账号",
            "标记临时兑换码/履约记录为内测烟测，不混入正式售卖判断",
            "保留脱敏计数证据，不保存卡密、API Key 或密码",
        ],
        "safety_boundaries": [
            "不自动砍价",
            "不批量私信",
            "不绕过闲鱼风控",
            "不伪造付款订单",
            "未获确认不写生产数据",
        ],
    }


def _cc_automation_coverage_summary() -> dict:
    """把全自动闭环目标拆成逐项证据，避免把内测可发货误判为正式闭环。"""
    audit_error = ""
    if not (_last_cc_readiness_audit or {}).get("updated_at"):
        try:
            _run_cc_readiness_audit("read_only")
        except Exception as e:
            audit_error = _safe_error(e)
            logger.warning(f"[XianyuAdmin] 闭环覆盖清单只读刷新失败: {scrub_secrets(str(e))}")
    lock = _cc_public_sale_lock_summary(refresh=False)
    loop_watch = _cc_loop_watch_summary()
    auto_strict_result = {}
    if _should_run_background_strict_audit(loop_watch):
        auto_strict_result = _run_background_strict_audit_once()
        # 严格门只读观察可能刚刚把同单闭环写入本地摘要，重新读取一次展示最新状态。
        lock = _cc_public_sale_lock_summary(refresh=False)
        loop_watch = _cc_loop_watch_summary()
    buyer_progress = _cc_buyer_chain_progress_summary()
    readiness = _cc_sale_readiness_summary()
    audit = _last_cc_readiness_audit or {}
    gates = lock.get("gates") if isinstance(lock.get("gates"), dict) else {}
    checks = loop_watch.get("checks") if isinstance(loop_watch.get("checks"), dict) else {}
    progress_steps = buyer_progress.get("steps") if isinstance(buyer_progress.get("steps"), dict) else {}
    plan_routing = readiness.get("plan_routing") if isinstance(readiness.get("plan_routing"), dict) else {}
    buyer_self_service = (
        readiness.get("buyer_self_service") if isinstance(readiness.get("buyer_self_service"), dict) else {}
    )
    ccswitch_import = readiness.get("ccswitch_import") if isinstance(readiness.get("ccswitch_import"), dict) else {}
    buyer_site_smoke = _cc_buyer_site_smoke_summary()
    buyer_site_smoke_plan = _cc_buyer_site_smoke_plan_summary()

    def make_item(
        key: str,
        label: str,
        ok: bool,
        evidence: str,
        next_action: str = "",
        external: bool = False,
    ) -> dict:
        return {
            "key": key,
            "label": label,
            "ok": bool(ok),
            "external": bool(external),
            "evidence": evidence,
            "next_action": next_action,
        }

    coverage = [
        make_item(
            "chrome_bookmark_folder",
            "Chrome 运营入口书签",
            bool(audit.get("chrome_bookmarks")),
            "只读巡检 chromeBookmarks.ok=true" if audit.get("chrome_bookmarks") else "尚未刷新到书签巡检证据",
            "运行 Chrome 书签修复脚本或刷新上架锁",
        ),
        make_item(
            "paid_order_detection",
            "检测闲鱼已付款订单",
            bool(loop_watch.get("can_auto_ship_paid_orders")),
            f"webhook={bool((readiness.get('checks') or {}).get('webhook_configured'))}, ws={bool((readiness.get('checks') or {}).get('ws_connected'))}, cookie={bool((readiness.get('checks') or {}).get('cookie_ok'))}",
            "保持闲鱼助手在线、Cookie 有效、webhook 已配置",
        ),
        make_item(
            "card_allocation",
            "自动分配未使用兑换码",
            bool(gates.get("inventory_ready") and gates.get("redemptions_ready")),
            f"可售兑换码={audit.get('redeem_available', 0)}",
            "补充 Sub2API 可售兑换码",
        ),
        make_item(
            "delivery_message_send",
            "生成并发送发货话术",
            bool(loop_watch.get("can_auto_ship_paid_orders") and int(checks.get("pending_rescue") or 0) == 0),
            f"自动发货={bool(loop_watch.get('can_auto_ship_paid_orders'))}，补救队列={int(checks.get('pending_rescue') or 0)}",
            "若补救队列非 0，等待自动补发或在 GUI 手动重试",
        ),
        make_item(
            "fulfillment_writeback",
            "回写履约状态",
            bool(_ctx and hasattr(_ctx, "cc_shipment_summary")),
            "本机 cc_shipments 履约表可用，严格门可按订单哈希回写 buyer_chain_status",
            "启动本机闲鱼助手并确认 SQLite 可写",
        ),
        make_item(
            "buyer_register_redeem",
            "买家自助注册/兑换",
            bool(gates.get("buyer_self_service_ready") and gates.get("redemptions_ready")),
            f"主站HTTP={buyer_self_service.get('main_http', audit.get('public_main_http', '未知'))}，兑换码={audit.get('redeem_available', 0)}，兑换Δ={buyer_site_smoke['redeemed_delta']}",
            "修复买家主站或补充启用兑换码",
        ),
        make_item(
            "api_key_creation",
            "买家创建 API Key",
            bool(gates.get("buyer_self_service_ready")),
            f"用户主站可用={bool(gates.get('buyer_self_service_ready'))}，KeyΔ={buyer_site_smoke['active_token_delta']}",
            "修复用户主站/API Key 页面",
        ),
        make_item(
            "cc_switch_import",
            "CC Switch 导入",
            bool(gates.get("ccswitch_import_ready")),
            f"入口HTTP={ccswitch_import.get('page_http', audit.get('ccswitch_entry_http', '未知'))}，导入标记={bool(ccswitch_import.get('has_import_link_marker', audit.get('ccswitch_has_import_link_marker')))}",
            "修复 JIYU 首页 CC Switch 导入入口",
        ),
        make_item(
            "model_call",
            "模型调用",
            bool(gates.get("channels_ready")),
            f"启用渠道={audit.get('sub2api_active_channels', 0)}，监控={audit.get('sub2api_enabled_monitors', 0)}，模型日志Δ={buyer_site_smoke['model_log_delta']}",
            "刷新/修复 Sub2API 渠道和监控状态",
        ),
        make_item(
            "safety_boundaries",
            "合规边界",
            True,
            "不自动砍价、不批量私信、不绕风控；webhook 未授权访问应为 401",
        ),
        make_item(
            "real_order_strict_gate",
            "真实小额单严格门",
            bool(progress_steps.get("same_order_verified")),
            f"真实订单={int(checks.get('sent_real_orders') or 0)}，同单完成={int((buyer_progress.get('counts') or {}).get('same_order_ready') or 0)}",
            "发布 1 个小额闲鱼测试商品，真实付款后让买家完成兑换/API Key/CC Switch/调模型",
            external=True,
        ),
    ]
    internal_items = [entry for entry in coverage if not entry["external"]]
    completed = len([entry for entry in coverage if entry["ok"]])
    internal_completed = len([entry for entry in internal_items if entry["ok"]])
    missing = [entry for entry in coverage if not entry["ok"]]
    return {
        "ok": True,
        "generated_at": now_et().isoformat(),
        "state": "public_sale_ready" if lock.get("can_public_sale") else loop_watch.get("stage"),
        "internal_automation_ready": internal_completed == len(internal_items),
        "public_sale_ready": bool(lock.get("can_public_sale")),
        "completed": completed,
        "total": len(coverage),
        "external_blocker": not bool(progress_steps.get("same_order_verified")),
        "items": coverage,
        "missing": missing,
        "audit_error": audit_error,
        "auto_strict_audit": auto_strict_result,
        "auto_strict_audit_status": _cc_auto_strict_audit_status(lock, loop_watch, auto_strict_result),
        "buyer_site_smoke": buyer_site_smoke,
        "buyer_site_smoke_plan": buyer_site_smoke_plan,
        "next_action": (
            missing[0]["next_action"] if missing else "可以小批量正式售卖并持续观察库存、上游余额和补救队列。"
        ),
        "plan_routing": plan_routing,
    }


def _project_file_text(relative_path: str) -> str:
    """读取项目内文本文件；失败时返回空串，避免证据接口影响运行态。"""
    try:
        root = Path(__file__).resolve().parents[4]
        return (root / relative_path).read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""


def _manual_precheck_item(
    key: str,
    label: str,
    ok: bool,
    evidence: str,
    next_action: str = "",
    category: str = "precheck",
) -> dict:
    """生成老板人工预检证据项；只描述结论，不泄露卡密或 Token。"""
    return {
        "key": key,
        "label": label,
        "category": category,
        "ok": bool(ok),
        "status": "pass" if ok else "missing",
        "evidence": evidence,
        "next_action": next_action,
    }


def _cc_manual_precheck_evidence_summary() -> dict:
    """汇总人工预检问题的只读证据，不发货、不分配卡密、不恢复自动发货。"""
    xianyu_admin_py = _project_file_text("packages/clawbot/src/xianyu/xianyu_admin.py")
    xianyu_live_py = _project_file_text("packages/clawbot/src/xianyu/xianyu_live.py")
    xianyu_apis_py = _project_file_text("packages/clawbot/src/xianyu/xianyu_apis.py")
    operator_state = get_operator_state()
    one_shot = operator_state.get("one_shot_delivery") or {}
    canary = operator_state.get("auto_resume_canary") or {}
    lock = _cc_public_sale_lock_summary(refresh=False)

    duplicate_guard_ok = all(
        token in (xianyu_admin_py + xianyu_live_py)
        for token in [
            "browser_delivery_claimed",
            "message_send_inflight",
            "message_send_uncertain",
            "consume_one_shot_delivery",
            "alreadyHandled",
            "consume_auto_resume_canary_after_sent",
            "operator_paused",
        ]
    )

    auto_ship_strategy_ok = all(
        token in (xianyu_admin_py + xianyu_apis_py)
        for token in [
            "confirm-xianyu-backend",
            "CC_XIANYU_AUTO_CONFIRM_SHIPMENT_ENABLED",
            "mtop.taobao.idle.logistic.consign.dummy",
            "confirm_dummy_shipment",
        ]
    )

    strict_ready = bool(_strict_audit_ready())
    paused = bool(operator_state.get("auto_ship_paused"))
    one_shot_active = bool(one_shot.get("active"))
    canary_active = bool(canary.get("active"))
    effective_state = str(lock.get("state") or "")
    effective_label = str(lock.get("state_label") or "")
    if strict_ready and paused and not bool(lock.get("can_public_sale")):
        effective_state = "paused_after_strict_gate"
        effective_label = "严格门已通过，自动发货暂停保护"

    items = [
        _manual_precheck_item(
            "duplicate_delivery_guard",
            "闲鱼卡密重复发送风险已加锁",
            duplicate_guard_ok,
            f"源码包含原子领取、单次放行、已处理幂等、暂停拦截和首单观察；当前暂停={paused}，单次放行={one_shot_active}，首单观察={canary_active}",
            "恢复自动发货前先点恢复前安全检查；恢复后观察第 1 单自动暂停。",
            "xianyu",
        ),
        _manual_precheck_item(
            "xianyu_auto_ship_strategy",
            "闲鱼自动发货策略已有可控落地路径",
            auto_ship_strategy_ok,
            "已保留浏览器当前页兜底，并新增默认关闭的 H5 虚拟商品确认发货实验入口"
            if auto_ship_strategy_ok
            else "缺少后端确认发货或浏览器兜底证据",
            "只对真实数字订单、已发卡记录并显式开启时实验后端确认发货。",
            "xianyu",
        ),
        _manual_precheck_item(
            "strict_real_order_chain",
            "真实小额单严格门证据",
            strict_ready,
            f"严格门状态={lock.get('state') or ''}，可公开售卖={bool(lock.get('can_public_sale'))}；若暂停保护，说明严格门过但仍等老板恢复自动发货",
            "若未通过，继续跑 xy_oid_* 真实小额单；若已通过，只等老板确认恢复自动发货。",
            "strict_gate",
        ),
    ]
    passed = len([item for item in items if item["ok"]])
    owner_actions = []
    if paused:
        owner_actions.append("自动发货仍处于暂停保护；恢复前先点 18800 的“恢复前安全检查”。")
    if not strict_ready:
        owner_actions.append("严格门证据不足时，需要新的 xy_oid_* 真实小额单完成兑换/API Key/调模型。")
    return _scrub_status_report(
        {
            "ok": True,
            "generated_at": now_et().isoformat(),
            "title": "人工预检闭环证据",
            "passed": passed,
            "total": len(items),
            "precheck_ready": passed == len(items),
            "can_public_sale": bool(lock.get("can_public_sale")),
            "state": effective_state,
            "state_label": effective_label,
            "items": items,
            "missing": [item for item in items if not item["ok"]],
            "owner_actions": owner_actions,
            "safety": {
                "read_only": True,
                "does_not_send_card": True,
                "does_not_click_xianyu_ship": True,
                "does_not_resume_auto_ship": True,
            },
        }
    )


def _cc_ops_snapshot_summary() -> dict:
    """给 GUI/通知/书签入口使用的一次性运营快照；只读、不触发审计。"""
    status = {"service": "running", "ws_connected": False, "cookie_ok": False}
    status["cc_auto_ship"] = _cc_auto_ship_status()
    if _ctx and hasattr(_ctx, "cc_shipment_summary"):
        status["cc_shipments"] = _ctx.cc_shipment_summary()
    if _ctx and hasattr(_ctx, "cc_final_sale_gate_summary"):
        status["cc_final_sale_gate"] = _ctx.cc_final_sale_gate_summary()
    if _ctx and hasattr(_ctx, "list_cc_item_mappings"):
        mappings = _ctx.list_cc_item_mappings(include_disabled=True)
        status["cc_item_mappings"] = {
            "total": len(mappings),
            "enabled": len([m for m in mappings if m.get("enabled")]),
        }
    live_snapshot = _live_runtime_snapshot()
    status["ws_connected"] = bool(live_snapshot.get("ws_connected"))
    status["cookie_ok"] = bool(live_snapshot.get("cookie_ok"))
    status["manual_chats"] = max(0, int(live_snapshot.get("manual_chats") or 0))

    next_action = _cc_operator_next_action_summary()
    lock = _cc_public_sale_lock_summary(refresh=False)
    loop_watch = _cc_loop_watch_summary()
    buyer_progress = _cc_buyer_chain_progress_summary()
    auto_strict_status = _cc_auto_strict_audit_status(lock, loop_watch)
    buyer_site_smoke = _cc_buyer_site_smoke_summary()
    buyer_site_smoke_plan = _cc_buyer_site_smoke_plan_summary()
    protected_pause_ready = bool(
        lock.get("can_internal_test")
        and lock.get("state") in {"paused_after_strict_gate", "paused_internal_test_ready"}
    )
    return {
        "ok": bool(
            status.get("ws_connected")
            and status.get("cookie_ok")
            and ((status.get("cc_auto_ship") or {}).get("operational") or protected_pause_ready)
            and int((status.get("cc_shipments") or {}).get("pending_rescue") or 0) == 0
        ),
        "generated_at": now_et().isoformat(),
        "next_action": next_action,
        "status": status,
        "sale_lock": lock,
        "loop_watch": loop_watch,
        "buyer_progress": buyer_progress,
        "auto_strict_audit_status": auto_strict_status,
        "buyer_site_smoke": buyer_site_smoke,
        "buyer_site_smoke_plan": buyer_site_smoke_plan,
    }


def _notification_signature(payload: dict) -> str:
    """提取会影响老板行动的状态，避免后台提醒重复刷屏。"""
    fields = {
        "severity": payload.get("severity"),
        "state": payload.get("state"),
        "loop_stage": payload.get("loop_stage"),
        "buyer_stage": payload.get("buyer_stage"),
        "buyer_attention_stage": payload.get("buyer_attention_stage"),
        "pending_rescue": payload.get("pending_rescue"),
        "ws_connected": payload.get("ws_connected"),
        "cookie_ok": payload.get("cookie_ok"),
        "unused_cards": payload.get("unused_cards"),
        "low_inventory": payload.get("low_inventory"),
        "can_public_sale": payload.get("can_public_sale"),
    }
    return json.dumps(fields, ensure_ascii=False, sort_keys=True)


def _buyer_chain_notification_override(buyer_progress: dict, loop_watch: dict) -> dict:
    """真实订单发货后，生成买家链路卡点提醒；只提醒老板，不自动联系买家。"""
    if not isinstance(buyer_progress, dict):
        return {}
    stage = str(buyer_progress.get("stage") or "")
    loop_stage = str(loop_watch.get("stage") or "")
    if stage == "verified":
        return {
            "severity": "ok",
            "state": "buyer_chain_verified",
            "title": "真实单买家闭环已通过",
            "body": "同一真实订单已完成发货、兑换、API Key 和模型调用。",
            "buyer_attention_stage": stage,
        }
    if loop_stage != "waiting_buyer_chain" and stage not in {
        "waiting_strict_audit",
        "waiting_redeem",
        "waiting_api_key",
        "waiting_model_call",
        "waiting_same_order_match",
    }:
        return {}

    mapping = {
        "waiting_strict_audit": (
            "已自动发货，等待严格门确认",
            "系统会自动观察买家是否完成兑换、创建 API Key 和模型调用。",
        ),
        "waiting_redeem": (
            "买家尚未兑换卡密",
            "已自动发货，但买家还没完成兑换；可人工确认对方是否打开兑换入口。",
        ),
        "waiting_api_key": (
            "买家尚未创建 API Key",
            "买家已兑换到账，但还没创建 API Key；可提醒其进入用户主站创建。",
        ),
        "waiting_model_call": (
            "买家尚未调模型",
            "买家已兑换并创建 API Key，但还没完成模型测试；可提醒其导入 CC Switch 后调一次模型。",
        ),
        "waiting_same_order_match": (
            "同单闭环待确认",
            "已有部分买家行为，但严格门尚未确认属于同一真实订单；继续观察或手动运行严格门。",
        ),
    }
    if stage not in mapping:
        return {}
    title, body = mapping[stage]
    return {
        "severity": "warning",
        "state": stage,
        "title": title,
        "body": body,
        "buyer_attention_stage": stage,
    }


def _build_ops_notification(snapshot: dict) -> dict:
    """把运营快照压缩成本机通知内容；不包含 token、卡密、API Key 等敏感信息。"""
    config = _ops_notify_config()
    next_action = snapshot.get("next_action") if isinstance(snapshot.get("next_action"), dict) else {}
    status = snapshot.get("status") if isinstance(snapshot.get("status"), dict) else {}
    sale_lock = snapshot.get("sale_lock") if isinstance(snapshot.get("sale_lock"), dict) else {}
    inventory = sale_lock.get("inventory") if isinstance(sale_lock.get("inventory"), dict) else {}
    loop_watch = snapshot.get("loop_watch") if isinstance(snapshot.get("loop_watch"), dict) else {}
    buyer_progress = snapshot.get("buyer_progress") if isinstance(snapshot.get("buyer_progress"), dict) else {}
    cc_shipments = status.get("cc_shipments") if isinstance(status.get("cc_shipments"), dict) else {}

    pending_rescue = int(cc_shipments.get("pending_rescue") or 0)
    unused_cards_raw = inventory.get("unused_cards")
    unused_cards = int(unused_cards_raw) if unused_cards_raw is not None else None
    low_inventory = unused_cards is not None and unused_cards <= int(config["low_inventory_threshold"])

    severity = next_action.get("severity") or "warning"
    title = next_action.get("title") or "CC中转状态变化"
    body = next_action.get("primary_action") or "打开本机运营入口查看状态。"
    state = next_action.get("state") or sale_lock.get("state") or "unknown"
    buyer_override = _buyer_chain_notification_override(buyer_progress, loop_watch)
    if not bool(status.get("ws_connected")):
        severity = "danger"
        state = "xianyu_ws_offline"
        title = "闲鱼助手离线"
        body = "WebSocket 未连接，自动发货会暂停；请保持闲鱼助手运行。"
    elif not bool(status.get("cookie_ok")):
        severity = "danger"
        state = "xianyu_cookie_invalid"
        title = "闲鱼登录状态异常"
        body = "Cookie 需要恢复；请打开闲鱼助手重新登录后再继续内测。"
    elif pending_rescue > 0:
        severity = "danger"
        state = "rescue_required"
        title = "有发货补救待处理"
        body = "补救队列不为空；系统会尝试自动补发，也可以在 GUI 里手动重试。"
    elif buyer_override:
        severity = buyer_override["severity"]
        state = buyer_override["state"]
        title = buyer_override["title"]
        body = buyer_override["body"]
    elif low_inventory:
        severity = "warning"
        state = "low_inventory"
        title = "兑换码库存偏低"
        body = f"未售兑换码剩余 {unused_cards} 个；建议补货后再扩大售卖。"

    payload = {
        "severity": severity,
        "state": state,
        "title": title,
        "body": body,
        "loop_stage": loop_watch.get("stage"),
        "buyer_stage": buyer_progress.get("stage"),
        "buyer_attention_stage": buyer_override.get("buyer_attention_stage", ""),
        "pending_rescue": pending_rescue,
        "ws_connected": bool(status.get("ws_connected")),
        "cookie_ok": bool(status.get("cookie_ok")),
        "unused_cards": unused_cards,
        "low_inventory": low_inventory,
        "can_public_sale": bool(sale_lock.get("can_public_sale")),
    }
    payload["signature"] = _notification_signature(payload)
    return payload


def _quote_osascript_string(value: str) -> str:
    """转义 macOS 通知脚本字符串，避免中文或引号导致脚本失败。"""
    return str(value or "").replace("\\", "\\\\").replace('"', '\\"')


def _send_local_ops_notification(payload: dict) -> dict:
    """发送本机 macOS 通知；非 macOS 环境降级为日志记录。"""
    title = str(payload.get("title") or "CC中转状态变化")[:80]
    body = str(payload.get("body") or "打开本机运营入口查看状态。")[:240]
    severity = str(payload.get("severity") or "warning")
    if os.getenv("CC_XIANYU_OPS_NOTIFY_DRY_RUN", "").strip().lower() in {"1", "true", "yes", "on"}:
        return {"sent": True, "dry_run": True, "title": title, "severity": severity}
    if os.name != "posix" or not Path("/usr/bin/osascript").exists():
        logger.info("[XianyuAdmin] CC中转运营提醒: %s - %s", title, body)
        return {"sent": False, "fallback": "log", "title": title, "severity": severity}

    script = (
        f'display notification "{_quote_osascript_string(body)}" '
        f'with title "CC中转" subtitle "{_quote_osascript_string(title)}"'
    )
    result = subprocess.run(
        ["/usr/bin/osascript", "-e", script],
        text=True,
        capture_output=True,
        timeout=5,
        check=False,
    )
    ok = result.returncode == 0
    if not ok:
        logger.warning("[XianyuAdmin] 本机运营提醒发送失败: %s", scrub_secrets(result.stderr or ""))
    return {
        "sent": ok,
        "title": title,
        "severity": severity,
        "stderr": scrub_secrets((result.stderr or "")[-200:]),
    }


def _run_ops_notify_once(*, force: bool = False, now_ts: float | None = None) -> dict:
    """检查一次运营状态变化，必要时发本机通知；不会触发发货或远程写入。"""
    global _last_ops_notify_signature, _last_ops_notify_at, _last_ops_notify_result
    config = _ops_notify_config()
    if not config["enabled"] and not force:
        return {"ran": False, "reason": "disabled", "config": config}
    now_value = time.time() if now_ts is None else now_ts
    if not force and now_value - float(_last_ops_notify_at or 0) < (config["interval_ms"] / 1000):
        return {"ran": False, "reason": "throttled", "last": _last_ops_notify_result, "config": config}
    if not _ops_notify_run_lock.acquire(blocking=False):
        return {"ran": False, "reason": "already_running", "config": config}
    try:
        snapshot = _cc_ops_snapshot_summary()
        payload = _build_ops_notification(snapshot)
        changed = force or payload["signature"] != _last_ops_notify_signature
        _last_ops_notify_at = now_value
        if changed:
            send_result = _send_local_ops_notification(payload)
            _last_ops_notify_signature = payload["signature"]
        else:
            send_result = {"sent": False, "reason": "unchanged"}
        _last_ops_notify_result = {
            "ran": True,
            "changed": changed,
            "sent": bool(send_result.get("sent")),
            "payload": {
                "severity": payload["severity"],
                "state": payload["state"],
                "title": payload["title"],
                "body": payload["body"],
                "pending_rescue": payload["pending_rescue"],
                "unused_cards": payload["unused_cards"],
                "loop_stage": payload["loop_stage"],
                "buyer_stage": payload["buyer_stage"],
                "buyer_attention_stage": payload["buyer_attention_stage"],
            },
            "send": send_result,
            "updated_at": now_et().isoformat(),
            "config": config,
        }
        return _last_ops_notify_result
    except Exception as e:
        logger.error(f"[XianyuAdmin] 本机运营提醒检查失败: {scrub_secrets(str(e))}", exc_info=True)
        return {"ran": False, "reason": _safe_error(e), "config": config}
    finally:
        _ops_notify_run_lock.release()


def _should_run_background_strict_audit(
    summary: dict,
    *,
    now_ts: float | None = None,
    last_run_at: float | None = None,
) -> bool:
    """判断后台是否应该跑严格门；只在真实订单已发货后触发，避免空跑和误写。"""
    config = _auto_strict_audit_config()
    if not config["enabled"]:
        return False
    if not isinstance(summary, dict):
        return False
    if summary.get("stage") != "waiting_buyer_chain":
        return False
    if summary.get("ready_for_public_sale") is True:
        return False
    checks = summary.get("checks") if isinstance(summary.get("checks"), dict) else {}
    if int(checks.get("pending_rescue") or 0) > 0:
        return False
    if int(checks.get("sent_real_orders") or 0) <= 0:
        return False
    if not summary.get("can_auto_ship_paid_orders"):
        return False
    now_value = time.time() if now_ts is None else now_ts
    last_value = _last_background_strict_audit_at if last_run_at is None else last_run_at
    return now_value - float(last_value or 0) >= (config["interval_ms"] / 1000)


def _run_background_strict_audit_once() -> dict:
    """后台观察循环的一次执行；严格只读，不分配卡密、不发闲鱼消息。"""
    global _last_background_strict_audit_at, _last_background_strict_audit_result
    summary = _cc_loop_watch_summary()
    if not _should_run_background_strict_audit(summary):
        result = {"ran": False, "stage": summary.get("stage"), "reason": "not_ready_or_throttled"}
        _last_background_strict_audit_result = {
            **result,
            "updated_at": now_et().isoformat(),
        }
        return result
    if not _strict_audit_run_lock.acquire(blocking=False):
        result = {"ran": False, "reason": "already_running", "stage": summary.get("stage")}
        _last_background_strict_audit_result = {
            **result,
            "updated_at": now_et().isoformat(),
        }
        return result
    try:
        # 先更新时间戳，避免审计脚本较慢时循环重复启动。
        _last_background_strict_audit_at = time.time()
        audit = _run_cc_readiness_audit("strict")
        logger.info(
            "[XianyuAdmin] 后台严格门只读审计完成 ok=%s readyOrders=%s",
            bool(audit.get("ok")),
            (audit.get("summary") or {}).get("same_order_ready"),
        )
        result = {
            "ran": True,
            "ok": bool(audit.get("ok")),
            "exit_code": audit.get("exit_code"),
            "stage": summary.get("stage"),
            "same_order_ready": int((audit.get("summary") or {}).get("same_order_ready") or 0),
            "same_order_matched": int((audit.get("summary") or {}).get("same_order_matched") or 0),
            "updated_at": now_et().isoformat(),
        }
        _last_background_strict_audit_result = result
        return result
    except Exception as e:
        logger.error(f"[XianyuAdmin] 后台严格门只读审计出错: {scrub_secrets(str(e))}", exc_info=True)
        result = {
            "ran": False,
            "reason": _safe_error(e),
            "stage": summary.get("stage"),
            "updated_at": now_et().isoformat(),
        }
        _last_background_strict_audit_result = result
        return result
    finally:
        _strict_audit_run_lock.release()


def _should_run_background_readiness_audit(*, now_ts: float | None = None, last_run_at: float | None = None) -> bool:
    """判断是否需要后台刷新只读巡检缓存；不触发任何生产写操作。"""
    config = _auto_readiness_audit_config()
    if not config["enabled"]:
        return False
    now_value = time.time() if now_ts is None else now_ts
    last_value = _last_background_readiness_audit_at if last_run_at is None else last_run_at
    return now_value - float(last_value or 0) >= (config["interval_ms"] / 1000)


def _run_background_readiness_audit_once() -> dict:
    """后台刷新一次只读巡检，更新上架锁库存/兑换码/渠道证据。"""
    global _last_background_readiness_audit_at
    if not _should_run_background_readiness_audit():
        return {"ran": False, "reason": "throttled"}
    if not _readiness_audit_run_lock.acquire(blocking=False):
        return {"ran": False, "reason": "already_running"}
    try:
        _last_background_readiness_audit_at = time.time()
        audit = _run_cc_readiness_audit("read_only")
        summary = audit.get("summary") or {}
        logger.info(
            "[XianyuAdmin] 后台只读巡检完成 ok=%s redeem_available=%s monitors=%s channels=%s",
            bool(audit.get("ok")),
            summary.get("redeem_available"),
            summary.get("sub2api_enabled_monitors"),
            summary.get("sub2api_active_channels"),
        )
        return {"ran": True, "ok": bool(audit.get("ok"))}
    except Exception as e:
        logger.error(f"[XianyuAdmin] 后台只读巡检出错: {scrub_secrets(str(e))}", exc_info=True)
        return {"ran": False, "reason": _safe_error(e)}
    finally:
        _readiness_audit_run_lock.release()


def _background_readiness_audit_loop() -> None:
    """后台定时只读巡检；让上架锁库存/渠道证据自动保持新鲜。"""
    while True:
        config = _auto_readiness_audit_config()
        time.sleep(config["scan_seconds"])
        if not config["enabled"]:
            continue
        _run_background_readiness_audit_once()


def _start_background_readiness_audit_loop() -> None:
    """启动一次后台只读巡检线程，避免重复启动。"""
    global _readiness_audit_loop_started
    with _readiness_audit_loop_lock:
        if _readiness_audit_loop_started:
            return
        worker = threading.Thread(
            target=_background_readiness_audit_loop,
            daemon=True,
            name="xianyu-cc-readiness-audit",
        )
        worker.start()
        _readiness_audit_loop_started = True
        logger.info("[XianyuAdmin] 后台只读巡检已启动")


def _background_strict_audit_loop() -> None:
    """后台循环观察真实订单买家闭环；不依赖 GUI 页面保持打开。"""
    while True:
        config = _auto_strict_audit_config()
        time.sleep(config["scan_seconds"])
        if not config["enabled"]:
            continue
        _run_background_strict_audit_once()


def _start_background_strict_audit_loop() -> None:
    """启动一次后台严格门观察线程，避免 start_admin_server 重入时重复启动。"""
    global _strict_audit_loop_started
    with _strict_audit_loop_lock:
        if _strict_audit_loop_started:
            return
        worker = threading.Thread(
            target=_background_strict_audit_loop,
            daemon=True,
            name="xianyu-cc-strict-audit",
        )
        worker.start()
        _strict_audit_loop_started = True
        logger.info("[XianyuAdmin] 后台严格门观察已启动")


def _background_ops_notify_loop() -> None:
    """后台轮询运营快照，状态变化时弹本机通知。"""
    while True:
        config = _ops_notify_config()
        time.sleep(config["scan_seconds"])
        if not config["enabled"]:
            continue
        _run_ops_notify_once()


def _start_background_ops_notify_loop() -> None:
    """启动一次本机运营提醒线程，避免重复通知线程。"""
    global _ops_notify_loop_started
    with _ops_notify_loop_lock:
        if _ops_notify_loop_started:
            return
        worker = threading.Thread(
            target=_background_ops_notify_loop,
            daemon=True,
            name="xianyu-cc-ops-notify",
        )
        worker.start()
        _ops_notify_loop_started = True
        logger.info("[XianyuAdmin] 本机运营提醒已启动")


@app.post("/api/session")
def create_admin_session(request: Request):
    """用一次全局 Token 换取仅限本管理面的短时 HttpOnly 会话。"""
    expected = _expected_api_token()
    provided = request.headers.get("x-api-token", "")
    if not expected:
        raise HTTPException(status_code=503, detail="管理面未配置 OPENCLAW_API_TOKEN")
    if not provided or not hmac.compare_digest(provided, expected):
        raise HTTPException(status_code=401, detail="Invalid or missing API token")
    session_token, ttl_seconds = _issue_admin_session()
    response = JSONResponse({"ok": True, "expires_in": ttl_seconds})
    response.set_cookie(
        key=_ADMIN_SESSION_COOKIE,
        value=session_token,
        max_age=ttl_seconds,
        httponly=True,
        secure=request.url.scheme == "https",
        samesite="strict",
        path="/api",
    )
    return response


@app.middleware("http")
async def xianyu_admin_auth_middleware(request: Request, call_next):
    """保护 API，同时允许浏览器先打开首页再在页面里输入本机 Token。"""
    public_paths = {"/", "/dashboard", "/ops-links"}
    session_exchange = request.method == "POST" and request.url.path == "/api/session"
    if (
        request.method == "OPTIONS"
        or request.url.path in public_paths
        or request.url.path.startswith("/static/")
        or session_exchange
    ):
        return await call_next(request)

    expected = _expected_api_token()
    if not expected:
        env_mode = os.getenv("ENV", "development").strip().lower()
        bind_host = str(
            getattr(request.app.state, "bind_host", None)
            or os.getenv("API_HOST", "127.0.0.1")
        ).strip().lower()
        if env_mode in {"production", "prod"}:
            return JSONResponse({"detail": "生产环境未配置 OPENCLAW_API_TOKEN，拒绝所有请求。"}, status_code=503)
        if bind_host not in ("127.0.0.1", "localhost"):
            return JSONResponse({"detail": "API 认证未配置且绑定到外网地址，拒绝所有请求。"}, status_code=503)
        return await call_next(request)

    provided = request.headers.get("x-api-token", "")
    if provided and hmac.compare_digest(provided, expected):
        return await call_next(request)
    session_token = request.cookies.get(_ADMIN_SESSION_COOKIE, "")
    if _admin_session_is_valid(session_token):
        if not _admin_session_write_is_same_origin(request):
            return JSONResponse({"detail": "管理会话只允许同源写请求"}, status_code=403)
        return await call_next(request)
    return JSONResponse({"detail": "Invalid or missing API token"}, status_code=401)


# 延迟初始化 (由 start_admin_server 注入)
_ctx = None  # XianyuContextManager
_bot = None  # XianyuReplyBot
_live = None  # XianyuLive


def _get_ctx():
    if not _ctx:
        raise HTTPException(503, "闲鱼服务未启动")
    return _ctx


# ============================================================
# Dashboard
# ============================================================


@app.get("/api/dashboard")
def dashboard(date: str = ""):
    try:
        ctx = _get_ctx()
        if not date:
            date = now_et().strftime("%Y-%m-%d")
        stats = ctx.daily_stats(date)

        # 最近 7 天趋势
        trend = []
        for i in range(6, -1, -1):
            d = (now_et() - timedelta(days=i)).strftime("%Y-%m-%d")
            trend.append(ctx.daily_stats(d))

        return {"today": stats, "trend": trend}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[XianyuAdmin] /api/dashboard 出错: {scrub_secrets(str(e))}", exc_info=True)
        raise HTTPException(status_code=500, detail=_safe_error(e)) from e


# ============================================================
# 对话管理
# ============================================================


@app.get("/api/chats")
def list_chats(limit: int = Query(50, le=200)):
    """列出最近活跃的对话"""
    try:
        ctx = _get_ctx()
        with ctx._conn() as c:
            rows = c.execute(
                """
                SELECT chat_id, MAX(ts) as last_ts, COUNT(*) as msg_count,
                       (SELECT content FROM messages m2 WHERE m2.chat_id=m.chat_id ORDER BY id DESC LIMIT 1) as last_msg
                FROM messages m
                GROUP BY chat_id
                ORDER BY last_ts DESC
                LIMIT ?
            """,
                (limit,),
            ).fetchall()
        return [
            {"chat_id": r[0], "last_ts": r[1], "msg_count": r[2], "last_msg": r[3][:100] if r[3] else ""} for r in rows
        ]
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[XianyuAdmin] /api/chats 出错: {scrub_secrets(str(e))}", exc_info=True)
        raise HTTPException(status_code=500, detail=_safe_error(e)) from e


@app.get("/api/chats/{chat_id}")
def get_chat(chat_id: str, limit: int = Query(100, le=500)):
    """获取某个对话的消息历史"""
    try:
        ctx = _get_ctx()
        with ctx._conn() as c:
            rows = c.execute(
                "SELECT role, content, ts FROM messages WHERE chat_id=? ORDER BY id DESC LIMIT ?",
                (chat_id, limit),
            ).fetchall()
        rows.reverse()
        bargain = ctx.get_bargain_count(chat_id)
        return {
            "chat_id": chat_id,
            "bargain_count": bargain,
            "messages": [{"role": r[0], "content": r[1], "ts": r[2]} for r in rows],
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[XianyuAdmin] /api/chats/{chat_id} 出错: {scrub_secrets(str(e))}", exc_info=True)
        raise HTTPException(status_code=500, detail=_safe_error(e)) from e


# ============================================================
# 商品管理
# ============================================================


@app.get("/api/items")
def list_items():
    try:
        ctx = _get_ctx()
        with ctx._conn() as c:
            rows = c.execute("SELECT item_id, data, updated FROM items ORDER BY updated DESC").fetchall()
        items = []
        for r in rows:
            try:
                data = json.loads(r[1])
            except Exception as e:  # noqa: F841
                data = {}
            items.append(
                {"item_id": r[0], "title": data.get("title", ""), "price": data.get("price", ""), "updated": r[2]}
            )
        return items
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[XianyuAdmin] /api/items 出错: {scrub_secrets(str(e))}", exc_info=True)
        raise HTTPException(status_code=500, detail=_safe_error(e)) from e


# ============================================================
# 订单管理
# ============================================================


@app.get("/api/orders")
def list_orders(date: str = "", limit: int = Query(50, le=200)):
    try:
        ctx = _get_ctx()
        with ctx._conn() as c:
            if date:
                rows = c.execute(
                    "SELECT id, chat_id, user_id, item_id, status, ts, notified FROM orders WHERE ts LIKE ? ORDER BY id DESC LIMIT ?",
                    (f"{date}%", limit),
                ).fetchall()
            else:
                rows = c.execute(
                    "SELECT id, chat_id, user_id, item_id, status, ts, notified FROM orders ORDER BY id DESC LIMIT ?",
                    (limit,),
                ).fetchall()
        return [
            {
                "id": r[0],
                "chat_id": r[1],
                "user_id": r[2],
                "item_id": r[3],
                "status": r[4],
                "ts": r[5],
                "notified": bool(r[6]),
            }
            for r in rows
        ]
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[XianyuAdmin] /api/orders 出错: {scrub_secrets(str(e))}", exc_info=True)
        raise HTTPException(status_code=500, detail=_safe_error(e)) from e


@app.get("/api/cc-shipments")
def list_cc_shipments(
    status: str = "",
    limit: int = Query(50, le=200),
    include_message: bool = False,
):
    """列出 CC中转自动发货状态，失败记录可用于人工补发。"""
    try:
        ctx = _get_ctx()
        return ctx.list_cc_shipments(status=status, limit=limit, include_message=include_message)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[XianyuAdmin] /api/cc-shipments 出错: {scrub_secrets(str(e))}", exc_info=True)
        raise HTTPException(status_code=500, detail=_safe_error(e)) from e


def _scrub_paid_order_probe_candidate(candidate: dict) -> dict:
    """脱敏真实待发货订单候选；不返回原始订单号、买家号或卡密。"""
    order_id = str(candidate.get("order_id") or "")
    buyer_id = str(candidate.get("buyer_id") or "")
    item_id = str(candidate.get("item_id") or candidate.get("source_item_id") or "")
    return {
        "order": _safe_order_marker(order_id),
        "buyer": {
            "present": bool(buyer_id.strip()),
            "hash": hashlib.sha256(buyer_id.encode("utf-8")).hexdigest()[:12] if buyer_id else "",
        },
        "item": {
            "present": bool(item_id.strip()),
            "hash": hashlib.sha256(item_id.encode("utf-8")).hexdigest()[:12] if item_id else "",
            "title": str(candidate.get("title") or "")[:80],
        },
        "amount": candidate.get("amount"),
        "statusText": str(candidate.get("status_text") or "")[:80],
        "classifiedStatus": str(candidate.get("classified_status") or "")[:40],
        "canAutoShipItem": bool(candidate.get("can_auto_ship_item")),
        "localShipmentStatus": str(candidate.get("local_shipment_status") or "none")[:80],
        "localShipmentPresent": bool(candidate.get("local_shipment_id")),
    }


@app.get("/api/cc-paid-order-probe")
async def cc_paid_order_probe(batch_size: int = Query(5, ge=1, le=20)):
    """只读扫描闲鱼真实待发货订单；不发卡、不分配库存、不点击发货。"""
    try:
        operator_state = get_operator_state()
        owner_call = getattr(_live, "call_on_owner", None)
        if not callable(owner_call):
            return {
                "ok": False,
                "readOnly": True,
                "autoShipPaused": bool(operator_state.get("auto_ship_paused")),
                "reason": "xianyu_live_unavailable",
                "candidates": [],
                "nextAction": "闲鱼实时服务未接入本机操作台，请先确认 ai.openclaw.xianyu 正在运行。",
            }
        result = await owner_call(
            "scan_cc_paid_orders_readonly",
            batch_size=int(batch_size),
            timeout=30.0,
        )
        candidates = [
            _scrub_paid_order_probe_candidate(item)
            for item in (result.get("candidates") or [])
            if isinstance(item, dict)
        ]
        raw_error = str(result.get("error") or "")[:200]
        next_action = result.get("next_action") or "只读扫描完成；确认候选无误后再单次放行发货。"
        if not result.get("ok") and result.get("reason") == "xianyu_order_api_failed":
            next_action = (
                "后台卖家订单接口暂时读不到订单。请打开卖家 Chromium 的真实已付款聊天/订单页，"
                "使用浏览器当前页兜底；兜底会先做可见付款校验，不会发卡、不会点击发货。"
            )
        return _scrub_status_report(
            {
                "ok": bool(result.get("ok")),
                "readOnly": True,
                "autoShipPaused": bool(operator_state.get("auto_ship_paused")),
                "reason": result.get("reason") or "",
                "error": raw_error,
                "processed": int(result.get("processed") or 0),
                "skipped": int(result.get("skipped") or 0),
                "totalCount": int(result.get("total_count") or 0),
                "candidates": candidates,
                "nextAction": next_action,
            }
        )
    except HTTPException:
        raise
    except OwnerLoopNotReady as e:
        raise HTTPException(503, "闲鱼实时连接尚未就绪，请稍后再试") from e
    except OwnerLoopTimeout as e:
        raise HTTPException(504, "只读扫单仍在后台核对，请稍后查看状态；本次没有执行发货") from e
    except Exception as e:
        logger.error(f"[XianyuAdmin] /api/cc-paid-order-probe 出错: {scrub_secrets(str(e))}", exc_info=True)
        raise HTTPException(status_code=500, detail=_safe_error(e)) from e


def _next_cc_browser_delivery(ctx, one_shot: bool = False) -> dict:
    """给浏览器发货助手取下一条可发送记录；只复用已分配话术，不新分配卡密。"""
    operator_state = get_operator_state()
    paused = bool(operator_state.get("auto_ship_paused"))
    one_shot_gate = peek_one_shot_delivery()
    if paused and not (one_shot and one_shot_gate.get("active")):
        return {
            "ok": True,
            "hasPending": False,
            "shipment": None,
            "reason": "operator_paused",
            "oneShotDelivery": one_shot_gate,
            "nextAction": "自动发货已暂停；系统不会向浏览器返回卡密话术。",
        }
    claimer = getattr(ctx, "claim_next_cc_browser_delivery", None)
    if callable(claimer):
        row = claimer()
        if row:
            consumed = None
            if paused and one_shot:
                consumed = consume_one_shot_delivery("浏览器已领取 1 条待发送卡密话术")
                if not consumed.get("allowed"):
                    marker = getattr(ctx, "mark_cc_shipment_send_failed", None)
                    if callable(marker):
                        marker(int(row.get("id") or 0), "单次放行已失效，本次不返回卡密话术")
                    return {
                        "ok": True,
                        "hasPending": False,
                        "shipment": None,
                        "reason": consumed.get("reason") or "one_shot_delivery_not_active",
                        "oneShotDelivery": consumed.get("one_shot_delivery") or {},
                        "nextAction": "单次放行已过期或已被使用；如仍需发卡，请重新点击“只放行一次”。",
                    }
            message = str(row.get("delivery_message") or "").strip()
            return {
                "ok": True,
                "hasPending": True,
                "oneShotDelivery": (consumed or {}).get("one_shot_delivery") or one_shot_gate,
                "shipment": {
                    "id": row.get("id"),
                    "orderId": row.get("order_id"),
                    "itemId": row.get("item_id"),
                    "buyerId": row.get("buyer_id"),
                    "chatId": row.get("chat_id"),
                    "status": row.get("status"),
                    "deliveryPreview": row.get("delivery_preview"),
                    "deliveryMessage": message,
                },
                "nextAction": "已锁定一条待发送话术；浏览器发送成功后会标记已发，失败会退回失败队列。",
            }
        return {
            "ok": True,
            "hasPending": False,
            "shipment": None,
            "oneShotDelivery": one_shot_gate,
            "nextAction": "暂无待浏览器发货记录；继续等待自动检测已付款订单。",
        }
    if paused and one_shot:
        return {
            "ok": True,
            "hasPending": False,
            "shipment": None,
            "oneShotDelivery": one_shot_gate,
            "nextAction": "单次放行已就绪，但暂无已生成的话术；浏览器会在当前已付款页先生成，再发送一次。",
        }
    for status in ("manual_delivery_ready", "message_send_failed"):
        rows = ctx.list_cc_shipments(status=status, limit=20, include_message=True)
        for row in rows:
            message = str(row.get("delivery_message") or "").strip()
            if not message:
                continue
            consumed = None
            if paused and one_shot:
                consumed = consume_one_shot_delivery("浏览器已领取 1 条待发送卡密话术")
                if not consumed.get("allowed"):
                    return {
                        "ok": True,
                        "hasPending": False,
                        "shipment": None,
                        "reason": consumed.get("reason") or "one_shot_delivery_not_active",
                        "oneShotDelivery": consumed.get("one_shot_delivery") or {},
                        "nextAction": "单次放行已过期或已被使用；如仍需发卡，请重新点击“只放行一次”。",
                    }
            return {
                "ok": True,
                "hasPending": True,
                "oneShotDelivery": (consumed or {}).get("one_shot_delivery") or one_shot_gate,
                "shipment": {
                    "id": row.get("id"),
                    "orderId": row.get("order_id"),
                    "itemId": row.get("item_id"),
                    "buyerId": row.get("buyer_id"),
                    "chatId": row.get("chat_id"),
                    "status": row.get("status"),
                    "deliveryPreview": row.get("delivery_preview"),
                    "deliveryMessage": message,
                },
                "nextAction": "打开对应闲鱼聊天页，插件识别到已付款/待发货信号后会填入并发送。",
            }
    return {
        "ok": True,
        "hasPending": False,
        "shipment": None,
        "oneShotDelivery": one_shot_gate,
        "nextAction": "暂无待浏览器发货记录；继续等待自动检测已付款订单。",
    }


def _next_cc_xianyu_confirm(ctx) -> dict:
    """给浏览器助手取下一条需点击闲鱼“发货/确认发货”的记录。"""
    rows = ctx.list_cc_shipments(status="message_sent", limit=50, include_message=False)
    for row in rows:
        confirm_status = str(row.get("xianyu_confirm_status") or "").strip()
        if confirm_status in {"confirmed", "skipped"}:
            continue
        order_id = str(row.get("order_id") or "").strip()
        if not re.fullmatch(r"\d{10,}", order_id):
            marker = getattr(ctx, "mark_cc_shipment_xianyu_confirm", None)
            if callable(marker):
                marker(order_id, "skipped", "不是闲鱼数字订单号，未进入浏览器确认发货队列")
            continue
        return {
            "ok": True,
            "hasPending": True,
            "shipment": {
                "id": row.get("id"),
                "orderId": row.get("order_id"),
                "itemId": row.get("item_id"),
                "buyerId": row.get("buyer_id"),
                "chatId": row.get("chat_id"),
                "status": row.get("status"),
                "xianyuConfirmStatus": confirm_status,
                "deliveryPreview": row.get("delivery_preview"),
            },
            "nextAction": "打开对应闲鱼待发货/聊天页面，浏览器助手会先识别已付款信号，再点击闲鱼发货按钮。",
        }
    return {
        "ok": True,
        "hasPending": False,
        "shipment": None,
        "nextAction": "暂无需要点击闲鱼发货按钮的订单。",
    }


def _next_cc_xianyu_current_page_confirm(ctx, item_id: str = "") -> dict:
    """给“当前页面已付款”补救路径取一条可确认发货记录。

    这条路径只服务生产内测补救：旧 `xy_manual_*` / `xy_browser_*` 记录已经发出卡密，
    但没有真实数字订单号，不能进入正式确认发货队列。浏览器侧仍必须先看到当前页面
    的“已付款/待发货”信号才会点击，后端这里只返回候选，不降低正式售卖严格门。
    """
    normalized_item_id = _normalize_cc_item_mapping_item_id(item_id)
    rows = ctx.list_cc_shipments(status="message_sent", limit=50, include_message=False)
    candidates: list[dict] = []
    for row in rows:
        confirm_status = str(row.get("xianyu_confirm_status") or "").strip()
        if confirm_status == "confirmed":
            continue
        order_id = str(row.get("order_id") or "").strip()
        if not order_id.startswith(("xy_manual_", "xy_browser_")):
            continue
        row_item_id = _normalize_cc_item_mapping_item_id(str(row.get("item_id") or ""))
        if normalized_item_id and row_item_id and normalized_item_id != row_item_id:
            continue
        candidates.append(row)

    if not candidates:
        return {
            "ok": True,
            "hasPending": False,
            "shipment": None,
            "queueType": "current_page_remediation",
            "nextAction": "暂无已发卡密但待页面确认发货的内测补救记录。",
        }
    if not normalized_item_id and len(candidates) > 1:
        return {
            "ok": True,
            "hasPending": False,
            "shipment": None,
            "queueType": "current_page_remediation",
            "reason": "multiple_manual_candidates",
            "nextAction": "存在多条内测补救记录；请打开对应商品/买家页面后再让桥接器确认发货。",
        }

    row = candidates[0]
    return {
        "ok": True,
        "hasPending": True,
        "queueType": "current_page_remediation",
        "shipment": {
            "id": row.get("id"),
            "orderId": row.get("order_id"),
            "itemId": row.get("item_id"),
            "buyerId": row.get("buyer_id"),
            "chatId": row.get("chat_id"),
            "status": row.get("status"),
            "xianyuConfirmStatus": row.get("xianyu_confirm_status"),
            "deliveryPreview": row.get("delivery_preview"),
        },
        "nextAction": "内测补救：只在当前闲鱼页面可见已付款/待发货信号时点击发货，不计入正式售卖严格门。",
    }


def _next_cc_xianyu_relist(ctx, mode: str = "production") -> dict:
    """给浏览器助手取下一条可尝试恢复上架的商品记录。

    生产模式只在卡密已发出且闲鱼确认发货已完成后进入队列；模拟模式允许
    `xy_manual_*`/`xy_browser_*` 已发卡记录进入队列，但仍不解锁正式售卖。
    是否真的点击，仍由浏览器页面上的“已下架/已售罄 + 重新上架按钮”二次确认。
    """
    normalized_mode = (mode or "production").strip().lower()
    simulation_mode = normalized_mode in {"simulation", "replacement", "strict_simulation"}
    rows = ctx.list_cc_shipments(status="message_sent", limit=50, include_message=False)
    for row in rows:
        relist_status = str(row.get("xianyu_relist_status") or "").strip()
        if relist_status in {"relisted", "online_verified", "skipped"}:
            continue
        order_id = str(row.get("order_id") or "").strip()
        confirm_status = str(row.get("xianyu_confirm_status") or "").strip()
        queue_type = "production_relist"
        if confirm_status != "confirmed":
            if not (simulation_mode and order_id.startswith(("xy_manual_", "xy_browser_", "xy_sim_"))):
                continue
            queue_type = "simulation_relist"
        item_id = str(row.get("item_id") or "").strip()
        if not item_id:
            marker = getattr(ctx, "mark_cc_shipment_xianyu_relist", None)
            if callable(marker):
                marker(order_id, "skipped", "缺少闲鱼商品 ID，未进入恢复上架队列")
            continue
        return {
            "ok": True,
            "hasPending": True,
            "queueType": queue_type,
            "shipment": {
                "id": row.get("id"),
                "orderId": order_id,
                "itemId": item_id,
                "buyerId": row.get("buyer_id"),
                "status": row.get("status"),
                "xianyuConfirmStatus": confirm_status,
                "xianyuRelistStatus": relist_status,
                "deliveryPreview": row.get("delivery_preview"),
            },
            "nextAction": (
                "模拟恢复上架：不点击最终发货按钮；打开对应闲鱼商品页，浏览器助手只有看到已下架/已售罄和重新上架按钮才会点击。"
                if queue_type == "simulation_relist"
                else "打开对应闲鱼商品页；浏览器助手只有看到已下架/已售罄和重新上架按钮才会点击。"
            ),
        }
    return {
        "ok": True,
        "hasPending": False,
        "shipment": None,
        "nextAction": "暂无需要恢复上架的商品。",
    }


@app.get("/api/cc-browser-delivery/next")
def next_cc_browser_delivery(one_shot: bool = False):
    """Chrome 发货助手读取下一条待发货话术；受本机 Token 保护。"""
    try:
        ctx = _get_ctx()
        return _next_cc_browser_delivery(ctx, one_shot=one_shot)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[XianyuAdmin] /api/cc-browser-delivery/next 出错: {scrub_secrets(str(e))}", exc_info=True)
        raise HTTPException(status_code=500, detail=_safe_error(e)) from e


@app.get("/api/cc-xianyu-confirm/next")
def next_cc_xianyu_confirm():
    """Chrome 助手读取下一条需在闲鱼页面点击确认发货的记录。"""
    try:
        ctx = _get_ctx()
        return _next_cc_xianyu_confirm(ctx)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[XianyuAdmin] /api/cc-xianyu-confirm/next 出错: {scrub_secrets(str(e))}", exc_info=True)
        raise HTTPException(status_code=500, detail=_safe_error(e)) from e


@app.get("/api/cc-xianyu-confirm/current-page-candidate")
def next_cc_xianyu_current_page_confirm(item_id: str = ""):
    """Chrome/桥接器读取当前已付款页面可补救确认发货的内测记录。"""
    try:
        ctx = _get_ctx()
        return _next_cc_xianyu_current_page_confirm(ctx, item_id=item_id)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"[XianyuAdmin] /api/cc-xianyu-confirm/current-page-candidate 出错: {scrub_secrets(str(e))}",
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail=_safe_error(e)) from e


@app.get("/api/cc-xianyu-relist/next")
def next_cc_xianyu_relist(mode: str = "production"):
    """Chrome 助手读取下一条可尝试恢复上架的记录。"""
    try:
        ctx = _get_ctx()
        return _next_cc_xianyu_relist(ctx, mode=mode)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[XianyuAdmin] /api/cc-xianyu-relist/next 出错: {scrub_secrets(str(e))}", exc_info=True)
        raise HTTPException(status_code=500, detail=_safe_error(e)) from e


class ShipmentResolveRequest(BaseModel):
    note: str = ""


class ShipmentConfirmFailedRequest(BaseModel):
    error: str = ""


class ShipmentSendFailedRequest(BaseModel):
    error: str = ""


class ShipmentRelistFailedRequest(BaseModel):
    error: str = ""


class ShipmentRelistMarkRequest(BaseModel):
    status: str = "relisted"


class ShipmentBrowserSendRequest(BaseModel):
    buyer_id: str = ""
    item_id: str = ""
    order_id: str = ""
    chat_id: str = ""


class CCItemMappingRequest(BaseModel):
    item_id: str
    plan_id: str
    title: str = ""
    enabled: bool = True


class CCOperatorModeRequest(BaseModel):
    auto_ship_paused: bool
    reason: str = ""


class CCOneShotDeliveryRequest(BaseModel):
    reason: str = ""
    ttl_seconds: int = 180


class CCOneShotBridgeRunRequest(BaseModel):
    reason: str = ""


class CCSellerBridgeOpenPageRequest(BaseModel):
    destination: str = "im"
    reason: str = ""


class CCManualPaidOrderRequest(BaseModel):
    item_id: str = ""
    plan_id: str = ""
    product_title: str = ""
    buyer_hint: str = ""
    proof_note: str = ""
    order_id: str = ""
    one_shot: bool = False


def _manual_paid_order_id(req: CCManualPaidOrderRequest, item_id: str) -> str:
    """生成稳定的本机手动实单订单号，避免重复点击重复分配卡密。"""
    explicit = str(req.order_id or "").strip()
    if explicit:
        if explicit.startswith("xy_"):
            return explicit
        trusted_prefixes = ("xianyu-real:", "real:")
        for trusted_prefix in trusted_prefixes:
            if explicit.startswith(trusted_prefix):
                raw_order_id = explicit[len(trusted_prefix) :].strip()
                if re.fullmatch(r"[A-Za-z0-9_-]{6,80}", raw_order_id):
                    return f"xy_oid_{hashlib.sha256(raw_order_id.encode()).hexdigest()[:16]}"
        prefix = "xy_browser_" if explicit.startswith("browser:") else "xy_manual_"
        return f"{prefix}{hashlib.sha256(explicit.encode()).hexdigest()[:16]}"
    basis = "|".join(
        [
            item_id,
            str(req.buyer_hint or "").strip(),
            str(req.product_title or "").strip(),
            str(req.proof_note or "").strip(),
            time.strftime("%Y%m%d"),
        ]
    )
    digest = hashlib.sha256(basis.encode("utf-8")).hexdigest()[:16]
    return f"xy_manual_{digest}"


def _resolve_manual_paid_order_plan(ctx, item_id: str, requested_plan: str) -> str:
    """手动兜底发货时解析套餐；优先显式 planId，其次商品映射，最后默认套餐。"""
    explicit = str(requested_plan or "").strip()
    if explicit:
        return explicit
    if item_id and hasattr(ctx, "get_cc_item_mapping"):
        with contextlib.suppress(Exception):
            mapping = ctx.get_cc_item_mapping(item_id)
            if mapping and mapping.get("plan_id"):
                return str(mapping["plan_id"]).strip()
    return os.getenv("CC_XIANYU_DEFAULT_PLAN_ID", "").strip()


async def _call_cc_manual_paid_order_webhook(payload: dict) -> dict:
    """调用 CC中转低权限发货接口；只在老板人工确认已付款后使用。"""
    endpoint = os.getenv("CC_XIANYU_WEBHOOK_URL", "").strip()
    token = os.getenv("CC_XIANYU_WEBHOOK_TOKEN", "").strip()
    if not endpoint or not token:
        raise HTTPException(503, "CC中转发货接口未配置")
    try:
        import httpx

        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(endpoint, json=payload, headers={"x-cc-xianyu-token": token})
    except Exception as e:
        raise HTTPException(502, f"发货接口暂时不可用: {_safe_error(e)}") from e
    if resp.status_code != 200:
        raise HTTPException(502, f"发货接口返回 HTTP {resp.status_code}")
    data = resp.json()
    message = str(data.get("deliveryMessage") or data.get("message") or "")
    if not message:
        raise HTTPException(502, "发货接口未返回发货话术")
    return data


def _cc_xianyu_remap_endpoint() -> tuple[str, str]:
    """解析 CC中转远端订单号接管接口，复用低权限闲鱼 webhook token。"""
    endpoint = (
        os.getenv("CC_XIANYU_REMAP_WEBHOOK_URL", "").strip()
        or os.getenv("JIYU_XIANYU_REMAP_WEBHOOK_URL", "").strip()
    )
    source_endpoint = (
        os.getenv("CC_XIANYU_WEBHOOK_URL", "").strip()
    )
    token = os.getenv("CC_XIANYU_WEBHOOK_TOKEN", "").strip()
    if not endpoint and source_endpoint:
        endpoint = re.sub(r"/paid-order/?$", "/remap-order", source_endpoint.rstrip("/"))
    return endpoint, token


async def _call_cc_xianyu_remap_order(old_order_id: str, new_order_id: str) -> dict:
    """把远端 JIYU AI 已发卡记录接管为真实闲鱼订单号，不分配新卡。"""
    endpoint, token = _cc_xianyu_remap_endpoint()
    if not endpoint or not token:
        raise HTTPException(503, "CC中转订单接管接口未配置")
    payload = {"oldOrderId": old_order_id, "newOrderId": new_order_id}
    try:
        import httpx

        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(endpoint, json=payload, headers={"x-cc-xianyu-token": token})
    except Exception as e:
        raise HTTPException(502, f"订单接管接口暂时不可用: {_safe_error(e)}") from e
    if resp.status_code != 200:
        raise HTTPException(502, f"订单接管接口返回 HTTP {resp.status_code}")
    data = resp.json()
    if data.get("ok") is not True:
        raise HTTPException(502, "订单接管接口未确认成功")
    return data


def _find_adoptable_browser_shipment(ctx, item_id: str) -> tuple[dict | None, str]:
    """查找同一商品唯一一条已发卡的浏览器临时订单，避免真实订单补抓后重复发卡。"""
    if not hasattr(ctx, "list_cc_shipments"):
        return None, "shipment_list_unavailable"
    normalized_item_id = _normalize_cc_item_mapping_item_id(item_id)
    candidates: list[dict] = []
    for row in ctx.list_cc_shipments(status="message_sent", limit=50, include_message=True):
        order_id = str(row.get("order_id") or "").strip()
        if not order_id.startswith("xy_browser_"):
            continue
        row_item_id = _normalize_cc_item_mapping_item_id(str(row.get("item_id") or ""))
        if normalized_item_id and row_item_id and normalized_item_id != row_item_id:
            continue
        candidates.append(row)
    if len(candidates) == 1:
        return candidates[0], ""
    if len(candidates) > 1:
        return None, "multiple_browser_shipments_for_item"
    return None, "browser_shipment_not_found"


@app.post("/api/cc-manual-paid-order/dispatch")
async def dispatch_manual_paid_order(req: CCManualPaidOrderRequest):
    """闲鱼已付款推送漏掉时，人工确认付款后生成可粘贴的发货话术。"""
    try:
        ctx = _get_ctx()
        item_id = _normalize_cc_item_mapping_item_id(req.item_id)
        if not item_id:
            raise HTTPException(400, "请填写闲鱼商品链接或商品 ID")
        order_id = _manual_paid_order_id(req, item_id)
        operator_state = get_operator_state()
        paused_one_shot = bool(operator_state.get("auto_ship_paused")) and bool(req.one_shot)
        one_shot_consumed: dict | None = None
        existing = None
        if hasattr(ctx, "get_cc_shipment_by_order_id"):
            existing = ctx.get_cc_shipment_by_order_id(order_id, include_message=True)
        if existing and existing.get("delivery_message"):
            existing_status = str(existing.get("status") or "").strip()
            if existing_status not in {"manual_delivery_ready", "message_send_failed"}:
                if paused_one_shot:
                    one_shot_consumed = consume_one_shot_delivery("当前订单已发过卡密，本次单次放行仅做幂等检查")
                return {
                    "ok": True,
                    "idempotent": True,
                    "alreadyHandled": True,
                    "shipmentId": existing.get("id"),
                    "orderId": order_id,
                    "status": existing_status,
                    "oneShotDelivery": (one_shot_consumed or {}).get("one_shot_delivery") or peek_one_shot_delivery(),
                    "deliveryMessage": "",
                    "nextAction": "这笔已付款页面已经发过卡密，本次巡检不会再次填入或发送。",
                }
            if paused_one_shot:
                one_shot_consumed = consume_one_shot_delivery("浏览器将发送已存在的待发卡密话术")
                if not one_shot_consumed.get("allowed"):
                    raise HTTPException(409, "单次放行已过期或已被使用，请重新点击“只放行一次”")
            return {
                "ok": True,
                "idempotent": True,
                "alreadyHandled": False,
                "shipmentId": existing.get("id"),
                "orderId": order_id,
                "status": existing_status,
                "oneShotDelivery": (one_shot_consumed or {}).get("one_shot_delivery") or peek_one_shot_delivery(),
                "deliveryMessage": existing.get("delivery_message"),
                "nextAction": "浏览器助手会填入并发送；人工兜底时也可以复制到闲鱼聊天。",
            }
        if order_id.startswith("xy_oid_") and hasattr(ctx, "adopt_cc_shipment_real_order"):
            adoptable, adopt_reason = _find_adoptable_browser_shipment(ctx, item_id)
            if adopt_reason == "multiple_browser_shipments_for_item":
                raise HTTPException(
                    409, "同一商品找到多条已发浏览器临时单，为避免错绑真实订单，本次不发新卡。请联系技术支持处理。"
                )
            if adoptable:
                old_order_id = str(adoptable.get("order_id") or "").strip()
                await _call_cc_xianyu_remap_order(old_order_id, order_id)
                adopted = ctx.adopt_cc_shipment_real_order(
                    old_order_id=old_order_id,
                    new_order_id=order_id,
                    buyer_id=str(req.buyer_hint or adoptable.get("buyer_id") or "").strip()[:120],
                    item_id=item_id,
                    chat_id=str(adoptable.get("chat_id") or ""),
                )
                if not adopted:
                    raise HTTPException(409, "真实订单号接管失败，为避免重复发卡，本次不生成新卡。")
                if paused_one_shot:
                    one_shot_consumed = consume_one_shot_delivery("已发浏览器临时单接管为真实订单号，本次不再发送卡密")
                shipment = ctx.get_cc_shipment_by_order_id(order_id, include_message=False) or {}
                return {
                    "ok": True,
                    "idempotent": True,
                    "alreadyHandled": True,
                    "adoptedRealOrder": True,
                    "shipmentId": shipment.get("id") or adoptable.get("id"),
                    "orderId": order_id,
                    "previousOrderId": old_order_id,
                    "status": "message_sent",
                    "oneShotDelivery": (one_shot_consumed or {}).get("one_shot_delivery") or peek_one_shot_delivery(),
                    "deliveryMessage": "",
                    "nextAction": "已把这笔已发卡密的浏览器临时单接管为真实闲鱼订单号；不会再次发送卡密。",
                }
        plan_id = _resolve_manual_paid_order_plan(ctx, item_id, req.plan_id)
        if not plan_id:
            raise HTTPException(400, "请先绑定套餐 planId，或填写 planId")
        product_title = str(req.product_title or "").strip()[:120] or "CC中转 兑换码"
        buyer_hint = str(req.buyer_hint or "").strip()[:120] or "manual-paid-proof"
        payload = {
            "orderId": order_id,
            "status": "等待卖家发货",
            "paid": True,
            "itemId": item_id,
            "productTitle": product_title,
            "buyerHint": buyer_hint,
            "planId": plan_id,
            "note": f"openclaw-xianyu-manual-paid-proof {str(req.proof_note or '').strip()[:120]}".strip(),
        }
        if paused_one_shot:
            one_shot_consumed = consume_one_shot_delivery("浏览器将为当前已付款页生成并发送 1 条卡密话术")
            if not one_shot_consumed.get("allowed"):
                raise HTTPException(409, "单次放行已过期或已被使用，请重新点击“只放行一次”")
        data = await _call_cc_manual_paid_order_webhook(payload)
        message = str(data.get("deliveryMessage") or data.get("message") or "")
        ctx.record_cc_shipment(
            order_id=order_id,
            buyer_id=buyer_hint,
            item_id=item_id,
            chat_id="",
            status="manual_delivery_ready",
            delivery_message=message,
            error="等待老板复制到闲鱼聊天并确认已发送",
        )
        shipment = ctx.get_cc_shipment_by_order_id(order_id, include_message=False) or {}
        return {
            "ok": True,
            "idempotent": False,
            "shipmentId": shipment.get("id"),
            "orderId": order_id,
            "status": "manual_delivery_ready",
            "planId": plan_id,
            "oneShotDelivery": (one_shot_consumed or {}).get("one_shot_delivery") or peek_one_shot_delivery(),
            "deliveryMessage": message,
            "nextAction": "浏览器助手会填入并发送；人工兜底时也可以复制到闲鱼聊天。",
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[XianyuAdmin] 手动已付款发货出错: {scrub_secrets(str(e))}", exc_info=True)
        raise HTTPException(status_code=500, detail=_safe_error(e)) from e


@app.post("/api/cc-shipments/{shipment_id}/resolve")
def resolve_cc_shipment(shipment_id: int, req: ShipmentResolveRequest):
    """人工确认某条失败发货已经补发或无需处理。"""
    try:
        ctx = _get_ctx()
        ok = ctx.resolve_cc_shipment(shipment_id, req.note)
        if not ok:
            raise HTTPException(404, "发货记录不存在")
        return {"ok": True, "id": shipment_id}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"[XianyuAdmin] /api/cc-shipments/{shipment_id}/resolve 出错: {scrub_secrets(str(e))}", exc_info=True
        )
        raise HTTPException(status_code=500, detail=_safe_error(e)) from e


@app.post("/api/cc-shipments/{shipment_id}/resend")
async def resend_cc_shipment(shipment_id: int):
    """通过当前闲鱼 WebSocket 补发一条已分配但发送失败的发货话术。"""
    try:
        owner_call = getattr(_live, "call_on_owner", None)
        if not callable(owner_call):
            raise HTTPException(503, "闲鱼实时助手未连接，暂时不能补发")
        return await owner_call(
            "resend_cc_shipment",
            shipment_id=int(shipment_id),
            timeout=45.0,
        )
    except HTTPException:
        raise
    except OwnerLoopNotReady as e:
        raise HTTPException(503, "闲鱼实时连接尚未就绪，请稍后再试") from e
    except OwnerLoopTimeout as e:
        raise HTTPException(504, "补发仍在后台核对结果，请勿重试；请先查看闲鱼聊天和本机履约状态") from e
    except LookupError as e:
        raise HTTPException(404, str(e)) from e
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    except RuntimeError as e:
        raise HTTPException(409, str(e)) from e
    except Exception as e:
        logger.error(
            f"[XianyuAdmin] /api/cc-shipments/{shipment_id}/resend 出错: {scrub_secrets(str(e))}", exc_info=True
        )
        raise HTTPException(status_code=500, detail=_safe_error(e)) from e


@app.post("/api/cc-shipments/{shipment_id}/browser-send")
async def browser_send_cc_shipment(shipment_id: int, req: ShipmentBrowserSendRequest):
    """浏览器助手识别到买家后，把已分配待发送的话术直接发给该买家。"""
    try:
        owner_call = getattr(_live, "call_on_owner", None)
        if not callable(owner_call):
            raise HTTPException(503, "闲鱼实时助手未连接，暂时不能发送")
        buyer_id = str(req.buyer_id or "").strip()
        if not buyer_id:
            raise HTTPException(400, "缺少买家信息，不能自动发送")
        return await owner_call(
            "send_manual_ready_cc_shipment",
            shipment_id=int(shipment_id),
            buyer_id=buyer_id,
            item_id=str(req.item_id or "").strip(),
            order_id=str(req.order_id or "").strip(),
            chat_id=str(req.chat_id or "").strip(),
            timeout=45.0,
        )
    except HTTPException:
        raise
    except OwnerLoopNotReady as e:
        raise HTTPException(503, "闲鱼实时连接尚未就绪，请稍后再试") from e
    except OwnerLoopTimeout as e:
        raise HTTPException(504, "发送仍在后台核对结果，请勿重试；请先查看闲鱼聊天和本机履约状态") from e
    except LookupError as e:
        raise HTTPException(404, str(e)) from e
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    except RuntimeError as e:
        raise HTTPException(409, str(e)) from e
    except Exception as e:
        logger.error(
            f"[XianyuAdmin] /api/cc-shipments/{shipment_id}/browser-send 出错: {scrub_secrets(str(e))}", exc_info=True
        )
        raise HTTPException(status_code=500, detail=_safe_error(e)) from e


@app.post("/api/cc-shipments/{shipment_id}/mark-sent")
def mark_cc_shipment_sent(shipment_id: int):
    """老板已把发货话术粘贴到闲鱼后，将本机履约记录标记为已发货。"""
    try:
        ctx = _get_ctx()
        if not hasattr(ctx, "get_cc_shipment"):
            raise HTTPException(503, "本机发货记录读取能力不可用")
        shipment = ctx.get_cc_shipment(int(shipment_id), include_message=True)
        if not shipment:
            raise HTTPException(404, "发货记录不存在")
        message = str(shipment.get("delivery_message") or "")
        if not message:
            raise HTTPException(400, "该记录没有可确认的话术")
        order_id = str(shipment.get("order_id") or "")
        ctx.record_cc_shipment(
            order_id=order_id,
            buyer_id=str(shipment.get("buyer_id") or ""),
            item_id=str(shipment.get("item_id") or ""),
            chat_id=str(shipment.get("chat_id") or ""),
            status="message_sent",
            delivery_message=message,
            error="",
        )
        canary_result = consume_auto_resume_canary_after_sent(order_id)
        return {
            "ok": True,
            "id": int(shipment_id),
            "order_id": shipment.get("order_id"),
            "status": "message_sent",
            "auto_resume_canary": canary_result,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"[XianyuAdmin] /api/cc-shipments/{shipment_id}/mark-sent 出错: {scrub_secrets(str(e))}", exc_info=True
        )
        raise HTTPException(status_code=500, detail=_safe_error(e)) from e


@app.post("/api/cc-shipments/{shipment_id}/mark-send-failed")
def mark_cc_shipment_send_failed(shipment_id: int, req: ShipmentSendFailedRequest):
    """浏览器助手未能发送卡密话术时，退回失败队列，避免领取状态永久卡住。"""
    try:
        ctx = _get_ctx()
        if not hasattr(ctx, "get_cc_shipment"):
            raise HTTPException(503, "本机发货记录读取能力不可用")
        shipment = ctx.get_cc_shipment(int(shipment_id), include_message=False)
        if not shipment:
            raise HTTPException(404, "发货记录不存在")
        if str(shipment.get("status") or "") == "message_sent":
            return {
                "ok": True,
                "id": int(shipment_id),
                "order_id": shipment.get("order_id"),
                "status": "message_sent",
                "alreadySent": True,
            }
        marker = getattr(ctx, "mark_cc_shipment_send_failed", None)
        if not callable(marker):
            raise HTTPException(503, "本机发货失败回写能力不可用")
        error = str(req.error or "浏览器助手未能发送发货话术").strip()[:500]
        ok = marker(int(shipment_id), error)
        if not ok:
            raise HTTPException(409, "该记录当前状态不能退回失败队列")
        return {
            "ok": True,
            "id": int(shipment_id),
            "order_id": shipment.get("order_id"),
            "status": "message_send_failed",
            "error": error,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"[XianyuAdmin] /api/cc-shipments/{shipment_id}/mark-send-failed 出错: {scrub_secrets(str(e))}",
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail=_safe_error(e)) from e


@app.post("/api/cc-shipments/{shipment_id}/mark-xianyu-confirmed")
def mark_cc_shipment_xianyu_confirmed(shipment_id: int):
    """浏览器助手已在闲鱼页面完成确认发货后，回写本机履约状态。"""
    try:
        ctx = _get_ctx()
        shipment = ctx.get_cc_shipment(int(shipment_id), include_message=False)
        if not shipment:
            raise HTTPException(404, "发货记录不存在")
        ok = ctx.mark_cc_shipment_xianyu_confirm(str(shipment.get("order_id") or ""), "confirmed", "")
        if not ok:
            raise HTTPException(404, "发货记录不存在")
        return {
            "ok": True,
            "id": int(shipment_id),
            "order_id": shipment.get("order_id"),
            "status": "confirmed",
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"[XianyuAdmin] /api/cc-shipments/{shipment_id}/mark-xianyu-confirmed 出错: {scrub_secrets(str(e))}",
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail=_safe_error(e)) from e


@app.post("/api/cc-shipments/{shipment_id}/mark-xianyu-confirm-failed")
def mark_cc_shipment_xianyu_confirm_failed(shipment_id: int, req: ShipmentConfirmFailedRequest):
    """浏览器助手未能点击闲鱼确认发货时，记录失败原因供人工处理。"""
    try:
        ctx = _get_ctx()
        shipment = ctx.get_cc_shipment(int(shipment_id), include_message=False)
        if not shipment:
            raise HTTPException(404, "发货记录不存在")
        error = str(req.error or "浏览器助手未能确认发货").strip()[:500]
        ok = ctx.mark_cc_shipment_xianyu_confirm(str(shipment.get("order_id") or ""), "failed", error)
        if not ok:
            raise HTTPException(404, "发货记录不存在")
        return {
            "ok": True,
            "id": int(shipment_id),
            "order_id": shipment.get("order_id"),
            "status": "failed",
            "error": error,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"[XianyuAdmin] /api/cc-shipments/{shipment_id}/mark-xianyu-confirm-failed 出错: {scrub_secrets(str(e))}",
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail=_safe_error(e)) from e


def _cc_backend_confirm_enabled() -> bool:
    """确认是否允许后端 H5 接口改闲鱼订单状态；默认关闭。"""
    return os.getenv("CC_XIANYU_AUTO_CONFIRM_SHIPMENT_ENABLED", "0").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _xianyu_cookie_for_backend_confirm() -> str:
    """优先复用运行中闲鱼 Live 的 Cookie，没有再读环境变量。"""
    live_cookie = str(getattr(_live, "cookies_str", "") or "").strip()
    if live_cookie:
        return live_cookie
    return os.getenv("XIANYU_COOKIES", "").strip()


@app.post("/api/cc-shipments/{shipment_id}/confirm-xianyu-backend")
async def confirm_cc_shipment_xianyu_backend(shipment_id: int):
    """用闲鱼 H5 虚拟发货接口确认发货；默认关闭，只允许真实数字订单。"""
    try:
        ctx = _get_ctx()
        shipment = ctx.get_cc_shipment(int(shipment_id), include_message=False)
        if not shipment:
            raise HTTPException(404, "发货记录不存在")
        order_id = str(shipment.get("order_id") or "").strip()
        if not _cc_backend_confirm_enabled():
            return {
                "ok": False,
                "skipped": True,
                "reason": "disabled",
                "nextAction": "后端确认发货默认关闭；如需实验真实订单 H5 虚拟发货，先显式开启 CC_XIANYU_AUTO_CONFIRM_SHIPMENT_ENABLED=1。",
            }
        if str(shipment.get("status") or "") != "message_sent":
            ctx.mark_cc_shipment_xianyu_confirm(order_id, "skipped", "卡密尚未确认发给买家，不允许后端确认发货")
            return {"ok": False, "skipped": True, "reason": "message_not_sent"}
        if not re.fullmatch(r"\d{10,}", order_id):
            ctx.mark_cc_shipment_xianyu_confirm(order_id, "skipped", "不是闲鱼数字订单号，未调用后端确认发货")
            return {"ok": False, "skipped": True, "reason": "non_numeric_order_id"}
        cookies_str = _xianyu_cookie_for_backend_confirm()
        if not cookies_str:
            ctx.mark_cc_shipment_xianyu_confirm(order_id, "failed", "缺少闲鱼 Cookie，无法调用后端确认发货")
            return {"ok": False, "status": "failed", "error": "缺少闲鱼 Cookie"}
        async with XianyuApis(cookies_str) as api:
            result = await api.confirm_dummy_shipment(order_id)
        if result.get("cookies_str") and _live is not None:
            owner_call = getattr(_live, "call_on_owner", None)
            if callable(owner_call):
                try:
                    await owner_call(
                        "reload_cookies",
                        cookies_str=str(result["cookies_str"]),
                        timeout=15.0,
                    )
                except Exception as e:
                    logger.warning("[XianyuAdmin] 闲鱼 Cookie 已刷新但实时连接同步失败: %s", scrub_secrets(str(e)))
        if result.get("success"):
            ctx.mark_cc_shipment_xianyu_confirm(order_id, "confirmed", "")
            return {"ok": True, "id": shipment_id, "status": "confirmed", "backend": "mtop_dummy"}
        error = str(result.get("error") or "后端确认发货失败")[:500]
        ctx.mark_cc_shipment_xianyu_confirm(order_id, "failed", error)
        return {"ok": False, "id": shipment_id, "status": "failed", "error": error}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"[XianyuAdmin] /api/cc-shipments/{shipment_id}/confirm-xianyu-backend 出错: {scrub_secrets(str(e))}",
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail=_safe_error(e)) from e


@app.post("/api/cc-shipments/{shipment_id}/mark-relisted")
def mark_cc_shipment_relisted(shipment_id: int, req: ShipmentRelistMarkRequest | None = None):
    """浏览器助手确认闲鱼商品已恢复上架后，回写本机状态。"""
    try:
        ctx = _get_ctx()
        shipment = ctx.get_cc_shipment(int(shipment_id), include_message=False)
        if not shipment:
            raise HTTPException(404, "发货记录不存在")
        requested_status = str((req.status if req else "") or "relisted").strip()[:80]
        if requested_status not in {"relisted", "online_verified"}:
            raise HTTPException(400, "恢复上架状态只能是 relisted 或 online_verified")
        ok = ctx.mark_cc_shipment_xianyu_relist(str(shipment.get("order_id") or ""), requested_status, "")
        if not ok:
            raise HTTPException(404, "发货记录不存在")
        return {
            "ok": True,
            "id": int(shipment_id),
            "order_id": shipment.get("order_id"),
            "status": requested_status,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"[XianyuAdmin] /api/cc-shipments/{shipment_id}/mark-relisted 出错: {scrub_secrets(str(e))}",
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail=_safe_error(e)) from e


@app.post("/api/cc-shipments/{shipment_id}/mark-relist-failed")
def mark_cc_shipment_relist_failed(shipment_id: int, req: ShipmentRelistFailedRequest):
    """浏览器助手未能恢复上架时，记录失败原因供人工处理。"""
    try:
        ctx = _get_ctx()
        shipment = ctx.get_cc_shipment(int(shipment_id), include_message=False)
        if not shipment:
            raise HTTPException(404, "发货记录不存在")
        error = str(req.error or "浏览器助手未能恢复上架").strip()[:500]
        ok = ctx.mark_cc_shipment_xianyu_relist(str(shipment.get("order_id") or ""), "failed", error)
        if not ok:
            raise HTTPException(404, "发货记录不存在")
        return {
            "ok": True,
            "id": int(shipment_id),
            "order_id": shipment.get("order_id"),
            "status": "failed",
            "error": error,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"[XianyuAdmin] /api/cc-shipments/{shipment_id}/mark-relist-failed 出错: {scrub_secrets(str(e))}",
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail=_safe_error(e)) from e


@app.get("/api/cc-item-mappings")
def list_cc_item_mappings(include_disabled: bool = True):
    """列出闲鱼商品到 CC中转套餐的映射。"""
    try:
        ctx = _get_ctx()
        return ctx.list_cc_item_mappings(include_disabled=include_disabled)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[XianyuAdmin] /api/cc-item-mappings 出错: {scrub_secrets(str(e))}", exc_info=True)
        raise HTTPException(status_code=500, detail=_safe_error(e)) from e


@app.post("/api/cc-item-mappings")
def upsert_cc_item_mapping(req: CCItemMappingRequest):
    """新增或更新闲鱼商品 → CC中转套餐映射。"""
    try:
        ctx = _get_ctx()
        normalized_item_id = _normalize_cc_item_mapping_item_id(req.item_id)
        return ctx.upsert_cc_item_mapping(
            item_id=normalized_item_id,
            plan_id=req.plan_id,
            title=req.title,
            enabled=req.enabled,
        )
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[XianyuAdmin] /api/cc-item-mappings 保存出错: {scrub_secrets(str(e))}", exc_info=True)
        raise HTTPException(status_code=500, detail=_safe_error(e)) from e


@app.delete("/api/cc-item-mappings/{item_id}")
def delete_cc_item_mapping(item_id: str):
    """删除一条闲鱼商品套餐映射。"""
    try:
        ctx = _get_ctx()
        ok = ctx.delete_cc_item_mapping(item_id)
        if not ok:
            raise HTTPException(404, "商品映射不存在")
        return {"ok": True, "item_id": item_id}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[XianyuAdmin] /api/cc-item-mappings/{item_id} 删除出错: {scrub_secrets(str(e))}", exc_info=True)
        raise HTTPException(status_code=500, detail=_safe_error(e)) from e


# ============================================================
# 咨询追踪
# ============================================================


@app.get("/api/consultations")
def list_consultations(date: str = "", limit: int = Query(50, le=200)):
    try:
        ctx = _get_ctx()
        with ctx._conn() as c:
            if date:
                rows = c.execute(
                    "SELECT chat_id, user_id, user_name, item_id, first_msg, first_ts, last_ts, msg_count, converted "
                    "FROM consultations WHERE first_ts LIKE ? ORDER BY last_ts DESC LIMIT ?",
                    (f"{date}%", limit),
                ).fetchall()
            else:
                rows = c.execute(
                    "SELECT chat_id, user_id, user_name, item_id, first_msg, first_ts, last_ts, msg_count, converted "
                    "FROM consultations ORDER BY last_ts DESC LIMIT ?",
                    (limit,),
                ).fetchall()
        return [
            {
                "chat_id": r[0],
                "user_id": r[1],
                "user_name": r[2],
                "item_id": r[3],
                "first_msg": r[4],
                "first_ts": r[5],
                "last_ts": r[6],
                "msg_count": r[7],
                "converted": bool(r[8]),
            }
            for r in rows
        ]
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[XianyuAdmin] /api/consultations 出错: {scrub_secrets(str(e))}", exc_info=True)
        raise HTTPException(status_code=500, detail=_safe_error(e)) from e


# ============================================================
# 系统状态
# ============================================================


@app.get("/api/status")
def system_status():
    try:
        status = {"service": "running", "ws_connected": False, "cookie_ok": False}
        status["cc_auto_ship"] = _cc_auto_ship_status()
        status["cc_auto_plan_routing"] = _cc_auto_plan_routing_summary()
        status["cc_chrome_extension"] = _cc_chrome_extension_summary()
        readiness_auto = _auto_readiness_audit_config()
        status["cc_readiness_audit"] = {
            "last": _last_cc_readiness_audit,
            "auto_enabled": readiness_auto["enabled"],
            "auto_interval_ms": readiness_auto["interval_ms"],
            "auto_scan_seconds": readiness_auto["scan_seconds"],
            "last_background_at": (
                _last_background_readiness_audit_at if _last_background_readiness_audit_at > 0 else None
            ),
        }
        if _ctx and hasattr(_ctx, "cc_shipment_summary"):
            status["cc_shipments"] = _ctx.cc_shipment_summary()
        if _ctx and hasattr(_ctx, "cc_final_sale_gate_summary"):
            status["cc_final_sale_gate"] = _ctx.cc_final_sale_gate_summary()
        status["cc_strict_audit"] = _latest_strict_audit()
        strict_auto = _auto_strict_audit_config()
        status["cc_background_strict_audit"] = {
            "enabled": strict_auto["enabled"],
            "interval_ms": strict_auto["interval_ms"],
            "scan_seconds": strict_auto["scan_seconds"],
            "last_at": _last_background_strict_audit_at if _last_background_strict_audit_at > 0 else None,
            "last": _last_background_strict_audit_result,
        }
        status["cc_ops_notify"] = {
            "config": _ops_notify_config(),
            "last": _last_ops_notify_result,
            "last_at": _last_ops_notify_at if _last_ops_notify_at > 0 else None,
        }
        if _ctx and hasattr(_ctx, "list_cc_item_mappings"):
            mappings = _ctx.list_cc_item_mappings(include_disabled=True)
            status["cc_item_mappings"] = {
                "total": len(mappings),
                "enabled": len([m for m in mappings if m.get("enabled")]),
            }
        live_snapshot = _live_runtime_snapshot()
        status["ws_connected"] = bool(live_snapshot.get("ws_connected"))
        status["cookie_ok"] = bool(live_snapshot.get("cookie_ok"))
        status["last_heartbeat"] = float(live_snapshot.get("last_heartbeat") or 0.0)
        token_ts = float(live_snapshot.get("token_ts") or 0.0)
        status["token_age_s"] = int(now_et().timestamp() - token_ts) if token_ts > 0 else -1
        status["manual_chats"] = max(0, int(live_snapshot.get("manual_chats") or 0))
        return status
    except Exception as e:
        logger.error(f"[XianyuAdmin] /api/status 出错: {scrub_secrets(str(e))}", exc_info=True)
        raise HTTPException(status_code=500, detail=_safe_error(e)) from e


@app.get("/api/cc-sale-readiness")
def cc_sale_readiness():
    """返回 CC中转闲鱼自动化运营水位和仍需人工介入的事项。"""
    try:
        return _cc_sale_readiness_summary()
    except Exception as e:
        logger.error(f"[XianyuAdmin] /api/cc-sale-readiness 出错: {scrub_secrets(str(e))}", exc_info=True)
        raise HTTPException(status_code=500, detail=_safe_error(e)) from e


@app.get("/api/cc-public-sale-lock")
def cc_public_sale_lock(refresh: bool = False):
    """返回上架前安全锁；refresh=True 时只跑只读巡检刷新库存/渠道证据。"""
    try:
        return _cc_public_sale_lock_summary(refresh=refresh)
    except Exception as e:
        logger.error(f"[XianyuAdmin] /api/cc-public-sale-lock 出错: {scrub_secrets(str(e))}", exc_info=True)
        raise HTTPException(status_code=500, detail=_safe_error(e)) from e


@app.get("/api/cc-loop-watch")
def cc_loop_watch():
    """返回真实订单全自动闭环的轻量观察状态，不触发远程写操作。"""
    try:
        return _cc_loop_watch_summary()
    except Exception as e:
        logger.error(f"[XianyuAdmin] /api/cc-loop-watch 出错: {scrub_secrets(str(e))}", exc_info=True)
        raise HTTPException(status_code=500, detail=_safe_error(e)) from e


@app.get("/api/cc-buyer-chain-progress")
def cc_buyer_chain_progress():
    """返回真实订单买家侧兑换/API/调模型进度；只读，不触发审计。"""
    try:
        return _cc_buyer_chain_progress_summary()
    except Exception as e:
        logger.error(f"[XianyuAdmin] /api/cc-buyer-chain-progress 出错: {scrub_secrets(str(e))}", exc_info=True)
        raise HTTPException(status_code=500, detail=_safe_error(e)) from e


@app.get("/api/cc-operator-next-action")
def cc_operator_next_action():
    """返回统一的下一步运营动作建议；只读，不触发审计或发货。"""
    try:
        return _cc_operator_next_action_summary()
    except Exception as e:
        logger.error(f"[XianyuAdmin] /api/cc-operator-next-action 出错: {scrub_secrets(str(e))}", exc_info=True)
        raise HTTPException(status_code=500, detail=_safe_error(e)) from e


@app.get("/api/cc-operator-mode")
def cc_operator_mode():
    """返回本机操作台的暂停/恢复与人工控制状态。"""
    try:
        return _cc_operator_mode_summary()
    except Exception as e:
        logger.error(f"[XianyuAdmin] /api/cc-operator-mode 出错: {scrub_secrets(str(e))}", exc_info=True)
        raise HTTPException(status_code=500, detail=_safe_error(e)) from e


@app.get("/api/cc-operator-mode/resume-preflight")
def cc_operator_resume_preflight():
    """只读检查现在是否可以恢复常驻自动发货；不改变暂停开关。"""
    try:
        return _cc_auto_ship_resume_preflight()
    except Exception as e:
        logger.error(
            f"[XianyuAdmin] /api/cc-operator-mode/resume-preflight 出错: {scrub_secrets(str(e))}", exc_info=True
        )
        raise HTTPException(status_code=500, detail=_safe_error(e)) from e


@app.post("/api/cc-operator-mode")
def update_cc_operator_mode(req: CCOperatorModeRequest):
    """人工暂停或恢复 CC中转自动发货；恢复前必须通过只读安全预检。"""
    try:
        resume_preflight = None
        if not req.auto_ship_paused:
            resume_preflight = _cc_auto_ship_resume_preflight()
            if not resume_preflight.get("ok"):
                raise HTTPException(status_code=409, detail=resume_preflight)
        set_auto_ship_paused(
            req.auto_ship_paused,
            req.reason,
            resume_canary=(not req.auto_ship_paused),
        )
        summary = _cc_operator_mode_summary()
        if resume_preflight is not None:
            summary["resume_preflight"] = resume_preflight
        return summary
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[XianyuAdmin] /api/cc-operator-mode 更新出错: {scrub_secrets(str(e))}", exc_info=True)
        raise HTTPException(status_code=500, detail=_safe_error(e)) from e


@app.post("/api/cc-operator-mode/one-shot-delivery")
def authorize_cc_one_shot_delivery(req: CCOneShotDeliveryRequest):
    """暂停状态下只放行一次浏览器发卡，避免恢复常驻自动发货造成重复消息。"""
    try:
        state = authorize_one_shot_delivery(req.reason, req.ttl_seconds)
        summary = _cc_operator_mode_summary()
        return {
            "ok": True,
            "auto_ship_paused": bool(state.get("auto_ship_paused")),
            "one_shot_delivery": state.get("one_shot_delivery") or {},
            "mode": summary,
            "nextAction": "3 分钟内只允许浏览器助手发送 1 条卡密；发送后会自动失效，常驻自动发货仍保持暂停。",
        }
    except Exception as e:
        logger.error(
            f"[XianyuAdmin] /api/cc-operator-mode/one-shot-delivery 出错: {scrub_secrets(str(e))}",
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail=_safe_error(e)) from e


def _humanize_cc_seller_page_scan(payload: dict) -> dict:
    """把只读扫页结果翻译成老板能照做的下一步，不改变发卡判定。"""
    if not isinstance(payload, dict) or payload.get("mode") != "scan_only":
        return payload
    scans = payload.get("scans") if isinstance(payload.get("scans"), list) else []
    first = scans[0] if scans and isinstance(scans[0], dict) else {}
    xianyu_tabs = int(payload.get("xianyuTabs") or 0)
    if xianyu_tabs != 1:
        payload["nextAction"] = (
            f"现在打开了 {xianyu_tabs} 个闲鱼页。请只保留 1 个真实已付款买家的聊天页或订单详情页，再点只读检查。"
        )
        return payload
    if not first:
        payload["nextAction"] = "没有读取到闲鱼页面内容。请确认卖家 Chromium 已打开闲鱼，并登录卖家号。"
        return payload
    if first.get("strictReadyToSend"):
        payload["nextAction"] = "当前唯一闲鱼页已看到付款信号、输入框和真实订单号，可以回到 18800 点“一键跑当前页”。"
        return payload
    if first.get("readyToSend") and not first.get("orderIdHintPresent"):
        if first.get("orderCardPresent") or first.get("shipActionPresent"):
            payload["nextAction"] = (
                "当前页已经看到待发货订单卡和聊天输入框，但还没拿到真实订单号。"
                "请点订单卡片里的“¥1.00 / 等待卖家发货”区域，或点“去发货”旁边进入订单详情；"
                "看到“订单号/交易号”后再点只读检查。"
            )
            return payload
        payload["nextAction"] = (
            "当前页看到付款信号和输入框，但没有识别到真实订单号。请打开订单详情页，或聊天页里带“订单号/交易号”的页面。"
        )
        return payload

    raw_url = str(first.get("url") or "")
    parsed = None
    with contextlib.suppress(Exception):
        parsed = urlsplit(raw_url)
    host = (parsed.hostname or "").lower().replace("www.", "") if parsed else ""
    path = (parsed.path or "/") if parsed else ""
    is_goofish_home = host == "goofish.com" and path in {"", "/"}
    is_goofish_im = host == "goofish.com" and path.startswith("/im")
    is_seller_workbench = host == "seller.goofish.com"
    if is_goofish_home:
        payload["nextAction"] = (
            "现在打开的是闲鱼首页，不是买家的已付款聊天/订单页。请从闲鱼消息或订单列表打开这笔已付款订单，页面看到“订单号/交易号”后再点只读检查。"
        )
        return payload
    if is_seller_workbench:
        payload["nextAction"] = (
            "现在已经打开卖家工作台。请在订单/待发货里打开这笔已付款订单，或点联系买家进入聊天页；看到订单号/交易号后再点只读检查。"
        )
        return payload

    if first.get("paidSignal") and not first.get("inputReady"):
        if first.get("orderCardPresent") or first.get("shipActionPresent"):
            payload["nextAction"] = (
                "页面看到了“等待卖家发货”的订单卡，但还没有聊天输入框。"
                "请点进买家的聊天输入区域；如果只看到订单卡，就点订单卡片或“去发货”旁边进入订单详情，看到订单号后再检查。"
            )
            return payload
        payload["nextAction"] = (
            "页面看到了付款信号，但没有找到聊天输入框。请切到买家聊天页，或在订单详情里打开联系买家窗口。"
        )
        return payload
    if is_goofish_im and not first.get("inputReady"):
        payload["nextAction"] = (
            "现在已经打开闲鱼消息页，但还没有点进具体买家的聊天。请在左侧会话列表点进已付款买家，看到聊天输入框和订单号/交易号后再点只读检查。"
        )
        return payload
    if first.get("inputReady") and not first.get("paidSignal"):
        payload["nextAction"] = (
            "页面有聊天输入框，但没看到“已付款/待发货”。请确认这是已付款订单，不要在普通聊天页发卡。"
        )
        return payload
    payload["nextAction"] = (
        "当前闲鱼页还不是已付款聊天/订单页，或没有聊天输入框。请打开真实已付款买家的聊天页/订单详情页。"
    )
    return payload


@app.get("/api/cc-seller-bridge/page-scan")
def scan_cc_seller_bridge_pages():
    """只读扫描卖家 Chromium 打开的闲鱼页，判断是否已付款且可发卡。"""
    try:
        repo_root = Path(__file__).resolve().parents[4]
        script = repo_root / "scripts" / "cc_zhongzhuan_seller_bridge.mjs"
        if not script.exists():
            raise HTTPException(503, "卖家桥接器脚本不存在")
        completed = subprocess.run(
            [
                _seller_bridge_node_binary(),
                str(script),
                "--scan-only",
                "--require-real-order-id",
                "--json",
            ],
            cwd=str(repo_root),
            text=True,
            capture_output=True,
            timeout=30,
            check=False,
        )
        stdout = (completed.stdout or "").strip()
        stderr = (completed.stderr or "").strip()
        try:
            payload = json.loads(stdout) if stdout else {}
        except json.JSONDecodeError:
            payload = {"ok": False, "error": "bridge_output_not_json", "stdout": stdout[-1000:]}
        scan_completed = (
            payload.get("mode") == "scan_only"
            and payload.get("readOnly") is True
            and isinstance(
                payload.get("scans"),
                list,
            )
        )
        if scan_completed:
            payload["ok"] = True
            payload["scanCompleted"] = True
            payload["notReady"] = int(payload.get("strictReadyPages") or 0) <= 0
        else:
            payload.setdefault("ok", completed.returncode == 0 and bool(payload.get("ok", True)))
        payload["exitCode"] = int(completed.returncode)
        payload["readOnly"] = True
        if stderr:
            payload["stderr"] = stderr[-1000:]
        if completed.returncode != 0 and not payload.get("error") and not scan_completed:
            payload["error"] = "seller_bridge_scan_failed"
        _humanize_cc_seller_page_scan(payload)
        return _scrub_status_report(payload)
    except subprocess.TimeoutExpired as e:
        return {
            "ok": False,
            "exitCode": 124,
            "readOnly": True,
            "error": "卖家页面只读检查超时。请确认卖家 Chromium 已打开，并只保留 1 个闲鱼页。",
            "stdout": scrub_secrets((e.stdout or "")[-500:] if isinstance(e.stdout, str) else ""),
            "stderr": scrub_secrets((e.stderr or "")[-500:] if isinstance(e.stderr, str) else ""),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"[XianyuAdmin] /api/cc-seller-bridge/page-scan 出错: {scrub_secrets(str(e))}",
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail=_safe_error(e)) from e


@app.post("/api/cc-seller-bridge/one-shot-delivery")
def run_cc_seller_bridge_one_shot_delivery(req: CCOneShotBridgeRunRequest):
    """从 18800 一键跑卖家桥接器：只发当前已付款页 1 条卡密，不点闲鱼发货。"""
    try:
        repo_root = Path(__file__).resolve().parents[4]
        script = repo_root / "scripts" / "cc_zhongzhuan_seller_bridge.mjs"
        if not script.exists():
            raise HTTPException(503, "卖家桥接器脚本不存在")
        command = [
            _seller_bridge_node_binary(),
            str(script),
            "--delivery-only",
            "--one-shot-override",
            "--require-single-xianyu-page",
            "--require-real-order-id",
            "--json",
        ]
        completed = subprocess.run(
            command,
            cwd=str(repo_root),
            text=True,
            capture_output=True,
            timeout=45,
            check=False,
        )
        stdout = (completed.stdout or "").strip()
        stderr = (completed.stderr or "").strip()
        payload: dict
        try:
            payload = json.loads(stdout) if stdout else {}
        except json.JSONDecodeError:
            payload = {
                "ok": False,
                "error": "bridge_output_not_json",
                "stdout": stdout[-1000:],
            }
        payload.setdefault("ok", completed.returncode == 0 and bool(payload.get("ok", True)))
        payload["exitCode"] = int(completed.returncode)
        payload["deliveryOnly"] = True
        payload["oneShot"] = True
        if stderr:
            payload["stderr"] = stderr[-1000:]
        if req.reason:
            payload["requestedReason"] = str(req.reason)[:120]
        if completed.returncode != 0 and not payload.get("error"):
            payload["error"] = "seller_bridge_failed"
        return _scrub_status_report(payload)
    except subprocess.TimeoutExpired as e:
        return {
            "ok": False,
            "exitCode": 124,
            "deliveryOnly": True,
            "oneShot": True,
            "error": "卖家桥接器超时。请确认只打开 1 个真实已付款聊天页，然后重试。",
            "stdout": scrub_secrets((e.stdout or "")[-500:] if isinstance(e.stdout, str) else ""),
            "stderr": scrub_secrets((e.stderr or "")[-500:] if isinstance(e.stderr, str) else ""),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"[XianyuAdmin] /api/cc-seller-bridge/one-shot-delivery 出错: {scrub_secrets(str(e))}",
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail=_safe_error(e)) from e


@app.post("/api/cc-seller-bridge/open-page")
def open_cc_seller_bridge_page(req: CCSellerBridgeOpenPageRequest):
    """只导航卖家 Chromium 到闲鱼消息/卖家工作台；不发卡、不改订单。"""
    destination = (req.destination or "im").strip().lower()
    allowed = {"im", "message", "messages", "seller", "workbench"}
    if destination not in allowed:
        raise HTTPException(400, "只支持打开闲鱼消息或卖家工作台")
    try:
        repo_root = Path(__file__).resolve().parents[4]
        script = repo_root / "scripts" / "cc_zhongzhuan_seller_bridge.mjs"
        if not script.exists():
            raise HTTPException(503, "卖家桥接器脚本不存在")
        command = [
            _seller_bridge_node_binary(),
            str(script),
            f"--open-page={destination}",
            "--json",
        ]
        completed = subprocess.run(
            command,
            cwd=str(repo_root),
            text=True,
            capture_output=True,
            timeout=20,
            check=False,
        )
        stdout = (completed.stdout or "").strip()
        stderr = (completed.stderr or "").strip()
        try:
            payload = json.loads(stdout) if stdout else {}
        except json.JSONDecodeError:
            payload = {
                "ok": False,
                "error": "bridge_output_not_json",
                "stdout": stdout[-1000:],
            }
        payload.setdefault("ok", completed.returncode == 0 and bool(payload.get("ok", True)))
        payload["exitCode"] = int(completed.returncode)
        payload["openPageOnly"] = True
        payload["deliveryOnly"] = False
        payload["oneShot"] = False
        if stderr:
            payload["stderr"] = stderr[-1000:]
        if req.reason:
            payload["requestedReason"] = str(req.reason)[:120]
        if completed.returncode != 0 and not payload.get("error"):
            payload["error"] = "seller_bridge_open_page_failed"
        return _scrub_status_report(payload)
    except subprocess.TimeoutExpired as e:
        return {
            "ok": False,
            "exitCode": 124,
            "openPageOnly": True,
            "deliveryOnly": False,
            "oneShot": False,
            "error": "卖家 Chromium 导航超时。请确认卖家浏览器仍在运行。",
            "stdout": scrub_secrets((e.stdout or "")[-500:] if isinstance(e.stdout, str) else ""),
            "stderr": scrub_secrets((e.stderr or "")[-500:] if isinstance(e.stderr, str) else ""),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"[XianyuAdmin] /api/cc-seller-bridge/open-page 出错: {scrub_secrets(str(e))}",
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail=_safe_error(e)) from e


@app.get("/api/cc-ops-snapshot")
def cc_ops_snapshot():
    """返回本机 CC中转运营快照；只读，不触发审计、发货或库存变更。"""
    try:
        return _cc_ops_snapshot_summary()
    except Exception as e:
        logger.error(f"[XianyuAdmin] /api/cc-ops-snapshot 出错: {scrub_secrets(str(e))}", exc_info=True)
        raise HTTPException(status_code=500, detail=_safe_error(e)) from e


@app.get("/api/cc-automation-coverage")
def cc_automation_coverage():
    """返回全自动闭环覆盖清单；只读，不触发审计、发货或库存变更。"""
    try:
        return _cc_automation_coverage_summary()
    except Exception as e:
        logger.error(f"[XianyuAdmin] /api/cc-automation-coverage 出错: {scrub_secrets(str(e))}", exc_info=True)
        raise HTTPException(status_code=500, detail=_safe_error(e)) from e


@app.get("/api/cc-manual-precheck-evidence")
def cc_manual_precheck_evidence():
    """返回人工预检闭环证据；只读，不发卡、不点击发货、不恢复自动发货。"""
    try:
        return _cc_manual_precheck_evidence_summary()
    except Exception as e:
        logger.error(f"[XianyuAdmin] /api/cc-manual-precheck-evidence 出错: {scrub_secrets(str(e))}", exc_info=True)
        raise HTTPException(status_code=500, detail=_safe_error(e)) from e


@app.get("/api/cc-real-order-test-pack")
def cc_real_order_test_pack():
    """返回真实小额单验收包；不发货、不分配卡密，必要时只读刷新证据。"""
    try:
        return _cc_real_order_test_pack_summary()
    except Exception as e:
        logger.error(f"[XianyuAdmin] /api/cc-real-order-test-pack 出错: {scrub_secrets(str(e))}", exc_info=True)
        raise HTTPException(status_code=500, detail=_safe_error(e)) from e


@app.get("/api/cc-buyer-site-smoke-plan")
def cc_buyer_site_smoke_plan():
    """返回站内买家烟测执行计划；只读，不创建用户、不兑换、不调模型。"""
    try:
        return _cc_buyer_site_smoke_plan_summary()
    except Exception as e:
        logger.error(f"[XianyuAdmin] /api/cc-buyer-site-smoke-plan 出错: {scrub_secrets(str(e))}", exc_info=True)
        raise HTTPException(status_code=500, detail=_safe_error(e)) from e


@app.post("/api/cc-ops-notify/check")
def cc_ops_notify_check(force: bool = False):
    """手动检查一次本机运营提醒；force=true 会发送一条当前状态通知。"""
    try:
        return _run_ops_notify_once(force=force)
    except Exception as e:
        logger.error(f"[XianyuAdmin] /api/cc-ops-notify/check 出错: {scrub_secrets(str(e))}", exc_info=True)
        raise HTTPException(status_code=500, detail=_safe_error(e)) from e


def _safe_order_marker(order_id: str) -> dict:
    """把订单号压成可排障但不泄露原文的标记。"""
    text = str(order_id or "").strip()
    prefix = "unknown"
    if text.startswith("xy_oid_"):
        prefix = "xy_oid_"
    elif text.startswith("xy_manual_"):
        prefix = "xy_manual_"
    elif text.startswith("xy_browser_"):
        prefix = "xy_browser_"
    elif text:
        prefix = "numeric" if text.isdigit() else "other"
    return {
        "prefix": prefix,
        "hash": hashlib.sha256(text.encode("utf-8")).hexdigest()[:12] if text else "",
    }


def _seller_bridge_node_binary() -> str:
    """选择支持 DevTools WebSocket 的 Node，可避免 LaunchAgent PATH 命中旧 Node。"""
    candidates = [
        os.getenv("OPENCLAW_NODE_BINARY", "").strip(),
        str(Path.home() / ".local" / "bin" / "node"),
        "/opt/homebrew/bin/node",
        "/usr/local/bin/node",
        "node",
    ]
    seen: set[str] = set()
    for candidate in candidates:
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        try:
            completed = subprocess.run(
                [candidate, "-e", "process.exit(typeof WebSocket === 'function' ? 0 : 1)"],
                text=True,
                capture_output=True,
                timeout=3,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            continue
        if completed.returncode == 0:
            return candidate
    return candidates[-1] or "node"


def _scrub_status_report(value):
    """递归脱敏状态报告，同时保持 JSON 结构不变。"""
    if isinstance(value, dict):
        return {str(k): _scrub_status_report(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_scrub_status_report(item) for item in value]
    if isinstance(value, str):
        return scrub_secrets(value)
    return value


def _cc_simulation_step(key: str, label: str, ok: bool, evidence: str, next_action: str) -> dict:
    """生成严格模拟门单步状态；只写老板能看懂的结论。"""
    return {
        "key": key,
        "label": label,
        "ok": bool(ok),
        "status": "pass" if ok else "missing",
        "evidence": evidence,
        "next_action": next_action,
    }


def _latest_cc_simulation_shipment() -> dict:
    """选择最近一条替换/浏览器模拟履约记录，不返回买家原文或完整卡密。"""
    if not (_ctx and hasattr(_ctx, "list_cc_shipments")):
        return {}
    rows = _ctx.list_cc_shipments(limit=30, include_message=False)
    if not rows:
        return {}
    simulation_prefixes = ("xy_manual_", "xy_browser_", "xy_sim_")
    for row in rows:
        if str(row.get("order_id") or "").startswith(simulation_prefixes):
            return row
    return rows[0]


def _cc_simulation_gate_summary() -> dict:
    """严格模拟门：除真实下单和最终点击发货外，其余链路尽量按正式门给证据。"""
    shipment = _latest_cc_simulation_shipment()
    order_id = str(shipment.get("order_id") or "")
    marker = _safe_order_marker(order_id)
    latest_order = {
        "order": f"{marker['prefix']}{marker['hash']}" if marker.get("hash") else marker.get("prefix"),
        "status": str(shipment.get("status") or "")[:80],
        "item_present": bool(str(shipment.get("item_id") or "").strip()),
        "xianyu_confirm_status": str(shipment.get("xianyu_confirm_status") or "")[:80],
        "relist_status": str(shipment.get("xianyu_relist_status") or "")[:80],
        "buyer_chain_status": str(shipment.get("buyer_chain_status") or "")[:80],
    }

    latest_audit = _latest_strict_audit()
    audit_summary = latest_audit.get("summary") if isinstance(latest_audit, dict) else {}
    if not isinstance(audit_summary, dict):
        audit_summary = {}
    matches = audit_summary.get("same_order_latest") or []
    if not isinstance(matches, list):
        matches = []

    redeemed = bool(int(audit_summary.get("redeemed_delta") or 0) > 0) or any(
        bool(item.get("balanceRedeemed")) for item in matches if isinstance(item, dict)
    )
    api_key_created = bool(int(audit_summary.get("active_token_delta") or 0) > 0) or any(
        int((item or {}).get("activeTokens") or 0) > 0 for item in matches if isinstance(item, dict)
    )
    model_called = bool(int(audit_summary.get("model_log_delta") or 0) > 0) or any(
        int((item or {}).get("modelLogsAfterRedeem") or 0) > 0 for item in matches if isinstance(item, dict)
    )

    readiness = _last_cc_readiness_audit or {}
    product_template = _build_cc_product_template(
        title="CC中转兑换码",
        plan_id=str(shipment.get("item_id") or "")[:80] or "替换模式测试套餐",
        price="1",
    )
    item_present = bool(str(shipment.get("item_id") or "").strip())
    message_sent = str(shipment.get("status") or "") == "message_sent"
    relist_status = str(shipment.get("xianyu_relist_status") or "")
    relisted = relist_status in {"relisted", "online_verified"}
    ccswitch_ok = bool(readiness.get("ccswitch_entry_ok"))
    channel_server_ok = (
        bool(readiness.get("overall_ok") or readiness.get("oracle"))
        and bool(readiness.get("config_contract_ok"))
    )

    steps = [
        _cc_simulation_step(
            "card_sent_to_buyer",
            "真实给买家号发送卡密",
            message_sent,
            "最近替换/浏览器履约记录已进入 message_sent" if message_sent else "还没有已发送卡密的替换履约记录",
            "打开买家聊天页，让浏览器助手发送卡密；发送后应变成已发。",
        ),
        _cc_simulation_step(
            "product_publish_package",
            "补宝贝标题、描述、价格和图片说明",
            item_present and bool(product_template.get("template")),
            "已生成可复制商品模板，且履约记录带商品标识" if item_present else "缺少商品标识或商品模板未生成",
            "复制商品模板到闲鱼发布页，并按模板补标题、描述、价格和至少 1 张宝贝图。",
        ),
        _cc_simulation_step(
            "product_relisted",
            "重新上架/恢复上架已回写",
            relisted,
            "浏览器助手已把恢复上架/在线核验结果回写" if relisted else "尚未看到恢复上架或在线核验成功回写",
            "打开对应闲鱼商品页，页面显示已下架/售罄时让浏览器助手点击重新上架。",
        ),
        _cc_simulation_step(
            "public_redeemed",
            "买家公网注册/兑换到账",
            redeemed,
            "严格门审计看到兑换增量或同单兑换证据" if redeemed else "还没有兑换到账证据",
            "用买家号打开 https://jiyu.245334.xyz/ 注册或登录，并兑换卡密。",
        ),
        _cc_simulation_step(
            "api_key_created",
            "创建 API Key 和名称",
            api_key_created,
            "严格门审计看到 API Key 增量或同单 token 证据" if api_key_created else "还没有 API Key 创建证据",
            "在公网主站创建 API Key，名称写本次替换模式测试用途。",
        ),
        _cc_simulation_step(
            "ccswitch_import_ready",
            "导入 CC Switch 入口可用",
            ccswitch_ok,
            "最近只读巡检确认 CC Switch 导入入口可用" if ccswitch_ok else "还没有 CC Switch 导入入口可用证据",
            "打开主站 CC Switch 页面，复制导入链接；必要时先运行生产内测巡检。",
        ),
        _cc_simulation_step(
            "terminal_model_call",
            "终端真实调用模型成功",
            model_called,
            "严格门审计看到模型调用日志增量" if model_called else "还没有模型调用日志增量",
            "把 API Key 导入 CC Switch 或终端配置后，真实调用一次模型。",
        ),
        _cc_simulation_step(
            "channel_server_status",
            "渠道和服务器状态正常",
            channel_server_ok,
            "最近只读巡检确认 Oracle/渠道可用" if channel_server_ok else "还没有渠道/服务器绿色证据",
            "运行健康检查或刷新 Dashboard，同步 86Game 渠道状态和服务器状态。",
        ),
    ]
    excluded_steps = [
        _cc_simulation_step(
            "real_buyer_payment",
            "买家真实下单付款",
            False,
            "替换模式故意不伪造真实付款",
            "买家号恢复后，跑 1 单新的闲鱼小额真实付款。",
        ),
        _cc_simulation_step(
            "final_xianyu_ship_click",
            "最终点击闲鱼发货按钮",
            False,
            "替换模式不把最终发货点击当作自动完成，避免误点真实交易",
            "真实订单页明确显示已付款/待发货后，再由浏览器助手点击发货。",
        ),
    ]
    missing = [step["label"] for step in steps if not step["ok"]]
    return _scrub_status_report(
        {
            "ok": True,
            "mode": "strict_simulation",
            "simulation_gate_ok": not missing,
            "can_unlock_public_sale": False,
            "strict_gate_required_prefix": "xy_oid_",
            "owner_warning": "严格模拟门只证明替换模式可演练；正式售卖仍必须通过新的 xy_oid_* 真实小额订单。",
            "latest_simulation_order": latest_order,
            "steps": steps,
            "excluded_steps": excluded_steps,
            "missing_steps": missing,
            "product_publish_package": {
                "title": product_template.get("title"),
                "price": product_template.get("price"),
                "template": product_template.get("template"),
                "image_checklist": ["上传至少 1 张宝贝图片", "图片不要包含完整卡密或 API Key"],
            },
            "next_real_gate": "买家号恢复后，仍需跑 1 笔新的 xy_oid_* 闲鱼真实付款订单。",
        }
    )


def _cc_export_status_report() -> dict:
    """生成老板可发给技术支持的脱敏状态报告。"""
    status = system_status()
    mode = _cc_operator_mode_summary()
    snapshot = _cc_ops_snapshot_summary()
    simulation_gate = _cc_simulation_gate_summary()
    sale_lock = snapshot.get("sale_lock") if isinstance(snapshot.get("sale_lock"), dict) else {}
    next_action = snapshot.get("next_action") if isinstance(snapshot.get("next_action"), dict) else {}
    shipments = status.get("cc_shipments") if isinstance(status.get("cc_shipments"), dict) else {}
    queues = {
        "pending_rescue": int(shipments.get("pending_rescue") or 0),
        "browser_delivery_claimed": int(shipments.get("browser_delivery_claimed") or 0),
        "message_send_inflight": int(shipments.get("message_send_inflight") or 0),
        "message_send_uncertain": int(shipments.get("message_send_uncertain") or 0),
        "message_send_failed": int(shipments.get("message_send_failed") or 0),
        "xianyu_confirm_page_pending": int(shipments.get("xianyu_confirm_page_pending") or 0),
        "xianyu_confirm_failed": int(shipments.get("xianyu_confirm_failed") or 0),
        "buyer_chain_verified": int(shipments.get("buyer_chain_verified") or 0),
    }
    recent_orders: list[dict] = []
    if _ctx and hasattr(_ctx, "list_cc_shipments"):
        for row in _ctx.list_cc_shipments(limit=8, include_message=False):
            recent_orders.append(
                {
                    "order": _safe_order_marker(str(row.get("order_id") or "")),
                    "status": str(row.get("status") or "")[:80],
                    "item_present": bool(str(row.get("item_id") or "").strip()),
                    "xianyu_confirm_status": str(row.get("xianyu_confirm_status") or "")[:80],
                    "relist_status": str(row.get("xianyu_relist_status") or "")[:80],
                    "buyer_chain_status": str(row.get("buyer_chain_status") or "")[:80],
                }
            )
    report = {
        "ok": True,
        "generated_at": now_et().isoformat(),
        "operator_summary": {
            "state": next_action.get("state") or mode.get("stage") or "",
            "title": next_action.get("title") or sale_lock.get("state_label") or "",
            "next_action": next_action.get("primary_action") or mode.get("next_action") or "",
            "auto_ship_paused": bool(mode.get("auto_ship_paused")),
            "can_internal_test": bool(sale_lock.get("can_internal_test")),
            "can_public_sale": bool(sale_lock.get("can_public_sale")),
        },
        "runtime": {
            "service": status.get("service"),
            "ws_connected": bool(status.get("ws_connected")),
            "cookie_ok": bool(status.get("cookie_ok")),
            "auto_ship_operational": bool((status.get("cc_auto_ship") or {}).get("operational")),
            "chrome_helper_online": bool((status.get("cc_chrome_extension") or {}).get("online")),
            "chrome_helper_next_action": (status.get("cc_chrome_extension") or {}).get("next_action") or "",
        },
        "queues": queues,
        "inventory": {
            "unused_cards": (sale_lock.get("inventory") or {}).get("unused_cards"),
            "redeem_available": (sale_lock.get("inventory") or {}).get("redeem_available"),
            "active_channels": (sale_lock.get("inventory") or {}).get("active_channels"),
            "enabled_monitors": (sale_lock.get("inventory") or {}).get("enabled_monitors"),
            "updated_at": (sale_lock.get("inventory") or {}).get("updated_at"),
        },
        "simulation_gate": {
            "mode": simulation_gate.get("mode"),
            "simulation_gate_ok": bool(simulation_gate.get("simulation_gate_ok")),
            "can_unlock_public_sale": bool(simulation_gate.get("can_unlock_public_sale")),
            "missing_steps": simulation_gate.get("missing_steps") or [],
            "excluded_steps": [
                {"key": item.get("key"), "label": item.get("label")}
                for item in (simulation_gate.get("excluded_steps") or [])
                if isinstance(item, dict)
            ],
        },
        "recent_orders": recent_orders,
        "plain_language_next_step": "联系技术支持时，把这个 JSON 发过去；里面已经去掉卡密、Token、买家昵称和 API Key。",
    }
    return _scrub_status_report(report)


@app.get("/api/export-status")
def export_status():
    """导出脱敏系统状态报告，方便老板一键发给技术支持。"""
    try:
        return _cc_export_status_report()
    except Exception as e:
        logger.error(f"[XianyuAdmin] /api/export-status 出错: {scrub_secrets(str(e))}", exc_info=True)
        raise HTTPException(status_code=500, detail=_safe_error(e)) from e


@app.get("/export-status")
def export_status_shortcut():
    """兼容老板手册里的短入口。"""
    return export_status()


@app.get("/api/cc-simulation-gate")
def cc_simulation_gate():
    """严格模拟门：展示替换模式距离正式严格门还差哪几步。"""
    try:
        return _cc_simulation_gate_summary()
    except Exception as e:
        logger.error(f"[XianyuAdmin] /api/cc-simulation-gate 出错: {scrub_secrets(str(e))}", exc_info=True)
        raise HTTPException(status_code=500, detail=_safe_error(e)) from e


@app.get("/api/cc-replacement-mode-test-pack")
def cc_replacement_mode_test_pack():
    """返回替换模式模拟验收清单；只演练，不放宽真实订单严格门。"""
    try:
        shipment_summary = _ctx.cc_shipment_summary() if _ctx and hasattr(_ctx, "cc_shipment_summary") else {}
        simulation_gate = _cc_simulation_gate_summary()
        return {
            "ok": True,
            "mode": "replacement_simulation",
            "can_unlock_public_sale": False,
            "strict_gate_required_prefix": "xy_oid_",
            "owner_warning": "替换模式只用于当前买家号不可用时演练流程，不替代真实小额订单。",
            "current_queue": {
                "pending_rescue": int((shipment_summary or {}).get("pending_rescue") or 0),
                "message_sent": int((shipment_summary or {}).get("message_sent") or 0),
                "buyer_chain_verified": int((shipment_summary or {}).get("buyer_chain_verified") or 0),
            },
            "simulation_gate": simulation_gate,
            "checklist": [
                {"label": "模拟买家下单", "how": "在操作台“已付款漏单兜底”里填写替换买家备注和商品。"},
                {"label": "自动发送卡密", "how": "生成话术后交给浏览器助手发送；必要时人工复制。"},
                {"label": "自动确认发货", "how": "桥接器只在当前闲鱼页可见已付款/待发货时点击。"},
                {"label": "补商品图片描述价格", "how": "复制商品模板后在闲鱼发布页补图、描述和测试价。"},
                {"label": "模拟买家拿到卡密", "how": "打开发货话术里的公网兑换入口。"},
                {"label": "公网注册账号", "how": "访问 https://jiyu.245334.xyz/ 注册或登录测试账号。"},
                {"label": "兑换卡密", "how": "在公网兑换码入口输入卡密，确认余额到账。"},
                {"label": "创建 API 及名称", "how": "在主站创建 API Key，名称写测试用途。"},
                {"label": "导入 CC Switch", "how": "复制导入链接或配置到 CC Switch。"},
                {"label": "终端真实调用测试", "how": "用生成的 API Key 调一次模型，确认返回成功。"},
            ],
            "next_real_gate": "买家号恢复后，仍需跑 1 笔新的 xy_oid_* 闲鱼真实付款订单。",
        }
    except Exception as e:
        logger.error(f"[XianyuAdmin] /api/cc-replacement-mode-test-pack 出错: {scrub_secrets(str(e))}", exc_info=True)
        raise HTTPException(status_code=500, detail=_safe_error(e)) from e


@app.get("/api/cc-product-template")
def cc_product_template(title: str = "", plan_id: str = "", price: str = ""):
    """生成可复制的闲鱼商品模板，只包含履约说明。"""
    try:
        return _build_cc_product_template(title=title, plan_id=plan_id, price=price)
    except Exception as e:
        logger.error(f"[XianyuAdmin] /api/cc-product-template 出错: {scrub_secrets(str(e))}", exc_info=True)
        raise HTTPException(status_code=500, detail=_safe_error(e)) from e


@app.get("/api/cc-readiness-audit")
def cc_readiness_audit(mode: str = Query("read_only")):
    """运行 CC中转生产闭环审计，供本机 GUI 一键查看。"""
    try:
        return _run_cc_readiness_audit(mode)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[XianyuAdmin] /api/cc-readiness-audit 出错: {scrub_secrets(str(e))}", exc_info=True)
        raise HTTPException(status_code=500, detail=_safe_error(e)) from e


def _secure_admin_html_response(html: str) -> HTMLResponse:
    """为本机管理页签发一次性脚本 nonce，并禁止页面被缓存或嵌入。"""
    nonce = secrets.token_urlsafe(24)
    content = html.replace("<script>", f'<script nonce="{nonce}">')
    csp = "; ".join(
        (
            "default-src 'none'",
            f"script-src 'self' 'nonce-{nonce}'",
            "style-src 'self' 'unsafe-inline'",
            "img-src 'self' data:",
            "font-src 'self'",
            "connect-src 'self'",
            "object-src 'none'",
            "base-uri 'none'",
            "form-action 'self'",
            "frame-ancestors 'none'",
        )
    )
    return HTMLResponse(
        content,
        headers={
            "Cache-Control": "no-store",
            "Content-Security-Policy": csp,
            "Referrer-Policy": "no-referrer",
            "X-Content-Type-Options": "nosniff",
        },
    )


@app.get("/ops-links", response_class=HTMLResponse)
def ops_links() -> HTMLResponse:
    """本机老板日常运营状态中心；只展示决策信息，工程细节默认折叠。"""
    html = """<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>CC中转状态中心</title>
  <link rel="icon" href="data:,">
  <style>
    :root{color-scheme:dark;--bg:#050507;--surface:#111114;--card:#1b1b1f;--card2:#24242a;--line:rgba(255,255,255,.09);--text:#f5f5f7;--muted:#a1a1aa;--soft:#d4d4d8;--ok:#32d583;--warn:#fdb022;--bad:#f97066;--accent:#8b7cf6;--blue:#67e8f9}
    *{box-sizing:border-box} body{margin:0;min-height:100vh;background:radial-gradient(circle at 50% -20%,rgba(139,124,246,.18),transparent 42%),linear-gradient(180deg,#07070a 0%,#030304 100%);color:var(--text);font-family:-apple-system,BlinkMacSystemFont,"SF Pro Display","Segoe UI",Roboto,"PingFang SC",sans-serif;-webkit-font-smoothing:antialiased} main{width:min(1080px,calc(100% - 40px));margin:0 auto;padding:42px 0 48px}.top{display:flex;justify-content:space-between;gap:24px;align-items:flex-start;margin-bottom:26px}.kicker{color:var(--muted);font-size:13px;font-weight:700;letter-spacing:.08em;text-transform:uppercase}.title{font-size:52px;letter-spacing:-.055em;line-height:.96;margin:8px 0 14px}.subtitle{max-width:650px;margin:0;color:var(--muted);font-size:17px;line-height:1.65}.actions{display:flex;gap:10px;flex-wrap:wrap;justify-content:flex-end}.btn,button{border:1px solid var(--line);background:rgba(255,255,255,.06);color:var(--text);border-radius:999px;padding:11px 15px;font-weight:750;text-decoration:none;cursor:pointer;transition:transform .18s ease,background .18s ease,border-color .18s ease}.btn:hover,button:hover{transform:translateY(-1px);background:rgba(255,255,255,.1);border-color:rgba(255,255,255,.17)}.primary{background:#f5f5f7;color:#050507;border-color:#f5f5f7}.primary:hover{background:#fff}.grid{display:grid;grid-template-columns:1.12fr .88fr;gap:16px}.stack{display:grid;gap:16px}.card{background:linear-gradient(180deg,rgba(255,255,255,.085),rgba(255,255,255,.045));border:1px solid var(--line);border-radius:30px;padding:24px;box-shadow:0 28px 70px rgba(0,0,0,.28)}.hero-card{min-height:360px;display:grid;align-content:space-between}.status-word{font-size:44px;letter-spacing:-.045em;font-weight:850;line-height:1.02}.tiny{font-size:13px;color:var(--muted);line-height:1.55}.pills{display:flex;gap:9px;flex-wrap:wrap}.pill{display:inline-flex;align-items:center;gap:8px;border:1px solid var(--line);background:rgba(255,255,255,.05);border-radius:999px;padding:7px 10px;color:var(--soft);font-size:12px;font-weight:750}.dot{width:8px;height:8px;border-radius:999px;background:var(--muted);box-shadow:0 0 18px currentColor}.ok{color:var(--ok)}.warn{color:var(--warn)}.bad{color:var(--bad)}.ring-wrap{display:flex;align-items:center;justify-content:center;min-height:210px}.ring{--pct:0;width:184px;height:184px;border-radius:50%;display:grid;place-items:center;background:conic-gradient(var(--ok) calc(var(--pct)*1%),rgba(255,255,255,.08) 0);position:relative}.ring:after{content:"";position:absolute;inset:13px;border-radius:50%;background:#141418;border:1px solid var(--line)}.ring b{position:relative;z-index:1;font-size:36px;letter-spacing:-.05em}.ring span{position:relative;z-index:1;display:block;color:var(--muted);font-size:12px;text-align:center}.mini-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:16px;margin-top:16px}.mini{min-height:160px}.mini h2{font-size:13px;color:var(--muted);margin:0 0 18px}.metric{font-size:34px;letter-spacing:-.045em;font-weight:850}.desc{margin-top:10px;color:var(--muted);font-size:14px;line-height:1.55}.next{margin-top:16px;display:grid;grid-template-columns:1fr auto;gap:14px;align-items:center}.next h2{margin:0 0 8px;font-size:14px;color:var(--muted)}.next-text{font-size:22px;letter-spacing:-.03em;line-height:1.25;font-weight:780}.token{max-width:430px;margin-left:auto}.token input{width:100%;border:1px solid var(--line);background:rgba(0,0,0,.28);color:var(--text);border-radius:16px;padding:13px 14px;margin:14px 0 10px;outline:none}.hidden{display:none!important}details{margin-top:16px}summary{cursor:pointer;color:var(--muted);font-weight:760}.debug{display:grid;grid-template-columns:repeat(2,1fr);gap:10px;margin-top:14px}.debug div{border:1px solid var(--line);border-radius:16px;padding:12px;color:var(--muted);font-size:13px;line-height:1.45}.error{border-color:rgba(249,112,102,.38);background:rgba(127,29,29,.18)}@media(max-width:880px){main{width:min(100% - 24px,1080px);padding-top:24px}.top,.grid,.next{grid-template-columns:1fr;display:grid}.title{font-size:40px}.actions{justify-content:flex-start}.mini-grid,.debug{grid-template-columns:1fr}.ring{width:154px;height:154px}}
  </style>
</head>
<body>
<main class="layui-container oe-console">
  <section class="top">
    <div>
      <div class="kicker">CC 中转 · 生产内测</div>
      <h1 class="title">状态中心</h1>
      <p class="subtitle">这个页面只给你看结论：现在能不能卖、自动发货是否安全、下一步该做什么。操作请去“操作台”。</p>
    </div>
    <div class="actions">
      <a class="btn primary" href="http://127.0.0.1:18800/" target="_blank" rel="noreferrer">打开操作台</a>
      <a class="btn" href="https://jiyu.245334.xyz/" target="_blank" rel="noreferrer">打开主站</a>
      <button id="refresh-button" type="button">刷新</button>
    </div>
  </section>

  <section class="card token" id="token-box">
    <div class="kicker">本机授权</div>
    <div class="desc">需要本机 API Token 换取 15 分钟管理会话。Token 不会保存在浏览器存储中。</div>
    <input id="token-input" type="password" autocomplete="off" autocapitalize="off" spellcheck="false" placeholder="OPENCLAW_API_TOKEN">
    <button class="primary" id="save-token-button" type="button">保存并刷新</button>
  </section>

  <section class="grid" id="dashboard" aria-label="CC中转状态中心">
    <article class="card hero-card">
      <div>
        <div class="kicker" id="hero-kicker">读取中</div>
        <div class="status-word" id="main-title">等待状态</div>
        <p class="subtitle" id="main-subtitle">正在读取本机运营快照。</p>
      </div>
      <div class="pills" id="hero-pills"><span class="pill"><i class="dot warn"></i>等待</span></div>
    </article>
    <article class="card">
      <div class="kicker">闭环进度</div>
      <div class="ring-wrap"><div class="ring" id="ring"><div><b id="ring-num">0%</b><span id="ring-label">读取中</span></div></div></div>
      <p class="desc" id="ring-desc">只统计内测发货、库存、兑换、API Key、CC Switch、调模型这些关键步骤。</p>
    </article>
  </section>

  <section class="mini-grid">
    <article class="card mini"><h2>自动发货</h2><div class="metric" id="m-ship">--</div><div class="desc" id="d-ship">读取中</div></article>
    <article class="card mini"><h2>库存与渠道</h2><div class="metric" id="m-stock">--</div><div class="desc" id="d-stock">读取中</div></article>
    <article class="card mini"><h2>买家链路</h2><div class="metric" id="m-buyer">--</div><div class="desc" id="d-buyer">读取中</div></article>
  </section>

  <section class="card next">
    <div><h2>下一步</h2><div class="next-text" id="next-action">读取中</div></div>
    <button id="copy-template-button" type="button">复制商品模板</button>
  </section>

  <details class="card">
    <summary>高级排障信息</summary>
    <div class="debug" id="debug-list"><div>读取中</div></div>
  </details>
</main>
<script src="/static/layui/layui.js"></script>
<script>
const $=id=>document.getElementById(id);
let layuiLayer=null,layuiElement=null;
if(window.layui){layui.use(['layer','element'],function(){layuiLayer=layui.layer;layuiElement=layui.element;layuiElement.render();});}
function notice(message,icon=1){if(layuiLayer)layuiLayer.msg(message,{icon,time:1800});else alert(message)}
function askConfirm(message,onYes){if(layuiLayer)layuiLayer.confirm(message,{title:'请确认'},function(index){layuiLayer.close(index);onYes();});else if(confirm(message))onYes();}
let manualShipmentId=0;
function element(tag,className='',text=''){const item=document.createElement(tag);if(className)item.className=className;if(text!==undefined&&text!==null)item.textContent=String(text);return item}
async function saveToken(){const input=$('token-input'),token=input.value.trim(); if(!token)return; input.value=''; const res=await fetch('/api/session',{method:'POST',credentials:'same-origin',headers:{'X-API-Token':token}}); if(!res.ok)throw new Error(res.status===401?'missing-token':'HTTP '+res.status); await loadSnapshot(true)}
async function api(url){const res=await fetch(url,{credentials:'same-origin'}); if(res.status===401)throw new Error('missing-token'); if(!res.ok)throw new Error('HTTP '+res.status); return res.json()}
function pill(label,kind='warn'){const item=element('span','pill');item.append(element('i',`dot ${kind}`),document.createTextNode(String(label??'')));return item}
function debugItem(label,value){const item=element('div');item.append(element('b','',label),document.createElement('br'),document.createTextNode(String(value??'')));return item}
function setMetric(id,value,desc){$('m-'+id).textContent=value; $('d-'+id).textContent=desc}
function boolKind(v){return v?'ok':'bad'}
function pct(done,total){return total?Math.max(0,Math.min(100,Math.round(done*100/total))):0}
function renderMissingToken(){
  $('token-box').classList.remove('hidden'); $('dashboard').classList.add('hidden');
  $('next-action').textContent='先填 OPENCLAW_API_TOKEN，然后刷新。';
}
function renderSnapshot(data,mode){
  $('token-box').classList.add('hidden'); $('dashboard').classList.remove('hidden');
  const status=data.status||{}, lock=data.sale_lock||{}, watch=data.loop_watch||{}, progress=data.buyer_progress||{}, action=data.next_action||{};
  const auto=status.cc_auto_ship||{}, ship=status.cc_shipments||{}, inv=lock.inventory||{}, gates=lock.gates||{};
  const paused=mode.auto_ship_paused===true || auto.paused===true;
  const internalReady=lock.can_internal_test===true;
  const publicReady=lock.can_public_sale===true;
  const strictPaused=lock.state==='paused_after_strict_gate';
  const autoReady=mode.can_auto_ship_paid_orders===true;
  $('hero-kicker').textContent=paused?'人工暂停中':(publicReady?'正式售卖':(internalReady?'生产内测':'需要处理'));
  $('main-title').textContent=paused?'自动发货已暂停':(action.title||lock.state_label||'状态未知');
  $('main-subtitle').textContent=paused?'你已经手动暂停发货。想继续卖时，先确认库存，再到操作台恢复。':(action.primary_action||lock.next_action||'按下一步执行。');
  $('hero-pills').replaceChildren(
    pill(publicReady?'正式可售':(internalReady?'内测可发货':'暂不建议上架'),publicReady||internalReady?'ok':'bad'),
    pill(paused?'发货暂停':(autoReady?'自动发货正常':'自动发货待处理'),paused?'warn':boolKind(autoReady)),
    pill((watch.stage_label||'实单闭环未知'),watch.ready_for_public_sale?'ok':'warn')
  );
  const completed=[autoReady, Number(inv.redeem_available||0)>0, Number(inv.active_channels||0)===10, Number(inv.enabled_monitors||0)===10, gates.ccswitch_import_ready===true, (progress.steps||{}).same_order_verified===true].filter(Boolean).length;
  const percent=pct(completed,6); $('ring').style.setProperty('--pct',percent); $('ring-num').textContent=percent+'%'; $('ring-label').textContent=publicReady?'已放行':'内测闭环';
  $('ring-desc').textContent=`关键步骤 ${completed}/6；正式售卖前仍以真实小额单为准。`;
  setMetric('ship',paused?'暂停':(autoReady?'正常':'检查'),`补救 ${ship.pending_rescue??0}；闲鱼 ${status.ws_connected?'在线':'离线'}；Cookie ${status.cookie_ok?'正常':'异常'}`);
  setMetric('stock',`${inv.redeem_available??'--'} 个`,`渠道 ${inv.active_channels??'--'}/10；监控 ${inv.enabled_monitors??'--'}/10`);
  const steps=progress.steps||{}; setMetric('buyer',steps.same_order_verified?'完成':'待跑',progress.next_action||watch.next_action||'等待真实小额单');
  $('next-action').textContent=paused?'如需继续售卖：先确认库存，再打开操作台恢复自动发货。':(action.primary_action||lock.next_action||watch.next_action||'继续观察。');
  $('debug-list').replaceChildren(...[
    ['售卖锁',lock.state_label||lock.state||'未知'],['自动发货',paused?'暂停':(autoReady?'正常':'待处理')],['商品映射',`${mode.enabled_item_mappings??0}/${mode.total_item_mappings??0}`],['补救队列',String(ship.pending_rescue??0)],['库存更新时间',inv.updated_at||'未刷新'],['接口说明','/v1 是程序接口，不是人工页面']
  ].map(([k,v])=>debugItem(k,v)));
}
async function loadSnapshot(refresh=false){
  try{
    const [snap,mode]=await Promise.all([api('/api/cc-ops-snapshot'+(refresh?'?refresh=true':'')),api('/api/cc-operator-mode')]);
    renderSnapshot(snap,mode||{});
  }catch(err){ if(String(err.message||err)==='missing-token'){renderMissingToken();return} $('dashboard').classList.remove('hidden'); $('main-title').textContent='读取失败'; $('main-subtitle').textContent=String(err.message||err); $('hero-pills').replaceChildren(pill('错误','bad')); }
}
async function copyTemplate(){
  try{const data=await api('/api/cc-product-template?title=CC中转内测卡&price=小额测试价'); await navigator.clipboard.writeText(data.template||''); notice('已复制商品模板');}
  catch(err){alert('复制失败：'+(err.message||err))}
}
$('refresh-button').addEventListener('click',()=>loadSnapshot(true));
$('save-token-button').addEventListener('click',()=>saveToken());
$('copy-template-button').addEventListener('click',()=>copyTemplate());
window.addEventListener('load',()=>{loadSnapshot(false); setInterval(()=>loadSnapshot(false),60000);});
</script>
</body>
</html>"""
    return _secure_admin_html_response(html)


@app.get("/", response_class=HTMLResponse)
def index() -> HTMLResponse:
    """本机 CC中转操作台；老板首屏只看关键运营结论，操作与排障默认折叠。"""
    html = """<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>CC中转操作台</title>
  <link rel="icon" href="data:,">
  <link rel="stylesheet" href="/static/layui/css/layui.css">
  <style>
    :root{color-scheme:dark;--canvas:oklch(9% .006 250);--panel:rgba(255,255,255,.045);--panel-strong:rgba(255,255,255,.07);--panel-soft:rgba(255,255,255,.025);--line:rgba(255,255,255,.075);--line-strong:rgba(255,255,255,.12);--text:rgba(255,255,255,.9);--muted:rgba(255,255,255,.56);--faint:rgba(255,255,255,.34);--ok:oklch(75% .16 154);--warn:oklch(80% .15 83);--bad:oklch(68% .18 28);--info:oklch(78% .09 230);--r-lg:28px;--r-md:20px;--r-sm:14px;--r-pill:999px}
    *{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0;min-height:100vh;background:radial-gradient(circle at 52% -18%,rgba(255,255,255,.105),transparent 38%),linear-gradient(180deg,#111216 0%,#07080a 46%,#050607 100%);color:var(--text);font-family:-apple-system,BlinkMacSystemFont,"SF Pro Display","Segoe UI",Roboto,"PingFang SC",sans-serif;-webkit-font-smoothing:antialiased;font-variant-numeric:tabular-nums}.layui-layer{color:#333}.layui-layer-dialog .layui-layer-content{color:#333}.layui-form-label{color:var(--muted);padding-left:0;text-align:left}.layui-input,.layui-textarea{background:rgba(0,0,0,.24)!important;border-color:var(--line)!important;color:var(--text)!important}.layui-table{background:transparent;color:var(--text);margin:0}.layui-table th{background:rgba(255,255,255,.055);color:var(--muted)}.layui-table td,.layui-table th{border-color:var(--line)}.layui-table tbody tr:hover{background:rgba(255,255,255,.035)}.layui-btn{border-radius:999px;font-weight:760}.layui-btn-primary{background:transparent;color:var(--text);border-color:var(--line)}.layui-btn-danger{background:rgba(255,99,82,.15);color:#ffd5cf;border:0}.layui-btn-normal{background:rgba(103,232,249,.15);color:#d7fbff}.layui-nav.oe-nav{background:rgba(255,255,255,.055);border:1px solid var(--line);border-radius:999px;margin-bottom:16px;padding:0 10px}.layui-nav.oe-nav .layui-nav-item a{color:var(--muted)}.layui-nav.oe-nav .layui-this:after{background:#f5f5f7;height:2px}button,a,input,textarea{font:inherit}button,.btn{min-height:40px;border:0;background:rgba(255,255,255,.075);color:var(--text);border-radius:var(--r-pill);padding:10px 15px;font-weight:760;text-decoration:none;cursor:pointer;transition:transform .16s cubic-bezier(.2,0,0,1),background .16s cubic-bezier(.2,0,0,1),opacity .16s cubic-bezier(.2,0,0,1);touch-action:manipulation}button:active,.btn:active{transform:scale(.96)}@media(hover:hover){button:hover,.btn:hover{background:rgba(255,255,255,.12)}}button:focus-visible,.btn:focus-visible,input:focus-visible,textarea:focus-visible,summary:focus-visible{outline:2px solid rgba(255,255,255,.45);outline-offset:3px}.primary{background:#f5f5f7;color:#050607}.danger{background:rgba(255,99,82,.15);color:#ffd5cf}.okbtn{background:rgba(50,213,131,.15);color:#d7ffe8}.ghost{background:transparent;border:1px solid var(--line)}main{width:min(1180px,calc(100% - 36px));margin:0 auto;padding:34px 0 56px}.top{display:grid;grid-template-columns:1fr auto;gap:20px;align-items:start;margin-bottom:22px}.kicker{color:var(--faint);font-size:12px;font-weight:820;letter-spacing:.12em;text-transform:uppercase}.title{margin:7px 0 10px;font-size:52px;line-height:.96;letter-spacing:-.055em;font-weight:860;text-wrap:balance}.subtitle{margin:0;max-width:700px;color:var(--muted);font-size:16px;line-height:1.58;text-wrap:pretty}.actions{display:flex;gap:9px;flex-wrap:wrap;justify-content:flex-end}.card{background:linear-gradient(180deg,var(--panel-strong),var(--panel));border:1px solid var(--line);border-radius:var(--r-lg);box-shadow:0 30px 80px rgba(0,0,0,.28);outline:1px solid rgba(255,255,255,.025);outline-offset:-1px}.hero{display:grid;grid-template-columns:minmax(0,1.06fr) minmax(320px,.94fr);gap:16px;margin-bottom:16px}.verdict{min-height:330px;padding:28px;display:grid;align-content:space-between;overflow:hidden;position:relative}.verdict:after{content:"";position:absolute;right:-80px;top:-120px;width:260px;height:260px;border-radius:50%;background:radial-gradient(circle,rgba(255,255,255,.12),transparent 70%);pointer-events:none}.verdict-word{position:relative;z-index:1;margin:12px 0 12px;font-size:54px;line-height:.98;letter-spacing:-.06em;font-weight:880;text-wrap:balance}.verdict-copy{position:relative;z-index:1;color:var(--muted);font-size:17px;line-height:1.62;max-width:720px}.signal-row{display:flex;gap:9px;flex-wrap:wrap;margin-top:22px}.pill{display:inline-flex;align-items:center;gap:8px;border:1px solid var(--line);background:rgba(255,255,255,.045);border-radius:var(--r-pill);padding:7px 10px;color:rgba(255,255,255,.72);font-size:12px;font-weight:780}.dot{width:8px;height:8px;border-radius:50%;background:var(--faint);box-shadow:0 0 18px currentColor}.ok{color:var(--ok)}.warn{color:var(--warn)}.bad{color:var(--bad)}.info{color:var(--info)}.intervention{padding:24px;display:grid;gap:18px}.status-orb{width:118px;height:118px;border-radius:50%;display:grid;place-items:center;background:conic-gradient(var(--ok) var(--orb,72%),rgba(255,255,255,.08) 0);margin-left:auto;position:relative}.status-orb:after{content:"";position:absolute;inset:10px;border-radius:50%;background:#111216;border:1px solid var(--line)}.status-orb b{position:relative;z-index:1;font-size:27px;letter-spacing:-.04em}.intervention h2{font-size:27px;line-height:1.1;letter-spacing:-.035em;margin:0;text-wrap:balance}.intervention p{margin:0;color:var(--muted);line-height:1.56}.intervention-actions{display:flex;gap:9px;flex-wrap:wrap}.cards{display:grid;grid-template-columns:repeat(6,1fr);gap:12px;margin-bottom:16px}.status-card{min-height:150px;padding:17px;background:linear-gradient(180deg,rgba(255,255,255,.055),rgba(255,255,255,.028));border:1px solid var(--line);border-radius:24px}.status-card .label{display:flex;align-items:center;justify-content:space-between;gap:10px;color:var(--faint);font-size:12px;font-weight:820;letter-spacing:.03em}.status-card .value{margin-top:26px;font-size:28px;line-height:1;letter-spacing:-.045em;font-weight:860}.status-card .desc{margin-top:12px;color:var(--muted);font-size:13px;line-height:1.42}.drawers{display:grid;gap:12px}.drawer{padding:0;overflow:hidden}.drawer summary{list-style:none;cursor:pointer;padding:19px 21px;display:flex;align-items:center;justify-content:space-between;gap:12px;color:var(--text);font-weight:830}.drawer summary::-webkit-details-marker{display:none}.drawer summary span{color:var(--muted);font-size:13px;font-weight:650}.drawer .body{border-top:1px solid var(--line);padding:20px}.grid-2{display:grid;grid-template-columns:1fr 1fr;gap:16px}.field{display:grid;gap:7px;margin-bottom:12px}label{color:var(--faint);font-size:12px;font-weight:780}input,textarea{width:100%;border:1px solid var(--line);background:rgba(0,0,0,.24);color:var(--text);border-radius:var(--r-sm);padding:12px 13px;outline:none}textarea{min-height:130px;resize:vertical;line-height:1.55}.row{display:flex;gap:9px;flex-wrap:wrap;align-items:center}.list{display:grid;gap:10px}.item{border:1px solid var(--line);border-radius:18px;padding:13px;background:rgba(255,255,255,.035)}.item-top{display:flex;justify-content:space-between;gap:12px}.hint{color:var(--muted);font-size:13px;line-height:1.5}.empty{color:var(--muted);border:1px dashed var(--line);border-radius:18px;padding:18px;text-align:center}.top-alerts{display:grid;gap:10px;margin-bottom:16px}.top-alert{display:grid;grid-template-columns:1fr auto;gap:14px;align-items:center;border:1px solid var(--line);border-radius:22px;padding:15px 16px;background:rgba(255,255,255,.045)}.top-alert.bad{border-color:rgba(255,99,82,.42);background:linear-gradient(135deg,rgba(255,99,82,.18),rgba(255,255,255,.035))}.top-alert.warn{border-color:rgba(255,214,10,.35);background:linear-gradient(135deg,rgba(255,214,10,.14),rgba(255,255,255,.035))}.top-alert .alert-title{font-size:16px;font-weight:850;letter-spacing:-.02em}.top-alert .alert-desc{margin-top:5px;color:var(--muted);font-size:13px;line-height:1.45}.top-alert .alert-actions{display:flex;gap:8px;flex-wrap:wrap;justify-content:flex-end}.mono{font-family:"SF Mono",ui-monospace,Menlo,monospace;color:rgba(255,255,255,.72);word-break:break-all}.hidden{display:none!important}.debug-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:10px}.debug-grid div{border:1px solid var(--line);border-radius:16px;padding:12px;color:var(--muted);font-size:13px;line-height:1.45}table{width:100%;border-collapse:collapse;font-size:13px}td,th{border-bottom:1px solid var(--line);padding:9px;text-align:left}th{color:var(--faint);font-weight:780}@media(max-width:1120px){.cards{grid-template-columns:repeat(3,1fr)}}@media(max-width:860px){main{width:min(100% - 24px,1180px);padding-top:24px}.top,.hero,.grid-2{grid-template-columns:1fr}.actions{justify-content:flex-start}.title{font-size:40px}.verdict-word{font-size:42px}.cards{grid-template-columns:1fr 1fr}.debug-grid{grid-template-columns:1fr}.status-orb{margin-left:0}}@media(max-width:520px){.cards{grid-template-columns:1fr}.verdict{min-height:280px;padding:22px}.status-card{min-height:132px}}
  </style>
</head>
<body>
<main class="layui-container oe-console">
  <section class="top">
    <div>
      <div class="kicker">OpenEverything · 统一运营入口</div>
      <h1 class="title">今天能不能卖，一眼看懂。</h1>
      <p class="subtitle">一个网址看完闲鱼售卖、每日简报、系统维护和帮助中心。首屏只回答老板每天关心的 6 件事；商品绑定、漏单补救、模板和工程排障都收在下面。</p>
    </div>
    <div class="actions">
      <a class="layui-btn layui-btn-primary primary" href="https://jiyu.245334.xyz/" target="_blank" rel="noreferrer">打开主站</a>
      <a class="layui-btn layui-btn-primary" href="https://www.goofish.com/" target="_blank" rel="noreferrer">打开闲鱼</a>
      <a class="layui-btn layui-btn-primary ghost" href="http://127.0.0.1:18800/ops-links" target="_blank" rel="noreferrer">状态中心</a>
      <button class="layui-btn layui-btn-primary ghost" data-action="export-status" type="button">导出状态报告</button>
      <button class="layui-btn layui-btn-normal" data-action="refresh" type="button">刷新</button>
    </div>
  </section>

  <section class="card layui-card" id="auth-box" style="max-width:520px;margin-left:auto;padding:22px;margin-bottom:16px">
    <div class="kicker">本机授权</div>
    <p class="hint">需要本机 API Token；Token 只用于换取 15 分钟 HttpOnly 管理会话，不会写入浏览器存储。</p>
    <input id="token-input" type="password" autocomplete="off" autocapitalize="off" spellcheck="false" placeholder="OPENCLAW_API_TOKEN" style="margin:12px 0">
    <button class="primary" data-action="save-token" type="button">保存并刷新</button>
  </section>

  <section id="app-shell" class="hidden">
    <ul class="layui-nav oe-nav" lay-filter="owner-nav" aria-label="统一运营入口导航">
      <li class="layui-nav-item layui-this"><a href="#overview">首页总览</a></li>
      <li class="layui-nav-item"><a href="#queue-drawer">闲鱼售卖</a></li>
      <li class="layui-nav-item"><a href="#audit-drawer">系统维护</a></li>
      <li class="layui-nav-item"><a href="#help-drawer">帮助中心</a></li>
    </ul>
    <section class="top-alerts hidden" id="top-alerts" aria-live="polite"></section>

    <section class="cards" aria-label="统一运营入口导航" id="overview">
      <article class="status-card"><div class="label">🏠 首页总览 <i class="dot ok"></i></div><div class="value">总览</div><div class="desc">打开后 3 秒判断绿灯、黄灯、红灯。</div></article>
      <article class="status-card"><div class="label">💰 闲鱼售卖 <i class="dot warn"></i></div><div class="value">发货</div><div class="desc">自动发货开关、补救队列、库存预警。</div></article>
      <article class="status-card"><div class="label">📊 每日简报 <i class="dot info"></i></div><div class="value">简报</div><div class="desc">订阅者、推送和数据源健康入口。</div></article>
      <article class="status-card"><div class="label">🔧 系统维护 <i class="dot info"></i></div><div class="value">维护</div><div class="desc">只读巡检、状态报告、备份和服务器监控。</div></article>
      <article class="status-card"><div class="label">❓ 帮助中心 <i class="dot ok"></i></div><div class="value">怎么办</div><div class="desc">每个告警旁边都给 3 步以内处理办法。</div></article>
      <article class="status-card"><div class="label">📤 技术支持 <i class="dot info"></i></div><div class="value">报告</div><div class="desc">点“导出状态报告”，复制给技术支持。</div></article>
    </section>

    <section class="hero">
      <article class="card layui-card verdict">
        <div>
          <div class="kicker" id="mode-kicker">读取中</div>
          <div class="verdict-word" id="mode-word">等待状态</div>
          <div class="verdict-copy" id="mode-desc">正在读取本机操作状态。</div>
        </div>
        <div class="signal-row" id="mode-pills"></div>
      </article>
      <article class="card layui-card intervention">
        <div class="status-orb" id="status-orb"><b id="orb-text">--</b></div>
        <div>
          <div class="kicker">是否需要老板介入</div>
          <h2 id="intervention-title">读取中</h2>
          <p id="intervention-desc">正在判断。</p>
        </div>
        <div class="intervention-actions">
          <button class="danger" data-action="set-pause" data-paused="true" type="button">暂停自动发货</button>
          <button class="layui-btn layui-btn-warm" data-action="authorize-one-shot" type="button">只放行一次发卡</button>
          <button class="layui-btn" data-action="scan-seller" type="button">只读检查当前页</button>
          <button class="layui-btn layui-btn-normal" data-action="run-one-shot" type="button">一键跑当前页</button>
          <button class="layui-btn layui-btn-primary ghost" data-action="resume-preflight" type="button">恢复前安全检查</button>
          <button class="okbtn" data-action="set-pause" data-paused="false" type="button">恢复自动发货</button>
        </div>
        <p class="hint" id="one-shot-hint">单次放行只给当前已付款页用：发送 1 条卡密后自动失效。</p>
        <p class="hint" id="one-shot-bridge-result">一键跑当前页：请只保留 1 个真实已付款闲鱼页；页面还必须能识别订单号/交易号，才会发送 1 条卡密。</p>
        <div class="row">
          <button class="layui-btn layui-btn-primary" data-action="open-seller" data-destination="im" type="button">打开卖家 Chromium 的闲鱼消息</button>
          <button class="layui-btn layui-btn-primary" data-action="open-seller" data-destination="seller" type="button">打开卖家 Chromium 的工作台</button>
          <a class="layui-btn layui-btn-primary ghost" href="https://www.goofish.com/im?spm=a21ybx.seo.sitemap.3" target="_blank" rel="noreferrer">普通浏览器兜底</a>
          <a class="layui-btn layui-btn-primary ghost" href="https://seller.goofish.com/" target="_blank" rel="noreferrer">工作台兜底</a>
        </div>
        <p class="hint">如果只读检查提示“闲鱼首页”，先点“打开闲鱼消息”，找到已付款买家的聊天；找不到再点“打开卖家工作台”看订单/待发货。</p>
      </article>
    </section>

    <section class="cards" aria-label="老板日常状态卡">
      <article class="status-card"><div class="label">当前能不能卖 <i class="dot" id="d-sale"></i></div><div class="value" id="v-sale">--</div><div class="desc" id="t-sale">读取中</div></article>
      <article class="status-card"><div class="label">自动发货 <i class="dot" id="d-auto"></i></div><div class="value" id="v-auto">--</div><div class="desc" id="t-auto">读取中</div></article>
      <article class="status-card"><div class="label">库存 <i class="dot" id="d-stock"></i></div><div class="value" id="v-stock">--</div><div class="desc" id="t-stock">读取中</div></article>
      <article class="status-card"><div class="label">上游余额 <i class="dot" id="d-balance"></i></div><div class="value" id="v-balance">--</div><div class="desc" id="t-balance">读取中</div></article>
      <article class="status-card"><div class="label">待处理订单 <i class="dot" id="d-pending"></i></div><div class="value" id="v-pending">--</div><div class="desc" id="t-pending">读取中</div></article>
      <article class="status-card"><div class="label">正式售卖资格 <i class="dot" id="d-public"></i></div><div class="value" id="v-public">--</div><div class="desc" id="t-public">读取中</div></article>
    </section>

    <section class="drawers">
      <details class="card layui-card drawer" id="precheck-drawer">
        <summary>人工预检证据 <span id="precheck-summary">CF、邮箱、重复发卡、自动发货、1:1 额度、严格门</span></summary>
        <div class="body">
          <div class="item" style="margin-bottom:12px">
            <div class="kicker">当前结论</div>
            <div class="hint" id="precheck-state">读取中。这个区域只读，不发卡、不点击闲鱼发货、不恢复自动发货。</div>
          </div>
          <div class="list" id="precheck-evidence"></div>
        </div>
      </details>

      <details class="card layui-card drawer">
        <summary>商品绑定 <span>多商品售卖前必须绑定，避免发错套餐</span></summary>
        <div class="body grid-2">
          <div>
            <div class="field"><label for="item-input">闲鱼商品链接或商品 ID</label><input id="item-input" placeholder="可粘贴完整闲鱼分享文本、短链接或 itemId=123456"></div>
            <div class="field"><label for="plan-input">套餐 / planId</label><input id="plan-input" placeholder="例如 xianyu-test-1"></div>
            <div class="field"><label for="title-input">老板备注</label><input id="title-input" placeholder="例如 1 元测试商品"></div>
            <div class="row"><button class="primary" data-action="save-mapping" type="button">保存绑定</button><button data-action="generate-template" type="button">生成商品模板</button></div>
          </div>
          <div class="list" id="mappings"></div>
        </div>
      </details>

      <details class="card layui-card drawer" id="rescue-drawer">
        <summary>已付款漏单兜底 <span>只在闲鱼已显示付款，但系统没自动发时使用</span></summary>
        <div class="body grid-2">
          <div>
            <p class="hint">这不是砍价、刷单或群发。它只给当前已付款测试单生成一次发货话术。</p>
            <div class="field"><label for="manual-buyer-input">买家/截图备注</label><input id="manual-buyer-input" placeholder="例如 手机截图已付款"></div>
            <div class="field"><label for="manual-proof-input">订单号或付款备注</label><input id="manual-proof-input" placeholder="有订单号填订单号；没有就填时间，例如 05:55 已付款截图"></div>
            <div class="row"><button class="danger" data-action="manual-dispatch" type="button">确认已付款，生成话术</button><button data-action="copy-manual-delivery" type="button">复制话术</button><button data-action="mark-manual-sent" type="button">已手动发送</button></div>
          </div>
          <div>
            <textarea id="manual-delivery-output" readonly placeholder="生成后这里会出现发货话术。复制到闲鱼聊天发出，再点“已手动发送”。"></textarea>
            <div class="hint" id="manual-dispatch-result" style="margin-top:10px">安全要求：只有页面或截图明确显示已付款时才用。</div>
          </div>
        </div>
      </details>

      <details class="card layui-card drawer" id="paid-probe-drawer">
        <summary>真实待发货扫单 <span>只读查看，不发卡、不点击发货</span></summary>
        <div class="body grid-2">
          <div>
            <p class="hint">如果你已经重新下单，但严格门还没看到真实单，先点这里。它只读取闲鱼卖家“待发货”列表，不会给买家发消息。</p>
            <div class="row"><button class="layui-btn layui-btn-normal" data-action="probe-paid-orders" type="button">只读扫真实待发货订单</button></div>
          </div>
          <div class="item"><div class="kicker">扫单结果</div><div class="hint" id="paid-probe-result">等待操作。看到 1 条目标订单后，再单次放行发货。</div></div>
        </div>
      </details>

      <details class="card layui-card drawer" id="queue-drawer">
        <summary>补救队列 <span>正常应该为空；有内容才需要处理</span></summary>
        <div class="body"><div class="list" id="shipments"></div></div>
      </details>

      <details class="card layui-card drawer" id="audit-drawer">
        <summary>商品模板与巡检 <span>只读巡检不会发货、不会扣卡密</span></summary>
        <div class="body grid-2">
          <div>
            <textarea id="product-template" readonly placeholder="点击生成商品模板"></textarea>
            <div class="row" style="margin-top:12px"><button data-action="copy-template" type="button">复制模板</button><button data-action="run-readiness" data-mode="read_only" type="button">运行内测巡检</button><button data-action="run-readiness" data-mode="strict" type="button">运行正式售卖严格门</button></div>
          </div>
          <div class="item"><div class="kicker">巡检结果</div><p class="hint" id="audit-result">等待操作。正式售卖严格门必须等新的真实闲鱼自动订单。</p></div>
        </div>
      </details>

      <details class="card layui-card drawer">
        <summary>替换模式模拟验收 <span>买家号暂不可用时，只演练流程，不解锁正式售卖</span></summary>
        <div class="body grid-2">
          <div>
            <p class="hint">这套清单对应：模拟下单 → 发卡 → 确认发货 → 发布商品 → 公网注册 → 兑换 → 创建 API → 导入 CC Switch → 终端调用。它不会替代真实 xy_oid_* 小额订单。</p>
            <div class="row"><button data-action="load-replacement" type="button">查看替换模式清单</button></div>
          </div>
          <div class="item"><div class="kicker">模拟验收结果</div><div class="hint" id="replacement-result">等待操作。</div></div>
        </div>
      </details>

      <details class="card layui-card drawer" id="help-drawer">
        <summary>帮助中心 <span>看不懂红灯时先看这里</span></summary>
        <div class="body">
          <div class="list">
            <div class="item"><b>红灯：补救队列不为空</b><div class="hint">1. 展开“补救队列”；2. 点“填入话术”；3. 复制到闲鱼并点“已手动发送”。</div></div>
            <div class="item"><b>黄灯：插件没有接管</b><div class="hint">1. 运行 make cc-seller-chrome；2. 打开 chrome://extensions；3. 加载运行版插件目录。</div></div>
            <div class="item"><b>无法自己处理</b><div class="hint">点右上角“导出状态报告”，把 JSON 发给技术支持。</div></div>
          </div>
        </div>
      </details>

      <details class="card layui-card drawer">
        <summary>高级排障 <span>工程信息默认折叠</span></summary>
        <div class="body">
          <div class="debug-grid" id="debug-grid"><div>读取中</div></div>
          <div id="raw-tables" style="margin-top:14px"></div>
        </div>
      </details>
    </section>
  </section>
</main>
<script src="/static/layui/layui.js"></script>
<script>
const $=id=>document.getElementById(id);
let layuiLayer=null,layuiElement=null;
if(window.layui){layui.use(['layer','element'],function(){layuiLayer=layui.layer;layuiElement=layui.element;layuiElement.render();});}
function notice(message,icon=1){if(layuiLayer)layuiLayer.msg(message,{icon,time:1800});else alert(message)}
function askConfirm(message,onYes){if(layuiLayer)layuiLayer.confirm(message,{title:'请确认'},function(index){layuiLayer.close(index);onYes();});else if(confirm(message))onYes();}
function askPrompt(message,defaultValue,onYes){if(layuiLayer)layuiLayer.prompt({title:message,value:defaultValue||'',formType:2},function(value,index){layuiLayer.close(index);onYes(value||'');});else onYes(prompt(message,defaultValue||'')||'');}
let manualShipmentId=0;
function escapeHtml(value){return String(value??'').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;').replaceAll("'",'&#39;')}
function element(tag,className='',text=null){const item=document.createElement(tag);if(className)item.className=className;if(text!==null)item.textContent=String(text);return item}
function actionButton(label,onClick,className=''){const item=element('button',className,label);item.type='button';item.addEventListener('click',onClick);return item}
function externalLink(label,href){const item=element('a','layui-btn layui-btn-xs layui-btn-primary',label);item.href=href;item.target='_blank';item.rel='noreferrer';return item}
function xianyuPageShortcutHtml(){const row=element('div','row');row.style.marginTop='10px';row.append(actionButton('打开卖家 Chromium 的闲鱼消息',()=>openSellerPage('im'),'layui-btn layui-btn-xs layui-btn-normal'),actionButton('打开卖家 Chromium 的工作台',()=>openSellerPage('seller'),'layui-btn layui-btn-xs layui-btn-primary'),externalLink('普通浏览器兜底','https://www.goofish.com/im?spm=a21ybx.seo.sitemap.3'),externalLink('工作台兜底','https://seller.goofish.com/'));return row}
function renderSellerScanMessage(message,showShortcuts=false){const target=$('one-shot-bridge-result');target.replaceChildren(document.createTextNode(String(message??'')));if(showShortcuts)target.append(xianyuPageShortcutHtml())}
async function saveToken(){const input=$('token-input'),token=input.value.trim(); if(!token)return; input.value=''; const response=await fetch('/api/session',{method:'POST',credentials:'same-origin',headers:{'X-API-Token':token}}); if(!response.ok)throw new Error(response.status===401?'missing-token':(await response.text()||('HTTP '+response.status))); await load(true)}
async function apiFetch(path,options={}){const request=Object.assign({},options,{credentials:'same-origin',headers:Object.assign({},options.headers||{})}); const response=await fetch(path,request); if(response.status===401)throw new Error('missing-token'); if(!response.ok)throw new Error(await response.text()||('HTTP '+response.status)); return response.json()}
async function exportStatusReport(){
  try{
    const data=await apiFetch('/api/export-status');
    const blob=new Blob([JSON.stringify(data,null,2)],{type:'application/json;charset=utf-8'});
    const url=URL.createObjectURL(blob);
    const a=document.createElement('a');
    a.href=url; a.download=`openeverything-status-${new Date().toISOString().slice(0,19).replaceAll(':','')}.json`;
    document.body.appendChild(a); a.click(); a.remove(); URL.revokeObjectURL(url);
  }catch(err){
    if(String(err.message||err)==='missing-token'){renderMissingToken();return}
    notice('状态报告导出失败：'+String(err.message||err),2);
  }
}
function kindClass(kind){return kind==='ok'?'ok':kind==='bad'?'bad':kind==='info'?'info':'warn'}
function setDot(id,kind){const el=$(id); el.className='dot '+kindClass(kind)}
function setCard(key,value,desc,kind){$('v-'+key).textContent=value; $('t-'+key).textContent=desc; setDot('d-'+key,kind)}
function pill(label,kind='warn'){const item=element('span','pill');item.append(element('i',`dot ${kindClass(kind)}`),document.createTextNode(String(label??'')));return item}
function extractItemId(value){const raw=String(value||'').trim(); const itemMatch=raw.match(/(?:itemId|item_id|id)=([A-Za-z0-9_-]+)/i); if(itemMatch)return itemMatch[1]; const nums=raw.match(/[0-9]{6,}/g); return nums?nums[nums.length-1]:raw}
function renderMissingToken(){ $('auth-box').classList.remove('hidden'); $('app-shell').classList.add('hidden'); }
function statusKind(ok, warn=false){return ok?'ok':(warn?'warn':'bad')}
function scrollToSection(id){const el=$(id); if(!el)return; if(el.tagName==='DETAILS')el.open=true; el.scrollIntoView({behavior:'smooth',block:'start'});}
function topAlert(kind,title,desc,...actions){const article=element('article',`top-alert ${kind}`);article.setAttribute('role','alert');const copy=element('div');copy.append(element('div','alert-title',title),element('div','alert-desc',desc));const actionBox=element('div','alert-actions');actionBox.append(...actions);article.append(copy,actionBox);return article}
function renderTopAlerts(ctx){
  const alerts=[];
  if(ctx.pendingRescue>0){alerts.push(topAlert('bad','有卡密没成功发给买家',`补救队列里还有 ${ctx.pendingRescue} 条待处理。先处理它，避免买家付款后收不到卡密。`,actionButton('怎么办',()=>scrollToSection('queue-drawer'),'layui-btn layui-btn-xs layui-btn-danger')));}
  if(ctx.confirmFailed>0){alerts.push(topAlert('bad','闲鱼确认发货失败',`有 ${ctx.confirmFailed} 条订单确认发货失败。先不要扩大售卖，查看补救队列里的失败原因。`,actionButton('查看失败',()=>scrollToSection('queue-drawer'),'layui-btn layui-btn-xs layui-btn-danger')));}
  if(ctx.pageConfirm>0){alerts.push(topAlert('warn','卡密已发，闲鱼还待确认发货',`有 ${ctx.pageConfirm} 条已发卡密记录还需要完成闲鱼发货状态。只在真实已付款页面处理。`,actionButton('去处理',()=>scrollToSection('queue-drawer'),'layui-btn layui-btn-xs layui-btn-warm')));}
  if(ctx.paused){
    const strictPaused=ctx.lockState==='paused_after_strict_gate';
    const pauseTitle=strictPaused?'严格门已通过，自动发货暂停保护':'自动发货仍处于暂停保护';
    const pauseDesc=ctx.oneShotActive?'现在只放行这一单，发完 1 条卡密会自动失效，不会连续刷屏。':(strictPaused?'现在不是系统故障，只是防重复发卡保护。你可以先点“恢复前安全检查”，通过后再恢复；恢复后第 1 单会自动暂停观察。':'为了避免重复发卡，新订单不会自动发卡。建议先用“只放行一次发卡”验证。');
    const pauseActions=strictPaused?[actionButton('恢复前安全检查',()=>checkResumePreflight(),'layui-btn layui-btn-xs layui-btn-normal'),actionButton('恢复自动发货',()=>setPause(false),'layui-btn layui-btn-xs layui-btn-warm')]:[actionButton('只放行一次',()=>authorizeOneShotDelivery(),'layui-btn layui-btn-xs layui-btn-warm'),actionButton('只读检查',()=>scanSellerPage(),'layui-btn layui-btn-xs')];
    alerts.push(topAlert('warn',pauseTitle,pauseDesc,...pauseActions));
  }
  if(!ctx.wsOk||!ctx.cookieOk){alerts.push(topAlert('bad','闲鱼登录或连接需要检查',`闲鱼连接：${ctx.wsOk?'在线':'离线'}；Cookie：${ctx.cookieOk?'正常':'异常'}。先打开卖家 Chromium，确认已登录闲鱼。`,actionButton('打开闲鱼消息',()=>openSellerPage('im'),'layui-btn layui-btn-xs layui-btn-danger')));}
  if(ctx.stockKnown&&ctx.stock<=0){alerts.push(topAlert('bad','可售卡密库存不足','库存为 0 时不要继续上架，否则买家付款后可能无法自动发卡。',actionButton('运行巡检',()=>scrollToSection('audit-drawer'),'layui-btn layui-btn-xs layui-btn-danger')));}
  if(!ctx.publicReady&&ctx.internalReady&&!ctx.paused&&alerts.length===0){alerts.push(topAlert('warn','还没到正式放量状态','当前可以生产内测，但正式售卖还需要真实小额单严格门证据。',actionButton('跑严格门',()=>runReadinessAudit('strict'),'layui-btn layui-btn-xs layui-btn-warm')));}
  const box=$('top-alerts');
  if(!alerts.length){box.classList.add('hidden');box.replaceChildren();return}
  box.classList.remove('hidden');
  box.replaceChildren(...alerts);
}
function mergeLockWithPrecheck(lock,precheck){
  const merged=Object.assign({},lock||{});
  if(precheck?.state==='paused_after_strict_gate'&&merged.can_public_sale!==true){
    merged.state='paused_after_strict_gate';
    merged.state_label=precheck.state_label||'严格门已通过，自动发货暂停保护';
    merged.can_internal_test=true;
  }
  return merged;
}
function renderPrecheck(precheck){
  const box=$('precheck-evidence'); if(!box)return;
  const list=Array.isArray(precheck?.items)?precheck.items:[];
  const passed=Number(precheck?.passed ?? list.filter(item=>item&&item.ok).length);
  const total=Number(precheck?.total ?? list.length);
  const ready=precheck?.precheck_ready===true;
  const label=precheck?.state_label||precheck?.state||'读取完成';
  $('precheck-summary').textContent=`${passed}/${total} 通过 · ${label}`;
  $('precheck-state').replaceChildren(element('b','',ready?'人工预检已通过':'还有预检项待处理'),document.createElement('br'),document.createTextNode(`${label}；这个区域只读，不发卡、不点击闲鱼发货、不恢复自动发货。`));
  if(!ready)$('precheck-drawer').open=true;
  if(!list.length){box.replaceChildren(element('div','empty','还没有人工预检证据。'));return}
  box.replaceChildren(...list.map(item=>{
    const ok=item&&item.ok===true;
    const card=element('div','item');
    const top=element('div','item-top');
    top.append(element('b','',`${ok?'✅':'⚠️'} ${item?.label||item?.key||'预检项'}`),element('span',ok?'ok':'warn',ok?'已通过':'待处理'));
    card.append(top,element('div','hint',item?.evidence||''));
    if(!ok)card.append(element('div','hint',`下一步：${item?.next_action||'按提示处理'}`));
    return card;
  }));
}
function renderMode(mode,status,lock,snap){
  $('auth-box').classList.add('hidden'); $('app-shell').classList.remove('hidden');
  const auto=status.cc_auto_ship||{}, ship=status.cc_shipments||{}, inv=lock.inventory||{}, ext=status.cc_chrome_extension||{}, action=snap.next_action||{}, watch=snap.loop_watch||{};
  const paused=mode.auto_ship_paused===true || auto.paused===true;
  const oneShot=mode.one_shot_delivery||auto.one_shot_delivery||{};
  const oneShotActive=oneShot.active===true;
  const autoReady=mode.can_auto_ship_paid_orders===true || auto.operational===true;
  const internalReady=lock.can_internal_test===true;
  const publicReady=lock.can_public_sale===true;
  const strictPaused=lock.state==='paused_after_strict_gate';
  const pendingRescue=Number(ship.pending_rescue||0);
  const pageConfirm=Number(ship.xianyu_confirm_page_pending||0);
  const confirmFailed=Number(ship.xianyu_confirm_failed||0);
  const stockKnown=inv.unused_cards!==null && inv.unused_cards!==undefined;
  const stock=stockKnown?Number(inv.unused_cards||0):0;
  const redemptionsKnown=inv.redeem_available!==null && inv.redeem_available!==undefined;
  const redemptions=redemptionsKnown?Number(inv.redeem_available||0):0;
  const channelsKnown=inv.active_channels!==null && inv.active_channels!==undefined;
  const channels=channelsKnown?Number(inv.active_channels||0):0;
  const audit=status.cc_readiness_audit?.last||{};
  const balanceKnown=Boolean(audit.updated_at || inv.updated_at);
  const balanceOk=Boolean(audit.oracle || lock.gates?.inventory_known);
  const wsOk=status.ws_connected===true;
  const cookieOk=status.cookie_ok===true;
  const needsHuman=paused || pendingRescue>0 || pageConfirm>0 || confirmFailed>0 || !autoReady || !internalReady || !wsOk || !cookieOk;
  renderTopAlerts({pendingRescue,pageConfirm,confirmFailed,paused,oneShotActive,wsOk,cookieOk,stockKnown,stock,publicReady,internalReady,lockState:lock.state});
  $('mode-kicker').textContent=publicReady?'正式售卖已放行':(strictPaused?'严格门已通过':(internalReady?'生产内测可继续':'需要先处理'));
  $('mode-word').textContent=paused?(oneShotActive?'已单次放行':(strictPaused?'待你恢复自动发货':'自动发货已暂停')):(publicReady?'可以正式小量卖':(internalReady?'可以生产内测':'先别上架'));
  $('mode-desc').textContent=paused?(oneShotActive?'只允许当前已付款页发送 1 条卡密，发完自动失效；常驻自动发货仍是暂停。':(strictPaused?'严格门、库存和渠道已经满足；当前只是暂停保护。点“恢复前安全检查”，确认通过后再恢复，首单发出后会自动暂停观察。':'系统不会自动发卡。恢复前先确认库存和闲鱼商品状态。')):(action.primary_action || lock.next_action || mode.next_action || '继续观察。');
  $('mode-pills').replaceChildren(
    pill(autoReady&&!paused?'自动发货开着':paused?'自动发货暂停':'自动发货待处理',autoReady&&!paused?'ok':'warn'),
    pill(oneShotActive?'单次放行有效':'单次放行关闭',oneShotActive?'warn':'ok'),
    pill(stockKnown?`库存 ${stock||0} 张`:'库存待刷新',stockKnown?(stock>0?'ok':'bad'):'warn'),
    pill(`补救 ${pendingRescue}`,pendingRescue===0?'ok':'bad'),
    pill(pageConfirm>0?`待点发货 ${pageConfirm}`:'发货按钮无待处理',pageConfirm>0?'warn':'ok'),
    pill(publicReady?'正式门通过':'正式门锁定',publicReady?'ok':'warn')
  );
  $('orb-text').textContent=needsHuman?'介入':'看守';
  $('status-orb').style.setProperty('--orb', needsHuman?'38%':'82%');
  if(pageConfirm>0){
    $('intervention-title').textContent='打开已付款测试单页面';
    $('intervention-desc').textContent='这条已发卡密的内测单可以继续走后半段：保持卖家 Chromium 打开对应闲鱼页，桥接器只有看到“已付款/待发货”才会点击发货。';
  }else if(pendingRescue>0){
    $('intervention-title').textContent='处理补救队列';
    $('intervention-desc').textContent='有卡密已分配但闲鱼消息未成功发送。展开补救队列，先让浏览器助手或人工补发。';
  }else if(paused){
    $('intervention-title').textContent=oneShotActive?'现在只允许发这一单':(strictPaused?'可恢复，先做安全检查':'如要继续卖，不建议直接恢复');
    $('intervention-desc').textContent=oneShotActive?'打开真实已付款聊天/订单页并运行一次卖家桥接器；发送 1 条卡密后会自动失效，不会连续发两条。':(strictPaused?'严格门已通过。建议先点“恢复前安全检查”；恢复后第 1 单发卡成功会自动暂停，方便你观察。':'建议先点“只放行一次发卡”跑当前测试单；确认安全后再考虑恢复自动发货。');
  }else if(!autoReady){
    $('intervention-title').textContent='自动发货需要检查';
    $('intervention-desc').textContent=mode.next_action||'先不要上架，等自动发货恢复正常。';
  }else if(!publicReady){
    $('intervention-title').textContent='只差真实小额单严格门';
    $('intervention-desc').textContent='当前可以生产内测；正式放量前，必须再跑一笔新的真实闲鱼自动付款订单。';
  }else{
    $('intervention-title').textContent='不用介入，保持看守';
    $('intervention-desc').textContent='继续观察库存、余额提醒和待处理订单。';
  }
  setCard('sale',publicReady?'正式可卖':strictPaused?'待恢复':'先别卖',publicReady?'严格门通过':lock.state_label||'看下一步',publicReady||strictPaused?'ok':'bad');
  setCard('auto',paused?'暂停':autoReady?'开着':'检查',`闲鱼 ${status.ws_connected?'在线':'离线'} · Cookie ${status.cookie_ok?'正常':'异常'}`,paused?'warn':statusKind(autoReady));
  $('one-shot-hint').textContent=oneShotActive?`单次放行有效，过期时间：${oneShot.expires_at||'约 3 分钟内'}。发完 1 条会自动关闭。`:'单次放行关闭：暂停状态下不会给浏览器返回卡密。';
  setCard('stock',stockKnown?(stock?`${stock} 张`:'不足'):'未刷新',stockKnown?`${redemptions} 个兑换码 · ${channels} 个渠道`:'点击刷新跑只读巡检',stockKnown?(stock>0&&redemptions>0&&channels>0?'ok':'bad'):'warn');
  setCard('balance',balanceKnown?(balanceOk?'已同步':'待确认'):'未知','每天同步；低于 50 元提醒，低于 20 元严重提醒',balanceKnown?(balanceOk?'ok':'warn'):'warn');
  setCard('pending',String(pendingRescue+pageConfirm+confirmFailed),`补救 ${pendingRescue} · 待点发货 ${pageConfirm} · 失败 ${confirmFailed}`,(pendingRescue+pageConfirm+confirmFailed)===0?'ok':'warn');
  setCard('public',publicReady?'已通过':strictPaused?'待恢复':'未放量',strictPaused?'严格门已过，等待恢复自动发货':(watch.stage_label||'等待真实订单'),publicReady||strictPaused?'ok':'warn');
  if(pendingRescue>0) $('queue-drawer').open=true;
  if(pageConfirm>0) $('rescue-drawer').open=true;
}
function renderMappings(list){
  const target=$('mappings');
  if(!Array.isArray(list)||!list.length){target.replaceChildren(element('div','empty','还没有商品绑定。单商品可用默认套餐，多商品必须绑定。'));return}
  target.replaceChildren(...list.map(m=>{
    const card=element('div','item');
    const top=element('div','item-top');
    const details=element('div');
    const itemHint=element('div','hint');
    itemHint.append(document.createTextNode('商品 '),element('span','mono',m.item_id||''));
    const planHint=element('div','hint');
    planHint.append(document.createTextNode('套餐 '),element('span','mono',m.plan_id||''));
    details.append(element('b','',m.title||'未命名商品'),itemHint,planHint);
    top.append(details,element('span','pill',m.enabled?'启用':'停用'));
    const actions=element('div','row');
    actions.style.marginTop='12px';
    actions.append(actionButton('填入编辑',()=>fillMapping(m.item_id||'',m.plan_id||'',m.title||'')),actionButton('删除',()=>deleteMapping(m.item_id||'')));
    card.append(top,actions);
    return card;
  }));
}
function renderShipments(list){
  const failed=(Array.isArray(list)?list:[]).filter(s=>['browser_delivery_claimed','message_send_inflight','message_send_uncertain','manual_delivery_ready','message_send_failed','webhook_failed','missing_delivery_message','exception','operator_paused'].includes(String(s.status||'')));
  const pagePending=(Array.isArray(list)?list:[]).filter(s=>String(s.status||'')==='message_sent' && ['xy_manual_','xy_browser_'].some(p=>String(s.order_id||'').startsWith(p)) && !['confirmed','skipped'].includes(String(s.xianyu_confirm_status||'')));
  const rows=[...failed,...pagePending];
  const target=$('shipments');
  if(!rows.length){target.replaceChildren(element('div','empty','补救队列为空。正常运营时就应该这样。'));return}
  const body=rows.map(s=>{
    const id=Number(s.id)||0;
    const isPage=String(s.status||'')==='message_sent';
    const title=isPage?'已发卡密，待页面点击发货':String(s.status||'');
    const actionHint=isPage?'打开对应闲鱼已付款页面，桥接器会安全点击发货。':'复制或重试发送这条话术。';
    const canBackendConfirm=/^[0-9]{10,}$/.test(String(s.order_id||'')) && isPage;
    const row=element('tr');
    const statusCell=element('td');
    statusCell.append(element('b','',title),element('div','hint',actionHint));
    const orderCell=element('td');orderCell.append(element('span','mono',s.order_id||''));
    const actions=element('div','row');
    if(!isPage)actions.append(actionButton('填入话术',()=>loadShipmentMessage(id,String(s.delivery_message||'')),'layui-btn layui-btn-xs'),actionButton('已手动发送',()=>markShipmentSent(id),'layui-btn layui-btn-xs layui-btn-normal'),actionButton('重试发送',()=>resendShipment(id),'layui-btn layui-btn-xs'));
    if(canBackendConfirm)actions.append(actionButton('后端确认发货',()=>confirmShipmentBackend(id),'layui-btn layui-btn-xs layui-btn-warm'));
    actions.append(actionButton('标记已处理',()=>resolveShipment(id),'layui-btn layui-btn-xs layui-btn-primary'));
    const actionCell=element('td');actionCell.append(actions);
    row.append(statusCell,orderCell,element('td','',s.item_id||''),actionCell);
    return row;
  });
  const header=element('tr');['状态','订单','商品','怎么办'].forEach(label=>header.append(element('th','',label)));
  const table=element('table','layui-table');const head=element('thead');head.append(header);const tbody=element('tbody');tbody.append(...body);table.append(head,tbody);
  const view=element('div','layui-table-view');view.append(table);target.replaceChildren(view);
}
function fillMapping(item,plan,title){$('item-input').value=item;$('plan-input').value=plan;$('title-input').value=title}
async function saveMapping(){const payload={item_id:extractItemId($('item-input').value),plan_id:$('plan-input').value.trim(),title:$('title-input').value.trim(),enabled:true}; if(!payload.item_id||!payload.plan_id){notice('请填写商品 ID 和套餐 planId',2);return} await apiFetch('/api/cc-item-mappings',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify(payload)}); await load(true)}
async function manualDispatch(){const payload={item_id:$('item-input').value.trim(),plan_id:$('plan-input').value.trim(),product_title:$('title-input').value.trim()||'CC中转内测卡',buyer_hint:$('manual-buyer-input').value.trim()||'手机截图已付款',proof_note:$('manual-proof-input').value.trim()}; if(!payload.item_id){notice('请先在商品绑定里填闲鱼商品链接或商品 ID',2);return} askConfirm('只在闲鱼已显示“我已付款，等待你发货”时使用。确认生成真实兑换码？',async()=>{ $('manual-dispatch-result').textContent='正在生成发货话术...'; const data=await apiFetch('/api/cc-manual-paid-order/dispatch',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify(payload)}); manualShipmentId=Number(data.shipmentId||0); $('manual-delivery-output').value=data.deliveryMessage||''; $('manual-dispatch-result').textContent=(data.idempotent?'已读取已有话术：':'已生成话术：')+'可由浏览器助手发送；人工兜底时复制到闲鱼聊天。'; await load(true)})}
async function copyManualDelivery(){const value=$('manual-delivery-output').value; if(!value){notice('还没有发货话术',2);return} await navigator.clipboard.writeText(value); $('manual-dispatch-result').textContent='已复制。请粘贴到闲鱼聊天并发送。'}
async function markManualSent(){if(!manualShipmentId){notice('请先生成或从队列填入发货话术',2);return} askConfirm('确认你已经把话术粘贴到闲鱼并发送给买家？',async()=>{ await apiFetch(`/api/cc-shipments/${manualShipmentId}/mark-sent`,{method:'POST'}); $('manual-dispatch-result').textContent='已标记为已发货，等待买家兑换和调模型。'; await load(true)})}
function loadShipmentMessage(id,message){manualShipmentId=Number(id)||0; $('manual-delivery-output').value=message||''; $('manual-dispatch-result').textContent='已从补救队列填入话术。复制并发送后点“已手动发送”。'; $('rescue-drawer').open=true; window.scrollTo({top:$('rescue-drawer').offsetTop-20,behavior:'smooth'});}
async function markShipmentSent(id){manualShipmentId=Number(id)||0; await markManualSent();}
async function deleteMapping(itemId){askConfirm('删除这个商品绑定？',async()=>{ await apiFetch(`/api/cc-item-mappings/${encodeURIComponent(itemId)}`,{method:'DELETE'}); await load(true)})}
function explainApiError(err){
  const raw=String(err&&err.message?err.message:err);
  try{
    const parsed=JSON.parse(raw);
    const detail=parsed.detail||parsed;
    if(detail.nextAction)return String(detail.nextAction);
    if(Array.isArray(detail.blockers)&&detail.blockers.length)return String(detail.blockers[0]);
    if(typeof detail==='string')return detail;
  }catch(_err){}
  return raw;
}
async function setPause(paused){
  const reason=paused?'老板手动暂停售卖':'老板手动恢复售卖';
  const action=async()=>{
    try{
      const data=await apiFetch('/api/cc-operator-mode',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({auto_ship_paused:paused,reason})});
      notice(paused?'已暂停自动发货':'已通过预检，自动发货已恢复',paused?0:1);
      if(!paused&&data.resume_preflight){$('one-shot-bridge-result').textContent=(data.resume_preflight.nextAction||'已恢复自动发货，请先小流量观察。')+' 系统已开启首单观察：第 1 单发卡成功后会自动暂停。'}
      await load(true);
    }catch(err){
      const message=explainApiError(err);
      $('one-shot-bridge-result').textContent=(paused?'暂停失败：':'恢复前预检未通过：')+message;
      notice(paused?'暂停失败':'恢复前预检未通过',2);
    }
  };
  if(paused){await action();return}
  askConfirm('恢复后，新已付款订单会自动发卡。系统会先检查严格门、库存、补救队列和闲鱼登录状态；不安全会拒绝恢复。确认继续？',action);
}
async function authorizeOneShotDelivery(){askConfirm('确认只放行一次？系统仍保持暂停，只允许当前已付款页发送 1 条卡密，3 分钟后自动失效。',async()=>{const data=await apiFetch('/api/cc-operator-mode/one-shot-delivery',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({reason:'老板在 18800 操作台点击只放行一次发卡',ttl_seconds:180})}); notice(data.nextAction||'已开启单次放行',1); await load(true)})}
async function checkResumePreflight(){
  try{
    const data=await apiFetch('/api/cc-operator-mode/resume-preflight');
    const blockers=Array.isArray(data.blockers)?data.blockers:[];
    if(data.ok){
      $('one-shot-bridge-result').textContent=data.nextAction||'恢复前安全检查通过，可以点“恢复自动发货”；恢复后请先小流量观察。';
      notice('恢复前安全检查通过',1);
    }else{
      const target=$('one-shot-bridge-result');
      target.replaceChildren(document.createTextNode('恢复前安全检查未通过：'+String(data.nextAction||blockers[0]||'还有红色项未处理')));
      if(blockers.length){const list=element('div','list');list.style.marginTop='10px';list.append(...blockers.map(blocker=>element('div','item',blocker)));target.append(list)}
      notice('恢复前安全检查未通过',2);
    }
  }catch(err){
    $('one-shot-bridge-result').textContent='恢复前安全检查失败：'+explainApiError(err);
    notice('恢复前安全检查失败',2);
  }
}
async function openSellerPage(destination){
  const label=destination==='seller'?'卖家工作台':'闲鱼消息';
  try{
    renderSellerScanMessage(`正在让卖家 Chromium 打开${label}...`,false);
    const data=await apiFetch('/api/cc-seller-bridge/open-page',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({destination,reason:'老板在 18800 操作台打开卖家页面'})});
    renderSellerScanMessage(data.nextAction||`已让卖家 Chromium 打开${label}。请找到已付款买家后再点只读检查。`,false);
    notice(data.ok?`已打开${label}`:`没有成功打开${label}`,data.ok?1:2);
  }catch(err){
    renderSellerScanMessage(`没有成功打开${label}：${String(err.message||err)}。你也可以点“普通浏览器兜底”手动打开。`,true);
    notice('打开卖家页面失败',2);
  }
}
async function scanSellerPage(){
  try{
    $('one-shot-bridge-result').textContent='正在只读检查卖家 Chromium 当前闲鱼页...';
    const data=await apiFetch('/api/cc-seller-bridge/page-scan');
    const scans=data.scans||[];
    const first=scans[0]||{};
    if(data.xianyuTabs!==1){
      renderSellerScanMessage(data.nextAction||`现在打开了 ${data.xianyuTabs||0} 个闲鱼页，请只保留 1 个真实已付款页。`,true);
      notice('闲鱼页数量不对',2);
      return;
    }
    if(first.strictReadyToSend){
      $('one-shot-bridge-result').textContent='只读检查通过：当前页已看到付款信号、输入框和真实订单号，可以点“一键跑当前页”。';
      notice('当前页可以发 1 条卡密',1);
      return;
    }
    if(first.readyToSend&&!first.orderIdHintPresent){
      renderSellerScanMessage(data.nextAction||'只读检查未通过：看到了付款信号和输入框，但没识别到订单号。请打开订单详情页，或聊天页里带“订单号/交易号”的页面。',true);
      notice('缺少订单号',2);
      return;
    }
    const nextMessage=data.nextAction||first.reason||'当前页不是已付款聊天/订单页';
    renderSellerScanMessage(`只读检查未通过：${nextMessage}。`,true);
    notice('当前页还不能发卡',0);
  }catch(err){
    $('one-shot-bridge-result').textContent='只读检查失败：'+String(err.message||err);
    notice('只读检查失败',2);
  }
}
async function runOneShotBridge(){askConfirm('确认一键跑当前页？请只保留 1 个真实已付款的闲鱼买家聊天/订单页，并确保页面能看到订单号/交易号。系统最多发送 1 条卡密，不点击闲鱼发货按钮。',async()=>{ $('one-shot-bridge-result').textContent='正在扫描当前闲鱼页...'; const data=await apiFetch('/api/cc-seller-bridge/one-shot-delivery',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({reason:'老板在 18800 操作台一键跑当前页'})}); const deliveries=data.deliveries||[]; const sent=deliveries.find(d=>d&&d.ok&&d.stage==='sent'); const skipped=deliveries.find(d=>d&&d.skipped); const failed=deliveries.find(d=>d&&!d.ok); if(sent){$('one-shot-bridge-result').textContent=`已发送 1 条卡密，记录 ID：${sent.shipmentId||''}。下一步让买家兑换、创建 API Key、调模型。`; notice('已发送 1 条卡密',1)}else if(String(data.error||'').includes('one_shot_requires_exactly_one_xianyu_page')){$('one-shot-bridge-result').textContent=data.nextAction||'为避免发错买家，请只保留 1 个真实已付款闲鱼页再点。'; notice('请只保留 1 个闲鱼页',2)}else if(skipped&&skipped.reason==='real_order_id_missing'){$('one-shot-bridge-result').textContent=skipped.nextAction||'当前页没有识别到订单号/交易号，为了通过正式严格门，本次不发卡。'; notice('缺少订单号，未发卡',2)}else if(skipped){$('one-shot-bridge-result').textContent=`未发送：${skipped.reason||'当前页不是已付款聊天页'}。请打开真实已付款聊天页后再点。`; notice('当前页未命中已付款信号',0)}else if(failed){$('one-shot-bridge-result').textContent=`执行失败：${failed.error||data.error||'未知错误'}`; notice('一键跑当前页失败',2)}else{$('one-shot-bridge-result').textContent=`未发送：${data.error||'没有找到可发送目标页'}`; notice('没有发送卡密',0)} await load(true)})}
async function resendShipment(id){if(!id)return; await apiFetch(`/api/cc-shipments/${id}/resend`,{method:'POST'}); await load(true)}
async function confirmShipmentBackend(id){if(!id)return; askConfirm('只对真实闲鱼数字订单使用。确认用后端 H5 接口尝试发货？',async()=>{ const data=await apiFetch(`/api/cc-shipments/${id}/confirm-xianyu-backend`,{method:'POST'}); notice(data.ok?'后端确认发货已完成':(data.nextAction||data.error||'后端确认发货未执行'),data.ok?1:2); await load(true)})}
async function resolveShipment(id){if(!id)return; askPrompt('处理备注，可空','已人工处理',async(note)=>{ await apiFetch(`/api/cc-shipments/${id}/resolve`,{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({note})}); await load(true)})}
async function generateProductTemplate(){const params=new URLSearchParams({title:$('title-input').value||'CC中转内测卡',plan_id:$('plan-input').value||'',price:'小额测试价'}); const data=await apiFetch(`/api/cc-product-template?${params.toString()}`); $('product-template').value=data.template||''}
async function copyProductTemplate(){if(!$('product-template').value){await generateProductTemplate()} await navigator.clipboard.writeText($('product-template').value); notice('已复制')}
async function runReadinessAudit(mode){$('audit-result').textContent='巡检运行中...'; try{const data=await apiFetch(`/api/cc-readiness-audit?mode=${encodeURIComponent(mode)}`); const s=data.summary||{}; $('audit-result').textContent=`${mode==='strict'?'正式售卖严格门':'生产内测巡检'}：${data.ok?'通过':'未通过'}；库存 ${s.redeem_available??0}；渠道 ${s.sub2api_active_channels??0}/10；监控 ${s.sub2api_enabled_monitors??0}/10；真实订单 ${s.real_orders??0}`; await load(true)}catch(err){$('audit-result').textContent='巡检失败：'+(err.message||err)}}
async function probePaidOrders(){
  $('paid-probe-result').textContent='正在只读扫描闲鱼待发货订单...';
  try{
    const data=await apiFetch('/api/cc-paid-order-probe');
    const candidates=Array.isArray(data.candidates)?data.candidates:[];
    const rows=candidates.map((c,idx)=>{const card=element('div','item');card.append(element('b','',`${idx+1}. ${c.statusText||'待发货订单'}`),element('div','hint',`订单：${c.order?.prefix||'未知'} / ${c.order?.hash||''}`),element('div','hint',`商品：${c.item?.present?'已识别':'未识别'}；买家：${c.buyer?.present?'已识别':'未识别'}；本机记录：${c.localShipmentStatus||'none'}`));return card});
    const list=element('div','list');list.style.marginTop='12px';list.append(...(rows.length?rows:[element('div','empty','没有候选订单。请确认闲鱼订单仍显示待发货。')]));
    $('paid-probe-result').replaceChildren(element('b','',candidates.length?`看到 ${candidates.length} 条真实待发货候选`:'暂未看到真实待发货订单'),document.createElement('br'),document.createTextNode(String(data.nextAction||'只读扫描完成')),list);
  }catch(err){$('paid-probe-result').textContent='只读扫单失败：'+(err.message||err)}
}
async function loadReplacementPack(){
  try{
    const data=await apiFetch('/api/cc-replacement-mode-test-pack');
    const gate=data.simulation_gate||{};
    const steps=(gate.steps||[]).map(step=>{const card=element('div','item');card.append(element('b','',`${step.ok?'✅':'⚠️'} ${step.label||step.key||''}`),element('div','hint',step.evidence||''),element('div','hint',`下一步：${step.next_action||'继续观察'}`));return card});
    const excluded=(gate.excluded_steps||[]).map(step=>{const card=element('div','item');card.append(element('b','',`🔒 ${step.label||step.key||''}`),element('div','hint',step.evidence||''));return card});
    const list=element('div','list');list.style.marginTop='12px';list.append(...steps,...excluded);
    $('replacement-result').replaceChildren(element('b','',gate.simulation_gate_ok?'严格模拟门已跑通':'严格模拟门未跑通'),document.createElement('br'),document.createTextNode(String(gate.owner_warning||data.owner_warning||'替换模式不解锁正式售卖。')),document.createElement('br'),document.createTextNode(`当前队列：补救 ${data.current_queue?.pending_rescue??0}，已发 ${data.current_queue?.message_sent??0}。`),list);
  }catch(err){$('replacement-result').textContent='读取失败：'+(err.message||err)}
}
function renderDebug(status,lock,items,mode){
  const auto=status.cc_auto_ship||{}, ship=status.cc_shipments||{}, map=status.cc_item_mappings||{}, inv=lock.inventory||{}, ext=status.cc_chrome_extension||{};
  const metrics=[['闲鱼连接',status.ws_connected?'在线':'离线'],['Cookie',status.cookie_ok?'正常':'异常'],['自动发货',auto.paused?'暂停':(auto.operational?'运行':'待处理')],['补救队列',ship.pending_rescue??0],['待点发货',ship.xianyu_confirm_page_pending??0],['商品映射',`${map.enabled??mode.enabled_item_mappings??0}/${map.total??mode.total_item_mappings??0}`],['库存',`${inv.unused_cards??'未知'} 张`],['桥接器',ext.needs_refresh_for_global_watch?'需刷新/打开弹窗':(ext.manifest_version||'未知')]];
  $('debug-grid').replaceChildren(...metrics.map(([label,value])=>{const card=element('div');card.append(element('b','',label),document.createElement('br'),document.createTextNode(String(value??'')));return card}));
  const target=$('raw-tables');
  if(!Array.isArray(items)||!items.length){target.replaceChildren();return}
  const table=element('table');const header=element('tr');['最近商品','价格','更新时间'].forEach(label=>header.append(element('th','',label)));table.append(header);
  items.slice(0,8).forEach(item=>{const row=element('tr');row.append(element('td','',item.title||item.item_id||''),element('td','',item.price||''),element('td','',item.updated||''));table.append(row)});
  target.replaceChildren(table);
}
async function load(refresh=false){
  try{
    const snapshotPath='/api/cc-ops-snapshot'+(refresh?'?refresh=true':'');
    const [snap,mode,status,mappings,shipments,lock,items,precheck]=await Promise.all([apiFetch(snapshotPath),apiFetch('/api/cc-operator-mode'),apiFetch('/api/status'),apiFetch('/api/cc-item-mappings'),apiFetch('/api/cc-shipments?limit=30&include_message=true'),apiFetch('/api/cc-public-sale-lock'),apiFetch('/api/items'),apiFetch('/api/cc-manual-precheck-evidence')]);
    const displayLock=mergeLockWithPrecheck(lock,precheck);
    renderMode(mode,status,displayLock,snap); renderMappings(mappings); renderShipments(shipments); renderDebug(status,displayLock,items,mode); renderPrecheck(precheck);
  }catch(err){ if(String(err.message||err)==='missing-token'){renderMissingToken();return} $('auth-box').classList.add('hidden'); $('app-shell').classList.remove('hidden'); $('mode-word').textContent='读取失败'; $('mode-desc').textContent=String(err.message||err); }
}
document.addEventListener('click',event=>{
  const control=event.target.closest('[data-action]');if(!control)return;
  const actions={
    'export-status':()=>exportStatusReport(),'refresh':()=>load(true),'save-token':()=>saveToken(),'set-pause':()=>setPause(control.dataset.paused==='true'),'authorize-one-shot':()=>authorizeOneShotDelivery(),'scan-seller':()=>scanSellerPage(),'run-one-shot':()=>runOneShotBridge(),'resume-preflight':()=>checkResumePreflight(),'open-seller':()=>openSellerPage(control.dataset.destination||'im'),'save-mapping':()=>saveMapping(),'generate-template':()=>generateProductTemplate(),'manual-dispatch':()=>manualDispatch(),'copy-manual-delivery':()=>copyManualDelivery(),'mark-manual-sent':()=>markManualSent(),'probe-paid-orders':()=>probePaidOrders(),'copy-template':()=>copyProductTemplate(),'run-readiness':()=>runReadinessAudit(control.dataset.mode||'read_only'),'load-replacement':()=>loadReplacementPack()
  };
  const action=actions[control.dataset.action];if(action)action();
});
window.addEventListener('load',()=>{load(false); setInterval(()=>load(false),60000)});
</script>
</body>
</html>"""
    return _secure_admin_html_response(html)


@app.get("/dashboard", response_class=HTMLResponse)
def owner_dashboard():
    """老板唯一收藏入口；内容复用本机操作台。"""
    return index()


def start_admin_server(
    ctx_manager,
    reply_bot=None,
    live_instance=None,
    host: str = "127.0.0.1",
    port: int = 18800,
):
    """启动闲鱼管理面板 (在独立线程中运行)"""
    global _ctx, _bot, _live
    _ctx = ctx_manager
    _bot = reply_bot
    _live = live_instance
    app.state.bind_host = str(host or "").strip()

    log_token_status()

    import uvicorn

    def _run():
        uvicorn.run(app, host=host, port=port, log_level="warning")

    t = threading.Thread(target=_run, daemon=True, name="xianyu-admin")
    t.start()
    _start_background_readiness_audit_loop()
    _start_background_strict_audit_loop()
    _start_background_ops_notify_loop()
    logger.info(f"[XianyuAdmin] 管理面板已启动: http://{host}:{port}")
    return t
