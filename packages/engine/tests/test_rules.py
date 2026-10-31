import random
import time
from datetime import date
from decimal import Decimal

import pytest
from conftest import ADVANCES, PERIOD_END, RULESET
from pydantic import ValidationError

from engine.reconcile import impact
from engine.rules import RuleSet, describe, load_ruleset
from engine.run import run


def clean_loan(number: int = 1, **changes):
    loan = {
        "loan_id": f"L{number:05d}", "vin": f"VIN{number}", "current_balance": 2_000_000,
        "original_balance": 2_500_000, "apr": Decimal("12.50"), "original_term": 60,
        "remaining_term": 40, "payments_made": 20, "fico": 620, "obligor_state": "TX",
        "dealer_name": f"Dealer {number}", "model_year": 2022, "vehicle_condition": "NEW",
        "days_past_due": 0, "modification_count": 0, "status": "ACTIVE",
        "origination_date": date(2024, 6, 1),
    }
    return {**loan, **changes}


def failed(rules: RuleSet, **changes) -> set[str]:
    loans = [clean_loan(**changes), clean_loan(2)]
    result = run(loans, rules, PERIOD_END, 0)
    return set(result.failed_rules_by_loan.get("L00001", ()))


@pytest.mark.parametrize("changes,rule", [
    ({"days_past_due": 31}, "E1"),
    ({"status": "CHARGED_OFF"}, "E2"),
    ({"status": "REPO"}, "E2"),
    ({"original_term": 85}, "E3"),
    ({"fico": 539}, "E4"),
    ({"current_balance": 7_500_001}, "E5"),
    ({"obligor_state": "PR"}, "E6"),
    ({"modification_count": 2}, "E8"),
    ({"apr": Decimal("5.99")}, "E9"),
    ({"apr": Decimal("30.00")}, "E9"),
    ({"model_year": 2013}, "E10"),
    ({"payments_made": 0}, "E11"),
])
def test_rule_fails_just_past_its_boundary(rules, changes, rule):
    assert failed(rules, **changes) == {rule}


@pytest.mark.parametrize("changes", [
    {"days_past_due": 30},
    {"original_term": 84},
    {"fico": 540},
    {"current_balance": 7_500_000},
    {"modification_count": 1},
    {"apr": Decimal("6.00")},
    {"apr": Decimal("29.99")},
    {"model_year": 2014},
    {"payments_made": 1},
])
def test_rule_passes_exactly_on_its_boundary(rules, changes):
    assert failed(rules, **changes) == set()


def test_a_shared_vin_fails_every_loan_that_uses_it(rules):
    result = run([clean_loan(1, vin="X"), clean_loan(2, vin="X")], rules, PERIOD_END, 0)
    assert set(result.rules["E12"].failed_loan_ids) == {"L00001", "L00002"}
    assert result.eligible_pool_cents == 0  # An empty pool must not break the share maths.


def test_advance_rate_follows_the_effective_date(rules):
    assert rules.advance_rate_on(date(2026, 2, 28)).pct == 85
    assert rules.advance_rate_on(date(2026, 3, 1)).pct == Decimal("82.5")


def test_fico_limit_does_not_apply_before_the_amendment(rules):
    loans = [clean_loan(number, fico=580, obligor_state=f"S{number % 9}")
             for number in range(30)]
    relaxed = rules.with_list("us_states", tuple(f"S{i}" for i in range(9)))
    before = run(loans, relaxed, date(2026, 2, 28), 0).concentrations["C4"]
    after = run(loans, relaxed, date(2026, 3, 1), 0).concentrations["C4"]
    assert not before.active and before.excess_cents == 0
    assert after.active and after.excess_cents > 0


def test_supplying_schedule_4_runs_e7_and_clears_provisional(loans, rules):
    result = run(loans, rules.with_list("schedule_4", ("NY", "VT")), PERIOD_END, ADVANCES)
    assert result.rules["E7"].status == "evaluated"
    assert not result.provisional


def test_an_amount_cut_once_is_not_cut_again(rules):
    """One dealer in one state breaches both limits, and the second cut sees the first."""
    breaching = [clean_loan(number, dealer_name="Big", obligor_state="TX", current_balance=100_000)
                 for number in range(30)]
    others = [clean_loan(number, dealer_name=f"D{number}", obligor_state=f"S{number % 9}",
                         current_balance=100_000) for number in range(30, 100)]
    allowed = rules.with_list("us_states", ("TX", *(f"S{i}" for i in range(9))))
    result = run([*breaching, *others], allowed, PERIOD_END, 0)
    state, dealer = result.concentrations["C1"], result.concentrations["C2"]
    assert state.excess_cents == 1_000_000  # 30% against a 20% limit.
    assert dealer.excess_cents == 1_500_000  # 20% left against a 5% limit, not 30%.
    assert result.excess_cents == 2_500_000


def test_same_input_gives_the_same_result(loans, rules):
    first = run(loans, rules, PERIOD_END, ADVANCES)
    shuffled = list(loans)
    random.Random(7).shuffle(shuffled)
    second = run(shuffled, rules, PERIOD_END, ADVANCES)
    assert first.digest == second.digest
    assert first.borrowing_base_cents == second.borrowing_base_cents


def test_changing_a_threshold_changes_the_digest_but_not_the_original(loans, rules):
    before = run(loans, rules, PERIOD_END, ADVANCES)
    edited = rules.with_threshold("E1", Decimal(60))
    after = run(loans, edited, PERIOD_END, ADVANCES)
    assert before.digest != after.digest
    assert rules.digest != edited.digest
    assert run(loans, rules, PERIOD_END, ADVANCES).digest == before.digest


def test_impact_preview_shows_what_an_edit_would_change(loans, rules, system):
    preview = impact(system, run(loans, rules.with_threshold("E1", Decimal(60)), PERIOD_END,
                                 ADVANCES))
    assert len(preview.newly_eligible) == 41
    assert not preview.newly_ineligible
    assert preview.eligible_pool_change_cents > 0


def test_a_rerun_is_fast_enough_for_the_stage(loans, rules):
    started = time.perf_counter()
    run(loans, rules, PERIOD_END, ADVANCES)
    assert time.perf_counter() - started < 1


def test_test_logic_reads_like_the_spec(rules):
    logic = {rule.id: describe(rule.test) for rule in rules.eligibility}
    assert logic["E1"] == "days_past_due <= 30"
    assert logic["E5"] == "current_balance <= 75,000"
    assert logic["E9"] == "6.00 <= apr <= 29.99"
    assert logic["E10"] == "year(origination_date) - model_year <= 10"
    assert logic["E12"] == "vin appears once in the tape"


def test_there_are_17_rules(rules):
    assert len(rules.eligibility) == 12 and len(rules.concentration) == 5


@pytest.mark.parametrize("change,message", [
    (lambda text: text.replace('"name": "days_past_due"', '"name": "os.system"'), "unknown field"),
    (lambda text: text.replace('"list": "schedule_4"', '"list": "nope"'), "unknown list"),
    (lambda text: text.replace('"kind": "compare"', '"kind": "eval"', 1), "union_tag_invalid"),
])
def test_a_bad_rule_set_is_rejected_on_load(change, message):
    text = RULESET.read_text(encoding="utf-8")
    assert change(text) != text
    with pytest.raises(ValidationError, match=message):
        load_ruleset(change(text))
