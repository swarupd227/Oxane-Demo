"""The validation stage: every loaded file is checked against its client's rule set before any
test is calculated from it.

Code runs the rules and measures change against the prior period. A blocking failure holds the
facility's load until an analyst resolves it. Where a change needs context, the model may read the
documents and say what likely caused it, but only with a quote found in a document; the figures
stay with code.
"""

import hashlib
import re
from decimal import Decimal
from pathlib import Path
from typing import Any

from engine.validation import (
    FAMILY_NAMES,
    Rule,
    blocking,
    exact_duplicates,
    pool_metrics,
    prior_period,
    validate,
)

from app.monitoring import steps
from app.pipeline.documents import normalise

METRIC_NAMES = {
    "pool_balance": "Pool balance",
    "live_loans": "Loans in the pool",
    "weighted_apr": "Weighted APR",
    "weighted_fico": "Weighted FICO",
    "weighted_remaining_term": "Weighted remaining term",
}


def rule_set(record: dict[str, Any], kind: str) -> tuple[list[Rule], str, list[dict[str, Any]]]:
    config = record["validation"][kind]
    rules = [
        Rule(r["id"], r["family"], r["severity"], r["text"], r.get("field", ""), r.get("kind", ""),
             tuple(r.get("allowed", ())))
        for r in config["rules"]
    ]
    return rules, config["key"], config["prior_period"]


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run_feed(
    record: dict[str, Any],
    facility: str,
    file: str,
    path: Path,
    kind: str,
    rows: list[dict[str, Any]],
    prior_rows: list[dict[str, Any]] | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """The feed's validation report, and the rows to load once any block is resolved."""
    rules, key, periods = rule_set(record, kind)
    mapped_fields = set(rows[0]) if rows else set()
    results = validate(
        rows, [r for r in rules if r.family in ("duplicates", "logical") or r.field in
               mapped_fields], key
    )
    by_id = {r.rule.id: r for r in results}
    report_rules = []
    for rule in rules:
        result = by_id.get(rule.id)
        status = "n/a" if result is None else "passed" if result.passed else rule.severity
        report_rules.append({
            "id": rule.id,
            "family": rule.family,
            "family_name": FAMILY_NAMES[rule.family],
            "severity": rule.severity,
            "text": rule.text,
            "field": rule.field,
            "checked": result.checked if result else 0,
            "failed": len(result.failures) if result else 0,
            "status": status,
            "examples": [
                {"key": f.key, "value": f.value, "row": f.row}
                for f in (result.failures[:6] if result else [])
            ],
        })
    held = blocking(results)
    loaded, collapsed = rows, []
    resolution = None
    if held:
        loaded, collapsed = exact_duplicates(rows, key)
        exact = all(r.rule.family == "duplicates" for r in held) and collapsed and not blocking(
            validate(loaded, [r.rule for r in held], key)
        )
        resolution = {
            "rule": held[0].rule.id,
            "proposed": (
                f"The rows for {', '.join(collapsed)} are identical in every field, so loading "
                "one copy loses nothing. Confirm with the sender that the file repeated a line."
                if exact
                else "The rows differ, so only the sender can say which is right. Ask for a "
                "corrected file."
            ),
            "collapsible": bool(exact),
            "collapsed": collapsed,
        }
        if not exact:
            loaded = []
    changes = []
    if prior_rows is not None and periods:
        thresholds = {p["metric"]: (p["basis"], Decimal(str(p["limit"]))) for p in periods}
        texts = {p["metric"]: (p["id"], p["text"]) for p in periods}
        for change in prior_period(pool_metrics(loaded), pool_metrics(prior_rows), thresholds):
            rule_id, text = texts[change.metric]
            changes.append({
                "id": rule_id,
                "metric": change.metric,
                "label": METRIC_NAMES[change.metric],
                "text": text,
                "prior": float(change.prior),
                "current": float(change.current),
                "change": float(change.change),
                "basis": change.basis,
                "limit": float(change.threshold),
                "flagged": change.flagged,
            })
    report = {
        "facility": facility,
        "file": file,
        "kind": kind,
        "sha256": digest(path),
        "rows_in_file": len(rows),
        "rows_loaded": len(loaded),
        "rules": report_rules,
        "prior_period": changes,
        "held": bool(held),
        "resolution": resolution,
        "explanation": None,
    }
    return report, loaded


def explain(
    gateway: Any, evidence: Any, report: dict[str, Any], facility_name: str,
    documents: list[str],
) -> None:
    """Ask the model what caused the flagged changes; keep its answer only if its quote is found
    in the document it names, and every number it wrote is in that quote."""
    flagged = [c for c in report["prior_period"] if c["flagged"]]
    if not flagged:
        return
    placeholders = {
        f"{c['metric']}_change": (
            f"{c['change']:+.2f}%" if c["basis"] == "pct" else f"{c['change']:+.2f}"
        )
        for c in flagged
    }
    facts = [
        {"measure": c["label"], "rule": c["text"], "change": f"{{{{{c['metric']}_change}}}}"}
        for c in flagged
    ]
    reading = steps.explain_change(
        gateway, facility_name, facts, [evidence.add(name) for name in documents]
    )
    source = evidence.cite(reading.document, reading.quote) if reading.document in documents \
        else None
    words = re.sub(r"\{\{\w+\}\}", "", reading.cause)
    numbers = re.findall(r"\d[\d,]*(?:\.\d+)?", words)
    quoted = normalise(reading.quote)
    report["explanation"] = {
        "explained": reading.explained,
        "cause": reading.cause,
        "quote": reading.quote,
        "document": reading.document,
        "source": source,
        "figures": placeholders,
        "verified": bool(source) and all(n in quoted for n in numbers),
        "by": "AI",
    }
