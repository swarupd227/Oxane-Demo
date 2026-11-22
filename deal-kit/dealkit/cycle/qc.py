"""The independent QC calculation for each facility, as the domain team's own workbooks.

The domain team rebuilds each result in its own template before a report is released. Its
figures come from this kit's calculations, not the platform's, and its template presents some of
them differently: a dash for nothing, whole dollars, outflows as negatives, rates as decimals.
One figure differs for a real reason: the QC model takes Bramble's charge-offs from the servicer
report, which includes nine loans the tape still shows as live.

Each line records the class the platform's comparison should give it, for the scorecard.
"""

from pathlib import Path
from typing import Any

from openpyxl import Workbook
from openpyxl.styles import Font

from dealkit.workbooks import _header, _save_stable

FILES = {
    "bramble": "QC_Bramble_May_2026.xlsx",
    "northmoor": "QC_Northmoor_May_2026.xlsx",
    "kestrel": "QC_Kestrel_Q1_2026.xlsx",
    "larkspur": "QC_Larkspur_May_2026.xlsx",
}


def _lines(key: dict[str, Any]) -> dict[str, list[tuple[str, Any, str, str]]]:
    """(line, QC value, unit, expected class) for each facility."""
    checks = key["checks"]
    bb = checks["bramble_borrowing_base"]["system"]
    rate = checks["terms_version"]["may"]["advance_rate_pct"]
    roll, offs = checks["roll_forward"], checks["charge_offs"]
    nd, spread = checks["northmoor_delinquency"], checks["northmoor_excess_spread"]
    k, lark = checks["kestrel"], checks["larkspur"]["may"]
    eligible = bb["eligible_pool"]
    whole = float(round(eligible))
    return {
        "bramble": [
            ("Eligible pool balance", whole, "US$",
             "agrees" if whole == eligible else "rounding"),
            ("Concentration excess", bb["excess"], "US$", "agrees"),
            ("Advance rate", rate / 100, "%", "percent"),
            ("Borrowing base", bb["borrowing_base"], "US$", "agrees"),
            ("Availability", bb["availability"], "US$", "agrees"),
            ("Defaulted receivables in the borrowing base", "-", "US$", "blank"),
            ("Principal collections", -roll["principal_collected"], "US$", "sign"),
            ("Gross charge-offs", offs["servicer"], "US$", "genuine"),
            ("60+ day delinquency, May", checks["bramble_delinquency"]["may"], "%", "agrees"),
        ],
        "northmoor": [
            ("60+ day delinquency, March", nd["march"], "%", "agrees"),
            ("60+ day delinquency, April", nd["april"], "%", "agrees"),
            ("60+ day delinquency, May", nd["may"], "%", "agrees"),
            ("Three-month average", nd["average"], "%", "agrees"),
            ("June level that breaches", nd["june_breach_above"], "%", "agrees"),
            ("Excess spread, April", round(spread["april"]["pct"] / 100, 4), "%", "percent"),
        ],
        "kestrel": [
            ("Net asset value", k["nav"], "US$", "agrees"),
            ("Loans outstanding", k["drawn"], "US$", "agrees"),
            ("Loan-to-value, reported NAV", k["ltv_reported_pct"], "%", "agrees"),
            ("Loan-to-value, with markdown",
             round(k["drawn"] / k["adjusted_nav"] * 100, 2), "%", "rounding"),
            ("Largest investment", k["largest_position_pct"], "%", "agrees"),
            ("Five largest investments", k["top_five_pct"], "%", "agrees"),
        ],
        "larkspur": [
            ("Aggregate principal balance", lark["total_par"], "US$", "agrees"),
            ("CCC obligations", lark["ccc_par"], "US$", "agrees"),
            ("CCC share", lark["ccc_pct"], "%", "agrees"),
            ("CCC excess", lark["ccc_excess"], "US$", "agrees"),
            ("CCC excess adjustment", -lark["haircut"], "US$", "sign"),
            ("Adjusted collateral balance", lark["adjusted_balance"], "US$", "agrees"),
            ("Borrowing base", lark["borrowing_base"], "US$", "agrees"),
            ("Availability", lark["availability"], "US$", "agrees"),
        ],
    }


def build_qc(key: dict[str, Any], folder: Path) -> dict[str, Any]:
    result = {}
    for facility, lines in _lines(key).items():
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "QC"
        sheet["A1"] = f"Independent QC calculation: {facility.title()}"
        sheet["A1"].font = Font(bold=True, size=13)
        sheet["A2"] = "Prepared by the domain team from source documents, before release."
        _header(sheet, 4, ["Line", "QC value", "Unit"])
        for line, value, unit, _ in lines:
            sheet.append([line, value, unit])
        sheet.column_dimensions["A"].width = 46
        sheet.column_dimensions["B"].width = 20
        _save_stable(workbook, folder / FILES[facility])
        result[facility] = {
            "file": FILES[facility],
            "lines": [{"line": line, "qc_value": value, "expected": expected}
                      for line, value, _, expected in lines],
        }
    return result
