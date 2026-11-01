import json
import threading
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from decimal import Decimal
from typing import Annotated, Any, Literal

from fastapi import Depends, FastAPI, HTTPException, Response, status
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app import session as case_session
from app.config import settings
from app.db import get_session
from app.deal import Deal, load_deal
from app.engine_service import active_files, pack_path, rule_preview, validation_run
from app.models import OnboardingCase
from app.scoring import scorecard
from app.seed import workbench


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    # Build the seed in the background, so the first page load on stage is instant.
    threading.Thread(target=workbench, daemon=True).start()
    yield


app = FastAPI(title="Oxane onboarding workbench API", lifespan=lifespan)

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


@app.get("/api/session")
def get_session_state(session: SessionDep) -> dict[str, Any]:
    return case_session.view(session, current_workbench())


class SessionEvent(BaseModel):
    type: str
    actor: str
    payload: dict[str, Any] = {}


@app.post("/api/session/events")
def post_event(event: SessionEvent, session: SessionDep) -> dict[str, Any]:
    run = current_workbench()
    try:
        case_session.record(session, run, event.actor, event.type, event.payload)
    except case_session.Refused as refused:
        raise HTTPException(status_code=409, detail=str(refused)) from refused
    return case_session.view(session, run)


@app.post("/api/session/reset")
def post_reset(session: SessionDep) -> dict[str, Any]:
    case_session.reset(session)
    return case_session.view(session, current_workbench())


@app.get("/api/load-file")
def get_load_file(session: SessionDep) -> JSONResponse:
    run = current_workbench()
    state = case_session.view(session, run)
    if not state["approvedAt"]:
        raise HTTPException(status_code=409, detail="The load file needs a second analyst first")
    result = validation_run(state["dealerMatched"])
    edits = state["termEdits"]
    return JSONResponse(
        {
            "note": "Demo layout, not a Panorama format. All data is synthetic.",
            "case": load_deal().case.number,
            "approved_at": state["approvedAt"],
            "prepared_by": case_session.ACTOR_NAMES[case_session.ANALYST],
            "approved_by": case_session.ACTOR_NAMES[state["approvedBy"]],
            "run_digest": result["digest"],
            "provisional": result["provisional"],
            "audit_chain_head": state["chainHead"],
            "open_items": state["openItems"],
            "terms": [
                {"name": term["name"], "tier": term["tier"], "clause": term["clause"],
                 "value": edits.get(term["name"], term["value"]),
                 "edited": term["name"] in edits}
                for term in run["terms"]
            ],
            "borrowing_base": result["system"],
        },
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
        raise HTTPException(status_code=404, detail="Not in the pack")
    return FileResponse(pack_path(file_name))


class RunRequest(BaseModel):
    dealer_match: bool = False


@app.post("/api/run")
def post_run(request: RunRequest) -> dict[str, Any]:
    return validation_run(request.dealer_match)


class PreviewRequest(BaseModel):
    rule_id: str
    value: Decimal


@app.post("/api/rules/preview")
def post_preview(request: PreviewRequest) -> dict[str, Any]:
    try:
        return rule_preview(request.rule_id, request.value)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
