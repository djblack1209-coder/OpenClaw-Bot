"""每日资讯 V2 的统一内容事实契约。"""

from __future__ import annotations

import hashlib
import math
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import date, datetime, time, timezone
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

_TRACKING_QUERY_KEYS = {
    "fbclid",
    "gclid",
    "mc_cid",
    "mc_eid",
    "ref",
    "ref_src",
}
_DATE_ONLY_FORMATS = (
    "%Y-%m-%d",
    "%Y/%m/%d",
    "%Y%m%d",
    "%m/%d/%Y",
    "%b %d, %Y",
    "%B %d, %Y",
)


def clean_text(value: Any) -> str:
    """把来源文本压缩为适合稳定比较的单行字符串。"""
    return re.sub(r"\s+", " ", str(value or "")).strip()


def stable_hash(value: str) -> str:
    """生成跨进程稳定的 SHA-256 标识。"""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _json_safe(value: Any) -> Any:
    """递归清理第三方对象，保证载荷可由标准 JSON 编码。"""
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Mapping):
        return {clean_text(key): _json_safe(item_value) for key, item_value in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_json_safe(item) for item in value]
    return clean_text(value)


def canonicalize_url(value: Any) -> str:
    """规范化公开 HTTP(S) 链接并移除常见追踪参数。"""
    raw = clean_text(value)
    if not raw:
        return ""
    try:
        parts = urlsplit(raw)
    except ValueError:
        return ""
    scheme = parts.scheme.lower()
    if scheme not in {"http", "https"} or not parts.hostname:
        return ""
    hostname = parts.hostname.lower()
    try:
        port = parts.port
    except ValueError:
        return ""
    if port and not ((scheme == "http" and port == 80) or (scheme == "https" and port == 443)):
        netloc = f"{hostname}:{port}"
    else:
        netloc = hostname
    query = [
        (key, item_value)
        for key, item_value in parse_qsl(parts.query, keep_blank_values=True)
        if not key.lower().startswith("utm_") and key.lower() not in _TRACKING_QUERY_KEYS
    ]
    query.sort(key=lambda item: (item[0].casefold(), item[1]))
    path = parts.path or ""
    if path != "/":
        path = path.rstrip("/")
    return urlunsplit((scheme, netloc, path, urlencode(query, doseq=True), ""))


def parse_content_datetime(value: Any) -> datetime | None:
    """解析来源常见日期格式并统一为 UTC。"""
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, date):
        parsed = datetime.combine(value, time.min)
    else:
        raw = clean_text(value)
        if not raw:
            return None
        normalized = raw.replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(normalized)
        except ValueError:
            try:
                parsed = parsedate_to_datetime(raw)
            except (TypeError, ValueError, OverflowError):
                parsed = None
            if parsed is None:
                for format_string in _DATE_ONLY_FORMATS:
                    try:
                        parsed = datetime.strptime(raw, format_string)
                        break
                    except ValueError:
                        continue
        if parsed is None:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)  # noqa: UP017 - Python 3.10 兼容
    return parsed.astimezone(timezone.utc)  # noqa: UP017 - Python 3.10 兼容


def _date_confidence(raw_value: Any, parsed: datetime | None, *, observed: bool = False) -> str:
    if parsed is None:
        return "missing"
    if observed:
        return "observed"
    raw = clean_text(raw_value)
    if re.fullmatch(r"\d{4}[-/]\d{2}[-/]\d{2}|\d{8}|\d{1,2}/\d{1,2}/\d{4}", raw):
        return "date_only"
    return "exact"


@dataclass(frozen=True)
class ContentItem:
    """一条可审计、可排序、可跨批次去重的内容事实。"""

    source_name: str
    content_kind: str
    source_item_id: str
    event_key: str
    entity_key: str
    category: str
    provider: str
    title: str
    summary: str
    source_url: str
    event_at: datetime | None
    published_at: datetime | None
    observed_at: datetime
    date_confidence: str
    payload: Mapping[str, Any] = field(default_factory=dict)
    evidence_path: str = ""

    def __post_init__(self) -> None:
        """收紧契约字段，避免空标识进入去重与排序。"""
        for name in (
            "source_name",
            "content_kind",
            "source_item_id",
            "event_key",
            "entity_key",
            "category",
            "provider",
            "title",
            "summary",
            "date_confidence",
            "evidence_path",
        ):
            object.__setattr__(self, name, clean_text(getattr(self, name)))
        object.__setattr__(self, "source_url", canonicalize_url(self.source_url))
        object.__setattr__(self, "payload", _json_safe(dict(self.payload)))
        if not self.source_name or not self.content_kind or not self.event_key:
            raise ValueError("content_item_missing_identity")
        if not self.source_item_id or not self.entity_key or not self.category or not self.provider or not self.title:
            raise ValueError("content_item_missing_required_field")
        if self.date_confidence not in {"exact", "date_only", "observed", "missing"}:
            raise ValueError("content_item_invalid_date_confidence")
        for name in ("event_at", "published_at", "observed_at"):
            value = getattr(self, name)
            if value is None and name != "observed_at":
                continue
            if not isinstance(value, datetime) or value.tzinfo is None:
                raise ValueError(f"content_item_{name}_must_be_timezone_aware")
            object.__setattr__(self, name, value.astimezone(timezone.utc))  # noqa: UP017 - Python 3.10 兼容
        if self.date_confidence == "missing" and self.freshness_at is not None:
            raise ValueError("content_item_inconsistent_missing_date")
        if self.date_confidence != "missing" and self.freshness_at is None:
            raise ValueError("content_item_missing_freshness_date")

    @property
    def freshness_at(self) -> datetime | None:
        """返回用于时效判断的来源事件时间，绝不使用入库时间冒充。"""
        return self.event_at or self.published_at

    def to_dict(self) -> dict[str, Any]:
        """转换为可持久化和投递的 JSON 兼容字典。"""
        return {
            "source_name": self.source_name,
            "content_kind": self.content_kind,
            "source_item_id": self.source_item_id,
            "event_key": self.event_key,
            "entity_key": self.entity_key,
            "category": self.category,
            "provider": self.provider,
            "title": self.title,
            "summary": self.summary,
            "source_url": self.source_url,
            "event_at": self.event_at.isoformat() if self.event_at else "",
            "published_at": self.published_at.isoformat() if self.published_at else "",
            "observed_at": self.observed_at.isoformat(),
            "date_confidence": self.date_confidence,
            "payload": dict(self.payload),
            "evidence_path": self.evidence_path,
        }


@dataclass(frozen=True)
class NormalizationRejection:
    """记录无法进入统一契约的来源行。"""

    index: int
    reason: str
    raw: Mapping[str, Any]


@dataclass(frozen=True)
class NormalizationResult:
    """批量归一化结果，坏行与有效内容相互隔离。"""

    items: tuple[ContentItem, ...]
    rejected: tuple[NormalizationRejection, ...]


def _event_key(source_name: str, *parts: Any) -> str:
    material = "|".join(clean_text(part).casefold() for part in parts)
    return f"{source_name}:{stable_hash(material)}"


def _source_url_for_13f(raw: Mapping[str, Any]) -> str:
    cik = re.sub(r"\D", "", clean_text(raw.get("cik")))
    accession = re.sub(r"\D", "", clean_text(raw.get("accession_number")))
    if not cik or not accession:
        return ""
    return f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession}"


def _amount_upper_bound(value: Any) -> int:
    numbers = [int(part.replace(",", "")) for part in re.findall(r"\d[\d,]*", clean_text(value))]
    return max(numbers, default=0)


def _normalize_senate(raw: Mapping[str, Any], *, observed_at: datetime, evidence_path: str) -> ContentItem:
    person = clean_text(raw.get("person") or raw.get("senator") or raw.get("representative"))
    ticker = clean_text(raw.get("ticker")).upper()
    transaction_type = clean_text(raw.get("transaction_type") or raw.get("type"))
    amount = clean_text(raw.get("amount"))
    transaction_date = clean_text(raw.get("transaction_date"))
    disclosure_raw = raw.get("disclosure_date") or raw.get("date_recieved")
    disclosure_at = parse_content_datetime(disclosure_raw)
    url = canonicalize_url(raw.get("ptr_link") or raw.get("link"))
    identity = (url, person, ticker, transaction_date, transaction_type, amount)
    title = " ".join(part for part in (person, transaction_type, ticker) if part) or "国会持仓披露"
    if amount:
        title = f"{title}（{amount}）"
    summary_parts = [
        clean_text(raw.get("asset_description")),
        f"交易日期 {transaction_date}" if transaction_date else "",
    ]
    return ContentItem(
        source_name="senate_trading",
        content_kind="transaction_disclosure",
        source_item_id=stable_hash("|".join(clean_text(part) for part in identity)),
        event_key=_event_key("senate_trading", *identity),
        entity_key=f"senate:{person.casefold()}:{ticker.casefold()}",
        category="market",
        provider=clean_text(raw.get("source")) or "senate-stock-watcher-data",
        title=title,
        summary="；".join(part for part in summary_parts if part),
        source_url=url,
        event_at=disclosure_at,
        published_at=disclosure_at,
        observed_at=observed_at,
        date_confidence=_date_confidence(disclosure_raw, disclosure_at),
        payload={**dict(raw), "amount_upper_bound": _amount_upper_bound(amount)},
        evidence_path=evidence_path,
    )


def _normalize_astock(raw: Mapping[str, Any], *, observed_at: datetime, evidence_path: str) -> ContentItem:
    code = clean_text(raw.get("code"))
    name = clean_text(raw.get("name"))
    reason = clean_text(raw.get("reason"))
    trade_date_raw = raw.get("trade_date") or raw.get("date")
    trade_date = parse_content_datetime(trade_date_raw)
    title_base = f"{name}（{code}）" if name and code else name or code or "A股龙虎榜"
    title = f"{title_base}：{reason}" if reason else title_base
    return ContentItem(
        source_name="akshare",
        content_kind="market_flow",
        source_item_id=stable_hash(f"{trade_date_raw}|{code}|{reason}"),
        event_key=_event_key("akshare", trade_date_raw, code, reason),
        entity_key=f"astock:{code or name.casefold()}",
        category="market",
        provider="akshare-eastmoney",
        title=title,
        summary=f"收盘价 {clean_text(raw.get('close_price'))}" if clean_text(raw.get("close_price")) else "",
        source_url=raw.get("url") or raw.get("source_url") or "",
        event_at=trade_date,
        published_at=trade_date,
        observed_at=observed_at,
        date_confidence=_date_confidence(trade_date_raw, trade_date),
        payload=dict(raw),
        evidence_path=evidence_path,
    )


def _normalize_github(raw: Mapping[str, Any], *, observed_at: datetime, evidence_path: str) -> ContentItem:
    repo = clean_text(raw.get("repo") or raw.get("title"))
    url = canonicalize_url(raw.get("url") or raw.get("source_url"))
    stars_today = clean_text(raw.get("stars_today"))
    summary = clean_text(raw.get("description") or raw.get("summary"))
    if stars_today:
        summary = f"{summary} · 今日新增 {stars_today} stars" if summary else f"今日新增 {stars_today} stars"
    observed_day = observed_at.date().isoformat()
    return ContentItem(
        source_name="github_trending",
        content_kind="repository_trend",
        source_item_id=repo.casefold(),
        event_key=_event_key("github_trending", repo, observed_day),
        entity_key=f"github:{repo.casefold()}",
        category="technology",
        provider="github",
        title=repo,
        summary=summary,
        source_url=url,
        event_at=observed_at,
        published_at=None,
        observed_at=observed_at,
        date_confidence="observed",
        payload=dict(raw),
        evidence_path=evidence_path,
    )


def _normalize_ai_update(raw: Mapping[str, Any], *, observed_at: datetime, evidence_path: str) -> ContentItem:
    provider = clean_text(raw.get("provider")).lower() or "unknown"
    title = clean_text(raw.get("title"))
    url = canonicalize_url(raw.get("url") or raw.get("link") or raw.get("source_url"))
    published_raw = raw.get("published_at") or raw.get("event_at")
    published_at = parse_content_datetime(published_raw)
    identity = url or title.casefold()
    return ContentItem(
        source_name="ai_model_updates",
        content_kind="model_update",
        source_item_id=stable_hash(f"{provider}|{identity}"),
        event_key=_event_key("ai_model_updates", provider, identity),
        entity_key=f"ai:{provider}:{stable_hash(title.casefold())[:16]}",
        category="ai",
        provider=provider,
        title=title,
        summary=clean_text(raw.get("summary") or raw.get("description")),
        source_url=url,
        event_at=published_at,
        published_at=published_at,
        observed_at=observed_at,
        date_confidence=_date_confidence(published_raw, published_at),
        payload=dict(raw),
        evidence_path=evidence_path,
    )


def _normalize_generic(
    source_name: str,
    raw: Mapping[str, Any],
    *,
    observed_at: datetime,
    evidence_path: str,
) -> ContentItem:
    title = clean_text(raw.get("title") or raw.get("name") or raw.get("summary"))
    url = canonicalize_url(raw.get("url") or raw.get("link") or raw.get("source_url"))
    event_raw = raw.get("event_at") or raw.get("published_at") or raw.get("date")
    event_at = parse_content_datetime(event_raw)
    uses_observed_time = source_name == "weather" and event_at is None
    if uses_observed_time:
        event_at = observed_at
    identity = url or title.casefold()
    return ContentItem(
        source_name=source_name,
        content_kind=clean_text(raw.get("content_kind")) or "news_update",
        source_item_id=stable_hash(f"{source_name}|{identity}"),
        event_key=_event_key(source_name, identity),
        entity_key=f"{source_name}:{stable_hash(title.casefold())[:16]}",
        category=clean_text(raw.get("category")) or source_name,
        provider=clean_text(raw.get("provider") or raw.get("source")) or source_name,
        title=title,
        summary=clean_text(raw.get("summary") or raw.get("description")),
        source_url=url,
        event_at=event_at,
        published_at=parse_content_datetime(raw.get("published_at")),
        observed_at=observed_at,
        date_confidence=_date_confidence(event_raw, event_at, observed=uses_observed_time),
        payload=dict(raw),
        evidence_path=evidence_path,
    )


def _normalize_13f_group(rows: list[Mapping[str, Any]], *, observed_at: datetime, evidence_path: str) -> ContentItem:
    first = rows[0]
    accession = clean_text(first.get("accession_number"))
    fund_name = clean_text(first.get("fund_name")) or "机构"
    filing_raw = first.get("filing_date")
    filing_at = parse_content_datetime(filing_raw)
    holdings = [dict(row) for row in rows]
    top_names = [clean_text(row.get("issuer")) for row in rows[:3] if clean_text(row.get("issuer"))]
    summary = f"主要持仓：{'、'.join(top_names)}" if top_names else ""
    return ContentItem(
        source_name="institutional_13f",
        content_kind="institutional_filing",
        source_item_id=accession or stable_hash(f"{fund_name}|{filing_raw}"),
        event_key=_event_key("institutional_13f", accession or fund_name, filing_raw),
        entity_key=f"13f:{clean_text(first.get('cik')) or fund_name.casefold()}",
        category="market",
        provider=clean_text(first.get("provider")) or "sec_edgar",
        title=f"{fund_name} 提交 13F（{len(rows)} 项持仓）",
        summary=summary,
        source_url=_source_url_for_13f(first),
        event_at=filing_at,
        published_at=filing_at,
        observed_at=observed_at,
        date_confidence=_date_confidence(filing_raw, filing_at),
        payload={"accession_number": accession, "holdings": holdings},
        evidence_path=evidence_path,
    )


def normalize_source_item(
    source_name: str,
    raw: Mapping[str, Any],
    *,
    fetched_at: Any,
    evidence_path: str = "",
) -> ContentItem:
    """把单条旧来源记录转换为 V2 契约。"""
    observed_at = parse_content_datetime(fetched_at) or datetime.now(timezone.utc)  # noqa: UP017 - Python 3.10 兼容
    normalized_source = clean_text(source_name).lower().replace("-", "_")
    if normalized_source == "senate_trading":
        return _normalize_senate(raw, observed_at=observed_at, evidence_path=evidence_path)
    if normalized_source == "akshare":
        return _normalize_astock(raw, observed_at=observed_at, evidence_path=evidence_path)
    if normalized_source == "github_trending":
        return _normalize_github(raw, observed_at=observed_at, evidence_path=evidence_path)
    if normalized_source == "ai_model_updates":
        return _normalize_ai_update(raw, observed_at=observed_at, evidence_path=evidence_path)
    if normalized_source == "institutional_13f":
        return _normalize_13f_group([raw], observed_at=observed_at, evidence_path=evidence_path)
    return _normalize_generic(
        normalized_source,
        raw,
        observed_at=observed_at,
        evidence_path=evidence_path,
    )


def normalize_source_items(
    source_name: str,
    rows: Iterable[Any],
    *,
    fetched_at: Any,
    evidence_path: str = "",
) -> list[ContentItem]:
    """批量转换来源记录，并把坏行隔离在可审计批量结果中。"""
    return list(
        normalize_source_batch(
            source_name,
            rows,
            fetched_at=fetched_at,
            evidence_path=evidence_path,
        ).items
    )


def normalize_source_batch(
    source_name: str,
    rows: Iterable[Any],
    *,
    fetched_at: Any,
    evidence_path: str = "",
) -> NormalizationResult:
    """转换整批来源数据并返回逐行隔离证据。"""
    normalized_source = clean_text(source_name).lower().replace("-", "_")
    indexed_rows = list(enumerate(rows))
    observed_at = parse_content_datetime(fetched_at) or datetime.now(timezone.utc)  # noqa: UP017 - Python 3.10 兼容
    items: list[ContentItem] = []
    rejected: list[NormalizationRejection] = [
        NormalizationRejection(
            index=index, reason="TypeError:source_row_must_be_mapping", raw={"value": _json_safe(row)}
        )
        for index, row in indexed_rows
        if not isinstance(row, Mapping)
    ]
    valid_rows = [(index, row) for index, row in indexed_rows if isinstance(row, Mapping)]
    if normalized_source == "institutional_13f":
        grouped: dict[str, list[tuple[int, Mapping[str, Any]]]] = {}
        for index, row in valid_rows:
            accession = clean_text(row.get("accession_number"))
            group_key = accession or stable_hash(f"{row.get('fund_name')}|{row.get('filing_date')}")
            grouped.setdefault(group_key, []).append((index, row))
        for _, indexed_group in sorted(grouped.items()):
            group = [row for _, row in indexed_group]
            first_index = indexed_group[0][0]
            try:
                items.append(_normalize_13f_group(group, observed_at=observed_at, evidence_path=evidence_path))
            except (TypeError, ValueError) as exc:
                rejected.append(
                    NormalizationRejection(
                        index=first_index,
                        reason=f"{type(exc).__name__}:{clean_text(exc)[:100]}",
                        raw=_json_safe({"rows": group}),
                    )
                )
        return NormalizationResult(items=tuple(items), rejected=tuple(sorted(rejected, key=lambda entry: entry.index)))
    for index, row in valid_rows:
        try:
            items.append(
                normalize_source_item(
                    normalized_source,
                    row,
                    fetched_at=observed_at,
                    evidence_path=evidence_path,
                )
            )
        except (TypeError, ValueError) as exc:
            rejected.append(
                NormalizationRejection(
                    index=index,
                    reason=f"{type(exc).__name__}:{clean_text(exc)[:100]}",
                    raw=_json_safe(row),
                )
            )
    return NormalizationResult(items=tuple(items), rejected=tuple(sorted(rejected, key=lambda entry: entry.index)))


def normalize_source_result(result: Any) -> NormalizationResult:
    """直接把现有 IntelSourceResult 或同结构字典转换为 V2 契约。"""
    if isinstance(result, Mapping):
        source_name = result.get("source")
        rows = result.get("items")
        fetched_at = result.get("fetched_at")
        evidence_path = result.get("evidence_path")
    else:
        source_name = getattr(result, "source", "")
        rows = getattr(result, "items", None)
        fetched_at = getattr(result, "fetched_at", "")
        evidence_path = getattr(result, "evidence_path", "")
    if isinstance(rows, (str, bytes, Mapping)) or not isinstance(rows, Iterable):
        raise ValueError("source_result_items_must_be_iterable")
    return normalize_source_batch(
        clean_text(source_name),
        rows,
        fetched_at=fetched_at,
        evidence_path=clean_text(evidence_path),
    )
