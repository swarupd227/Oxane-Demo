"""Read PDFs into pages, and find quotes in them. This is what keeps citations honest."""

import io
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pypdfium2

SECTION = re.compile(r"^(\d{1,2}\.\d{1,2}) [A-Z]")
IMAGE_ONLY_BELOW = 60  # Characters. A scan carries little more than the running header.


def normalise(text: str) -> str:
    return " ".join(text.split())


@dataclass(frozen=True)
class Page:
    number: int
    raw: str
    text: str

    @property
    def is_image_only(self) -> bool:
        return len(self.text) < IMAGE_ONLY_BELOW


@dataclass(frozen=True)
class PdfDocument:
    id: str
    path: Path
    pages: tuple[Page, ...]

    @property
    def body(self) -> str:
        """Full text with page markers, for the model to read."""
        return "\n\n".join(f"[page {page.number}]\n{page.raw}" for page in self.pages)

    def sections(self) -> list[tuple[str, str, int]]:
        """Clause anchors: section number, title and page."""
        anchors = []
        for page in self.pages:
            for line in page.raw.splitlines():
                stripped = line.strip()
                if SECTION.match(stripped) and ". ." not in stripped:
                    number, _, title = stripped.partition(" ")
                    anchors.append((number, title, page.number))
        return anchors


def read_pdf(document_id: str, path: Path) -> PdfDocument:
    pdf = pypdfium2.PdfDocument(str(path))
    try:
        pages = []
        for number, page in enumerate(pdf, start=1):
            raw = page.get_textpage().get_text_range().replace("\r\n", "\n")
            pages.append(Page(number, raw, normalise(raw)))
        return PdfDocument(document_id, path, tuple(pages))
    finally:
        pdf.close()


def render_page_png(path: Path, page_number: int, scale: float = 2.0) -> bytes:
    pdf = pypdfium2.PdfDocument(str(path))
    try:
        image = pdf[page_number - 1].render(scale=scale).to_pil()
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        return buffer.getvalue()
    finally:
        pdf.close()


def quote_rects(path: Path, page_number: int, quote: str) -> list[dict[str, float]]:
    """One rectangle per line of a quote, as fractions of the page. Empty if it is not there."""
    pdf = pypdfium2.PdfDocument(str(path))
    try:
        page = pdf[page_number - 1]
        width, height = page.get_size()
        textpage = page.get_textpage()
        raw = textpage.get_text_range()

        # Collapse whitespace, remembering where each kept character came from.
        collapsed: list[str] = []
        origin: list[int] = []
        for index, char in enumerate(raw):
            if char.isspace():
                if collapsed and collapsed[-1] != " ":
                    collapsed.append(" ")
                    origin.append(index)
            else:
                collapsed.append(char)
                origin.append(index)

        needle = normalise(quote)
        start = "".join(collapsed).find(needle)
        if start < 0:
            return []

        # A new line starts wherever the text jumps back to the left.
        lines: list[list[tuple[float, float, float, float]]] = []
        for index in origin[start:start + len(needle)]:
            if raw[index].isspace():
                continue
            box = textpage.get_charbox(index)
            if not lines or box[0] < lines[-1][-1][0]:
                lines.append([])
            lines[-1].append(box)
        return [{
            "x0": min(box[0] for box in boxes) / width,
            "x1": max(box[2] for box in boxes) / width,
            "top": 1 - max(box[3] for box in boxes) / height,
            "bottom": 1 - min(box[1] for box in boxes) / height,
        } for boxes in lines]
    finally:
        pdf.close()


def find_citation(documents: dict[str, PdfDocument], document_id: str,
                  quote: str) -> dict[str, Any] | None:
    """Find a quote in its document. A quote that is not found verifies nothing."""
    document = documents.get(document_id)
    needle = normalise(quote)
    if document is None or not needle:
        return None
    pages = [page.number for page in document.pages if needle in page.text]
    if not pages:
        return None
    # Schedule headings also appear in the contents, so the last match is the real one.
    page = pages[-1]
    return {"document": document_id, "page": page,
            "rects": quote_rects(document.path, page, quote)}
