"""Agreements, amendment, servicer reports and the client's model for the two test deals.

The wording and structure differ from the Bramble agreement on purpose: different section
numbering, schedules written as numbered paragraphs, a trigger defined in the body, and in the
SME agreement no reserve at all, so an extraction that invents one is caught.
"""

from datetime import date
from pathlib import Path
from typing import Any

from openpyxl import Workbook
from openpyxl.styles import Font
from reportlab.lib.units import inch
from reportlab.platypus import PageBreak, Spacer

from dealkit.newdeals.tapes import Row, delinquency_pct
from dealkit.pdfkit import (
    ARTICLE,
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
from dealkit.workbooks import _save_stable


def long_date(value: date) -> str:
    return f"{value:%B} {value.day}, {value.year}"


def usd(amount: float) -> str:
    return f"US${amount:,.0f}" if float(amount).is_integer() else f"US${amount:,.2f}"


def _cover(title: str, dated: date, borrower: str, lender: str) -> list[Any]:
    return [
        Spacer(1, 1.6 * inch),
        text(title, TITLE),
        text(f"dated as of {long_date(dated)}", CENTERED),
        Spacer(1, 0.3 * inch),
        text("among", CENTERED),
        text(borrower.upper(), CENTERED),
        text("as Borrower,", CENTERED),
        text("and", CENTERED),
        text(lender.upper(), CENTERED),
        text("as Lender and Administrative Agent", CENTERED),
        PageBreak(),
    ]


def consumer_agreement(deal: dict[str, Any], path: Path) -> None:
    b, lender = deal["borrower"]["name"], deal["lender"]["name"]
    e, c, t = deal["eligibility"], deal["concentration"], deal["triggers"]
    states = ", ".join(e["restricted_states"])
    story = _cover("LOAN AND SECURITY AGREEMENT", deal["signing_date"], b, lender)
    story += [
        text(
            f'This Loan and Security Agreement (this "Agreement") is entered into as of '
            f'{long_date(deal["signing_date"])} among {b} (the "Borrower"), '
            f'{deal["servicer"]} (the "Servicer") and {lender} (the "Lender").'
        ),
        text("ARTICLE I - DEFINITIONS", ARTICLE),
        text("Section 1.01 Defined Terms", SECTION),
        text(
            '"Instalment Receivable" means a fixed-rate, fully amortising consumer instalment '
            "loan originated at the point of sale by a Merchant and acquired by the Borrower."
        ),
        text(
            '"Eligible Receivable" means an Instalment Receivable that satisfies each of the '
            "criteria in Schedule A on the relevant Determination Date."
        ),
        text(
            '"Eligible Pool Balance" means the aggregate Principal Balance of all Eligible '
            "Receivables."
        ),
        text(
            '"Excess Concentration Amount" means the amount by which Eligible Receivables '
            "exceed any limit in Schedule B, each limit measured against the Eligible Pool "
            "Balance."
        ),
        text(
            f'"Delinquent Receivable" means an Instalment Receivable on which any payment is '
            f"{t['delinquency']['days']} or more days past its due date."
        ),
        text(
            '"Delinquency Ratio" means, for any Collection Period, the aggregate Principal '
            "Balance of Delinquent Receivables divided by the aggregate Principal Balance of all "
            "Instalment Receivables other than Charged-Off Receivables."
        ),
        text('"Determination Date" means the last day of each calendar month.'),
        text("ARTICLE II - THE LOANS", ARTICLE),
        text("Section 2.01 Commitment", SECTION),
        text(
            f"The Lender agrees to make advances to the Borrower from time to time during the "
            f"Availability Period in an aggregate principal amount outstanding not to exceed "
            f'{usd(deal["commitment_usd"])} (the "Maximum Facility Amount").'
        ),
        text("Section 2.02 Borrowing Base", SECTION),
        text(
            'The "Borrowing Base" on any date equals (a) the Advance Rate multiplied by the '
            "Eligible Pool Balance less the Excess Concentration Amount, minus (b) the Reserve "
            "Account Requirement."
        ),
        text(f'The "Advance Rate" is {deal["advance_rate_pct"]}%.'),
        text(
            f'The "Reserve Account Requirement" is {deal["reserve_pct"]}% of the Eligible '
            "Pool Balance."
        ),
        text("Section 2.03 Interest", SECTION),
        text(
            f"Advances bear interest at {deal['margin']}, payable monthly in arrears on the "
            f"{deal['report_day']}th day of each month."
        ),
        text("Section 2.04 Availability Period", SECTION),
        text(
            f"The Availability Period ends on {long_date(deal['revolving_period_end'])}. All "
            f"advances shall be repaid in full on {long_date(deal['final_maturity'])} (the "
            '"Final Maturity Date").'
        ),
        PageBreak(),
        text("ARTICLE III - REPORTING", ARTICLE),
        text("Section 3.01 Monthly Servicer Report", SECTION),
        text(
            f"The Servicer shall deliver a Monthly Servicer Report and a data tape of all "
            f"Instalment Receivables no later than the {deal['report_day']}th day of each "
            "calendar month, for the Collection Period ending on the preceding Determination "
            "Date."
        ),
        text("ARTICLE IV - AMORTISATION EVENTS", ARTICLE),
        text("Section 4.01 Amortisation Events", SECTION),
        text(
            f"(a) Delinquency Trigger. The average of the Delinquency Ratios for the three most "
            f"recent Collection Periods exceeds {t['delinquency']['limit_pct']}%.",
            INDENT_1,
        ),
        text(
            f"(b) Net Loss Trigger. The annualised Net Loss Ratio for any Collection Period "
            f"exceeds {t['net_loss']['limit_pct']}%.",
            INDENT_1,
        ),
        text(
            "(c) Borrowing Base Deficiency. The outstanding advances exceed the Borrowing Base "
            "and the deficiency is not cured within two Business Days.",
            INDENT_1,
        ),
        text("ARTICLE V - MISCELLANEOUS", ARTICLE),
        text("Section 5.01 Governing Law", SECTION),
        text(f"This Agreement is governed by the laws of the {deal['governing_law']}."),
        PageBreak(),
        text("SCHEDULE A - ELIGIBILITY CRITERIA", ARTICLE),
        text("Each Eligible Receivable must satisfy each of the following:"),
        text(
            f"1. No payment on the Receivable is more than {e['max_days_past_due']} days past due.",
            INDENT_1,
        ),
        text(
            f"2. The Obligor had a FICO score of at least {e['min_credit_score']} at origination.",
            INDENT_1,
        ),
        text(
            f"3. The original term of the Receivable does not exceed {e['max_original_term']} "
            "months.",
            INDENT_1,
        ),
        text(
            f"4. The Principal Balance of the Receivable does not exceed "
            f"{usd(e['max_current_balance'])}.",
            INDENT_1,
        ),
        text(
            f"5. The annual percentage rate of the Receivable does not exceed {e['max_apr']}%.",
            INDENT_1,
        ),
        text(
            f"6. The Obligor does not reside in any of the following Restricted States: {states}.",
            INDENT_1,
        ),
        text(
            "7. The Receivable is not a Charged-Off Receivable or a Defaulted Receivable.", INDENT_1
        ),
        Spacer(1, 0.2 * inch),
        text("SCHEDULE B - CONCENTRATION LIMITS", ARTICLE),
        text(
            "Eligible Receivables in excess of the following shall be Excess Concentration Amounts:"
        ),
        text(
            f"1. Receivables owed by Obligors residing in any single State: {c['state_pct']}% "
            "of the Eligible Pool Balance.",
            INDENT_1,
        ),
        text(
            f"2. Receivables with an Obligor FICO score at origination below "
            f"{c['low_score']['below']}: {c['low_score']['limit_pct']}% of the Eligible Pool "
            "Balance.",
            INDENT_1,
        ),
        text(
            f"3. Receivables with an original term of more than {c['long_term']['above']} "
            f"months: {c['long_term']['limit_pct']}% of the Eligible Pool Balance.",
            INDENT_1,
        ),
    ]
    build(path, story, "Loan and Security Agreement", "Loan and Security Agreement - Executed")


def consumer_amendment(deal: dict[str, Any], path: Path) -> None:
    a = deal["amendment"]
    b, lender = deal["borrower"]["name"], deal["lender"]["name"]
    story = [
        Spacer(1, 1.2 * inch),
        text("FIRST AMENDMENT TO LOAN AND SECURITY AGREEMENT", TITLE),
        text(f"dated {long_date(a['signed'])}", CENTERED),
        Spacer(1, 0.4 * inch),
        text(
            f"This First Amendment is made between {b} and {lender} and amends the Loan and "
            f"Security Agreement dated as of {long_date(deal['signing_date'])} (the "
            '"Agreement").'
        ),
        text("1. Amendments", SECTION),
        text(
            f"(a) In Section 2.02, the Advance Rate of {deal['advance_rate_pct']}% is replaced "
            f"by {a['advance_rate_pct']}%, with effect from {long_date(a['effective'])}.",
            INDENT_1,
        ),
        text(
            f'(b) Schedule B is amended by adding a new paragraph 4: "4. '
            f"{a['new_concentration']['text']}: {a['new_concentration']['limit_pct']}% of the "
            f'Eligible Pool Balance.", with effect from {long_date(a["effective"])}.',
            INDENT_1,
        ),
        text("2. No Other Changes", SECTION),
        text(
            "Except as set out in this First Amendment, the Agreement remains in full force "
            "and effect."
        ),
        text("3. Governing Law", SECTION),
        text(f"This First Amendment is governed by the laws of the {deal['governing_law']}."),
    ]
    build(path, story, "First Amendment", "First Amendment - Executed")


def sme_agreement(deal: dict[str, Any], path: Path) -> None:
    b, lender = deal["borrower"]["name"], deal["lender"]["name"]
    e, c, t = deal["eligibility"], deal["concentration"], deal["triggers"]
    sectors = ", ".join(e["excluded_sectors"])
    story = _cover("RECEIVABLES FINANCING AGREEMENT", deal["signing_date"], b, lender)
    story += [
        text(
            f"THIS RECEIVABLES FINANCING AGREEMENT is made on {long_date(deal['signing_date'])} "
            f'between {b} (the "Company"), {deal["parent"]} (the "Originator" and '
            f'"Servicer") and {lender} (the "Funder").'
        ),
        text("1. INTERPRETATION", ARTICLE),
        text("1.1 Definitions", SECTION),
        text(
            '"Business Loan" means a senior secured or unsecured amortising term loan made by '
            "the Originator to a small or medium-sized business and sold to the Company."
        ),
        text(
            '"Qualifying Loan" means a Business Loan that meets every requirement of the '
            "First Schedule on the relevant Reporting Date."
        ),
        text(
            '"Qualifying Balance" means the aggregate outstanding principal of all Qualifying '
            "Loans, less any amount by which Qualifying Loans exceed a limit in the Second "
            "Schedule."
        ),
        text(
            f'"Arrears Ratio" means the outstanding principal of Business Loans more than '
            f"{t['delinquency']['days'] - 1} days in arrears divided by the outstanding "
            "principal of all Business Loans that are not Written-Off Loans."
        ),
        text("2. THE FACILITY", ARTICLE),
        text("2.1 Facility Limit", SECTION),
        text(
            f"The Funder makes available to the Company a revolving facility of up to "
            f'{usd(deal["commitment_usd"])} (the "Facility Limit").'
        ),
        text("2.2 Funding Base", SECTION),
        text(
            f"The Company may request an advance up to the Funding Base, which is "
            f'{deal["advance_rate_pct"]}% of the Qualifying Balance (the "Funding Ratio").'
        ),
        text("2.3 Pricing", SECTION),
        text(f"Each advance accrues interest at {deal['margin']}."),
        text("2.4 Term", SECTION),
        text(
            f"The Company may request advances until {long_date(deal['revolving_period_end'])}. "
            f"The Termination Date is {long_date(deal['final_maturity'])}."
        ),
        PageBreak(),
        text("3. INFORMATION", ARTICLE),
        text("3.1 Monthly Report", SECTION),
        text(
            f"By the {deal['report_day']}th day of each month the Servicer shall provide a "
            "monthly report and a loan-level data file as at the last day of the previous "
            'month (the "Reporting Date").'
        ),
        text("4. STOP EVENTS", ARTICLE),
        text("4.1 Arrears", SECTION),
        text(
            f"A Stop Event occurs if the Arrears Ratio, averaged over the three most recent "
            f"Reporting Dates, is greater than {t['delinquency']['limit_pct']}%."
        ),
        text("4.2 Consequences", SECTION),
        text(
            "While a Stop Event continues, no further advance may be requested and all "
            "collections are applied to repay advances."
        ),
        text("5. LAW", ARTICLE),
        text(f"This agreement is governed by the law of the {deal['governing_law']}."),
        PageBreak(),
        text("FIRST SCHEDULE - QUALIFYING LOANS", ARTICLE),
        text(f"(a) the loan is not more than {e['max_days_past_due']} days in arrears;", INDENT_1),
        text(
            f"(b) the borrower's internal risk grade is {e['max_risk_grade']} or better on the "
            "Originator's scale of 1 (strongest) to 10 (weakest);",
            INDENT_1,
        ),
        text(
            f"(c) the original principal of the loan did not exceed "
            f"{usd(e['max_original_principal'])};",
            INDENT_1,
        ),
        text(
            f"(d) the remaining term of the loan is no more than {e['max_remaining_term']} months;",
            INDENT_1,
        ),
        text(
            f"(e) the borrower does not operate in an Excluded Sector, being {sectors}; and",
            INDENT_1,
        ),
        text("(f) the loan is not a Defaulted Loan or a Written-Off Loan.", INDENT_1),
        Spacer(1, 0.2 * inch),
        text("SECOND SCHEDULE - PORTFOLIO LIMITS", ARTICLE),
        text(
            f"1. Loans to any one borrower: {c['obligor_pct']}% of the aggregate principal of "
            "Qualifying Loans.",
            INDENT_1,
        ),
        text(
            f"2. Loans to borrowers in any one sector: {c['sector_pct']}% of the aggregate "
            "principal of Qualifying Loans.",
            INDENT_1,
        ),
        text(
            f"3. Loans to borrowers in any one region: {c['region_pct']}% of the aggregate "
            "principal of Qualifying Loans.",
            INDENT_1,
        ),
        text(
            f"4. Loans to borrowers with a risk grade of {c['weak_grade']['from']} or weaker: "
            f"{c['weak_grade']['limit_pct']}% of the aggregate principal of Qualifying Loans.",
            INDENT_1,
        ),
    ]
    build(path, story, "Receivables Financing Agreement", "Receivables Financing Agreement")


def servicer_report(
    deal: dict[str, Any],
    rows: list[Row],
    cutoff: date,
    path: Path,
    facts: dict[str, Any] | None,
    closed: tuple[str, ...],
    history: dict[str, str],
) -> float:
    """The month's report: pool, collections, losses and the arrears trend. Returns the
    month's ratio."""
    days = deal["triggers"]["delinquency"]["days"]
    live = [row for row in rows if row["status"] not in closed]
    pool = sum(row["current_balance"] for row in live)
    ratio = delinquency_pct(rows, days, closed)
    month = f"{cutoff:%B %Y}"
    trend = [[label, f"{value}%"] for label, value in history.items()] + [[month, f"{ratio:.2f}%"]]
    story = [
        text(f"{deal['servicer']}", REPORT_HEAD),
        text(f"Monthly Report - {month}", REPORT_TITLE),
        text(
            f"Facility: {deal['borrower']['name']}. Reporting date {long_date(cutoff)}.",
            REPORT_BODY,
        ),
        text("Pool summary", REPORT_HEAD),
        table(
            [
                ["Measure", "Value"],
                ["Loans outstanding", f"{len(live):,}"],
                ["Outstanding principal (US$)", f"{pool:,.2f}"],
            ],
            widths=[3.5, 2.0],
        ),
        Spacer(1, 0.15 * inch),
    ]
    if facts is not None:
        story += [
            text("Collections and losses", REPORT_HEAD),
            text(
                "Principal collections for the month were "
                f"US${facts['principal_collections']:,.2f}.",
                REPORT_BODY,
            ),
            text(
                f"Charge-offs for the month were US${facts['charge_offs']:,.2f} across "
                f"{len(facts['charged_off'])} loans.",
                REPORT_BODY,
            ),
            text(
                f"New loans purchased in the month: {len(facts['new_loans'])}, with principal of "
                f"US${facts['new_balance']:,.2f}.",
                REPORT_BODY,
            ),
        ]
    story += [
        text(f"Arrears ({days}+ days) as a share of outstanding principal", REPORT_HEAD),
        table([["Month", "Ratio"], *trend], widths=[3.5, 2.0]),
    ]
    build(path, story, f"Monthly Report {month}", f"{deal['servicer']} - Monthly Report", SANS)
    return ratio


def client_model(deal: dict[str, Any], path: Path) -> None:
    """The lender's own borrowing base model, with its own (stale) advance rate."""
    m = deal["client_model"]
    book = Workbook()
    sheet = book.active
    sheet.title = "Inputs"
    sheet.append(
        [f"{deal['lender']['short']} - {deal['borrower']['short']} borrowing base model v1"]
    )
    sheet["A1"].font = Font(bold=True)
    sheet.append([])
    for label, value in [
        ("Maximum facility amount", deal["commitment_usd"]),
        ("Advance rate", float(m["stale_advance_rate_pct"]) / 100),
        ("Reserve account requirement", float(deal["reserve_pct"]) / 100),
        ("Single state limit", float(deal["concentration"]["state_pct"]) / 100),
        ("FICO below 640 limit", float(deal["concentration"]["low_score"]["limit_pct"]) / 100),
        ("Term over 48 months limit", float(deal["concentration"]["long_term"]["limit_pct"]) / 100),
        (
            "Delinquency trigger (3m avg, 60+)",
            float(deal["triggers"]["delinquency"]["limit_pct"]) / 100,
        ),
    ]:
        sheet.append([label, value])
    calc = book.create_sheet("Calculation")
    calc.append(["Eligible pool balance", None])
    calc.append(["Less excess concentrations", None])
    calc.append(["Borrowing base", "=(B1-B2)*Inputs!B4-B1*Inputs!B5"])
    _save_stable(book, path)
