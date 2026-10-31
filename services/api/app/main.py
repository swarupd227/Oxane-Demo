import threading
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from decimal import Decimal
from typing import Annotated, Any, Literal

from fastapi import Depends, FastAPI, HTTPException, Response, status
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_session
from app.deal import Deal, load_deal
from app.engine_service import pack_path, read_key, rule_preview, validation_run
from app.models import OnboardingCase
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


@app.get("/api/workbench")
def get_workbench() -> dict[str, Any]:
    return workbench()


@app.get("/api/pack/{file_name}")
def get_pack_file(file_name: str) -> FileResponse:
    # Only names from the pack list are served, so a path can never escape the folder.
    if file_name not in read_key("pack").values():
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
