"""Northmoor Motor Credit Trust: a subprime auto warehouse, with three months of tapes.

Planted here: the May servicer report never arrives (M1), 60+ day delinquency climbs 5.10%,
5.60%, 6.60% towards a 6.0% three-month trigger (M5), the car behind one May loan is already
pledged to Bramble (M7, set by the build), and May collections dip, as they did last May (N2).
"""

from collections import Counter, defaultdict
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np
from reportlab.lib.units import inch
from reportlab.platypus import PageBreak, Spacer

from dealkit.cycle.common import (
    delinquency_ratio,
    live,
    new_loan,
    pool_balance,
    roll_month,
    set_delinquency,
    write_certificate,
    write_tape,
)
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
from dealkit.tape import US_STATES, _base_row, _dealers

# Northmoor's own tape layout: different names, order and fewer fields than Bramble's.
COLUMNS: dict[str, str] = {
    "Acct_No": "loan_id",
    "Vehicle_VIN": "vin",
    "Contract_Date": "origination_date",
    "First_Due": "first_payment_date",
    "Maturity": "maturity_date",
    "Amt_Financed": "original_balance",
    "Principal_Bal": "current_balance",
    "APR_Pct": "apr",
    "Term_Mos": "original_term",
    "Mos_Remaining": "remaining_term",
    "Pmts_Paid": "payments_made",
    "Pmt_Amt": "monthly_payment",
    "Score": "fico",
    "State": "obligor_state",
    "Zip3": "obligor_zip3",
    "Dealer": "dealer_name",
    "Dealer_St": "dealer_state",
    "Make": "vehicle_make",
    "Model": "vehicle_model",
    "Yr": "model_year",
    "Cond": "vehicle_condition",
    "Days_Delinq": "days_past_due",
    "Status_Cd": "status",
    "CO_Date": "charge_off_date",
    "CO_Amt": "charge_off_amount",
    "Repo_Date": "repossession_date",
    "AsOf": "cutoff_date",
}

MONTHS = (("march", date(2026, 3, 31)), ("april", date(2026, 4, 30)), ("may", date(2026, 5, 31)))
FILES = {
    "credit_agreement": "Northmoor_Credit_Agreement.pdf",
    **{f"loan_tape_{m}": f"NMC_Tape_{d:%Y-%m}.csv" for m, d in MONTHS},
    "servicer_report_march": "NMC_Servicer_Report_March_2026.pdf",
    "servicer_report_april": "NMC_Servicer_Report_April_2026.pdf",
    "borrowing_base_certificate_april": "NMC_BBC_April_2026.xlsx",
    "borrowing_base_certificate_may": "NMC_BBC_May_2026.xlsx",
}


def _base_pool(
    spec: dict[str, Any], rng: np.random.Generator, cutoff: date
) -> tuple[list[dict[str, Any]], list[str]]:
    dealers = _dealers(rng)
    weights = np.minimum(rng.dirichlet(np.full(len(dealers), 2.0)), 0.025)
    weights = weights / weights.sum()
    rows = []
    for number in range(spec["loans"]):
        row = _base_row(rng, number, cutoff, dealers, weights, spec["mean_original_balance_usd"])
        row.update(
            loan_id=f"NMC{300000 + number}",
            servicer_code="NMC01",
            fico=int(np.clip(rng.normal(578, 38), 480, 720)),
        )
        rows.append(row)
    return rows, dealers


def northmoor_view(
    rows: list[dict[str, Any]], spec: dict[str, Any], outstanding: float
) -> dict[str, Any]:
    """Northmoor's borrowing base, in whole cents. Excess is measured on the eligible pool."""
    pool = [row for row in rows if row["status"] not in ("PAID_OFF", "REPURCHASED")]
    vins = Counter(row["vin"] for row in pool)
    failed: defaultdict[str, list[str]] = defaultdict(list)
    eligible = []
    for row in pool:
        tests = {
            "E1": row["days_past_due"] <= 30,
            "E2": row["status"] not in ("CHARGED_OFF", "REPO"),
            "E3": row["original_term"] <= 84,
            "E4": row["fico"] >= 500,
            "E5": row["current_balance"] <= 40000,
            "E6": row["obligor_state"] in US_STATES,
            "E7": vins[row["vin"]] == 1,
        }
        misses = [rule for rule, ok in tests.items() if not ok]
        for rule in misses:
            failed[rule].append(row["loan_id"])
        if not misses:
            eligible.append(row)
    cents = sum(round(row["current_balance"] * 100) for row in eligible)
    limits = {item["id"]: item["limit_pct"] for item in spec["concentration"]}
    concentrations = {}
    for rule, key in (("C1", "obligor_state"), ("C2", "dealer_name")):
        totals: defaultdict[str, int] = defaultdict(int)
        for row in eligible:
            totals[row[key]] += round(row["current_balance"] * 100)
        name = max(sorted(totals), key=lambda item: totals[item])
        limit = round(cents * limits[rule] / 100)
        concentrations[rule] = {
            "largest": name,
            "amount_cents": totals[name],
            "share_pct": round(totals[name] / cents * 100, 2),
            "limit_pct": limits[rule],
            "excess_cents": max(0, totals[name] - limit),
        }
    excess = sum(item["excess_cents"] for item in concentrations.values())
    reserve = round(cents * spec["reserve_pct"] / 100)
    base = round((cents - excess) * spec["advance_rate_pct"] / 100) - reserve
    return {
        "gross_pool": sum(round(row["current_balance"] * 100) for row in pool) / 100,
        "eligible_pool": cents / 100,
        "excess": excess / 100,
        "reserve": reserve / 100,
        "borrowing_base": base / 100,
        "availability": round(min(base / 100, spec["limit_usd"]) - outstanding, 2),
        "failures": {rule: len(ids) for rule, ids in failed.items()},
        "concentrations": concentrations,
    }


def build_northmoor(
    cycle: dict[str, Any], folder: Path, bramble_rows: list[dict[str, Any]]
) -> dict[str, Any]:
    spec = cycle["northmoor"]
    rng = np.random.default_rng(cycle["seed"] + 7)
    rows, dealers = _base_pool(spec, rng, date(2026, 2, 28))
    for row in rows:
        row["raw_origination_date"] = row["origination_date"].isoformat()
    next_number = 300000 + spec["loans"]
    months: dict[str, Any] = {}
    previous = rows
    for month, cutoff in MONTHS:
        fresh = []
        for _ in range(spec["new_loans_per_month"]):
            loan = new_loan(
                rng,
                f"NMC{next_number}",
                cutoff,
                dealers,
                spec["mean_original_balance_usd"],
                "NMC01",
            )
            loan["fico"] = int(np.clip(rng.normal(578, 38), 500, 720))
            loan["raw_origination_date"] = loan["origination_date"].isoformat()
            fresh.append(loan)
            next_number += 1
        roll = roll_month(
            previous, rng, cutoff, spec["payoff_rate"][month], spec["charge_offs_per_month"], fresh
        )
        late = {row["loan_id"] for row in previous if row["days_past_due"] >= 31}
        set_delinquency(roll, rng, spec["delinquency_pct"][month], late, keep_current=set())
        months[month] = {
            "rows": sorted(roll.rows, key=lambda row: row["loan_id"]),
            "roll": roll,
            "opening": pool_balance(previous),
        }
        previous = roll.rows

    shared = _plant_shared_vin(
        months["may"]["rows"], months["may"]["roll"].new_loans, bramble_rows, rng
    )
    for month, _ in MONTHS:
        write_tape(months[month]["rows"], COLUMNS, folder / FILES[f"loan_tape_{month}"])

    outstanding = spec["outstanding_advances_usd"]
    views = {m: northmoor_view(months[m]["rows"], spec, outstanding) for m in ("april", "may")}
    for month in ("april", "may"):
        _certificate(
            spec,
            MONTHS[["march", "april", "may"].index(month)][1],
            views[month],
            folder / FILES[f"borrowing_base_certificate_{month}"],
        )

    principal = {m: months[m]["roll"].principal_collected for m in ("march", "april", "may")}
    history = _collections_history(spec, principal)
    spread = {}
    for month in ("march", "april"):
        spread[month] = _servicer_report(
            cycle,
            month,
            months[month],
            history if month == "april" else None,
            folder / FILES[f"servicer_report_{month}"],
        )
    _credit_agreement(cycle, folder / FILES["credit_agreement"])

    ratios = {m: delinquency_ratio(months[m]["rows"]) for m in ("march", "april", "may")}
    return {
        "rows": months["may"]["rows"],
        "delinquency": {
            **ratios,
            "average": round(sum(ratios.values()) / 3, 2),
            "trigger": spec["delinquency_trigger_pct"],
            # June breaches the trigger if it is above this.
            "june_breach_above": round(
                3 * spec["delinquency_trigger_pct"] - ratios["april"] - ratios["may"], 2
            ),
        },
        "excess_spread": spread,
        "borrowing_base": views,
        "collections": {
            "principal": principal,
            "history": history,
            "may_vs_april": round(principal["may"] / principal["april"], 4),
            "last_may_vs_april": spec["seasonal_profile"][1],
        },
        "shared_vin": shared,
        "pool": {m: pool_balance(months[m]["rows"]) for m in ("march", "april", "may")},
    }


def _plant_shared_vin(
    may: list[dict[str, Any]],
    new_ids: list[str],
    bramble: list[dict[str, Any]],
    rng: np.random.Generator,
) -> dict[str, Any]:
    """Give a new Northmoor loan the car behind a seasoned, current Bramble loan."""
    seasoned = [
        row
        for row in live(bramble)
        if row["status"] == "ACTIVE"
        and row["origination_date"].year == 2024
        and row["days_past_due"] == 0
    ]
    source = seasoned[int(rng.integers(0, len(seasoned)))]
    chosen = new_ids[int(rng.integers(0, len(new_ids)))]
    target = next(row for row in may if row["loan_id"] == chosen)
    for field in ("vin", "vehicle_make", "vehicle_model", "model_year", "vehicle_condition"):
        target[field] = source[field]
    return {
        "vin": source["vin"],
        "bramble_loan": source["loan_id"],
        "northmoor_loan": target["loan_id"],
    }


def _collections_history(spec: dict[str, Any], principal: dict[str, float]) -> list[list[Any]]:
    """Thirteen months of principal collections, April 2025 to April 2026, in US$ thousands."""
    april = principal["april"] / 1000
    labels = [
        "Apr 2025",
        "May 2025",
        "Jun 2025",
        "Jul 2025",
        "Aug 2025",
        "Sep 2025",
        "Oct 2025",
        "Nov 2025",
        "Dec 2025",
        "Jan 2026",
        "Feb 2026",
    ]
    scale = 0.93  # The pool was smaller a year ago.
    earlier = [
        [label, round(april * scale * factor)]
        for label, factor in zip(labels, spec["seasonal_profile"], strict=False)
    ]
    return [*earlier, ["Mar 2026", round(principal["march"] / 1000)], ["Apr 2026", round(april)]]


def _certificate(spec: dict[str, Any], cutoff: date, view: dict[str, Any], path: Path) -> None:
    described = {item["id"]: item["text"] for item in spec["eligibility"]}
    names = {item["id"]: item["text"] for item in spec["concentration"]}
    write_certificate(
        path,
        spec["name"],
        cutoff,
        [
            ("1. Aggregate Principal Balance of Receivables", view["gross_pool"]),
            ("2. Less Ineligible Receivables", -(view["gross_pool"] - view["eligible_pool"])),
            ("3. Eligible Receivables Balance", view["eligible_pool"]),
            ("4. Less Excess Concentrations", -view["excess"]),
            ("5. Advance Rate", spec["advance_rate_pct"] / 100),
            ("6. Less Reserve", -view["reserve"]),
            ("7. Borrowing Base", view["borrowing_base"]),
            ("8. Advances Outstanding", spec["outstanding_advances_usd"]),
            ("9. Availability", view["availability"]),
        ],
        [
            (rule[1:], described[rule], count)
            for rule, count in sorted(view["failures"].items(), key=lambda item: int(item[0][1:]))
        ],
        [
            [
                names[rule],
                item["largest"],
                item["amount_cents"] / 100,
                item["share_pct"],
                item["limit_pct"],
                item["excess_cents"] / 100,
            ]
            for rule, item in view["concentrations"].items()
        ],
        "Chief Financial Officer, Northmoor Auto Finance Inc., as Servicer",
    )


def _servicer_report(
    cycle: dict[str, Any],
    month: str,
    data: dict[str, Any],
    history: list[list[Any]] | None,
    path: Path,
) -> dict[str, float]:
    spec = cycle["northmoor"]
    roll, rows = data["roll"], data["rows"]
    added = set(roll.new_loans)
    pool = pool_balance(rows)
    charge_offs = round(
        sum(row["charge_off_amount"] for row in rows if row["status"] == "CHARGED_OFF"), 2
    )
    recoveries = round(charge_offs * 0.42, 2)
    fee = round(pool * 0.02 / 12, 2)
    target = spec["excess_spread_pct"][month]
    # Interest on the Advances is what makes the stated excess spread true to the cent.
    cost = round(
        roll.interest_collected - fee - (charge_offs - recoveries) - target / 100 * pool / 12, 2
    )
    spread = round(
        (roll.interest_collected - fee - cost - (charge_offs - recoveries)) / pool * 1200, 2
    )
    period = f"{data['rows'][0]['cutoff_date']:%B %Y}"
    head = f"NMC Servicer Report - {period}"
    ratio = delinquency_ratio(rows)
    story: list[Any] = [
        text(spec["servicer"], REPORT_TITLE),
        text(f"Monthly Servicer Report: {spec['name']}, {period}", REPORT_HEAD),
        text(f"Lender: {cycle['lender']}", REPORT_BODY),
        Spacer(1, 0.15 * inch),
        text("A. Pool", REPORT_HEAD),
        table(
            [
                ["Item", "US$"],
                ["Beginning principal balance", f"{data['opening']:,.2f}"],
                [
                    f"Receivables added ({len(roll.new_loans)})",
                    f"{sum(r['current_balance'] for r in rows if r['loan_id'] in added):,.2f}",
                ],
                ["Principal collections", f"({roll.principal_collected:,.2f})"],
                ["Charge-offs", f"({charge_offs:,.2f})"],
                ["Ending principal balance", f"{pool:,.2f}"],
            ],
            widths=[4.3, 2.0],
            total_row=True,
        ),
        Spacer(1, 0.2 * inch),
        text("B. Excess spread", REPORT_HEAD),
        table(
            [
                ["Item", "US$"],
                ["Interest collections", f"{roll.interest_collected:,.2f}"],
                ["Servicing fee (2.00% a year)", f"({fee:,.2f})"],
                ["Interest on Advances", f"({cost:,.2f})"],
                ["Charge-offs net of recoveries", f"({charge_offs - recoveries:,.2f})"],
                ["Excess spread, annualised", f"{spread:.2f}%"],
            ],
            widths=[4.3, 2.0],
            total_row=True,
        ),
        Spacer(1, 0.2 * inch),
        text("C. Delinquency", REPORT_HEAD),
        table(
            [
                ["Measure", "Value"],
                ["60+ day Delinquency Ratio", f"{ratio:.2f}%"],
                [
                    "Receivables 60+ days past due",
                    f"{sum(1 for r in live(rows) if r['days_past_due'] >= 60):,}",
                ],
            ],
            widths=[4.3, 2.0],
        ),
    ]
    if history:
        story += [
            PageBreak(),
            text("D. Principal collections, last thirteen months", REPORT_HEAD),
            table(
                [["Month", "US$ thousands"], *[[label, f"{value:,}"] for label, value in history]],
                widths=[3.0, 2.0],
            ),
            text(
                "Collections fall each May, when tax refunds stop funding early payoffs.",
                REPORT_BODY,
            ),
        ]
    build(path, story, head, head, SANS)
    return {
        "pct": spread,
        "interest": roll.interest_collected,
        "fee": fee,
        "cost": cost,
        "net_losses": round(charge_offs - recoveries, 2),
        "pool": pool,
    }


def _credit_agreement(cycle: dict[str, Any], path: Path) -> None:
    spec = cycle["northmoor"]
    clauses = [
        (
            "Section 1.1 Definitions",
            [
                '"Delinquency Ratio" means, for any Collection Period, the aggregate Principal '
                "Balance of Receivables 60 or more days past due on its last day, divided by the "
                "aggregate Principal Balance of all Receivables on that day, excluding Receivables "
                "charged off.",
                '"Excess Spread" means, for any Collection Period, Interest Collections less the '
                "Servicing Fee, interest on the Advances and Charge-offs net of Recoveries, "
                "divided "
                "by the aggregate Principal Balance of the Receivables and multiplied by twelve.",
            ],
        ),
        (
            "Section 2.3 Borrowing Base",
            [
                f"The Borrowing Base is (a) the Eligible Receivables Balance less Excess "
                f"Concentrations, multiplied by {spec['advance_rate_pct']}%, less (b) a Reserve of "
                f"{spec['reserve_pct']}% of the Eligible Receivables Balance."
            ],
        ),
        (
            "Section 6.1 Reporting",
            [
                "By the fifteenth Business Day of each month the Servicer shall deliver, for the "
                "previous Collection Period, (a) a loan tape, (b) a Servicer Report and (c) a "
                "Borrowing Base Certificate."
            ],
        ),
        (
            "Section 7.1 Amortisation Events",
            [
                f"(a) The average Delinquency Ratio for the three most recent Collection Periods "
                f"exceeds {spec['delinquency_trigger_pct']:.1f}%.",
                "(b) The average Excess Spread for the three most recent Collection Periods "
                f"is less "
                f"than {spec['excess_spread_floor_pct']:.1f}%.",
                "On an Amortisation Event no further Advances may be made and all Collections are "
                "applied to repay the Advances.",
            ],
        ),
        (
            "Schedule 1 Eligibility Criteria",
            [f"{i}. {item['text']}." for i, item in enumerate(spec["eligibility"], start=1)],
        ),
        (
            "Schedule 2 Concentration Limits",
            [
                f"{i}. {item['text']}: {item['limit_pct']}% of the Eligible Receivables Balance."
                for i, item in enumerate(spec["concentration"], start=1)
            ],
        ),
    ]
    story: list[Any] = [
        Spacer(1, 1.4 * inch),
        text("CREDIT AGREEMENT", TITLE),
        text(f"dated as of {_date(spec['signed'])}", CENTERED),
        text(f"{spec['name'].upper()}, as Borrower", CENTERED),
        text(f"{spec['servicer'].upper()}, as Servicer", CENTERED),
        text(f"{cycle['lender'].upper()}, as Lender", CENTERED),
        text(f"US${spec['limit_usd']:,} {spec['type']}", CENTERED),
        PageBreak(),
        text("EXTRACT: SECTIONS RELEVANT TO MONITORING", ARTICLE),
        text("Conformed copy. Sections not relevant to monthly monitoring are omitted.", SMALL),
    ]
    for heading, paragraphs in clauses:
        story.append(text(heading, SECTION))
        story += [
            text(
                paragraph,
                INDENT_1
                if paragraph[:2].rstrip(".").isdigit() or paragraph.startswith("(")
                else BODY,
            )
            for paragraph in paragraphs
        ]
    build(path, story, "Northmoor Credit Agreement", "Northmoor Credit Agreement (extract)")
