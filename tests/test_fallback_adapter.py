from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from app.adapters.contracts import (
    AccountDTO,
    AdapterCapabilities,
    BalanceDTO,
    InstitutionKind,
    PositionDTO,
    TransactionDTO,
)
from app.adapters.fallback import FallbackReadOnlyAdapter


class _Adapter:
    def __init__(self, *, provider_code: str, fail_methods: set[str] | None = None) -> None:
        self.provider_code = provider_code
        self.institution_kind = InstitutionKind.BROKER
        self.capabilities = AdapterCapabilities()
        self.fail_methods = fail_methods or set()
        self.calls: list[str] = []

    def _maybe_fail(self, method_name: str) -> None:
        self.calls.append(method_name)
        if method_name in self.fail_methods:
            raise RuntimeError(f"{method_name} failed")

    def validate_read_only_scope(self) -> None:
        self._maybe_fail("validate_read_only_scope")

    def list_accounts(self) -> list[AccountDTO]:
        self._maybe_fail("list_accounts")
        return [
            AccountDTO(
                external_account_id="acct-1",
                account_label="Main",
                account_type="brokerage",
                base_currency="USD",
            )
        ]

    def fetch_balances(self, since_utc: datetime) -> list[BalanceDTO]:
        self._maybe_fail("fetch_balances")
        return [
            BalanceDTO(
                external_account_id="acct-1",
                as_of_utc=since_utc,
                currency="USD",
                balance_amount=Decimal("100.00"),
                available_amount=Decimal("80.00"),
            )
        ]

    def fetch_positions(self, since_utc: datetime) -> list[PositionDTO]:
        self._maybe_fail("fetch_positions")
        return [
            PositionDTO(
                external_account_id="acct-1",
                instrument_ref="US0378331005",
                as_of_utc=since_utc,
                quantity=Decimal("1.0"),
                avg_cost=Decimal("10.00"),
                market_price=Decimal("12.00"),
                market_value=Decimal("12.00"),
            )
        ]

    def fetch_transactions(self, since_utc: datetime) -> list[TransactionDTO]:
        self._maybe_fail("fetch_transactions")
        return [
            TransactionDTO(
                external_account_id="acct-1",
                external_txn_id="txn-1",
                txn_type="deposit",
                trade_side=None,
                instrument_ref=None,
                executed_at_utc=since_utc,
                settled_at_utc=since_utc,
                quantity=None,
                price=None,
                gross_amount=Decimal("10.00"),
                fee_amount=Decimal("0.00"),
                tax_amount=Decimal("0.00"),
                net_amount=Decimal("10.00"),
                currency="USD",
                raw_category="seed",
            )
        ]


def test_rejects_mismatched_provider_codes() -> None:
    primary = _Adapter(provider_code="SAXO")
    fallback = _Adapter(provider_code="FIXTURE")

    with pytest.raises(ValueError, match="provider_code must match"):
        FallbackReadOnlyAdapter(primary=primary, fallback=fallback)


def test_uses_primary_adapter_and_normalizes_iterables() -> None:
    adapter = FallbackReadOnlyAdapter(
        primary=_Adapter(provider_code="SAXO"),
        fallback=_Adapter(provider_code="SAXO"),
    )
    since_utc = datetime(2026, 1, 1, tzinfo=timezone.utc)

    assert adapter.provider_code == "SAXO"
    adapter.validate_read_only_scope()
    assert adapter.list_accounts()[0].external_account_id == "acct-1"
    assert adapter.fetch_balances(since_utc)[0].balance_amount == Decimal("100.00")
    assert adapter.fetch_positions(since_utc)[0].instrument_ref == "US0378331005"
    assert adapter.fetch_transactions(since_utc)[0].external_txn_id == "txn-1"


def test_falls_back_when_primary_raises() -> None:
    primary = _Adapter(
        provider_code="SAXO",
        fail_methods={
            "validate_read_only_scope",
            "list_accounts",
            "fetch_balances",
            "fetch_positions",
            "fetch_transactions",
        },
    )
    fallback = _Adapter(provider_code="SAXO")
    adapter = FallbackReadOnlyAdapter(primary=primary, fallback=fallback)
    since_utc = datetime(2026, 1, 1, tzinfo=timezone.utc)

    adapter.validate_read_only_scope()
    assert adapter.list_accounts()[0].external_account_id == "acct-1"
    assert adapter.fetch_balances(since_utc)[0].balance_amount == Decimal("100.00")
    assert adapter.fetch_positions(since_utc)[0].instrument_ref == "US0378331005"
    assert adapter.fetch_transactions(since_utc)[0].external_txn_id == "txn-1"
    assert primary.calls == [
        "validate_read_only_scope",
        "list_accounts",
        "fetch_balances",
        "fetch_positions",
        "fetch_transactions",
    ]
    assert fallback.calls == [
        "validate_read_only_scope",
        "list_accounts",
        "fetch_balances",
        "fetch_positions",
        "fetch_transactions",
    ]
