"""Build the answer key. The pipeline must never read this output."""

import json
import re
from datetime import date, datetime
from pathlib import Path
from typing import Any

import pdfplumber

from dealkit.calc import View, borrower_view, system_view
from dealkit.reports import delinquency_ratio, financial_figures
from dealkit.tape import COLUMNS, Tape

PACK_FILES = {
    "credit_agreement": "Bramble_Credit_Agreement_Executed.pdf",
    "amendment_1": "Bramble_Amendment_No_1.pdf",
    "fee_letter": "Bramble_Fee_Letter.pdf",
    "loan_tape": "BAF_Loan_Tape_2026-04.csv",
    "servicer_report": "BAF_Servicer_Report_April_2026.pdf",
    "borrowing_base_certificate": "Bramble_BBC_April_2026.xlsx",
    "financial_statements": "BAF_Financial_Statements_Q1_2026.pdf",
    "lender_requirements": "Calderwood_Requirements.xlsx",
}


def normalise(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def page_texts(path: Path) -> list[str]:
    with pdfplumber.open(path) as pdf:
        return [normalise(page.extract_text() or "") for page in pdf.pages]


def _field(name: str, tier: int, document: str, clause: str, value: Any,
           quote: str | None) -> dict[str, Any]:
    return {"name": name, "tier": tier, "document": document, "clause": clause, "value": value,
            "quote": quote}


def _fields(deal: dict[str, Any]) -> list[dict[str, Any]]:
    t = deal["terms"]
    ca, am = "credit_agreement", "amendment_1"
    return [
        _field("Facility limit", 1, ca, "Annex A", deal["facility"]["limit_usd"], None),
        _field("Advance rate", 1, am, "2(a), amending Credit Agreement 2.3",
               [{"pct": t["advance_rate_original_pct"], "to": "2026-02-28"},
                {"pct": t["advance_rate_amended_pct"], "from": "2026-03-01"}],
               'In Section 2.3, "85%" is deleted and replaced with "82.5%"'),
        _field("Eligibility criteria", 1, ca, "Schedule 1", 12, "ELIGIBILITY CRITERIA"),
        _field("Concentration limits", 1, ca, "Schedule 2; Amendment No. 1 2(b)", 5,
               "CONCENTRATION LIMITS"),
        _field("Excess concentration treatment", 1, ca, "1.1 Borrowing Base",
               "Excess amounts excluded from the eligible pool",
               "Excess amounts identified under Schedule 2 are excluded"),
        _field("Reserve amount", 1, ca, "1.1 Reserve Amount", "1% of eligible pool",
               "of the Eligible Pool Balance."),
        _field("Delinquency trigger", 1, ca, "7.1", "60+ day delinquency above 6.0%, three-month "
               "average", "three most recently ended Collection Periods exceeds 6.0%"),
        _field("Minimum tangible net worth covenant", 1, ca, "6.12(a)",
               t["min_tangible_net_worth_usd"], "is not less than US$40,000,000"),
        _field("Maximum leverage covenant", 1, ca, "6.12(b)", t["max_leverage_ratio"],
               "does not exceed 6.00 to 1.00"),
        _field("Minimum liquidity covenant", 1, ca, "6.12(d)", t["min_liquidity_usd"],
               "Liquidity at all times is not less than US$10,000,000"),
        _field("Restricted jurisdictions", 1, ca, "Schedule 4 (missing from the pack)", None,
               None),
        _field("Margin", 2, ca, "2.6", "Term SOFR + 3.25%", "plus 3.25%"),
        _field("Unused fee", 2, "fee_letter", "2", "0.50% a year", "Unused Fee of 0.50% a year"),
        _field("Interest period and payment date", 2, ca, "2.7", "Monthly, 15th of each month",
               "Each Interest Period is one month"),
        _field("Borrowing base reporting date", 2, ca, "Schedule 3",
               "15th business day after month end", "On or before the 15th Business Day"),
        _field("Financial statement reporting", 2, ca, "Schedule 3",
               "Quarterly within 45 days; annual audited within 120 days",
               "Within 45 days after"),
        _field("Revolving period end", 2, ca, "1.1", t["revolving_period_end"].isoformat(),
               '"Revolving Period End Date" means January 15, 2028'),
        _field("Final maturity", 2, ca, "1.1", t["final_maturity"].isoformat(),
               '"Final Maturity Date" means January 15, 2029'),
        _field("Event of default list", 2, ca, "8.1", t["events_of_default"],
               'Each of the following is an "Event of Default"'),
        _field("Lender alert thresholds", 2, "lender_requirements", "Alerts", 6, None),
        _field("Borrower, parent and servicer names", 3, ca, "Parties",
               {"borrower": deal["borrower"]["name"], "parent": deal["borrower"]["parent"],
                "servicer": deal["servicer"]["name"]}, "is entered into as of"),
        _field("Lender and agent names", 3, ca, "Parties", deal["lender"]["name"],
               "as lender (the"),
        _field("Governing law", 3, ca, "10.9", f"{t['governing_law']} law",
               "governed by the law of the State of New York"),
        _field("Signing date", 3, ca, "Cover", t["signing_date"].isoformat(),
               "dated as of January 15, 2026"),
        _field("Amendment dates", 3, am, "Cover; 2(a)",
               {"signed": t["amendment_signed"].isoformat(),
                "effective": t["amendment_effective"].isoformat()},
               "with effect from 1 March 2026"),
        _field("Notice addresses", 3, ca, "10.2",
               {"borrower": deal["borrower"]["address"], "lender": deal["lender"]["address"]},
               "Attention: Treasurer"),
    ]


def _locate(fields: list[dict[str, Any]], pack_dir: Path) -> None:
    """Record the page of each quote, failing the build if a quote is not in its document."""
    texts = {doc: page_texts(pack_dir / name) for doc, name in PACK_FILES.items()
             if name.endswith(".pdf")}
    for field in fields:
        if field["quote"] is None or field["document"] not in texts:
            field["page"] = None
            continue
        pages = texts[field["document"]]
        needle = normalise(field["quote"])
        # Later matches win for schedule headings, which also appear in the contents list.
        hits = [number for number, body in enumerate(pages, start=1) if needle in body]
        if not hits:
            raise ValueError(f"Quote not found for {field['name']}: {field['quote']!r}")
        field["page"] = hits[-1]
    # A scanned page carries nothing but the running header and page number.
    scans = [number for number, body in enumerate(texts["credit_agreement"], start=1)
             if len(body) < 60]
    if len(scans) != 1:
        raise ValueError(f"Expected one image-only page, found {scans}")
    next(f for f in fields if f["name"] == "Facility limit")["page"] = scans[0]


def _summary(view: View) -> dict[str, Any]:
    return {
        "gross_pool": view.gross_pool / 100,
        "eligible_pool": view.eligible_pool / 100,
        "excess_concentration": view.excess / 100,
        "advance_rate_pct": view.advance_rate_pct,
        "reserve": view.reserve / 100,
        "borrowing_base": view.borrowing_base / 100,
        "availability": view.availability / 100,
        "concentrations": {
            rule: {**item, "amount": item["amount_cents"] / 100,
                   "excess": item["excess_cents"] / 100}
            for rule, item in view.concentrations.items()
        },
    }


def _rules(deal: dict[str, Any], system: View) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for rule in deal["eligibility"]:
        rule_id = rule["id"]
        if rule_id == "E7":
            result[rule_id] = {"status": "not_evaluated", "reason": "Schedule 4 missing"}
            continue
        failed = system.failures_by_rule.get(rule_id, [])
        result[rule_id] = {"status": "evaluated", "failed": len(failed), "loan_ids": failed}
    return result


def _x9(tape: Tape) -> dict[str, Any]:
    """Count mixed rows that the first payment date cannot settle either way."""
    def parsed(raw: str, fmt: str) -> date | None:
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            return None

    mixed = set(tape.planted["x9_loans"])
    uncertain = []
    for row in tape.rows:
        if row["loan_id"] not in mixed:
            continue
        readings = [parsed(row["raw_origination_date"], fmt) for fmt in ("%m/%d/%Y", "%d/%m/%Y")]
        plausible = [r for r in readings if r and 20 <= (row["first_payment_date"] - r).days <= 60]
        if len(set(plausible)) != 1:
            uncertain.append(row["loan_id"])
    return {"rows": len(mixed), "loan_ids": sorted(mixed), "uncertain_loan_ids": uncertain}


def _exceptions(deal: dict[str, Any], tape: Tape, borrower: View, before: View,
                after: View) -> dict[str, Any]:
    balances = {row["loan_id"]: row["current_balance"] for row in tape.rows}
    x4 = tape.planted["x4_loans"]
    x5 = tape.planted["x5_clusters"]
    x5_ids = [loan for cluster in x5 for loan in cluster["loan_ids"]]
    groups = tape.planted["x6_groups"]
    eligible_ids = {row["loan_id"] for row in before.eligible_rows}
    pool = before.eligible_pool / 100
    f = deal["financials"]
    figures = financial_figures(deal)
    tnw = figures["tangible_net_worth"]
    adjusted_tnw = tnw + f["subordinated_debt"]
    history = deal["servicer_history"]
    ratio = delinquency_ratio(tape.rows)
    weighted = sum(r["apr"] * r["current_balance"] for r in before.eligible_rows) / sum(
        r["current_balance"] for r in before.eligible_rows)

    def share(ids: list[str]) -> float:
        return round(sum(balances[i] for i in ids if i in eligible_ids) / pool * 100, 2)

    return {
        "X1": {"type": "conflicting", "applied_pct": 82.5, "superseded_pct": 85},
        "X2": {"type": "missing", "rule": "E7", "document": "Schedule 4"},
        "X3": {"type": "low_confidence", "field": "Facility limit",
               "value": deal["facility"]["limit_usd"]},
        "X4": {"type": "conflicting", "loans": len(x4), "loan_ids": x4,
               "amount": round(sum(balances[i] for i in x4), 2),
               "cause": "Borrower tested 60 days past due instead of 30"},
        "X5": {"type": "data_integrity", "clusters": x5, "loans": len(x5_ids),
               "amount": round(sum(balances[i] for i in x5_ids), 2)},
        "X6": {"type": "ambiguous", "names": deal["planted"]["x6_dealer_names"],
               "share_pct_each": {name: share(ids) for name, ids in groups.items()},
               "share_pct_combined": share([i for ids in groups.values() for i in ids]),
               "excess_after_match": after.concentrations["C2"]["excess_cents"] / 100},
        "X7": {"type": "missing", "field": "Recoveries", "document": "servicer_report",
               "delinquency_ratio_pct": {"february": history["february_pct"],
                                         "march": history["march_pct"], "april": ratio},
               "three_month_average_pct": round(
                   (history["february_pct"] + history["march_pct"] + ratio) / 3, 2),
               "trigger_pct": deal["terms"]["delinquency_trigger_pct"]},
        "X8": {"type": "derived", "field": "Weighted average APR", "value_pct": round(weighted, 4),
               "formula": "sum(apr * current_balance) / sum(current_balance), eligible pool"},
        "X9": {"type": "ambiguous", **_x9(tape)},
        "X10": {"type": "cross_reference", "clauses": ["1.1", "6.12(c)"],
                "tangible_net_worth_k": tnw,
                "leverage_without_carve_out": round(f["total_liabilities"] / tnw, 2),
                "leverage_with_carve_out": round(
                    figures["adjusted_liabilities"] / adjusted_tnw, 2)},
    }


def build_key(deal: dict[str, Any], tape: Tape, pack_dir: Path, key_dir: Path) -> None:
    borrower = borrower_view(tape.rows, deal)
    before = system_view(tape.rows, deal, match_dealers=False)
    after = system_view(tape.rows, deal, match_dealers=True)
    exceptions = _exceptions(deal, tape, borrower, before, after)

    fields = _fields(deal)
    _locate(fields, pack_dir)

    gap = (borrower.eligible_pool - before.eligible_pool) / 100
    key = {
        "fields.json": fields,
        "rules.json": _rules(deal, before),
        "calculation.json": {
            "borrower_certificate": _summary(borrower),
            "system_before_dealer_match": _summary(before),
            "system_after_dealer_match": _summary(after),
            "eligible_pool_bridge": {
                "borrower": borrower.eligible_pool / 100,
                "past_due_loans": -exceptions["X4"]["amount"],
                "duplicate_vin_loans": -exceptions["X5"]["amount"],
                "system": before.eligible_pool / 100,
                "total_gap": gap,
            },
            "status": "provisional: E7 not run",
        },
        "exceptions.json": exceptions,
        "mapping.json": {
            "columns": COLUMNS,
            "derived": [{"field": "Weighted average APR", "source": "NoteRate, CurrBal"}],
        },
        "pack.json": PACK_FILES,
    }
    key_dir.mkdir(parents=True, exist_ok=True)
    for name, content in key.items():
        (key_dir / name).write_text(json.dumps(content, indent=2, sort_keys=True) + "\n",
                                    encoding="utf-8")
