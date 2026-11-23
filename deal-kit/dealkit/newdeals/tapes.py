"""Loan tapes for the two test deals: an onboarding tape and the next month's.

Rows are held with internal names and plain numbers; each deal writes them under its own
column names and file format, so the pipeline has to map an unfamiliar layout.
"""

import csv
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any

import numpy as np
from openpyxl import Workbook

from dealkit.workbooks import _save_stable

Row = dict[str, Any]


def _money(value: float) -> float:
    return float(Decimal(str(value)).quantize(Decimal("0.01"), ROUND_HALF_UP))


def _months_between(start: date, end: date) -> int:
    return (end.year - start.year) * 12 + end.month - start.month


def _add_months(start: date, months: int) -> date:
    year, month = divmod(start.month - 1 + months, 12)
    day = min(start.day, 28)
    return date(start.year + year, month + 1, day)


def _balance(original: float, apr: float, term: int, paid: int) -> float:
    """Scheduled principal outstanding after `paid` level payments."""
    rate = apr / 100 / 12
    if rate == 0:
        return original * (term - paid) / term
    payment = original * rate / (1 - (1 + rate) ** -term)
    return original * (1 + rate) ** paid - payment * ((1 + rate) ** paid - 1) / rate


def _choice(rng: np.random.Generator, options: list[tuple[str, float]]) -> str:
    names = [name for name, _ in options]
    weights = np.array([weight for _, weight in options], dtype=float)
    return str(names[int(rng.choice(len(names), p=weights / weights.sum()))])


# Consumer instalment: point-of-sale loans for household purchases.

STATES = [("CA", 23), ("TX", 13), ("FL", 11), ("IL", 7), ("GA", 6), ("OH", 6), ("PA", 5),
          ("NC", 5), ("AZ", 4), ("MI", 4), ("NY", 3), ("WA", 4), ("CO", 3), ("NJ", 3),
          ("VT", 1), ("TN", 2)]
PRODUCTS = [("Furniture", 30), ("Electronics", 22), ("Home Improvement", 24), ("Medical", 12),
            ("Power Sports", 12)]
MERCHANTS = {
    "Furniture": ["Oakline Home", "Cedar & Co Furnishings", "Brightroom Living"],
    "Electronics": ["Voltage Hub", "ClearSignal Electronics"],
    "Home Improvement": ["Summit Roofing", "Evergreen Windows", "Northgate Solar"],
    "Medical": ["Lumen Dental Group", "ClearView Vision"],
    "Power Sports": ["Ridgeway Powersports", "Tidewater Marine"],
}
CONSUMER_COLUMNS = {
    "loan_id": "AccountNo", "origination_date": "OriginationDt", "maturity_date": "MaturityDt",
    "original_balance": "OrigPrincipal", "current_balance": "CurrPrincipal", "apr": "APR_Pct",
    "original_term": "TermMonths", "remaining_term": "RemTerm",
    "days_past_due": "DaysDelinquent", "status": "AcctStatus", "credit_score": "FICO_Orig",
    "obligor_state": "BorrowerState", "product": "ProductCategory", "merchant": "MerchantName",
}


def consumer_tape(deal: dict[str, Any]) -> list[Row]:
    rng = np.random.default_rng(deal["seed"])
    cutoff = deal["tape"]["cutoff"]
    rows = []
    for index in range(deal["tape"]["loans"]):
        product = _choice(rng, PRODUCTS)
        term = int(rng.choice([24, 36, 48, 60, 72], p=[0.15, 0.3, 0.27, 0.23, 0.05]))
        original = _money(float(rng.uniform(2500, 30000)))
        if index % 233 == 17:
            original = _money(float(rng.uniform(52000, 58000)))  # above the balance limit
        apr = round(float(rng.uniform(7.99, 33.99)), 2)
        if index % 311 == 5:
            apr = 36.49
        seasoned = int(rng.integers(1, min(term - 2, 30)))
        start = _add_months(cutoff, -seasoned)
        current = _money(_balance(original, apr, term, seasoned))
        score = int(np.clip(rng.normal(705, 48), 560, 830))
        dpd = 0
        status = "CURRENT"
        draw = float(rng.random())
        if draw < 0.045:
            dpd = int(rng.choice([35, 45, 62, 75, 95, 120]))
            status = "DELINQUENT"
        elif draw < 0.11:
            dpd = int(rng.choice([5, 10, 15, 22, 28]))
            status = "DELINQUENT"
        elif draw < 0.118:
            status = "CHARGED_OFF"
            dpd = 150
        rows.append({
            "loan_id": f"HCR{100000 + index * 7}",
            "origination_date": start,
            "maturity_date": _add_months(start, term),
            "original_balance": original,
            "current_balance": current,
            "apr": apr,
            "original_term": term,
            "remaining_term": term - seasoned,
            "days_past_due": dpd,
            "status": status,
            "credit_score": score,
            "obligor_state": _choice(rng, STATES),
            "product": product,
            "merchant": str(rng.choice(MERCHANTS[product])),
        })
    return rows


def _next_month(rows: list[Row], later: dict[str, Any], rng: np.random.Generator,
                make_new: Any, paid_status: str, off_status: str, arrears_status: str,
                performing: str) -> tuple[list[Row], dict[str, Any]]:
    """Roll a tape forward one month: amortise, pay off, charge off, add new loans and drop
    one loan from the file entirely, so the roll-forward has a gap to find."""
    live = [row for row in rows if row["status"] not in (paid_status, off_status)]
    order = rng.permutation(len(live))
    paid = {live[int(i)]["loan_id"] for i in order[: later["paid_off"]]}
    off = {live[int(i)]["loan_id"] for i in order[later["paid_off"]:
                                                   later["paid_off"] + later["charged_off"]]}
    dropped = live[int(order[later["paid_off"] + later["charged_off"]])]["loan_id"]
    out: list[Row] = []
    collections = 0.0
    charge_offs = 0.0
    for row in rows:
        if row["status"] in (paid_status, off_status) or row["loan_id"] == dropped:
            continue
        new = dict(row)
        if row["loan_id"] in paid:
            collections += row["current_balance"]
            new.update(current_balance=0.0, status=paid_status, days_past_due=0,
                       remaining_term=0)
        elif row["loan_id"] in off:
            charge_offs += row["current_balance"]
            new.update(current_balance=0.0, status=off_status, days_past_due=150)
        else:
            term = row["original_term"]
            paid_so_far = term - row["remaining_term"] + 1
            scheduled = _money(_balance(row["original_balance"], row["apr"], term,
                                        min(paid_so_far, term)))
            if row["days_past_due"] >= 30 or float(rng.random()) < 0.035:
                # Missed this month: balance unchanged, a month further behind.
                new["days_past_due"] = row["days_past_due"] + 30
                new["status"] = arrears_status
            else:
                collections += row["current_balance"] - scheduled
                new["current_balance"] = scheduled
                new["remaining_term"] = max(0, row["remaining_term"] - 1)
                new["days_past_due"] = 0
                new["status"] = performing
        out.append(new)
    fresh = [make_new(i) for i in range(later["new_loans"])]
    facts = {
        "paid_off": sorted(paid), "charged_off": sorted(off), "dropped": dropped,
        "principal_collections": _money(collections), "charge_offs": _money(charge_offs),
        "new_loans": [row["loan_id"] for row in fresh],
        "new_balance": _money(sum(row["current_balance"] for row in fresh)),
    }
    return out + fresh, facts


def consumer_later(deal: dict[str, Any], rows: list[Row]) -> tuple[list[Row], dict[str, Any]]:
    later = deal["later"]
    rng = np.random.default_rng(deal["seed"] + 1)
    cutoff = later["cutoff"]

    def make_new(index: int) -> Row:
        product = _choice(rng, PRODUCTS)
        term = int(rng.choice([24, 36, 48, 60]))
        original = _money(float(rng.uniform(3000, 28000)))
        return {
            "loan_id": f"HCR{200000 + index * 7}", "origination_date": _add_months(cutoff, -1),
            "maturity_date": _add_months(cutoff, term - 1), "original_balance": original,
            "current_balance": original, "apr": round(float(rng.uniform(8.99, 29.99)), 2),
            "original_term": term, "remaining_term": term, "days_past_due": 0,
            "status": "CURRENT", "credit_score": int(np.clip(rng.normal(710, 40), 600, 830)),
            "obligor_state": _choice(rng, STATES), "product": product,
            "merchant": str(rng.choice(MERCHANTS[product])),
        }

    out, facts = _next_month(rows, later, rng, make_new, "PAID_OFF", "CHARGED_OFF",
                             "DELINQUENT", "CURRENT")
    # One account appears twice with different balances: a blocking duplicate.
    live = [row for row in out if row["status"] == "CURRENT"]
    twin = dict(live[len(live) // 2])
    twin["current_balance"] = _money(twin["current_balance"] * 0.5)
    out.append(twin)
    facts["duplicate"] = twin["loan_id"]
    return out, facts


def write_consumer_csv(rows: list[Row], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(CONSUMER_COLUMNS.values())
        for row in rows:
            cells = []
            for name in CONSUMER_COLUMNS:
                value = row[name]
                if isinstance(value, date):
                    value = f"{value:%m/%d/%Y}"
                elif isinstance(value, float):
                    value = f"{value:.2f}"
                cells.append(value)
            writer.writerow(cells)


# SME loans: amortising term loans to small businesses.

SECTORS = [("Construction", 16), ("Healthcare", 14), ("Retail", 13), ("Manufacturing", 15),
           ("Transport and Logistics", 12), ("Hospitality", 10), ("Professional Services", 14),
           ("Gaming", 2), ("Agriculture", 4)]
REGIONS = [("Southwest", 34), ("Southeast", 22), ("Midwest", 18), ("Northeast", 16),
           ("West", 10)]
SME_COLUMNS = {
    "loan_id": "Facility Ref", "obligor_id": "Borrower ID", "origination_date": "Drawdown Date",
    "maturity_date": "Final Repayment", "original_balance": "Original Principal",
    "current_balance": "Outstanding Principal", "apr": "Rate (%)",
    "original_term": "Term (m)", "remaining_term": "Remaining (m)",
    "days_past_due": "Arrears Days", "status": "Loan Status", "risk_grade": "Risk Grade",
    "sector": "Sector", "region": "Region",
}


def sme_tape(deal: dict[str, Any]) -> list[Row]:
    rng = np.random.default_rng(deal["seed"])
    cutoff = deal["tape"]["cutoff"]
    rows = []
    for index in range(deal["tape"]["loans"]):
        term = int(rng.choice([36, 48, 60, 84, 96, 120], p=[0.2, 0.2, 0.3, 0.18, 0.07, 0.05]))
        original = _money(float(rng.lognormal(11.9, 0.6)))
        original = min(max(original, 25000.0), 950000.0)
        seasoned = int(rng.integers(2, min(term - 3, 40)))
        start = _add_months(cutoff, -seasoned)
        apr = round(float(rng.uniform(7.25, 15.75)), 2)
        current = _money(_balance(original, apr, term, seasoned))
        grade = int(np.clip(round(rng.normal(4.6, 1.5)), 1, 9))
        dpd, status = 0, "PERFORMING"
        draw = float(rng.random())
        if draw < 0.06:
            dpd = int(rng.choice([31, 45, 61, 92]))
            status = "ARREARS"
        elif draw < 0.10:
            dpd = int(rng.choice([7, 14, 21, 28]))
            status = "ARREARS"
        elif draw < 0.11:
            dpd, status = 120, "DEFAULT"
        # A few borrowers hold several loans; one holds enough to pass the obligor limit.
        obligor = f"B{10000 + index}"
        if index % 9 == 0:
            obligor = f"B{10000 + index - 9 * int(rng.integers(0, 3))}" if index > 18 else obligor
        if index % 37 == 3:
            obligor = "B19001"
        rows.append({
            "loan_id": f"FSF-{20000 + index * 3:06d}", "obligor_id": obligor,
            "origination_date": start, "maturity_date": _add_months(start, term),
            "original_balance": original, "current_balance": current, "apr": apr,
            "original_term": term, "remaining_term": term - seasoned, "days_past_due": dpd,
            "status": status, "risk_grade": grade, "sector": _choice(rng, SECTORS),
            "region": _choice(rng, REGIONS),
        })
    return rows


def sme_later(deal: dict[str, Any], rows: list[Row]) -> tuple[list[Row], dict[str, Any]]:
    later = deal["later"]
    rng = np.random.default_rng(deal["seed"] + 1)
    cutoff = later["cutoff"]

    def make_new(index: int) -> Row:
        term = int(rng.choice([36, 48, 60, 84]))
        original = _money(min(max(float(rng.lognormal(11.8, 0.5)), 30000.0), 700000.0))
        return {
            "loan_id": f"FSF-{40000 + index * 3:06d}", "obligor_id": f"B{30000 + index}",
            "origination_date": _add_months(cutoff, -1),
            "maturity_date": _add_months(cutoff, term - 1), "original_balance": original,
            "current_balance": original, "apr": round(float(rng.uniform(7.5, 14.5)), 2),
            "original_term": term, "remaining_term": term, "days_past_due": 0,
            "status": "PERFORMING", "risk_grade": int(rng.integers(2, 7)),
            "sector": _choice(rng, [s for s in SECTORS if s[0] != "Gaming"]),
            "region": _choice(rng, REGIONS),
        }

    return _next_month(rows, later, rng, make_new, "REPAID", "WRITTEN_OFF", "ARREARS",
                       "PERFORMING")


COLLATERAL = ["Equipment", "Real estate", "Receivables", "Unsecured", "Vehicles"]


def write_sme_xlsx(rows: list[Row], path: Path, renamed: dict[str, str] | None = None,
                   added: str | None = None, seed: int = 0) -> None:
    renamed = renamed or {}
    book = Workbook()
    sheet = book.active
    sheet.title = "Loans"
    headers = [renamed.get(name, name) for name in SME_COLUMNS.values()]
    if added:
        headers.append(added)
    sheet.append(headers)
    rng = np.random.default_rng(seed)
    for row in rows:
        cells: list[Any] = []
        for name in SME_COLUMNS:
            value = row[name]
            cells.append(f"{value:%Y-%m-%d}" if isinstance(value, date) else value)
        if added:
            cells.append(COLLATERAL[int(rng.integers(0, len(COLLATERAL)))])
        sheet.append(cells)
    _save_stable(book, path)


def delinquency_pct(rows: list[Row], days: int, closed: tuple[str, ...]) -> float:
    live = [row for row in rows if row["status"] not in closed]
    pool = sum(row["current_balance"] for row in live)
    late = sum(row["current_balance"] for row in live if row["days_past_due"] >= days)
    return round(late / pool * 100, 2) if pool else 0.0


def first_business_day_after(day: date) -> date:
    day += timedelta(days=1)
    while day.weekday() >= 5:
        day += timedelta(days=1)
    return day


__all__ = ["consumer_tape", "consumer_later", "sme_tape", "sme_later", "write_consumer_csv",
           "write_sme_xlsx", "delinquency_pct", "_months_between", "first_business_day_after"]
