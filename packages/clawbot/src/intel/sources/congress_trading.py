"""国会持仓数据源：Senate raw GitHub fallback。"""

from __future__ import annotations

import json
import urllib.request
from datetime import datetime, timezone
from typing import Any

from src.intel.runtime_policy import resolve_runtime_policy
from src.intel.sources.base import IntelSourceResult

SENATE_RAW_URL = (
    "https://raw.githubusercontent.com/timothycarambat/senate-stock-watcher-data/master/aggregate/all_transactions.json"
)


def _as_text(payload: bytes | str) -> str:
    """把 HTTP 响应体转为文本。"""
    if isinstance(payload, bytes):
        return payload.decode("utf-8")
    return str(payload)


def parse_transactions(payload: bytes | str, limit: int = 20) -> list[dict[str, Any]]:
    """解析 Senate watcher 预编译 JSON 为统一交易记录。"""
    raw = json.loads(_as_text(payload))
    if isinstance(raw, dict):
        records = raw.get("data") or raw.get("transactions") or []
    else:
        records = raw
    normalized: list[dict[str, Any]] = []
    for item in list(records):
        if not isinstance(item, dict):
            continue
        normalized.append(
            {
                "source": "senate-stock-watcher-data",
                "transaction_date": str(item.get("transaction_date", "") or ""),
                "disclosure_date": str(item.get("disclosure_date", "") or item.get("date_recieved", "") or ""),
                "person": str(item.get("senator", "") or item.get("representative", "") or item.get("person", "")),
                "owner": str(item.get("owner", "") or ""),
                "ticker": str(item.get("ticker", "") or ""),
                "asset_description": str(item.get("asset_description", "") or ""),
                "asset_type": str(item.get("asset_type", "") or ""),
                "transaction_type": str(item.get("type", "") or item.get("transaction_type", "") or ""),
                "amount": str(item.get("amount", "") or ""),
                "ptr_link": str(item.get("ptr_link", "") or item.get("link", "") or ""),
            }
        )
    normalized.sort(
        key=lambda item: (
            _parse_source_date(item.get("disclosure_date")),
            _parse_source_date(item.get("transaction_date")),
            str(item.get("person", "")).casefold(),
            str(item.get("ticker", "")).casefold(),
        ),
        reverse=True,
    )
    return normalized[: max(0, int(limit))]


def _parse_source_date(value: Any) -> datetime:
    """把 Senate 的日期转为可排序 UTC 时间，坏值稳定排在最后。"""
    raw = str(value or "").strip()
    for format_string in ("%m/%d/%Y", "%Y-%m-%d", "%Y/%m/%d"):
        try:
            return datetime.strptime(raw, format_string).replace(tzinfo=timezone.utc)  # noqa: UP017
        except ValueError:
            continue
    return datetime.min.replace(tzinfo=timezone.utc)  # noqa: UP017 - Python 3.10 兼容


def fetch_senate_transactions(
    url: str = SENATE_RAW_URL,
    limit: int = 20,
    timeout: int = 20,
    opener=None,
) -> list[dict[str, Any]]:
    """从 raw.githubusercontent.com 拉取 Senate 交易记录。"""
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "OpenClaw-IntelBrief/0.1",
            "Accept": "application/json,text/plain,*/*",
        },
    )
    open_fn = opener or urllib.request.urlopen
    with open_fn(request, timeout=timeout) as response:
        payload = response.read()
    return parse_transactions(payload, limit=limit)


class SenateTransactionsAdapter:
    """Senate raw GitHub source adapter.

    The adapter normalizes the already-verified raw GitHub fallback into the
    shared IntelSourceResult contract. It does not write evidence itself; callers
    pass the evidence path that records the target-worker real-call proof.
    """

    source_name = "senate_trading"

    def __init__(
        self,
        *,
        url: str = SENATE_RAW_URL,
        timeout: int = 20,
        opener=None,
        evidence_path: str = "",
    ) -> None:
        self.url = url
        self.timeout = timeout
        self.opener = opener
        self.evidence_path = evidence_path

    def fetch(self, *, limit: int = 20) -> IntelSourceResult:
        items = fetch_senate_transactions(
            url=self.url,
            limit=limit,
            timeout=self.timeout,
            opener=self.opener,
        )
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
