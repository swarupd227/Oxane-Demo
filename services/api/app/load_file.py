"""The load file: the approved case, in the layout a platform import would read."""

from decimal import Decimal
from typing import Any

from app import engine_service
from app.deal import load_deal
from app.session import ACTOR_NAMES, ANALYST


def _lender_fields(run: dict[str, Any], result: dict[str, Any]) -> list[dict[str, Any]]:
    """Each field the lender asked for, with its value where the run calculated one."""
    system = result["system"]
    values: dict[str, Any] = {
        "Weighted average APR": result["weighted_average_apr"],
        "Pool balance": system["gross_pool"],
        "Eligible pool balance": system["eligible_pool"],
        "Borrowing base": system["borrowing_base"],
        "Availability": system["availability"],
    }
    return [{"name": item["name"], "status": item["status"], "source": item["detail"],
             "value": values.get(item["name"])}
            for item in run["mapping"]["requirements"]]


def build_load_file(run: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
    edit = state["ruleEdit"]
    override = None
    if edit and edit["status"] == "approved":
        override = (edit["rule_id"], Decimal(str(edit["to"])))

    result = engine_service.validation_run(state["dealerMatched"], override)
    edits = state["termEdits"]
    outcomes = state["exceptions"]
    return {
        "format": "onboarding-load-file/1",
        "note": "Sandbox output, not a Panorama import format. All data is synthetic.",
        "case": load_deal().case.number,
        "approval": {
            "approved_at": state["approvedAt"],
            "prepared_by": state["preparedBy"],
            "approved_by": state["approvedByName"] or ACTOR_NAMES[ANALYST],
            "audit_chain_head": state["chainHead"],
            "run_digest": result["digest"],
            "provisional": result["provisional"],
            "rules_not_evaluated": result["not_evaluated"],
        },
        "open_items": state["openItems"],
        "ontology_version": run.get("ontology_version"),
        "facility_terms": [
            {"name": term["name"], "tier": term["tier"], "clause": term["clause"],
             "value": edits.get(term["name"], term["value"]),
             "edited": term["name"] in edits,
             "effective_from": term.get("effective_from"),
             "concept": term["grounding"]["concept"]["id"] if "grounding" in term else None}
            for term in run["terms"]
        ],
        "rules": {
            "version": 2 if override else 1,
            "items": engine_service.rule_views(override),
        },
        "tape_mapping": [{"column": row["column"], "field": row["field"],
                          "concept": row.get("concept")}
                         for row in run["mapping"]["rows"]],
        "lender_fields": _lender_fields(run, result),
        "exceptions": [
            {"id": item["id"], "type": item["type"], "title": item["title"],
             "owner": item["owner"], "outcome": outcomes.get(item["id"])}
            for item in [*run["exceptions"], *state["heldItems"]]
        ],
        "borrowing_base": result["system"],
        "concentrations": result["concentrations"],
        "covenants": result["covenants"],
        "loans": engine_service.loan_records(state["dealerMatched"], override),
    }
