from __future__ import annotations

import base64
import json
from collections.abc import Mapping
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

import httpx
import pytest

from app.adapters.lunar_read_only import LunarReadOnlyAdapter


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
        self.calls.append({"method": method, "url": url, "headers": headers, "params": params})
        queue = self._payloads.get(url)
        if not queue:
            raise AssertionError(f"Unexpected request URL in test client: {url}")
        payload = queue.pop(0)
        request = httpx.Request(method=method, url=url, headers=headers, params=params)
        return httpx.Response(200, json=payload, request=request)


def _token_with_scope(scope: str | list[str]) -> str:
    payload = {"scope": scope}
    encoded = base64.urlsafe_b64encode(json.dumps(payload).encode("utf-8")).decode("utf-8")
    return f"header.{encoded.rstrip('=')}.sig"


def test_validate_read_only_scope_requires_access_token() -> None:
    adapter = LunarReadOnlyAdapter(
        base_url="https://lunar.example",
        access_token="",
        device_id="device",
        os_name="linux",
        client=_FakeHttpClient({}),
    )

    with pytest.raises(ValueError, match="LUNAR_ACCESS_TOKEN is required"):
        adapter.validate_read_only_scope()


def test_validate_read_only_scope_enforces_scope_rules() -> None:
    base_url = "https://lunar.example"

    missing_scope = LunarReadOnlyAdapter(
        base_url=base_url,
        access_token=_token_with_scope("OTHER_SCOPE"),
        device_id="device",
        os_name="linux",
        client=_FakeHttpClient({}),
    )
    with pytest.raises(ValueError, match="missing required read scope"):
        missing_scope.validate_read_only_scope()

    forbidden_scope = LunarReadOnlyAdapter(
        base_url=base_url,
        access_token=_token_with_scope(["PSP_AI", "PSP_PI"]),
        device_id="device",
        os_name="linux",
        client=_FakeHttpClient({}),
    )
    with pytest.raises(ValueError, match="forbidden scope detected"):
        forbidden_scope.validate_read_only_scope()


def test_validate_read_only_scope_calls_accounts_endpoint_when_scope_is_valid() -> None:
    base_url = "https://lunar.example"
    fake_client = _FakeHttpClient(
        {
            f"{base_url}/accounts": [
                {"accounts": []},
            ]
        }
    )
    adapter = LunarReadOnlyAdapter(
        base_url=base_url,
        access_token=_token_with_scope("PSP_AI"),
        device_id="device-id",
        os_name="ios",
        client=fake_client,
    )

    adapter.validate_read_only_scope()

    assert fake_client.calls[0]["method"] == "GET"
    assert fake_client.calls[0]["headers"]["Authorization"].startswith("Bearer ")
    assert fake_client.calls[0]["headers"]["X-DeviceId"] == "device-id"
    assert fake_client.calls[0]["headers"]["X-Os"] == "ios"


def test_fetch_methods_map_payloads_and_filter_transactions() -> None:
    since_utc = datetime(2026, 1, 1, tzinfo=timezone.utc)
    base_url = "https://lunar.example"

    fake_client = _FakeHttpClient(
        {
            f"{base_url}/accounts": [
                {
                    "accounts": [
                        {
                            "id": "acct-1",
                            "name": "Main",
                            "type": "Personal",
                            "currency": "dkk",
                            "balances": [
                                {"amount": "1250.50"},
                                "invalid-balance-row",
                            ],
                        }
                    ]
                },
                    {
                        "accounts": [
                            {
                                "id": "acct-1",
                                "name": "Main",
                                "type": "Personal",
                                "currency": "DKK",
                                "balances": [{"amount": "1250.50"}],
                            }
                        ]
                    },
                {
                    "accounts": [
                        {
                            "id": "acct-1",
                            "name": "Main",
                            "type": "Personal",
                            "currency": "DKK",
                        }
                    ]
                },
            ],
            f"{base_url}/accounts/acct-1/transactions": [
                {
                    "transactions": [
                        {
                            "id": "txn-old",
                            "type": "transfer",
                            "transactionTime": "2025-12-01T10:00:00Z",
                            "bookingDate": "2025-12-01T10:00:00Z",
                            "billingAmount": {"value": "-3.00"},
                            "text": "old txn",
                        },
                        {
                            "id": "txn-new",
                            "type": "interest",
                            "transactionTime": "2026-01-10T10:00:00Z",
                            "bookingDate": "2026-01-10T10:00:00Z",
                            "amount": "5.50",
                            "currency": "DKK",
                            "text": "new txn",
                        },
                    ]
                }
            ],
        }
    )
    adapter = LunarReadOnlyAdapter(
        base_url=base_url,
        access_token=_token_with_scope("PSP_AI"),
        device_id="device-id",
        os_name="linux",
        client=fake_client,
    )

    accounts = list(adapter.list_accounts())
    balances = list(adapter.fetch_balances(since_utc))
    positions = list(adapter.fetch_positions(since_utc))
    transactions = list(adapter.fetch_transactions(since_utc))

    assert len(accounts) == 1
    assert accounts[0].external_account_id == "acct-1"
    assert accounts[0].account_type == "personal"
    assert accounts[0].base_currency == "DKK"

    assert len(balances) == 1
    assert balances[0].balance_amount == Decimal("1250.50")
    assert balances[0].currency == "DKK"

    assert positions == []

    assert len(transactions) == 1
    assert transactions[0].external_txn_id == "txn-new"
    assert transactions[0].txn_type == "interest"
    assert transactions[0].gross_amount == Decimal("5.50")
    assert transactions[0].net_amount == Decimal("5.50")


def test_fetch_transactions_requires_transactions_list() -> None:
    base_url = "https://lunar.example"
    fake_client = _FakeHttpClient(
        {
            f"{base_url}/accounts": [{"accounts": [{"id": "acct-1", "currency": "DKK"}]}],
            f"{base_url}/accounts/acct-1/transactions": [{"transactions": "invalid"}],
        }
    )
    adapter = LunarReadOnlyAdapter(
        base_url=base_url,
        access_token=_token_with_scope("PSP_AI"),
        device_id="device-id",
        os_name="linux",
        client=fake_client,
    )

    with pytest.raises(ValueError, match="missing list `transactions`"):
        list(adapter.fetch_transactions(datetime(2026, 1, 1, tzinfo=timezone.utc)))


def test_lunar_helper_methods_cover_edge_cases() -> None:
    adapter = LunarReadOnlyAdapter(
        base_url="https://lunar.example",
        access_token=_token_with_scope("PSP_AI"),
        device_id="",
        os_name="",
        client=_FakeHttpClient(
            {
                "https://lunar.example/ping": [{"ok": True}],
                "https://x": [{"x": 1}],
            }
        ),
    )

    assert adapter._build_url("/ping") == "https://lunar.example/ping"
    assert adapter._build_url("https://x") == "https://x"
    assert adapter._auth_headers()["X-DeviceId"] == "finance-agents"
    assert adapter._auth_headers()["X-Os"] == "linux"
    assert "X-Request-Id" in adapter._auth_headers()

    assert adapter._extract_scopes_from_token("not-a-jwt") == set()
    assert adapter._extract_scopes_from_token(_token_with_scope("PSP_AI PSP_X")) == {
        "PSP_AI",
        "PSP_X",
    }
    assert adapter._extract_scopes_from_token(_token_with_scope(["PSP_AI", "PSP_X"])) == {
        "PSP_AI",
        "PSP_X",
    }

    assert adapter._map_txn_type("fee_charge", Decimal("1")) == "fee"
    assert adapter._map_txn_type("interest_credit", Decimal("1")) == "interest"
    assert adapter._map_txn_type("cash_dividend", Decimal("1")) == "dividend"
    assert adapter._map_txn_type("other", Decimal("1")) == "deposit"
    assert adapter._map_txn_type("other", Decimal("-1")) == "withdrawal"

    with pytest.raises(ValueError, match="missing required field"):
        adapter._required_str({}, "id")
    with pytest.raises(ValueError, match="empty required field"):
        adapter._required_str({"id": " "}, "id")

    assert adapter._optional_str(None) is None
    assert adapter._optional_str("  x  ") == "x"

    assert adapter._extract_transaction_amount({"billingAmount": {"value": "2.00"}}) == Decimal(
        "2.00"
    )
    assert adapter._extract_transaction_amount({"billingAmount": "3.00"}) == Decimal("3.00")
    assert adapter._extract_transaction_amount({"amount": "4.00"}) == Decimal("4.00")
    assert adapter._extract_transaction_amount({}) == Decimal("0")

    assert adapter._datetime(datetime(2026, 1, 1, 12, 0)) == datetime(
        2026, 1, 1, 12, 0, tzinfo=timezone.utc
    )
    assert adapter._datetime("2026-01-01T12:00:00") == datetime(
        2026, 1, 1, 12, 0, tzinfo=timezone.utc
    )
    assert adapter._optional_datetime(None) is None
    assert adapter._optional_datetime("2026-01-01T12:00:00Z") == datetime(
        2026, 1, 1, 12, 0, tzinfo=timezone.utc
    )
    assert adapter._normalize_utc(datetime(2026, 1, 1, 12, 0)) == datetime(
        2026, 1, 1, 12, 0, tzinfo=timezone.utc
    )

    with pytest.raises(ValueError, match="Cannot parse decimal value"):
        adapter._decimal("not-decimal")
    with pytest.raises(ValueError, match="Missing required datetime"):
        adapter._datetime(None)
    with pytest.raises(ValueError, match="Cannot parse datetime value"):
        adapter._datetime(123)
    with pytest.raises(ValueError, match="Invalid currency code"):
        adapter._currency("DK")


def test_get_json_and_accounts_payload_validation_errors() -> None:
    base_url = "https://lunar.example"
    fake_client = _FakeHttpClient(
        {
            f"{base_url}/invalid-json": [["not-a-dict"]],
            f"{base_url}/accounts": [{"accounts": "invalid"}],
        }
    )
    adapter = LunarReadOnlyAdapter(
        base_url=base_url,
        access_token=_token_with_scope("PSP_AI"),
        device_id="device-id",
        os_name="linux",
        client=fake_client,
    )

    with pytest.raises(ValueError, match="is not a JSON object"):
        adapter._get_json("/invalid-json")

    with pytest.raises(ValueError, match="missing list `accounts`"):
        list(adapter.list_accounts())
