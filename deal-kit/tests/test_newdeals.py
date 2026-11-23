import csv
import json

import pypdfium2
from openpyxl import load_workbook

from dealkit.newdeals.build import NEWDEALS_DIR, build_newdeals


def _text(path):
    pdf = pypdfium2.PdfDocument(str(path))
    try:
        return " ".join(" ".join(page.get_textpage().get_text_range().split()) for page in pdf)
    finally:
        pdf.close()


def test_new_deals_rebuild_byte_for_byte():
    assert build_newdeals() == build_newdeals()


def test_each_deal_has_an_onboarding_pack_and_a_later_month():
    build_newdeals()
    for deal in ("harbourline", "fenwick"):
        assert any((NEWDEALS_DIR / deal / "onboarding").glob("*.pdf"))
        assert any((NEWDEALS_DIR / deal / "monthly").iterdir())
        assert (NEWDEALS_DIR / deal / "key.json").exists()


def test_the_consumer_amendment_changes_the_advance_rate():
    build_newdeals()
    text = _text(NEWDEALS_DIR / "harbourline/onboarding/Harbourline_First_Amendment.pdf")
    assert "the Advance Rate of 88.00% is replaced by 86.00%" in text


def test_the_sme_agreement_has_no_reserve():
    build_newdeals()
    text = _text(NEWDEALS_DIR / "fenwick/onboarding/Fenwick_Receivables_Financing_Agreement.pdf")
    assert "Funding Ratio" in text and "reserve" not in text.lower()


def test_the_later_consumer_tape_repeats_one_account():
    build_newdeals()
    key = json.loads((NEWDEALS_DIR / "harbourline/key.json").read_text(encoding="utf-8"))
    with (NEWDEALS_DIR / "harbourline/monthly/Harbourline_Loan_Tape_2026-10.csv").open(
            encoding="utf-8") as handle:
        ids = [row["AccountNo"] for row in csv.DictReader(handle)]
    assert ids.count(key["later"]["duplicate"]) == 2
    assert key["later"]["dropped"] not in ids


def test_the_later_sme_tape_changes_its_layout():
    build_newdeals()
    first = load_workbook(NEWDEALS_DIR / "fenwick/onboarding/Fenwick_Portfolio_2026-09.xlsx")
    later = load_workbook(NEWDEALS_DIR / "fenwick/monthly/Fenwick_Portfolio_2026-10.xlsx")
    before = [cell.value for cell in next(first["Loans"].iter_rows(max_row=1))]
    after = [cell.value for cell in next(later["Loans"].iter_rows(max_row=1))]
    assert "Arrears Days" in before and "Days in Arrears" in after
    assert set(after) - set(before) == {"Days in Arrears", "Collateral Type"}
