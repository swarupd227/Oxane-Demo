"""The monitoring checks, run on the generated May cycle, must match the cycle answer key."""

import csv
import json
from datetime import date
from decimal import Decimal

import pytest
from conftest import OUTPUT, read_key

from engine.covenants import delinquency_ratio
from engine.monitoring import (
    CLOSED,
    TermVersion,
    charge_offs,
    duplicate_collateral,
    in_force,
    leverage,
    loan_to_value,
    position_concentration,
    roll_forward,
    rolling_trigger,
    seasonal,
    stale_valuations,
    what_if,
    within_tolerance,
)
from engine.rules import RuleSet
from engine.run import coerce_loan, run, to_cents

CYCLE = OUTPUT / "cycle"
SUNRISE = {"Sunrise Motors": "Sunrise Motors LLC"}

# Northmoor's columns as the platform mapped them when the facility was onboarded.
NORTHMOOR = {
    "Acct_No": "loan_id", "Vehicle_VIN": "vin", "Principal_Bal": "current_balance",
    "Days_Delinq": "days_past_due", "Status_Cd": "status", "CO_Amt": "charge_off_amount",
}

pytestmark = pytest.mark.skipif(not (OUTPUT / "cycle-key" / "key.json").exists(),
                                reason="The cycle kit has not been built")


@pytest.fixture(scope="module")
def key() -> dict:
    return json.loads((OUTPUT / "cycle-key" / "key.json").read_text(encoding="utf-8"))


def _light(row: dict[str, str]) -> dict:
    """The fields monitoring needs, typed: money in cents."""
    return {
        "loan_id": row["loan_id"], "vin": row["vin"], "status": row["status"],
        "current_balance": to_cents(row["current_balance"] or "0"),
        "days_past_due": int(row["days_past_due"] or 0),
        "charge_off_amount": (to_cents(row["charge_off_amount"])
                              if row["charge_off_amount"] else None),
    }


def _tape(path, columns: dict[str, str]) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return [{columns[k]: v for k, v in row.items() if k in columns}
                for row in csv.DictReader(handle)]


@pytest.fixture(scope="module")
def bramble_columns() -> dict[str, str]:
    return read_key("mapping")["columns"]


@pytest.fixture(scope="module")
def april(bramble_columns) -> list[dict]:
    return [_light(r) for r in _tape(OUTPUT / "pack" / read_key("pack")["loan_tape"],
                                     bramble_columns)]


@pytest.fixture(scope="module")
def may_raw(bramble_columns) -> list[dict[str, str]]:
    return _tape(CYCLE / "bramble" / "BAF_Loan_Tape_2026-05.csv", bramble_columns)


@pytest.fixture(scope="module")
def may(may_raw) -> list[dict]:
    return [_light(r) for r in may_raw]


def _northmoor(month: str) -> list[dict]:
    return [_light(r) for r in _tape(CYCLE / "northmoor" / f"NMC_Tape_2026-{month}.csv", NORTHMOOR)]


def test_roll_forward_finds_the_gap_and_the_missing_loans(april, may, key):
    expected = key["checks"]["roll_forward"]
    result = roll_forward(april, may, to_cents(str(expected["principal_collected"])))
    assert result.opening_cents == to_cents(str(expected["opening"]))
    assert result.additions_cents == to_cents(str(expected["additions"]))
    assert result.gap_cents == to_cents(str(expected["gap"]))
    assert list(result.missing_loan_ids) == key["issues"]["M2"]["loans"]


def test_charge_off_schedule_names_the_nine_loans(may, key):
    on_tape = {r["loan_id"]: r["charge_off_amount"] for r in may if r["status"] == "CHARGED_OFF"}
    balances = {r["loan_id"]: r["current_balance"] for r in may}
    reported = on_tape | {loan: balances[loan] for loan in key["issues"]["M3"]["loans"]}
    result = charge_offs(may, reported)
    assert sorted(result.only_in_report) == sorted(key["issues"]["M3"]["loans"])
    assert result.difference_cents == to_cents(str(key["checks"]["charge_offs"]["difference"]))


def test_may_uses_the_terms_in_force_before_amendment_2():
    versions = [
        TermVersion("Credit Agreement", date(2026, 1, 15), {"limit": 250, "dealer": 5}, "2.1"),
        TermVersion("Amendment No. 1", date(2026, 3, 1), {"limit": 250, "dealer": 5}, "2(a)"),
        TermVersion("Amendment No. 2", date(2026, 6, 1), {"limit": 300, "dealer": 7}, "2(a)"),
    ]
    assert in_force(versions, date(2026, 5, 31)).label == "Amendment No. 1"
    assert in_force(versions, date(2026, 6, 30)).label == "Amendment No. 2"


def test_bramble_borrowing_base_matches_the_key_and_the_certificate(may_raw, rules: RuleSet, key):
    loans = [coerce_loan(r) for r in may_raw if r["status"] not in ("PAID_OFF", "REPURCHASED")]
    result = run(loans, rules, date(2026, 5, 31), 5_050_000_000, dealer_aliases=SUNRISE)
    expected = key["checks"]["bramble_borrowing_base"]
    assert result.eligible_pool_cents == to_cents(str(expected["system"]["eligible_pool"]))
    assert result.borrowing_base_cents == to_cents(str(expected["system"]["borrowing_base"]))
    stated = Decimal(str(expected["certificate"]["borrowing_base"]))
    check = within_tolerance(stated, Decimal(result.borrowing_base_cents) / 100, Decimal(50))
    assert check.within and check.difference != 0


def test_northmoor_delinquency_is_an_early_warning_and_june_what_if_breaches(key):
    monthly = [(m, delinquency_ratio([r for r in _northmoor(n) if r["status"] not in
                                      ("PAID_OFF", "REPURCHASED")]))
               for m, n in (("March", "03"), ("April", "04"), ("May", "05"))]
    assert [v for _, v in monthly] == [Decimal("5.10"), Decimal("5.60"), Decimal("6.60")]
    trigger = rolling_trigger(monthly, Decimal("6.0"))
    assert (trigger.average, trigger.breached, trigger.early_warning) == (
        Decimal("5.77"), False, True)
    assert trigger.next_month_breaches_beyond == Decimal("5.80")
    assert what_if(trigger, Decimal("5.90"), "June").breached
    assert not what_if(trigger, Decimal("5.70"), "June").breached


def test_leverage_passes_as_reported_and_breaches_with_the_guarantee(key):
    figures = key["checks"]["bramble_covenants"]
    reported = leverage(320800, figures["tangible_net_worth_k"], 12000, 15000, Decimal("6.0"))
    counted = leverage(320800, figures["tangible_net_worth_k"], 12000, 15000, Decimal("6.0"),
                       added_liabilities=figures["guarantee_k"])
    assert (reported.ratio, reported.passed) == (Decimal("5.28"), True)
    assert (counted.ratio, counted.passed) == (Decimal("6.20"), False)


def test_kestrel_nav_tests(key):
    kestrel = key["checks"]["kestrel"]
    nav = to_cents(str(kestrel["nav"]))
    drawn = to_cents(str(kestrel["drawn"]))
    assert loan_to_value(drawn, nav, Decimal(35)).ratio_pct == Decimal("30.3")
    marked = loan_to_value(drawn, nav, Decimal(35), adjustments_cents=-8_500_000_000)
    assert (marked.ratio_pct, marked.passed) == (Decimal("32.2"), True)
    positions = [{"name": p["name"], "valued": date.fromisoformat(p["valued"]),
                  "value_cents": p["value"] * 100} for p in kestrel["positions"]]
    stale = stale_valuations(positions, date(2026, 3, 31), 90)
    assert [(s.name, s.age_days) for s in stale] == [("Harlow Logistics Group", 106)]
    concentration = position_concentration(positions, nav, Decimal(15), Decimal(55))
    assert (concentration.largest_pct, concentration.top_five_pct) == (
        Decimal("12.8"), Decimal("52.4"))
    assert concentration.passed


def test_one_vin_is_pledged_across_facilities_and_none_within(may, key):
    within, across = duplicate_collateral({"bramble": may, "northmoor": _northmoor("05")})
    assert within == ()
    assert [shared.vin for shared in across] == [key["issues"]["M7"]["vin"]]
    assert {facility for facility, _ in across[0].holdings} == {"bramble", "northmoor"}


def test_northmoor_may_dip_is_seasonal(key):
    collections = key["checks"]["northmoor_collections"]
    history = dict(collections["history"])
    principal = collections["principal"]
    check = seasonal(round(principal["may"]), round(principal["april"]),
                     history["May 2025"], history["Apr 2025"])
    assert check.within and check.change < 0


def test_closed_statuses_leave_the_pool():
    assert {"PAID_OFF", "REPURCHASED", "CHARGED_OFF"} == CLOSED
