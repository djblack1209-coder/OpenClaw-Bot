"""auto_shipper 单元测试 — 闲鱼自动发货"""
import pytest
from src.xianyu.auto_shipper import AutoShipper


@pytest.fixture
def shipper(tmp_path):
    return AutoShipper(db_path=str(tmp_path / "test_shipper.db"))


class TestCardManagement:
    def test_add_cards(self, shipper):
        result = shipper.add_cards("item_001", ["card-A", "card-B", "card-C"])
        assert result["added"] == 3
        assert result["duplicates"] == 0

    def test_add_duplicate_cards(self, shipper):
        shipper.add_cards("item_001", ["card-A", "card-B"])
        result = shipper.add_cards("item_001", ["card-B", "card-C"])
        assert result["added"] == 1
        assert result["duplicates"] == 1

    def test_inventory(self, shipper):
        shipper.add_cards("item_001", ["c1", "c2", "c3"])
        inv = shipper.get_inventory("item_001")
        assert len(inv) == 1
        assert inv[0]["available"] == 3
        assert inv[0]["total"] == 3


class TestShippingRules:
    def test_set_and_get_rule(self, shipper):
        shipper.set_rule("item_001", auto_ship=True, delay_seconds=60)
        rule = shipper.get_rule("item_001")
        assert rule is not None
        assert rule["auto_ship"] == 1
        assert rule["delay_seconds"] == 60

    def test_get_nonexistent_rule(self, shipper):
        rule = shipper.get_rule("item_999")
        assert rule is None

    def test_min_delay(self, shipper):
        shipper.set_rule("item_001", delay_seconds=1)
        rule = shipper.get_rule("item_001")
        assert rule["delay_seconds"] >= 10


class TestProcessOrder:
    def test_successful_order(self, shipper):
        shipper.add_cards("item_001", ["activation-code-123"])
        result = shipper.process_order("order_001", "item_001", "buyer_001")
        assert result["success"]
        assert result["card_content"] == "activation-code-123"
        assert result["remaining"] == 0

    def test_out_of_stock(self, shipper):
        result = shipper.process_order("order_001", "item_001", "buyer_001")
        assert not result["success"]
        assert "库存" in result["reason"]

    def test_auto_ship_disabled(self, shipper):
        shipper.add_cards("item_001", ["code-1"])
        shipper.set_rule("item_001", auto_ship=False)
        result = shipper.process_order("order_001", "item_001")
        assert not result["success"]
        assert "未启用" in result["reason"]

    def test_multiple_orders_consume_stock(self, shipper):
        shipper.add_cards("item_001", ["c1", "c2", "c3"])
        r1 = shipper.process_order("o1", "item_001")
        r2 = shipper.process_order("o2", "item_001")
        r3 = shipper.process_order("o3", "item_001")
        r4 = shipper.process_order("o4", "item_001")
        assert r1["success"] and r2["success"] and r3["success"]
        assert not r4["success"]  # 库存耗尽


class TestStats:
    def test_shipping_stats(self, shipper):
        shipper.add_cards("item_001", ["c1", "c2"])
        shipper.process_order("o1", "item_001")
        stats = shipper.get_shipping_stats()
        assert stats["total_shipped"] == 1
