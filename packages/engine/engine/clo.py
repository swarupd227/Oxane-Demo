"""CLO and broadly syndicated loan checks: the CCC bucket and its excess, the borrowing base,
early-warning indicators and identifier changes.

Money is whole cents and prices are Decimals in points of par. Ratings are compared on one
notch scale shared by Moody's and S&P. Which rating a test uses is the client's master field:
the platform default is Moody's, and a client may override it with the lower of the two.
"""

from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

MOODYS = ("Aaa", "Aa1", "Aa2", "Aa3", "A1", "A2", "A3", "Baa1", "Baa2", "Baa3", "Ba1", "Ba2",
          "Ba3", "B1", "B2", "B3", "Caa1", "Caa2", "Caa3", "Ca", "C")
SP = ("AAA", "AA+", "AA", "AA-", "A+", "A", "A-", "BBB+", "BBB", "BBB-", "BB+", "BB", "BB-",
      "B+", "B", "B-", "CCC+", "CCC", "CCC-", "CC", "C")
CCC_NOTCH = MOODYS.index("Caa1")
NOT_RATED = ("NR", "")

Position = dict[str, Any]


def notch(moodys: str, sp: str, basis: str = "moodys") -> int | None:
    """The notch a test uses: `moodys`, or `lower_of` the two. Not rated gives None."""
    m = MOODYS.index(moodys) if moodys in MOODYS else None
    s = SP.index(sp) if sp in SP else None
    if basis == "moodys":
        return m if m is not None else s
    found = [n for n in (m, s) if n is not None]
    return max(found) if found else None


def is_ccc(position: Position, basis: str) -> bool:
    found = notch(position["moodys"], position["sp"], basis)
    return found is not None and found >= CCC_NOTCH


def _pct(part: int, whole: int) -> Decimal:
    if not whole:
        return Decimal(0)
    return (Decimal(part) / Decimal(whole) * 100).quantize(Decimal("0.01"), ROUND_HALF_UP)


@dataclass(frozen=True)
class ExcessPart:
    loanx: str
    issuer: str
    par_in_excess_cents: int
    bid: Decimal
    haircut_cents: int


@dataclass(frozen=True)
class BorrowingBase:
    total_par_cents: int
    ccc_par_cents: int
    ccc_pct: Decimal
    ccc_limit_pct: Decimal
    ccc_limit_cents: int
    ccc_excess_cents: int
    excess: tuple[ExcessPart, ...]
    haircut_cents: int
    adjusted_cents: int
    advance_rate_pct: Decimal
    borrowing_base_cents: int
    availability_cents: int
    ccc_positions: tuple[str, ...]
    passed: bool  # the CCC bucket is within its limit


def borrowing_base(positions: list[Position], bids: dict[str, Decimal], ccc_limit_pct: Decimal,
                   advance_rate_pct: Decimal, commitment_cents: int, drawn_cents: int,
                   basis: str) -> BorrowingBase:
    """The CCC excess is carried at market value: the CCC loans with the lowest bid first, up to
    the excess, lose the difference between par and market value."""
    total = sum(p["par_cents"] for p in positions)
    ccc = sorted((p for p in positions if is_ccc(p, basis)),
                 key=lambda p: (bids[p["loanx"]], p["loanx"]))
    ccc_par = sum(p["par_cents"] for p in ccc)
    limit = int((Decimal(total) * ccc_limit_pct / 100).to_integral_value(ROUND_HALF_UP))
    excess = max(0, ccc_par - limit)
    parts, left = [], excess
    for p in ccc:
        if left <= 0:
            break
        part = min(p["par_cents"], left)
        cut = int((Decimal(part) * (1 - bids[p["loanx"]] / 100)).to_integral_value(ROUND_HALF_UP))
        parts.append(ExcessPart(p["loanx"], p["issuer"], part, bids[p["loanx"]], cut))
        left -= part
    haircut = sum(p.haircut_cents for p in parts)
    adjusted = total - haircut
    base = int((Decimal(adjusted) * advance_rate_pct / 100).to_integral_value(ROUND_HALF_UP))
    return BorrowingBase(total, ccc_par, _pct(ccc_par, total), ccc_limit_pct, limit, excess,
                         tuple(parts), haircut, adjusted, advance_rate_pct, base,
                         min(commitment_cents, base) - drawn_cents,
                         tuple(p["loanx"] for p in ccc), excess == 0)


# Identifiers


@dataclass(frozen=True)
class IdentifierChange:
    old_loanx: str
    new_loanx: str
    old_cusip: str
    new_cusip: str
    issuer: str
    matched_on: tuple[str, ...]


@dataclass(frozen=True)
class PositionChanges:
    sold: tuple[str, ...]  # old LoanX IDs explained by a sale
    bought: tuple[str, ...]  # new LoanX IDs explained by a purchase
    relinked: tuple[IdentifierChange, ...]
    unexplained_gone: tuple[str, ...]
    unexplained_new: tuple[str, ...]


LINK_FIELDS = ("issuer", "facility", "maturity", "spread_bps")


def compare_positions(prior: list[Position], current: list[Position],
                      trades: list[dict[str, Any]]) -> PositionChanges:
    """What left the book and what joined it. A loan that left with no sale, matched to one that
    joined with no purchase on issuer, facility, maturity and spread, is the same loan under a
    new identifier: it is linked, not reported as missing and new."""
    before = {p["loanx"]: p for p in prior}
    now = {p["loanx"]: p for p in current}
    gone = sorted(set(before) - set(now))
    new = sorted(set(now) - set(before))
    sales = {t["loanx"] for t in trades if t["direction"] == "Sell"}
    buys = {t["loanx"] for t in trades if t["direction"] == "Buy"}
    sold = tuple(x for x in gone if x in sales)
    bought = tuple(x for x in new if x in buys)
    loose_gone = [x for x in gone if x not in sales]
    loose_new = [x for x in new if x not in buys]
    links = []
    for old in list(loose_gone):
        match = [x for x in loose_new
                 if all(before[old][f] == now[x][f] for f in LINK_FIELDS)]
        if len(match) == 1:
            links.append(IdentifierChange(old, match[0], before[old]["cusip"],
                                          now[match[0]]["cusip"], before[old]["issuer"],
                                          LINK_FIELDS))
            loose_gone.remove(old)
            loose_new.remove(match[0])
    return PositionChanges(sold, bought, tuple(links), tuple(loose_gone), tuple(loose_new))


def par_roll(prior: list[Position], current: list[Position], trades: list[dict[str, Any]]
             ) -> dict[str, int]:
    """Last month's par, less sales, plus purchases, against this month's."""
    opening = sum(p["par_cents"] for p in prior)
    sold = sum(t["par_cents"] for t in trades if t["direction"] == "Sell")
    bought = sum(t["par_cents"] for t in trades if t["direction"] == "Buy")
    closing = sum(p["par_cents"] for p in current)
    return {"opening": opening, "sold": sold, "bought": bought, "expected": opening - sold + bought,
            "closing": closing, "gap": opening - sold + bought - closing}


# Early warning


@dataclass(frozen=True)
class RatingChange:
    loanx: str
    issuer: str
    before: tuple[str, str]
    after: tuple[str, str]
    notches: int  # positive is a downgrade
    into_ccc: bool


@dataclass(frozen=True)
class PriceMove:
    loanx: str
    issuer: str
    before: Decimal
    after: Decimal
    change: Decimal


def early_warnings(prior: list[Position], current: list[Position],
                   prior_bids: dict[str, Decimal], bids: dict[str, Decimal],
                   links: dict[str, str], move_limit: Decimal, basis: str
                   ) -> tuple[tuple[RatingChange, ...], tuple[PriceMove, ...]]:
    """Downgrades, and price falls of more than `move_limit` points. `links` maps new LoanX IDs
    to old ones, so a loan under a new identifier is compared with its own history."""
    before = {p["loanx"]: p for p in prior}
    ratings, prices = [], []
    for p in current:
        old_id = links.get(p["loanx"], p["loanx"])
        old = before.get(old_id)
        if old is None:
            continue
        was, now = notch(old["moodys"], old["sp"], basis), notch(p["moodys"], p["sp"], basis)
        if was is not None and now is not None and now > was:
            ratings.append(RatingChange(p["loanx"], p["issuer"], (old["moodys"], old["sp"]),
                                        (p["moodys"], p["sp"]), now - was,
                                        was < CCC_NOTCH <= now))
        if old_id in prior_bids and p["loanx"] in bids:
            move = bids[p["loanx"]] - prior_bids[old_id]
            if -move > move_limit:
                prices.append(PriceMove(p["loanx"], p["issuer"], prior_bids[old_id],
                                        bids[p["loanx"]], move))
    return tuple(ratings), tuple(prices)


def days_to(maturity: date, as_of: date) -> int:
    return (maturity - as_of).days
