"""Middle-market and back-leverage facilities: obligor covenants and the borrowing base.

A back-leverage lender advances against a fund's loans to middle-market obligors. Each obligor
reports its own financials; code works out its leverage and interest cover from the figures read
from them, tests each against the covenant in force for the test date (after any waiver), and
builds the borrowing base from the loans that stay eligible. The model reads the statements;
nothing here trusts a figure it did not compute.

Amounts are integers: obligor financials in US$ thousands, loan balances in cents.
"""

from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

TWO = Decimal("0.01")


def ratio(numerator: int, denominator: int) -> Decimal:
    if not denominator:
        raise ValueError("Ratio with a zero denominator")
    return (Decimal(numerator) / Decimal(denominator)).quantize(TWO, ROUND_HALF_UP)


@dataclass(frozen=True)
class AddBack:
    description: str
    amount_k: int
    # "capped": cost savings, synergies, restructuring; "uncapped": another permitted
    # adjustment; "judgement": the documents do not settle which it is; None: not itemised.
    kind: str | None = None


def covenant_ebitda(ebitda_k: int, addbacks: list[AddBack], cap_pct: Decimal,
                    treat_judgement_as: str = "uncapped") -> int:
    """EBITDA plus add-backs, with capped add-backs limited to `cap_pct` of EBITDA before them.
    An add-back not itemised is treated as capped, the strict reading."""
    cap = int((Decimal(ebitda_k) * cap_pct / 100).to_integral_value(ROUND_HALF_UP))
    capped = uncapped = 0
    for item in addbacks:
        kind = item.kind or "capped"
        if kind == "judgement":
            kind = treat_judgement_as
        if kind == "capped":
            capped += item.amount_k
        else:
            uncapped += item.amount_k
    return ebitda_k + min(cap, capped) + uncapped


@dataclass(frozen=True)
class LeverageReading:
    name: str
    covenant_ebitda_k: int
    leverage: Decimal
    passed: bool


def addback_readings(ebitda_k: int, net_debt_k: int, addbacks: list[AddBack], cap_pct: Decimal,
                     maximum: Decimal) -> list[LeverageReading]:
    """Leverage under each reading of the add-backs: as the obligor reported it, with any
    judgement items under the cap, and with every add-back under the cap."""
    total = ebitda_k + sum(a.amount_k for a in addbacks)
    readings = [("As reported", total)]
    if any(a.kind == "judgement" for a in addbacks):
        readings.append(("Judgement items under the cap",
                         covenant_ebitda(ebitda_k, addbacks, cap_pct, "capped")))
    readings.append(("Every add-back under the cap", covenant_ebitda(
        ebitda_k, [AddBack(a.description, a.amount_k, "capped") for a in addbacks], cap_pct)))
    out = []
    for name, value in readings:
        lev = ratio(net_debt_k, value)
        out.append(LeverageReading(name, value, lev, lev <= maximum))
    return out


@dataclass(frozen=True)
class CovenantVersion:
    label: str
    max_leverage: Decimal
    effective_for: tuple[date, ...] = ()  # test dates it covers; empty means every test date


def level_in_force(versions: list[CovenantVersion], test_date: date) -> CovenantVersion:
    """The covenant that applies on a test date: a waiver covering that date, else the original."""
    for version in reversed(versions):
        if not version.effective_for or test_date in version.effective_for:
            return version
    raise ValueError("No covenant version applies")


@dataclass(frozen=True)
class ObligorTest:
    obligor: str
    leverage: Decimal
    max_leverage: Decimal
    icr: Decimal
    min_icr: Decimal
    leverage_passed: bool
    icr_passed: bool
    leverage_headroom: Decimal
    reported_leverage: Decimal | None
    leverage_difference: Decimal | None
    within_tolerance: bool | None

    @property
    def passed(self) -> bool:
        return self.leverage_passed and self.icr_passed


def check_obligor(obligor: str, net_debt_k: int, covenant_ebitda_k: int, interest_k: int,
                 max_leverage: Decimal, min_icr: Decimal,
                 reported_leverage: Decimal | None = None,
                 tolerance: Decimal = Decimal("0.02")) -> ObligorTest:
    leverage = ratio(net_debt_k, covenant_ebitda_k)
    icr = ratio(covenant_ebitda_k, interest_k)
    difference = None if reported_leverage is None else leverage - reported_leverage
    return ObligorTest(
        obligor, leverage, max_leverage, icr, min_icr, leverage <= max_leverage,
        icr >= min_icr, max_leverage - leverage, reported_leverage, difference,
        None if difference is None else abs(difference) <= tolerance)


@dataclass(frozen=True)
class ObligorLoan:
    id: str
    name: str
    sector: str
    outstanding_cents: int
    advance_rate_pct: Decimal
    eligible: bool = True
    reason: str = ""


@dataclass
class BackLeverageBase:
    aggregate_cents: int
    eligible_cents: int
    excluded: list[tuple[str, str, int]]  # id, reason, outstanding
    single_limit_cents: int
    sector_limit_cents: int
    obligor_excess_cents: dict[str, int]
    sector_excess_cents: dict[str, int]
    largest: tuple[str, Decimal]
    largest_sector: tuple[str, Decimal]
    values_cents: dict[str, int]
    excess_reduction_cents: int
    borrowing_base_cents: int
    availability_cents: int
    shares: dict[str, Decimal] = field(default_factory=dict)


def _cents(value: Decimal) -> int:
    return int(value.to_integral_value(ROUND_HALF_UP))


def borrowing_base(loans: list[ObligorLoan], single_limit_pct: Decimal, sector_limit_pct: Decimal,
                   commitment_cents: int, drawn_cents: int) -> BackLeverageBase:
    """Each eligible loan at its advance rate, less any concentration excess at the rate that
    applies to it. Sector excess is taken from the sector's largest loans first."""
    eligible = [loan for loan in loans if loan.eligible]
    total = sum(loan.outstanding_cents for loan in eligible)
    single = _cents(Decimal(total) * single_limit_pct / 100)
    sector_cap = _cents(Decimal(total) * sector_limit_pct / 100)
    obligor_excess = {loan.id: loan.outstanding_cents - single for loan in eligible
                      if loan.outstanding_cents > single}
    sectors: dict[str, int] = {}
    for loan in eligible:
        sectors[loan.sector] = sectors.get(loan.sector, 0) + loan.outstanding_cents - \
            obligor_excess.get(loan.id, 0)
    sector_excess = {s: v - sector_cap for s, v in sectors.items() if v > sector_cap}
    taken: dict[str, int] = dict(obligor_excess)
    for sector, amount in sector_excess.items():
        left = amount
        for loan in sorted((x for x in eligible if x.sector == sector),
                           key=lambda x: (-x.outstanding_cents, x.id)):
            part = min(left, loan.outstanding_cents - taken.get(loan.id, 0))
            taken[loan.id] = taken.get(loan.id, 0) + part
            left -= part
            if not left:
                break
    values = {loan.id: _cents(Decimal(loan.outstanding_cents) * loan.advance_rate_pct / 100)
              for loan in eligible}
    reduction = sum(_cents(Decimal(taken[loan.id]) * loan.advance_rate_pct / 100)
                    for loan in eligible if taken.get(loan.id))
    base = sum(values.values()) - reduction
    largest = max(eligible, key=lambda x: (x.outstanding_cents, x.id))
    top_sector = max(sectors, key=lambda s: (sectors[s], s))
    share = {loan.id: (Decimal(loan.outstanding_cents) / Decimal(total) * 100).quantize(
        TWO, ROUND_HALF_UP) for loan in eligible}
    return BackLeverageBase(
        aggregate_cents=sum(loan.outstanding_cents for loan in loans),
        eligible_cents=total,
        excluded=[(loan.id, loan.reason, loan.outstanding_cents) for loan in loans
                  if not loan.eligible],
        single_limit_cents=single,
        sector_limit_cents=sector_cap,
        obligor_excess_cents=obligor_excess,
        sector_excess_cents=sector_excess,
        largest=(largest.id, share[largest.id]),
        largest_sector=(top_sector, (Decimal(sectors[top_sector]) / Decimal(total) * 100)
                        .quantize(TWO, ROUND_HALF_UP)),
        values_cents=values,
        excess_reduction_cents=reduction,
        borrowing_base_cents=base,
        availability_cents=min(commitment_cents, base) - drawn_cents,
        shares=share,
    )
