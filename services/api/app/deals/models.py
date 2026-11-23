"""Tables for deals created in the workbench. Uploaded files are stored in the database, so they
survive a container restart; every write is also an event in the owning record's hash chain."""

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    LargeBinary,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def new_chain() -> str:
    return uuid.uuid4().hex


class Client(Base):
    __tablename__ = "deal_client"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    short_name: Mapped[str] = mapped_column(String(40))
    contact_name: Mapped[str] = mapped_column(String(80), default="")
    ai_permitted: Mapped[bool] = mapped_column(Boolean, default=True)
    approval_levels: Mapped[int] = mapped_column(Integer, default=2)
    master_field_overrides: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    audit_id: Mapped[str] = mapped_column(String(32), default=new_chain)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Facility(Base):
    __tablename__ = "deal_facility"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("deal_client.id"))
    name: Mapped[str] = mapped_column(String(120))
    deal_type: Mapped[str] = mapped_column(String(40))
    commitment_cents: Mapped[int] = mapped_column(BigInteger)
    status: Mapped[str] = mapped_column(String(16), default="onboarding")
    case_id: Mapped[int | None] = mapped_column(Integer)
    config: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    audit_id: Mapped[str] = mapped_column(String(32), default=new_chain)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    live_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class DealCase(Base):
    __tablename__ = "deal_case"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("deal_client.id"))
    facility_id: Mapped[int | None] = mapped_column(ForeignKey("deal_facility.id"))
    facility_name: Mapped[str] = mapped_column(String(120))
    deal_type: Mapped[str] = mapped_column(String(40))
    commitment_cents: Mapped[int] = mapped_column(BigInteger)
    stage: Mapped[str] = mapped_column(String(24), default="documents")
    state: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    audit_id: Mapped[str] = mapped_column(String(32), default=new_chain)
    created_by: Mapped[str] = mapped_column(String(80), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Document(Base):
    __tablename__ = "deal_document"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    case_id: Mapped[int | None] = mapped_column(ForeignKey("deal_case.id"), index=True)
    submission_id: Mapped[int | None] = mapped_column(ForeignKey("deal_submission.id"),
                                                      index=True)
    name: Mapped[str] = mapped_column(String(200))
    kind: Mapped[str] = mapped_column(String(24))
    kind_source: Mapped[str] = mapped_column(String(12), default="analyst")
    version: Mapped[int] = mapped_column(Integer, default=1)
    effective_date: Mapped[date | None] = mapped_column(Date)
    sha256: Mapped[str] = mapped_column(String(64))
    size: Mapped[int] = mapped_column(Integer)
    content_type: Mapped[str] = mapped_column(String(100))
    content: Mapped[bytes] = mapped_column(LargeBinary, deferred=True)
    status: Mapped[str] = mapped_column(String(12), default="active")
    replaces_id: Mapped[int | None] = mapped_column(Integer)
    uploaded_by: Mapped[str] = mapped_column(String(80), default="")
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),
                                                  server_default=func.now())


class ClientMapping(Base):
    """A client's stored tape mapping, per layout. Never shared between clients."""

    __tablename__ = "deal_client_mapping"
    __table_args__ = (UniqueConstraint("client_id", "signature"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("deal_client.id"))
    signature: Mapped[str] = mapped_column(String(64))
    headers: Mapped[list[str]] = mapped_column(JSONB)
    columns: Mapped[dict[str, Any]] = mapped_column(JSONB)
    status_map: Mapped[dict[str, Any]] = mapped_column(JSONB)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(),
                                                 onupdate=func.now())


class Submission(Base):
    __tablename__ = "deal_submission"
    __table_args__ = (UniqueConstraint("facility_id", "period"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    facility_id: Mapped[int] = mapped_column(ForeignKey("deal_facility.id"))
    period: Mapped[str] = mapped_column(String(7))
    period_end: Mapped[date] = mapped_column(Date)
    due_date: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(16), default="expected")
    state: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    audit_id: Mapped[str] = mapped_column(String(32), default=new_chain)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class LlmSpend(Base):
    """One model call for a new deal. Live calls count against the daily cap."""

    __tablename__ = "deal_llm_spend"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    day: Mapped[date] = mapped_column(Date, index=True)
    case_id: Mapped[int | None] = mapped_column(Integer, index=True)
    submission_id: Mapped[int | None] = mapped_column(Integer, index=True)
    task: Mapped[str] = mapped_column(String(40))
    model: Mapped[str] = mapped_column(String(40))
    input_tokens: Mapped[int] = mapped_column(Integer)
    output_tokens: Mapped[int] = mapped_column(Integer)
    cache_read_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cache_write_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[float] = mapped_column(Numeric(12, 6))
    replay: Mapped[bool] = mapped_column(Boolean, default=False)
    seconds: Mapped[float] = mapped_column(Numeric(8, 1), default=0)


class WorkItem(Base):
    """A hand-off: a step finished by one persona, waiting on another."""

    __tablename__ = "work_item"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key: Mapped[str] = mapped_column(String(160), unique=True)
    subject: Mapped[str] = mapped_column(String(80), index=True)
    chain: Mapped[str] = mapped_column(String(32))
    kind: Mapped[str] = mapped_column(String(24))
    title: Mapped[str] = mapped_column(String(200))
    detail: Mapped[str] = mapped_column(String(400), default="")
    role: Mapped[str] = mapped_column(String(24))
    assignee: Mapped[str | None] = mapped_column(String(40))
    client_key: Mapped[str | None] = mapped_column(String(40))
    from_persona: Mapped[str | None] = mapped_column(String(40))
    link: Mapped[str] = mapped_column(String(200), default="")
    status: Mapped[str] = mapped_column(String(12), default="open")
    sla_hours: Mapped[int] = mapped_column(Integer, default=24)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    done_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    done_by: Mapped[str | None] = mapped_column(String(40))
    note: Mapped[str | None] = mapped_column(String(1000))
