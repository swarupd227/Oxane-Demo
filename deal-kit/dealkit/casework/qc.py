"""The domain team's independent QC calculation of Bramble's first borrowing base.

The team rebuilds the April result in its own template before the first report is released.
Its figures come from this kit's calculations, not the platform's, and the template presents
some of them its own way: whole dollars, deductions as negatives, rates as decimals, a dash for
nothing. Two figures differ for a real reason:

- the QC template takes the sub-600 FICO bucket from Calderwood's model, which uses FICO 600 and
  below, where the agreement says below 600;
- the QC template leaves charged-off receivables out of the gross pool, where the platform keeps
  them in the pool and excludes them as ineligible. Eligible pool and borrowing base still agree.

Each line records the class the platform's comparison should give it, for the scorecard.
"""

from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from openpyxl import Workbook
from openpyxl.styles import Font

from dealkit.calc import cents, failures
from dealkit.reports import delinquency_ratio
from dealkit.workbooks import _header, _save_stable


def _lines(rows: list[dict[str, Any]], agreed: dict[str, Any], deal: dict[str, Any]
           ) -> list[tuple[str, Any, str, str]]:
    vin_counts = Counter(row["vin"] for row in rows)
    eligible = [row for row in rows if not failures(row, vin_counts)]
    pool = agreed["eligible_pool"]
    live = [row for row in rows if row["status"] != "CHARGED_OFF"]
    gross_without_charge_offs = sum(cents(row["current_balance"]) for row in live) / 100
    weighted = sum(row["apr"] * row["current_balance"] for row in eligible) / sum(
        row["current_balance"] for row in eligible)
    states: defaultdict[str, int] = defaultdict(int)
    for row in eligible:
        states[row["obligor_state"]] += cents(row["current_balance"])
    largest_state = round(max(states.values()) / cents(pool) * 100, 2)
    bucket_le_600 = sum(cents(r["current_balance"]) for r in eligible if r["fico"] <= 600) / 100
    whole = float(round(pool))
    apr_qc = round(weighted, 3)
    rate = deal["terms"]["advance_rate_amended_pct"]
    reserve = round(pool * deal["terms"]["reserve_pct"] / 100, 2)
    return [
        ("Loans on the tape", len(rows), "count", "agrees"),
        ("Aggregate outstanding balance of pool receivables", gross_without_charge_offs, "US$",
         "genuine"),
        ("Eligible pool balance", whole, "US$", "agrees" if whole == pool else "rounding"),
        ("Excess concentration amount", -agreed["excess"], "US$", "sign"),
        ("Advance rate", round(rate / 100, 4), "%", "percent"),
        ("Reserve amount", reserve, "US$", "agrees"),
        ("Borrowing base", agreed["borrowing_base"], "US$", "agrees"),
        ("Availability", agreed["availability"], "US$", "agrees"),
        ("Excluded under criterion 7 (Restricted Jurisdictions)", "-", "US$", "blank"),
        ("Sub-600 FICO bucket balance", bucket_le_600, "US$", "genuine"),
        ("Largest single-state share", round(largest_state / 100, 4), "%", "percent"),
        ("Weighted average APR, eligible pool", apr_qc, "%",
         "agrees" if apr_qc == round(weighted, 2) else "rounding"),
        ("60+ day delinquency ratio, April", delinquency_ratio(rows), "%", "agrees"),
    ]


def build_qc(rows: list[dict[str, Any]], agreed: dict[str, Any], deal: dict[str, Any],
             casework: dict[str, Any], path: Path) -> dict[str, Any]:
    lines = _lines(rows, agreed, deal)
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "QC"
    sheet["A1"] = "Independent QC calculation: Bramble Auto Receivables I, April 2026"
    sheet["A1"].font = Font(bold=True, size=13)
    sheet["A2"] = (f"Prepared by the {casework['qc']['preparer']} from the source documents, "
                   "before the first report is released.")
    _header(sheet, 4, ["Line", "QC value", "Unit"])
    for line, value, unit, _ in lines:
        sheet.append([line, value, unit])
    sheet.column_dimensions["A"].width = 56
    sheet.column_dimensions["B"].width = 20
    _save_stable(workbook, path)
    return {
        "file": casework["qc"]["file"],
        "lines": [{"line": line, "qc_value": value, "expected": expected}
                  for line, value, _, expected in lines],
    }
