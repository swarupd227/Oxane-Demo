from datetime import date
from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import BaseModel

from app.config import settings


class CaseConfig(BaseModel):
    number: str
    target_go_live: date | None


class Lender(BaseModel):
    name: str
    short_name: str
    desk: str


class Borrower(BaseModel):
    name: str
    short_name: str
    parent: str
    description: str


class Facility(BaseModel):
    type: str
    short_type: str
    limit_usd: int
    collateral: str
    first_tape_loans: int


class Pricing(BaseModel):
    margin: str
    unused_fee: str


class KeyDate(BaseModel):
    label: str
    date: date


class OxaneRole(BaseModel):
    title: str
    summary: str


class Analysts(BaseModel):
    preparer: str
    approver: str


class Deal(BaseModel):
    case: CaseConfig
    lender: Lender
    borrower: Borrower
    facility: Facility
    pricing: Pricing
    dates: list[KeyDate]
    oxane_role: OxaneRole
    analysts: Analysts


def parse_deal(path: Path) -> Deal:
    return Deal.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))


@lru_cache
def load_deal() -> Deal:
    return parse_deal(settings.deal_file)
