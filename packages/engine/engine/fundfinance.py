"""Subscription lines: investor classes, the borrowing base and notice reconciliation.

A subscription line lends against the fund's investors' uncalled commitments. Each investor's
class (Included, Designated or Excluded) follows from its rating and the class the lender
approved; an Exclusion Event takes it out of the base. Concentration limits cap what one
investor, and designated investors together, can count for. Capital call and distribution
notices are reconciled to the investor register investor by investor.

Amounts are in cents.
"""

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

SP = ["AAA", "AA+", "AA", "AA-", "A+", "A", "A-", "BBB+", "BBB", "BBB-", "BB+", "BB", "BB-",
      "B+", "B", "B-", "CCC+", "CCC", "CCC-", "CC", "C"]


def _cents(value: Decimal) -> int:
    return int(value.to_integral_value(ROUND_HALF_UP))


@dataclass(frozen=True)
class InvestorClass:
    name: str  # "Included", "Designated" or "Excluded"
    reason: str
    exclusion_event: bool = False


def classify(rating: str, approved: str, included_min: str = "A-",
             exclusion_below: str = "BBB-") -> InvestorClass:
    """The agreement's class for an investor, from its S&P rating and its approved class.
    "NR" or a blank rating means unrated."""
    if approved == "Excluded":
        return InvestorClass("Excluded", "Not approved by the lender")
    rated = rating in SP
    if rated and SP.index(rating) > SP.index(exclusion_below):
        return InvestorClass("Excluded", f"Exclusion Event: rated {rating}, below "
                             f"{exclusion_below}", True)
    if approved == "Included" and rated and SP.index(rating) <= SP.index(included_min):
        return InvestorClass("Included", f"Approved, rated {rating}")
    if approved == "Included":
        return InvestorClass("Designated", f"Rated {rating or 'NR'}, below {included_min}")
    return InvestorClass("Designated", "Approved as designated, unrated")


@dataclass(frozen=True)
class Investor:
    id: str
    name: str
    uncalled_cents: int
    investor_class: str


@dataclass
class SubscriptionBase:
    aggregate_eligible_cents: int
    single_limit_cents: int
    investor_excess_cents: dict[str, int]
    designated_cents: int
    designated_limit_cents: int
    designated_excess_cents: int
    values_cents: dict[str, int]
    concentration_reduction_cents: int
    borrowing_base_cents: int
    availability_cents: int
    prepayment_cents: int
    shares: dict[str, Decimal]


def borrowing_base(investors: list[Investor], advance_rates: dict[str, Decimal],
                   single_limit_pct: Decimal, designated_limit_pct: Decimal,
                   commitment_cents: int, drawn_cents: int) -> SubscriptionBase:
    eligible = [i for i in investors if i.investor_class != "Excluded"]
    aggregate = sum(i.uncalled_cents for i in eligible)
    single = _cents(Decimal(aggregate) * single_limit_pct / 100)
    excess = {i.id: i.uncalled_cents - single for i in eligible if i.uncalled_cents > single}
    designated = sum(i.uncalled_cents - excess.get(i.id, 0) for i in eligible
                     if i.investor_class == "Designated")
    designated_cap = _cents(Decimal(aggregate) * designated_limit_pct / 100)
    designated_excess = max(0, designated - designated_cap)
    values = {i.id: _cents(Decimal(i.uncalled_cents - excess.get(i.id, 0))
                           * advance_rates[i.investor_class] / 100) for i in eligible}
    reduction = sum(_cents(Decimal(v) * advance_rates[next(
        i.investor_class for i in eligible if i.id == k)] / 100) for k, v in excess.items())
    base = sum(values.values()) - _cents(Decimal(designated_excess)
                                         * advance_rates.get("Designated", Decimal(0)) / 100)
    available = min(commitment_cents, base)
    return SubscriptionBase(
        aggregate_eligible_cents=aggregate,
        single_limit_cents=single,
        investor_excess_cents=excess,
        designated_cents=designated,
        designated_limit_cents=designated_cap,
        designated_excess_cents=designated_excess,
        values_cents=values,
        concentration_reduction_cents=reduction,
        borrowing_base_cents=base,
        availability_cents=available - drawn_cents,
        prepayment_cents=max(0, drawn_cents - available),
        shares={i.id: (Decimal(i.uncalled_cents) / Decimal(aggregate) * 100).quantize(
            Decimal("0.01"), ROUND_HALF_UP) for i in eligible} if aggregate else {},
    )


@dataclass(frozen=True)
class NoticeLine:
    investor: str
    commitment_cents: int
    amount_cents: int
    expected_cents: int

    @property
    def difference_cents(self) -> int:
        return self.amount_cents - self.expected_cents


def reconcile_notice(lines: list[tuple[str, int, int]], total_cents: int, pct: Decimal,
                     tolerance_cents: int = 100) -> tuple[list[NoticeLine], int, bool]:
    """Each investor's amount against its pro-rata share of the notice. Returns the lines, the
    sum's difference from the stated total, and whether every line is within tolerance."""
    out = [NoticeLine(investor, commitment, amount,
                      _cents(Decimal(commitment) * pct / 100))
           for investor, commitment, amount in lines]
    summed = sum(line.amount_cents for line in out) - total_cents
    ok = abs(summed) <= tolerance_cents and all(
        abs(line.difference_cents) <= tolerance_cents for line in out)
    return out, summed, ok


@dataclass(frozen=True)
class RegisterCheck:
    investor: str
    prior_uncalled_cents: int
    called_cents: int
    recallable_cents: int
    expected_cents: int
    register_cents: int

    @property
    def difference_cents(self) -> int:
        return self.register_cents - self.expected_cents


def roll_register(prior: dict[str, int], calls: dict[str, int], recallable: dict[str, int],
                  register: dict[str, int]) -> list[RegisterCheck]:
    """Each investor's uncalled commitment rolled from the prior register through the month's
    notices, against what the new register says."""
    return [RegisterCheck(k, prior[k], calls.get(k, 0), recallable.get(k, 0),
                          prior[k] - calls.get(k, 0) + recallable.get(k, 0), register[k])
            for k in sorted(prior)]
