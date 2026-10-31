"""The servicer report and the borrower's financial statements."""

from collections import defaultdict
from collections.abc import Callable
from pathlib import Path
from typing import Any

from reportlab.lib.units import inch
from reportlab.platypus import PageBreak, Spacer

from dealkit.pdfkit import REPORT_BODY, REPORT_HEAD, REPORT_TITLE, SANS, build, table, text


def _usd(amount: float) -> str:
    return f"{amount:,.2f}"


def _pct(part: float, whole: float) -> str:
    return f"{part / whole * 100:.2f}%"


def delinquency_ratio(rows: list[dict[str, Any]]) -> float:
    """Delinquency Ratio as defined in the agreement, excluding charged-off loans."""
    live = [row for row in rows if row["status"] != "CHARGED_OFF"]
    late = sum(row["current_balance"] for row in live if row["days_past_due"] >= 60)
    return round(late / sum(row["current_balance"] for row in live) * 100, 2)


def _strat(rows: list[dict[str, Any]], label: str, key: Callable[[dict[str, Any]], str],
           top: int | None = None, keep_order: bool = False) -> list[Any]:
    groups: defaultdict[str, list[float]] = defaultdict(list)
    for row in rows:
        groups[key(row)].append(row["current_balance"])
    total = sum(sum(values) for values in groups.values())
    ordered = sorted(groups) if keep_order else sorted(
        groups, key=lambda name: (-sum(groups[name]), name))
    body = [
        [name, f"{len(groups[name]):,}", _usd(sum(groups[name])), _pct(sum(groups[name]), total)]
        for name in ordered[:top]
    ]
    return [table([[label, "Loans", "Balance (US$)", "% of pool"], *body],
                  widths=[2.9, 0.8, 1.6, 1.0])]


def build_servicer_report(deal: dict[str, Any], rows: list[dict[str, Any]], path: Path) -> None:
    history = deal["servicer_history"]
    april_ratio = delinquency_ratio(rows)
    average = round((history["february_pct"] + history["march_pct"] + april_ratio) / 3, 2)
    live = [row for row in rows if row["status"] not in ("CHARGED_OFF",)]
    pool = sum(row["current_balance"] for row in live)

    interest = sum(row["current_balance"] * row["apr"] / 1200 for row in live)
    scheduled = sum(row["monthly_payment"] for row in live)
    principal = scheduled - interest
    charged = [row for row in rows if row["status"] == "CHARGED_OFF"]
    repo = [row for row in rows if row["status"] == "REPO"]

    def bucket(row: dict[str, Any]) -> str:
        dpd = row["days_past_due"]
        for limit, name in ((0, "A. Current"), (30, "B. 1-30 days"), (59, "C. 31-59 days"),
                            (89, "D. 60-89 days")):
            if dpd <= limit:
                return name
        return "E. 90+ days"

    def band(field: str, edges: list[int]) -> Callable[[dict[str, Any]], str]:
        def label(row: dict[str, Any]) -> str:
            value = row[field]
            for low, high in zip(edges, edges[1:], strict=False):
                if low <= value < high:
                    return f"{low:>3}-{high - 1}"
            return f"{edges[-1]}+"

        return label

    period = f"{deal['tape']['cutoff_date']:%B %Y}"
    head = f"Servicer Report - {period}"
    story: list[Any] = [
        Spacer(1, 1.6 * inch),
        text("Bramble Auto Finance LLC", REPORT_TITLE),
        text(f"Monthly Servicer Report: {period}", REPORT_HEAD),
        text(f"Issuer: {deal['borrower']['name']}", REPORT_BODY),
        text(f"Lender: {deal['lender']['name']}", REPORT_BODY),
        text(f"Collection Period end: {deal['tape']['cutoff_date']:%d %B %Y}", REPORT_BODY),
        PageBreak(),
        text("1. Collections", REPORT_HEAD),
        table([
            ["Item", "Amount (US$)"],
            ["Scheduled principal received", _usd(principal)],
            ["Interest received", _usd(interest)],
            ["Total collections", _usd(scheduled)],
        ], widths=[4.3, 2.0], total_row=True),
        Spacer(1, 0.2 * inch),
        text("Collections are shown on a cash basis. Amounts were swept to the Collection Account "
             "within two Business Days of receipt.", REPORT_BODY),
        PageBreak(),
        text("2. Charge-offs and recoveries", REPORT_HEAD),
        table([
            ["Item", period],
            ["Loans charged off in the month", f"{len(charged):,}"],
            ["Gross charge-offs (US$)", _usd(sum(row["charge_off_amount"] for row in charged))],
            ["Vehicles repossessed in the month", f"{len(repo):,}"],
            ["Recoveries (US$)", ""],
        ], widths=[4.3, 2.0]),
        PageBreak(),
        text("3. Delinquency at month end", REPORT_HEAD),
        *_strat(live, "Bucket", bucket, keep_order=True),
        PageBreak(),
        text("4. Delinquency trend", REPORT_HEAD),
        table([
            ["Collection Period", "60+ day ratio"],
            ["February 2026", f"{history['february_pct']:.2f}%"],
            ["March 2026", f"{history['march_pct']:.2f}%"],
            [period, f"{april_ratio:.2f}%"],
            ["Three-month average", f"{average:.2f}%"],
        ], widths=[4.3, 2.0], total_row=True),
        PageBreak(),
        text("5. Pool by state", REPORT_HEAD),
        *_strat(live, "State", lambda row: row["obligor_state"], top=24),
        PageBreak(),
        text("6. Pool by credit score", REPORT_HEAD),
        *_strat(live, "FICO at origination", band("fico", [500, 540, 580, 600, 640, 680, 720]),
                keep_order=True),
        Spacer(1, 0.25 * inch),
        text("7. Pool by original term", REPORT_HEAD),
        *_strat(live, "Months", lambda row: f"{row['original_term']:>3}", keep_order=True),
        PageBreak(),
        text("8. Pool by vehicle type and make", REPORT_HEAD),
        *_strat(live, "New or used", lambda row: row["vehicle_condition"]),
        Spacer(1, 0.25 * inch),
        *_strat(live, "Make", lambda row: row["vehicle_make"]),
        PageBreak(),
        text("9. Largest dealers", REPORT_HEAD),
        *_strat(live, "Dealer", lambda row: row["dealer_name"], top=20),
        Spacer(1, 0.2 * inch),
        text(f"Pool balance excluding charged-off loans: US${_usd(pool)}.", REPORT_BODY),
    ]
    build(path, story, head, head, SANS)


def financial_figures(deal: dict[str, Any]) -> dict[str, int]:
    f = deal["financials"]
    return {
        "tangible_net_worth": f["total_equity"] - f["goodwill"] - f["intangibles"]
        - f["related_party_receivables"],
        "adjusted_liabilities": f["total_liabilities"] - f["subordinated_debt"],
    }


NOTES = [
    ("Note 1. Organization", "Bramble Auto Finance LLC is a Delaware limited liability company "
     "that originates and services retail installment contracts for new and used vehicles through "
     "a network of franchised and independent dealers. The consolidated statements include its "
     "wholly owned special purpose subsidiaries."),
    ("Note 2. Basis of presentation", "The statements are prepared under US GAAP on an unaudited "
     "basis and reflect all adjustments that management considers necessary for a fair "
     "presentation. Results for the quarter do not indicate results for the full year."),
    ("Note 3. Finance receivables", "Finance receivables are carried at amortized cost, net of an "
     "allowance for credit losses. Interest accrues on the simple interest method and accrual "
     "stops when a contract is more than 90 days past due. Contracts are charged off when a "
     "vehicle is sold after repossession or when a contract reaches 120 days past due."),
    ("Note 4. Debt", "Debt consists of warehouse facilities secured by finance receivables, term "
     "asset-backed notes issued by consolidated special purpose subsidiaries, and subordinated "
     "notes held by the members' affiliates. The subordinated notes are unsecured and rank behind "
     "all senior obligations."),
    ("Note 5. Goodwill and intangibles", "Goodwill arose on the acquisition of a regional dealer "
     "finance platform. Intangible assets are dealer relationships amortized over ten years. No "
     "impairment was recorded in the quarter."),
    ("Note 6. Related parties", "Amounts due from affiliates represent advances to entities under "
     "common ownership, are unsecured, and carry no fixed repayment date."),
    ("Note 7. Commitments and contingencies", "The Company is party to routine litigation arising "
     "from its lending and collection activities. Management does not expect any such matter to "
     "have a material effect on the consolidated statements."),
    ("Note 8. Subsequent events", "The Company evaluated events through the date of issue. "
     "Amendment No. 1 to the warehouse facility with Calderwood Bank plc took effect on 1 March "
     "2026, within the quarter, and no other matters required disclosure."),
]


def build_financials(deal: dict[str, Any], path: Path) -> None:
    f = deal["financials"]

    def k(value: int) -> str:
        return f"({-value:,})" if value < 0 else f"{value:,}"

    restricted, other_assets = 2300, 1000
    assets = [
        ("Cash and cash equivalents", f["unrestricted_cash"]),
        ("Restricted cash", restricted),
        ("Finance receivables, net", f["receivables_net"]),
        ("Goodwill", f["goodwill"]),
        ("Intangible assets, net", f["intangibles"]),
        ("Due from affiliates", f["related_party_receivables"]),
        ("Other assets", other_assets),
    ]
    abs_notes, warehouse = 230000, 65000
    accrued = f["total_liabilities"] - abs_notes - warehouse - f["subordinated_debt"]
    liabilities = [
        ("Term asset-backed notes", abs_notes),
        ("Warehouse facilities", warehouse),
        ("Subordinated notes", f["subordinated_debt"]),
        ("Accrued and other liabilities", accrued),
    ]
    total_assets = sum(value for _, value in assets)
    if total_assets != f["total_liabilities"] + f["total_equity"]:
        raise ValueError("Balance sheet does not balance")

    income = [("Interest income", 21400), ("Interest expense", -8950),
              ("Provision for credit losses", -6100), ("Servicing and operating expense", -4820)]
    net_income = sum(value for _, value in income)
    opening_equity = f["total_equity"] - net_income
    cash_flows = [("Operating activities", 6200), ("Investing activities", -28400),
                  ("Financing activities", 25000)]
    opening_cash = f["unrestricted_cash"] - sum(value for _, value in cash_flows)

    widths = [4.3, 2.0]
    title = "Bramble Auto Finance LLC - Unaudited Consolidated Financial Statements"
    story: list[Any] = [
        Spacer(1, 1.6 * inch),
        text("Bramble Auto Finance LLC", REPORT_TITLE),
        text("Unaudited Consolidated Financial Statements", REPORT_HEAD),
        text(f"For the quarter ended {f['period_end']:%d %B %Y}", REPORT_BODY),
        text("All amounts in US$ thousands", REPORT_BODY),
        PageBreak(),
        text("Contents", REPORT_HEAD),
        *[text(line, REPORT_BODY) for line in (
            "Consolidated balance sheet", "Consolidated statement of income",
            "Consolidated statement of cash flows", "Consolidated statement of members' equity",
            "Notes to the consolidated financial statements")],
        PageBreak(),
        text("Consolidated balance sheet", REPORT_HEAD),
        table([["Assets", "31 Mar 2026"], *[[n, k(v)] for n, v in assets],
               ["Total assets", k(total_assets)]], widths=widths, total_row=True),
        Spacer(1, 0.25 * inch),
        table([["Liabilities", "31 Mar 2026"], *[[n, k(v)] for n, v in liabilities],
               ["Total liabilities", k(f["total_liabilities"])]], widths=widths, total_row=True),
        Spacer(1, 0.25 * inch),
        table([["Members' equity", "31 Mar 2026"],
               ["Total members' equity", k(f["total_equity"])]], widths=widths),
        PageBreak(),
        text("Consolidated statement of income", REPORT_HEAD),
        table([["Quarter ended", "31 Mar 2026"], *[[n, k(v)] for n, v in income],
               ["Net income", k(net_income)]], widths=widths, total_row=True),
        PageBreak(),
        text("Consolidated statement of cash flows", REPORT_HEAD),
        table([["Quarter ended", "31 Mar 2026"], ["Opening cash", k(opening_cash)],
               *[[n, k(v)] for n, v in cash_flows], ["Closing cash", k(f["unrestricted_cash"])]],
              widths=widths, total_row=True),
        PageBreak(),
        text("Consolidated statement of members' equity", REPORT_HEAD),
        table([["Quarter ended", "31 Mar 2026"], ["Opening members' equity", k(opening_equity)],
               ["Net income", k(net_income)], ["Closing members' equity", k(f["total_equity"])]],
              widths=widths, total_row=True),
    ]
    for heading, body in NOTES:
        story += [PageBreak(), text(heading, REPORT_HEAD), text(body, REPORT_BODY)]
    build(path, story, title, title, SANS)
