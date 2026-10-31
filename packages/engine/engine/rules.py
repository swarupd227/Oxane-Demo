"""The rule format.

Rules are data: a small closed set of node types, validated on load. Nothing is
ever passed to eval, so a rule drafted by a language model can only do what
these nodes allow, and it can only name fields in the platform catalogue.
"""

import hashlib
import json
from collections.abc import Iterator
from datetime import date
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

LOAN_FIELDS = frozenset({
    "loan_id", "vin", "origination_date", "first_payment_date", "original_balance",
    "current_balance", "apr", "original_term", "remaining_term", "payments_made", "fico",
    "obligor_state", "dealer_name", "model_year", "vehicle_condition", "days_past_due",
    "modification_count", "status",
})


class _Node(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class FieldRef(_Node):
    kind: Literal["field"] = "field"
    name: str


class Const(_Node):
    kind: Literal["const"] = "const"
    value: Decimal


class YearOf(_Node):
    kind: Literal["year_of"] = "year_of"
    of: FieldRef


class Subtract(_Node):
    kind: Literal["subtract"] = "subtract"
    left: "Expr"
    right: "Expr"


Expr = Annotated[FieldRef | Const | YearOf | Subtract, Field(discriminator="kind")]
Subtract.model_rebuild()


class Compare(_Node):
    kind: Literal["compare"] = "compare"
    op: Literal["<=", "<", ">=", ">", "=="]
    left: Expr
    right: Expr


class Between(_Node):
    kind: Literal["between"] = "between"
    value: Expr
    low: Decimal
    high: Decimal


class Member(_Node):
    kind: Literal["member"] = "member"
    value: FieldRef
    list: str
    negate: bool = False


class Unique(_Node):
    kind: Literal["unique"] = "unique"
    value: FieldRef


Test = Annotated[Compare | Between | Member | Unique, Field(discriminator="kind")]


class EligibilityRule(_Node):
    id: str
    plain_english: str
    clause_ref: str
    clause_text: str
    test: Test


class ConcentrationRule(_Node):
    id: str
    plain_english: str
    clause_ref: str
    clause_text: str
    limit_pct: Decimal
    effective_from: date | None = None
    group_by: FieldRef | None = None
    where: Test | None = None

    @model_validator(mode="after")
    def _one_bucket_kind(self) -> "ConcentrationRule":
        if (self.group_by is None) == (self.where is None):
            raise ValueError(f"{self.id} needs exactly one of group_by and where")
        return self


class AdvanceRate(_Node):
    pct: Decimal
    effective_from: date
    source: str


class RuleSet(_Node):
    version: int
    facility_limit_cents: int
    reserve_pct: Decimal
    advance_rates: tuple[AdvanceRate, ...]
    lists: dict[str, tuple[str, ...] | None]
    eligibility: tuple[EligibilityRule, ...]
    concentration: tuple[ConcentrationRule, ...]

    @model_validator(mode="after")
    def _references_resolve(self) -> "RuleSet":
        ids = [rule.id for rule in (*self.eligibility, *self.concentration)]
        if len(ids) != len(set(ids)):
            raise ValueError("Rule ids must be unique")
        for rule in self.eligibility:
            self._check_test(rule.id, rule.test)
        for rule in self.concentration:
            if rule.where:
                self._check_test(rule.id, rule.where)
            if rule.group_by:
                self._check_field(rule.id, rule.group_by)
        return self

    def _check_test(self, rule_id: str, test: Compare | Between | Member | Unique) -> None:
        if isinstance(test, Member) and test.list not in self.lists:
            raise ValueError(f"{rule_id} names an unknown list: {test.list}")
        for node in _fields_in(test):
            self._check_field(rule_id, node)

    @staticmethod
    def _check_field(rule_id: str, node: FieldRef) -> None:
        if node.name not in LOAN_FIELDS:
            raise ValueError(f"{rule_id} names an unknown field: {node.name}")

    @property
    def digest(self) -> str:
        return digest_of(self.model_dump(mode="json"))

    def advance_rate_on(self, as_of: date) -> AdvanceRate:
        active = [rate for rate in self.advance_rates if rate.effective_from <= as_of]
        if not active:
            raise ValueError(f"No advance rate in effect on {as_of}")
        return max(active, key=lambda rate: rate.effective_from)

    def with_threshold(self, rule_id: str, value: Decimal) -> "RuleSet":
        """Copy this rule set with one threshold changed, for previews and comparisons."""
        def changed(rule: EligibilityRule) -> EligibilityRule:
            if rule.id != rule_id:
                return rule
            if isinstance(rule.test, Compare) and isinstance(rule.test.right, Const):
                test = rule.test.model_copy(update={"right": Const(value=value)})
                return rule.model_copy(update={"test": test})
            raise ValueError(f"{rule_id} has no single threshold to change")

        if rule_id not in {rule.id for rule in self.eligibility}:
            raise ValueError(f"Unknown eligibility rule: {rule_id}")
        return self.model_copy(update={"eligibility": tuple(map(changed, self.eligibility))})

    def without_rules(self, rule_ids: set[str]) -> "RuleSet":
        kept = tuple(rule for rule in self.eligibility if rule.id not in rule_ids)
        return self.model_copy(update={"eligibility": kept})

    def with_list(self, name: str, values: tuple[str, ...]) -> "RuleSet":
        """Supply a list that was missing, such as Schedule 4 when it arrives."""
        return self.model_copy(update={"lists": {**self.lists, name: values}})


def _fields_in(node: object) -> Iterator[FieldRef]:
    if isinstance(node, FieldRef):
        yield node
    elif isinstance(node, BaseModel):
        for name in type(node).model_fields:
            yield from _fields_in(getattr(node, name))


def describe(test: Compare | Between | Member | Unique) -> str:
    """The test logic as analysts read it on the Rules screen."""
    if isinstance(test, Compare):
        return f"{_describe_expr(test.left)} {test.op} {_describe_expr(test.right)}"
    if isinstance(test, Between):
        return f"{test.low} <= {_describe_expr(test.value)} <= {test.high}"
    if isinstance(test, Member):
        return f"{test.value.name} {'not in' if test.negate else 'in'} {test.list}"
    return f"{test.value.name} appears once in the tape"


def _describe_expr(expr: FieldRef | Const | YearOf | Subtract) -> str:
    if isinstance(expr, FieldRef):
        return expr.name
    if isinstance(expr, Const):
        return f"{expr.value:,}" if expr.value == expr.value.to_integral() else str(expr.value)
    if isinstance(expr, YearOf):
        return f"year({expr.of.name})"
    return f"{_describe_expr(expr.left)} - {_describe_expr(expr.right)}"


def digest_of(value: object) -> str:
    canonical = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def load_ruleset(text: str) -> RuleSet:
    return RuleSet.model_validate_json(text)
