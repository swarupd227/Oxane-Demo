"""Borrowing base arithmetic for the deal kit, in whole cents.

`system_view` is the correct reading of the agreement and feeds the answer key.
`borrower_view` repeats the borrower's mistakes and feeds its certificate: it
tests 60 days past due instead of 30, has no duplicate VIN test, and treats the
two Sunrise Motors spellings as separate dealers.
"""

from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Any

from dealkit.tape import US_STATES


def cents(amount: float) -> int:
    return round(amount * 100)


def failures(row: dict[str, Any], vin_counts: Counter[str], past_due_limit: int = 30,
             check_vin: bool = True) -> list[str]:
    tests = {
        "E1": row["days_past_due"] <= past_due_limit,
        "E2": row["status"] not in ("CHARGED_OFF", "REPO"),
        "E3": row["original_term"] <= 84,
        "E4": row["fico"] >= 540,
        "E5": row["current_balance"] <= 75000,
        "E6": row["obligor_state"] in US_STATES,
        "E8": row["modification_count"] <= 1,
        "E9": 6.00 <= row["apr"] <= 29.99,
        "E10": row["origination_date"].year - row["model_year"] <= 10,
        "E11": row["payments_made"] >= 1,
        "E12": not check_vin or vin_counts[row["vin"]] == 1,
    }
    return [rule for rule, passed in tests.items() if not passed]


@dataclass
class View:
    gross_pool: int
    eligible_pool: int
    eligible_rows: list[dict[str, Any]]
    failures_by_rule: dict[str, list[str]]
    concentrations: dict[str, dict[str, Any]]
    excess: int
    advance_rate_pct: float
    reserve: int
    borrowing_base: int
    availability: int


def _concentrations(rows: list[dict[str, Any]], eligible_pool: int, limits: dict[str, float],
                    dealer_alias: dict[str, str]) -> dict[str, dict[str, Any]]:
    def dealer(row: dict[str, Any]) -> str:
        return dealer_alias.get(row["dealer_name"], row["dealer_name"])

    def largest(key: str | None = None, keyer: Any = None) -> tuple[str, int]:
        totals: defaultdict[str, int] = defaultdict(int)
        for row in rows:
            totals[keyer(row) if keyer else row[key]] += cents(row["current_balance"])
        name = max(sorted(totals), key=lambda item: totals[item])
        return name, totals[name]

    def total(predicate: Any) -> int:
        return sum(cents(row["current_balance"]) for row in rows if predicate(row))

    buckets = {
        "C1": largest("obligor_state"),
        "C2": largest(keyer=dealer),
        "C3": ("Term above 72 months", total(lambda row: row["original_term"] > 72)),
        "C4": ("FICO below 600", total(lambda row: row["fico"] < 600)),
        "C5": ("Used vehicles", total(lambda row: row["vehicle_condition"] == "USED")),
    }
    result = {}
    for rule, (name, amount) in buckets.items():
        limit = round(eligible_pool * limits[rule] / 100)
        result[rule] = {
            "largest": name,
            "amount_cents": amount,
            "share_pct": round(amount / eligible_pool * 100, 2),
            "limit_pct": limits[rule],
            "excess_cents": max(0, amount - limit),
        }
    return result


def _view(rows: list[dict[str, Any]], deal: dict[str, Any], past_due_limit: int, check_vin: bool,
          dealer_alias: dict[str, str]) -> View:
    vin_counts = Counter(row["vin"] for row in rows)
    by_rule: defaultdict[str, list[str]] = defaultdict(list)
    eligible = []
    for row in rows:
        failed = failures(row, vin_counts, past_due_limit, check_vin)
        for rule in failed:
            by_rule[rule].append(row["loan_id"])
        if not failed:
            eligible.append(row)

    eligible_pool = sum(cents(row["current_balance"]) for row in eligible)
    limits = {item["id"]: item["limit_pct"] for item in deal["concentration"]}
    concentrations = _concentrations(eligible, eligible_pool, limits, dealer_alias)
    excess = sum(item["excess_cents"] for item in concentrations.values())

    terms = deal["terms"]
    rate = terms["advance_rate_amended_pct"]
    reserve = round(eligible_pool * terms["reserve_pct"] / 100)
    base = round((eligible_pool - excess) * rate / 100) - reserve
    drawable = min(base, deal["facility"]["limit_usd"] * 100)
    return View(
        gross_pool=sum(cents(row["current_balance"]) for row in rows),
        eligible_pool=eligible_pool,
        eligible_rows=eligible,
        failures_by_rule=dict(by_rule),
        concentrations=concentrations,
        excess=excess,
        advance_rate_pct=rate,
        reserve=reserve,
        borrowing_base=base,
        availability=drawable - deal["bbc"]["outstanding_advances_usd"] * 100,
    )


def system_view(rows: list[dict[str, Any]], deal: dict[str, Any], match_dealers: bool) -> View:
    names = deal["planted"]["x6_dealer_names"]
    alias = {names[1]: names[0]} if match_dealers else {}
    return _view(rows, deal, past_due_limit=30, check_vin=True, dealer_alias=alias)


def borrower_view(rows: list[dict[str, Any]], deal: dict[str, Any]) -> View:
    return _view(rows, deal, past_due_limit=60, check_vin=False, dealer_alias={})
