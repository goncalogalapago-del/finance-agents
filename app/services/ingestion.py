from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.adapters.contracts import (
    AccountDTO,
    BalanceDTO,
    InstitutionKind,
    PositionDTO,
    ReadOnlyFinanceAdapter,
    TransactionDTO,
)
from app.models.account import Account
from app.models.balance import Balance
from app.models.ingestion_run import IngestionRun, IngestionRunStatus
from app.models.institution import Institution, InstitutionType
from app.models.instrument import Instrument
from app.models.position import Position
from app.models.transaction import TradeSide, Transaction, TransactionType
from app.services.audit import AuditService


class UnknownSourceError(Exception):
    pass


class IngestionService:
    def __init__(self, db: Session, adapters: dict[str, ReadOnlyFinanceAdapter]) -> None:
        self.db = db
        self.adapters = adapters
        self.audit = AuditService(db)

    def run(self, *, source: str, since_utc: Optional[datetime] = None) -> dict[str, Any]:
        if source == "all":
            return self._run_all_sources(since_utc=since_utc)

        adapter = self.adapters.get(source)
        if adapter is None:
            raise UnknownSourceError(f"Unknown ingestion source: {source}")

        run_id = str(uuid4())
        run_started_utc = datetime.now(timezone.utc)
        period_start_utc = since_utc or (run_started_utc - timedelta(days=30))

        self.audit.append_event(
            event_type="INGESTION_PULL_STARTED",
            entity_type="ingestion_run",
            entity_id=run_id,
            run_id=run_id,
            payload={"source": source, "period_start_utc": period_start_utc.isoformat()},
        )

        try:
            pulled_counts = self._pull_and_persist(
                adapter=adapter,
                period_start_utc=period_start_utc,
            )

            period_end_utc = datetime.now(timezone.utc)

            self.db.add(
                IngestionRun(
                    id=run_id,
                    source=source,
                    status=IngestionRunStatus.SUCCESS,
                    started_at_utc=run_started_utc,
                    finished_at_utc=period_end_utc,
                    period_start_utc=period_start_utc,
                    period_end_utc=period_end_utc,
                    stats_payload=pulled_counts,
                )
            )

            self.audit.append_event(
                event_type="INGESTION_PULL_COMPLETED",
                entity_type="ingestion_run",
                entity_id=run_id,
                run_id=run_id,
                payload={"source": source, "pulled_counts": pulled_counts},
            )

            return {
                "run_id": run_id,
                "source": source,
                "status": IngestionRunStatus.SUCCESS.value,
                "pulled_counts": pulled_counts,
            }
        except Exception as exc:
            self.db.add(
                IngestionRun(
                    id=run_id,
                    source=source,
                    status=IngestionRunStatus.FAILED,
                    started_at_utc=run_started_utc,
                    finished_at_utc=datetime.now(timezone.utc),
                    period_start_utc=period_start_utc,
                    period_end_utc=datetime.now(timezone.utc),
                    stats_payload={"error": str(exc)},
                )
            )
            self.audit.append_event(
                event_type="INGESTION_PULL_FAILED",
                entity_type="ingestion_run",
                entity_id=run_id,
                run_id=run_id,
                payload={"source": source, "error": str(exc)},
            )
            raise

    def _run_all_sources(self, *, since_utc: Optional[datetime]) -> dict[str, Any]:
        if not self.adapters:
            raise UnknownSourceError("No ingestion sources configured")

        run_id = str(uuid4())
        run_started_utc = datetime.now(timezone.utc)
        period_start_utc = since_utc or (run_started_utc - timedelta(days=30))
        source_names = sorted(self.adapters.keys())
        self.audit.append_event(
            event_type="INGESTION_PULL_STARTED",
            entity_type="ingestion_run",
            entity_id=run_id,
            run_id=run_id,
            payload={
                "source": "all",
                "sources": source_names,
                "period_start_utc": period_start_utc.isoformat(),
            },
        )

        pulled_totals = {
            "balances": 0,
            "positions": 0,
            "transactions": 0,
        }
        failed_sources: dict[str, str] = {}
        source_results: dict[str, dict[str, Any]] = {}
        for source_name in source_names:
            adapter = self.adapters[source_name]
            try:
                pulled_counts = self._pull_and_persist(
                    adapter=adapter,
                    period_start_utc=period_start_utc,
                )
                for key, value in pulled_counts.items():
                    pulled_totals[key] += value
                source_results[source_name] = {
                    "status": IngestionRunStatus.SUCCESS.value,
                    "pulled_counts": pulled_counts,
                }
            except Exception as exc:
                failed_sources[source_name] = str(exc)
                source_results[source_name] = {
                    "status": IngestionRunStatus.FAILED.value,
                    "error": str(exc),
                }

        period_end_utc = datetime.now(timezone.utc)
        if len(failed_sources) == len(source_names):
            status = IngestionRunStatus.FAILED
        elif failed_sources:
            status = IngestionRunStatus.DEGRADED
        else:
            status = IngestionRunStatus.SUCCESS

        stats_payload = {
            "sources": source_results,
            "pulled_totals": pulled_totals,
            "failed_sources": failed_sources,
        }
        self.db.add(
            IngestionRun(
                id=run_id,
                source="all",
                status=status,
                started_at_utc=run_started_utc,
                finished_at_utc=period_end_utc,
                period_start_utc=period_start_utc,
                period_end_utc=period_end_utc,
                stats_payload=stats_payload,
            )
        )

        if status == IngestionRunStatus.FAILED:
            self.audit.append_event(
                event_type="INGESTION_PULL_FAILED",
                entity_type="ingestion_run",
                entity_id=run_id,
                run_id=run_id,
                payload={"source": "all", "failed_sources": failed_sources},
            )
            failed_names = ", ".join(sorted(failed_sources.keys()))
            raise RuntimeError(f"All ingestion sources failed: {failed_names}")

        self.audit.append_event(
            event_type="INGESTION_PULL_COMPLETED",
            entity_type="ingestion_run",
            entity_id=run_id,
            run_id=run_id,
            payload={
                "source": "all",
                "status": status.value,
                "pulled_totals": pulled_totals,
                "failed_sources": failed_sources,
            },
        )
        return {
            "run_id": run_id,
            "source": "all",
            "status": status.value,
            "pulled_counts": pulled_totals,
        }

    def _pull_and_persist(
        self,
        *,
        adapter: ReadOnlyFinanceAdapter,
        period_start_utc: datetime,
    ) -> dict[str, int]:
        adapter.validate_read_only_scope()
        accounts = list(adapter.list_accounts())
        balances = list(adapter.fetch_balances(period_start_utc))
        positions = list(adapter.fetch_positions(period_start_utc))
        transactions = list(adapter.fetch_transactions(period_start_utc))
        self._persist_canonical(
            adapter=adapter,
            accounts=accounts,
            balances=balances,
            positions=positions,
            transactions=transactions,
        )
        return {
            "balances": len(balances),
            "positions": len(positions),
            "transactions": len(transactions),
        }

    def _persist_canonical(
        self,
        *,
        adapter: ReadOnlyFinanceAdapter,
        accounts: list[AccountDTO],
        balances: list[BalanceDTO],
        positions: list[PositionDTO],
        transactions: list[TransactionDTO],
    ) -> None:
        institution = self._upsert_institution(
            provider_code=adapter.provider_code,
            institution_kind=adapter.institution_kind,
        )
        account_ids = self._upsert_accounts(institution_id=institution.id, accounts=accounts)
        instrument_currencies = self._build_instrument_currency_map(
            accounts=accounts,
            positions=positions,
            transactions=transactions,
        )
        instrument_ids = self._upsert_instruments(
            positions=positions,
            transactions=transactions,
            currency_by_ref=instrument_currencies,
        )
        self._upsert_balances(account_ids=account_ids, balances=balances)
        self._upsert_positions(
            account_ids=account_ids,
            instrument_ids=instrument_ids,
            positions=positions,
        )
        self._upsert_transactions(
            account_ids=account_ids,
            instrument_ids=instrument_ids,
            transactions=transactions,
        )

    def _upsert_institution(
        self, *, provider_code: str, institution_kind: InstitutionKind
    ) -> Institution:
        code = provider_code.strip().upper()
        institution = self.db.scalar(select(Institution).where(Institution.provider_code == code))
        institution_type = (
            InstitutionType.BROKER
            if institution_kind == InstitutionKind.BROKER
            else InstitutionType.BANK
        )
        if institution is None:
            institution = Institution(
                name=code,
                type=institution_type,
                provider_code=code,
            )
            self.db.add(institution)
            self.db.flush()
        else:
            institution.type = institution_type
        return institution

    def _upsert_accounts(
        self,
        *,
        institution_id: str,
        accounts: list[AccountDTO],
    ) -> dict[str, str]:
        account_ids: dict[str, str] = {}
        for account in accounts:
            currency = self._normalize_currency(account.base_currency)
            existing = self.db.scalar(
                select(Account).where(
                    Account.institution_id == institution_id,
                    Account.external_account_id == account.external_account_id,
                )
            )
            if existing is None:
                existing = Account(
                    institution_id=institution_id,
                    external_account_id=account.external_account_id,
                    account_label=account.account_label,
                    account_type=account.account_type,
                    base_currency=currency,
                    is_active=True,
                )
                self.db.add(existing)
                self.db.flush()
            else:
                existing.account_label = account.account_label
                existing.account_type = account.account_type
                existing.base_currency = currency
                existing.is_active = True
            account_ids[account.external_account_id] = existing.id
        return account_ids

    def _upsert_instruments(
        self,
        *,
        positions: list[PositionDTO],
        transactions: list[TransactionDTO],
        currency_by_ref: dict[str, str],
    ) -> dict[str, str]:
        refs = {
            position.instrument_ref for position in positions
        } | {txn.instrument_ref for txn in transactions if txn.instrument_ref is not None}
        instrument_ids: dict[str, str] = {}
        for instrument_ref in refs:
            isin = instrument_ref if self._looks_like_isin(instrument_ref) else None
            symbol = instrument_ref if isin is None else None
            stmt = select(Instrument)
            if isin is not None:
                stmt = stmt.where(Instrument.isin == isin)
            else:
                stmt = stmt.where(Instrument.symbol == symbol)
            existing = self.db.scalar(stmt)
            if existing is None:
                existing = Instrument(
                    isin=isin,
                    symbol=symbol,
                    name=instrument_ref,
                    asset_class="unknown",
                    currency=currency_by_ref.get(instrument_ref, "USD"),
                    is_allowlisted=False,
                )
                self.db.add(existing)
                self.db.flush()
            instrument_ids[instrument_ref] = existing.id
        return instrument_ids

    def _upsert_balances(
        self,
        *,
        account_ids: dict[str, str],
        balances: list[BalanceDTO],
    ) -> None:
        for balance in balances:
            account_id = account_ids.get(balance.external_account_id)
            if account_id is None:
                msg = (
                    "No account mapping for balance "
                    f"external_account_id={balance.external_account_id}"
                )
                raise ValueError(msg)
            currency = self._normalize_currency(balance.currency)
            existing = self.db.scalar(
                select(Balance).where(
                    Balance.account_id == account_id,
                    Balance.as_of_utc == balance.as_of_utc,
                    Balance.currency == currency,
                )
            )
            if existing is None:
                existing = Balance(
                    account_id=account_id,
                    as_of_utc=balance.as_of_utc,
                    currency=currency,
                    balance_amount=balance.balance_amount,
                    available_amount=balance.available_amount,
                )
                self.db.add(existing)
            else:
                existing.balance_amount = balance.balance_amount
                existing.available_amount = balance.available_amount

    def _upsert_positions(
        self,
        *,
        account_ids: dict[str, str],
        instrument_ids: dict[str, str],
        positions: list[PositionDTO],
    ) -> None:
        for position in positions:
            account_id = account_ids.get(position.external_account_id)
            if account_id is None:
                msg = (
                    "No account mapping for position "
                    f"external_account_id={position.external_account_id}"
                )
                raise ValueError(msg)
            instrument_id = instrument_ids.get(position.instrument_ref)
            if instrument_id is None:
                raise ValueError(
                    "No instrument mapping for position "
                    f"ref={position.instrument_ref}"
                )
            existing = self.db.scalar(
                select(Position).where(
                    Position.account_id == account_id,
                    Position.instrument_id == instrument_id,
                    Position.as_of_utc == position.as_of_utc,
                )
            )
            if existing is None:
                existing = Position(
                    account_id=account_id,
                    instrument_id=instrument_id,
                    as_of_utc=position.as_of_utc,
                    quantity=position.quantity,
                    avg_cost=position.avg_cost,
                    market_price=position.market_price,
                    market_value=position.market_value,
                )
                self.db.add(existing)
            else:
                existing.quantity = position.quantity
                existing.avg_cost = position.avg_cost
                existing.market_price = position.market_price
                existing.market_value = position.market_value

    def _upsert_transactions(
        self,
        *,
        account_ids: dict[str, str],
        instrument_ids: dict[str, str],
        transactions: list[TransactionDTO],
    ) -> None:
        for txn in transactions:
            account_id = account_ids.get(txn.external_account_id)
            if account_id is None:
                msg = (
                    "No account mapping for transaction "
                    f"external_account_id={txn.external_account_id}"
                )
                raise ValueError(msg)
            instrument_id = (
                instrument_ids.get(txn.instrument_ref) if txn.instrument_ref is not None else None
            )
            existing = self.db.scalar(
                select(Transaction).where(
                    Transaction.account_id == account_id,
                    Transaction.external_txn_id == txn.external_txn_id,
                )
            )
            txn_type = self._parse_transaction_type(txn.txn_type, txn.external_txn_id)
            trade_side = self._parse_trade_side(txn.trade_side, txn.external_txn_id)
            currency = self._normalize_currency(txn.currency)
            if existing is None:
                existing = Transaction(
                    account_id=account_id,
                    instrument_id=instrument_id,
                    external_txn_id=txn.external_txn_id,
                    txn_type=txn_type,
                    trade_side=trade_side,
                    executed_at_utc=txn.executed_at_utc,
                    settled_at_utc=txn.settled_at_utc,
                    quantity=txn.quantity,
                    price=txn.price,
                    gross_amount=txn.gross_amount,
                    fee_amount=txn.fee_amount,
                    tax_amount=txn.tax_amount,
                    net_amount=txn.net_amount,
                    currency=currency,
                    raw_category=txn.raw_category,
                )
                self.db.add(existing)
            else:
                existing.instrument_id = instrument_id
                existing.txn_type = txn_type
                existing.trade_side = trade_side
                existing.executed_at_utc = txn.executed_at_utc
                existing.settled_at_utc = txn.settled_at_utc
                existing.quantity = txn.quantity
                existing.price = txn.price
                existing.gross_amount = txn.gross_amount
                existing.fee_amount = txn.fee_amount
                existing.tax_amount = txn.tax_amount
                existing.net_amount = txn.net_amount
                existing.currency = currency
                existing.raw_category = txn.raw_category

    @staticmethod
    def _normalize_currency(currency: str) -> str:
        normalized = currency.strip().upper()
        if len(normalized) != 3:
            raise ValueError(f"Invalid currency code `{currency}`")
        return normalized

    @staticmethod
    def _parse_transaction_type(value: str, external_txn_id: str) -> TransactionType:
        try:
            return TransactionType(value)
        except ValueError as exc:
            raise ValueError(
                f"Unsupported txn_type `{value}` for transaction external_txn_id={external_txn_id}"
            ) from exc

    @staticmethod
    def _parse_trade_side(value: Optional[str], external_txn_id: str) -> Optional[TradeSide]:
        if value is None:
            return None
        try:
            return TradeSide(value)
        except ValueError as exc:
            raise ValueError(
                "Unsupported trade_side "
                f"`{value}` for transaction external_txn_id={external_txn_id}"
            ) from exc

    @staticmethod
    def _looks_like_isin(value: str) -> bool:
        cleaned = value.strip().upper()
        return len(cleaned) == 12 and cleaned.isalnum()

    def _build_instrument_currency_map(
        self,
        *,
        accounts: list[AccountDTO],
        positions: list[PositionDTO],
        transactions: list[TransactionDTO],
    ) -> dict[str, str]:
        account_currency = {
            account.external_account_id: self._normalize_currency(account.base_currency)
            for account in accounts
        }
        currency_by_ref: dict[str, str] = {}
        for txn in transactions:
            if txn.instrument_ref is not None:
                normalized_currency = self._normalize_currency(txn.currency)
                currency_by_ref.setdefault(txn.instrument_ref, normalized_currency)
        for position in positions:
            currency = account_currency.get(position.external_account_id)
            if currency is not None:
                currency_by_ref.setdefault(position.instrument_ref, currency)
        return currency_by_ref
