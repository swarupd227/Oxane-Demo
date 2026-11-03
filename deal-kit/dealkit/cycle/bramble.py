"""Bramble's May 2026 submissions, rolled forward from the April tape built at onboarding.

Planted here: 27 loans missing from the May tape (M2), 9 loans charged off in the servicer report
but active on the tape (M3), Amendment No. 2 (M4), the affiliate guarantee behind the leverage
question (M6), two new tape columns (N1) and a US$3.20 rounding difference in the certificate (N3).
"""

import copy
import dataclasses
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np
from reportlab.lib.units import inch
from reportlab.platypus import PageBreak, Spacer

from dealkit.calc import system_view
from dealkit.cycle.common import (
    CLOSED,
    delinquency_ratio,
    live,
    new_loan,
    pick_total,
    pool_balance,
    roll_month,
    set_delinquency,
    write_certificate,
    write_tape,
)
from dealkit.legal_docs import _date
from dealkit.pdfkit import (
    BODY,
    CENTERED,
    INDENT_1,
    REPORT_BODY,
    REPORT_HEAD,
    REPORT_TITLE,
    SANS,
    SECTION,
    TITLE,
    build,
    table,
    text,
)
from dealkit.tape import COLUMNS

FILES = {
    "loan_tape": "BAF_Loan_Tape_2026-05.csv",
    "servicer_report": "BAF_Servicer_Report_May_2026.pdf",
    "borrowing_base_certificate": "Bramble_BBC_May_2026.xlsx",
    "compliance_certificate": "BAF_Compliance_Certificate_Q1_2026.pdf",
    "amendment_2": "Bramble_Amendment_No_2.pdf",
}


def _usd(amount: float) -> str:
    return f"{amount:,.2f}"


def build_bramble(
    deal: dict[str, Any], cycle: dict[str, Any], april: list[dict[str, Any]], folder: Path
) -> dict[str, Any]:
    spec = cycle["bramble"]
    planted = spec["planted"]
    rng = np.random.default_rng(cycle["seed"])
    cutoff: date = spec["cutoff"]
    dealers = sorted({row["dealer_name"] for row in april})

    # Onboarding escalated the three shared VINs; the borrower repurchased the second loan of each.
    april_by_id = {row["loan_id"]: row for row in april}
    first_number = max(int(row["loan_id"][3:]) for row in april) + 1
    fresh = [
        new_loan(
            rng,
            f"BAF{first_number + i}",
            cutoff,
            dealers,
            deal["tape"]["mean_original_balance_usd"],
            "BAF01",
        )
        for i in range(spec["new_loans"])
    ]
    roll = roll_month(april, rng, cutoff, spec["payoff_rate"], charge_offs=6, new_rows=fresh)
    duplicates = _shared_vin_seconds(april)
    for row in roll.rows:
        if row["loan_id"] in duplicates and row["status"] == "ACTIVE":
            roll.principal_collected += row["previous_balance"] - row["current_balance"]
            roll.principal_collected += row["current_balance"]
            row.update(status="REPURCHASED", current_balance=0.0)
            roll.payoffs.append(row["loan_id"])

    # M2: loans the servicer collected on, but left off the tape.
    steady = [
        row
        for row in roll.rows
        if row["status"] == "ACTIVE"
        and row["previous_balance"] is not None
        and 9000 < row["current_balance"] < 26000
        and april_by_id[row["loan_id"]]["days_past_due"] == 0
    ]
    missing = pick_total(rng, steady, planted["m2_missing_loans"], planted["m2_gap_usd"], 400)
    missing_ids = {row["loan_id"] for row in missing}
    hidden_principal = sum(row["previous_balance"] - row["current_balance"] for row in missing)
    hidden_interest = sum(row["previous_balance"] * row["apr"] / 1200 for row in missing)
    roll.rows = [row for row in roll.rows if row["loan_id"] not in missing_ids]

    previous_late = {row["loan_id"] for row in april if row["days_past_due"] >= 31}
    set_delinquency(roll, rng, spec["may_delinquency_pct"], previous_late, keep_current=set())
    roll.principal_collected = round(roll.principal_collected + hidden_principal, 2)
    roll.interest_collected = round(roll.interest_collected + hidden_interest, 2)

    # M3: loans the servicer charged off, after bankruptcy or a total loss on the car, that the
    # tape still shows as live. Most were already late.
    late = [
        row
        for row in roll.rows
        if row["status"] in ("ACTIVE", "DELINQUENT")
        and row["previous_balance"] is not None
        and 8000 < row["current_balance"] < 24000
        and (row["status"] == "DELINQUENT" or int(row["loan_id"][3:]) % 9 == 0)
    ]
    unreported = pick_total(
        rng, late, planted["m3_charge_off_loans"], planted["m3_charge_off_usd"], 1500
    )

    rows = sorted(roll.rows, key=lambda row: row["loan_id"])
    extra = {
        name: [
            ("Y" if (int(row["loan_id"][3:]) * (7 + k)) % 10 < (3 if k else 6) else "N")
            for row in rows
        ]
        for k, name in enumerate(spec["new_columns"])
    }
    write_tape(rows, COLUMNS, folder / FILES["loan_tape"], extra)

    opening = pool_balance(april)
    additions = round(
        sum(row["current_balance"] for row in rows if row["loan_id"] in roll.new_loans), 2
    )
    tape_charge_offs = round(
        sum(row["charge_off_amount"] for row in rows if row["status"] == "CHARGED_OFF"), 2
    )
    closing_tape = pool_balance(rows)
    expected = round(opening + additions - roll.principal_collected - tape_charge_offs, 2)
    servicer_charge_offs = round(
        tape_charge_offs + sum(r["current_balance"] for r in unreported), 2
    )
    history = spec["delinquency_history"]
    may_ratio = delinquency_ratio(rows)

    facts = {
        "rows": rows,
        "roll_forward": {
            "opening": opening,
            "additions": additions,
            "new_loans": len(roll.new_loans),
            "principal_collected": roll.principal_collected,
            "charge_offs": tape_charge_offs,
            "expected_closing": expected,
            "tape_closing": closing_tape,
            "gap": round(expected - closing_tape, 2),
            "missing_loans": sorted(missing_ids),
            "missing_balance": round(sum(row["current_balance"] for row in missing), 2),
        },
        "charge_offs": {
            "tape": tape_charge_offs,
            "servicer": servicer_charge_offs,
            "difference": round(servicer_charge_offs - tape_charge_offs, 2),
            "loans": [row["loan_id"] for row in unreported],
        },
        "delinquency": {
            "february": history["february"],
            "march": history["march"],
            "april": history["april"],
            "may": may_ratio,
            "average": round((history["march"] + history["april"] + may_ratio) / 3, 2),
        },
        "interest_collected": roll.interest_collected,
    }
    _servicer_report(deal, cycle, rows, unreported, facts, folder / FILES["servicer_report"])
    facts["certificate"] = _certificate(
        deal, cycle, rows, folder / FILES["borrowing_base_certificate"]
    )
    _compliance_certificate(deal, cycle, folder / FILES["compliance_certificate"])
    _amendment_2(deal, cycle, folder / FILES["amendment_2"])
    return facts


def _shared_vin_seconds(april: list[dict[str, Any]]) -> set[str]:
    seen: dict[str, str] = {}
    seconds = set()
    for row in april:
        if row["vin"] in seen:
            seconds.add(row["loan_id"])
        seen.setdefault(row["vin"], row["loan_id"])
    return seconds


def _servicer_report(
    deal: dict[str, Any],
    cycle: dict[str, Any],
    rows: list[dict[str, Any]],
    unreported: list[dict[str, Any]],
    facts: dict[str, Any],
    path: Path,
) -> None:
    roll, offs, trend = facts["roll_forward"], facts["charge_offs"], facts["delinquency"]
    servicer_closing = round(
        roll["opening"] + roll["additions"] - roll["principal_collected"] - offs["servicer"], 2
    )
    charged = sorted(
        [
            (row["loan_id"], row["charge_off_amount"])
            for row in rows
            if row["status"] == "CHARGED_OFF"
        ]
        + [(row["loan_id"], row["current_balance"]) for row in unreported]
    )
    pool = live(rows)

    def bucket(row: dict[str, Any]) -> str:
        for limit, name in (
            (0, "A. Current"),
            (30, "B. 1-30 days"),
            (59, "C. 31-59 days"),
            (89, "D. 60-89 days"),
        ):
            if row["days_past_due"] <= limit:
                return name
        return "E. 90+ days"

    buckets: dict[str, list[float]] = {}
    for row in pool:
        buckets.setdefault(bucket(row), []).append(row["current_balance"])
    total = sum(sum(values) for values in buckets.values())
    period = cycle["period"]["label"]
    head = f"Servicer Report - {period}"
    story: list[Any] = [
        Spacer(1, 1.6 * inch),
        text("Bramble Auto Finance LLC", REPORT_TITLE),
        text(f"Monthly Servicer Report: {period}", REPORT_HEAD),
        text(f"Issuer: {deal['borrower']['name']}", REPORT_BODY),
        text(f"Lender: {deal['lender']['name']}", REPORT_BODY),
        text(f"Collection Period end: {_date(cycle['bramble']['cutoff'])}", REPORT_BODY),
        PageBreak(),
        text("1. Pool balance", REPORT_HEAD),
        table(
            [
                ["Item", "Amount (US$)"],
                ["Pool balance at start of period", _usd(roll["opening"])],
                [f"Receivables purchased ({roll['new_loans']} loans)", _usd(roll["additions"])],
                ["Principal collections", f"({_usd(roll['principal_collected'])})"],
                ["Gross charge-offs", f"({_usd(offs['servicer'])})"],
                ["Pool balance at end of period", _usd(servicer_closing)],
            ],
            widths=[4.3, 2.0],
            total_row=True,
        ),
        Spacer(1, 0.25 * inch),
        text("2. Collections", REPORT_HEAD),
        table(
            [
                ["Item", "Amount (US$)"],
                [
                    "Principal received, including prepayments and repurchases",
                    _usd(roll["principal_collected"]),
                ],
                ["Interest received", _usd(facts["interest_collected"])],
                [
                    "Total collections",
                    _usd(roll["principal_collected"] + facts["interest_collected"]),
                ],
            ],
            widths=[4.3, 2.0],
            total_row=True,
        ),
        PageBreak(),
        text("3. Receivables charged off in the period", REPORT_HEAD),
        table(
            [
                ["Loan number", "Charge-off amount (US$)"],
                *[[loan, _usd(amount)] for loan, amount in charged],
                ["Total", _usd(offs["servicer"])],
            ],
            widths=[3.0, 2.0],
            total_row=True,
        ),
        PageBreak(),
        text("4. Delinquency at month end", REPORT_HEAD),
        table(
            [
                ["Bucket", "Loans", "Balance (US$)", "% of pool"],
                *[
                    [
                        name,
                        f"{len(buckets[name]):,}",
                        _usd(sum(buckets[name])),
                        f"{sum(buckets[name]) / total * 100:.2f}%",
                    ]
                    for name in sorted(buckets)
                ],
            ],
            widths=[2.9, 0.8, 1.6, 1.0],
        ),
        Spacer(1, 0.25 * inch),
        text("5. Delinquency trend", REPORT_HEAD),
        table(
            [
                ["Collection Period", "60+ day ratio"],
                ["February 2026", f"{trend['february']:.2f}%"],
                ["March 2026", f"{trend['march']:.2f}%"],
                ["April 2026", f"{trend['april']:.2f}%"],
                [period, f"{trend['may']:.2f}%"],
                ["Three-month average", f"{trend['average']:.2f}%"],
            ],
            widths=[4.3, 2.0],
            total_row=True,
        ),
    ]
    build(path, story, head, head, SANS)


def _certificate(
    deal: dict[str, Any], cycle: dict[str, Any], rows: list[dict[str, Any]], path: Path
) -> dict[str, float]:
    """After April's query the borrower now combines the Sunrise names. Its only slip is a
    US$3.20 rounding difference in the eligible pool."""
    may = copy.deepcopy(deal)
    may["bbc"]["outstanding_advances_usd"] = cycle["bramble"]["outstanding_advances_usd"]
    pool = [row for row in rows if row["status"] not in ("PAID_OFF", "REPURCHASED")]
    view = system_view(pool, may, match_dealers=True)
    rounding = round(cycle["bramble"]["planted"]["n3_rounding_usd"] * 100)
    eligible = view.eligible_pool + rounding
    base = round((eligible - view.excess) * view.advance_rate_pct / 100) - round(
        eligible * may["terms"]["reserve_pct"] / 100
    )
    stated = dataclasses.replace(
        view,
        eligible_pool=eligible,
        borrowing_base=base,
        reserve=round(eligible * may["terms"]["reserve_pct"] / 100),
    )
    outstanding = cycle["bramble"]["outstanding_advances_usd"]
    availability = min(stated.borrowing_base / 100, deal["facility"]["limit_usd"]) - outstanding
    described = {item["id"]: item["text"] for item in deal["eligibility"]}
    names = {item["id"]: item["text"] for item in deal["concentration"]}
    write_certificate(
        path,
        deal["borrower"]["name"],
        cycle["bramble"]["cutoff"],
        [
            ("1. Aggregate Outstanding Balance of Pool Receivables", stated.gross_pool / 100),
            (
                "2. Less Receivables that are not Eligible Receivables",
                -(stated.gross_pool - stated.eligible_pool) / 100,
            ),
            ("3. Eligible Pool Balance", stated.eligible_pool / 100),
            ("4. Less Excess Concentration Amount", -stated.excess / 100),
            ("5. Advance Rate", stated.advance_rate_pct / 100),
            ("6. Less Reserve Amount", -stated.reserve / 100),
            ("7. Borrowing Base", stated.borrowing_base / 100),
            ("8. Outstanding Advances", outstanding),
            ("9. Availability", round(availability, 2)),
        ],
        [
            (rule[1:], described[rule], len(ids))
            for rule, ids in sorted(
                view.failures_by_rule.items(), key=lambda item: int(item[0][1:])
            )
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
            for rule, item in view.concentrations.items()
        ],
        "Treasurer, Bramble Auto Receivables I LLC",
    )
    return {
        "eligible_pool": stated.eligible_pool / 100,
        "excess": stated.excess / 100,
        "borrowing_base": stated.borrowing_base / 100,
        "availability": round(availability, 2),
        "outstanding_advances": outstanding,
    }


def _compliance_certificate(deal: dict[str, Any], cycle: dict[str, Any], path: Path) -> None:
    spec, f, terms = cycle["bramble"]["compliance"], deal["financials"], deal["terms"]
    worth = f["total_equity"] - f["goodwill"] - f["intangibles"] - f["related_party_receivables"]
    carve = min(f["subordinated_debt"], terms["subordinated_debt_cap_usd"] // 1000)
    leverage = round((f["total_liabilities"] - carve) / (worth + carve), 2)
    head = "Compliance Certificate - Quarter ended 31 March 2026"
    story: list[Any] = [
        text("Bramble Auto Finance LLC", REPORT_TITLE),
        text("Compliance Certificate", REPORT_HEAD),
        text(f"To: {deal['lender']['name']}, as Lender and Administrative Agent", REPORT_BODY),
        text(
            "Delivered under Section 5.1(c) of the Credit Agreement dated "
            f"{_date(terms['signing_date'])} "
            f"for the fiscal quarter ended {_date(spec['period_end'])}.",
            REPORT_BODY,
        ),
        text("All amounts in US$ thousands unless stated otherwise.", REPORT_BODY),
        Spacer(1, 0.2 * inch),
        text("1. Financial covenants", REPORT_HEAD),
        table(
            [
                ["Covenant", "Section", "Required", "Actual", "In compliance"],
                [
                    "Minimum Tangible Net Worth",
                    "6.12(a)",
                    f"{terms['min_tangible_net_worth_usd'] // 1000:,}",
                    f"{worth:,}",
                    "Yes",
                ],
                [
                    "Maximum Leverage Ratio",
                    "6.12(b)",
                    f"{terms['max_leverage_ratio']:.2f} to 1.00",
                    f"{leverage:.2f} to 1.00",
                    "Yes",
                ],
                [
                    "Minimum Liquidity",
                    "6.12(d)",
                    f"{terms['min_liquidity_usd'] // 1000:,}",
                    f"{f['unrestricted_cash']:,}",
                    "Yes",
                ],
            ],
            widths=[2.2, 0.8, 1.2, 1.2, 1.0],
        ),
        Spacer(1, 0.2 * inch),
        text("2. Leverage Ratio calculation", REPORT_HEAD),
        table(
            [
                ["Line", "Amount"],
                ["Total Liabilities per balance sheet", f"{f['total_liabilities']:,}"],
                ["Less Subordinated Debt under 6.12(c)", f"({carve:,})"],
                ["Adjusted Total Liabilities", f"{f['total_liabilities'] - carve:,}"],
                ["Tangible Net Worth", f"{worth:,}"],
                ["Add Subordinated Debt under 6.12(c)", f"{carve:,}"],
                ["Adjusted Tangible Net Worth", f"{worth + carve:,}"],
                ["Leverage Ratio", f"{leverage:.2f} to 1.00"],
            ],
            widths=[4.3, 2.0],
            total_row=True,
        ),
        Spacer(1, 0.2 * inch),
        text("3. Contingent obligations", REPORT_HEAD),
        text(
            "The Parent has guaranteed the obligations of "
            f"{spec['guaranteed_party']}, an affiliate "
            "under common ownership, under its dealer floor plan facility. The amount guaranteed "
            f"at quarter end was US${spec['affiliate_guarantee_k']:,} thousand. "
            "No payment has been "
            "demanded and, as no loss is probable, the guarantee is not recognised on the balance "
            "sheet. It is therefore excluded from Total Liabilities above.",
            REPORT_BODY,
        ),
        Spacer(1, 0.2 * inch),
        text("4. Certification", REPORT_HEAD),
        text(
            "The undersigned certifies that no Default or Event of Default has occurred and is "
            "continuing, and that the calculations above are true and correct.",
            REPORT_BODY,
        ),
        text(
            f"Chief Financial Officer, Bramble Auto Finance LLC. Dated {_date(spec['delivered'])}.",
            REPORT_BODY,
        ),
    ]
    build(path, story, head, head, SANS)


def _amendment_2(deal: dict[str, Any], cycle: dict[str, Any], path: Path) -> None:
    spec = cycle["bramble"]["amendment_2"]
    borrower, lender = deal["borrower"]["name"], deal["lender"]["name"]
    signed, effective = _date(spec["signed"]), _date(spec["effective"])
    old_limit, new_limit = deal["facility"]["limit_usd"], spec["limit_usd"]
    old_dealer = next(item["limit_pct"] for item in deal["concentration"] if item["id"] == "C2")
    story = [
        Spacer(1, 1.5 * inch),
        text("AMENDMENT NO. 2 TO CREDIT AGREEMENT", TITLE),
        text(f"dated {signed}", CENTERED),
        Spacer(1, 0.3 * inch),
        text("between", CENTERED),
        text(borrower.upper(), CENTERED),
        text("as Borrower", CENTERED),
        text("and", CENTERED),
        text(lender.upper(), CENTERED),
        text("as Lender and Administrative Agent", CENTERED),
        PageBreak(),
        text(
            f'This Amendment No. 2 (this "Amendment") is dated {signed} and is made between '
            f"{borrower} and {lender}. It amends the Credit Agreement dated as of "
            f"{_date(deal['terms']['signing_date'])}, as amended by Amendment No. 1 dated "
            f'{_date(deal["terms"]["amendment_signed"])} (the "Credit Agreement").'
        ),
        text("1. Definitions", SECTION),
        text(
            "Capitalised terms used and not defined in this Amendment have the meanings given "
            "in the Credit Agreement."
        ),
        text("2. Amendments to the Credit Agreement", SECTION),
        text(
            f"(a) In Annex A, the Commitment of the Lender of US${old_limit:,} is deleted and "
            f"replaced with US${new_limit:,}, and the Facility Limit is increased accordingly, "
            f"with effect from {effective}.",
            INDENT_1,
        ),
        text(
            f'(b) In Schedule 2, row 2, "{old_dealer}%" is deleted and replaced with '
            f'"{spec["dealer_limit_pct"]}%", with effect from {effective}.',
            INDENT_1,
        ),
        text(
            "(c) Each Borrowing Base Certificate for a Collection Period ending on or after "
            f"{effective} shall be calculated using the Credit Agreement as amended by this "
            "Amendment. No Borrowing Base Certificate for an earlier Collection Period is "
            "reopened, and the Collection Period ending 31 May 2026 is calculated without it.",
            INDENT_1,
        ),
        text("3. Conditions to Effectiveness", SECTION),
        text(
            "This Amendment takes effect on the later of its effective date and the date on which "
            "the Lender has received this Amendment signed by each party and payment of the "
            "upsize fee agreed in a separate letter."
        ),
        text("4. Continuing Effect", SECTION),
        text(
            "Except as expressly amended by this Amendment, the Credit Agreement remains in full "
            "force and effect."
        ),
        text("5. Governing Law", SECTION),
        text(
            f"This Amendment is governed by the law of the State of "
            f"{deal['terms']['governing_law']}."
        ),
        Spacer(1, 0.4 * inch),
        text(f"{borrower.upper()}, as Borrower", BODY),
        text("By: /s/ (signature on file)", BODY),
        Spacer(1, 0.3 * inch),
        text(f"{lender.upper()}, as Lender and Administrative Agent", BODY),
        text("By: /s/ (signature on file)", BODY),
    ]
    build(path, story, "Amendment No. 2", "Amendment No. 2 to Credit Agreement")


__all__ = ["CLOSED", "FILES", "build_bramble"]
