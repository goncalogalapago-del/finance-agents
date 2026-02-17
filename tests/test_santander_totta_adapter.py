from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from uuid import uuid4

import httpx
import pytest

from app.adapters.santander_totta_read_only import SantanderTottaReadOnlyAdapter


class _FakeHttpClient:
    def __init__(self, payloads: dict[str, list[dict[str, Any]]]) -> None:
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


def test_validate_read_only_scope_requires_token() -> None:
    adapter = SantanderTottaReadOnlyAdapter(
        base_url="https://bank.example",
        access_token="",
        client=_FakeHttpClient({}),
    )
    with pytest.raises(ValueError, match="SANTANDER_TOTTA_ACCESS_TOKEN is required"):
        adapter.validate_read_only_scope()


def test_validate_read_only_scope_checks_accounts_endpoint() -> None:
    base_url = "https://bank.example"
    fake_client = _FakeHttpClient({f"{base_url}/accounts": [{"accounts": []}]})
    adapter = SantanderTottaReadOnlyAdapter(
        base_url=base_url,
        access_token=uuid4().hex,
        client=fake_client,
    )

    adapter.validate_read_only_scope()

    assert len(fake_client.calls) == 1
    assert fake_client.calls[0]["url"] == f"{base_url}/accounts"


def test_fetch_methods_map_payloads() -> None:
    since_utc = datetime(2026, 1, 1, tzinfo=timezone.utc)
    base_url = "https://bank.example"
    account_payload = {
        "accounts": [
            {
                "resourceId": "acct-1",
                "name": "Conta Ordem",
                "cashAccountType": "CACC",
                "currency": "EUR",
            }
        ]
    }
    fake_client = _FakeHttpClient(
        {
            f"{base_url}/accounts": [account_payload, account_payload, account_payload],
            f"{base_url}/accounts/acct-1/balances": [
                {"balances": [{"balanceAmount": "1000.10", "currency": "EUR"}]}
            ],
            f"{base_url}/accounts/acct-1/transactions": [
                {
                    "transactions": [
                        {
                            "transactionId": "txn-1",
                            "bookingDate": "2025-12-01",
                            "transactionAmount": "-10.00",
                            "currency": "EUR",
                            "remittanceInformationUnstructured": "old",
                        },
                        {
                            "transactionId": "txn-2",
                            "bookingDate": "2026-01-15",
                            "transactionAmount": "5.00",
                            "currency": "EUR",
                            "remittanceInformationUnstructured": "new",
                        },
                    ]
                }
            ],
        }
    )
    adapter = SantanderTottaReadOnlyAdapter(
        base_url=base_url,
        access_token=uuid4().hex,
        client=fake_client,
    )

    accounts = list(adapter.list_accounts())
    balances = list(adapter.fetch_balances(since_utc))
    positions = list(adapter.fetch_positions(since_utc))
    transactions = list(adapter.fetch_transactions(since_utc))

    assert len(accounts) == 1
    assert accounts[0].external_account_id == "acct-1"
    assert accounts[0].base_currency == "EUR"

    assert len(balances) == 1
    assert balances[0].balance_amount == Decimal("1000.10")
    assert balances[0].currency == "EUR"

    assert positions == []

    assert len(transactions) == 1
    assert transactions[0].external_txn_id == "txn-2"
    assert transactions[0].txn_type == "deposit"
    assert transactions[0].net_amount == Decimal("5.00")


def test_accounts_payload_validation() -> None:
    base_url = "https://bank.example"
    adapter = SantanderTottaReadOnlyAdapter(
        base_url=base_url,
        access_token=uuid4().hex,
        client=_FakeHttpClient({f"{base_url}/accounts": [{"accounts": "bad"}]}),
    )
    with pytest.raises(ValueError, match="missing list `accounts`"):
        list(adapter.list_accounts())
