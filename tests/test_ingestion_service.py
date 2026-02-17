from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from app.adapters.contracts import (
    AccountDTO,
    AdapterCapabilities,
    BalanceDTO,
    InstitutionKind,
    PositionDTO,
    TransactionDTO,
)
from app.models.account import Account
from app.models.audit_event import AuditEvent
from app.models.balance import Balance
from app.models.ingestion_run import IngestionRun, IngestionRunStatus
from app.models.instrument import Instrument
from app.models.position import Position
from app.models.transaction import Transaction
from app.services.ingestion import IngestionService, UnknownSourceError


class _SuccessfulAdapter:
    provider_code = "TEST_OK"
    institution_kind = InstitutionKind.BROKER
    capabilities = AdapterCapabilities()
    snapshot_utc = datetime(2026, 1, 15, 12, 0, tzinfo=timezone.utc)
    settled_utc = datetime(2026, 1, 13, 12, 0, tzinfo=timezone.utc)

    def validate_read_only_scope(self) -> None:
        return None

    def list_accounts(self) -> list[AccountDTO]:
        return [
            AccountDTO(
                external_account_id="acct-1",
                account_label="Main",
                account_type="brokerage",
                base_currency="USD",
            )
        ]

    def fetch_balances(self, since_utc: datetime) -> list[BalanceDTO]:
        return [
            BalanceDTO(
                external_account_id="acct-1",
                as_of_utc=self.snapshot_utc,
                currency="USD",
                balance_amount=Decimal("100.00"),
                available_amount=Decimal("80.00"),
            ),
            BalanceDTO(
                external_account_id="acct-1",
                as_of_utc=self.snapshot_utc,
                currency="EUR",
                balance_amount=Decimal("25.00"),
                available_amount=Decimal("25.00"),
            ),
        ]

    def fetch_positions(self, since_utc: datetime) -> list[PositionDTO]:
        return [
            PositionDTO(
                external_account_id="acct-1",
                instrument_ref="US0378331005",
                as_of_utc=self.snapshot_utc,
                quantity=Decimal("10"),
                avg_cost=Decimal("150.00"),
                market_price=Decimal("180.00"),
                market_value=Decimal("1800.00"),
            )
        ]

    def fetch_transactions(self, since_utc: datetime) -> list[TransactionDTO]:
        return [
            TransactionDTO(
                external_account_id="acct-1",
                external_txn_id="txn-1",
                txn_type="dividend",
                trade_side=None,
                instrument_ref="US0378331005",
                executed_at_utc=self.settled_utc,
                settled_at_utc=self.settled_utc,
                quantity=None,
                price=None,
                gross_amount=Decimal("12.00"),
                fee_amount=Decimal("0.00"),
                tax_amount=Decimal("1.80"),
                net_amount=Decimal("10.20"),
                currency="USD",
                raw_category="cash_dividend",
            ),
            TransactionDTO(
                external_account_id="acct-1",
                external_txn_id="txn-2",
                txn_type="interest",
                trade_side=None,
                instrument_ref=None,
                executed_at_utc=self.settled_utc,
                settled_at_utc=self.settled_utc,
                quantity=None,
                price=None,
                gross_amount=Decimal("2.00"),
                fee_amount=Decimal("0.00"),
                tax_amount=Decimal("0.00"),
                net_amount=Decimal("2.00"),
                currency="USD",
                raw_category="interest",
            ),
            TransactionDTO(
                external_account_id="acct-1",
                external_txn_id="txn-3",
                txn_type="fee",
                trade_side=None,
                instrument_ref=None,
                executed_at_utc=self.settled_utc,
                settled_at_utc=self.settled_utc,
                quantity=None,
                price=None,
                gross_amount=Decimal("1.00"),
                fee_amount=Decimal("1.00"),
                tax_amount=Decimal("0.00"),
                net_amount=Decimal("-1.00"),
                currency="USD",
                raw_category="custody_fee",
            ),
        ]


class _FailingAdapter(_SuccessfulAdapter):
    provider_code = "TEST_FAIL"

    def fetch_positions(self, since_utc: datetime) -> list[Any]:
        raise RuntimeError("provider timeout")


def test_run_raises_unknown_source_when_adapter_is_missing(
    test_session_factory: sessionmaker,
) -> None:
    with test_session_factory() as session:
        service = IngestionService(db=session, adapters={})

        with pytest.raises(UnknownSourceError, match="Unknown ingestion source: missing"):
            service.run(source="missing")

        assert session.scalars(select(IngestionRun)).all() == []
        assert session.scalars(select(AuditEvent)).all() == []


def test_run_success_persists_successful_ingestion(test_session_factory: sessionmaker) -> None:
    since_utc = datetime(2026, 1, 1, tzinfo=timezone.utc)

    with test_session_factory() as session:
        service = IngestionService(db=session, adapters={"fixture": _SuccessfulAdapter()})

        result = service.run(source="fixture", since_utc=since_utc)
        session.commit()

        run = session.get(IngestionRun, result["run_id"])
        event_types = session.scalars(
            select(AuditEvent.event_type).order_by(AuditEvent.id.asc())
        ).all()
        account_count = session.scalar(select(func.count()).select_from(Account))
        balance_count = session.scalar(select(func.count()).select_from(Balance))
        position_count = session.scalar(select(func.count()).select_from(Position))
        txn_count = session.scalar(select(func.count()).select_from(Transaction))
        instrument_count = session.scalar(select(func.count()).select_from(Instrument))

    assert run is not None
    assert result["status"] == "SUCCESS"
    assert result["pulled_counts"] == {"balances": 2, "positions": 1, "transactions": 3}
    assert run.status == IngestionRunStatus.SUCCESS
    assert run.period_start_utc.replace(tzinfo=timezone.utc) == since_utc
    assert event_types == ["INGESTION_PULL_STARTED", "INGESTION_PULL_COMPLETED"]
    assert account_count == 1
    assert balance_count == 2
    assert position_count == 1
    assert txn_count == 3
    assert instrument_count == 1


def test_run_failure_persists_failed_ingestion_and_audit(
    test_session_factory: sessionmaker,
) -> None:
    with test_session_factory() as session:
        service = IngestionService(db=session, adapters={"fixture": _FailingAdapter()})

        with pytest.raises(RuntimeError, match="provider timeout"):
            service.run(source="fixture")
        session.commit()

        run = session.scalars(select(IngestionRun)).one()
        events = session.scalars(select(AuditEvent).order_by(AuditEvent.id.asc())).all()

    assert run.status == IngestionRunStatus.FAILED
    assert run.stats_payload["error"] == "provider timeout"
    assert [event.event_type for event in events] == [
        "INGESTION_PULL_STARTED",
        "INGESTION_PULL_FAILED",
    ]
    assert events[1].prev_hash == events[0].event_hash


def test_run_is_idempotent_for_duplicate_snapshots(test_session_factory: sessionmaker) -> None:
    since_utc = datetime(2026, 1, 1, tzinfo=timezone.utc)
    adapter = _SuccessfulAdapter()

    with test_session_factory() as session:
        service = IngestionService(db=session, adapters={"fixture": adapter})

        service.run(source="fixture", since_utc=since_utc)
        service.run(source="fixture", since_utc=since_utc)
        session.commit()

        account_count = session.scalar(select(func.count()).select_from(Account))
        balance_count = session.scalar(select(func.count()).select_from(Balance))
        position_count = session.scalar(select(func.count()).select_from(Position))
        txn_count = session.scalar(select(func.count()).select_from(Transaction))
        instrument_count = session.scalar(select(func.count()).select_from(Instrument))

    assert account_count == 1
    assert balance_count == 2
    assert position_count == 1
    assert txn_count == 3
    assert instrument_count == 1


def test_run_all_marks_degraded_when_one_source_fails(test_session_factory: sessionmaker) -> None:
    since_utc = datetime(2026, 1, 1, tzinfo=timezone.utc)

    with test_session_factory() as session:
        service = IngestionService(
            db=session,
            adapters={
                "ok": _SuccessfulAdapter(),
                "bad": _FailingAdapter(),
            },
        )

        result = service.run(source="all", since_utc=since_utc)
        session.commit()

        run = session.get(IngestionRun, result["run_id"])
        event_types = session.scalars(
            select(AuditEvent.event_type).order_by(AuditEvent.id.asc())
        ).all()

    assert run is not None
    assert result["status"] == "DEGRADED"
    assert result["pulled_counts"] == {"balances": 2, "positions": 1, "transactions": 3}
    assert run.status == IngestionRunStatus.DEGRADED
    assert run.stats_payload["failed_sources"] == {"bad": "provider timeout"}
    assert run.stats_payload["sources"]["ok"]["status"] == "SUCCESS"
    assert run.stats_payload["sources"]["bad"]["status"] == "FAILED"
    assert event_types == ["INGESTION_PULL_STARTED", "INGESTION_PULL_COMPLETED"]


def test_run_all_raises_when_all_sources_fail(test_session_factory: sessionmaker) -> None:
    with test_session_factory() as session:
        service = IngestionService(
            db=session,
            adapters={"bad-1": _FailingAdapter(), "bad-2": _FailingAdapter()},
        )

        with pytest.raises(RuntimeError, match="All ingestion sources failed"):
            service.run(source="all")
        session.commit()

        run = session.scalars(select(IngestionRun)).one()
        event_types = session.scalars(
            select(AuditEvent.event_type).order_by(AuditEvent.id.asc())
        ).all()

    assert run.status == IngestionRunStatus.FAILED
    assert run.stats_payload["failed_sources"] == {
        "bad-1": "provider timeout",
        "bad-2": "provider timeout",
    }
    assert event_types == ["INGESTION_PULL_STARTED", "INGESTION_PULL_FAILED"]


def test_run_all_raises_when_no_sources_are_configured(test_session_factory: sessionmaker) -> None:
    with test_session_factory() as session:
        service = IngestionService(db=session, adapters={})

        with pytest.raises(UnknownSourceError, match="No ingestion sources configured"):
            service.run(source="all")


def test_upsert_instruments_uses_symbol_lookup_for_non_isin_refs(
    test_session_factory: sessionmaker,
) -> None:
    with test_session_factory() as session:
        service = IngestionService(db=session, adapters={})
        ids = service._upsert_instruments(
            positions=[
                PositionDTO(
                    external_account_id="acct-1",
                    instrument_ref="AAPL.US",
                    as_of_utc=_SuccessfulAdapter.snapshot_utc,
                    quantity=Decimal("1"),
                    avg_cost=None,
                    market_price=None,
                    market_value=None,
                )
            ],
            transactions=[],
            currency_by_ref={"AAPL.US": "USD"},
        )
        session.commit()

        instrument = session.get(Instrument, ids["AAPL.US"])

    assert instrument is not None
    assert instrument.isin is None
    assert instrument.symbol == "AAPL.US"


def test_upsert_balances_requires_account_mapping(test_session_factory: sessionmaker) -> None:
    with test_session_factory() as session:
        service = IngestionService(db=session, adapters={})

        with pytest.raises(ValueError, match="No account mapping for balance"):
            service._upsert_balances(
                account_ids={},
                balances=[
                    BalanceDTO(
                        external_account_id="missing",
                        as_of_utc=_SuccessfulAdapter.snapshot_utc,
                        currency="USD",
                        balance_amount=Decimal("10"),
                        available_amount=Decimal("10"),
                    )
                ],
            )


def test_upsert_positions_requires_account_and_instrument_mappings(
    test_session_factory: sessionmaker,
) -> None:
    position = PositionDTO(
        external_account_id="missing",
        instrument_ref="US0378331005",
        as_of_utc=_SuccessfulAdapter.snapshot_utc,
        quantity=Decimal("1"),
        avg_cost=None,
        market_price=None,
        market_value=None,
    )

    with test_session_factory() as session:
        service = IngestionService(db=session, adapters={})

        with pytest.raises(ValueError, match="No account mapping for position"):
            service._upsert_positions(
                account_ids={},
                instrument_ids={"US0378331005": "inst-1"},
                positions=[position],
            )

        with pytest.raises(ValueError, match="No instrument mapping for position"):
            service._upsert_positions(
                account_ids={"missing": "acct-1"},
                instrument_ids={},
                positions=[position],
            )


def test_upsert_transactions_requires_account_mapping(test_session_factory: sessionmaker) -> None:
    txn = TransactionDTO(
        external_account_id="missing",
        external_txn_id="txn-missing",
        txn_type="dividend",
        trade_side=None,
        instrument_ref=None,
        executed_at_utc=_SuccessfulAdapter.settled_utc,
        settled_at_utc=_SuccessfulAdapter.settled_utc,
        quantity=None,
        price=None,
        gross_amount=Decimal("1.00"),
        fee_amount=Decimal("0.00"),
        tax_amount=Decimal("0.00"),
        net_amount=Decimal("1.00"),
        currency="USD",
        raw_category=None,
    )

    with test_session_factory() as session:
        service = IngestionService(db=session, adapters={})

        with pytest.raises(ValueError, match="No account mapping for transaction"):
            service._upsert_transactions(
                account_ids={},
                instrument_ids={},
                transactions=[txn],
            )


def test_ingestion_validation_helpers_raise_actionable_errors() -> None:
    with pytest.raises(ValueError, match="Invalid currency code"):
        IngestionService._normalize_currency("US")

    with pytest.raises(ValueError, match="Unsupported txn_type"):
        IngestionService._parse_transaction_type("unsupported", "txn-1")

    with pytest.raises(ValueError, match="Unsupported trade_side"):
        IngestionService._parse_trade_side("hold", "txn-1")
