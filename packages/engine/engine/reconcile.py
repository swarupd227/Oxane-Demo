"""Explain the difference between the borrower's certificate and the system's run."""

from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_EVEN, Decimal

from engine.rules import RuleSet
from engine.run import Loan, RunResult, run


@dataclass(frozen=True)
class Certificate:
    """What the borrower reported, and the tests it says it applied."""

    eligible_pool_cents: int
    excess_cents: int
    advance_rate_pct: Decimal
    reserve_cents: int
    borrowing_base_cents: int
    outstanding_advances_cents: int
    availability_cents: int
    thresholds: dict[str, Decimal]  # Rules the borrower tested differently.
    rules_not_applied: frozenset[str]  # Rules the borrower did not test at all.


@dataclass(frozen=True)
class BridgeLine:
    rule_id: str
    label: str
    loan_ids: tuple[str, ...]
    amount_cents: int


@dataclass(frozen=True)
class Bridge:
    borrower_cents: int
    system_cents: int
    gap_cents: int
    lines: tuple[BridgeLine, ...]
    unexplained_cents: int
    reproduces_certificate: bool


@dataclass(frozen=True)
class BaseBridge:
    borrower_cents: int
    lines: tuple[tuple[str, int], ...]
    system_cents: int


def borrower_rules(rules: RuleSet, certificate: Certificate) -> RuleSet:
    adjusted = rules.without_rules(set(certificate.rules_not_applied))
    for rule_id, value in certificate.thresholds.items():
        adjusted = adjusted.with_threshold(rule_id, value)
    return adjusted


def bridge_eligible_pool(loans: list[Loan], rules: RuleSet, system: RunResult,
                         certificate: Certificate, as_of: date) -> Bridge:
    """Re-run the tape the way the borrower says it did, then attribute each loan that differs."""
    replay = run(loans, borrower_rules(rules, certificate), as_of,
                 certificate.outstanding_advances_cents)
    balances = {loan["loan_id"]: loan["current_balance"] for loan in loans}
    labels = {rule.id: rule.plain_english for rule in rules.eligibility}

    only_borrower = set(replay.eligible_loan_ids) - set(system.eligible_loan_ids)
    by_rule: dict[str, list[str]] = {}
    for loan_id in sorted(only_borrower):
        by_rule.setdefault(system.failed_rules_by_loan[loan_id][0], []).append(loan_id)

    lines = tuple(
        BridgeLine(rule_id, labels[rule_id], tuple(ids), sum(balances[i] for i in ids))
        for rule_id, ids in by_rule.items()
    )
    gap = certificate.eligible_pool_cents - system.eligible_pool_cents
    return Bridge(
        borrower_cents=certificate.eligible_pool_cents,
        system_cents=system.eligible_pool_cents,
        gap_cents=gap,
        lines=lines,
        unexplained_cents=gap - sum(line.amount_cents for line in lines),
        reproduces_certificate=replay.eligible_pool_cents == certificate.eligible_pool_cents,
    )


def bridge_borrowing_base(bridge: Bridge, system: RunResult,
                          certificate: Certificate) -> BaseBridge:
    """Carry each pool difference through the advance rate and reserve to the borrowing base."""
    pct = system.advance_rate_pct
    reserve_share = (Decimal(system.reserve_cents) / system.eligible_pool_cents
                     if system.eligible_pool_cents else Decimal(0))
    net = pct / 100 - reserve_share

    def scaled(amount: int, factor: Decimal) -> int:
        return int((amount * factor).to_integral_value(rounding=ROUND_HALF_EVEN))

    lines = [(line.label, -scaled(line.amount_cents, net)) for line in bridge.lines]
    excess_change = system.excess_cents - certificate.excess_cents
    if excess_change:
        lines.append(("Excess concentration", -scaled(excess_change, pct / 100)))
    if certificate.advance_rate_pct != pct:
        lines.append(("Advance rate", scaled(
            certificate.eligible_pool_cents - certificate.excess_cents,
            (pct - certificate.advance_rate_pct) / 100)))
    residual = (system.borrowing_base_cents - certificate.borrowing_base_cents
                - sum(amount for _, amount in lines))
    if residual:
        lines.append(("Rounding", residual))
    return BaseBridge(certificate.borrowing_base_cents, tuple(lines),
                      system.borrowing_base_cents)


@dataclass(frozen=True)
class ImpactPreview:
    newly_ineligible: tuple[str, ...]
    newly_eligible: tuple[str, ...]
    eligible_pool_change_cents: int
    borrowing_base_change_cents: int


def impact(before: RunResult, after: RunResult) -> ImpactPreview:
    """What a rule edit would change, shown before the analyst saves it."""
    was, now = set(before.eligible_loan_ids), set(after.eligible_loan_ids)
    return ImpactPreview(
        newly_ineligible=tuple(sorted(was - now)),
        newly_eligible=tuple(sorted(now - was)),
        eligible_pool_change_cents=after.eligible_pool_cents - before.eligible_pool_cents,
        borrowing_base_change_cents=after.borrowing_base_cents - before.borrowing_base_cents,
    )
