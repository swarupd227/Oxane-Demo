"""Setup steps of a new case around the agreement: the reporting the client needs, the client
model Oxane builds where the client has none, the query tracker and the bank's rule library.

Code builds every workbook and computes every figure and every waiting time. The model may only
draft the notes that go with the built model, with every figure a {{placeholder}} that code
fills; a client that does not permit AI gets the code template and no model call.
"""

import hashlib
from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.deals import ai, checks, workbook
from app.deals import rules as deal_rules
from app.deals.models import Client, DealCase, Document, Facility
from app.deals.onboard import (
    _save,
    _state,
    active_docs,
    case_ref,
    gateway,
    log,
    pdfs,
    readiness,
    rebuild,
    refuse,
)
from app.personas import Persona

# What a client may ask to receive, and how code produces each line.
REPORT_LINES: dict[str, tuple[str, str]] = {
    "gross_pool": ("Gross pool balance", "Sum of current balances on the tape"),
    "eligible_pool": ("Eligible pool balance", "Engine: loans passing every eligibility rule"),
    "ineligible_by_rule": ("Ineligible balance by rule", "Engine: failed balance per rule"),
    "excess_concentration": ("Excess concentration", "Engine: amount over each limit"),
    "advance_rate": ("Advance rate in force", "Approved terms, amended rate from its date"),
    "reserve": ("Reserve", "Approved terms"),
    "borrowing_base": ("Borrowing base", "(Eligible - excess) x advance rate - reserve"),
    "availability": ("Availability", "Lower of the borrowing base and the facility limit"),
    "delinquency_ratio": ("Delinquency ratio and trigger", "Engine: rolling average against "
                          "the trigger in the agreement"),
    "loss_ratio": ("Annualised loss ratio", "Charge-offs x 12 over the opening pool"),
    "roll_forward": ("Pool roll-forward", "Opening + new - collections - charge-offs"),
    "stratification": ("Pool stratification", "Balance by status, score band and region"),
}
FREQUENCIES = ("Monthly", "Quarterly", "Weekly")
FORMATS = ("XLSX", "PDF", "CSV")
WITH_RESULTS = ("gross_pool", "eligible_pool", "excess_concentration", "advance_rate", "reserve",
                "borrowing_base", "availability")


def _invalid(fields: dict[str, str], message: str = "Check the entry") -> None:
    if fields:
        raise HTTPException(status_code=422, detail={"message": message, "fields": fields})


# The reporting the client needs


def catalogue() -> list[dict[str, str]]:
    return [{"key": k, "label": label, "how": how} for k, (label, how) in REPORT_LINES.items()]


def capture_reporting(db: Session, case: DealCase, client: Client, persona: Persona,
                      body: dict[str, Any]) -> dict[str, Any]:
    """Record the report lines, frequency, format and delivery day the client asked for."""
    lines = [k for k in body.get("lines") or [] if isinstance(k, str)]
    frequency = body.get("frequency") or "Monthly"
    fmt = body.get("format") or "XLSX"
    errors: dict[str, str] = {}
    unknown = [k for k in lines if k not in REPORT_LINES]
    if not lines:
        errors["lines"] = "Choose at least one report line"
    elif unknown:
        errors["lines"] = f"Unknown report line: {unknown[0]}"
    if frequency not in FREQUENCIES:
        errors["frequency"] = "Monthly, quarterly or weekly"
    if fmt not in FORMATS:
        errors["format"] = "XLSX, PDF or CSV"
    state = _state(case)
    term_day = ((state.get("terms") or {}).get("reporting_day") or {}).get("typed")
    day = body.get("day") or term_day
    try:
        day = int(day) if day is not None else None
    except (TypeError, ValueError):
        day = None
        errors["day"] = "A day from 1 to 28"
    if day is not None and not 1 <= day <= 28:
        errors["day"] = "A day from 1 to 28"
    note = (body.get("note") or "").strip()[:300]
    _invalid(errors)
    before = state.get("reporting") or {}
    state["reporting"] = {
        "lines": [k for k in REPORT_LINES if k in lines], "frequency": frequency,
        "format": fmt, "day": day, "day_source": "agreement" if day is not None and
        day == term_day and not body.get("day") else ("client" if day else None),
        "note": note or None, "version": before.get("version", 0) + 1,
        "captured_by": persona.name, "captured_at": datetime.now(UTC).isoformat()}
    _save(case, state)
    log(db, case, persona, "reporting", f"Recorded the client's reporting: "
        f"{len(state['reporting']['lines'])} lines, {frequency.lower()}, {fmt}"
        + (f", by day {day}" if day else ""), {"reason": note or None})
    rebuild(db, case, client)
    return state["reporting"]


# The client model Oxane builds where the client has none


def own_model(db: Session, case: DealCase) -> Document | None:
    return next((d for d in active_docs(db, case) if d.kind == "client_model"
                 and d.kind_source != "oxane"), None)


def model_facts(state: dict[str, Any]) -> dict[str, str]:
    """The figures the notes may refer to, each worked out or copied by code."""
    terms = state.get("terms") or {}
    rules = state.get("rules") or {}
    engine = (state.get("validation") or {}).get("engine") or {}

    def val(key: str) -> str:
        return (terms.get(key) or {}).get("value") or "not stated"

    return {
        "facility_limit": val("commitment"), "advance_rate": val("advance_rate"),
        "reserve": val("reserve"), "delinquency_trigger": val("delinquency_trigger"),
        "eligibility_rules": str(len(rules.get("eligibility", []))),
        "concentration_limits": str(len(rules.get("concentration", []))),
        "borrowing_base": f"US${engine.get('borrowing_base_cents', 0) / 100:,.2f}",
        "as_of": (state.get("validation") or {}).get("as_of") or "",
    }


FACT_WORDS = {
    "facility_limit": "the facility limit in the agreement",
    "advance_rate": "the advance rate in force",
    "reserve": "the reserve deducted in the borrowing base",
    "delinquency_trigger": "the delinquency trigger level",
    "eligibility_rules": "how many eligibility criteria the model tests",
    "concentration_limits": "how many concentration limits the model tests",
    "borrowing_base": "the borrowing base the model works out on the onboarding tape",
    "as_of": "the date of the onboarding tape",
}


def template_notes() -> list[str]:
    return ["This model was built by Oxane from the executed agreement and its amendments, "
            "because no borrowing base model was provided. It applies {{eligibility_rules}} "
            "eligibility criteria and {{concentration_limits}} concentration limits.",
            "It uses an advance rate of {{advance_rate}}, a reserve of {{reserve}} and a facility "
            "limit of {{facility_limit}}. On the tape dated {{as_of}} it gives a borrowing base "
            "of {{borrowing_base}}.",
            "Please confirm the model reflects how you calculate the borrowing base, or tell us "
            "what to change."]


def draft_notes(case: DealCase, client: Client, facts: dict[str, str]) -> tuple[list[str], str]:
    """AI wording where the client permits it, else the template. Code fills every figure."""
    paragraphs, by = template_notes(), "template"
    if client.ai_permitted:
        try:
            result = ai.draft_model_notes(gateway(case, client, "deals_model_notes"),
                                          {k: FACT_WORDS[k] for k in facts})
            usable = bool(result.paragraphs)
            for paragraph in result.paragraphs:
                _, unknown = checks.fill(paragraph, facts)
                if unknown:
                    usable = False
            if usable:
                paragraphs, by = result.paragraphs, "ai"
        except Exception:  # noqa: BLE001 - the template stands in when the model cannot
            paragraphs, by = template_notes(), "template"
    return [checks.fill(p, facts)[0] for p in paragraphs], by


def build_model(db: Session, case: DealCase, client: Client, persona: Persona
                ) -> dict[str, Any]:
    """Build the client model workbook from the approved terms and rule set. Code only."""
    if own_model(db, case) is not None:
        raise refuse("The client provided its own model; it is compared with the agreement")
    state = _state(case)
    if (state.get("rules") or {}).get("status") != "approved":
        raise refuse("Approve the rule set first; the model is built from it", 422)
    if not (state.get("validation") or {}).get("engine"):
        raise refuse("Run validation first; the model shows the borrowing base on the tape", 422)
    before = state.get("built_model") or {}
    version = before.get("version", 0) + 1
    facts = model_facts(state)
    notes, notes_by = draft_notes(case, client, facts)
    name = f"{case_ref(case)}_Client_Model_v{version}.xlsx"
    content = workbook.client_model(
        {"ref": case_ref(case), "facility_name": case.facility_name, "client": client.name,
         "version": version, "built_by": persona.name}, state, notes, notes_by)
    for old in db.scalars(select(Document).where(Document.case_id == case.id,
                                                 Document.kind == "client_model",
                                                 Document.kind_source == "oxane",
                                                 Document.status == "active")):
        old.status = "replaced"
    doc = Document(case_id=case.id, name=name, kind="client_model", kind_source="oxane",
                   version=version, sha256=hashlib.sha256(content).hexdigest(),
                   size=len(content), content=content, status="active",
                   content_type="application/vnd.openxmlformats-officedocument.spreadsheetml"
                   ".sheet", uploaded_by=persona.name, replaces_id=before.get("doc_id"))
    db.add(doc)
    db.flush()
    state = _state(case)
    state["built_model"] = {
        "version": version, "name": name, "doc_id": doc.id, "sha256": doc.sha256,
        "rules_version": (state.get("rules") or {}).get("version", 1),
        "built_by": persona.name, "built_at": datetime.now(UTC).isoformat(),
        "notes": notes, "notes_by": notes_by, "status": "built", "validation": None,
        "history": [*before.get("history", []), *([{
            k: before.get(k) for k in ("version", "status", "validation", "sent_at")}]
            if before else [])]}
    _save(case, state)
    log(db, case, persona, "build-client-model",
        f"Built client model v{version} from the approved terms and rule set "
        f"(notes: {'AI wording, figures filled by code' if notes_by == 'ai' else 'template'})",
        {"refs": [f"doc:{doc.id}"]})
    rebuild(db, case, client)
    return state["built_model"]


# The query tracker: analyst time apart from client waiting time


def _hours(start: str | None, end: str | None) -> float | None:
    if not start:
        return None
    a = datetime.fromisoformat(start)
    b = datetime.fromisoformat(end) if end else datetime.now(UTC)
    return round((b - a).total_seconds() / 3600, 2)


def query_tracker(state: dict[str, Any]) -> dict[str, Any]:
    rows = []
    for item in state.get("exceptions", []):
        query = item.get("query")
        if not query:
            continue
        answered = (item.get("answer") or {}).get("at")
        closed = next((h["at"] for h in reversed(item.get("history", []))
                       if h["action"] in ("close", "accept")), None)
        rows.append({"ref": item["ref"], "title": item["title"], "type": item["type"],
                     "sent_at": query["sent_at"], "sent_by": query["by"],
                     "answered_at": answered, "closed_at": closed,
                     "status": "waiting" if item["status"] == "with_client" else (
                         "answered" if item["status"] == "answered" else "closed"),
                     "client_wait_hours": _hours(query["sent_at"], answered),
                     "model_check": item["key"].startswith("model:validation:")})
    return {"queries": rows, "open": sum(r["status"] == "waiting" for r in rows),
            "client_wait_hours": round(sum(r["client_wait_hours"] or 0 for r in rows), 2)}


# The bank's rule library: rules approved on the client's other facilities


def library(db: Session, client: Client, exclude_case: int | None = None
            ) -> list[dict[str, Any]]:
    """Every rule live on this client's facilities, once per test, with the facility that
    first set it. Rules never cross from one client to another."""
    seen: dict[str, dict[str, Any]] = {}
    for facility in db.scalars(select(Facility).where(Facility.client_id == client.id,
                                                      Facility.status == "live")
                               .order_by(Facility.id)):
        if facility.case_id == exclude_case:
            continue
        for kind in ("eligibility", "concentration"):
            for rule in (facility.config.get("rules") or {}).get(kind, []):
                key = f"{kind}:{rule.get('describe')}"
                if rule.get("describe") and key not in seen:
                    seen[key] = {**rule, "kind": kind, "origin": {
                        "facility_id": facility.id, "facility": facility.name,
                        "ref": f"FAC-{2000 + facility.id}"}}
    return list(seen.values())


def add_library_rules(db: Session, case: DealCase, client: Client, persona: Persona
                      ) -> dict[str, Any]:
    """Reuse the bank's library: each rule is checked again against this agreement's own text
    and added only where this agreement states the same clause and threshold."""
    state = _state(case)
    rules = state.get("rules") or {"eligibility": [], "concentration": [], "not_codable": [],
                                   "status": "draft", "version": 1}
    if rules.get("status") == "approved":
        raise refuse("The rules are approved. Reopen them to change a rule")
    candidates = library(db, client, case.id)
    if not candidates:
        raise refuse(f"{client.name} has no live facility yet, so its rule library is empty",
                     422)
    documents = pdfs(active_docs(db, case), ("agreement", "amendment"))
    added, skipped = [], []
    for rule in candidates:
        kind = rule["kind"]
        have = {r.get("describe") for r in rules.get(kind, [])}
        if rule["describe"] in have:
            skipped.append({"describe": rule["describe"], "why": "already in this rule set"})
            continue
        checked = None
        for name in documents:
            draft = {k: v for k, v in rule.items() if k not in (
                "id", "page", "rects", "verified", "problem", "kind", "edited")}
            attempt = deal_rules.verify_rule({**draft, "document": name}, documents,
                                             kind == "concentration")
            if attempt["verified"]:
                checked = attempt
                break
        if checked is None:
            skipped.append({"describe": rule["describe"], "from": rule["origin"]["ref"],
                            "why": "this agreement does not state the same clause"})
            continue
        prefix = "E" if kind == "eligibility" else "C"
        numbers = [int(r["id"][1:]) for r in rules.get(kind, [])] or [0]
        checked.update(id=f"{prefix}{max(numbers) + 1}", source="library",
                       origin=rule["origin"])
        checked["describe"] = deal_rules.describe_rule(checked, kind == "concentration")
        rules[kind] = [*rules.get(kind, []), checked]
        added.append(checked["id"])
    rules["library_checked"] = {"at": datetime.now(UTC).isoformat(), "added": added,
                                "skipped": skipped}
    state["rules"] = rules
    _save(case, state)
    log(db, case, persona, "rules-library",
        f"Checked {client.name}'s rule library ({len(candidates)} rules): {len(added)} reused, "
        f"{len(skipped)} not reused")
    rebuild(db, case, client)
    return rules


def provenance(db: Session, client: Client, state: dict[str, Any]) -> dict[str, Any]:
    """What came from the bank's library, what from the lender's stored mapping, and what was
    set for this facility alone."""
    rules = state.get("rules") or {}
    rows = []
    for kind in ("eligibility", "concentration"):
        for r in rules.get(kind, []):
            rows.append({"id": r["id"], "kind": kind, "describe": r.get("describe"),
                         "plain_english": r.get("plain_english"),
                         "from": "bank_library" if r.get("source") == "library" else "facility",
                         "origin": r.get("origin")})
    mapping = state.get("mapping") or {}
    return {
        "rules": rows,
        "library_rules": sum(r["from"] == "bank_library" for r in rows),
        "facility_rules": sum(r["from"] == "facility" for r in rows),
        "mapping": {"source": mapping.get("source"),
                    "from": "lender_mapping" if mapping.get("source") == "stored" else "new",
                    "signature": (mapping.get("signature") or "")[:12],
                    "columns": sum(1 for f in (mapping.get("columns") or {}).values() if f)},
        "thresholds": "facility",
        "client": client.name,
    }


def setup_view(db: Session, case: DealCase) -> dict[str, Any]:
    client = db.get(Client, case.client_id)
    state = case.state or {}
    return {"report_catalogue": catalogue(), "queries": query_tracker(state),
            "own_client_model": own_model(db, case) is not None,
            "rule_library": [{"describe": r["describe"], "kind": r["kind"],
                              "plain_english": r.get("plain_english"), "origin": r["origin"]}
                             for r in library(db, client, case.id)],
            "provenance": provenance(db, client, state),
            "ready": readiness(db, case, state)}
