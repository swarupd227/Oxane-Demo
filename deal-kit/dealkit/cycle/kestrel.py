"""Kestrel Credit Fund III: a NAV facility to a private credit fund, reporting quarterly.

Planted here: a US$85m markdown on one position after the quarter (M8), which the NAV
definition may or may not catch, and one position last valued in December 2025 (M9).
"""

from datetime import date, timedelta
from pathlib import Path
from typing import Any

from reportlab.lib.units import inch
from reportlab.platypus import PageBreak, Spacer

from dealkit.legal_docs import _date
from dealkit.pdfkit import (
    ARTICLE,
    BODY,
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

FILES = {
    "credit_agreement": "Kestrel_NAV_Facility_Agreement.pdf",
    "nav_report": "Kestrel_Q1_2026_NAV_Report.pdf",
    "valuation_report": "Kestrel_Q1_2026_Valuation_Report.pdf",
    "compliance_certificate": "Kestrel_Q1_2026_Compliance_Certificate.pdf",
}


def _m(amount: float) -> str:
    return f"{amount / 1e6:,.1f}"


def _valuation_dates(spec: dict[str, Any]) -> dict[str, date]:
    """Every position valued in the last fortnight of the quarter, except the stale one."""
    end: date = spec["quarter_end"]
    dates = {
        name: end - timedelta(days=(index * 3) % 14)
        for index, (name, _, _) in enumerate(spec["positions"])
    }
    dates[spec["stale_position"]["name"]] = spec["stale_position"]["valued"]
    return dates


def build_kestrel(cycle: dict[str, Any], folder: Path) -> dict[str, Any]:
    spec = cycle["kestrel"]
    positions = [{"name": n, "sector": s, "value": v} for n, s, v in spec["positions"]]
    nav = sum(p["value"] for p in positions) - spec["other_net_liabilities_usd"]
    if nav != spec["nav_usd"]:
        raise ValueError(f"Positions give a NAV of {nav:,}, not {spec['nav_usd']:,}")
    dates = _valuation_dates(spec)
    for position in positions:
        position["valued"] = dates[position["name"]]
        position["age_days"] = (spec["quarter_end"] - position["valued"]).days
    markdown = spec["markdown"]
    adjusted = nav - markdown["amount_usd"]
    drawn = spec["drawn_usd"]
    ordered = sorted(positions, key=lambda p: -p["value"])
    after = sorted(
        (
            {
                **p,
                "value": p["value"]
                - (markdown["amount_usd"] if p["name"] == markdown["position"] else 0),
            }
            for p in positions
        ),
        key=lambda p: -p["value"],
    )

    _agreement(cycle, folder / FILES["credit_agreement"])
    _nav_report(cycle, positions, nav, folder / FILES["nav_report"])
    _valuation_report(cycle, positions, folder / FILES["valuation_report"])
    _compliance(cycle, nav, folder / FILES["compliance_certificate"])
    return {
        "nav": nav,
        "drawn": drawn,
        "adjusted_nav": adjusted,
        "ltv_reported_pct": round(drawn / nav * 100, 1),
        "ltv_adjusted_pct": round(drawn / adjusted * 100, 1),
        "max_ltv_pct": spec["max_ltv_pct"],
        "largest_position_pct": round(ordered[0]["value"] / nav * 100, 1),
        "top_five_pct": round(sum(p["value"] for p in ordered[:5]) / nav * 100, 1),
        "top_five_after_markdown_pct": round(
            sum(p["value"] for p in after[:5]) / adjusted * 100, 1
        ),
        "stale": [
            {"name": p["name"], "valued": p["valued"].isoformat(), "age_days": p["age_days"]}
            for p in positions
            if p["age_days"] > spec["valuation_max_age_days"]
        ],
        "positions": [{**p, "valued": p["valued"].isoformat()} for p in positions],
    }


def _agreement(cycle: dict[str, Any], path: Path) -> None:
    spec = cycle["kestrel"]
    story: list[Any] = [
        Spacer(1, 1.4 * inch),
        text("NAV FACILITY AGREEMENT", TITLE),
        text(f"dated as of {_date(spec['signed'])}", CENTERED),
        text(f"{spec['name'].upper()}, as Borrower", CENTERED),
        text(f"{spec['manager'].upper()}, as Manager", CENTERED),
        text(f"{cycle['lender'].upper()}, as Lender", CENTERED),
        text(f"US${spec['commitment_usd']:,} revolving NAV facility", CENTERED),
        PageBreak(),
        text("EXTRACT: SECTIONS RELEVANT TO MONITORING", ARTICLE),
        text("Conformed copy. Sections not relevant to quarterly monitoring are omitted.", SMALL),
        text("Section 1.1 Definitions", SECTION),
        text(
            '"Net Asset Value" means, on any Calculation Date, the net asset value of the '
            "Borrower as stated in the most recent Quarterly NAV Report, adjusted for any "
            "Valuation Event of which the Borrower has notified the Lender."
        ),
        text(
            '"Valuation Event" means any event that the Manager determines, acting in good '
            "faith, has reduced the value of an Investment by more than 10% since its last "
            "valuation."
        ),
        text(
            '"Loan-to-Value Ratio" means the aggregate principal amount of the Loans '
            "outstanding divided by the Net Asset Value."
        ),
        text("Section 6.2 Valuations", SECTION),
        text(
            f"Each Investment shall be valued by an Approved Valuer as of a date not more than "
            f"{spec['valuation_max_age_days']} days before each Calculation Date. An Investment "
            "whose last valuation is older is valued at nil for the Loan-to-Value Ratio until "
            "it is revalued, unless the Lender agrees otherwise."
        ),
        text("Section 6.3 Concentration", SECTION),
        text(
            f"(a) No single Investment may exceed {spec['max_single_position_pct']}% of the Net "
            "Asset Value.",
            INDENT_1,
        ),
        text(
            f"(b) The five largest Investments together may not exceed "
            f"{spec['max_top_five_pct']}% of the Net Asset Value.",
            INDENT_1,
        ),
        text("Section 7.1 Loan-to-Value Ratio", SECTION),
        text(
            f"The Borrower shall ensure that the Loan-to-Value Ratio does not exceed "
            f"{spec['max_ltv_pct']}% on any Calculation Date. Each Quarter End is a Calculation "
            "Date."
        ),
        text("Section 8.1 Reporting", SECTION),
        text(
            "Within 60 days after each Quarter End the Borrower shall deliver a Quarterly NAV "
            "Report, the valuation report of the Approved Valuer and a Compliance Certificate."
        ),
    ]
    build(path, story, "Kestrel NAV Facility Agreement", "Kestrel NAV Facility Agreement (extract)")


def _nav_report(
    cycle: dict[str, Any], positions: list[dict[str, Any]], nav: int, path: Path
) -> None:
    spec = cycle["kestrel"]
    head = "Quarterly NAV Report - Q1 2026"
    story: list[Any] = [
        text(spec["name"], REPORT_TITLE),
        text(f"Quarterly NAV Report as of {_date(spec['quarter_end'])}", REPORT_HEAD),
        text(f"Prepared by {spec['manager']}. Amounts in US$ millions.", REPORT_BODY),
        Spacer(1, 0.15 * inch),
        table(
            [
                ["Investment", "Sector", "Fair value"],
                *[[p["name"], p["sector"], _m(p["value"])] for p in positions],
                ["Total investments", "", _m(sum(p["value"] for p in positions))],
            ],
            widths=[2.8, 2.0, 1.2],
            align_right_from=2,
            total_row=True,
        ),
        Spacer(1, 0.15 * inch),
        table(
            [
                ["Net asset value", "US$ millions"],
                ["Total investments", _m(sum(p["value"] for p in positions))],
                ["Cash less other liabilities", f"({_m(spec['other_net_liabilities_usd'])})"],
                ["Net asset value", _m(nav)],
            ],
            widths=[4.3, 1.7],
            total_row=True,
        ),
        Spacer(1, 0.15 * inch),
        text(
            "Fair values are those of the Approved Valuer at the dates in its report.", REPORT_BODY
        ),
    ]
    build(path, story, head, head, SANS)


def _valuation_report(cycle: dict[str, Any], positions: list[dict[str, Any]], path: Path) -> None:
    spec, markdown = cycle["kestrel"], cycle["kestrel"]["markdown"]
    head = "Valuation Report - Q1 2026"
    story: list[Any] = [
        text("Harrowgate Valuation Advisory LLP", REPORT_TITLE),
        text(f"Independent valuation of the investments of {spec['name']}", REPORT_HEAD),
        text(
            f"Prepared for {spec['manager']} as Approved Valuer. Amounts in US$ millions.",
            REPORT_BODY,
        ),
        Spacer(1, 0.15 * inch),
        text("1. Valuations", REPORT_HEAD),
        table(
            [
                ["Investment", "Valuation date", "Method", "Fair value"],
                *[
                    [p["name"], _date(p["valued"]), "Discounted cash flow", _m(p["value"])]
                    for p in positions
                ],
            ],
            widths=[2.5, 1.4, 1.5, 0.9],
            align_right_from=3,
        ),
        PageBreak(),
        text("2. Events after the valuation date", REPORT_HEAD),
        text(
            f"On {_date(markdown['date'])} {markdown['position']} reported that it had breached "
            "the leverage covenant in its senior credit agreement and entered a standstill with "
            "its lenders. On the information available to us, we estimate that the fair value of "
            f"the investment has fallen by about US${markdown['amount_usd'] / 1e6:,.0f} million "
            "since the valuation date. This is not reflected in the valuation above, which is "
            f"stated as of {_date(spec['quarter_end'])}, and we have not been asked to revalue "
            "the investment.",
            REPORT_BODY,
        ),
        text("3. Basis", REPORT_HEAD),
        text(
            "Valuations follow the IPEV Valuation Guidelines. Each investment was valued on the "
            "date shown, using the information available on that date.",
            REPORT_BODY,
        ),
    ]
    build(path, story, head, head, SANS)


def _compliance(cycle: dict[str, Any], nav: int, path: Path) -> None:
    spec = cycle["kestrel"]
    ltv = spec["drawn_usd"] / nav * 100
    head = "Compliance Certificate - Q1 2026"
    story: list[Any] = [
        text(spec["name"], REPORT_TITLE),
        text("Compliance Certificate", REPORT_HEAD),
        text(
            f"To: {cycle['lender']}. Delivered under Section 8.1 of the NAV Facility Agreement "
            f"for the Calculation Date {_date(spec['quarter_end'])}.",
            REPORT_BODY,
        ),
        Spacer(1, 0.15 * inch),
        table(
            [
                ["Test", "Section", "Limit", "Actual", "In compliance"],
                ["Loan-to-Value Ratio", "7.1", f"{spec['max_ltv_pct']}%", f"{ltv:.1f}%", "Yes"],
                [
                    "Largest Investment",
                    "6.3(a)",
                    f"{spec['max_single_position_pct']}%",
                    "12.8%",
                    "Yes",
                ],
                [
                    "Five largest Investments",
                    "6.3(b)",
                    f"{spec['max_top_five_pct']}%",
                    "52.4%",
                    "Yes",
                ],
            ],
            widths=[1.9, 0.8, 0.8, 0.9, 1.1],
        ),
        Spacer(1, 0.15 * inch),
        table(
            [
                ["Loan-to-Value Ratio", "US$ millions"],
                ["Loans outstanding", _m(spec["drawn_usd"])],
                ["Net Asset Value per the Quarterly NAV Report", _m(nav)],
                ["Loan-to-Value Ratio", f"{ltv:.1f}%"],
            ],
            widths=[4.3, 1.7],
            total_row=True,
        ),
        Spacer(1, 0.15 * inch),
        text(
            "The Manager has not determined that any Valuation Event has occurred. No Default "
            "has occurred and is continuing.",
            REPORT_BODY,
        ),
        text(
            f"Chief Financial Officer, {spec['manager']}, for and on behalf of the Borrower. "
            f"Dated {_date(spec['received']['compliance_certificate'])}.",
            REPORT_BODY,
        ),
    ]
    build(path, story, head, head, SANS)


__all__ = ["FILES", "build_kestrel", "BODY"]
