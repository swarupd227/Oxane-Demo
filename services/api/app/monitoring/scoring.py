"""The cycle scorecard: the pitch brief's Use Case 2 measures (section 5b), by name.

Each measure shows what this cycle measured apart from what is assumed. Assumptions are stated
with their source and are to be replaced by baselines measured in discovery.

This is the only code that reads the cycle answer key. The pipeline never does.
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
    "M10": ("F-validate-northmoor-duplicate", "query"),
    "M11": ("F-larkspur-ccc", "confirmed"),
    "M12": ("F-larkspur-price", "confirmed"),
    # The RFP review: middle-market, subscription line, CLO daily feeds.
    "M13": ("F-ravenglass-leverage", "confirmed"),
    "M14": ("F-ravenglass-addbacks", "expert"),
    "M15": ("F-ravenglass-financials", "query"),
    "M16": ("F-ravenglass-waiver", "logged"),
    "M17": ("F-wharfedale-exclusion", "confirmed"),
    "M18": ("F-wharfedale-concentration", "confirmed"),
    "M19": ("F-wharfedale-register", "query"),
    "M20": ("F-feed-larkspur-prices-gap", "query"),
}
NOISE = {
    "N1": "F-layout-",
    "N2": "F-northmoor-collections",
    "N3": "F-certificate-rounding",
    "N4": "F-change-bramble",
    "N5": "F-larkspur-identifier",
    "N6": "F-ravenglass-rounding",
    "N7": "F-wharfedale-distribution",
    "N8": "F-feed-larkspur-positions-late",
}
# The key names obligor layouts by letter; the platform's library by its own ids.
LAYOUT_IDS = {"A": "LAY-0601", "B": "LAY-0602", "C": "LAY-0603", "D": "LAY-0604",
              "standard": "LAY-0611", "own": "LAY-0612"}


def review_accuracy(cycle: dict[str, Any], key: dict[str, Any]) -> list[tuple[str, bool | None]]:
    """The RFP review's values against the key. None means the value rests on a model step that
    has not been recorded, so it is not scored yet."""
    checks, tests = key["checks"], cycle["tests"]
    if "ravenglass" not in checks or "ravenglass" not in tests:
        return []
    r, rk = tests["ravenglass"], checks["ravenglass"]
    w, wk = tests["wharfedale"], checks["wharfedale"]
    daily, dk = cycle["daily_feeds"], checks["larkspur_daily"]
    rows = {o["id"]: o for o in r["obligors"]}
    bb = r["borrowing_base"]
    breach, addbacks, waiver = (rows[rk[k]["id"]] for k in ("breach", "addbacks", "waiver"))
    readings = {x["name"]: x["leverage"] for x in addbacks["readings"]}
    judgement = readings.get("Judgement items under the cap")
    extracted = r["extraction"]["status"] == "recorded"
    keyed = all(not c["by"] == "AI" for c in r["covenant_changes"])
    layouts = {**rk["layouts"], **rk["certificate_forms"]}
    wb, before = w["borrowing_base"], w["before_exclusion"]
    feeds = {f["feed"]: f for f in daily["feeds"]}
    return [
        ("Ravenglass obligors reported", r["received"] == rk["received"]),
        ("Ravenglass breaching obligor's leverage",
         breach["eligible"] is False and _close(breach["leverage"], rk["breach"]["leverage"])),
        ("Ravenglass add-backs: leverage as reported and fully capped",
         _close(addbacks["leverage"], rk["addbacks"]["readings"]["as_reported"])
         and _close(addbacks["readings"][-1]["leverage"],
                    rk["addbacks"]["readings"]["all_capped"])),
        ("Ravenglass add-backs: leverage with the integration costs capped",
         None if judgement is None and not extracted
         else judgement is not None
         and _close(judgement, rk["addbacks"]["readings"]["integration_capped"])),
        ("Ravenglass waived covenant level", _close(waiver["max_leverage"], rk["waiver"]["amended"])
         and _close(waiver["leverage"], rk["waiver"]["leverage"]) and waiver["eligible"]),
        ("Ravenglass excluded obligors",
         sorted(b["obligor"] for b in bb["excluded"]) == sorted(rk["excluded"])),
        ("Ravenglass borrowing base", _close(bb["borrowing_base"], rk["borrowing_base"])),
        ("Ravenglass availability", _close(bb["availability"], rk["availability"])),
        ("Ravenglass certificate difference", _close(bb["difference"],
                                                     rk["certificate_difference"])),
        ("Ravenglass largest obligor and sector",
         bb["largest"]["obligor"] == rk["largest_obligor"]["id"]
         and _close(bb["largest_sector"]["pct"], rk["largest_sector"]["pct"])),
        ("Ravenglass obligor layouts recognised",
         {LAYOUT_IDS[k]: v for k, v in layouts.items()} == r["layouts"]),
        ("Ravenglass obligor figures read with verified quotes",
         r["extraction"]["verified"] == rk["received"] if extracted else None),
        ("Ravenglass waiver read from the notice", None if keyed else any(
            c["by"] == "AI" and c["verified"] and c["obligor"] == rk["waiver"]["id"]
            for c in r["covenant_changes"])),
        ("Wharfedale excluded investor", [x["id"] for x in w["exclusions"]]
         == [wk["exclusion"]["id"]]),
        ("Wharfedale borrowing base before the exclusion",
         _close(before["borrowing_base"], wk["before_exclusion"]["borrowing_base"])),
        ("Wharfedale borrowing base after the exclusion",
         _close(wb["borrowing_base"], wk["after_exclusion"]["borrowing_base"])),
        ("Wharfedale mandatory prepayment",
         _close(wb["prepayment"], wk["after_exclusion"]["prepayment"])),
        ("Wharfedale concentration excess",
         wb["concentration_excess"] == wk["after_exclusion"]["concentration_excess"]),
        ("Wharfedale register break", [x["id"] for x in w["register_breaks"]]
         == [wk["register"]["stale"]["id"]] and _close(
             w["register_breaks"][0]["difference"], wk["register"]["stale"]["difference"])),
        ("Wharfedale notices reconcile", w["notices"]["capital_call"]["reconciles"]
         and w["notices"]["distribution"]["reconciles"]),
        ("Wharfedale investor classes", w["classes"] == wk["classes"]),
        ("Larkspur daily deliveries", daily["expected"] == dk["expected"]
         and daily["received"] == dk["received"]),
        ("Larkspur late and missing daily files",
         [{"feed": k, "as_of": d} for k, f in feeds.items() for d in f["late"]] == dk["late"]
         and [{"feed": k, "as_of": d} for k, f in feeds.items() for d in f["missing"]]
         == dk["missing"]),
    ]


def read_key() -> dict[str, Any] | None:
    path = settings.deal_kit_output / "cycle-key" / "key.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def _close(a: float, b: float, tolerance: float = 0.005) -> bool:
    return abs(float(a) - float(b)) <= tolerance


def accuracy(cycle: dict[str, Any], key: dict[str, Any]) -> list[tuple[str, bool]]:
    """Each value the cycle loaded, extracted or reconciled, against the key."""
    checks, recon, tests = key["checks"], cycle["reconciliation"], cycle["tests"]
    b, n, k = tests["bramble"], tests["northmoor"], tests["kestrel"]
    terms = {t["name"]: t for t in cycle["terms"]["terms"]}
    nd, kd = checks["northmoor_delinquency"], checks["kestrel"]
    spread = {m["month"].split()[0].lower(): m["value"] for m in n["excess_spread_months"]}
    lark, lark_key = tests["larkspur"], checks["larkspur"]
    feeds = {(f["facility"], f.get("month", "May")): f for f in cycle["validation"]["feeds"]}
    northmoor_feed = feeds[("northmoor", "May")]
    blocked = checks["validation"]["northmoor"]["blocking"][0]
    change = next(c for c in feeds[("bramble", "May")]["prior_period"]
                  if c["metric"] == "pool_balance")
    qc_expected = {(f, line["line"]): line["expected"] for f, q in checks["qc"].items()
                   for line in q["lines"]}
    qc_found = {(f, line["line"]): line["class"] for f, q in cycle["qc"].items()
                for line in q["lines"]}
    links = lark["changes"]["relinked"]
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
        (
            "Northmoor blocked row",
            northmoor_feed["held"]
            and northmoor_feed["resolution"]["collapsed"] == [blocked["loan_id"]],
        ),
        (
            "Northmoor rows loaded after resolution",
            northmoor_feed["rows_loaded"] == blocked["rows_in_file"] - 1,
        ),
        (
            "Bramble pool change on April",
            _close(change["change"], checks["prior_period"]["bramble"]["pool_balance_change_pct"]),
        ),
        (
            "Larkspur CCC share",
            _close(lark["borrowing_base"]["ccc_pct"], lark_key["may"]["ccc_pct"]),
        ),
        (
            "Larkspur CCC excess adjustment",
            _close(lark["borrowing_base"]["haircut"], lark_key["may"]["haircut"]),
        ),
        (
            "Larkspur borrowing base",
            _close(lark["borrowing_base"]["borrowing_base"], lark_key["may"]["borrowing_base"]),
        ),
        (
            "Larkspur identifier change linked",
            [(c["old_loanx"], c["new_loanx"]) for c in links]
            == [(lark_key["identifier_change"]["old_loanx"],
                 lark_key["identifier_change"]["new_loanx"])],
        ),
        (
            "Larkspur downgrade and price move",
            [d["issuer"] for d in lark["downgrades"]]
            == [d["issuer"] for d in lark_key["downgrades"]]
            and [m["issuer"] for m in lark["price_moves"]]
            == [m["issuer"] for m in lark_key["price_moves"]],
        ),
        ("QC variances classified", qc_found == qc_expected),
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


def _measure(name: str, measured: str, measured_details: list[str], *, target: str = "",
             passed: bool | None = None, assumed: str | None = None,
             assumed_details: list[str] | None = None) -> dict[str, Any]:
    return {
        "name": name,
        "measured": {"value": measured, "details": measured_details},
        "assumed": {"value": assumed, "details": assumed_details or []} if assumed else None,
        "target": target,
        "passed": passed,
    }


def scorecard(cycle: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
    key = read_key()
    if key is None:
        return {"available": False}
    items = cycle["findings"]
    found, missed = [], []
    issues = {k: v for k, v in ISSUES.items() if k in key["issues"]}
    noise_items = {k: v for k, v in NOISE.items() if k in key["noise"]}
    for issue, (prefix, expected) in issues.items():
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
        i["id"] for i in items for prefix, _ in issues.values() if i["id"].startswith(prefix)
    }
    noise_raised = [
        n
        for n, prefix in noise_items.items()
        if any(i["id"].startswith(prefix) and _outcome(state, i) != "logged" for i in items)
    ]
    other_alerts = [
        i["title"]
        for i in items
        if i["id"] not in planted
        and _outcome(state, i) != "logged"
        and not any(i["id"].startswith(p) for p in noise_items.values())
    ]
    scored = [*accuracy(cycle, key), *review_accuracy(cycle, key)]
    values = [(name, ok) for name, ok in scored if ok is not None]
    awaiting = [name for name, ok in scored if ok is None]
    pending = cycle.get("pending_recording", [])
    feeds = cycle["validation"]["feeds"]
    loaded = [f for f in feeds if not f["held"] or f["facility"] in state["blocks"]]
    decided = sum(1 for i in items if i["id"] in state["triage"])
    to_decide = sum(1 for i in items if i["rule_outcome"] is None)
    released = [p["at"] for p in state["packs"].values()]
    usage = cycle["usage"]
    assume = _assumptions()
    facilities = cycle["facilities"]

    # Effort: the stated baseline against review effort estimated from this cycle's queue.
    baseline = assume["baseline_hours_per_cycle"]
    per_facility = {
        f["id"]: assume["review_hours_per_facility"] + assume["review_hours_per_finding"] * sum(
            1 for i in items if f["id"] in i["facility"].split(",") and i["rule_outcome"] is None)
        for f in facilities
    }
    hours_now = sum(per_facility.values())
    hours_before = sum(baseline[f["id"]] for f in facilities)
    month = assume["analyst_hours_per_month"]
    mandates_before = month / (hours_before / len(facilities))
    mandates_after = month / (hours_now / len(facilities))

    # Traceability: every workbook input names its source; pack figures link to a page where
    # one exists and are otherwise calculated from those inputs.
    figures = [fig for pack in cycle["packs"] for fig in pack["figures"].values()]
    sourced = sum(1 for fig in figures if fig["source"])
    inputs, noted = _workbook_inputs(cycle, state)
    minutes = _minutes(state["firstAt"], state["lastAt"])
    turnaround = (
        f"{_minutes(state['openedAt'], max(released))} minutes"
        if state["openedAt"] and len(released) == len(facilities)
        else f"{len(released)} of {len(facilities)} packs released"
    )
    by_client = {c["client"]: c for c in usage.get("by_client", [])}
    measures = [
        _measure(
            "Accuracy and completeness of loaded updates and reconciliations",
            f"{sum(ok for _, ok in values)} of {len(values)} values",
            [f"{len(loaded)} of {len(feeds)} files loaded"
             + ("" if len(loaded) == len(feeds) else "; one load is held by a blocking check"),
             *[f"Wrong: {name}" for name, ok in values if not ok],
             *[f"Not scored until its model step is recorded: {name}" for name in awaiting]],
            target="Every value right, every file loaded", passed=all(ok for _, ok in values),
        ),
        _measure(
            "Material issues missed",
            str(len(missed)),
            missed or [f"All {len(issues)} planted issues found with the right outcome"],
            target="None", passed=not missed,
        ),
        _measure(
            "False alerts per cycle",
            str(len(noise_raised) + len(other_alerts)),
            [f"{n}: {key['noise'][n]['summary']}" for n in noise_raised] + other_alerts
            or [f"None of the {len(noise_items)} noise items raised"],
            target="None", passed=not noise_raised and not other_alerts,
        ),
        _measure(
            "Hours per cycle, by mandate",
            f"{minutes} minutes in this session" if minutes is not None else "Not started",
            [f"{state['actions']} actions; {decided} of {to_decide} open findings decided",
             f"{sum(1 for i in items if i['rule_outcome'])} findings logged by rule, no review"],
            assumed=f"{hours_now:.1f} h against a {hours_before:.1f} h baseline",
            assumed_details=[f"{f['name'].split()[0]}: {per_facility[f['id']]:.2f} h against "
                             f"{baseline[f['id']]:.1f} h" for f in facilities]
            + [f"Review effort: {assume['review_hours_per_facility']} h a facility plus "
               f"{assume['review_hours_per_finding']} h a finding to decide"],
        ),
        _measure(
            "Turnaround time per cycle",
            turnaround,
            ["Cycle opened to every pack released, in this session",
             "The demo clock is fixed at 24 June 2026; the last file arrived on 19 June"],
            assumed=f"{assume['baseline_turnaround_business_days']} business days today",
            assumed_details=["Baseline from the last file to release, to be measured"],
        ),
        _measure(
            "Processing cost per cycle",
            f"US${usage['cost_usd']:.2f}",
            [f"{usage['calls']} model calls to {usage['model']}, "
             f"{usage['input_tokens'] + usage['output_tokens']:,} tokens plus cache",
             *[f"{c['client'].title()}: {c['calls']} calls, US${c['cost_usd']:.2f}"
               + ("" if c["ai_permitted"] else " (AI not permitted)")
               for c in by_client.values()],
             f"{usage['model_seconds']} s of model time; replay costs nothing",
             *([f"{len(pending)} model steps pending recording; their code fallbacks ran"]
               if pending else [])],
        ),
        _measure(
            "Share of values linked to source evidence, with an audit trail of changes",
            f"{noted} of {inputs} input values linked to their source",
            ["Each workbook input notes its file and page or cell; every result is a formula "
             "over those inputs",
             f"{sourced} of {len(figures)} pack figures open their document page; the rest are "
             "calculated by code",
             f"{state['events']} audit events, hash chain "
             + ("intact" if state["chainIntact"] else "broken")],
            passed=state["chainIntact"] and noted == inputs,
        ),
        _measure(
            "Additional deals supportable per analyst",
            "Not measurable in a demo",
            ["Needs live cycles run alongside the existing process"],
            assumed=f"{mandates_after - mandates_before:+.0f} mandates "
            f"({mandates_before:.0f} to {mandates_after:.0f})",
            assumed_details=[f"{month} analyst hours a month, divided by hours per mandate "
                             "before and after", "Quality held: no issue missed, no false alert"],
        ),
    ]
    return {
        "available": True,
        "measures": measures,
        "issues": [
            {
                "id": issue,
                "summary": key["issues"][issue]["summary"],
                "expected": expected,
                "found": issue in found,
                "facility": key["issues"][issue]["facility"],
            }
            for issue, (_, expected) in issues.items()
        ],
        "noise": [
            {"id": n, "summary": key["noise"][n]["summary"], "raised": n in noise_raised}
            for n in noise_items
        ],
        "pending_recording": pending,
        "not_scored": awaiting,
        "assumptions": assume["source"],
        "caveat": "Measured on a synthetic cycle that the checks were built against. Results are "
        "not independent and do not indicate accuracy on live portfolios.",
    }


def _workbook_inputs(cycle: dict[str, Any], state: dict[str, Any]) -> tuple[int, int]:
    import io

    from openpyxl import load_workbook

    from app.monitoring import workbook

    total = noted = 0
    for facility in cycle["facilities"]:
        content, _ = workbook.build(cycle, state, facility["id"])
        book = load_workbook(io.BytesIO(content))
        cells = [c for c in book["Inputs"]["B"][1:] if c.value is not None]
        if "Positions" in book.sheetnames:
            cells += [c for col in ("C", "G") for c in book["Positions"][col][1:]]
        for name in ("Obligors", "Investors"):
            if name in book.sheetnames:
                cells += [c for row in book[name].iter_rows(min_row=2) for c in row
                          if c.value is not None and c.font is not None and c.font.color
                          is not None and str(c.font.color.rgb).endswith("1F4E9A")]
        total += len(cells)
        noted += sum(1 for c in cells if c.comment and c.comment.text.startswith("Source:"))
    return total, noted


def _assumptions() -> dict[str, Any]:
    from app.monitoring.cycle import record

    return record()["assumptions"]
