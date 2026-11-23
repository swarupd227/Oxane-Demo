"""Rules for a new facility: checked drafts become an engine rule set, with every threshold from
the approved terms or from the clause the rule quotes."""

from datetime import date
from decimal import Decimal
from typing import Any

from engine.generic import FIELDS, STATUSES
from engine.rules import (
    AdvanceRate,
    Between,
    Compare,
    ConcentrationRule,
    Const,
    EligibilityRule,
    FieldRef,
    Member,
    RuleSet,
    Unique,
    describe,
)

from app.deals.checks import cite, figures, figures_in_quote, iso
from app.pipeline.documents import PdfDocument

TEST_KINDS = ("max", "min", "below", "above", "between", "in_list", "not_in_list", "not_status",
              "unique")
SINCE_ALWAYS = date(2000, 1, 1)


def check_test(test: dict[str, Any]) -> str | None:
    kind, field = test.get("kind"), test.get("field")
    if kind not in TEST_KINDS:
        return "Unknown test"
    if field not in FIELDS:
        return f"{field} is not a tape field"
    numeric = FIELDS[field][0] in ("money", "rate", "int")
    if kind in ("max", "min", "below", "above", "between") and not numeric:
        return f"{field} is not a number"
    if kind in ("max", "below", "between") and test.get("high") is None:
        return "No upper limit"
    if kind in ("min", "above", "between") and test.get("low") is None:
        return "No lower limit"
    if kind in ("in_list", "not_in_list") and not test.get("values"):
        return "No values listed"
    if kind == "not_status":
        if field != "status":
            return "A status test must be on status"
        bad = [v for v in test.get("values", []) if v not in STATUSES]
        if bad or not test.get("values"):
            return "Statuses must be standard statuses"
    return None


def limits_of(test: dict[str, Any]) -> list[float]:
    return [v for v in (test.get("low"), test.get("high")) if v is not None]


def verify_rule(rule: dict[str, Any], documents: dict[str, PdfDocument],
                concentration: bool) -> dict[str, Any]:
    """Find the clause on its page and check each threshold is a figure the clause states."""
    problem = None
    test = rule.get("where") if concentration else rule.get("test")
    if concentration:
        if not 0 < float(rule.get("limit_pct") or 0) <= 100:
            problem = "Limit must be a percentage"
        elif (rule.get("group_by") is None) == (test is None):
            problem = "Needs either a field to group by or a bucket test"
        elif rule.get("group_by") and rule["group_by"] not in FIELDS:
            problem = f"{rule['group_by']} is not a tape field"
        elif test:
            problem = check_test(test)
    else:
        problem = check_test(test or {})
    found = cite(documents, rule.get("document", ""), rule.get("clause_text", ""))
    if problem is None and found is None:
        problem = "Clause not found in the document"
    clause = rule.get("clause_text", "")
    stated = figures(clause)
    wanted = [Decimal(str(v)) for v in limits_of(test or {})]
    if concentration:
        wanted.append(Decimal(str(rule.get("limit_pct"))))
    if problem is None:
        for value in wanted:
            # "more than 30 days" is coded as max 30; a lower bound of 600 may read "600".
            if not any(value == g for g in stated):
                problem = f"Threshold {value.normalize():f} is not stated in the clause"
                break
    for value in (test or {}).get("values", []) if (test or {}).get("kind") in (
            "in_list", "not_in_list") else []:
        if problem is None and value.lower() not in clause.lower():
            problem = f"{value} is not in the clause"
    return {**rule, "page": found["page"] if found else None,
            "rects": found["rects"] if found else [], "verified": problem is None,
            "problem": problem}


def _test_node(rule_id: str, test: dict[str, Any], lists: dict[str, tuple[str, ...] | None]
               ) -> Any:
    field = FieldRef(name=test["field"])
    kind = test["kind"]
    if kind == "max":
        return Compare(op="<=", left=field, right=Const(value=Decimal(str(test["high"]))))
    if kind == "min":
        return Compare(op=">=", left=field, right=Const(value=Decimal(str(test["low"]))))
    if kind == "below":
        return Compare(op="<", left=field, right=Const(value=Decimal(str(test["high"]))))
    if kind == "above":
        return Compare(op=">", left=field, right=Const(value=Decimal(str(test["low"]))))
    if kind == "between":
        return Between(value=field, low=Decimal(str(test["low"])),
                       high=Decimal(str(test["high"])))
    if kind == "unique":
        return Unique(value=field)
    name = f"{rule_id.lower()}_values"
    lists[name] = tuple(test["values"])
    return Member(value=field, list=name, negate=kind in ("not_in_list", "not_status"))


def describe_rule(rule: dict[str, Any], concentration: bool) -> str:
    try:
        lists: dict[str, tuple[str, ...] | None] = {}
        if concentration:
            if rule.get("group_by"):
                return f"largest {rule['group_by']} group <= {rule['limit_pct']}% of eligible pool"
            return (f"{describe(_test_node(rule['id'], rule['where'], lists))} <= "
                    f"{rule['limit_pct']}% of eligible pool")
        return describe(_test_node(rule["id"], rule["test"], lists))
    except (KeyError, TypeError, ValueError):
        return ""


def build_ruleset(terms: dict[str, Any], rules: dict[str, Any], version: int = 1) -> RuleSet:
    """The engine's rule set. Facility limit, advance rate and reserve come from approved terms."""
    lists: dict[str, tuple[str, ...] | None] = {}
    eligibility = tuple(
        EligibilityRule(id=r["id"], plain_english=r["plain_english"], clause_ref=r["ref"],
                        clause_text=r["clause_text"], test=_test_node(r["id"], r["test"], lists))
        for r in rules["eligibility"])
    concentration = tuple(
        ConcentrationRule(
            id=r["id"], plain_english=r["plain_english"], clause_ref=r["ref"],
            clause_text=r["clause_text"], limit_pct=Decimal(str(r["limit_pct"])),
            effective_from=date.fromisoformat(r["effective_from"]) if iso(
                r.get("effective_from")) else None,
            group_by=FieldRef(name=r["group_by"]) if r.get("group_by") else None,
            where=_test_node(r["id"], r["where"], lists) if r.get("where") else None)
        for r in rules["concentration"])
    rate = terms["advance_rate"]
    rates = []
    source = f"{rate.get('doc_name', '')} p.{rate.get('page') or '-'}"
    original = rate.get("original")
    if original and rate.get("effective_from") and original.get("typed"):
        rates.append(AdvanceRate(pct=Decimal(original["typed"]), effective_from=SINCE_ALWAYS,
                                 source=f"{original.get('doc_name', '')} p.{original.get('page')}"))
        rates.append(AdvanceRate(pct=Decimal(rate["typed"]),
                                 effective_from=date.fromisoformat(rate["effective_from"]),
                                 source=source))
    else:
        rates.append(AdvanceRate(pct=Decimal(rate["typed"]), effective_from=SINCE_ALWAYS,
                                 source=source))
    reserve = terms.get("reserve") or {}
    return RuleSet(
        version=version,
        facility_limit_cents=int(terms["commitment"]["typed"]) * 100,
        reserve_pct=Decimal(reserve["typed"]) if reserve.get("typed") is not None else Decimal(0),
        advance_rates=tuple(rates), lists=lists, eligibility=eligibility,
        concentration=concentration)


def rule_fields(rules: dict[str, Any]) -> set[str]:
    used = set()
    for rule in rules.get("eligibility", []):
        used.add(rule["test"]["field"])
    for rule in rules.get("concentration", []):
        if rule.get("group_by"):
            used.add(rule["group_by"])
        if rule.get("where"):
            used.add(rule["where"]["field"])
    return used


__all__ = ["figures_in_quote"]
