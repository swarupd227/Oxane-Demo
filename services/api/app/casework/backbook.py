"""The backbook: existing deals loaded with the stored mapping, exceptions only where they differ.

Code applies Bramble's stored mapping to each tape and lists only what does not fit: a column the
mapping does not know, a stored column that is absent, blanks where a value is required, codes
outside the stored reference data. The model suggests what each difference means; code checks
every suggestion against the tape before an analyst can accept it.
"""

import csv
from collections import Counter
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from engine.run import INTEGER_FIELDS, MONEY_FIELDS

from app.casework.steps import BackbookSuggestion
from app.pipeline.catalogue import PLATFORM_FIELDS

CUTOFF = date(2026, 4, 30)
RANGES = {"fico": (300, 850), "days_past_due": (0, 999), "original_term": (1, 120),
          "model_year": (1990, 2027)}


def read(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _fits(field: str, value: str) -> bool:
    if value == "":
        return False
    if field in INTEGER_FIELDS:
        try:
            number = int(value)
        except ValueError:
            return False
        low, high = RANGES.get(field, (0, 10**9))
        return low <= number <= high
    if field in MONEY_FIELDS:
        try:
            return Decimal(value) >= 0
        except InvalidOperation:
            return False
    return True


def differences(deal: dict[str, Any], rows: list[dict[str, str]], stored: dict[str, str],
                statuses: set[str]) -> list[dict[str, Any]]:
    header = list(rows[0])
    absent = [column for column in stored if column not in header]
    found = []
    for column in header:
        if column not in stored:
            found.append({"deal": deal["id"], "column": column, "kind": "unknown_column",
                          "absent_stored_columns": absent,
                          "samples": sorted({row[column] for row in rows})[:6]})
    for column, field in stored.items():
        if column not in header:
            continue
        if field in INTEGER_FIELDS or field in MONEY_FIELDS:
            blanks = sum(1 for row in rows if row[column] == "")
            if blanks:
                found.append({"deal": deal["id"], "column": column, "kind": "blank_values",
                              "field": field, "rows": blanks,
                              "statuses_of_blank_rows": dict(Counter(
                                  row.get("LoanStatus", "") for row in rows
                                  if row[column] == ""))})
        if field == "status":
            codes = sorted({row[column] for row in rows} - statuses)
            if codes:
                found.append({"deal": deal["id"], "column": column, "kind": "code_values",
                              "field": field, "codes": codes,
                              "stored_values": sorted(statuses),
                              "rows": sum(1 for row in rows if row[column] in codes)})
    return found


def _due_after_cutoff(row: dict[str, str]) -> bool:
    try:
        return datetime.strptime(row.get("NextDueDate", ""), "%Y-%m-%d").date() > CUTOFF
    except ValueError:
        return False


def check(suggestion: BackbookSuggestion, difference: dict[str, Any],
          rows: list[dict[str, str]], stored: dict[str, str], statuses: set[str]
          ) -> tuple[bool, str]:
    """Whether the tape bears the suggestion out, and the evidence either way."""
    column = difference["column"]
    if difference["kind"] == "unknown_column":
        if suggestion.field is None:
            return True, "Kept as raw data on the loan record; no platform field is loaded"
        if suggestion.field not in PLATFORM_FIELDS:
            return False, f"{suggestion.field} is not a platform field"
        if suggestion.field in stored.values() and stored_column(stored, suggestion.field) \
                not in difference["absent_stored_columns"]:
            return False, f"{suggestion.field} is already loaded from another column"
        bad = sum(1 for row in rows if not _fits(suggestion.field, row[column]))
        if bad:
            return False, f"{bad} values do not fit {suggestion.field}"
        return True, (f"All {len(rows)} values fit {suggestion.field}, and the stored column "
                      f"{stored_column(stored, suggestion.field)} is absent from this tape")
    if difference["kind"] == "blank_values":
        blanks = [row for row in rows if row[column] == ""]
        if suggestion.treat_blank_as is None:
            balance = sum(float(row["CurrBal"]) for row in blanks)
            return False, (f"Leaving {len(blanks)} rows out would drop US${balance:,.2f} of "
                           "receivables from the load; an expert has to decide")
        if not _fits(difference["field"], suggestion.treat_blank_as):
            return False, f"{suggestion.treat_blank_as} does not fit {difference['field']}"
        current = [row for row in blanks if _due_after_cutoff(row)
                   and row.get("ChgOffDate", "") == "" and row.get("RepoDate", "") == ""]
        if len(current) != len(blanks):
            return False, (f"{len(blanks) - len(current)} of the blank rows are not current, so "
                           "a blank cannot mean zero days past due")
        return True, (f"All {len(blanks)} blank rows are current: next payment due after the "
                      "cut-off, no charge-off or repossession date")
    if difference["kind"] == "code_values":
        mapping = {pair[0]: pair[1] for pair in suggestion.code_map if len(pair) == 2}
        codes = set(difference["codes"])
        if set(mapping) != codes:
            return False, "The map does not cover exactly the codes on the tape"
        if not set(mapping.values()) <= statuses:
            return False, "The map uses a value outside the stored reference data"
        if len(set(mapping.values())) != len(mapping):
            return False, "Two codes map to the same value"
        evidence = []
        for code, status in sorted(mapping.items()):
            chosen = [row for row in rows if row[column] == code]
            if status == "CHARGED_OFF" and not all(row.get("ChgOffDate") for row in chosen):
                return False, f"Some {code} rows have no charge-off date"
            if status == "REPO" and not all(row.get("RepoDate") for row in chosen):
                return False, f"Some {code} rows have no repossession date"
            if status == "DELINQUENT" and not all(int(row.get("DPD") or 0) > 30
                                                 for row in chosen):
                return False, f"Some {code} rows are not more than 30 days past due"
            evidence.append(f"{code} ({len(chosen)} rows) to {status}")
        return True, "Each code agrees with the dates and days past due on its rows: " + \
            "; ".join(evidence)
    return False, "Unknown difference"


def stored_column(stored: dict[str, str], field: str) -> str | None:
    return next((column for column, name in stored.items() if name == field), None)


def load(folder: Path, deals: list[dict[str, Any]], stored: dict[str, str], statuses: set[str]
         ) -> tuple[list[dict[str, Any]], dict[str, list[dict[str, str]]]]:
    views, tapes = [], {}
    for deal in deals:
        rows = read(folder / deal["file"])
        tapes[deal["id"]] = rows
        found = differences(deal, rows, stored, statuses)
        header = list(rows[0])
        views.append({
            **deal, "rows": len(rows), "columns": len(header),
            "matched": sum(1 for column in header if column in stored),
            "stored": len(stored),
            "pool_balance": round(sum(float(row["CurrBal"]) for row in rows), 2),
            "differences": found,
        })
    return views, tapes


def attach(views: list[dict[str, Any]], tapes: dict[str, list[dict[str, str]]],
           suggestions: list[BackbookSuggestion], stored: dict[str, str],
           statuses: set[str]) -> None:
    for view in views:
        for difference in view["differences"]:
            match = next((s for s in suggestions if s.deal == view["id"]
                          and s.column == difference["column"]), None)
            if match is None:
                difference["suggestion"] = None
                difference["check"] = {"ok": False, "evidence": "No suggestion"}
                continue
            ok, evidence = check(match, difference, tapes[view["id"]], stored, statuses)
            difference["suggestion"] = {
                "kind": match.kind, "field": match.field, "treat_blank_as": match.treat_blank_as,
                "code_map": match.code_map, "reason": match.reason}
            difference["check"] = {"ok": ok, "evidence": evidence}
        view["exceptions"] = len(view["differences"])
        view["clean"] = not view["differences"]
