"""The borrower's certificate and the lender requirements sheet, as Excel workbooks."""

import re
import zipfile
from pathlib import Path
from typing import Any

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill

from dealkit.calc import View

BOLD = Font(bold=True)
SHADE = PatternFill("solid", fgColor="DDE6F0")
FIXED_TIME = (2026, 5, 20, 9, 0, 0)


def _save_stable(workbook: Workbook, path: Path) -> None:
    """openpyxl stamps the save time into the file, so fix it to keep builds identical."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    workbook.save(temporary)
    with zipfile.ZipFile(temporary) as source, zipfile.ZipFile(
        path, "w", compression=zipfile.ZIP_DEFLATED
    ) as target:
        for name in sorted(source.namelist()):
            data = source.read(name)
            if name == "docProps/core.xml":
                data = re.sub(rb"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", b"2026-05-20T09:00:00Z",
                              data)
            info = zipfile.ZipInfo(name, date_time=FIXED_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            target.writestr(info, data)
    temporary.unlink()


def _header(sheet: Any, row: int, values: list[str]) -> None:
    for column, value in enumerate(values, start=1):
        cell = sheet.cell(row=row, column=column, value=value)
        cell.font = BOLD
        cell.fill = SHADE


def build_bbc(deal: dict[str, Any], view: View, path: Path) -> None:
    """Write the certificate from the borrower's own, flawed, view of the pool."""
    workbook = Workbook()
    summary = workbook.active
    summary.title = "BBC Summary"
    summary["A1"] = deal["borrower"]["name"]
    summary["A1"].font = Font(bold=True, size=14)
    summary["A2"] = "Borrowing Base Certificate"
    summary["A3"] = "Collection Period ended"
    summary["B3"] = deal["tape"]["cutoff_date"].isoformat()

    outstanding = deal["bbc"]["outstanding_advances_usd"]
    lines = [
        ("1. Aggregate Outstanding Balance of Pool Receivables", view.gross_pool / 100),
        ("2. Less Receivables that are not Eligible Receivables",
         -(view.gross_pool - view.eligible_pool) / 100),
        ("3. Eligible Pool Balance", view.eligible_pool / 100),
        ("4. Less Excess Concentration Amount", -view.excess / 100),
        ("5. Advance Rate", view.advance_rate_pct / 100),
        ("6. Less Reserve Amount", -view.reserve / 100),
        ("7. Borrowing Base", view.borrowing_base / 100),
        ("8. Outstanding Advances", outstanding),
        ("9. Availability", view.availability / 100),
    ]
    for offset, (label, value) in enumerate(lines):
        summary.cell(row=5 + offset, column=1, value=label)
        cell = summary.cell(row=5 + offset, column=2, value=value)
        cell.number_format = "0.0%" if label.startswith("5.") else "#,##0.00"
    summary["A16"] = "Certified by: Treasurer, Bramble Auto Receivables I LLC"
    summary.column_dimensions["A"].width = 58
    summary.column_dimensions["B"].width = 20

    excluded = workbook.create_sheet("Ineligible Detail")
    _header(excluded, 1, ["Criterion", "Description", "Loans excluded"])
    described = {item["id"]: item["text"] for item in deal["eligibility"]}
    described["E1"] = "Not more than 60 days past due"
    row = 2
    for rule in sorted(view.failures_by_rule, key=lambda name: int(name[1:])):
        excluded.append([f"{int(rule[1:])}", described[rule], len(view.failures_by_rule[rule])])
        row += 1
    excluded.column_dimensions["B"].width = 56

    concentration = workbook.create_sheet("Concentration")
    _header(concentration, 1, ["Limit", "Largest", "Balance (US$)", "% of pool", "Limit %",
                               "Excess (US$)"])
    names = {item["id"]: item["text"] for item in deal["concentration"]}
    for rule, item in view.concentrations.items():
        concentration.append([names[rule], item["largest"], item["amount_cents"] / 100,
                              item["share_pct"], item["limit_pct"], item["excess_cents"] / 100])
    concentration.column_dimensions["A"].width = 42
    concentration.column_dimensions["B"].width = 28
    _save_stable(workbook, path)


def build_requirements(deal: dict[str, Any], path: Path) -> None:
    workbook = Workbook()
    fields = workbook.active
    fields.title = "Required Fields"
    fields["A1"] = f"{deal['lender']['name']}: monitoring requirements"
    fields["A1"].font = Font(bold=True, size=14)
    _header(fields, 3, ["Field", "Level", "Required", "Notes"])
    required = [
        ("Loan ID", "Loan", "Y", ""),
        ("VIN", "Loan", "Y", "Must be unique across the pool"),
        ("Origination date", "Loan", "Y", "ISO format"),
        ("Original balance", "Loan", "Y", ""),
        ("Current balance", "Loan", "Y", ""),
        ("APR", "Loan", "Y", ""),
        ("Original term", "Loan", "Y", ""),
        ("Remaining term", "Loan", "Y", ""),
        ("FICO at origination", "Loan", "Y", ""),
        ("Obligor state", "Loan", "Y", ""),
        ("Dealer name", "Loan", "Y", "Group dealers under one parent where known"),
        ("Days past due", "Loan", "Y", ""),
        ("Modification count", "Loan", "Y", ""),
        ("Status", "Loan", "Y", ""),
        ("Charge-off date", "Loan", "N", ""),
        ("New or used", "Loan", "Y", ""),
        ("Model year", "Loan", "Y", ""),
        ("Weighted average APR", "Pool", "Y", "Weighted by current balance"),
        ("Pool balance", "Pool", "Y", ""),
        ("Eligible pool balance", "Pool", "Y", ""),
        ("Borrowing base", "Pool", "Y", ""),
        ("Availability", "Pool", "Y", ""),
    ]
    for item in required:
        fields.append(list(item))
    fields.column_dimensions["A"].width = 28
    fields.column_dimensions["D"].width = 44

    alerts = workbook.create_sheet("Alerts")
    _header(alerts, 1, ["Alert", "Threshold", "Recipient"])
    for item in [
        ("60+ day delinquency", "Above 5%", "Warehouse desk"),
        ("Dealer concentration", "Above 4.5% of eligible pool", "Warehouse desk"),
        ("State concentration", "Above 18% of eligible pool", "Warehouse desk"),
        ("Availability", "Below US$500,000", "Warehouse desk and credit"),
        ("Late borrowing base certificate", "Any", "Warehouse desk"),
        ("Duplicate VIN", "Any", "Credit"),
    ]:
        alerts.append(list(item))
    alerts.column_dimensions["A"].width = 34
    alerts.column_dimensions["B"].width = 30
    alerts.column_dimensions["C"].width = 28

    layout = workbook.create_sheet("Report Layout")
    _header(layout, 1, ["Section", "Content"])
    for item in [
        ("1", "Facility summary: limit, advance rate, outstanding, availability"),
        ("2", "Borrowing base calculation, with differences from the borrower's certificate"),
        ("3", "Eligibility exclusions by criterion"),
        ("4", "Concentration tests"),
        ("5", "Open exceptions and owners"),
    ]:
        layout.append(list(item))
    layout.column_dimensions["B"].width = 76
    _save_stable(workbook, path)
