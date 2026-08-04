"""CC中转闲鱼自动发货单元测试。"""

import asyncio
import base64
import hashlib
import json
import os
import sqlite3
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from src.core.loop_owner import OwnerLoopNotReady, OwnerLoopTimeout
from src.xianyu import cc_operator_state, xianyu_admin
from src.xianyu.cc_operator_state import (
    authorize_one_shot_delivery,
    consume_one_shot_delivery,
    get_operator_state,
    set_auto_ship_paused,
)
from src.xianyu.xianyu_apis import XianyuApis
from src.xianyu.xianyu_context import XianyuContextManager
from src.xianyu.xianyu_live import XianyuLive


class FakeResponse:
    def __init__(self, status_code: int, payload: dict):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


class FakeHttpxClient:
    calls: list[dict] = []
    response = FakeResponse(200, {})

    def __init__(self, timeout: float):
        self.timeout = timeout

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def post(self, url: str, json: dict, headers: dict):
        self.__class__.calls.append({"url": url, "json": json, "headers": headers, "timeout": self.timeout})
        return self.__class__.response


@pytest.fixture(autouse=True)
def clean_cc_xianyu_env(monkeypatch, tmp_path):
    for name in (
        "CC_XIANYU_AUTO_SHIP_ENABLED",
        "CC_XIANYU_WEBHOOK_URL",
        "CC_XIANYU_WEBHOOK_TOKEN",
        "CC_XIANYU_AUTO_SHIP_DELAY_SECONDS",
        "CC_XIANYU_DEFAULT_PLAN_ID",
        "CC_XIANYU_DEFAULT_ITEM_ID",
        "CC_XIANYU_AUTO_SHIP_PAUSED",
        "CC_XIANYU_AUTO_CONFIRM_SHIPMENT_ENABLED",
        "CC_XIANYU_AUTO_STRICT_AUDIT_ENABLED",
        "CC_XIANYU_AUTO_STRICT_AUDIT_INTERVAL_MS",
        "CC_XIANYU_AUTO_STRICT_AUDIT_SCAN_SECONDS",
        "CC_XIANYU_OPS_NOTIFY_ENABLED",
        "CC_XIANYU_OPS_NOTIFY_INTERVAL_MS",
        "CC_XIANYU_OPS_NOTIFY_SCAN_SECONDS",
        "CC_XIANYU_LOW_INVENTORY_THRESHOLD",
        "CC_XIANYU_OPS_NOTIFY_DRY_RUN",
        "FRIST_API_XIANYU_WEBHOOK_URL",
        "FRIST_API_XIANYU_WEBHOOK_TOKEN",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("CC_OPERATOR_STATE_FILE", str(tmp_path / "cc-operator-state.json"))
    monkeypatch.setenv("CC_XIANYU_AUTO_SHIP_PAUSED", "0")
    monkeypatch.setattr(xianyu_admin, "_last_ops_notify_signature", "", raising=False)
    monkeypatch.setattr(xianyu_admin, "_last_ops_notify_at", 0.0, raising=False)
    monkeypatch.setattr(xianyu_admin, "_last_ops_notify_result", {}, raising=False)


@pytest.fixture
def live():
    instance = object.__new__(XianyuLive)
    instance.ctx = SimpleNamespace(
        get_item=MagicMock(return_value={"title": "CC中转 月卡"}),
        get_cc_item_mapping=MagicMock(return_value=None),
        get_latest_chat_id=MagicMock(return_value="chat-buyer-001"),
    )
    instance.notifier = SimpleNamespace(
        notify_health=MagicMock(),
        notify_order=MagicMock(),
    )
    instance.ctx.record_cc_shipment = MagicMock()
    instance.ctx.get_cc_shipment_by_order_id = MagicMock(return_value=None)
    instance.ctx.claim_cc_auto_ship_order = MagicMock(
        side_effect=lambda order_id, buyer_id, item_id: {
            "id": 1,
            "order_id": order_id,
            "buyer_id": buyer_id,
            "item_id": item_id,
            "status": "webhook_inflight",
        }
    )
    instance.ctx.claim_cc_shipment_send = MagicMock(
        side_effect=lambda shipment_id, expected_statuses: (
            instance.ctx.get_cc_shipment(shipment_id, include_message=True)
            if instance.ctx.get_cc_shipment(shipment_id, include_message=True).get("status") in expected_statuses
            else None
        )
    )
    instance.ctx.complete_cc_shipment_send = MagicMock(return_value=True)
    instance.send_msg = AsyncMock()
    instance.myid = "seller-001"
    return instance


@pytest.fixture
def fake_httpx(monkeypatch):
    FakeHttpxClient.calls = []
    FakeHttpxClient.response = FakeResponse(200, {})
    monkeypatch.setitem(sys.modules, "httpx", SimpleNamespace(AsyncClient=FakeHttpxClient))
    return FakeHttpxClient


def configure_cc_webhook(monkeypatch):
    monkeypatch.setenv("CC_XIANYU_AUTO_SHIP_ENABLED", "1")
    monkeypatch.setenv("CC_XIANYU_WEBHOOK_URL", "https://cc.example.test/api/ops/xianyu/paid-order")
    monkeypatch.setenv("CC_XIANYU_WEBHOOK_TOKEN", "unit-test-token")
    monkeypatch.setenv("CC_XIANYU_AUTO_SHIP_DELAY_SECONDS", "0")
    monkeypatch.setenv("CC_XIANYU_DEFAULT_PLAN_ID", "starter")


def test_operator_state_missing_or_corrupt_fails_closed(tmp_path, monkeypatch):
    """运营状态不可读时必须保持暂停，不能静默恢复自动发货。"""
    state_path = tmp_path / "cc-operator-state.json"
    monkeypatch.setenv("CC_OPERATOR_STATE_FILE", str(state_path))
    monkeypatch.delenv("CC_XIANYU_AUTO_SHIP_PAUSED", raising=False)

    assert get_operator_state()["auto_ship_paused"] is True

    state_path.write_text("{broken", encoding="utf-8")
    assert get_operator_state()["auto_ship_paused"] is True


def test_one_shot_delivery_ticket_is_consumed_once_under_concurrency(tmp_path, monkeypatch):
    """多个浏览器助手同时领取时，单次放行票只能成功消费一次。"""
    state_path = tmp_path / "cc-operator-state.json"
    monkeypatch.setenv("CC_OPERATOR_STATE_FILE", str(state_path))
    authorize_one_shot_delivery("concurrency test", ttl_seconds=180)

    # 放大旧版无锁读写窗口，让并发回归可以稳定复现。
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state["race_padding"] = "x" * 2_000_000
    state_path.write_text(json.dumps(state), encoding="utf-8")
    workers = 12
    barrier = threading.Barrier(workers)

    def consume() -> dict:
        barrier.wait(timeout=5)
        return consume_one_shot_delivery("concurrent claim")

    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(lambda _index: consume(), range(workers)))

    assert sum(result["allowed"] is True for result in results) == 1
    assert cc_operator_state.peek_one_shot_delivery()["active"] is False


def test_cc_shipment_send_claim_is_atomic_across_threads(tmp_path):
    """同一条待补发记录并发领取时只能有一个发送者进入执行态。"""
    ctx = XianyuContextManager(db_path=str(tmp_path / "xianyu-chat.db"))
    ctx.record_cc_shipment(
        order_id="xy_oid_atomic_send",
        buyer_id="buyer-atomic",
        item_id="item-atomic",
        status="message_send_failed",
        delivery_message="兑换码：CC-ATOMIC-SEND",
    )
    shipment_id = ctx.list_cc_shipments(include_message=True)[0]["id"]
    workers = 8
    barrier = threading.Barrier(workers)

    def claim() -> dict | None:
        barrier.wait(timeout=5)
        return ctx.claim_cc_shipment_send(
            shipment_id,
            expected_statuses=("message_send_failed",),
        )

    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(lambda _index: claim(), range(workers)))

    assert sum(result is not None for result in results) == 1
    assert ctx.get_cc_shipment(shipment_id)["status"] == "message_send_inflight"


def test_cc_auto_ship_order_claim_is_atomic_across_threads(tmp_path):
    """同一真实订单的并发付款事件只能有一个 webhook 分配执行者。"""
    ctx = XianyuContextManager(db_path=str(tmp_path / "xianyu-chat.db"))
    workers = 8
    barrier = threading.Barrier(workers)

    def claim() -> dict | None:
        barrier.wait(timeout=5)
        return ctx.claim_cc_auto_ship_order(
            "xy_oid_atomic_webhook",
            buyer_id="buyer-atomic",
            item_id="item-atomic",
        )

    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(lambda _index: claim(), range(workers)))

    assert sum(result is not None for result in results) == 1
    shipment = ctx.get_cc_shipment_by_order_id("xy_oid_atomic_webhook")
    assert shipment["status"] == "webhook_inflight"


def test_pause_record_cannot_downgrade_sent_or_uncertain_shipment(tmp_path):
    """暂停分支不能覆盖已发送或结果不确定的终态。"""
    ctx = XianyuContextManager(db_path=str(tmp_path / "xianyu-chat.db"))
    for order_id, terminal_status in (
        ("xy_oid_sent_terminal", "message_sent"),
        ("xy_oid_uncertain_terminal", "message_send_uncertain"),
    ):
        ctx.record_cc_shipment(order_id=order_id, status=terminal_status, delivery_message="兑换码：CC-TERMINAL")
        ctx.record_cc_shipment(order_id=order_id, status="operator_paused", error="暂停")
        shipment = ctx.get_cc_shipment_by_order_id(order_id, include_message=True)
        assert shipment["status"] == terminal_status
        assert shipment["delivery_message"] == "兑换码：CC-TERMINAL"


def test_xianyu_live_message_sent_consumes_auto_resume_canary(live, monkeypatch):
    """WebSocket 自动发货路径写入 message_sent 时，也会触发首单自动暂停。"""
    set_auto_ship_paused(False, "unit test safe resume", resume_canary=True)

    live._record_cc_shipment_safely(
        "xy_oid_live_canary",
        "buyer-live",
        "item-live",
        "message_sent",
        chat_id="chat-live",
        delivery_message="兑换码：CC-LIVE",
    )

    state = get_operator_state()
    assert state["auto_ship_paused"] is True
    assert state["auto_resume_canary"]["remaining"] == 0
    assert state["auto_resume_canary"]["last_order_id"] == "xy_oid_live_canary"
    live.ctx.record_cc_shipment.assert_called_once()


@pytest.mark.asyncio
async def test_unconfigured_cc_webhook_returns_none_and_allows_legacy_fallback(live):
    result = await live._try_cc_zhongzhuan_auto_ship(object(), "order-001", "item-001", "buyer-001")

    assert result is None
    live.send_msg.assert_not_called()
    live.notifier.notify_health.assert_not_called()


@pytest.mark.asyncio
async def test_operator_pause_stops_cc_auto_ship(monkeypatch, live, fake_httpx):
    configure_cc_webhook(monkeypatch)
    set_auto_ship_paused(True, "unit test pause")

    result = await live._try_cc_zhongzhuan_auto_ship(object(), "order-paused", "item-001", "buyer-001")

    assert result is False
    assert fake_httpx.calls == []
    live.send_msg.assert_not_called()
    live.ctx.record_cc_shipment.assert_called_once_with(
        order_id="order-paused",
        buyer_id="buyer-001",
        item_id="item-001",
        chat_id="",
        status="operator_paused",
        delivery_message="",
        error="本机操作台已暂停自动发货",
    )


def test_resolves_empty_item_id_when_cc_webhook_is_configured(monkeypatch, live):
    assert live._resolve_auto_ship_item_id("") is None

    monkeypatch.setenv("CC_XIANYU_DEFAULT_ITEM_ID", "default-item")
    assert live._resolve_auto_ship_item_id("") == "default-item"

    monkeypatch.delenv("CC_XIANYU_DEFAULT_ITEM_ID", raising=False)
    configure_cc_webhook(monkeypatch)
    assert live._resolve_auto_ship_item_id("") == ""
    assert live._resolve_auto_ship_item_id("recent-item") == "recent-item"


@pytest.mark.parametrize(
    "reminder",
    [
        "等待卖家发货",
        "待发货",
        "等待发货",
        "待卖家发货",
        "卖家待发货",
        "买家已付款",
        "已付款",
        "买家已支付",
        "已支付",
        "买家已付款，等待卖家发货",
        "已付款｜等待卖家发货",
    ],
)
def test_detects_xianyu_paid_order_status_variants(live, reminder):
    assert live._check_order({"3": {"redReminder": reminder}}) == "paid"


@pytest.mark.parametrize(
    ("reminder", "expected"),
    [
        ("等待买家付款", "pending_payment"),
        ("待付款", "pending_payment"),
        ("等待付款", "pending_payment"),
        ("买家未付款", "pending_payment"),
        ("未付款", "pending_payment"),
        ("退款成功", "refunded"),
        ("退款中", "refunding"),
        ("退款处理中", "refunding"),
        ("交易关闭", "closed"),
        ("订单关闭", "closed"),
        ("交易成功", "completed"),
        ("普通聊天消息", None),
    ],
)
def test_xianyu_order_status_variants_do_not_false_ship(live, reminder, expected):
    assert live._check_order({"3": {"redReminder": reminder}}) == expected


def test_detects_paid_status_from_structured_order_fields(live):
    """闲鱼状态字段位置变化时，仍应识别已付款订单。"""
    assert live._check_order({"orderInfo": {"statusText": "买家已付款，等待卖家发货"}}) == "paid"
    assert live._check_order({"tradeInfo": {"tradeStatusText": "待发货"}}) == "paid"
    assert live._check_order({"3": {"reminderContent": "已支付，等待卖家发货"}}) == "paid"
    assert live._check_order({"bizOrderInfo": {"payStatusText": "已支付"}}) == "paid"


def test_order_status_detection_ignores_plain_chat_text(live):
    """普通聊天里出现付款字样不能触发自动发货。"""
    message = {
        "1": {"10": {"reminderContent": "我已付款了吗？"}},
        "text": "买家说已付款了吗",
    }

    assert live._check_order(message) is None


def test_detects_paid_status_from_xianyu_system_chat_title(live):
    """新版闲鱼把付款提醒放在聊天系统卡片标题时，也要识别为待发货。"""
    message = {
        "1": {
            "5": "1783389000000",
            "10": {
                "senderUserId": "buyer-system-card",
                "reminderTitle": "我已付款，等待你发货",
                "reminderContent": "请包装好商品，并按我在闲鱼上提供的地址发货",
            },
        }
    }

    assert live._check_order(message) == "paid"
    assert XianyuLive._extract_order_buyer_id(message) == "buyer-system-card"


def test_paid_text_in_normal_chat_content_does_not_trigger(live):
    """只信系统卡片标题；普通聊天内容照抄付款文案也不能自动发货。"""
    message = {
        "1": {
            "10": {
                "senderUserId": "buyer-normal-chat",
                "reminderTitle": "Carven",
                "reminderContent": "我已付款，等待你发货",
            }
        }
    }

    assert live._check_order(message) is None


def test_decode_sync_payload_accepts_plain_json_system_card():
    """明文 JSON 系统卡片不能再被直接跳过。"""
    message = {"1": {"10": {"senderUserId": "buyer-plain", "reminderTitle": "我已付款，等待你发货"}}}
    raw = base64.b64encode(json.dumps(message).encode()).decode()

    assert XianyuLive._decode_sync_message_payload(raw) == message


def test_stable_xianyu_order_id_prefers_real_order_identifier():
    """有真实订单号时，重复消息应生成同一个脱敏 order_id。"""
    message = {
        "1": "buyer-001@goofish",
        "3": {"redReminder": "等待卖家发货"},
        "orderInfo": {"bizOrderId": "XYREALORDER123456"},
    }
    changed_message = {
        **message,
        "volatile": {"timestamp": "later"},
    }

    first = XianyuLive._stable_xianyu_order_id(message, "buyer-001", "item-001", "paid")
    second = XianyuLive._stable_xianyu_order_id(changed_message, "buyer-001", "item-001", "paid")

    assert first == second
    assert first.startswith("xy_oid_")
    assert "XYREALORDER" not in first


def test_stable_xianyu_order_id_extracts_order_identifier_from_url_params():
    """真实订单号藏在闲鱼 URL 参数里时，也要稳定识别，避免重复发卡。"""
    message = {
        "1": "buyer-url@goofish",
        "3": {
            "redReminder": "等待卖家发货",
            "reminderUrl": "https://market.m.taobao.com/app/idleFish-F2e/orderDetail?itemId=item-001&bizOrderId=XYURLORDER123456&spm=a",
        },
    }
    changed_message = {
        **message,
        "volatile": {"timestamp": "later", "seq": 2},
    }

    first = XianyuLive._stable_xianyu_order_id(message, "buyer-url", "item-001", "paid")
    second = XianyuLive._stable_xianyu_order_id(changed_message, "buyer-url", "item-001", "paid")

    assert first == second
    assert first.startswith("xy_oid_")
    assert "XYURLORDER" not in first


def test_extracts_item_identifier_from_paid_order_url_params():
    """商品 ID 藏在闲鱼订单 URL 参数里时，应优先识别出来用于套餐路由。"""
    message = {
        "3": {
            "redReminder": "等待卖家发货",
            "reminderUrl": "https://market.m.taobao.com/app/idleFish-F2e/orderDetail?itemId=item-pro&bizOrderId=XYURLORDER123456",
        },
    }

    assert XianyuLive._extract_xianyu_item_identifier(message) == "item-pro"


def test_extracts_item_identifier_from_structured_item_fields():
    """闲鱼消息直接带 itemId / item_id_str 字段时也要识别。"""
    assert XianyuLive._extract_xianyu_item_identifier({"orderInfo": {"itemId": "item-basic"}}) == "item-basic"
    assert XianyuLive._extract_xianyu_item_identifier({"bizOrderInfo": {"item_id_str": "item-pro"}}) == "item-pro"


def test_extract_item_identifier_ignores_plain_chat_text():
    """普通聊天文本里出现 itemId=xxx 不能污染商品映射，避免发错套餐。"""
    message = {
        "1": {"10": {"reminderContent": "我看到链接里写着 itemId=item-pro，是这个吗？"}},
        "text": "https://example.test/chat?itemId=item-pro",
    }

    assert XianyuLive._extract_xianyu_item_identifier(message) == ""


@pytest.mark.asyncio
async def test_paid_order_uses_message_item_id_before_recent_item(monkeypatch):
    """已付款事件自带商品 ID 时，自动发货必须用该商品而不是最近聊天商品。"""
    paid_message = {
        "1": "buyer-paid@goofish",
        "3": {
            "redReminder": "等待卖家发货",
            "reminderUrl": "https://market.m.taobao.com/app/idleFish-F2e/orderDetail?itemId=item-pro&bizOrderId=XYPAIDORDER123456",
        },
    }
    raw = base64.b64encode(b"not-json").decode()
    monkeypatch.setattr("src.xianyu.xianyu_live.decrypt", lambda _: json.dumps(paid_message))

    class FakeTask:
        def add_done_callback(self, callback):
            self.callback = callback

    created_tasks = []

    def fake_create_task(coro):
        created_tasks.append(coro)
        return FakeTask()

    monkeypatch.setattr("src.xianyu.xianyu_live.asyncio.create_task", fake_create_task)

    class FakeBus:
        async def publish(self, *args, **kwargs):
            return {"ok": True, "args": args, "kwargs": kwargs}

    monkeypatch.setattr("src.core.event_bus.get_event_bus", lambda: FakeBus(), raising=False)

    instance = object.__new__(XianyuLive)
    instance.ctx = SimpleNamespace(
        get_recent_item_id=MagicMock(return_value="item-basic"),
        get_item=MagicMock(return_value={"title": "CC中转 Pro", "skuList": [{"price": "990"}]}),
        record_order=MagicMock(),
        mark_converted=MagicMock(),
    )
    instance.notifier = SimpleNamespace(notify_order=MagicMock())
    delayed_marker = object()
    instance._delayed_auto_ship = MagicMock(return_value=delayed_marker)
    instance._log_bg_task_error = MagicMock()
    ws = SimpleNamespace(send=AsyncMock())

    await instance.handle_message(
        {"headers": {"mid": "mid-001", "sid": "sid-001"}, "body": {"syncPushPackage": {"data": [{"data": raw}]}}},
        ws,
    )

    instance.ctx.record_order.assert_called_once_with(
        chat_id="buyer-paid",
        user_id="buyer-paid",
        item_id="item-pro",
        status="等待卖家发货",
        amount=9.9,
    )
    instance.ctx.mark_converted.assert_called_once_with("buyer-paid", "item-pro")
    instance._delayed_auto_ship.assert_called_once()
    delayed_args = instance._delayed_auto_ship.call_args.args
    assert delayed_args[1].startswith("xy_oid_")
    assert delayed_args[2] == "item-pro"
    assert delayed_args[3] == "buyer-paid"
    assert created_tasks == [delayed_marker]


@pytest.mark.asyncio
async def test_plain_json_paid_system_card_starts_auto_ship(monkeypatch):
    """明文付款系统卡片应进入自动发货任务，而不是被 WebSocket 主循环跳过。"""
    paid_message = {
        "1": {
            "5": "1783389000000",
            "10": {
                "senderUserId": "buyer-plain-paid",
                "reminderTitle": "我已付款，等待你发货",
                "reminderContent": "请包装好商品，并按我在闲鱼上提供的地址发货",
                "reminderUrl": "https://market.m.taobao.com/app/idleFish-F2e/orderDetail?itemId=item-pro&bizOrderId=XYPLAINORDER123456",
            },
        }
    }
    raw = base64.b64encode(json.dumps(paid_message).encode()).decode()

    class FakeTask:
        def add_done_callback(self, callback):
            self.callback = callback

    created_tasks = []

    def fake_create_task(coro):
        created_tasks.append(coro)
        return FakeTask()

    monkeypatch.setattr("src.xianyu.xianyu_live.asyncio.create_task", fake_create_task)

    class FakeBus:
        async def publish(self, *args, **kwargs):
            return {"ok": True, "args": args, "kwargs": kwargs}

    monkeypatch.setattr("src.core.event_bus.get_event_bus", lambda: FakeBus(), raising=False)

    instance = object.__new__(XianyuLive)
    instance.ctx = SimpleNamespace(
        get_recent_item_id=MagicMock(return_value="item-basic"),
        get_item=MagicMock(return_value={"title": "CC中转 Pro", "skuList": [{"price": "100"}]}),
        record_order=MagicMock(),
        mark_converted=MagicMock(),
    )
    instance.notifier = SimpleNamespace(notify_order=MagicMock())
    delayed_marker = object()
    instance._delayed_auto_ship = MagicMock(return_value=delayed_marker)
    instance._log_bg_task_error = MagicMock()
    ws = SimpleNamespace(send=AsyncMock())

    await instance.handle_message(
        {"headers": {"mid": "mid-plain", "sid": "sid-plain"}, "body": {"syncPushPackage": {"data": [{"data": raw}]}}},
        ws,
    )

    instance.ctx.record_order.assert_called_once_with(
        chat_id="buyer-plain-paid",
        user_id="buyer-plain-paid",
        item_id="item-pro",
        status="等待卖家发货",
        amount=1.0,
    )
    instance.ctx.mark_converted.assert_called_once_with("buyer-plain-paid", "item-pro")
    instance._delayed_auto_ship.assert_called_once()
    delayed_args = instance._delayed_auto_ship.call_args.args
    assert delayed_args[1].startswith("xy_oid_")
    assert delayed_args[2] == "item-pro"
    assert delayed_args[3] == "buyer-plain-paid"
    assert created_tasks == [delayed_marker]


def test_stable_xianyu_order_id_fails_closed_without_business_identifier():
    """只有易变消息字段而没有真实订单号时，必须拒绝生成履约键。"""
    first_message = {
        "1": "buyer-001@goofish",
        "3": {"redReminder": "等待卖家发货"},
        "volatile": {"timestamp": "1783389000000", "seq": 1},
    }
    second_message = {
        **first_message,
        "volatile": {"timestamp": "1783389000999", "seq": 2},
    }

    first = XianyuLive._stable_xianyu_order_id(first_message, "buyer-001", "item-001", "paid")
    second = XianyuLive._stable_xianyu_order_id(second_message, "buyer-001", "item-001", "paid")

    assert first is None
    assert second is None


def test_parse_seller_sold_order_item_hashes_real_order_id():
    """订单轮询拿到真实订单号时，本机只保存脱敏订单号。"""
    parsed = XianyuLive._parse_seller_sold_order_item(
        {
            "commonData": {
                "orderId": "XYREALORDERPOLL123456",
                "itemId": "item-poll",
                "orderStatus": "待发货",
                "itemTitle": "CC中转测试卡",
            },
            "buyerInfoVO": {"buyerId": "buyer-poll"},
            "priceVO": {"totalPrice": "1.00"},
        }
    )

    assert parsed["order_id"].startswith("xy_oid_")
    assert "XYREALORDERPOLL" not in parsed["order_id"]
    assert parsed["raw_order_id"] == "XYREALORDERPOLL123456"
    assert parsed["item_id"] == "item-poll"
    assert parsed["buyer_id"] == "buyer-poll"
    assert parsed["amount"] == 1.0


def test_extract_cid_from_create_chat_response_variants():
    """创建单聊会话响应结构变化时仍能提取 chat_id。"""
    assert (
        XianyuLive._extract_cid_from_create_chat_response(
            {"body": [{"singleChatConversation": {"cid": "chat-001@goofish"}}]}
        )
        == "chat-001"
    )
    assert (
        XianyuLive._extract_cid_from_create_chat_response(
            {"body": [{"singleChatUserConversation": {"singleChatConversation": {"cid": "chat-002@goofish"}}}]}
        )
        == "chat-002"
    )
    assert (
        XianyuLive._extract_cid_from_create_chat_response(
            {"body": [{"data": {"singleChatConversation": {"cid": "chat-003@goofish"}}}]}
        )
        == "chat-003"
    )


@pytest.mark.asyncio
async def test_create_chat_conversation_sends_lwp_and_waits_response():
    """缺少聊天上下文时，可通过闲鱼 LWP 创建/获取会话再发货。"""
    instance = object.__new__(XianyuLive)
    instance.myid = "seller-001"
    instance._pending_mid_futures = {}

    class FakeWs:
        open = True

        async def send(self, payload: str):
            sent = json.loads(payload)
            mid = sent["headers"]["mid"]
            instance._dispatch_mid_response(
                {
                    "headers": {"mid": mid},
                    "body": [{"singleChatConversation": {"cid": "chat-created@goofish"}}],
                }
            )

    instance.ws = FakeWs()

    chat_id = await instance.create_chat_conversation("buyer-created", "item-created", timeout=1)

    assert chat_id == "chat-created"
    assert instance._pending_mid_futures == {}


@pytest.mark.asyncio
async def test_paid_order_poll_uses_seller_not_ship_api_and_dispatches_cc(monkeypatch, live):
    """WebSocket 漏掉付款卡片时，订单轮询应能把待发货订单交给 CC webhook。"""
    configure_cc_webhook(monkeypatch)
    live.ws = SimpleNamespace(open=True)
    live.cookies_str = "unb=seller-001; _m_h5_tk=token_9999999999999"
    live.cookies = {"unb": "seller-001", "_m_h5_tk": "token_9999999999999"}
    live.myid = "seller-001"
    live.ctx.record_order = MagicMock()
    live.ctx.mark_converted = MagicMock()
    live._try_cc_zhongzhuan_auto_ship = AsyncMock(return_value=True)

    class FakeOrderApi:
        def __init__(self, cookies_str: str):
            self.cookies_str = cookies_str

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get_sold_orders_page(self, page: int, query_code: str):
            assert page == 1
            assert query_code == "NOT_SHIP"
            return {
                "success": True,
                "total_count": 1,
                "items": [
                    {
                        "commonData": {
                            "orderId": "XYREALORDERPOLL123456",
                            "itemId": "item-poll",
                            "orderStatus": "待发货",
                        },
                        "buyerInfoVO": {"buyerId": "buyer-poll"},
                        "priceVO": {"totalPrice": "1.00"},
                    }
                ],
            }

    monkeypatch.setattr("src.xianyu.xianyu_live.XianyuApis", FakeOrderApi)

    result = await live._poll_cc_paid_orders_once(batch_size=5)

    assert result["ok"] is True
    assert result["processed"] == 1
    assert result["shipped"] == 1
    live.ctx.record_order.assert_called_once_with(
        chat_id="buyer-poll",
        user_id="buyer-poll",
        item_id="item-poll",
        status="等待卖家发货",
        amount=1.0,
    )
    live.ctx.mark_converted.assert_called_once_with("buyer-poll", "item-poll")
    live._try_cc_zhongzhuan_auto_ship.assert_awaited_once()
    args = live._try_cc_zhongzhuan_auto_ship.call_args.args
    kwargs = live._try_cc_zhongzhuan_auto_ship.call_args.kwargs
    assert args[0] is live.ws
    assert args[1].startswith("xy_oid_")
    assert "XYREALORDERPOLL" not in args[1]
    assert args[2] == "item-poll"
    assert args[3] == "buyer-poll"
    assert kwargs["xianyu_order_id_for_confirm"] == "XYREALORDERPOLL123456"


@pytest.mark.asyncio
async def test_paid_order_poll_pauses_when_rescue_queue_not_clear(monkeypatch, live):
    """已分配未发送的补救单存在时，轮询不能再分配新卡。"""
    configure_cc_webhook(monkeypatch)
    live.ws = SimpleNamespace(open=True)
    live.ctx.cc_shipment_summary = MagicMock(return_value={"pending_rescue": 1})
    live._try_cc_zhongzhuan_auto_ship = AsyncMock()

    result = await live._poll_cc_paid_orders_once(batch_size=5)

    assert result == {"ok": False, "reason": "pending_rescue_exists", "processed": 0}
    live._try_cc_zhongzhuan_auto_ship.assert_not_called()


@pytest.mark.asyncio
async def test_paid_order_poll_reuses_manual_ready_shipment_without_new_card(monkeypatch, live):
    """真实待发货订单出现后，应优先复用已分配待发送卡密，不再次请求发卡。"""
    configure_cc_webhook(monkeypatch)
    live.ws = SimpleNamespace(open=True)
    live.cookies_str = "unb=seller-001; _m_h5_tk=token_9999999999999"
    live.cookies = {"unb": "seller-001", "_m_h5_tk": "token_9999999999999"}
    live.myid = "seller-001"
    live.ctx.record_order = MagicMock()
    live.ctx.mark_converted = MagicMock()
    live.ctx.cc_shipment_summary = MagicMock(
        return_value={
            "pending_rescue": 1,
            "by_status": {"manual_delivery_ready": 1},
        }
    )
    live.ctx.list_cc_shipments = MagicMock(
        return_value=[
            {
                "id": 31,
                "order_id": "xy_manual_ready_order",
                "buyer_id": "手机截图已付款",
                "item_id": "item-poll",
                "chat_id": "",
                "status": "manual_delivery_ready",
                "delivery_message": "兑换网址：https://jiyu.245334.xyz，卡密：CC-OLD-CARD",
            }
        ]
    )
    live.ctx.get_cc_shipment = MagicMock(return_value=live.ctx.list_cc_shipments.return_value[0])
    live._try_cc_zhongzhuan_auto_ship = AsyncMock()

    class FakeOrderApi:
        def __init__(self, cookies_str: str):
            self.cookies_str = cookies_str

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get_sold_orders_page(self, page: int, query_code: str):
            return {
                "success": True,
                "total_count": 1,
                "items": [
                    {
                        "commonData": {
                            "orderId": "XYREALORDERPOLL123456",
                            "itemId": "item-poll",
                            "orderStatus": "待发货",
                        },
                        "buyerInfoVO": {"buyerId": "buyer-poll"},
                        "priceVO": {"totalPrice": "1.00"},
                    }
                ],
            }

    monkeypatch.setattr("src.xianyu.xianyu_live.XianyuApis", FakeOrderApi)

    result = await live._poll_cc_paid_orders_once(batch_size=5)

    assert result["ok"] is True
    assert result["processed"] == 1
    assert result["shipped"] == 1
    live._try_cc_zhongzhuan_auto_ship.assert_not_called()
    live.send_msg.assert_awaited_once_with(
        live.ws,
        "chat-buyer-001",
        "buyer-poll",
        "兑换网址：https://jiyu.245334.xyz，卡密：CC-OLD-CARD",
    )
    complete_args = live.ctx.complete_cc_shipment_send.call_args.args
    assert complete_args[0] == 31
    assert complete_args[1].startswith("xy_oid_")
    assert "XYREALORDERPOLL" not in complete_args[1]
    assert complete_args[2:] == (
        "buyer-poll",
        "item-poll",
    )
    assert live.ctx.complete_cc_shipment_send.call_args.kwargs == {
        "chat_id": "chat-buyer-001",
        "status": "message_sent",
        "error": "",
    }


@pytest.mark.asyncio
async def test_manual_ready_shipment_send_failure_keeps_rescue_state(live):
    """复用已分配卡密时如果闲鱼发送失败，要保留补救状态，不丢话术。"""
    live.ws = SimpleNamespace(open=True)
    live.ctx.list_cc_shipments = MagicMock(
        return_value=[
            {
                "id": 32,
                "order_id": "xy_manual_ready_order",
                "buyer_id": "手机截图已付款",
                "item_id": "item-poll",
                "chat_id": "",
                "status": "manual_delivery_ready",
                "delivery_message": "兑换网址：https://jiyu.245334.xyz，卡密：CC-OLD-CARD",
            }
        ]
    )
    live.ctx.get_cc_shipment = MagicMock(return_value=live.ctx.list_cc_shipments.return_value[0])
    live.send_msg = AsyncMock(side_effect=RuntimeError("websocket closed"))

    result = await live._try_send_existing_manual_ready_shipment(
        live.ws,
        {"order_id": "xy_oid_real_order", "buyer_id": "buyer-poll", "item_id": "item-poll"},
        "item-poll",
    )

    assert result is False
    live.ctx.complete_cc_shipment_send.assert_called_once_with(
        32,
        "xy_oid_real_order",
        "buyer-poll",
        "item-poll",
        chat_id="chat-buyer-001",
        status="message_send_uncertain",
        error="websocket closed",
    )
    live.notifier.notify_health.assert_called_once()


@pytest.mark.asyncio
async def test_configured_cc_webhook_sends_paid_order_and_delivery_message(monkeypatch, live, fake_httpx):
    configure_cc_webhook(monkeypatch)
    fake_httpx.response = FakeResponse(200, {"deliveryMessage": "兑换网址：https://jiyu.245334.xyz，卡密：CC-TEST"})

    ws = object()
    result = await live._try_cc_zhongzhuan_auto_ship(ws, "order-002", "item-002", "buyer-002")

    assert result is True
    assert len(fake_httpx.calls) == 1
    call = fake_httpx.calls[0]
    assert call["url"] == "https://cc.example.test/api/ops/xianyu/paid-order"
    assert call["headers"] == {"x-cc-xianyu-token": "unit-test-token"}
    assert call["json"] == {
        "orderId": "order-002",
        "status": "等待卖家发货",
        "paid": True,
        "itemId": "item-002",
        "productTitle": "CC中转 月卡",
        "buyerHint": "buyer-002",
        "planId": "starter",
        "note": "openclaw-xianyu-live",
    }
    live.send_msg.assert_awaited_once_with(
        ws, "chat-buyer-001", "buyer-002", "兑换网址：https://jiyu.245334.xyz，卡密：CC-TEST"
    )
    live.ctx.record_cc_shipment.assert_called_once_with(
        order_id="order-002",
        buyer_id="buyer-002",
        item_id="item-002",
        chat_id="chat-buyer-001",
        status="message_send_inflight",
        delivery_message="兑换网址：https://jiyu.245334.xyz，卡密：CC-TEST",
        error="消息发送处理中；异常退出时必须人工核对，禁止自动重试",
    )
    live.ctx.complete_cc_shipment_send.assert_called_once_with(
        1,
        "order-002",
        "buyer-002",
        "item-002",
        chat_id="chat-buyer-001",
        status="message_sent",
        error="",
    )
    live.notifier.notify_order.assert_called_once()


@pytest.mark.asyncio
async def test_concurrent_paid_events_call_webhook_and_send_only_once(monkeypatch, tmp_path, fake_httpx):
    """同一订单的并发已付款事件只能分配一次卡密并发送一次消息。"""
    configure_cc_webhook(monkeypatch)
    fake_httpx.response = FakeResponse(200, {"deliveryMessage": "兑换码：CC-CONCURRENT"})
    instance = object.__new__(XianyuLive)
    instance.ctx = XianyuContextManager(db_path=str(tmp_path / "xianyu-chat.db"))
    instance.notifier = SimpleNamespace(notify_health=MagicMock(), notify_order=MagicMock())
    instance.send_msg = AsyncMock()
    instance.myid = "seller-001"

    results = await asyncio.gather(
        instance._try_cc_zhongzhuan_auto_ship(object(), "xy_oid_concurrent_paid", "item-002", "buyer-002"),
        instance._try_cc_zhongzhuan_auto_ship(object(), "xy_oid_concurrent_paid", "item-002", "buyer-002"),
    )

    assert all(result in {True, False} for result in results)
    assert len(fake_httpx.calls) == 1
    instance.send_msg.assert_awaited_once()
    shipment = instance.ctx.get_cc_shipment_by_order_id("xy_oid_concurrent_paid")
    assert shipment["status"] == "message_sent"


@pytest.mark.asyncio
async def test_xianyu_confirm_shipment_is_opt_in_after_delivery(monkeypatch, live, fake_httpx):
    """默认不点闲鱼确认发货；开启后只对数字订单号执行。"""
    configure_cc_webhook(monkeypatch)
    monkeypatch.setenv("CC_XIANYU_AUTO_CONFIRM_SHIPMENT_ENABLED", "1")
    fake_httpx.response = FakeResponse(200, {"deliveryMessage": "兑换网址：https://jiyu.245334.xyz，卡密：CC-CONFIRM"})
    live.cookies_str = "_m_h5_tk=token_123; unb=seller-001"
    live.ctx.mark_cc_shipment_xianyu_confirm = MagicMock(return_value=True)

    class FakeConfirmApis:
        def __init__(self, cookies_str: str):
            self.cookies_str = cookies_str

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def confirm_dummy_shipment(self, order_id: str):
            return {"success": True, "order_id": order_id, "cookies_str": self.cookies_str}

    monkeypatch.setattr("src.xianyu.xianyu_live.XianyuApis", FakeConfirmApis)

    result = await live._try_cc_zhongzhuan_auto_ship(object(), "1234567890123456", "item-002", "buyer-002")

    assert result is True
    live.ctx.mark_cc_shipment_xianyu_confirm.assert_called_once_with("1234567890123456", "confirmed", "")
    assert live.notifier.notify_order.call_count == 2


@pytest.mark.asyncio
async def test_poll_auto_ship_confirms_with_raw_order_id_but_marks_hashed_order(monkeypatch, live, fake_httpx):
    """订单轮询发卡后，确认发货用真实订单号，本机状态仍按脱敏订单号回写。"""
    configure_cc_webhook(monkeypatch)
    monkeypatch.setenv("CC_XIANYU_AUTO_CONFIRM_SHIPMENT_ENABLED", "1")
    fake_httpx.response = FakeResponse(
        200, {"deliveryMessage": "兑换网址：https://jiyu.245334.xyz，卡密：CC-RAW-CONFIRM"}
    )
    live.ctx.mark_cc_shipment_xianyu_confirm = MagicMock(return_value=True)

    class FakeConfirmApis:
        seen_order_ids: list[str] = []

        def __init__(self, cookies_str: str):
            self.cookies_str = cookies_str

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def confirm_dummy_shipment(self, order_id: str):
            self.__class__.seen_order_ids.append(order_id)
            return {"success": True, "order_id": order_id, "cookies_str": self.cookies_str}

    monkeypatch.setattr("src.xianyu.xianyu_live.XianyuApis", FakeConfirmApis)
    hashed_order_id = XianyuLive._hash_xianyu_order_id("1234567890123456")

    result = await live._try_cc_zhongzhuan_auto_ship(
        object(),
        hashed_order_id,
        "item-raw-confirm",
        "buyer-raw-confirm",
        xianyu_order_id_for_confirm="1234567890123456",
    )

    assert result is True
    assert FakeConfirmApis.seen_order_ids == ["1234567890123456"]
    live.ctx.mark_cc_shipment_xianyu_confirm.assert_called_once_with(hashed_order_id, "confirmed", "")


@pytest.mark.asyncio
async def test_xianyu_confirm_shipment_skips_manual_order_id(monkeypatch, live):
    """手工兜底订单号不是闲鱼真实数字订单号时，不能自动点确认发货。"""
    monkeypatch.setenv("CC_XIANYU_AUTO_CONFIRM_SHIPMENT_ENABLED", "1")
    live.ctx.mark_cc_shipment_xianyu_confirm = MagicMock(return_value=True)

    result = await live._maybe_confirm_xianyu_order_shipped("xy_manual_test", "item-001", "buyer-001")

    assert result["reason"] == "non_numeric_order_id"
    live.ctx.mark_cc_shipment_xianyu_confirm.assert_called_once()
    live.notifier.notify_order.assert_not_called()


@pytest.mark.asyncio
async def test_xianyu_api_confirm_dummy_rejects_non_numeric_order_id():
    """闲鱼确认发货 API 封装自身也要拒绝非数字订单号，防止误调用。"""
    async with XianyuApis("_m_h5_tk=token_123") as api:
        result = await api.confirm_dummy_shipment("xy_manual_test")

    assert result["success"] is False
    assert result["non_retryable"] is True
    assert "数字订单号" in result["error"]


@pytest.mark.asyncio
async def test_configured_cc_webhook_skips_duplicate_already_sent_order(monkeypatch, live, fake_httpx):
    """同一订单已发货时，重复事件不再调用 webhook，避免二次分配卡密。"""
    configure_cc_webhook(monkeypatch)
    live.ctx.get_cc_shipment_by_order_id = MagicMock(
        return_value={
            "id": 77,
            "order_id": "xy_oid_duplicate",
            "buyer_id": "buyer-dup",
            "item_id": "item-dup",
            "chat_id": "chat-dup",
            "status": "message_sent",
            "delivery_message": "兑换网址：https://jiyu.245334.xyz，卡密：CC-DUP",
        }
    )

    result = await live._try_cc_zhongzhuan_auto_ship(object(), "xy_oid_duplicate", "item-dup", "buyer-dup")

    assert result is True
    assert fake_httpx.calls == []
    live.send_msg.assert_not_called()


@pytest.mark.asyncio
async def test_configured_cc_webhook_resends_duplicate_failed_message_without_reallocating(
    monkeypatch, live, fake_httpx
):
    """同一订单已有已分配话术但发送失败时，只补发旧话术，不重新请求发卡。"""
    configure_cc_webhook(monkeypatch)
    live.ws = SimpleNamespace(open=True)
    live.ctx.get_cc_shipment_by_order_id = MagicMock(
        return_value={
            "id": 78,
            "order_id": "xy_oid_failed_once",
            "buyer_id": "buyer-dup",
            "item_id": "item-dup",
            "chat_id": "chat-dup",
            "status": "message_send_failed",
            "delivery_message": "兑换网址：https://jiyu.245334.xyz，卡密：CC-OLD",
        }
    )
    live.ctx.get_cc_shipment = MagicMock(
        return_value={
            "id": 78,
            "order_id": "xy_oid_failed_once",
            "buyer_id": "buyer-dup",
            "item_id": "item-dup",
            "chat_id": "chat-dup",
            "status": "message_send_failed",
            "delivery_message": "兑换网址：https://jiyu.245334.xyz，卡密：CC-OLD",
        }
    )

    result = await live._try_cc_zhongzhuan_auto_ship(live.ws, "xy_oid_failed_once", "item-dup", "buyer-dup")

    assert result is True
    assert fake_httpx.calls == []
    live.send_msg.assert_awaited_once_with(
        live.ws,
        "chat-dup",
        "buyer-dup",
        "兑换网址：https://jiyu.245334.xyz，卡密：CC-OLD",
    )


@pytest.mark.asyncio
async def test_configured_cc_webhook_prefers_item_mapping_plan(monkeypatch, live, fake_httpx):
    configure_cc_webhook(monkeypatch)
    live.ctx.get_item.return_value = None
    live.ctx.get_cc_item_mapping.return_value = {
        "item_id": "item-pro",
        "plan_id": "pro-month",
        "title": "CC中转 Pro 月卡",
        "enabled": True,
    }
    fake_httpx.response = FakeResponse(200, {"deliveryMessage": "兑换网址：https://jiyu.245334.xyz，卡密：CC-PRO"})

    result = await live._try_cc_zhongzhuan_auto_ship(object(), "order-mapping", "item-pro", "buyer-pro")

    assert result is True
    assert fake_httpx.calls[0]["json"]["planId"] == "pro-month"
    assert fake_httpx.calls[0]["json"]["productTitle"] == "CC中转 Pro 月卡"
    live.send_msg.assert_awaited_once()


@pytest.mark.asyncio
async def test_configured_cc_webhook_can_ship_without_item_context(monkeypatch, live, fake_httpx):
    configure_cc_webhook(monkeypatch)
    fake_httpx.response = FakeResponse(200, {"deliveryMessage": "兑换网址：https://jiyu.245334.xyz，卡密：CC-NO-ITEM"})

    result = await live._try_cc_zhongzhuan_auto_ship(object(), "order-no-item", "", "buyer-no-item")

    assert result is True
    assert fake_httpx.calls[0]["json"]["itemId"] == ""
    assert fake_httpx.calls[0]["json"]["productTitle"] == "CC中转 兑换码"
    live.ctx.get_item.assert_not_called()
    live.send_msg.assert_awaited_once()


@pytest.mark.asyncio
async def test_cc_webhook_http_error_stops_without_sending_or_falling_back(monkeypatch, live, fake_httpx):
    configure_cc_webhook(monkeypatch)
    fake_httpx.response = FakeResponse(502, {"error": "bad_gateway"})

    result = await live._try_cc_zhongzhuan_auto_ship(object(), "order-003", "item-003", "buyer-003")

    assert result is False
    live.send_msg.assert_not_called()
    live.ctx.record_cc_shipment.assert_called_once_with(
        order_id="order-003",
        buyer_id="buyer-003",
        item_id="item-003",
        chat_id="",
        status="webhook_failed",
        delivery_message="",
        error="HTTP 502",
    )
    live.notifier.notify_health.assert_called_once()


@pytest.mark.asyncio
async def test_cc_webhook_without_delivery_message_stops_without_sending(monkeypatch, live, fake_httpx):
    configure_cc_webhook(monkeypatch)
    fake_httpx.response = FakeResponse(200, {"ok": True})

    result = await live._try_cc_zhongzhuan_auto_ship(object(), "order-004", "item-004", "buyer-004")

    assert result is False
    live.send_msg.assert_not_called()
    live.ctx.record_cc_shipment.assert_called_once_with(
        order_id="order-004",
        buyer_id="buyer-004",
        item_id="item-004",
        chat_id="",
        status="missing_delivery_message",
        delivery_message="",
        error="webhook 未返回发货话术",
    )
    live.notifier.notify_health.assert_called_once()


@pytest.mark.asyncio
async def test_cc_webhook_marks_send_result_uncertain_and_blocks_automatic_reship(monkeypatch, live, fake_httpx):
    configure_cc_webhook(monkeypatch)
    fake_httpx.response = FakeResponse(200, {"deliveryMessage": "兑换网址：https://jiyu.245334.xyz，卡密：CC-RESEND"})
    live.send_msg = AsyncMock(side_effect=RuntimeError("websocket closed"))

    result = await live._try_cc_zhongzhuan_auto_ship(object(), "order-send-failed", "item-004", "buyer-004")

    assert result is False
    live.ctx.record_cc_shipment.assert_called_once_with(
        order_id="order-send-failed",
        buyer_id="buyer-004",
        item_id="item-004",
        chat_id="chat-buyer-001",
        status="message_send_inflight",
        delivery_message="兑换网址：https://jiyu.245334.xyz，卡密：CC-RESEND",
        error="消息发送处理中；异常退出时必须人工核对，禁止自动重试",
    )
    live.ctx.complete_cc_shipment_send.assert_called_once_with(
        1,
        "order-send-failed",
        "buyer-004",
        "item-004",
        chat_id="chat-buyer-001",
        status="message_send_uncertain",
        error="websocket closed",
    )
    live.notifier.notify_health.assert_called_once()


@pytest.mark.asyncio
async def test_resend_cc_shipment_sends_existing_delivery_message(live):
    live.ws = SimpleNamespace(open=True)
    live.ctx.get_cc_shipment = MagicMock(
        return_value={
            "id": 12,
            "order_id": "order-resend-001",
            "buyer_id": "buyer-resend",
            "item_id": "item-resend",
            "chat_id": "chat-resend",
            "status": "message_send_failed",
            "delivery_message": "兑换网址：https://jiyu.245334.xyz，卡密：CC-RESEND-OK",
        }
    )

    result = await live.resend_cc_shipment(12)

    assert result["ok"] is True
    assert result["id"] == 12
    live.send_msg.assert_awaited_once_with(
        live.ws,
        "chat-resend",
        "buyer-resend",
        "兑换网址：https://jiyu.245334.xyz，卡密：CC-RESEND-OK",
    )
    live.ctx.complete_cc_shipment_send.assert_called_once_with(
        12,
        "order-resend-001",
        "buyer-resend",
        "item-resend",
        chat_id="chat-resend",
        status="message_sent",
        error="",
    )


@pytest.mark.asyncio
async def test_resend_cc_shipment_rejects_records_without_delivery_message(live):
    live.ws = SimpleNamespace(open=True)
    live.ctx.get_cc_shipment = MagicMock(
        return_value={
            "id": 13,
            "order_id": "order-resend-missing-message",
            "buyer_id": "buyer-resend",
            "item_id": "item-resend",
            "chat_id": "chat-resend",
            "status": "message_send_failed",
            "delivery_message": "",
        }
    )

    with pytest.raises(ValueError, match="没有可补发的话术"):
        await live.resend_cc_shipment(13)

    live.send_msg.assert_not_called()


@pytest.mark.asyncio
async def test_browser_send_manual_ready_shipment_sends_existing_message(live):
    """浏览器助手拿到买家信息后，可发送已分配待发送的话术，不重新分配卡密。"""
    live.ws = SimpleNamespace(open=True)
    live.ctx.get_cc_shipment = MagicMock(
        return_value={
            "id": 14,
            "order_id": "xy_manual_browser_ready",
            "buyer_id": "手机截图已付款",
            "item_id": "item-browser",
            "chat_id": "",
            "status": "manual_delivery_ready",
            "delivery_message": "兑换网址：https://jiyu.245334.xyz，卡密：CC-BROWSER-OK",
        }
    )
    live.ctx.update_cc_shipment_delivery_state = MagicMock(return_value=True)

    result = await live.send_manual_ready_cc_shipment(
        shipment_id=14,
        buyer_id="buyer-browser",
        item_id="item-browser",
        order_id="xy_oid_browser_real_order",
    )

    assert result["ok"] is True
    assert result["status"] == "message_sent"
    live.send_msg.assert_awaited_once_with(
        live.ws,
        "chat-buyer-001",
        "buyer-browser",
        "兑换网址：https://jiyu.245334.xyz，卡密：CC-BROWSER-OK",
    )
    live.ctx.complete_cc_shipment_send.assert_called_once_with(
        14,
        "xy_oid_browser_real_order",
        "buyer-browser",
        "item-browser",
        chat_id="chat-buyer-001",
        status="message_sent",
        error="",
    )


@pytest.mark.asyncio
async def test_browser_send_manual_ready_shipment_marks_uncertain_on_send_failure(live):
    """浏览器助手发送异常后必须停在不确定态，不能留下可自动重试的记录。"""
    live.ws = SimpleNamespace(open=True)
    live.ctx.get_cc_shipment = MagicMock(
        return_value={
            "id": 15,
            "order_id": "xy_manual_browser_ready",
            "buyer_id": "手机截图已付款",
            "item_id": "item-browser",
            "chat_id": "chat-browser",
            "status": "manual_delivery_ready",
            "delivery_message": "兑换网址：https://jiyu.245334.xyz，卡密：CC-BROWSER-UNCERTAIN",
        }
    )
    live.send_msg = AsyncMock(side_effect=ConnectionError("连接在确认帧前断开"))

    with pytest.raises(RuntimeError, match="结果不确定"):
        await live.send_manual_ready_cc_shipment(
            shipment_id=15,
            buyer_id="buyer-browser",
            item_id="item-browser",
            order_id="xy_oid_browser_real_order",
        )

    live.ctx.complete_cc_shipment_send.assert_called_once_with(
        15,
        "xy_oid_browser_real_order",
        "buyer-browser",
        "item-browser",
        chat_id="chat-browser",
        status="message_send_uncertain",
        error="连接在确认帧前断开",
    )


@pytest.mark.asyncio
async def test_delayed_auto_ship_uses_legacy_shipper_only_when_cc_is_not_configured(live):
    live._try_cc_zhongzhuan_auto_ship = AsyncMock(return_value=None)
    shipper = MagicMock()
    shipper.get_rule.return_value = {"delay_seconds": 0}
    shipper.process_order.return_value = {"success": True, "message": "卡密：LEGACY-CARD", "remaining": 2}
    live._shipper = shipper

    ws = object()
    await live._delayed_auto_ship(ws, "order-005", "item-005", "buyer-005")

    shipper.process_order.assert_called_once_with(order_id="order-005", item_id="item-005", buyer_id="buyer-005")
    live.send_msg.assert_awaited_once_with(ws, "chat-buyer-001", "buyer-005", "卡密：LEGACY-CARD")


@pytest.mark.asyncio
async def test_delayed_auto_ship_does_not_send_legacy_card_when_cc_webhook_failed(live):
    live._try_cc_zhongzhuan_auto_ship = AsyncMock(return_value=False)
    shipper = MagicMock()
    live._shipper = shipper

    await live._delayed_auto_ship(object(), "order-006", "item-006", "buyer-006")

    shipper.process_order.assert_not_called()
    live.send_msg.assert_not_called()


def test_xianyu_context_tracks_cc_shipments_for_manual_reship(tmp_path):
    ctx = XianyuContextManager(db_path=str(tmp_path / "xianyu-chat.db"))

    ctx.record_cc_shipment(
        order_id="order-db-001",
        buyer_id="buyer-db",
        item_id="item-db",
        chat_id="chat-db",
        status="message_send_failed",
        delivery_message="兑换网址：https://jiyu.245334.xyz，卡密：CC-DB123-4567",
        error="socket closed",
    )
    rows = ctx.list_cc_shipments(status="message_send_failed", include_message=True)

    assert len(rows) == 1
    assert rows[0]["status"] == "message_send_failed"
    assert rows[0]["delivery_message"].endswith("CC-DB123-4567")
    assert rows[0]["delivery_preview"].startswith("兑换网址")
    assert "CC-DB123-4567" not in rows[0]["delivery_preview"]
    assert "CC-****" in rows[0]["delivery_preview"]
    summary = ctx.cc_shipment_summary()
    assert summary["total"] == 1
    assert summary["pending_rescue"] == 1
    by_order = ctx.get_cc_shipment_by_order_id("order-db-001", include_message=True)
    assert by_order["id"] == rows[0]["id"]
    assert by_order["delivery_message"].endswith("CC-DB123-4567")
    assert ctx.get_cc_shipment_by_order_id("") is None

    assert ctx.resolve_cc_shipment(rows[0]["id"], "已人工补发") is True
    resolved = ctx.list_cc_shipments(include_message=False)[0]
    assert resolved["status"] == "manually_resolved"
    assert resolved["resolve_note"] == "已人工补发"
    assert "delivery_message" not in resolved
    assert ctx.cc_shipment_summary()["pending_rescue"] == 0

    gate_before_real_order = ctx.cc_final_sale_gate_summary()
    assert gate_before_real_order["local_ready"] is False
    assert gate_before_real_order["sent_real_orders"] == 0

    ctx.record_cc_shipment(
        order_id="xy_oid_001_real_order",
        buyer_id="buyer-real",
        item_id="item-real",
        chat_id="chat-real",
        status="message_sent",
        delivery_message="兑换网址：https://jiyu.245334.xyz，卡密：CC-REAL",
        error="",
    )
    gate_after_real_order = ctx.cc_final_sale_gate_summary()
    assert gate_after_real_order["local_ready"] is True
    assert gate_after_real_order["sent_real_orders"] == 1
    assert gate_after_real_order["buyer_chain_verified_orders"] == 0
    assert gate_after_real_order["pending_rescue"] == 0
    assert gate_after_real_order["strict_audit_command"].endswith("--require-real-order")

    order_hash = hashlib.sha256(b"xy_oid_001_real_order").hexdigest()
    saved = ctx.record_cc_strict_audit(
        {
            "mode": "strict",
            "ok": True,
            "exit_code": 0,
            "summary": {
                "same_order_ready": 1,
                "same_order_matched": 1,
                "real_orders": 1,
                "redeemed_delta": 1,
                "active_token_delta": 1,
                "model_log_delta": 1,
                "same_order_latest": [{"orderIdPrefix": "xy_oid_0", "orderIdHash": order_hash, "ready": True}],
            },
            "stdout": "不要保存完整输出",
            "stderr": "不要保存错误输出",
        }
    )
    latest_audit = ctx.latest_cc_strict_audit()
    assert saved["ok"] is True
    assert latest_audit["same_order_ready"] == 1
    assert latest_audit["summary"]["same_order_latest"][0]["ready"] is True
    assert saved["marked_buyer_chain_verified"] == 1
    verified = ctx.list_cc_shipments(status="message_sent")[0]
    assert verified["buyer_chain_status"] == "verified"
    assert verified["buyer_chain_verified_at"]
    assert ctx.cc_shipment_summary()["buyer_chain_verified"] == 1
    assert ctx.cc_final_sale_gate_summary()["buyer_chain_verified_orders"] == 1
    assert "stdout" not in latest_audit
    assert "stderr" not in latest_audit


def test_strict_audit_ready_requires_xy_oid_real_order(tmp_path):
    """旧手工/浏览器补救单即使买家链路跑通，也不能解锁正式售卖。"""
    ctx = XianyuContextManager(db_path=str(tmp_path / "xianyu-chat.db"))
    old_ctx = xianyu_admin._ctx
    old_last = dict(xianyu_admin._last_cc_strict_audit)
    xianyu_admin._ctx = ctx
    xianyu_admin._last_cc_strict_audit.clear()
    try:
        ctx.record_cc_shipment(
            order_id="xy_manual_internal_test_order",
            buyer_id="buyer-manual",
            item_id="item-manual",
            chat_id="chat-manual",
            status="message_sent",
            delivery_message="兑换网址：https://jiyu.245334.xyz，卡密：CC-MANUAL",
            error="",
        )
        manual_hash = hashlib.sha256(b"xy_manual_internal_test_order").hexdigest()
        ctx.record_cc_strict_audit(
            {
                "mode": "strict",
                "ok": True,
                "exit_code": 0,
                "summary": {
                    "same_order_ready": 1,
                    "same_order_matched": 1,
                    "real_orders": 1,
                    "redeemed_delta": 1,
                    "active_token_delta": 1,
                    "model_log_delta": 1,
                    "same_order_latest": [{"orderIdPrefix": "xy_manual_", "orderIdHash": manual_hash, "ready": True}],
                },
            }
        )

        latest_manual = xianyu_admin._latest_strict_audit()
        assert latest_manual["real_orders"] == 0
        assert latest_manual["summary"]["real_orders"] == 0
        assert latest_manual["summary"]["display_note"] == "manual_or_browser_orders_are_internal_test_only"
        assert xianyu_admin._strict_audit_ready() is False
        progress = xianyu_admin._cc_buyer_chain_progress_summary()
        assert progress["stage"] == "waiting_paid_order"
        assert progress["counts"]["same_order_ready"] == 0

        ctx.record_cc_shipment(
            order_id="xy_oid_real_unlock_order",
            buyer_id="buyer-real",
            item_id="item-real",
            chat_id="chat-real",
            status="message_sent",
            delivery_message="兑换网址：https://jiyu.245334.xyz，卡密：CC-REAL",
            error="",
        )
        real_hash = hashlib.sha256(b"xy_oid_real_unlock_order").hexdigest()
        saved = ctx.record_cc_strict_audit(
            {
                "mode": "strict",
                "ok": True,
                "exit_code": 0,
                "summary": {
                    "same_order_ready": 1,
                    "same_order_matched": 1,
                    "real_orders": 1,
                    "redeemed_delta": 1,
                    "active_token_delta": 1,
                    "model_log_delta": 1,
                    "same_order_latest": [{"orderIdPrefix": "xy_oid_", "orderIdHash": real_hash, "ready": True}],
                },
            }
        )
        xianyu_admin._last_cc_strict_audit.clear()

        assert saved["marked_buyer_chain_verified"] == 1
        assert xianyu_admin._strict_audit_ready() is True
    finally:
        xianyu_admin._ctx = old_ctx
        xianyu_admin._last_cc_strict_audit.clear()
        xianyu_admin._last_cc_strict_audit.update(old_last)


def test_xianyu_context_updates_manual_ready_shipment_delivery_state(tmp_path):
    """自动发货绑定真实订单时，应更新原补救记录并保留已分配话术。"""
    ctx = XianyuContextManager(db_path=str(tmp_path / "xianyu-chat.db"))
    ctx.record_cc_shipment(
        order_id="xy_manual_before_real_order",
        buyer_id="手机截图已付款",
        item_id="item-poll",
        status="manual_delivery_ready",
        delivery_message="兑换网址：https://jiyu.245334.xyz，卡密：CC-MANUAL-KEEP",
    )
    shipment_id = ctx.list_cc_shipments(include_message=True)[0]["id"]

    updated = ctx.update_cc_shipment_delivery_state(
        shipment_id,
        "xy_oid_real_order",
        "buyer-real",
        "item-poll",
        "chat-real",
        "message_sent",
        "",
    )

    assert updated is True
    assert ctx.get_cc_shipment_by_order_id("xy_manual_before_real_order") is None
    real = ctx.get_cc_shipment_by_order_id("xy_oid_real_order", include_message=True)
    assert real["status"] == "message_sent"
    assert real["buyer_id"] == "buyer-real"
    assert real["chat_id"] == "chat-real"
    assert real["delivery_message"].endswith("CC-MANUAL-KEEP")
    assert ctx.cc_shipment_summary()["pending_rescue"] == 0


def test_xianyu_context_migrates_existing_cc_shipments_table(tmp_path):
    db_path = tmp_path / "xianyu-chat.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        """
        CREATE TABLE cc_shipments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id TEXT NOT NULL UNIQUE,
            chat_id TEXT DEFAULT '',
            buyer_id TEXT DEFAULT '',
            item_id TEXT DEFAULT '',
            status TEXT NOT NULL,
            delivery_message TEXT DEFAULT '',
            error TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now')),
            resolved_at TEXT DEFAULT '',
            resolve_note TEXT DEFAULT ''
        )
        """
    )
    conn.execute(
        "INSERT INTO cc_shipments(order_id,status) VALUES(?,?)",
        ("xy_existing_order", "message_sent"),
    )
    conn.commit()
    conn.close()

    ctx = XianyuContextManager(db_path=str(db_path))
    row = ctx.list_cc_shipments()[0]

    assert row["order_id"] == "xy_existing_order"
    assert row["buyer_chain_status"] == ""
    assert row["buyer_chain_verified_at"] == ""


def test_xianyu_context_tracks_cc_item_mappings(tmp_path):
    ctx = XianyuContextManager(db_path=str(tmp_path / "xianyu-chat.db"))

    saved = ctx.upsert_cc_item_mapping("item-001", "starter", "CC中转 日卡")

    assert saved["item_id"] == "item-001"
    assert saved["plan_id"] == "starter"
    assert saved["enabled"] is True
    assert ctx.get_cc_item_mapping("item-001")["plan_id"] == "starter"

    ctx.upsert_cc_item_mapping("item-001", "starter-off", "停用测试", enabled=False)
    assert ctx.get_cc_item_mapping("item-001") is None
    disabled = ctx.get_cc_item_mapping("item-001", enabled_only=False)
    assert disabled["plan_id"] == "starter-off"
    assert disabled["enabled"] is False
    assert len(ctx.list_cc_item_mappings(include_disabled=True)) == 1
    assert ctx.list_cc_item_mappings(include_disabled=False) == []
    assert ctx.delete_cc_item_mapping("item-001") is True
    assert ctx.delete_cc_item_mapping("item-001") is False


def test_xianyu_admin_cc_item_mapping_routes(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENCLAW_API_TOKEN", raising=False)
    monkeypatch.setenv("ENV", "development")
    monkeypatch.setenv("API_HOST", "127.0.0.1")
    monkeypatch.setattr("src.api.auth._API_TOKEN", "", raising=False)
    ctx = XianyuContextManager(db_path=str(tmp_path / "xianyu-chat.db"))
    old_ctx, old_live = xianyu_admin._ctx, xianyu_admin._live
    xianyu_admin._ctx = ctx
    xianyu_admin._live = None
    try:
        client = TestClient(xianyu_admin.app)
        ctx.save_item("item-cached-001", {"title": "CC中转 日卡", "price": "9.9"})
        items = client.get("/api/items")
        assert items.status_code == 200
        assert items.json()[0]["item_id"] == "item-cached-001"
        assert items.json()[0]["title"] == "CC中转 日卡"
        assert items.json()[0]["price"] == "9.9"

        create = client.post(
            "/api/cc-item-mappings",
            json={"item_id": "item-api", "plan_id": "starter", "title": "API测试", "enabled": True},
        )
        assert create.status_code == 200
        assert create.json()["plan_id"] == "starter"

        status = client.get("/api/status")
        assert status.status_code == 200
        assert status.json()["cc_item_mappings"] == {"total": 1, "enabled": 1}

        listed = client.get("/api/cc-item-mappings")
        assert listed.status_code == 200
        assert listed.json()[0]["item_id"] == "item-api"

        deleted = client.delete("/api/cc-item-mappings/item-api")
        assert deleted.status_code == 200
        assert client.get("/api/cc-item-mappings").json() == []
    finally:
        xianyu_admin._ctx = old_ctx
        xianyu_admin._live = old_live


def test_xianyu_admin_normalizes_full_goofish_share_text_for_mapping(tmp_path, monkeypatch):
    """老板可直接粘贴闲鱼完整分享文本，后台应自动剪出可绑定的短链接和分享码。"""
    monkeypatch.delenv("OPENCLAW_API_TOKEN", raising=False)
    monkeypatch.setenv("ENV", "development")
    monkeypatch.setenv("API_HOST", "127.0.0.1")
    monkeypatch.setattr("src.api.auth._API_TOKEN", "", raising=False)
    ctx = XianyuContextManager(db_path=str(tmp_path / "xianyu-chat.db"))
    old_ctx, old_live = xianyu_admin._ctx, xianyu_admin._live
    xianyu_admin._ctx = ctx
    xianyu_admin._live = None
    try:
        client = TestClient(xianyu_admin.app)
        share_text = (
            "【闲鱼】[https://m.tb.cn/h.RC4QcXM?tk=DxWwgNjrfdQ]"
            "(https://m.tb.cn/h.RC4QcXM?tk=DxWwgNjrfdQ) CZ007 「我在闲鱼发布了【测试】」\\n"
            "点击链接直接打开"
        )

        created = client.post(
            "/api/cc-item-mappings",
            json={"item_id": share_text, "plan_id": "test-plan", "title": "测试商品", "enabled": True},
        )

        assert created.status_code == 200
        assert created.json()["item_id"] == "https://m.tb.cn/h.RC4QcXM?tk=DxWwgNjrfdQ CZ007"
        assert ctx.get_cc_item_mapping("https://m.tb.cn/h.RC4QcXM?tk=DxWwgNjrfdQ CZ007")["plan_id"] == "test-plan"
        assert ctx.get_cc_item_mapping("https://m.tb.cn/h.RC4QcXM?tk=DxWwgNjrfdQ")["plan_id"] == "test-plan"
        assert ctx.get_cc_item_mapping(share_text)["plan_id"] == "test-plan"
    finally:
        xianyu_admin._ctx = old_ctx
        xianyu_admin._live = old_live


def test_manual_paid_order_trusted_browser_real_prefix_counts_as_xy_oid():
    """只有浏览器已付款页提取到真实订单号时，才允许转换为 xy_oid 严格门订单。"""
    raw_order_id = "123456789012345"
    req = xianyu_admin.CCManualPaidOrderRequest(order_id=f"xianyu-real:{raw_order_id}")

    order_id = xianyu_admin._manual_paid_order_id(req, "item-real")

    assert order_id == f"xy_oid_{hashlib.sha256(raw_order_id.encode()).hexdigest()[:16]}"


def test_manual_paid_order_browser_prefix_is_not_real_order_gate(tmp_path):
    """浏览器付款页兜底生成的订单可幂等发货，但不能冒充卖家订单接口真实订单。"""
    req = xianyu_admin.CCManualPaidOrderRequest(order_id="browser:https://m.tb.cn/h.RC4QcXM?tk=DxWwgNjrfdQ")
    order_id = xianyu_admin._manual_paid_order_id(req, "https://m.tb.cn/h.RC4QcXM?tk=DxWwgNjrfdQ")
    assert order_id.startswith("xy_browser_")

    ctx = XianyuContextManager(db_path=str(tmp_path / "xianyu-chat.db"))
    ctx.record_cc_shipment(
        order_id=order_id,
        buyer_id="浏览器已付款页面",
        item_id="https://m.tb.cn/h.RC4QcXM?tk=DxWwgNjrfdQ",
        status="message_sent",
        delivery_message="兑换码：CC-BROWSER",
    )
    gate = ctx.cc_final_sale_gate_summary()
    assert gate["sent_real_orders"] == 0
    assert gate["local_ready"] is False


def test_xianyu_admin_manual_paid_order_dispatch_creates_copyable_delivery(tmp_path, monkeypatch, fake_httpx):
    """闲鱼已付款推送漏掉时，老板可人工确认付款并生成可粘贴发货话术。"""
    monkeypatch.delenv("OPENCLAW_API_TOKEN", raising=False)
    monkeypatch.setenv("ENV", "development")
    monkeypatch.setenv("API_HOST", "127.0.0.1")
    monkeypatch.setenv("CC_XIANYU_WEBHOOK_URL", "https://cc.example.test/api/ops/xianyu/paid-order")
    monkeypatch.setenv("CC_XIANYU_WEBHOOK_TOKEN", "unit-test-token")
    monkeypatch.setattr("src.api.auth._API_TOKEN", "", raising=False)
    fake_httpx.response = FakeResponse(200, {"deliveryMessage": "兑换入口：https://jiyu.245334.xyz\n兑换码：CC-MANUAL"})
    ctx = XianyuContextManager(db_path=str(tmp_path / "xianyu-chat.db"))
    ctx.upsert_cc_item_mapping("https://m.tb.cn/h.RC4QcXM?tk=DxWwgNjrfdQ CZ007", "codex-30-day", "测试")
    old_ctx, old_live = xianyu_admin._ctx, xianyu_admin._live
    xianyu_admin._ctx = ctx
    xianyu_admin._live = None
    try:
        client = TestClient(xianyu_admin.app)

        created = client.post(
            "/api/cc-manual-paid-order/dispatch",
            json={
                "item_id": "【闲鱼】[https://m.tb.cn/h.RC4QcXM?tk=DxWwgNjrfdQ](https://m.tb.cn/h.RC4QcXM?tk=DxWwgNjrfdQ) CZ007 「测试」",
                "buyer_hint": "手机截图已付款",
                "product_title": "测试",
                "proof_note": "05:55 已付款截图",
            },
        )

        assert created.status_code == 200
        payload = created.json()
        assert payload["ok"] is True
        assert payload["status"] == "manual_delivery_ready"
        assert payload["deliveryMessage"].endswith("CC-MANUAL")
        assert payload["orderId"].startswith("xy_manual_")
        assert fake_httpx.calls[0]["json"]["planId"] == "codex-30-day"
        assert fake_httpx.calls[0]["json"]["paid"] is True
        rows = ctx.list_cc_shipments(include_message=True)
        assert rows[0]["status"] == "manual_delivery_ready"
        assert rows[0]["delivery_message"].endswith("CC-MANUAL")
        assert ctx.cc_shipment_summary()["pending_rescue"] == 1

        repeated = client.post(
            "/api/cc-manual-paid-order/dispatch",
            json={
                "item_id": "https://m.tb.cn/h.RC4QcXM?tk=DxWwgNjrfdQ CZ007",
                "buyer_hint": "手机截图已付款",
                "product_title": "测试",
                "proof_note": "05:55 已付款截图",
            },
        )
        assert repeated.status_code == 200
        assert repeated.json()["idempotent"] is True
        assert len(fake_httpx.calls) == 1
    finally:
        xianyu_admin._ctx = old_ctx
        xianyu_admin._live = old_live


def test_xianyu_admin_manual_paid_order_dispatch_does_not_resend_sent_shipment(tmp_path, monkeypatch, fake_httpx):
    """同一已付款页面如果已经发过卡密，后续巡检不能再次返回可发送话术。"""
    monkeypatch.delenv("OPENCLAW_API_TOKEN", raising=False)
    monkeypatch.setenv("ENV", "development")
    monkeypatch.setenv("API_HOST", "127.0.0.1")
    monkeypatch.setenv("CC_XIANYU_WEBHOOK_URL", "https://cc.example.test/api/ops/xianyu/paid-order")
    monkeypatch.setenv("CC_XIANYU_WEBHOOK_TOKEN", "unit-test-token")
    monkeypatch.setattr("src.api.auth._API_TOKEN", "", raising=False)
    fake_httpx.response = FakeResponse(
        200, {"deliveryMessage": "兑换入口：https://jiyu.245334.xyz\n兑换码：CC-SHOULD-NOT-CREATE"}
    )
    ctx = XianyuContextManager(db_path=str(tmp_path / "xianyu-chat.db"))
    item_id = "https://m.tb.cn/h.RC4QcXM?tk=DxWwgNjrfdQ"
    req = xianyu_admin.CCManualPaidOrderRequest(order_id=f"browser:{item_id}")
    order_id = xianyu_admin._manual_paid_order_id(req, item_id)
    ctx.upsert_cc_item_mapping(item_id, "xianyu-test-1", "1元测试")
    ctx.record_cc_shipment(
        order_id=order_id,
        buyer_id="浏览器已付款页面",
        item_id=item_id,
        status="message_sent",
        delivery_message="兑换入口：https://jiyu.245334.xyz\n兑换码：CC-ALREADY-SENT",
    )
    old_ctx, old_live = xianyu_admin._ctx, xianyu_admin._live
    xianyu_admin._ctx = ctx
    xianyu_admin._live = None
    try:
        client = TestClient(xianyu_admin.app)

        repeated = client.post(
            "/api/cc-manual-paid-order/dispatch",
            json={
                "order_id": f"browser:{item_id}",
                "item_id": item_id,
                "buyer_hint": "浏览器已付款页面",
                "product_title": "1元测试",
                "proof_note": "same paid page rescan",
            },
        )

        assert repeated.status_code == 200
        payload = repeated.json()
        assert payload["idempotent"] is True
        assert payload["alreadyHandled"] is True
        assert payload["status"] == "message_sent"
        assert payload["deliveryMessage"] == ""
        assert len(fake_httpx.calls) == 0
        rows = ctx.list_cc_shipments(include_message=True)
        assert len(rows) == 1
        assert rows[0]["delivery_message"].endswith("CC-ALREADY-SENT")
    finally:
        xianyu_admin._ctx = old_ctx
        xianyu_admin._live = old_live


def test_xianyu_admin_manual_paid_order_dispatch_adopts_browser_sent_shipment_to_real_order(
    tmp_path,
    monkeypatch,
    fake_httpx,
):
    """浏览器已发卡后识别到真实订单号时，只接管订单号，不再生成第二张卡。"""
    monkeypatch.delenv("OPENCLAW_API_TOKEN", raising=False)
    monkeypatch.setenv("ENV", "development")
    monkeypatch.setenv("API_HOST", "127.0.0.1")
    monkeypatch.setenv("CC_XIANYU_WEBHOOK_URL", "https://cc.example.test/api/ops/xianyu/paid-order")
    monkeypatch.setenv("CC_XIANYU_WEBHOOK_TOKEN", "unit-test-token")
    monkeypatch.setattr("src.api.auth._API_TOKEN", "", raising=False)
    fake_httpx.response = FakeResponse(200, {"ok": True})
    ctx = XianyuContextManager(db_path=str(tmp_path / "xianyu-chat.db"))
    item_id = "1065629676333"
    old_order_id = "xy_browser_already_sent_real_page"
    raw_real_order_id = "1234567890123456789"
    new_order_id = f"xy_oid_{hashlib.sha256(raw_real_order_id.encode()).hexdigest()[:16]}"
    ctx.upsert_cc_item_mapping(item_id, "xianyu-test-1", "1元测试")
    ctx.record_cc_shipment(
        order_id=old_order_id,
        buyer_id="浏览器桥接器已付款页面",
        item_id=item_id,
        status="message_sent",
        delivery_message="兑换入口：https://jiyu.245334.xyz\n兑换码：CC-ALREADY-SENT",
    )
    old_ctx, old_live = xianyu_admin._ctx, xianyu_admin._live
    xianyu_admin._ctx = ctx
    xianyu_admin._live = None
    try:
        client = TestClient(xianyu_admin.app)

        adopted = client.post(
            "/api/cc-manual-paid-order/dispatch",
            json={
                "order_id": f"xianyu-real:{raw_real_order_id}",
                "item_id": item_id,
                "buyer_hint": "浏览器桥接器已付款页面",
                "product_title": "1元测试",
                "proof_note": "headinfo real order",
                "one_shot": True,
            },
        )

        assert adopted.status_code == 200
        payload = adopted.json()
        assert payload["idempotent"] is True
        assert payload["alreadyHandled"] is True
        assert payload["orderId"] == new_order_id
        assert payload["status"] == "message_sent"
        assert payload["deliveryMessage"] == ""
        assert len(fake_httpx.calls) == 1
        assert fake_httpx.calls[0]["url"] == "https://cc.example.test/api/ops/xianyu/remap-order"
        assert fake_httpx.calls[0]["json"] == {"oldOrderId": old_order_id, "newOrderId": new_order_id}
        rows = ctx.list_cc_shipments(include_message=True)
        assert len(rows) == 1
        assert rows[0]["order_id"] == new_order_id
        assert rows[0]["delivery_message"].endswith("CC-ALREADY-SENT")
        assert ctx.cc_final_sale_gate_summary()["sent_real_orders"] == 1
    finally:
        xianyu_admin._ctx = old_ctx
        xianyu_admin._live = old_live


def test_xianyu_admin_manual_paid_order_mark_sent_clears_rescue_but_not_real_order_gate(tmp_path, monkeypatch):
    """人工粘贴发货后可清空补救队列，但不能冒充真实订单自动闭环证据。"""
    monkeypatch.delenv("OPENCLAW_API_TOKEN", raising=False)
    monkeypatch.setenv("ENV", "development")
    monkeypatch.setenv("API_HOST", "127.0.0.1")
    monkeypatch.setattr("src.api.auth._API_TOKEN", "", raising=False)
    ctx = XianyuContextManager(db_path=str(tmp_path / "xianyu-chat.db"))
    ctx.record_cc_shipment(
        order_id="xy_manual_test_paid_order",
        buyer_id="手机截图已付款",
        item_id="https://m.tb.cn/h.RC4QcXM?tk=DxWwgNjrfdQ CZ007",
        status="manual_delivery_ready",
        delivery_message="兑换入口：https://jiyu.245334.xyz\n兑换码：CC-MANUAL",
    )
    old_ctx, old_live = xianyu_admin._ctx, xianyu_admin._live
    xianyu_admin._ctx = ctx
    xianyu_admin._live = None
    try:
        shipment_id = ctx.list_cc_shipments(include_message=True)[0]["id"]
        client = TestClient(xianyu_admin.app)

        marked = client.post(f"/api/cc-shipments/{shipment_id}/mark-sent")

        assert marked.status_code == 200
        assert marked.json()["status"] == "message_sent"
        assert ctx.list_cc_shipments(include_message=True)[0]["status"] == "message_sent"
        gate = ctx.cc_final_sale_gate_summary()
        assert gate["local_ready"] is False
        assert gate["sent_real_orders"] == 0
        assert gate["pending_rescue"] == 0
    finally:
        xianyu_admin._ctx = old_ctx
        xianyu_admin._live = old_live


def test_xianyu_admin_resume_auto_ship_canary_pauses_after_first_sent(tmp_path, monkeypatch):
    """恢复常驻自动发货后，第 1 条真正发出的卡密会自动重新暂停，防止连续发卡。"""
    monkeypatch.delenv("OPENCLAW_API_TOKEN", raising=False)
    monkeypatch.setenv("ENV", "development")
    monkeypatch.setenv("API_HOST", "127.0.0.1")
    monkeypatch.setattr("src.api.auth._API_TOKEN", "", raising=False)
    monkeypatch.setattr(
        xianyu_admin,
        "_cc_auto_ship_resume_preflight",
        lambda: {
            "ok": True,
            "safe_to_resume": True,
            "nextAction": "可以恢复自动发货；恢复后建议先小流量观察。",
            "blockers": [],
        },
    )
    ctx = XianyuContextManager(db_path=str(tmp_path / "xianyu-chat.db"))
    ctx.record_cc_shipment(
        order_id="xy_oid_canary_order",
        buyer_id="buyer-canary",
        item_id="item-canary",
        status="manual_delivery_ready",
        delivery_message="兑换码：CC-CANARY",
    )
    old_ctx, old_live = xianyu_admin._ctx, xianyu_admin._live
    xianyu_admin._ctx = ctx
    xianyu_admin._live = None
    try:
        client = TestClient(xianyu_admin.app)
        resumed = client.post(
            "/api/cc-operator-mode",
            json={"auto_ship_paused": False, "reason": "unit test safe resume"},
        )
        assert resumed.status_code == 200
        assert resumed.json()["auto_ship_paused"] is False
        assert resumed.json()["auto_resume_canary_active"] is True
        assert get_operator_state()["auto_resume_canary"]["remaining"] == 1

        shipment_id = ctx.list_cc_shipments(include_message=True)[0]["id"]
        marked = client.post(f"/api/cc-shipments/{shipment_id}/mark-sent")

        assert marked.status_code == 200
        assert marked.json()["auto_resume_canary"]["paused"] is True
        state = get_operator_state()
        assert state["auto_ship_paused"] is True
        assert state["pause_reason"] == "恢复后首单已发送，系统自动暂停观察，防止连续发卡"
        assert state["auto_resume_canary"]["remaining"] == 0
        assert state["auto_resume_canary"]["last_order_id"] == "xy_oid_canary_order"
    finally:
        xianyu_admin._ctx = old_ctx
        xianyu_admin._live = old_live


def test_xianyu_admin_browser_send_manual_ready_route(tmp_path, monkeypatch):
    """本机管理台应提供浏览器助手发货入口，且必须带买家信息。"""
    monkeypatch.delenv("OPENCLAW_API_TOKEN", raising=False)
    monkeypatch.setenv("ENV", "development")
    monkeypatch.setenv("API_HOST", "127.0.0.1")
    monkeypatch.setattr("src.api.auth._API_TOKEN", "", raising=False)
    ctx = XianyuContextManager(db_path=str(tmp_path / "xianyu-chat.db"))
    send_manual = AsyncMock(
        return_value={
            "ok": True,
            "id": 21,
            "order_id": "xy_oid_browser_real_order",
            "buyer_id": "buyer-browser",
            "status": "message_sent",
        }
    )

    async def call_on_owner(operation: str, **kwargs):
        assert operation == "send_manual_ready_cc_shipment"
        assert kwargs.pop("timeout") == 45.0
        return await send_manual(**kwargs)

    fake_live = SimpleNamespace(
        send_manual_ready_cc_shipment=send_manual,
        call_on_owner=AsyncMock(side_effect=call_on_owner),
    )
    old_ctx, old_live = xianyu_admin._ctx, xianyu_admin._live
    xianyu_admin._ctx = ctx
    xianyu_admin._live = fake_live
    try:
        client = TestClient(xianyu_admin.app)

        missing = client.post("/api/cc-shipments/21/browser-send", json={"item_id": "item-browser"})
        assert missing.status_code == 400

        sent = client.post(
            "/api/cc-shipments/21/browser-send",
            json={
                "buyer_id": "buyer-browser",
                "item_id": "item-browser",
                "order_id": "xy_oid_browser_real_order",
            },
        )

        assert sent.status_code == 200
        assert sent.json()["status"] == "message_sent"
        fake_live.send_manual_ready_cc_shipment.assert_awaited_once_with(
            shipment_id=21,
            buyer_id="buyer-browser",
            item_id="item-browser",
            order_id="xy_oid_browser_real_order",
            chat_id="",
        )
    finally:
        xianyu_admin._ctx = old_ctx
        xianyu_admin._live = old_live


def test_xianyu_admin_browser_delivery_next_reuses_pending_message(tmp_path, monkeypatch):
    """浏览器助手只能读取已分配待发送话术，不能触发新卡密分配。"""
    monkeypatch.delenv("OPENCLAW_API_TOKEN", raising=False)
    monkeypatch.setenv("ENV", "development")
    monkeypatch.setenv("API_HOST", "127.0.0.1")
    monkeypatch.setattr("src.api.auth._API_TOKEN", "", raising=False)
    ctx = XianyuContextManager(db_path=str(tmp_path / "xianyu-chat.db"))
    ctx.record_cc_shipment(
        order_id="xy_manual_browser_pending",
        buyer_id="手机截图已付款",
        item_id="item-browser",
        chat_id="",
        status="manual_delivery_ready",
        delivery_message="兑换入口：https://jiyu.245334.xyz\n兑换码：CC-BROWSER-PENDING",
    )
    old_ctx, old_live = xianyu_admin._ctx, xianyu_admin._live
    xianyu_admin._ctx = ctx
    xianyu_admin._live = None
    try:
        client = TestClient(xianyu_admin.app)

        response = client.get("/api/cc-browser-delivery/next")

        assert response.status_code == 200
        payload = response.json()
        assert payload["hasPending"] is True
        assert payload["shipment"]["status"] == "browser_delivery_claimed"
        assert payload["shipment"]["deliveryMessage"].endswith("CC-BROWSER-PENDING")
        assert "CC-BROWSER-PENDING" not in payload["shipment"]["deliveryPreview"]
    finally:
        xianyu_admin._ctx = old_ctx
        xianyu_admin._live = old_live


def test_xianyu_admin_browser_delivery_next_claims_pending_once(tmp_path, monkeypatch):
    """同一条待发卡密被浏览器领取后，第二个发送器不能再次拿到完整话术。"""
    monkeypatch.delenv("OPENCLAW_API_TOKEN", raising=False)
    monkeypatch.setenv("ENV", "development")
    monkeypatch.setenv("API_HOST", "127.0.0.1")
    monkeypatch.setattr("src.api.auth._API_TOKEN", "", raising=False)
    ctx = XianyuContextManager(db_path=str(tmp_path / "xianyu-chat.db"))
    ctx.record_cc_shipment(
        order_id="xy_manual_browser_claim_once",
        buyer_id="手机截图已付款",
        item_id="item-browser",
        chat_id="",
        status="manual_delivery_ready",
        delivery_message="兑换入口：https://jiyu.245334.xyz\n兑换码：CC-CLAIM-ONCE",
    )
    old_ctx, old_live = xianyu_admin._ctx, xianyu_admin._live
    xianyu_admin._ctx = ctx
    xianyu_admin._live = None
    try:
        client = TestClient(xianyu_admin.app)

        first = client.get("/api/cc-browser-delivery/next")
        second = client.get("/api/cc-browser-delivery/next")

        assert first.status_code == 200
        first_payload = first.json()
        assert first_payload["hasPending"] is True
        assert first_payload["shipment"]["status"] == "browser_delivery_claimed"
        assert first_payload["shipment"]["deliveryMessage"].endswith("CC-CLAIM-ONCE")
        stored = ctx.get_cc_shipment(first_payload["shipment"]["id"], include_message=True)
        assert stored["status"] == "browser_delivery_claimed"

        assert second.status_code == 200
        second_payload = second.json()
        assert second_payload["hasPending"] is False
        assert second_payload["shipment"] is None
        assert "CC-CLAIM-ONCE" not in json.dumps(second_payload, ensure_ascii=False)
    finally:
        xianyu_admin._ctx = old_ctx
        xianyu_admin._live = old_live


def test_xianyu_admin_browser_delivery_next_respects_operator_pause(tmp_path, monkeypatch):
    """老板点暂停后，浏览器发货入口也不能继续返回卡密话术。"""
    monkeypatch.delenv("OPENCLAW_API_TOKEN", raising=False)
    monkeypatch.setenv("ENV", "development")
    monkeypatch.setenv("API_HOST", "127.0.0.1")
    monkeypatch.setattr("src.api.auth._API_TOKEN", "", raising=False)
    set_auto_ship_paused(True, "unit test pause")
    ctx = XianyuContextManager(db_path=str(tmp_path / "xianyu-chat.db"))
    ctx.record_cc_shipment(
        order_id="xy_manual_browser_paused",
        buyer_id="手机截图已付款",
        item_id="item-browser",
        chat_id="",
        status="manual_delivery_ready",
        delivery_message="兑换入口：https://jiyu.245334.xyz\n兑换码：CC-PAUSED-NO-SEND",
    )
    old_ctx, old_live = xianyu_admin._ctx, xianyu_admin._live
    xianyu_admin._ctx = ctx
    xianyu_admin._live = None
    try:
        client = TestClient(xianyu_admin.app)

        response = client.get("/api/cc-browser-delivery/next")

        assert response.status_code == 200
        payload = response.json()
        assert payload["hasPending"] is False
        assert payload["shipment"] is None
        assert payload["reason"] == "operator_paused"
        assert "CC-PAUSED-NO-SEND" not in json.dumps(payload, ensure_ascii=False)
        assert ctx.list_cc_shipments(include_message=True)[0]["status"] == "manual_delivery_ready"
    finally:
        xianyu_admin._ctx = old_ctx
        xianyu_admin._live = old_live


def test_xianyu_admin_one_shot_delivery_allows_exactly_one_claim_when_paused(tmp_path, monkeypatch):
    """老板暂停自动发货后，可单次放行一条浏览器话术，但第二次不能再拿到卡密。"""
    monkeypatch.delenv("OPENCLAW_API_TOKEN", raising=False)
    monkeypatch.setenv("ENV", "development")
    monkeypatch.setenv("API_HOST", "127.0.0.1")
    monkeypatch.setattr("src.api.auth._API_TOKEN", "", raising=False)
    set_auto_ship_paused(True, "unit test pause")
    ctx = XianyuContextManager(db_path=str(tmp_path / "xianyu-chat.db"))
    ctx.record_cc_shipment(
        order_id="xy_manual_browser_one_shot",
        buyer_id="手机截图已付款",
        item_id="item-browser",
        chat_id="",
        status="manual_delivery_ready",
        delivery_message="兑换入口：https://jiyu.245334.xyz\n兑换码：CC-ONE-SHOT",
    )
    old_ctx, old_live = xianyu_admin._ctx, xianyu_admin._live
    xianyu_admin._ctx = ctx
    xianyu_admin._live = None
    try:
        client = TestClient(xianyu_admin.app)

        blocked = client.get("/api/cc-browser-delivery/next")
        assert blocked.status_code == 200
        assert blocked.json()["reason"] == "operator_paused"
        assert "CC-ONE-SHOT" not in json.dumps(blocked.json(), ensure_ascii=False)

        authorized = client.post(
            "/api/cc-operator-mode/one-shot-delivery",
            json={"reason": "unit test one shot", "ttl_seconds": 180},
        )
        assert authorized.status_code == 200
        assert authorized.json()["auto_ship_paused"] is True
        assert authorized.json()["one_shot_delivery"]["active"] is True

        first = client.get("/api/cc-browser-delivery/next?one_shot=1")
        second = client.get("/api/cc-browser-delivery/next?one_shot=1")

        assert first.status_code == 200
        first_payload = first.json()
        assert first_payload["hasPending"] is True
        assert first_payload["shipment"]["deliveryMessage"].endswith("CC-ONE-SHOT")
        assert first_payload["oneShotDelivery"]["active"] is False

        assert second.status_code == 200
        second_payload = second.json()
        assert second_payload["hasPending"] is False
        assert "CC-ONE-SHOT" not in json.dumps(second_payload, ensure_ascii=False)
        assert ctx.list_cc_shipments(include_message=True)[0]["status"] == "browser_delivery_claimed"
    finally:
        xianyu_admin._ctx = old_ctx
        xianyu_admin._live = old_live


def test_xianyu_admin_one_shot_dispatch_consumes_gate_for_paid_page_fallback(
    tmp_path,
    monkeypatch,
    fake_httpx,
):
    """暂停状态下，浏览器已付款页兜底生成话术也必须消费单次放行票。"""
    monkeypatch.delenv("OPENCLAW_API_TOKEN", raising=False)
    monkeypatch.setenv("ENV", "development")
    monkeypatch.setenv("API_HOST", "127.0.0.1")
    monkeypatch.setenv("CC_XIANYU_WEBHOOK_URL", "https://cc.example.test/api/ops/xianyu/paid-order")
    monkeypatch.setenv("CC_XIANYU_WEBHOOK_TOKEN", "unit-test-token")
    monkeypatch.setattr("src.api.auth._API_TOKEN", "", raising=False)
    fake_httpx.response = FakeResponse(
        200, {"deliveryMessage": "兑换入口：https://jiyu.245334.xyz\n兑换码：CC-DISPATCH-ONE"}
    )
    set_auto_ship_paused(True, "unit test pause")
    ctx = XianyuContextManager(db_path=str(tmp_path / "xianyu-chat.db"))
    ctx.upsert_cc_item_mapping("item-real", "xianyu-test-1", "1元测试")
    old_ctx, old_live = xianyu_admin._ctx, xianyu_admin._live
    xianyu_admin._ctx = ctx
    xianyu_admin._live = None
    try:
        client = TestClient(xianyu_admin.app)

        unauthorized = client.post(
            "/api/cc-manual-paid-order/dispatch",
            json={
                "item_id": "item-real",
                "order_id": "xianyu-real:123456789012345",
                "buyer_hint": "浏览器桥接器已付款页面",
                "product_title": "1元测试",
                "proof_note": "paid page",
                "one_shot": True,
            },
        )
        assert unauthorized.status_code == 409
        assert len(fake_httpx.calls) == 0

        client.post(
            "/api/cc-operator-mode/one-shot-delivery",
            json={"reason": "unit test one shot dispatch", "ttl_seconds": 180},
        )
        created = client.post(
            "/api/cc-manual-paid-order/dispatch",
            json={
                "item_id": "item-real",
                "order_id": "xianyu-real:123456789012345",
                "buyer_hint": "浏览器桥接器已付款页面",
                "product_title": "1元测试",
                "proof_note": "paid page",
                "one_shot": True,
            },
        )

        assert created.status_code == 200
        payload = created.json()
        assert payload["orderId"].startswith("xy_oid_")
        assert payload["deliveryMessage"].endswith("CC-DISPATCH-ONE")
        assert payload["oneShotDelivery"]["active"] is False
        assert len(fake_httpx.calls) == 1

        repeated = client.post(
            "/api/cc-manual-paid-order/dispatch",
            json={
                "item_id": "item-real",
                "order_id": "xianyu-real:123456789012345",
                "buyer_hint": "浏览器桥接器已付款页面",
                "product_title": "1元测试",
                "proof_note": "paid page",
                "one_shot": True,
            },
        )
        assert repeated.status_code == 409
        assert len(fake_httpx.calls) == 1
    finally:
        xianyu_admin._ctx = old_ctx
        xianyu_admin._live = old_live


def test_xianyu_admin_one_shot_bridge_route_uses_delivery_only_mode(monkeypatch, tmp_path):
    """18800 一键跑当前页只能调用单次发卡模式，不能顺带确认发货或恢复上架。"""
    monkeypatch.delenv("OPENCLAW_API_TOKEN", raising=False)
    monkeypatch.setenv("ENV", "development")
    monkeypatch.setenv("API_HOST", "127.0.0.1")
    monkeypatch.setattr("src.api.auth._API_TOKEN", "", raising=False)
    calls = []

    class _Completed:
        returncode = 0
        stdout = json.dumps(
            {
                "ok": True,
                "mode": "one_shot_delivery_only",
                "deliveries": [{"ok": True, "stage": "sent", "shipmentId": 123}],
                "confirms": [],
                "relist": {"ok": True, "skipped": True},
            }
        )
        stderr = ""

    def _fake_run(command, **kwargs):
        calls.append({"command": command, "kwargs": kwargs})
        return _Completed()

    monkeypatch.setattr(xianyu_admin, "_seller_bridge_node_binary", lambda: "node")
    monkeypatch.setattr(xianyu_admin.subprocess, "run", _fake_run)
    client = TestClient(xianyu_admin.app)

    response = client.post(
        "/api/cc-seller-bridge/one-shot-delivery",
        json={"reason": "unit test"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["deliveryOnly"] is True
    assert payload["oneShot"] is True
    assert payload["deliveries"][0]["stage"] == "sent"
    assert len(calls) == 1
    command = calls[0]["command"]
    assert "--delivery-only" in command
    assert "--one-shot-override" in command
    assert "--require-single-xianyu-page" in command
    assert "--require-real-order-id" in command
    assert "--json" in command


def test_xianyu_admin_seller_bridge_page_scan_is_read_only(monkeypatch):
    """18800 当前页检查只能调用只读扫描模式，不允许顺带发卡。"""
    monkeypatch.delenv("OPENCLAW_API_TOKEN", raising=False)
    monkeypatch.setenv("ENV", "development")
    monkeypatch.setenv("API_HOST", "127.0.0.1")
    monkeypatch.setattr("src.api.auth._API_TOKEN", "", raising=False)
    calls = []

    class _Completed:
        returncode = 1
        stdout = json.dumps(
            {
                "ok": False,
                "mode": "scan_only",
                "readOnly": True,
                "xianyuTabs": 1,
                "readyPages": 0,
                "scans": [
                    {
                        "title": "闲鱼 - 闲不住？上闲鱼！",
                        "url": "https://www.goofish.com/",
                        "readyToSend": False,
                        "reason": "no_paid_order_signal",
                    }
                ],
            }
        )
        stderr = ""

    def _fake_run(command, **kwargs):
        calls.append({"command": command, "kwargs": kwargs})
        return _Completed()

    monkeypatch.setattr(xianyu_admin, "_seller_bridge_node_binary", lambda: "node")
    monkeypatch.setattr(xianyu_admin.subprocess, "run", _fake_run)
    client = TestClient(xianyu_admin.app)

    response = client.get("/api/cc-seller-bridge/page-scan")

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["readOnly"] is True
    assert payload["scanCompleted"] is True
    assert payload["notReady"] is True
    assert "error" not in payload
    assert payload["mode"] == "scan_only"
    assert payload["readyPages"] == 0
    assert "闲鱼首页" in payload["nextAction"]
    assert len(calls) == 1
    command = calls[0]["command"]
    assert "--scan-only" in command
    assert "--require-real-order-id" in command
    assert "--json" in command
    assert "--one-shot-override" not in command
    assert "--delivery-only" not in command


def test_xianyu_admin_seller_bridge_page_scan_guides_im_list(monkeypatch):
    """只读检查停在闲鱼消息列表时，要提示点进已付款买家，而不是泛泛报未命中。"""
    monkeypatch.delenv("OPENCLAW_API_TOKEN", raising=False)
    monkeypatch.setenv("ENV", "development")
    monkeypatch.setenv("API_HOST", "127.0.0.1")
    monkeypatch.setattr("src.api.auth._API_TOKEN", "", raising=False)

    class _Completed:
        returncode = 0
        stdout = json.dumps(
            {
                "ok": False,
                "mode": "scan_only",
                "readOnly": True,
                "xianyuTabs": 1,
                "readyPages": 0,
                "strictReadyPages": 0,
                "scans": [
                    {
                        "title": "聊天_闲鱼",
                        "url": "https://www.goofish.com/im?spm=a21ybx.seo.sitemap.3",
                        "paidSignal": False,
                        "inputReady": False,
                        "orderIdHintPresent": False,
                        "readyToSend": False,
                        "strictReadyToSend": False,
                        "reason": "no_paid_order_signal",
                    }
                ],
            }
        )
        stderr = ""

    monkeypatch.setattr(xianyu_admin, "_seller_bridge_node_binary", lambda: "node")
    monkeypatch.setattr(xianyu_admin.subprocess, "run", lambda *_args, **_kwargs: _Completed())
    client = TestClient(xianyu_admin.app)

    response = client.get("/api/cc-seller-bridge/page-scan")

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["scanCompleted"] is True
    assert payload["notReady"] is True
    assert "闲鱼消息页" in payload["nextAction"]
    assert "左侧会话列表" in payload["nextAction"]
    assert "已付款买家" in payload["nextAction"]


def test_xianyu_admin_seller_bridge_page_scan_guides_paid_order_card(monkeypatch):
    """看到待发货订单卡但缺订单号时，要告诉老板点订单卡/去发货入口。"""
    monkeypatch.delenv("OPENCLAW_API_TOKEN", raising=False)
    monkeypatch.setenv("ENV", "development")
    monkeypatch.setenv("API_HOST", "127.0.0.1")
    monkeypatch.setattr("src.api.auth._API_TOKEN", "", raising=False)

    class _Completed:
        returncode = 0
        stdout = json.dumps(
            {
                "ok": False,
                "mode": "scan_only",
                "readOnly": True,
                "xianyuTabs": 1,
                "readyPages": 0,
                "strictReadyPages": 0,
                "scans": [
                    {
                        "title": "聊天_闲鱼",
                        "url": "https://www.goofish.com/im?spm=a21ybx.seo.sitemap.3",
                        "paidSignal": True,
                        "inputReady": False,
                        "orderIdHintPresent": False,
                        "orderCardPresent": True,
                        "shipActionPresent": False,
                        "readyToSend": False,
                        "strictReadyToSend": False,
                        "reason": "no_chat_input_found",
                    }
                ],
            }
        )
        stderr = ""

    monkeypatch.setattr(xianyu_admin, "_seller_bridge_node_binary", lambda: "node")
    monkeypatch.setattr(xianyu_admin.subprocess, "run", lambda *_args, **_kwargs: _Completed())
    client = TestClient(xianyu_admin.app)

    response = client.get("/api/cc-seller-bridge/page-scan")

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["scanCompleted"] is True
    assert payload["notReady"] is True
    assert "等待卖家发货" in payload["nextAction"]
    assert "订单卡" in payload["nextAction"]
    assert "去发货" in payload["nextAction"]


def test_xianyu_admin_seller_bridge_open_page_only_navigates(monkeypatch):
    """18800 打开闲鱼消息只能导航卖家 Chromium，不能顺带发卡或单次放行。"""
    monkeypatch.delenv("OPENCLAW_API_TOKEN", raising=False)
    monkeypatch.setenv("ENV", "development")
    monkeypatch.setenv("API_HOST", "127.0.0.1")
    monkeypatch.setattr("src.api.auth._API_TOKEN", "", raising=False)
    calls = []

    class _Completed:
        returncode = 0
        stdout = json.dumps(
            {
                "ok": True,
                "mode": "open_page_only",
                "destination": "im",
                "url": "https://www.goofish.com/im?spm=a21ybx.seo.sitemap.3",
                "openedIn": "existing_tab",
                "broughtFront": True,
                "nextAction": "卖家 Chromium 已打开对应闲鱼页面。",
            }
        )
        stderr = ""

    def _fake_run(command, **kwargs):
        calls.append({"command": command, "kwargs": kwargs})
        return _Completed()

    monkeypatch.setattr(xianyu_admin, "_seller_bridge_node_binary", lambda: "node")
    monkeypatch.setattr(xianyu_admin.subprocess, "run", _fake_run)
    client = TestClient(xianyu_admin.app)

    response = client.post(
        "/api/cc-seller-bridge/open-page",
        json={"destination": "im", "reason": "unit test"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["openPageOnly"] is True
    assert payload["deliveryOnly"] is False
    assert payload["oneShot"] is False
    assert payload["destination"] == "im"
    assert payload["broughtFront"] is True
    assert len(calls) == 1
    command = calls[0]["command"]
    assert "--open-page=im" in command
    assert "--json" in command
    assert "--delivery-only" not in command
    assert "--one-shot-override" not in command
    assert "--require-real-order-id" not in command


def test_xianyu_admin_mark_send_failed_releases_claimed_delivery(tmp_path, monkeypatch):
    """浏览器领取后如果页面发送失败，必须退回失败队列，避免永久卡住。"""
    monkeypatch.delenv("OPENCLAW_API_TOKEN", raising=False)
    monkeypatch.setenv("ENV", "development")
    monkeypatch.setenv("API_HOST", "127.0.0.1")
    monkeypatch.setattr("src.api.auth._API_TOKEN", "", raising=False)
    ctx = XianyuContextManager(db_path=str(tmp_path / "xianyu-chat.db"))
    ctx.record_cc_shipment(
        order_id="xy_manual_browser_claim_failed",
        buyer_id="手机截图已付款",
        item_id="item-browser",
        chat_id="",
        status="browser_delivery_claimed",
        delivery_message="兑换入口：https://jiyu.245334.xyz\n兑换码：CC-CLAIM-FAILED",
    )
    shipment_id = ctx.list_cc_shipments(include_message=True)[0]["id"]
    old_ctx, old_live = xianyu_admin._ctx, xianyu_admin._live
    xianyu_admin._ctx = ctx
    xianyu_admin._live = None
    try:
        client = TestClient(xianyu_admin.app)

        response = client.post(
            f"/api/cc-shipments/{shipment_id}/mark-send-failed",
            json={"error": "输入框没找到，未发送"},
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["status"] == "message_send_failed"
        row = ctx.get_cc_shipment(shipment_id, include_message=True)
        assert row["status"] == "message_send_failed"
        assert "输入框没找到" in row["error"]
    finally:
        xianyu_admin._ctx = old_ctx
        xianyu_admin._live = old_live


def test_xianyu_admin_browser_delivery_next_ignores_already_sent_messages(tmp_path, monkeypatch):
    """已发送过的卡密即使数据库还保留完整话术，也不能再次进入浏览器待发送队列。"""
    monkeypatch.delenv("OPENCLAW_API_TOKEN", raising=False)
    monkeypatch.setenv("ENV", "development")
    monkeypatch.setenv("API_HOST", "127.0.0.1")
    monkeypatch.setattr("src.api.auth._API_TOKEN", "", raising=False)
    ctx = XianyuContextManager(db_path=str(tmp_path / "xianyu-chat.db"))
    ctx.record_cc_shipment(
        order_id="xy_browser_already_sent",
        buyer_id="浏览器已付款页面",
        item_id="item-browser",
        chat_id="",
        status="message_sent",
        delivery_message="兑换入口：https://jiyu.245334.xyz\n兑换码：CC-ALREADY-SENT",
    )
    old_ctx, old_live = xianyu_admin._ctx, xianyu_admin._live
    xianyu_admin._ctx = ctx
    xianyu_admin._live = None
    try:
        client = TestClient(xianyu_admin.app)

        response = client.get("/api/cc-browser-delivery/next")

        assert response.status_code == 200
        payload = response.json()
        assert payload["hasPending"] is False
        assert payload["shipment"] is None
        assert "CC-ALREADY-SENT" not in json.dumps(payload, ensure_ascii=False)
    finally:
        xianyu_admin._ctx = old_ctx
        xianyu_admin._live = old_live


def test_xianyu_admin_confirm_shipment_queue_returns_sent_unconfirmed_order(tmp_path, monkeypatch):
    """发货话术已发送后，应进入“闲鱼确认发货”队列，供浏览器助手点击发货按钮。"""
    monkeypatch.delenv("OPENCLAW_API_TOKEN", raising=False)
    monkeypatch.setenv("ENV", "development")
    monkeypatch.setenv("API_HOST", "127.0.0.1")
    monkeypatch.setattr("src.api.auth._API_TOKEN", "", raising=False)
    ctx = XianyuContextManager(db_path=str(tmp_path / "xianyu-chat.db"))
    ctx.record_cc_shipment(
        order_id="123456789012345",
        buyer_id="buyer-browser",
        item_id="item-browser",
        chat_id="chat-browser",
        status="message_sent",
        delivery_message="兑换入口：https://jiyu.245334.xyz\n兑换码：CC-CONFIRM-PENDING",
    )
    old_ctx, old_live = xianyu_admin._ctx, xianyu_admin._live
    xianyu_admin._ctx = ctx
    xianyu_admin._live = None
    try:
        client = TestClient(xianyu_admin.app)

        response = client.get("/api/cc-xianyu-confirm/next")

        assert response.status_code == 200
        payload = response.json()
        assert payload["hasPending"] is True
        assert payload["shipment"]["id"] == ctx.list_cc_shipments()[0]["id"]
        assert payload["shipment"]["orderId"] == "123456789012345"
        assert payload["shipment"]["status"] == "message_sent"
        assert "CC-CONFIRM-PENDING" not in payload["shipment"]["deliveryPreview"]
        assert "点击闲鱼发货" in payload["nextAction"]
    finally:
        xianyu_admin._ctx = old_ctx
        xianyu_admin._live = old_live


def test_xianyu_admin_confirm_shipment_queue_skips_manual_orders(tmp_path, monkeypatch):
    """手工兜底单没有真实闲鱼数字订单号，不能进入自动点击发货按钮队列。"""
    monkeypatch.delenv("OPENCLAW_API_TOKEN", raising=False)
    monkeypatch.setenv("ENV", "development")
    monkeypatch.setenv("API_HOST", "127.0.0.1")
    monkeypatch.setattr("src.api.auth._API_TOKEN", "", raising=False)
    ctx = XianyuContextManager(db_path=str(tmp_path / "xianyu-chat.db"))
    ctx.record_cc_shipment(
        order_id="xy_manual_need_confirm",
        buyer_id="buyer-browser",
        item_id="item-browser",
        chat_id="chat-browser",
        status="message_sent",
        delivery_message="兑换入口：https://jiyu.245334.xyz\n兑换码：CC-MANUAL-PENDING",
    )
    old_ctx, old_live = xianyu_admin._ctx, xianyu_admin._live
    xianyu_admin._ctx = ctx
    xianyu_admin._live = None
    try:
        client = TestClient(xianyu_admin.app)

        response = client.get("/api/cc-xianyu-confirm/next")

        assert response.status_code == 200
        payload = response.json()
        assert payload["hasPending"] is False
        shipment = ctx.get_cc_shipment_by_order_id("xy_manual_need_confirm")
        assert shipment["xianyu_confirm_status"] == "skipped"
        assert "不是闲鱼数字订单号" in shipment["xianyu_confirm_error"]
    finally:
        xianyu_admin._ctx = old_ctx
        xianyu_admin._live = old_live


def test_xianyu_admin_current_page_confirm_candidate_allows_manual_remediation(tmp_path, monkeypatch):
    """已发卡密的手工内测单可走当前页面补救确认发货，但仍不算正式订单。"""
    monkeypatch.delenv("OPENCLAW_API_TOKEN", raising=False)
    monkeypatch.setenv("ENV", "development")
    monkeypatch.setenv("API_HOST", "127.0.0.1")
    monkeypatch.setattr("src.api.auth._API_TOKEN", "", raising=False)
    ctx = XianyuContextManager(db_path=str(tmp_path / "xianyu-chat.db"))
    ctx.record_cc_shipment(
        order_id="xy_manual_need_page_confirm",
        buyer_id="手机截图已付款",
        item_id="https://m.tb.cn/h.RC4QcXM?tk=DxWwgNjrfdQ CZ007",
        chat_id="",
        status="message_sent",
        delivery_message="兑换入口：https://jiyu.245334.xyz\n兑换码：CC-MANUAL-PAGE",
    )
    old_ctx, old_live = xianyu_admin._ctx, xianyu_admin._live
    xianyu_admin._ctx = ctx
    xianyu_admin._live = None
    try:
        client = TestClient(xianyu_admin.app)

        strict_queue = client.get("/api/cc-xianyu-confirm/next")
        assert strict_queue.status_code == 200
        assert strict_queue.json()["hasPending"] is False

        candidate = client.get(
            "/api/cc-xianyu-confirm/current-page-candidate",
            params={"item_id": "https://m.tb.cn/h.RC4QcXM?tk=DxWwgNjrfdQ CZ007"},
        )

        assert candidate.status_code == 200
        payload = candidate.json()
        assert payload["hasPending"] is True
        assert payload["queueType"] == "current_page_remediation"
        assert payload["shipment"]["orderId"] == "xy_manual_need_page_confirm"
        assert "内测补救" in payload["nextAction"]
        summary = ctx.cc_shipment_summary()
        assert summary["xianyu_confirm_page_pending"] == 0
        gate = ctx.cc_final_sale_gate_summary()
        assert gate["sent_real_orders"] == 0
        assert gate["local_ready"] is False
    finally:
        xianyu_admin._ctx = old_ctx
        xianyu_admin._live = old_live


def test_cc_shipment_summary_excludes_skipped_manual_confirm_from_page_pending(tmp_path):
    """已跳过确认发货的手工内测单，不应在老板首页显示为待点发货。"""
    ctx = XianyuContextManager(db_path=str(tmp_path / "xianyu-chat.db"))
    ctx.record_cc_shipment(
        order_id="xy_manual_skipped_confirm",
        buyer_id="manual-buyer",
        item_id="item-manual",
        status="message_sent",
        delivery_message="兑换码：CC-SKIPPED",
    )
    ctx.mark_cc_shipment_xianyu_confirm(
        "xy_manual_skipped_confirm",
        "skipped",
        "不是闲鱼数字订单号，未进入浏览器确认发货队列",
    )

    summary = ctx.cc_shipment_summary()

    assert summary["xianyu_confirm_page_pending"] == 0
    assert summary["xianyu_confirm_pending"] == 0


def test_xianyu_admin_confirm_shipment_mark_routes_update_status(tmp_path, monkeypatch):
    """浏览器助手点击闲鱼发货后，应能回写确认结果，失败也要可追踪。"""
    monkeypatch.delenv("OPENCLAW_API_TOKEN", raising=False)
    monkeypatch.setenv("ENV", "development")
    monkeypatch.setenv("API_HOST", "127.0.0.1")
    monkeypatch.setattr("src.api.auth._API_TOKEN", "", raising=False)
    ctx = XianyuContextManager(db_path=str(tmp_path / "xianyu-chat.db"))
    ctx.record_cc_shipment(
        order_id="123456789012346",
        buyer_id="buyer-browser",
        item_id="item-browser",
        status="message_sent",
        delivery_message="兑换码：CC-CONFIRM-MARK",
    )
    old_ctx, old_live = xianyu_admin._ctx, xianyu_admin._live
    xianyu_admin._ctx = ctx
    xianyu_admin._live = None
    try:
        client = TestClient(xianyu_admin.app)
        shipment_id = ctx.list_cc_shipments()[0]["id"]

        failed = client.post(
            f"/api/cc-shipments/{shipment_id}/mark-xianyu-confirm-failed",
            json={"error": "页面缺少确认按钮"},
        )
        assert failed.status_code == 200
        after_failed = ctx.get_cc_shipment(shipment_id)
        assert after_failed["xianyu_confirm_status"] == "failed"
        assert after_failed["xianyu_confirm_error"] == "页面缺少确认按钮"

        confirmed = client.post(f"/api/cc-shipments/{shipment_id}/mark-xianyu-confirmed")

        assert confirmed.status_code == 200
        assert confirmed.json()["status"] == "confirmed"
        after_confirmed = ctx.get_cc_shipment(shipment_id)
        assert after_confirmed["xianyu_confirm_status"] == "confirmed"
        assert after_confirmed["xianyu_confirm_at"]
    finally:
        xianyu_admin._ctx = old_ctx
        xianyu_admin._live = old_live


def test_xianyu_admin_backend_confirm_is_disabled_by_default(tmp_path, monkeypatch):
    """后端 H5 确认发货默认关闭，避免误改真实闲鱼订单。"""
    monkeypatch.delenv("OPENCLAW_API_TOKEN", raising=False)
    monkeypatch.setenv("ENV", "development")
    monkeypatch.setenv("API_HOST", "127.0.0.1")
    monkeypatch.setattr("src.api.auth._API_TOKEN", "", raising=False)
    ctx = XianyuContextManager(db_path=str(tmp_path / "xianyu-chat.db"))
    ctx.record_cc_shipment(
        order_id="123456789012399",
        buyer_id="buyer-backend-confirm",
        item_id="item-backend-confirm",
        status="message_sent",
        delivery_message="兑换码：CC-BACKEND-CONFIRM",
    )
    old_ctx, old_live = xianyu_admin._ctx, xianyu_admin._live
    xianyu_admin._ctx = ctx
    xianyu_admin._live = None
    try:
        client = TestClient(xianyu_admin.app)
        shipment_id = ctx.list_cc_shipments()[0]["id"]

        response = client.post(f"/api/cc-shipments/{shipment_id}/confirm-xianyu-backend")

        assert response.status_code == 200
        payload = response.json()
        assert payload["ok"] is False
        assert payload["skipped"] is True
        assert payload["reason"] == "disabled"
        after = ctx.get_cc_shipment(shipment_id)
        assert after["xianyu_confirm_status"] in ("", None)
    finally:
        xianyu_admin._ctx = old_ctx
        xianyu_admin._live = old_live


def test_xianyu_admin_backend_confirm_only_confirms_numeric_order(tmp_path, monkeypatch):
    """H5 后端确认发货只处理真实数字订单，手工/浏览器内测单必须跳过。"""
    monkeypatch.delenv("OPENCLAW_API_TOKEN", raising=False)
    monkeypatch.setenv("ENV", "development")
    monkeypatch.setenv("API_HOST", "127.0.0.1")
    monkeypatch.setenv("CC_XIANYU_AUTO_CONFIRM_SHIPMENT_ENABLED", "1")
    monkeypatch.setattr("src.api.auth._API_TOKEN", "", raising=False)
    ctx = XianyuContextManager(db_path=str(tmp_path / "xianyu-chat.db"))
    ctx.record_cc_shipment(
        order_id="123456789012398",
        buyer_id="buyer-backend-confirm",
        item_id="item-backend-confirm",
        status="message_sent",
        delivery_message="兑换码：CC-BACKEND-CONFIRM",
    )
    ctx.record_cc_shipment(
        order_id="xy_manual_backend_confirm",
        buyer_id="buyer-manual",
        item_id="item-manual",
        status="message_sent",
        delivery_message="兑换码：CC-MANUAL-BACKEND-CONFIRM",
    )

    class FakeBackendConfirmApis:
        seen_order_ids: list[str] = []

        def __init__(self, cookies_str: str):
            self.cookies_str = cookies_str

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def confirm_dummy_shipment(self, order_id: str):
            self.__class__.seen_order_ids.append(order_id)
            return {"success": True, "order_id": order_id, "cookies_str": self.cookies_str}

    monkeypatch.setattr("src.xianyu.xianyu_admin.XianyuApis", FakeBackendConfirmApis)
    old_ctx, old_live = xianyu_admin._ctx, xianyu_admin._live
    xianyu_admin._ctx = ctx
    xianyu_admin._live = SimpleNamespace(cookies_str="_m_h5_tk=token_123; unb=seller-001")
    try:
        client = TestClient(xianyu_admin.app)
        rows = {row["order_id"]: row for row in ctx.list_cc_shipments(limit=10)}

        manual_response = client.post(
            f"/api/cc-shipments/{rows['xy_manual_backend_confirm']['id']}/confirm-xianyu-backend"
        )
        numeric_response = client.post(f"/api/cc-shipments/{rows['123456789012398']['id']}/confirm-xianyu-backend")

        assert manual_response.status_code == 200
        assert manual_response.json()["reason"] == "non_numeric_order_id"
        assert numeric_response.status_code == 200
        assert numeric_response.json()["ok"] is True
        assert numeric_response.json()["status"] == "confirmed"
        assert FakeBackendConfirmApis.seen_order_ids == ["123456789012398"]
        assert ctx.get_cc_shipment_by_order_id("xy_manual_backend_confirm")["xianyu_confirm_status"] == "skipped"
        assert ctx.get_cc_shipment_by_order_id("123456789012398")["xianyu_confirm_status"] == "confirmed"
    finally:
        xianyu_admin._ctx = old_ctx
        xianyu_admin._live = old_live


def test_xianyu_admin_relist_next_queue_only_after_confirmed(tmp_path, monkeypatch):
    """恢复上架队列只领取已发卡且确认发货完成的记录。"""
    monkeypatch.delenv("OPENCLAW_API_TOKEN", raising=False)
    monkeypatch.setenv("ENV", "development")
    monkeypatch.setenv("API_HOST", "127.0.0.1")
    monkeypatch.setattr("src.api.auth._API_TOKEN", "", raising=False)
    ctx = XianyuContextManager(db_path=str(tmp_path / "xianyu-chat.db"))
    ctx.record_cc_shipment(
        order_id="xy_oid_pending_confirm",
        buyer_id="buyer-pending",
        item_id="item-pending",
        status="message_sent",
        delivery_message="兑换码：CC-PENDING",
    )
    ctx.record_cc_shipment(
        order_id="xy_oid_ready_relist",
        buyer_id="buyer-ready",
        item_id="item-ready",
        status="message_sent",
        delivery_message="兑换码：CC-READY",
    )
    ctx.mark_cc_shipment_xianyu_confirm("xy_oid_ready_relist", "confirmed", "")
    old_ctx, old_live = xianyu_admin._ctx, xianyu_admin._live
    xianyu_admin._ctx = ctx
    xianyu_admin._live = None
    try:
        client = TestClient(xianyu_admin.app)
        response = client.get("/api/cc-xianyu-relist/next")

        assert response.status_code == 200
        body = response.json()
        assert body["hasPending"] is True
        assert body["shipment"]["orderId"] == "xy_oid_ready_relist"
        assert body["shipment"]["itemId"] == "item-ready"
    finally:
        xianyu_admin._ctx = old_ctx
        xianyu_admin._live = old_live


def test_xianyu_admin_relist_simulation_mode_allows_manual_sent_without_confirm(tmp_path, monkeypatch):
    """模拟门恢复上架可以领取已发卡的替换单，但默认生产队列仍要求确认发货。"""
    monkeypatch.delenv("OPENCLAW_API_TOKEN", raising=False)
    monkeypatch.setenv("ENV", "development")
    monkeypatch.setenv("API_HOST", "127.0.0.1")
    monkeypatch.setattr("src.api.auth._API_TOKEN", "", raising=False)
    ctx = XianyuContextManager(db_path=str(tmp_path / "xianyu-chat.db"))
    ctx.record_cc_shipment(
        order_id="xy_manual_relist_simulation",
        buyer_id="replacement-buyer",
        item_id="item-simulation-relist",
        status="message_sent",
        delivery_message="兑换码：CC-SIM-RELIST",
    )
    ctx.mark_cc_shipment_xianyu_confirm("xy_manual_relist_simulation", "skipped", "模拟门不点击最终发货按钮")
    old_ctx, old_live = xianyu_admin._ctx, xianyu_admin._live
    xianyu_admin._ctx = ctx
    xianyu_admin._live = None
    try:
        client = TestClient(xianyu_admin.app)

        production_queue = client.get("/api/cc-xianyu-relist/next")
        simulation_queue = client.get("/api/cc-xianyu-relist/next", params={"mode": "simulation"})

        assert production_queue.status_code == 200
        assert production_queue.json()["hasPending"] is False
        assert simulation_queue.status_code == 200
        payload = simulation_queue.json()
        assert payload["hasPending"] is True
        assert payload["queueType"] == "simulation_relist"
        assert payload["shipment"]["orderId"] == "xy_manual_relist_simulation"
        assert payload["shipment"]["itemId"] == "item-simulation-relist"
        assert "不点击最终发货按钮" in payload["nextAction"]
        assert ctx.cc_final_sale_gate_summary()["sent_real_orders"] == 0
    finally:
        xianyu_admin._ctx = old_ctx
        xianyu_admin._live = old_live


def test_xianyu_admin_relist_online_verified_counts_for_simulation_gate(tmp_path, monkeypatch):
    """商品页已经在线时，可回写 online_verified 并满足模拟门的发布/上架核验。"""
    monkeypatch.delenv("OPENCLAW_API_TOKEN", raising=False)
    monkeypatch.setenv("ENV", "development")
    monkeypatch.setenv("API_HOST", "127.0.0.1")
    monkeypatch.setattr("src.api.auth._API_TOKEN", "", raising=False)
    ctx = XianyuContextManager(db_path=str(tmp_path / "xianyu-chat.db"))
    order_id = "xy_manual_online_verified"
    ctx.record_cc_shipment(
        order_id=order_id,
        buyer_id="buyer-browser",
        item_id="item-online",
        status="message_sent",
        delivery_message="兑换码：CC-ONLINE",
    )
    ctx.record_cc_strict_audit(
        {
            "mode": "strict",
            "ok": True,
            "exit_code": 0,
            "summary": {
                "same_order_ready": 1,
                "same_order_matched": 1,
                "real_orders": 1,
                "redeemed_delta": 1,
                "active_token_delta": 1,
                "model_log_delta": 1,
                "same_order_latest": [
                    {
                        "orderIdPrefix": "xy_manual_",
                        "orderIdHash": hashlib.sha256(order_id.encode()).hexdigest(),
                        "newApiRedeemed": True,
                        "activeTokens": 1,
                        "modelLogsAfterRedeem": 1,
                        "ready": True,
                    }
                ],
            },
        }
    )
    old_ctx, old_live = xianyu_admin._ctx, xianyu_admin._live
    old_readiness = dict(xianyu_admin._last_cc_readiness_audit)
    old_strict = dict(xianyu_admin._last_cc_strict_audit)
    xianyu_admin._ctx = ctx
    xianyu_admin._live = None
    xianyu_admin._last_cc_readiness_audit.clear()
    xianyu_admin._last_cc_readiness_audit.update(
        {
            "overall_ok": True,
            "oracle": True,
            "buyer_self_service_ok": True,
            "ccswitch_entry_ok": True,
            "newapi_enabled_channels": 3,
        }
    )
    xianyu_admin._last_cc_strict_audit.clear()
    try:
        client = TestClient(xianyu_admin.app)
        shipment_id = ctx.list_cc_shipments()[0]["id"]

        response = client.post(f"/api/cc-shipments/{shipment_id}/mark-relisted", json={"status": "online_verified"})

        assert response.status_code == 200
        assert response.json()["status"] == "online_verified"
        gate = client.get("/api/cc-simulation-gate").json()
        steps = {step["key"]: step for step in gate["steps"]}
        assert steps["product_relisted"]["ok"] is True
        assert gate["simulation_gate_ok"] is True
        assert gate["can_unlock_public_sale"] is False
        assert xianyu_admin._strict_audit_ready() is False
    finally:
        xianyu_admin._ctx = old_ctx
        xianyu_admin._live = old_live
        xianyu_admin._last_cc_readiness_audit.clear()
        xianyu_admin._last_cc_readiness_audit.update(old_readiness)
        xianyu_admin._last_cc_strict_audit.clear()
        xianyu_admin._last_cc_strict_audit.update(old_strict)


def test_xianyu_admin_relist_mark_routes_update_status(tmp_path, monkeypatch):
    """买家确认收货后，如商品页已下架，浏览器助手恢复上架后应回写记录。"""
    monkeypatch.delenv("OPENCLAW_API_TOKEN", raising=False)
    monkeypatch.setenv("ENV", "development")
    monkeypatch.setenv("API_HOST", "127.0.0.1")
    monkeypatch.setattr("src.api.auth._API_TOKEN", "", raising=False)
    ctx = XianyuContextManager(db_path=str(tmp_path / "xianyu-chat.db"))
    ctx.record_cc_shipment(
        order_id="xy_oid_relist_mark",
        buyer_id="buyer-browser",
        item_id="item-browser",
        status="message_sent",
        delivery_message="兑换码：CC-RELIST-MARK",
    )
    old_ctx, old_live = xianyu_admin._ctx, xianyu_admin._live
    xianyu_admin._ctx = ctx
    xianyu_admin._live = None
    try:
        client = TestClient(xianyu_admin.app)
        shipment_id = ctx.list_cc_shipments()[0]["id"]

        failed = client.post(
            f"/api/cc-shipments/{shipment_id}/mark-relist-failed",
            json={"error": "页面没有重新上架按钮"},
        )
        assert failed.status_code == 200
        after_failed = ctx.get_cc_shipment(shipment_id)
        assert after_failed["xianyu_relist_status"] == "failed"
        assert after_failed["xianyu_relist_error"] == "页面没有重新上架按钮"

        relisted = client.post(f"/api/cc-shipments/{shipment_id}/mark-relisted")

        assert relisted.status_code == 200
        assert relisted.json()["status"] == "relisted"
        after_relisted = ctx.get_cc_shipment(shipment_id)
        assert after_relisted["xianyu_relist_status"] == "relisted"
        assert after_relisted["xianyu_relist_at"]
    finally:
        xianyu_admin._ctx = old_ctx
        xianyu_admin._live = old_live


def test_operator_next_action_points_manual_ready_to_chrome_watch(tmp_path, monkeypatch):
    """已分配待发送话术时，老板下一步应指向聊天页插件看守，而不是泛泛等待后台。"""
    monkeypatch.delenv("OPENCLAW_API_TOKEN", raising=False)
    monkeypatch.setenv("ENV", "development")
    monkeypatch.setenv("API_HOST", "127.0.0.1")
    configure_cc_webhook(monkeypatch)
    monkeypatch.setattr("src.api.auth._API_TOKEN", "", raising=False)
    ctx = XianyuContextManager(db_path=str(tmp_path / "xianyu-chat.db"))
    ctx.record_cc_shipment(
        order_id="xy_manual_need_browser_watch",
        buyer_id="手机截图已付款",
        item_id="https://m.tb.cn/h.RC4QcXM?tk=DxWwgNjrfdQ CZ007",
        status="manual_delivery_ready",
        delivery_message="兑换入口：https://jiyu.245334.xyz\n兑换码：CC-MANUAL",
    )
    old_ctx, old_live = xianyu_admin._ctx, xianyu_admin._live
    xianyu_admin._ctx = ctx
    xianyu_admin._live = SimpleNamespace(
        runtime_snapshot_sync=lambda timeout=5.0: {
            "ws_connected": True,
            "cookie_ok": True,
            "last_heartbeat": 0.0,
            "token_ts": 0.0,
            "manual_chats": 0,
        }
    )
    try:
        client = TestClient(xianyu_admin.app)

        mode = client.get("/api/cc-operator-mode").json()
        action = client.get("/api/cc-operator-next-action").json()

        assert mode["stage"] == "rescue_required"
        assert "看守当前聊天页" in mode["next_action"]
        assert "Chrome 插件" in mode["next_action"]
        assert action["state"] == "rescue_required"
        assert "看守当前聊天页" in action["primary_action"]
        assert "等待后台自动补发" not in action["primary_action"]
    finally:
        xianyu_admin._ctx = old_ctx
        xianyu_admin._live = old_live


def test_xianyu_status_reports_chrome_extension_global_watch_capability(tmp_path, monkeypatch):
    """操作台应能告诉老板 Chrome 插件是否已刷新到全局看守版本。"""
    status_file = tmp_path / "social-extension.json"
    monkeypatch.setattr(xianyu_admin, "_SOCIAL_EXTENSION_STATUS_FILE", status_file)
    monkeypatch.setattr(
        xianyu_admin,
        "_cc_social_pilot_install_summary",
        lambda: {
            "detected": False,
            "source": "not_found",
            "expected_path": "/repo/packages/openclaw-npm/assets/chrome-extension",
        },
    )

    missing = xianyu_admin._cc_chrome_extension_summary()
    assert missing["needs_refresh_for_global_watch"] is True
    assert missing["social_pilot_installed"] is False
    assert "make cc-seller-chrome" in missing["next_action"]
    assert "加载运行版插件目录" in missing["next_action"]

    status_file.write_text(
        json.dumps(
            {
                "online": True,
                "platform": "x",
                "updated_at": "2026-07-06T20:20:00-0400",
                "extension": {
                    "manifest_version": "",
                    "cc_delivery_helper_version": "",
                    "capabilities": {},
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    old_payload = xianyu_admin._cc_chrome_extension_summary()
    assert old_payload["needs_refresh_for_global_watch"] is True
    assert old_payload["social_pilot_installed"] is False
    assert "make cc-seller-chrome" in old_payload["next_action"]
    assert "加载运行版插件目录" in old_payload["next_action"]

    status_file.write_text(
        json.dumps(
            {
                "online": True,
                "platform": "xianyu",
                "updated_at": "2026-07-06T20:20:00-0400",
                "extension": {
                    "manifest_version": "0.2.1",
                    "cc_delivery_helper_version": "2026-07-06-global-watch",
                    "capabilities": {
                        "all_open_xianyu_tabs_watch": True,
                        "single_pending_global_gate": True,
                        "target_tab_preflight": True,
                        "xianyu_relist_item": True,
                        "relist_queue_watch": True,
                        "paid_page_dispatch": True,
                    },
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    ready = xianyu_admin._cc_chrome_extension_summary()
    assert ready["needs_refresh_for_global_watch"] is False
    assert ready["social_pilot_installed"] is False
    assert ready["supports_global_watch"] is True
    assert ready["supports_target_tab_preflight"] is True
    assert ready["supports_paid_page_dispatch"] is True
    assert ready["supports_relist_queue"] is True
    assert ready["manifest_version"] == "0.2.1"


def test_xianyu_admin_cors_allows_chrome_extension_origin():
    """浏览器发货助手需要从插件页访问 18800 操作台。"""
    client = TestClient(xianyu_admin.app)

    response = client.options(
        "/api/status",
        headers={
            "Origin": "chrome-extension://abcdefghijklmnopabcdefghijklmnop",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "x-api-token, content-type",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "chrome-extension://abcdefghijklmnopabcdefghijklmnop"


def test_xianyu_admin_cors_rejects_unlisted_web_origin():
    """不能为了浏览器助手把 18800 操作台开放给任意网页。"""
    client = TestClient(xianyu_admin.app)

    response = client.options(
        "/api/status",
        headers={
            "Origin": "https://evil.example",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "x-api-token, content-type",
        },
    )

    assert response.status_code == 400


def test_xianyu_status_reports_local_bridge_next_action(tmp_path, monkeypatch):
    """本机桥接器接管时，操作台提示要说人话，不再要求刷新插件。"""
    status_file = tmp_path / "social-extension.json"
    monkeypatch.setattr(xianyu_admin, "_SOCIAL_EXTENSION_STATUS_FILE", status_file)
    monkeypatch.setattr(
        xianyu_admin,
        "_cc_social_pilot_install_summary",
        lambda: {
            "detected": True,
            "source": "running_chrome_process",
            "expected_path": "/repo/packages/openclaw-npm/assets/chrome-extension",
        },
    )
    status_file.write_text(
        json.dumps(
            {
                "online": True,
                "platform": "xianyu",
                "updated_at": "2026-07-07T09:20:00-0600",
                "extension": {
                    "manifest_version": "bridge",
                    "cc_delivery_helper_version": "2026-07-07-local-devtools-bridge",
                    "capabilities": {
                        "all_open_xianyu_tabs_watch": True,
                        "single_pending_global_gate": True,
                        "target_tab_preflight": True,
                        "xianyu_relist_item": True,
                        "relist_queue_watch": True,
                        "paid_page_dispatch": True,
                    },
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    summary = xianyu_admin._cc_chrome_extension_summary()

    assert summary["needs_refresh_for_global_watch"] is False
    assert "本机卖家桥接器已接管" in summary["next_action"]


def test_xianyu_status_detects_social_pilot_loaded_by_launch_argument(tmp_path, monkeypatch):
    """专用卖家 Chrome 用 --load-extension 启动时，即使未写 Preferences 也应识别为已加载。"""
    extension_dir = tmp_path / "packages/openclaw-npm/assets/chrome-extension"
    extension_dir.mkdir(parents=True)
    monkeypatch.setattr(xianyu_admin, "_SOCIAL_PILOT_EXTENSION_DIR", extension_dir)
    monkeypatch.setenv("CC_XIANYU_CHROME_PROFILE_DIR", str(tmp_path / "seller-profile"))
    monkeypatch.setattr(
        xianyu_admin.subprocess,
        "check_output",
        lambda *args, **kwargs: f"Google Chrome --load-extension={extension_dir} --user-data-dir=/tmp/seller",
    )

    summary = xianyu_admin._cc_social_pilot_install_summary()

    assert summary["detected"] is True
    assert summary["source"] == "running_chrome_process"
    assert summary["expected_path"] == str(extension_dir)


def test_xianyu_status_marks_stale_chrome_extension_heartbeat_offline(tmp_path, monkeypatch):
    """插件心跳过期时不能继续显示在线，避免旧状态误导生产检查。"""
    status_file = tmp_path / "social-extension.json"
    monkeypatch.setattr(xianyu_admin, "_SOCIAL_EXTENSION_STATUS_FILE", status_file)
    monkeypatch.setattr(
        xianyu_admin,
        "_cc_social_pilot_install_summary",
        lambda: {
            "detected": True,
            "source": "chrome_preferences",
            "expected_path": "/repo/packages/openclaw-npm/assets/chrome-extension",
        },
    )
    status_file.write_text(
        json.dumps(
            {
                "online": True,
                "platform": "xianyu",
                "updated_at": "2026-07-06T20:20:00-0400",
                "extension": {
                    "manifest_version": "0.2.1",
                    "cc_delivery_helper_version": "2026-07-07-background-heartbeat",
                    "capabilities": {
                        "all_open_xianyu_tabs_watch": True,
                        "single_pending_global_gate": True,
                        "target_tab_preflight": True,
                        "xianyu_relist_item": True,
                        "relist_queue_watch": True,
                        "paid_page_dispatch": True,
                    },
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    old_ts = time.time() - 3600
    os.utime(status_file, (old_ts, old_ts))

    stale = xianyu_admin._cc_chrome_extension_summary()

    assert stale["online"] is False
    assert stale["needs_refresh_for_global_watch"] is True
    assert "心跳已过期" in stale["next_action"]


def test_ops_notification_payload_prioritizes_low_inventory(monkeypatch):
    """本机提醒会把低库存提到老板可见层，不泄露任何卡密或 token。"""
    monkeypatch.setenv("CC_XIANYU_LOW_INVENTORY_THRESHOLD", "3")
    snapshot = {
        "next_action": {
            "severity": "warning",
            "state": "run_real_small_order",
            "title": "生产内测可发货，等待真实小额单",
            "primary_action": "发布 1 个小额闲鱼测试商品，完成真实付款；系统会自动发卡。",
        },
        "status": {
            "ws_connected": True,
            "cookie_ok": True,
            "cc_shipments": {"pending_rescue": 0},
        },
        "sale_lock": {
            "can_public_sale": False,
            "inventory": {"unused_cards": 2},
        },
        "loop_watch": {"stage": "waiting_paid_order"},
        "buyer_progress": {"stage": "waiting_paid_order"},
    }

    payload = xianyu_admin._build_ops_notification(snapshot)

    assert payload["severity"] == "warning"
    assert payload["low_inventory"] is True
    assert payload["title"] == "兑换码库存偏低"
    assert "2" in payload["body"]
    assert "token" not in payload["body"].lower()


def test_ops_notification_payload_prioritizes_buyer_chain_stall_over_low_inventory(monkeypatch):
    """真实订单发货后，提醒应优先告诉老板买家卡在哪一步。"""
    monkeypatch.setenv("CC_XIANYU_LOW_INVENTORY_THRESHOLD", "3")
    snapshot = {
        "next_action": {
            "severity": "warning",
            "state": "waiting_model_call",
            "title": "买家自助链路未跑完",
            "primary_action": "提醒买家导入 CC Switch 后选择模型测试一次。",
        },
        "status": {
            "ws_connected": True,
            "cookie_ok": True,
            "cc_shipments": {"pending_rescue": 0},
        },
        "sale_lock": {
            "can_public_sale": False,
            "inventory": {"unused_cards": 1},
        },
        "loop_watch": {"stage": "waiting_buyer_chain"},
        "buyer_progress": {
            "stage": "waiting_model_call",
            "steps": {
                "paid_order_shipped": True,
                "card_redeemed": True,
                "api_key_created": True,
                "model_called": False,
            },
        },
    }

    payload = xianyu_admin._build_ops_notification(snapshot)

    assert payload["severity"] == "warning"
    assert payload["state"] == "waiting_model_call"
    assert payload["buyer_attention_stage"] == "waiting_model_call"
    assert payload["low_inventory"] is True
    assert payload["title"] == "买家尚未调模型"
    assert "CC Switch" in payload["body"]


def test_ops_notification_payload_reports_buyer_chain_verified():
    """严格门转绿时，本机提醒应明确真实单闭环已完成。"""
    snapshot = {
        "next_action": {
            "severity": "ok",
            "state": "public_sale_ready",
            "title": "正式售卖已放行",
            "primary_action": "可以小批量正式售卖。",
        },
        "status": {
            "ws_connected": True,
            "cookie_ok": True,
            "cc_shipments": {"pending_rescue": 0},
        },
        "sale_lock": {
            "can_public_sale": True,
            "inventory": {"unused_cards": 5},
        },
        "loop_watch": {"stage": "closed_loop_verified"},
        "buyer_progress": {"stage": "verified"},
    }

    payload = xianyu_admin._build_ops_notification(snapshot)

    assert payload["severity"] == "ok"
    assert payload["state"] == "buyer_chain_verified"
    assert payload["buyer_attention_stage"] == "verified"
    assert payload["title"] == "真实单买家闭环已通过"


def test_ops_notify_check_route_force_sends_dry_run_notification(monkeypatch):
    """GUI 的“发送当前状态提醒”按钮走真实路由，测试中用 dry-run 防止弹窗。"""
    monkeypatch.delenv("OPENCLAW_API_TOKEN", raising=False)
    monkeypatch.setenv("ENV", "development")
    monkeypatch.setenv("API_HOST", "127.0.0.1")
    monkeypatch.setenv("CC_XIANYU_OPS_NOTIFY_DRY_RUN", "1")
    monkeypatch.setattr("src.api.auth._API_TOKEN", "", raising=False)
    monkeypatch.setattr(
        xianyu_admin,
        "_cc_ops_snapshot_summary",
        lambda: {
            "next_action": {
                "severity": "warning",
                "state": "run_real_small_order",
                "title": "生产内测可发货，等待真实小额单",
                "primary_action": "发布 1 个小额闲鱼测试商品，完成真实付款；系统会自动发卡。",
            },
            "status": {
                "ws_connected": True,
                "cookie_ok": True,
                "cc_shipments": {"pending_rescue": 0},
            },
            "sale_lock": {
                "can_public_sale": False,
                "inventory": {"unused_cards": 5},
            },
            "loop_watch": {"stage": "waiting_paid_order"},
            "buyer_progress": {"stage": "waiting_paid_order"},
        },
    )

    client = TestClient(xianyu_admin.app)
    response = client.post("/api/cc-ops-notify/check?force=true")

    assert response.status_code == 200
    data = response.json()
    assert data["ran"] is True
    assert data["changed"] is True
    assert data["sent"] is True
    assert data["send"]["dry_run"] is True
    assert data["payload"]["state"] == "run_real_small_order"


def test_xianyu_admin_dashboard_alias_points_to_owner_console(monkeypatch):
    """老板只记 /dashboard 入口即可打开本机统一操作台。"""
    monkeypatch.delenv("OPENCLAW_API_TOKEN", raising=False)
    monkeypatch.setenv("ENV", "development")
    monkeypatch.setenv("API_HOST", "127.0.0.1")
    monkeypatch.setattr("src.api.auth._API_TOKEN", "", raising=False)

    client = TestClient(xianyu_admin.app)
    response = client.get("/dashboard")

    assert response.status_code == 200
    assert "统一运营入口" in response.text
    assert "闲鱼售卖" in response.text
    assert "每日简报" in response.text
    assert "系统维护" in response.text
    assert "帮助中心" in response.text
    assert "替换模式模拟验收" in response.text
    assert "导出状态报告" in response.text


def test_xianyu_admin_export_status_returns_redacted_support_report(tmp_path, monkeypatch):
    """老板导出的状态报告应能发给技术支持，且不包含卡密和 token。"""
    monkeypatch.delenv("OPENCLAW_API_TOKEN", raising=False)
    monkeypatch.setenv("ENV", "development")
    monkeypatch.setenv("API_HOST", "127.0.0.1")
    monkeypatch.setattr("src.api.auth._API_TOKEN", "", raising=False)
    ctx = XianyuContextManager(db_path=str(tmp_path / "xianyu-chat.db"))
    ctx.record_cc_shipment(
        order_id="xy_manual_support_report",
        buyer_id="补牙牙牙牙牙牙牙牙",
        item_id="item-support",
        status="manual_delivery_ready",
        delivery_message="兑换入口：https://jiyu.245334.xyz\n兑换码：SECRET-CARD-001\nAPI Key：sk-secret",
        error="等待发送",
    )
    old_ctx, old_live = xianyu_admin._ctx, xianyu_admin._live
    xianyu_admin._ctx = ctx
    xianyu_admin._live = SimpleNamespace(ws=SimpleNamespace(open=True), _cookie_ok=True)
    try:
        client = TestClient(xianyu_admin.app)
        response = client.get("/api/export-status")

        assert response.status_code == 200
        report = response.json()
        dumped = json.dumps(report, ensure_ascii=False)
        assert report["ok"] is True
        assert "operator_summary" in report
        assert report["queues"]["pending_rescue"] == 1
        assert "SECRET-CARD-001" not in dumped
        assert "sk-secret" not in dumped
        assert "OPENCLAW_API_TOKEN" not in dumped
        assert "补牙牙牙" not in dumped
        assert "联系技术支持时，把这个 JSON 发过去" in report["plain_language_next_step"]
    finally:
        xianyu_admin._ctx = old_ctx
        xianyu_admin._live = old_live


def test_xianyu_admin_simulation_gate_tracks_strict_like_steps_without_unlocking(tmp_path, monkeypatch):
    """严格模拟门应追踪除真实下单/最终点发货外的闭环证据，但永远不解锁正式售卖。"""
    monkeypatch.delenv("OPENCLAW_API_TOKEN", raising=False)
    monkeypatch.setenv("ENV", "development")
    monkeypatch.setenv("API_HOST", "127.0.0.1")
    monkeypatch.setattr("src.api.auth._API_TOKEN", "", raising=False)
    ctx = XianyuContextManager(db_path=str(tmp_path / "xianyu-chat.db"))
    order_id = "xy_manual_replacement_strict_like"
    ctx.record_cc_shipment(
        order_id=order_id,
        buyer_id="补牙牙牙牙牙牙牙牙",
        item_id="https://m.tb.cn/h.RC4QcXM?tk=DxWwgNjrfdQ CZ007",
        chat_id="chat-replacement-buyer",
        status="message_sent",
        delivery_message="兑换入口：https://jiyu.245334.xyz\n兑换码：CC-REPLACE-SECRET\nAPI Key：sk-secret",
        error="",
    )
    ctx.mark_cc_shipment_xianyu_relist(order_id, "relisted", "")
    manual_hash = hashlib.sha256(order_id.encode()).hexdigest()
    ctx.record_cc_strict_audit(
        {
            "mode": "strict",
            "ok": True,
            "exit_code": 0,
            "summary": {
                "same_order_ready": 1,
                "same_order_matched": 1,
                "real_orders": 1,
                "redeemed_delta": 1,
                "active_token_delta": 1,
                "model_log_delta": 2,
                "same_order_latest": [
                    {
                        "orderIdPrefix": "xy_manual_",
                        "orderIdHash": manual_hash,
                        "newApiRedeemed": True,
                        "activeTokens": 1,
                        "modelLogsAfterRedeem": 2,
                        "ready": True,
                    }
                ],
            },
        }
    )
    old_ctx, old_live = xianyu_admin._ctx, xianyu_admin._live
    old_readiness = dict(xianyu_admin._last_cc_readiness_audit)
    old_strict = dict(xianyu_admin._last_cc_strict_audit)
    xianyu_admin._ctx = ctx
    xianyu_admin._live = SimpleNamespace(ws=SimpleNamespace(open=True), _cookie_ok=True)
    xianyu_admin._last_cc_readiness_audit.clear()
    xianyu_admin._last_cc_readiness_audit.update(
        {
            "overall_ok": True,
            "oracle": True,
            "buyer_self_service_ok": True,
            "ccswitch_entry_ok": True,
            "newapi_enabled_channels": 3,
            "public_main_http": 200,
            "public_models_no_auth_http": 401,
            "public_webhook_no_token_http": 401,
        }
    )
    xianyu_admin._last_cc_strict_audit.clear()
    try:
        client = TestClient(xianyu_admin.app)
        response = client.get("/api/cc-simulation-gate")

        assert response.status_code == 200
        gate = response.json()
        dumped = json.dumps(gate, ensure_ascii=False)
        steps = {step["key"]: step for step in gate["steps"]}
        excluded = {step["key"]: step for step in gate["excluded_steps"]}

        assert gate["ok"] is True
        assert gate["mode"] == "strict_simulation"
        assert gate["simulation_gate_ok"] is True
        assert gate["can_unlock_public_sale"] is False
        assert gate["strict_gate_required_prefix"] == "xy_oid_"
        assert gate["latest_simulation_order"]["order"].startswith("xy_manual_")
        assert steps["card_sent_to_buyer"]["ok"] is True
        assert steps["product_publish_package"]["ok"] is True
        assert steps["product_relisted"]["ok"] is True
        assert steps["public_redeemed"]["ok"] is True
        assert steps["api_key_created"]["ok"] is True
        assert steps["ccswitch_import_ready"]["ok"] is True
        assert steps["terminal_model_call"]["ok"] is True
        assert steps["channel_server_status"]["ok"] is True
        assert excluded["real_buyer_payment"]["ok"] is False
        assert excluded["final_xianyu_ship_click"]["ok"] is False
        assert xianyu_admin._strict_audit_ready() is False
        assert "CC-REPLACE-SECRET" not in dumped
        assert "sk-secret" not in dumped
        assert "补牙牙牙" not in dumped
    finally:
        xianyu_admin._ctx = old_ctx
        xianyu_admin._live = old_live
        xianyu_admin._last_cc_readiness_audit.clear()
        xianyu_admin._last_cc_readiness_audit.update(old_readiness)
        xianyu_admin._last_cc_strict_audit.clear()
        xianyu_admin._last_cc_strict_audit.update(old_strict)


def test_xianyu_admin_replacement_mode_pack_keeps_public_sale_locked(tmp_path, monkeypatch):
    """替换模式只能证明本地流程可演练，不能替代 xy_oid_* 真实订单严格门。"""
    monkeypatch.delenv("OPENCLAW_API_TOKEN", raising=False)
    monkeypatch.setenv("ENV", "development")
    monkeypatch.setenv("API_HOST", "127.0.0.1")
    monkeypatch.setattr("src.api.auth._API_TOKEN", "", raising=False)
    ctx = XianyuContextManager(db_path=str(tmp_path / "xianyu-chat.db"))
    ctx.record_cc_shipment(
        order_id="xy_manual_replacement_mode",
        buyer_id="replacement-buyer",
        item_id="item-replacement",
        status="message_sent",
        delivery_message="兑换入口：https://jiyu.245334.xyz\n兑换码：CC-REPLACE",
        error="",
    )
    old_ctx, old_live = xianyu_admin._ctx, xianyu_admin._live
    xianyu_admin._ctx = ctx
    xianyu_admin._live = None
    try:
        client = TestClient(xianyu_admin.app)
        response = client.get("/api/cc-replacement-mode-test-pack")

        assert response.status_code == 200
        pack = response.json()
        assert pack["ok"] is True
        assert pack["mode"] == "replacement_simulation"
        assert pack["can_unlock_public_sale"] is False
        assert pack["strict_gate_required_prefix"] == "xy_oid_"
        assert pack["checklist"][0]["label"] == "模拟买家下单"
        assert any(item["label"] == "终端真实调用测试" for item in pack["checklist"])
        assert "不替代真实小额订单" in pack["owner_warning"]
    finally:
        xianyu_admin._ctx = old_ctx
        xianyu_admin._live = old_live


def test_xianyu_admin_paid_order_probe_failure_gives_plain_next_action(tmp_path, monkeypatch):
    """只读扫单失败时，应告诉老板走浏览器当前页兜底，而不是只显示技术错误。"""
    monkeypatch.delenv("OPENCLAW_API_TOKEN", raising=False)
    monkeypatch.setenv("ENV", "development")
    monkeypatch.setenv("API_HOST", "127.0.0.1")
    monkeypatch.setattr("src.api.auth._API_TOKEN", "", raising=False)
    ctx = XianyuContextManager(db_path=str(tmp_path / "xianyu-chat.db"))
    scan_paid_orders = AsyncMock(
        return_value={
            "ok": False,
            "read_only": True,
            "reason": "xianyu_order_api_failed",
            "error": "PERMISSION_EXCEPTION::无权限访问",
            "processed": 0,
            "candidates": [],
            "next_action": "闲鱼卖家订单读取失败，请确认登录态和卖家页面是否正常。",
        }
    )

    async def call_on_owner(operation: str, **kwargs):
        assert operation == "scan_cc_paid_orders_readonly"
        assert kwargs.pop("timeout") == 30.0
        return await scan_paid_orders(**kwargs)

    fake_live = SimpleNamespace(
        scan_cc_paid_orders_readonly=scan_paid_orders,
        call_on_owner=AsyncMock(side_effect=call_on_owner),
    )
    old_ctx, old_live = xianyu_admin._ctx, xianyu_admin._live
    xianyu_admin._ctx = ctx
    xianyu_admin._live = fake_live
    try:
        client = TestClient(xianyu_admin.app)

        response = client.get("/api/cc-paid-order-probe")

        assert response.status_code == 200
        payload = response.json()
        assert payload["ok"] is False
        assert payload["readOnly"] is True
        assert "无权限访问" in payload["error"]
        assert "浏览器" in payload["nextAction"]
        assert "不会发卡" in payload["nextAction"]
        assert ctx.list_cc_shipments(include_message=True) == []
    finally:
        xianyu_admin._ctx = old_ctx
        xianyu_admin._live = old_live


@pytest.mark.parametrize(
    ("failure", "expected_status", "expected_text"),
    [
        (OwnerLoopNotReady("owner not ready"), 503, "尚未就绪"),
        (OwnerLoopTimeout("owner timeout"), 504, "后台核对"),
    ],
)
def test_xianyu_admin_paid_order_probe_maps_owner_boundary_failures(
    tmp_path, monkeypatch, failure, expected_status, expected_text
):
    """所有者循环异常必须保留 503/504 语义，不能被通用 500 吞掉。"""
    monkeypatch.delenv("OPENCLAW_API_TOKEN", raising=False)
    monkeypatch.setenv("ENV", "development")
    monkeypatch.setenv("API_HOST", "127.0.0.1")
    monkeypatch.setattr("src.api.auth._API_TOKEN", "", raising=False)
    ctx = XianyuContextManager(db_path=str(tmp_path / "xianyu-owner-boundary.db"))
    fake_live = SimpleNamespace(call_on_owner=AsyncMock(side_effect=failure))
    old_ctx, old_live = xianyu_admin._ctx, xianyu_admin._live
    xianyu_admin._ctx = ctx
    xianyu_admin._live = fake_live
    try:
        response = TestClient(xianyu_admin.app).get("/api/cc-paid-order-probe")
        assert response.status_code == expected_status
        assert expected_text in response.json()["detail"]
    finally:
        xianyu_admin._ctx = old_ctx
        xianyu_admin._live = old_live


def test_xianyu_admin_paid_order_probe_is_read_only_and_scrubbed(tmp_path, monkeypatch):
    """只读扫真实待发货订单：能看见候选单，但不能发卡或泄露原始订单号。"""
    monkeypatch.delenv("OPENCLAW_API_TOKEN", raising=False)
    monkeypatch.setenv("ENV", "development")
    monkeypatch.setenv("API_HOST", "127.0.0.1")
    monkeypatch.setattr("src.api.auth._API_TOKEN", "", raising=False)
    ctx = XianyuContextManager(db_path=str(tmp_path / "xianyu-chat.db"))

    scan_paid_orders = AsyncMock(
        return_value={
            "ok": True,
            "processed": 1,
            "candidates": [
                {
                    "order_id": "xy_oid_hashonly",
                    "raw_order_id": "123456789012345",
                    "buyer_id": "buyer-secret",
                    "item_id": "item-real",
                    "title": "1元测试商品",
                    "amount": 1.0,
                    "status_text": "买家已付款，等待卖家发货",
                    "can_auto_ship_item": True,
                    "local_shipment_status": "none",
                }
            ],
            "next_action": "只读扫描完成",
        }
    )

    async def call_on_owner(operation: str, **kwargs):
        assert operation == "scan_cc_paid_orders_readonly"
        assert kwargs.pop("timeout") == 30.0
        return await scan_paid_orders(**kwargs)

    fake_live = SimpleNamespace(
        scan_cc_paid_orders_readonly=scan_paid_orders,
        call_on_owner=AsyncMock(side_effect=call_on_owner),
    )
    old_ctx, old_live = xianyu_admin._ctx, xianyu_admin._live
    xianyu_admin._ctx = ctx
    xianyu_admin._live = fake_live
    try:
        client = TestClient(xianyu_admin.app)

        response = client.get("/api/cc-paid-order-probe")

        assert response.status_code == 200
        payload = response.json()
        assert payload["ok"] is True
        assert payload["readOnly"] is True
        assert payload["autoShipPaused"] is False
        assert payload["candidates"][0]["order"]["prefix"] == "xy_oid_"
        assert payload["candidates"][0]["buyer"]["present"] is True
        assert payload["candidates"][0]["item"]["present"] is True
        assert "123456789012345" not in json.dumps(payload, ensure_ascii=False)
        assert "buyer-secret" not in json.dumps(payload, ensure_ascii=False)
        assert ctx.list_cc_shipments(include_message=True) == []
        fake_live.scan_cc_paid_orders_readonly.assert_awaited_once_with(batch_size=5)
    finally:
        xianyu_admin._ctx = old_ctx
        xianyu_admin._live = old_live


@pytest.mark.asyncio
async def test_xianyu_live_readonly_paid_order_probe_does_not_send_or_record(monkeypatch, live):
    """Live 只读扫单只能读取和解析订单，不能调用 webhook、send_msg 或写履约表。"""

    class FakeSoldOrderApis:
        def __init__(self, cookies_str: str):
            self.cookies_str = cookies_str

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get_sold_orders_page(self, page: int = 1, query_code: str = "NOT_SHIP"):
            assert page == 1
            assert query_code == "NOT_SHIP"
            return {
                "success": True,
                "total_count": 1,
                "cookies_str": "fresh-cookie",
                "items": [
                    {
                        "commonData": {
                            "orderId": "123456789012345",
                            "itemId": "item-real",
                            "orderStatus": "买家已付款，等待卖家发货",
                            "itemTitle": "1元测试商品",
                        },
                        "buyerInfoVO": {"buyerId": "buyer-real"},
                        "priceVO": {"totalPrice": "1.00"},
                    }
                ],
            }

    monkeypatch.setattr("src.xianyu.xianyu_live.XianyuApis", FakeSoldOrderApis)
    live.cookies_str = "old-cookie"
    live.cookies = {}
    live.myid = "seller-001"
    live.ctx.get_cc_shipment_by_order_id = MagicMock(return_value=None)
    live._resolve_auto_ship_item_id = MagicMock(return_value="item-real")

    result = await live.scan_cc_paid_orders_readonly(batch_size=5)

    assert result["ok"] is True
    assert result["read_only"] is True
    assert result["processed"] == 1
    assert result["candidates"][0]["order_id"].startswith("xy_oid_")
    assert result["candidates"][0]["raw_order_id"] == "123456789012345"
    assert result["candidates"][0]["buyer_id"] == "buyer-real"
    assert result["candidates"][0]["can_auto_ship_item"] is True
    assert live.cookies_str == "fresh-cookie"
    live.send_msg.assert_not_awaited()
    live.ctx.record_cc_shipment.assert_not_called()
