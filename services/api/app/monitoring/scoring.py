"""The cycle scorecard: the RFP's use case 2 measures, computed against the cycle answer key.

This is the only code that reads the key. The pipeline never does.
"""

import json
from datetime import datetime
from typing import Any

from app.config import settings

# Planted issue -> the finding that should catch it, and the outcome it should end with.
ISSUES = {
    "M1": ("F-late-servicer-report", "query"),
    "M2": ("F-roll-forward", "query"),
    "M3": ("F-charge-offs", "query"),
    "M4": ("F-terms-", "logged"),
    "M5": ("F-northmoor-delinquency", "confirmed"),
    "M6": ("F-bramble-leverage", "expert"),
    "M7": ("F-shared-vin", "confirmed"),
    "M8": ("F-kestrel-markdown", "expert"),
    "M9": ("F-kestrel-stale-valuation", "query"),
}
NOISE = {"N1": "F-layout-", "N2": "F-northmoor-collections", "N3": "F-certificate-rounding"}


def read_key() -> dict[str, Any] | None:
    path = settings.deal_kit_output / "cycle-key" / "key.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def _close(a: float, b: float, tolerance: float = 0.005) -> bool:
    return abs(float(a) - float(b)) <= tolerance


def accuracy(cycle: dict[str, Any], key: dict[str, Any]) -> list[tuple[str, bool]]:
    """Each value the cycle extracted or reconciled, against the key."""
    checks, recon, tests = key["checks"], cycle["reconciliation"], cycle["tests"]
    b, n, k = tests["bramble"], tests["northmoor"], tests["kestrel"]
    terms = {t["name"]: t for t in cycle["terms"]["terms"]}
    nd, kd = checks["northmoor_delinquency"], checks["kestrel"]
    spread = {m["month"].split()[0].lower(): m["value"] for m in n["excess_spread_months"]}
    return [
        ("Roll-forward gap", _close(recon["roll_forward"]["gap"], checks["roll_forward"]["gap"])),
        (
            "Missing loans",
            sorted(m["loan_id"] for m in recon["roll_forward"]["missing"])
            == sorted(key["issues"]["M2"]["loans"]),
        ),
        (
            "Charge-off difference",
            _close(recon["charge_offs"]["difference"], checks["charge_offs"]["difference"]),
        ),
        (
            "Charge-off loans",
            sorted(i["loan_id"] for i in recon["charge_offs"]["loans"])
            == sorted(key["issues"]["M3"]["loans"]),
        ),
        (
            "Facility limit in force for May",
            terms["Facility limit"]["value_in_force"].replace("US$", "").replace(",", "")
            == str(checks["terms_version"]["may"]["facility_limit"]),
        ),
        (
            "Dealer limit in force for May",
            terms["Dealer concentration limit"]["value_in_force"].rstrip("%")
            == str(checks["terms_version"]["may"]["dealer_limit_pct"]),
        ),
        (
            "Dealer limit from June",
            terms["Dealer concentration limit"]["next_value"].rstrip("%")
            == str(checks["terms_version"]["june"]["dealer_limit_pct"]),
        ),
        (
            "Bramble eligible pool",
            _close(
                b["borrowing_base"]["system"]["eligible_pool"],
                checks["bramble_borrowing_base"]["system"]["eligible_pool"],
            ),
        ),
        (
            "Bramble borrowing base",
            _close(
                b["borrowing_base"]["system"]["borrowing_base"],
                checks["bramble_borrowing_base"]["system"]["borrowing_base"],
            ),
        ),
        (
            "Bramble delinquency, May",
            _close(b["delinquency"]["monthly"][-1]["value"], checks["bramble_delinquency"]["may"]),
        ),
        (
            "Northmoor delinquency, three months",
            [m["value"] for m in n["delinquency"]["monthly"]]
            == [nd["march"], nd["april"], nd["may"]],
        ),
        ("Northmoor three-month average", _close(n["delinquency"]["average"], nd["average"])),
        (
            "Northmoor June breach level",
            _close(n["delinquency"]["next_month_breaches_beyond"], nd["june_breach_above"]),
        ),
        (
            "Northmoor excess spread",
            _close(spread.get("march", 0), checks["northmoor_excess_spread"]["march"]["pct"])
            and _close(spread.get("april", 0), checks["northmoor_excess_spread"]["april"]["pct"]),
        ),
        (
            "Bramble leverage as reported",
            _close(b["leverage"]["recomputed"], checks["bramble_covenants"]["leverage_reported"]),
        ),
        (
            "Bramble leverage with the guarantee",
            _close(
                b["leverage"]["with_guarantees"],
                checks["bramble_covenants"]["leverage_with_guarantee"],
            ),
        ),
        ("Kestrel loan-to-value", _close(k["ltv"]["reported"], kd["ltv_reported_pct"], 0.05)),
        (
            "Kestrel loan-to-value with markdown",
            _close(k["ltv"]["with_markdown"], kd["ltv_adjusted_pct"], 0.05),
        ),
        (
            "Kestrel stale valuation",
            [s["name"] for s in k["valuations"]["stale"]] == [s["name"] for s in kd["stale"]],
        ),
        (
            "Shared VIN",
            [s["vin"] for s in cycle["collateral"]["across"]]
            == [s["vin"] for s in checks["duplicate_collateral"]["across"]],
        ),
    ]


def _outcome(state: dict[str, Any], item: dict[str, Any]) -> str:
    """The decision if one was made, otherwise the suggestion. The scorecard says which."""
    return state["decisions"].get(item["id"]) or item["suggested"]["outcome"]


def _minutes(start: str | None, end: str | None) -> float | None:
    if not (start and end):
        return None
    return round(
        (datetime.fromisoformat(end) - datetime.fromisoformat(start)).total_seconds() / 60, 1
    )


def scorecard(cycle: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
    key = read_key()
    if key is None:
        return {"available": False}
    items = cycle["findings"]
    found, missed = [], []
    for issue, (prefix, expected) in ISSUES.items():
        matches = [i for i in items if i["id"].startswith(prefix)]
        if matches and all(_outcome(state, i) == expected for i in matches):
            found.append(issue)
        else:
            missed.append(
                f"{issue}: {key['issues'][issue]['summary']}"
                + ("" if matches else " (not raised)")
                + ("" if not matches else f" (ended as {_outcome(state, matches[0])})")
            )
    planted = {
        i["id"] for i in items for prefix, _ in ISSUES.values() if i["id"].startswith(prefix)
    }
    noise_raised = [
        n
        for n, prefix in NOISE.items()
        if any(i["id"].startswith(prefix) and _outcome(state, i) != "logged" for i in items)
    ]
    other_alerts = [
        i["title"]
        for i in items
        if i["id"] not in planted
        and _outcome(state, i) != "logged"
        and not any(i["id"].startswith(p) for p in NOISE.values())
    ]
    values = accuracy(cycle, key)
    decided = sum(1 for i in items if i["id"] in state["triage"])
    approved = [p["at"] for p in state["packs"].values()]
    usage = cycle["usage"]
    return {
        "available": True,
        "measures": [
            {
                "name": "Accuracy and completeness",
                "formula": "Extracted and reconciled values that match the answer key",
                "target": "Reported as measured",
                "value": f"{sum(ok for _, ok in values)} of {len(values)}",
                "details": [name for name, ok in values if not ok],
                "passed": None,
            },
            {
                "name": "Material issues missed",
                "formula": "Planted issues M1 to M9 not found with the right outcome",
                "target": "None",
                "value": str(len(missed)),
                "details": missed,
                "passed": not missed,
            },
            {
                "name": "False alerts",
                "formula": "Alerts raised that are not real issues",
                "target": "None of the three noise items",
                "value": str(len(noise_raised) + len(other_alerts)),
                "details": [f"{n}: {key['noise'][n]['summary']}" for n in noise_raised]
                + other_alerts,
                "passed": not noise_raised,
            },
            {
                "name": "Analyst effort per cycle",
                "formula": "Actions and minutes logged by the workbench in this session",
                "target": "Reported as measured",
                "value": f"{state['actions']} actions"
                + (
                    f", {_minutes(state['firstAt'], state['lastAt'])} minutes"
                    if state["firstAt"]
                    else ""
                ),
                "details": [
                    f"{decided} of {len(items)} findings decided by the analyst; the rest "
                    "logged by rule within tolerance"
                ],
                "passed": None,
            },
            {
                "name": "Turnaround time",
                "formula": "Cycle opened to every lender pack approved, this session",
                "target": "Reported as measured",
                "value": (
                    f"{_minutes(state['openedAt'], max(approved))} minutes"
                    if state["openedAt"] and len(approved) == len(cycle["facilities"])
                    else f"{len(approved)} of {len(cycle['facilities'])} packs approved"
                ),
                "details": [
                    "The demo clock is fixed at 24 June 2026; the last document arrived on 19 June"
                ],
                "passed": None,
            },
            {
                "name": "Processing cost",
                "formula": "Logged model usage for the cycle",
                "target": "Reported as measured",
                "value": f"US${usage['cost_usd']:.2f}",
                "details": [
                    f"{usage['calls']} calls to {usage['model']}",
                    f"{usage['input_tokens'] + usage['output_tokens']:,} tokens",
                    f"{usage['model_seconds']} s of model time",
                ],
                "passed": None,
            },
        ],
        "issues": [
            {
                "id": issue,
                "summary": key["issues"][issue]["summary"],
                "expected": expected,
                "found": issue in found,
            }
            for issue, (_, expected) in ISSUES.items()
        ],
        "caveat": "Measured on a synthetic cycle that the checks were built against. Results are "
        "not independent and do not indicate accuracy on live portfolios.",
    }
