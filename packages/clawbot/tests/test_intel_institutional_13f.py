from __future__ import annotations

import json

from src.intel.sources.institutional_13f import (
    Institutional13FAdapter,
    Institutional13FSpec,
    find_latest_13f_filing,
    parse_information_table_xml,
)

SUBMISSIONS_SAMPLE = {
    "name": "BERKSHIRE HATHAWAY INC",
    "filings": {
        "recent": {
            "form": ["10-Q", "13F-HR", "13F-HR/A"],
            "accessionNumber": ["0000000000-26-000001", "0001193125-26-226661", "0001193125-26-100000"],
            "filingDate": ["2026-06-01", "2026-05-15", "2026-02-14"],
            "primaryDocument": ["brk-10q.htm", "xslForm13F_X02/primary_doc.xml", "primary_doc.xml"],
        }
    },
}


INFORMATION_TABLE_SAMPLE = """<?xml version="1.0" encoding="UTF-8"?>
<informationTable xmlns="http://www.sec.gov/edgar/document/thirteenf/informationtable">
  <infoTable>
    <nameOfIssuer>ALLY FINL INC</nameOfIssuer>
    <titleOfClass>COM</titleOfClass>
    <cusip>02005N100</cusip>
    <value>498992850</value>
    <shrsOrPrnAmt>
      <sshPrnamt>12719675</sshPrnamt>
      <sshPrnamtType>SH</sshPrnamtType>
    </shrsOrPrnAmt>
    <investmentDiscretion>DFND</investmentDiscretion>
  </infoTable>
  <infoTable>
    <nameOfIssuer>APPLE INC</nameOfIssuer>
    <titleOfClass>COM</titleOfClass>
    <cusip>037833100</cusip>
    <value>6051089</value>
    <shrsOrPrnAmt>
      <sshPrnamt>20000000</sshPrnamt>
      <sshPrnamtType>SH</sshPrnamtType>
    </shrsOrPrnAmt>
  </infoTable>
</informationTable>
"""


class _FakeResponse:
    def __init__(self, body: bytes | str) -> None:
        self.body = body if isinstance(body, bytes) else body.encode("utf-8")

    def __enter__(self) -> _FakeResponse:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
        return self.body


def test_find_latest_13f_filing_from_sec_submissions_json():
    filing = find_latest_13f_filing(SUBMISSIONS_SAMPLE, cik="0001067983")

    assert filing == {
        "fund_name": "BERKSHIRE HATHAWAY INC",
        "cik": "0001067983",
        "accession_number": "0001193125-26-226661",
        "accession_nodashes": "000119312526226661",
        "filing_date": "2026-05-15",
        "primary_document": "xslForm13F_X02/primary_doc.xml",
    }


def test_parse_information_table_xml_normalizes_holdings():
    holdings = parse_information_table_xml(
        INFORMATION_TABLE_SAMPLE,
        fund_name="BERKSHIRE HATHAWAY INC",
        cik="0001067983",
        accession_number="0001193125-26-226661",
        filing_date="2026-05-15",
        limit=2,
    )

    assert holdings == [
        {
            "source": "sec_13f_information_table",
            "provider": "sec_edgar",
            "fund_name": "BERKSHIRE HATHAWAY INC",
            "cik": "0001067983",
            "accession_number": "0001193125-26-226661",
            "filing_date": "2026-05-15",
            "issuer": "ALLY FINL INC",
            "class": "COM",
            "cusip": "02005N100",
            "value_thousands_usd": "498992850",
            "shares": "12719675",
            "share_type": "SH",
            "investment_discretion": "DFND",
            "title": "BERKSHIRE HATHAWAY INC 13F：ALLY FINL INC（498992850 千美元）",
        },
        {
            "source": "sec_13f_information_table",
            "provider": "sec_edgar",
            "fund_name": "BERKSHIRE HATHAWAY INC",
            "cik": "0001067983",
            "accession_number": "0001193125-26-226661",
            "filing_date": "2026-05-15",
            "issuer": "APPLE INC",
            "class": "COM",
            "cusip": "037833100",
            "value_thousands_usd": "6051089",
            "shares": "20000000",
            "share_type": "SH",
            "investment_discretion": "",
            "title": "BERKSHIRE HATHAWAY INC 13F：APPLE INC（6051089 千美元）",
        },
    ]


def test_parse_information_table_xml_aggregates_duplicate_issuer_rows():
    duplicate_xml = """<informationTable xmlns="http://www.sec.gov/edgar/document/thirteenf/informationtable">
      <infoTable>
        <nameOfIssuer>ALLY FINL INC</nameOfIssuer>
        <titleOfClass>COM</titleOfClass>
        <cusip>02005N100</cusip>
        <value>100</value>
        <shrsOrPrnAmt><sshPrnamt>10</sshPrnamt><sshPrnamtType>SH</sshPrnamtType></shrsOrPrnAmt>
      </infoTable>
      <infoTable>
        <nameOfIssuer>ALLY FINL INC</nameOfIssuer>
        <titleOfClass>COM</titleOfClass>
        <cusip>02005N100</cusip>
        <value>250</value>
        <shrsOrPrnAmt><sshPrnamt>25</sshPrnamt><sshPrnamtType>SH</sshPrnamtType></shrsOrPrnAmt>
      </infoTable>
    </informationTable>"""

    holdings = parse_information_table_xml(
        duplicate_xml,
        fund_name="BERKSHIRE HATHAWAY INC",
        cik="0001067983",
        accession_number="0001193125-26-226661",
        filing_date="2026-05-15",
        limit=10,
    )

    assert len(holdings) == 1
    assert holdings[0]["issuer"] == "ALLY FINL INC"
    assert holdings[0]["value_thousands_usd"] == "350"
    assert holdings[0]["shares"] == "35"
    assert holdings[0]["title"] == "BERKSHIRE HATHAWAY INC 13F：ALLY FINL INC（350 千美元）"


def test_institutional_13f_adapter_fetches_latest_sec_information_table_without_credentials():
    index_payload = {"directory": {"item": [{"name": "primary_doc.xml"}, {"name": "53405.xml"}]}}
    bodies = {
        "https://data.sec.gov/submissions/CIK0001067983.json": json.dumps(SUBMISSIONS_SAMPLE),
        "https://www.sec.gov/Archives/edgar/data/1067983/000119312526226661/index.json": json.dumps(index_payload),
        "https://www.sec.gov/Archives/edgar/data/1067983/000119312526226661/53405.xml": INFORMATION_TABLE_SAMPLE,
    }
    calls: list[str] = []

    def opener(request, timeout: int):
        calls.append(request.full_url)
        return _FakeResponse(bodies[request.full_url])

    adapter = Institutional13FAdapter(
        institutions=(Institutional13FSpec(name="BERKSHIRE HATHAWAY INC", cik="0001067983"),),
        opener=opener,
        timeout=6,
        evidence_path="evidence/institutional-13f.json",
    )

    result = adapter.fetch(limit=2)

    assert result.source == "institutional_13f"
    assert result.worker == "overseas"
    assert result.health_status == "success"
    assert result.raw_count == 2
    assert [item["issuer"] for item in result.items] == ["ALLY FINL INC", "APPLE INC"]
    assert calls == [
        "https://data.sec.gov/submissions/CIK0001067983.json",
        "https://www.sec.gov/Archives/edgar/data/1067983/000119312526226661/index.json",
        "https://www.sec.gov/Archives/edgar/data/1067983/000119312526226661/53405.xml",
    ]
    assert result.evidence_path.endswith("institutional-13f.json")
