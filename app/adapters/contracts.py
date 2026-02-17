from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Optional, Protocol


@dataclass(frozen=True)
class AccountDTO:
    external_account_id: str
    account_label: str
    account_type: str
    base_currency: str


@dataclass(frozen=True)
class BalanceDTO:
    external_account_id: str
    as_of_utc: datetime
    currency: str
    balance_amount: Decimal
    available_amount: Optional[Decimal]


@dataclass(frozen=True)
class PositionDTO:
    external_account_id: str
    instrument_ref: str
    as_of_utc: datetime
    quantity: Decimal
    avg_cost: Optional[Decimal]
    market_price: Optional[Decimal]
    market_value: Optional[Decimal]


@dataclass(frozen=True)
class TransactionDTO:
    external_account_id: str
    external_txn_id: str
    txn_type: str
    trade_side: Optional[str]
    instrument_ref: Optional[str]
    executed_at_utc: datetime
    settled_at_utc: Optional[datetime]
    quantity: Optional[Decimal]
    price: Optional[Decimal]
    gross_amount: Optional[Decimal]
    fee_amount: Optional[Decimal]
    tax_amount: Optional[Decimal]
    net_amount: Decimal
    currency: str
    raw_category: Optional[str]


class ReadOnlyFinanceAdapter(Protocol):
    provider_code: str

    def validate_read_only_scope(self) -> None:
        ...

    def list_accounts(self) -> Iterable[AccountDTO]:
        ...

    def fetch_balances(self, since_utc: datetime) -> Iterable[BalanceDTO]:
        ...

    def fetch_positions(self, since_utc: datetime) -> Iterable[PositionDTO]:
        ...

    def fetch_transactions(self, since_utc: datetime) -> Iterable[TransactionDTO]:
        ...
