from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Optional
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, Numeric, String, Text, UniqueConstraint
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class TransactionType(str, Enum):
    TRADE = "trade"
    DEPOSIT = "deposit"
    WITHDRAWAL = "withdrawal"
    FEE = "fee"
    DIVIDEND = "dividend"
    INTEREST = "interest"
    OTHER = "other"


class TradeSide(str, Enum):
    BUY = "buy"
    SELL = "sell"


class Transaction(Base):
    __tablename__ = "transactions"
    __table_args__ = (
        UniqueConstraint("account_id", "external_txn_id", name="uq_transaction_external"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    account_id: Mapped[str] = mapped_column(String(36), ForeignKey("accounts.id"), nullable=False)
    instrument_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("instruments.id"), nullable=True
    )
    external_txn_id: Mapped[str] = mapped_column(Text, nullable=False)
    txn_type: Mapped[TransactionType] = mapped_column(
        SAEnum(TransactionType, name="txn_type_enum", native_enum=False),
        nullable=False,
    )
    trade_side: Mapped[Optional[TradeSide]] = mapped_column(
        SAEnum(TradeSide, name="trade_side_enum", native_enum=False),
        nullable=True,
    )
    executed_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    settled_at_utc: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    quantity: Mapped[Optional[Decimal]] = mapped_column(Numeric(24, 10), nullable=True)
    price: Mapped[Optional[Decimal]] = mapped_column(Numeric(20, 6), nullable=True)
    gross_amount: Mapped[Optional[Decimal]] = mapped_column(Numeric(20, 6), nullable=True)
    fee_amount: Mapped[Optional[Decimal]] = mapped_column(Numeric(20, 6), nullable=True)
    tax_amount: Mapped[Optional[Decimal]] = mapped_column(Numeric(20, 6), nullable=True)
    net_amount: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    raw_category: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
