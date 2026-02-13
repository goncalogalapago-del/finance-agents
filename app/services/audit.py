from datetime import datetime, timezone
from hashlib import sha256
from json import dumps
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.audit_event import AuditEvent


class AuditService:
    """Append-only audit writer with optional hash chaining."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def append_event(
        self,
        *,
        event_type: str,
        entity_type: str,
        entity_id: str,
        payload: dict[str, Any],
        actor_id: Optional[str] = None,
        run_id: Optional[str] = None,
    ) -> AuditEvent:
        prev = self.db.scalar(select(AuditEvent).order_by(AuditEvent.id.desc()).limit(1))
        prev_hash = prev.event_hash if prev is not None else None
        event_time_utc = datetime.now(timezone.utc)
        chain_value = self._chain_hash(
            prev_hash=prev_hash,
            event_type=event_type,
            event_time_utc=event_time_utc,
            entity_type=entity_type,
            entity_id=entity_id,
            payload=payload,
        )

        event = AuditEvent(
            event_type=event_type,
            event_time_utc=event_time_utc,
            actor_id=actor_id,
            run_id=run_id,
            entity_type=entity_type,
            entity_id=entity_id,
            payload=payload,
            prev_hash=prev_hash,
            event_hash=chain_value,
        )
        self.db.add(event)
        self.db.flush()
        return event

    @staticmethod
    def _chain_hash(
        *,
        prev_hash: Optional[str],
        event_type: str,
        event_time_utc: datetime,
        entity_type: str,
        entity_id: str,
        payload: dict[str, Any],
    ) -> str:
        canonical_payload = dumps(payload, sort_keys=True, separators=(",", ":"))
        raw = "|".join(
            [
                prev_hash or "",
                event_type,
                event_time_utc.isoformat(),
                entity_type,
                entity_id,
                canonical_payload,
            ]
        )
        return sha256(raw.encode("utf-8")).hexdigest()
