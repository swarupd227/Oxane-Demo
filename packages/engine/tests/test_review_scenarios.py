"""The engine's middle-market, subscription-line and daily-feed checks against the cycle key.

The files are read here the plain way, with no platform code, so the engine is tested on the
same inputs the pipeline uses.
"""

import csv
import json
from datetime import date, datetime, time
from decimal import Decimal

import pytest
from conftest import OUTPUT
from openpyxl import load_workbook

from engine.directlending import (
    AddBack,
    CovenantVersion,
    ObligorLoan,
    addback_readings,
    borrowing_base,
    check_obligor,
    covenant_ebitda,
    level_in_force,
    ratio,
)
from engine.feeds import business_days, check_daily
from engine.fundfinance import Investor, classify, reconcile_notice, roll_register
from engine.fundfinance import borrowing_base as subscription_base

CYCLE = OUTPUT / "cycle"
pytestmark = pytest.mark.skipif(not (OUTPUT / "cycle-key" / "key.json").exists()
                                or not (CYCLE / "ravenglass").exists(),
                                reason="Build the cycle kit first")


@pytest.fixture(scope="module")
def key():
    return json.loads((OUTPUT / "cycle-key" / "key.json").read_text(encoding="utf-8"))["checks"]


def _sheet(path, name):
    rows = list(load_workbook(path, read_only=True)[name].iter_rows(values_only=True))
    return [dict(zip(rows[0], r, strict=True)) for r in rows[1:]]


@pytest.fixture(scope="module")
def portfolio():
    return {r["Obligor ID"]: r for r in _sheet(
        CYCLE / "ravenglass" / "Ravenglass_Portfolio_Report_2026-05-31.xlsx", "Portfolio")}


@pytest.fixture(scope="module")
def register():
    return json.loads((CYCLE / "ravenglass" / "Ravenglass_Obligor_Register.json").read_text(
        encoding="utf-8"))["obligors"]


def test_ratios_round_half_up():
    assert ratio(76380, 12000) == Decimal("6.37")
    assert ratio(38700, 8000) == Decimal("4.84")


def test_the_add_back_cap_gives_three_readings(key, portfolio):
    k = key["ravenglass"]["addbacks"]
    items = [AddBack("synergies", 1900, "capped"), AddBack("integration", 900, "judgement"),
             AddBack("settlement", 600, "uncapped")]
    net_debt = int(portfolio[k["id"]]["Net debt (US$000)"])
    readings = addback_readings(k["ebitda_k"], net_debt, items, Decimal(20), Decimal("6.00"))
    got = [float(r.leverage) for r in readings]
    assert got == [k["readings"]["as_reported"], k["readings"]["integration_capped"],
                   k["readings"]["all_capped"]]
    assert [r.passed for r in readings] == [True, False, False]
    assert covenant_ebitda(10000, [AddBack("not itemised", 3400)], Decimal(20)) == 12000


def test_a_waiver_applies_only_to_its_test_dates():
    versions = [CovenantVersion("original", Decimal("5.50")),
                CovenantVersion("waiver", Decimal("6.25"),
                                (date(2026, 3, 31), date(2026, 6, 30)))]
    assert level_in_force(versions, date(2026, 3, 31)).max_leverage == Decimal("6.25")
    assert level_in_force(versions, date(2026, 9, 30)).max_leverage == Decimal("5.50")


def test_obligor_covenants_and_the_borrowing_base_match_the_key(key, portfolio, register):
    k = key["ravenglass"]
    waiver = k["waiver"]
    loans, failed = [], []
    for o in register:
        row = portfolio[o["id"]]
        maximum = Decimal(str(waiver["amended"] if o["id"] == waiver["id"] else
                              o["max_leverage"]))
        check = check_obligor(o["id"], int(row["Net debt (US$000)"]),
                              int(row["Covenant EBITDA (US$000)"]),
                              int(row["Interest expense (US$000)"]), maximum,
                              Decimal(str(o["min_icr"])),
                              Decimal(str(row["Total net leverage (x)"])))
        reported_q1 = str(row["Financials as of"]).startswith("2026-03-31")
        if not check.passed:
            failed.append(o["id"])
        loans.append(ObligorLoan(o["id"], o["name"], o["sector"], o["outstanding"] * 100,
                                 Decimal(str(row["Advance rate (%)"])),
                                 check.passed and reported_q1))
    assert failed == [k["breach"]["id"]]
    base = borrowing_base(loans, Decimal("7.5"), Decimal(20), 200_000_000_00, 138_000_000_00)
    assert sorted(x[0] for x in base.excluded) == sorted(k["excluded"])
    assert base.borrowing_base_cents / 100 == k["borrowing_base"]
    assert base.availability_cents / 100 == k["availability"]
    assert base.largest[0] == k["largest_obligor"]["id"]
    assert not base.obligor_excess_cents and not base.sector_excess_cents


def test_the_reported_leverage_differs_only_by_truncation(key, portfolio):
    k = key["ravenglass"]["rounding"]
    row = portfolio[k["id"]]
    check = check_obligor(k["id"], int(row["Net debt (US$000)"]),
                          int(row["Covenant EBITDA (US$000)"]),
                          int(row["Interest expense (US$000)"]), Decimal(6), Decimal(2),
                          Decimal(str(row["Total net leverage (x)"])))
    assert check.leverage_difference == Decimal("0.01") and check.within_tolerance


def test_investor_classes_follow_the_rating_floor():
    assert classify("A-", "Included").name == "Included"
    assert classify("BBB", "Included").name == "Designated"
    excluded = classify("BB+", "Included")
    assert excluded.name == "Excluded" and excluded.exclusion_event
    assert classify("NR", "Designated").name == "Designated"


def test_the_subscription_line_matches_the_key(key):
    k = key["wharfedale"]
    folder = CYCLE / "wharfedale"
    april = {r["Investor ID"]: r for r in _sheet(
        folder / "Wharfedale_Investor_Register_2026-04-30.xlsx", "Register")}
    may = {r["Investor ID"]: r for r in _sheet(
        folder / "Wharfedale_Investor_Register_2026-05-31.xlsx", "Register")}
    call = _sheet(folder / "Wharfedale_Capital_Call_Notice_07.xlsx", "Allocation")
    dist = _sheet(folder / "Wharfedale_Distribution_Notice_04.xlsx", "Allocation")

    def cents(value):
        return int(round(float(value) * 100))

    lines, gap, ok = reconcile_notice(
        [(r["Investor ID"], cents(r["Commitment (US$)"]), cents(r["Amount called (US$)"]))
         for r in call], sum(cents(r["Amount called (US$)"]) for r in call), Decimal(8))
    assert ok and gap == 0
    rolled = roll_register({i: cents(r["Uncalled (US$)"]) for i, r in april.items()},
                           {r["Investor ID"]: cents(r["Amount called (US$)"]) for r in call},
                           {r["Investor ID"]: cents(r["Recallable (US$)"]) for r in dist},
                           {i: cents(r["Uncalled (US$)"]) for i, r in may.items()})
    breaks = [c.investor for c in rolled if c.difference_cents]
    assert breaks == [k["register"]["stale"]["id"]]
    investors = [Investor(c.investor, may[c.investor]["Investor"],
                          min(c.expected_cents, c.register_cents),
                          classify(may[c.investor]["Rating (S&P)"],
                                   april[c.investor]["Designation"]).name) for c in rolled]
    base = subscription_base(investors, {"Included": Decimal(90), "Designated": Decimal(65)},
                             Decimal(15), Decimal(30), 250_000_000_00, 228_000_000_00)
    after = k["after_exclusion"]
    assert base.borrowing_base_cents / 100 == after["borrowing_base"]
    assert base.prepayment_cents / 100 == after["prepayment"]
    assert {i: v / 100 for i, v in base.investor_excess_cents.items()} == after[
        "concentration_excess"]


def test_daily_feeds_find_the_late_file_and_the_gap(key):
    k = key["larkspur_daily"]
    with (CYCLE / "larkspur-daily" / "Larkspur_Daily_Feed_Log_May_2026.csv").open(
            encoding="utf-8") as handle:
        log = list(csv.DictReader(handle))
    days = business_days(date(2026, 5, 1), date(2026, 5, 29))
    assert len(days) == k["business_days"]
    rules = {"positions": (1, time(7)), "prices": (0, time(18)), "ratings": (1, time(7))}
    late, missing = [], []
    for feed, (lag, at) in rules.items():
        arrived = {date.fromisoformat(r["as_of"]): (datetime.fromisoformat(r["received_at"])
                                                    if r["received_at"] else None, 0)
                   for r in log if r["feed"] == feed}
        for d in check_daily(feed, days, lag, at, arrived):
            if d.status == "late":
                late.append({"feed": feed, "as_of": d.as_of.isoformat()})
            elif d.status == "missing":
                missing.append({"feed": feed, "as_of": d.as_of.isoformat()})
    assert late == k["late"] and missing == k["missing"]
