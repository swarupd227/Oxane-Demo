"""Workbench settings an administrator changes at run time. One row per setting."""

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, LargeBinary, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class AppSetting(Base):
    __tablename__ = "app_setting"

    name: Mapped[str] = mapped_column(String(40), primary_key=True)
    provider: Mapped[str] = mapped_column(String(16), default="anthropic")
    # Fernet token (AES-128-CBC with HMAC-SHA256) under SETTINGS_ENCRYPTION_KEY. Never plaintext.
    key_encrypted: Mapped[bytes | None] = mapped_column(LargeBinary)
    last4: Mapped[str | None] = mapped_column(String(4))
    model: Mapped[str | None] = mapped_column(String(80))
    last_test: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    updated_by: Mapped[str | None] = mapped_column(String(80))
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True),
                                                        server_default=func.now())
