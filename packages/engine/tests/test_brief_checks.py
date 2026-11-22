"""The checks the pitch brief asks for, run on the generated cycle: validation rule families,
change against the prior period, the CLO warehouse, headroom, alert rules and QC variances."""

import csv
import json
from datetime import date
from decimal import Decimal

import pytest
from conftest import OUTPUT, read_key
from openpyxl import load_workbook

from engine.alerts import (
    AlertRule,
    InvalidRule,
    back_test,
    check_rule,
    classify,
    headroom,
)
from engine.clo import borrowing_base, compare_positions, early_warnings, notch, par_roll
from engine.run import to_cents
from engine.validation import (
    Rule,
    blocking,
    exact_duplicates,
    pool_metrics,
    prior_period,
    validate,
)

CYCLE = OUTPUT / "cycle"
NORTHMOOR = {"Acct_No": "loan_id", "Vehicle_VIN": "vin", "Principal_Bal": "current_balance",
             "Amt_Financed": "original_balance", "Status_Cd": "status", "Days_Delinq":
             "days_past_due", "CO_Amt": "charge_off_amount"}

pytestmark = pytest.mark.skipif(not (OUTPUT / "cycle-key" / "key.json").exists(),
                                reason="The cycle kit has not been built")


@pytest.fixture(scope="module")
def key() -> dict:
    return json.loads((OUTPUT / "cycle-key" / "key.json").read_text(encoding="utf-8"))


def _tape(path, columns):
    with path.open(encoding="utf-8", newline="") as handle:
        return [{columns[k]: v for k, v in row.items() if k in columns}
                for row in csv.DictReader(handle)]


RULES = [
    Rule("V1", "missing_data", "blocking", "Every row has a loan number", "loan_id"),
    Rule("V2", "duplicates", "blocking", "Loan numbers are unique", "loan_id"),
    Rule("V3", "data_types", "blocking", "Balance is a number", "current_balance", "number"),
    Rule("V4", "reference_data", "warning", "Status is a known code", "status",
         allowed=("ACTIVE", "DELINQUENT", "CHARGED_OFF", "PAID_OFF", "REPO", "REPURCHASED")),
    Rule("V5", "logical", "warning", "Balance not above original",
         kind="balance_not_above_original"),
]


def test_the_repeated_northmoor_line_blocks_the_load_and_collapses_on_resolution(key):
    rows = _tape(CYCLE / "northmoor" / "NMC_Tape_2026-05.csv", NORTHMOOR)
    results = validate(rows, RULES, "loan_id")
    held = blocking(results)
    assert [r.rule.id for r in held] == ["V2"]
    planted = key["checks"]["validation"]["northmoor"]["blocking"][0]
    assert {f.key for f in held[0].failures} == {planted["loan_id"]}
    assert len(rows) == planted["rows_in_file"]
    kept, collapsed = exact_duplicates(rows, "loan_id")
    assert collapsed == [planted["loan_id"]] and len(kept) == len(rows) - 1
    assert not blocking(validate(kept, RULES, "loan_id"))


def test_rows_that_share_a_key_but_differ_are_not_collapsed():
    rows = [{"loan_id": "A", "current_balance": "1"}, {"loan_id": "A", "current_balance": "2"}]
    kept, collapsed = exact_duplicates(rows, "loan_id")
    assert len(kept) == 2 and collapsed == []


def test_bramble_warnings_are_found_and_do_not_block(key):
    columns = read_key("mapping")["columns"]
    rows = _tape(CYCLE / "bramble" / "BAF_Loan_Tape_2026-05.csv", columns)
    rules = [
        Rule("W1", "missing_data", "warning", "Employment type", "employment_type"),
        Rule("W2", "data_types", "warning", "Stated income is a number", "stated_monthly_income",
             "number"),
        *RULES,
    ]
    results = {r.rule.id: r for r in validate(rows, rules, "loan_id")}
    planted = key["checks"]["validation"]["bramble"]["warnings"]
    assert [f.key for f in results["W1"].failures] == planted["missing_employment_type"]
    assert [f.key for f in results["W2"].failures] == planted["income_not_a_number"]
    assert not blocking(list(results.values()))


def test_bramble_pool_change_against_april_is_flagged(key):
    columns = read_key("mapping")["columns"]
    april = _tape(OUTPUT / "pack" / read_key("pack")["loan_tape"], columns)
    may = _tape(CYCLE / "bramble" / "BAF_Loan_Tape_2026-05.csv", columns)
    changes = {c.metric: c for c in prior_period(
        pool_metrics(may), pool_metrics(april),
        {"pool_balance": ("pct", Decimal(5)), "weighted_apr": ("abs", Decimal("0.5"))})}
    expected = key["checks"]["prior_period"]["bramble"]["pool_balance_change_pct"]
    assert changes["pool_balance"].flagged
    assert changes["pool_balance"].change == Decimal(str(expected))
    assert not changes["weighted_apr"].flagged


def _positions(name: str) -> tuple[list[dict], list[dict]]:
    book = load_workbook(CYCLE / "larkspur" / name, read_only=True)
    rows = list(book["Positions"].iter_rows(min_row=2, values_only=True))
    positions = [{"loanx": r[0], "cusip": r[1], "issuer": r[2], "facility": r[3],
                  "par_cents": int(r[4]) * 100, "spread_bps": r[5], "maturity": r[7],
                  "moodys": r[8], "sp": r[9]} for r in rows]
    trades = []
    if "Trades" in book.sheetnames:
        trades = [{"direction": r[1], "loanx": r[2], "par_cents": int(r[5]) * 100}
                  for r in book["Trades"].iter_rows(min_row=2, values_only=True)]
    return positions, trades


def _bids(name: str) -> dict[str, Decimal]:
    with (CYCLE / "larkspur" / name).open(encoding="utf-8") as handle:
        return {r["LoanX_ID"]: Decimal(r["Bid"]) for r in csv.DictReader(handle)}


def test_larkspur_ccc_excess_and_borrowing_base_match_the_key(key):
    expected = key["checks"]["larkspur"]
    for month, positions_file, prices_file in (
        ("april", "Larkspur_Collateral_Report_2026-04-30.xlsx", "Meridian_Prices_2026-04-30.csv"),
        ("may", "Larkspur_Collateral_Report_2026-05-29.xlsx", "Meridian_Prices_2026-05-29.csv"),
    ):
        positions, _ = _positions(positions_file)
        result = borrowing_base(positions, _bids(prices_file), Decimal("7.5"), Decimal(70),
                                400_000_000_00, 290_000_000_00, "lower_of")
        assert result.ccc_pct == Decimal(str(expected[month]["ccc_pct"]))
        assert result.haircut_cents == to_cents(str(expected[month]["haircut"]))
        assert result.borrowing_base_cents == to_cents(str(expected[month]["borrowing_base"]))
    assert not result.passed and [p.issuer for p in result.excess] == ["Embsay Fitness"]


def test_moodys_only_would_miss_the_split_rated_loan():
    assert notch("B3", "CCC+", "moodys") < notch("B3", "CCC+", "lower_of")


def test_identifier_change_is_linked_not_missing_and_new(key):
    april, _ = _positions("Larkspur_Collateral_Report_2026-04-30.xlsx")
    may, trades = _positions("Larkspur_Collateral_Report_2026-05-29.xlsx")
    changes = compare_positions(april, may, trades)
    planted = key["checks"]["larkspur"]["identifier_change"]
    assert [(c.old_loanx, c.new_loanx) for c in changes.relinked] == [
        (planted["old_loanx"], planted["new_loanx"])]
    assert changes.unexplained_gone == () and changes.unexplained_new == ()
    assert len(changes.sold) == 1 and len(changes.bought) == 2
    assert par_roll(april, may, trades)["gap"] == 0


def test_early_warnings_find_the_downgrade_and_the_price_fall(key):
    april, _ = _positions("Larkspur_Collateral_Report_2026-04-30.xlsx")
    may, trades = _positions("Larkspur_Collateral_Report_2026-05-29.xlsx")
    links = {c.new_loanx: c.old_loanx for c in compare_positions(april, may, trades).relinked}
    ratings, prices = early_warnings(april, may, _bids("Meridian_Prices_2026-04-30.csv"),
                                     _bids("Meridian_Prices_2026-05-29.csv"), links,
                                     Decimal(10), "lower_of")
    assert [(r.issuer, r.into_ccc) for r in ratings] == [("Kettlewell Auto Parts", True)]
    assert [p.issuer for p in prices] == [key["issues"]["M12"]["issuer"]]


def test_headroom_warns_when_close_or_moving_towards_the_limit():
    near = headroom(Decimal("5.77"), Decimal("6.0"), "max", Decimal("0.5"), Decimal("5.10"))
    assert near.passed and near.early_warning and near.trend == "towards"
    far = headroom(Decimal("4.20"), Decimal("3.0"), "min", Decimal("0.5"), Decimal("4.30"))
    assert far.passed and not far.early_warning
    assert not headroom(Decimal("8.41"), Decimal("7.5"), "max", Decimal("0.5")).passed


def test_alert_rules_are_checked_and_back_tested():
    catalogue = {"northmoor.delinquency_60_plus": {"unit": "%", "range": [0, 100]}}
    rule = AlertRule("northmoor", "delinquency_60_plus", ">", Decimal("5.5"))
    check_rule(rule, catalogue, {"northmoor"})
    fired = back_test(rule, [("Mar", Decimal("5.10")), ("Apr", Decimal("5.60")),
                             ("May", Decimal("6.60"))])
    assert [f for _, _, f in fired] == [False, True, True]
    with pytest.raises(InvalidRule):
        check_rule(AlertRule("larkspur", "delinquency_60_plus", ">", Decimal(5)), catalogue,
                   {"northmoor"})
    with pytest.raises(InvalidRule):
        check_rule(AlertRule("northmoor", "delinquency_60_plus", ">", Decimal(500)), catalogue,
                   {"northmoor"})


@pytest.mark.parametrize(("platform", "qc", "unit", "expected"), [
    (0, "-", "US$", "blank"),
    (None, "", "US$", "blank"),
    (100.0, 100.0, "US$", "agrees"),
    (1487923.26, -1487923.26, "US$", "sign"),
    (82.5, 0.825, "%", "percent"),
    (67818516.47, 67818516.0, "US$", "rounding"),
    (32.2, 32.17, "%", "rounding"),
    (355508.03, 495508.03, "US$", "genuine"),
    (12.0, "-", "US$", "genuine"),
])
def test_qc_variances_are_classified(platform, qc, unit, expected):
    assert classify(platform, qc, unit) == expected


def test_today_is_after_every_larkspur_maturity_check():
    april, _ = _positions("Larkspur_Collateral_Report_2026-04-30.xlsx")
    assert all(date.fromisoformat(p["maturity"]) > date(2026, 5, 29) for p in april)
