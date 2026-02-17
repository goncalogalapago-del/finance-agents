from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.models.audit_event import AuditEvent
from app.services.audit import AuditService


def test_chain_hash_is_stable_across_payload_key_order() -> None:
    event_time = datetime(2026, 1, 1, tzinfo=timezone.utc)

    hash_a = AuditService._chain_hash(
        prev_hash="abc",
        event_type="EVENT",
        event_time_utc=event_time,
        entity_type="entity",
        entity_id="id-1",
        payload={"b": 2, "a": 1},
    )
    hash_b = AuditService._chain_hash(
        prev_hash="abc",
        event_type="EVENT",
        event_time_utc=event_time,
        entity_type="entity",
        entity_id="id-1",
        payload={"a": 1, "b": 2},
    )

    assert hash_a == hash_b


def test_append_event_links_hash_chain(test_session_factory: sessionmaker) -> None:
    with test_session_factory() as session:
        service = AuditService(session)
        first = service.append_event(
            event_type="FIRST",
            entity_type="ingestion_run",
            entity_id="run-1",
            run_id="run-1",
            payload={"step": 1},
        )
        second = service.append_event(
            event_type="SECOND",
            entity_type="ingestion_run",
            entity_id="run-1",
            run_id="run-1",
            payload={"step": 2},
        )
        session.commit()

        stored = session.scalars(select(AuditEvent).order_by(AuditEvent.id.asc())).all()

    assert len(stored) == 2
    assert first.prev_hash is None
    assert second.prev_hash == first.event_hash
    assert stored[1].prev_hash == stored[0].event_hash

