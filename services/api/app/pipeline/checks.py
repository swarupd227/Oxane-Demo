"""Deterministic checks. No model is involved in anything in this file."""

import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime

from app.pipeline.documents import PdfDocument, normalise

REFERENCE = re.compile(r"\b(Schedule|Annex|Exhibit) (\d+|[A-Z])\b")
HEADING = re.compile(r"^\s*(SCHEDULE|ANNEX|EXHIBIT) (\d+|[A-Z])\b(?! \.)", re.M)
DEALER_SUFFIX = re.compile(r"[,.]?\s+(LLC|INC|LTD|CORP|CO)\.?$", re.I)
EARLIEST_GAP_DAYS, LATEST_GAP_DAYS = 20, 60


def missing_attachments(agreement: PdfDocument, scans: list[str]) -> list[dict[str, str]]:
    """Every schedule the agreement refers to must have a page of its own."""
    referred = {(kind.lower(), number)
                for page in agreement.pages for kind, number in REFERENCE.findall(page.raw)}
    present = set()
    for page in agreement.pages:
        if page.number <= 5:  # The contents list names schedules without being them.
            continue
        for kind, number in HEADING.findall(page.raw):
            present.add((kind.lower(), number))
    # An image-only page cannot show its heading, so the scan read supplies it.
    for text in scans:
        for kind, number in HEADING.findall(text):
            present.add((kind.lower(), number))
    return [{"name": f"{kind.title()} {number}", "reason": "Referred to in the credit agreement "
             "but not in the pack"}
            for kind, number in sorted(referred - present)]


def _parse(raw: str, pattern: str) -> date | None:
    try:
        return datetime.strptime(raw, pattern).date()
    except ValueError:
        return None


@dataclass(frozen=True)
class DateReview:
    mixed_rows: int
    day_first_rows: int
    uncertain_rows: tuple[str, ...]
    resolved: dict[str, str]


def review_dates(rows: list[dict[str, str]], date_field: str, anchor_field: str,
                 id_field: str) -> DateReview:
    """Resolve each date against a later date in the same row, and count what stays uncertain."""
    resolved: dict[str, str] = {}
    uncertain: list[str] = []
    day_first = 0
    for row in rows:
        raw = row[date_field]
        anchor = date.fromisoformat(row[anchor_field])
        month_first_value = _parse(raw, "%m/%d/%Y")
        day_first_value = _parse(raw, "%d/%m/%Y")
        plausible = {value for value in (month_first_value, day_first_value)
                     if value and EARLIEST_GAP_DAYS <= (anchor - value).days <= LATEST_GAP_DAYS}
        if len(plausible) == 1:
            value = plausible.pop()
            resolved[row[id_field]] = value.isoformat()
            if value == day_first_value and value != month_first_value:
                day_first += 1
        else:
            uncertain.append(row[id_field])
            fallback = month_first_value or day_first_value
            resolved[row[id_field]] = fallback.isoformat() if fallback else ""
    return DateReview(day_first + len(uncertain), day_first, tuple(uncertain), resolved)


def dealer_key(name: str) -> str:
    return normalise(DEALER_SUFFIX.sub("", name.strip())).lower()


def dealer_variants(names: list[str]) -> list[list[str]]:
    """Group names that differ only by case, punctuation or company suffix."""
    groups: defaultdict[str, set[str]] = defaultdict(set)
    for name in names:
        groups[dealer_key(name)].add(name)
    return [sorted(group) for _, group in sorted(groups.items()) if len(group) > 1]


def blank_money_lines(document: PdfDocument) -> list[tuple[str, int]]:
    """Report lines labelled as an amount, with no amount beside them."""
    blanks = []
    for page in document.pages:
        for line in page.raw.splitlines():
            stripped = line.strip()
            if stripped.endswith("(US$)") and stripped != "(US$)" and "Amount" not in stripped:
                blanks.append((stripped, page.number))
    return blanks


def contains_value(value: str, quote: str) -> bool:
    """Every figure in a value must appear in its quote, or the quote does not support it."""
    figures = re.findall(r"\d[\d,]*\.?\d*", value)
    compact = quote.replace(",", "")
    return all(figure.replace(",", "").rstrip(".") in compact for figure in figures)


def values_agree(first: str, second: str) -> bool:
    def figures(text: str) -> list[str]:
        return sorted(item.replace(",", "") for item in re.findall(r"\d[\d,]*\.?\d*", text))

    both = figures(first), figures(second)
    if both[0] or both[1]:
        return both[0] == both[1]
    # Two readers rarely word a sentence alike, so prose agrees if most of its words match.
    words = [set(re.findall(r"[a-z]+", text.lower())) - {"the", "a", "an", "of"}
             for text in (first, second)]
    return len(words[0] & words[1]) / max(len(words[0] | words[1]), 1) >= 0.6
