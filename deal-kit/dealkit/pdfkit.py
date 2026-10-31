"""Shared PDF building blocks. Every document sets invariant=1 so builds are byte-identical."""

from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, SimpleDocTemplate, Table, TableStyle

SERIF = "Times-Roman"
SERIF_BOLD = "Times-Bold"
SANS = "Helvetica"
SANS_BOLD = "Helvetica-Bold"

BODY = ParagraphStyle("Body", fontName=SERIF, fontSize=10.5, leading=12.8, spaceAfter=6,
                      alignment=TA_JUSTIFY)
INDENT_1 = ParagraphStyle("Indent1", parent=BODY, leftIndent=0.35 * inch)
INDENT_2 = ParagraphStyle("Indent2", parent=BODY, leftIndent=0.7 * inch)
SECTION = ParagraphStyle("Section", parent=BODY, fontName=SERIF_BOLD, spaceBefore=8,
                         spaceAfter=5, keepWithNext=1)
ARTICLE = ParagraphStyle("Article", parent=BODY, fontName=SERIF_BOLD, fontSize=12, leading=15,
                         alignment=TA_CENTER, spaceBefore=16, spaceAfter=10, keepWithNext=1)
TITLE = ParagraphStyle("Title", parent=BODY, fontName=SERIF_BOLD, fontSize=20, leading=25,
                       alignment=TA_CENTER, spaceAfter=14)
CENTERED = ParagraphStyle("Centered", parent=BODY, alignment=TA_CENTER)
SMALL = ParagraphStyle("Small", parent=BODY, fontSize=9, leading=11, spaceAfter=3)

REPORT_BODY = ParagraphStyle("ReportBody", fontName=SANS, fontSize=9.5, leading=13, spaceAfter=6)
REPORT_HEAD = ParagraphStyle("ReportHead", fontName=SANS_BOLD, fontSize=13, leading=16,
                             spaceBefore=4, spaceAfter=8, keepWithNext=1)
REPORT_TITLE = ParagraphStyle("ReportTitle", fontName=SANS_BOLD, fontSize=20, leading=25,
                              spaceAfter=10)


def text(value: str, style: ParagraphStyle = BODY) -> Paragraph:
    return Paragraph(escape(value), style)


def page_frame(header: str, font: str = SERIF):
    def draw(canvas: Any, doc: Any) -> None:
        canvas.saveState()
        canvas.setFont(font, 8.5)
        canvas.setFillColor(colors.HexColor("#444444"))
        width, height = LETTER
        canvas.drawString(inch, height - 0.6 * inch, header)
        canvas.drawCentredString(width / 2, 0.55 * inch, str(doc.page))
        canvas.restoreState()

    return draw


def build(path: Path, story: list[Any], title: str, header: str, font: str = SERIF) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(str(path), pagesize=LETTER, invariant=1, title=title,
                            author="", leftMargin=inch, rightMargin=inch,
                            topMargin=0.9 * inch, bottomMargin=0.9 * inch)
    frame = page_frame(header, font)
    doc.build(story, onFirstPage=frame, onLaterPages=frame)


def table(rows: list[list[Any]], widths: list[float] | None = None, header: bool = True,
          font: str = SANS, size: float = 8.5, align_right_from: int = 1,
          total_row: bool = False) -> Table:
    grid = Table(rows, colWidths=[w * inch for w in widths] if widths else None, repeatRows=1
                 if header else 0)
    style = [
        ("FONT", (0, 0), (-1, -1), font, size),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ALIGN", (align_right_from, 0), (-1, -1), "RIGHT"),
        ("LINEBELOW", (0, -1), (-1, -1), 0.5, colors.black),
        ("TOPPADDING", (0, 0), (-1, -1), 2.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
    ]
    if header:
        style += [
            ("FONT", (0, 0), (-1, 0), SANS_BOLD if font == SANS else SERIF_BOLD, size),
            ("LINEBELOW", (0, 0), (-1, 0), 0.75, colors.black),
            ("LINEABOVE", (0, 0), (-1, 0), 0.75, colors.black),
        ]
    if total_row:
        style += [
            ("FONT", (0, -1), (-1, -1), SANS_BOLD if font == SANS else SERIF_BOLD, size),
            ("LINEABOVE", (0, -1), (-1, -1), 0.5, colors.black),
        ]
    grid.setStyle(TableStyle(style))
    return grid
