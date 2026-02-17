from datetime import datetime, timezone
from enum import Enum
from uuid import uuid4

from sqlalchemy import DateTime, String, Text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class InstitutionType(str, Enum):
    BROKER = "BROKER"
    BANK = "BANK"


class Institution(Base):
    __tablename__ = "institutions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    name: Mapped[str] = mapped_column(Text, nullable=False)
    type: Mapped[InstitutionType] = mapped_column(
        SAEnum(InstitutionType, name="institution_type_enum", native_enum=False),
        nullable=False,
    )
    provider_code: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    created_at_utc: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
