from __future__ import annotations

from src.intel.sources.astock_flow import AkshareLhbAdapter, normalize_lhb_records


class _FakeFrame:
    def __init__(self, rows: list[dict[str, object]]):
        self._rows = rows

    def head(self, limit: int):
        return _FakeFrame(self._rows[:limit])

    def to_dict(self, orient: str):
        assert orient == "records"
        return self._rows


class _FakeAkshare:
    @staticmethod
    def stock_lhb_detail_em():
        return _FakeFrame(
            [
                {"上榜日": "2026-08-04", "代码": "000021", "名称": "深科技", "解读": "机构买入", "收盘价": 26.5},
                {"上榜日": "2026-08-03", "代码": "000001", "名称": "平安银行", "解读": "资金净流入", "收盘价": 12.3},
            ]
        )


def test_normalize_lhb_records_maps_common_chinese_columns():
    rows = normalize_lhb_records(
        [
            {"上榜日": "2026-08-04", "代码": "000021", "名称": "深科技", "解读": "机构买入", "收盘价": 26.5},
            {
                "TRADE_DATE": "2026-08-03",
                "SECURITY_CODE": "000001",
                "SECURITY_NAME_ABBR": "平安银行",
                "EXPLAIN": "资金净流入",
            },
        ],
        limit=2,
    )

    assert rows == [
        {
            "source": "akshare_stock_lhb_detail_em",
            "trade_date": "2026-08-04",
            "trade_date_raw": "2026-08-04",
            "code": "000021",
            "name": "深科技",
            "reason": "机构买入",
            "close_price": "26.5",
        },
        {
            "source": "akshare_stock_lhb_detail_em",
            "trade_date": "2026-08-03",
            "trade_date_raw": "2026-08-03",
            "code": "000001",
            "name": "平安银行",
            "reason": "资金净流入",
            "close_price": "",
        },
    ]


def test_akshare_lhb_adapter_returns_domestic_source_result():
    adapter = AkshareLhbAdapter(ak_module=_FakeAkshare, evidence_path="phaseb/yanhuoyun-akshare.jsonl")

    result = adapter.fetch(limit=1)

    assert result.source == "akshare"
    assert result.worker == "domestic"
    assert result.health_status == "success"
    assert result.raw_count == 1
    assert result.items[0]["code"] == "000021"
    assert result.items[0]["trade_date"] == "2026-08-04"
    assert result.evidence_path.endswith("yanhuoyun-akshare.jsonl")


def test_normalize_lhb_records_normalizes_and_sorts_trade_dates_before_limit():
    rows = normalize_lhb_records(
        [
            {"TRADE_DATE": "08/03/2026", "代码": "000001", "名称": "旧记录"},
            {"TRADE_DATE": "2026/08/04", "代码": "000021", "名称": "新记录"},
        ],
        limit=1,
    )

    assert rows[0]["trade_date"] == "2026-08-04"
    assert rows[0]["trade_date_raw"] == "2026/08/04"
    assert rows[0]["code"] == "000021"


def test_invalid_trade_date_is_preserved_for_audit_but_sorted_after_valid_date():
    rows = normalize_lhb_records(
        [
            {"TRADE_DATE": "unknown", "代码": "999999", "名称": "坏日期"},
            {"TRADE_DATE": "2026-08-04", "代码": "000021", "名称": "有效日期"},
        ],
        limit=2,
    )

    assert [row["code"] for row in rows] == ["000021", "999999"]
    assert rows[1]["trade_date"] == ""
    assert rows[1]["trade_date_raw"] == "unknown"
