"""Ravenglass Direct Lending Fund I: Calderwood Bank's back-leverage facility to a direct lending
fund, secured on a middle-market book of 40 obligor loans.

Each obligor sends quarterly financial statements and a compliance certificate, in one of four
statement layouts and two certificate forms. The fund sends a monthly portfolio report and a
borrowing base certificate. The facility record set at onboarding holds each obligor's loan and
the covenant levels in its underlying loan agreement.

Planted here: one obligor's leverage over its covenant (M13); one obligor whose add-backs need an
expert's reading of the cap (M14); one obligor whose Q1 financials never arrived (M15); one
waiver that raises an obligor's leverage covenant (M16); and the fund's report truncating one
obligor's leverage, 0.01x under the recomputed figure (N6).

Obligor amounts are US$ thousands, in multiples of ten, so every layout prints them exactly.
"""

import csv
import json
from datetime import date, timedelta
from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any

import numpy as np
from openpyxl import Workbook
from openpyxl.styles import Font
from reportlab.lib.units import inch
from reportlab.platypus import PageBreak, Spacer

from dealkit.legal_docs import _date
from dealkit.pdfkit import (
    ARTICLE,
    CENTERED,
    INDENT_1,
    REPORT_BODY,
    REPORT_HEAD,
    REPORT_TITLE,
    SANS,
    SECTION,
    SMALL,
    TITLE,
    build,
    table,
    text,
)
from dealkit.workbooks import _header, _save_stable

FILES = {
    "agreement": "Ravenglass_Back_Leverage_Agreement.pdf",
    "record": "Ravenglass_Obligor_Register.json",
    "portfolio_report": "Ravenglass_Portfolio_Report_2026-05-31.xlsx",
    "borrowing_base_certificate": "Ravenglass_BBC_2026-05-31.xlsx",
    "inbox": "Ravenglass_Inbox_May_2026.csv",
}
LAYOUTS = {
    "A": "Consolidated statements, US$ thousands",
    "B": "Management accounts, US$ millions",
    "C": "Lender reporting template, US$ thousands",
    "D": "Sponsor quarterly pack, US$ thousands",
}
CERTIFICATES = {"standard": "Fund's standard form", "own": "Obligor's own form"}
MAX_LEVERAGE = [5.00, 5.25, 5.50, 5.75, 6.00, 6.50]
MIN_ICR = [1.75, 2.00, 2.25, 2.50]


def ratio(numerator: int, denominator: int) -> Decimal:
    return (Decimal(numerator) / Decimal(denominator)).quantize(Decimal("0.01"), ROUND_HALF_UP)


def tens(value: float) -> int:
    return int(round(value / 10)) * 10


def financials_file(obligor: dict[str, Any]) -> str:
    return f"{obligor['id']}_Financial_Statements_Q1_2026.pdf"


def certificate_file(obligor: dict[str, Any]) -> str:
    return f"{obligor['id']}_Compliance_Certificate_Q1_2026.pdf"


def waiver_file(obligor: dict[str, Any]) -> str:
    return f"Ravenglass_Waiver_Notice_{obligor['id']}_2026-05-18.pdf"


def _finish(o: dict[str, Any], rng: np.random.Generator) -> dict[str, Any]:
    """Everything an obligor's statements print, from its EBITDA, add-backs and net debt."""
    o["covenant_ebitda"] = o["ebitda"] + sum(item[1] for item in o["addbacks"])
    o["leverage"] = float(ratio(o["net_debt"], o["covenant_ebitda"]))
    o["icr"] = float(ratio(o["covenant_ebitda"], o["interest"]))
    o["cash"] = tens(o["net_debt"] * rng.uniform(0.05, 0.14))
    o["gross_debt"] = o["net_debt"] + o["cash"]
    o["revolver"] = tens(o["gross_debt"] * rng.uniform(0.0, 0.12))
    o["term_loan"] = o["gross_debt"] - o["revolver"]
    o["revenue"] = tens(o["ebitda"] / rng.uniform(0.13, 0.27))
    o["gross_profit"] = tens(o["revenue"] * rng.uniform(0.38, 0.55))
    o["cost_of_sales"] = o["revenue"] - o["gross_profit"]
    o["opex"] = o["gross_profit"] - o["ebitda"]
    o["depreciation"] = tens(o["ebitda"] * rng.uniform(0.18, 0.32))
    o["operating_profit"] = o["ebitda"] - o["depreciation"]
    o["pbt"] = o["operating_profit"] - o["interest"]
    return o


def _obligors(spec: dict[str, Any], rng: np.random.Generator) -> list[dict[str, Any]]:
    planted = spec["planted"]
    roles = {"breach": "M13", "addbacks": "M14", "missing": "M15", "waiver": "M16",
             "rounding": "N6"}
    count = spec["obligors"]
    # Planted obligors sit at fixed places in the book, not at its start.
    slots = {"breach": 6, "addbacks": 13, "missing": 21, "waiver": 28, "rounding": 34}
    sectors, sponsors, prefixes = spec["sectors"], spec["sponsors"], spec["prefixes"]
    suffix = {
        "Healthcare services": "Healthcare", "Software": "Software", "Business services":
        "Business Services", "Industrials": "Industries", "Consumer services": "Leisure",
        "Specialty chemicals": "Chemicals", "Education": "Learning", "Food and beverage": "Foods",
        "Insurance services": "Insurance Services", "Logistics": "Logistics",
        "Building products": "Building Products", "Financial technology": "Payments",
    }
    layouts = list("A" * 14 + "B" * 11 + "C" * 9 + "D" * 6)
    order = rng.permutation(len(layouts))
    layouts = [layouts[i] for i in order]
    by_slot = {slot: role for role, slot in slots.items()}
    obligors, used = [], 0
    for index in range(count):
        number = index + 1
        layout = layouts[index]
        base: dict[str, Any] = {
            "id": f"RVG-{number:03d}",
            "layout": layout,
            "certificate_form": "own" if layout == "D" or (layout == "B" and number % 3 == 0)
            else "standard",
            "sponsor": sponsors[int(rng.integers(0, len(sponsors)))],
            "role": None,
        }
        role = by_slot.get(index)
        if role:
            p = planted[role]
            base.update(
                name=p["name"], sector=p["sector"], facility=p["facility"],
                outstanding=p["outstanding"], ebitda=p["ebitda"], net_debt=p["net_debt"],
                interest=p["interest"], max_leverage=p["max_leverage"], min_icr=p["min_icr"],
                addbacks=[[d, a, k] for d, a, k in p.get("items", [])], role=roles[role],
            )
            obligors.append(_finish(base, rng))
            continue
        sector = sectors[(index * 5) % len(sectors)]
        name = f"{prefixes[used]} {suffix[sector]}"
        used += 1
        draw = rng.random()
        facility = "First lien" if draw < 0.5 else "Unitranche" if draw < 0.85 else "Second lien"
        ebitda = int(rng.integers(400, 2400)) * 10
        addbacks = []
        if rng.random() < 0.55:
            if rng.random() < 0.5:
                addbacks.append(["Non-recurring transaction costs",
                                 tens(ebitda * rng.uniform(0.02, 0.07)), "uncapped"])
            else:
                addbacks.append(["Cost savings from the procurement programme",
                                 tens(ebitda * rng.uniform(0.03, 0.10)), "capped"])
        maximum = float(MAX_LEVERAGE[int(rng.integers(0, len(MAX_LEVERAGE)))])
        if facility == "Second lien":
            maximum = 6.50
        minimum = float(MIN_ICR[int(rng.integers(0, len(MIN_ICR)))])
        covenant = ebitda + sum(a[1] for a in addbacks)
        target = max(2.6, maximum - rng.uniform(0.6, 2.1))
        net_debt = tens(target * covenant)
        interest = tens(net_debt * rng.uniform(0.075, 0.10))
        if covenant / interest < minimum + 0.3:
            interest = tens(covenant / (minimum + 0.45))
        base.update(
            name=name, sector=sector, facility=facility,
            outstanding=int(rng.integers(40, 97)) * 100000, ebitda=ebitda, net_debt=net_debt,
            interest=interest, max_leverage=maximum, min_icr=minimum, addbacks=addbacks,
        )
        obligors.append(_finish(base, rng))
    for o in obligors:
        o["commitment"] = int(-(-o["outstanding"] * 1.15 // 1000000)) * 1000000
    return obligors


def build_ravenglass(cycle: dict[str, Any], folder: Path) -> dict[str, Any]:
    spec = cycle["ravenglass"]
    planted = spec["planted"]
    rng = np.random.default_rng(spec["seed"])
    obligors = _obligors(spec, rng)
    by_role = {o["role"]: o for o in obligors if o["role"]}
    missing = by_role["M15"]
    waiver = by_role["M16"]

    # Arrivals: most obligors report in the fortnight before the deadline; two a few days late.
    due: date = spec["financials_due"]
    late = {obligors[3]["id"], obligors[30]["id"]}
    inbox = []
    for o in obligors:
        if o is missing:
            continue
        early = int(rng.integers(0, 9))
        received = due - timedelta(days=early)
        while received.weekday() >= 5:
            received -= timedelta(days=1)
        if o["id"] in late:
            received = due + timedelta(days=3 + (o["id"] == obligors[30]["id"]))
        o["received"] = received
        inbox.append({"document": "obligor_financials", "obligor": o["id"],
                      "label": f"Q1 financial statements, {o['name']}",
                      "file": financials_file(o), "due": due, "received": received,
                      "channel": "Data room"})
        inbox.append({"document": "obligor_compliance", "obligor": o["id"],
                      "label": f"Q1 compliance certificate, {o['name']}",
                      "file": certificate_file(o), "due": due, "received": received,
                      "channel": "Email"})
    missing["received"] = None
    for document, label in (("obligor_financials", "Q1 financial statements"),
                            ("obligor_compliance", "Q1 compliance certificate")):
        inbox.append({"document": document, "obligor": missing["id"],
                      "label": f"{label}, {missing['name']}", "file": None, "due": due,
                      "received": None, "channel": "Data room" if "statements" in label
                      else "Email"})
    w = planted["waiver"]
    inbox.append({"document": "waiver_notice", "obligor": waiver["id"],
                  "label": f"Amendment and waiver notice, {waiver['name']}",
                  "file": waiver_file(waiver), "due": w["received"], "received": w["received"],
                  "channel": "Email"})
    for document, label in (("portfolio_report", "Portfolio report, May"),
                            ("borrowing_base_certificate", "Borrowing base certificate, May")):
        inbox.append({"document": document, "obligor": "", "label": label,
                      "file": FILES[document], "due": date(2026, 6, 12),
                      "received": spec["received"][document], "channel": "Upload"})

    _agreement(cycle, folder / FILES["agreement"])
    _record(spec, obligors, folder / FILES["record"])
    for o in obligors:
        if o is missing:
            continue
        _financials(spec, o, folder / financials_file(o))
        _certificate(spec, o, folder / certificate_file(o))
    _waiver(spec, waiver, folder / waiver_file(waiver))
    _portfolio_report(spec, obligors, folder / FILES["portfolio_report"])
    certificate = _bbc(spec, obligors, folder / FILES["borrowing_base_certificate"])
    with (folder / FILES["inbox"]).open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["document", "obligor", "label", "file", "due",
                                                    "received", "channel"],
                                lineterminator="\n")
        writer.writeheader()
        for row in inbox:
            writer.writerow({**row, "due": row["due"].isoformat(),
                             "received": row["received"].isoformat() if row["received"] else "",
                             "file": row["file"] or ""})
    return _facts(spec, obligors, certificate)


def _facts(spec: dict[str, Any], obligors: list[dict[str, Any]],
           certificate: dict[str, Any]) -> dict[str, Any]:
    """The answer, worked out here independently of the platform's engine."""
    by_role = {o["role"]: o for o in obligors if o["role"]}
    rates = spec["advance_rates"]
    waiver = spec["planted"]["waiver"]

    def maximum(o: dict[str, Any]) -> float:
        return waiver["amended"] if o is by_role["M16"] else o["max_leverage"]

    excluded = {}
    for o in obligors:
        if o is by_role["M15"]:
            excluded[o["id"]] = "financials not delivered"
        elif o["leverage"] > maximum(o) or o["icr"] < o["min_icr"]:
            excluded[o["id"]] = "Material Obligor Event"
    eligible = [o for o in obligors if o["id"] not in excluded]
    total = sum(o["outstanding"] for o in eligible)
    largest = max(eligible, key=lambda o: o["outstanding"])
    sectors: dict[str, int] = {}
    for o in eligible:
        sectors[o["sector"]] = sectors.get(o["sector"], 0) + o["outstanding"]
    top_sector = max(sectors, key=lambda s: sectors[s])

    def value(o: dict[str, Any]) -> Decimal:
        return (Decimal(o["outstanding"]) * Decimal(rates[o["facility"]]) / 100).quantize(
            Decimal("0.01"), ROUND_HALF_UP)

    base = float(sum(value(o) for o in eligible))
    calloway = by_role["M14"]
    capped = sum(a for _, a, kind in calloway["addbacks"] if kind == "capped")
    judgement = sum(a for _, a, kind in calloway["addbacks"] if kind == "judgement")
    uncapped = sum(a for _, a, kind in calloway["addbacks"] if kind == "uncapped")
    cap = calloway["ebitda"] * spec["addback_cap_pct"] // 100
    total_addbacks = capped + judgement + uncapped
    readings = {
        "as_reported": calloway["leverage"],
        "integration_capped": float(ratio(calloway["net_debt"], calloway["ebitda"]
                                          + min(cap, capped + judgement) + uncapped)),
        "all_capped": float(ratio(calloway["net_debt"], calloway["ebitda"]
                                  + min(cap, total_addbacks))),
    }
    layouts: dict[str, int] = {}
    forms: dict[str, int] = {}
    for o in obligors:
        if o is by_role["M15"]:
            continue
        layouts[o["layout"]] = layouts.get(o["layout"], 0) + 1
        forms[o["certificate_form"]] = forms.get(o["certificate_form"], 0) + 1
    return {
        "obligors": len(obligors),
        "received": len(obligors) - 1,
        "breach": {"id": by_role["M13"]["id"], "name": by_role["M13"]["name"],
                   "leverage": by_role["M13"]["leverage"],
                   "max_leverage": by_role["M13"]["max_leverage"],
                   "icr": by_role["M13"]["icr"]},
        "addbacks": {"id": calloway["id"], "name": calloway["name"],
                     "ebitda_k": calloway["ebitda"], "addbacks_k": total_addbacks,
                     "addback_pct": round(total_addbacks / calloway["ebitda"] * 100, 2),
                     "cap_k": cap, "readings": readings,
                     "max_leverage": calloway["max_leverage"]},
        "missing": {"id": by_role["M15"]["id"], "name": by_role["M15"]["name"]},
        "waiver": {"id": by_role["M16"]["id"], "name": by_role["M16"]["name"],
                   "leverage": by_role["M16"]["leverage"], "original": waiver["max_leverage"],
                   "amended": waiver["amended"]},
        "rounding": {"id": by_role["N6"]["id"], "name": by_role["N6"]["name"],
                     "reported": spec["planted"]["rounding"]["reported"],
                     "recomputed": by_role["N6"]["leverage"]},
        "excluded": excluded,
        "eligible_balance": total,
        "borrowing_base": base,
        "availability": round(min(spec["commitment_usd"], base) - spec["drawn_usd"], 2),
        "certificate": certificate,
        "certificate_difference": round(certificate["borrowing_base"] - base, 2),
        "largest_obligor": {"id": largest["id"],
                            "pct": round(largest["outstanding"] / total * 100, 2)},
        "largest_sector": {"sector": top_sector,
                           "pct": round(sectors[top_sector] / total * 100, 2)},
        "concentration_excess": 0.0,
        "layouts": dict(sorted(layouts.items())),
        "certificate_forms": dict(sorted(forms.items())),
    }


# Documents


def _agreement(cycle: dict[str, Any], path: Path) -> None:
    spec = cycle["ravenglass"]
    rates = spec["advance_rates"]
    story: list[Any] = [
        Spacer(1, 1.4 * inch),
        text("LOAN AND SECURITY AGREEMENT", TITLE),
        text(f"dated as of {_date(spec['signed'])}", CENTERED),
        text(f"{spec['borrower'].upper()}, as Borrower", CENTERED),
        text(f"{spec['manager'].upper()}, as Servicer", CENTERED),
        text(f"{cycle['lender'].upper()}, as Lender", CENTERED),
        text(f"US${spec['commitment_usd']:,} back-leverage facility", CENTERED),
        PageBreak(),
        text("EXTRACT: SECTIONS RELEVANT TO MONITORING", ARTICLE),
        text("Conformed copy. Sections not relevant to monitoring are omitted.", SMALL),
        text("Section 1.1 Definitions", SECTION),
        text('"Advance Rate" means, for an Eligible Obligor Loan, ' + ", ".join(
            f"{pct}% for a {kind} Loan" for kind, pct in rates.items()) + "."),
        text('"Eligible Obligor Loan" means an Obligor Loan (a) whose Obligor has delivered its '
             "quarterly financial statements and compliance certificate within 45 days after "
             "each quarter end and (b) for which no Material Obligor Event has occurred and is "
             "continuing."),
        text('"Material Obligor Event" means that an Obligor fails to meet any financial '
             "covenant in its Underlying Loan Agreement, tested as that covenant stands after "
             "any amendment or waiver notified to the Lender under Section 7.3."),
        text('"Covenant EBITDA" means Consolidated EBITDA plus the adjustments the Underlying '
             "Loan Agreement permits, provided that cost savings, synergies and restructuring "
             f"charges added back may not exceed {spec['addback_cap_pct']}% of Consolidated "
             "EBITDA before such adjustments."),
        text('"Concentration Excess Amount" means the amount by which the Outstanding Balance '
             f"of Eligible Obligor Loans to one Obligor exceeds {spec['single_obligor_limit_pct']}%"
             " of the Aggregate Eligible Balance, or to Obligors in one Sector exceeds "
             f"{spec['sector_limit_pct']}% of it."),
        text('"Borrowing Base" means the sum, for each Eligible Obligor Loan, of its Outstanding '
             "Balance multiplied by its Advance Rate, less the Concentration Excess Amount "
             "multiplied by the Advance Rate that applies to it."),
        text("Section 2.4 Borrowing Base", SECTION),
        text("The Advances outstanding shall not exceed the lesser of the Commitment and the "
             "Borrowing Base. The Borrower shall deliver a Borrowing Base Certificate with each "
             "monthly Portfolio Report."),
        text("Section 7.2 Reporting", SECTION),
        text("(a) Within ten Business Days after each month end, the Servicer shall deliver a "
             "Portfolio Report listing each Obligor Loan and the financial covenant results of "
             "each Obligor.", INDENT_1),
        text("(b) Within 45 days after each quarter end, the Servicer shall deliver each "
             "Obligor's financial statements and compliance certificate for that quarter.",
             INDENT_1),
        text("Section 7.3 Amendments", SECTION),
        text("The Servicer shall notify the Lender within five Business Days of any amendment "
             "or waiver of a financial covenant in an Underlying Loan Agreement."),
    ]
    build(path, story, "Ravenglass Loan and Security Agreement",
          "Ravenglass Loan and Security Agreement (extract)")


def _record(spec: dict[str, Any], obligors: list[dict[str, Any]], path: Path) -> None:
    """The facility record set at onboarding: each obligor loan and its covenant levels."""
    rows = [{"id": o["id"], "name": o["name"], "sector": o["sector"], "sponsor": o["sponsor"],
             "facility": o["facility"], "commitment": o["commitment"],
             "outstanding": o["outstanding"], "max_leverage": o["max_leverage"],
             "min_icr": o["min_icr"]} for o in obligors]
    path.write_text(json.dumps({"facility": spec["name"], "as_of": spec["as_of"].isoformat(),
                                "obligors": rows}, indent=1) + "\n", encoding="utf-8")


def _k(value: int) -> str:
    return f"{value:,}" if value >= 0 else f"({-value:,})"


def _m(value: int) -> str:
    """US$ thousands as US$ millions, two places: exact, as every amount is a multiple of ten."""
    text_value = f"{Decimal(value) / 1000:,.2f}"
    return text_value if value >= 0 else f"({text_value.lstrip('-')})"


def _financials(spec: dict[str, Any], o: dict[str, Any], path: Path) -> None:
    quarter = _date(spec["quarter_end"])
    q = {k: tens(o[k] / 4) for k in ("revenue", "ebitda", "interest")}
    layout = o["layout"]
    if layout == "A":
        story = [
            text(o["name"], REPORT_TITLE),
            text(f"Consolidated financial statements for the quarter ended {quarter} "
                 "(unaudited)", REPORT_HEAD),
            text("Amounts in US$ thousands.", REPORT_BODY),
            text("Consolidated income statement", REPORT_HEAD),
            table([["US$ thousands", "Quarter", "Last twelve months"],
                   ["Revenue", _k(q["revenue"]), _k(o["revenue"])],
                   ["Cost of sales", _k(-tens(o["cost_of_sales"] / 4)), _k(-o["cost_of_sales"])],
                   ["Gross profit", "", _k(o["gross_profit"])],
                   ["Operating expenses", "", _k(-o["opex"])],
                   ["EBITDA", _k(q["ebitda"]), _k(o["ebitda"])],
                   ["Depreciation and amortisation", "", _k(-o["depreciation"])],
                   ["Operating profit", "", _k(o["operating_profit"])],
                   ["Interest expense", _k(-q["interest"]), _k(-o["interest"])],
                   ["Profit before tax", "", _k(o["pbt"])]],
                  widths=[3.0, 1.3, 1.7]),
            Spacer(1, 0.15 * inch),
            text("Consolidated balance sheet extract", REPORT_HEAD),
            table([["US$ thousands", f"At {quarter}"],
                   ["Cash and cash equivalents", _k(o["cash"])],
                   ["Senior term loan", _k(o["term_loan"])],
                   ["Revolving credit facility", _k(o["revolver"])],
                   ["Total borrowings", _k(o["gross_debt"])],
                   ["Net debt", _k(o["net_debt"])]], widths=[4.3, 1.7], total_row=True),
        ]
    elif layout == "B":
        story = [
            text(f"{o['name']}: management accounts", REPORT_TITLE),
            text(f"Period: twelve months to {quarter}. US$ millions.", REPORT_BODY),
            text("Profit and loss account", REPORT_HEAD),
            table([["US$m", "LTM"],
                   ["Turnover", _m(o["revenue"])],
                   ["Gross margin", _m(o["gross_profit"])],
                   ["Overheads", _m(-o["opex"])],
                   ["EBITDA before adjustments", _m(o["ebitda"])],
                   ["Finance costs", _m(-o["interest"])]], widths=[4.3, 1.7]),
            Spacer(1, 0.15 * inch),
            text("Net debt", REPORT_HEAD),
            table([["US$m", quarter],
                   ["Gross debt", _m(o["gross_debt"])],
                   ["Less: cash", _m(-o["cash"])],
                   ["Net debt", _m(o["net_debt"])]], widths=[4.3, 1.7], total_row=True),
            text("Prepared by management. Not audited.", REPORT_BODY),
        ]
    elif layout == "C":
        story = [
            text("Quarterly lender reporting template", REPORT_TITLE),
            text(f"Obligor: {o['name']} ({o['id']}). Quarter end: {quarter}. "
                 "US$ thousands.", REPORT_BODY),
            table([["Item", "Value"],
                   ["Revenue (LTM)", _k(o["revenue"])],
                   ["EBITDA (LTM, before adjustments)", _k(o["ebitda"])],
                   ["Cash", _k(o["cash"])],
                   ["Total debt", _k(o["gross_debt"])],
                   ["Net debt", _k(o["net_debt"])],
                   ["Cash interest expense (LTM)", _k(o["interest"])]],
                  widths=[4.3, 1.7]),
            Spacer(1, 0.15 * inch),
            text("Completed by the Obligor's finance team in the Servicer's template.",
                 REPORT_BODY),
        ]
    else:
        story = [
            text(o["name"], REPORT_TITLE),
            text(f"Quarterly update to lenders from {o['sponsor']}", REPORT_HEAD),
            text(f"Trading in the quarter to {quarter} was in line with the budget. The "
                 "business continued to integrate the sites acquired last year and kept "
                 "working capital within its target range.", REPORT_BODY),
            text("Key figures", REPORT_HEAD),
            table([["US$000", "LTM"],
                   ["LTM revenue", _k(o["revenue"])],
                   ["LTM EBITDA", _k(o["ebitda"])],
                   ["Net debt", _k(o["net_debt"])],
                   ["Net interest", _k(o["interest"])]], widths=[4.3, 1.7]),
        ]
    build(path, story, f"{o['name']} Q1 2026 financial statements",
          f"{o['name']}: Q1 2026 financial statements", SANS)


def _certificate(spec: dict[str, Any], o: dict[str, Any], path: Path) -> None:
    quarter = _date(spec["quarter_end"])
    maximum = spec["planted"]["waiver"]["amended"] if o["role"] == "M16" else o["max_leverage"]
    met_leverage = o["leverage"] <= maximum
    signed = o["received"] - timedelta(days=1)
    if o["certificate_form"] == "standard":
        lines = [["Line", "US$ thousands"], ["Consolidated EBITDA", _k(o["ebitda"])]]
        lines += [[f"Add: {d}", _k(a)] for d, a, _ in o["addbacks"]]
        lines += [["Covenant EBITDA", _k(o["covenant_ebitda"])],
                  ["Total Net Debt", _k(o["net_debt"])],
                  ["Interest Expense", _k(o["interest"])]]
        story = [
            text("Compliance Certificate", REPORT_TITLE),
            text(f"Obligor: {o['name']}. To: {spec['manager']} as Servicer. Test date: "
                 f"{quarter}.", REPORT_BODY),
            table(lines, widths=[4.3, 1.7]),
            Spacer(1, 0.15 * inch),
            table([["Financial covenant", "Actual", "Required", "Met"],
                   ["Total Net Leverage Ratio", f"{o['leverage']:.2f}:1.00",
                    f"Maximum {maximum:.2f}:1.00", "Yes" if met_leverage else "No"],
                   ["Interest Cover", f"{o['icr']:.2f}:1.00",
                    f"Minimum {o['min_icr']:.2f}:1.00", "Yes"]],
                  widths=[2.2, 1.1, 1.7, 0.6]),
            Spacer(1, 0.15 * inch),
            text("No Default has occurred and is continuing." if met_leverage else
                 "The Total Net Leverage Ratio exceeds the maximum. The Obligor has asked its "
                 "lenders for a waiver; none has been granted at the date of this certificate.",
                 REPORT_BODY),
            text(f"Chief Financial Officer, for and on behalf of {o['name']}. Dated "
                 f"{_date(signed)}.", REPORT_BODY),
        ]
    else:
        adjustments = "; ".join(f"{d} of US${a:,} thousand" for d, a, _ in o["addbacks"])
        story = [
            text(o["name"], REPORT_TITLE),
            text("Certificate of compliance with financial covenants", REPORT_HEAD),
            text(f"We certify that for the Relevant Period ending {quarter}:", REPORT_BODY),
            text(f"(a) Consolidated EBITDA was US${o['ebitda']:,} thousand"
                 + (f", and the adjustments made were: {adjustments}" if adjustments else
                    ", with no adjustments")
                 + f", giving Covenant EBITDA of US${o['covenant_ebitda']:,} thousand;",
                 REPORT_BODY),
            text(f"(b) Total Net Debt was US${o['net_debt']:,} thousand and Interest Expense "
                 f"was US${o['interest']:,} thousand;", REPORT_BODY),
            text(f"(c) the Leverage Ratio was {o['leverage']:.2f} times against a maximum of "
                 f"{maximum:.2f} times; and", REPORT_BODY),
            text(f"(d) Interest Cover was {o['icr']:.2f} times against a minimum of "
                 f"{o['min_icr']:.2f} times.", REPORT_BODY),
            text(f"Signed by the Finance Director on {_date(signed)}.", REPORT_BODY),
        ]
    build(path, story, f"{o['name']} Q1 2026 compliance certificate",
          f"{o['name']}: Q1 2026 compliance certificate", SANS)


def _waiver(spec: dict[str, Any], o: dict[str, Any], path: Path) -> None:
    w = spec["planted"]["waiver"]
    story = [
        text(spec["manager"], REPORT_TITLE),
        text("Notice of amendment and waiver", REPORT_HEAD),
        text(f"To: Calderwood Bank plc as Lender. Delivered under Section 7.3 of the Loan and "
             f"Security Agreement dated {_date(spec['signed'])}.", REPORT_BODY),
        text(f"Obligor: {o['name']} ({o['id']}).", REPORT_BODY),
        text(f"1. On {_date(w['signed'])} the required lenders under the Obligor's Underlying "
             "Loan Agreement agreed the amendment below. It is effective from that date.",
             REPORT_BODY),
        text(f"2. For the test dates of {_date(w['test_dates'][0])} and "
             f"{_date(w['test_dates'][1])}, the maximum Total Net Leverage Ratio is increased "
             f"from {w['max_leverage']:.2f}:1.00 to {w['amended']:.2f}:1.00. From the next "
             f"test date it returns to {w['max_leverage']:.2f}:1.00.", REPORT_BODY),
        text("3. In return the Obligor's margin rises by 0.50% a year until the ratio is below "
             f"{w['max_leverage']:.2f}:1.00 on a test date. No other term is changed.",
             REPORT_BODY),
        text(f"For and on behalf of {spec['manager']} as Servicer. {_date(w['received'])}.",
             REPORT_BODY),
    ]
    build(path, story, f"Amendment and waiver notice, {o['name']}",
          f"Notice of amendment and waiver: {o['id']}", SANS)


PORTFOLIO_COLUMNS = [
    "Obligor ID", "Obligor", "Sector", "Sponsor", "Facility type", "Commitment (US$)",
    "Outstanding (US$)", "Financials as of", "LTM EBITDA (US$000)", "EBITDA adjustments (US$000)",
    "Covenant EBITDA (US$000)", "Net debt (US$000)", "Interest expense (US$000)",
    "Total net leverage (x)", "Max leverage (x)", "Interest cover (x)", "Min interest cover (x)",
    "Advance rate (%)",
]


def _portfolio_report(spec: dict[str, Any], obligors: list[dict[str, Any]], path: Path) -> None:
    """The fund's own report. It carries its own figures, as funds do: the last quarter it has
    for an obligor that has not reported, leverage truncated rather than rounded for one, and
    covenant levels as amended."""
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Portfolio"
    _header(sheet, 1, PORTFOLIO_COLUMNS)
    waiver = spec["planted"]["waiver"]
    for o in obligors:
        leverage = o["leverage"]
        if o["role"] == "N6":
            leverage = float((Decimal(o["net_debt"]) / Decimal(o["covenant_ebitda"])).quantize(
                Decimal("0.01"), ROUND_DOWN))
        as_of = spec["planted"]["missing"]["last_quarter"] if o["role"] == "M15" \
            else spec["quarter_end"]
        sheet.append([
            o["id"], o["name"], o["sector"], o["sponsor"], o["facility"], o["commitment"],
            o["outstanding"], as_of.isoformat(), o["ebitda"],
            o["covenant_ebitda"] - o["ebitda"], o["covenant_ebitda"], o["net_debt"],
            o["interest"], leverage,
            waiver["amended"] if o["role"] == "M16" else o["max_leverage"], o["icr"],
            o["min_icr"], spec["advance_rates"][o["facility"]],
        ])
    for column, width in zip("ABCDEFGHIJKLMNOPQR",
                             [11, 34, 22, 22, 13, 16, 16, 14, 14, 14, 14, 14, 14, 12, 12, 12, 12,
                              12], strict=True):
        sheet.column_dimensions[column].width = width
    report = workbook.create_sheet("Report")
    report.append(["Portfolio report", spec["short_name"]])
    report.append(["As of", spec["as_of"].isoformat()])
    report.append(["Financial covenants tested at", spec["quarter_end"].isoformat()])
    report.append(["Prepared by", spec["manager"]])
    _save_stable(workbook, path)


def _bbc(spec: dict[str, Any], obligors: list[dict[str, Any]], path: Path) -> dict[str, Any]:
    """The fund's certificate: every obligor loan at its advance rate. It applies no exclusion."""
    rates = spec["advance_rates"]
    values = [(Decimal(o["outstanding"]) * Decimal(rates[o["facility"]]) / 100).quantize(
        Decimal("0.01"), ROUND_HALF_UP) for o in obligors]
    aggregate = sum(o["outstanding"] for o in obligors)
    base = float(sum(values))
    workbook = Workbook()
    summary = workbook.active
    summary.title = "BBC Summary"
    summary["A1"] = spec["borrower"]
    summary["A1"].font = Font(bold=True, size=14)
    summary["A2"] = "Borrowing Base Certificate"
    summary["A3"] = "Determination date"
    summary["B3"] = spec["as_of"].isoformat()
    lines = [
        ("Aggregate Outstanding Balance", aggregate),
        ("Less: loans that are not Eligible Obligor Loans", 0),
        ("Aggregate Eligible Balance", aggregate),
        ("Less: Concentration Excess Amount at its Advance Rate", 0),
        ("Borrowing Base", base),
        ("Advances outstanding", spec["drawn_usd"]),
        ("Availability", round(min(spec["commitment_usd"], base) - spec["drawn_usd"], 2)),
    ]
    for offset, (label, value) in enumerate(lines):
        summary.cell(row=5 + offset, column=1, value=label)
        summary.cell(row=5 + offset, column=2, value=value).number_format = "#,##0.00"
    summary.cell(row=13, column=1, value=f"Certified by: Chief Financial Officer, "
                                          f"{spec['manager']}")
    summary.column_dimensions["A"].width = 56
    summary.column_dimensions["B"].width = 20
    detail = workbook.create_sheet("Obligor Detail")
    _header(detail, 1, ["Obligor ID", "Obligor", "Facility type", "Outstanding (US$)",
                        "Advance rate (%)", "Borrowing base value (US$)"])
    for o, value in zip(obligors, values, strict=True):
        detail.append([o["id"], o["name"], o["facility"], o["outstanding"],
                       rates[o["facility"]], float(value)])
    detail.column_dimensions["B"].width = 34
    _save_stable(workbook, path)
    return {"aggregate": aggregate, "eligible": aggregate, "borrowing_base": base,
            "availability": lines[-1][1]}
