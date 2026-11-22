"""The borrowing base under the client model's treatments, one difference at a time.

This is the kit's own arithmetic, in whole cents, and feeds only the answer key. The platform
works the same impacts out with its rules engine, and the scorecard compares the two.
"""

from collections import Counter, defaultdict
from typing import Any

from dealkit.calc import cents, failures


def borrowing_base(rows: list[dict[str, Any]], deal: dict[str, Any], *,
                   rate_pct: float | None = None,
                   exclude_from_dpd: int = 31, fico_bucket_le: bool = False,
                   denominator: str = "eligible", match_dealers: bool = True) -> dict[str, Any]:
    """`exclude_from_dpd` is the first days-past-due value that fails: 31 under the agreement
    (more than 30 days), 30 under the client's "30+ days" wording."""
    vin_counts = Counter(row["vin"] for row in rows)
    eligible = [row for row in rows
                if not failures(row, vin_counts, past_due_limit=exclude_from_dpd - 1)]
    pool = sum(cents(row["current_balance"]) for row in eligible)
    gross = sum(cents(row["current_balance"]) for row in rows)
    base_for_limits = gross if denominator == "total" else pool

    names = deal["planted"]["x6_dealer_names"]
    alias = {names[1]: names[0]} if match_dealers else {}
    limits = {item["id"]: item["limit_pct"] for item in deal["concentration"]}

    def in_bucket(row: dict[str, Any]) -> bool:
        return row["fico"] <= 600 if fico_bucket_le else row["fico"] < 600

    groups: dict[str, dict[str, int]] = {
        "C1": defaultdict(int), "C2": defaultdict(int), "C3": defaultdict(int),
        "C4": defaultdict(int), "C5": defaultdict(int),
    }
    for row in eligible:
        balance = cents(row["current_balance"])
        groups["C1"][row["obligor_state"]] += balance
        groups["C2"][alias.get(row["dealer_name"], row["dealer_name"])] += balance
        if row["original_term"] > 72:
            groups["C3"]["term"] += balance
        if in_bucket(row):
            groups["C4"]["fico"] += balance
        if row["vehicle_condition"] == "USED":
            groups["C5"]["used"] += balance
    excess = 0
    for rule, buckets in groups.items():
        limit = round(base_for_limits * limits[rule] / 100)
        excess += sum(max(0, amount - limit) for amount in buckets.values())

    rate = rate_pct if rate_pct is not None else deal["terms"]["advance_rate_amended_pct"]
    reserve = round(pool * deal["terms"]["reserve_pct"] / 100)
    base = round((pool - excess) * rate / 100) - reserve
    drawable = min(base, deal["facility"]["limit_usd"] * 100)
    return {
        "eligible_pool": pool / 100,
        "excess": excess / 100,
        "borrowing_base": base / 100,
        "availability": (drawable - deal["bbc"]["outstanding_advances_usd"] * 100) / 100,
        "fico_bucket": groups["C4"]["fico"] / 100,
        "eligible_loans": len(eligible),
    }


def impacts(rows: list[dict[str, Any]], deal: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Each difference on its own, against the agreement's reading after the dealer match."""
    agreed = borrowing_base(rows, deal)
    variants = {
        "advance_rate": borrowing_base(rows, deal,
                                       rate_pct=deal["terms"]["advance_rate_original_pct"]),
        "past_due_exclusion": borrowing_base(rows, deal, exclude_from_dpd=30),
        "concentration_denominator": borrowing_base(rows, deal, denominator="total"),
        "dealer_grouping": borrowing_base(rows, deal, match_dealers=False),
        "fico_bucket": borrowing_base(rows, deal, fico_bucket_le=True),
    }
    result = {}
    for topic, variant in variants.items():
        result[topic] = {
            "borrowing_base_change": round(variant["borrowing_base"] - agreed["borrowing_base"],
                                           2),
            "eligible_loans_change": variant["eligible_loans"] - agreed["eligible_loans"],
            "fico_bucket_change": round(variant["fico_bucket"] - agreed["fico_bucket"], 2),
        }
    result["missing_fico"] = {"borrowing_base_change": 0.0, "eligible_loans_change": 0,
                              "fico_bucket_change": 0.0,
                              "loans_without_score": sum(1 for row in rows if row["fico"] is None)}
    result["agreed"] = agreed
    return result
