"""The lender-facing Excel workbook for one facility, with live formulas.

Every calculated cell is a real Excel formula over the input cells, so a client can trace it.
Every input cell carries a note naming its source document and page, or file and cell. A last
sheet sets the platform's results beside the independent QC calculation, with each variance
classified. The workbook says Provisional until every approval level has signed off.

Each formula is built together with its value, so the tests can check that Excel's answer and
the engine's agree without opening Excel.
"""

import io
from dataclasses import dataclass
from typing import Any

from openpyxl import Workbook
from openpyxl.comments import Comment
from openpyxl.styles import Font, PatternFill

INPUT_FONT = Font(color="1F4E9A")
BOLD = Font(bold=True)
HEAD_FILL = PatternFill("solid", fgColor="E8E4DA")
FORMATS = {"US$": '#,##0.00;(#,##0.00);"-"', "%": "0.00", "x": "0.00", "pts": "0.00",
           "days": "0", "count": "#,##0", "": "General"}


@dataclass(frozen=True)
class X:
    """A formula and the value it gives."""

    f: str
    v: float

    @staticmethod
    def of(other: "X | float | int") -> "X":
        return other if isinstance(other, X) else X(repr(float(other)).rstrip("0").rstrip("."),
                                                    float(other))

    def __add__(self, o: "X | float") -> "X":
        o = X.of(o)
        return X(f"{self.f}+{o.f}", self.v + o.v)

    def __sub__(self, o: "X | float") -> "X":
        o = X.of(o)
        return X(f"{self.f}-({o.f})", self.v - o.v)

    def __mul__(self, o: "X | float") -> "X":
        o = X.of(o)
        return X(f"({self.f})*({o.f})", self.v * o.v)

    def __truediv__(self, o: "X | float") -> "X":
        o = X.of(o)
        return X(f"({self.f})/({o.f})", self.v / o.v)


def _round(value: float, places: int) -> float:
    from decimal import ROUND_HALF_UP, Decimal

    return float(Decimal(str(value)).quantize(Decimal(1).scaleb(-places), ROUND_HALF_UP))


def ROUND(x: X, places: int) -> X:  # noqa: N802 - Excel's own names
    return X(f"ROUND({x.f},{places})", _round(x.v, places))


def MIN(*xs: X | float) -> X:  # noqa: N802
    items = [X.of(x) for x in xs]
    return X(f"MIN({','.join(i.f for i in items)})", min(i.v for i in items))


def MAX(*xs: X | float) -> X:  # noqa: N802
    items = [X.of(x) for x in xs]
    return X(f"MAX({','.join(i.f for i in items)})", max(i.v for i in items))


def ABS(x: X) -> X:  # noqa: N802
    return X(f"ABS({x.f})", abs(x.v))


def SUM(cells: list[X]) -> X:  # noqa: N802
    return X(f"SUM({','.join(c.f for c in cells)})", sum(c.v for c in cells))


def AVERAGE(cells: list[X]) -> X:  # noqa: N802
    return X(f"AVERAGE({','.join(c.f for c in cells)})", sum(c.v for c in cells) / len(cells))


def source_text(source: dict[str, Any] | None, fallback: str) -> str:
    if not source:
        return fallback
    name = source["document"].split("/")[-1]
    return f"{name}, page {source['page']}" + (f" ({source['label']})" if source.get(
        "label") else "")


class Book:
    def __init__(self, title: str, status: str) -> None:
        self.wb = Workbook()
        self.summary = self.wb.active
        self.summary.title = "Summary"
        self.inputs = self._sheet("Inputs", ["Input", "Value", "Unit", "Source"])
        self.calc = self._sheet("Calculation", ["Result", "Value", "Unit", "How it is worked out"])
        self.values: dict[str, float] = {}
        self.summary["A1"] = title
        self.summary["A1"].font = Font(bold=True, size=14)
        self.summary["A2"] = status
        self.summary["A2"].font = Font(bold=True, color="9C2B1C" if "PROVISIONAL" in status
                                       else "2E6B3A")
        self.summary.column_dimensions["A"].width = 60
        self.summary.column_dimensions["B"].width = 22

    def _sheet(self, name: str, header: list[str]):  # noqa: ANN202
        ws = self.wb.create_sheet(name)
        for column, value in enumerate(header, start=1):
            cell = ws.cell(row=1, column=column, value=value)
            cell.font, cell.fill = BOLD, HEAD_FILL
        for column, width in zip("ABCD", [48, 20, 8, 70], strict=True):
            ws.column_dimensions[column].width = width
        return ws

    def note(self, line: str) -> None:
        row = self.summary.max_row + 1
        self.summary.cell(row=row, column=1, value=line)

    def input(self, label: str, value: Any, unit: str, source: str) -> X:
        ws = self.inputs
        row = ws.max_row + 1
        ws.cell(row=row, column=1, value=label)
        cell = ws.cell(row=row, column=2, value=value)
        cell.font = INPUT_FONT
        cell.number_format = FORMATS.get(unit, "General")
        cell.comment = Comment(f"Source: {source}", "Oxane platform")
        ws.cell(row=row, column=3, value=unit)
        ws.cell(row=row, column=4, value=source)
        number = float(value) if isinstance(value, int | float) else 0.0
        return X(f"Inputs!$B${row}", number)

    def calc_row(self, label: str, x: X, unit: str, how: str) -> X:
        ws = self.calc
        row = ws.max_row + 1
        ws.cell(row=row, column=1, value=label)
        cell = ws.cell(row=row, column=2, value=f"={x.f}")
        cell.number_format = FORMATS.get(unit, "General")
        ws.cell(row=row, column=3, value=unit)
        ws.cell(row=row, column=4, value=how)
        self.values[label] = x.v
        return X(f"Calculation!$B${row}", x.v)

    def text_calc(self, label: str, formula: str, how: str) -> None:
        ws = self.calc
        row = ws.max_row + 1
        ws.cell(row=row, column=1, value=label)
        ws.cell(row=row, column=2, value=f"={formula}")
        ws.cell(row=row, column=4, value=how)

    def qc(self, comparison: dict[str, Any], links: dict[str, X]) -> None:
        ws = self.wb.create_sheet("QC comparison")
        header = ["Line", "Platform", "Independent QC", "Difference", "Class", "Unit"]
        for column, value in enumerate(header, start=1):
            cell = ws.cell(row=1, column=column, value=value)
            cell.font, cell.fill = BOLD, HEAD_FILL
        for column, width in zip("ABCDEF", [44, 20, 20, 16, 40, 8], strict=True):
            ws.column_dimensions[column].width = width
        ws.cell(row=2, column=1, value=f"QC workbook: {comparison['file']}")
        for row, line in enumerate(comparison["lines"], start=3):
            ws.cell(row=row, column=1, value=line["line"])
            link = links.get(line["line"])
            platform = ws.cell(row=row, column=2, value=f"={link.f}" if link else line["platform"])
            platform.number_format = FORMATS.get(line["unit"], "General")
            qc = ws.cell(row=row, column=3, value=line["qc"])
            qc.font = INPUT_FONT
            qc.number_format = FORMATS.get(line["unit"], "General")
            qc.comment = Comment(f"Source: {comparison['file']}, {line['cell']}", "Oxane platform")
            if isinstance(line["qc"], int | float):
                ws.cell(row=row, column=4, value=f"=B{row}-C{row}").number_format = FORMATS.get(
                    line["unit"], "General")
            ws.cell(row=row, column=5, value=line["label"])
            ws.cell(row=row, column=6, value=line["unit"])

    def save(self) -> bytes:
        for ws in (self.inputs, self.calc):
            ws.freeze_panes = "A2"
        buffer = io.BytesIO()
        self.wb.save(buffer)
        return buffer.getvalue()


def _status(cycle: dict[str, Any], session: dict[str, Any], facility: str) -> str:
    released = session.get("packs", {}).get(facility)
    if released:
        return f"RELEASED {released['at'][:10]}, approved by {released['by']}"
    return "PROVISIONAL: not for release until every approval level has signed off"


def build(
    cycle: dict[str, Any], session: dict[str, Any], facility_id: str
) -> tuple[bytes, dict[str, float]]:
    facility = next(f for f in cycle["facilities"] if f["id"] == facility_id)
    book = Book(f"{facility['name']}: {cycle['cycle']['label']} monitoring workbook",
                _status(cycle, session, facility_id))
    book.note("")
    book.note(f"Client: {facility.get('client_name', '')}")
    book.note(f"Period end: {cycle['cycle']['period_end']}")
    book.note("Blue figures on Inputs are taken from the source named in each cell's note.")
    book.note("Every figure on Calculation is an Excel formula over Inputs.")
    book.note("QC comparison sets the platform's results beside the independent QC workbook.")
    links = BUILDERS[facility_id](book, cycle)
    book.qc(cycle["qc"][facility_id], links)
    return book.save(), book.values


def _bramble(book: Book, cycle: dict[str, Any]) -> dict[str, X]:
    t = cycle["tests"]["bramble"]
    bb, recon, lev = t["borrowing_base"], cycle["reconciliation"], t["leverage"]
    s = bb["system"]
    tape = "BAF_Loan_Tape_2026-05.csv"
    gross = book.input("Gross pool balance", s["gross_pool"], "US$",
                       f"{tape}: CurrBal of loans in the pool, rules engine")
    ineligible = book.input("Receivables that are not eligible", s["ineligible"], "US$",
                            f"{tape}: loans failing eligibility criteria E1 to E12")
    excess = book.input("Concentration excess", s["excess"], "US$",
                        "Rules engine: dealer limit 5% in force for May (Schedule 2)")
    rate = book.input("Advance rate", s["advance_rate_pct"], "%", s["advance_rate_source"])
    reserve = book.input("Reserve", s["reserve_pct"], "%", "Credit Agreement, Reserve Account")
    limit = book.input("Facility limit", s["facility_limit"], "US$",
                       "Credit Agreement; US$300m applies only from 1 Jun 2026")
    outstanding = book.input("Advances outstanding", s["outstanding"], "US$",
                             "Facility record: advances outstanding at 31 May 2026")
    cert = {k: book.input(f"Certificate: {k.replace('_', ' ')}", v, "US$",
                          f"Bramble_BBC_May_2026.xlsx, BBC Summary!{cell}")
            for (k, v), cell in zip(bb["certificate"].items(), ("B7", "B11", "B13"),
                                    strict=True)}
    eligible = book.calc_row("Eligible pool", gross - ineligible, "US$",
                             "Gross pool less receivables that are not eligible")
    base = book.calc_row(
        "Borrowing base",
        ROUND((eligible - excess) * rate / 100, 2) - ROUND(eligible * reserve / 100, 2),
        "US$", "(Eligible pool less concentration excess) x advance rate, less the reserve")
    available = book.calc_row("Availability", MIN(base, limit) - outstanding, "US$",
                              "Lesser of borrowing base and limit, less advances outstanding")
    for key, mine in (("eligible_pool", eligible), ("borrowing_base", base),
                      ("availability", available)):
        diff = book.calc_row(f"Certificate less platform: {key.replace('_', ' ')}",
                             cert[key] - mine, "US$", "Within US$50 is logged, not alerted")
        book.text_calc(f"Within tolerance: {key.replace('_', ' ')}",
                       f'IF(ABS({diff.f})<=50,"Within","Outside")', "Tolerance US$50")
    rf = recon["roll_forward"]
    opening = book.input("Pool balance, end of April", rf["opening"], "US$",
                         "BAF_Loan_Tape_2026-04.csv (onboarding), loans in the pool")
    additions = book.input("Receivables purchased", rf["additions"], "US$",
                           f"{tape}: new loans ({rf['new_loans']})")
    collections = book.input("Principal collections", rf["collections"], "US$",
                             source_text(rf["sources"]["collections"], "Servicer report"))
    offs = book.input("Charge-offs on the tape", rf["charge_offs"], "US$",
                      f"{tape}: ChgOffAmt of loans charged off in May")
    actual = book.input("Pool balance on the May tape", rf["actual"], "US$", tape)
    expected = book.calc_row("Expected pool balance", opening + additions - collections - offs,
                             "US$", "April balance plus purchases, less collections and "
                             "charge-offs")
    book.calc_row("Roll-forward gap", expected - actual, "US$",
                  "Expected less the tape; traced to loans missing from the tape")
    months = [book.input(f"60+ day delinquency, {m['month']}", m["value"], "%",
                         "Servicer report trend" if i < 2 else f"{tape}, recomputed")
              for i, m in enumerate(t["delinquency"]["monthly"])]
    trigger = book.input("Delinquency trigger", t["delinquency"]["limit"], "%",
                         "Credit Agreement Section 7.1")
    average = book.calc_row("Three-month average", ROUND(AVERAGE(months), 2), "%",
                            "Average of the last three months")
    book.calc_row("Headroom to the trigger", trigger - average, "pts", "Trigger less average")
    tl = book.input("Total liabilities (US$ thousands)", lev["total_liabilities_k"], "",
                    "BAF_Financial_Statements_Q1_2026.pdf, balance sheet")
    tnw = book.input("Tangible net worth (US$ thousands)", lev["tangible_net_worth_k"], "",
                     "BAF_Financial_Statements_Q1_2026.pdf, spread by code")
    carve = book.input("Subordinated debt carve-out (US$ thousands)", lev["carve_out_k"], "",
                       "Credit Agreement 6.12(c): lesser of subordinated debt and the cap")
    guarantee = book.input("Affiliate guarantee (US$ thousands)", lev["guarantees_k"], "",
                           source_text(lev["guarantees"][0]["source"] if lev["guarantees"]
                                       else None, "Compliance certificate"))
    book.input("Maximum leverage", lev["maximum"], "x", "Credit Agreement 6.12(b)")
    book.calc_row("Leverage, balance sheet", ROUND((tl - carve) / (tnw + carve), 2), "x",
                  "(Total liabilities less carve-out) / (tangible net worth plus carve-out)")
    book.calc_row("Leverage, counting the guarantee",
                  ROUND((tl + guarantee - carve) / (tnw + carve), 2), "x",
                  "Expert view needed: whether the guarantee counts as a liability")
    return {
        "Eligible pool balance": eligible, "Concentration excess": excess, "Advance rate": rate,
        "Borrowing base": base, "Availability": available,
        "Principal collections": collections, "Gross charge-offs": offs,
        "60+ day delinquency, May": months[-1],
    }


def _northmoor(book: Book, cycle: dict[str, Any]) -> dict[str, X]:
    n = cycle["tests"]["northmoor"]
    d = n["delinquency"]
    months = [book.input(f"60+ day delinquency, {m['month']}", m["value"], "%",
                         f"NMC_Tape_2026-{('03', '04', '05')[i]}.csv, recomputed from the tape")
              for i, m in enumerate(d["monthly"])]
    trigger = book.input("Delinquency trigger", d["limit"], "%",
                         source_text(d["source"], "Credit Agreement 7.1(a)"))
    average = book.calc_row("Three-month average", ROUND(AVERAGE(months), 2), "%",
                            "Average of March, April and May")
    june = book.calc_row("June level that breaches", ROUND(trigger * 3 - months[1] - months[2], 2),
                         "%", "Three times the trigger, less April and May")
    book.calc_row("Headroom to the trigger", trigger - average, "pts", "Trigger less average")
    spreads = {}
    for item in n["excess_spread_months"]:
        parts = {k: book.input(f"{item['month']}: {k}", v, "US$",
                               source_text(item["sources"].get(k), "Servicer report"))
                 for k, v in item["parts"].items()}
        spreads[item["month"]] = book.calc_row(
            f"Excess spread, {item['month']}",
            ROUND((parts["Interest collections"] - parts["Servicing fee"]
                   - parts["Interest on advances"] - parts["Charge-offs net of recoveries"]) * 12
                  / parts["Ending principal balance"] * 100, 2),
            "%", "(Interest less fees, interest on advances and net charge-offs) x 12 / pool")
    return {
        "60+ day delinquency, March": months[0], "60+ day delinquency, April": months[1],
        "60+ day delinquency, May": months[2], "Three-month average": average,
        "June level that breaches": june,
        "Excess spread, April": spreads.get("April 2026", X("0", 0)),
    }


def _kestrel(book: Book, cycle: dict[str, Any]) -> dict[str, X]:
    k = cycle["tests"]["kestrel"]
    nav = book.input("Net asset value", k["nav"], "US$", source_text(k["nav_source"], "NAV report"))
    drawn = book.input("Loans outstanding", k["drawn"], "US$",
                       source_text(k["drawn_source"], "Compliance certificate"))
    markdown = book.input("Post-quarter markdown", k["ltv"]["markdown"], "US$",
                          source_text(k["ltv"]["events"][0]["source"] if k["ltv"]["events"]
                                      else None, "Valuation report, section 2"))
    book.input("Maximum loan-to-value", k["ltv"]["limit"], "%", "NAV Facility Agreement 7.1")
    values = [book.input(f"Fair value: {p['name']}", p["value"], "US$",
                         f"Kestrel_Q1_2026_Valuation_Report.pdf, valued {p['valued']}")
              for p in k["positions"]]
    ltv = book.calc_row("Loan-to-value, reported NAV", ROUND(drawn / nav * 100, 1), "%",
                        "Loans outstanding / NAV")
    marked = book.calc_row("Loan-to-value, with markdown",
                           ROUND(drawn / (nav - markdown) * 100, 1), "%",
                           "Loans outstanding / (NAV less the markdown); expert view needed")
    first, last = values[0].f.split("!")[1], values[-1].f.split("!")[1]
    ordered = sorted(v.v for v in values)
    largest = book.calc_row("Largest investment",
                            X(f"ROUND(MAX(Inputs!{first}:{last})/{nav.f}*100,1)",
                              _round(ordered[-1] / nav.v * 100, 1)), "%",
                            "Largest fair value / NAV")
    top = book.calc_row("Five largest investments",
                        X(f"ROUND(SUMPRODUCT(LARGE(Inputs!{first}:{last},{{1,2,3,4,5}}))"
                          f"/{nav.f}*100,1)", _round(sum(ordered[-5:]) / nav.v * 100, 1)), "%",
                        "Five largest fair values / NAV")
    return {"Net asset value": nav, "Loans outstanding": drawn,
            "Loan-to-value, reported NAV": ltv, "Loan-to-value, with markdown": marked,
            "Largest investment": largest, "Five largest investments": top}


def _larkspur(book: Book, cycle: dict[str, Any]) -> dict[str, X]:
    t = cycle["tests"]["larkspur"]
    bb = t["borrowing_base"]
    ws = book.wb.create_sheet("Positions", 1)
    header = ["LoanX ID", "Issuer", "Par", "Moody's", "S&P", "CCC (lower of)", "Bid",
              "Market value"]
    for column, value in enumerate(header, start=1):
        cell = ws.cell(row=1, column=column, value=value)
        cell.font, cell.fill = BOLD, HEAD_FILL
    for column, width in zip("ABCDEFGH", [11, 32, 16, 9, 8, 15, 9, 16], strict=True):
        ws.column_dimensions[column].width = width
    rows = {}
    for row, p in enumerate(t["positions"], start=2):
        ws.cell(row=row, column=1, value=p["loanx"])
        ws.cell(row=row, column=2, value=p["issuer"])
        par = ws.cell(row=row, column=3, value=p["par"])
        par.font, par.number_format = INPUT_FONT, FORMATS["US$"]
        par.comment = Comment(f"Source: {t['positions_file']}, Positions!E{p['sheet_row']}",
                              "Oxane platform")
        ws.cell(row=row, column=4, value=p["moodys"])
        ws.cell(row=row, column=5, value=p["sp"])
        ccc = ws.cell(row=row, column=6, value="Yes" if p["ccc"] else "No")
        ccc.comment = Comment("Thornbury's master field: the lower of Moody's and S&P",
                              "Oxane platform")
        bid = ws.cell(row=row, column=7, value=p["bid"])
        bid.font = INPUT_FONT
        bid.comment = Comment(f"Source: {t['prices_file']}, row {p['price_row']}, Bid",
                              "Oxane platform")
        ws.cell(row=row, column=8, value=f"=ROUND(C{row}*G{row}/100,2)").number_format = \
            FORMATS["US$"]
        rows[p["loanx"]] = (row, p)
    last = len(t["positions"]) + 1
    pars = [p["par"] for p in t["positions"]]
    total = book.calc_row("Aggregate principal balance", X(f"SUM(Positions!C2:C{last})",
                                                           sum(pars)), "US$", "Sum of par")
    ccc_par = book.calc_row("CCC obligations",
                            X(f'SUMIF(Positions!F2:F{last},"Yes",Positions!C2:C{last})',
                              sum(p["par"] for p in t["positions"] if p["ccc"])), "US$",
                            "Par of loans rated Caa1 or CCC+ or below, lower of the two")
    limit_pct = book.input("CCC limit", bb["ccc_limit_pct"], "%",
                           source_text(t["ccc_source"], "Credit Agreement 1.1"))
    rate = book.input("Advance rate", bb["advance_rate_pct"], "%",
                      "Larkspur_Warehouse_Credit_Agreement.pdf, Borrowing Base")
    commitment = book.input("Commitment", bb["commitment"], "US$", "Credit Agreement, cover")
    drawn = book.input("Loans outstanding", bb["drawn"], "US$",
                       "Facility record: loans outstanding at the Determination Date")
    share = book.calc_row("CCC share", ROUND(ccc_par / total * 100, 2), "%", "CCC par / total par")
    allowed = book.calc_row("CCC allowed", ROUND(total * limit_pct / 100, 2), "US$",
                            "Total par x CCC limit")
    excess = book.calc_row("CCC excess", MAX(0, ccc_par - allowed), "US$",
                           "CCC par above the allowed amount")
    ccc_rows = sorted((rows[p["loanx"]] for p in t["positions"] if p["ccc"]),
                      key=lambda item: (item[1]["bid"], item[1]["loanx"]))
    cuts, before = [], X.of(0)
    for row, p in ccc_rows:
        par, bid = X(f"Positions!C{row}", p["par"]), X(f"Positions!G{row}", p["bid"])
        allocated = book.calc_row(f"Excess carried at market value: {p['issuer']}",
                                  MIN(par, MAX(0, excess - before)), "US$",
                                  "Lowest bid first, up to the CCC excess")
        cuts.append(book.calc_row(f"Haircut: {p['issuer']}",
                                  ROUND(allocated * (X.of(1) - bid / 100), 2), "US$",
                                  "Excess part x (1 less bid / 100)"))
        before = before + par
    haircut = book.calc_row("CCC excess adjustment", SUM(cuts), "US$", "Sum of the haircuts")
    adjusted = book.calc_row("Adjusted collateral balance", total - haircut, "US$",
                             "Total par less the CCC excess adjustment")
    base = book.calc_row("Borrowing base", ROUND(adjusted * rate / 100, 2), "US$",
                         "Advance rate x adjusted collateral balance")
    available = book.calc_row("Availability", MIN(commitment, base) - drawn, "US$",
                              "Lesser of commitment and borrowing base, less loans outstanding")
    return {"Aggregate principal balance": total, "CCC obligations": ccc_par, "CCC share": share,
            "CCC excess": excess, "CCC excess adjustment": haircut,
            "Adjusted collateral balance": adjusted, "Borrowing base": base,
            "Availability": available}


BUILDERS = {"bramble": _bramble, "northmoor": _northmoor, "kestrel": _kestrel,
            "larkspur": _larkspur}
