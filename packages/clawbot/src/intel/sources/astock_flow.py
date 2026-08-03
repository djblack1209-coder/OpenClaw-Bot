"""A-share data adapters for Intel Brief."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from src.intel.runtime_policy import resolve_runtime_policy
from src.intel.sources.base import IntelSourceResult


def _first_text(row: dict[str, Any], keys: tuple[str, ...]) -> str:
    for key in keys:
        value = row.get(key)
        if value is not None and str(value) != "nan":
            return str(value)
    return ""


def _trade_date_text(raw: str) -> str:
    """把 AKShare 常见交易日格式统一为 ISO 日期。"""
    raw = str(raw or "").strip()
    if not raw:
        return ""
    normalized = raw.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(normalized).date().isoformat()
    except ValueError:
        for format_string in ("%Y/%m/%d", "%Y%m%d", "%m/%d/%Y"):
            try:
                return datetime.strptime(raw, format_string).date().isoformat()
            except ValueError:
                continue
    return ""


def normalize_lhb_records(records: list[dict[str, Any]], *, limit: int = 20) -> list[dict[str, str]]:
    """Normalize AKShare Eastmoney LHB rows to a compact stable schema."""
    normalized: list[dict[str, str]] = []
    for row in records:
        trade_date_raw = _first_text(row, ("上榜日", "TRADE_DATE", "交易日期", "日期", "date"))
        normalized.append(
            {
                "source": "akshare_stock_lhb_detail_em",
                "trade_date": _trade_date_text(trade_date_raw),
                "trade_date_raw": trade_date_raw,
                "code": _first_text(row, ("代码", "SECURITY_CODE", "股票代码", "code")),
                "name": _first_text(row, ("名称", "SECURITY_NAME_ABBR", "股票简称", "name")),
                "reason": _first_text(row, ("解读", "EXPLAIN", "上榜原因", "reason")),
                "close_price": _first_text(row, ("收盘价", "CLOSE_PRICE", "close_price")),
            }
        )
    normalized.sort(
        key=lambda item: (item["trade_date"], item["code"], item["reason"]),
        reverse=True,
    )
    return normalized[: max(0, int(limit))]


class AkshareLhbAdapter:
    """AKShare Eastmoney 龙虎榜 adapter.

    `akshare` is imported lazily so the controller can build bundles and run tests
    without installing the dependency. Target domestic workers must provide it in
    their local runtime before invoking this adapter.
    """

    source_name = "akshare"

    def __init__(self, *, ak_module=None, evidence_path: str = "") -> None:
        self.ak_module = ak_module
        self.evidence_path = evidence_path

    def _ak(self):
        if self.ak_module is not None:
            return self.ak_module
        import akshare as ak  # type: ignore[import-not-found]

        return ak

    def fetch(self, *, limit: int = 20) -> IntelSourceResult:
        frame = self._ak().stock_lhb_detail_em()
        rows = frame.to_dict(orient="records")
        items = normalize_lhb_records(rows, limit=limit)
        policy = resolve_runtime_policy(self.source_name)
        return IntelSourceResult(
            source=self.source_name,
            worker=policy.preferred_worker,
            fetched_at=datetime.now(timezone.utc).isoformat(),  # noqa: UP017 - Python 3.10 worker compatibility
            items=items,
            raw_count=len(items),
            health_status="success",
            evidence_path=self.evidence_path,
        )
