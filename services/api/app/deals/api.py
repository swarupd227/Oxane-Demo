"""HTTP endpoints for new deals, hand-offs and the client portal.

Reads are open to internal personas; writes check the acting persona's role. Uploads and every
endpoint that may call the model also need the demo access code.
"""

import json
from datetime import UTC, date, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from fastapi.responses import Response as RawResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_session
from app.deals import audit, files, handoffs, monitor, onboard, workbook
from app.deals.guard import check_access, check_upload, cost_of, status
from app.deals.models import Client, DealCase, Document, Facility, Submission
from app.personas import ROLES, Persona, acting, all_personas, require

router = APIRouter()
SessionDep = Annotated[Session, Depends(get_session)]
DEAL_TYPES = ("Consumer instalment", "SME loans", "Auto ABS", "Equipment finance",
              "Fund finance", "Other")
DOC_KINDS = ("auto", "agreement", "amendment", "loan_tape", "servicer_report", "client_model",
             "other")
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def invalid(fields: dict[str, str], message: str = "Check the highlighted fields") -> None:
    if fields:
        raise HTTPException(status_code=422, detail={"message": message, "fields": fields})


def _get(db: Session, model: Any, ident: int, what: str) -> Any:
    row = db.get(model, ident)
    if row is None:
        raise HTTPException(status_code=404, detail=f"No such {what}")
    return row


def _internal(request: Request, db: Session) -> Persona | None:
    persona = acting(request, db)
    if persona is not None and persona.role == "client":
        raise HTTPException(status_code=403, detail="Not available to client users")
    return persona


# People, status and access


@router.get("/api/personas")
def get_personas(db: SessionDep) -> dict[str, Any]:
    return {"personas": [p.view() for p in all_personas(db)], "roles": ROLES}


@router.get("/api/deals/status")
def get_status(db: SessionDep) -> dict[str, Any]:
    return status(db)


@router.post("/api/deals/access/check")
def post_access(request: Request) -> dict[str, Any]:
    check_access(request)
    return {"ok": True}


# Hand-offs


@router.get("/api/work")
def get_work(request: Request, db: SessionDep) -> dict[str, Any]:
    persona = require(request, db)
    return handoffs.mine(db, persona)


class Note(BaseModel):
    note: str | None = None


@router.post("/api/work/{item_id}/complete")
def post_complete(item_id: int, body: Note, request: Request, db: SessionDep) -> dict[str, Any]:
    persona = require(request, db)
    handoffs.complete(db, item_id, persona, body.note)
    db.commit()
    return handoffs.mine(db, persona)


@router.get("/api/work/subject")
def get_subject(subject: str, request: Request, db: SessionDep) -> list[dict[str, Any]]:
    _internal(request, db)
    return handoffs.for_subject(db, subject)


# Clients


class ClientBody(BaseModel):
    name: str | None = None
    short_name: str | None = None
    contact_name: str | None = None
    ai_permitted: bool | None = None
    approval_levels: int | None = None
    master_field_overrides: dict[str, str] | None = None
    reason: str | None = None


def client_view(db: Session, client: Client, detail: bool = False) -> dict[str, Any]:
    view = {"id": client.id, "ref": f"CLT-{100 + client.id}", "name": client.name,
            "short_name": client.short_name, "contact_name": client.contact_name,
            "ai_permitted": client.ai_permitted, "approval_levels": client.approval_levels,
            "master_field_overrides": client.master_field_overrides or {},
            "created_at": client.created_at.isoformat(),
            "archived_at": client.archived_at.isoformat() if client.archived_at else None,
            "cases": db.scalar(select(DealCase.id).where(DealCase.client_id == client.id)
                               .limit(1)) is not None}
    if detail:
        from app.deals.models import ClientMapping

        view["case_list"] = [case_summary(db, c) for c in db.scalars(
            select(DealCase).where(DealCase.client_id == client.id).order_by(DealCase.id))]
        view["facility_list"] = [facility_summary(db, f) for f in db.scalars(
            select(Facility).where(Facility.client_id == client.id).order_by(Facility.id))]
        view["mappings"] = [{"signature": m.signature[:12], "headers": m.headers,
                             "columns": m.columns, "updated_at": m.updated_at.isoformat()}
                            for m in db.scalars(select(ClientMapping).where(
                                ClientMapping.client_id == client.id))]
        view["history"] = audit.history(db, client.audit_id)
    return view


def _client_fields(db: Session, body: ClientBody, client: Client | None) -> dict[str, Any]:
    errors: dict[str, str] = {}
    data = body.model_dump(exclude_unset=True, exclude={"reason"})
    name = (data.get("name", client.name if client else "") or "").strip()
    if not name:
        errors["name"] = "Enter the client's legal name"
    elif len(name) > 120:
        errors["name"] = "At most 120 characters"
    else:
        clash = db.scalars(select(Client).where(Client.name.ilike(name),
                                                Client.archived_at.is_(None))).first()
        if clash is not None and (client is None or clash.id != client.id):
            errors["name"] = "A client with this name already exists"
    short = (data.get("short_name", client.short_name if client else "") or "").strip()
    if not short:
        short = name.split()[0] if name else ""
    if len(short) > 40:
        errors["short_name"] = "At most 40 characters"
    levels = data.get("approval_levels", client.approval_levels if client else 2)
    if levels not in (2, 3):
        errors["approval_levels"] = "Two or three approval levels"
    contact = (data.get("contact_name", client.contact_name if client else "") or "").strip()
    if len(contact) > 80:
        errors["contact_name"] = "At most 80 characters"
    overrides = data.get("master_field_overrides",
                         client.master_field_overrides if client else {}) or {}
    from engine.generic import FIELDS

    bad = [k for k in overrides if k not in FIELDS]
    if bad:
        errors["master_field_overrides"] = f"Unknown field: {bad[0]}"
    invalid(errors)
    return {"name": name, "short_name": short, "contact_name": contact,
            "ai_permitted": data.get("ai_permitted", client.ai_permitted if client else True),
            "approval_levels": levels, "master_field_overrides": overrides}


@router.get("/api/deals/clients")
def get_clients(request: Request, db: SessionDep, archived: bool = False
                ) -> list[dict[str, Any]]:
    _internal(request, db)
    query = select(Client).order_by(Client.name)
    if not archived:
        query = query.where(Client.archived_at.is_(None))
    return [client_view(db, c) for c in db.scalars(query)]


@router.post("/api/deals/clients")
def post_client(body: ClientBody, request: Request, db: SessionDep) -> dict[str, Any]:
    persona = require(request, db, "admin")
    values = _client_fields(db, body, None)
    client = Client(**values)
    db.add(client)
    db.flush()
    audit.append(db, client.audit_id, persona.name, "create-client",
                 f"Created client {client.name}: AI "
                 f"{'permitted' if client.ai_permitted else 'not permitted'}, "
                 f"{client.approval_levels} approval levels", {"values": values})
    handoffs.open_item(db, f"client:{client.id}:onboard", f"client:{client.id}",
                       client.audit_id, "work", f"New client {client.name}: open its first case",
                       "onboarding_analyst", f"/clients/{client.id}", persona, sla_hours=72)
    db.commit()
    return client_view(db, client, True)


@router.patch("/api/deals/clients/{client_id}")
def patch_client(client_id: int, body: ClientBody, request: Request, db: SessionDep
                 ) -> dict[str, Any]:
    persona = require(request, db, "admin")
    client = _get(db, Client, client_id, "client")
    if client.archived_at:
        raise HTTPException(status_code=409, detail="This client is archived")
    values = _client_fields(db, body, client)
    changed = {k: v for k, v in values.items() if getattr(client, k) != v}
    if "ai_permitted" in changed and not (body.reason or "").strip():
        invalid({"reason": "Say why the AI permission changes"})
    for key, value in changed.items():
        setattr(client, key, value)
    if changed:
        audit.append(db, client.audit_id, persona.name, "edit-client",
                     "Changed " + ", ".join(k.replace("_", " ") for k in changed),
                     {"values": changed, "reason": body.reason})
    db.commit()
    return client_view(db, client, True)


@router.post("/api/deals/clients/{client_id}/archive")
def archive_client(client_id: int, body: Note, request: Request, db: SessionDep
                   ) -> dict[str, Any]:
    persona = require(request, db, "admin")
    client = _get(db, Client, client_id, "client")
    live = db.scalars(select(Facility).where(Facility.client_id == client.id,
                                             Facility.status == "live")).first()
    if live is not None:
        raise HTTPException(status_code=409, detail=f"{live.name} is live. Archive the facility "
                            "first")
    client.archived_at = datetime.now(UTC)
    audit.append(db, client.audit_id, persona.name, "archive-client",
                 f"Archived client {client.name}", {"reason": body.note})
    db.commit()
    return client_view(db, client, True)


@router.get("/api/deals/clients/{client_id}")
def get_client(client_id: int, request: Request, db: SessionDep) -> dict[str, Any]:
    _internal(request, db)
    return client_view(db, _get(db, Client, client_id, "client"), True)


# Cases


class CaseBody(BaseModel):
    client_id: int | None = None
    facility_name: str | None = None
    deal_type: str | None = None
    commitment: float | None = None


def case_summary(db: Session, case: DealCase) -> dict[str, Any]:
    client = db.get(Client, case.client_id)
    state = case.state or {}
    terms = state.get("terms") or {}
    exceptions = [e for e in state.get("exceptions", []) if e["severity"] != "info"]
    engine = (state.get("validation") or {}).get("engine") or {}
    return {
        "id": case.id, "ref": onboard.case_ref(case), "facility_name": case.facility_name,
        "client": {"id": client.id, "name": client.name, "ai_permitted": client.ai_permitted},
        "deal_type": case.deal_type, "commitment_cents": case.commitment_cents,
        "stage": case.stage, "created_by": case.created_by,
        "created_at": case.created_at.isoformat(),
        "archived_at": case.archived_at.isoformat() if case.archived_at else None,
        "documents": db.query(Document).filter(Document.case_id == case.id,
                                               Document.status == "active").count(),
        "terms": {"approved": sum(t["status"] in ("approved", "absent") for t in terms.values()),
                  "total": len(terms)},
        "exceptions_open": len(onboard.open_exceptions(state)),
        "exceptions_total": len(exceptions),
        "queries_with_client": sum(e["status"] == "with_client" for e in exceptions),
        "pool_cents": engine.get("gross_pool_cents"), "facility_id": case.facility_id,
    }


def doc_view(doc: Document) -> dict[str, Any]:
    return {"id": doc.id, "ref": files.doc_key(doc), "name": doc.name, "kind": doc.kind,
            "kind_source": doc.kind_source, "version": doc.version,
            "effective_date": doc.effective_date.isoformat() if doc.effective_date else None,
            "sha256": doc.sha256, "size": doc.size, "content_type": doc.content_type,
            "status": doc.status, "uploaded_by": doc.uploaded_by,
            "uploaded_at": doc.uploaded_at.isoformat(), "replaces_id": doc.replaces_id}


def _can(persona: Persona | None, case: DealCase, client: Client, db: Session
         ) -> dict[str, str | None]:
    """Each action and, if this persona cannot take it, why not."""
    role = persona.role if persona else None
    state = case.state or {}

    def only(*roles: str) -> str | None:
        if role in roles:
            return None
        return "For the " + " or ".join(ROLES[r].lower() for r in roles)

    preparing = only("onboarding_analyst")
    if state.get("qc", {}).get("status") in ("pending", "passed") or state.get("approved_at"):
        preparing = "The case is with QC or the reviewer"
    ai = None if client.ai_permitted else f"{client.name} does not permit AI"
    qc_role = only("qc")
    if qc_role is None and persona and persona.name in onboard.preparers(db, case):
        qc_role = "You worked on this case"
    review = only("reviewer")
    if review is None and persona and (persona.name in onboard.preparers(db, case)
                                       or persona.name == (state.get("qc") or {})
                                       .get("completed_by")):
        review = "You prepared or checked this case"
    return {"prepare": preparing, "ai": ai, "qc": qc_role, "review": review,
            "expert": only("expert"), "client": only("client")}


def case_view(db: Session, case: DealCase, persona: Persona | None) -> dict[str, Any]:
    client = db.get(Client, case.client_id)
    docs = list(db.scalars(select(Document).where(Document.case_id == case.id)
                           .order_by(Document.id)))
    state = case.state or {}
    return {
        **case_summary(db, case),
        "client": client_view(db, client),
        "state": state,
        "documents_list": [doc_view(d) for d in docs],
        "readiness": onboard.readiness(db, case, state),
        "qc_items": onboard.qc_items(state),
        "cost": cost_of(db, case_id=case.id),
        "history": audit.history(db, case.audit_id),
        "work": handoffs.for_subject(db, onboard.subject(case)),
        "can": _can(persona, case, client, db),
        "stages": list(onboard.STAGES),
    }


def _case(db: Session, case_id: int) -> tuple[DealCase, Client]:
    case = _get(db, DealCase, case_id, "case")
    return case, db.get(Client, case.client_id)


def _writable(case: DealCase) -> None:
    if case.archived_at:
        raise HTTPException(status_code=409, detail="This case is archived")
    state = case.state or {}
    if (state.get("qc") or {}).get("status") in ("pending", "passed") or state.get("approved_at"):
        raise HTTPException(status_code=409, detail="The case is with QC or the reviewer; it "
                            "cannot be changed now")


def _case_fields(body: CaseBody, case: DealCase | None, db: Session) -> dict[str, Any]:
    errors: dict[str, str] = {}
    data = body.model_dump(exclude_unset=True)
    out: dict[str, Any] = {}
    if case is None:
        client = db.get(Client, data.get("client_id") or 0)
        if client is None or client.archived_at:
            errors["client_id"] = "Choose a client"
        out["client_id"] = data.get("client_id")
    name = (data.get("facility_name", case.facility_name if case else "") or "").strip()
    if not name:
        errors["facility_name"] = "Enter the facility name"
    elif len(name) > 120:
        errors["facility_name"] = "At most 120 characters"
    deal_type = data.get("deal_type", case.deal_type if case else None)
    if deal_type not in DEAL_TYPES:
        errors["deal_type"] = "Choose a deal type"
    commitment = data.get("commitment", case.commitment_cents / 100 if case else None)
    if commitment is None or not 0 < commitment <= 10_000_000_000:
        errors["commitment"] = "Enter the commitment in US$, more than zero"
    invalid(errors)
    out.update(facility_name=name, deal_type=deal_type,
               commitment_cents=int(round(float(commitment) * 100)))
    return out


@router.get("/api/deals/cases")
def get_cases(request: Request, db: SessionDep, archived: bool = False) -> list[dict[str, Any]]:
    _internal(request, db)
    query = select(DealCase).order_by(DealCase.id.desc())
    if not archived:
        query = query.where(DealCase.archived_at.is_(None))
    return [case_summary(db, c) for c in db.scalars(query)]


@router.post("/api/deals/cases")
def post_case(body: CaseBody, request: Request, db: SessionDep) -> dict[str, Any]:
    persona = require(request, db, "onboarding_analyst")
    values = _case_fields(body, None, db)
    case = DealCase(**values, stage="documents", state={}, created_by=persona.name)
    db.add(case)
    db.flush()
    client = db.get(Client, case.client_id)
    onboard.log(db, case, persona, "create-case",
                f"Opened {onboard.case_ref(case)} for {client.name}: {case.facility_name}, "
                f"{case.deal_type}, US${case.commitment_cents / 100:,.0f}")
    audit.append(db, client.audit_id, persona.name, "case-opened",
                 f"Opened {onboard.case_ref(case)}: {case.facility_name}")
    handoffs.close_items(db, f"client:{client.id}:onboard", persona)
    onboard.rebuild(db, case, client)
    db.commit()
    return case_view(db, case, persona)


@router.get("/api/deals/cases/{case_id}")
def get_case(case_id: int, request: Request, db: SessionDep) -> dict[str, Any]:
    persona = _internal(request, db)
    case, _ = _case(db, case_id)
    return case_view(db, case, persona)


@router.patch("/api/deals/cases/{case_id}")
def patch_case(case_id: int, body: CaseBody, request: Request, db: SessionDep
               ) -> dict[str, Any]:
    persona = require(request, db, "onboarding_analyst")
    case, client = _case(db, case_id)
    _writable(case)
    values = _case_fields(body, case, db)
    changed = {k: v for k, v in values.items() if getattr(case, k) != v}
    for key, value in changed.items():
        setattr(case, key, value)
    if changed:
        onboard.log(db, case, persona, "edit-case",
                    "Changed " + ", ".join(k.replace("_", " ") for k in changed),
                    {"values": changed})
    db.commit()
    return case_view(db, case, persona)


@router.post("/api/deals/cases/{case_id}/archive")
def archive_case(case_id: int, body: Note, request: Request, db: SessionDep) -> dict[str, Any]:
    persona = require(request, db, "onboarding_analyst", "admin")
    case, _ = _case(db, case_id)
    if case.facility_id:
        raise HTTPException(status_code=409, detail="This case went live; archive the facility")
    if not (body.note or "").strip():
        invalid({"note": "Say why the case is archived"})
    case.archived_at = datetime.now(UTC)
    onboard.log(db, case, persona, "archive-case", "Archived the case", {"reason": body.note})
    handoffs.close_items(db, f"case:{case.id}:", persona, outcome="withdrawn")
    db.commit()
    return case_view(db, case, persona)


def _store(db: Session, request: Request, body: bytes, name: str, kind: str,
           persona: Persona, effective: str | None, **owner: Any) -> Document:
    if kind not in DOC_KINDS:
        invalid({"kind": "Choose the document type"})
    media = check_upload(name, body)
    effective_date = None
    if effective:
        try:
            effective_date = date.fromisoformat(effective)
        except ValueError:
            invalid({"effective_date": "Not a date"})
    import hashlib

    doc = Document(name=name[:200], kind=kind, kind_source="analyst" if kind != "auto" else "",
                   sha256=hashlib.sha256(body).hexdigest(), size=len(body), content_type=media,
                   content=body, status="active", uploaded_by=persona.name,
                   effective_date=effective_date, **owner)
    db.add(doc)
    db.flush()
    return doc


@router.post("/api/deals/cases/{case_id}/documents")
async def post_document(case_id: int, request: Request, db: SessionDep, name: str,
                        kind: str = "auto", effective_date: str | None = None) -> dict[str, Any]:
    check_access(request)
    persona = require(request, db, "onboarding_analyst")
    case, client = _case(db, case_id)
    _writable(case)
    if kind == "auto" and not client.ai_permitted:
        invalid({"kind": f"{client.name} does not permit AI: choose the type"})
    body = await request.body()
    same = db.scalars(select(Document).where(Document.case_id == case.id,
                                             Document.status == "active",
                                             Document.sha256 == __import__("hashlib")
                                             .sha256(body).hexdigest())).first()
    if same is not None:
        invalid({"file": f"This file is already in the case as {same.name}"})
    doc = _store(db, request, body, name, kind, persona, effective_date, case_id=case.id)
    onboard.log(db, case, persona, "upload", f"Uploaded {doc.name} ({doc.size:,} bytes, "
                f"sha256 {doc.sha256[:12]})", {"refs": [files.doc_key(doc)]})
    onboard.rebuild(db, case, client)
    db.commit()
    return case_view(db, case, persona)


@router.post("/api/deals/cases/{case_id}/documents/{doc_id}/replace")
async def replace_document(case_id: int, doc_id: int, request: Request, db: SessionDep,
                           name: str) -> dict[str, Any]:
    check_access(request)
    persona = require(request, db, "onboarding_analyst")
    case, client = _case(db, case_id)
    _writable(case)
    old = _get(db, Document, doc_id, "document")
    if old.case_id != case.id or old.status != "active":
        raise HTTPException(status_code=404, detail="No such document")
    body = await request.body()
    doc = _store(db, request, body, name, old.kind, persona,
                 old.effective_date.isoformat() if old.effective_date else None, case_id=case.id)
    doc.version, doc.replaces_id, doc.kind_source = old.version + 1, old.id, old.kind_source
    old.status = "replaced"
    onboard.log(db, case, persona, "replace", f"Replaced {old.name} v{old.version} with "
                f"{doc.name} v{doc.version}", {"refs": [files.doc_key(doc)]})
    onboard.rebuild(db, case, client)
    db.commit()
    return case_view(db, case, persona)


class DocBody(BaseModel):
    kind: str | None = None
    effective_date: str | None = None


@router.patch("/api/deals/cases/{case_id}/documents/{doc_id}")
def patch_document(case_id: int, doc_id: int, body: DocBody, request: Request, db: SessionDep
                   ) -> dict[str, Any]:
    persona = require(request, db, "onboarding_analyst")
    case, client = _case(db, case_id)
    _writable(case)
    doc = _get(db, Document, doc_id, "document")
    if doc.case_id != case.id:
        raise HTTPException(status_code=404, detail="No such document")
    if body.kind is not None:
        if body.kind not in DOC_KINDS[1:]:
            invalid({"kind": "Choose the document type"})
        doc.kind, doc.kind_source = body.kind, "analyst"
    if body.effective_date is not None:
        try:
            doc.effective_date = date.fromisoformat(body.effective_date) \
                if body.effective_date else None
        except ValueError:
            invalid({"effective_date": "Not a date"})
    onboard.log(db, case, persona, "edit-document", f"Set {doc.name} to {doc.kind}"
                + (f", effective {doc.effective_date}" if doc.effective_date else ""))
    onboard.rebuild(db, case, client)
    db.commit()
    return case_view(db, case, persona)


@router.delete("/api/deals/cases/{case_id}/documents/{doc_id}")
def delete_document(case_id: int, doc_id: int, request: Request, db: SessionDep
                    ) -> dict[str, Any]:
    persona = require(request, db, "onboarding_analyst")
    case, client = _case(db, case_id)
    _writable(case)
    doc = _get(db, Document, doc_id, "document")
    if doc.case_id != case.id or doc.status != "active":
        raise HTTPException(status_code=404, detail="No such document")
    doc.status = "removed"
    onboard.log(db, case, persona, "remove", f"Removed {doc.name} from the case (kept in the "
                "record)", {"refs": [files.doc_key(doc)]})
    onboard.rebuild(db, case, client)
    db.commit()
    return case_view(db, case, persona)


@router.get("/api/deals/documents/{doc_id}/file")
def get_document_file(doc_id: int, request: Request, db: SessionDep) -> RawResponse:
    _internal(request, db)
    doc = _get(db, Document, doc_id, "document")
    return RawResponse(doc.content, media_type=doc.content_type,
                       headers={"Content-Disposition": f'inline; filename="{doc.name}"'})


def _case_step(case_id: int, request: Request, db: Session, model: bool = False
               ) -> tuple[DealCase, Client, Persona]:
    if model:
        check_access(request)
    persona = require(request, db, "onboarding_analyst")
    case, client = _case(db, case_id)
    _writable(case)
    return case, client, persona


@router.post("/api/deals/cases/{case_id}/classify")
def post_classify(case_id: int, request: Request, db: SessionDep) -> dict[str, Any]:
    case, client, persona = _case_step(case_id, request, db, True)
    onboard.classify(db, case, client, persona)
    db.commit()
    return case_view(db, case, persona)


@router.post("/api/deals/cases/{case_id}/extract")
def post_extract(case_id: int, request: Request, db: SessionDep) -> dict[str, Any]:
    case, client, persona = _case_step(case_id, request, db, True)
    onboard.extract(db, case, client, persona)
    db.commit()
    return case_view(db, case, persona)


@router.post("/api/deals/cases/{case_id}/terms/manual")
def post_manual(case_id: int, request: Request, db: SessionDep) -> dict[str, Any]:
    case, client, persona = _case_step(case_id, request, db)
    onboard.manual_terms(db, case, client, persona)
    db.commit()
    return case_view(db, case, persona)


@router.post("/api/deals/cases/{case_id}/terms/approve-verified")
def post_bulk(case_id: int, request: Request, db: SessionDep) -> dict[str, Any]:
    case, client, persona = _case_step(case_id, request, db)
    onboard.approve_verified_terms(db, case, client, persona)
    db.commit()
    return case_view(db, case, persona)


@router.post("/api/deals/cases/{case_id}/terms/{key}")
def post_term(case_id: int, key: str, body: dict[str, Any], request: Request, db: SessionDep
              ) -> dict[str, Any]:
    case, client, persona = _case_step(case_id, request, db)
    onboard.term_action(db, case, client, persona, key, body)
    db.commit()
    return case_view(db, case, persona)


@router.post("/api/deals/cases/{case_id}/rules/draft")
def post_draft_rules(case_id: int, request: Request, db: SessionDep) -> dict[str, Any]:
    case, client, persona = _case_step(case_id, request, db, True)
    onboard.draft_rules(db, case, client, persona)
    db.commit()
    return case_view(db, case, persona)


@router.post("/api/deals/cases/{case_id}/rules")
def post_rules(case_id: int, body: dict[str, Any], request: Request, db: SessionDep
               ) -> dict[str, Any]:
    case, client, persona = _case_step(case_id, request, db)
    onboard.rule_action(db, case, client, persona, body)
    db.commit()
    return case_view(db, case, persona)


@router.post("/api/deals/cases/{case_id}/mapping/suggest")
def post_suggest(case_id: int, request: Request, db: SessionDep) -> dict[str, Any]:
    case, client, persona = _case_step(case_id, request, db, True)
    onboard.suggest_mapping(db, case, client, persona)
    db.commit()
    return case_view(db, case, persona)


@router.post("/api/deals/cases/{case_id}/mapping")
def post_mapping(case_id: int, body: dict[str, Any], request: Request, db: SessionDep
                 ) -> dict[str, Any]:
    case, client, persona = _case_step(case_id, request, db)
    onboard.mapping_action(db, case, client, persona, body)
    db.commit()
    return case_view(db, case, persona)


class ValidateBody(BaseModel):
    as_of: str | None = None


@router.post("/api/deals/cases/{case_id}/validate")
def post_validate(case_id: int, body: ValidateBody, request: Request, db: SessionDep
                  ) -> dict[str, Any]:
    case, client, persona = _case_step(case_id, request, db)
    onboard.validate_case(db, case, client, persona, body.as_of)
    db.commit()
    return case_view(db, case, persona)


@router.post("/api/deals/cases/{case_id}/exceptions/{ref}")
def post_exception(case_id: int, ref: str, body: dict[str, Any], request: Request,
                   db: SessionDep) -> dict[str, Any]:
    case, client, persona = _case_step(case_id, request, db)
    onboard.work_exception(db, case, client, persona, ref, body)
    db.commit()
    return case_view(db, case, persona)


class Answer(BaseModel):
    text: str


@router.post("/api/deals/cases/{case_id}/exceptions/{ref}/decide")
def post_decide(case_id: int, ref: str, body: Answer, request: Request, db: SessionDep
                ) -> dict[str, Any]:
    persona = require(request, db, "expert")
    case, client = _case(db, case_id)
    onboard.answer(db, case, client, persona, ref, body.text, "expert")
    db.commit()
    return case_view(db, case, persona)


@router.post("/api/deals/queries/{case_id}/{ref}/answer")
def post_answer(case_id: int, ref: str, body: Answer, request: Request, db: SessionDep
                ) -> dict[str, Any]:
    persona = require(request, db, "client")
    case, client = _case(db, case_id)
    if persona.client != f"deal:{client.id}":
        raise HTTPException(status_code=404, detail="No such query")
    onboard.answer(db, case, client, persona, ref, body.text, "client")
    db.commit()
    return portal_view(db, persona)


@router.post("/api/deals/cases/{case_id}/submit-qc")
def post_submit_qc(case_id: int, request: Request, db: SessionDep) -> dict[str, Any]:
    case, client, persona = _case_step(case_id, request, db)
    onboard.submit_for_qc(db, case, client, persona)
    db.commit()
    return case_view(db, case, persona)


class QcMark(BaseModel):
    item: str
    result: str
    note: str = ""


@router.post("/api/deals/cases/{case_id}/qc")
def post_qc(case_id: int, body: QcMark, request: Request, db: SessionDep) -> dict[str, Any]:
    persona = require(request, db, "qc")
    case, _ = _case(db, case_id)
    onboard.qc_mark(db, case, persona, body.item, body.result, body.note)
    db.commit()
    return case_view(db, case, persona)


@router.post("/api/deals/cases/{case_id}/qc/complete")
def post_qc_complete(case_id: int, request: Request, db: SessionDep) -> dict[str, Any]:
    persona = require(request, db, "qc")
    case, client = _case(db, case_id)
    onboard.qc_complete(db, case, persona)
    onboard.rebuild(db, case, client)
    db.commit()
    return case_view(db, case, persona)


class Reason(BaseModel):
    reason: str | None = None


@router.post("/api/deals/cases/{case_id}/approve")
def post_approve(case_id: int, body: Reason, request: Request, db: SessionDep) -> dict[str, Any]:
    persona = require(request, db, "reviewer")
    case, _ = _case(db, case_id)
    onboard.approve(db, case, persona, body.reason)
    db.commit()
    return case_view(db, case, persona)


@router.post("/api/deals/cases/{case_id}/return")
def post_return(case_id: int, body: Reason, request: Request, db: SessionDep) -> dict[str, Any]:
    persona = require(request, db, "reviewer")
    case, client = _case(db, case_id)
    onboard.return_case(db, case, persona, body.reason or "")
    onboard.rebuild(db, case, client)
    db.commit()
    return case_view(db, case, persona)


@router.post("/api/deals/cases/{case_id}/go-live")
def post_go_live(case_id: int, request: Request, db: SessionDep) -> dict[str, Any]:
    persona = require(request, db, "reviewer")
    case, client = _case(db, case_id)
    onboard.go_live(db, case, client, persona)
    db.commit()
    return case_view(db, case, persona)


def _load_file(db: Session, case: DealCase) -> dict[str, Any]:
    view = case_view(db, case, None)
    state = case.state
    return {
        "case": view["ref"], "facility": case.facility_name, "client": view["client"]["name"],
        "status": "final" if state.get("approved_at") else "provisional",
        "approved_by": state.get("approved_by"), "approved_at": state.get("approved_at"),
        "terms": state.get("terms"), "ruleset": onboard.ruleset_of(state).model_dump(mode="json"),
        "mapping": state.get("mapping"), "validation": state.get("validation"),
        "exceptions": state.get("exceptions"), "qc": state.get("qc"),
        "audit_head": view["history"]["entries"][0]["hash"] if view["history"]["entries"]
        else None,
    }


@router.get("/api/deals/cases/{case_id}/load-file.json")
def get_load_file(case_id: int, request: Request, db: SessionDep) -> JSONResponse:
    _internal(request, db)
    case, _ = _case(db, case_id)
    if not (case.state or {}).get("approved_at"):
        raise HTTPException(status_code=409, detail="The load file is available after "
                            "second-analyst approval")
    return JSONResponse(json.loads(json.dumps(_load_file(db, case), default=str)), headers={
        "Content-Disposition": f'attachment; filename="{onboard.case_ref(case)}-load-file.json"'})


@router.get("/api/deals/cases/{case_id}/configuration.xlsx")
def get_configuration(case_id: int, request: Request, db: SessionDep) -> RawResponse:
    _internal(request, db)
    case, _ = _case(db, case_id)
    if not (case.state or {}).get("rules"):
        raise HTTPException(status_code=409, detail="Draft the rules first")
    final = bool((case.state or {}).get("approved_at"))
    content = workbook.configuration(case_view(db, case, None), final)
    word = "final" if final else "provisional"
    return RawResponse(content, media_type=XLSX, headers={
        "Content-Disposition":
            f'attachment; filename="{onboard.case_ref(case)}-configuration-{word}.xlsx"'})


# Facilities and monthly submissions


def facility_summary(db: Session, facility: Facility) -> dict[str, Any]:
    client = db.get(Client, facility.client_id)
    subs = list(db.scalars(select(Submission).where(Submission.facility_id == facility.id)
                           .order_by(Submission.period)))
    latest = next((s for s in reversed(subs) if s.status != "expected"), None)
    tests = (latest.state.get("tests") if latest else None) or {}
    return {
        "id": facility.id, "ref": monitor.fac_ref(facility), "name": facility.name,
        "client": {"id": client.id, "name": client.name, "ai_permitted": client.ai_permitted,
                   "approval_levels": client.approval_levels},
        "deal_type": facility.deal_type, "commitment_cents": facility.commitment_cents,
        "status": facility.status, "case_id": facility.case_id,
        "live_at": facility.live_at.isoformat() if facility.live_at else None,
        "reporting_day": facility.config.get("reporting_day"),
        "submissions": [{"id": s.id, "ref": monitor.sub_ref(s), "period": s.period,
                         "period_end": s.period_end.isoformat(), "due_date": s.due_date.isoformat(),
                         "status": s.status} for s in subs],
        "latest": {"period": latest.period, "status": latest.status,
                   "borrowing_base_cents": tests.get("borrowing_base_cents"),
                   "delinquency_average": tests.get("delinquency_average"),
                   "delinquency_limit": tests.get("delinquency_limit"),
                   "breached": bool(tests.get("delinquency_breached")),
                   "warning": bool(tests.get("delinquency_warning")),
                   "open": sum(1 for f in latest.state.get("findings", [])
                               if not f.get("decision"))} if latest else None,
    }


@router.get("/api/deals/facilities")
def get_facilities(request: Request, db: SessionDep) -> list[dict[str, Any]]:
    _internal(request, db)
    return [facility_summary(db, f) for f in db.scalars(
        select(Facility).where(Facility.archived_at.is_(None)).order_by(Facility.id))]


@router.get("/api/deals/facilities/{facility_id}")
def get_facility(facility_id: int, request: Request, db: SessionDep) -> dict[str, Any]:
    _internal(request, db)
    facility = _get(db, Facility, facility_id, "facility")
    case = db.get(DealCase, facility.case_id) if facility.case_id else None
    return {**facility_summary(db, facility), "config": facility.config,
            "case_ref": onboard.case_ref(case) if case else None,
            "history": audit.history(db, facility.audit_id),
            "work": handoffs.for_subject(db, f"facility:{facility.id}")}


class FacilityBody(BaseModel):
    name: str | None = None
    commitment: float | None = None
    reporting_day: int | None = None
    reason: str | None = None


@router.patch("/api/deals/facilities/{facility_id}")
def patch_facility(facility_id: int, body: FacilityBody, request: Request, db: SessionDep
                   ) -> dict[str, Any]:
    persona = require(request, db, "monitoring_analyst", "admin")
    facility = _get(db, Facility, facility_id, "facility")
    errors: dict[str, str] = {}
    changes = []
    if body.name is not None:
        if not body.name.strip() or len(body.name) > 120:
            errors["name"] = "Enter a name of at most 120 characters"
        elif body.name.strip() != facility.name:
            changes.append(f"name to {body.name.strip()}")
    if body.commitment is not None and not 0 < body.commitment <= 10_000_000_000:
        errors["commitment"] = "Enter the commitment in US$, more than zero"
    if body.reporting_day is not None and not 1 <= body.reporting_day <= 28:
        errors["reporting_day"] = "A day from 1 to 28"
    if not (body.reason or "").strip():
        errors["reason"] = "Say why the facility record changes"
    invalid(errors)
    if body.name is not None:
        facility.name = body.name.strip()
    if body.commitment is not None and int(body.commitment * 100) != facility.commitment_cents:
        changes.append(f"commitment to US${body.commitment:,.0f}")
        facility.commitment_cents = int(round(body.commitment * 100))
        config = dict(facility.config)
        config["ruleset"] = {**config["ruleset"], "facility_limit_cents":
                             facility.commitment_cents}
        facility.config = config
    if body.reporting_day is not None and body.reporting_day != facility.config.get(
            "reporting_day"):
        changes.append(f"reporting day to {body.reporting_day}")
        facility.config = {**facility.config, "reporting_day": body.reporting_day}
        for sub in db.scalars(select(Submission).where(Submission.facility_id == facility.id,
                                                       Submission.status == "expected")):
            sub.due_date = onboard.due_date(sub.period_end, body.reporting_day)
    if changes:
        audit.append(db, facility.audit_id, persona.name, "edit-facility",
                     "Changed " + ", ".join(changes), {"reason": body.reason})
    db.commit()
    return get_facility(facility_id, request, db)


@router.post("/api/deals/facilities/{facility_id}/archive")
def archive_facility(facility_id: int, body: Note, request: Request, db: SessionDep
                     ) -> dict[str, Any]:
    persona = require(request, db, "admin")
    facility = _get(db, Facility, facility_id, "facility")
    if not (body.note or "").strip():
        invalid({"note": "Say why"})
    facility.status, facility.archived_at = "archived", datetime.now(UTC)
    audit.append(db, facility.audit_id, persona.name, "archive-facility",
                 "Archived the facility", {"reason": body.note})
    db.commit()
    return facility_summary(db, facility)


def sub_view(db: Session, sub: Submission, persona: Persona | None) -> dict[str, Any]:
    facility = db.get(Facility, sub.facility_id)
    client = db.get(Client, facility.client_id)
    docs = list(db.scalars(select(Document).where(Document.submission_id == sub.id)
                           .order_by(Document.id)))
    state = sub.state or {}
    role = persona.role if persona else None
    report = state.get("report") or {}
    levels = monitor.levels_for(client)
    next_level = levels[len(report.get("approvals", []))] if report and len(
        report.get("approvals", [])) < len(levels) else None
    return {
        "id": sub.id, "ref": monitor.sub_ref(sub), "period": sub.period,
        "period_label": monitor.period_label(sub.period),
        "period_end": sub.period_end.isoformat(), "due_date": sub.due_date.isoformat(),
        "status": sub.status, "state": state,
        "facility": facility_summary(db, facility),
        "documents": [doc_view(d) for d in docs],
        "levels": levels, "next_level": next_level,
        "cost": cost_of(db, submission_id=sub.id),
        "history": audit.history(db, sub.audit_id),
        "work": handoffs.for_subject(db, monitor.subject(sub)),
        "can": {
            "prepare": None if role == "monitoring_analyst" else "For the monitoring analyst",
            "ai": None if client.ai_permitted else f"{client.name} does not permit AI",
            "approve": None if next_level and role == next_level["role"] else (
                f"Level {next_level['level']} is for the {next_level['title'].lower()}"
                if next_level else "Nothing to approve"),
            "expert": None if role == "expert" else "For the credit expert",
        },
    }


def _sub(db: Session, sub_id: int) -> tuple[Submission, Facility, Client]:
    sub = _get(db, Submission, sub_id, "submission")
    facility = db.get(Facility, sub.facility_id)
    return sub, facility, db.get(Client, facility.client_id)


def _sub_step(sub_id: int, request: Request, db: Session, model: bool = False
              ) -> tuple[Submission, Facility, Client, Persona]:
    if model:
        check_access(request)
    persona = require(request, db, "monitoring_analyst")
    sub, facility, client = _sub(db, sub_id)
    if sub.status == "released":
        raise HTTPException(status_code=409, detail="This month's report is released")
    if facility.status != "live":
        raise HTTPException(status_code=409, detail="The facility is not live")
    return sub, facility, client, persona


@router.get("/api/deals/submissions/{sub_id}")
def get_submission(sub_id: int, request: Request, db: SessionDep) -> dict[str, Any]:
    persona = _internal(request, db)
    sub, _, _ = _sub(db, sub_id)
    return sub_view(db, sub, persona)


@router.post("/api/deals/submissions/{sub_id}/documents")
async def post_sub_document(sub_id: int, request: Request, db: SessionDep, name: str,
                            kind: str = "loan_tape") -> dict[str, Any]:
    check_access(request)
    sub, facility, client, persona = _sub_step(sub_id, request, db)
    if kind not in ("loan_tape", "servicer_report", "other"):
        invalid({"kind": "A loan tape, servicer report or other file"})
    body = await request.body()
    for old in db.scalars(select(Document).where(Document.submission_id == sub.id,
                                                 Document.kind == kind,
                                                 Document.status == "active")):
        if kind != "other":
            old.status = "replaced"
    doc = _store(db, request, body, name, kind, persona, sub.period_end.isoformat(),
                 submission_id=sub.id)
    monitor.receive(db, sub, persona)
    state = dict(sub.state or {})
    if kind == "loan_tape":
        state.pop("mapping", None)
    if kind == "servicer_report":
        state.pop("report_figures", None)
    sub.state = state
    monitor.log(db, sub, persona, "upload", f"Received {doc.name} by upload "
                f"(sha256 {doc.sha256[:12]})", {"refs": [files.doc_key(doc)]})
    db.commit()
    return sub_view(db, sub, persona)


@router.post("/api/deals/submissions/{sub_id}/map")
def post_sub_map(sub_id: int, request: Request, db: SessionDep) -> dict[str, Any]:
    sub, facility, client, persona = _sub_step(sub_id, request, db, True)
    monitor.map_tape(db, sub, facility, client, persona)
    db.commit()
    return sub_view(db, sub, persona)


@router.post("/api/deals/submissions/{sub_id}/mapping")
def post_sub_mapping(sub_id: int, body: dict[str, Any], request: Request, db: SessionDep
                     ) -> dict[str, Any]:
    sub, facility, client, persona = _sub_step(sub_id, request, db)
    monitor.confirm(db, sub, client, persona, body)
    db.commit()
    return sub_view(db, sub, persona)


@router.post("/api/deals/submissions/{sub_id}/figures")
def post_figure(sub_id: int, body: dict[str, Any], request: Request, db: SessionDep
                ) -> dict[str, Any]:
    sub, facility, client, persona = _sub_step(sub_id, request, db)
    monitor.enter_figure(db, sub, persona, body)
    db.commit()
    return sub_view(db, sub, persona)


@router.post("/api/deals/submissions/{sub_id}/process")
def post_process(sub_id: int, request: Request, db: SessionDep) -> dict[str, Any]:
    sub, facility, client, persona = _sub_step(sub_id, request, db, True)
    monitor.process(db, sub, facility, client, persona)
    db.commit()
    return sub_view(db, sub, persona)


class Triage(BaseModel):
    outcome: str
    note: str = ""


@router.post("/api/deals/submissions/{sub_id}/triage/{ref}")
def post_triage(sub_id: int, ref: str, body: Triage, request: Request, db: SessionDep
                ) -> dict[str, Any]:
    sub, facility, client, persona = _sub_step(sub_id, request, db)
    monitor.triage(db, sub, facility, persona, ref, body.outcome, body.note)
    if body.outcome in ("confirmed", "logged") and ref.split("-")[0] == "EXC":
        held = (sub.state.get("validation") or {}).get("held")
        if held:
            monitor.process(db, sub, facility, client, persona)
    db.commit()
    return sub_view(db, sub, persona)


@router.post("/api/deals/submissions/{sub_id}/expert/{ref}")
def post_sub_expert(sub_id: int, ref: str, body: Answer, request: Request, db: SessionDep
                    ) -> dict[str, Any]:
    persona = require(request, db, "expert")
    sub, facility, _ = _sub(db, sub_id)
    monitor.expert_decide(db, sub, facility, persona, ref, body.text)
    db.commit()
    return sub_view(db, sub, persona)


@router.post("/api/deals/submissions/{sub_id}/report/draft")
def post_draft_report(sub_id: int, request: Request, db: SessionDep) -> dict[str, Any]:
    sub, facility, client, persona = _sub_step(sub_id, request, db, client_ai(db, sub_id))
    monitor.draft_report(db, sub, client, persona)
    db.commit()
    return sub_view(db, sub, persona)


def client_ai(db: Session, sub_id: int) -> bool:
    sub = db.get(Submission, sub_id)
    if sub is None:
        return False
    facility = db.get(Facility, sub.facility_id)
    return bool(db.get(Client, facility.client_id).ai_permitted)


@router.post("/api/deals/submissions/{sub_id}/approve")
def post_sub_approve(sub_id: int, request: Request, db: SessionDep) -> dict[str, Any]:
    persona = require(request, db, "monitoring_analyst", "reviewer", "head")
    sub, facility, client = _sub(db, sub_id)
    monitor.approve(db, sub, facility, client, persona)
    db.commit()
    return sub_view(db, sub, persona)


@router.get("/api/deals/submissions/{sub_id}/report.xlsx")
def get_report(sub_id: int, request: Request, db: SessionDep) -> RawResponse:
    persona = acting(request, db)
    sub, facility, client = _sub(db, sub_id)
    released = bool((sub.state.get("report") or {}).get("released_at"))
    if persona is not None and persona.role == "client" and (
            not released or persona.client != f"deal:{client.id}"):
        raise HTTPException(status_code=404, detail="No released report")
    if not (sub.state.get("validation") or {}).get("engine"):
        raise HTTPException(status_code=409, detail="Run the month first")
    tape = db.get(Document, sub.state["mapping"]["tape_doc"])
    content = workbook.lender_report(
        {"name": facility.name, "commitment_cents": facility.commitment_cents},
        {"period": sub.period, "state": sub.state, "tape_name": tape.name})
    word = "released" if released else "provisional"
    return RawResponse(content, media_type=XLSX, headers={
        "Content-Disposition":
            f'attachment; filename="{monitor.fac_ref(facility)}-{sub.period}-{word}.xlsx"'})


# The client portal: what a lender contact may see


def portal_view(db: Session, persona: Persona) -> dict[str, Any]:
    queries, reports = [], []
    if persona.client and persona.client.startswith("deal:"):
        client_id = int(persona.client.split(":", 1)[1])
        client = db.get(Client, client_id)
        for case in db.scalars(select(DealCase).where(DealCase.client_id == client_id)):
            for item in (case.state or {}).get("exceptions", []):
                if item.get("query"):
                    queries.append({
                        "case_id": case.id, "case": onboard.case_ref(case),
                        "facility": case.facility_name, "ref": item["ref"],
                        "title": item["title"], "question": item["query"]["text"],
                        "asked_by": item["query"]["by"], "asked_at": item["query"]["sent_at"],
                        "answer": (item.get("answer") or {}).get("text"),
                        "status": "waiting" if item["status"] == "with_client" else "answered",
                        "scripted": False})
        for facility in db.scalars(select(Facility).where(Facility.client_id == client_id)):
            for sub in db.scalars(select(Submission).where(Submission.facility_id == facility.id,
                                                           Submission.status == "released")):
                report = sub.state.get("report") or {}
                reports.append({"facility": facility.name, "period": sub.period,
                                "released_at": report.get("released_at"),
                                "text": report.get("text", []),
                                "download": f"/api/deals/submissions/{sub.id}/report.xlsx",
                                "scripted": False})
        name = client.name if client else ""
    else:
        name = {"calderwood": "Calderwood Bank plc", "thornbury": "Thornbury Bank N.A."}.get(
            persona.client or "", "")
        from app.main import scripted_portal

        scripted = scripted_portal(db, persona.client or "")
        queries += scripted["queries"]
        reports += scripted["reports"]
        return {"persona": persona.view(), "client_name": name, "queries": queries,
                "reports": reports, "brief": scripted["brief"], "alerts": scripted["alerts"],
                "work": handoffs.mine(db, persona)["waiting"]}
    return {"persona": persona.view(), "client_name": name, "queries": queries,
            "reports": reports, "brief": None, "alerts": [],
            "work": handoffs.mine(db, persona)["waiting"]}


@router.get("/api/portal")
def get_portal(request: Request, db: SessionDep) -> dict[str, Any]:
    persona = require(request, db, "client")
    return portal_view(db, persona)


__all__ = ["router", "Query"]
