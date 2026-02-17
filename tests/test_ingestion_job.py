from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.models.audit_event import AuditEvent
from app.models.ingestion_run import IngestionRun, IngestionRunStatus


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

        stmt = select(AuditEvent.event_type).order_by(AuditEvent.id.asc())
        event_types = session.scalars(stmt).all()
        assert event_types == ["INGESTION_PULL_STARTED", "INGESTION_PULL_COMPLETED"]


def test_ingestion_job_rejects_unknown_source(client: TestClient) -> None:
    response = client.post("/jobs/ingestion/run", json={"source": "unknown"})

    assert response.status_code == 400
    assert "Unknown ingestion source" in response.json()["detail"]
