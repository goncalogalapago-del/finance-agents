from datetime import datetime, timezone
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.models.audit_event import AuditEvent
from app.models.ingestion_run import IngestionRun, IngestionRunStatus
from app.services.ingestion import IngestionService, UnknownSourceError


class _SuccessfulAdapter:
    provider_code = "TEST_OK"

    def validate_read_only_scope(self) -> None:
        return None

    def list_accounts(self) -> list[Any]:
        return []

    def fetch_balances(self, since_utc: datetime) -> list[Any]:
        return [object(), object()]

    def fetch_positions(self, since_utc: datetime) -> list[Any]:
        return [object()]

    def fetch_transactions(self, since_utc: datetime) -> list[Any]:
        return [object(), object(), object()]


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

    assert run is not None
    assert result["status"] == "SUCCESS"
    assert result["pulled_counts"] == {"balances": 2, "positions": 1, "transactions": 3}
    assert run.status == IngestionRunStatus.SUCCESS
    assert run.period_start_utc.replace(tzinfo=timezone.utc) == since_utc
    assert event_types == ["INGESTION_PULL_STARTED", "INGESTION_PULL_COMPLETED"]


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
