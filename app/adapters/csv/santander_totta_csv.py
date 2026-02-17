from __future__ import annotations

import csv
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

from app.adapters.contracts import (
    AccountDTO,
    AdapterCapabilities,
    BalanceDTO,
    InstitutionKind,
    PositionDTO,
    ReadOnlyFinanceAdapter,
    TransactionDTO,
)


class SantanderTottaCsvReadOnlyAdapter(ReadOnlyFinanceAdapter):
    provider_code = "SANTANDER_TOTTA"
    institution_kind = InstitutionKind.BANK
    capabilities = AdapterCapabilities(supports_positions=False)

    def __init__(self, *, csv_dir: str) -> None:
        self._csv_dir = Path(csv_dir).expanduser()

    def validate_read_only_scope(self) -> None:
        if not self._csv_dir.exists() or not self._csv_dir.is_dir():
            raise ValueError(f"Santander Totta CSV directory does not exist: {self._csv_dir}")
        accounts_path = self._csv_dir / "accounts.csv"
        if not accounts_path.exists():
            raise ValueError(
                "Santander Totta CSV fallback requires accounts.csv "
                f"at {accounts_path}"
            )

    def list_accounts(self) -> list[AccountDTO]:
        accounts: list[AccountDTO] = []
        for row in self._rows("accounts.csv"):
            accounts.append(
                AccountDTO(
                    external_account_id=self._required_str(row, "external_account_id"),
                    account_label=self._required_str(row, "account_label"),
                    account_type=self._required_str(row, "account_type"),
                    base_currency=self._currency(self._required_str(row, "base_currency")),
                )
            )
        return accounts

    def fetch_balances(self, since_utc: datetime) -> list[BalanceDTO]:
        balances: list[BalanceDTO] = []
        for row in self._rows("balances.csv"):
            as_of_utc = self._datetime(self._required_str(row, "as_of_utc"))
            if as_of_utc < self._normalize_utc(since_utc):
                continue
            balances.append(
                BalanceDTO(
                    external_account_id=self._required_str(row, "external_account_id"),
                    as_of_utc=as_of_utc,
                    currency=self._currency(self._required_str(row, "currency")),
                    balance_amount=self._decimal(self._required_str(row, "balance_amount")),
                    available_amount=self._optional_decimal(row.get("available_amount")),
                )
            )
        return balances

    def fetch_positions(self, since_utc: datetime) -> list[PositionDTO]:
        del since_utc
        return []

    def fetch_transactions(self, since_utc: datetime) -> list[TransactionDTO]:
        transactions: list[TransactionDTO] = []
        for row in self._rows("transactions.csv"):
            executed_at_utc = self._datetime(self._required_str(row, "executed_at_utc"))
            if executed_at_utc < self._normalize_utc(since_utc):
                continue
            transactions.append(
                TransactionDTO(
                    external_account_id=self._required_str(row, "external_account_id"),
                    external_txn_id=self._required_str(row, "external_txn_id"),
                    txn_type=self._required_str(row, "txn_type"),
                    trade_side=None,
                    instrument_ref=None,
                    executed_at_utc=executed_at_utc,
                    settled_at_utc=self._optional_datetime(row.get("settled_at_utc")),
                    quantity=None,
                    price=None,
                    gross_amount=self._optional_decimal(row.get("gross_amount")),
                    fee_amount=self._optional_decimal(row.get("fee_amount")),
                    tax_amount=self._optional_decimal(row.get("tax_amount")),
                    net_amount=self._decimal(self._required_str(row, "net_amount")),
                    currency=self._currency(self._required_str(row, "currency")),
                    raw_category=self._optional_str(row.get("raw_category")),
                )
            )
        return transactions

    def _rows(self, filename: str) -> list[dict[str, str]]:
        path = self._csv_dir / filename
        if not path.exists():
            return []
        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            return [dict(row) for row in reader]

    @staticmethod
    def _required_str(row: dict[str, Any], key: str) -> str:
        value = row.get(key)
        if value is None:
            raise ValueError(f"Santander Totta CSV row missing required column `{key}`")
        text = str(value).strip()
        if not text:
            raise ValueError(
                f"Santander Totta CSV row has empty value for required column `{key}`"
            )
        return text

    @staticmethod
    def _optional_str(value: Any) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    @staticmethod
    def _decimal(raw: Any) -> Decimal:
        try:
            return Decimal(str(raw))
        except Exception as exc:
            raise ValueError(
                f"Invalid decimal value `{raw}` in Santander Totta CSV input"
            ) from exc

    @classmethod
    def _optional_decimal(cls, raw: Any) -> Decimal | None:
        text = cls._optional_str(raw)
        if text is None:
            return None
        return cls._decimal(text)

    @staticmethod
    def _datetime(raw: str) -> datetime:
        normalized = raw.strip().replace("Z", "+00:00")
        if "T" not in normalized:
            normalized = f"{normalized}T00:00:00+00:00"
        parsed = datetime.fromisoformat(normalized)
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)

    @classmethod
    def _optional_datetime(cls, raw: Any) -> datetime | None:
        text = cls._optional_str(raw)
        if text is None:
            return None
        return cls._datetime(text)

    @staticmethod
    def _normalize_utc(value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    @staticmethod
    def _currency(raw: str) -> str:
        currency = raw.strip().upper()
        if len(currency) != 3:
            raise ValueError(f"Invalid currency code `{raw}` in Santander Totta CSV input")
        return currency
