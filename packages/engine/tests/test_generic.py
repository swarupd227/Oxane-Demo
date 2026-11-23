from datetime import date
from decimal import Decimal

import pytest

from engine import generic
from engine.rules import AdvanceRate, Compare, Const, EligibilityRule, FieldRef, RuleSet
from engine.run import run

STATUS = {"CURRENT": "performing", "LATE": "arrears", "CO": "charged_off", "PAID": "paid_off"}


def loan(ident, balance, dpd=0, status="CURRENT", score="700"):
    return generic.coerce({"loan_id": ident, "current_balance": balance, "days_past_due": str(dpd),
                           "status": status, "credit_score": score}, STATUS)


def test_coerce_types_and_maps_status():
    row = generic.coerce({"loan_id": "A1", "current_balance": "1,234.56", "apr": "9.5",
                          "origination_date": "03/15/2026", "days_past_due": "0",
                          "status": "LATE"}, STATUS)
    assert row["current_balance"] == 123456 and row["apr"] == Decimal("9.5")
    assert row["origination_date"] == date(2026, 3, 15) and row["status"] == "arrears"
    with pytest.raises(generic.CoercionError):
        generic.coerce({"loan_id": "A", "current_balance": "abc"}, STATUS)


def test_delinquency_ratio_excludes_closed_loans():
    loans = [loan("A", "100"), loan("B", "100", 60, "LATE"), loan("C", "500", 150, "CO")]
    assert generic.delinquency_ratio(loans, 60) == Decimal("50.00")


def test_roll_forward_finds_the_missing_loan_and_closes_the_gap():
    prior = [loan("A", "100"), loan("B", "200"), loan("C", "300")]
    current = [loan("A", "90"), loan("B", "0", status="CO"), loan("D", "50")]
    roll = generic.roll_forward(prior, current, 1000)
    assert roll.missing_loan_ids == ("C",) and roll.missing_cents == 30000
    assert roll.charge_offs_cents == 20000 and roll.new_cents == 5000
    assert roll.expected_cents == 60000 + 5000 - 1000 - 20000
    assert roll.gap_cents == roll.expected_cents - 14000
    assert generic.roll_forward(prior, current, None).gap_cents is None


def test_the_rule_engine_runs_on_standard_fields():
    rules = RuleSet(version=1, facility_limit_cents=10**9, reserve_pct=Decimal(0),
                    advance_rates=(AdvanceRate(pct=Decimal("80"), effective_from=date(2000, 1, 1),
                                               source="test"),),
                    lists={}, concentration=(),
                    eligibility=(EligibilityRule(
                        id="E1", plain_english="", clause_ref="", clause_text="",
                        test=Compare(op=">=", left=FieldRef(name="credit_score"),
                                     right=Const(value=Decimal(600)))),))
    result = run([loan("A", "100", score="650"), loan("B", "100", score="590")], rules,
                 date(2026, 9, 30), 0)
    assert result.eligible_loan_ids == ("A",) and result.borrowing_base_cents == 8000


def test_duplicate_ids_reports_rows():
    assert generic.duplicate_ids([{"loan_id": "A"}, {"loan_id": "B"}, {"loan_id": "A"}]) == {
        "A": [1, 3]}
