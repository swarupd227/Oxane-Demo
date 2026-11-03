import csv
import json

from dealkit.cycle.build import build_cycle
from dealkit.cycle.common import CYCLE_DIR, CYCLE_KEY_DIR


def test_cycle_rebuilds_byte_for_byte():
    assert build_cycle() == build_cycle()


def test_every_planted_issue_and_noise_item_is_in_the_key():
    build_cycle()
    key = json.loads((CYCLE_KEY_DIR / "key.json").read_text(encoding="utf-8"))
    assert sorted(key["issues"]) == [f"M{n}" for n in range(1, 10)]
    assert sorted(key["noise"]) == ["N1", "N2", "N3"]


def test_the_missing_loans_are_on_the_april_tape_and_absent_in_may():
    build_cycle()
    key = json.loads((CYCLE_KEY_DIR / "key.json").read_text(encoding="utf-8"))
    with (CYCLE_DIR / "bramble" / "BAF_Loan_Tape_2026-05.csv").open(encoding="utf-8") as handle:
        may = {row["LoanNumber"] for row in csv.DictReader(handle)}
    missing = key["issues"]["M2"]["loans"]
    assert len(missing) == 27 and not may & set(missing)


def test_the_shared_vin_is_on_both_may_tapes():
    build_cycle()
    key = json.loads((CYCLE_KEY_DIR / "key.json").read_text(encoding="utf-8"))
    vin = key["issues"]["M7"]["vin"]
    with (CYCLE_DIR / "bramble" / "BAF_Loan_Tape_2026-05.csv").open(encoding="utf-8") as handle:
        bramble = [row for row in csv.DictReader(handle) if row["VIN"] == vin]
    with (CYCLE_DIR / "northmoor" / "NMC_Tape_2026-05.csv").open(encoding="utf-8") as handle:
        northmoor = [row for row in csv.DictReader(handle) if row["Vehicle_VIN"] == vin]
    assert len(bramble) == len(northmoor) == 1


def test_bramble_may_tape_adds_exactly_two_columns():
    build_cycle()
    with (CYCLE_DIR / "bramble" / "BAF_Loan_Tape_2026-05.csv").open(encoding="utf-8") as handle:
        header = next(csv.reader(handle))
    assert header[-2:] == ["CoBorrower", "GAPCoverage"] and len(header) == 40
