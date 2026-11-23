"""Excel outputs for new deals: the configuration workbook and load file of a case, and the
monthly lender workbook of a live facility. Inputs carry a note with their source; results are
live formulas over the inputs. Each says Provisional until its approvals are complete."""

import io
from typing import Any

from openpyxl import Workbook
from openpyxl.comments import Comment
from openpyxl.styles import Font, PatternFill

BOLD = Font(bold=True)
INPUT = Font(color="1F4E9A")
HEAD = PatternFill("solid", fgColor="E8E4DA")


def _head(sheet: Any, values: list[str]) -> None:
    sheet.append(values)
    for cell in sheet[sheet.max_row]:
        cell.font, cell.fill = BOLD, HEAD


def _bytes(book: Workbook) -> bytes:
    out = io.BytesIO()
    book.save(out)
    return out.getvalue()


def configuration(case: dict[str, Any], final: bool) -> bytes:
    state = case["state"]
    book = Workbook()
    cover = book.active
    cover.title = "Case"
    cover.append([f"{case['ref']} {case['facility_name']} - configuration "
                  f"({'final' if final else 'provisional'})"])
    cover["A1"].font = Font(bold=True, size=13)
    for label, value in (("Client", case["client"]["name"]), ("Deal type", case["deal_type"]),
                         ("Commitment (US$)", case["commitment_cents"] / 100),
                         ("Approved by", state.get("approved_by") or "Not yet approved"),
                         ("Audit chain head", case["history"]["entries"][0]["hash"]
                          if case["history"]["entries"] else "")):
        cover.append([label, value])
    terms = book.create_sheet("Terms")
    _head(terms, ["Term", "Tier", "Value", "Status", "Document", "Page", "Clause", "Quote",
                  "Source", "Effective from"])
    for t in (state.get("terms") or {}).values():
        terms.append([t["label"], t["tier"], t.get("value") or "", t["status"],
                      t.get("doc_name") or "", t.get("page") or "", t.get("clause") or "",
                      t.get("quote") or "", t.get("source"), t.get("effective_from") or ""])
    rules = book.create_sheet("Rules")
    _head(rules, ["Rule", "Kind", "Clause", "Plain English", "Test", "Document", "Page",
                  "Clause text", "Source"])
    for kind in ("eligibility", "concentration"):
        for r in (state.get("rules") or {}).get(kind, []):
            rules.append([r["id"], kind, r.get("ref"), r.get("plain_english"),
                          r.get("describe"), r.get("document"), r.get("page"),
                          r.get("clause_text"), r.get("source")])
    fields = book.create_sheet("Field map")
    _head(fields, ["Source column", "Loader field", "Sample", "Check"])
    mapping = state.get("mapping") or {}
    for item in mapping.get("checks", []):
        fields.append([item.get("column") or "", item.get("field") or "(not loaded)",
                       item.get("sample") or "", item.get("problem") or "OK"])
    statuses = book.create_sheet("Statuses")
    _head(statuses, ["Tape status", "Standard status"])
    for raw, standard in (mapping.get("status_map") or {}).items():
        statuses.append([raw, standard])
    exceptions = book.create_sheet("Exceptions")
    _head(exceptions, ["Ref", "Type", "Severity", "Title", "Status", "Last note"])
    for e in state.get("exceptions", []):
        exceptions.append([e["ref"], e["type"], e["severity"], e["title"], e["status"],
                           (e["history"][-1]["note"] if e.get("history") else "")])
    run = book.create_sheet("Expected output")
    engine = (state.get("validation") or {}).get("engine")
    if engine:
        _head(run, ["Line", "Value (US$)", "How"])
        run.append(["Gross pool", engine["gross_pool_cents"] / 100, "Tape"])
        run.append(["Eligible pool", engine["eligible_pool_cents"] / 100, "Engine"])
        run.append(["Excess concentration", engine["excess_cents"] / 100, "Engine"])
        run.append(["Advance rate (%)", float(engine["advance_rate_pct"]),
                    engine["advance_rate_source"]])
        run.append(["Reserve", engine["reserve_cents"] / 100, "Engine"])
        run.append(["Borrowing base", "=(B3-B4)*B5/100-B6", "Formula"])
        run.append(["Facility limit", engine["facility_limit_cents"] / 100, "Terms"])
        run.append(["Availability", "=MIN(B7,B8)", "Formula"])
    return _bytes(book)


def lender_report(facility: dict[str, Any], sub: dict[str, Any]) -> bytes:
    state = sub["state"]
    engine = state["validation"]["engine"]
    tests = state.get("tests") or {}
    report = state.get("report") or {}
    released = bool(report.get("released_at"))
    book = Workbook()
    sheet = book.active
    sheet.title = "Report"
    sheet.append([f"{facility['name']} - monthly report {sub['period']} "
                  f"({'released' if released else 'provisional'})"])
    sheet["A1"].font = Font(bold=True, size=13)
    _head(sheet, ["Line", "Value", "Source"])
    rows = [
        ("Gross pool (US$)", engine["gross_pool_cents"] / 100, f"Tape {sub['tape_name']}"),
        ("Eligible pool (US$)", engine["eligible_pool_cents"] / 100, "Engine, facility rule set"),
        ("Excess concentration (US$)", engine["excess_cents"] / 100, "Engine"),
        ("Advance rate (%)", float(engine["advance_rate_pct"]), engine["advance_rate_source"]),
        ("Reserve (US$)", engine["reserve_cents"] / 100, "Engine"),
    ]
    for label, value, source in rows:
        sheet.append([label, value, source])
        sheet.cell(row=sheet.max_row, column=2).font = INPUT
        sheet.cell(row=sheet.max_row, column=2).comment = Comment(source, "Oxane")
    sheet.append(["Borrowing base (US$)", "=(B4-B5)*B6/100-B7", "Formula"])
    sheet.append(["Facility limit (US$)", facility["commitment_cents"] / 100, "Agreement"])
    sheet.append(["Availability (US$)", "=MIN(B8,B9)", "Formula"])
    if tests.get("delinquency_months"):
        sheet.append([])
        _head(sheet, ["Delinquency, month", "Ratio (%)", "Source"])
        start = sheet.max_row + 1
        for month in tests["delinquency_months"]:
            sheet.append([month["period"], float(month["value"]), "Engine, from tape"])
        end = sheet.max_row
        sheet.append(["Rolling average (%)", f"=ROUND(AVERAGE(B{start}:B{end}),2)", "Formula"])
        sheet.append(["Trigger (%)", float(tests["delinquency_limit"]),
                      tests.get("delinquency_source") or "Agreement"])
        sheet.append(["Breached", f"=IF(B{end + 1}>B{end + 2},\"Yes\",\"No\")", "Formula"])
    text = book.create_sheet("Commentary")
    for paragraph in report.get("text", []):
        text.append([paragraph])
    approvals = book.create_sheet("Approvals")
    _head(approvals, ["Level", "Title", "By", "At"])
    for a in report.get("approvals", []):
        approvals.append([a["level"], a["title"], a["by"], a["at"]])
    return _bytes(book)
