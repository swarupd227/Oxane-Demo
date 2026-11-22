"""The pitch brief's Use Case 1 measures (section 5b), by name, measured apart from assumed.

This and app.scoring are the only code that reads an answer key. Assumptions are stated in
casework.yaml with their source, to be replaced by baselines measured in discovery.
"""

import json
from typing import Any

from app.casework.definitions import key_of
from app.casework.run import record
from app.casework.view import view as casework_view
from app.config import settings


def read_key() -> dict[str, Any] | None:
    path = settings.deal_kit_output / "casework-key" / "key.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def checks(casework: dict[str, Any], key: dict[str, Any]) -> dict[str, list[tuple[str, bool]]]:
    """Each casework value against the expert-verified record, by area."""
    nodes = {n["key"]: n for n in casework["definitions"]["nodes"]}
    edges = {(n["key"], r["key"]) for n in nodes.values() for r in n["refers_to"]}
    definitions = []
    for term in key["definitions"]["terms"]:
        node = nodes.get(key_of(term["term"]))
        definitions.append((f"{term['term']}: found on page {term['page']}",
                            bool(node and node["source"]
                                 and node["source"]["page"] == term["page"])))
        if term.get("amended_by"):
            definitions.append((f"{term['term']}: amendment found",
                                bool(node and node["amendment_source"])))
    for source, target in key["definitions"]["edges"]:
        definitions.append((f"{source} relies on {target}",
                            (key_of(source), key_of(target)) in edges))
    outside = {key_of(name.split(" (")[0].split(" - ")[0])
               for name in casework["definitions"]["not_in_pack"]}
    for name in key["definitions"]["not_in_pack"]:
        definitions.append((f"{name} flagged as not in the pack", key_of(name) in outside))

    rows = {r["topic"]: r for r in casework["client_model"]["rows"]}
    model = []
    for topic, cell in key["client_model"]["cells"].items():
        model.append((f"Client model {topic} read from {cell}",
                      rows.get(topic, {}).get("cell") == cell))
    expected = key["client_model"]["differences"]
    for topic, item in expected.items():
        row = rows.get(topic, {})
        model.append((f"Difference found: {topic}", row.get("status") in ("differs", "silent")))
        model.append((f"Impact on borrowing base: {topic}",
                      abs(row.get("borrowing_base_change", 99e9) - item["borrowing_base_change"])
                      <= 1.0))
    model += [(f"No false difference: {topic}", False) for topic, row in rows.items()
              if row["status"] in ("differs", "silent") and topic not in expected]

    found = {x["line"]: x["class"] for x in casework["qc"]["lines"]}
    qc = [(f"QC line classified: {x['line']}", found.get(x["line"]) == x["expected"])
          for x in key["qc"]["lines"]]

    deals = {d["id"]: d for d in casework["backbook"]}
    backbook = []
    for deal in key["backbook"]:
        mine = deals.get(deal["id"], {"differences": [], "rows": 0})
        backbook.append((f"{deal['id']}: {deal['rows']} rows read", mine["rows"] == deal["rows"]))
        for item in deal["exceptions"]:
            match = next((d for d in mine["differences"] if d["column"] == item["column"]), None)
            suggestion = (match or {}).get("suggestion") or {}
            if item["kind"] == "renamed_column":
                ok = suggestion.get("field") == item["field"]
            elif item["kind"] == "new_column":
                ok = match is not None and suggestion.get("field") is None
            elif item["kind"] == "blank_values":
                ok = match is not None and match["rows"] == item["rows"] and str(
                    suggestion.get("treat_blank_as")) == str(item["treat_as"])
            else:
                ok = {a: b for a, b in suggestion.get("code_map", [])} == item["map"]
            backbook.append((f"{deal['id']}: {item['kind']} {item['column']}",
                             bool(ok and match and match["check"]["ok"])))
        planted = {item["column"] for item in deal["exceptions"]}
        backbook += [(f"{deal['id']}: no false exception on {d['column']}", False)
                     for d in mine["differences"] if d["column"] not in planted]
    return {"definitions": definitions, "client_model": model, "qc": qc, "backbook": backbook}


def _measure(name: str, measured: str, details: list[str], *, assumed: str | None = None,
             assumed_details: list[str] | None = None, passed: bool | None = None
             ) -> dict[str, Any]:
    return {"name": name, "measured": {"value": measured, "details": details},
            "assumed": {"value": assumed, "details": assumed_details or []} if assumed else None,
            "passed": passed}


def brief_measures(run: dict[str, Any], state: dict[str, Any], fields: list[dict[str, Any]],
                   minutes: int | None) -> dict[str, Any] | None:
    key = read_key()
    try:
        cw = casework_view(state)
    except FileNotFoundError:
        return None
    if key is None:
        return None
    from app.casework.view import current

    raw = current()
    areas = checks(raw, key)
    assume = record()["assumptions"]
    track = cw["tracker"]

    after = [(f["name"], f["after_review"]) for f in fields]
    every = [("Term: " + n, ok) for n, ok in after] + [x for a in areas.values() for x in a]
    right = sum(ok for _, ok in every)
    wrong = [name for name, ok in every if not ok]
    tier1_missed = [f["name"] for f in fields if f["tier"] == 1 and not f["before_review"]]
    material = [n for n, ok in areas["client_model"] + areas["qc"] if not ok
                and ("Difference" in n or "Impact" in n or "QC" in n)]

    queue = len(run["exceptions"])
    queries = len(track["queries"])
    processed = len(run["terms"]) + len(run["rules"]) + len(raw["client_model"]["rows"])
    backbook_columns = sum(d["columns"] for d in cw["backbook"])
    backbook_exceptions = sum(d["exceptions"] for d in cw["backbook"])

    platform = assume["platform_hours"]
    new_hours = (platform["new_facility_base"] + platform["per_exception"] * queue
                 + platform["per_query"] * queries)
    deal_hours = [platform["backbook_deal_base"] + platform["per_exception"] * d["exceptions"]
                  for d in cw["backbook"]]
    baseline = assume["baseline_hours"]
    new_type, back_type = list(baseline)
    rate = assume["analyst_cost_per_hour_usd"]
    model_cost = (run.get("usage") or {}).get("cost_usd", 0) + raw["usage"]["cost_usd"]

    sourced_terms = [t for t in run["terms"] if t["status"] != "missing"]
    linked = [
        ("Terms with their source page or sheet",
         sum(1 for t in sourced_terms if t.get("source") or (t["document"] and t["clause"])),
         len(sourced_terms)),
        ("Definitions quoted on their page", raw["definitions"]["checks"]["quotes_found"],
         raw["definitions"]["checks"]["quotes"]),
        ("Thresholds found in their verified source",
         sum(1 for r in cw["config"]["thresholds"] if r["in_source"]),
         len(cw["config"]["thresholds"])),
        ("Client-model readings tied to their cell",
         sum(1 for r in raw["client_model"]["rows"] if r["cell"]),
         len(raw["client_model"]["rows"]) + len(raw["client_model"]["rejected"])),
        ("QC lines tied to their workbook cell", len(raw["qc"]["lines"]), len(raw["qc"]["lines"])),
    ]
    month = assume["analyst_hours_per_month"]
    before_per_month = month / baseline[new_type]
    after_per_month = month / new_hours
    measures = [
        _measure("Field-level accuracy against expert-verified records",
                 f"{right} of {len(every)} values",
                 [f"Terms after review: {sum(ok for _, ok in after)} of {len(after)}"]
                 + [f"{area.replace('_', ' ').capitalize()}: {sum(ok for _, ok in items)} of "
                    f"{len(items)}" for area, items in areas.items()]
                 + [f"Wrong: {name}" for name in wrong[:6]],
                 passed=not wrong),
        _measure("Material errors and omissions", str(len(tier1_missed) + len(material)),
                 [f"Tier 1 value wrong or missing before review: {n}" for n in tier1_missed]
                 + [f"Missed: {n}" for n in material]
                 or ["None"],
                 passed=not material),
        _measure("Exception rate",
                 f"{queue + queries} of {processed} items ({(queue + queries) / processed:.1%})",
                 [f"{queue} exception queue items and {queries} client queries, over "
                  f"{len(run['terms'])} terms, {len(run['rules'])} rules and "
                  f"{len(raw['client_model']['rows'])} client-model readings",
                  f"Backbook: {backbook_exceptions} exceptions over {backbook_columns} columns "
                  f"in {len(cw['backbook'])} deals "
                  f"({backbook_exceptions / backbook_columns:.1%})"]),
        _measure("Hours per onboarding, by deal type",
                 f"{minutes} min in this session" if minutes is not None else "In progress",
                 ["Pack upload to approved load file, this session"],
                 assumed=f"{new_type}: {new_hours:.1f} h against {baseline[new_type]} h",
                 assumed_details=[f"{back_type}: {sum(deal_hours) / len(deal_hours):.1f} h "
                                  f"against {baseline[back_type]} h a deal",
                                  f"Estimate: {platform['new_facility_base']} h a new facility "
                                  f"plus {platform['per_exception']} h an exception and "
                                  f"{platform['per_query']} h a query"]),
        _measure("Elapsed time, split from client waiting",
                 f"{track['elapsed_hours']:.1f} business hours: {track['analyst_hours']:.1f} "
                 f"analyst, {track['client_waiting_hours']:.1f} waiting on the client",
                 [f"Pack received {track['pack_received'][:10]}, as of "
                  f"{track['clock'][:16].replace('T', ' ')}",
                  f"{track['open_with_client']} queries with the client, {track['drafted']} "
                  "drafted and not sent",
                  "Client waiting: business hours with a query open with the client"]),
        _measure("Cost per onboarding", f"US${model_cost:.2f} of model use",
                 [f"Pack pipeline US${(run.get('usage') or {}).get('cost_usd', 0):.2f}, "
                  f"casework US${raw['usage']['cost_usd']:.2f}"],
                 assumed=f"US${new_hours * rate:,.0f} analyst time against "
                         f"US${baseline[new_type] * rate:,.0f}",
                 assumed_details=[f"US${rate} an analyst hour"]),
        _measure("Share of values linked to source",
                 f"{sum(a for _, a, _ in linked)} of {sum(b for _, _, b in linked)} values",
                 [f"{label}: {a} of {b}" for label, a, b in linked]
                 + [f"{len(state['audit'])} audit events, hash chain "
                    + ("intact" if state.get("chainIntact", True) else "broken")],
                 passed=all(a == b for _, a, b in linked)),
        _measure("Capacity released", "Not measured",
                 ["Requires a parallel run against the current process"],
                 assumed=f"{before_per_month:.1f} to {after_per_month:.1f} new facilities a "
                         "month per analyst",
                 assumed_details=[f"{month} analyst hours a month, divided by hours per "
                                  "onboarding before and after"]),
    ]
    return {"measures": measures, "assumptions": assume["source"]}
