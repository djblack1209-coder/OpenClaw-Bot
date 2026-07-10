"""SEC EDGAR 13F institutional holdings adapter for Intel Brief."""

from __future__ import annotations

import json
import re
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from src.intel.runtime_policy import resolve_runtime_policy
from src.intel.sources.base import IntelSourceResult

SEC_USER_AGENT = "OpenClaw-IntelBrief/0.1 contact=openclaw-intel@example.invalid"


@dataclass(frozen=True)
class Institutional13FSpec:
    """One institution/fund to monitor via SEC 13F."""

    name: str
    cik: str


DEFAULT_INSTITUTIONS = (
    Institutional13FSpec(name="BERKSHIRE HATHAWAY INC", cik="0001067983"),
)


def _clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _digits(value: str) -> str:
    return re.sub(r"\D", "", str(value or ""))


def _cik10(cik: str) -> str:
    return _digits(cik).zfill(10)


def _local_name(tag: str) -> str:
    return str(tag or "").rsplit("}", 1)[-1]


def _child_text(node: ET.Element, path: tuple[str, ...]) -> str:
    current: ET.Element | None = node
    for name in path:
        if current is None:
            return ""
        found = None
        for child in list(current):
            if _local_name(child.tag) == name:
                found = child
                break
        current = found
    return _clean("".join(current.itertext())) if current is not None else ""


def _int_or_none(value: str) -> int | None:
    cleaned = _clean(value).replace(",", "")
    if not cleaned:
        return None
    try:
        return int(cleaned)
    except ValueError:
        return None


def find_latest_13f_filing(submissions_payload: dict[str, Any], *, cik: str) -> dict[str, str]:
    """Find the latest 13F-HR filing from SEC submissions JSON."""
    recent = ((submissions_payload.get("filings") or {}).get("recent") or {}) if isinstance(submissions_payload, dict) else {}
    forms = recent.get("form") or []
    accessions = recent.get("accessionNumber") or []
    filing_dates = recent.get("filingDate") or []
    primary_docs = recent.get("primaryDocument") or []
    fund_name = _clean(submissions_payload.get("name")) or _cik10(cik)
    for form, accession, filing_date, primary_doc in zip(forms, accessions, filing_dates, primary_docs, strict=False):
        if _clean(form) != "13F-HR":
            continue
        accession_text = _clean(accession)
        return {
            "fund_name": fund_name,
            "cik": _cik10(cik),
            "accession_number": accession_text,
            "accession_nodashes": accession_text.replace("-", ""),
            "filing_date": _clean(filing_date),
            "primary_document": _clean(primary_doc),
        }
    raise ValueError(f"latest_13f_not_found: {_cik10(cik)}")


def parse_information_table_xml(
    payload: bytes | str,
    *,
    fund_name: str,
    cik: str,
    accession_number: str,
    filing_date: str,
    limit: int = 20,
) -> list[dict[str, str]]:
    """Parse SEC 13F information table XML into normalized holding rows."""
    text = payload.decode("utf-8", errors="replace") if isinstance(payload, bytes) else str(payload)
    root = ET.fromstring(text)
    grouped: dict[tuple[str, str, str], dict[str, str]] = {}
    for node in root.iter():
        if _local_name(node.tag) != "infoTable":
            continue
        issuer = _child_text(node, ("nameOfIssuer",))
        value = _child_text(node, ("value",))
        class_name = _child_text(node, ("titleOfClass",))
        cusip = _child_text(node, ("cusip",))
        shares = _child_text(node, ("shrsOrPrnAmt", "sshPrnamt"))
        key = (issuer, class_name, cusip)
        if key not in grouped:
            grouped[key] = {
                "source": "sec_13f_information_table",
                "provider": "sec_edgar",
                "fund_name": _clean(fund_name),
                "cik": _cik10(cik),
                "accession_number": _clean(accession_number),
                "filing_date": _clean(filing_date),
                "issuer": issuer,
                "class": class_name,
                "cusip": cusip,
                "value_thousands_usd": value,
                "shares": shares,
                "share_type": _child_text(node, ("shrsOrPrnAmt", "sshPrnamtType")),
                "investment_discretion": _child_text(node, ("investmentDiscretion",)),
                "title": "",
            }
            continue
        current = grouped[key]
        current_value = _int_or_none(current["value_thousands_usd"])
        next_value = _int_or_none(value)
        if current_value is not None and next_value is not None:
            current["value_thousands_usd"] = str(current_value + next_value)
        current_shares = _int_or_none(current["shares"])
        next_shares = _int_or_none(shares)
        if current_shares is not None and next_shares is not None:
            current["shares"] = str(current_shares + next_shares)
        if not current["share_type"]:
            current["share_type"] = _child_text(node, ("shrsOrPrnAmt", "sshPrnamtType"))
        if not current["investment_discretion"]:
            current["investment_discretion"] = _child_text(node, ("investmentDiscretion",))

    holdings = list(grouped.values())
    holdings.sort(key=lambda item: _int_or_none(item["value_thousands_usd"]) or 0, reverse=True)
    for holding in holdings:
        issuer = holding["issuer"]
        value = holding["value_thousands_usd"]
        holding["title"] = f"{_clean(fund_name)} 13F：{issuer}（{value} 千美元）" if issuer else f"{_clean(fund_name)} 13F holding"
    return holdings[: max(0, int(limit))]


def _fetch_bytes(url: str, *, timeout: int, opener=None, accept: str = "application/json,*/*") -> bytes:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": SEC_USER_AGENT,
            "Accept": accept,
        },
    )
    open_fn = opener or urllib.request.urlopen
    with open_fn(request, timeout=timeout) as response:
        return response.read()


def _submissions_url(cik: str) -> str:
    return f"https://data.sec.gov/submissions/CIK{_cik10(cik)}.json"


def _archive_base(cik: str, accession_nodashes: str) -> str:
    return f"https://www.sec.gov/Archives/edgar/data/{int(_digits(cik))}/{accession_nodashes}"


def _find_information_table_name(index_payload: dict[str, Any], primary_document: str) -> str:
    items = ((index_payload.get("directory") or {}).get("item") or []) if isinstance(index_payload, dict) else []
    names = [_clean(item.get("name")) for item in items if isinstance(item, dict)]
    xml_names = [name for name in names if name.lower().endswith(".xml")]
    primary_base = _clean(primary_document).split("/")[-1]
    for name in xml_names:
        lowered = name.lower()
        if "infotable" in lowered or "informationtable" in lowered:
            return name
    for name in xml_names:
        if name != primary_base:
            return name
    if xml_names:
        return xml_names[0]
    raise ValueError("information_table_xml_not_found")


def fetch_institutional_13f(
    *,
    institutions: tuple[Institutional13FSpec, ...] = DEFAULT_INSTITUTIONS,
    limit: int = 20,
    timeout: int = 20,
    opener=None,
) -> list[dict[str, str]]:
    """Fetch latest official SEC 13F information table rows for configured institutions."""
    rows: list[dict[str, str]] = []
    per_institution_limit = max(1, int(limit))
    errors: list[str] = []
    for institution in institutions:
        try:
            submissions = json.loads(
                _fetch_bytes(_submissions_url(institution.cik), timeout=timeout, opener=opener).decode("utf-8")
            )
            filing = find_latest_13f_filing(submissions, cik=institution.cik)
            base = _archive_base(institution.cik, filing["accession_nodashes"])
            index_url = f"{base}/index.json"
            index_payload = json.loads(_fetch_bytes(index_url, timeout=timeout, opener=opener).decode("utf-8"))
            info_name = _find_information_table_name(index_payload, filing["primary_document"])
            info_url = f"{base}/{info_name}"
            xml_payload = _fetch_bytes(
                info_url,
                timeout=timeout,
                opener=opener,
                accept="application/xml,text/xml,*/*",
            )
            rows.extend(
                parse_information_table_xml(
                    xml_payload,
                    fund_name=filing["fund_name"] or institution.name,
                    cik=filing["cik"],
                    accession_number=filing["accession_number"],
                    filing_date=filing["filing_date"],
                    limit=per_institution_limit,
                )
            )
        except Exception as exc:
            errors.append(f"{institution.name}:{exc}")
    if not rows and errors:
        raise RuntimeError("; ".join(errors)[:500])
    return rows[: max(0, int(limit))]


class Institutional13FAdapter:
    """SEC 13F institutional holdings adapter."""

    source_name = "institutional_13f"

    def __init__(
        self,
        *,
        institutions: tuple[Institutional13FSpec, ...] = DEFAULT_INSTITUTIONS,
        timeout: int = 20,
        opener=None,
        evidence_path: str = "",
    ) -> None:
        self.institutions = institutions
        self.timeout = timeout
        self.opener = opener
        self.evidence_path = evidence_path

    def fetch(self, *, limit: int = 20) -> IntelSourceResult:
        items = fetch_institutional_13f(
            institutions=self.institutions,
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
