"""The weekly status-call brief for each client's named contact.

For a client that permits AI, the model drafts the words from the cycle's findings and every
figure is a {{placeholder}} that code fills, as in the lender pack. For a client that does not,
code writes the brief from a fixed template: the existing process, with no model call.
"""

import re
from datetime import date
from typing import Any

from app.monitoring import steps

HEADINGS = ["Missing data", "Open questions", "Exclusions", "Identifier changes",
            "Missing financials", "Waiting on an expert"]


def _fig(value: str, means: str, source: Any = None) -> dict[str, Any]:
    return {"value": value, "means": means, "source": source}


def _day(iso: str) -> str:
    """A date as the brief writes it in prose: 22 Jun 2026, never 2026-06-22."""
    if not iso:
        return ""
    day = date.fromisoformat(iso)
    return f"{day.day} {day:%b %Y}"


def missing_financials(missing: list[str]) -> list[str]:
    """Calderwood's "Missing financials", by facility, written by code. Bramble's Q1 pack
    arrived; any review facility obligor whose financials did not is named."""
    return ["Bramble: Q1 statements and compliance certificate arrived before the due date"] + [
        f"Ravenglass: {name}'s Q1 financials have not arrived and have been chased; its loan is "
        "out of the borrowing base until they do" for name in missing]


def _doc(label: str) -> str:
    """"Servicer report, May" as prose: "May servicer report"."""
    kind, _, when = label.partition(", ")
    return f"{when} {kind.lower()}" if when else kind.lower()


def client_missing_data(cycle: dict[str, Any]) -> list[str]:
    """Calderwood's missing data written to the client, from the same facts as the brief."""
    late = [s for s in cycle["submissions"] if s["status"] == "late"]
    reused = [s for s in cycle["submissions"] if s.get("reused")]
    held = [v for v in cycle["validation"]["feeds"] if v["held"]]
    return [f"{s['facility'].title()}'s {_doc(s['label'])}, due {_day(s['due'])}, has not "
            "arrived; we have chased it and escalated it" for s in late] + [
        f"{s['facility'].title()}'s {_doc(s['label'])} was not resent, so with your consent we "
        f"used the {_doc(s['reused']['from'])}" for s in reused] + [
        f"{v['facility'].title()}'s May tape repeats one loan's row ({{{{duplicate_loan}}}}); we "
        "are holding the load until the servicer confirms it" for v in held]


def calderwood_facts(cycle: dict[str, Any], items: list[dict[str, Any]]) -> tuple[
        dict[str, Any], dict[str, dict[str, Any]]]:
    t, recon = cycle["tests"], cycle["reconciliation"]
    b = t["bramble"]
    late = [s for s in cycle["submissions"] if s["status"] == "late"]
    reused = [s for s in cycle["submissions"] if s.get("reused")]
    offs, roll = recon["charge_offs"], recon["roll_forward"]
    held = [v for v in cycle["validation"]["feeds"] if v["held"]]
    system = b["borrowing_base"]["system"]
    figures = {
        "missing_loans": _fig(str(len(roll["missing"])), "loans missing from Bramble's May tape"),
        "gap": _fig(f"US${roll['gap']:,.2f}", "Bramble roll-forward gap"),
        "charge_off_loans": _fig(str(len(offs["loans"])),
                                 "Bramble loans charged off in the report but live on the tape"),
        "charge_off_difference": _fig(f"US${offs['difference']:,.2f}",
                                      "charge-offs in the servicer report above the tape",
                                      offs["source"]),
        "ineligible": _fig(f"US${system['ineligible']:,.2f}",
                           "Bramble receivables excluded as not eligible"),
        "ineligible_loans": _fig(str(system["ineligible_loans"]),
                                 "number of Bramble receivables excluded as not eligible"),
        "concentration_excess": _fig(f"US${system['excess']:,.2f}",
                                     "Bramble dealer concentration excess deducted"),
        "northmoor_due": _fig(_day(late[0]["due"]) if late else "",
                              "date Northmoor's report was due"),
        "duplicate_loan": _fig(held[0]["resolution"]["collapsed"][0] if held and
                               held[0]["resolution"]["collapsed"] else "",
                               "Northmoor loan whose row the May tape repeats"),
        "stale_days": _fig(str(t["kestrel"]["valuations"]["stale"][0]["age_days"]),
                           "age in days of Kestrel's oldest valuation"),
        "ltv_with_markdown": _fig(f"{t['kestrel']['ltv']['with_markdown']:.1f}%",
                                  "Kestrel loan-to-value counting the markdown"),
        "leverage_with_guarantee": _fig(f"{b['leverage']['with_guarantees']:.2f}x",
                                        "Bramble leverage if the guarantee counts"),
        "delinquency_average": _fig(f"{t['northmoor']['delinquency']['average']:.2f}%",
                                    "Northmoor three-month 60+ day average"),
    }
    mine = [i for i in items if not i["facility"].startswith("larkspur")]
    facts = {
        "missing_data": [f"{s['label']} for {s['facility'].title()}: late, chased and escalated"
                         for s in late]
        + [f"{s['label']} for {s['facility'].title()} not resent: {s['reused']['from']} reused "
           "with the client's consent" for s in reused]
        + [f"{v['facility'].title()} May tape repeats one loan's row ({{{{duplicate_loan}}}}); "
           "the load is held until the servicer confirms" for v in held],
        "open_questions": [
            f"{i['facility'].split(',')[0].title()}: {i['topic']}" for i in mine
            if i["suggested"]["outcome"] == "query"
        ],
        "exclusions": [
            "Bramble: {{ineligible_loans}} receivables worth {{ineligible}} excluded as not "
            "eligible, and {{concentration_excess}} of dealer concentration excess deducted",
            "Bramble: {{missing_loans}} loans missing from the tape are out of the pool until the "
            "servicer explains them",
        ],
        "identifier_changes": ["None on this client's facilities this month"],
        "missing_financials": ["None outstanding: Bramble's Q1 statements and compliance "
                               "certificate arrived before the due date"],
        "waiting_on_an_expert": [
            f"{i['facility'].title()}: {i['topic']}" for i in mine
            if i["suggested"]["outcome"] == "expert"
        ],
        "placeholders": {f"{{{{{k}}}}}": v["means"] for k, v in figures.items()},
    }
    return facts, figures


def draft_calderwood(gateway: Any, client: dict[str, Any], cycle: dict[str, Any],
                     items: list[dict[str, Any]]) -> dict[str, Any]:
    facts, figures = calderwood_facts(cycle, items)
    draft = steps.draft_status_brief(gateway, client["name"], client["contact"]["name"],
                                     HEADINGS, facts)
    texts = [draft.opening, *(p for s in draft.sections for p in s.points)]
    pattern = re.compile(r"\{\{(\w+)\}\}")
    unknown = sorted({m for t in texts for m in pattern.findall(t) if m not in figures})
    numbers = sorted({m for t in texts for m in re.findall(r"(?<![\w{])\d[\d,.]*%?",
                                                            pattern.sub("", t))})
    return {
        "client": client["id"],
        "ai": True,
        "opening": draft.opening,
        "sections": [{"heading": s.heading, "points": s.points} for s in draft.sections],
        "figures": figures,
        "unknown_placeholders": unknown,
        "numbers_in_text": numbers,
    }


def template_brief(client: dict[str, Any], cycle: dict[str, Any]) -> dict[str, Any]:
    """Thornbury's brief, written by code from a fixed template. No model is called."""
    lark = cycle["tests"]["larkspur"]
    bb = lark["borrowing_base"]
    feeds = [v for v in cycle["validation"]["feeds"] if v["facility"] == "larkspur"]
    warnings = [r for v in feeds for r in v["rules"] if r["status"] == "warning"]
    excess = bb["excess"][0] if bb["excess"] else None
    figures = {
        "ccc_pct": _fig(f"{bb['ccc_pct']:.2f}%", "CCC share of par", lark["ccc_source"]),
        "ccc_limit": _fig(f"{bb['ccc_limit_pct']:.1f}%", "CCC limit"),
        "ccc_excess": _fig(f"US${bb['ccc_excess']:,.2f}", "CCC excess"),
        "haircut": _fig(f"US${bb['haircut']:,.2f}", "CCC excess adjustment"),
        "borrowing_base": _fig(f"US${bb['borrowing_base']:,.2f}", "borrowing base"),
    }
    sections = [
        {"heading": "Missing data", "points": ["None. The collateral report arrived by SFTP and "
                                               "the bid prices by API, both on time."]},
        {"heading": "Open questions", "points": [
            (f"No S&P rating on {w['failed']} position{'s' if w['failed'] != 1 else ''} "
             f"({', '.join(e['key'] for e in w['examples'])}), so the lower-of rule uses "
             "Moody's alone. Logged; no query needed."
             if w["field"] == "sp"
             else f"Warning not met, {w['text'].lower()}: {w['failed']} row"
             f"{'s' if w['failed'] != 1 else ''}. Logged.")
            for w in warnings] or ["None."]},
        {"heading": "Exclusions", "points": [
            "CCC share is {{ccc_pct}} against a {{ccc_limit}} limit. {{ccc_excess}} of CCC "
            "excess is carried at market value"
            + (f", taken from {excess['issuer']} at a bid of {excess['bid']:.2f}" if excess
               else "")
            + ", so the CCC excess adjustment of {{haircut}} comes off the borrowing base."]},
        {"heading": "Identifier changes", "points": [
            f"{c['issuer']}: LoanX {c['old_loanx']} is now {c['new_loanx']} and CUSIP "
            f"{c['old_cusip']} is now {c['new_cusip']}. Matched on issuer, facility, maturity "
            "and spread, with no trade, so its history carries over. It is not a sale and a "
            "new purchase." for c in lark["changes"]["relinked"]] or ["None."]},
        {"heading": "Missing financials", "points": ["None outstanding."]},
        {"heading": "Early warnings", "points": [
            f"{d['issuer']} downgraded from {'/'.join(d['before'])} to {'/'.join(d['after'])}."
            for d in lark["downgrades"]] + [
            f"{m['issuer']} bid fell {abs(m['change']):.2f} points to {m['after']:.2f}."
            for m in lark["price_moves"]]},
    ]
    return {
        "client": client["id"],
        "ai": False,
        "opening": f"Larkspur's May cycle ran on code checks only, as {client['name']} requires. "
        "Borrowing base {{borrowing_base}}.",
        "sections": sections,
        "figures": figures,
        "unknown_placeholders": [],
        "numbers_in_text": [],
    }
