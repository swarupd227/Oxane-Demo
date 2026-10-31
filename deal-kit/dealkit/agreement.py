"""Assemble the credit agreement from its section files and render it to PDF."""

import io
import re
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

import numpy as np
import pypdfium2
from PIL import Image as PILImage
from PIL import ImageFilter
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.units import inch
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    Image,
    NextPageTemplate,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
)
from reportlab.platypus.tableofcontents import TableOfContents

from dealkit.config import ROOT
from dealkit.pdfkit import (
    ARTICLE,
    BODY,
    CENTERED,
    INDENT_1,
    INDENT_2,
    SECTION,
    SERIF,
    SMALL,
    TITLE,
    page_frame,
    table,
    text,
)

CONTENT_DIR = ROOT / "content" / "credit_agreement"
HEADER = "Credit Agreement - Execution Version"

ARTICLES = {
    1: "DEFINITIONS",
    2: "THE FACILITY",
    3: "CONDITIONS PRECEDENT",
    4: "REPRESENTATIONS AND WARRANTIES",
    5: "AFFIRMATIVE COVENANTS",
    6: "NEGATIVE AND FINANCIAL COVENANTS",
    7: "PERFORMANCE TRIGGERS",
    8: "EVENTS OF DEFAULT",
    9: "THE AGENTS",
    10: "MISCELLANEOUS",
}
ROMAN = re.compile(r"^\((i{1,3}|iv|v|vi{1,3}|ix|x)\)\s")
LETTER_ITEM = re.compile(r"^\(([a-z])\)\s")
NUMBERED = re.compile(r"^\d+\.\s")
SECTION_REF = re.compile(r"Section (\d+\.\d+)")


def placeholders(deal: dict[str, Any]) -> dict[str, str]:
    terms = deal["terms"]

    def usd(amount: int) -> str:
        return f"US${amount:,}"

    def long_date(value: Any) -> str:
        return f"{value:%B} {value.day}, {value.year}"

    return {
        "borrower": deal["borrower"]["name"],
        "parent": deal["borrower"]["parent"],
        "lender": deal["lender"]["name"],
        "servicer": deal["servicer"]["name"],
        "borrower_address": deal["borrower"]["address"],
        "lender_address": deal["lender"]["address"],
        "facility_limit": usd(deal["facility"]["limit_usd"]),
        "final_maturity": long_date(terms["final_maturity"]),
        "revolving_end": long_date(terms["revolving_period_end"]),
        "reserve_pct": f"{terms['reserve_pct']}%",
        "margin": f"{terms['margin_pct']:.2f}%",
        "payment_day": f"{terms['payment_day']}th",
        "min_tnw": usd(terms["min_tangible_net_worth_usd"]),
        "max_leverage": f"{terms['max_leverage_ratio']:.2f}",
        "sub_debt_cap": usd(terms["subordinated_debt_cap_usd"]),
        "min_liquidity": usd(terms["min_liquidity_usd"]),
        "delinquency_trigger": f"{terms['delinquency_trigger_pct']:.1f}%",
        "governing_law": terms["governing_law"],
        "threshold_amount": "US$2,500,000",
    }


def _fill(body: str, values: dict[str, str]) -> str:
    def replace(match: re.Match[str]) -> str:
        return values[match.group(1)]

    return re.sub(r"\{\{(\w+)\}\}", replace, body)


def load_sections(values: dict[str, str]) -> dict[str, tuple[str, list[str]]]:
    """Read every section file into {number: (title, paragraphs)}."""
    sections: dict[str, tuple[str, list[str]]] = {}
    for path in sorted(CONTENT_DIR.glob("articles_*.txt")) + [CONTENT_DIR / "core.txt"]:
        body = _fill(path.read_text(encoding="utf-8"), values).split("\n# SCHEDULE", 1)[0]
        for chunk in re.split(r"^## ", body, flags=re.M)[1:]:
            heading, _, rest = chunk.partition("\n")
            number, _, title = heading.strip().partition(" ")
            if number in sections:
                raise ValueError(f"Section {number} appears twice")
            paragraphs = [p.strip() for p in re.split(r"\n\s*\n", rest) if p.strip()]
            sections[number] = (title.strip(), paragraphs)
    return dict(sorted(sections.items(), key=lambda item: tuple(map(int, item[0].split(".")))))


def load_definitions(values: dict[str, str]) -> list[list[str]]:
    """Merge the definition files alphabetically. Sub-paragraphs stay with their term."""
    entries: list[list[str]] = []
    for path in sorted(CONTENT_DIR.glob("defs_*.txt")):
        blocks = re.split(r"\n\s*\n", _fill(path.read_text(encoding="utf-8"), values))
        for block in (b.strip() for b in blocks if b.strip()):
            if block.startswith('"'):
                entries.append([block])
            else:
                entries[-1].append(block)
    terms = [entry[0].split('"')[1].lower() for entry in entries]
    duplicates = {term for term in terms if terms.count(term) > 1}
    if duplicates:
        raise ValueError(f"Defined twice: {sorted(duplicates)}")
    return sorted(entries, key=lambda entry: entry[0].split('"')[1].lower())


def load_schedules(values: dict[str, str]) -> list[tuple[str, list[str]]]:
    core = _fill((CONTENT_DIR / "core.txt").read_text(encoding="utf-8"), values)
    schedules = []
    for chunk in re.split(r"^# ", core, flags=re.M)[1:]:
        heading, _, rest = chunk.partition("\n")
        schedules.append((heading.strip(), [p.strip() for p in re.split(r"\n\s*\n", rest)
                                            if p.strip()]))
    return schedules


def check_cross_references(sections: dict[str, Any], definitions: list[list[str]]) -> None:
    corpus = [p for _, paragraphs in sections.values() for p in paragraphs]
    corpus += [p for entry in definitions for p in entry]
    known = set(sections) | {"1.1"}
    broken = sorted({m for p in corpus for m in SECTION_REF.findall(p) if m not in known})
    if broken:
        raise ValueError(f"References to missing sections: {broken}")


def _styled(paragraph: str, previous_letter: str | None) -> tuple[Paragraph, str | None]:
    """Pick the indent. (i) is a letter after (h), and a roman numeral otherwise."""
    letter = LETTER_ITEM.match(paragraph)
    if letter:
        token = letter.group(1)
        follows = previous_letter is not None and ord(token) == ord(previous_letter) + 1
        if not ROMAN.match(paragraph) or follows:
            return Paragraph(escape(paragraph), INDENT_1), token
    if ROMAN.match(paragraph):
        return Paragraph(escape(paragraph), INDENT_2), previous_letter
    if NUMBERED.match(paragraph):
        return Paragraph(escape(paragraph), INDENT_1), previous_letter
    return Paragraph(escape(paragraph), BODY), None


def _render_paragraphs(paragraphs: list[str]) -> list[Any]:
    story: list[Any] = []
    previous: str | None = None
    rows: list[list[str]] = []
    for paragraph in paragraphs:
        for line in paragraph.splitlines():
            if line.startswith("|"):
                rows.append([cell.strip() for cell in line.strip("|").split("|")])
        if paragraph.startswith("|"):
            continue
        item, previous = _styled(paragraph, previous)
        story.append(item)
    if rows:
        wrapped = [[Paragraph(escape(cell), SMALL) for cell in row] for row in rows]
        widths = {2: [1.2, 5.3], 3: [0.5, 4.2, 1.8]}[len(rows[0])]
        story.append(table(wrapped, widths=widths, font=SERIF, align_right_from=99))
    return story


def _definition(entry: list[str]) -> list[Any]:
    head = entry[0]
    term = head.split('"')[1]
    rest = head[len(term) + 2:]
    first = Paragraph(f'<b>"{escape(term)}"</b>{escape(rest)}', BODY)
    return [first] + _render_paragraphs(entry[1:])


def _scanned_page(deal: dict[str, Any], rng: np.random.Generator, work_dir: Path) -> Image:
    """Render Annex A, then degrade it to an image-only page like a poor scan."""
    source = work_dir / "annex_a.pdf"
    from dealkit.pdfkit import build as build_simple

    limit = f"US${deal['facility']['limit_usd']:,}"
    build_simple(source, [
        Spacer(1, 0.6 * inch),
        text("ANNEX A", TITLE),
        text("COMMITMENT SCHEDULE", CENTERED),
        Spacer(1, 0.3 * inch),
        table([["Lender", "Commitment"], [deal["lender"]["name"], limit], ["Total", limit]],
              widths=[3.5, 2.5], font=SERIF, size=12),
        Spacer(1, 0.4 * inch),
        text("Initialled for identification on the Closing Date.", BODY),
        text("/s/ R.A.   /s/ M.T.", BODY),
    ], "Annex A", "")

    bitmap = pypdfium2.PdfDocument(str(source))[0].render(scale=1.5).to_pil()
    gray = bitmap.convert("L").rotate(0.9, fillcolor=236, resample=PILImage.Resampling.BILINEAR)
    pixels = np.asarray(gray, dtype=np.float32) * 0.86 + 12
    pixels += rng.normal(0, 16, pixels.shape)
    pixels[rng.random(pixels.shape) < 0.012] = 45
    scan = PILImage.fromarray(np.clip(pixels, 0, 255).astype(np.uint8)).filter(
        ImageFilter.GaussianBlur(0.75)
    )
    buffer = io.BytesIO()
    scan.save(buffer, format="JPEG", quality=38)
    buffer.seek(0)
    return Image(buffer, width=6.5 * inch, height=8.4 * inch)


class _AgreementDoc(BaseDocTemplate):
    def afterFlowable(self, flowable: Any) -> None:
        if isinstance(flowable, Paragraph) and flowable.style.name in ("Article", "Section"):
            level = 0 if flowable.style.name == "Article" else 1
            self.notify("TOCEntry", (level, flowable.getPlainText(), self.page))


def _toc() -> TableOfContents:
    from reportlab.lib.styles import ParagraphStyle

    toc = TableOfContents()
    toc.levelStyles = [
        ParagraphStyle("TOC0", fontName="Times-Bold", fontSize=10, leading=13, spaceBefore=5),
        ParagraphStyle("TOC1", fontName="Times-Roman", fontSize=10, leading=12, leftIndent=14),
    ]
    return toc


def build_agreement(deal: dict[str, Any], rng: np.random.Generator, path: Path) -> None:
    values = placeholders(deal)
    sections = load_sections(values)
    definitions = load_definitions(values)
    schedules = load_schedules(values)
    check_cross_references(sections, definitions)

    borrower, lender = deal["borrower"]["name"], deal["lender"]["name"]
    signing = deal["terms"]["signing_date"]
    signed = f"{signing:%B} {signing.day}, {signing.year}"

    story: list[Any] = [
        Spacer(1, 1.2 * inch),
        text("CREDIT AGREEMENT", TITLE),
        text(f"dated as of {signed}", CENTERED),
        Spacer(1, 0.3 * inch),
        text("among", CENTERED),
        text(borrower.upper(), CENTERED),
        text("as Borrower,", CENTERED),
        text(f"{deal['servicer']['name'].upper()}", CENTERED),
        text("as Servicer and Parent,", CENTERED),
        text("and", CENTERED),
        text(lender.upper(), CENTERED),
        text("as Lender and Administrative Agent", CENTERED),
        Spacer(1, 0.4 * inch),
        text("Senior Secured Revolving Warehouse Facility", CENTERED),
        PageBreak(),
        text("TABLE OF CONTENTS", ARTICLE),
        _toc(),
        Spacer(1, 10),
        text("SCHEDULES AND EXHIBITS", ARTICLE),
    ]
    for line in (
        "Schedule 1 - Eligibility Criteria", "Schedule 2 - Concentration Limits",
        "Schedule 3 - Reporting Requirements", "Schedule 4 - Restricted Jurisdictions",
        "Annex A - Commitment Schedule", "Exhibit A - Form of Borrowing Base Certificate",
        "Exhibit B - Form of Advance Request", "Exhibit C - Form of Compliance Certificate",
    ):
        story.append(text(line, SMALL))
    story += [
        PageBreak(),
        text("CREDIT AGREEMENT", ARTICLE),
        text(f'This CREDIT AGREEMENT (this "Agreement") is entered into as of {signed} among '
             f'{borrower}, a Delaware limited liability company (the "Borrower"), '
             f'{deal["servicer"]["name"]}, a Delaware limited liability company, as servicer (the '
             f'"Servicer") and as Parent, and {lender}, as lender (the "Lender") and as '
             "administrative agent (the \"Administrative Agent\")."),
        text("The Borrower wishes to finance its purchase of retail auto loan receivables "
             "originated by the Parent, and the Lender is willing to make a senior secured "
             "revolving warehouse facility available on the terms of this Agreement. The parties "
             "therefore agree as follows."),
    ]

    current_article = 0
    for number, (title, paragraphs) in sections.items():
        article = int(number.split(".")[0])
        if article != current_article:
            current_article = article
            story.append(Paragraph(f"ARTICLE {article} - {ARTICLES[article]}", ARTICLE))
            if article == 1:
                story.append(Paragraph("1.1 Defined Terms", SECTION))
                story.append(text("In this Agreement, the following terms have these meanings:"))
                for entry in definitions:
                    story += _definition(entry)
        story.append(Paragraph(f"{number} {escape(title)}", SECTION))
        story += _render_paragraphs(paragraphs)

    story += [
        PageBreak(),
        text("IN WITNESS WHEREOF, the parties have executed this Agreement as of the date first "
             "written above."),
        Spacer(1, 0.3 * inch),
    ]
    for party, role in ((borrower, "as Borrower"), (deal["servicer"]["name"], "as Servicer"),
                        (lender, "as Lender and Administrative Agent")):
        story += [text(f"{party.upper()}, {role}", BODY), text("By: /s/ (signature on file)", BODY),
                  text("Name: Authorised Signatory", BODY), Spacer(1, 0.3 * inch)]

    for heading, paragraphs in schedules:
        story += [PageBreak(), Paragraph(escape(heading), ARTICLE)]
        story += _render_paragraphs(paragraphs)

    story += [PageBreak(), _scanned_page(deal, rng, path.parent.parent / "work")]

    for heading, lines in _exhibits(values):
        story += [PageBreak(), Paragraph(escape(heading), ARTICLE)]
        story += [text(line) for line in lines]

    path.parent.mkdir(parents=True, exist_ok=True)
    doc = _AgreementDoc(str(path), pagesize=LETTER, invariant=1, title="Credit Agreement",
                        author="", leftMargin=inch, rightMargin=inch,
                        topMargin=0.9 * inch, bottomMargin=0.9 * inch)
    frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="body")
    doc.addPageTemplates([
        PageTemplate(id="cover", frames=[frame]),
        PageTemplate(id="body", frames=[frame], onPage=page_frame(HEADER)),
    ])
    story.insert(0, NextPageTemplate("body"))
    doc.multiBuild(story, maxPasses=6)


def _exhibits(values: dict[str, str]) -> list[tuple[str, list[str]]]:
    borrower = values["borrower"]
    return [
        ("EXHIBIT A - FORM OF BORROWING BASE CERTIFICATE", [
            f"To: {values['lender']}, as Lender, and the Verification Agent.",
            f"The undersigned, a Responsible Officer of {borrower}, certifies as of the last day "
            "of the Collection Period stated below that the attached schedule is a true and "
            "complete calculation of the Borrowing Base, made in accordance with the Agreement, "
            "and that no Default or Event of Default has occurred and is continuing.",
            "Collection Period ended: ______________",
            "1. Aggregate Outstanding Balance of Pool Receivables: US$ ______________",
            "2. Less Receivables that are not Eligible Receivables: US$ ______________",
            "3. Eligible Pool Balance: US$ ______________",
            "4. Less Excess Concentration Amount: US$ ______________",
            "5. Advance Rate: ______ %",
            "6. Less Reserve Amount: US$ ______________",
            "7. Borrowing Base: US$ ______________",
            "8. Outstanding Advances: US$ ______________",
            "9. Availability: US$ ______________",
        ]),
        ("EXHIBIT B - FORM OF ADVANCE REQUEST", [
            f"To: {values['lender']}, as Administrative Agent.",
            f"{borrower} requests an Advance under Section 2.2 of the Agreement as follows.",
            "Date of Advance (a Business Day): ______________",
            "Amount of Advance: US$ ______________",
            "Account to be credited: ______________",
            "The Borrower confirms that each condition in Section 3.2 is satisfied on the date of "
            "this request and will be satisfied on the date of the Advance, and that after giving "
            "effect to the Advance no Borrowing Base Deficiency will exist.",
        ]),
        ("EXHIBIT C - FORM OF COMPLIANCE CERTIFICATE", [
            f"To: {values['lender']}, as Lender.",
            "The undersigned, a Responsible Officer of the Parent, certifies as of the fiscal "
            "quarter end stated below that the attached calculations of Tangible Net Worth, the "
            "Leverage Ratio and Liquidity under Section 6.12 are true and complete.",
            "Fiscal quarter ended: ______________",
            "Tangible Net Worth: US$ ______________",
            "Leverage Ratio: ______ to 1.00",
            "Liquidity: US$ ______________",
        ]),
    ]
