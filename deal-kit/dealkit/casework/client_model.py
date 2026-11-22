"""Calderwood's own borrowing base model, as the lender sends it with a new facility.

The template is the desk's standard one, issued before Amendment No. 1 and carrying house
conventions. The onboarding team has to set it against the agreement: where the two differ, the
agreement governs the borrowing base, and the difference becomes a query to the client.
"""

from pathlib import Path
from typing import Any

from openpyxl import Workbook
from openpyxl.styles import Font

from dealkit.workbooks import _header, _save_stable


def build_client_model(deal: dict[str, Any], casework: dict[str, Any], path: Path
                       ) -> dict[str, Any]:
    spec = casework["client_model"]
    workbook = Workbook()
    cover = workbook.active
    cover.title = "Cover"
    cover["A1"] = f"{deal['lender']['name']}: warehouse borrowing base model"
    cover["A1"].font = Font(bold=True, size=14)
    lines = [
        f"Template version {spec['template_version']}, issued {spec['issued']:%d %B %Y}",
        f"Owner: {deal['lender']['desk']}",
        f"Facility: {deal['borrower']['name']}",
        "One copy per facility. Parameters follow the facility agreement unless the desk "
        "standard says otherwise.",
        "Sheets: Parameters, Limits, Reporting.",
    ]
    for row, line in enumerate(lines, start=3):
        cover.cell(row=row, column=1, value=line)
    cover.column_dimensions["A"].width = 96

    cells: dict[str, dict[str, Any]] = {}

    def sheet(name: str, header: list[str], items: list[dict[str, Any]]) -> None:
        ws = workbook.create_sheet(name)
        _header(ws, 1, header)
        for row, item in enumerate(items, start=2):
            ws.cell(row=row, column=1, value=item["ref"])
            ws.cell(row=row, column=2, value=item["label"])
            cell = ws.cell(row=row, column=3, value=item["value"])
            if isinstance(item["value"], float):
                cell.number_format = "0.00%"
            if "note" in item:
                ws.cell(row=row, column=4, value=item["note"] or None)
            cells[item["topic"]] = {"ref": item["ref"], "cell": f"{name}!C{row}",
                                    "value": item["value"], "differs": item.get("differs", False)}
        ws.column_dimensions["A"].width = 6
        ws.column_dimensions["B"].width = 30
        ws.column_dimensions["C"].width = 84
        ws.column_dimensions["D"].width = 40

    sheet("Parameters", ["Ref", "Parameter", "Value", "Basis"], spec["parameters"])
    sheet("Limits", ["Ref", "Limit", "Share of base"], spec["limits"])
    sheet("Reporting", ["Ref", "Requirement", "Detail"], spec["reporting"])
    _save_stable(workbook, path)
    return cells
