"""The onboarding pipeline: every case the team has open or has taken live.

The deal kit generates the other cases at summary level (deal-kit/output/casework/pipeline).
Case 0412 and its backbook deals come from the live session and the casework run, so their
stage and counts move as the analyst works. Every count and total here is worked out by code.
"""

import json
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.config import settings
from app.deal import load_deal

PIPELINE_FILE = Path("casework/pipeline/cases.json")
OWNER = {"initials": "OA", "name": "Onboarding analyst"}


def _path() -> Path:
    return settings.deal_kit_output / PIPELINE_FILE


@lru_cache(maxsize=2)
def _load(_: float) -> dict[str, Any]:
    return json.loads(_path().read_text(encoding="utf-8"))


def generated() -> dict[str, Any]:
    path = _path()
    if not path.exists():
        raise FileNotFoundError("Build the deal kit: python -m dealkit.build")
    return _load(path.stat().st_mtime)


def business_days(start: date, end: date) -> int:
    days, cursor = 0, start
    while cursor < end:
        if cursor.weekday() < 5:
            days += 1
        cursor = date.fromordinal(cursor.toordinal() + 1)
    return days


def stage_of(state: dict[str, Any], casework: dict[str, Any] | None) -> str:
    if not state["intakeDone"]:
        return "Intake"
    ready = state["readiness"]
    if not (ready["tier1_approved"] and ready["mapping_accepted"] and ready["run_complete"]):
        return "Interpretation"
    if not state["approvedAt"]:
        return "Clarification"
    if casework and casework["qc"]["status"] != "released":
        return "QC"
    return "Live"


def _active(workbench: dict[str, Any], state: dict[str, Any],
            casework: dict[str, Any] | None, as_of: date) -> dict[str, Any]:
    deal = load_deal()
    items = [*workbench["exceptions"], *state["heldItems"]]
    approved = sum(1 for term in workbench["terms"]
                   if state["termApprovals"].get(term["name"]) == "approved")
    tracker = casework["tracker"] if casework else None
    received = (tracker["pack_received"] if tracker else None) or as_of.isoformat()
    opened = date.fromisoformat(received[:10])
    pool = None
    if casework and state["intakeDone"]:
        pool = next((line["platform"] for line in casework["qc"]["lines"]
                     if line["line"].startswith("Aggregate outstanding balance")), None)
    stage = stage_of(state, casework)
    clock = tracker["clock"] if tracker else None
    return {
        "number": deal.case.number,
        "client": deal.lender.name,
        "facility": deal.borrower.name,
        "deal_type": "Auto ABF",
        "stage": stage,
        "limit_usd": deal.facility.limit_usd,
        "owner": OWNER["initials"],
        "opened": opened.isoformat(),
        "stage_entered": None,
        "went_live": None,
        "target_go_live": deal.case.target_go_live,
        "business_days_open": business_days(opened, as_of),
        "business_days_in_stage": None,
        "records": deal.facility.first_tape_loans,
        "pool_balance": pool,
        "documents": {
            "expected": len(workbench["documents"]) + len(workbench["missing_documents"]),
            "received": len(workbench["documents"]) if state["intakeDone"] else 0,
        },
        "terms": {
            "total": len(workbench["terms"]),
            "extracted": (sum(1 for term in workbench["terms"] if term["status"] != "missing")
                          if state["intakeDone"] else 0),
            "approved": approved,
        },
        "rules": len(workbench["rules"]),
        "exceptions": {
            "total": len(items) if state["intakeDone"] else 0,
            "open": (sum(1 for item in items if item["id"] not in state["exceptions"])
                     if state["intakeDone"] else 0),
        },
        "queries": {
            "total": len(tracker["queries"]) if tracker and state["intakeDone"] else 0,
            "with_client": tracker["open_with_client"] if tracker and state["intakeDone"] else 0,
        },
        "qc_variances_open": (len(casework["qc"]["open"])
                              if casework and state["intakeDone"] else 0),
        "last_activity": clock if state["audit"] else received,
        "active": True,
        "parent": None,
    }


def _backbook(casework: dict[str, Any], numbers: dict[str, Any], client: str,
              as_of: date) -> list[dict[str, Any]]:
    rows = []
    for deal in casework["backbook"]:
        meta = numbers.get(deal["id"])
        if not meta:
            continue
        opened = date.fromisoformat(meta["opened"])
        stage = "Live" if deal["loaded"] else ("Clarification" if deal["exceptions"] else "QC")
        rows.append({
            "number": meta["number"], "client": client, "facility": deal["name"],
            "deal_type": "Auto ABF", "stage": stage, "limit_usd": None,
            "owner": OWNER["initials"], "opened": opened.isoformat(), "stage_entered": None,
            "went_live": None, "target_go_live": None,
            "business_days_open": business_days(opened, as_of), "business_days_in_stage": None,
            "records": deal["rows"], "pool_balance": deal["pool_balance"],
            "documents": {"expected": 1, "received": 1},
            "terms": {"total": 0, "extracted": 0, "approved": 0}, "rules": 0,
            "exceptions": {"total": deal["exceptions"],
                           "open": 0 if deal["loaded"] else deal["exceptions"]},
            "queries": {"total": 0, "with_client": 0}, "qc_variances_open": 0,
            "last_activity": meta["opened"] + "T10:00:00", "active": False,
            "parent": "0412", "backbook": deal["id"], "file": deal["file"],
            "columns": {"matched": deal["matched"], "total": deal["columns"]},
        })
    return rows


def pipeline(workbench: dict[str, Any], state: dict[str, Any],
             casework: dict[str, Any] | None) -> dict[str, Any]:
    kit = generated()
    as_of = date.fromisoformat(kit["as_of"])
    team = [*kit["team"], OWNER]
    active = _active(workbench, state, casework, as_of)
    others = [{**case, "active": False, "parent": None} for case in kit["cases"]]
    backbook = _backbook(casework, kit["backbook"], active["client"], as_of) if casework else []
    cases = sorted([active, *backbook, *others], key=lambda case: case["number"], reverse=True)
    stages = kit["stages"]
    return {
        "as_of": kit["as_of"],
        "stages": stages,
        "team": team,
        "cases": cases,
        "summary": {
            "cases": len(cases),
            "by_stage": {stage: sum(1 for case in cases if case["stage"] == stage)
                         for stage in stages},
            "clients": len({case["client"] for case in cases}),
            "open_exceptions": sum(case["exceptions"]["open"] for case in cases),
            "queries_with_client": sum(case["queries"]["with_client"] for case in cases),
            "qc_variances_open": sum(case["qc_variances_open"] for case in cases),
            "pool_balance": round(sum(case["pool_balance"] or 0 for case in cases), 2),
        },
    }
