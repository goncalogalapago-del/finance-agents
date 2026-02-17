from __future__ import annotations

from datetime import datetime
from typing import Any

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from app.adapters.contracts import AdapterCapabilities, InstitutionKind
from app.api.jobs import (
    IngestionPreflightRequest,
    IngestionRunRequest,
    preflight_ingestion,
    run_ingestion_job,
)
from app.models.account import Account
from app.models.audit_event import AuditEvent
from app.models.balance import Balance
from app.models.ingestion_run import IngestionRun, IngestionRunStatus
from app.models.position import Position
from app.models.transaction import Transaction


def test_ingestion_job_with_fixture_writes_run_and_audit(
    client: TestClient, test_session_factory: sessionmaker
) -> None:
    response = client.post("/jobs/ingestion/run", json={"source": "fixture"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["source"] == "fixture"
    assert payload["status"] == "SUCCESS"
    assert payload["pulled_counts"] == {
        "balances": 1,
        "positions": 1,
        "transactions": 1,
    }

    run_id = payload["run_id"]

    with test_session_factory() as session:
        run = session.get(IngestionRun, run_id)
        assert run is not None
        assert run.status == IngestionRunStatus.SUCCESS
        assert session.scalar(select(func.count()).select_from(Account)) == 1
        assert session.scalar(select(func.count()).select_from(Balance)) == 1
        assert session.scalar(select(func.count()).select_from(Position)) == 1
        assert session.scalar(select(func.count()).select_from(Transaction)) == 1

        stmt = select(AuditEvent.event_type).order_by(AuditEvent.id.asc())
        event_types = session.scalars(stmt).all()
        assert event_types == ["INGESTION_PULL_STARTED", "INGESTION_PULL_COMPLETED"]


def test_ingestion_job_rejects_unknown_source(client: TestClient) -> None:
    response = client.post("/jobs/ingestion/run", json={"source": "unknown"})

    assert response.status_code == 400
    assert "Unknown ingestion source" in response.json()["detail"]


def test_ingestion_job_all_sources_works_with_default_registry(client: TestClient) -> None:
    response = client.post("/jobs/ingestion/run", json={"source": "all"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["source"] == "all"
    assert payload["status"] == "SUCCESS"
    assert payload["pulled_counts"] == {
        "balances": 1,
        "positions": 1,
        "transactions": 1,
    }


class _ReadyAdapter:
    provider_code = "READY"
    institution_kind = InstitutionKind.BANK
    capabilities = AdapterCapabilities()

    def validate_read_only_scope(self) -> None:
        return None

    def list_accounts(self) -> list[Any]:
        return []

    def fetch_balances(self, since_utc: datetime) -> list[Any]:
        return []

    def fetch_positions(self, since_utc: datetime) -> list[Any]:
        return []

    def fetch_transactions(self, since_utc: datetime) -> list[Any]:
        return []


class _BrokenAdapter(_ReadyAdapter):
    provider_code = "BROKEN"

    def validate_read_only_scope(self) -> None:
        raise ValueError("missing read scope")


class _FakeDbSession:
    def __init__(self, *, commit_error: Exception | None = None) -> None:
        self._commit_error = commit_error
        self.commit_calls = 0
        self.rollback_calls = 0

    def commit(self) -> None:
        self.commit_calls += 1
        if self._commit_error is not None:
            raise self._commit_error

    def rollback(self) -> None:
        self.rollback_calls += 1


def test_ingestion_preflight_reports_degraded_sources(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "app.api.jobs.build_adapter_registry",
        lambda: {"fixture": _ReadyAdapter(), "saxo": _BrokenAdapter()},
    )

    response = client.post("/jobs/ingestion/preflight", json={"source": "all"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "DEGRADED"
    assert payload["sources"] == [
        {"source": "fixture", "status": "READY", "error": None},
        {"source": "saxo", "status": "FAILED", "error": "missing read scope"},
    ]


def test_ingestion_preflight_rejects_unknown_source(client: TestClient) -> None:
    response = client.post("/jobs/ingestion/preflight", json={"source": "unknown"})

    assert response.status_code == 400
    assert "Unknown ingestion source" in response.json()["detail"]


def test_ingestion_preflight_all_rejects_when_no_sources(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.api.jobs.build_adapter_registry", lambda: {})

    with pytest.raises(HTTPException, match="No ingestion sources configured"):
        preflight_ingestion(IngestionPreflightRequest(source="all"))


def test_ingestion_preflight_selected_source_ready(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.api.jobs.build_adapter_registry", lambda: {"fixture": _ReadyAdapter()})

    response = preflight_ingestion(IngestionPreflightRequest(source="fixture"))

    assert response.status == "READY"
    assert [item.model_dump() for item in response.sources] == [
        {"source": "fixture", "status": "READY", "error": None}
    ]


def test_ingestion_preflight_selected_source_failed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.api.jobs.build_adapter_registry",
        lambda: {"fixture": _BrokenAdapter()},
    )

    response = preflight_ingestion(IngestionPreflightRequest(source="fixture"))

    assert response.status == "FAILED"
    assert [item.model_dump() for item in response.sources] == [
        {"source": "fixture", "status": "FAILED", "error": "missing read scope"}
    ]


def test_run_ingestion_job_returns_500_when_service_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    class _BoomService:
        def __init__(self, db: Any, adapters: dict[str, Any]) -> None:
            del db, adapters

        def run(self, *, source: str, since_utc: datetime | None = None) -> dict[str, Any]:
            del source, since_utc
            raise RuntimeError("boom")

    fake_db = _FakeDbSession()
    monkeypatch.setattr("app.api.jobs.IngestionService", _BoomService)
    monkeypatch.setattr("app.api.jobs.build_adapter_registry", lambda: {"fixture": _ReadyAdapter()})

    with pytest.raises(HTTPException, match="ingestion failed") as exc_info:
        run_ingestion_job(request=IngestionRunRequest(source="fixture"), db=fake_db)  # type: ignore[arg-type]

    assert exc_info.value.status_code == 500
    assert fake_db.commit_calls == 1
    assert fake_db.rollback_calls == 0


def test_run_ingestion_job_rolls_back_when_error_commit_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _BoomService:
        def __init__(self, db: Any, adapters: dict[str, Any]) -> None:
            del db, adapters

        def run(self, *, source: str, since_utc: datetime | None = None) -> dict[str, Any]:
            del source, since_utc
            raise RuntimeError("boom")

    fake_db = _FakeDbSession(commit_error=RuntimeError("commit failed"))
    monkeypatch.setattr("app.api.jobs.IngestionService", _BoomService)
    monkeypatch.setattr("app.api.jobs.build_adapter_registry", lambda: {"fixture": _ReadyAdapter()})

    with pytest.raises(HTTPException, match="ingestion failed"):
        run_ingestion_job(request=IngestionRunRequest(source="fixture"), db=fake_db)  # type: ignore[arg-type]

    assert fake_db.commit_calls == 1
    assert fake_db.rollback_calls == 1
