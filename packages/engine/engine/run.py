"""Run a rule set over a loan tape and calculate the borrowing base.

All money is held as whole cents. Percentages of a cent are rounded half to
even, so results do not depend on the order loans arrive in.
"""

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import ROUND_HALF_EVEN, Decimal
from typing import Any

from engine.rules import (
    Between,
    Compare,
    ConcentrationRule,
    Const,
    FieldRef,
    Member,
    RuleSet,
    Subtract,
    Unique,
    YearOf,
    digest_of,
)

Loan = dict[str, Any]

INTEGER_FIELDS = ("original_term", "remaining_term", "payments_made", "fico", "model_year",
                  "days_past_due", "modification_count")
MONEY_FIELDS = ("original_balance", "current_balance")


def to_cents(amount: Decimal | str) -> int:
    return int((Decimal(amount) * 100).to_integral_value(rounding=ROUND_HALF_EVEN))


def _pct_of(amount: int, pct: Decimal) -> int:
    return int((amount * pct / 100).to_integral_value(rounding=ROUND_HALF_EVEN))


def _share(part: int, whole: int) -> Decimal:
    return round(Decimal(part) / Decimal(whole) * 100, 2) if whole else Decimal(0)


def _parse_date(raw: str) -> date:
    for pattern in ("%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(raw, pattern).date()
        except ValueError:
            continue
    raise ValueError(f"Unreadable date: {raw!r}")


def coerce_loan(row: dict[str, str]) -> Loan:
    """Turn one mapped tape row of strings into typed values."""
    loan: Loan = dict(row)
    for name in INTEGER_FIELDS:
        loan[name] = int(row[name])
    for name in MONEY_FIELDS:
        loan[name] = to_cents(row[name])
    loan["apr"] = Decimal(row["apr"])
    loan["origination_date"] = _parse_date(row["origination_date"])
    return loan


def _value(expr: FieldRef | Const | YearOf | Subtract, loan: Loan) -> Any:
    if isinstance(expr, FieldRef):
        return loan[expr.name]
    if isinstance(expr, Const):
        return expr.value
    if isinstance(expr, YearOf):
        return loan[expr.of.name].year
    return _value(expr.left, loan) - _value(expr.right, loan)


def _money_scaled(test: Compare, loan: Loan) -> tuple[Any, Any]:
    left, right = _value(test.left, loan), _value(test.right, loan)
    if isinstance(test.left, FieldRef) and test.left.name in MONEY_FIELDS:
        return left, to_cents(right)
    return left, right


def _passes(test: Compare | Between | Member | Unique, loan: Loan, lists: dict[str, Any],
            seen: dict[str, Counter[Any]]) -> bool:
    if isinstance(test, Compare):
        left, right = _money_scaled(test, loan)
        return {"<=": left <= right, "<": left < right, ">=": left >= right, ">": left > right,
                "==": left == right}[test.op]
    if isinstance(test, Between):
        return test.low <= _value(test.value, loan) <= test.high
    if isinstance(test, Member):
        return (loan[test.value.name] in lists[test.list]) != test.negate
    return seen[test.value.name][loan[test.value.name]] == 1


@dataclass(frozen=True)
class RuleOutcome:
    rule_id: str
    status: str  # "evaluated" or "not_evaluated"
    failed_loan_ids: tuple[str, ...] = ()
    failed_cents: int = 0
    reason: str | None = None


@dataclass(frozen=True)
class ConcentrationOutcome:
    rule_id: str
    active: bool
    limit_pct: Decimal
    limit_cents: int
    largest: str
    largest_cents: int
    share_pct: Decimal
    excess_cents: int
    excess_by_group: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True)
class RunResult:
    as_of: date
    ruleset_version: int
    ruleset_digest: str
    tape_digest: str
    gross_pool_cents: int
    eligible_pool_cents: int
    eligible_loan_ids: tuple[str, ...]
    failed_rules_by_loan: dict[str, tuple[str, ...]]
    rules: dict[str, RuleOutcome]
    concentrations: dict[str, ConcentrationOutcome]
    excess_cents: int
    advance_rate_pct: Decimal
    advance_rate_source: str
    reserve_cents: int
    borrowing_base_cents: int
    outstanding_advances_cents: int
    availability_cents: int
    provisional: bool

    @property
    def digest(self) -> str:
        return digest_of({
            "ruleset": self.ruleset_digest, "tape": self.tape_digest, "as_of": self.as_of,
            "eligible": self.eligible_loan_ids, "base": self.borrowing_base_cents,
            "excess": self.excess_cents, "rules": {
                rule_id: outcome.failed_loan_ids for rule_id, outcome in self.rules.items()
            },
        })


def tape_digest(loans: list[Loan]) -> str:
    return digest_of(sorted(loans, key=lambda loan: loan["loan_id"]))


def _group_key(rule: ConcentrationRule, loan: Loan, aliases: dict[str, str]) -> str:
    assert rule.group_by is not None
    value = str(loan[rule.group_by.name])
    return aliases.get(value, value) if rule.group_by.name == "dealer_name" else value


def _concentrations(eligible: list[Loan], pool: int, rules: RuleSet, as_of: date,
                    aliases: dict[str, str]) -> dict[str, ConcentrationOutcome]:
    """Apply limits in schedule order. Each excess dollar leaves one loan and is not recut."""
    remaining = {loan["loan_id"]: loan["current_balance"] for loan in eligible}
    results = {}
    for rule in rules.concentration:
        active = rule.effective_from is None or rule.effective_from <= as_of
        groups: defaultdict[str, list[Loan]] = defaultdict(list)
        for loan in eligible:
            if rule.group_by:
                groups[_group_key(rule, loan, aliases)].append(loan)
            elif rule.where and _passes(rule.where, loan, rules.lists, {}):
                groups[rule.plain_english].append(loan)

        def full(members: list[Loan]) -> int:
            return sum(loan["current_balance"] for loan in members)

        limit = _pct_of(pool, rule.limit_pct)
        excess_by_group: dict[str, int] = {}
        for name in sorted(groups):
            members = groups[name]
            excess = max(0, sum(remaining[loan["loan_id"]] for loan in members) - limit)
            if not active or not excess:
                continue
            excess_by_group[name] = excess
            # Largest balances first, then loan id, so the cut never depends on tape order.
            for loan in sorted(members, key=lambda m: (-remaining[m["loan_id"]], m["loan_id"])):
                taken = min(excess, remaining[loan["loan_id"]])
                remaining[loan["loan_id"]] -= taken
                excess -= taken

        largest = max(sorted(groups), key=lambda name: full(groups[name]), default="")
        largest_cents = full(groups[largest]) if groups else 0
        results[rule.id] = ConcentrationOutcome(
            rule_id=rule.id,
            active=active,
            limit_pct=rule.limit_pct,
            limit_cents=limit,
            largest=largest,
            largest_cents=largest_cents,
            share_pct=_share(largest_cents, pool),
            excess_cents=sum(excess_by_group.values()),
            excess_by_group=excess_by_group,
        )
    return results


def run(loans: list[Loan], rules: RuleSet, as_of: date, outstanding_advances_cents: int,
        dealer_aliases: dict[str, str] | None = None) -> RunResult:
    aliases = dealer_aliases or {}
    ordered = sorted(loans, key=lambda loan: loan["loan_id"])

    unique_fields = {rule.test.value.name for rule in rules.eligibility
                     if isinstance(rule.test, Unique)}
    seen = {name: Counter(loan[name] for loan in ordered) for name in unique_fields}

    runnable = []
    outcomes: dict[str, RuleOutcome] = {}
    for rule in rules.eligibility:
        test = rule.test
        if isinstance(test, Member) and rules.lists[test.list] is None:
            outcomes[rule.id] = RuleOutcome(rule.id, "not_evaluated",
                                            reason=f"List {test.list} has not been received")
        else:
            runnable.append(rule)

    failed: defaultdict[str, list[str]] = defaultdict(list)
    failed_rules: dict[str, tuple[str, ...]] = {}
    eligible = []
    for loan in ordered:
        hits = tuple(rule.id for rule in runnable
                     if not _passes(rule.test, loan, rules.lists, seen))
        for rule_id in hits:
            failed[rule_id].append(loan["loan_id"])
        if hits:
            failed_rules[loan["loan_id"]] = hits
        else:
            eligible.append(loan)

    balances = {loan["loan_id"]: loan["current_balance"] for loan in ordered}
    for rule in runnable:
        ids = tuple(failed[rule.id])
        outcomes[rule.id] = RuleOutcome(rule.id, "evaluated", ids,
                                        sum(balances[loan_id] for loan_id in ids))

    pool = sum(loan["current_balance"] for loan in eligible)
    concentrations = _concentrations(eligible, pool, rules, as_of, aliases)
    excess = sum(item.excess_cents for item in concentrations.values())

    rate = rules.advance_rate_on(as_of)
    reserve = _pct_of(pool, rules.reserve_pct)
    base = _pct_of(pool - excess, rate.pct) - reserve
    availability = min(base, rules.facility_limit_cents) - outstanding_advances_cents

    return RunResult(
        as_of=as_of,
        ruleset_version=rules.version,
        ruleset_digest=rules.digest,
        tape_digest=tape_digest(ordered),
        gross_pool_cents=sum(balances.values()),
        eligible_pool_cents=pool,
        eligible_loan_ids=tuple(loan["loan_id"] for loan in eligible),
        failed_rules_by_loan=failed_rules,
        rules={rule.id: outcomes[rule.id] for rule in rules.eligibility},
        concentrations=concentrations,
        excess_cents=excess,
        advance_rate_pct=rate.pct,
        advance_rate_source=rate.source,
        reserve_cents=reserve,
        borrowing_base_cents=base,
        outstanding_advances_cents=outstanding_advances_cents,
        availability_cents=availability,
        provisional=any(item.status == "not_evaluated" for item in outcomes.values()),
    )


def weighted_average(loans: list[Loan], loan_ids: tuple[str, ...], name: str) -> Decimal:
    """A derived pool figure, weighted by current balance."""
    chosen = set(loan_ids)
    members = [loan for loan in loans if loan["loan_id"] in chosen]
    weight = sum(loan["current_balance"] for loan in members)
    return sum(Decimal(loan[name]) * loan["current_balance"] for loan in members) / weight
