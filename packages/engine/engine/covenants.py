"""Financial covenants and the delinquency trigger."""

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from engine.run import Loan


@dataclass(frozen=True)
class Financials:
    """Parent figures for one quarter end, all in the same units."""

    total_equity: int
    goodwill: int
    intangibles: int
    related_party_receivables: int
    subordinated_debt: int
    total_liabilities: int
    unrestricted_cash: int


@dataclass(frozen=True)
class CovenantTerms:
    min_tangible_net_worth: int
    max_leverage_ratio: Decimal
    min_liquidity: int
    subordinated_debt_cap: int


@dataclass(frozen=True)
class CovenantResult:
    name: str
    clause: str
    value: Decimal
    limit: Decimal
    passed: bool
    formula: str


def _ratio(numerator: int, denominator: int) -> Decimal:
    return (Decimal(numerator) / Decimal(denominator)).quantize(Decimal("0.01"), ROUND_HALF_UP)


def tangible_net_worth(figures: Financials) -> int:
    return (figures.total_equity - figures.goodwill - figures.intangibles
            - figures.related_party_receivables)


def evaluate_covenants(figures: Financials, terms: CovenantTerms) -> tuple[CovenantResult, ...]:
    worth = tangible_net_worth(figures)
    # 6.12(c) applies to the Leverage Ratio only, never to the worth test itself.
    carve_out = min(figures.subordinated_debt, terms.subordinated_debt_cap)
    leverage = _ratio(figures.total_liabilities - carve_out, worth + carve_out)
    return (
        CovenantResult("Minimum tangible net worth", "6.12(a), 1.1", Decimal(worth),
                       Decimal(terms.min_tangible_net_worth),
                       worth >= terms.min_tangible_net_worth,
                       "equity - goodwill - intangibles - related party receivables"),
        CovenantResult("Maximum leverage ratio", "6.12(b), 6.12(c), 1.1", leverage,
                       terms.max_leverage_ratio, leverage <= terms.max_leverage_ratio,
                       "(total liabilities - carve-out) / (tangible net worth + carve-out)"),
        CovenantResult("Minimum liquidity", "6.12(d)", Decimal(figures.unrestricted_cash),
                       Decimal(terms.min_liquidity),
                       figures.unrestricted_cash >= terms.min_liquidity, "unrestricted cash"),
    )


def leverage_without_carve_out(figures: Financials) -> Decimal:
    """Shown beside the covenant, because skipping 6.12(c) would report a false breach."""
    return _ratio(figures.total_liabilities, tangible_net_worth(figures))


def delinquency_ratio(loans: list[Loan]) -> Decimal:
    """60+ day balance over pool balance, excluding charged-off loans."""
    live = [loan for loan in loans if loan["status"] != "CHARGED_OFF"]
    late = sum(loan["current_balance"] for loan in live if loan["days_past_due"] >= 60)
    total = sum(loan["current_balance"] for loan in live)
    return (Decimal(late) / Decimal(total) * 100).quantize(Decimal("0.01"), ROUND_HALF_UP)


@dataclass(frozen=True)
class TriggerResult:
    average_pct: Decimal
    trigger_pct: Decimal
    tripped: bool


def delinquency_trigger(monthly_pct: tuple[Decimal, Decimal, Decimal],
                        trigger_pct: Decimal) -> TriggerResult:
    average = (sum(monthly_pct) / 3).quantize(Decimal("0.01"), ROUND_HALF_UP)
    return TriggerResult(average, trigger_pct, average > trigger_pct)
