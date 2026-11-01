"""The scorecard. This is the only code that compares a run with the answer key."""

from datetime import date, datetime
from typing import Any

from app import engine_service
from app.engine_service import read_key


def _clean(text: str) -> str:
    return text.lower().replace(",", "")


def _dates(iso: str) -> list[str]:
    """The ways a value may fairly write a date."""
    day: date = date.fromisoformat(iso)
    return [iso, f"{day:%B} {day.day} {day.year}", f"{day.day} {day:%B} {day.year}",
            f"{day.day} {day:%b} {day.year}"]


def _money_or_count(expected: Any) -> list[list[str]]:
    number = float(expected)
    return [[str(int(number))] if number.is_integer() else [f"{number:.2f}"]]


def expected_fragments(field: dict[str, Any]) -> list[list[str]]:
    """What a correct value must contain. Each inner list is a set of accepted spellings."""
    name, value = field["name"], field["value"]
    if name == "Advance rate":
        return [["82.5"], _dates("2026-03-01")]
    if name in ("Revolving period end", "Final maturity", "Signing date"):
        return [_dates(value)]
    if name == "Amendment dates":
        return [_dates(value["signed"]), _dates(value["effective"])]
    if name == "Maximum leverage covenant":
        return [["6.00", "6.0"]]
    if name == "Excess concentration treatment":
        return [["exclud", "deduct"]]
    if name == "Reserve amount":
        return [["1%"]]
    if name == "Delinquency trigger":
        return [["6.0"]]
    if name == "Margin":
        return [["3.25"]]
    if name == "Unused fee":
        return [["0.50"]]
    if name == "Interest period and payment date":
        return [["month"], ["15"]]
    if name == "Borrowing base reporting date":
        return [["15th"]]
    if name == "Financial statement reporting":
        return [["45"], ["120"]]
    if name == "Governing law":
        return [["new york"]]
    if name == "Borrower, parent and servicer names":
        return [[_clean(item)] for item in value.values()]
    if name == "Lender and agent names":
        return [[_clean(value)]]
    if name == "Notice addresses":
        return [[_clean(address.split(",")[0])] for address in value.values()]
    return _money_or_count(value)


def value_is_correct(field: dict[str, Any], term: dict[str, Any], shown: str) -> bool:
    if field["value"] is None:  # Restricted jurisdictions: the right answer is that it is absent.
        return term["status"] == "missing"
    if term["status"] == "missing":
        return False
    cleaned = _clean(shown)
    return all(any(_clean(option) in cleaned for option in options)
               for options in expected_fragments(field))


def _field_results(run: dict[str, Any], edits: dict[str, str]) -> list[dict[str, Any]]:
    terms = {term["name"]: term for term in run["terms"]}
    results = []
    for field in read_key("fields"):
        term = terms[field["name"]]
        reviewed = edits.get(field["name"], term["value"])
        results.append({
            "name": field["name"], "tier": field["tier"], "value": term["value"],
            "before_review": value_is_correct(field, term, term["value"]),
            "after_review": value_is_correct(field, term, reviewed),
        })
    return results


def _exception_results(run: dict[str, Any]) -> tuple[list[str], list[str]]:
    """Match on substance, not only on the id the pipeline gave an item."""
    key = read_key("exceptions")
    found: dict[str, dict[str, Any]] = {item["id"]: item for item in run["exceptions"]}
    tests = {
        "X4": lambda item: str(key["X4"]["loans"]) in item["title"],
        "X5": lambda item: (str(key["X5"]["loans"]) in item["title"]
                            and str(len(key["X5"]["clusters"])) in item["title"]),
        "X6": lambda item: all(name in item["title"] for name in key["X6"]["names"]),
    }
    matched = [ident for ident in key if ident in found
               and tests.get(ident, lambda _: True)(found[ident])]
    false_items = [item["id"] for item in run["exceptions"] if item["id"] not in matched]
    return matched, false_items


def _rule_results() -> tuple[int, int, list[str]]:
    outcome = engine_service.validation_run(dealer_match=False)
    expected = read_key("rules")
    wrong = [rule["id"] for rule in outcome["rules"]
             if expected[rule["id"]]["status"] == "evaluated"
             and rule["failed"] != expected[rule["id"]]["failed"]]
    evaluated = sum(1 for item in expected.values() if item["status"] == "evaluated")
    return evaluated - len(wrong), evaluated, wrong


def _minutes(start: str, end: str) -> int:
    first, last = datetime.fromisoformat(start), datetime.fromisoformat(end)
    return max(0, round((last - first).total_seconds() / 60))


def _rate(rows: list[dict[str, Any]], tier_test: Any, key: str) -> tuple[int, int, list[str]]:
    chosen = [row for row in rows if tier_test(row["tier"])]
    wrong = [f"{row['name']}: {row['value']}" for row in chosen if not row[key]]
    return len(chosen) - len(wrong), len(chosen), wrong


def scorecard(run: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
    if run.get("seed"):
        return {"available": False, "measures": []}

    rows = _field_results(run, state["termEdits"])
    tier1_before = _rate(rows, lambda tier: tier == 1, "before_review")
    tier1_after = _rate(rows, lambda tier: tier == 1, "after_review")
    others = _rate(rows, lambda tier: tier > 1, "before_review")
    matched, false_items = _exception_results(run)
    planted = read_key("exceptions")
    missed = [ident for ident in planted if ident not in matched]
    rules_right, rules_total, rules_wrong = _rule_results()
    queue, processed = len(run["exceptions"]), len(run["terms"]) + len(run["rules"])
    usage = run["usage"]

    live = [entry for entry in state["audit"] if not entry["earlier"]]
    started, approved = state["startedAt"], state["approvedAt"]
    terms_done = sum(1 for status in state["termApprovals"].values() if status == "approved")
    earlier = sum(1 for entry in state["audit"] if entry["earlier"])

    def measure(name: str, formula: str, target: str, value: str,
                details: list[str] | None = None, passed: bool | None = None) -> dict[str, Any]:
        return {"name": name, "formula": formula, "target": target, "value": value,
                "details": details or [], "passed": passed}

    measures = [
        measure("Field-level accuracy, Tier 1, before review", "Correct values / fields extracted",
                "No target set", f"{tier1_before[0]} of {tier1_before[1]}", tier1_before[2]),
        measure("Field-level accuracy, Tier 1, after review", "Correct values after analyst edits",
                "Every value correct", f"{tier1_after[0]} of {tier1_after[1]}", tier1_after[2],
                tier1_after[0] == tier1_after[1]),
        measure("Field-level accuracy, Tier 2 and 3", "Correct values / fields extracted",
                "No target set", f"{others[0]} of {others[1]}", others[2]),
        measure("Material errors and omissions", "Tier 1 values wrong or missing before review",
                "No target set, each listed", str(len(tier1_before[2])), tier1_before[2]),
        measure("Exceptions found", "Reference exceptions found / 10", "10 of 10",
                f"{len(matched)} of {len(planted)}", [f"Missed: {item}" for item in missed],
                len(matched) == len(planted)),
        measure("False positives", "Queue items not in the reference set", "3 or fewer",
                str(len(false_items)), false_items, len(false_items) <= 3),
        measure("Rule results", "Rules matching the reference result on the tape",
                "No target set", f"{rules_right} of {rules_total}", rules_wrong),
        measure("Exception rate", "Queue items / fields and rules processed",
                "No target set", f"{queue} of {processed} ({queue / processed:.1%})"),
        measure("Processing cost", "Logged model usage for the pack", "No target set",
                f"US${usage['cost_usd']:.2f}",
                [f"{usage['calls']} calls to {usage['model']}",
                 f"{usage['input_tokens'] + usage['output_tokens']:,} uncached tokens"]),
        measure("Pipeline run time", "Time spent in model calls when the run was recorded",
                "No target set",
                f"{usage['model_seconds']} s" if usage.get("model_seconds") else "Not recorded"),
        measure("Analyst effort", "Actions an analyst took in this session",
                "No target set", f"{len(live)} actions, {terms_done} terms approved",
                [f"{earlier} more were preloaded in the sandbox"]),
        measure("Onboarding time", "Pack upload to approved load file, this session",
                "No target set",
                f"{_minutes(started, approved)} min" if started and approved
                else "In progress"),
    ]
    return {
        "available": True,
        "measures": measures,
        "caveat": "Extraction was tuned on this synthetic pack. Results are not independent and "
                  "do not indicate accuracy on live facilities.",
    }
