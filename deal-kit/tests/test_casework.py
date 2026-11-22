"""The casework around the pack: the client's model, the QC workbook and the backbook tapes."""

import csv
import json

from openpyxl import load_workbook

from dealkit.build import build_all
from dealkit.casework.common import CASEWORK_DIR, CASEWORK_KEY_DIR, load_casework
from dealkit.tape import COLUMNS


def _key() -> dict:
    build_all()
    return json.loads((CASEWORK_KEY_DIR / "key.json").read_text(encoding="utf-8"))


def test_client_model_cells_hold_the_values_the_key_names():
    key = _key()
    spec = load_casework()["client_model"]
    book = load_workbook(CASEWORK_DIR / "client" / spec["file"])
    for topic, cell in key["client_model"]["cells"].items():
        sheet, ref = cell.split("!")
        assert book[sheet][ref].value is not None, topic


def test_each_difference_is_worked_out_against_the_agreed_borrowing_base():
    model = _key()["client_model"]
    differences = model["differences"]
    assert set(differences) == {"advance_rate", "past_due_exclusion", "concentration_denominator",
                                "dealer_grouping", "fico_bucket", "missing_fico"}
    # The stale advance rate and the two concentration treatments would overstate availability.
    assert differences["advance_rate"]["borrowing_base_change"] > 1_000_000
    assert differences["concentration_denominator"]["borrowing_base_change"] > 0
    assert differences["dealer_grouping"]["borrowing_base_change"] > 0
    # The FICO band moves loans between buckets but not, this month, the borrowing base.
    assert differences["fico_bucket"]["borrowing_base_change"] == 0
    assert differences["fico_bucket"]["fico_bucket_change"] > 0
    assert model["agreed"]["borrowing_base"] == 48193346.69


def test_qc_workbook_has_two_genuine_variances_and_each_presentation_class():
    lines = _key()["qc"]["lines"]
    classes = [line["expected"] for line in lines]
    assert classes.count("genuine") == 2
    assert {"blank", "rounding", "sign", "percent", "agrees"} <= set(classes)


def test_backbook_tapes_use_the_stored_layout_except_where_planted():
    key = _key()
    for deal in key["backbook"]:
        with (CASEWORK_DIR / "backbook" / deal["file"]).open(encoding="utf-8") as handle:
            header = next(csv.reader(handle))
        planted = {item["column"] for item in deal["exceptions"]
                   if item["kind"] in ("renamed_column", "new_column")}
        assert set(header) - set(COLUMNS) == planted, deal["id"]
    assert [d["exceptions"] for d in key["backbook"] if d["id"] == "ashdown"] == [[]]


def test_definitions_key_finds_every_definition_in_the_pack():
    terms = _key()["definitions"]["terms"]
    assert all(term["page"] for term in terms)
    assert {"Borrowing Base", "Defaulted Receivable"} <= {term["term"] for term in terms}


def test_pipeline_counts_are_worked_out_and_consistent():
    _key()
    spec = load_casework()["pipeline"]
    pipeline = json.loads((CASEWORK_DIR / "pipeline" / spec["file"]).read_text(encoding="utf-8"))
    cases = pipeline["cases"]
    assert [case["number"] for case in cases] == [case["number"] for case in spec["cases"]]
    assert set(pipeline["backbook"]) == {deal["id"] for deal in load_casework()["backbook"]}
    for case in cases:
        profile = spec["profiles"][case["deal_type"]]
        assert profile["records"][0] <= case["records"] <= profile["records"][1]
        assert case["pool_balance"] > 0
        assert case["documents"]["received"] <= case["documents"]["expected"]
        assert case["terms"]["approved"] <= case["terms"]["extracted"] <= case["terms"]["total"]
        assert 0 <= case["exceptions"]["open"] <= case["exceptions"]["total"]
        assert 0 <= case["queries"]["with_client"] <= case["queries"]["total"]
        assert case["business_days_in_stage"] <= case["business_days_open"]
        assert case["last_activity"][:10] <= pipeline["as_of"]
        if case["stage"] == "Live":
            assert case["exceptions"]["open"] == 0
            assert case["terms"]["approved"] == case["terms"]["total"]
        if case["stage"] == "Intake":
            assert case["terms"]["extracted"] == 0
