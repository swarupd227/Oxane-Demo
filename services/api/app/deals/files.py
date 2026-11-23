"""Read stored files: PDFs into pages with positions, tapes into rows, workbooks into text."""

import csv
import hashlib
import io
from pathlib import Path
from typing import Any

from openpyxl import load_workbook

from app.deals.models import Document
from app.pipeline.documents import PdfDocument, read_pdf

CACHE = Path("/tmp/oxane-deal-files")


def local_path(doc: Document) -> Path:
    """PDF tools need a file; the database copy is the record, this is a cache."""
    suffix = Path(doc.name).suffix.lower()
    path = CACHE / f"{doc.sha256}{suffix}"
    if not path.exists():
        CACHE.mkdir(parents=True, exist_ok=True)
        path.write_bytes(doc.content)
    return path


def pdf(doc: Document) -> PdfDocument:
    return read_pdf(doc_key(doc), local_path(doc))


def doc_key(doc: Document) -> str:
    return f"DOC-{4000 + doc.id}"


def _cell(value: Any) -> str:
    if value is None:
        return ""
    if hasattr(value, "strftime"):
        return value.strftime("%Y-%m-%d")
    if isinstance(value, float) and value.is_integer() and abs(value) < 1e15:
        return str(int(value))
    return str(value).strip()


def table(doc: Document) -> tuple[list[str], list[dict[str, str]]]:
    """Headers and rows of a CSV, or of the first sheet of a workbook that has a header row."""
    if doc.name.lower().endswith(".csv"):
        text = doc.content.decode("utf-8-sig")
        reader = csv.reader(io.StringIO(text))
        rows = [row for row in reader if any(cell.strip() for cell in row)]
    else:
        book = load_workbook(io.BytesIO(doc.content), read_only=True, data_only=True)
        sheet = book.worksheets[0]
        rows = [[_cell(c) for c in row] for row in sheet.iter_rows(values_only=True)
                if any(c not in (None, "") for c in row)]
    if not rows:
        return [], []
    headers = [h.strip() for h in rows[0]]
    body = [{h: (row[i].strip() if i < len(row) else "") for i, h in enumerate(headers) if h}
            for row in rows[1:]]
    return [h for h in headers if h], body


def workbook_text(doc: Document, limit: int = 200) -> str:
    book = load_workbook(io.BytesIO(doc.content), read_only=True, data_only=False)
    lines = []
    for sheet in book.worksheets:
        lines.append(f"[sheet {sheet.title}]")
        for r, row in enumerate(sheet.iter_rows(values_only=True), start=1):
            cells = [_cell(c) for c in row]
            if any(cells):
                lines.append(f"row {r}: " + " | ".join(cells))
            if len(lines) > limit:
                break
    return "\n".join(lines)


def workbook_cells(doc: Document) -> list[tuple[str, str, str, Any]]:
    """(sheet, cell, label to its left, value) for every number in a workbook."""
    book = load_workbook(io.BytesIO(doc.content), data_only=True)
    found = []
    for sheet in book.worksheets:
        for row in sheet.iter_rows():
            label = ""
            for cell in row:
                if isinstance(cell.value, str) and not cell.value.startswith("="):
                    label = cell.value
                elif isinstance(cell.value, int | float) and label:
                    found.append((sheet.title, cell.coordinate, label, cell.value))
    return found


def preview(doc: Document) -> str:
    """The first part of a file, enough to tell what it is."""
    name = doc.name.lower()
    if name.endswith(".pdf"):
        document = pdf(doc)
        return "\n".join(page.raw for page in document.pages[:2])[:2500]
    if name.endswith(".csv"):
        return "\n".join(doc.content.decode("utf-8-sig").splitlines()[:4])
    return workbook_text(doc, limit=12)


def signature(headers: list[str]) -> str:
    """A layout's identity: its column names, in any order."""
    canonical = "\n".join(sorted(h.strip().lower() for h in headers))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
