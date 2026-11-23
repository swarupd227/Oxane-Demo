"""Which model key the workbench uses, and the storage behind the admin's Settings screen.

Resolution, used by every model client (the scripted gateway in record and live modes, the new
deals' gateway and the record scripts that drive it): a key saved on the Settings screen first,
then the environment's key. It is read again on every call, so a change takes effect on the next
request without a restart.

A saved key is encrypted at rest with Fernet under SETTINGS_ENCRYPTION_KEY. Without that key
nothing can be saved: there is no plaintext fallback. The key itself never leaves this module in
a response, a log line, an audit event or an error message.
"""

import os
import re
import threading
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

import httpx
from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.admin.models import AppSetting
from app.config import settings
from app.db import engine

NAME = "ai_provider"
AUDIT_CHAIN = "settings-ai-provider"
PROVIDERS = ("anthropic", "foundry")
PROVIDER_LABELS = {"anthropic": "Anthropic API", "foundry": "Claude on Microsoft Foundry"}
ENV_VARS = {"anthropic": "ANTHROPIC_API_KEY", "foundry": "ANTHROPIC_FOUNDRY_API_KEY"}
ANTHROPIC_BASE = "https://api.anthropic.com"
API_VERSION = "2023-06-01"
CHECK_LIMIT_PER_MINUTE = 10
REDACTED = "[redacted]"
_KEY_SHAPE = re.compile(r"sk-ant-[A-Za-z0-9_\-]{4,}")
_KEY_ALLOWED = re.compile(r"^[A-Za-z0-9_\-.:+/=]{20,400}$")
_MODEL_ALLOWED = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:@/\-]{0,79}$")


class EncryptionUnavailable(RuntimeError):
    """SETTINGS_ENCRYPTION_KEY is unset or is not a valid Fernet key."""


# Encryption


def _fernet() -> Fernet | None:
    raw = settings.settings_encryption_key.strip()
    if not raw:
        return None
    try:
        return Fernet(raw.encode())
    except ValueError:
        return None


def encryption_ready() -> bool:
    return _fernet() is not None


def encrypt(key: str) -> bytes:
    fernet = _fernet()
    if fernet is None:
        raise EncryptionUnavailable("SETTINGS_ENCRYPTION_KEY is not set")
    return fernet.encrypt(key.encode("utf-8"))


def decrypt(token: bytes | None) -> str | None:
    """The saved key, or None when there is none or it cannot be read with today's key."""
    fernet = _fernet()
    if not token or fernet is None:
        return None
    try:
        return fernet.decrypt(bytes(token)).decode("utf-8")
    except (InvalidToken, ValueError):
        return None


# Validation and scrubbing


def key_problem(key: str) -> str | None:
    if not key:
        return "Enter the API key"
    if not _KEY_ALLOWED.match(key):
        return "That does not look like an API key: 20 to 400 characters, no spaces or quotes"
    return None


def model_problem(model: str) -> str | None:
    if model and not _MODEL_ALLOWED.match(model):
        return "Use a model id such as claude-opus-5-5"
    return None


def scrub(text: str, *secrets: str | None) -> str:
    """Text safe to show or store: every given secret, and anything shaped like a key, removed."""
    for secret in secrets:
        if secret and len(secret) >= 4:
            text = text.replace(secret, REDACTED)
    return _KEY_SHAPE.sub(REDACTED, text)[:500]


def last4(key: str) -> str | None:
    return key[-4:] if len(key) >= 12 else None


# Resolution


@dataclass(frozen=True)
class Effective:
    provider: str
    key: str = field(repr=False)
    model: str
    source: Literal["db", "env", "none"]
    # A key is saved but cannot be decrypted with the current SETTINGS_ENCRYPTION_KEY.
    unreadable: bool = False

    @property
    def configured(self) -> bool:
        return bool(self.key)


def env_key(provider: str) -> str:
    key = settings.anthropic_foundry_api_key if provider == "foundry" \
        else settings.anthropic_api_key
    return key.strip()


def _row(db: Session) -> AppSetting | None:
    return db.get(AppSetting, NAME)


def _resolve(row: AppSetting | None, env_provider: str | None) -> Effective:
    model = (row.model if row is not None and row.model else None) or settings.deals_model
    unreadable = False
    if row is not None and row.key_encrypted:
        key = decrypt(row.key_encrypted)
        if key:
            return Effective(row.provider, key, model, "db")
        unreadable = True
    provider = env_provider or settings.llm_provider
    key = env_key(provider)
    return Effective(provider, key, model, "env" if key else "none", unreadable)


def effective(db: Session | None = None, env_provider: str | None = None) -> Effective:
    """The key, provider and model every model client uses right now. Never raises."""
    try:
        if db is not None:
            return _resolve(_row(db), env_provider)
        with Session(engine) as own:
            return _resolve(_row(own), env_provider)
    except SQLAlchemyError:
        # No database, or the table is not migrated yet: the environment decides.
        return _resolve(None, env_provider)


def key_health(db: Session) -> bool | None:
    """Whether the key in use passed its last connection test: True or False, or None when it
    has not been tested since it was set. Only a test of that same key counts (not a typed one),
    and nothing about the key itself is returned."""
    try:
        row = _row(db)
    except SQLAlchemyError:
        return None
    current = _resolve(row, None)
    test = (row.last_test if row is not None else None) or {}
    if not current.configured or not test or test.get("subject") != current.source \
            or test.get("provider") != current.provider:
        return None
    if current.source == "db" and row is not None and row.updated_at is not None:
        try:
            if datetime.fromisoformat(test.get("at", "")) < row.updated_at:
                return None
        except (TypeError, ValueError):
            return None
    return bool(test.get("ok"))


def sdk_client(current: Effective) -> Any:
    """A fresh SDK client for the resolved key. Built per key, so nothing outlives a change."""
    key = current.key or None
    if current.provider == "foundry":
        from anthropic import AnthropicFoundry

        return AnthropicFoundry(api_key=key)
    from anthropic import Anthropic

    return Anthropic(api_key=key)


# The local .env file


def env_file() -> Path | None:
    raw = settings.local_env_file.strip()
    return Path(raw) if raw else None


def env_file_state() -> dict[str, Any]:
    path = env_file()
    if path is None:
        return {"enabled": False, "writable": False}
    writable = path.is_file() and os.access(path, os.W_OK)
    return {"enabled": True, "writable": writable}


def write_env(path: Path, name: str, value: str) -> None:
    """Set NAME=value in a .env file, keeping every other line, comment and line ending.

    Written to a temporary file and renamed over the original, so a reader never sees half a
    file. A single-file bind mount cannot be renamed over; that one is rewritten in place.
    """
    text = ""
    if path.exists():
        with open(path, encoding="utf-8", newline="") as handle:
            text = handle.read()
    newline = "\r\n" if "\r\n" in text else "\n"
    pattern = re.compile(rf"^\s*(export\s+)?{re.escape(name)}\s*=")
    lines: list[str] = []
    done = False
    for line in text.splitlines():
        if pattern.match(line):
            if not done:
                lines.append(f"{name}={value}")
                done = True
            continue  # a duplicate would shadow the new value
        lines.append(line)
    if not done:
        lines.append(f"{name}={value}")
    body = newline.join(lines) + newline
    temp = path.with_name(f".{path.name}.{uuid.uuid4().hex[:8]}.tmp")
    try:
        with open(temp, "w", encoding="utf-8", newline="") as handle:
            handle.write(body)
            handle.flush()
            os.fsync(handle.fileno())
        if path.exists():
            os.chmod(temp, path.stat().st_mode)
        os.replace(temp, path)
    except OSError:
        temp.unlink(missing_ok=True)
        with open(path, "r+" if path.exists() else "w", encoding="utf-8", newline="") as handle:
            handle.seek(0)
            handle.write(body)
            handle.truncate()
            handle.flush()
            os.fsync(handle.fileno())


# Checking a key


class _RateLimit:
    def __init__(self, per_minute: int) -> None:
        self.per_minute = per_minute
        self._calls: deque[float] = deque()
        self._lock = threading.Lock()

    def allow(self) -> bool:
        now = time.monotonic()
        with self._lock:
            while self._calls and now - self._calls[0] > 60:
                self._calls.popleft()
            if len(self._calls) >= self.per_minute:
                return False
            self._calls.append(now)
            return True

    def reset(self) -> None:
        with self._lock:
            self._calls.clear()


check_limit = _RateLimit(CHECK_LIMIT_PER_MINUTE)


def _send(method: str, url: str, **kwargs: Any) -> httpx.Response:
    """The one network call the test makes. Tests replace this."""
    return httpx.request(method, url, **kwargs)


def _error_text(response: httpx.Response) -> str:
    try:
        body = response.json()
        error = body.get("error") if isinstance(body, dict) else None
        if isinstance(error, dict) and error.get("message"):
            return f"{error.get('type', 'error')}: {error['message']}"
    except ValueError:
        pass
    return response.text[:300] or response.reason_phrase


def check_key(provider: str, key: str, model: str, subject: str) -> dict[str, Any]:
    """A cheap call that proves the key works: list models (Anthropic) or a one-token message
    (Foundry, which has no model list). The key is never part of the result."""
    result: dict[str, Any] = {"ok": False, "status": None, "latency_ms": None, "models": [],
                              "error": None, "provider": provider, "subject": subject,
                              "at": datetime.now(UTC).isoformat()}
    headers = {"x-api-key": key, "anthropic-version": API_VERSION}
    if provider == "foundry":
        base = os.environ.get("ANTHROPIC_FOUNDRY_BASE_URL", "").rstrip("/")
        resource = os.environ.get("ANTHROPIC_FOUNDRY_RESOURCE", "").strip()
        if not base and not resource:
            result["error"] = "ANTHROPIC_FOUNDRY_RESOURCE is not set on the API"
            return result
        base = base or f"https://{resource}.services.ai.azure.com/anthropic"
        request: dict[str, Any] = {
            "method": "POST", "url": f"{base}/v1/messages",
            "headers": {**headers, "api-key": key, "content-type": "application/json"},
            "json": {"model": model, "max_tokens": 1,
                     "messages": [{"role": "user", "content": "ping"}]}}
    else:
        request = {"method": "GET", "url": f"{ANTHROPIC_BASE}/v1/models", "headers": headers,
                   "params": {"limit": 50}}
    started = time.perf_counter()
    try:
        response = _send(request.pop("method"), request.pop("url"), timeout=15, **request)
    except httpx.HTTPError as error:
        result["latency_ms"] = round((time.perf_counter() - started) * 1000)
        result["error"] = scrub(f"Could not reach the provider: {type(error).__name__}", key)
        return result
    result["latency_ms"] = round((time.perf_counter() - started) * 1000)
    result["status"] = response.status_code
    if response.status_code == 200:
        result["ok"] = True
        if provider == "anthropic":
            try:
                data = response.json().get("data", [])
                result["models"] = [str(m.get("id")) for m in data if isinstance(m, dict)][:50]
            except (ValueError, AttributeError):
                result["models"] = []
        else:
            result["models"] = [model]
    else:
        result["error"] = scrub(_error_text(response), key)
    return result
