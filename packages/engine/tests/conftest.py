import csv
import json
import os
import re
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from openpyxl import load_workbook

from engine.reconcile import Certificate
from engine.rules import RuleSet, load_ruleset
from engine.run import Loan, RunResult, coerce_loan, run, to_cents

OUTPUT = Path(os.environ.get("DEAL_KIT_OUTPUT", "/deal-kit/output"))
RULESET = Path(__file__).parent.parent / "rulesets" / "calderwood-bramble.v1.json"
PERIOD_END = date(2026, 4, 30)
ADVANCES = 4_800_000_000
SUNRISE = {"Sunrise Motors": "Sunrise Motors LLC"}


def read_key(name: str):
    return json.loads((OUTPUT / "answer-key" / f"{name}.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def rules() -> RuleSet:
    return load_ruleset(RULESET.read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def loans() -> list[Loan]:
    columns = read_key("mapping")["columns"]
    path = OUTPUT / "pack" / read_key("pack")["loan_tape"]
    with path.open(encoding="utf-8", newline="") as handle:
        return [coerce_loan({columns[k]: v for k, v in row.items()})
                for row in csv.DictReader(handle)]


@pytest.fixture(scope="session")
def system(loans: list[Loan], rules: RuleSet) -> RunResult:
    return run(loans, rules, PERIOD_END, ADVANCES)


@pytest.fixture(scope="session")
def matched(loans: list[Loan], rules: RuleSet) -> RunResult:
    return run(loans, rules, PERIOD_END, ADVANCES, dealer_aliases=SUNRISE)


@pytest.fixture(scope="session")
def certificate() -> Certificate:
    """Read the certificate the way phase 4 will: the file, not the generator."""
    book = load_workbook(OUTPUT / "pack" / read_key("pack")["borrowing_base_certificate"])
    sheet = book["BBC Summary"]

    def money(cell: str) -> int:
        return to_cents(Decimal(str(sheet[cell].value)))

    criteria = {row[0].value: row[1].value
                for row in book["Ineligible Detail"].iter_rows(min_row=2)}
    stated = re.search(r"(\d+) days", criteria["1"])
    assert stated
    return Certificate(
        eligible_pool_cents=money("B7"),
        excess_cents=-money("B8"),
        advance_rate_pct=Decimal(str(sheet["B9"].value)) * 100,
        reserve_cents=-money("B10"),
        borrowing_base_cents=money("B11"),
        outstanding_advances_cents=money("B12"),
        availability_cents=money("B13"),
        thresholds={"E1": Decimal(stated.group(1))},
        rules_not_applied=frozenset({"E7", "E12"}),
    )
