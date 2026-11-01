"""Turn checked model answers into terms, rules and exceptions for the workbench."""

import re
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from engine.rules import RuleSet

from app.pipeline.catalogue import FIELDS, PLATFORM_FIELDS, US_STATES
from app.pipeline.checks import contains_value, values_agree
from app.pipeline.documents import PdfDocument, find_citation, normalise
from app.pipeline.steps import (
    AmendmentReading,
    DraftConcentration,
    DraftEligibility,
    DraftRules,
    ExtractedField,
    Extraction,
    ResolvedFormula,
    ScanRead,
)

# Sent to the workbench and to the queue when a value cannot be checked.
UNVERIFIED = "unverified"

# These fields answer how many, so their figure is a count and not a quoted number.
COUNT_FIELDS = {"Eligibility criteria", "Concentration limits", "Event of default list",
                "Lender alert thresholds"}
# These fields gather figures from several rows, so one quote cannot hold them all.
MULTI_PART_FIELDS = {"Financial statement reporting", "Interest period and payment date"}


def amount(text: str) -> int:
    """The first figure in a value, as a whole number."""
    match = re.search(r"\d[\d,]*", text)
    if match is None:
        raise ValueError(f"No figure in {text!r}")
    return int(match.group().replace(",", ""))


def iso_date(text: str | None) -> str | None:
    match = re.search(r"\d{4}-\d{2}-\d{2}", text or "")
    return match.group() if match else None


def long_date(iso: str) -> str:
    return f"{date.fromisoformat(iso):%-d %b %Y}"


def _number(value: float | None) -> str:
    """Whole numbers stay whole, so test logic reads 30 and not 30.0."""
    if value is None:
        raise ValueError("A rule is missing its threshold")
    return str(int(value)) if float(value).is_integer() else str(value)


def percent(text: str) -> str:
    match = re.search(r"(\d+(?:\.\d+)?)\s*%", text)
    if match is None:
        raise ValueError(f"No percentage in {text!r}")
    return match.group(1)


@dataclass
class Scan:
    document: str
    page: int
    read: ScanRead

    @property
    def rects(self) -> list[dict[str, float]]:
        r = self.read
        return [{"x0": r.x0, "x1": r.x1, "top": r.top, "bottom": r.bottom}]


@dataclass
class Evidence:
    documents: dict[str, PdfDocument]
    scans: list[Scan]
    workbook_text: dict[str, str] = field(default_factory=dict)

    def verify(self, document: str, quote: str) -> tuple[dict[str, Any] | None, str]:
        """Find a quote in the real source. Returns the citation and how it was found."""
        needle = normalise(quote)
        for scan in self.scans:
            if scan.document == document and needle and needle in normalise(scan.read.text):
                return {"document": document, "page": scan.page, "rects": scan.rects}, "scan"
        cited = find_citation(self.documents, document, quote)
        if cited:
            return cited, "text"
        if needle and needle in normalise(self.workbook_text.get(document, "")):
            return None, "workbook"
        return None, UNVERIFIED


def _confidence(found_by: str, supported: bool, tier: int, agreed: bool | None) -> str:
    """Confidence comes from checks that can fail, not from the model's opinion of itself."""
    if found_by == UNVERIFIED or not supported:
        return "low"
    if found_by == "scan":
        return "low"
    if tier == 1 and not agreed:
        return "medium"
    return "high"


def build_terms(first: Extraction, second: Extraction, evidence: Evidence,
                amendment: AmendmentReading) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Return the 26 terms, and any problem a person needs to look at."""
    by_name = {item.name: item for item in first.fields}
    reviewer = {item.name: item for item in second.fields}
    terms, problems = [], []

    for name, tier, _ in FIELDS:
        item = by_name.get(name)
        if item is None or not item.found:
            terms.append({
                "name": name, "tier": tier, "value": "Not found", "confidence": "none",
                "status": "missing", "clause": item.clause if item else "", "document": "",
                "source": None, "also_cited": [], "provenance": "ai", "verified": False,
            })
            continue
        source, found_by = evidence.verify(item.source_document, item.quote)
        supported = (name in COUNT_FIELDS | MULTI_PART_FIELDS or found_by == "scan"
                     or contains_value(item.value, item.quote))
        second_read = reviewer.get(name)
        agreed = (values_agree(item.value, second_read.value) and second_read.found
                  if tier == 1 and second_read else None)
        confidence = _confidence(found_by, supported, tier, agreed)
        terms.append({
            "name": name, "tier": tier, "value": item.value, "confidence": confidence,
            "status": "review", "clause": item.clause, "document": item.source_document,
            "source": source, "also_cited": [], "provenance": "ai",
            "verified": found_by != UNVERIFIED and supported,
        })
        if found_by == UNVERIFIED or not supported:
            problems.append(_problem(name, item, "Its quote could not be found in the document."
                                     if found_by == UNVERIFIED
                                     else "The quote does not contain the value."))
        elif tier == 1 and not agreed:
            shown = second_read.value if second_read else "no answer"
            problems.append(_problem(name, item, f"A second read gave {shown}."))

    _apply_amendment(terms, amendment, evidence)
    return terms, problems


def _problem(name: str, item: ExtractedField, why: str) -> dict[str, Any]:
    return {"field": name, "value": item.value, "clause": item.clause, "why": why}


def _apply_amendment(terms: list[dict[str, Any]], amendment: AmendmentReading,
                     evidence: Evidence) -> None:
    """Show the amended value by effective date. The original stays visible beside it."""
    rate = next(term for term in terms if term["name"] == "Advance rate")
    limits = next(term for term in terms if term["name"] == "Concentration limits")
    dates = next(term for term in terms if term["name"] == "Amendment dates")
    effective = {change.effective_from for change in amendment.changes}
    signed = iso_date(amendment.signed)
    if len(effective) == 1 and signed:
        # The amendment reading states these directly, so they replace the term's wording.
        dates["value"] = f"Signed {long_date(signed)}; effective {long_date(effective.pop())}"
    for change in amendment.changes:
        if "Schedule 2" in change.target and change.kind == "add_item":
            source, found_by = evidence.verify("amendment_1", change.quote)
            if found_by != UNVERIFIED:
                note = f"Adds a limit from {long_date(change.effective_from)}"
                limits["also_cited"] = [{**source, "label": "Amendment No. 1, 2(b)", "note": note}]
                limits["value"] = f"{amount(limits['value']) + 1} limits, as amended"
            continue
        if "2.3" not in change.target:
            continue
        source, found_by = evidence.verify("amendment_1", change.quote)
        if found_by == UNVERIFIED:
            rate["confidence"] = "low"
            rate["verified"] = False
            continue
        original = rate["source"]
        if original:
            rate["also_cited"] = [{**original, "label": "Credit Agreement 2.3",
                                   "note": f"{change.old_value}, superseded from "
                                           f"{long_date(change.effective_from)}"}]
        rate.update(document="amendment_1", source=source,
                    value=f"{change.new_value} from {long_date(change.effective_from)}",
                    clause="Amendment No. 1, 2(a), amending Credit Agreement 2.3",
                    original_value=change.old_value, amended_value=change.new_value,
                    effective_from=change.effective_from)


def _eligibility(draft: DraftEligibility) -> dict[str, Any]:
    field_node = {"kind": "field", "name": draft.field or ""}

    def compare(op: str, value: float | None) -> dict[str, Any]:
        return {"kind": "compare", "op": op, "left": field_node,
                "right": {"kind": "const", "value": _number(value)}}

    if draft.test == "max":
        test = compare("<=", draft.high)
    elif draft.test == "min":
        test = compare(">=", draft.low)
    elif draft.test == "between":
        test = {"kind": "between", "value": field_node, "low": f"{draft.low:.2f}",
                "high": f"{draft.high:.2f}"}
    elif draft.test == "not_status":
        test = {"kind": "member", "value": {"kind": "field", "name": "status"},
                "list": "excluded_statuses", "negate": True}
    elif draft.test == "in_us_states":
        test = {"kind": "member", "value": {"kind": "field", "name": "obligor_state"},
                "list": "us_states"}
    elif draft.test == "not_restricted":
        test = {"kind": "member", "value": {"kind": "field", "name": "obligor_state"},
                "list": "schedule_4", "negate": True}
    elif draft.test == "vehicle_age_max":
        test = {"kind": "compare", "op": "<=", "left": {
            "kind": "subtract",
            "left": {"kind": "year_of", "of": {"kind": "field", "name": "origination_date"}},
            "right": {"kind": "field", "name": "model_year"},
        }, "right": {"kind": "const", "value": _number(draft.high)}}
    else:
        test = {"kind": "unique", "value": {"kind": "field", "name": "vin"}}
    return {
        "id": f"E{draft.paragraph}", "plain_english": draft.plain_english,
        "clause_ref": f"Schedule 1, paragraph {draft.paragraph}",
        "clause_text": draft.clause_text, "test": test,
    }


BUCKET_IDS = {"state": "C1", "dealer": "C2", "long_term": "C3", "low_fico": "C4", "used": "C5"}


def _concentration(draft: DraftConcentration) -> dict[str, Any]:
    rule: dict[str, Any] = {
        "id": BUCKET_IDS[draft.bucket], "plain_english": draft.plain_english,
        "clause_ref": draft.clause_ref, "clause_text": draft.clause_text,
        "limit_pct": _number(draft.limit_pct), "effective_from": iso_date(draft.effective_from),
    }
    if draft.bucket == "state":
        rule["group_by"] = {"kind": "field", "name": "obligor_state"}
    elif draft.bucket == "dealer":
        rule["group_by"] = {"kind": "field", "name": "dealer_name"}
    elif draft.bucket == "used":
        rule["where"] = {"kind": "member", "value": {"kind": "field", "name": "vehicle_condition"},
                         "list": "used_conditions"}
    else:
        name, op = ("original_term", ">") if draft.bucket == "long_term" else ("fico", "<")
        rule["where"] = {"kind": "compare", "op": op, "left": {"kind": "field", "name": name},
                         "right": {"kind": "const", "value": _number(draft.threshold)}}
    return rule


def build_ruleset(draft: DraftRules, terms: list[dict[str, Any]], signing_date: str,
                  amendment_effective: str | None, tape_statuses: list[str]) -> RuleSet:
    """Validation here is the gate: a draft the engine will not accept stops the pipeline."""
    unknown = {s for item in draft.eligibility for s in item.statuses} - set(tape_statuses)
    if unknown:
        raise ValueError(f"Rule draft names statuses that are not on the tape: {sorted(unknown)}")
    values = {term["name"]: term for term in terms}
    rate = values["Advance rate"]
    original = rate.get("original_value", rate["value"])
    rates = [{"pct": percent(original), "effective_from": signing_date,
              "source": "Credit Agreement 2.3"}]
    if amendment_effective and "amended_value" in rate:
        rates.append({"pct": percent(rate["amended_value"]), "effective_from": amendment_effective,
                      "source": "Amendment No. 1, 2(a)"})
    statuses = sorted({s for item in draft.eligibility for s in item.statuses})
    return RuleSet.model_validate({
        "version": 1,
        "facility_limit_cents": amount(values["Facility limit"]["value"]) * 100,
        "reserve_pct": percent(values["Reserve amount"]["value"]),
        "advance_rates": rates,
        "lists": {"us_states": US_STATES, "excluded_statuses": statuses,
                  "used_conditions": ["USED"], "schedule_4": None},
        "eligibility": [_eligibility(item) for item in
                        sorted(draft.eligibility, key=lambda rule: rule.paragraph)],
        "concentration": [_concentration(item) for item in draft.concentration],
    })


NUMERIC_FIELDS = {"original_balance", "current_balance", "apr", "original_term", "fico",
                  "days_past_due", "payments_made", "remaining_term", "model_year",
                  "modification_count"}


def check_mapping(columns: list[dict[str, Any]],
                  rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    """A match only holds if the column's values fit the field, and no field is used twice."""
    seen: dict[str, str] = {}
    for column in columns:
        target = column["field"]
        if target not in PLATFORM_FIELDS:
            column.update(confidence="low", note="Not a platform field")
            continue
        if target in seen:
            column.update(confidence="low", note=f"Also claimed by {seen[target]}")
        seen[target] = column["column"]
        values = [row[column["column"]] for row in rows if row[column["column"]]]
        if target in NUMERIC_FIELDS and not all(
            re.fullmatch(r"-?\d+(\.\d+)?", value) for value in values
        ):
            column.update(confidence="low", note="Values are not all numbers")
    return columns


def formula_sources(formula: ResolvedFormula, evidence: Evidence) -> list[dict[str, Any]]:
    cited = []
    for part in formula.parts:
        source, _ = evidence.verify("credit_agreement", part.quote)
        cited.append({"clause": part.clause, "quote": part.quote, "source": source})
    return cited
