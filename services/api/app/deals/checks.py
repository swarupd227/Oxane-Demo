"""Code checks on everything the model or an analyst supplies. Nothing reaches a calculation
until it has passed here."""

import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from engine.generic import FIELDS, STATUSES, is_type, number, parse_date

from app.pipeline.documents import PdfDocument, find_citation, normalise

FIGURE = re.compile(r"\d[\d,]*(?:\.\d+)?")


def figures(text: str) -> list[Decimal]:
    found = []
    for raw in FIGURE.findall(text or ""):
        try:
            found.append(Decimal(raw.replace(",", "")))
        except InvalidOperation:
            continue
    return found


def figures_in_quote(value: str, quote: str) -> bool:
    """Every figure in the value appears in the quote, so the model cannot add one."""
    wanted, given = figures(value), figures(quote)
    return all(any(w == g for g in given) for w in wanted)


def cite(documents: dict[str, PdfDocument], document: str, quote: str) -> dict[str, Any] | None:
    if not quote.strip():
        return None
    return find_citation(documents, document, quote)


def on_page(documents: dict[str, PdfDocument], document: str, page: int,
            value: str) -> bool:
    """A manually entered value: each of its figures, or its words, appear on the stated page."""
    doc = documents.get(document)
    if doc is None or not 1 <= page <= len(doc.pages):
        return False
    text = doc.pages[page - 1].text
    wanted = figures(value)
    if wanted:
        given = figures(text)
        return all(any(w == g for g in given) for w in wanted)
    return normalise(value).lower() in text.lower()


MONTHS = "January February March April May June July August September October November December"


def parse_term(unit: str, value: str) -> tuple[Any, str | None]:
    """The typed value of a term, or None and why it could not be read."""
    text = (value or "").strip()
    if not text:
        return None, "No value"
    if unit == "money":
        found = figures(text)
        if len(found) != 1:
            return None, "Expected one amount"
        scale = 1_000_000 if re.search(r"\bmillion\b|\bm\b", text, re.I) else 1
        return int(found[0] * scale), None
    if unit == "pct":
        found = figures(text)
        if len(found) != 1 or "%" not in text and "per cent" not in text.lower():
            return None, "Expected one percentage"
        return str(found[0].quantize(Decimal("0.01"))), None
    if unit == "day":
        found = figures(text)
        if len(found) != 1 or not 1 <= found[0] <= 31:
            return None, "Expected a day of the month"
        return int(found[0]), None
    if unit == "date":
        parsed = parse_date(text)
        if parsed is None:
            for pattern in ("%B %d, %Y", "%d %B %Y", "%B %d %Y"):
                try:
                    parsed = datetime.strptime(text.replace("  ", " "), pattern).date()
                    break
                except ValueError:
                    continue
        if parsed is None:
            return None, "Expected a date"
        return parsed.isoformat(), None
    return text, None


def iso(value: str | None) -> str | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value[:10]).isoformat()
    except ValueError:
        return None


# Mapping


SYNONYMS: dict[str, tuple[str, ...]] = {
    "loan_id": ("loan id", "loan number", "account", "accountno", "facility ref", "loan ref",
                "reference", "contract"),
    "obligor_id": ("borrower id", "obligor id", "customer id", "client id"),
    "origination_date": ("origination", "drawdown", "start date", "funded", "booked"),
    "maturity_date": ("maturity", "final repayment", "end date"),
    "original_balance": ("original principal", "orig principal", "origprincipal",
                         "original balance", "amount financed", "loan amount"),
    "current_balance": ("current principal", "currprincipal", "outstanding", "current balance",
                        "principal balance"),
    "apr": ("apr", "rate", "interest"),
    "original_term": ("term months", "termmonths", "term (m)", "original term"),
    "remaining_term": ("remaining", "remterm", "rem term"),
    "days_past_due": ("days delinquent", "daysdelinquent", "arrears", "dpd", "days past due"),
    "status": ("status",),
    "credit_score": ("fico", "credit score", "bureau"),
    "risk_grade": ("risk grade", "grade", "rating"),
    "obligor_state": ("state",),
    "region": ("region",),
    "sector": ("sector", "industry"),
    "product": ("product", "category", "purpose"),
    "merchant": ("merchant", "dealer", "retailer"),
    "collateral_type": ("collateral", "security"),
}
STATUS_WORDS = {
    "performing": ("current", "performing", "active", "ok"),
    "arrears": ("delinquent", "arrears", "late", "past due"),
    "defaulted": ("default",),
    "charged_off": ("charged", "written", "write"),
    "paid_off": ("paid", "repaid", "closed", "settled"),
}


def _flat(text: str) -> str:
    return re.sub(r"[^a-z0-9()]+", " ", text.lower()).strip()


def heuristic_mapping(headers: list[str]) -> dict[str, str | None]:
    """Name matching only, for a client that does not permit AI. The analyst confirms each."""
    used: set[str] = set()
    result: dict[str, str | None] = {}
    for header in headers:
        flat = _flat(header)
        squashed = flat.replace(" ", "")
        match = None
        for name, words in SYNONYMS.items():
            if name in used:
                continue
            if any(_flat(w) == flat or _flat(w).replace(" ", "") == squashed for w in words):
                match = name
                break
        if match is None:
            for name, words in SYNONYMS.items():
                if name not in used and any(_flat(w) in flat for w in words):
                    match = name
                    break
        result[header] = match
        if match:
            used.add(match)
    return result


def heuristic_statuses(values: list[str]) -> dict[str, str]:
    result = {}
    for value in values:
        flat = value.lower().replace("_", " ")
        for status, words in STATUS_WORDS.items():
            if any(w in flat for w in words):
                result[value] = status
                break
    return result


def check_column(field: str, values: list[str]) -> str | None:
    """Why a column's values do not fit a field, or None if they do."""
    if field not in FIELDS:
        return "Not a platform field"
    kind = FIELDS[field][0]
    filled = [v for v in values if str(v).strip()]
    if not filled:
        return "Column is blank"
    bad = [v for v in filled if not is_type(v, kind)]
    if bad:
        return f"{len(bad)} values are not {kind}s, for example {bad[0]!r}"
    nums = [number(v) for v in filled]
    ranges = {"credit_score": (250, 900), "days_past_due": (0, 2000), "risk_grade": (0, 30),
              "apr": (0, 100), "original_term": (1, 600), "remaining_term": (0, 600)}
    if field in ranges:
        low, high = ranges[field]
        out = [n for n in nums if n is not None and not low <= n <= high]
        if out:
            return f"{len(out)} values outside {low} to {high}"
    if field in ("original_balance", "current_balance"):
        if any(n is not None and n < 0 for n in nums):
            return "Negative balances"
    if field == "obligor_state" and any(len(v.strip()) != 2 for v in filled):
        return "Not two-letter state codes"
    return None


def check_mapping(columns: dict[str, str | None], rows: list[dict[str, str]],
                  status_map: dict[str, str]) -> list[dict[str, Any]]:
    """Each column's mapping with the result of checking it against the tape."""
    checked = []
    seen: set[str] = set()
    for column, field in columns.items():
        values = [row.get(column, "") for row in rows]
        problem = None
        if field:
            problem = check_column(field, values)
            if field in seen:
                problem = "Field already mapped from another column"
            seen.add(field)
        checked.append({"column": column, "field": field, "problem": problem,
                        "sample": next((v for v in values if v), "")})
    missing = [f for f in ("loan_id", "current_balance", "status", "days_past_due")
               if f not in seen]
    for field in missing:
        checked.append({"column": None, "field": field, "problem": "Required field not mapped",
                        "sample": ""})
    status_column = next((c for c, f in columns.items() if f == "status"), None)
    if status_column:
        values = sorted({row.get(status_column, "") for row in rows})
        unmapped = [v for v in values if v and status_map.get(v) not in STATUSES]
        if unmapped:
            checked.append({"column": status_column, "field": "status",
                            "problem": "Status values not mapped: " + ", ".join(unmapped),
                            "sample": ""})
    return checked


def fill(template: str, values: dict[str, str]) -> tuple[str, list[str]]:
    """Fill {{placeholders}}; report unknown ones. Text with a bare figure is refused."""
    unknown = []

    def replace(match: re.Match[str]) -> str:
        key = match.group(1).strip()
        if key not in values:
            unknown.append(key)
            return match.group(0)
        return values[key]

    stripped = re.sub(r"\{\{[^}]+\}\}", "", template)
    if re.search(r"\d", stripped):
        unknown.append("a figure written outside a placeholder")
    return re.sub(r"\{\{([^}]+)\}\}", replace, template), unknown


__all__ = ["MONTHS"]
