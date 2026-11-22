"""The configuration workbook: source field to loader field to expected output, with sources.

Today an analyst builds this workbook by hand. Here code writes it from the accepted mapping,
the validated terms and the rule set, and checks that every threshold the rules engine uses is
the figure in its verified source, so no threshold is ever typed. Each row notes where its value
came from, and the workbook says Provisional until the case is approved and its first report
has passed QC.
"""

import io
import re
from decimal import Decimal
from typing import Any

from engine.rules import Between, Compare, Const, RuleSet
from engine.run import INTEGER_FIELDS, MONEY_FIELDS, coerce_loan
from openpyxl import Workbook
from openpyxl.comments import Comment
from openpyxl.styles import Font, PatternFill

from app.pipeline.catalogue import PLATFORM_FIELDS
from app.pipeline.documents import PdfDocument, find_citation, normalise

WORDS = {"one": "1", "once": "1", "two": "2", "ten": "10"}
BOLD = Font(bold=True)
HEAD = PatternFill("solid", fgColor="E8E4DA")
INPUT = Font(color="1F4E9A")


def _numbers(text: str) -> set[Decimal]:
    spelled = re.sub(r"\b(" + "|".join(WORDS) + r")\b", lambda m: WORDS[m.group(1)], text.lower())
    return {Decimal(n.replace(",", "")) for n in re.findall(r"\d[\d,]*(?:\.\d+)?", spelled)}


def _thresholds(test: Any) -> list[Decimal]:
    if isinstance(test, Compare) and isinstance(test.right, Const):
        return [test.right.value]
    if isinstance(test, Between):
        return [test.low, test.high]
    return []


def _near(documents: dict[str, PdfDocument], document: str, quote: str, number: Decimal
          ) -> bool:
    """Whether the number follows the quoted row on its page, as a schedule's limit column."""
    citation = find_citation(documents, document, quote)
    if citation is None:
        return False
    page = documents[document].pages[citation["page"] - 1].text
    start = page.find(normalise(quote))
    return number in _numbers(page[start + len(normalise(quote)): start + len(normalise(quote))
                                   + 40])


def rule_rows(ruleset: RuleSet, documents: dict[str, PdfDocument]) -> list[dict[str, Any]]:
    rows = []
    for rule in ruleset.eligibility:
        citation = find_citation(documents, "credit_agreement", rule.clause_text)
        wanted = _thresholds(rule.test)
        stated = _numbers(rule.clause_text)
        rows.append({
            "id": f"CFG-{rule.id}", "rule": rule.id, "area": "Eligibility",
            "parameter": rule.plain_english, "value": ", ".join(f"{v.normalize():f}"
                                                               for v in wanted) or "List",
            "clause": rule.clause_ref, "quote": rule.clause_text, "source": citation,
            "in_source": all(v in stated for v in wanted) and citation is not None,
            "engine": ", ".join(f"{v.normalize():f}" for v in wanted) or "List",
        })
    for rule in ruleset.concentration:
        document = "amendment_1" if rule.effective_from else "credit_agreement"
        citation = find_citation(documents, document, rule.clause_text)
        rows.append({
            "id": f"CFG-{rule.id}", "rule": rule.id, "area": "Concentration",
            "parameter": rule.plain_english, "value": f"{rule.limit_pct.normalize():f}%",
            "clause": rule.clause_ref, "quote": rule.clause_text, "source": citation,
            "in_source": _near(documents, document, rule.clause_text, rule.limit_pct),
            "engine": f"{rule.limit_pct.normalize():f}%",
            "effective_from": rule.effective_from.isoformat() if rule.effective_from else None,
        })
    return rows


def term_rows(ruleset: RuleSet, terms: dict[str, dict[str, Any]], facts: dict[str, Any]
              ) -> list[dict[str, Any]]:
    """Figures the engine takes from validated terms, checked against the term's value."""
    covenants = facts["covenants"]
    rate = max(ruleset.advance_rates, key=lambda r: r.effective_from)
    wanted = [
        ("CFG-ADV", "Advance rate", "Advance rate", rate.pct, "%"),
        ("CFG-RES", "Reserve amount", "Reserve", ruleset.reserve_pct, "%"),
        ("CFG-LIM", "Facility limit", "Facility limit",
         Decimal(ruleset.facility_limit_cents) / 100, "US$"),
        ("CFG-TNW", "Minimum tangible net worth covenant", "Minimum tangible net worth",
         Decimal(covenants["min_tangible_net_worth"]), "US$"),
        ("CFG-LEV", "Maximum leverage covenant", "Maximum leverage",
         Decimal(str(covenants["max_leverage_ratio"])), "x"),
        ("CFG-LIQ", "Minimum liquidity covenant", "Minimum liquidity",
         Decimal(covenants["min_liquidity"]), "US$"),
        ("CFG-DQT", "Delinquency trigger", "Delinquency trigger",
         Decimal(str(covenants["delinquency_trigger_pct"])), "%"),
    ]
    rows = []
    for ident, name, label, engine_value, unit in wanted:
        term = terms[name]
        stated = _numbers(term["value"])
        rows.append({
            "id": ident, "rule": None, "area": "Facility terms", "parameter": label,
            "term": name, "value": term["value"], "clause": term["clause"],
            "quote": None, "source": term["source"],
            "in_source": bool(term.get("verified")) and engine_value in stated,
            "engine": f"{engine_value.normalize():f}" + ("%" if unit == "%" else ""),
        })
    return rows


def _transform(field: str, dates: dict[str, Any]) -> str:
    if field == "origination_date":
        return (f"Month first (MM/DD/YYYY); {dates['mixed_rows']} day-first rows resolved "
                "against the first payment date")
    if field.endswith("_date"):
        return "ISO date"
    if field in MONEY_FIELDS:
        return "US dollars to whole cents"
    if field in INTEGER_FIELDS:
        return "Whole number"
    if field == "apr":
        return "Per cent, two places"
    if field == "status":
        return "Stored code list"
    return "As received"


def field_rows(stored: dict[str, str], sample: dict[str, str], tape_file: str,
               dates: dict[str, Any], resolved_dates: dict[str, str]) -> list[dict[str, Any]]:
    renamed = {field: sample[column] for column, field in stored.items()}
    loan = coerce_loan({**renamed, "origination_date": resolved_dates.get(
        renamed["loan_id"], renamed["origination_date"])})
    rows = []
    for column, field in stored.items():
        value = loan.get(field, sample[column])
        if field in MONEY_FIELDS:
            shown = f"{value} cents"
        elif hasattr(value, "isoformat"):
            shown = value.isoformat()
        else:
            shown = str(value)
        rows.append({
            "source": column, "file": tape_file, "sample": sample[column], "field": field,
            "meaning": PLATFORM_FIELDS.get(field, ""), "transform": _transform(field, dates),
            "expected": shown,
        })
    return rows


def _fmt(value: Any, unit: str, conventions: dict[str, str]) -> str:
    if value is None:
        return "-" if conventions.get("nil") == "dash" else ""
    if unit == "%":
        if conventions.get("percent") == "decimal":
            return f"{Decimal(str(value)) / 100:.4f}"
        return f"{value}%"
    if unit == "US$":
        return f"{value:,.2f}"
    return f"{value:,}" if isinstance(value, int) else str(value)


def report_rows(values: dict[str, Any], units: dict[str, str], conventions: dict[str, str],
                deductions: set[str]) -> list[dict[str, Any]]:
    rows = []
    for line, value in values.items():
        unit = units[line]
        shown = -value if line in deductions and value and conventions.get(
            "negative") == "negative_number" else value
        rows.append({"line": line, "value": value, "unit": unit,
                     "client_format": _fmt(shown, unit, conventions)})
    return rows


# The workbook


def _sheet(book: Workbook, title: str, header: list[str], widths: list[int]) -> Any:
    ws = book.create_sheet(title)
    for column, (name, width) in enumerate(zip(header, widths, strict=True), start=1):
        cell = ws.cell(row=1, column=column, value=name)
        cell.font, cell.fill = BOLD, HEAD
        ws.column_dimensions[chr(64 + column)].width = width
    ws.freeze_panes = "A2"
    return ws


def _where(source: dict[str, Any] | None, files: dict[str, str]) -> str:
    if not source:
        return "Not in the pack"
    return f"{files.get(source['document'], source['document'])}, page {source['page']}"


def build(record: dict[str, Any], view: dict[str, Any], files: dict[str, str]) -> bytes:
    config = record["config"]
    book = Workbook()
    cover = book.active
    cover.title = "Status"
    cover["A1"] = "Case 0412: Bramble Auto Receivables I, configuration workbook"
    cover["A1"].font = Font(bold=True, size=14)
    cover["A2"] = view["status"]["label"]
    cover["A2"].font = Font(bold=True, color="2E6B3A" if view["status"]["final"] else "9C2B1C")
    lines = [
        "",
        "Built by the platform from the accepted mapping, the validated terms and the rule set.",
        "Every threshold the rules engine uses is checked against the figure in its source.",
        "Blue values are taken from the source named in the cell's note.",
        f"Prepared by: {view['status']['prepared_by']}",
        f"Approved by: {view['status']['approved_by'] or 'Not yet approved'}",
        f"First report released: {view['status']['released'] or 'Not yet released'}",
        f"Rule set digest: {record['config']['ruleset_digest']}",
    ]
    for row, line in enumerate(lines, start=3):
        cover.cell(row=row, column=1, value=line)
    cover.column_dimensions["A"].width = 100

    ws = _sheet(book, "Field map", ["Source field", "Sample", "Loader field", "Meaning",
                                    "Transform", "Expected output"], [16, 22, 26, 40, 50, 24])
    for item in config["fields"]:
        ws.append([item["source"], item["sample"], item["field"], item["meaning"],
                   item["transform"], item["expected"]])
        cell = ws.cell(row=ws.max_row, column=1)
        cell.font = INPUT
        cell.comment = Comment(f"Source: {item['file']}, column {item['source']}; mapping "
                               "accepted by the onboarding analyst", "Oxane platform")

    ws = _sheet(book, "Rules and thresholds",
                ["ID", "Area", "Parameter", "Configured value", "Engine uses", "Matches",
                 "Clause", "Source"], [10, 14, 60, 18, 14, 9, 34, 46])
    for item in view["thresholds"]:
        ws.append([item["id"], item["area"], item["parameter"], item["value"], item["engine"],
                   "Yes" if item["in_source"] else "Check", item["clause"],
                   _where(item["source"], files)])
        cell = ws.cell(row=ws.max_row, column=4)
        cell.font = INPUT
        note = f"Source: {_where(item['source'], files)}"
        if item.get("quote"):
            note += f'. "{item["quote"]}"'
        if item.get("change"):
            note += f". Changed by four-eyes approval: {item['change']}"
        cell.comment = Comment(note, "Oxane platform")

    ws = _sheet(book, "Report lines", ["Line", "Platform value", "Unit", "As the client reports"],
                [52, 20, 8, 24])
    for item in config["report"]:
        ws.append([item["line"], item["value"], item["unit"], item["client_format"]])

    ws = _sheet(book, "Client conventions", ["Topic", "Client's model or template", "Cell",
                                             "Treatment on the platform"], [26, 70, 16, 70])
    for item in view["conventions"]:
        ws.append([item["label"], item["quote"], item["cell"], item["treatment"]])
        ws.cell(row=ws.max_row, column=2).comment = Comment(
            f"Source: {files.get('client_model', 'client model')}, {item['cell']}",
            "Oxane platform")
    buffer = io.BytesIO()
    book.save(buffer)
    return buffer.getvalue()
