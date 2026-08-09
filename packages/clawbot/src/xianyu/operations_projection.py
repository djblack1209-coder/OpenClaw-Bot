"""把闲鱼运行快照投影为稳定的老板运营状态。"""

from collections.abc import Mapping


def _plain(value: object) -> object:
    """递归复制 JSON 形状数据，保证投影不会持有调用方的可变引用。"""
    if isinstance(value, Mapping):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise TypeError(f"运营投影只接受普通快照值，收到 {type(value).__name__}")


def _mapping(value: object) -> dict[str, object]:
    plain = _plain(value)
    return plain if isinstance(plain, dict) else {}


def _records(value: object) -> list[dict[str, object]]:
    plain = _plain(value)
    if not isinstance(plain, list):
        return []
    return [item for item in plain if isinstance(item, dict)]


def _project_sale_readiness(snapshot: Mapping[str, object]) -> dict[str, object]:
    auto = _mapping(snapshot.get("auto_ship"))
    runtime = _mapping(snapshot.get("runtime"))
    shipments = _mapping(snapshot.get("shipments"))
    gate = _mapping(snapshot.get("sale_gate"))
    routing = _mapping(snapshot.get("plan_routing"))
    readiness_audit = _mapping(snapshot.get("readiness_audit"))
    chrome_extension = _mapping(snapshot.get("chrome_extension"))
    latest_strict_audit = _mapping(snapshot.get("latest_strict_audit"))
    enabled_mappings = int(snapshot.get("enabled_item_mappings") or 0)
    pending_rescue = int(shipments.get("pending_rescue") or 0)
    buyer_chain_verified = int(shipments.get("buyer_chain_verified") or 0)
    ws_connected = bool(runtime.get("ws_connected"))
    cookie_ok = bool(runtime.get("cookie_ok"))
    manual_chats = max(0, int(runtime.get("manual_chats") or 0))
    buyer_self_service_known = bool(
        readiness_audit.get("public_main_http") or readiness_audit.get("public_models_no_auth_http")
    )
    buyer_self_service = {
        "known": buyer_self_service_known,
        "ok": bool(readiness_audit.get("buyer_self_service_ok")) if buyer_self_service_known else None,
        "main_http": readiness_audit.get("public_main_http") if buyer_self_service_known else None,
        "models_no_auth_http": readiness_audit.get("public_models_no_auth_http")
        if buyer_self_service_known
        else None,
        "webhook_no_token_http": readiness_audit.get("public_webhook_no_token_http")
        if buyer_self_service_known
        else None,
        "webhook_public_locked": readiness_audit.get("webhook_public_locked")
        if buyer_self_service_known
        else None,
    }
    ccswitch_import_known = ("ccswitch_entry_ok" in readiness_audit) or bool(
        readiness_audit.get("ccswitch_entry_http")
    )
    ccswitch_import = {
        "known": ccswitch_import_known,
        "ok": bool(readiness_audit.get("ccswitch_entry_ok")) if ccswitch_import_known else None,
        "page_http": readiness_audit.get("ccswitch_entry_http") if ccswitch_import_known else None,
        "has_cc_switch_text": readiness_audit.get("ccswitch_has_cc_switch_text")
        if ccswitch_import_known
        else None,
        "has_ccswitch_marker": readiness_audit.get("ccswitch_has_ccswitch_marker")
        if ccswitch_import_known
        else None,
        "has_import_link_marker": readiness_audit.get("ccswitch_has_import_link_marker")
        if ccswitch_import_known
        else None,
    }
    auto_operational = bool(auto.get("operational", auto.get("configured")) and not auto.get("paused"))
    can_auto_ship = bool(auto_operational and ws_connected and cookie_ok and pending_rescue == 0)
    strict_ready = bool(snapshot.get("strict_ready")) and pending_rescue == 0

    human_required = []
    if not auto.get("configured"):
        human_required.append("配置 CC中转自动发货 webhook")
    if auto.get("paused"):
        human_required.append("在操作台恢复自动发货")
    if not ws_connected:
        human_required.append("保持闲鱼助手 WebSocket 在线")
    if not cookie_ok:
        human_required.append("闲鱼 Cookie 失效时扫码恢复")
    if pending_rescue > 0:
        human_required.append("处理发货补救队列")
    if enabled_mappings == 0 and not routing.get("default_plan_id_present"):
        human_required.append("配置默认套餐或商品套餐映射，避免无映射订单靠兜底发货")
    if buyer_self_service_known and not buyer_self_service.get("ok"):
        human_required.append("修复买家主站或 API 网关公网入口")
    if buyer_self_service_known and buyer_self_service.get("webhook_public_locked") is False:
        human_required.append("修复闲鱼发货 webhook 未授权拦截")
    if ccswitch_import_known and not ccswitch_import.get("ok"):
        human_required.append("修复 CC Switch 导入入口")
    if pending_rescue > 0 and chrome_extension.get("needs_refresh_for_global_watch"):
        human_required.append("打开 OpenClaw 桌面端运营台处理待发货补救；首次使用先完成闲鱼登录")
    if not strict_ready:
        human_required.append("发布商品后跑 1 单小额真实付款，并完成兑换/API/调模型严格验收")
    human_required.append("持续处理上游续费和库存补货")

    return {
        "automation_level": "生产内测自动发货可用" if can_auto_ship else "需要先处理红色项",
        "can_auto_ship_paid_orders": can_auto_ship,
        "ready_for_public_sale": strict_ready,
        "checks": {
            "webhook_configured": bool(auto.get("configured")),
            "auto_ship_paused": bool(auto.get("paused")),
            "ws_connected": ws_connected,
            "cookie_ok": cookie_ok,
            "pending_rescue": pending_rescue,
            "enabled_item_mappings": enabled_mappings,
            "real_order_seen": bool(gate.get("local_ready")),
            "buyer_chain_verified_orders": buyer_chain_verified,
            "ccswitch_import_ok": ccswitch_import.get("ok"),
        },
        "plan_routing": routing,
        "chrome_extension": chrome_extension,
        "buyer_self_service": buyer_self_service,
        "ccswitch_import": ccswitch_import,
        "human_required": human_required,
        "operator_addresses": {
            "user_site": "https://jiyu.245334.xyz/",
            "jiyu_console": "https://jiyu.245334.xyz/admin/dashboard",
            "jiyu_health": "https://jiyu.245334.xyz/health",
            "xianyu_gui": "http://127.0.0.1:18800/",
        },
        "manual_chats": manual_chats,
        "last_strict_audit": latest_strict_audit,
    }


def _project_loop_watch(snapshot: Mapping[str, object]) -> dict[str, object]:
    auto = _mapping(snapshot.get("auto_ship"))
    runtime = _mapping(snapshot.get("runtime"))
    shipments = _mapping(snapshot.get("shipments"))
    gate = _mapping(snapshot.get("sale_gate"))
    latest_strict_audit = _mapping(snapshot.get("latest_strict_audit"))
    auto_strict = _mapping(snapshot.get("auto_strict_audit"))
    enabled_mappings = int(snapshot.get("enabled_item_mappings") or 0)
    ws_connected = bool(runtime.get("ws_connected"))
    cookie_ok = bool(runtime.get("cookie_ok"))
    pending_rescue = int(shipments.get("pending_rescue") or 0)
    by_status = _mapping(shipments.get("by_status"))
    manual_ready = int(by_status.get("manual_delivery_ready") or 0)
    buyer_chain_verified = int(shipments.get("buyer_chain_verified") or 0)
    sent_real_orders = int(gate.get("sent_real_orders") or 0)
    auto_operational = bool(auto.get("operational", auto.get("configured")) and not auto.get("paused"))
    auto_ready = bool(auto_operational and ws_connected and cookie_ok)
    strict_ready = bool(snapshot.get("strict_ready")) and pending_rescue == 0

    if auto.get("paused"):
        stage = "operator_paused"
        label = "自动发货已暂停"
        next_action = "需要继续售卖时，在本机操作台点“恢复自动发货”。"
    elif not auto.get("configured"):
        stage = "webhook_not_configured"
        label = "自动发货 webhook 未配置"
        next_action = "打开 OpenClaw 桌面端运营台检查自动发货配置；首次使用先完成闲鱼登录"
    elif not ws_connected:
        stage = "xianyu_ws_offline"
        label = "闲鱼 WebSocket 未在线"
        next_action = "打开 OpenClaw 桌面端运营台；首次使用完成闲鱼登录后系统会自动保持连接"
    elif not cookie_ok:
        stage = "xianyu_cookie_invalid"
        label = "闲鱼 Cookie 需要恢复"
        next_action = "打开 OpenClaw 桌面端运营台并重新完成闲鱼登录"
    elif pending_rescue > 0:
        stage = "rescue_required"
        label = "有发货补救待处理"
        next_action = (
            "打开 OpenClaw 桌面端运营台，在闲鱼买家聊天页确认并发送已分配话术。"
            if manual_ready > 0
            else "等待后台自动补发，或在补救队列点击重试发送/标记已处理"
        )
    elif sent_real_orders <= 0:
        stage = "waiting_paid_order"
        label = "等待真实已付款订单"
        next_action = "发布闲鱼商品并跑 1 单小额真实付款；系统会自动发卡"
    elif strict_ready:
        stage = "closed_loop_verified"
        label = "实单闭环已通过"
        next_action = "可以小批量继续内测，仍需观察库存、上游余额和补救队列"
    else:
        stage = "waiting_buyer_chain"
        label = "已自动发货，等待买家完成兑换/API/调模型严格闭环"
        next_action = "让买家按发货话术完成注册兑换、创建 API Key、CC Switch 导入和模型测试，然后运行正式售卖严格门"

    background_at = float(snapshot.get("last_background_strict_audit_at") or 0.0)
    return {
        "stage": stage,
        "stage_label": label,
        "next_action": next_action,
        "auto_ready": auto_ready,
        "can_auto_ship_paid_orders": bool(auto_ready and pending_rescue == 0),
        "ready_for_public_sale": strict_ready,
        "checks": {
            "webhook_configured": bool(auto.get("configured")),
            "auto_ship_paused": bool(auto.get("paused")),
            "ws_connected": ws_connected,
            "cookie_ok": cookie_ok,
            "pending_rescue": pending_rescue,
            "manual_delivery_ready": manual_ready,
            "sent_real_orders": sent_real_orders,
            "enabled_item_mappings": enabled_mappings,
            "buyer_chain_verified_orders": buyer_chain_verified,
            "strict_buyer_chain_verified": strict_ready,
        },
        "latest_shipments": _records(shipments.get("latest")),
        "latest_gate": _records(gate.get("latest")),
        "strict_audit_command": gate.get(
            "strict_audit_command",
            "node scripts/cc_zhongzhuan_readiness_audit.mjs --require-real-order",
        ),
        "buyer_chain_required": _mapping(gate.get("buyer_chain_required")),
        "last_strict_audit": latest_strict_audit,
        "auto_strict_audit_enabled": bool(auto_strict.get("enabled")),
        "auto_strict_audit_interval_ms": int(auto_strict.get("interval_ms") or 0),
        "background_strict_audit_enabled": bool(auto_strict.get("enabled")),
        "background_strict_audit_scan_seconds": int(auto_strict.get("scan_seconds") or 0),
        "last_background_strict_audit_at": background_at if background_at > 0 else None,
        "last_background_strict_audit": _mapping(snapshot.get("last_background_strict_audit")),
    }


def _project_buyer_progress(
    snapshot: Mapping[str, object],
    loop_watch: Mapping[str, object],
) -> dict[str, object]:
    latest_audit = _mapping(snapshot.get("latest_strict_audit"))
    audit_summary = _mapping(latest_audit.get("summary"))
    matches = _records(audit_summary.get("same_order_latest"))
    checks = _mapping(loop_watch.get("checks"))
    same_order_verified = bool(snapshot.get("strict_ready"))
    steps = {
        "paid_order_shipped": int(checks.get("sent_real_orders") or 0) > 0,
        "card_redeemed": any(bool(item.get("balanceRedeemed")) for item in matches),
        "api_key_created": any(int(item.get("activeTokens") or 0) > 0 for item in matches),
        "model_called": any(int(item.get("modelLogsAfterRedeem") or 0) > 0 for item in matches),
        "same_order_verified": same_order_verified,
    }
    if same_order_verified:
        steps["card_redeemed"] = True
        steps["api_key_created"] = True
        steps["model_called"] = True
    if not steps["paid_order_shipped"]:
        stage = "waiting_paid_order"
        next_action = "发布闲鱼商品并跑 1 单小额真实付款。"
    elif not latest_audit:
        stage = "waiting_strict_audit"
        next_action = "系统会自动运行严格门；也可在 GUI 点“运行正式售卖严格门”。"
    elif not steps["card_redeemed"]:
        stage = "waiting_redeem"
        next_action = "提醒买家打开兑换入口注册/登录并输入兑换码。"
    elif not steps["api_key_created"]:
        stage = "waiting_api_key"
        next_action = "提醒买家在用户主站创建 API Key。"
    elif not steps["model_called"]:
        stage = "waiting_model_call"
        next_action = "提醒买家导入 CC Switch 后选择模型测试一次。"
    elif steps["same_order_verified"]:
        stage = "verified"
        next_action = "同一真实订单已完成发货、兑换、API Key 和模型调用。"
    else:
        stage = "waiting_same_order_match"
        next_action = "已有部分买家行为，但严格门尚未确认属于同一真实订单；继续观察或重新运行严格门。"

    return {
        "stage": stage,
        "next_action": next_action,
        "steps": steps,
        "counts": {
            "sent_real_orders": int(checks.get("sent_real_orders") or 0),
            "buyer_chain_verified_orders": int(checks.get("buyer_chain_verified_orders") or 0),
            "same_order_ready": int(latest_audit.get("same_order_ready") or 0) if same_order_verified else 0,
            "same_order_matched": int(latest_audit.get("same_order_matched") or 0) if same_order_verified else 0,
        },
        "latest_orders": matches[:5],
        "last_strict_audit": latest_audit,
        "loop_stage": loop_watch.get("stage"),
    }


def project_operations(snapshot: Mapping[str, object]) -> dict[str, dict[str, object]]:
    """从一个普通只读快照生成所有运营投影，不执行 I/O 或访问运行对象。"""
    plain_snapshot = _mapping(snapshot)
    provided_loop_watch = plain_snapshot.get("loop_watch")
    loop_watch = (
        _mapping(provided_loop_watch) if isinstance(provided_loop_watch, Mapping) else _project_loop_watch(plain_snapshot)
    )
    return {
        "sale_readiness": _project_sale_readiness(plain_snapshot),
        "loop_watch": loop_watch,
        "buyer_progress": _project_buyer_progress(plain_snapshot, loop_watch),
    }
