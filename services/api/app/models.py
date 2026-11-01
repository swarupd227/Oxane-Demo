from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import BigInteger, Boolean, DateTime, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class CaseStatus(StrEnum):
    AWAITING_PACK = "awaiting_pack"
    IN_REVIEW = "in_review"
    APPROVED = "approved"
    APPROVED_WITH_OPEN_ITEMS = "approved_with_open_items"


class OnboardingCase(Base):
    __tablename__ = "onboarding_case"

    number: Mapped[str] = mapped_column(String(16), primary_key=True)
    status: Mapped[str] = mapped_column(String(32), default=CaseStatus.AWAITING_PACK)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    session_id: Mapped[str | None] = mapped_column(String(32))


class CaseEvent(Base):
    """One thing a person did. Rows are never changed, and the database enforces that."""

    __tablename__ = "case_event"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(String(32), index=True)
    seq: Mapped[int] = mapped_column(Integer)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    actor: Mapped[str] = mapped_column(String(32))
    type: Mapped[str] = mapped_column(String(32))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    earlier: Mapped[bool] = mapped_column(Boolean)
    prev_hash: Mapped[str] = mapped_column(String(64))
    hash: Mapped[str] = mapped_column(String(64))
