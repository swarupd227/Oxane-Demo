"""Monthly monitoring for a facility that went live from a new case.

The month's tape is mapped with the client's stored mapping when its layout is unchanged; only
a changed layout goes to the model (or, without AI, to name matching), and the analyst confirms
it. Validation holds the load on a blocking failure. The engine runs the facility's own rule set,
reconciles the pool against the prior period and works out the triggers from the thresholds set
at go-live. Findings are triaged, the report is drafted with every figure filled by code, and it
stays provisional until each approval level the client requires has signed off.
"""

import copy
import re
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from engine import generic
from engine.monitoring import rolling_trigger
from engine.rules import RuleSet
from engine.validation import prior_period
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from app.deals import ai, audit, checks, files, handoffs
from app.deals import rules as deal_rules
from app.deals.guard import DealsGateway
from app.deals.models import Client, Document, Facility, Submission
from app.deals.onboard import (
    _call,
    confirm_mapping,
    mapped_rows,
    refuse,
    run_validation,
    suggest_columns,
)
from app.personas import Persona
from app.pipeline.documents import PdfDocument

OUTCOMES = {"logged": "Logged, no alert", "query": "Query to sender",
            "confirmed": "Confirmed issue", "expert": "Expert review"}
LEVEL_ROLES = {1: "monitoring_analyst", 2: "reviewer", 3: "head"}
LEVEL_TITLES = {1: "Preparer", 2: "Second analyst", 3: "Head of monitoring"}


def sub_ref(sub: Submission) -> str:
    return f"SUB-{3000 + sub.id}"


def fac_ref(facility: Facility) -> str:
    return f"FAC-{2000 + facility.id}"


def subject(sub: Submission) -> str:
    return f"submission:{sub.id}"


def _state(sub: Submission) -> dict[str, Any]:
    return copy.deepcopy(sub.state or {})


def _save(sub: Submission, state: dict[str, Any]) -> None:
    sub.state = state
    flag_modified(sub, "state")


def docs_of(db: Session, sub: Submission) -> list[Document]:
    return list(db.scalars(select(Document).where(Document.submission_id == sub.id,
                                                  Document.status == "active")
                           .order_by(Document.id)))


def log(db: Session, sub: Submission, persona: Persona, kind: str, text: str,
        payload: dict[str, Any] | None = None) -> None:
    audit.append(db, sub.audit_id, persona.name, kind, text, payload)


def gateway_for(sub: Submission, client: Client) -> DealsGateway | None:
    return DealsGateway(submission_id=sub.id, client_key=f"deal:{client.id}",
                        ref=sub_ref(sub)) if client.ai_permitted else None


def prior_submission(db: Session, sub: Submission) -> Submission | None:
    return db.scalars(select(Submission).where(Submission.facility_id == sub.facility_id,
                                               Submission.period < sub.period,
                                               Submission.status == "released")
                      .order_by(Submission.period.desc())).first()


def _loans_from(db: Session, doc_id: int, mapping: dict[str, Any], excluded: list[str]
                ) -> list[dict[str, Any]]:
    doc = db.get(Document, doc_id)
    _, rows = files.table(doc)
    rows = mapped_rows(rows, mapping["columns"])
    seen: set[str] = set()
    loans = []
    for row in rows:
        if row["loan_id"] in excluded or row["loan_id"] in seen:
            continue
        seen.add(row["loan_id"])
        loans.append(generic.coerce(row, mapping["status_map"]))
    return loans


def receive(db: Session, sub: Submission, persona: Persona) -> None:
    if sub.status == "expected":
        sub.status = "received"
        handoffs.close_items(db, f"facility:{sub.facility_id}:first", persona)
        log(db, sub, persona, "receive", f"Received the {sub.period} submission")


def map_tape(db: Session, sub: Submission, facility: Facility, client: Client,
             persona: Persona) -> dict[str, Any]:
    docs = docs_of(db, sub)
    tape = next((d for d in reversed(docs) if d.kind == "loan_tape"), None)
    if tape is None:
        raise refuse("Upload the month's loan tape first", 422)
    headers, rows = files.table(tape)
    if not rows:
        raise refuse("The tape has no rows", 422)
    stored = facility.config["mapping"]
    state = _state(sub)
    signature = files.signature(headers)
    if signature == stored["signature"]:
        columns, statuses, source = stored["columns"], dict(stored["status_map"]), "facility"
        # A new status value still needs a standard status.
        status_col = next((h for h, f in columns.items() if f == "status"), None)
        new = sorted({r.get(status_col or "", "") for r in rows} - set(statuses) - {""})
        if new:
            statuses.update(checks.heuristic_statuses(new))
        confirmed = not new
    else:
        columns, statuses, source = suggest_columns(db, client, headers, rows,
                                                    gateway_for(sub, client))
        confirmed = False
    changed = sorted(set(headers) ^ set(stored["headers"]))
    state["mapping"] = {"tape_doc": tape.id, "signature": signature, "headers": headers,
                        "columns": columns, "status_map": statuses, "source": source,
                        "confirmed": confirmed, "changed_columns": changed,
                        "checks": checks.check_mapping(columns, rows, statuses)}
    if confirmed and any(c["problem"] for c in state["mapping"]["checks"]):
        state["mapping"]["confirmed"] = False
    _save(sub, state)
    words = {"facility": "the facility's stored mapping (layout unchanged)",
             "stored": "the client's stored mapping", "ai": "AI, for the changed layout",
             "rules": "name matching for the changed layout (AI not permitted)"}[source]
    log(db, sub, persona, "map", f"Mapped the tape with {words}")
    return state["mapping"]


def confirm(db: Session, sub: Submission, client: Client, persona: Persona,
            body: dict[str, Any]) -> dict[str, Any]:
    state = _state(sub)
    mapping = state.get("mapping")
    if not mapping:
        raise refuse("Map the tape first", 422)
    tape = db.get(Document, mapping["tape_doc"])
    headers, rows = files.table(tape)
    columns = body.get("columns") or mapping["columns"]
    statuses = body.get("status_map") or mapping["status_map"]
    mapping["checks"] = confirm_mapping(db, client, headers, rows, columns, statuses)
    mapping.update(columns={h: columns.get(h) or None for h in headers}, status_map=statuses,
                   confirmed=True, confirmed_by=persona.name)
    state["mapping"] = mapping
    _save(sub, state)
    log(db, sub, persona, "confirm-mapping", "Confirmed the changed layout's mapping and stored "
        "it for the client")
    return mapping


def read_report(db: Session, sub: Submission, client: Client, persona: Persona) -> None:
    """The model reads the servicer report's figures; code finds each quote on its page."""
    report = next((d for d in docs_of(db, sub) if d.kind == "servicer_report"
                   and d.name.lower().endswith(".pdf")), None)
    state = _state(sub)
    if report is None or not client.ai_permitted:
        state.setdefault("report_figures", {})
        _save(sub, state)
        return
    document = files.pdf(report)
    named = {report.name: PdfDocument(report.name, document.path, document.pages)}
    reading = _call(ai.read_report, gateway_for(sub, client), report.name, document.body)
    figures = {}
    for figure in reading.figures:
        if not figure.found:
            continue
        found = checks.cite(named, report.name, figure.quote)
        ok = found is not None and checks.figures_in_quote(figure.value, figure.quote)
        typed, problem = checks.parse_term("money", figure.value)
        cents = int(checks.figures(figure.value)[0] * 100) if checks.figures(figure.value) else 0
        figures[figure.key] = {"value": figure.value, "cents": cents
                               if ok and typed is not None and not problem else None,
                               "quote": figure.quote, "page": found["page"] if found else None,
                               "document": report.name, "verified": ok and not problem,
                               "source": "ai"}
    state["report_figures"] = figures
    _save(sub, state)
    log(db, sub, persona, "read-report", f"Read {len(figures)} figures from {report.name}; "
        f"{sum(f['verified'] for f in figures.values())} verified on their page")


def enter_figure(db: Session, sub: Submission, persona: Persona, body: dict[str, Any]) -> None:
    key = body.get("key")
    if key not in ("principal_collections", "charge_offs", "pool_balance", "new_loans_balance"):
        raise refuse("Unknown figure", 422)
    report = next((d for d in docs_of(db, sub) if d.kind == "servicer_report"), None)
    if report is None:
        raise refuse("Upload the servicer report first", 422)
    document = files.pdf(report)
    named = {report.name: PdfDocument(report.name, document.path, document.pages)}
    value = (body.get("value") or "").strip()
    page = int(body.get("page") or 0)
    typed, problem = checks.parse_term("money", value)
    errors = {}
    if problem:
        errors["value"] = problem
    elif not checks.on_page(named, report.name, page, value):
        errors["page"] = f"This figure is not on page {page} of {report.name}"
    if errors:
        raise HTTPException(status_code=422, detail={"message": "Check the figure",
                                                     "fields": errors})
    state = _state(sub)
    state.setdefault("report_figures", {})[key] = {
        "value": value, "cents": int(checks.figures(value)[0] * 100), "quote": None, "page": page,
        "document": report.name, "verified": True, "source": "analyst"}
    _save(sub, state)
    log(db, sub, persona, "enter-figure", f"Entered {key.replace('_', ' ')} {value} from "
        f"{report.name} p.{page}")


def _history(db: Session, facility: Facility, sub: Submission) -> list[tuple[str, Decimal]]:
    months = []
    baseline = facility.config["baseline"]
    if baseline.get("delinquency_pct") is not None:
        months.append((baseline["period"], Decimal(baseline["delinquency_pct"])))
    for other in db.scalars(select(Submission).where(Submission.facility_id == facility.id,
                                                     Submission.period < sub.period,
                                                     Submission.status == "released")
                            .order_by(Submission.period)):
        value = (other.state.get("tests") or {}).get("delinquency_pct")
        if value is not None:
            months.append((other.period, Decimal(value)))
    return months


def process(db: Session, sub: Submission, facility: Facility, client: Client,
            persona: Persona) -> dict[str, Any]:
    state = _state(sub)
    mapping = state.get("mapping")
    if not mapping or not mapping.get("confirmed"):
        raise refuse("Confirm the tape mapping first", 422)
    if "report_figures" not in state:
        read_report(db, sub, client, persona)
        state = _state(sub)
    ruleset = RuleSet.model_validate(facility.config["ruleset"])
    used = deal_rules.rule_fields(facility.config["rules"])
    thresholds = facility.config["thresholds"]
    trigger = thresholds.get("delinquency")
    tape = db.get(Document, mapping["tape_doc"])
    _, rows = files.table(tape)
    view = run_validation(mapped_rows(rows, mapping["columns"]), mapping["status_map"], ruleset,
                          used, sub.period_end, state.get("excluded_rows", []),
                          trigger["days"] if trigger else None)
    state["validation"] = view
    state["provisional"] = True
    if view.get("engine"):
        current = _loans_from(db, tape.id, mapping, state.get("excluded_rows", []))
        prior_sub = prior_submission(db, sub)
        if prior_sub is not None:
            prior = _loans_from(db, prior_sub.state["mapping"]["tape_doc"],
                                prior_sub.state["mapping"],
                                prior_sub.state.get("excluded_rows", []))
            prior_label = prior_sub.period
        else:
            baseline = facility.config["baseline"]
            prior = _loans_from(db, baseline["tape_doc"], facility.config["mapping"],
                                baseline.get("excluded_rows", []))
            prior_label = baseline["period"]
        collections = (state.get("report_figures") or {}).get("principal_collections") or {}
        roll = generic.roll_forward(prior, current, collections.get("cents")
                                    if collections.get("verified") else None)
        limits = {k: (v[0], Decimal(v[1])) for k, v in thresholds["prior_period"].items()}
        changes = prior_period(generic.metrics(current), generic.metrics(prior), limits)
        state["reconciliation"] = {
            "prior_period": prior_label,
            "roll_forward": {k: (list(v) if isinstance(v, tuple) else v)
                             for k, v in roll.__dict__.items()},
            "changes": [{"metric": c.metric, "prior": str(c.prior), "current": str(c.current),
                         "change": str(c.change), "threshold": str(c.threshold),
                         "basis": c.basis, "flagged": c.flagged} for c in changes],
        }
        tests: dict[str, Any] = {"borrowing_base_cents": view["engine"]["borrowing_base_cents"],
                                 "availability_cents": view["engine"]["availability_cents"]}
        if trigger:
            month = Decimal(view["engine"]["delinquency_pct"])
            history = [*_history(db, facility, sub), (sub.period, month)]
            rolled = rolling_trigger(history, Decimal(str(trigger["limit_pct"])), "max",
                                     trigger["months"])
            tests.update(delinquency_pct=str(month), delinquency_average=str(rolled.average),
                         delinquency_limit=str(rolled.limit), delinquency_months=[
                             {"period": p, "value": str(v)} for p, v in rolled.monthly[-3:]],
                         delinquency_breached=rolled.breached,
                         delinquency_warning=rolled.early_warning,
                         delinquency_headroom=str(rolled.headroom),
                         delinquency_window=min(len(history), trigger["months"]),
                         delinquency_source=trigger.get("source"))
        loss = thresholds.get("loss")
        if loss and roll.opening_cents:
            annual = generic.pct(roll.charge_offs_cents * 12, roll.opening_cents)
            tests.update(loss_pct=str(annual), loss_limit=str(loss["limit_pct"]),
                         loss_breached=annual > Decimal(str(loss["limit_pct"])),
                         loss_source=loss.get("source"))
        state["tests"] = tests
    state["findings"] = _findings(state, sub)
    state["processed_at"] = datetime.now(UTC).isoformat()
    _save(sub, state)
    sub.status = "held" if view.get("held") else "in_review"
    log(db, sub, persona, "process", "Validation held the load" if view.get("held") else
        f"Ran validation, reconciliation and tests: borrowing base US$"
        f"{view['engine']['borrowing_base_cents'] / 100:,.2f}")
    return state


def _finding(key: str, check: str, severity: str, title: str, detail: str, suggested: str,
             reason: str) -> dict[str, Any]:
    return {"key": key, "check": check, "severity": severity, "title": title, "detail": detail,
            "suggested": {"outcome": suggested, "reason": reason, "by": "Rule"}}


def _findings(state: dict[str, Any], sub: Submission) -> list[dict[str, Any]]:
    before = {f["key"]: f for f in state.get("findings", [])}
    items = []
    for check in (state.get("validation") or {}).get("checks", []):
        if check["failed"]:
            items.append(_finding(f"val:{check['id']}", "Validation", check["severity"],
                                  f"{check['text']}: {check['failed']} rows fail",
                                  ", ".join(f"{e['key']} (row {e['row']})"
                                            for e in check["examples"][:4]),
                                  "query" if check["severity"] == "blocking" else "logged",
                                  "Blocking check: the load is held until the rows are excluded "
                                  "or a corrected file arrives" if check["severity"] == "blocking"
                                  else "Warning check, logged with the rows"))
    recon = state.get("reconciliation") or {}
    roll = recon.get("roll_forward") or {}
    if roll.get("missing_loan_ids"):
        items.append(_finding("rec:missing", "Reconciliation", "warning",
                              f"{len(roll['missing_loan_ids'])} "
                              f"{'loan' if len(roll['missing_loan_ids']) == 1 else 'loans'} from "
                              f"{recon['prior_period']} not on this tape",
                              f"{', '.join(roll['missing_loan_ids'][:5])}: US$"
                              f"{roll['missing_cents'] / 100:,.2f} last period", "query",
                              "Loans that leave the pool should be listed as repaid or charged "
                              "off"))
    if roll.get("gap_cents"):
        items.append(_finding("rec:gap", "Reconciliation", "warning",
                              f"Roll-forward gap of US${roll['gap_cents'] / 100:,.2f}",
                              "Opening plus new loans less collections and charge-offs, against "
                              "the tape", "query", "The pool does not roll forward to the tape"))
    if roll and roll.get("collections_cents") is None:
        items.append(_finding("rec:collections", "Reconciliation", "warning",
                              "No verified collections figure",
                              "Without the servicer's principal collections the roll-forward "
                              "cannot close", "query", "Ask the servicer for the report"))
    for change in recon.get("changes", []):
        if change["flagged"]:
            items.append(_finding(f"prior:{change['metric']}", "Prior period", "warning",
                                  f"{change['metric'].replace('_', ' ').capitalize()} moved "
                                  f"{change['change']}% against {recon['prior_period']}",
                                  f"{change['prior']} to {change['current']}", "logged",
                                  "A move beyond the tolerance, explained by the new loans"))
    tests = state.get("tests") or {}
    if tests.get("delinquency_breached") or tests.get("delinquency_warning"):
        word = "breached" if tests["delinquency_breached"] else "within the warning band"
        items.append(_finding("test:delinquency", "Trigger", "warning",
                              f"Delinquency trigger {word}: {tests['delinquency_average']}% "
                              f"against {tests['delinquency_limit']}%",
                              f"{tests['delinquency_window']}-month average; source "
                              f"{tests.get('delinquency_source')}",
                              "confirmed" if tests["delinquency_breached"] else "expert",
                              "A trigger breach is a confirmed issue" if
                              tests["delinquency_breached"] else
                              "Near the limit: needs credit judgement on the trend"))
    if tests.get("loss_breached"):
        items.append(_finding("test:loss", "Trigger", "warning",
                              f"Loss trigger breached: {tests['loss_pct']}% annualised",
                              f"Limit {tests['loss_limit']}%", "confirmed", "Breach"))
    for item in items:
        old = before.get(item["key"])
        item["ref"] = old["ref"] if old else None
        item["decision"] = old.get("decision") if old else None
    counter = max([int(f["ref"].rsplit("-", 1)[1]) for f in before.values() if f.get("ref")]
                  or [0])
    for item in items:
        if item["ref"] is None:
            counter += 1
            item["ref"] = f"EXC-{sub.period}-{3000 + sub.id}-{counter:02d}"
    return items


def triage(db: Session, sub: Submission, facility: Facility, persona: Persona, ref: str,
           outcome: str, note: str) -> None:
    state = _state(sub)
    item = next((f for f in state.get("findings", []) if f["ref"] == ref), None)
    if item is None:
        raise refuse("Unknown finding", 404)
    if outcome not in OUTCOMES:
        raise refuse("Unknown outcome", 422)
    if outcome != item["suggested"]["outcome"] and not note.strip():
        raise HTTPException(status_code=422, detail={"message": "Give a reason", "fields": {
            "note": "A reason is required when the decision differs from the suggestion"}})
    item["decision"] = {"outcome": outcome, "note": note.strip() or None, "by": persona.name,
                        "at": datetime.now(UTC).isoformat(), "status":
                        "with_expert" if outcome == "expert" else "decided"}
    if outcome == "expert":
        handoffs.open_item(db, f"submission:{sub.id}:expert:{ref}", subject(sub), sub.audit_id,
                           "expert", f"Expert judgement: {item['title']}"[:200], "expert",
                           f"/facilities/{facility.id}/submissions/{sub.id}", persona,
                           detail=note)
    if item["key"].startswith("val:") and item["severity"] == "blocking" and outcome in (
            "confirmed", "logged"):
        check = next(c for c in state["validation"]["checks"]
                     if c["id"] == item["key"].split(":", 1)[1])
        state["excluded_rows"] = sorted(set(state.get("excluded_rows", [])) | set(check["keys"]))
    state["findings"] = [item if f["ref"] == ref else f for f in state["findings"]]
    _save(sub, state)
    log(db, sub, persona, "triage", f"{ref}: {OUTCOMES[outcome]}", {"reason": note or None,
                                                                    "refs": [ref]})


def expert_decide(db: Session, sub: Submission, facility: Facility, persona: Persona, ref: str,
                  text: str) -> None:
    state = _state(sub)
    item = next((f for f in state.get("findings", []) if f["ref"] == ref), None)
    if item is None or (item.get("decision") or {}).get("status") != "with_expert":
        raise refuse("Nothing is waiting on you for this finding", 404)
    if not text.strip():
        raise HTTPException(status_code=422, detail={"message": "Record the decision",
                                                     "fields": {"text": "Required"}})
    item["decision"].update(status="decided", expert={"text": text.strip(), "by": persona.name,
                                                      "at": datetime.now(UTC).isoformat()})
    state["findings"] = [item if f["ref"] == ref else f for f in state["findings"]]
    _save(sub, state)
    handoffs.close_items(db, f"submission:{sub.id}:expert:{ref}", persona, text.strip())
    handoffs.open_item(db, f"submission:{sub.id}:expert:{ref}:back", subject(sub), sub.audit_id,
                       "review", f"Expert decided {ref}: {item['title']}"[:200],
                       "monitoring_analyst", f"/facilities/{facility.id}/submissions/{sub.id}",
                       persona, detail=text.strip())
    log(db, sub, persona, "expert-decision", f"{ref}: expert decision recorded",
        {"reason": text.strip(), "refs": [ref]})


def report_facts(state: dict[str, Any]) -> dict[str, str]:
    engine = (state.get("validation") or {}).get("engine") or {}
    tests = state.get("tests") or {}
    roll = (state.get("reconciliation") or {}).get("roll_forward") or {}
    facts = {
        "pool_balance": f"US${engine.get('gross_pool_cents', 0) / 100:,.2f}",
        "eligible_pool": f"US${engine.get('eligible_pool_cents', 0) / 100:,.2f}",
        "borrowing_base": f"US${engine.get('borrowing_base_cents', 0) / 100:,.2f}",
        "advance_rate": f"{engine.get('advance_rate_pct', '')}%",
        "loans": f"{engine.get('loans', 0):,}",
        "new_loans": f"{roll.get('new_loans', 0):,}",
        "charge_offs": f"US${roll.get('charge_offs_cents', 0) / 100:,.2f}",
    }
    if tests.get("delinquency_average"):
        facts["delinquency_average"] = f"{tests['delinquency_average']}%"
        facts["delinquency_limit"] = f"{tests['delinquency_limit']}%"
    return facts


FACT_WORDS = {
    "pool_balance": "outstanding pool balance", "eligible_pool": "eligible pool balance",
    "borrowing_base": "borrowing base", "advance_rate": "advance rate in force",
    "loans": "number of loans", "new_loans": "number of new loans this month",
    "charge_offs": "charge-offs this month",
    "delinquency_average": "delinquency ratio, rolling average",
    "delinquency_limit": "delinquency trigger level",
}


def template_commentary(state: dict[str, Any]) -> list[str]:
    tests = state.get("tests") or {}
    text = ["The pool stood at {{pool_balance}} across {{loans}} loans, with {{new_loans}} new "
            "loans and {{charge_offs}} of charge-offs in the month.",
            "The eligible pool was {{eligible_pool}} and the borrowing base {{borrowing_base}} "
            "at an advance rate of {{advance_rate}}."]
    if tests.get("delinquency_average"):
        word = "above" if tests.get("delinquency_breached") else "below"
        text.append("The rolling delinquency ratio was {{delinquency_average}}, " + word +
                    " the trigger of {{delinquency_limit}}.")
    return text


# A drafted paragraph about the request itself, rather than the facility, is not usable.
OFF_TOPIC = re.compile(r"placeholder|source document|no documents|not been (checked|verified)|"
                       r"were (not )?provided|supplied|as an ai|i (cannot|can't|don't)", re.I)


def draft_report(db: Session, sub: Submission, client: Client, persona: Persona) -> None:
    state = _state(sub)
    if not state.get("tests"):
        raise refuse("Run the month first", 422)
    facts = report_facts(state)
    tests = state["tests"]
    trigger_status = ("breached" if tests.get("delinquency_breached") else
                      "near the limit" if tests.get("delinquency_warning") else
                      "within limits")
    values = facts | {"trigger_status": trigger_status}
    paragraphs = template_commentary(state)
    drafted_by = "template"
    if client.ai_permitted:
        context = {k: FACT_WORDS[k] for k in facts}
        context["trigger_status"] = (
            "whether the delinquency trigger is within limits, near the limit or breached")
        result = _call(ai.draft_commentary, gateway_for(sub, client), context)
        usable = bool(result.paragraphs)
        for paragraph in result.paragraphs:
            _, unknown = checks.fill(paragraph, values)
            if unknown or OFF_TOPIC.search(paragraph):
                usable = False
        if usable:
            paragraphs, drafted_by = result.paragraphs, "ai"
    filled = [checks.fill(p, values)[0] for p in paragraphs]
    state["report"] = {"template": paragraphs, "text": filled, "drafted_by": drafted_by,
                       "facts": facts, "drafted_at": datetime.now(UTC).isoformat(),
                       "approvals": [], "released_at": None}
    _save(sub, state)
    log(db, sub, persona, "draft-report", f"Drafted the report ({'AI wording, figures filled '
        'by code' if drafted_by == 'ai' else 'code template'})")


def levels_for(client: Client) -> list[dict[str, Any]]:
    return [{"level": n, "role": LEVEL_ROLES[n], "title": LEVEL_TITLES[n]}
            for n in range(1, client.approval_levels + 1)]


def approve(db: Session, sub: Submission, facility: Facility, client: Client,
            persona: Persona) -> dict[str, Any]:
    state = _state(sub)
    report = state.get("report")
    if not report:
        raise refuse("Draft the report first", 422)
    if report.get("released_at"):
        raise refuse("This report is already released")
    if (state.get("validation") or {}).get("held"):
        raise refuse("The load is held by a blocking check. Resolve it first")
    waiting = [f["ref"] for f in state.get("findings", [])
               if not f.get("decision") or f["decision"].get("status") == "with_expert"]
    if waiting:
        raise refuse(f"Every finding needs a decision first: {waiting[0]}")
    levels = levels_for(client)
    done = report["approvals"]
    level = levels[len(done)]
    if persona.role != level["role"]:
        raise refuse(f"Level {level['level']} is for the {level['title'].lower()}", 403)
    if any(a["by"] == persona.name for a in done):
        raise refuse("Each approval level needs a different person")
    preparers = {e.actor for e in audit.events(db, sub.audit_id)
                 if e.type not in ("approve-report", "handoff", "handoff-done",
                                   "expert-decision", "release")}
    if level["level"] > 1 and persona.name in preparers:
        raise refuse("You prepared this month, so a second analyst has to approve it")
    done.append({"level": level["level"], "title": level["title"], "by": persona.name,
                 "at": datetime.now(UTC).isoformat()})
    handoffs.close_items(db, f"submission:{sub.id}:approve:", persona)
    released = len(done) == len(levels)
    if released:
        report["released_at"] = datetime.now(UTC).isoformat()
        state["provisional"] = False
        sub.status = "released"
        handoffs.open_item(db, f"submission:{sub.id}:released", subject(sub), sub.audit_id,
                           "notice", f"Report released: {facility.name}, {sub.period}",
                           "client", "/portal", persona, client_key=f"deal:{client.id}",
                           sla_hours=24 * 7)
    else:
        nxt = levels[len(done)]
        handoffs.open_item(db, f"submission:{sub.id}:approve:{nxt['level']}", subject(sub),
                           sub.audit_id, "approval", f"Approve {facility.name} report "
                           f"{sub.period}, level {nxt['level']}", nxt["role"],
                           f"/facilities/{facility.id}/submissions/{sub.id}", persona)
        sub.status = "in_approval"
    state["report"] = report
    _save(sub, state)
    log(db, sub, persona, "release" if released else "approve-report",
        f"{'Released' if released else 'Approved'} the report at level {level['level']} "
        f"({level['title']})")
    return report


def period_label(period: str) -> str:
    return date.fromisoformat(period + "-01").strftime("%B %Y")
