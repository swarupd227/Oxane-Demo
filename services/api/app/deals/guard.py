"""What keeps live AI safe on a public demo: an access code, a daily spend cap, upload limits,
and a gateway that records every call's cost.

New deals call the model whenever a key is configured, whatever LLM_MODE says, because their
documents have never been seen before. A call whose exact request was recorded earlier is
replayed at no cost, which is how the automated tests run offline. Without a key only recorded
calls work. A client that does not permit AI never reaches this gateway at all.
"""

import hashlib
import json
import time
from dataclasses import asdict
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from fastapi import HTTPException, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.admin import ai_provider
from app.config import settings
from app.db import engine
from app.deals.models import LlmSpend
from app.pipeline.gateway import (
    AnthropicClient,
    ModelClient,
    ModelError,
    ReplayMiss,
    Schema,
    Usage,
    strict_schema,
)

ACCESS_HEADER = "x-demo-access-code"
UPLOAD_TYPES = {
    ".pdf": ("application/pdf", b"%PDF"),
    ".csv": ("text/csv", None),
    ".xlsx": ("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", b"PK"),
}


class SpendCapReached(RuntimeError):
    """Today's live model spend has reached the cap."""


class ModelUnavailable(RuntimeError):
    """No key is configured and this request was never recorded."""


def access_configured() -> bool:
    # There is no access code: uploads and live AI are open, and the daily spend cap is the guard.
    return True


def check_access(request: Request) -> None:
    """Uploads and model calls are open to every working persona; the daily cap limits spend."""
    return None


def spent_today(db: Session) -> float:
    total = db.scalar(select(func.coalesce(func.sum(LlmSpend.cost_usd), 0))
                      .where(LlmSpend.day == datetime.now(UTC).date(),
                             LlmSpend.replay.is_(False)))
    return float(total or 0)


def status(db: Session) -> dict[str, Any]:
    spent = spent_today(db)
    cap = settings.live_daily_cap_usd
    key_set = ai_provider.effective(db).configured
    return {
        "access_configured": access_configured(),
        "live_available": key_set or settings.deals_stub_model,
        "mode": "stub" if settings.deals_stub_model else ("live" if key_set else "replay"),
        "spent_today_usd": round(spent, 4),
        "cap_usd": cap,
        "cap_reached": spent >= cap,
        # The key in use: True if its last connection test passed, False if it failed, None
        # if it has not been tested since it was set. Never anything about the key itself.
        "key_ok": ai_provider.key_health(db) if key_set else None,
        "max_upload_mb": settings.max_upload_mb,
        "upload_types": sorted(UPLOAD_TYPES),
    }


def check_upload(name: str, body: bytes) -> str:
    """The file's media type, or a 422 saying what is wrong with it."""
    suffix = Path(name).suffix.lower()
    if suffix not in UPLOAD_TYPES:
        raise HTTPException(status_code=422, detail="Upload a PDF, CSV or XLSX file")
    if not body:
        raise HTTPException(status_code=422, detail="The file is empty")
    if len(body) > settings.max_upload_mb * 1024 * 1024:
        raise HTTPException(status_code=413, detail=f"Files are limited to "
                            f"{settings.max_upload_mb} MB")
    media, magic = UPLOAD_TYPES[suffix]
    if magic and not body.startswith(magic):
        raise HTTPException(status_code=422, detail=f"The file is not a valid {suffix[1:].upper()}")
    if suffix == ".csv":
        try:
            body.decode("utf-8-sig")
        except UnicodeDecodeError as error:
            raise HTTPException(status_code=422, detail="The CSV is not UTF-8 text") from error
    return media


class DealsGateway:
    """The model gateway for one case or submission, with the same payload hashing as the
    scripted gateway, the daily cap checked before every live call and each call's cost saved."""

    def __init__(self, case_id: int | None = None, submission_id: int | None = None,
                 client_factory: Any = None, fixtures: Path | None = None,
                 client_key: str = "deal", ref: str = "") -> None:
        self.case_id = case_id
        self.submission_id = submission_id
        self.client_key = client_key
        self.ref = ref
        # The key and model come from Settings › AI provider when saved there, else the
        # environment; AnthropicClient resolves the key again on each call.
        current = ai_provider.effective()
        self.model = current.model
        self.fixtures = fixtures or settings.deals_llm_fixtures
        self.live = current.configured
        self._factory = client_factory or (lambda: AnthropicClient(settings.llm_provider))
        self._client: ModelClient | None = None
        self.usage: list[Usage] = []

    def parse(self, task: str, system: str, content: list[dict[str, Any]],
              schema: type[Schema], max_tokens: int = 16000, effort: str = "medium") -> Schema:
        payload = {
            "model": self.model,
            "max_tokens": max_tokens,
            "thinking": {"type": "adaptive"},
            "output_config": {"effort": effort,
                              "format": {"type": "json_schema", "schema": strict_schema(schema)}},
            "system": [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            "messages": [{"role": "user", "content": content}],
        }
        digest = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"))
                                .encode("utf-8")).hexdigest()
        path = self.fixtures / task / f"{digest[:32]}.json"
        if settings.deals_stub_model:
            from app.deals import stub

            self._save(task, Usage(task=task, input_tokens=0, output_tokens=0, from_replay=True))
            return schema.model_validate_json(stub.answer(task, content))
        if path.exists():
            saved = json.loads(path.read_text(encoding="utf-8"))
            usage = Usage(**{**saved["usage"], "task": task, "from_replay": True})
            self._save(task, usage)
            return schema.model_validate_json(saved["text"])
        if not self.live:
            raise ModelUnavailable(f"No model key is configured and {task} was not recorded")
        with Session(engine) as db:
            if spent_today(db) >= settings.live_daily_cap_usd:
                raise SpendCapReached("Today's live AI limit has been reached")
        if self._client is None:
            self._client = self._factory()
        started = time.perf_counter()
        text, usage = self._client.request(payload)
        usage = Usage(**{**asdict(usage), "task": task,
                         "seconds": round(time.perf_counter() - started, 1)})
        self._save(task, usage)
        parsed = schema.model_validate_json(text)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps({"task": task, "model": self.model, "text": text,
                                        "usage": asdict(usage)}, indent=1), encoding="utf-8")
        except OSError:
            pass  # A read-only image keeps the answer for this request only.
        return parsed

    def _save(self, task: str, usage: Usage, outcome: str = "accepted") -> None:
        self.usage.append(usage)
        if not usage.from_replay:
            try:  # The agents console's run log: live calls only; code checks follow.
                from app.agents import runlog

                runlog.record_run(task, self.client_key, f"case:{self.case_id}" if self.case_id
                                  else f"submission:{self.submission_id}", usage.input_tokens,
                                  usage.output_tokens, round(usage.cost_usd(self.model), 6),
                                  "awaiting_review", int(usage.seconds * 1000), ref=self.ref)
            except Exception:  # noqa: BLE001 - logging must never stop a step
                pass
        # Its own transaction, so the spend is kept even if the step that asked fails later.
        with Session(engine) as db:
            db.add(LlmSpend(day=datetime.now(UTC).date(), case_id=self.case_id,
                            submission_id=self.submission_id, task=task[:40], model=self.model,
                            input_tokens=usage.input_tokens, output_tokens=usage.output_tokens,
                            cache_read_tokens=usage.cache_read_tokens,
                            cache_write_tokens=usage.cache_write_tokens,
                            cost_usd=Decimal(str(round(usage.cost_usd(self.model), 6))),
                            replay=usage.from_replay, seconds=Decimal(str(usage.seconds))))
            db.commit()


def cost_of(db: Session, case_id: int | None = None,
            submission_id: int | None = None) -> dict[str, Any]:
    where = (LlmSpend.case_id == case_id) if case_id is not None \
        else (LlmSpend.submission_id == submission_id)
    rows = list(db.scalars(select(LlmSpend).where(where)))
    return {
        "calls": len(rows),
        "live_calls": sum(not r.replay for r in rows),
        "cost_usd": round(sum(float(r.cost_usd) for r in rows), 4),
        "live_cost_usd": round(sum(float(r.cost_usd) for r in rows if not r.replay), 4),
        "tokens": sum(r.input_tokens + r.output_tokens for r in rows),
    }


def today() -> date:
    return datetime.now(UTC).date()


__all__ = ["DealsGateway", "SpendCapReached", "ModelUnavailable", "ModelError", "ReplayMiss",
           "check_access", "check_upload", "status", "cost_of", "today"]
