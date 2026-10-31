"""Phase 2 is done when the engine matches the key on every rule and every total."""

from decimal import Decimal

import pytest
from conftest import ADVANCES, PERIOD_END, read_key

from engine.covenants import (
    CovenantTerms,
    Financials,
    delinquency_ratio,
    delinquency_trigger,
    evaluate_covenants,
    leverage_without_carve_out,
)
from engine.reconcile import bridge_borrowing_base, bridge_eligible_pool
from engine.run import run, to_cents, weighted_average

RULE_IDS = [f"E{number}" for number in range(1, 13) if number != 7]


def cents(amount: float) -> int:
    return to_cents(Decimal(str(amount)))


@pytest.mark.parametrize("rule_id", RULE_IDS)
def test_eligibility_rule_matches_the_key(system, rule_id):
    expected = read_key("rules")[rule_id]
    assert set(system.rules[rule_id].failed_loan_ids) == set(expected["loan_ids"])


def test_e7_is_not_evaluated_and_the_run_is_provisional(system):
    assert system.rules["E7"].status == "not_evaluated"
    assert read_key("rules")["E7"]["status"] == "not_evaluated"
    assert system.provisional


@pytest.mark.parametrize("rule_id", ["C1", "C2", "C3", "C4", "C5"])
@pytest.mark.parametrize("view,fixture", [("system_before_dealer_match", "system"),
                                          ("system_after_dealer_match", "matched")])
def test_concentration_rule_matches_the_key(view, fixture, rule_id, request):
    result = request.getfixturevalue(fixture).concentrations[rule_id]
    expected = read_key("calculation")[view]["concentrations"][rule_id]
    assert result.largest_cents == expected["amount_cents"]
    assert result.excess_cents == expected["excess_cents"]
    assert float(result.share_pct) == pytest.approx(expected["share_pct"], abs=0.011)


@pytest.mark.parametrize("view,fixture", [("system_before_dealer_match", "system"),
                                          ("system_after_dealer_match", "matched")])
def test_totals_match_the_key(view, fixture, request):
    result = request.getfixturevalue(fixture)
    expected = read_key("calculation")[view]
    assert result.gross_pool_cents == cents(expected["gross_pool"])
    assert result.eligible_pool_cents == cents(expected["eligible_pool"])
    assert result.excess_cents == cents(expected["excess_concentration"])
    assert result.reserve_cents == cents(expected["reserve"])
    assert result.borrowing_base_cents == cents(expected["borrowing_base"])
    assert result.availability_cents == cents(expected["availability"])


def test_bridge_explains_the_whole_gap(loans, rules, system, certificate):
    bridge = bridge_eligible_pool(loans, rules, system, certificate, PERIOD_END)
    expected = read_key("calculation")["eligible_pool_bridge"]
    exceptions = read_key("exceptions")

    assert bridge.reproduces_certificate
    assert bridge.unexplained_cents == 0
    assert bridge.gap_cents == cents(expected["total_gap"])

    lines = {line.rule_id: line for line in bridge.lines}
    assert set(lines) == {"E1", "E12"}
    assert set(lines["E1"].loan_ids) == set(exceptions["X4"]["loan_ids"])
    assert lines["E1"].amount_cents == cents(exceptions["X4"]["amount"])
    vin_loans = {loan for item in exceptions["X5"]["clusters"] for loan in item["loan_ids"]}
    assert set(lines["E12"].loan_ids) == vin_loans


def test_base_bridge_sums_exactly(loans, rules, matched, certificate):
    bridge = bridge_eligible_pool(loans, rules, matched, certificate, PERIOD_END)
    result = bridge_borrowing_base(bridge, matched, certificate)
    assert result.borrower_cents + sum(amount for _, amount in result.lines) == result.system_cents
    assert any(label == "Excess concentration" for label, _ in result.lines)


def test_certificate_availability_matches_the_engine_replay(loans, rules, certificate):
    from engine.reconcile import borrower_rules

    replay = run(loans, borrower_rules(rules, certificate), PERIOD_END, ADVANCES)
    assert replay.borrowing_base_cents == certificate.borrowing_base_cents
    assert replay.availability_cents == certificate.availability_cents


def test_weighted_average_apr_matches_the_key(loans, system):
    value = weighted_average(loans, system.eligible_loan_ids, "apr")
    assert float(value) == pytest.approx(read_key("exceptions")["X8"]["value_pct"], abs=0.0001)


def test_delinquency_trigger_matches_the_key(loans):
    x7 = read_key("exceptions")["X7"]
    april = delinquency_ratio(loans)
    assert float(april) == x7["delinquency_ratio_pct"]["april"]
    result = delinquency_trigger((Decimal("0.71"), Decimal("0.76"), april), Decimal("6.0"))
    assert float(result.average_pct) == x7["three_month_average_pct"]
    assert not result.tripped


def test_covenants_match_the_key():
    figures = Financials(58000, 6000, 3500, 2000, 12000, 320800, 12600)
    terms = CovenantTerms(40000, Decimal("6.0"), 10000, 15000)
    worth, leverage, liquidity = evaluate_covenants(figures, terms)
    x10 = read_key("exceptions")["X10"]
    assert worth.value == x10["tangible_net_worth_k"] and worth.passed
    assert float(leverage.value) == x10["leverage_with_carve_out"] and leverage.passed
    assert float(leverage_without_carve_out(figures)) == x10["leverage_without_carve_out"]
    assert liquidity.passed


def test_availability_falls_below_the_lender_alert_after_the_match(system, matched):
    assert system.availability_cents > 50_000_000 > matched.availability_cents > 0
