"""Compare the platform's results with the domain team's independent QC workbook.

Code classifies every line: agreement, a presentation difference (blank against dash, rounding,
sign convention, per cent against decimal) or a genuine variance. A genuine variance holds the
report as provisional until an analyst records how it was resolved.
"""

from pathlib import Path
from typing import Any

from engine.alerts import CLASSES, classify
from openpyxl import load_workbook

QC_FILES = {
    "bramble": "QC_Bramble_May_2026.xlsx",
    "northmoor": "QC_Northmoor_May_2026.xlsx",
    "kestrel": "QC_Kestrel_Q1_2026.xlsx",
    "larkspur": "QC_Larkspur_May_2026.xlsx",
}


def platform_values(cycle: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """The platform's figure for each QC line, as the cycle computed it."""
    t, recon = cycle["tests"], cycle["reconciliation"]
    b, n, k, lark = t["bramble"], t["northmoor"], t["kestrel"], t["larkspur"]["borrowing_base"]
    bb = b["borrowing_base"]["system"]
    nd = {m["month"].split()[0]: m["value"] for m in n["delinquency"]["monthly"]}
    spread = {m["month"].split()[0]: m["value"] for m in n["excess_spread_months"]}
    return {
        "bramble": {
            "Eligible pool balance": bb["eligible_pool"],
            "Concentration excess": bb["excess"],
            "Advance rate": bb["advance_rate_pct"],
            "Borrowing base": bb["borrowing_base"],
            "Availability": bb["availability"],
            "Defaulted receivables in the borrowing base": 0,
            "Principal collections": recon["roll_forward"]["collections"],
            "Gross charge-offs": recon["roll_forward"]["charge_offs"],
            "60+ day delinquency, May": b["delinquency"]["monthly"][-1]["value"],
        },
        "northmoor": {
            "60+ day delinquency, March": nd.get("March"),
            "60+ day delinquency, April": nd.get("April"),
            "60+ day delinquency, May": nd.get("May"),
            "Three-month average": n["delinquency"]["average"],
            "June level that breaches": n["delinquency"]["next_month_breaches_beyond"],
            "Excess spread, April": spread.get("April"),
        },
        "kestrel": {
            "Net asset value": k["nav"],
            "Loans outstanding": k["drawn"],
            "Loan-to-value, reported NAV": k["ltv"]["reported"],
            "Loan-to-value, with markdown": k["ltv"]["with_markdown"],
            "Largest investment": k["concentration"]["largest_pct"],
            "Five largest investments": k["concentration"]["top_five_pct"],
        },
        "larkspur": {
            "Aggregate principal balance": lark["total_par"],
            "CCC obligations": lark["ccc_par"],
            "CCC share": lark["ccc_pct"],
            "CCC excess": lark["ccc_excess"],
            "CCC excess adjustment": lark["haircut"],
            "Adjusted collateral balance": lark["adjusted"],
            "Borrowing base": lark["borrowing_base"],
            "Availability": lark["availability"],
        },
    }


def read_qc(path: Path) -> list[tuple[str, Any, str, int]]:
    sheet = load_workbook(path, read_only=True)["QC"]
    return [
        (row[0], row[1], row[2], index)
        for index, row in enumerate(sheet.iter_rows(min_row=5, values_only=True), start=5)
        if row[0]
    ]


def compare(cycle: dict[str, Any], folder: Path) -> dict[str, Any]:
    values = platform_values(cycle)
    result = {}
    for facility, file in QC_FILES.items():
        lines = []
        for line, qc_value, unit, row in read_qc(folder / file):
            platform = values[facility].get(line)
            kind = classify(platform, qc_value, unit)
            lines.append({
                "line": line,
                "unit": unit,
                "platform": platform,
                "qc": qc_value,
                "class": kind,
                "label": CLASSES[kind],
                "cell": f"QC!B{row}",
            })
        result[facility] = {
            "file": file,
            "lines": lines,
            "agrees": sum(x["class"] == "agrees" for x in lines),
            "presentation": sum(x["class"] not in ("agrees", "genuine") for x in lines),
            "genuine": [x["line"] for x in lines if x["class"] == "genuine"],
        }
    return result
