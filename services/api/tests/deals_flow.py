"""The create-to-monitor flow for the generated test deals, step by step through the API.

The tests run it offline on recorded model calls. With RECORD_DEALS=1 and a key set, the same
flow records any call that is missing.
"""

import uuid
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from app.config import settings
from app.main import app

client = TestClient(app)
CODE = "test-access-code"


def h(persona: str, code: bool = False) -> dict[str, str]:
    headers = {"X-Acting-User": persona}
    if code:
        headers["X-Demo-Access-Code"] = CODE
    return headers


def ok(response: Any) -> Any:
    assert response.status_code == 200, (response.status_code, response.text[:800])
    return response.json()


def deal_dir(deal: str) -> Path:
    return settings.newdeals_dir / deal


CREATED: list[int] = []


def new_client(name: str, contact: str, ai: bool, levels: int = 2) -> dict[str, Any]:
    row = ok(client.post("/api/deals/clients", headers=h("alex"), json={
        "name": f"{name} {uuid.uuid4().hex[:6]}", "contact_name": contact, "ai_permitted": ai,
        "approval_levels": levels}))
    CREATED.append(row["id"])
    return row


def cleanup(client_ids: list[int]) -> None:
    """Remove test clients and everything under them. Their audit chains stay, as all do."""
    from sqlalchemy import delete, or_, select, update
    from sqlalchemy.orm import Session

    from app.db import engine
    from app.deals.models import (
        Client,
        ClientMapping,
        DealCase,
        Document,
        Facility,
        LlmSpend,
        Submission,
        WorkItem,
    )

    if not client_ids:
        return
    with Session(engine) as db:
        cases = list(db.scalars(select(DealCase.id).where(DealCase.client_id.in_(client_ids))))
        facilities = list(db.scalars(select(Facility.id).where(Facility.client_id.in_(client_ids))))
        subs = list(db.scalars(select(Submission.id).where(Submission.facility_id.in_(facilities))))
        subjects = [f"case:{i}" for i in cases] + [f"facility:{i}" for i in facilities] + [
            f"submission:{i}" for i in subs] + [f"client:{i}" for i in client_ids]
        db.execute(delete(WorkItem).where(WorkItem.subject.in_(subjects)))
        db.execute(delete(LlmSpend).where(or_(LlmSpend.case_id.in_(cases),
                                              LlmSpend.submission_id.in_(subs))))
        db.execute(delete(Document).where(or_(Document.case_id.in_(cases),
                                              Document.submission_id.in_(subs))))
        db.execute(delete(Submission).where(Submission.id.in_(subs)))
        db.execute(update(DealCase).where(DealCase.id.in_(cases)).values(facility_id=None))
        db.execute(delete(Facility).where(Facility.id.in_(facilities)))
        db.execute(delete(DealCase).where(DealCase.id.in_(cases)))
        db.execute(delete(ClientMapping).where(ClientMapping.client_id.in_(client_ids)))
        db.execute(delete(Client).where(Client.id.in_(client_ids)))
        db.commit()


def new_case(client_id: int, name: str, deal_type: str, commitment: float) -> dict[str, Any]:
    return ok(client.post("/api/deals/cases", headers=h("hannah"), json={
        "client_id": client_id, "facility_name": name, "deal_type": deal_type,
        "commitment": commitment}))


def upload(case_id: int, path: Path, kind: str = "auto") -> dict[str, Any]:
    return ok(client.post(f"/api/deals/cases/{case_id}/documents",
                          params={"name": path.name, "kind": kind},
                          content=path.read_bytes(), headers=h("hannah", True)))


def step(case_id: int, name: str, body: Any = None, persona: str = "hannah",
         code: bool = False) -> dict[str, Any]:
    return ok(client.post(f"/api/deals/cases/{case_id}/{name}", json=body,
                          headers=h(persona, code)))


def approve_terms(case: dict[str, Any]) -> dict[str, Any]:
    cid = case["id"]
    case = step(cid, "terms/approve-verified")
    for key, term in case["state"]["terms"].items():
        if term["status"] == "proposed" and term["verified"] and term["typed"] is not None:
            case = step(cid, f"terms/{key}", {"action": "approve"})
        elif term["status"] in ("missing", "proposed") and key not in ("commitment",
                                                                       "advance_rate"):
            case = step(cid, f"terms/{key}", {"action": "absent",
                                              "reason": "Checked: not stated in the agreement"})
    return case


REPORT_LINES = ["gross_pool", "eligible_pool", "excess_concentration", "advance_rate",
                "borrowing_base", "availability", "delinquency_ratio"]


def capture_reporting(case_id: int, **extra: Any) -> dict[str, Any]:
    """The reporting the client asked for at intake."""
    return step(case_id, "reporting", {"lines": REPORT_LINES, "frequency": "Monthly",
                                       "format": "XLSX", **extra})


def work_open(case: dict[str, Any], query_on: tuple[str, ...] = ("Client model",)
              ) -> dict[str, Any]:
    cid = case["id"]
    for item in case["state"]["exceptions"]:
        if item["status"] != "open" or item["severity"] == "info":
            continue
        if item["type"] in query_on:
            case = step(cid, f"exceptions/{item['ref']}",
                        {"action": "query", "note": "Please confirm the rate your model uses"})
        else:
            case = step(cid, f"exceptions/{item['ref']}",
                        {"action": "accept", "note": "Reviewed against the documents"})
    return case


def onboard_ai(deal: str, client_row: dict[str, Any], name: str, deal_type: str,
               commitment: float, uploads: list[str]) -> dict[str, Any]:
    case = new_case(client_row["id"], name, deal_type, commitment)
    cid = case["id"]
    for file in uploads:
        case = upload(cid, deal_dir(deal) / "onboarding" / file)
    case = step(cid, "classify", code=True)
    case = step(cid, "extract", code=True)
    case = approve_terms(case)
    case = capture_reporting(cid)
    case = step(cid, "rules/draft", code=True)
    for kind in ("eligibility", "concentration"):
        for rule in case["state"]["rules"][kind]:
            if not rule["verified"]:
                case = step(cid, "rules", {"action": "remove", "kind": kind, "id": rule["id"],
                                           "reason": f"Failed code check: {rule['problem']}"})
    case = step(cid, "rules", {"action": "approve"})
    case = step(cid, "mapping/suggest", code=True)
    case = step(cid, "mapping", {})
    case = step(cid, "validate", {"as_of": "2026-09-30"})
    return case


def finish_onboarding(case: dict[str, Any], client_persona: str) -> dict[str, Any]:
    cid = case["id"]
    if not case["setup"]["own_client_model"] and not case["state"].get("built_model"):
        # No client model: Oxane builds one and the client validates it like any query.
        case = step(cid, "client-model/build", code=True)
    case = work_open(case)
    for item in case["state"]["exceptions"]:
        if item["status"] == "with_client":
            ok(client.post(f"/api/deals/queries/{cid}/{item['ref']}/answer",
                           headers=h(client_persona),
                           json={"text": "Our model still uses the original rate; we will "
                                 "update it.", "outcome": "confirmed"}))
    case = ok(client.get(f"/api/deals/cases/{cid}", headers=h("hannah")))
    for item in case["state"]["exceptions"]:
        if item["status"] in ("answered", "decided"):
            case = step(cid, f"exceptions/{item['ref']}", {"action": "close"})
    case = step(cid, "submit-qc")
    for item in case["qc_items"]:
        case = step(cid, "qc", {"item": item["id"], "result": "agrees"}, persona="tom")
    case = step(cid, "qc/complete", persona="tom")
    case = step(cid, "approve", {"reason": None}, persona="marcus")
    return step(cid, "go-live", persona="marcus")


def sub_step(sub_id: int, name: str, body: Any = None, persona: str = "priya",
             code: bool = False) -> dict[str, Any]:
    return ok(client.post(f"/api/deals/submissions/{sub_id}/{name}", json=body,
                          headers=h(persona, code)))


def first_month(facility_id: int, deal: str, tape: str, report: str | None,
                confirm_mapping: bool = False) -> dict[str, Any]:
    facility = ok(client.get(f"/api/deals/facilities/{facility_id}", headers=h("priya")))
    sub_id = facility["submissions"][0]["id"]
    folder = deal_dir(deal) / "monthly"
    ok(client.post(f"/api/deals/submissions/{sub_id}/documents",
                   params={"name": tape, "kind": "loan_tape"},
                   content=(folder / tape).read_bytes(), headers=h("priya", True)))
    if report:
        ok(client.post(f"/api/deals/submissions/{sub_id}/documents",
                       params={"name": report, "kind": "servicer_report"},
                       content=(folder / report).read_bytes(), headers=h("priya", True)))
    sub = sub_step(sub_id, "map", code=True)
    if confirm_mapping or not sub["state"]["mapping"]["confirmed"]:
        sub = sub_step(sub_id, "mapping", {}, code=True)
    # Validation, and the calculations when nothing blocks, ran by themselves.
    return sub


def triage_all(sub: dict[str, Any]) -> dict[str, Any]:
    for finding in sub["state"]["findings"]:
        if finding.get("decision"):
            continue
        if finding["severity"] == "blocking":
            body = {"outcome": "confirmed",
                    "note": "Rows excluded from the load; corrected file requested"}
        else:
            body = {"outcome": finding["suggested"]["outcome"], "note": ""}
        sub = sub_step(sub["id"], f"triage/{finding['ref']}", body)
    if sub["state"].get("hold_released"):
        # The released hold is re-run by the analyst.
        sub = sub_step(sub["id"], "process", code=True)
    if any(not f.get("decision") for f in sub["state"]["findings"]):
        return triage_all(sub)
    return sub
