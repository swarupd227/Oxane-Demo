"""Seeded workbench data for phase 3.

These views are built from the answer key, so they show a perfect extraction.
Phase 4 replaces them with real pipeline output. The workbench labels them as
seed data until then, and the scorecard does not claim any accuracy from them.
"""

import re
import threading
from functools import lru_cache
from typing import Any

import pypdfium2

from app.engine_service import PERIOD_END, pack_path, read_key, rule_views, tape_rows

DOCUMENT_INFO: dict[str, dict[str, Any]] = {
    "credit_agreement": {
        "title": "Credit agreement", "kind": "Agreement", "dated": "2026-01-15",
        "version": "Execution version", "effective": "2026-01-15",
        "note": "One scanned page: Annex A",
    },
    "amendment_1": {
        "title": "Amendment No. 1", "kind": "Amendment", "dated": "2026-02-20",
        "version": "No. 1", "effective": "2026-03-01", "links_to": "credit_agreement",
        "note": "Amends the credit agreement",
    },
    "fee_letter": {
        "title": "Fee letter", "kind": "Fee letter", "dated": "2026-01-15", "version": "Final",
        "effective": "2026-01-15",
    },
    "loan_tape": {
        "title": "Loan tape, April 2026", "kind": "Loan tape", "dated": "2026-04-30",
        "version": "April 2026", "effective": "2026-04-30",
    },
    "servicer_report": {
        "title": "Servicer report, April 2026", "kind": "Servicer report", "dated": "2026-04-30",
        "version": "April 2026", "effective": "2026-04-30",
    },
    "borrowing_base_certificate": {
        "title": "Borrowing base certificate", "kind": "Certificate", "dated": "2026-04-30",
        "version": "April 2026", "effective": "2026-04-30",
        "note": "Prepared by the borrower",
    },
    "financial_statements": {
        "title": "Financial statements, Q1 2026", "kind": "Financials", "dated": "2026-03-31",
        "version": "Unaudited", "effective": "2026-03-31",
    },
    "lender_requirements": {
        "title": "Lender requirements sheet", "kind": "Requirements", "dated": "2026-01-15",
        "version": "Final", "effective": "2026-01-15",
    },
}

# Name -> (shown value, confidence, seeded status).
TERM_VIEWS: dict[str, tuple[str, str, str]] = {
    "Facility limit": ("US$250,000,000", "low", "review"),
    "Advance rate": ("82.5% from 1 Mar 2026", "high", "review"),
    "Eligibility criteria": ("12 criteria", "high", "approved"),
    "Concentration limits": ("5 limits, as amended", "high", "approved"),
    "Excess concentration treatment": ("Excluded from the eligible pool", "high", "approved"),
    "Reserve amount": ("1% of eligible pool", "high", "approved"),
    "Delinquency trigger": ("60+ days above 6.0%, 3-month average", "high", "approved"),
    "Minimum tangible net worth covenant": ("US$40,000,000", "high", "approved"),
    "Maximum leverage covenant": ("6.00 to 1.00", "high", "approved"),
    "Minimum liquidity covenant": ("US$10,000,000", "high", "approved"),
    "Restricted jurisdictions": ("Not found", "none", "missing"),
    "Margin": ("Term SOFR + 3.25%", "high", "approved"),
    "Unused fee": ("0.50% a year", "high", "approved"),
    "Interest period and payment date": ("Monthly, 15th of each month", "high", "approved"),
    "Borrowing base reporting date": ("15th business day after month end", "high", "approved"),
    "Financial statement reporting": ("Quarterly 45 days; annual 120 days", "medium", "review"),
    "Revolving period end": ("15 Jan 2028", "high", "approved"),
    "Final maturity": ("15 Jan 2029", "high", "approved"),
    "Event of default list": ("14 events", "high", "approved"),
    "Lender alert thresholds": ("6 alerts", "medium", "review"),
    "Borrower, parent and servicer names": ("Bramble entities", "high", "approved"),
    "Lender and agent names": ("Calderwood Bank plc", "high", "approved"),
    "Governing law": ("New York law", "high", "approved"),
    "Signing date": ("15 Jan 2026", "high", "approved"),
    "Amendment dates": ("Signed 20 Feb 2026; effective 1 Mar 2026", "high", "approved"),
    "Notice addresses": ("Bramble and Calderwood addresses", "high", "approved"),
}

# Longer passages to highlight, where the key's quote is only a fragment.
HIGHLIGHTS = {
    "Advance rate": 'In Section 2.3, "85%" is deleted and replaced with "82.5%", with effect from '
                    "1 March 2026.",
    "Reserve amount": '"Reserve Amount" means, on any date, an amount equal to 1% of the Eligible '
                      "Pool Balance.",
    "Margin": "Term SOFR for the applicable Interest Period plus 3.25%",
    "Governing law": "governed by the law of the State of New York",
}

ALSO_CITED = {
    "Advance rate": [{
        "label": "Credit Agreement 2.3",
        "document": "credit_agreement",
        "quote": 'The "Advance Rate" means 85%.',
        "note": "85%, superseded from 1 Mar 2026",
    }],
    "Eligibility criteria": [{
        "label": 'Definition of "Eligible Receivable", 1.1',
        "document": "credit_agreement",
        "quote": '"Eligible Receivable" means, on any date of determination, a Pool Receivable '
                 "that satisfies each of the criteria set out in Schedule 1",
        "note": "Failing any one criterion excludes the loan in full",
    }],
    "Maximum leverage covenant": [{
        "label": "Tangible Net Worth, 1.1",
        "document": "credit_agreement",
        "quote": '"Tangible Net Worth" means',
        "note": "Used in the ratio, with the carve-out in 6.12(c)",
    }],
}

# Annex A is an image, so its highlight is placed by hand, as fractions of the page.
SCAN_HIGHLIGHT = [{"x0": 0.21, "top": 0.292, "x1": 0.79, "bottom": 0.335}]

LESS_CERTAIN_FIELDS = {"stated_monthly_income", "payment_to_income", "vehicle_book_value",
                       "loan_to_value", "amount_financed", "odometer_at_origination"}
UNCERTAIN_FIELDS = {"servicer_code": "No platform equivalent named in the requirements",
                    "employment_type": "Value list differs from the platform's",
                    "origination_date": "Two date formats found in 120 rows"}


def _pdf_files() -> dict[str, str]:
    return {doc: name for doc, name in read_key("pack").items() if name.endswith(".pdf")}


@lru_cache
def _page_text(document: str) -> tuple[str, ...]:
    pdf = pypdfium2.PdfDocument(str(pack_path(_pdf_files()[document])))
    try:
        return tuple(re.sub(r"\s+", " ", page.get_textpage().get_text_range()) for page in pdf)
    finally:
        pdf.close()


def _find_page(document: str, quote: str) -> int | None:
    needle = re.sub(r"\s+", " ", quote)
    hits = [i for i, body in enumerate(_page_text(document), start=1) if needle in body]
    return hits[-1] if hits else None


def _rects(document: str, page_number: int, quote: str) -> list[dict[str, float]]:
    """Find a quote on a page and return one rectangle per line, as fractions of the page."""
    pdf = pypdfium2.PdfDocument(str(pack_path(_pdf_files()[document])))
    try:
        page = pdf[page_number - 1]
        width, height = page.get_size()
        textpage = page.get_textpage()
        raw = textpage.get_text_range()

        # Collapse whitespace, remembering where each kept character came from.
        collapsed: list[str] = []
        origin: list[int] = []
        for index, char in enumerate(raw):
            if char.isspace():
                if collapsed and collapsed[-1] != " ":
                    collapsed.append(" ")
                    origin.append(index)
            else:
                collapsed.append(char)
                origin.append(index)

        needle = " ".join(quote.split())
        start = "".join(collapsed).find(needle)
        if start < 0:
            return []

        # A new line starts wherever the text jumps back to the left.
        lines: list[list[tuple[float, float, float, float]]] = []
        for index in origin[start:start + len(needle)]:
            if raw[index].isspace():
                continue
            box = textpage.get_charbox(index)
            if not lines or box[0] < lines[-1][-1][0]:
                lines.append([])
            lines[-1].append(box)
        return [{
            "x0": min(box[0] for box in boxes) / width,
            "x1": max(box[2] for box in boxes) / width,
            "top": 1 - max(box[3] for box in boxes) / height,
            "bottom": 1 - min(box[1] for box in boxes) / height,
        } for boxes in lines]
    finally:
        pdf.close()


def _citation(document: str, quote: str) -> dict[str, Any] | None:
    page = _find_page(document, quote)
    if page is None:
        return None
    return {"document": document, "page": page, "rects": _rects(document, page, quote)}


def _term(field: dict[str, Any]) -> dict[str, Any]:
    name = field["name"]
    shown, confidence, status = TERM_VIEWS[name]
    document = field["document"]
    source = None
    if name == "Facility limit":
        source = {"document": document, "page": field["page"], "rects": SCAN_HIGHLIGHT}
    elif field["quote"] and document in _pdf_files():
        source = _citation(document, HIGHLIGHTS.get(name, field["quote"]))
    also = []
    for item in ALSO_CITED.get(name, []):
        cited = _citation(item["document"], item["quote"])
        if cited:
            also.append({**cited, "label": item["label"], "note": item["note"]})
    return {
        "name": name, "tier": field["tier"], "value": shown, "confidence": confidence,
        "status": status, "clause": field["clause"], "document": document, "source": source,
        "also_cited": also, "provenance": "ai",
    }


def _mapping() -> dict[str, Any]:
    columns = read_key("mapping")["columns"]
    first = tape_rows()[0]
    rows = []
    for raw in first:
        target = columns[raw]
        confidence = ("low" if target in UNCERTAIN_FIELDS else
                      "medium" if target in LESS_CERTAIN_FIELDS else "high")
        rows.append({
            "column": raw, "field": target, "confidence": confidence,
            "sample": first[raw], "note": UNCERTAIN_FIELDS.get(target),
        })
    requirements = [
        {"name": "Loan-level fields", "status": "met", "detail": "17 of 17 mapped from the tape"},
        {"name": "Pool balance", "status": "calculated", "detail": "From the validation run"},
        {"name": "Eligible pool balance", "status": "calculated",
         "detail": "From the validation run"},
        {"name": "Borrowing base", "status": "calculated", "detail": "From the validation run"},
        {"name": "Availability", "status": "calculated", "detail": "From the validation run"},
        {"name": "Weighted average APR", "status": "derived",
         "detail": "Not a tape column. sum(NoteRate x CurrBal) / sum(CurrBal)"},
    ]
    x9 = read_key("exceptions")["X9"]
    return {
        "rows": rows, "requirements": requirements,
        "dates": {"mixed_rows": x9["rows"], "uncertain": len(x9["uncertain_loan_ids"]),
                  "method": "Resolved against FirstPmtDate, 20 to 60 days later"},
    }


def _exceptions() -> list[dict[str, Any]]:
    key = read_key("exceptions")
    x4, x5, x6, x7, x9, x10 = (key[k] for k in ("X4", "X5", "X6", "X7", "X9", "X10"))
    ca, am = "credit_agreement", "amendment_1"

    def link(document: str, quote: str) -> dict[str, Any] | None:
        return _citation(document, quote)

    return [
        {"id": "X1", "type": "conflicting", "label": "Amended term",
         "title": "Advance rate changed by Amendment No. 1", "owner": "Onboarding analyst",
         "where": "Credit Agreement 2.3 and Amendment No. 1, 2(a)",
         "evidence": ["Credit Agreement 2.3 states 85%.",
                      "Amendment No. 1 replaces it with 82.5% from 1 March 2026.",
                      "The April period therefore uses 82.5%."],
         "suggestion": "Confirm 82.5% for the April period.", "actions": ["accept"],
         "tier1": True, "source": link(am, 'In Section 2.3, "85%" is deleted and replaced')},
        {"id": "X2", "type": "missing", "label": "Missing document",
         "title": "Schedule 4 is not in the pack", "owner": "Borrower's counsel",
         "where": "Credit Agreement, Schedule 4",
         "evidence": ["The definition of Restricted Jurisdiction refers to Schedule 4.",
                      "Schedule 4 is listed in the contents but was not received.",
                      "Rule E7 cannot run, so the borrowing base is provisional."],
         "suggestion": "Request Schedule 4 from the borrower's counsel.", "actions": ["query"],
         "blocking": True,
         "source": link(ca, "each state, territory or other jurisdiction listed in Schedule 4")},
        {"id": "X3", "type": "ambiguous", "label": "Low confidence",
         "title": "Facility limit read from a poor scan", "owner": "Onboarding analyst",
         "where": "Credit Agreement, Annex A",
         "evidence": ["Annex A is an image-only page.", "The value reads as US$250,000,000.",
                      "This value appears nowhere else in the pack."],
         "suggestion": "Confirm against the signed page.", "actions": ["accept"], "tier1": True,
         "source": {"document": ca, "page": 61, "rects": SCAN_HIGHLIGHT}},
        {"id": "X4", "type": "conflicting", "label": "Certificate vs tape",
         "title": f"{x4['loans']} loans over 30 days past due counted as eligible",
         "owner": "Borrower", "where": "Borrowing base certificate and loan tape",
         "evidence": ["The certificate's criterion 1 says 60 days. Schedule 1 says 30.",
                      f"{x4['loans']} loans are 31 to 59 days past due.",
                      f"They total US${x4['amount']:,.2f}."],
         "suggestion": "Query the borrower and ask for a corrected certificate.",
         "actions": ["query"], "blocking": True, "drill": "E1"},
        {"id": "X5", "type": "conflicting", "label": "Data integrity",
         "title": f"{x5['loans']} loans share {len(x5['clusters'])} VINs", "owner": "Credit",
         "where": "Loan tape, VIN column",
         "evidence": ["Each VIN appears on two different loans.",
                      f"Together they total US${x5['amount']:,.2f}.",
                      "This may be double pledging. The check covers this pool only."],
         "suggestion": "Escalate to credit before these loans are accepted.",
         "actions": ["escalate"], "blocking": True, "drill": "E12"},
        {"id": "X6", "type": "ambiguous", "label": "Possible match",
         "title": '"Sunrise Motors LLC" and "Sunrise Motors" may be one dealer',
         "owner": "Onboarding analyst", "where": "Loan tape, DealerName column",
         "evidence": [f"Separately they are {x6['share_pct_each']['Sunrise Motors LLC']}% and "
                      f"{x6['share_pct_each']['Sunrise Motors']}% of the eligible pool.",
                      f"Together they are {x6['share_pct_combined']}%, over the 5% limit.",
                      "Schedule 2 treats variations of one name as one dealer."],
         "suggestion": "Accept the match. The borrowing base will be recalculated.",
         "actions": ["accept"], "recalculates": True,
         "source": link(ca, "trading under variations of one name")},
        {"id": "X7", "type": "missing", "label": "Blank field",
         "title": "April recoveries are blank", "owner": "Servicer",
         "where": "Servicer report, section 2",
         "evidence": ["The recoveries line has no value for April.",
                      f"The delinquency trigger can still run: {x7['three_month_average_pct']}% "
                      f"against {x7['trigger_pct']}%."],
         "suggestion": "Ask the servicer for the April figure.", "actions": ["query"]},
        {"id": "X8", "type": "ambiguous", "label": "Derived field",
         "title": "Weighted average APR is not a tape column", "owner": "Onboarding analyst",
         "where": "Lender requirements sheet",
         "evidence": ["Calderwood asks for this field.",
                      f"Calculated from the tape: {key['X8']['value_pct']:.2f}%.",
                      f"Formula: {key['X8']['formula']}."],
         "suggestion": "Accept the derived field.", "actions": ["accept"]},
        {"id": "X9", "type": "ambiguous", "label": "Format conflict",
         "title": f"Origination dates mix formats in {x9['rows']} rows",
         "owner": "Onboarding analyst", "where": "Loan tape, OrigDate column",
         "evidence": ["Most rows are MM/DD/YYYY and a batch is DD/MM/YYYY.",
                      "Each row was resolved against its first payment date.",
                      f"{len(x9['uncertain_loan_ids'])} row stays uncertain."],
         "suggestion": "Accept the resolution.", "actions": ["accept"]},
        {"id": "X10", "type": "ambiguous", "label": "Cross-reference",
         "title": "Leverage Ratio depends on 1.1 and 6.12(c)", "owner": "Onboarding analyst",
         "where": "Credit Agreement 1.1 and 6.12(c)",
         "evidence": [f"Without the carve-out the ratio reads "
                      f"{x10['leverage_without_carve_out']} and looks like a breach.",
                      f"With it the ratio is {x10['leverage_with_carve_out']}, within 6.00.",
                      "The carve-out applies to this ratio only."],
         "suggestion": "Confirm the full formula.", "actions": ["accept"], "tier1": True,
         "source": link(ca, "Solely for the purpose of calculating the Leverage Ratio")},
    ]


def _documents() -> list[dict[str, Any]]:
    pack = read_key("pack")
    documents = []
    for doc, info in DOCUMENT_INFO.items():
        file_name = pack[doc]
        if file_name.endswith(".pdf"):
            size = f"{len(_page_text(doc))} pages"
        elif file_name.endswith(".csv"):
            size = f"{len(tape_rows()):,} rows, {len(tape_rows()[0])} columns"
        else:
            size = "Workbook"
        documents.append({"id": doc, "file": file_name, "size": size, **info})
    return documents


_build_lock = threading.Lock()


def workbench() -> dict[str, Any]:
    # The startup warm-up and a first request must not both do this work.
    with _build_lock:
        return _build_workbench()


@lru_cache
def _build_workbench() -> dict[str, Any]:
    return {
        "seed": True,
        "period_end": PERIOD_END.isoformat(),
        "documents": _documents(),
        "missing_documents": [{
            "name": "Schedule 4: Restricted Jurisdictions",
            "reason": "Referred to in the credit agreement but not in the pack",
        }],
        "terms": [_term(field) for field in read_key("fields")],
        "rules": rule_views(),
        "mapping": _mapping(),
        "exceptions": _exceptions(),
    }
