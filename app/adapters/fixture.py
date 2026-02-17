from collections.abc import Iterable
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from app.adapters.contracts import (
    AccountDTO,
    BalanceDTO,
    PositionDTO,
    ReadOnlyFinanceAdapter,
    TransactionDTO,
)

FIXTURE_SNAPSHOT_UTC = datetime(2026, 1, 31, 16, 0, tzinfo=timezone.utc)
FIXTURE_EXECUTED_UTC = datetime(2026, 1, 29, 16, 0, tzinfo=timezone.utc)


class FixtureReadOnlyAdapter(ReadOnlyFinanceAdapter):
    """Deterministic adapter used to wire ingestion flow before provider APIs."""

    provider_code = "FIXTURE"

    def validate_read_only_scope(self) -> None:
        return None

    def list_accounts(self) -> Iterable[AccountDTO]:
        return [
            AccountDTO(
                external_account_id="fixture-broker-001",
                account_label="Fixture Main",
                account_type="brokerage",
                base_currency="USD",
            )
        ]

    def fetch_balances(self, since_utc: datetime) -> Iterable[BalanceDTO]:
        return [
            BalanceDTO(
                external_account_id="fixture-broker-001",
                as_of_utc=FIXTURE_SNAPSHOT_UTC,
                currency="USD",
                balance_amount=Decimal("10250.15"),
                available_amount=Decimal("1250.15"),
            )
        ]

    def fetch_positions(self, since_utc: datetime) -> Iterable[PositionDTO]:
        return [
            PositionDTO(
                external_account_id="fixture-broker-001",
                instrument_ref="US0378331005",
                as_of_utc=FIXTURE_SNAPSHOT_UTC,
                quantity=Decimal("12.0"),
                avg_cost=Decimal("165.00"),
                market_price=Decimal("190.00"),
                market_value=Decimal("2280.00"),
            )
        ]

    def fetch_transactions(self, since_utc: datetime) -> Iterable[TransactionDTO]:
        return [
            TransactionDTO(
                external_account_id="fixture-broker-001",
                external_txn_id="fixture-txn-001",
                txn_type="dividend",
                trade_side=None,
                instrument_ref="US0378331005",
                executed_at_utc=FIXTURE_EXECUTED_UTC,
                settled_at_utc=FIXTURE_EXECUTED_UTC + timedelta(days=1),
                quantity=None,
                price=None,
                gross_amount=Decimal("10.00"),
                fee_amount=Decimal("0.00"),
                tax_amount=Decimal("1.50"),
                net_amount=Decimal("8.50"),
                currency="USD",
                raw_category="cash_dividend",
            )
        ]
