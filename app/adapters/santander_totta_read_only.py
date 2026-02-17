from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Protocol
from uuid import uuid4

from app.adapters.contracts import (
    AccountDTO,
    AdapterCapabilities,
    BalanceDTO,
    InstitutionKind,
    PositionDTO,
    ReadOnlyFinanceAdapter,
    TransactionDTO,
)
from app.adapters.http_client import RetryRateLimitedHttpClient


class _HttpClient(Protocol):
    def request(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str] | None = None,
        params: Mapping[str, Any] | None = None,
    ) -> Any:
        ...


class SantanderTottaReadOnlyAdapter(ReadOnlyFinanceAdapter):
    provider_code = "SANTANDER_TOTTA"
    institution_kind = InstitutionKind.BANK
    capabilities = AdapterCapabilities(supports_positions=False)

    def __init__(
        self,
        *,
        base_url: str,
        access_token: str,
        client: _HttpClient | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._access_token = access_token.strip()
        self._client = client or RetryRateLimitedHttpClient(
            max_retries=3,
            backoff_seconds=0.5,
            requests_per_second=5.0,
            timeout_seconds=20.0,
        )

    def validate_read_only_scope(self) -> None:
        if not self._access_token:
            raise ValueError(
                "SANTANDER_TOTTA_ACCESS_TOKEN is required to use santander_totta adapter"
            )
        self._get_json("/accounts")

    def list_accounts(self) -> Iterable[AccountDTO]:
        payload = self._get_json("/accounts")
        for raw in self._accounts_from_payload(payload):
            yield self._map_account(raw)

    def fetch_balances(self, since_utc: datetime) -> Iterable[BalanceDTO]:
        del since_utc
        now_utc = datetime.now(timezone.utc).replace(microsecond=0)
        for account in self.list_accounts():
            payload = self._get_json(f"/accounts/{account.external_account_id}/balances")
            balances = payload.get("balances")
            if not isinstance(balances, list):
                continue
            for row in balances:
                if not isinstance(row, dict):
                    continue
                amount = self._decimal(
                    row.get("balanceAmount")
                    or row.get("amount")
                    or row.get("currentBalance")
                    or "0"
                )
                yield BalanceDTO(
                    external_account_id=account.external_account_id,
                    as_of_utc=now_utc,
                    currency=self._currency(row.get("currency") or account.base_currency),
                    balance_amount=amount,
                    available_amount=amount,
                )

    def fetch_positions(self, since_utc: datetime) -> Iterable[PositionDTO]:
        del since_utc
        return []

    def fetch_transactions(self, since_utc: datetime) -> Iterable[TransactionDTO]:
        since_utc_normalized = self._normalize_utc(since_utc)
        for account in self.list_accounts():
            payload = self._get_json(f"/accounts/{account.external_account_id}/transactions")
            transactions = payload.get("transactions")
            if not isinstance(transactions, list):
                continue
            for row in transactions:
                if not isinstance(row, dict):
                    continue
                dto = self._map_transaction(
                    account_id=account.external_account_id,
                    currency=account.base_currency,
                    raw=row,
                )
                if dto.executed_at_utc >= since_utc_normalized:
                    yield dto

    def _get_json(
        self,
        path: str,
        *,
        params: Mapping[str, str] | None = None,
    ) -> dict[str, Any]:
        response = self._client.request(
            "GET",
            self._build_url(path),
            headers=self._auth_headers(),
            params=params,
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError(f"Santander Totta response at `{path}` is not a JSON object")
        return payload

    def _accounts_from_payload(self, payload: dict[str, Any]) -> list[dict[str, Any]]:
        raw_accounts = payload.get("accounts")
        if not isinstance(raw_accounts, list):
            raise ValueError("Santander Totta accounts response missing list `accounts`")
        return [row for row in raw_accounts if isinstance(row, dict)]

    def _map_account(self, raw: dict[str, Any]) -> AccountDTO:
        account_id = self._required_str(raw, "resourceId")
        iban = self._optional_str(raw.get("iban"))
        account_label = self._optional_str(raw.get("name")) or iban or account_id
        account_type = self._optional_str(raw.get("cashAccountType")) or "bank"
        currency = self._currency(raw.get("currency") or "EUR")
        return AccountDTO(
            external_account_id=account_id,
            account_label=account_label,
            account_type=account_type.lower(),
            base_currency=currency,
        )

    def _map_transaction(
        self,
        *,
        account_id: str,
        currency: str,
        raw: dict[str, Any],
    ) -> TransactionDTO:
        booking_date = raw.get("bookingDate") or raw.get("valueDate") or raw.get("date")
        executed_at_utc = self._datetime(booking_date)
        amount_value = self._decimal(raw.get("transactionAmount") or raw.get("amount") or "0")
        txn_type = "deposit" if amount_value >= Decimal("0") else "withdrawal"
        transaction_id = self._optional_str(raw.get("transactionId")) or str(uuid4())
        return TransactionDTO(
            external_account_id=account_id,
            external_txn_id=transaction_id,
            txn_type=txn_type,
            trade_side=None,
            instrument_ref=None,
            executed_at_utc=executed_at_utc,
            settled_at_utc=self._optional_datetime(raw.get("valueDate")),
            quantity=None,
            price=None,
            gross_amount=amount_value,
            fee_amount=None,
            tax_amount=None,
            net_amount=amount_value,
            currency=self._currency(raw.get("currency") or currency),
            raw_category=self._optional_str(raw.get("remittanceInformationUnstructured"))
            or self._optional_str(raw.get("bankTransactionCode")),
        )

    def _auth_headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._access_token}",
            "Accept": "application/json",
            "X-Request-ID": str(uuid4()),
        }

    def _build_url(self, path: str) -> str:
        if path.startswith("http://") or path.startswith("https://"):
            return path
        return f"{self._base_url}{path}"

    @staticmethod
    def _required_str(raw: dict[str, Any], key: str) -> str:
        value = raw.get(key)
        if value is None:
            raise ValueError(f"Santander Totta payload missing required field `{key}`")
        text = str(value).strip()
        if not text:
            raise ValueError(f"Santander Totta payload has empty required field `{key}`")
        return text

    @staticmethod
    def _optional_str(value: Any) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    @staticmethod
    def _decimal(value: Any) -> Decimal:
        try:
            return Decimal(str(value))
        except Exception as exc:
            raise ValueError(f"Cannot parse decimal value `{value}`") from exc

    @staticmethod
    def _datetime(value: Any) -> datetime:
        if value is None:
            raise ValueError("Missing required datetime value in Santander Totta payload")
        if isinstance(value, datetime):
            return SantanderTottaReadOnlyAdapter._normalize_utc(value)
        if not isinstance(value, str):
            raise ValueError(f"Cannot parse datetime value `{value}`")
        normalized = value.strip()
        if "T" not in normalized:
            normalized = f"{normalized}T00:00:00+00:00"
        normalized = normalized.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(normalized)
        return SantanderTottaReadOnlyAdapter._normalize_utc(parsed)

    @staticmethod
    def _optional_datetime(value: Any) -> datetime | None:
        if value is None:
            return None
        return SantanderTottaReadOnlyAdapter._datetime(value)

    @staticmethod
    def _normalize_utc(value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    @staticmethod
    def _currency(value: Any) -> str:
        currency = str(value).strip().upper()
        if len(currency) != 3:
            raise ValueError(f"Invalid currency code `{value}`")
        return currency
