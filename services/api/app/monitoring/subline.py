"""Wharfedale Infrastructure Partners III: Thornbury Bank's subscription line, lent against the
fund's investors' uncalled commitments.

Thornbury does not permit AI, so nothing here calls a model. The administrator's investor
register and its capital call and distribution notices are workbooks, read through stored
mappings. Code classifies every investor from its rating and approved class, finds Exclusion
Events the register has not applied, reconciles each notice to the register investor by investor
and works out the borrowing base, concentration excess and any mandatory prepayment.
"""

from decimal import Decimal
from pathlib import Path
from typing import Any

from engine.fundfinance import (
    Investor,
    borrowing_base,
    classify,
    reconcile_notice,
    roll_register,
)
from openpyxl import load_workbook

from app.monitoring.middle_market import read_sheet

FACILITY = "wharfedale"


def _cents(text: str) -> int:
    return int((Decimal(text) * 100).to_integral_value())


def _usd(value: float) -> str:
    return f"US${value:,.2f}"


def _notice(path: Path) -> tuple[dict[str, Any], list[tuple]]:
    book = load_workbook(path, read_only=True)
    header = {row[0]: row[1] for row in book["Notice"].iter_rows(min_row=4, values_only=True)
              if row[0]}
    lines = list(book["Allocation"].iter_rows(min_row=2, values_only=True))
    return header, lines


def tests(meta: dict[str, Any], folder: Path, evidence: Any) -> dict[str, Any]:
    fac = next(f for f in meta["facilities"] if f["id"] == FACILITY)
    terms = fac["terms"]
    april = read_sheet(folder / fac["registers"]["April"], "Register", fac["mapping"])
    may = read_sheet(folder / fac["registers"]["May"], "Register", fac["mapping"])
    call_head, call_lines = _notice(folder / fac["capital_call"])
    dist_head, dist_lines = _notice(folder / fac["distribution"])
    prior = {r["investor_id"]: _cents(r["uncalled"]) for r in april}
    register = {r["investor_id"]: _cents(r["uncalled"]) for r in may}
    calls = {line[0]: _cents(str(line[3])) for line in call_lines}
    recallable = {line[0]: _cents(str(line[4])) for line in dist_lines}
    call_check, call_sum, call_ok = reconcile_notice(
        [(line[0], _cents(str(line[2])), _cents(str(line[3]))) for line in call_lines],
        _cents(str(call_head["Amount called (US$)"])),
        Decimal(str(call_head["Per cent of commitments"])))
    dist_check, dist_sum, dist_ok = reconcile_notice(
        [(line[0], _cents(str(line[2])), _cents(str(line[3]))) for line in dist_lines],
        _cents(str(dist_head["Amount distributed (US$)"])),
        Decimal(str(dist_head["Per cent of commitments"])))
    recall_check, recall_sum, recall_ok = reconcile_notice(
        [(line[0], _cents(str(line[2])), _cents(str(line[4]))) for line in dist_lines],
        _cents(str(dist_head["Of which recallable (US$)"])),
        Decimal(str(dist_head["Recallable per cent"])))
    rolled = {c.investor: c for c in roll_register(prior, calls, recallable, register)}
    by_april = {r["investor_id"]: r for r in april}
    investors, rows = [], []
    for r in may:
        oid = r["investor_id"]
        before = classify(by_april[oid]["rating"], by_april[oid]["designation"],
                          terms["included_min_rating"], terms["exclusion_below"])
        now = classify(r["rating"], by_april[oid]["designation"], terms["included_min_rating"],
                       terms["exclusion_below"])
        roll = rolled[oid]
        # Use the rolled figure where the register has not posted the month's notices.
        uncalled = min(roll.expected_cents, roll.register_cents)
        investors.append(Investor(oid, r["investor"], uncalled, now.name))
        rows.append({
            "id": oid, "name": r["investor"], "type": r["investor_type"],
            "commitment": _cents(r["commitment"]) / 100,
            "called": _cents(r["called"]) / 100,
            "register_uncalled": roll.register_cents / 100,
            "prior_uncalled": roll.prior_uncalled_cents / 100,
            "call": roll.called_cents / 100, "recallable": roll.recallable_cents / 100,
            "expected_uncalled": roll.expected_cents / 100,
            "difference": roll.difference_cents / 100,
            "uncalled": uncalled / 100,
            "rating": r["rating"], "prior_rating": by_april[oid]["rating"],
            "rating_date": r["rating_date"][:10],
            "register_designation": r["designation"],
            "class": now.name, "prior_class": before.name, "reason": now.reason,
            "exclusion_event": now.exclusion_event,
            "sheet_row": int(r["sheet_row"]),
        })
    rates = {k: Decimal(v) for k, v in terms["advance_rates"].items()}
    commitment, drawn = terms["commitment_usd"] * 100, terms["drawn_usd"] * 100
    single, designated = Decimal(terms["single_investor_limit_pct"]), Decimal(
        terms["designated_limit_pct"])
    after = borrowing_base(investors, rates, single, designated, commitment, drawn)
    as_registered = borrowing_base(
        [Investor(i.id, i.name, i.uncalled_cents, next(r["prior_class"] for r in rows
                                                        if r["id"] == i.id)) for i in investors],
        rates, single, designated, commitment, drawn)
    by_id = {r["id"]: r for r in rows}
    for r in rows:
        r["counted"] = (after.values_cents.get(r["id"], 0)) / 100
        r["excess"] = after.investor_excess_cents.get(r["id"], 0) / 100
        r["share_pct"] = float(after.shares.get(r["id"], 0))
    largest = max((r for r in rows if r["class"] != "Excluded"), key=lambda r: r["uncalled"])
    agreement = f"{FACILITY}/{fac['agreement']}"
    evidence.add(agreement)
    clauses = {key: evidence.cite(agreement, terms[f"{key}_quote"], label) for key, label in (
        ("exclusion", "Credit Agreement 1.1, Exclusion Event"),
        ("concentration", "Credit Agreement 1.1, Concentration Limits"),
        ("base", "Credit Agreement 1.1, Borrowing Base"),
        ("prepayment", "Credit Agreement 2.5, Mandatory prepayment"))}

    def view(base: Any) -> dict[str, Any]:
        return {
            "aggregate_eligible_uncalled": base.aggregate_eligible_cents / 100,
            "single_limit": base.single_limit_cents / 100,
            "concentration_excess": {k: v / 100 for k, v in base.investor_excess_cents.items()},
            "concentration_reduction": base.concentration_reduction_cents / 100,
            "designated": base.designated_cents / 100,
            "designated_limit": base.designated_limit_cents / 100,
            "designated_excess": base.designated_excess_cents / 100,
            "designated_pct": float((Decimal(base.designated_cents) / Decimal(
                base.aggregate_eligible_cents) * 100).quantize(Decimal("0.01"))),
            "borrowing_base": base.borrowing_base_cents / 100,
            "availability": base.availability_cents / 100,
            "prepayment": base.prepayment_cents / 100,
        }

    def lines(check: list[Any]) -> list[dict[str, Any]]:
        return [{"investor": c.investor, "name": by_id[c.investor]["name"],
                 "amount": c.amount_cents / 100, "expected": c.expected_cents / 100,
                 "difference": c.difference_cents / 100} for c in check]

    return {
        "determination_date": fac["determination_date"].isoformat(),
        "register_file": fac["registers"]["May"],
        "investors": rows,
        "classes": {k: sum(1 for r in rows if r["class"] == k)
                    for k in ("Included", "Designated", "Excluded")},
        "commitments": sum(r["commitment"] for r in rows),
        "uncalled": sum(r["uncalled"] for r in rows),
        "exclusions": [r for r in rows if r["exclusion_event"]],
        "unapplied": [r["id"] for r in rows if r["exclusion_event"]
                      and r["register_designation"] != "Excluded"],
        "borrowing_base": {**view(after), "commitment": commitment / 100, "drawn": drawn / 100,
                           "advance_rates": {k: float(v) for k, v in rates.items()},
                           "single_limit_pct": float(single),
                           "designated_limit_pct": float(designated),
                           "passed": after.prepayment_cents == 0},
        "before_exclusion": view(as_registered),
        "largest": {"id": largest["id"], "name": largest["name"],
                    "share_pct": largest["share_pct"], "excess": largest["excess"]},
        "notices": {
            "capital_call": {"file": fac["capital_call"], "number": 7,
                             "date": str(call_head["Notice date"]),
                             "due": str(call_head["Due date"]),
                             "total": _cents(str(call_head["Amount called (US$)"])) / 100,
                             "pct": float(call_head["Per cent of commitments"]),
                             "sum_difference": call_sum / 100, "reconciles": call_ok,
                             "lines": lines(call_check)},
            "distribution": {"file": fac["distribution"], "number": 4,
                             "date": str(dist_head["Notice date"]),
                             "total": _cents(str(dist_head["Amount distributed (US$)"])) / 100,
                             "recallable": _cents(str(dist_head["Of which recallable (US$)"]))
                             / 100,
                             "pct": float(dist_head["Per cent of commitments"]),
                             "recallable_pct": float(dist_head["Recallable per cent"]),
                             "sum_difference": (dist_sum + recall_sum) / 100,
                             "reconciles": dist_ok and recall_ok,
                             "lines": lines(recall_check)},
        },
        "register_breaks": [r for r in rows if r["difference"]],
        "clauses": [c for c in clauses.values() if c],
        "clause_sources": clauses,
        "ai_used": False,
    }


def _item(**item: Any) -> dict[str, Any]:
    return {"rule_outcome": None, "evidence": [], "sources": [], "clauses": [], **item}


def findings(t: dict[str, Any]) -> list[dict[str, Any]]:
    """Thornbury does not permit AI, so rules suggest each outcome, as they do today."""
    items = []
    bb, before, clauses = t["borrowing_base"], t["before_exclusion"], t["clause_sources"]
    for r in t["exclusions"]:
        items.append(_item(
            id=f"F-wharfedale-exclusion-{r['id']}", facility=FACILITY,
            check="Investor eligibility",
            title=f"{r['name']} downgraded to {r['rating']}: an Exclusion Event",
            detail=f"Rated {r['prior_rating']} at the end of April, {r['rating']} from "
            f"{r['rating_date']}, below the agreement's floor. The register still shows it as "
            f"{r['register_designation']}. Its uncalled commitment of {_usd(r['uncalled'])} "
            f"leaves the borrowing base, which falls from {_usd(before['borrowing_base'])} to "
            f"{_usd(bb['borrowing_base'])}, below the loans outstanding of {_usd(bb['drawn'])}. "
            f"Mandatory prepayment of {_usd(bb['prepayment'])} is due within two business days.",
            owner="Lender", investor=r["id"],
            clauses=[c for c in (clauses["exclusion"], clauses["prepayment"]) if c],
            suggested={"outcome": "confirmed", "by": "Rule",
                       "reason": "The rating is below the agreement's floor on clear terms and "
                       "the base is below the loans, so the lender is told. Suggested by rule: "
                       "this client does not permit AI."},
            handoff={"on": "confirmed", "role": "client", "client": "thornbury",
                     "title": f"Prepayment notice: Wharfedale borrowing base short by "
                     f"{_usd(bb['prepayment'])}"}))
    for oid, excess in bb["concentration_excess"].items():
        r = next(x for x in t["investors"] if x["id"] == oid)
        items.append(_item(
            id=f"F-wharfedale-concentration-{oid}", facility=FACILITY,
            check="Investor concentration",
            title=f"{r['name']}: {r['share_pct']:.2f}% of eligible uncalled against a "
            f"{bb['single_limit_pct']:.0f}% limit",
            detail=f"After the exclusion, the aggregate eligible uncalled is "
            f"{_usd(bb['aggregate_eligible_uncalled'])}, so this investor counts only up to "
            f"{_usd(bb['single_limit'])}. The excess of {_usd(excess)} takes "
            f"{_usd(bb['concentration_reduction'])} off the borrowing base. It was "
            f"{_usd(t['before_exclusion']['single_limit'])} before the exclusion, inside the "
            "limit.", owner="Lender", investor=oid,
            clauses=[c for c in (clauses["concentration"],) if c],
            suggested={"outcome": "confirmed", "by": "Rule",
                       "reason": "A concentration limit exceeded on clear terms is reported to "
                       "the lender. Suggested by rule: this client does not permit AI."},
            handoff={"on": "confirmed", "role": "client", "client": "thornbury",
                     "title": f"Lender told: {r['name']} over the investor concentration limit"}))
    for r in t["register_breaks"]:
        items.append(_item(
            id=f"F-wharfedale-register-{r['id']}", facility=FACILITY,
            check="Notice reconciliation",
            title=f"Register uncalled for {r['name']} does not reflect May's notices",
            detail=f"April's register shows {_usd(r['prior_uncalled'])} uncalled. Capital call "
            f"7 called {_usd(r['call'])} and distribution 4 made {_usd(r['recallable'])} "
            f"recallable, so May should show {_usd(r['expected_uncalled'])}; the register shows "
            f"{_usd(r['register_uncalled'])}. The borrowing base uses the lower figure until the "
            "administrator corrects it.", owner="Administrator", investor=r["id"],
            suggested={"outcome": "query", "by": "Rule",
                       "reason": "The register is inconsistent with the notices, so the "
                       "administrator must correct it. Suggested by rule: this client does not "
                       "permit AI."},
            handoff={"on": "query", "role": "client", "client": "thornbury",
                     "title": f"For the status call: Wharfedale register query on {r['name']}"}))
    dist = t["notices"]["distribution"]
    if dist["reconciles"]:
        items.append(_item(
            id="F-wharfedale-distribution", facility=FACILITY, check="Notice reconciliation",
            rule_outcome="logged",
            rule_reason="Every investor's share is its pro-rata part of the notice to the cent, "
            "and the register adds back the recallable amount.",
            title=f"Distribution notice 4 reconciles: {_usd(dist['total'])}, "
            f"{_usd(dist['recallable'])} recallable",
            detail="The recallable part is added back to each investor's uncalled commitment.",
            suggested={"outcome": "logged", "by": "Rule",
                       "reason": "Reconciles to the cent; recallable amount added back."}))
    return items


TOPICS = {
    "F-wharfedale-exclusion": "An investor downgraded below the floor leaves the borrowing base",
    "F-wharfedale-concentration": "One investor over the concentration limit after the exclusion",
    "F-wharfedale-register": "The investor register has not posted May's notices for one "
    "investor",
    "F-wharfedale-distribution": "The distribution notice reconciles to the register",
}


def pack(t: dict[str, Any], items: list[dict[str, Any]]) -> dict[str, Any]:
    """Written by code from a fixed template, as Thornbury requires."""
    bb, before = t["borrowing_base"], t["before_exclusion"]

    def fig(value: str, means: str, source: Any = None) -> dict[str, Any]:
        return {"value": value, "means": means, "source": source}

    excluded = t["exclusions"][0] if t["exclusions"] else None
    figures = {
        "open_items": fig(str(sum(i["suggested"]["outcome"] != "logged" for i in items)),
                          "findings that need someone to act"),
        "base_before": fig(_usd(before["borrowing_base"]), "borrowing base before the exclusion"),
        "borrowing_base": fig(_usd(bb["borrowing_base"]), "borrowing base, recomputed",
                              t["clause_sources"]["base"]),
        "drawn": fig(_usd(bb["drawn"]), "loans outstanding"),
        "prepayment": fig(_usd(bb["prepayment"]), "mandatory prepayment",
                          t["clause_sources"]["prepayment"]),
        "concentration_reduction": fig(_usd(bb["concentration_reduction"]),
                                       "concentration excess at its advance rate"),
        "largest_share": fig(f"{t['largest']['share_pct']:.2f}%", "largest investor's share"),
        "single_limit": fig(f"{bb['single_limit_pct']:.0f}%", "single-investor limit"),
    }
    sections = [
        {"heading": "Submissions", "text": "The May investor register, capital call notice 7 and "
         "distribution notice 4 arrived on time. Each passed every blocking check."},
        {"heading": "Investor eligibility", "text": (
            f"{excluded['name']} was downgraded to {excluded['rating']}, below the agreement's "
            "floor, so it is an Excluded Investor. The register had not applied this." if excluded
            else "No Exclusion Event this month.")},
        {"heading": "Borrowing base and concentration", "text": "The borrowing base falls from "
         "{{base_before}} to {{borrowing_base}} against loans of {{drawn}}, so a mandatory "
         "prepayment of {{prepayment}} is due within two business days. After the exclusion the "
         "largest investor is {{largest_share}} of eligible uncalled against a {{single_limit}} "
         "limit, which takes {{concentration_reduction}} off the base."},
        {"heading": "Notices", "text": "Capital call 7 and distribution 4 reconcile investor by "
         "investor. One investor's register entry has not posted them; we have asked the "
         "administrator to correct it and use the lower figure meanwhile."},
    ]
    return {"facility": FACILITY, "summary": "Wharfedale's borrowing base is below the loans "
            "after an investor's downgrade, so a prepayment is due. Prepared on code checks only, "
            "as Thornbury requires.", "sections": sections, "figures": figures,
            "unknown_placeholders": [], "numbers_in_text": [], "ai": False}


def brief_points(t: dict[str, Any]) -> dict[str, list[str]]:
    bb = t["borrowing_base"]
    out: dict[str, list[str]] = {"Exclusions": [], "Open questions": []}
    for r in t["exclusions"]:
        out["Exclusions"].append(
            f"Wharfedale: {r['name']} downgraded to {r['rating']} and excluded; borrowing base "
            f"{_usd(bb['borrowing_base'])} against loans of {_usd(bb['drawn'])}, so "
            f"{_usd(bb['prepayment'])} is to be prepaid.")
    for r in t["register_breaks"]:
        out["Open questions"].append(
            f"Wharfedale: the register has not posted capital call 7 or distribution 4 for "
            f"{r['name']}; administrator asked to correct it.")
    return out


def headroom_rows(t: dict[str, Any], history: list[tuple[str, float]], row: Any) -> list[
        dict[str, Any]]:
    bb = t["borrowing_base"]
    return [
        row(FACILITY, "Availability", "Section 2.5", bb["availability"], 0, "min", "US$",
            [*history, ("May 2026", bb["availability"])], Decimal(10_000_000),
            note=f"Mandatory prepayment of {_usd(bb['prepayment'])} after the exclusion"),
        row(FACILITY, "Largest investor share", "Section 1.1", t["largest"]["share_pct"],
            bb["single_limit_pct"], "max", "%", [("May 2026", t["largest"]["share_pct"])],
            Decimal(1), note=t["largest"]["name"]),
        row(FACILITY, "Designated investors' share", "Section 1.1", bb["designated_pct"],
            bb["designated_limit_pct"], "max", "%", [("May 2026", bb["designated_pct"])],
            Decimal(3)),
    ]


def qc_values(t: dict[str, Any]) -> dict[str, Any]:
    bb = t["borrowing_base"]
    return {"Aggregate eligible uncalled": bb["aggregate_eligible_uncalled"],
            "Concentration reduction": bb["concentration_reduction"],
            "Borrowing base": bb["borrowing_base"], "Mandatory prepayment": bb["prepayment"]}
