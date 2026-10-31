import re
from pathlib import Path

CONTENT = Path(__file__).parent.parent / "content" / "credit_agreement"
DRAFTED = [*CONTENT.glob("articles_*.txt"), CONTENT / "defs_a.txt"]


def test_drafted_text_has_no_figures_of_its_own():
    """Numbers that matter live in deal.yaml, core.txt and defs_core.txt only."""
    for path in DRAFTED:
        body = path.read_text(encoding="utf-8")
        assert not re.search(r"[$%]|\bpercent\b|\bUS\$", body), path.name


def test_drafted_text_does_not_restate_core_sections():
    numbers = {"2.1", "2.3", "2.6", "2.7", "6.12", "7.1", "8.1", "10.2", "10.9"}
    for path in DRAFTED:
        headings = re.findall(r"^## (\d+\.\d+)", path.read_text(encoding="utf-8"), flags=re.M)
        assert not numbers & set(headings), path.name


def test_drafted_text_uses_only_known_placeholders():
    allowed = {"borrower", "parent", "lender", "servicer", "threshold_amount"}
    for path in DRAFTED:
        assert set(re.findall(r"\{\{(\w+)\}\}", path.read_text(encoding="utf-8"))) <= allowed
