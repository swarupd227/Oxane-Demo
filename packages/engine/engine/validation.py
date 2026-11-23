"""Validate a loaded file before anything is calculated from it.

The six rule families come from the client's validation set: missing data, duplicates, reference
data, data types, logical constraints and change against the prior period. Each rule is either
blocking, which holds the facility's load until an analyst resolves it, or a warning, which is
logged. Rows are mapped tape rows of strings, as they arrive; nothing here reads a file.
"""

from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any

Row = dict[str, Any]
FAMILIES = ("missing_data", "duplicates", "reference_data", "data_types", "logical", "prior_period")
CLOSED = frozenset({"CHARGED_OFF", "PAID_OFF", "REPURCHASED"})
FAMILY_NAMES = {
    "missing_data": "Missing data",
    "duplicates": "Duplicates",
    "reference_data": "Reference data",
    "data_types": "Data types",
    "logical": "Logical constraints",
    "prior_period": "Change against prior period",
}


@dataclass(frozen=True)
class Rule:
    id: str
    family: str
    severity: str  # "blocking" or "warning"
    text: str
    field: str = ""
    kind: str = ""  # data types: "number", "integer" or "date"; logical: a check name
    allowed: tuple[str, ...] = ()


@dataclass(frozen=True)
class Failure:
    key: str
    value: str
    row: int  # one-based line in the file, after the header


@dataclass
class RuleResult:
    rule: Rule
    checked: int
    failures: list[Failure] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not self.failures


def _blank(value: Any) -> bool:
    return value is None or str(value).strip() == ""


def _number(value: str) -> Decimal | None:
    try:
        return Decimal(str(value).replace(",", ""))
    except InvalidOperation:
        return None


def _is_type(value: str, kind: str) -> bool:
    if _blank(value):
        return True  # a blank is a missing-data question, not a type error
    if kind == "number":
        return _number(value) is not None
    if kind == "integer":
        return str(value).strip().lstrip("-").isdigit()
    if kind == "date":
        return _date(value) is not None
    raise ValueError(f"Unknown data type {kind}")


def _date(value: str) -> date | None:
    for pattern in ("%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(str(value).strip(), pattern).date()
        except ValueError:
            continue
    return None


def _not_above_original(row: Row) -> bool:
    current, original = _number(row.get("current_balance", "")), _number(
        row.get("original_balance", "")
    )
    return current is None or original is None or current <= original


def _matures_after_origination(row: Row) -> bool:
    start, end = _date(row.get("origination_date", "")), _date(row.get("maturity_date", ""))
    return start is None or end is None or end > start


def _charge_off_has_amount(row: Row) -> bool:
    return row.get("status") != "CHARGED_OFF" or not _blank(row.get("charge_off_amount"))


def _price_in_range(row: Row) -> bool:
    price = _number(row.get("bid", ""))
    return price is None or Decimal(0) < price <= Decimal(110)


def _not_above_commitment(field_name: str) -> Callable[[Row], bool]:
    def check(row: Row) -> bool:
        value, commitment = _number(row.get(field_name, "")), _number(row.get("commitment", ""))
        return value is None or commitment is None or value <= commitment

    return check


LOGICAL: dict[str, Callable[[Row], bool]] = {
    "balance_not_above_original": _not_above_original,
    "matures_after_origination": _matures_after_origination,
    "charge_off_has_amount": _charge_off_has_amount,
    "price_in_range": _price_in_range,
    "outstanding_not_above_commitment": _not_above_commitment("outstanding"),
    "uncalled_not_above_commitment": _not_above_commitment("uncalled"),
}


def _row_passes(rule: Rule, row: Row, value: Any) -> bool:
    if rule.family == "missing_data":
        return not _blank(value)
    if rule.family == "reference_data":
        return _blank(value) or value in rule.allowed
    if rule.family == "data_types":
        return _is_type(value, rule.kind)
    if rule.family == "logical":
        return LOGICAL[rule.kind](row)
    raise ValueError(f"Unknown rule family {rule.family}")


def validate(rows: list[Row], rules: list[Rule], key: str) -> list[RuleResult]:
    """Run every rule except change against prior period, which needs two periods."""
    results = []
    for rule in rules:
        if rule.family == "prior_period":
            continue
        result = RuleResult(rule, len(rows))
        if rule.family == "duplicates":
            # kind "live": only loans still in the pool count, so a loan repurchased this month
            # does not clash with the loan that replaced it.
            def counted(row: Row, rule: Rule = rule) -> bool:
                return rule.kind != "live" or row.get("status") not in CLOSED

            counts = Counter(row.get(rule.field or key, "") for row in rows if counted(row))
            for index, row in enumerate(rows, start=1):
                value = row.get(rule.field or key, "")
                if counted(row) and counts[value] > 1:
                    result.failures.append(Failure(row.get(key, ""), str(value), index))
        else:
            for index, row in enumerate(rows, start=1):
                value = row.get(rule.field, "")
                if not _row_passes(rule, row, value):
                    result.failures.append(Failure(row.get(key, ""), str(value), index))
        results.append(result)
    return results


def exact_duplicates(rows: list[Row], key: str) -> tuple[list[Row], list[str]]:
    """Rows repeated exactly, field for field, collapse to one. Rows that share a key but differ
    are left alone: only someone who can ask the sender may choose between them."""
    seen: dict[str, Row] = {}
    kept, collapsed = [], []
    for row in rows:
        previous = seen.get(row.get(key, ""))
        if previous is not None and previous == row:
            collapsed.append(row[key])
            continue
        seen.setdefault(row.get(key, ""), row)
        kept.append(row)
    return kept, collapsed


# Change against the prior period


def _weighted(rows: list[Row], field_name: str) -> Decimal:
    total = sum(_number(r["current_balance"]) or 0 for r in rows)
    if not total:
        return Decimal(0)
    weighted = sum(
        (_number(r["current_balance"]) or 0) * (_number(r.get(field_name, "")) or 0) for r in rows
    )
    return (Decimal(weighted) / Decimal(total)).quantize(Decimal("0.01"), ROUND_HALF_UP)


def pool_metrics(rows: list[Row]) -> dict[str, Decimal]:
    """The pool-level figures a period is compared on, from loans still in the pool."""
    pool = [r for r in rows if r.get("status") not in CLOSED]
    return {
        "pool_balance": Decimal(sum(_number(r["current_balance"]) or 0 for r in pool)).quantize(
            Decimal("0.01")
        ),
        "live_loans": Decimal(len(pool)),
        "weighted_apr": _weighted(pool, "apr"),
        "weighted_fico": _weighted(pool, "fico"),
        "weighted_remaining_term": _weighted(pool, "remaining_term"),
    }


@dataclass(frozen=True)
class Change:
    metric: str
    prior: Decimal
    current: Decimal
    change: Decimal  # per cent for "pct" thresholds, points or units for "abs"
    threshold: Decimal
    basis: str  # "pct" or "abs"
    flagged: bool


def prior_period(current: dict[str, Decimal], prior: dict[str, Decimal],
                 thresholds: dict[str, tuple[str, Decimal]]) -> list[Change]:
    """Each metric's move against the prior period, flagged when it moves more than its limit."""
    changes = []
    for metric, (basis, limit) in thresholds.items():
        before, now = prior[metric], current[metric]
        if basis == "pct":
            move = ((now / before - 1) * 100).quantize(Decimal("0.01"), ROUND_HALF_UP) if before \
                else Decimal(0)
        else:
            move = (now - before).quantize(Decimal("0.01"), ROUND_HALF_UP)
        changes.append(Change(metric, before, now, move, limit, basis, abs(move) > limit))
    return changes


def blocking(results: list[RuleResult]) -> list[RuleResult]:
    return [r for r in results if r.rule.severity == "blocking" and not r.passed]
