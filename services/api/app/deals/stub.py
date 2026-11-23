"""A deterministic stand-in for the model, for tests and the offline end-to-end run only.

It is switched on by DEALS_STUB_MODEL=1 and never in a deployment. It answers the new-deal tasks
by reading the request's own document text with patterns written for the two generated test
deals (Harbourline and Fenwick), and quotes exactly what it matched. On any other document it
finds nothing, so it also exercises the paths for terms that are missing. It is a test double,
not a recording of the model: the pipeline's code checks run on its answers exactly as on the
model's.
"""

import json
import re
from typing import Any

from app.deals.checks import SYNONYMS, heuristic_mapping, heuristic_statuses

DATE = r"([A-Z][a-z]+ \d{1,2}, \d{4})"


def _documents(content: list[dict[str, Any]]) -> dict[str, list[str]]:
    """Document id -> page texts, whitespace collapsed, from <document> blocks."""
    text = "\n".join(block.get("text", "") for block in content if block.get("type") == "text")
    docs: dict[str, list[str]] = {}
    for ident, body in re.findall(r'<document id="([^"]+)">\n(.*?)\n</document>', text, re.S):
        pages = re.split(r"\[page \d+\]\n", body)
        docs[ident] = [" ".join(p.split()) for p in pages if p.strip()]
    return docs


def _find(docs: dict[str, list[str]], pattern: str) -> tuple[str, str, re.Match[str]] | None:
    """The last match across documents (amendments sort after agreements by name is not
    guaranteed, so callers choose the document where it matters)."""
    for ident, pages in docs.items():
        for page in pages:
            match = re.search(pattern, page)
            if match:
                return ident, page, match
    return None


def _term(key: str, found: tuple[str, str, re.Match[str]] | None, value_group: int = 1,
          **extra: Any) -> dict[str, Any]:
    base = {"key": key, "found": False, "value": "", "document": "", "clause": "", "quote": "",
            "effective_from": None, "original": None, "basis_days": None,
            "window_months": None, "note": None}
    if found is None:
        return base
    ident, _, match = found
    return {**base, "found": True, "value": match.group(value_group), "document": ident,
            "quote": match.group(0).strip(), **extra}


def _iso(text: str | None) -> str | None:
    if not text:
        return None
    from datetime import datetime

    return datetime.strptime(text, "%B %d, %Y").date().isoformat()


def extract(content: list[dict[str, Any]]) -> dict[str, Any]:
    docs = _documents(content)
    agreements = {k: v for k, v in docs.items() if "Amendment" not in k}
    amendments = {k: v for k, v in docs.items() if "Amendment" in k}
    terms = []
    terms.append(_term("commitment", _find(agreements, r"(US\$[\d,]+) \(the \"(?:Maximum "
                                                       r"Facility Amount|Facility Limit)\"\)")))
    base = _find(agreements, r"The \"Advance Rate\" is ([\d.]+%)") or _find(
        agreements, r"which is ([\d.]+%) of the Qualifying Balance")
    change = _find(amendments, r"the Advance Rate of ([\d.]+%) is replaced by ([\d.]+%), with "
                               r"effect from " + DATE)
    if change and base:
        ident, _, match = change
        terms.append({**_term("advance_rate", change, 2), "effective_from": _iso(match.group(3)),
                      "original": {"value": base[2].group(1), "document": base[0],
                                   "quote": base[2].group(0)}})
    else:
        terms.append(_term("advance_rate", base))
    terms.append(_term("reserve", _find(agreements, r"The \"Reserve Account Requirement\" is "
                                                    r"([\d.]+%)")))
    trigger = _find(agreements, r"average of the Delinquency Ratios for the three most recent "
                                r"Collection Periods exceeds ([\d.]+%)") or _find(
        agreements, r"Arrears Ratio, averaged over the three most recent Reporting Dates, is "
                    r"greater than ([\d.]+%)")
    days = _find(agreements, r"(\d+) or more days past its due date")
    arrears = _find(agreements, r"more than (\d+) days in arrears divided")
    basis = int(days[2].group(1)) if days else (int(arrears[2].group(1)) + 1 if arrears else None)
    terms.append(_term("delinquency_trigger", trigger, basis_days=basis,
                       window_months=3 if trigger else None))
    terms.append(_term("loss_trigger", _find(agreements, r"annualised Net Loss Ratio for any "
                                                         r"Collection Period exceeds ([\d.]+%)")))
    terms.append(_term("revolving_period_end", _find(
        agreements, r"The Availability Period ends on " + DATE) or _find(
        agreements, r"may request advances until " + DATE)))
    terms.append(_term("final_maturity", _find(
        agreements, r"repaid in full on " + DATE) or _find(
        agreements, r"The Termination Date is " + DATE)))
    terms.append(_term("margin", _find(agreements, r"interest at ((?:Term )?SOFR plus [\d.]+% "
                                                   r"per annum)")))
    terms.append(_term("reporting_day", _find(agreements, r"no later than the (\d+)th day of "
                                                          r"each calendar month") or _find(
        agreements, r"By the (\d+)th day of each month")))
    terms.append(_term("borrower", _find(agreements, r"among ([A-Z][^()]+?) \(the \"Borrower\"\)")
                       or _find(agreements, r"between ([A-Z][^()]+?) \(the \"Company\"\)")))
    terms.append(_term("lender", _find(agreements, r"and ([A-Z][^()]+?) \(the \"Lender\"\)")
                       or _find(agreements, r"and ([A-Z][^()]+?) \(the \"Funder\"\)")))
    terms.append(_term("servicer", _find(agreements, r", ([A-Z][^(),]+?) \(the \"Servicer\"\)")
                       or _find(agreements, r", ([A-Z][^(),]+?) \(the \"Originator\"")))
    law = r"governed by the laws? of the (State of [A-Z][a-z]+(?: [A-Z][a-z]+)?)"
    terms.append(_term("governing_law", _find(agreements, law)))
    return {"terms": terms}


ELIGIBILITY = [
    (r"No payment on the Receivable is more than (\d+) days past due\.", "max", "days_past_due"),
    (r"had a FICO score of at least (\d+) at origination\.", "min", "credit_score"),
    (r"original term of the Receivable does not exceed (\d+) months\.", "max", "original_term"),
    (r"Principal Balance of the Receivable does not exceed US\$([\d,]+)\.", "max",
     "current_balance"),
    (r"annual percentage rate of the Receivable does not exceed ([\d.]+)%\.", "max", "apr"),
    (r"the loan is not more than (\d+) days in arrears;", "max", "days_past_due"),
    (r"internal risk grade is (\d+) or better", "max", "risk_grade"),
    (r"original principal of the loan did not exceed US\$([\d,]+);", "max", "original_balance"),
    (r"remaining term of the loan is no more than (\d+) months;", "max", "remaining_term"),
]
LISTS = [
    (r"does not reside in any of the following Restricted States: ([A-Z, ]+)\.",
     "obligor_state"),
    (r"does not operate in an Excluded Sector, being ([A-Za-z ,]+); and", "sector"),
]
STATUS = [
    (r"The Receivable is not a Charged-Off Receivable or a Defaulted Receivable\.",
     ["charged_off", "defaulted"]),
    (r"the loan is not a Defaulted Loan or a Written-Off Loan\.", ["defaulted", "charged_off"]),
]
CONCENTRATION = [
    (r"Obligors residing in any single State: ([\d.]+)% of the Eligible Pool Balance\.",
     {"group_by": "obligor_state"}),
    (r"Obligor FICO score at origination below (\d+): ([\d.]+)% of the Eligible Pool Balance\.",
     {"where": ("below", "credit_score")}),
    (r"original term of more than (\d+) months: ([\d.]+)% of the Eligible Pool Balance\.",
     {"where": ("above", "original_term")}),
    (r"Loans to any one borrower: ([\d.]+)% of the aggregate principal of Qualifying Loans\.",
     {"group_by": "obligor_id"}),
    (r"Loans to borrowers in any one sector: ([\d.]+)%", {"group_by": "sector"}),
    (r"Loans to borrowers in any one region: ([\d.]+)%", {"group_by": "region"}),
    (r"risk grade of (\d+) or weaker: ([\d.]+)% of the aggregate principal of Qualifying Loans\.",
     {"where": ("min", "risk_grade")}),
]


def _num(text: str) -> float:
    return float(text.replace(",", ""))


def rules(content: list[dict[str, Any]]) -> dict[str, Any]:
    docs = _documents(content)
    eligibility, concentration = [], []
    for ident, pages in sorted(docs.items()):
        for page in pages:
            for pattern, kind, field in ELIGIBILITY:
                for match in re.finditer(pattern, page):
                    value = _num(match.group(1))
                    eligibility.append({
                        "ref": "Eligibility schedule", "plain_english": match.group(0).rstrip(".;"),
                        "clause_text": match.group(0), "document": ident,
                        "test": {"kind": kind, "field": field,
                                 "low": value if kind == "min" else None,
                                 "high": value if kind == "max" else None, "values": []}})
            for pattern, field in LISTS:
                for match in re.finditer(pattern, page):
                    values = [v.strip() for v in re.split(r",| and ", match.group(1)) if v.strip()]
                    eligibility.append({
                        "ref": "Eligibility schedule", "plain_english": match.group(0).rstrip(".;"),
                        "clause_text": match.group(0), "document": ident,
                        "test": {"kind": "not_in_list", "field": field, "low": None,
                                 "high": None, "values": values}})
            for pattern, statuses in STATUS:
                for match in re.finditer(pattern, page):
                    eligibility.append({
                        "ref": "Eligibility schedule", "plain_english": match.group(0).rstrip(".;"),
                        "clause_text": match.group(0), "document": ident,
                        "test": {"kind": "not_status", "field": "status", "low": None,
                                 "high": None, "values": statuses}})
            for pattern, shape in CONCENTRATION:
                for match in re.finditer(pattern, page):
                    groups = match.groups()
                    where = None
                    if "where" in shape:
                        kind, field = shape["where"]
                        bound = _num(groups[0])
                        where = {"kind": kind, "field": field,
                                 "low": bound if kind in ("min", "above") else None,
                                 "high": bound if kind in ("max", "below") else None,
                                 "values": []}
                    concentration.append({
                        "ref": "Concentration schedule", "plain_english": match.group(0)
                        .rstrip("."), "clause_text": match.group(0), "document": ident,
                        "limit_pct": _num(groups[-1]), "group_by": shape.get("group_by"),
                        "where": where, "effective_from": None})
            for match in re.finditer(r"\"4\. (Receivables financing [A-Za-z ]+ products): "
                                     r"([\d.]+)% of the Eligible Pool Balance\.\", with effect "
                                     r"from " + DATE, page):
                product = match.group(1).removeprefix("Receivables financing ")
                product = product.removesuffix(" products")
                concentration.append({
                    "ref": "Schedule B, para 4 (added by the First Amendment)",
                    "plain_english": match.group(1), "clause_text": f"{match.group(1)}: "
                    f"{match.group(2)}% of the Eligible Pool Balance", "document": ident,
                    "limit_pct": _num(match.group(2)), "group_by": None,
                    "where": {"kind": "in_list", "field": "product", "low": None, "high": None,
                              "values": [product]},
                    "effective_from": _iso(match.group(3))})
    return {"eligibility": eligibility, "concentration": concentration, "not_codable": []}


def classify(content: list[dict[str, Any]]) -> dict[str, Any]:
    text = content[0]["text"]
    out = []
    for ident, body in re.findall(r"--- (.+?) ---\n(.*?)(?=\n\n--- |\Z)", text, re.S):
        flat = " ".join(body.split()).lower()
        if "amendment" in flat[:400]:
            kind = "amendment"
        elif "agreement" in flat[:600] and ("among" in flat or "between" in flat):
            kind = "agreement"
        elif "monthly report" in flat or "servicer report" in flat:
            kind = "servicer_report"
        elif "model" in flat[:200] or "[sheet inputs]" in flat:
            kind = "client_model"
        elif ident.lower().endswith((".csv", ".xlsx")):
            kind = "loan_tape"
        else:
            kind = "other"
        out.append({"document": ident, "kind": kind, "title": f"{kind.replace('_', ' ').title()}"
                    f": {ident}", "dated": None, "effective": None})
    return {"documents": out}


def map_tape(content: list[dict[str, Any]]) -> dict[str, Any]:
    text = content[0]["text"]
    headers = [h.strip() for h in re.search(r"Columns: (.*)\n", text).group(1).split(", ")]
    statuses = re.search(r"Status values: (.*)$", text, re.S).group(1).strip()
    values = [v.strip() for v in statuses.split(",") if v.strip()]
    columns = heuristic_mapping(headers)
    assert SYNONYMS
    return {"columns": [{"column": h, "field": f, "note": None} for h, f in columns.items()],
            "statuses": [{"value": v, "status": s} for v, s in
                         heuristic_statuses(values).items()]}


def read_report(content: list[dict[str, Any]]) -> dict[str, Any]:
    text = " ".join(content[0]["text"].split())
    figures = []
    for key, pattern in (("principal_collections", r"Principal collections for the month were "
                                                   r"(US\$[\d,]+\.\d{2})"),
                         ("charge_offs", r"Charge-offs for the month were (US\$[\d,]+\.\d{2})"),
                         ("new_loans_balance", r"with principal of (US\$[\d,]+\.\d{2})")):
        match = re.search(pattern, text)
        figures.append({"key": key, "found": bool(match),
                        "value": match.group(1) if match else "",
                        "quote": match.group(0) if match else ""})
    figures.append({"key": "pool_balance", "found": False, "value": "", "quote": ""})
    return {"figures": figures}


def commentary(content: list[dict[str, Any]]) -> dict[str, Any]:
    text = content[0]["text"]
    names = set(re.findall(r"\{\{(\w+)\}\}", text))
    paragraphs = ["The pool stood at {{pool_balance}} across {{loans}} loans this month."]
    if "delinquency_average" in names:
        paragraphs.append("The rolling delinquency ratio was {{delinquency_average}} against a "
                          "trigger of {{delinquency_limit}}.")
    paragraphs.append("The borrowing base was {{borrowing_base}} on an eligible pool of "
                      "{{eligible_pool}}.")
    return {"paragraphs": paragraphs}


ANSWERS = {"deals_extract": extract, "deals_rules": rules, "deals_classify": classify,
           "deals_map": map_tape, "deals_report": read_report, "deals_commentary": commentary}


def answer(task: str, content: list[dict[str, Any]]) -> str:
    return json.dumps(ANSWERS[task](content))
