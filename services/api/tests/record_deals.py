"""Record the new deals' model calls by running their flows once with a key.

    python tests/record_deals.py consumer|sme|month-consumer|month-sme

Calls already recorded replay at no cost; only missing ones go to the model.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from app.config import settings  # noqa: E402

settings.demo_access_code = "test-access-code"
if "--stub" in sys.argv:
    settings.deals_stub_model = True

import deals_flow as flow  # noqa: E402


def consumer() -> dict:
    row = flow.new_client("Ashgrove Capital Partners LP", "Nadia Brooks", True)
    case = flow.onboard_ai("harbourline", row, "Harbourline Consumer Receivables LLC",
                           "Consumer instalment", 150_000_000,
                           ["Harbourline_Loan_and_Security_Agreement.pdf",
                            "Harbourline_First_Amendment.pdf",
                            "Harbourline_Loan_Tape_2026-09.csv",
                            "Ashgrove_Harbourline_BB_Model_v1.xlsx",
                            "Harbourline_Servicer_Report_September_2026.pdf"])
    return {"client": row, "case": case}


def sme() -> dict:
    row = flow.new_client("Marlow Bank plc", "Owen Price", True, 3)
    case = flow.onboard_ai("fenwick", row, "Fenwick SME Funding LLC", "SME loans", 80_000_000,
                           ["Fenwick_Receivables_Financing_Agreement.pdf",
                            "Fenwick_Portfolio_2026-09.xlsx"])
    return {"client": row, "case": case}


def summary(case: dict) -> dict:
    state = case["state"]
    return {
        "terms": {k: (t["status"], t.get("value"), t.get("problem"))
                  for k, t in state["terms"].items()},
        "rules": [(r["id"], r.get("describe"), r["verified"], r.get("problem"))
                  for r in state["rules"]["eligibility"] + state["rules"]["concentration"]],
        "not_codable": state["rules"].get("not_codable"),
        "mapping": state["mapping"]["columns"], "statuses": state["mapping"]["status_map"],
        "engine": {k: v for k, v in (state["validation"].get("engine") or {}).items()
                   if k.endswith("cents") or k in ("loans", "eligible_loans", "advance_rate_pct",
                                                   "delinquency_pct")},
        "held": state["validation"].get("held"),
        "exceptions": [(e["ref"], e["severity"], e["title"], e["status"])
                       for e in state["exceptions"]],
        "cost": case["cost"],
    }


def month_summary(sub: dict) -> dict:
    state = sub["state"]
    return {"status": sub["status"], "mapping_source": state["mapping"]["source"],
            "changed": state["mapping"].get("changed_columns"),
            "held": state["validation"].get("held"), "tests": state.get("tests"),
            "roll": (state.get("reconciliation") or {}).get("roll_forward"),
            "figures": state.get("report_figures"),
            "findings": [(f["ref"], f["title"], f["suggested"]["outcome"])
                         for f in state.get("findings", [])],
            "report": (state.get("report") or {}).get("text"), "cost": sub["cost"]}


def full(which: str) -> None:
    result = consumer() if which == "consumer" else sme()
    persona = f"client-{result['client']['id']}"
    case = flow.finish_onboarding(result["case"], persona)
    deal = "harbourline" if which == "consumer" else "fenwick"
    tape = "Harbourline_Loan_Tape_2026-10.csv" if deal == "harbourline" else \
        "Fenwick_Portfolio_2026-10.xlsx"
    report = "Harbourline_Servicer_Report_October_2026.pdf" if deal == "harbourline" else \
        "Fenwick_Monthly_Report_October_2026.pdf"
    sub = flow.first_month(case["facility_id"], deal, tape, report)
    sub = flow.triage_all(sub)
    if sub["state"]["validation"].get("held"):
        sub = flow.sub_step(sub["id"], "process", code=True)
        sub = flow.triage_all(sub)
    sub = flow.sub_step(sub["id"], "report/draft", code=True)
    for persona_id in ("priya", "marcus", "elena")[: result["client"]["approval_levels"]]:
        sub = flow.sub_step(sub["id"], "approve", persona=persona_id)
    print(json.dumps(month_summary(sub), indent=1, default=str)[:6000])


if __name__ == "__main__":
    which = sys.argv[1]
    if which.endswith("-full"):
        full(which.removesuffix("-full"))
    else:
        result = {"consumer": consumer, "sme": sme}[which]()
        print(json.dumps(summary(result["case"]), indent=1, default=str))
