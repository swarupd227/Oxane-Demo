import csv
import json

from dealkit.cycle.build import build_cycle
from dealkit.cycle.common import CYCLE_DIR, CYCLE_KEY_DIR


def test_cycle_rebuilds_byte_for_byte():
    assert build_cycle() == build_cycle()


def test_every_planted_issue_and_noise_item_is_in_the_key():
    build_cycle()
    key = json.loads((CYCLE_KEY_DIR / "key.json").read_text(encoding="utf-8"))
    assert sorted(key["issues"], key=lambda i: int(i[1:])) == [f"M{n}" for n in range(1, 13)]
    assert sorted(key["noise"]) == ["N1", "N2", "N3", "N4", "N5"]


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


def test_northmoor_may_tape_repeats_one_line_exactly():
    build_cycle()
    key = json.loads((CYCLE_KEY_DIR / "key.json").read_text(encoding="utf-8"))
    loan = key["issues"]["M10"]["loan"]
    with (CYCLE_DIR / "northmoor" / "NMC_Tape_2026-05.csv").open(encoding="utf-8") as handle:
        rows = [row for row in csv.DictReader(handle) if row["Acct_No"] == loan]
    assert len(rows) == 2 and rows[0] == rows[1]


def test_larkspur_files_carry_the_identifier_change_and_the_ccc_breach():
    build_cycle()
    key = json.loads((CYCLE_KEY_DIR / "key.json").read_text(encoding="utf-8"))
    change = key["checks"]["larkspur"]["identifier_change"]
    with (CYCLE_DIR / "larkspur" / "Meridian_Prices_2026-05-29.csv").open(encoding="utf-8") as f:
        may = {row["LoanX_ID"] for row in csv.DictReader(f)}
    assert change["new_loanx"] in may and change["old_loanx"] not in may
    lark = key["checks"]["larkspur"]
    assert lark["april"]["ccc_pct"] < 7.5 < lark["may"]["ccc_pct"]


def test_each_facility_has_a_qc_workbook_with_one_genuine_variance():
    build_cycle()
    key = json.loads((CYCLE_KEY_DIR / "key.json").read_text(encoding="utf-8"))
    qc = key["checks"]["qc"]
    assert sorted(qc) == ["bramble", "kestrel", "larkspur", "northmoor"]
    genuine = [line["line"] for f in qc.values() for line in f["lines"]
               if line["expected"] == "genuine"]
    assert genuine == ["Gross charge-offs"]
    assert all((CYCLE_DIR / "qc" / f["file"]).exists() for f in qc.values())


def test_the_rest_of_the_book_is_twenty_facilities_kept_out_of_the_key():
    build_cycle()
    book = json.loads((CYCLE_DIR / "book" / "Book_Facilities.json").read_text(encoding="utf-8"))
    assert len({f["id"] for f in book}) == 20
    assert {f["client"] for f in book} == {"calderwood", "thornbury"}
    key = (CYCLE_KEY_DIR / "key.json").read_text(encoding="utf-8")
    assert not any(f["name"] in key for f in book)
    with (CYCLE_DIR / "book" / "Book_Summaries.csv").open(encoding="utf-8") as handle:
        assert len(list(csv.DictReader(handle))) == 60
