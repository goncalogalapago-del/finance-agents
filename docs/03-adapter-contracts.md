# Read-Only Adapter Contracts (MVP)

## Goals

- Provider implementations are swappable.
- API ingestion is primary; CSV fallback is supported.
- All adapters output canonical DTOs.

## Python Interface (Proposed)

```python
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Iterable, Protocol

@dataclass(frozen=True)
class BalanceDTO:
    external_account_id: str
    as_of_utc: datetime
    currency: str
    balance_amount: Decimal
    available_amount: Decimal | None

@dataclass(frozen=True)
class PositionDTO:
    external_account_id: str
    instrument_ref: str  # ISIN preferred, symbol fallback
    as_of_utc: datetime
    quantity: Decimal
    avg_cost: Decimal | None
    market_price: Decimal | None
    market_value: Decimal | None

@dataclass(frozen=True)
class TransactionDTO:
    external_account_id: str
    external_txn_id: str
    txn_type: str
    trade_side: str | None
    instrument_ref: str | None
    executed_at_utc: datetime
    settled_at_utc: datetime | None
    quantity: Decimal | None
    price: Decimal | None
    gross_amount: Decimal | None
    fee_amount: Decimal | None
    tax_amount: Decimal | None
    net_amount: Decimal
    currency: str
    raw_category: str | None

class ReadOnlyFinanceAdapter(Protocol):
    provider_code: str

    def validate_read_only_scope(self) -> None: ...
    def list_accounts(self) -> Iterable[dict]: ...
    def fetch_balances(self, since_utc: datetime) -> Iterable[BalanceDTO]: ...
    def fetch_positions(self, since_utc: datetime) -> Iterable[PositionDTO]: ...
    def fetch_transactions(self, since_utc: datetime) -> Iterable[TransactionDTO]: ...
```

## Required Adapter Behaviors

- Enforce read-only scope check at startup.
- Support pagination with retry + bounded backoff.
- Produce stable idempotency identifiers.
- Emit metadata-only audit events for pulls.
- Never log secrets or raw auth headers.

## CSV Fallback Contract

Per provider CSV importers must map source columns to canonical DTOs and provide:
- schema version
- source filename checksum
- parse errors with row numbers
- import run id for audit correlation

## Provider Modules (Initial)

- `adapters/saxo_read_only.py`
- `adapters/lunar_read_only.py`
- `adapters/csv/saxo_csv.py`
- `adapters/csv/lunar_csv.py`

