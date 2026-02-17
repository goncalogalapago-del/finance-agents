from datetime import datetime
from decimal import Decimal
from typing import Optional
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Balance(Base):
    __tablename__ = "balances"
    __table_args__ = (
        UniqueConstraint("account_id", "as_of_utc", "currency", name="uq_balance_snapshot"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    account_id: Mapped[str] = mapped_column(String(36), ForeignKey("accounts.id"), nullable=False)
    as_of_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    balance_amount: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    available_amount: Mapped[Optional[Decimal]] = mapped_column(Numeric(20, 6), nullable=True)
