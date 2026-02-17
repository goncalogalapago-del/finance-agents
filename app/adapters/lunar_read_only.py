from __future__ import annotations

import base64
import json
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


class LunarReadOnlyAdapter(ReadOnlyFinanceAdapter):
    provider_code = "LUNAR"
    institution_kind = InstitutionKind.BANK
    capabilities = AdapterCapabilities(supports_positions=False)
    _REQUIRED_SCOPE = "PSP_AI"
    _FORBIDDEN_SCOPE = "PSP_PI"

    def __init__(
        self,
        *,
        base_url: str,
        access_token: str,
        device_id: str,
        os_name: str,
        client: _HttpClient | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._access_token = access_token.strip()
        self._device_id = device_id.strip() or "finance-agents"
        self._os_name = os_name.strip() or "linux"
        self._client = client or RetryRateLimitedHttpClient(
            max_retries=3,
            backoff_seconds=0.5,
            requests_per_second=5.0,
            timeout_seconds=20.0,
        )

    def validate_read_only_scope(self) -> None:
        if not self._access_token:
            raise ValueError("LUNAR_ACCESS_TOKEN is required to use the lunar adapter")

        scopes = self._extract_scopes_from_token(self._access_token)
        if scopes:
            if self._REQUIRED_SCOPE not in scopes:
                raise ValueError(
                    "Lunar token is missing required read scope "
                    f"`{self._REQUIRED_SCOPE}`"
                )
            if self._FORBIDDEN_SCOPE in scopes:
                raise ValueError(
                    "Lunar token is not read-only; "
                    f"forbidden scope detected: `{self._FORBIDDEN_SCOPE}`"
                )

        # Validate the token can access a read-only endpoint.
        self._get_json("/accounts")

    def list_accounts(self) -> Iterable[AccountDTO]:
        payload = self._get_json("/accounts")
        for raw in self._accounts_from_payload(payload):
            yield self._map_account(raw)

    def fetch_balances(self, since_utc: datetime) -> Iterable[BalanceDTO]:
        now_utc = datetime.now(timezone.utc).replace(microsecond=0)
        payload = self._get_json("/accounts")
        for raw in self._accounts_from_payload(payload):
            account = self._map_account(raw)
            balances = raw.get("balances")
            if not isinstance(balances, list):
                continue
            for balance in balances:
                if not isinstance(balance, dict):
                    continue
                amount = self._decimal(balance.get("amount") or "0")
                yield BalanceDTO(
                    external_account_id=account.external_account_id,
                    as_of_utc=now_utc,
                    currency=account.base_currency,
                    balance_amount=amount,
                    available_amount=amount,
                )

    def fetch_positions(self, since_utc: datetime) -> Iterable[PositionDTO]:
        del since_utc
        # Lunar AISP endpoints are account-centric; no securities positions expected.
        return []

    def fetch_transactions(self, since_utc: datetime) -> Iterable[TransactionDTO]:
        since_normalized = self._normalize_utc(since_utc)
        for account in self.list_accounts():
            offset = 0
            limit = 250
            while True:
                payload = self._get_json(
                    f"/accounts/{account.external_account_id}/transactions",
                    params={"offset": str(offset), "limit": str(limit)},
                )
                raw_rows = payload.get("transactions")
                if not isinstance(raw_rows, list):
                    raise ValueError("Lunar transactions response missing list `transactions`")
                rows = [row for row in raw_rows if isinstance(row, dict)]
                for row in rows:
                    dto = self._map_transaction(
                        account_id=account.external_account_id,
                        account_currency=account.base_currency,
                        raw=row,
                    )
                    if dto.executed_at_utc >= since_normalized:
                        yield dto
                if len(rows) < limit:
                    break
                offset += limit

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
            raise ValueError(f"Lunar response at `{path}` is not a JSON object")
        return payload

    def _accounts_from_payload(self, payload: dict[str, Any]) -> list[dict[str, Any]]:
        raw_accounts = payload.get("accounts")
        if not isinstance(raw_accounts, list):
            raise ValueError("Lunar accounts response missing list `accounts`")
        accounts = [row for row in raw_accounts if isinstance(row, dict)]
        return accounts

    def _map_account(self, raw: dict[str, Any]) -> AccountDTO:
        account_id = self._required_str(raw, "id")
        label = self._optional_str(raw.get("name")) or account_id
        account_type = self._optional_str(raw.get("type")) or "bank"
        currency = self._currency(raw.get("currency") or "DKK")
        return AccountDTO(
            external_account_id=account_id,
            account_label=label,
            account_type=account_type.lower(),
            base_currency=currency,
        )

    def _map_transaction(
        self,
        *,
        account_id: str,
        account_currency: str,
        raw: dict[str, Any],
    ) -> TransactionDTO:
        amount_value = self._extract_transaction_amount(raw)
        txn_type = self._map_txn_type(raw.get("type"), amount_value)
        timestamp = self._datetime(raw.get("transactionTime") or raw.get("timestamp"))
        settled_at = self._optional_datetime(raw.get("bookingDate") or raw.get("postingTime"))
        transaction_id = self._required_str(raw, "id")
        return TransactionDTO(
            external_account_id=account_id,
            external_txn_id=transaction_id,
            txn_type=txn_type,
            trade_side=None,
            instrument_ref=None,
            executed_at_utc=timestamp,
            settled_at_utc=settled_at,
            quantity=None,
            price=None,
            gross_amount=amount_value,
            fee_amount=None,
            tax_amount=None,
            net_amount=amount_value,
            currency=self._currency(raw.get("currency") or account_currency),
            raw_category=self._optional_str(raw.get("type")) or self._optional_str(raw.get("text")),
        )

    def _extract_transaction_amount(self, raw: dict[str, Any]) -> Decimal:
        amount_field = raw.get("billingAmount")
        if isinstance(amount_field, dict):
            value = amount_field.get("value")
        else:
            value = amount_field
        if value is None:
            value = raw.get("amount")
        return self._decimal(value if value is not None else "0")

    def _map_txn_type(self, raw_type: Any, amount: Decimal) -> str:
        type_value = (self._optional_str(raw_type) or "other").lower()
        if "fee" in type_value:
            return "fee"
        if "interest" in type_value:
            return "interest"
        if "dividend" in type_value:
            return "dividend"
        if amount >= Decimal("0"):
            return "deposit"
        return "withdrawal"

    def _auth_headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._access_token}",
            "Accept": "application/json",
            "X-DeviceId": self._device_id,
            "X-Os": self._os_name,
            "X-Request-Id": str(uuid4()),
        }

    def _build_url(self, path: str) -> str:
        if path.startswith("http://") or path.startswith("https://"):
            return path
        return f"{self._base_url}{path}"

    @staticmethod
    def _extract_scopes_from_token(token: str) -> set[str]:
        segments = token.split(".")
        if len(segments) < 2:
            return set()
        payload_segment = segments[1]
        padded = payload_segment + "=" * (-len(payload_segment) % 4)
        try:
            decoded = base64.urlsafe_b64decode(padded.encode("utf-8")).decode("utf-8")
            payload = json.loads(decoded)
        except Exception:
            return set()
        raw_scope = payload.get("scope")
        if isinstance(raw_scope, str):
            return {scope for scope in raw_scope.split() if scope}
        if isinstance(raw_scope, list):
            return {str(scope) for scope in raw_scope if str(scope)}
        return set()

    @staticmethod
    def _required_str(raw: dict[str, Any], key: str) -> str:
        value = raw.get(key)
        if value is None:
            raise ValueError(f"Lunar payload missing required field `{key}`")
        text = str(value).strip()
        if not text:
            raise ValueError(f"Lunar payload contains empty required field `{key}`")
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
            raise ValueError("Missing required datetime value in Lunar payload")
        if isinstance(value, datetime):
            return LunarReadOnlyAdapter._normalize_utc(value)
        if not isinstance(value, str):
            raise ValueError(f"Cannot parse datetime value `{value}`")
        normalized = value.strip().replace("Z", "+00:00")
        parsed = datetime.fromisoformat(normalized)
        return LunarReadOnlyAdapter._normalize_utc(parsed)

    @staticmethod
    def _optional_datetime(value: Any) -> datetime | None:
        if value is None:
            return None
        return LunarReadOnlyAdapter._datetime(value)

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
