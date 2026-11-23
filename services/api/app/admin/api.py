"""Settings › AI provider: the administrator sets the model key the workbench uses.

Every endpoint needs the Administrator persona: the demo is public with
no sign-in, so the persona alone proves nothing. No response, log line, audit event or error
message ever contains the key; a request body is never echoed back in a validation error.
"""

from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi import Query as QueryParam
from sqlalchemy.orm import Session

from app.admin import ai_provider as ap
from app.admin.models import AppSetting
from app.config import settings
from app.db import get_session
from app.deals import audit
from app.personas import ROLES, Persona, acting

router = APIRouter(prefix="/api/admin")
SessionDep = Annotated[Session, Depends(get_session)]


def _refuse(reason: str, message: str) -> HTTPException:
    return HTTPException(status_code=403, detail={"message": message, "reason": reason,
                                                  "fields": {}})


def _admin(request: Request, db: Session) -> Persona:
    persona = acting(request, db)
    if persona is None or persona.role != "admin":
        who = f" You are acting as {persona.name}, {ROLES[persona.role].lower()}." if persona \
            else ""
        raise _refuse("not_admin", f"Only the administrator can change settings.{who}")
    return persona


def _invalid(fields: dict[str, str]) -> None:
    if fields:
        raise HTTPException(status_code=422, detail={"message": "Check the highlighted fields",
                                                     "fields": fields})


async def _body(request: Request) -> dict[str, Any]:
    try:
        body = await request.json()
    except ValueError:
        body = None
    if not isinstance(body, dict):
        raise HTTPException(status_code=422, detail={"message": "Send a JSON object",
                                                     "fields": {}})
    return body


def _text(body: dict[str, Any], name: str) -> str | None:
    value = body.get(name)
    if value is None:
        return None
    if not isinstance(value, str):
        _invalid({name: "Must be text"})
    return value.strip()


def _view(db: Session) -> dict[str, Any]:
    row = db.get(AppSetting, ap.NAME)
    current = ap.effective(db)
    return {
        "provider": current.provider,
        "provider_label": ap.PROVIDER_LABELS.get(current.provider, current.provider),
        "configured": current.configured,
        "source": current.source,
        "last4": ap.last4(current.key) if current.key else None,
        "model": current.model,
        "model_override": row.model if row is not None else None,
        "model_default": settings.deals_model,
        "saved_provider": row.provider if row is not None and row.key_encrypted else None,
        "saved_key": bool(row is not None and row.key_encrypted),
        "saved_key_unreadable": current.unreadable,
        "env_provider": settings.llm_provider,
        "env_key_set": bool(ap.env_key(settings.llm_provider)),
        "updated_by": row.updated_by if row is not None else None,
        "updated_at": row.updated_at.isoformat() if row is not None and row.updated_at else None,
        "last_test": row.last_test if row is not None else None,
        "encryption_ready": ap.encryption_ready(),
        "env_file": ap.env_file_state(),
        "providers": [{"id": p, "label": ap.PROVIDER_LABELS[p]} for p in ap.PROVIDERS],
    }


def _record(db: Session, persona: Persona, kind: str, text: str, payload: dict[str, Any]) -> None:
    """The hash-chained log. Provider, model and what changed; never key material."""
    audit.append(db, ap.AUDIT_CHAIN, persona.id, kind, text, payload)


@router.get("/ai-provider")
def get_ai_provider(request: Request, db: SessionDep) -> dict[str, Any]:
    _admin(request, db)
    return _view(db)


@router.put("/ai-provider")
async def put_ai_provider(request: Request, db: SessionDep) -> dict[str, Any]:
    persona = _admin(request, db)
    body = await _body(request)
    provider = _text(body, "provider") or "anthropic"
    key = _text(body, "key") or ""
    model = _text(body, "model")
    fields: dict[str, str] = {}
    if provider not in ap.PROVIDERS:
        fields["provider"] = "Choose Anthropic API or Microsoft Foundry"
    if key and (problem := ap.key_problem(key)):
        fields["key"] = problem
    if model and (problem := ap.model_problem(model)):
        fields["model"] = problem
    _invalid(fields)
    row = db.get(AppSetting, ap.NAME)
    if not key and (row is None or not row.key_encrypted):
        _invalid({"key": "Enter the API key"})
    if key and not ap.encryption_ready():
        raise HTTPException(status_code=409, detail={
            "message": "The key can't be saved: SETTINGS_ENCRYPTION_KEY is not set on the API",
            "reason": "encryption_missing", "fields": {}})
    if row is None:
        row = AppSetting(name=ap.NAME, provider=provider)
        db.add(row)
    changes = []
    if key:
        row.key_encrypted = ap.encrypt(key)
        row.last4 = ap.last4(key)
        changes.append("key")
    if row.provider != provider:
        changes.append("provider")
    row.provider = provider
    if model is not None and (model or None) != row.model:
        row.model = model or None
        changes.append("model")
    row.updated_by = persona.name
    row.updated_at = datetime.now(UTC)
    label = ap.PROVIDER_LABELS[provider]
    words = {"key": f"saved a new {label} key", "provider": f"switched the provider to {label}",
             "model": f"set the model to {row.model or 'the default'}"}
    text = "; ".join(words[c] for c in changes) or "saved the AI provider unchanged"
    _record(db, persona, "ai-provider-save", text[0].upper() + text[1:],
            {"provider": provider, "model": row.model, "changed": changes})
    db.commit()
    written, env_error = False, None
    path = ap.env_file()
    if key and path is not None:
        try:
            ap.write_env(path, ap.ENV_VARS[provider], key)
            written = True
        except OSError as error:
            env_error = ap.scrub(f"Could not write the .env file: {error.strerror or 'error'}",
                                 key)
    return {**_view(db), "saved": True, "env_written": written, "env_error": env_error}


@router.delete("/ai-provider")
def delete_ai_provider(request: Request, db: SessionDep) -> dict[str, Any]:
    persona = _admin(request, db)
    row = db.get(AppSetting, ap.NAME)
    if row is not None and row.key_encrypted:
        row.key_encrypted = None
        row.last4 = None
        row.provider = "anthropic"
        row.updated_by = persona.name
        row.updated_at = datetime.now(UTC)
        _record(db, persona, "ai-provider-remove",
                "Removed the saved AI provider key; the environment's key applies",
                {"changed": ["key"]})
        db.commit()
    return _view(db)


@router.post("/ai-provider/test")
async def test_ai_provider(request: Request, db: SessionDep) -> dict[str, Any]:
    _admin(request, db)
    body = await _body(request)
    key = _text(body, "key") or ""
    provider = _text(body, "provider")
    model = _text(body, "model")
    fields: dict[str, str] = {}
    if provider is not None and provider not in ap.PROVIDERS:
        fields["provider"] = "Choose Anthropic API or Microsoft Foundry"
    if key and (problem := ap.key_problem(key)):
        fields["key"] = problem
    if model and (problem := ap.model_problem(model)):
        fields["model"] = problem
    _invalid(fields)
    current = ap.effective(db)
    if key:
        subject, provider = "typed", provider or "anthropic"
    else:
        key, subject, provider = current.key, current.source, current.provider
        if not key:
            raise HTTPException(status_code=422, detail={
                "message": "No key is configured: enter one to test it", "fields": {}})
    if not ap.check_limit.allow():
        raise HTTPException(status_code=429, detail={
            "message": "Too many connection tests: wait a minute and try again", "fields": {}})
    result = ap.check_key(provider, key, model or current.model, subject)
    row = db.get(AppSetting, ap.NAME)
    if row is None:
        row = AppSetting(name=ap.NAME, provider="anthropic", updated_at=None)
        db.add(row)
    row.last_test = {k: v for k, v in result.items() if k != "models"} | {
        "model_count": len(result["models"])}
    db.commit()
    return result


@router.post("/purge-test-data")
def purge_test_data(request: Request, db: SessionDep, apply: bool = False,
                    keep_client: Annotated[list[int] | None, QueryParam()] = None
                    ) -> dict[str, Any]:
    """Remove what tests left in this database (see app.admin.purge). A dry run unless
    ?apply=true; ?keep_client=ID (repeatable) keeps a client someone created on purpose.
    Administrator only, as for the AI provider."""
    from app.admin import purge

    persona = _admin(request, db)
    result = purge.purge_test_data(db, apply=apply, keep=set(keep_client or []))
    if apply:
        _record(db, persona, "purge-test-data",
                f"Purged test data: {result['clients']} clients, {result['cases']} cases, "
                f"{result['facilities']} facilities; rebuilt {result['scripted_rebuilt']} "
                "scripted hand-offs", {k: v for k, v in result.items()
                                       if isinstance(v, int) and not isinstance(v, bool)})
        db.commit()
    return result
