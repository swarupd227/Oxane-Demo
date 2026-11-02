import hashlib
import json
import threading
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from decimal import Decimal
from typing import Annotated, Any, Literal

from fastapi import Depends, FastAPI, HTTPException, Request, Response, status
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app import session as case_session
from app.config import settings
from app.db import get_session
from app.deal import Deal, load_deal
from app.engine_service import (
    active_files,
    pack_digests,
    pack_path,
    rule_preview,
    validation_run,
)
from app.load_file import build_load_file
from app.models import OnboardingCase
from app.pipeline import ontology
from app.scoring import scorecard
from app.seed import workbench


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    # Build the seed in the background, so the first page load on stage is instant.
    threading.Thread(target=workbench, daemon=True).start()
    yield


# The API description is for local work. It is not part of the signed-in product.
app = FastAPI(
    title="Onboarding workbench API",
    lifespan=lifespan,
    docs_url=None if settings.auth_required else "/docs",
    redoc_url=None,
    openapi_url=None if settings.auth_required else "/openapi.json",
)
PRINCIPAL_HEADER = "x-ms-client-principal-name"


def signed_in_user(request: Request) -> str | None:
    """The platform sets this header after sign-in, and strips any copy a client sends."""
    return request.headers.get(PRINCIPAL_HEADER)


@app.middleware("http")
async def require_sign_in(request: Request, call_next: Any) -> Any:
    open_path = request.url.path == "/api/health" or not request.url.path.startswith("/api")
    if settings.auth_required and not open_path and not signed_in_user(request):
        return JSONResponse({"detail": "Sign-in required"}, status_code=401)
    return await call_next(request)

SessionDep = Annotated[Session, Depends(get_session)]


class Health(BaseModel):
    status: Literal["ok", "degraded"]
    database: Literal["ok", "unavailable"]


class CaseView(BaseModel):
    number: str
    status: str
    llm_mode: str
    deal: Deal


@app.get("/api/health")
def health(session: SessionDep, response: Response) -> Health:
    try:
        session.execute(text("select 1"))
    except SQLAlchemyError:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return Health(status="degraded", database="unavailable")
    return Health(status="ok", database="ok")


@app.get("/api/case")
def get_case(session: SessionDep) -> CaseView:
    deal = load_deal()
    case = session.get(OnboardingCase, deal.case.number)
    if case is None:
        case = OnboardingCase(number=deal.case.number)
        session.add(case)
        session.commit()
    return CaseView(
        number=case.number, status=case.status, llm_mode=settings.llm_mode, deal=deal
    )


def current_workbench() -> dict[str, Any]:
    recorded = settings.pipeline_dir / "workbench.json"
    if recorded.exists():
        return json.loads(recorded.read_text(encoding="utf-8"))
    return workbench()


@app.get("/api/workbench")
def get_workbench() -> dict[str, Any]:
    return current_workbench()


@app.get("/api/ontology")
def get_ontology() -> dict[str, Any]:
    return {"version": ontology.version(),
            "concepts": [ontology.view(cid) for cid in ontology.concepts()]}


@app.get("/api/me")
def get_me(request: Request) -> dict[str, Any]:
    user = signed_in_user(request) if settings.auth_required else None
    return {"signed_in": bool(user), "user": user,
            "role": settings.role_of(user) if user else None}


@app.get("/api/session")
def get_session_state(session: SessionDep) -> dict[str, Any]:
    return case_session.view(session, current_workbench())


class SessionEvent(BaseModel):
    type: str
    actor: str
    payload: dict[str, Any] = {}


@app.post("/api/session/events")
def post_event(event: SessionEvent, request: Request, session: SessionDep) -> dict[str, Any]:
    run = current_workbench()
    actor, payload = event.actor, dict(event.payload)
    if settings.auth_required:
        user = signed_in_user(request) or ""
        actor = settings.role_of(user) or "unassigned"
        payload["user"] = user
    try:
        case_session.record(session, run, actor, event.type, payload)
    except case_session.Refused as refused:
        raise HTTPException(status_code=409, detail=str(refused)) from refused
    return case_session.view(session, run)


@app.post("/api/session/reset")
def post_reset(request: Request, session: SessionDep) -> dict[str, Any]:
    if settings.auth_required and not settings.role_of(signed_in_user(request) or ""):
        raise HTTPException(status_code=403, detail="User not recognised")
    case_session.reset(session)
    return case_session.view(session, current_workbench())


@app.get("/api/load-file")
def get_load_file(session: SessionDep) -> JSONResponse:
    run = current_workbench()
    state = case_session.view(session, run)
    if not state["approvedAt"]:
        raise HTTPException(status_code=409,
                            detail="The load file is available after second-analyst approval")
    return JSONResponse(
        build_load_file(run, state),
        headers={"Content-Disposition": 'attachment; filename="case-0412-load-file.json"'},
    )


@app.get("/api/scorecard")
def get_scorecard(session: SessionDep) -> dict[str, Any]:
    run = current_workbench()
    return scorecard(run, case_session.view(session, run))


@app.get("/api/pack/{file_name}")
def get_pack_file(file_name: str) -> FileResponse:
    # Only names from the pack list are served, so a path can never escape the folder.
    if file_name not in active_files():
        raise HTTPException(status_code=404, detail="File not in the document pack")
    return FileResponse(pack_path(file_name))


class RunRequest(BaseModel):
    dealer_match: bool = False


@app.post("/api/run")
def post_run(request: RunRequest, session: SessionDep) -> dict[str, Any]:
    # An approved rule change applies to every run from then on.
    edit = case_session.view(session, current_workbench())["ruleEdit"]
    approved = edit and edit["status"] == "approved"
    override = (edit["rule_id"], Decimal(str(edit["to"]))) if approved else None
    return validation_run(request.dealer_match, override)


@app.post("/api/intake/verify")
async def post_verify(request: Request, name: str) -> dict[str, Any]:
    """Check one uploaded file against the pack by content. A renamed file still matches."""
    body = await request.body()
    match = pack_digests().get(hashlib.sha256(body).hexdigest())
    return {"name": name, "recognised": match is not None, "file": match}


class PreviewRequest(BaseModel):
    rule_id: str
    value: Decimal


@app.post("/api/rules/preview")
def post_preview(request: PreviewRequest) -> dict[str, Any]:
    try:
        return rule_preview(request.rule_id, request.value)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


if settings.static_dir:
    root = settings.static_dir.resolve()

    @app.get("/{path:path}", include_in_schema=False)
    def serve_workbench(path: str) -> FileResponse:
        """Serve built files, and hand every other path to the single-page app."""
        if path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Not found")
        target = (root / path).resolve()
        if path and target.is_relative_to(root) and target.is_file():
            return FileResponse(target)
        return FileResponse(root / "index.html")
