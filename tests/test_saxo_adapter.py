from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from uuid import uuid4

import httpx
import pytest

from app.adapters.saxo_read_only import SaxoReadOnlyAdapter


class _FakeHttpClient:
    def __init__(self, payloads: dict[str, list[Any]]) -> None:
        self._payloads = payloads
        self.calls: list[dict[str, Any]] = []

    def request(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str] | None = None,
        params: Mapping[str, Any] | None = None,
    ) -> httpx.Response:
        self.calls.append(
            {
                "method": method,
                "url": url,
                "headers": headers,
                "params": params,
            }
        )
        queue = self._payloads.get(url)
        if not queue:
            raise AssertionError(f"Unexpected request URL in test client: {url}")
        payload = queue.pop(0)
        request = httpx.Request(method=method, url=url, headers=headers, params=params)
        return httpx.Response(200, json=payload, request=request)


def test_validate_read_only_scope_accepts_read_permissions_only() -> None:
    base_url = "https://saxo.example"
    credential_value = uuid4().hex
    fake_client = _FakeHttpClient(
        {
            f"{base_url}/openapi/port/v1/permissions": [
                {
                    "Permissions": [
                        "portfolio.read",
                        "transactions.read",
                    ]
                }
            ]
        }
    )
    adapter = SaxoReadOnlyAdapter(
        base_url=base_url,
        access_token=credential_value,
        client=fake_client,
    )

    adapter.validate_read_only_scope()

    assert len(fake_client.calls) == 1
    assert fake_client.calls[0]["method"] == "GET"
    assert fake_client.calls[0]["headers"]["Authorization"] == f"Bearer {credential_value}"


def test_validate_read_only_scope_rejects_trade_write_permission() -> None:
    base_url = "https://saxo.example"
    credential_value = uuid4().hex
    fake_client = _FakeHttpClient(
        {
            f"{base_url}/openapi/port/v1/permissions": [
                {"Permissions": ["portfolio.read", "trade.write"]}
            ]
        }
    )
    adapter = SaxoReadOnlyAdapter(
        base_url=base_url,
        access_token=credential_value,
        client=fake_client,
    )

    with pytest.raises(ValueError, match="not read-only"):
        adapter.validate_read_only_scope()


def test_fetch_methods_map_payloads_and_follow_pagination() -> None:
    since_utc = datetime(2026, 1, 1, tzinfo=timezone.utc)
    base_url = "https://saxo.example"
    credential_value = uuid4().hex
    fake_client = _FakeHttpClient(
        {
            f"{base_url}/openapi/port/v1/accounts/me": [
                {
                    "Data": [
                        {
                            "AccountKey": "A1",
                            "AccountName": "Main",
                            "AccountType": "Client",
                            "Currency": "USD",
                        }
                    ]
                }
            ],
            f"{base_url}/openapi/port/v1/balances/me": [
                {
                    "Data": [
                        {
                            "AccountKey": "A1",
                            "LastUpdated": "2026-01-31T12:00:00Z",
                            "Currency": "USD",
                            "TotalValue": "1000.50",
                            "CashAvailable": "250.25",
                        }
                    ],
                    "__next": "/openapi/port/v1/balances/me?page=2",
                }
            ],
            f"{base_url}/openapi/port/v1/balances/me?page=2": [
                {
                    "Data": [
                        {
                            "AccountKey": "A1",
                            "LastUpdated": "2026-01-31T12:00:00Z",
                            "Currency": "EUR",
                            "TotalValue": "30.00",
                            "CashAvailable": "20.00",
                        }
                    ]
                }
            ],
            f"{base_url}/openapi/port/v1/positions/me": [
                {
                    "Data": [
                        {
                            "AccountKey": "A1",
                            "Isin": "US0378331005",
                            "LastUpdated": "2026-01-31T12:00:00Z",
                            "Quantity": "10",
                            "AverageOpenPrice": "150.00",
                            "Price": "180.00",
                            "MarketValue": "1800.00",
                        }
                    ]
                }
            ],
            f"{base_url}/openapi/port/v1/transactions/me": [
                {
                    "Data": [
                        {
                            "AccountKey": "A1",
                            "TransactionId": "T1",
                            "Type": "Dividend",
                            "TradeDate": "2026-01-29T12:00:00Z",
                            "SettlementDate": "2026-01-30T12:00:00Z",
                            "GrossAmount": "10.00",
                            "Commission": "0.00",
                            "Taxes": "1.50",
                            "NetAmount": "8.50",
                            "Currency": "USD",
                            "Isin": "US0378331005",
                            "Description": "Cash dividend",
                        }
                    ]
                }
            ],
        }
    )
    adapter = SaxoReadOnlyAdapter(
        base_url=base_url,
        access_token=credential_value,
        client=fake_client,
    )

    accounts = list(adapter.list_accounts())
    balances = list(adapter.fetch_balances(since_utc))
    positions = list(adapter.fetch_positions(since_utc))
    transactions = list(adapter.fetch_transactions(since_utc))

    assert len(accounts) == 1
    assert accounts[0].external_account_id == "A1"
    assert accounts[0].account_label == "Main"
    assert accounts[0].base_currency == "USD"

    assert len(balances) == 2
    assert balances[0].balance_amount == Decimal("1000.50")
    assert balances[0].available_amount == Decimal("250.25")
    assert balances[1].currency == "EUR"

    assert len(positions) == 1
    assert positions[0].instrument_ref == "US0378331005"
    assert positions[0].market_value == Decimal("1800.00")

    assert len(transactions) == 1
    assert transactions[0].txn_type == "dividend"
    assert transactions[0].trade_side is None
    assert transactions[0].net_amount == Decimal("8.50")
    assert transactions[0].instrument_ref == "US0378331005"

    first_balance_call = fake_client.calls[1]
    second_balance_call = fake_client.calls[2]
    assert first_balance_call["url"] == f"{base_url}/openapi/port/v1/balances/me"
    assert first_balance_call["params"] == {"from_utc": since_utc.isoformat()}
    assert second_balance_call["url"] == f"{base_url}/openapi/port/v1/balances/me?page=2"
    assert second_balance_call["params"] is None


def test_validate_read_only_scope_requires_access_token() -> None:
    adapter = SaxoReadOnlyAdapter(
        base_url="https://saxo.example",
        access_token="",
        client=_FakeHttpClient({}),
    )

    with pytest.raises(ValueError, match="SAXO_ACCESS_TOKEN is required"):
        adapter.validate_read_only_scope()


def test_validate_read_only_scope_rejects_empty_permissions() -> None:
    base_url = "https://saxo.example"
    adapter = SaxoReadOnlyAdapter(
        base_url=base_url,
        access_token=uuid4().hex,
        client=_FakeHttpClient({f"{base_url}/openapi/port/v1/permissions": [{"Permissions": []}]}),
    )

    with pytest.raises(ValueError, match="did not include any permissions"):
        adapter.validate_read_only_scope()


def test_saxo_response_validation_errors() -> None:
    base_url = "https://saxo.example"
    adapter_bad_data = SaxoReadOnlyAdapter(
        base_url=base_url,
        access_token=uuid4().hex,
        client=_FakeHttpClient({f"{base_url}/openapi/port/v1/accounts/me": [{"Data": "bad"}]}),
    )
    with pytest.raises(ValueError, match="does not include a list `Data` field"):
        list(adapter_bad_data.list_accounts())

    adapter_bad_row = SaxoReadOnlyAdapter(
        base_url=base_url,
        access_token=uuid4().hex,
        client=_FakeHttpClient({f"{base_url}/openapi/port/v1/accounts/me": [{"Data": ["bad"]}]}),
    )
    with pytest.raises(ValueError, match="contains a non-object row"):
        list(adapter_bad_row.list_accounts())

    adapter_bad_json = SaxoReadOnlyAdapter(
        base_url=base_url,
        access_token=uuid4().hex,
        client=_FakeHttpClient({f"{base_url}/openapi/port/v1/permissions": [["bad"]]}),
    )
    with pytest.raises(ValueError, match="is not a JSON object"):
        adapter_bad_json._get_json("/openapi/port/v1/permissions")


def test_saxo_helper_methods_cover_unmapped_paths() -> None:
    adapter = SaxoReadOnlyAdapter(
        base_url="https://saxo.example",
        access_token=uuid4().hex,
        client=_FakeHttpClient({}),
    )

    assert adapter._extract_permissions({"permissions": [{"permission": "portfolio.read"}]}) == [
        "portfolio.read"
    ]
    assert adapter._extract_permissions({"Permissions": "invalid"}) == []

    position = adapter._map_position(
        {
            "AccountKey": "A1",
            "Uic": "12345",
            "AsOfUtc": "2026-01-31T12:00:00Z",
            "Amount": "3",
        }
    )
    assert position.instrument_ref == "12345"

    txn = adapter._map_transaction(
        {
            "AccountKey": "A1",
            "TransactionId": "T-1",
            "Type": "other",
            "Side": "b",
            "Uic": "12345",
            "TradeDate": "2026-01-10T12:00:00Z",
            "Amount": "10.00",
            "Fee": "1.00",
            "Tax": "2.00",
            "Currency": "USD",
        }
    )
    assert txn.trade_side == "buy"
    assert txn.instrument_ref == "12345"
    assert txn.net_amount == Decimal("7.00")

    assert adapter._map_txn_type("orderFill") == "trade"
    assert adapter._map_txn_type("interest payment") == "interest"
    assert adapter._map_txn_type("cash deposit") == "deposit"
    assert adapter._map_txn_type("withdraw funds") == "withdrawal"
    assert adapter._map_txn_type("commission charge") == "fee"
    assert adapter._map_txn_type("unknown") == "other"

    assert adapter._map_trade_side("s") == "sell"
    assert adapter._map_trade_side("unknown") is None

    assert adapter._build_url("https://saxo.example/path") == "https://saxo.example/path"
    assert adapter._resolve_next_url(None) == ""
    assert adapter._to_utc_isoformat(datetime(2026, 1, 1, 12, 0)) == datetime(
        2026, 1, 1, 12, 0, tzinfo=timezone.utc
    ).isoformat()

    with pytest.raises(ValueError, match="missing required field"):
        adapter._required_str({}, "AccountKey")
    with pytest.raises(ValueError, match="empty required field"):
        adapter._required_str({"AccountKey": " "}, "AccountKey")
    with pytest.raises(ValueError, match="Missing required datetime"):
        adapter._datetime(None)
    with pytest.raises(ValueError, match="Cannot parse datetime value"):
        adapter._datetime(123)
    with pytest.raises(ValueError, match="Invalid currency code"):
        adapter._currency("US")
