from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import JSON, BigInteger, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id_type = BigInteger().with_variant(Integer, "sqlite")

    id: Mapped[int] = mapped_column(id_type, primary_key=True, autoincrement=True)
    event_type: Mapped[str] = mapped_column(String(128), nullable=False)
    event_time_utc: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    actor_id: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    run_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    entity_type: Mapped[str] = mapped_column(String(128), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(256), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    prev_hash: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    event_hash: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
