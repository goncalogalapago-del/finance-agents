from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Protocol

from app.adapters.contracts import (
    AccountDTO,
    BalanceDTO,
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


class SaxoReadOnlyAdapter(ReadOnlyFinanceAdapter):
    provider_code = "SAXO"
    _FORBIDDEN_SCOPE_TOKENS = ("trade", "write", "order")

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
            raise ValueError("SAXO_ACCESS_TOKEN is required to use the saxo adapter")

        payload = self._get_json("/openapi/port/v1/permissions")
        permissions = self._extract_permissions(payload)
        if not permissions:
            raise ValueError("Saxo permissions response did not include any permissions")

        for permission in permissions:
            lowered = permission.lower()
            if any(token in lowered for token in self._FORBIDDEN_SCOPE_TOKENS):
                raise ValueError(
                    "Saxo credentials are not read-only; "
                    f"forbidden permission detected: {permission}"
                )

    def list_accounts(self) -> Iterable[AccountDTO]:
        for raw in self._iter_items("/openapi/port/v1/accounts/me"):
            yield self._map_account(raw)

    def fetch_balances(self, since_utc: datetime) -> Iterable[BalanceDTO]:
        params = {"from_utc": self._to_utc_isoformat(since_utc)}
        for raw in self._iter_items("/openapi/port/v1/balances/me", params=params):
            yield self._map_balance(raw)

    def fetch_positions(self, since_utc: datetime) -> Iterable[PositionDTO]:
        params = {"from_utc": self._to_utc_isoformat(since_utc)}
        for raw in self._iter_items("/openapi/port/v1/positions/me", params=params):
            yield self._map_position(raw)

    def fetch_transactions(self, since_utc: datetime) -> Iterable[TransactionDTO]:
        params = {"from_utc": self._to_utc_isoformat(since_utc)}
        for raw in self._iter_items("/openapi/port/v1/transactions/me", params=params):
            yield self._map_transaction(raw)

    def _iter_items(
        self,
        path: str,
        *,
        params: dict[str, str] | None = None,
    ) -> Iterable[dict[str, Any]]:
        current_url = self._build_url(path)
        current_params: dict[str, str] | None = params
        while current_url:
            response = self._client.request(
                "GET",
                current_url,
                headers=self._auth_headers(),
                params=current_params,
            )
            response.raise_for_status()
            payload = response.json()
            data = payload.get("Data")
            if not isinstance(data, list):
                raise ValueError(f"Saxo response at `{path}` does not include a list `Data` field")
            for row in data:
                if not isinstance(row, dict):
                    raise ValueError(f"Saxo response at `{path}` contains a non-object row")
                yield row
            raw_next = payload.get("__next")
            current_url = self._resolve_next_url(raw_next)
            current_params = None

    def _get_json(self, path: str) -> dict[str, Any]:
        response = self._client.request(
            "GET",
            self._build_url(path),
            headers=self._auth_headers(),
            params=None,
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError(f"Saxo response at `{path}` is not a JSON object")
        return payload

    def _extract_permissions(self, payload: dict[str, Any]) -> list[str]:
        raw = payload.get("Permissions")
        if raw is None:
            raw = payload.get("permissions")
        if not isinstance(raw, list):
            return []
        permissions: list[str] = []
        for item in raw:
            if isinstance(item, str):
                permissions.append(item)
            elif isinstance(item, dict):
                value = item.get("Permission") or item.get("permission")
                if isinstance(value, str):
                    permissions.append(value)
        return permissions

    def _map_account(self, raw: dict[str, Any]) -> AccountDTO:
        external_account_id = self._required_str(raw, "AccountKey")
        account_label = self._optional_str(raw.get("AccountName")) or external_account_id
        account_type = self._optional_str(raw.get("AccountType")) or "brokerage"
        currency = self._currency(raw.get("Currency") or raw.get("ClientCurrency") or "USD")
        return AccountDTO(
            external_account_id=external_account_id,
            account_label=account_label,
            account_type=account_type.lower(),
            base_currency=currency,
        )

    def _map_balance(self, raw: dict[str, Any]) -> BalanceDTO:
        return BalanceDTO(
            external_account_id=self._required_str(raw, "AccountKey"),
            as_of_utc=self._datetime(raw.get("LastUpdated") or raw.get("AsOfUtc")),
            currency=self._currency(raw.get("Currency") or raw.get("AccountCurrency") or "USD"),
            balance_amount=self._decimal(raw.get("TotalValue") or raw.get("Balance") or "0"),
            available_amount=self._optional_decimal(
                raw.get("CashAvailable") or raw.get("Available")
            ),
        )

    def _map_position(self, raw: dict[str, Any]) -> PositionDTO:
        instrument_ref = self._optional_str(raw.get("Isin")) or self._optional_str(
            raw.get("Symbol")
        )
        if not instrument_ref:
            instrument_ref = self._required_str(raw, "Uic")
        return PositionDTO(
            external_account_id=self._required_str(raw, "AccountKey"),
            instrument_ref=instrument_ref,
            as_of_utc=self._datetime(raw.get("LastUpdated") or raw.get("AsOfUtc")),
            quantity=self._decimal(raw.get("Quantity") or raw.get("Amount") or "0"),
            avg_cost=self._optional_decimal(raw.get("AverageOpenPrice")),
            market_price=self._optional_decimal(raw.get("Price")),
            market_value=self._optional_decimal(raw.get("MarketValue")),
        )

    def _map_transaction(self, raw: dict[str, Any]) -> TransactionDTO:
        txn_type = self._map_txn_type(raw.get("Type") or raw.get("TransactionType"))
        trade_side = self._map_trade_side(raw.get("BuySell") or raw.get("Side"))
        instrument_ref = self._optional_str(raw.get("Isin")) or self._optional_str(
            raw.get("Symbol")
        )
        if not instrument_ref:
            instrument_ref = self._optional_str(raw.get("Uic"))
        gross_amount = self._optional_decimal(raw.get("GrossAmount") or raw.get("Amount"))
        fee_amount = self._optional_decimal(raw.get("Commission") or raw.get("Fee"))
        tax_amount = self._optional_decimal(raw.get("Taxes") or raw.get("Tax"))
        net_amount = self._optional_decimal(raw.get("NetAmount"))
        if net_amount is None:
            net_amount = gross_amount or Decimal("0")
            if fee_amount is not None:
                net_amount -= fee_amount
            if tax_amount is not None:
                net_amount -= tax_amount

        return TransactionDTO(
            external_account_id=self._required_str(raw, "AccountKey"),
            external_txn_id=self._required_str(raw, "TransactionId"),
            txn_type=txn_type,
            trade_side=trade_side,
            instrument_ref=instrument_ref,
            executed_at_utc=self._datetime(raw.get("TradeDate") or raw.get("ExecutedAtUtc")),
            settled_at_utc=self._optional_datetime(
                raw.get("SettlementDate") or raw.get("SettledAtUtc")
            ),
            quantity=self._optional_decimal(raw.get("Quantity")),
            price=self._optional_decimal(raw.get("Price")),
            gross_amount=gross_amount,
            fee_amount=fee_amount,
            tax_amount=tax_amount,
            net_amount=net_amount,
            currency=self._currency(raw.get("Currency") or raw.get("AccountCurrency") or "USD"),
            raw_category=self._optional_str(raw.get("Description"))
            or self._optional_str(raw.get("Type")),
        )

    def _map_txn_type(self, raw_type: Any) -> str:
        value = self._optional_str(raw_type)
        lowered = (value or "other").lower()
        if lowered in {"buy", "sell", "trade", "orderfill"}:
            return "trade"
        if "dividend" in lowered:
            return "dividend"
        if "interest" in lowered:
            return "interest"
        if "deposit" in lowered:
            return "deposit"
        if "withdraw" in lowered:
            return "withdrawal"
        if "fee" in lowered or "commission" in lowered:
            return "fee"
        return "other"

    def _map_trade_side(self, raw_side: Any) -> str | None:
        value = self._optional_str(raw_side)
        if value is None:
            return None
        lowered = value.lower()
        if lowered in {"buy", "b"}:
            return "buy"
        if lowered in {"sell", "s"}:
            return "sell"
        return None

    def _build_url(self, path: str) -> str:
        if path.startswith("http://") or path.startswith("https://"):
            return path
        return f"{self._base_url}{path}"

    def _resolve_next_url(self, raw_next: Any) -> str:
        next_token = self._optional_str(raw_next)
        if not next_token:
            return ""
        return self._build_url(next_token)

    def _auth_headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._access_token}",
            "Accept": "application/json",
        }

    @staticmethod
    def _required_str(raw: dict[str, Any], key: str) -> str:
        value = raw.get(key)
        if value is None:
            raise ValueError(f"Saxo payload missing required field `{key}`")
        text = str(value).strip()
        if not text:
            raise ValueError(f"Saxo payload contains empty required field `{key}`")
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
        except Exception as exc:  # pragma: no cover - explicit parse guard
            raise ValueError(f"Cannot parse decimal value `{value}`") from exc

    @classmethod
    def _optional_decimal(cls, value: Any) -> Decimal | None:
        if value is None:
            return None
        return cls._decimal(value)

    @staticmethod
    def _datetime(value: Any) -> datetime:
        if value is None:
            raise ValueError("Missing required datetime value in Saxo payload")
        if isinstance(value, datetime):
            if value.tzinfo is None:
                return value.replace(tzinfo=timezone.utc)
            return value.astimezone(timezone.utc)
        if not isinstance(value, str):
            raise ValueError(f"Cannot parse datetime value `{value}`")
        normalized = value.strip().replace("Z", "+00:00")
        parsed = datetime.fromisoformat(normalized)
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)

    @classmethod
    def _optional_datetime(cls, value: Any) -> datetime | None:
        if value is None:
            return None
        return cls._datetime(value)

    @staticmethod
    def _currency(value: Any) -> str:
        currency = str(value).strip().upper()
        if len(currency) != 3:
            raise ValueError(f"Invalid currency code `{value}`")
        return currency

    @staticmethod
    def _to_utc_isoformat(value: datetime) -> str:
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        else:
            value = value.astimezone(timezone.utc)
        return value.isoformat()
