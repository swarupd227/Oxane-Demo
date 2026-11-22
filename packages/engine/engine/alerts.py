"""Covenant headroom, client alert rules and the comparison with the independent QC calculation.

Headroom is the distance from a test's value to its limit, in the test's own unit. An alert rule
is a structured condition on one facility metric; the model may draft one from a client's words,
but only this code decides whether it is valid and when it would have fired. A QC variance is
genuine unless it is one of the known presentation differences.
"""

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

# Headroom


@dataclass(frozen=True)
class Headroom:
    value: Decimal
    limit: Decimal
    direction: str  # "max": must stay at or below. "min": must stay at or above.
    headroom: Decimal  # positive while the test passes
    used_pct: Decimal  # how much of the room to the limit is used, for a bar
    passed: bool
    early_warning: bool
    trend: str  # "towards", "away" or "flat", against the prior value


def headroom(value: Decimal, limit: Decimal, direction: str, warning_band: Decimal,
             prior: Decimal | None = None) -> Headroom:
    room = (limit - value) if direction == "max" else (value - limit)
    passed = room >= 0
    used = (value / limit * 100) if direction == "max" and limit else (
        (limit / value * 100) if value else Decimal(100)
    )
    trend = "flat"
    if prior is not None and prior != value:
        closer = (value > prior) if direction == "max" else (value < prior)
        trend = "towards" if closer else "away"
    return Headroom(value, limit, direction, room, used.quantize(Decimal("0.1")), passed,
                    passed and (room <= warning_band or (trend == "towards" and room <= warning_band
                                                         * 2)), trend)


# Alert rules

OPERATORS = {">": lambda a, b: a > b, ">=": lambda a, b: a >= b, "<": lambda a, b: a < b,
             "<=": lambda a, b: a <= b}


@dataclass(frozen=True)
class AlertRule:
    facility: str
    metric: str
    operator: str
    threshold: Decimal


class InvalidRule(ValueError):
    """The drafted rule does not fit the facility, its metrics or the allowed operators."""


def check_rule(rule: AlertRule, catalogue: dict[str, dict[str, Any]], facilities: set[str]
               ) -> None:
    """`catalogue` maps "facility.metric" to the metric's unit and allowed range."""
    if rule.facility not in facilities:
        raise InvalidRule(f"{rule.facility} is not one of this client's facilities")
    entry = catalogue.get(f"{rule.facility}.{rule.metric}")
    if entry is None:
        raise InvalidRule(f"{rule.metric} is not a metric the platform holds for {rule.facility}")
    if rule.operator not in OPERATORS:
        raise InvalidRule(f"{rule.operator} is not an allowed comparison")
    low, high = (Decimal(str(v)) for v in entry["range"])
    if not low <= rule.threshold <= high:
        raise InvalidRule(f"A threshold of {rule.threshold} {entry['unit']} is outside the "
                          f"metric's range of {low} to {high}")


def back_test(rule: AlertRule, history: list[tuple[str, Decimal]]) -> list[tuple[str, Decimal,
                                                                                 bool]]:
    """Each past period, its value and whether the rule would have fired."""
    test = OPERATORS[rule.operator]
    return [(period, value, test(value, rule.threshold)) for period, value in history]


# QC comparison

CLASSES = {
    "agrees": "Agrees",
    "blank": "Presentation: blank against dash",
    "rounding": "Presentation: rounding",
    "sign": "Presentation: sign convention",
    "percent": "Presentation: per cent against decimal",
    "genuine": "Genuine variance",
}
BLANKS = (None, "", "-", "–", "—", "n/a")


def _num(value: Any) -> Decimal | None:
    if isinstance(value, str):
        value = value.replace(",", "").replace("US$", "").replace("%", "").strip()
        if value in BLANKS:
            return None
    try:
        return None if value is None else Decimal(str(value))
    except ArithmeticError:
        return None


def classify(platform: Any, qc: Any, unit: str) -> str:
    """One QC line: agreement, a presentation difference, or a genuine variance. Rounding means
    within a dollar for money and within 0.05 points for a percentage."""
    a, b = _num(platform), _num(qc)
    if a is None or b is None:
        both_empty = (a is None or a == 0) and (b is None or b == 0)
        return "blank" if both_empty else "genuine"
    if a == b:
        return "agrees"
    if a == -b:
        return "sign"
    if unit == "%" and (a == b * 100 or a * 100 == b):
        return "percent"
    tolerance = Decimal("1") if unit == "US$" else Decimal("0.05")
    if abs(a - b) < tolerance:
        return "rounding"
    return "genuine"
