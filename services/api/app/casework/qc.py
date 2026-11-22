"""Compare the platform's first borrowing base with the domain team's independent QC workbook.

Code classifies every line with the same rules as the monitoring cycle: agreement, a
presentation difference (blank against dash, rounding, sign, per cent against decimal) or a
genuine variance. For each genuine variance code then looks for the loans that explain it, by
testing whether the difference equals the balance of a set of receivables with one feature in
common. The report stays provisional until each genuine variance has a recorded resolution.
"""

from collections.abc import Callable
from decimal import Decimal
from pathlib import Path
from typing import Any

from engine.alerts import CLASSES, classify
from engine.covenants import delinquency_ratio
from engine.run import Loan, RunResult, weighted_average
from openpyxl import load_workbook


def platform_values(result: RunResult, loans: list[Loan], fico_rule: str, state_rule: str
                    ) -> dict[str, Any]:
    state = result.concentrations.get(state_rule)
    return {
        "Loans on the tape": len(loans),
        "Aggregate outstanding balance of pool receivables": result.gross_pool_cents / 100,
        "Eligible pool balance": result.eligible_pool_cents / 100,
        "Excess concentration amount": result.excess_cents / 100,
        "Advance rate": float(result.advance_rate_pct),
        "Reserve amount": result.reserve_cents / 100,
        "Borrowing base": result.borrowing_base_cents / 100,
        "Availability": result.availability_cents / 100,
        "Excluded under criterion 7 (Restricted Jurisdictions)": (
            None if result.rules["E7"].status == "not_evaluated"
            else result.rules["E7"].failed_cents / 100),
        "Sub-600 FICO bucket balance": result.concentrations[fico_rule].largest_cents / 100,
        "Largest single-state share": float(state.share_pct) if state else None,
        "Weighted average APR, eligible pool": round(float(weighted_average(
            loans, result.eligible_loan_ids, "apr")), 2),
        "60+ day delinquency ratio, April": float(delinquency_ratio(loans)),
    }


def read_qc(path: Path) -> list[tuple[str, Any, str, int]]:
    sheet = load_workbook(path, read_only=True)["QC"]
    return [(row[0], row[1], row[2], index)
            for index, row in enumerate(sheet.iter_rows(min_row=5, values_only=True), start=5)
            if row[0]]


def _explain(difference: Decimal, loans: list[Loan], eligible: set[str]
             ) -> dict[str, Any] | None:
    """A set of receivables, sharing one feature, whose balance is the whole difference."""
    tests: list[tuple[str, Callable[[Loan], bool]]] = [
        ("charged-off receivables", lambda x: x["status"] == "CHARGED_OFF"),
        ("repossessed receivables", lambda x: x["status"] == "REPO"),
        ("eligible receivables with a FICO score of exactly 600",
         lambda x: x["loan_id"] in eligible and x["fico"] == 600),
        ("eligible receivables with a FICO score of exactly 540",
         lambda x: x["loan_id"] in eligible and x["fico"] == 540),
        ("receivables exactly 30 days past due", lambda x: x["days_past_due"] == 30),
        ("receivables 60 or more days past due", lambda x: x["days_past_due"] >= 60),
    ]
    for label, test in tests:
        chosen = [x for x in loans if test(x)]
        total = Decimal(sum(x["current_balance"] for x in chosen)) / 100
        if chosen and abs(abs(difference) - total) < Decimal("0.01"):
            return {"loans": len(chosen), "label": label, "amount": float(total),
                    "loan_ids": sorted(x["loan_id"] for x in chosen)[:12]}
    return None


def compare(path: Path, result: RunResult, loans: list[Loan], fico_rule: str, state_rule: str
            ) -> dict[str, Any]:
    values = platform_values(result, loans, fico_rule, state_rule)
    eligible = set(result.eligible_loan_ids)
    lines = []
    for line, qc_value, unit, row in read_qc(path):
        platform = values.get(line)
        kind = classify(platform, qc_value, unit)
        entry = {"line": line, "unit": unit, "platform": platform, "qc": qc_value,
                 "class": kind, "label": CLASSES[kind], "cell": f"QC!B{row}"}
        if kind == "genuine" and isinstance(platform, int | float) and isinstance(
                qc_value, int | float):
            difference = Decimal(str(platform)) - Decimal(str(qc_value))
            entry["difference"] = float(difference)
            entry["explained_by"] = _explain(difference, loans, eligible)
        lines.append(entry)
    return {
        "file": path.name,
        "lines": lines,
        "agrees": sum(x["class"] == "agrees" for x in lines),
        "presentation": sum(x["class"] not in ("agrees", "genuine") for x in lines),
        "genuine": [x["line"] for x in lines if x["class"] == "genuine"],
    }
