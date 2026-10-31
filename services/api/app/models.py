from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, String, func
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
