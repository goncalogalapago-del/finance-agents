from datetime import datetime
from decimal import Decimal
from typing import Optional
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Position(Base):
    __tablename__ = "positions"
    __table_args__ = (
        UniqueConstraint("account_id", "instrument_id", "as_of_utc", name="uq_position_snapshot"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    account_id: Mapped[str] = mapped_column(String(36), ForeignKey("accounts.id"), nullable=False)
    instrument_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("instruments.id"), nullable=False
    )
    as_of_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(24, 10), nullable=False)
    avg_cost: Mapped[Optional[Decimal]] = mapped_column(Numeric(20, 6), nullable=True)
    market_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(20, 6), nullable=True)
    market_value: Mapped[Optional[Decimal]] = mapped_column(Numeric(20, 6), nullable=True)
