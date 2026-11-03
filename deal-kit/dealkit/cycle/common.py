"""Shared pieces of the cycle kit: loading cycle.yaml and rolling a loan tape forward a month.

A roll keeps the pool's arithmetic exact, so a roll-forward always closes: opening balance plus
new loans, less principal collected and charge-offs, equals the closing balance.
"""

import csv
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import yaml

from dealkit.config import OUTPUT_DIR, ROOT
from dealkit.tape import ZIP3_RANGES, _add_months, _balance, _base_row, _format_date

CYCLE_FILE = ROOT / "cycle.yaml"
CYCLE_DIR = OUTPUT_DIR / "cycle"
CYCLE_KEY_DIR = OUTPUT_DIR / "cycle-key"

# Statuses of loans that have left the pool. A tape still lists them in the month they leave.
CLOSED = ("CHARGED_OFF", "PAID_OFF", "REPURCHASED")


def load_cycle() -> dict[str, Any]:
    return yaml.safe_load(CYCLE_FILE.read_text(encoding="utf-8"))


def live(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Pool receivables: every loan still in the pool, as the roll-forward counts them."""
    return [row for row in rows if row["status"] not in CLOSED]


def pool_balance(rows: list[dict[str, Any]]) -> float:
    return round(sum(row["current_balance"] for row in live(rows)), 2)


def delinquency_ratio(rows: list[dict[str, Any]]) -> float:
    """60+ day balance over pool balance, without charged-off loans, as both agreements say."""
    pool = live(rows)
    late = sum(row["current_balance"] for row in pool if row["days_past_due"] >= 60)
    return round(late / sum(row["current_balance"] for row in pool) * 100, 2)


def pick_total(
    rng: np.random.Generator,
    candidates: list[dict[str, Any]],
    count: int,
    target: float,
    tolerance: float,
) -> list[dict[str, Any]]:
    """Draw `count` loans whose balances total `target`, within `tolerance`."""
    balances = np.array([row["current_balance"] for row in candidates])
    chosen = list(rng.choice(len(candidates), size=count, replace=False))
    for _ in range(5000):
        gap = target - balances[chosen].sum()
        if abs(gap) <= tolerance:
            return [candidates[i] for i in sorted(chosen)]
        # Swap one chosen loan for an outside loan, moving the total as close to target as it can.
        outside = np.setdiff1d(np.arange(len(candidates)), chosen)
        slot = int(rng.integers(0, count))
        wanted = balances[chosen[slot]] + gap
        best = outside[np.argmin(np.abs(balances[outside] - wanted))]
        if abs(balances[best] - wanted) < abs(gap):
            chosen[slot] = int(best)
    raise ValueError(f"No {count} loans total {target:,.2f}")


@dataclass
class Roll:
    """One month's movement in a pool, from the servicer's side."""

    rows: list[dict[str, Any]]
    principal_collected: float = 0.0
    interest_collected: float = 0.0
    payoffs: list[str] = field(default_factory=list)
    charged_off: list[str] = field(default_factory=list)
    new_loans: list[str] = field(default_factory=list)


def _due_dates(row: dict[str, Any], cutoff: date) -> None:
    due = date(cutoff.year, cutoff.month, min(row["first_payment_date"].day, 28))
    if due > cutoff:
        due = _add_months(due, -1)
    if row["days_past_due"]:
        row["next_due_date"] = cutoff - timedelta(days=row["days_past_due"])
        row["last_payment_date"] = _add_months(row["next_due_date"], -1)
    else:
        row["last_payment_date"] = due
        row["next_due_date"] = _add_months(due, 1)


def new_loan(
    rng: np.random.Generator,
    loan_id: str,
    cutoff: date,
    dealers: list[str],
    mean_balance: float,
    servicer_code: str,
) -> dict[str, Any]:
    """A loan bought into the pool this month, with its first payment made."""
    weights = np.full(len(dealers), 1 / len(dealers))
    row = _base_row(rng, 0, cutoff, dealers, weights, mean_balance)
    first_payment = date(cutoff.year, cutoff.month, int(rng.integers(1, 28)))
    origination = first_payment - timedelta(days=int(rng.integers(30, 46)))
    term = row["original_term"]
    current = _balance(row["original_balance"], row["apr"], row["monthly_payment"], 1)
    low, high = ZIP3_RANGES.get(row["obligor_state"], (100, 999))
    row.update(
        loan_id=loan_id,
        origination_date=origination,
        first_payment_date=first_payment,
        maturity_date=_add_months(first_payment, term - 1),
        payments_made=1,
        remaining_term=term - 1,
        current_balance=round(current, 2),
        days_past_due=0,
        servicer_code=servicer_code,
        cutoff_date=cutoff,
        obligor_zip3=f"{int(rng.integers(low, high + 1)):03d}",
        raw_origination_date=origination.strftime("%m/%d/%Y"),
    )
    if row["vehicle_condition"] == "NEW":
        row["model_year"] = origination.year
    return row


def roll_month(
    previous: list[dict[str, Any]],
    rng: np.random.Generator,
    cutoff: date,
    payoff_rate: float,
    charge_offs: int,
    new_rows: list[dict[str, Any]],
) -> Roll:
    """Move every loan one month on. Delinquency is set afterwards by `set_delinquency`.

    Loans that closed last month leave the tape. Repossessions are charged off when the
    car is sold. A share of loans pays off, and some of last month's 60+ day loans are charged
    off. Every other loan makes its payment, which `set_delinquency` reverses for loans it makes
    late.
    """
    roll = Roll(rows=[])
    late_before = [
        row["loan_id"]
        for row in previous
        if row["status"] not in CLOSED and row["status"] != "REPO" and row["days_past_due"] >= 60
    ]
    charge = (
        set(
            rng.choice(late_before, size=min(charge_offs, len(late_before)), replace=False).tolist()
        )
        if late_before
        else set()
    )
    for old in previous:
        if old["status"] in CLOSED:
            continue
        row = dict(old, cutoff_date=cutoff, previous_balance=old["current_balance"])
        if old["status"] == "REPO" or old["loan_id"] in charge:
            row.update(
                status="CHARGED_OFF",
                charge_off_amount=old["current_balance"],
                charge_off_date=cutoff - timedelta(days=int(rng.integers(2, 26))),
                days_past_due=0,
            )
            roll.charged_off.append(row["loan_id"])
        elif rng.random() < payoff_rate:
            roll.principal_collected += old["current_balance"]
            row.update(status="PAID_OFF", current_balance=0.0, days_past_due=0, remaining_term=0)
            roll.payoffs.append(row["loan_id"])
        else:
            paid = old["payments_made"] + 1
            balance = (
                round(
                    _balance(old["original_balance"], old["apr"], old["monthly_payment"], paid), 2
                )
                if paid < old["original_term"]
                else 0.0
            )
            row.update(
                payments_made=paid,
                remaining_term=max(old["remaining_term"] - 1, 0),
                current_balance=max(balance, 0.0),
                status="ACTIVE",
                days_past_due=0,
            )
        roll.rows.append(row)
    for row in new_rows:
        roll.rows.append(dict(row, previous_balance=None))
        roll.new_loans.append(row["loan_id"])
    return roll


def set_delinquency(
    roll: Roll,
    rng: np.random.Generator,
    target_pct: float,
    previous_late: set[str],
    keep_current: set[str],
) -> None:
    """Make loans late until the 60+ day ratio is exactly `target_pct`, to two decimals.

    A late loan made no payment, so its balance goes back to last month's. Loans late last
    month are made late first, so delinquency carries over the way it does in a real pool.
    """
    continuing = [
        row
        for row in roll.rows
        if row["status"] == "ACTIVE"
        and row["previous_balance"] is not None
        and row["loan_id"] not in keep_current
    ]
    # Light delinquency first: a few loans 1 to 59 days late, which the trigger does not count.
    for row in continuing:
        draw = rng.random()
        if draw < 0.05:
            row["days_past_due"] = int(rng.integers(3, 29))
        elif draw < 0.062:
            row["days_past_due"] = int(rng.integers(31, 59))
            row["status"] = "DELINQUENT"
            _unpaid(row)

    pool = live(roll.rows)
    total = sum(row["current_balance"] for row in pool)
    late = sum(row["current_balance"] for row in pool if row["days_past_due"] >= 60)
    candidates = sorted(
        (row for row in continuing if row["days_past_due"] < 60),
        key=lambda row: (row["loan_id"] not in previous_late, rng.random()),
    )

    def ratio(extra_late: float, extra_total: float) -> float:
        return (late + extra_late) / (total + extra_total) * 100

    for row in candidates:
        gain = row["previous_balance"] - row["current_balance"]
        if ratio(row["previous_balance"], gain) >= target_pct - 0.004:
            # Finish with whichever loan lands closest to the target.
            remaining = [c for c in candidates if c["days_past_due"] < 60]
            best = min(
                remaining,
                key=lambda c: abs(
                    round(
                        ratio(c["previous_balance"], c["previous_balance"] - c["current_balance"]),
                        2,
                    )
                    - target_pct
                ),
            )
            _make_late(best, rng)
            break
        _make_late(row, rng)
        late += row["current_balance"]
        total += gain
    for row in roll.rows:
        _due_dates(row, roll.rows[0]["cutoff_date"])
    achieved = delinquency_ratio(roll.rows)
    if round(achieved, 2) != round(target_pct, 2):
        raise ValueError(f"Delinquency reached {achieved}, not {target_pct}")
    roll.principal_collected = round(
        roll.principal_collected
        + sum(
            row["previous_balance"] - row["current_balance"]
            for row in roll.rows
            if row["previous_balance"] is not None and row["status"] in ("ACTIVE", "DELINQUENT")
        ),
        2,
    )
    roll.interest_collected = round(
        sum(
            row["previous_balance"] * row["apr"] / 1200
            for row in roll.rows
            if row["previous_balance"] is not None and row["status"] == "ACTIVE"
        ),
        2,
    )


def _unpaid(row: dict[str, Any]) -> None:
    row["current_balance"] = row["previous_balance"]
    row["payments_made"] -= 1
    row["remaining_term"] += 1


def _make_late(row: dict[str, Any], rng: np.random.Generator) -> None:
    if row["status"] != "DELINQUENT":
        _unpaid(row)
    row["status"] = "DELINQUENT"
    row["days_past_due"] = int(rng.integers(61, 118))


def write_certificate(
    path: Path,
    borrower: str,
    period_end: date,
    lines: list[tuple[str, float]],
    ineligible: list[tuple[str, str, int]],
    concentrations: list[list[Any]],
    signer: str,
) -> None:
    """A borrowing base certificate workbook, in the layout both auto borrowers use."""
    from openpyxl import Workbook
    from openpyxl.styles import Font

    from dealkit.workbooks import _header, _save_stable

    workbook = Workbook()
    summary = workbook.active
    summary.title = "BBC Summary"
    summary["A1"] = borrower
    summary["A1"].font = Font(bold=True, size=14)
    summary["A2"] = "Borrowing Base Certificate"
    summary["A3"] = "Collection Period ended"
    summary["B3"] = period_end.isoformat()
    for offset, (label, value) in enumerate(lines):
        summary.cell(row=5 + offset, column=1, value=label)
        cell = summary.cell(row=5 + offset, column=2, value=value)
        cell.number_format = "0.0%" if "Advance Rate" in label else "#,##0.00"
    summary.cell(row=7 + len(lines), column=1, value=f"Certified by: {signer}")
    summary.column_dimensions["A"].width = 58
    summary.column_dimensions["B"].width = 20

    excluded = workbook.create_sheet("Ineligible Detail")
    _header(excluded, 1, ["Criterion", "Description", "Loans excluded"])
    for item in ineligible:
        excluded.append(list(item))
    excluded.column_dimensions["B"].width = 56

    sheet = workbook.create_sheet("Concentration")
    _header(sheet, 1, ["Limit", "Largest", "Balance (US$)", "% of pool", "Limit %", "Excess (US$)"])
    for item in concentrations:
        sheet.append(item)
    sheet.column_dimensions["A"].width = 42
    sheet.column_dimensions["B"].width = 28
    _save_stable(workbook, path)


def write_tape(
    rows: list[dict[str, Any]],
    columns: dict[str, str],
    path: Path,
    extra: dict[str, list[str]] | None = None,
) -> None:
    """Write a tape in a borrower's own layout. `extra` adds columns with no platform field."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow([*columns, *(extra or {})])
        for index, row in enumerate(rows):
            values = []
            for name in columns.values():
                value = row.get("raw_origination_date") if name == "origination_date" else row[name]
                values.append(
                    ""
                    if value is None
                    else _format_date(value)
                    if isinstance(value, date)
                    else value
                )
            writer.writerow([*values, *(column[index] for column in (extra or {}).values())])
