"""Monthly monitoring checks: reconciliation, effective terms, triggers, NAV tests and collateral.

Every check here is deterministic. Money is held as whole cents and percentages as Decimals
rounded half up to two places, as the agreements state them. Inputs are mapped tape rows and
figures already extracted from documents; nothing here reads a file.
"""

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

Row = dict[str, Any]

# Loans that have left the pool. A tape still lists them in the month they leave.
CLOSED = frozenset({"CHARGED_OFF", "PAID_OFF", "REPURCHASED"})


def pct(part: Decimal | int, whole: Decimal | int, places: str = "0.01") -> Decimal:
    if not whole:
        return Decimal(0)
    return (Decimal(part) / Decimal(whole) * 100).quantize(Decimal(places), ROUND_HALF_UP)


def pool_cents(rows: list[Row]) -> int:
    return sum(row["current_balance"] for row in rows if row["status"] not in CLOSED)


# Reconciliation


@dataclass(frozen=True)
class RollForward:
    opening_cents: int
    additions_cents: int
    new_loans: int
    collections_cents: int
    charge_offs_cents: int
    expected_cents: int
    actual_cents: int
    gap_cents: int
    missing_loan_ids: tuple[str, ...]
    missing_last_balance_cents: int


def roll_forward(previous: list[Row], current: list[Row], collections_cents: int) -> RollForward:
    """Opening balance plus new loans, less collections and charge-offs, against the new tape.

    Collections come from the servicer report; everything else comes from the two tapes. Any
    loan in last month's pool that the new tape does not list at all, not even as paid off or
    charged off, is missing.
    """
    before = {row["loan_id"]: row for row in previous if row["status"] not in CLOSED}
    listed = {row["loan_id"] for row in current}
    new = [row for row in current if row["loan_id"] not in before and row["status"] not in CLOSED]
    charged = [row for row in current
               if row["status"] == "CHARGED_OFF" and row["loan_id"] in before]
    opening = sum(row["current_balance"] for row in before.values())
    additions = sum(row["current_balance"] for row in new)
    charge_offs = sum(row["charge_off_amount"] or 0 for row in charged)
    expected = opening + additions - collections_cents - charge_offs
    actual = pool_cents(current)
    missing = sorted(set(before) - listed)
    return RollForward(opening, additions, len(new), collections_cents, charge_offs, expected,
                       actual, expected - actual, tuple(missing),
                       sum(before[loan_id]["current_balance"] for loan_id in missing))


@dataclass(frozen=True)
class ChargeOffCheck:
    tape_cents: int
    report_cents: int
    difference_cents: int
    only_in_report: tuple[str, ...]
    only_on_tape: tuple[str, ...]


def charge_offs(current: list[Row], reported: dict[str, int]) -> ChargeOffCheck:
    """The servicer report's charge-off schedule against the tape, loan by loan."""
    on_tape = {row["loan_id"]: row["charge_off_amount"] or 0 for row in current
               if row["status"] == "CHARGED_OFF"}
    tape, report = sum(on_tape.values()), sum(reported.values())
    return ChargeOffCheck(tape, report, report - tape,
                          tuple(sorted(set(reported) - set(on_tape))),
                          tuple(sorted(set(on_tape) - set(reported))))


# Effective-dated terms


@dataclass(frozen=True)
class TermVersion:
    label: str
    effective_from: date
    values: dict[str, Any]
    source: str


def in_force(versions: list[TermVersion], period_end: date) -> TermVersion:
    """The version that governs a reporting period: the latest one effective by its last day."""
    eligible = [v for v in versions if v.effective_from <= period_end]
    if not eligible:
        raise ValueError(f"No terms are in force on {period_end}")
    return max(eligible, key=lambda version: version.effective_from)


# Triggers and covenants


@dataclass(frozen=True)
class RollingTrigger:
    monthly: tuple[tuple[str, Decimal], ...]
    average: Decimal
    limit: Decimal
    direction: str  # "max": breached above the limit. "min": breached below it.
    breached: bool
    headroom: Decimal
    next_month_breaches_beyond: Decimal | None
    early_warning: bool


def rolling_trigger(monthly: list[tuple[str, Decimal]], limit: Decimal, direction: str = "max",
                    window: int = 3, warning_band: Decimal = Decimal("0.5")) -> RollingTrigger:
    """A trigger tested on the average of the last `window` months, with the value next month
    must pass for the average to breach. An early warning is raised inside `warning_band`."""
    recent = [value for _, value in monthly[-window:]]
    average = (sum(recent) / len(recent)).quantize(Decimal("0.01"), ROUND_HALF_UP)
    breached = average > limit if direction == "max" else average < limit
    headroom = (limit - average) if direction == "max" else (average - limit)
    beyond = None
    if len(recent) == window:
        beyond = (limit * window - sum(recent[1:])).quantize(Decimal("0.01"), ROUND_HALF_UP)
    return RollingTrigger(tuple(monthly), average, limit, direction, breached, headroom, beyond,
                          not breached and headroom <= warning_band)


def what_if(trigger: RollingTrigger, next_value: Decimal, label: str) -> RollingTrigger:
    """The trigger as it would stand after one more month at `next_value`."""
    return rolling_trigger([*trigger.monthly, (label, next_value)], trigger.limit,
                           trigger.direction)


@dataclass(frozen=True)
class Leverage:
    total_liabilities: int
    carve_out: int
    added_liabilities: int
    tangible_net_worth: int
    ratio: Decimal
    limit: Decimal
    passed: bool


def leverage(total_liabilities: int, tangible_net_worth: int, subordinated_debt: int,
             carve_out_cap: int, limit: Decimal, added_liabilities: int = 0) -> Leverage:
    """The Leverage Ratio with the 6.12(c) carve-out, optionally counting liabilities the
    borrower left out, such as an off-balance-sheet guarantee."""
    carve = min(subordinated_debt, carve_out_cap)
    ratio = (Decimal(total_liabilities + added_liabilities - carve)
             / Decimal(tangible_net_worth + carve)).quantize(Decimal("0.01"), ROUND_HALF_UP)
    return Leverage(total_liabilities, carve, added_liabilities, tangible_net_worth, ratio, limit,
                    ratio <= limit)


# NAV facilities


@dataclass(frozen=True)
class LoanToValue:
    drawn_cents: int
    nav_cents: int
    adjustments_cents: int
    ratio_pct: Decimal
    limit_pct: Decimal
    passed: bool


def loan_to_value(drawn_cents: int, nav_cents: int, limit_pct: Decimal,
                  adjustments_cents: int = 0) -> LoanToValue:
    nav = nav_cents + adjustments_cents
    ratio = pct(drawn_cents, nav, "0.1")
    return LoanToValue(drawn_cents, nav_cents, adjustments_cents, ratio, limit_pct,
                       ratio <= limit_pct)


@dataclass(frozen=True)
class StaleValuation:
    name: str
    valued: date
    age_days: int


def stale_valuations(positions: list[dict[str, Any]], calculation_date: date,
                     max_age_days: int) -> tuple[StaleValuation, ...]:
    return tuple(
        StaleValuation(p["name"], p["valued"], (calculation_date - p["valued"]).days)
        for p in positions if (calculation_date - p["valued"]).days > max_age_days
    )


@dataclass(frozen=True)
class PositionConcentration:
    largest_name: str
    largest_pct: Decimal
    top_five_pct: Decimal
    largest_limit_pct: Decimal
    top_five_limit_pct: Decimal
    passed: bool


def position_concentration(positions: list[dict[str, Any]], nav_cents: int,
                           largest_limit: Decimal, top_five_limit: Decimal
                           ) -> PositionConcentration:
    ordered = sorted(positions, key=lambda p: -p["value_cents"])
    largest = pct(ordered[0]["value_cents"], nav_cents, "0.1")
    top = pct(sum(p["value_cents"] for p in ordered[:5]), nav_cents, "0.1")
    return PositionConcentration(ordered[0]["name"], largest, top, largest_limit, top_five_limit,
                                 largest <= largest_limit and top <= top_five_limit)


# Collateral


@dataclass(frozen=True)
class SharedCollateral:
    vin: str
    holdings: tuple[tuple[str, str], ...]  # (facility, loan_id)


def duplicate_collateral(tapes: dict[str, list[Row]]) -> tuple[tuple[SharedCollateral, ...],
                                                               tuple[SharedCollateral, ...]]:
    """VINs pledged twice within one facility's pool, and across one lender's facilities."""
    seen: defaultdict[str, list[tuple[str, str]]] = defaultdict(list)
    for facility, rows in tapes.items():
        for row in rows:
            if row["status"] not in CLOSED:
                seen[row["vin"]].append((facility, row["loan_id"]))
    within, across = [], []
    for vin, holdings in sorted(seen.items()):
        if len(holdings) < 2:
            continue
        shared = SharedCollateral(vin, tuple(holdings))
        (across if len({facility for facility, _ in holdings}) > 1 else within).append(shared)
    return tuple(within), tuple(across)


# Tolerances


@dataclass(frozen=True)
class Tolerance:
    within: bool
    difference: Decimal
    tolerance: Decimal


def within_tolerance(reported: Decimal, computed: Decimal, tolerance: Decimal) -> Tolerance:
    difference = reported - computed
    return Tolerance(abs(difference) <= tolerance, difference, tolerance)


@dataclass(frozen=True)
class SeasonalCheck:
    change: Decimal
    last_year_change: Decimal
    within: bool


def seasonal(this_month: int, last_month: int, last_year_this: int,
             last_year_last: int) -> SeasonalCheck:
    """A month-on-month dip counts as seasonal if it is no deeper than the same month last year."""
    change = (Decimal(this_month) / Decimal(last_month) - 1).quantize(Decimal("0.0001"))
    last = (Decimal(last_year_this) / Decimal(last_year_last) - 1).quantize(Decimal("0.0001"))
    return SeasonalCheck(change, last, change >= last)
