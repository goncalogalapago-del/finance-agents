from __future__ import annotations

from datetime import datetime
from typing import Any

from app.adapters.contracts import (
    AccountDTO,
    BalanceDTO,
    PositionDTO,
    ReadOnlyFinanceAdapter,
    TransactionDTO,
)


class FallbackReadOnlyAdapter(ReadOnlyFinanceAdapter):
    def __init__(
        self,
        *,
        primary: ReadOnlyFinanceAdapter,
        fallback: ReadOnlyFinanceAdapter,
    ) -> None:
        if primary.provider_code != fallback.provider_code:
            raise ValueError(
                "Fallback adapter provider_code must match primary provider_code "
                f"({primary.provider_code} != {fallback.provider_code})"
            )
        self.provider_code = primary.provider_code
        self._primary = primary
        self._fallback = fallback

    def validate_read_only_scope(self) -> None:
        self._invoke("validate_read_only_scope")

    def list_accounts(self) -> list[AccountDTO]:
        return self._invoke("list_accounts")

    def fetch_balances(self, since_utc: datetime) -> list[BalanceDTO]:
        return self._invoke("fetch_balances", since_utc)

    def fetch_positions(self, since_utc: datetime) -> list[PositionDTO]:
        return self._invoke("fetch_positions", since_utc)

    def fetch_transactions(self, since_utc: datetime) -> list[TransactionDTO]:
        return self._invoke("fetch_transactions", since_utc)

    def _invoke(self, method_name: str, *args: Any) -> Any:
        try:
            return self._call(self._primary, method_name, *args)
        except Exception:
            return self._call(self._fallback, method_name, *args)

    @staticmethod
    def _call(adapter: ReadOnlyFinanceAdapter, method_name: str, *args: Any) -> Any:
        method = getattr(adapter, method_name)
        result = method(*args)
        if result is None:
            return None
        if isinstance(result, list):
            return result
        return list(result)
