"""The standard loan model for facilities onboarded on the platform, and the monthly figures
worked out from it.

A facility's tape is mapped to these fields and its statuses to the standard statuses below, so
one rule format and one set of monitoring checks serve every deal type. Money is whole cents and
percentages are Decimals rounded half up to two places. Nothing here reads a file.
"""

from dataclasses import dataclass
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any

from engine.run import Loan, to_cents

# field -> (type, what it holds). Types: id, text, date, money, rate, int.
FIELDS: dict[str, tuple[str, str]] = {
    "loan_id": ("id", "Unique loan or account number"),
    "obligor_id": ("text", "Borrower or obligor identifier"),
    "origination_date": ("date", "Date the loan was made"),
    "maturity_date": ("date", "Final scheduled repayment date"),
    "original_balance": ("money", "Principal at origination"),
    "current_balance": ("money", "Outstanding principal at the reporting date"),
    "apr": ("rate", "Interest rate, per cent a year"),
    "original_term": ("int", "Original term in months"),
    "remaining_term": ("int", "Remaining term in months"),
    "days_past_due": ("int", "Days past due or in arrears"),
    "status": ("text", "Loan status, mapped to a standard status"),
    "credit_score": ("int", "Credit score (for example FICO) at origination"),
    "risk_grade": ("int", "Internal risk grade"),
    "obligor_state": ("text", "Obligor's US state, two letters"),
    "region": ("text", "Region"),
    "sector": ("text", "Industry sector"),
    "product": ("text", "Product or purpose category"),
    "merchant": ("text", "Merchant or originating dealer"),
    "collateral_type": ("text", "Collateral type"),
}
REQUIRED = ("loan_id", "current_balance", "status", "days_past_due")
STATUSES = ("performing", "arrears", "defaulted", "charged_off", "paid_off")
CLOSED = frozenset({"charged_off", "paid_off"})


class CoercionError(ValueError):
    """A mapped value could not be read as its field's type."""


def parse_date(raw: str) -> date | None:
    text = str(raw).strip()
    for pattern in ("%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(text, pattern).date()
        except ValueError:
            continue
    return None


def number(raw: Any) -> Decimal | None:
    text = str(raw).strip().replace(",", "").replace("$", "").rstrip("%")
    if not text:
        return None
    try:
        return Decimal(text)
    except InvalidOperation:
        return None


def is_type(raw: Any, kind: str) -> bool:
    """Whether a non-blank value reads as the type. Blanks are a missing-data question."""
    if str(raw).strip() == "":
        return True
    if kind in ("money", "rate"):
        return number(raw) is not None
    if kind == "int":
        value = number(raw)
        return value is not None and value == value.to_integral_value()
    if kind == "date":
        return parse_date(raw) is not None
    return True


def coerce(row: dict[str, Any], status_map: dict[str, str]) -> Loan:
    """One mapped row of strings to typed values; status mapped to the standard set."""
    loan: Loan = {}
    for name, raw in row.items():
        kind = FIELDS.get(name, ("text", ""))[0]
        text = str(raw).strip()
        if name == "status":
            loan[name] = status_map.get(text, text)
            continue
        if kind in ("id", "text"):
            loan[name] = text
            continue
        if text == "":
            loan[name] = None
            continue
        if kind == "money":
            value = number(text)
            if value is None:
                raise CoercionError(f"{name}: {text!r}")
            loan[name] = to_cents(value)
        elif kind == "rate":
            value = number(text)
            if value is None:
                raise CoercionError(f"{name}: {text!r}")
            loan[name] = value
        elif kind == "int":
            value = number(text)
            if value is None:
                raise CoercionError(f"{name}: {text!r}")
            loan[name] = int(value)
        elif kind == "date":
            parsed = parse_date(text)
            if parsed is None:
                raise CoercionError(f"{name}: {text!r}")
            loan[name] = parsed
    return loan


def pct(part: int | Decimal, whole: int | Decimal) -> Decimal:
    if not whole:
        return Decimal(0)
    return (Decimal(part) / Decimal(whole) * 100).quantize(Decimal("0.01"), ROUND_HALF_UP)


def live(loans: list[Loan]) -> list[Loan]:
    return [loan for loan in loans if loan.get("status") not in CLOSED]


def pool_cents(loans: list[Loan]) -> int:
    return sum(loan["current_balance"] or 0 for loan in live(loans))


def delinquency_ratio(loans: list[Loan], days: int) -> Decimal:
    """Balance at least `days` past due over the balance of loans not charged off or repaid."""
    pool = live(loans)
    late = sum(loan["current_balance"] or 0 for loan in pool
               if (loan.get("days_past_due") or 0) >= days)
    return pct(late, sum(loan["current_balance"] or 0 for loan in pool))


def weighted(loans: list[Loan], name: str) -> Decimal | None:
    pool = [loan for loan in live(loans) if loan.get(name) is not None]
    weight = sum(loan["current_balance"] or 0 for loan in pool)
    if not weight:
        return None
    total = sum(Decimal(loan[name]) * (loan["current_balance"] or 0) for loan in pool)
    return (total / weight).quantize(Decimal("0.01"), ROUND_HALF_UP)


def metrics(loans: list[Loan]) -> dict[str, Decimal]:
    """Pool figures a period is compared on."""
    result = {"pool_balance": Decimal(pool_cents(loans)) / 100,
              "live_loans": Decimal(len(live(loans)))}
    for name in ("apr", "credit_score", "risk_grade", "remaining_term"):
        value = weighted(loans, name)
        if value is not None:
            result[f"weighted_{name}"] = value
    return result


@dataclass(frozen=True)
class RollForward:
    opening_cents: int
    new_cents: int
    new_loans: int
    collections_cents: int | None
    charge_offs_cents: int
    charged_off_loans: int
    paid_off_loans: int
    expected_cents: int | None
    actual_cents: int
    gap_cents: int | None
    missing_loan_ids: tuple[str, ...]
    missing_cents: int


def roll_forward(prior: list[Loan], current: list[Loan],
                 collections_cents: int | None) -> RollForward:
    """Opening pool plus new loans, less principal collections and charge-offs, against the new
    tape. A charge-off is the prior balance of a loan now charged off. A loan in last period's
    pool that the new tape does not list at all is missing. Without the servicer's collections
    figure the expected balance cannot be worked out, and the gap is left open."""
    before = {loan["loan_id"]: loan for loan in live(prior)}
    listed = {loan["loan_id"] for loan in current}
    new = [loan for loan in live(current) if loan["loan_id"] not in before]
    charged = [loan for loan in current
               if loan.get("status") == "charged_off" and loan["loan_id"] in before]
    paid = [loan for loan in current
            if loan.get("status") == "paid_off" and loan["loan_id"] in before]
    opening = sum(loan["current_balance"] or 0 for loan in before.values())
    additions = sum(loan["current_balance"] or 0 for loan in new)
    charge_offs = sum(before[loan["loan_id"]]["current_balance"] or 0 for loan in charged)
    actual = pool_cents(current)
    missing = tuple(sorted(set(before) - listed))
    expected = (None if collections_cents is None
                else opening + additions - collections_cents - charge_offs)
    return RollForward(opening, additions, len(new), collections_cents, charge_offs, len(charged),
                       len(paid), expected, actual,
                       None if expected is None else expected - actual, missing,
                       sum(before[i]["current_balance"] or 0 for i in missing))


def duplicate_ids(rows: list[dict[str, Any]]) -> dict[str, list[int]]:
    """Loan ids listed more than once, with their one-based row numbers."""
    seen: dict[str, list[int]] = {}
    for index, row in enumerate(rows, start=1):
        seen.setdefault(str(row.get("loan_id", "")), []).append(index)
    return {key: lines for key, lines in seen.items() if len(lines) > 1}
