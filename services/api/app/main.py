from typing import Annotated, Literal

from fastapi import Depends, FastAPI, Response, status
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_session
from app.deal import Deal, load_deal
from app.models import OnboardingCase

app = FastAPI(title="Oxane onboarding workbench API")

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
