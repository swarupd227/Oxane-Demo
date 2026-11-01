"""Build the exception queue from what the pipeline found.

Items appear only when a check raised them. Nothing here knows how many there
should be, which is what lets the scorecard measure found and false items.
"""

from typing import Any

from app.pipeline.assemble import long_date
from app.pipeline.checks import DateReview


def build_queue(terms: list[dict[str, Any]], problems: list[dict[str, Any]],
                missing: list[dict[str, str]], run: dict[str, Any], matched: dict[str, Any],
                variants: list[list[str]], blanks: list[tuple[str, int]], dates: DateReview,
                requirements: list[dict[str, Any]], formula: dict[str, Any],
                ) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    by_name = {term["name"]: term for term in terms}

    rate = by_name["Advance rate"]
    if "amended_value" in rate:
        items.append({
            "id": "X1", "type": "conflicting", "label": "Amended term",
            "title": "Advance rate changed by Amendment No. 1", "owner": "Onboarding analyst",
            "where": rate["clause"],
            "evidence": [f"Credit Agreement 2.3 states {rate['original_value']}.",
                         f"Amendment No. 1 replaces it with {rate['amended_value']} from "
                         f"{long_date(rate['effective_from'])}."],
            "suggestion": f"Confirm {rate['amended_value']} for the April period.",
            "actions": ["accept"], "tier1": True, "source": rate["source"],
        })

    for item in missing:
        items.append({
            "id": "X2", "type": "missing", "label": "Missing document",
            "title": f"{item['name']} is not in the pack", "owner": "Borrower's counsel",
            "where": f"Credit Agreement, {item['name']}",
            "evidence": [item["reason"] + ".", "Rule E7 cannot run, so the borrowing base is "
                         "provisional."],
            "suggestion": f"Request {item['name']} from the borrower's counsel.",
            "actions": ["query"], "blocking": True,
        })

    limit = by_name["Facility limit"]
    if limit["confidence"] == "low":
        items.append({
            "id": "X3", "type": "ambiguous", "label": "Low confidence",
            "title": "Facility limit read from a low-quality scan", "owner": "Onboarding analyst",
            "where": limit["clause"],
            "evidence": ["Annex A is an image-only page.", f"The value reads as {limit['value']}."],
            "suggestion": "Confirm against the signed page.", "actions": ["accept"],
            "tier1": True, "source": limit["source"],
        })

    for line in run["pool_bridge"]["lines"]:
        if line["rule_id"] == "E1":
            items.append({
                "id": "X4", "type": "conflicting", "label": "Certificate vs tape",
                "title": f"{line['loans']} loans over 30 days past due counted as eligible",
                "owner": "Borrower", "where": "Borrowing base certificate and loan tape",
                "evidence": ["The certificate tests 60 days past due. Schedule 1 says 30.",
                             f"{line['loans']} loans are affected.",
                             f"They total US${line['amount']:,.2f}."],
                "suggestion": "Query the borrower and ask for a corrected certificate.",
                "actions": ["query"], "blocking": True, "drill": "E1",
            })
        elif line["rule_id"] == "E12":
            vins = {row["vin"] for row in line["rows"]}
            items.append({
                "id": "X5", "type": "conflicting", "label": "Data integrity",
                "title": f"{line['loans']} loans share {len(vins)} VINs", "owner": "Credit",
                "where": "Loan tape, VIN column",
                "evidence": ["Each VIN appears on more than one loan.",
                             f"Together they total US${line['amount']:,.2f}.",
                             "This may be double pledging. The check covers this pool only."],
                "suggestion": "Escalate to credit before these loans are accepted.",
                "actions": ["escalate"], "blocking": True, "drill": "E12",
            })

    dealer = next(item for item in matched["concentrations"] if item["id"] == "C2")
    for names in variants:
        items.append({
            "id": "X6", "type": "ambiguous", "label": "Possible match",
            "title": " and ".join(f'"{name}"' for name in names) + " may be one dealer",
            "owner": "Onboarding analyst", "where": "Loan tape, dealer column",
            "evidence": [f"Together they are {dealer['share_pct']}% of the eligible pool.",
                         f"The limit is {dealer['limit_pct']}%.",
                         "Schedule 2 treats variations of one name as one dealer."],
            "suggestion": "Accept the match. The borrowing base will be recalculated.",
            "actions": ["accept"], "recalculates": dealer["excess"] > 0,
        })

    for label, page in blanks:
        items.append({
            "id": "X7", "type": "missing", "label": "Blank field",
            "title": f"Servicer report has no figure for {label.replace(' (US$)', '').lower()}",
            "owner": "Servicer", "where": f"Servicer report, page {page}",
            "evidence": [f"{label} has no value."],
            "suggestion": "Request the figure from the servicer.", "actions": ["query"],
        })

    derived = [item for item in requirements if item["status"] == "derived"]
    for number, requirement in enumerate(derived):
        expression = requirement["detail"].removeprefix("Formula: ").rstrip(".")
        evidence = [f"Formula: {expression}."]
        if "APR" in requirement["requirement"]:
            evidence.insert(0, f"Calculated from the tape: {run['weighted_average_apr']:.2f}%.")
        items.append({
            "id": "X8" if number == 0 else f"X8.{number + 1}", "type": "ambiguous",
            "label": "Derived field",
            "title": f"{requirement['requirement']} is not a tape column",
            "owner": "Onboarding analyst", "where": "Lender requirements sheet",
            "evidence": evidence, "suggestion": "Accept the derived field.",
            "actions": ["accept"],
        })

    if dates.mixed_rows:
        items.append({
            "id": "X9", "type": "ambiguous", "label": "Format conflict",
            "title": f"Origination dates mix formats in {dates.mixed_rows} rows",
            "owner": "Onboarding analyst", "where": "Loan tape, origination date column",
            "evidence": ["Each row was resolved against its first payment date.",
                         f"{len(dates.uncertain_rows)} rows remain unresolved."],
            "suggestion": "Accept the resolution.", "actions": ["accept"],
        })

    if formula["parts"]:
        clauses = sorted({"1.1" if "Definition" in part["clause"] else part["clause"]
                          for part in formula["parts"]})
        expression = formula["formula"].removeprefix(f"{formula['term']} = ")
        # The model may remark on what it was shown, which means nothing to an analyst.
        conditions = [line for line in formula["conditions"] if "provided" not in line.lower()]
        items.append({
            "id": "X10", "type": "ambiguous", "label": "Cross-reference",
            "title": f"{formula['term']} depends on more than one clause",
            "owner": "Onboarding analyst",
            "where": "Credit Agreement " + ", ".join(clauses),
            "evidence": [f"{formula['term']} = {expression}.", *conditions[:4]],
            "suggestion": "Confirm the full formula.", "actions": ["accept"], "tier1": True,
            "source": next((p["source"] for p in formula["parts"] if p["source"]), None),
        })

    for number, problem in enumerate(problems, start=1):
        items.append({
            "id": f"Q{number}", "type": "ambiguous", "label": "Unverified",
            "title": f"{problem['field']} could not be confirmed", "owner": "Onboarding analyst",
            "where": problem["clause"], "evidence": [problem["why"]],
            "suggestion": "Check the value against the source.", "actions": ["accept"],
        })
    return items
