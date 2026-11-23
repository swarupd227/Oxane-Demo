"""Partial reuse across the desk's book: what each facility took from its bank's rule library,
which data layouts it reuses from each sender, and what was set for the facility alone.

Read from the facility record (`rule_libraries`, `reuse`, `mapping_library`) and the cycle's
book. Code only: no model is involved, and a bank's library is offered only to its own
facilities, so nothing is pooled across clients.
"""

from typing import Any

KIND_OF = {"Auto ABF": "auto", "CLO / BSL": "clo", "Middle-market": "middle_market"}


def _scripted_kind(meta: dict[str, Any], facility: dict[str, Any]) -> str:
    entry = meta.get("reuse", {}).get(facility["id"]) or {}
    return entry.get("kind") or KIND_OF.get(facility.get("asset_class", ""), "")


def facility_reuse(meta: dict[str, Any], facility: dict[str, Any], kind: str,
                   book_tests: list[dict[str, Any]] | None) -> dict[str, Any]:
    client = facility["client"]
    library = meta["rule_libraries"][client]
    scripted = meta.get("reuse", {}).get(facility["id"]) or {}
    tests = {t["test"]: t for t in book_tests or []}
    rules = []
    for rule in library["rules"]:
        if kind not in rule["kinds"]:
            continue
        test = tests.get(rule.get("test", ""))
        if test is not None:
            unit = test["unit"]
            limit = f"US${test['limit']:,.0f}" if unit == "US$" else f"{test['limit']:g}{unit}"
            parameter = f"{limit}, {test['clause']}"
        else:
            parameter = (scripted.get("parameters") or {}).get(rule["id"])
        rules.append({"id": rule["id"], "rule": rule["rule"], "from": "bank_library",
                      "parameter": parameter or "Facility's own clause",
                      "parameter_from": "facility"})
    validation = [{"set": name, "from": "bank_library"}
                  for name, kinds in library.get("validation_sets", {}).items() if kind in kinds]
    layouts = []
    for entry in meta["mapping_library"]:
        if facility["id"] not in entry["facilities"]:
            continue
        shared = [f for f in entry["facilities"] if f != facility["id"]]
        layouts.append({"id": entry["id"], "document": entry["document"],
                        "sender": entry["sender"], "version": entry["versions"][-1]["version"],
                        "from": "sender_layout" if shared else "facility",
                        "shared_with": shared})
    if not layouts:
        layouts.append({"id": None, "document": "Monthly summary figures",
                        "sender": library["summary_template"], "version": None,
                        "from": "lender_template", "shared_with": []})
    specific = [{"rule": text, "from": "facility"} for text in scripted.get("specific", [])]
    return {
        "facility": facility["id"], "name": facility["name"], "client": client,
        "kind": kind, "library": {k: library[k] for k in ("name", "version", "owner")},
        "rules": rules, "validation_sets": validation, "layouts": layouts,
        "specific": specific,
        "counts": {"library_rules": len(rules), "facility_rules": len(specific),
                   "reused_layouts": sum(1 for x in layouts if x["from"] != "facility"),
                   "own_layouts": sum(1 for x in layouts if x["from"] == "facility")},
    }


def reuse(meta: dict[str, Any], cycle: dict[str, Any]) -> dict[str, Any]:
    facilities = []
    for f in cycle["facilities"]:
        facilities.append(facility_reuse(meta, f, _scripted_kind(meta, f), None))
    for f in (cycle.get("book") or {}).get("facilities", []):
        facilities.append(facility_reuse(meta, f, f["kind"], f.get("tests")))
    libraries = []
    for client, library in meta["rule_libraries"].items():
        users = [x for x in facilities if x["client"] == client]
        libraries.append({
            "client": client, "name": library["name"], "version": library["version"],
            "owner": library["owner"], "updated": str(library["updated"]),
            "rules": [{**r, "facilities": [x["facility"] for x in users
                                           if any(y["id"] == r["id"] for y in x["rules"])]}
                      for r in library["rules"]],
            "facilities": len(users)})
    return {"libraries": libraries, "facilities": facilities}
