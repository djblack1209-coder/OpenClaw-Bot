import json

from src.intel.sources.congress_trading import SENATE_RAW_URL, fetch_senate_transactions, parse_transactions

SAMPLE = [
    {
        "transaction_date": "11/10/2020",
        "owner": "Spouse",
        "ticker": "BYND",
        "asset_description": "Beyond Meat, Inc.",
        "asset_type": "Stock",
        "type": "Sale (Full)",
        "amount": "$50,001 - $100,000",
        "senator": "Ron L Wyden",
        "ptr_link": "https://efdsearch.senate.gov/search/view/ptr/example/",
        "disclosure_date": "11/16/2020",
    }
]


class FakeResponse:
    status = 200
    headers = {"content-type": "application/json"}

    def __init__(self, payload):
        self._payload = payload

    def read(self):
        return self._payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


class FakeOpener:
    def __init__(self, payload):
        self.payload = payload
        self.requested_url = None

    def __call__(self, request, timeout=20):
        self.requested_url = request.full_url
        return FakeResponse(self.payload)


def test_parse_transactions_normalizes_senate_rows():
    rows = parse_transactions(json.dumps(SAMPLE), limit=5)

    assert rows == [
        {
            "source": "senate-stock-watcher-data",
            "transaction_date": "11/10/2020",
            "disclosure_date": "11/16/2020",
            "person": "Ron L Wyden",
            "owner": "Spouse",
            "ticker": "BYND",
            "asset_description": "Beyond Meat, Inc.",
            "asset_type": "Stock",
            "transaction_type": "Sale (Full)",
            "amount": "$50,001 - $100,000",
            "ptr_link": "https://efdsearch.senate.gov/search/view/ptr/example/",
        }
    ]


def test_fetch_senate_transactions_uses_raw_github_url_with_injected_opener():
    opener = FakeOpener(json.dumps(SAMPLE).encode("utf-8"))

    rows = fetch_senate_transactions(opener=opener, limit=1)

    assert opener.requested_url == SENATE_RAW_URL
    assert rows[0]["person"] == "Ron L Wyden"
    assert rows[0]["ticker"] == "BYND"
