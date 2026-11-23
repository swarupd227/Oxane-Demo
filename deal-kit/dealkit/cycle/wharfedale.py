"""Wharfedale Infrastructure Partners III: Thornbury Bank's subscription line to an
infrastructure fund, lent against its investors' uncalled commitments.

The fund administrator sends the investor register each month, and every capital call and
distribution notice as it is issued, all as workbooks. Thornbury does not permit AI, so code
reads them through stored mappings and does every check.

Planted here: an investor downgraded below BBB-, an Exclusion Event the register has not applied,
which takes the borrowing base below the loans outstanding (M17); the largest investor then over
its concentration limit (M18); the register not posting May's call and distribution for one
investor (M19); and the distribution notice, which reconciles exactly (N7).
"""

from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any

from openpyxl import Workbook
from openpyxl.styles import Font
from reportlab.lib.units import inch
from reportlab.platypus import PageBreak, Spacer

from dealkit.legal_docs import _date
from dealkit.pdfkit import ARTICLE, CENTERED, INDENT_1, SECTION, SMALL, TITLE, build, text
from dealkit.workbooks import _header, _save_stable

FILES = {
    "agreement": "Wharfedale_Subscription_Facility_Agreement.pdf",
    "register_april": "Wharfedale_Investor_Register_2026-04-30.xlsx",
    "register_may": "Wharfedale_Investor_Register_2026-05-31.xlsx",
    "capital_call": "Wharfedale_Capital_Call_Notice_07.xlsx",
    "distribution": "Wharfedale_Distribution_Notice_04.xlsx",
}
SP = ["AAA", "AA+", "AA", "AA-", "A+", "A", "A-", "BBB+", "BBB", "BBB-", "BB+", "BB", "BB-",
      "B+", "B", "B-", "CCC+", "CCC", "CCC-", "CC", "C"]
REGISTER_COLUMNS = ["Investor ID", "Investor", "Investor type", "Commitment (US$)",
                    "Called to date (US$)", "Uncalled (US$)", "Rating (S&P)", "Designation",
                    "Rating date"]


def _cents(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), ROUND_HALF_UP)


def classify(rating: str, approved: str, spec: dict[str, Any]) -> tuple[str, str]:
    """The agreement's classes, from the investor's rating and the class it was approved in."""
    if approved == "Excluded":
        return "Excluded", "Not approved"
    if rating in SP and SP.index(rating) > SP.index(spec["exclusion_below"]):
        return "Excluded", f"Exclusion Event: rated {rating}, below {spec['exclusion_below']}"
    if approved == "Included" and rating in SP and SP.index(rating) <= SP.index(
            spec["included_min_rating"]):
        return "Included", "Rated at or above " + spec["included_min_rating"]
    if approved == "Included":
        return "Designated", f"Rated below {spec['included_min_rating']}"
    return "Designated", "Approved without a rating"


def borrowing_base(investors: list[dict[str, Any]], uncalled: dict[str, Decimal],
                   classes: dict[str, str], spec: dict[str, Any]) -> dict[str, Any]:
    """Worked out independently of the platform's engine."""
    rates = {k: Decimal(v) for k, v in spec["advance_rates"].items()}
    eligible = [i for i in investors if classes[i["id"]] != "Excluded"]
    aggregate = sum(uncalled[i["id"]] for i in eligible)
    single = _cents(aggregate * Decimal(spec["single_investor_limit_pct"]) / 100)
    excess = {i["id"]: max(Decimal(0), uncalled[i["id"]] - single) for i in eligible}
    designated = sum(uncalled[i["id"]] - excess[i["id"]] for i in eligible
                     if classes[i["id"]] == "Designated")
    designated_cap = _cents(aggregate * Decimal(spec["designated_limit_pct"]) / 100)
    designated_excess = max(Decimal(0), designated - designated_cap)
    value = sum(_cents((uncalled[i["id"]] - excess[i["id"]]) * rates[classes[i["id"]]] / 100)
                for i in eligible) - _cents(designated_excess * rates["Designated"] / 100)
    commitment, drawn = Decimal(spec["commitment_usd"]), Decimal(spec["drawn_usd"])
    over = {k: float(v) for k, v in excess.items() if v}
    return {
        "aggregate_eligible_uncalled": float(aggregate),
        "single_limit": float(single),
        "concentration_excess": over,
        "concentration_reduction": float(sum(
            _cents(excess[k] * rates[classes[k]] / 100) for k in over)),
        "designated_excess": float(designated_excess),
        "borrowing_base": float(value),
        "availability": float(min(commitment, value) - drawn),
        "prepayment": float(max(Decimal(0), drawn - min(commitment, value))),
    }


def build_wharfedale(cycle: dict[str, Any], folder: Path) -> dict[str, Any]:
    spec = cycle["wharfedale"]
    planted = spec["planted"]
    call, dist = spec["capital_call"], spec["distribution"]
    investors = [
        {"id": f"WIP-{n:03d}", "name": name, "kind": kind,
         "commitment": Decimal(size) * 1_000_000, "rating": rating, "approved": approved}
        for n, (name, kind, size, rating, approved) in enumerate(spec["investors"], start=1)
    ]
    for i in investors:
        i["called_april"] = _cents(i["commitment"] * Decimal(spec["called_before_pct"]) / 100)
        i["uncalled_april"] = i["commitment"] - i["called_april"]
        i["call"] = _cents(i["commitment"] * Decimal(call["pct"]) / 100)
        i["distribution"] = _cents(i["commitment"] * Decimal(dist["pct"]) / 100)
        i["recallable"] = _cents(i["commitment"] * Decimal(dist["recallable_pct"]) / 100)
        i["uncalled_may"] = i["uncalled_april"] - i["call"] + i["recallable"]
        i["called_may"] = i["commitment"] - i["uncalled_may"]
        i["rating_may"] = planted["downgrade"]["rating"] if i["name"] == \
            planted["downgrade"]["name"] else i["rating"]

    _agreement(cycle, folder / FILES["agreement"])
    _register(spec, investors, "april", folder / FILES["register_april"])
    _register(spec, investors, "may", folder / FILES["register_may"])
    _notice(spec, investors, "call", folder / FILES["capital_call"])
    _notice(spec, investors, "distribution", folder / FILES["distribution"])

    uncalled = {i["id"]: i["uncalled_may"] for i in investors}
    before = {i["id"]: classify(i["rating"], i["approved"], spec)[0] for i in investors}
    after = {i["id"]: classify(i["rating_may"], i["approved"], spec)[0] for i in investors}
    stale = next(i for i in investors if i["name"] == planted["stale_register"])
    down = next(i for i in investors if i["name"] == planted["downgrade"]["name"])
    base_before = borrowing_base(investors, uncalled, before, spec)
    base_after = borrowing_base(investors, uncalled, after, spec)
    largest = max((i for i in investors if after[i["id"]] != "Excluded"),
                  key=lambda i: uncalled[i["id"]])
    return {
        "investors": len(investors),
        "commitments": float(sum(i["commitment"] for i in investors)),
        "uncalled": float(sum(uncalled.values())),
        "classes": {k: sum(1 for v in after.values() if v == k)
                    for k in ("Included", "Designated", "Excluded")},
        "exclusion": {"id": down["id"], "name": down["name"], "from": down["rating"],
                      "to": down["rating_may"], "uncalled": float(uncalled[down["id"]])},
        "before_exclusion": base_before,
        "after_exclusion": base_after,
        "concentration": {"id": largest["id"], "name": largest["name"],
                          "share_pct": float((uncalled[largest["id"]] / Decimal(
                              base_after["aggregate_eligible_uncalled"]) * 100).quantize(
                              Decimal("0.01"), ROUND_HALF_UP)),
                          "excess": base_after["concentration_excess"].get(largest["id"], 0.0)},
        "capital_call": {"number": call["number"], "total": float(sum(i["call"] for i in
                                                                       investors)),
                         "differences": []},
        "distribution": {"number": dist["number"],
                         "total": float(sum(i["distribution"] for i in investors)),
                         "recallable": float(sum(i["recallable"] for i in investors)),
                         "differences": []},
        "register": {"stale": {"id": stale["id"], "name": stale["name"],
                               "register_uncalled": float(stale["uncalled_april"]),
                               "expected_uncalled": float(stale["uncalled_may"]),
                               "difference": float(stale["uncalled_april"]
                                                   - stale["uncalled_may"])},
                     "designation_not_updated": down["id"]},
    }


def _agreement(cycle: dict[str, Any], path: Path) -> None:
    spec = cycle["wharfedale"]
    rates = spec["advance_rates"]
    story: list[Any] = [
        Spacer(1, 1.4 * inch),
        text("REVOLVING CREDIT AGREEMENT", TITLE),
        text(f"dated as of {_date(spec['signed'])}", CENTERED),
        text(f"{spec['fund'].upper()}, as Borrower", CENTERED),
        text(f"{spec['general_partner'].upper()}, as General Partner", CENTERED),
        text("THORNBURY BANK N.A., as Lender", CENTERED),
        text(f"US${spec['commitment_usd']:,} subscription facility", CENTERED),
        PageBreak(),
        text("EXTRACT: SECTIONS RELEVANT TO MONITORING", ARTICLE),
        text("Conformed copy. Sections not relevant to monitoring are omitted.", SMALL),
        text("Section 1.1 Definitions", SECTION),
        text('"Included Investor" means an Investor approved by the Lender as an Included '
             f"Investor whose S&P rating is {spec['included_min_rating']} or higher."),
        text('"Designated Investor" means an Investor approved by the Lender as a Designated '
             "Investor, or an Included Investor whose rating falls below "
             f"{spec['included_min_rating']}."),
        text('"Exclusion Event" means, for an Investor, that it transfers its interest without '
             "the Lender's consent, fails to fund a capital call when due, becomes insolvent, "
             f"or is rated below {spec['exclusion_below']} by S&P. An Investor subject to an "
             "Exclusion Event is an Excluded Investor."),
        text('"Borrowing Base" means the sum of ' + " and ".join(
            f"{pct}% of the Uncalled Capital Commitments of {kind} Investors"
            for kind, pct in rates.items()) + ", in each case after the Concentration Limits."),
        text('"Concentration Limits" means that the Uncalled Capital Commitment of any one '
             f"Investor counts only up to {spec['single_investor_limit_pct']}% of the aggregate "
             "Uncalled Capital Commitments of Included and Designated Investors, and those of "
             f"Designated Investors together only up to {spec['designated_limit_pct']}% of it."),
        text("Section 2.5 Mandatory prepayment", SECTION),
        text("If the Loans outstanding exceed the lesser of the Commitment and the Borrowing "
             "Base, the Borrower shall prepay the excess within two Business Days."),
        text("Section 6.2 Reporting", SECTION),
        text("(a) Within five Business Days after each month end, the Administrator shall "
             "deliver an updated Investor Register.", INDENT_1),
        text("(b) The Borrower shall deliver each capital call notice and distribution notice "
             "on the day it is issued.", INDENT_1),
    ]
    build(path, story, "Wharfedale Revolving Credit Agreement",
          "Wharfedale Revolving Credit Agreement (extract)")


def _register(spec: dict[str, Any], investors: list[dict[str, Any]], month: str,
              path: Path) -> None:
    """The administrator's register. In May it has not posted the call or the distribution for
    one investor, and it still shows the downgraded investor as Included."""
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Register"
    _header(sheet, 1, REGISTER_COLUMNS)
    stale = spec["planted"]["stale_register"]
    for i in investors:
        if month == "april" or i["name"] == stale:
            called, uncalled = i["called_april"], i["uncalled_april"]
        else:
            called, uncalled = i["called_may"], i["uncalled_may"]
        rating = i["rating"] if month == "april" else i["rating_may"]
        changed = month == "may" and rating != i["rating"]
        sheet.append([i["id"], i["name"], i["kind"], float(i["commitment"]), float(called),
                      float(uncalled), rating, i["approved"],
                      spec["planted"]["downgrade"]["date"].isoformat() if changed
                      else "2026-01-15"])
    for column, width in zip("ABCDEFGHI", [11, 42, 22, 18, 18, 18, 12, 13, 12], strict=True):
        sheet.column_dimensions[column].width = width
    report = workbook.create_sheet("Report")
    report.append(["Investor register", spec["fund"]])
    report.append(["As of", "2026-04-30" if month == "april" else "2026-05-31"])
    report.append(["Administrator", spec["administrator"]])
    _save_stable(workbook, path)


def _notice(spec: dict[str, Any], investors: list[dict[str, Any]], kind: str,
            path: Path) -> None:
    detail = spec["capital_call"] if kind == "call" else spec["distribution"]
    workbook = Workbook()
    notice = workbook.active
    notice.title = "Notice"
    notice["A1"] = spec["fund"]
    notice["A1"].font = Font(bold=True, size=14)
    notice["A2"] = f"{'Capital call' if kind == 'call' else 'Distribution'} notice no. " \
        f"{detail['number']}"
    rows: list[tuple[str, Any]] = [("Notice date", detail["date"].isoformat())]
    if kind == "call":
        rows += [("Due date", detail["due"].isoformat()),
                 ("Amount called (US$)", float(sum(i["call"] for i in investors))),
                 ("Per cent of commitments", detail["pct"]),
                 ("Purpose", "Repayment of the subscription facility and two acquisitions")]
    else:
        rows += [("Amount distributed (US$)", float(sum(i["distribution"] for i in investors))),
                 ("Of which recallable (US$)", float(sum(i["recallable"] for i in investors))),
                 ("Per cent of commitments", detail["pct"]),
                 ("Recallable per cent", detail["recallable_pct"])]
    for offset, (label, value) in enumerate(rows):
        notice.cell(row=4 + offset, column=1, value=label)
        notice.cell(row=4 + offset, column=2, value=value)
    notice.column_dimensions["A"].width = 30
    notice.column_dimensions["B"].width = 58
    sheet = workbook.create_sheet("Allocation")
    if kind == "call":
        _header(sheet, 1, ["Investor ID", "Investor", "Commitment (US$)", "Amount called (US$)"])
        for i in investors:
            sheet.append([i["id"], i["name"], float(i["commitment"]), float(i["call"])])
    else:
        _header(sheet, 1, ["Investor ID", "Investor", "Commitment (US$)",
                           "Amount distributed (US$)", "Recallable (US$)"])
        for i in investors:
            sheet.append([i["id"], i["name"], float(i["commitment"]), float(i["distribution"]),
                          float(i["recallable"])])
    sheet.column_dimensions["B"].width = 42
    _save_stable(workbook, path)


__all__ = ["FILES", "build_wharfedale", "classify", "date"]
