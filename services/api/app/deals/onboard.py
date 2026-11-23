"""A new onboarding case on uploaded documents, from intake to go-live.

The model classifies, reads terms with quotes, drafts rules and suggests a tape mapping. Code
finds every quote on its page, checks every figure against its quote, builds and validates the
rule set, runs the engine on the tape, builds the exception queue and holds the controls:
nothing goes to QC with an open exception, the reviewer cannot be anyone who prepared the case,
and only an approved case can go live. A client that does not permit AI gets no model calls:
the analyst classifies, enters terms with page references and writes rules, and code runs the
rest the same way.
"""

import copy
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

from engine import generic
from engine.rules import RuleSet
from engine.run import run as run_engine
from engine.validation import Rule, blocking, exact_duplicates, validate
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from app.deals import ai, audit, checks, files, handoffs
from app.deals import rules as deal_rules
from app.deals.guard import DealsGateway, ModelUnavailable, SpendCapReached
from app.deals.models import Client, ClientMapping, DealCase, Document, Facility, Submission
from app.personas import Persona
from app.pipeline.documents import PdfDocument
from app.pipeline.gateway import ModelError

TERM_INFO = {key: {"label": label, "tier": tier, "unit": unit}
             for key, label, tier, unit, _ in ai.TERMS}
REQUIRED_TERMS = ("commitment", "advance_rate")
STAGES = ("documents", "terms", "rules", "mapping", "validation", "exceptions", "qc", "review",
          "approved", "live")


def case_ref(case: DealCase) -> str:
    return f"ONB-{1000 + case.id}"


def subject(case: DealCase) -> str:
    return f"case:{case.id}"


def refuse(detail: str, status_code: int = 409) -> HTTPException:
    return HTTPException(status_code=status_code, detail=detail)


def _state(case: DealCase) -> dict[str, Any]:
    return copy.deepcopy(case.state or {})


def _save(case: DealCase, state: dict[str, Any]) -> None:
    case.state = state
    flag_modified(case, "state")


def active_docs(db: Session, case: DealCase) -> list[Document]:
    return list(db.scalars(select(Document).where(Document.case_id == case.id,
                                                  Document.status == "active")
                           .order_by(Document.id)))


def doc_names(docs: list[Document]) -> dict[int, str]:
    """A stable name per document for prompts and citations: its file name."""
    seen: dict[str, int] = {}
    names = {}
    for doc in docs:
        count = seen.get(doc.name, 0) + 1
        seen[doc.name] = count
        names[doc.id] = doc.name if count == 1 else f"{doc.name} (v{doc.version})"
    return names


def pdfs(docs: list[Document], kinds: tuple[str, ...] | None = None) -> dict[str, PdfDocument]:
    names = doc_names(docs)
    result = {}
    for doc in docs:
        if doc.name.lower().endswith(".pdf") and (kinds is None or doc.kind in kinds):
            document = files.pdf(doc)
            result[names[doc.id]] = PdfDocument(names[doc.id], document.path, document.pages)
    return result


def gateway(case: DealCase, client: Client, task: str = "deals") -> DealsGateway:
    if not client.ai_permitted:
        try:  # The refusal is part of the record, at zero cost.
            from app.agents.runlog import record_run

            record_run(task, f"deal:{client.id}", subject(case), 0, 0, 0.0, "refused", 0,
                       ref=case_ref(case))
        except Exception:  # noqa: BLE001 - logging must never stop a step
            pass
        raise refuse(f"{client.name} does not permit AI. Enter this step by hand")
    return DealsGateway(case_id=case.id, client_key=f"deal:{client.id}", ref=case_ref(case))


def _call(fn: Any, *args: Any) -> Any:
    try:
        return fn(*args)
    except SpendCapReached as error:
        raise refuse(str(error), 429) from error
    except ModelUnavailable as error:
        raise refuse("Live AI is not configured on this environment", 503) from error
    except ModelError as error:
        raise refuse(f"The model did not complete: {error}", 502) from error


def log(db: Session, case: DealCase, persona: Persona, kind: str, text: str,
        payload: dict[str, Any] | None = None) -> None:
    audit.append(db, case.audit_id, persona.name, kind, text, payload)


def tape_doc(docs: list[Document]) -> Document | None:
    tapes = [d for d in docs if d.kind == "loan_tape"]
    return tapes[-1] if tapes else None


# Intake


def classify(db: Session, case: DealCase, client: Client, persona: Persona) -> dict[str, Any]:
    docs = active_docs(db, case)
    if not docs:
        raise refuse("Upload the documents first", 422)
    names = doc_names(docs)
    result = _call(ai.classify, gateway(case, client, "deals_classify"),
                   {names[d.id]: files.preview(d) for d in docs})
    by_name = {item.document: item for item in result.documents}
    changed = 0
    for doc in docs:
        item = by_name.get(names[doc.id])
        if item is None:
            continue
        if doc.kind == "auto":
            doc.kind, doc.kind_source = item.kind, "ai"
            changed += 1
        state = _state(case)
        state.setdefault("classified", {})[str(doc.id)] = {
            "kind": item.kind, "title": item.title, "dated": checks.iso(item.dated),
            "effective": checks.iso(item.effective)}
        _save(case, state)
        if doc.effective_date is None and checks.iso(item.effective or item.dated):
            doc.effective_date = date.fromisoformat(checks.iso(item.effective or item.dated))
    log(db, case, persona, "classify", f"Classified {len(docs)} documents ({changed} by AI)")
    rebuild(db, case, client)
    return {"classified": len(docs)}


# Terms


def _term_from(extracted: ai.ExtractedTerm, documents: dict[str, PdfDocument]) -> dict[str, Any]:
    info = TERM_INFO[extracted.key]
    term: dict[str, Any] = {"key": extracted.key, **info, "source": "ai", "note": extracted.note,
                            "basis_days": extracted.basis_days,
                            "window_months": extracted.window_months,
                            "effective_from": checks.iso(extracted.effective_from),
                            "status": "proposed"}
    if not extracted.found or not extracted.value.strip():
        return {**term, "status": "missing", "value": None, "typed": None, "verified": False,
                "problem": "Not found in the documents", "confidence": None}
    typed, parse_problem = checks.parse_term(info["unit"], extracted.value)
    found = checks.cite(documents, extracted.document, extracted.quote)
    problem = None
    if found is None:
        problem = "Quote not found in the document"
    elif not checks.figures_in_quote(extracted.value, extracted.quote):
        problem = "A figure in the value is not in the quote"
    elif parse_problem:
        problem = parse_problem
    original = None
    if extracted.original and extracted.original.value:
        o_found = checks.cite(documents, extracted.original.document, extracted.original.quote)
        o_typed, _ = checks.parse_term(info["unit"], extracted.original.value)
        original = {"value": extracted.original.value, "typed": o_typed,
                    "doc_name": extracted.original.document, "quote": extracted.original.quote,
                    "page": o_found["page"] if o_found else None,
                    "rects": o_found["rects"] if o_found else [],
                    "verified": bool(o_found) and checks.figures_in_quote(
                        extracted.original.value, extracted.original.quote)}
        if not original["verified"] and problem is None:
            problem = "The amended-from value is not verified"
    confidence = "low" if problem else ("medium" if extracted.note else "high")
    return {**term, "value": extracted.value.strip(), "typed": typed if not problem else None,
            "doc_name": extracted.document, "clause": extracted.clause, "quote": extracted.quote,
            "page": found["page"] if found else None, "rects": found["rects"] if found else [],
            "verified": problem is None, "problem": problem, "confidence": confidence,
            "original": original}


def extract(db: Session, case: DealCase, client: Client, persona: Persona) -> dict[str, Any]:
    docs = active_docs(db, case)
    readable = [d for d in docs if d.kind in ("agreement", "amendment")]
    if not any(d.kind == "agreement" for d in readable):
        raise refuse("Upload the agreement, and set its type, before extracting terms", 422)
    documents = pdfs(readable)
    texts = {name: doc.body for name, doc in documents.items()}
    result = _call(ai.extract_terms, gateway(case, client, "deals_extract"), texts)
    state = _state(case)
    terms: dict[str, Any] = {}
    returned = {item.key: item for item in result.terms if item.key in TERM_INFO}
    for key in ai.TERM_KEYS:
        if key in returned:
            terms[key] = _term_from(returned[key], documents)
        else:
            terms[key] = {"key": key, **TERM_INFO[key], "source": "ai", "status": "missing",
                          "value": None, "typed": None, "verified": False, "confidence": None,
                          "problem": "Not returned by the model"}
    state["terms"] = terms
    state["extracted_at"] = datetime.now(UTC).isoformat()
    _save(case, state)
    verified = sum(t["verified"] for t in terms.values())
    log(db, case, persona, "extract", f"Extracted {len(terms)} terms: {verified} verified on "
        f"their page, {sum(t['status'] == 'missing' for t in terms.values())} not found")
    rebuild(db, case, client)
    return {"terms": len(terms), "verified": verified}


def manual_terms(db: Session, case: DealCase, client: Client, persona: Persona) -> None:
    """Without AI the analyst starts from the empty catalogue."""
    state = _state(case)
    if state.get("terms"):
        return
    state["terms"] = {key: {"key": key, **TERM_INFO[key], "source": "analyst", "status": "missing",
                            "value": None, "typed": None, "verified": False, "confidence": None,
                            "problem": "Enter from the documents"} for key in ai.TERM_KEYS}
    _save(case, state)
    log(db, case, persona, "manual-terms", "Started manual term entry: AI not permitted")
    rebuild(db, case, client)


def term_action(db: Session, case: DealCase, client: Client, persona: Persona, key: str,
                body: dict[str, Any]) -> dict[str, Any]:
    state = _state(case)
    terms = state.get("terms") or {}
    if key not in terms:
        raise refuse("Unknown term", 404)
    term = terms[key]
    action = body.get("action")
    reason = (body.get("reason") or "").strip()
    info = TERM_INFO[key]
    if action == "approve":
        if not term.get("verified") or term.get("typed") is None:
            raise refuse("Only a value verified on its page can be approved. Edit it with its "
                         "source first", 422)
        term.update(status="approved", approved_by=persona.name)
        text = f"Approved {info['label']}: {term['value']}"
    elif action in ("edit", "enter"):
        value = (body.get("value") or "").strip()
        document = body.get("document") or ""
        quote = (body.get("quote") or "").strip()
        page = body.get("page")
        errors: dict[str, str] = {}
        typed, problem = checks.parse_term(info["unit"], value)
        if problem:
            errors["value"] = problem
        if action == "edit" and not reason:
            errors["reason"] = "A reason is required"
        documents = pdfs(active_docs(db, case))
        if document not in documents:
            errors["document"] = "Choose the document it comes from"
        found = None
        if not errors:
            if quote:
                found = checks.cite(documents, document, quote)
                if found is None:
                    errors["quote"] = "This passage is not in the document"
                elif not checks.figures_in_quote(value, quote):
                    errors["value"] = "A figure in the value is not in the passage"
                elif page and found["page"] != int(page):
                    errors["page"] = f"The passage is on page {found['page']}"
            elif not page:
                errors["page"] = "Give the page, or the passage it appears in"
            elif not checks.on_page(documents, document, int(page), value):
                errors["value"] = f"This value is not on page {page} of {document}"
        if errors:
            raise HTTPException(status_code=422, detail={"message": "Check the entry",
                                                         "fields": errors})
        before = term.get("value")
        page_no = found["page"] if found else int(page)
        term.update(value=value, typed=typed, doc_name=document, quote=quote or None,
                    page=page_no, rects=found["rects"] if found else [], verified=True,
                    problem=None, confidence="manual" if action == "enter" else term.get(
                        "confidence"), source="analyst", status="approved",
                    approved_by=persona.name, clause=body.get("clause") or term.get("clause"),
                    effective_from=checks.iso(body.get("effective_from")) or (
                        term.get("effective_from") if action == "edit" else None),
                    basis_days=body.get("basis_days", term.get("basis_days")),
                    window_months=body.get("window_months", term.get("window_months")))
        if action == "edit":
            term["edited"] = {"from": before, "reason": reason, "by": persona.name}
            if term.get("original") and term.get("effective_from") is None:
                term["original"] = None
        text = (f"Edited {info['label']} from {before} to {value}" if action == "edit"
                else f"Entered {info['label']}: {value} ({document} p.{page_no})")
    elif action == "absent":
        if not reason:
            raise HTTPException(status_code=422, detail={"message": "Check the entry",
                                                         "fields": {"reason": "Say why"}})
        if key in REQUIRED_TERMS:
            raise refuse(f"{info['label']} is needed to calculate the borrowing base", 422)
        term.update(status="absent", value=None, typed=None, verified=True, problem=None,
                    approved_by=persona.name, absent_reason=reason)
        text = f"Confirmed {info['label']} is not in the documents"
    else:
        raise refuse("Unknown action", 422)
    terms[key] = term
    state["terms"] = terms
    _save(case, state)
    log(db, case, persona, f"term-{action}", text, {"term": key, "reason": reason or None,
                                                    "refs": [f"term:{key}"]})
    rebuild(db, case, client)
    return term


def approve_verified_terms(db: Session, case: DealCase, client: Client,
                           persona: Persona) -> int:
    state = _state(case)
    names = []
    for term in (state.get("terms") or {}).values():
        if term["status"] == "proposed" and term.get("verified") and term.get("typed") is not None \
                and term.get("confidence") == "high" and term["tier"] > 1:
            term.update(status="approved", approved_by=persona.name)
            names.append(term["label"])
    _save(case, state)
    if names:
        log(db, case, persona, "term-bulk", f"Approved {len(names)} verified Tier 2 and 3 terms")
    rebuild(db, case, client)
    return len(names)


def terms_ready(state: dict[str, Any]) -> bool:
    terms = state.get("terms") or {}
    return bool(terms) and all(t["status"] in ("approved", "absent") for t in terms.values()
                               if t["tier"] == 1) and all(
        terms.get(k, {}).get("status") == "approved" for k in REQUIRED_TERMS)


# Rules


def _rule_row(kind: str, index: int, draft: dict[str, Any]) -> dict[str, Any]:
    prefix = "E" if kind == "eligibility" else "C"
    return {"id": f"{prefix}{index}", "source": draft.pop("source", "ai"), **draft}


def draft_rules(db: Session, case: DealCase, client: Client, persona: Persona) -> dict[str, Any]:
    state = _state(case)
    if not terms_ready(state):
        raise refuse("Approve the Tier 1 terms first; rule thresholds come from them", 422)
    docs = active_docs(db, case)
    documents = pdfs(docs, ("agreement", "amendment"))
    mapped = list(generic.FIELDS)
    result = _call(ai.draft_rules, gateway(case, client, "deals_rules"),
                   {name: doc.body for name, doc in documents.items()}, mapped)
    eligibility = [deal_rules.verify_rule(_rule_row("eligibility", i, {
        "ref": r.ref, "plain_english": r.plain_english, "clause_text": r.clause_text,
        "document": r.document, "test": r.test.model_dump()}), documents, False)
        for i, r in enumerate(result.eligibility, start=1)]
    concentration = [deal_rules.verify_rule(_rule_row("concentration", i, {
        "ref": r.ref, "plain_english": r.plain_english, "clause_text": r.clause_text,
        "document": r.document, "limit_pct": r.limit_pct, "group_by": r.group_by,
        "where": r.where.model_dump() if r.where else None,
        "effective_from": checks.iso(r.effective_from)}), documents, True)
        for i, r in enumerate(result.concentration, start=1)]
    for rule in eligibility:
        rule["describe"] = deal_rules.describe_rule(rule, False)
    for rule in concentration:
        rule["describe"] = deal_rules.describe_rule(rule, True)
    state["rules"] = {"eligibility": eligibility, "concentration": concentration,
                      "not_codable": result.not_codable, "status": "draft", "version": 1}
    _save(case, state)
    bad = sum(not r["verified"] for r in eligibility + concentration)
    log(db, case, persona, "draft-rules", f"Drafted {len(eligibility)} eligibility and "
        f"{len(concentration)} concentration rules; {bad} failed code checks")
    rebuild(db, case, client)
    return state["rules"]


def rule_action(db: Session, case: DealCase, client: Client, persona: Persona,
                body: dict[str, Any]) -> dict[str, Any]:
    state = _state(case)
    rules = state.get("rules") or {"eligibility": [], "concentration": [], "not_codable": [],
                                   "status": "draft", "version": 1}
    action = body.get("action")
    if rules.get("status") == "approved" and action != "reopen":
        raise refuse("The rules are approved. Reopen them to change a rule")
    if action == "approve":
        if not terms_ready(state):
            raise refuse("Approve the Tier 1 terms first", 422)
        bad = [r["id"] for r in rules["eligibility"] + rules["concentration"] if not r["verified"]]
        if bad:
            raise refuse(f"Fix or remove the rules that failed code checks: {', '.join(bad)}",
                         422)
        if not rules["eligibility"]:
            raise refuse("There are no eligibility rules", 422)
        try:
            ruleset = deal_rules.build_ruleset(state["terms"], rules, rules.get("version", 1))
        except (ValueError, KeyError) as error:
            raise refuse(f"The engine refused the rule set: {error}", 422) from error
        rules.update(status="approved", approved_by=persona.name, digest=ruleset.digest)
        text = f"Approved rule set v{rules.get('version', 1)}: {len(rules['eligibility'])} " \
               f"eligibility, {len(rules['concentration'])} concentration"
    elif action == "reopen":
        rules.update(status="draft", version=rules.get("version", 1) + 1)
        text = "Reopened the rule set for changes"
    elif action in ("add", "edit"):
        kind = body.get("kind")
        if kind not in ("eligibility", "concentration"):
            raise refuse("Choose eligibility or concentration", 422)
        reason = (body.get("reason") or "").strip()
        if action == "edit" and not reason:
            raise HTTPException(status_code=422, detail={"message": "Check the rule",
                                                         "fields": {"reason": "A reason is "
                                                                    "required"}})
        documents = pdfs(active_docs(db, case), ("agreement", "amendment"))
        rows = rules[kind]
        if action == "edit":
            existing = next((r for r in rows if r["id"] == body.get("id")), None)
            if existing is None:
                raise refuse("Unknown rule", 404)
            draft = {**existing, **{k: v for k, v in body.get("rule", {}).items()
                                    if k in ("plain_english", "clause_text", "document", "ref",
                                             "test", "limit_pct", "group_by", "where",
                                             "effective_from")}}
            draft["source"] = "analyst"
        else:
            numbers = [int(r["id"][1:]) for r in rows] or [0]
            draft = _rule_row(kind, max(numbers) + 1, {**body.get("rule", {}),
                                                         "source": "analyst"})
        checked = deal_rules.verify_rule(draft, documents, kind == "concentration")
        if not checked["verified"]:
            raise HTTPException(status_code=422, detail={"message": checked["problem"],
                                                         "fields": {"rule": checked["problem"]}})
        checked["describe"] = deal_rules.describe_rule(checked, kind == "concentration")
        if action == "edit":
            checked["edited"] = {"reason": reason, "by": persona.name}
            rules[kind] = [checked if r["id"] == checked["id"] else r for r in rows]
            text = f"Edited rule {checked['id']}: {checked['describe']}"
        else:
            rules[kind] = [*rows, checked]
            text = f"Added rule {checked['id']}: {checked['describe']}"
    elif action == "remove":
        kind = body.get("kind", "eligibility")
        reason = (body.get("reason") or "").strip()
        if not reason:
            raise HTTPException(status_code=422, detail={"message": "Check the rule",
                                                         "fields": {"reason": "Say why"}})
        rules[kind] = [r for r in rules.get(kind, []) if r["id"] != body.get("id")]
        text = f"Removed rule {body.get('id')}"
    else:
        raise refuse("Unknown action", 422)
    state["rules"] = rules
    _save(case, state)
    log(db, case, persona, f"rules-{action}", text, {"reason": body.get("reason"),
                                                      "refs": [f"rule:{body.get('id')}"]})
    rebuild(db, case, client)
    return rules


# Mapping


def stored_mapping(db: Session, client: Client, headers: list[str]) -> ClientMapping | None:
    return db.scalars(select(ClientMapping).where(
        ClientMapping.client_id == client.id,
        ClientMapping.signature == files.signature(headers))).first()


def suggest_columns(db: Session, client: Client, headers: list[str], rows: list[dict[str, str]],
                    gw: Any | None) -> tuple[dict[str, str | None], dict[str, str], str]:
    """Stored mapping for the same layout first, then the model (if permitted) for a new
    layout, else name matching. Client overrides always win."""
    stored = stored_mapping(db, client, headers)
    if stored is not None:
        columns, statuses, source = dict(stored.columns), dict(stored.status_map), "stored"
    else:
        # Reuse what is known from the client's other layouts for unchanged columns.
        known: dict[str, str] = {}
        known_status: dict[str, str] = {}
        for other in db.scalars(select(ClientMapping).where(ClientMapping.client_id == client.id)
                                .order_by(ClientMapping.updated_at)):
            known.update({c: f for c, f in other.columns.items() if f})
            known_status.update(other.status_map)
        unknown = [h for h in headers if h not in known]
        columns = {h: known.get(h) for h in headers}
        statuses = dict(known_status)
        source = "stored" if not unknown else ("ai" if gw is not None else "rules")
        if unknown:
            if gw is not None:
                status_col = next((h for h in headers if known.get(h) == "status"), None)
                values = sorted({r.get(status_col or "", "") for r in rows} - {""})
                if status_col is None:
                    values = []
                result = _call(ai.map_tape, gw, headers, rows[:5], values)
                for match in result.columns:
                    if match.column in unknown:
                        columns[match.column] = match.field if match.field in generic.FIELDS \
                            else None
                statuses.update({s.value: s.status for s in result.statuses})
            else:
                guessed = checks.heuristic_mapping(headers)
                taken = {f for f in columns.values() if f}
                for header in unknown:
                    field = guessed.get(header)
                    columns[header] = field if field not in taken else None
        status_col = next((h for h, f in columns.items() if f == "status"), None)
        if status_col:
            values = sorted({r.get(status_col, "") for r in rows} - {""})
            missing = [v for v in values if v not in statuses]
            if missing:
                statuses.update(checks.heuristic_statuses(missing))
    for field, column in (client.master_field_overrides or {}).items():
        if column in columns and field in generic.FIELDS:
            for header, mapped in list(columns.items()):
                if mapped == field and header != column:
                    columns[header] = None
            columns[column] = field
    return columns, statuses, source


def suggest_mapping(db: Session, case: DealCase, client: Client, persona: Persona
                    ) -> dict[str, Any]:
    docs = active_docs(db, case)
    tape = tape_doc(docs)
    if tape is None:
        raise refuse("Upload the loan tape, and set its type, first", 422)
    headers, rows = files.table(tape)
    if not rows:
        raise refuse("The tape has no rows", 422)
    stored = stored_mapping(db, client, headers)
    gw = None if stored is not None or not client.ai_permitted \
        else gateway(case, client, "deals_map")
    columns, statuses, source = suggest_columns(db, client, headers, rows, gw)
    state = _state(case)
    state["mapping"] = {"tape_doc": tape.id, "signature": files.signature(headers),
                        "headers": headers, "columns": columns, "status_map": statuses,
                        "source": source, "confirmed": False,
                        "checks": checks.check_mapping(columns, rows, statuses),
                        "status_values": sorted({r.get(next((h for h, f in columns.items()
                                                             if f == "status"), ""), "")
                                                 for r in rows} - {""})}
    _save(case, state)
    words = {"stored": "the client's stored mapping", "ai": "AI suggestions",
             "rules": "name matching (AI not permitted)"}[source]
    log(db, case, persona, "suggest-mapping", f"Mapped {len(headers)} columns from {words}")
    rebuild(db, case, client)
    return state["mapping"]


def confirm_mapping(db: Session, client: Client, headers: list[str], rows: list[dict[str, str]],
                    columns: dict[str, str | None], statuses: dict[str, str]
                    ) -> list[dict[str, Any]]:
    """Check an analyst's mapping and store it for the client. Refuses one that fails."""
    columns = {h: (columns.get(h) or None) for h in headers}
    problems = [c for c in checks.check_mapping(columns, rows, statuses) if c["problem"]]
    if problems:
        raise HTTPException(status_code=422, detail={
            "message": "The mapping does not fit the tape",
            "fields": {(p["column"] or p["field"]): p["problem"] for p in problems}})
    stored = stored_mapping(db, client, headers)
    if stored is None:
        stored = ClientMapping(client_id=client.id, signature=files.signature(headers),
                               headers=headers, columns=columns, status_map=statuses)
        db.add(stored)
    else:
        stored.columns, stored.status_map = columns, statuses
    db.flush()
    return checks.check_mapping(columns, rows, statuses)


def mapping_action(db: Session, case: DealCase, client: Client, persona: Persona,
                   body: dict[str, Any]) -> dict[str, Any]:
    state = _state(case)
    mapping = state.get("mapping")
    if not mapping:
        raise refuse("Suggest a mapping first", 422)
    tape = db.get(Document, mapping["tape_doc"])
    headers, rows = files.table(tape)
    columns = body.get("columns") or mapping["columns"]
    statuses = body.get("status_map") or mapping["status_map"]
    changed = [h for h in headers if (columns.get(h) or None) != mapping["columns"].get(h)]
    mapping["checks"] = confirm_mapping(db, client, headers, rows, columns, statuses)
    mapping.update(columns={h: columns.get(h) or None for h in headers}, status_map=statuses,
                   confirmed=True, confirmed_by=persona.name)
    state["mapping"] = mapping
    _save(case, state)
    log(db, case, persona, "confirm-mapping", f"Confirmed the tape mapping ({len(changed)} "
        "columns changed by the analyst) and stored it for the client")
    rebuild(db, case, client)
    return mapping


# Validation and the engine run


def mapped_rows(rows: list[dict[str, str]], columns: dict[str, str | None]
                ) -> list[dict[str, str]]:
    return [{field: row.get(col, "") for col, field in columns.items() if field}
            for row in rows]


def validation_rules(fields: set[str], used: set[str]) -> list[Rule]:
    rules = []
    for name in sorted(set(generic.REQUIRED) | used):
        if name in fields:
            rules.append(Rule(f"MD-{name}", "missing_data", "blocking",
                              f"{name} is present on every row", name))
    rules.append(Rule("DUP-loan_id", "duplicates", "blocking", "Each loan appears once",
                      "loan_id"))
    for name in sorted(fields):
        kind = generic.FIELDS[name][0]
        if kind in ("money", "rate", "int", "date"):
            word = {"money": "number", "rate": "number", "int": "integer", "date": "date"}[kind]
            severity = "blocking" if name in used or name in generic.REQUIRED else "warning"
            rules.append(Rule(f"DT-{name}", "data_types", severity, f"{name} is a {word}", name,
                              word))
    if {"current_balance", "original_balance"} <= fields:
        rules.append(Rule("LG-balance", "logical", "warning",
                          "Current balance is not above the original balance",
                          kind="balance_not_above_original"))
    if {"origination_date", "maturity_date"} <= fields:
        rules.append(Rule("LG-maturity", "logical", "warning",
                          "Maturity is after origination", kind="matures_after_origination"))
    return rules


def run_validation(rows: list[dict[str, str]], status_map: dict[str, str], ruleset: RuleSet,
                   used: set[str], as_of: date, excluded: list[str],
                   delinquency_days: int | None) -> dict[str, Any]:
    """Validate a mapped tape, then run the engine on the rows that may be loaded."""
    fields = set(rows[0]) if rows else set()
    kept, collapsed = exact_duplicates(rows, "loan_id")
    results = validate(kept, validation_rules(fields, used), "loan_id")
    statuses = sorted({r.get("status", "") for r in kept} - {""})
    unknown = [s for s in statuses if status_map.get(s) not in generic.STATUSES]
    held = blocking(results)
    excluded_set = set(excluded)
    open_blocks = [r for r in held if {f.key for f in r.failures} - excluded_set]
    checks_view = [{"id": r.rule.id, "family": r.rule.family, "severity": r.rule.severity,
                    "text": r.rule.text, "checked": r.checked, "failed": len(r.failures),
                    "examples": [{"key": f.key, "value": f.value, "row": f.row}
                                 for f in r.failures[:8]],
                    "keys": sorted({f.key for f in r.failures})[:500]}
                   for r in results]
    view: dict[str, Any] = {"as_of": as_of.isoformat(), "rows": len(rows),
                            "collapsed_duplicates": collapsed, "checks": checks_view,
                            "unknown_statuses": unknown, "held": bool(open_blocks or unknown),
                            "excluded": sorted(excluded_set)}
    if open_blocks or unknown:
        return view
    loaded = [r for r in kept if r["loan_id"] not in excluded_set]
    loans = [generic.coerce(r, status_map) for r in loaded]
    result = run_engine(loans, ruleset, as_of, 0)
    base = min(result.borrowing_base_cents, ruleset.facility_limit_cents)
    view["engine"] = {
        "loans": len(loans), "gross_pool_cents": result.gross_pool_cents,
        "eligible_pool_cents": result.eligible_pool_cents,
        "eligible_loans": len(result.eligible_loan_ids),
        "excess_cents": result.excess_cents, "advance_rate_pct": str(result.advance_rate_pct),
        "advance_rate_source": result.advance_rate_source, "reserve_cents": result.reserve_cents,
        "borrowing_base_cents": result.borrowing_base_cents,
        "availability_cents": base, "facility_limit_cents": ruleset.facility_limit_cents,
        "ruleset_digest": result.ruleset_digest, "tape_digest": result.tape_digest,
        "run_digest": result.digest,
        "rules": [{"id": rid, "status": o.status, "failed": len(o.failed_loan_ids),
                   "failed_cents": o.failed_cents, "loans": list(o.failed_loan_ids[:200]),
                   "reason": o.reason} for rid, o in result.rules.items()],
        "concentrations": [{"id": rid, "active": c.active, "limit_pct": str(c.limit_pct),
                            "limit_cents": c.limit_cents, "largest": c.largest,
                            "largest_cents": c.largest_cents, "share_pct": str(c.share_pct),
                            "excess_cents": c.excess_cents}
                           for rid, c in result.concentrations.items()],
        "delinquency_pct": str(generic.delinquency_ratio(loans, delinquency_days))
        if delinquency_days else None,
        "metrics": {k: str(v) for k, v in generic.metrics(loans).items()},
        "independent_eligible_cents": sum(
            r_loan["current_balance"] or 0 for r_loan in loans
            if r_loan["loan_id"] not in result.failed_rules_by_loan),
    }
    return view


def case_as_of(db: Session, case: DealCase, tape: Document) -> date:
    state = case.state or {}
    if state.get("as_of"):
        return date.fromisoformat(state["as_of"])
    if tape.effective_date:
        return tape.effective_date
    classified = (state.get("classified") or {}).get(str(tape.id), {})
    if classified.get("dated"):
        return date.fromisoformat(classified["dated"])
    first = datetime.now(UTC).date().replace(day=1)
    return first - timedelta(days=1)


def ruleset_of(state: dict[str, Any]) -> RuleSet:
    return deal_rules.build_ruleset(state["terms"], state["rules"],
                                    state["rules"].get("version", 1))


def validate_case(db: Session, case: DealCase, client: Client, persona: Persona,
                  as_of: str | None = None) -> dict[str, Any]:
    state = _state(case)
    if (state.get("rules") or {}).get("status") != "approved":
        raise refuse("Approve the rule set first", 422)
    mapping = state.get("mapping") or {}
    if not mapping.get("confirmed"):
        raise refuse("Confirm the tape mapping first", 422)
    if as_of:
        if checks.iso(as_of) is None:
            raise HTTPException(status_code=422, detail={"message": "Check the date",
                                                         "fields": {"as_of": "Not a date"}})
        state["as_of"] = checks.iso(as_of)
        _save(case, state)
    tape = db.get(Document, mapping["tape_doc"])
    _, rows = files.table(tape)
    trigger = state["terms"].get("delinquency_trigger") or {}
    view = run_validation(mapped_rows(rows, mapping["columns"]), mapping["status_map"],
                          ruleset_of(state), deal_rules.rule_fields(state["rules"]),
                          case_as_of(db, case, tape), state.get("excluded_rows", []),
                          (trigger.get("basis_days") or 60) if trigger.get("typed") else None)
    state = _state(case)
    state["validation"] = view
    state["client_model"] = compare_client_model(db, case, state)
    _save(case, state)
    engine_view = view.get("engine")
    log(db, case, persona, "validate", (
        f"Ran the engine on {engine_view['loans']:,} loans: borrowing base US$"
        f"{engine_view['borrowing_base_cents'] / 100:,.2f}") if engine_view else
        "Validation held the load: resolve the blocking checks", {"digest": (engine_view or {})
                                                                  .get("run_digest")})
    rebuild(db, case, client)
    return view


def compare_client_model(db: Session, case: DealCase, state: dict[str, Any]
                         ) -> list[dict[str, Any]]:
    """The client's own model against the approved terms, cell by cell. Code only."""
    model = next((d for d in active_docs(db, case) if d.kind == "client_model"
                  and d.kind_source != "oxane" and d.name.lower().endswith(".xlsx")), None)
    if model is None:
        return []
    terms = state.get("terms") or {}
    as_of = (state.get("validation") or {}).get("as_of")
    rate = terms.get("advance_rate", {})
    rate_now = rate.get("typed")
    if rate.get("original") and rate.get("effective_from") and as_of and \
            as_of < rate["effective_from"]:
        rate_now = rate["original"].get("typed")
    wanted = {"advance rate": ("advance_rate", rate_now, "pct"),
              "reserve": ("reserve", (terms.get("reserve") or {}).get("typed"), "pct"),
              "facility amount": ("commitment", (terms.get("commitment") or {}).get("typed"),
                                  "money"),
              "delinquency trigger": ("delinquency_trigger",
                                      (terms.get("delinquency_trigger") or {}).get("typed"),
                                      "pct")}
    found = []
    for sheet, cell, label, value in files.workbook_cells(model):
        for words, (key, agreed, unit) in wanted.items():
            if words in label.lower() and agreed is not None:
                model_value = Decimal(str(value))
                if unit == "pct" and model_value <= 1:
                    model_value *= 100
                agreed_value = Decimal(str(agreed))
                found.append({"term": key, "label": label, "cell": f"{sheet}!{cell}",
                              "model": str(model_value.quantize(Decimal("0.01"))),
                              "agreed": str(agreed_value.quantize(Decimal("0.01"))),
                              "differs": model_value.quantize(Decimal("0.01"))
                              != agreed_value.quantize(Decimal("0.01")),
                              "document": model.name})
    return found


# Exceptions


def _exc(key: str, kind: str, severity: str, title: str, detail: str, suggested: str,
         link: str, auto: bool = False) -> dict[str, Any]:
    return {"key": key, "type": kind, "severity": severity, "title": title, "detail": detail,
            "suggested": suggested, "link": link, "auto_resolved": auto}


def _wanted_exceptions(db: Session, case: DealCase, state: dict[str, Any]) -> list[dict[str, Any]]:
    docs = active_docs(db, case)
    items = []
    kinds = {d.kind for d in docs}
    if "agreement" not in kinds:
        items.append(_exc("doc:agreement", "Document", "blocking", "No agreement in the pack",
                          "Terms and rules come from the agreement.",
                          "Upload the executed agreement", "documents"))
    if "loan_tape" not in kinds:
        items.append(_exc("doc:tape", "Document", "blocking", "No loan tape in the pack",
                          "The engine runs on the loan tape.", "Upload the loan tape",
                          "documents"))
    if "auto" in kinds:
        items.append(_exc("doc:types", "Document", "blocking", "Documents without a type",
                          "Classify the documents or set each type.", "Run classification",
                          "documents"))
    for term in (state.get("terms") or {}).values():
        done = term["status"] in ("approved", "absent")
        label = term["label"]
        if term["status"] == "missing" or (term["status"] == "absent"):
            sev = "blocking" if term["tier"] == 1 else "warning"
            items.append(_exc(f"term:missing:{term['key']}", "Term", sev,
                              f"{label} not found in the documents",
                              term.get("absent_reason") or "No passage in the agreement or "
                              "amendments states it. Nothing has been filled in.",
                              "Confirm it is absent, enter it with its page, or query the client",
                              "terms", done))
        elif term.get("problem"):
            items.append(_exc(f"term:unverified:{term['key']}", "Term", "blocking",
                              f"{label}: {term['problem'].lower()}",
                              f"Read as {term.get('value')}. {term.get('quote') or ''}"[:300],
                              "Edit the value with its source, or query the client", "terms",
                              done))
        elif term.get("confidence") == "medium":
            items.append(_exc(f"term:low:{term['key']}", "Term", "warning",
                              f"{label}: check the reading", term.get("note") or "",
                              "Approve, edit or escalate", "terms", done))
        if term.get("original") and term.get("effective_from"):
            items.append(_exc(f"term:amended:{term['key']}", "Term", "info",
                              f"{label} amended from {term['original']['value']} to "
                              f"{term.get('value')} from {term['effective_from']}",
                              f"Source: {term['original'].get('doc_name')} p."
                              f"{term['original'].get('page')} and {term.get('doc_name')} p."
                              f"{term.get('page')}", "Approve the amended value", "terms", done))
    rules = state.get("rules") or {}
    for rule in rules.get("eligibility", []) + rules.get("concentration", []):
        if not rule.get("verified"):
            items.append(_exc(f"rule:{rule['id']}", "Rule", "blocking",
                              f"Rule {rule['id']} failed code checks: {rule.get('problem')}",
                              rule.get("clause_text", "")[:300], "Edit or remove the rule",
                              "rules"))
    for index, text in enumerate(rules.get("not_codable", []), start=1):
        items.append(_exc(f"rule:uncoded:{index}", "Rule", "warning",
                          f"Criterion not codable on the tape: {text}"[:200],
                          "The tape has no field to test this. It needs a client confirmation or "
                          "a servicer certificate.", "Query the client or escalate", "rules"))
    mapping = state.get("mapping") or {}
    for item in mapping.get("checks", []):
        if item.get("problem") and not mapping.get("confirmed"):
            items.append(_exc(f"map:{item.get('column') or item.get('field')}", "Mapping",
                              "blocking", f"{item.get('column') or item.get('field')}: "
                              f"{item['problem']}", f"Field {item.get('field') or '-'}",
                              "Correct the mapping", "mapping"))
    validation = state.get("validation") or {}
    excluded = set(state.get("excluded_rows", []))
    for check in validation.get("checks", []):
        if not check["failed"]:
            continue
        keys = set(check.get("keys", []))
        resolved = check["severity"] == "blocking" and keys <= excluded
        items.append(_exc(f"val:{check['id']}", "Data", check["severity"],
                          f"{check['text']}: {check['failed']} rows fail",
                          ", ".join(f"{e['key']} (row {e['row']}: {e['value'] or 'blank'})"
                                    for e in check["examples"][:4]),
                          "Exclude the affected rows from the load" if check["severity"]
                          == "blocking" else "Accept and log", "validation", resolved))
    for status in validation.get("unknown_statuses", []):
        items.append(_exc(f"val:status:{status}", "Data", "blocking",
                          f"Status {status} has no standard status", "Map it on the Mapping tab",
                          "Correct the mapping", "mapping"))
    built = state.get("built_model")
    if built:
        # Oxane built the model because the client has none: the client validates it through
        # the query cycle like any other question, and the clock on their wait runs the same.
        validation = built.get("validation") or {}
        items.append(_exc(f"model:validation:v{built['version']}", "Client model", "blocking",
                          f"Client model v{built['version']} built by Oxane: client to validate",
                          f"{built['name']}, built from the approved terms and rule set "
                          f"v{built['rules_version']}. "
                          + ("The client confirmed it." if validation.get("outcome") == "confirmed"
                             else "The client asked for changes: " + validation["text"]
                             if validation.get("outcome") == "changes" else
                             "Send it to the client to confirm or change."),
                          "Query the client: send the model for validation", "exceptions"))
    for diff in state.get("client_model", []):
        if diff["differs"]:
            items.append(_exc(f"model:{diff['term']}", "Client model", "warning",
                              f"Client model {diff['label'].lower()} {diff['model']} against "
                              f"{diff['agreed']} in the agreement",
                              f"{diff['document']} {diff['cell']}",
                              "Query the client", "exceptions"))
    return items


def rebuild(db: Session, case: DealCase, client: Client) -> None:
    """Rebuild the queue from the current state, keeping each item's reference and outcome."""
    state = _state(case)
    existing = {e["key"]: e for e in state.get("exceptions", [])}
    counter = state.get("exception_counter", 0)
    result = []
    for item in _wanted_exceptions(db, case, state):
        before = existing.get(item["key"])
        if before is None:
            counter += 1
            ref = f"EXC-{1000 + case.id}-{counter:02d}"
            status = "resolved" if item["auto_resolved"] else "open"
            result.append({**item, "ref": ref, "status": status, "history": [],
                           "raised_at": datetime.now(UTC).isoformat()})
        else:
            status = before["status"]
            if item["auto_resolved"] and status in ("open",):
                status = "resolved"
            if not item["auto_resolved"] and before["status"] == "resolved" and \
                    before.get("resolved_by_code"):
                status = "open"
            result.append({**before, **item, "status": status,
                           "resolved_by_code": item["auto_resolved"]})
    # Items whose cause has gone (a term fixed, a file replaced) close themselves.
    for key, before in existing.items():
        if key not in {r["key"] for r in result} and before["status"] not in ("resolved",
                                                                              "accepted"):
            result.append({**before, "status": "resolved", "resolved_by_code": True,
                           "detail": before["detail"]})
    state["exceptions"] = result
    state["exception_counter"] = counter
    _save(case, state)
    case.stage = stage_of(db, case, state)


OUTCOMES = {"accept": "accepted", "query": "with_client", "escalate": "with_expert"}


def work_exception(db: Session, case: DealCase, client: Client, persona: Persona, ref: str,
                   body: dict[str, Any]) -> dict[str, Any]:
    state = _state(case)
    item = next((e for e in state.get("exceptions", []) if e["ref"] == ref), None)
    if item is None:
        raise refuse("Unknown exception", 404)
    action = body.get("action")
    note = (body.get("note") or "").strip()
    if action not in ("accept", "query", "escalate", "close"):
        raise refuse("Unknown action", 422)
    if action in ("query", "escalate", "accept") and not note:
        raise HTTPException(status_code=422, detail={"message": "Add a note",
                                                     "fields": {"note": "A note is required"}})
    if item["status"] in ("accepted", "resolved"):
        raise refuse("This exception is already closed")
    subject_link = f"/deals/cases/{case.id}/exceptions"
    model_check = item["key"].startswith("model:validation:")
    if model_check and action in ("accept", "escalate"):
        raise refuse("Only the client can validate the model Oxane built: query the client")
    outcome = ((state.get("built_model") or {}).get("validation") or {}).get("outcome")
    if model_check and action == "close" and outcome != "confirmed":
        raise refuse("The client asked for changes: rebuild the model and send the new version")
    if action == "accept":
        if item["severity"] == "blocking" and item["type"] == "Data":
            check_id = item["key"].split(":", 1)[1]
            check = next((c for c in (state.get("validation") or {}).get("checks", [])
                          if c["id"] == check_id), None)
            keys = set((check or {}).get("keys", []))
            state["excluded_rows"] = sorted(set(state.get("excluded_rows", [])) | keys)
            note = f"{note} (excluded {len(keys)} rows)"
        elif item["severity"] == "blocking" and item["type"] in ("Term", "Rule", "Mapping",
                                                                  "Document"):
            raise refuse(f"Fix this on the {item['link'].title()} tab; it closes itself when "
                         "fixed")
        item["status"] = "accepted"
        handoffs.close_items(db, f"case:{case.id}:exc:{ref}", persona)
    elif action == "close":
        if item["status"] not in ("answered", "decided"):
            raise refuse("Only an answered query or an expert decision can be closed")
        item["status"] = "accepted"
        handoffs.close_items(db, f"case:{case.id}:exc:{ref}", persona)
    elif action == "query":
        item["status"] = "with_client"
        item["query"] = {"text": note, "sent_at": datetime.now(UTC).isoformat(),
                         "by": persona.name}
        if model_check:
            built = state["built_model"]
            item["query"]["model_doc"] = built["doc_id"]
            built.update(status="with_client", sent_at=item["query"]["sent_at"],
                         sent_by=persona.name, ref=ref)
            state["built_model"] = built
        handoffs.open_item(db, f"case:{case.id}:exc:{ref}:query", subject(case), case.audit_id,
                           "query", f"Query on {case.facility_name}: {item['title']}"[:200],
                           "client", "/portal", persona, detail=note,
                           client_key=f"deal:{client.id}", sla_hours=48)
    else:
        item["status"] = "with_expert"
        item["escalation"] = {"text": note, "at": datetime.now(UTC).isoformat(),
                              "by": persona.name}
        handoffs.open_item(db, f"case:{case.id}:exc:{ref}:expert", subject(case),
                           case.audit_id, "expert", f"Expert judgement: {item['title']}"[:200],
                           "expert", subject_link, persona, detail=note)
    item["history"].append({"at": datetime.now(UTC).isoformat(), "by": persona.name,
                            "action": action, "note": note})
    state["exceptions"] = [item if e["ref"] == ref else e for e in state["exceptions"]]
    _save(case, state)
    log(db, case, persona, f"exception-{action}", f"{ref}: {OUTCOMES.get(action, 'closed')} "
        f"- {item['title']}", {"refs": [ref], "reason": note})
    if action == "accept" and item["type"] == "Data":
        validate_case(db, case, client, persona)
    rebuild(db, case, client)
    return item


def answer(db: Session, case: DealCase, client: Client, persona: Persona, ref: str,
           text: str, role: str, outcome: str | None = None) -> dict[str, Any]:
    """A client answers a query, or an expert records a decision. Both go back to the analyst.
    On the model Oxane built, the client either confirms it or asks for changes."""
    state = _state(case)
    item = next((e for e in state.get("exceptions", []) if e["ref"] == ref), None)
    want = "with_client" if role == "client" else "with_expert"
    if item is None or item["status"] != want:
        raise refuse("Nothing is waiting on you for this item", 404)
    if not text.strip():
        raise HTTPException(status_code=422, detail={"message": "Write the answer",
                                                     "fields": {"text": "Required"}})
    if item["key"].startswith("model:validation:"):
        if outcome not in ("confirmed", "changes"):
            raise HTTPException(status_code=422, detail={
                "message": "Confirm the model or ask for changes",
                "fields": {"outcome": "Confirm or ask for changes"}})
        built = state["built_model"]
        built["validation"] = {"outcome": outcome, "text": text.strip(), "by": persona.name,
                               "at": datetime.now(UTC).isoformat()}
        built["status"] = "confirmed" if outcome == "confirmed" else "changes_requested"
        state["built_model"] = built
        log(db, case, persona, "model-validation",
            f"{ref}: the client {'confirmed' if outcome == 'confirmed' else 'asked for changes to'}"
            f" client model v{built['version']}", {"refs": [ref], "reason": text.strip()})
    kind = "query" if role == "client" else "expert"
    item["status"] = "answered" if role == "client" else "decided"
    item["answer" if role == "client" else "decision"] = {
        "text": text.strip(), "at": datetime.now(UTC).isoformat(), "by": persona.name}
    item["history"].append({"at": datetime.now(UTC).isoformat(), "by": persona.name,
                            "action": "answered" if role == "client" else "decided",
                            "note": text.strip()})
    state["exceptions"] = [item if e["ref"] == ref else e for e in state["exceptions"]]
    _save(case, state)
    handoffs.close_items(db, f"case:{case.id}:exc:{ref}:{kind}", persona, text.strip())
    handoffs.open_item(db, f"case:{case.id}:exc:{ref}:back", subject(case), case.audit_id,
                       "review", f"{'Client answered' if role == 'client' else 'Expert decided'}"
                       f" {ref}: {item['title']}"[:200], "onboarding_analyst",
                       f"/deals/cases/{case.id}/exceptions", persona, detail=text.strip())
    log(db, case, persona, "answer" if role == "client" else "expert-decision",
        f"{ref}: {'answered by the client' if role == 'client' else 'expert decision'}",
        {"refs": [ref], "reason": text.strip()})
    return item


def open_exceptions(state: dict[str, Any]) -> list[dict[str, Any]]:
    return [e for e in state.get("exceptions", [])
            if e["status"] not in ("accepted", "resolved") and e["severity"] != "info"]


# Controls: QC, four-eyes approval, go-live


def readiness(db: Session, case: DealCase, state: dict[str, Any]) -> dict[str, bool]:
    validation = state.get("validation") or {}
    return {
        "terms_approved": terms_ready(state),
        "reporting_captured": bool((state.get("reporting") or {}).get("lines")),
        "rules_approved": (state.get("rules") or {}).get("status") == "approved",
        "mapping_confirmed": bool((state.get("mapping") or {}).get("confirmed")),
        "validation_run": bool(validation.get("engine")),
        "client_model_agreed": client_model_agreed(db, case, state),
        "exceptions_worked": not open_exceptions(state),
    }


def client_model_agreed(db: Session, case: DealCase, state: dict[str, Any]) -> bool:
    """The client's own model was compared with the agreement, or, where the client has none,
    the model Oxane built was confirmed by the client."""
    if any(d.kind == "client_model" and d.kind_source != "oxane" for d in active_docs(db, case)):
        return True
    built = state.get("built_model") or {}
    return ((built.get("validation") or {}).get("outcome") == "confirmed"
            and built.get("status") == "confirmed")


def preparers(db: Session, case: DealCase) -> set[str]:
    """Everyone who changed the case's content. None of them may review it."""
    reviewer_kinds = {"approve", "return", "go-live", "qc-mark", "qc-complete", "handoff",
                      "handoff-done", "answer", "expert-decision"}
    return {e.actor for e in audit.events(db, case.audit_id) if e.type not in reviewer_kinds}


def stage_of(db: Session, case: DealCase, state: dict[str, Any]) -> str:
    if case.facility_id and state.get("live_at"):
        return "live"
    if state.get("approved_at"):
        return "approved"
    qc = state.get("qc") or {}
    if qc.get("status") == "passed":
        return "review"
    if qc.get("status") == "pending":
        return "qc"
    ready = readiness(db, case, state)
    if not state.get("terms"):
        return "documents"
    if not ready["terms_approved"]:
        return "terms"
    if not ready["rules_approved"]:
        return "rules"
    if not ready["mapping_confirmed"]:
        return "mapping"
    if not ready["validation_run"]:
        return "validation"
    return "exceptions"


def qc_items(state: dict[str, Any]) -> list[dict[str, Any]]:
    items = []
    for term in (state.get("terms") or {}).values():
        if term["status"] == "approved" and term["tier"] == 1:
            items.append({"id": f"term:{term['key']}", "label": term["label"],
                          "value": term["value"], "source": f"{term.get('doc_name')} p."
                          f"{term.get('page')}", "quote": term.get("quote")})
    rules = state.get("rules") or {}
    for rule in rules.get("eligibility", []) + rules.get("concentration", []):
        items.append({"id": f"rule:{rule['id']}", "label": f"{rule['id']} {rule['plain_english']}",
                      "value": rule.get("describe"), "source": f"{rule.get('document')} p."
                      f"{rule.get('page')}", "quote": rule.get("clause_text")})
    engine_view = (state.get("validation") or {}).get("engine")
    if engine_view:
        agrees = engine_view["independent_eligible_cents"] == engine_view["eligible_pool_cents"]
        items.append({"id": "calc:eligible", "label": "Eligible pool, recomputed loan by loan",
                      "value": f"US${engine_view['independent_eligible_cents'] / 100:,.2f}",
                      "source": "Independent recalculation", "quote": None,
                      "computed": "agrees" if agrees else "variance"})
    return items


def submit_for_qc(db: Session, case: DealCase, client: Client, persona: Persona) -> None:
    state = _state(case)
    unmet = [k for k, v in readiness(db, case, state).items() if not v]
    if unmet:
        raise refuse("Not ready for QC: " + ", ".join(u.replace("_", " ") for u in unmet), 422)
    state["qc"] = {"status": "pending", "submitted_by": persona.name,
                   "submitted_at": datetime.now(UTC).isoformat(), "marks": {}}
    _save(case, state)
    case.stage = "qc"
    handoffs.close_items(db, f"case:{case.id}:returned", persona)
    handoffs.open_item(db, f"case:{case.id}:qc", subject(case), case.audit_id, "qc",
                       f"Independent QC: {case.facility_name}", "qc",
                       f"/deals/cases/{case.id}/qc", persona)
    log(db, case, persona, "submit-qc", "Submitted the case for independent QC")


def qc_mark(db: Session, case: DealCase, persona: Persona, item_id: str, result: str,
            note: str) -> None:
    state = _state(case)
    qc = state.get("qc") or {}
    if qc.get("status") != "pending":
        raise refuse("The case is not in QC")
    if persona.name in preparers(db, case):
        raise refuse("You worked on this case, so QC must be done by someone independent")
    if result not in ("agrees", "variance") or (result == "variance" and not note.strip()):
        raise HTTPException(status_code=422, detail={"message": "Check the QC entry",
                                                     "fields": {"note": "Describe the variance"}})
    qc["marks"][item_id] = {"result": result, "note": note.strip() or None, "by": persona.name,
                            "at": datetime.now(UTC).isoformat()}
    state["qc"] = qc
    _save(case, state)
    log(db, case, persona, "qc-mark", f"QC {item_id}: {result}", {"reason": note or None,
                                                                  "refs": [item_id]})


def qc_complete(db: Session, case: DealCase, persona: Persona) -> str:
    state = _state(case)
    qc = state.get("qc") or {}
    if qc.get("status") != "pending":
        raise refuse("The case is not in QC")
    items = qc_items(state)
    unmarked = [i["id"] for i in items if i["id"] not in qc["marks"]]
    if unmarked:
        raise refuse(f"Check every item first: {len(unmarked)} left", 422)
    variances = [k for k, m in qc["marks"].items() if m["result"] == "variance"]
    handoffs.close_items(db, f"case:{case.id}:qc", persona)
    if variances:
        qc.update(status="returned", completed_by=persona.name)
        handoffs.open_item(db, f"case:{case.id}:returned", subject(case), case.audit_id,
                           "review", f"QC variances to fix: {case.facility_name}",
                           "onboarding_analyst", f"/deals/cases/{case.id}/qc", persona,
                           detail="; ".join(f"{k}: {qc['marks'][k]['note']}" for k in variances))
        text = f"QC returned the case with {len(variances)} variances"
    else:
        qc.update(status="passed", completed_by=persona.name,
                  completed_at=datetime.now(UTC).isoformat())
        handoffs.open_item(db, f"case:{case.id}:approve", subject(case), case.audit_id,
                           "approval", f"Approve load file: {case.facility_name}", "reviewer",
                           f"/deals/cases/{case.id}/approval", persona)
        text = "QC passed: every term, rule and the recalculation agree"
    state["qc"] = qc
    _save(case, state)
    case.stage = stage_of(db, case, state)
    log(db, case, persona, "qc-complete", text)
    return qc["status"]


def approve(db: Session, case: DealCase, persona: Persona, reason: str | None) -> None:
    state = _state(case)
    if (state.get("qc") or {}).get("status") != "passed":
        raise refuse("Independent QC must pass first")
    if persona.name in preparers(db, case) or persona.name == state["qc"].get("completed_by"):
        raise refuse("You prepared or checked this case, so a second analyst has to approve it")
    state["approved_at"] = datetime.now(UTC).isoformat()
    state["approved_by"] = persona.name
    _save(case, state)
    case.stage = "approved"
    handoffs.close_items(db, f"case:{case.id}:approve", persona)
    log(db, case, persona, "approve", "Approved the load file and configuration (four-eyes)",
        {"reason": reason})


def return_case(db: Session, case: DealCase, persona: Persona, reason: str) -> None:
    state = _state(case)
    if not reason.strip():
        raise HTTPException(status_code=422, detail={"message": "Say why",
                                                     "fields": {"reason": "Required"}})
    if (state.get("qc") or {}).get("status") != "passed" or state.get("approved_at"):
        raise refuse("Only a case waiting for approval can be returned")
    state["qc"]["status"] = "returned"
    _save(case, state)
    case.stage = stage_of(db, case, state)
    handoffs.close_items(db, f"case:{case.id}:approve", persona)
    handoffs.open_item(db, f"case:{case.id}:returned", subject(case), case.audit_id, "review",
                       f"Returned by reviewer: {case.facility_name}", "onboarding_analyst",
                       f"/deals/cases/{case.id}/approval", persona, detail=reason)
    log(db, case, persona, "return", "Returned the case to the analyst", {"reason": reason})


def first_period_after(as_of: date) -> date:
    """The end of the month after the onboarding tape."""
    nxt = (as_of.replace(day=1) + timedelta(days=32)).replace(day=1)
    return (nxt + timedelta(days=32)).replace(day=1) - timedelta(days=1)


def due_date(period_end: date, day: int) -> date:
    nxt = period_end + timedelta(days=1)
    return nxt.replace(day=min(day, 28))


def _provenance(db: Session, client: Client, state: dict[str, Any]) -> dict[str, Any]:
    from app.deals.setup import provenance

    return provenance(db, client, state)


def go_live(db: Session, case: DealCase, client: Client, persona: Persona) -> Facility:
    state = _state(case)
    if not state.get("approved_at"):
        raise refuse("Only an approved case can go live")
    if state.get("live_at"):
        raise refuse("This case is already live")
    terms = state["terms"]
    trigger = terms.get("delinquency_trigger") or {}
    loss = terms.get("loss_trigger") or {}
    validation = state["validation"]
    as_of = date.fromisoformat(validation["as_of"])
    reporting_day = (terms.get("reporting_day") or {}).get("typed") or 15
    config = {
        "ruleset": ruleset_of(state).model_dump(mode="json"),
        "rules": state["rules"],
        "mapping": {"signature": state["mapping"]["signature"],
                    "headers": state["mapping"]["headers"],
                    "columns": state["mapping"]["columns"],
                    "status_map": state["mapping"]["status_map"]},
        "thresholds": {
            "delinquency": {"limit_pct": trigger.get("typed"),
                            "days": trigger.get("basis_days") or 60,
                            "months": trigger.get("window_months") or 3,
                            "source": f"{trigger.get('doc_name')} p.{trigger.get('page')}"}
            if trigger.get("typed") else None,
            "loss": {"limit_pct": loss.get("typed"),
                     "source": f"{loss.get('doc_name')} p.{loss.get('page')}"}
            if loss.get("typed") else None,
            "prior_period": {"pool_balance": ["pct", "10"], "live_loans": ["pct", "10"]},
        },
        "terms": {k: {"value": t.get("value"), "typed": t.get("typed"), "source":
                      f"{t.get('doc_name')} p.{t.get('page')}" if t.get("page") else None}
                  for k, t in terms.items()},
        "reporting_day": reporting_day,
        "reporting": state.get("reporting"),
        "provenance": _provenance(db, client, state),
        "client_model": {k: (state.get("built_model") or {}).get(k) for k in
                         ("name", "version", "status", "doc_id")}
        if state.get("built_model") else {"status": "client's own"},
        "baseline": {"period": as_of.isoformat()[:7], "as_of": as_of.isoformat(),
                     "tape_doc": state["mapping"]["tape_doc"],
                     "excluded_rows": state.get("excluded_rows", []),
                     "delinquency_pct": validation["engine"].get("delinquency_pct")},
    }
    facility = Facility(client_id=client.id, name=case.facility_name, deal_type=case.deal_type,
                        commitment_cents=case.commitment_cents, status="live", case_id=case.id,
                        config=config, live_at=datetime.now(UTC))
    db.add(facility)
    db.flush()
    case.facility_id = facility.id
    state["live_at"] = datetime.now(UTC).isoformat()
    state["facility_id"] = facility.id
    _save(case, state)
    case.stage = "live"
    period_end = first_period_after(as_of)
    for _ in range(3):
        db.add(Submission(facility_id=facility.id, period=period_end.isoformat()[:7],
                          period_end=period_end, due_date=due_date(period_end, reporting_day),
                          status="expected", state={}))
        period_end = first_period_after(period_end)
    db.flush()
    audit.append(db, facility.audit_id, persona.name, "go-live",
                 f"Went live from {case_ref(case)} with rule set v"
                 f"{state['rules'].get('version', 1)}, the stored mapping and thresholds")
    log(db, case, persona, "go-live", f"Went live as FAC-{2000 + facility.id}")
    handoffs.open_item(db, f"facility:{facility.id}:first", f"facility:{facility.id}",
                       facility.audit_id, "work",
                       f"{facility.name} is live: first submission due "
                       f"{due_date(first_period_after(as_of), reporting_day):%d %b %Y}",
                       "monitoring_analyst", f"/facilities/{facility.id}", persona,
                       sla_hours=24 * 30)
    return facility
