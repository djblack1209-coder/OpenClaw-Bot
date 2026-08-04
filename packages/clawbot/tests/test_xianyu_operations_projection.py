from copy import deepcopy
from types import MappingProxyType, SimpleNamespace

import pytest

from src.xianyu.operations_projection import project_operations


def test_project_operations_preserves_verified_runtime_contract():
    """严格门已通过时，一次纯投影应生成既有运营、观察和买家进度合同。"""
    strict_audit = {
        "ok": True,
        "same_order_ready": 1,
        "same_order_matched": 1,
        "summary": {
            "same_order_latest": [
                {
                    "orderIdPrefix": "xy_oid_demo",
                    "newApiRedeemed": True,
                    "activeTokens": 1,
                    "modelLogsAfterRedeem": 1,
                }
            ]
        },
    }
    snapshot = {
        "auto_ship": {"configured": True, "operational": True, "paused": False},
        "runtime": {"ws_connected": True, "cookie_ok": True, "manual_chats": 3},
        "shipments": {
            "pending_rescue": 0,
            "buyer_chain_verified": 1,
            "by_status": {},
            "latest": [{"id": 7, "status": "message_sent"}],
        },
        "sale_gate": {
            "local_ready": True,
            "sent_real_orders": 1,
            "latest": [{"order_id": "xy_oid_demo"}],
            "strict_audit_command": "node scripts/audit.mjs --strict",
            "buyer_chain_required": {"model_call": True},
        },
        "enabled_item_mappings": 2,
        "plan_routing": {
            "mode": "item_mapping_then_default",
            "label": "优先按商品映射发货；无映射时使用默认套餐",
            "risk": "low",
            "enabled_item_mappings": 2,
            "default_plan_id_present": True,
            "default_plan_id": "xianyu-test-1",
            "can_ship_unmapped_order": True,
        },
        "readiness_audit": {
            "public_main_http": 200,
            "public_models_no_auth_http": 401,
            "public_webhook_no_token_http": 401,
            "buyer_self_service_ok": True,
            "webhook_public_locked": True,
            "ccswitch_entry_ok": True,
            "ccswitch_entry_http": 200,
            "ccswitch_has_cc_switch_text": True,
            "ccswitch_has_ccswitch_marker": True,
            "ccswitch_has_import_link_marker": True,
        },
        "chrome_extension": {"online": True, "needs_refresh_for_global_watch": False},
        "strict_ready": True,
        "latest_strict_audit": strict_audit,
        "auto_strict_audit": {"enabled": True, "interval_ms": 600_000, "scan_seconds": 60},
        "last_background_strict_audit_at": 123.0,
        "last_background_strict_audit": {"ok": True},
    }
    original = deepcopy(snapshot)

    projection = project_operations(snapshot)

    assert snapshot == original
    assert projection == {
        "sale_readiness": {
            "automation_level": "生产内测自动发货可用",
            "can_auto_ship_paid_orders": True,
            "ready_for_public_sale": True,
            "checks": {
                "webhook_configured": True,
                "auto_ship_paused": False,
                "ws_connected": True,
                "cookie_ok": True,
                "pending_rescue": 0,
                "enabled_item_mappings": 2,
                "real_order_seen": True,
                "buyer_chain_verified_orders": 1,
                "ccswitch_import_ok": True,
            },
            "plan_routing": snapshot["plan_routing"],
            "chrome_extension": snapshot["chrome_extension"],
            "buyer_self_service": {
                "known": True,
                "ok": True,
                "main_http": 200,
                "models_no_auth_http": 401,
                "webhook_no_token_http": 401,
                "webhook_public_locked": True,
            },
            "ccswitch_import": {
                "known": True,
                "ok": True,
                "page_http": 200,
                "has_cc_switch_text": True,
                "has_ccswitch_marker": True,
                "has_import_link_marker": True,
            },
            "human_required": ["持续处理上游续费和库存补货"],
            "operator_addresses": {
                "user_site": "https://jiyu.245334.xyz/",
                "newapi_console": "https://jiyu.245334.xyz/console",
                "frist_health": "https://frist-api-oracle.245334.xyz/",
                "xianyu_gui": "http://127.0.0.1:18800/",
            },
            "manual_chats": 3,
            "last_strict_audit": strict_audit,
        },
        "loop_watch": {
            "stage": "closed_loop_verified",
            "stage_label": "实单闭环已通过",
            "next_action": "可以小批量继续内测，仍需观察库存、上游余额和补救队列",
            "auto_ready": True,
            "can_auto_ship_paid_orders": True,
            "ready_for_public_sale": True,
            "checks": {
                "webhook_configured": True,
                "auto_ship_paused": False,
                "ws_connected": True,
                "cookie_ok": True,
                "pending_rescue": 0,
                "manual_delivery_ready": 0,
                "sent_real_orders": 1,
                "enabled_item_mappings": 2,
                "buyer_chain_verified_orders": 1,
                "strict_buyer_chain_verified": True,
            },
            "latest_shipments": snapshot["shipments"]["latest"],
            "latest_gate": snapshot["sale_gate"]["latest"],
            "strict_audit_command": "node scripts/audit.mjs --strict",
            "buyer_chain_required": {"model_call": True},
            "last_strict_audit": strict_audit,
            "auto_strict_audit_enabled": True,
            "auto_strict_audit_interval_ms": 600_000,
            "background_strict_audit_enabled": True,
            "background_strict_audit_scan_seconds": 60,
            "last_background_strict_audit_at": 123.0,
            "last_background_strict_audit": {"ok": True},
        },
        "buyer_progress": {
            "stage": "verified",
            "next_action": "同一真实订单已完成发货、兑换、API Key 和模型调用。",
            "steps": {
                "paid_order_shipped": True,
                "card_redeemed": True,
                "api_key_created": True,
                "model_called": True,
                "same_order_verified": True,
            },
            "counts": {
                "sent_real_orders": 1,
                "buyer_chain_verified_orders": 1,
                "same_order_ready": 1,
                "same_order_matched": 1,
            },
            "latest_orders": strict_audit["summary"]["same_order_latest"],
            "last_strict_audit": strict_audit,
            "loop_stage": "closed_loop_verified",
        },
    }


def test_project_operations_fails_closed_for_paused_offline_rescue_snapshot():
    """暂停、离线且有补救单时，所有可售结论必须保持关闭。"""
    snapshot = MappingProxyType(
        {
            "auto_ship": MappingProxyType({"configured": True, "operational": False, "paused": True}),
            "runtime": MappingProxyType({"ws_connected": False, "cookie_ok": False, "manual_chats": 0}),
            "shipments": MappingProxyType(
                {
                    "pending_rescue": 2,
                    "buyer_chain_verified": 0,
                    "by_status": MappingProxyType({"manual_delivery_ready": 1}),
                    "latest": (),
                }
            ),
            "sale_gate": MappingProxyType({"sent_real_orders": 0, "latest": ()}),
            "enabled_item_mappings": 0,
            "plan_routing": MappingProxyType({"default_plan_id_present": False}),
            "chrome_extension": MappingProxyType({"needs_refresh_for_global_watch": True}),
            "strict_ready": False,
            "latest_strict_audit": MappingProxyType({}),
            "auto_strict_audit": MappingProxyType(
                {"enabled": True, "interval_ms": 600_000, "scan_seconds": 60}
            ),
        }
    )

    projection = project_operations(snapshot)

    readiness = projection["sale_readiness"]
    assert readiness["can_auto_ship_paid_orders"] is False
    assert readiness["ready_for_public_sale"] is False
    assert readiness["human_required"] == [
        "在操作台恢复自动发货",
        "保持闲鱼助手 WebSocket 在线",
        "闲鱼 Cookie 失效时扫码恢复",
        "处理发货补救队列",
        "配置默认套餐或商品套餐映射，避免无映射订单靠兜底发货",
        "刷新 Chrome 插件并打开一次弹窗，同步新版发货看守能力",
        "发布商品后跑 1 单小额真实付款，并完成兑换/API/调模型严格验收",
        "持续处理上游续费和库存补货",
    ]
    assert projection["loop_watch"]["stage"] == "operator_paused"
    assert projection["loop_watch"]["checks"]["pending_rescue"] == 2
    assert projection["buyer_progress"]["stage"] == "waiting_paid_order"


def test_project_operations_rejects_live_runtime_objects():
    """纯投影 seam 不接受 WebSocket、owner-loop 或其他有状态运行对象。"""
    with pytest.raises(TypeError, match="只接受普通快照值"):
        project_operations({"runtime": SimpleNamespace(ws_connected=True)})
