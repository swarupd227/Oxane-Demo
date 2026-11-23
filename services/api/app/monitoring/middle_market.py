"""Ravenglass Direct Lending Fund I: Calderwood Bank's back-leverage facility on a middle-market
book of 40 obligor loans.

The model reads each obligor's quarterly financial statements and compliance certificate, in
whatever layout the obligor uses, with an exact quote for every figure; code finds each quote on
its page, works out every obligor's leverage and interest cover, tests each against the covenant
in force for the test date (after any waiver), and builds the borrowing base with the engine. A
waiver notice is read the same way. Drafted text carries figures only as {{placeholders}}.

Where a model reading has not been recorded, the cycle still runs: obligor figures come from the
fund's own portfolio report (a structured file, read through the stored mapping), a keyed
covenant change stands in for the notice reading, and triage suggestions, the pack and the brief
come from rules and templates. Every such step is listed as pending recording.
"""

import csv
import json
import re
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

from engine.directlending import (
    AddBack,
    CovenantVersion,
    ObligorLoan,
    addback_readings,
    borrowing_base,
    check_obligor,
    level_in_force,
)
from engine.run import to_cents
from openpyxl import load_workbook

from app.monitoring import steps
from app.pipeline.documents import PdfDocument, normalise
from app.pipeline.gateway import ReplayMiss

FACILITY = "ravenglass"


class Pending:
    """Model steps that could not replay because they were never recorded."""

    def __init__(self) -> None:
        self.items: list[dict[str, str]] = []

    def run(self, task: str, subject: str, call: Any) -> Any:
        try:
            return call()
        except ReplayMiss:
            self.items.append({"task": task, "facility": FACILITY, "subject": subject})
            return None


def _number(text: str) -> Decimal:
    found = re.search(r"\d[\d,]*(?:\.\d+)?", text)
    if found is None:
        raise ValueError(f"No number in {text!r}")
    value = Decimal(found.group(0).replace(",", ""))
    return -value if "(" in text[: found.start()] else value


def _usd(value: float) -> str:
    return f"US${value:,.2f}"


def _m(value: float) -> str:
    return f"US${value / 1e6:,.2f}m"


def _k(value: int) -> str:
    return f"US${value:,}k"


def read_sheet(path: Path, sheet: str, mapping: dict[str, str]) -> list[dict[str, str]]:
    book = load_workbook(path, read_only=True)
    rows = list(book[sheet].iter_rows(values_only=True))
    header = [str(h) for h in rows[0]]
    out = []
    for line, values in enumerate(rows[1:], start=2):
        raw = dict(zip(header, values, strict=True))
        item = {mapping[k]: ("" if v is None else str(v)) for k, v in raw.items() if k in mapping}
        item["sheet_row"] = str(line)
        out.append(item)
    return out


def certificate(path: Path) -> dict[str, float]:
    sheet = load_workbook(path, read_only=True)["BBC Summary"]
    cells = {row[0]: row[1] for row in sheet.iter_rows(min_row=5, max_row=11, values_only=True)}
    return {"aggregate": float(cells["Aggregate Outstanding Balance"]),
            "eligible": float(cells["Aggregate Eligible Balance"]),
            "borrowing_base": float(cells["Borrowing Base"]),
            "availability": float(cells["Availability"])}


def submissions(fac: dict[str, Any], folder: Path) -> list[dict[str, Any]]:
    """The fund's inbox log for the cycle, as the collect step takes it."""
    with (folder / fac["inbox"]).open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    items = []
    for row in rows:
        items.append({
            "facility": FACILITY, "label": row["label"], "file": row["file"] or None,
            "due": date.fromisoformat(row["due"]),
            "received": date.fromisoformat(row["received"]) if row["received"] else None,
            "channel": row["channel"], "obligor": row["obligor"] or None,
            "document": row["document"],
            "sender": "Ravenglass Capital Management LLP",
            "contact": "Portfolio reporting team",
            "escalation_note": "Still not received one business day after the reminder. The "
            "obligor's loan stays out of the borrowing base until they arrive.",
        })
    return items


def layout_of(document: PdfDocument, library: list[dict[str, Any]], kind: str) -> str | None:
    """The stored layout whose own heading this document carries, or None for a new layout."""
    text = document.pages[0].text if document.pages else ""
    for entry in library:
        if entry.get("obligor_documents") == kind and entry["signature"] in text:
            return entry["id"]
    return None


# Model readings, each checked by code


WANTED = ["Consolidated EBITDA", "Net debt", "Interest expense", "Covenant EBITDA",
          "Total net leverage", "Interest cover"]


def _find(figures: list[steps.Figure], name: str) -> steps.Figure | None:
    wanted = name.lower()
    return next((f for f in figures if normalise(f.name).lower() == wanted), None) or next(
        (f for f in figures if wanted in normalise(f.name).lower()), None)


def extraction(gateway: Any, evidence: Any, fac: dict[str, Any], received: list[dict[str, Any]],
               pending: Pending) -> dict[str, Any]:
    """Every received obligor's figures as the model read them, each quote found on its page.
    Obligors are read in batches, in register order, so each request is the same every run."""
    terms = fac["terms"]
    batch_size = terms["batch_size"]
    readings: dict[str, dict[str, Any]] = {}
    batches, done = 0, 0
    for start in range(0, len(received), batch_size):
        batch = received[start:start + batch_size]
        batches += 1
        docs = {o["id"]: (evidence.add(f"{FACILITY}/{o['financials_file']}"),
                          evidence.add(f"{FACILITY}/{o['certificate_file']}")) for o in batch}
        result = pending.run(
            "read_obligor_financials", f"Obligors {batch[0]['id']} to {batch[-1]['id']}",
            lambda docs=docs: steps.read_obligor_financials(
                gateway, [d for pair in docs.values() for d in pair],
                terms["ebitda_definition"]))
        if result is None:
            continue
        done += 1
        for reading in result.obligors:
            if reading.obligor_id not in docs:
                continue
            pair = docs[reading.obligor_id]
            scale = Decimal(1000) if "million" in reading.unit.lower() else Decimal(1)
            figures, verified = {}, True
            for name in WANTED:
                item = _find(reading.figures, name)
                if item is None:
                    continue
                source = next((s for s in (evidence.cite(d.id, item.quote) for d in pair) if s),
                              None)
                number = re.search(r"\d[\d,]*(?:\.\d+)?", item.value)
                held = bool(number) and number.group(0) in normalise(item.quote)
                ok = bool(source) and held
                verified = verified and ok
                value = _number(item.value)
                if name == "Interest expense":
                    value = abs(value)  # statements print it as an outflow, in brackets
                if name not in ("Total net leverage", "Interest cover"):
                    value = value * scale
                figures[name] = {"value": float(value), "source": source, "verified": ok}
            addbacks = []
            for a in reading.addbacks:
                source = next((s for s in (evidence.cite(d.id, a.quote) for d in pair) if s),
                              None)
                verified = verified and bool(source)
                addbacks.append({"description": a.description,
                                 "amount_k": int(abs(_number(a.amount)) * scale),
                                 "kind": a.kind,
                                 "reason": a.reason, "source": source})
            readings[reading.obligor_id] = {"figures": figures, "addbacks": addbacks,
                                            "verified": verified and all(
                                                n in figures for n in WANTED[:3])}
    return {"status": "recorded" if done == batches else "pending" if not done else "partial",
            "batches": batches, "batches_read": done, "readings": readings}


def covenant_changes(gateway: Any, evidence: Any, fac: dict[str, Any], subs: list[dict[str, Any]],
                     pending: Pending) -> list[dict[str, Any]]:
    """Changes to obligors' covenants, read from each notice by the model, or keyed by the
    analyst where the reading is not recorded. Either way code finds the quote on its page."""
    out = []
    notices = [s for s in subs if s.get("document") == "waiver_notice" and s.get("file")]
    for notice in notices:
        relative = f"{FACILITY}/{notice['file']}"
        document = evidence.add(relative)
        reading = pending.run("read_covenant_notice", notice["label"],
                              lambda document=document: steps.read_covenant_notice(
                                  gateway, document))
        if reading is not None:
            for change in reading.changes:
                source = evidence.cite(relative, change.quote, "Notice of amendment and waiver")
                out.append({
                    "obligor": change.obligor_id, "covenant": change.covenant,
                    "old_value": change.old_value, "new_value": change.new_value,
                    "test_dates": change.test_dates, "effective_from": change.effective_from,
                    "document": relative, "source": source, "verified": bool(source),
                    "by": "AI",
                })
            continue
        for keyed in fac.get("keyed_covenant_changes", []):
            if keyed["document"] != notice["file"]:
                continue
            source = evidence.cite(relative, keyed["quote"], "Notice of amendment and waiver")
            out.append({
                "obligor": keyed["obligor"], "covenant": keyed["covenant"],
                "old_value": keyed["old_value"], "new_value": keyed["new_value"],
                "test_dates": [d.isoformat() if isinstance(d, date) else d
                               for d in keyed["test_dates"]],
                "effective_from": str(keyed["effective_from"]), "document": relative,
                "source": source, "verified": bool(source),
                "by": f"Keyed by {keyed['keyed_by']}",
            })
    return out


# Tests


def tests(gateway: Any, evidence: Any, meta: dict[str, Any], folder: Path,
          subs: list[dict[str, Any]], pending: Pending) -> dict[str, Any]:
    fac = next(f for f in meta["facilities"] if f["id"] == FACILITY)
    terms = fac["terms"]
    library = meta["mapping_library"]
    record = json.loads((folder / fac["obligor_record"]).read_text(encoding="utf-8"))
    report = {r["obligor_id"]: r for r in read_sheet(folder / fac["portfolio_report"],
                                                     "Portfolio", fac["mapping"])}
    stated = certificate(folder / fac["certificate"])
    quarter_end = fac["quarter_end"]
    got = {(s["obligor"], s["document"]): s for s in subs if s.get("obligor") and s["received"]}
    obligors = []
    for o in record["obligors"]:
        fs, cc = got.get((o["id"], "obligor_financials")), got.get((o["id"], "obligor_compliance"))
        obligors.append({**o, "received": bool(fs and cc),
                         "financials_file": fs["file"] if fs else None,
                         "certificate_file": cc["file"] if cc else None,
                         "received_on": max(fs["received"], cc["received"]) if fs and cc
                         else None})
    received = [o for o in obligors if o["received"]]
    read = extraction(gateway, evidence, fac, received, pending)
    changes = covenant_changes(gateway, evidence, fac, subs, pending)
    agreement = f"{FACILITY}/{fac['agreement']}"
    evidence.add(agreement)
    clauses = {key: evidence.cite(agreement, terms[f"{key}_quote"], label) for key, label in (
        ("eligible", "Agreement 1.1, Eligible Obligor Loan"),
        ("event", "Agreement 1.1, Material Obligor Event"),
        ("ebitda", "Agreement 1.1, Covenant EBITDA"),
        ("base", "Agreement 1.1, Borrowing Base"),
        ("concentration", "Agreement 1.1, Concentration Excess Amount"))}
    cap = Decimal(str(terms["addback_cap_pct"]))
    tolerance = Decimal(str(terms["leverage_tolerance_x"]))
    rates = terms["advance_rates"]
    rows, loans = [], []
    for o in obligors:
        line = report[o["id"]]
        reading = read["readings"].get(o["id"])
        basis = "extracted" if reading and reading["verified"] else "portfolio_report"
        if basis == "extracted":
            f = reading["figures"]
            ebitda = int(f["Consolidated EBITDA"]["value"])
            net_debt = int(f["Net debt"]["value"])
            interest = int(f["Interest expense"]["value"])
            addbacks = [AddBack(a["description"], a["amount_k"], a["kind"])
                        for a in reading["addbacks"]]
            items = reading["addbacks"]
        else:
            ebitda = int(Decimal(line["ebitda"]))
            net_debt = int(Decimal(line["net_debt"]))
            interest = int(Decimal(line["interest_expense"]))
            adjustments = int(Decimal(line["ebitda_adjustments"] or "0"))
            addbacks = [AddBack("EBITDA adjustments, not itemised", adjustments, None)] \
                if adjustments else []
            items = []
        covenant = ebitda + sum(a.amount_k for a in addbacks)
        versions = [CovenantVersion("Underlying loan agreement",
                                    Decimal(str(o["max_leverage"])))]
        mine = [c for c in changes if c["obligor"] == o["id"] and c["verified"]]
        for change in mine:
            versions.append(CovenantVersion(
                f"Waiver of {change['effective_from']}", _number(change["new_value"]),
                tuple(date.fromisoformat(d) for d in change["test_dates"])))
        in_force = level_in_force(versions, quarter_end)
        stale = line["financials_as_of"][:10] != quarter_end.isoformat()
        check = check_obligor(o["id"], net_debt, covenant, interest, in_force.max_leverage,
                              Decimal(str(o["min_icr"])),
                              Decimal(line["reported_leverage"]) if line["reported_leverage"]
                              else None, tolerance)
        share = Decimal(sum(a.amount_k for a in addbacks)) / Decimal(ebitda) * 100
        flagged = bool(addbacks) and share > cap
        readings = [
            {"name": r.name, "covenant_ebitda_k": r.covenant_ebitda_k,
             "leverage": float(r.leverage), "passed": r.passed}
            for r in addback_readings(ebitda, net_debt, addbacks, cap, in_force.max_leverage)
        ] if flagged else []
        if not o["received"]:
            eligible, reason = False, "Q1 financials not delivered"
        elif not check.passed:
            eligible, reason = False, "Material Obligor Event"
        else:
            eligible, reason = True, ""
        rate = Decimal(rates[o["facility"]])
        loans.append(ObligorLoan(o["id"], o["name"], o["sector"], o["outstanding"] * 100, rate,
                                 eligible, reason))
        rows.append({
            "id": o["id"], "name": o["name"], "sector": o["sector"], "sponsor": o["sponsor"],
            "facility": o["facility"], "outstanding": o["outstanding"],
            "advance_rate": float(rate), "received": o["received"],
            "received_on": o["received_on"],
            "financials_file": o["financials_file"], "certificate_file": o["certificate_file"],
            "layout": layout_of(evidence.add(f"{FACILITY}/{o['financials_file']}"), library,
                                "financials") if o["financials_file"] else None,
            "certificate_layout": layout_of(evidence.add(f"{FACILITY}/{o['certificate_file']}"),
                                            library, "certificates")
            if o["certificate_file"] else None,
            "basis": basis, "stale": stale, "financials_as_of": line["financials_as_of"][:10],
            "ebitda_k": ebitda, "addbacks_k": covenant - ebitda, "covenant_ebitda_k": covenant,
            "net_debt_k": net_debt, "interest_k": interest,
            "leverage": float(check.leverage), "reported_leverage": float(check.reported_leverage)
            if check.reported_leverage is not None else None,
            "leverage_difference": float(check.leverage_difference)
            if check.leverage_difference is not None else None,
            "within_tolerance": check.within_tolerance,
            "max_leverage": float(in_force.max_leverage), "max_leverage_basis": in_force.label,
            "original_max_leverage": o["max_leverage"],
            "reported_max_leverage": float(line["reported_max_leverage"]),
            "icr": float(check.icr), "min_icr": o["min_icr"],
            "leverage_passed": check.leverage_passed, "icr_passed": check.icr_passed,
            "headroom": float(check.leverage_headroom), "eligible": eligible, "reason": reason,
            "addback_pct": float(share.quantize(Decimal("0.01"))) if addbacks else 0.0,
            "addbacks_flagged": flagged, "addback_items": items, "readings": readings,
            "sources": {k: v["source"] for k, v in (reading or {}).get("figures", {}).items()},
            "sheet_row": int(line["sheet_row"]),
        })
    commitment, drawn = terms["commitment_usd"] * 100, terms["drawn_usd"] * 100
    base = borrowing_base(loans, Decimal(str(terms["single_obligor_limit_pct"])),
                          Decimal(str(terms["sector_limit_pct"])), commitment, drawn)
    by_id = {r["id"]: r for r in rows}
    bridge = [{"obligor": oid, "name": by_id[oid]["name"], "reason": why,
               "outstanding": cents / 100,
               "value": float(Decimal(cents) * Decimal(str(by_id[oid]["advance_rate"]))
                              / 100 / 100)}
              for oid, why, cents in base.excluded]
    flagged = [r for r in rows if r["addbacks_flagged"]]
    sensitivity = [{"obligor": r["id"], "name": r["name"],
                    "if_excluded": round(r["outstanding"] * r["advance_rate"] / 100, 2)}
                   for r in flagged if r["eligible"]]
    layouts: dict[str, int] = {}
    for r in rows:
        for key in ("layout", "certificate_layout"):
            if r[key]:
                layouts[r[key]] = layouts.get(r[key], 0) + 1
    return {
        "quarter_end": quarter_end.isoformat(),
        "determination_date": fac["determination_date"].isoformat(),
        "portfolio_file": fac["portfolio_report"],
        "certificate_file": fac["certificate"],
        "obligors": rows,
        "received": len(received),
        "covenant_changes": changes,
        "extraction": {k: v for k, v in read.items() if k != "readings"}
        | {"obligors_read": len(read["readings"]),
           "verified": sum(1 for r in read["readings"].values() if r["verified"])},
        "borrowing_base": {
            "aggregate": base.aggregate_cents / 100,
            "eligible": base.eligible_cents / 100,
            "excluded": bridge,
            "single_limit": base.single_limit_cents / 100,
            "sector_limit": base.sector_limit_cents / 100,
            "obligor_excess": {k: v / 100 for k, v in base.obligor_excess_cents.items()},
            "sector_excess": {k: v / 100 for k, v in base.sector_excess_cents.items()},
            "excess_reduction": base.excess_reduction_cents / 100,
            "largest": {"obligor": base.largest[0], "name": by_id[base.largest[0]]["name"],
                        "pct": float(base.largest[1])},
            "largest_sector": {"sector": base.largest_sector[0],
                               "pct": float(base.largest_sector[1])},
            "single_limit_pct": terms["single_obligor_limit_pct"],
            "sector_limit_pct": terms["sector_limit_pct"],
            "borrowing_base": base.borrowing_base_cents / 100,
            "commitment": commitment / 100,
            "drawn": drawn / 100,
            "availability": base.availability_cents / 100,
            "certificate": stated,
            "difference": round(stated["borrowing_base"] - base.borrowing_base_cents / 100, 2),
            "bridged": round(sum(b["value"] for b in bridge), 2),
            "sensitivity": sensitivity,
            "passed": base.availability_cents >= 0,
        },
        "layouts": dict(sorted(layouts.items())),
        "clauses": [c for c in clauses.values() if c],
        "clause_sources": clauses,
        "cap_pct": float(cap),
        "tolerance_x": float(tolerance),
    }


# Findings, triage, pack and brief


def _item(**item: Any) -> dict[str, Any]:
    return {"rule_outcome": None, "evidence": [], "sources": [], "clauses": [], **item}


def findings(t: dict[str, Any], subs: list[dict[str, Any]], pretty: Any) -> list[dict[str, Any]]:
    items = []
    late = {s["obligor"]: s for s in subs if s.get("obligor") and s["status"] == "late"}
    clauses = t["clause_sources"]
    for r in t["obligors"]:
        if not r["received"]:
            sub = late.get(r["id"])
            chase = sub["chase"] if sub else []
            value = r["outstanding"] * r["advance_rate"] / 100
            items.append(_item(
                id=f"F-ravenglass-financials-{r['id']}", facility=FACILITY, check="Submissions",
                title=f"{r['name']}: Q1 financials not received",
                detail=(f"Due {pretty(sub['due'])}" if sub else "Due 15 May 2026")
                + (f". Reminder sent {pretty(chase[0]['at'])}" if chase else "")
                + (f", escalated {pretty(chase[1]['at'])}" if len(chase) > 1 else "")
                + ". Out of the borrowing base until they arrive: the loan of "
                f"{_m(r['outstanding'])}"
                f" carries {_m(value)} of value. The fund's portfolio report still shows its "
                f"figures as of {pretty(r['financials_as_of'])}.",
                owner="Borrower", sender="Ravenglass Capital Management LLP", obligor=r["id"],
                clauses=[c for c in (clauses["eligible"],) if c],
                handoff={"on": "query", "role": "client", "client": "calderwood",
                         "title": f"For the status call: {r['name']} financials outstanding"}))
            continue
        if not r["eligible"]:
            value = r["outstanding"] * r["advance_rate"] / 100
            test = "leverage" if not r["leverage_passed"] else "interest cover"
            figure = (f"{r['leverage']:.2f}x against a {r['max_leverage']:.2f}x maximum"
                      if test == "leverage" else
                      f"{r['icr']:.2f}x against a {r['min_icr']:.2f}x minimum")
            items.append(_item(
                id=f"F-ravenglass-leverage-{r['id']}", facility=FACILITY,
                check="Obligor covenants", title=f"{r['name']}: {test} {figure}",
                detail=f"Recomputed from the Q1 figures: net debt {_k(r['net_debt_k'])} over "
                f"Covenant EBITDA {_k(r['covenant_ebitda_k'])}. A Material Obligor Event, so "
                f"the loan of {_m(r['outstanding'])} leaves the borrowing base, taking "
                f"{_m(value)} off it. The fund's certificate still includes it.",
                owner="Lender", obligor=r["id"],
                sources=[s for s in r["sources"].values() if s][:2],
                clauses=[c for c in (clauses["event"], clauses["eligible"]) if c],
                handoff={"on": "confirmed", "role": "client", "client": "calderwood",
                         "title": f"Lender told: {r['name']} {test} over its covenant"}))
        if r["addbacks_flagged"]:
            readings = "; ".join(f"{x['name'].lower()} {x['leverage']:.2f}x" for x in r["readings"])
            items.append(_item(
                id=f"F-ravenglass-addbacks-{r['id']}", facility=FACILITY, check="Add-backs",
                title=f"{r['name']}: add-backs {r['addback_pct']:.0f}% of EBITDA against a "
                f"{t['cap_pct']:.0f}% cap",
                detail=f"Leverage on the maximum of {r['max_leverage']:.2f}x: {readings}. "
                "Whether each add-back falls under the cap on cost savings, synergies and "
                "restructuring is a reading of the Covenant EBITDA definition.",
                owner="Credit expert", obligor=r["id"],
                sources=[a["source"] for a in r["addback_items"] if a.get("source")],
                clauses=[c for c in (clauses["ebitda"],) if c]))
        if r["within_tolerance"] and r["leverage_difference"]:
            items.append(_item(
                id=f"F-ravenglass-rounding-{r['id']}", facility=FACILITY,
                check="Obligor covenants", rule_outcome="logged",
                rule_reason=f"Within the {t['tolerance_x']:.2f}x tolerance agreed for reported "
                "ratios; the covenant passes either way.",
                title=f"{r['name']}: fund reports {r['reported_leverage']:.2f}x, recomputed "
                f"{r['leverage']:.2f}x", detail="The fund's report truncates the ratio; the "
                "platform rounds it, as the agreement does.", obligor=r["id"]))
        if r["max_leverage_basis"].startswith("Waiver"):
            change = next(c for c in t["covenant_changes"] if c["obligor"] == r["id"])
            items.append(_item(
                id=f"F-ravenglass-waiver-{r['id']}", facility=FACILITY, check="Covenant terms",
                rule_outcome="logged",
                rule_reason="A waiver notified under Section 7.3 sets the level for this test "
                "date; the quote is found on its page. Both levels are on the record.",
                title=f"{r['name']}: maximum leverage {r['max_leverage']:.2f}x for Q1 under a "
                f"waiver, was {r['original_max_leverage']:.2f}x",
                detail=f"Leverage of {r['leverage']:.2f}x passes the waived level and would "
                f"fail the original. {change['by']}.", obligor=r["id"],
                sources=[change["source"]] if change["source"] else []))
    return items


RULE_SUGGESTIONS = {
    "F-ravenglass-financials": ("query", "Financials are missing, so only the borrower can fix "
                                "it: chase it and keep the loan out of the base."),
    "F-ravenglass-leverage": ("confirmed", "The recomputed ratio fails the covenant on clear "
                              "terms, so the lender is told."),
    "F-ravenglass-addbacks": ("expert", "The result turns on how the add-back cap is read, so a "
                              "credit expert decides."),
}


def triage(gateway: Any, items: list[dict[str, Any]], pending: Pending) -> None:
    open_items = [{"id": i["id"], "check": i["check"], "title": i["title"],
                   "detail": i["detail"]} for i in items if i["rule_outcome"] is None]
    reading = pending.run("suggest_triage", "Ravenglass findings",
                          lambda: steps.suggest_triage(gateway, open_items)) if open_items else None
    suggestions = {s.id: s for s in reading.suggestions} if reading else {}
    for item in items:
        if item["rule_outcome"]:
            item["suggested"] = {"outcome": "logged", "reason": item["rule_reason"], "by": "Rule"}
        elif item["id"] in suggestions:
            s = suggestions[item["id"]]
            item["suggested"] = {"outcome": s.outcome, "reason": s.reason, "by": "AI"}
        else:
            prefix = next(p for p in RULE_SUGGESTIONS if item["id"].startswith(p))
            outcome, reason = RULE_SUGGESTIONS[prefix]
            item["suggested"] = {"outcome": outcome, "by": "Rule", "reason": reason
                                 + (" Suggested by rule: the AI suggestion is pending recording."
                                    if reading is None else "")}


TOPICS = {
    "F-ravenglass-financials": "One obligor's quarterly financials not received; its loan is out "
    "of the borrowing base",
    "F-ravenglass-leverage": "One obligor's leverage over its covenant; its loan leaves the "
    "borrowing base",
    "F-ravenglass-addbacks": "One obligor's add-backs above the cap; whether leverage passes "
    "depends on how the cap is read",
    "F-ravenglass-rounding": "One obligor's reported leverage rounded differently, within "
    "tolerance",
    "F-ravenglass-waiver": "A waiver raises one obligor's leverage covenant for this quarter",
}
HEADINGS = ["Submissions", "Obligor covenants", "Borrowing base", "Open items"]


def pack_figures(t: dict[str, Any], items: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    bb = t["borrowing_base"]
    rows = {r["id"]: r for r in t["obligors"]}

    def fig(value: str, means: str, source: Any = None) -> dict[str, Any]:
        return {"value": value, "means": means, "source": source}

    breach = next((rows[i["obligor"]] for i in items
                   if i["id"].startswith("F-ravenglass-leverage")), None)
    addbacks = next((rows[i["obligor"]] for i in items
                     if i["id"].startswith("F-ravenglass-addbacks")), None)
    waived = next((rows[i["obligor"]] for i in items
                   if i["id"].startswith("F-ravenglass-waiver")), None)
    figures = {
        "open_items": fig(str(sum(i["suggested"]["outcome"] != "logged" for i in items)),
                          "findings that need someone to act"),
        "obligors": fig(str(len(rows)), "obligor loans in the facility"),
        "received": fig(str(t["received"]), "obligors whose Q1 financials arrived"),
        "excluded": fig(str(len(bb["excluded"])), "obligor loans out of the borrowing base"),
        "borrowing_base": fig(_usd(bb["borrowing_base"]), "borrowing base, recomputed",
                              t["clause_sources"]["base"]),
        "certificate_base": fig(_usd(bb["certificate"]["borrowing_base"]),
                                "borrowing base on the fund's certificate"),
        "difference": fig(_usd(bb["difference"]), "certificate above the recomputed base"),
        "availability": fig(_usd(bb["availability"]), "availability, recomputed"),
        "largest_obligor": fig(f"{bb['largest']['pct']:.2f}%", "largest obligor's share"),
        "obligor_limit": fig(f"{bb['single_limit_pct']}%", "single-obligor limit"),
    }
    if breach:
        figures |= {"breach_leverage": fig(f"{breach['leverage']:.2f}x",
                                           "the breaching obligor's leverage"),
                    "breach_max": fig(f"{breach['max_leverage']:.2f}x", "its covenant maximum")}
    if addbacks:
        worst = addbacks["readings"][-1]["leverage"] if addbacks["readings"] else 0
        figures |= {"addback_pct": fig(f"{addbacks['addback_pct']:.0f}%",
                                       "add-backs as a share of EBITDA"),
                    "addback_cap": fig(f"{t['cap_pct']:.0f}%", "cap on add-backs"),
                    "addback_leverage": fig(f"{addbacks['leverage']:.2f}x",
                                            "leverage as the obligor reported it"),
                    "addback_capped": fig(f"{worst:.2f}x", "leverage with every add-back capped")}
    if waived:
        figures |= {"waiver_from": fig(f"{waived['original_max_leverage']:.2f}x",
                                       "maximum leverage before the waiver"),
                    "waiver_to": fig(f"{waived['max_leverage']:.2f}x",
                                     "maximum leverage under the waiver")}
    return figures


def _facts(t: dict[str, Any], items: list[dict[str, Any]], subs: list[dict[str, Any]],
           figures: dict[str, Any], outcome_words: dict[str, str]) -> dict[str, Any]:
    mine = [s for s in subs if s["facility"] == FACILITY]
    kinds: dict[str, list[dict[str, Any]]] = {}
    for s in mine:
        kinds.setdefault(re.sub(r",.*$", "", s["label"]), []).append(s)
    return {
        "submissions": [{"document": label,
                         "status": "all received" if all(s["received"] for s in group)
                         else "not all received"} for label, group in kinds.items()],
        "findings": [{"topic": next(v for k, v in TOPICS.items() if i["id"].startswith(k)),
                      "outcome": outcome_words[i["suggested"]["outcome"]]} for i in items],
        "placeholders": {f"{{{{{k}}}}}": v["means"] for k, v in figures.items()},
    }


def _template_sections(figures: dict[str, Any]) -> tuple[str, list[dict[str, str]]]:
    summary = ("{{received}} of {{obligors}} obligors reported for Q1. {{excluded}} obligor loans "
               "are out of the borrowing base, which is {{borrowing_base}} against "
               "{{certificate_base}} on the fund's certificate.")
    sections = [
        {"heading": "Submissions", "text": "{{received}} of {{obligors}} obligors delivered Q1 "
         "financial statements and compliance certificates. The missing obligor has been chased "
         "and escalated, and its loan stays out of the borrowing base until they arrive."},
        {"heading": "Obligor covenants", "text": (
            "One obligor's leverage of {{breach_leverage}} is above its {{breach_max}} maximum: "
            "a Material Obligor Event, and the lender has been told. " if "breach_leverage" in
            figures else "") + ("One obligor's add-backs are {{addback_pct}} of EBITDA against "
                                "a {{addback_cap}} cap; leverage is {{addback_leverage}} as "
                                "reported and {{addback_capped}} with every add-back capped, so "
                                "a credit expert is reviewing it. " if "addback_pct" in figures
                                else "")
         + ("A waiver raised one obligor's maximum leverage from {{waiver_from}} to "
            "{{waiver_to}} for this quarter." if "waiver_from" in figures else "")},
        {"heading": "Borrowing base", "text": "The recomputed borrowing base is "
         "{{borrowing_base}}, {{difference}} below the fund's certificate, because the "
         "certificate keeps the excluded loans. Availability is {{availability}}. The largest "
         "obligor is {{largest_obligor}} of the eligible balance against a {{obligor_limit}} "
         "limit."},
        {"heading": "Open items", "text": "{{open_items}} findings need someone to act."},
    ]
    return summary, sections


def pack(gateway: Any, fac: dict[str, Any], t: dict[str, Any], items: list[dict[str, Any]],
         subs: list[dict[str, Any]], pending: Pending,
         outcome_words: dict[str, str]) -> dict[str, Any]:
    figures = pack_figures(t, items)
    facts = _facts(t, items, subs, figures, outcome_words)
    draft = pending.run("draft_pack", f"Lender pack · {fac['name']}",
                        lambda: steps.draft_pack(gateway, fac["name"], HEADINGS, facts))
    if draft is None:
        summary, sections = _template_sections(figures)
        ai = False
    else:
        summary = draft.summary
        sections = [{"heading": s.heading, "text": s.text} for s in draft.sections]
        ai = True
    placeholders = re.compile(r"\{\{(\w+)\}\}")
    texts = [summary, *(s["text"] for s in sections)]
    return {
        "facility": FACILITY,
        "summary": summary,
        "sections": sections,
        "figures": figures,
        "unknown_placeholders": sorted({m for x in texts for m in placeholders.findall(x)
                                        if m not in figures}),
        "numbers_in_text": sorted({m for x in texts for m in re.findall(
            r"(?<![\w{])\d[\d,.]*%?", placeholders.sub("", x))}),
        "ai": ai,
        "pending_recording": draft is None,
    }


def brief_section(gateway: Any, client: dict[str, Any], t: dict[str, Any],
                  items: list[dict[str, Any]], pending: Pending) -> tuple[dict[str, Any],
                                                                          dict[str, Any]]:
    """The facility's part of Calderwood's status-call brief: drafted by the model with
    placeholders when recorded, otherwise the facts as code writes them."""
    bb = t["borrowing_base"]
    figures = {
        "rvg_received": {"value": str(t["received"]), "means": "Ravenglass obligors reported",
                         "source": None},
        "rvg_obligors": {"value": str(len(t["obligors"])), "means": "Ravenglass obligors",
                         "source": None},
        "rvg_excluded_value": {"value": _usd(bb["bridged"]),
                               "means": "Ravenglass borrowing base value of excluded loans",
                               "source": None},
        "rvg_borrowing_base": {"value": _usd(bb["borrowing_base"]),
                               "means": "Ravenglass borrowing base, recomputed", "source": None},
    }
    rows = {r["id"]: r for r in t["obligors"]}
    missing = [i for i in items if i["id"].startswith("F-ravenglass-financials")]
    expert = [i for i in items if i["suggested"]["outcome"] == "expert"]
    confirmed = [i for i in items if i["suggested"]["outcome"] == "confirmed"]
    points = [
        "Ravenglass: {{rvg_received}} of {{rvg_obligors}} obligors reported for Q1"
        + (f"; {rows[missing[0]['obligor']]['name']}'s financials are missing and have been "
           "chased" if missing else ""),
        "Ravenglass: excluded loans take {{rvg_excluded_value}} off the borrowing base, which "
        "is {{rvg_borrowing_base}}; the fund's certificate still includes them",
    ]
    for n, item in enumerate(confirmed):
        r = rows[item["obligor"]]
        figures[f"rvg_breach_{n}"] = {"value": f"{r['leverage']:.2f}x", "source": None,
                                      "means": f"{r['name']} leverage"}
        figures[f"rvg_breach_max_{n}"] = {"value": f"{r['max_leverage']:.2f}x", "source": None,
                                          "means": f"{r['name']} maximum leverage"}
        points.append(f"Ravenglass: {r['name']}'s leverage of {{{{rvg_breach_{n}}}}} is over its "
                      f"{{{{rvg_breach_max_{n}}}}} maximum, so its loan is out of the base; the "
                      "lender has been told")
    for n, item in enumerate(expert):
        r = rows[item["obligor"]]
        figures[f"rvg_addbacks_{n}"] = {"value": f"{r['addback_pct']:.0f}%", "source": None,
                                        "means": f"{r['name']} add-backs as a share of EBITDA"}
        points.append(f"Ravenglass: {r['name']}'s add-backs of {{{{rvg_addbacks_{n}}}}} of "
                      "EBITDA are above the cap; whether leverage passes is with a credit expert")
    facts = {"points": points,
             "placeholders": {f"{{{{{k}}}}}": v["means"] for k, v in figures.items()}}
    draft = pending.run("draft_status_brief", f"Status-call brief · {client['name']} · Ravenglass",
                        lambda: steps.draft_status_brief(gateway, client["name"],
                                                         client["contact"]["name"],
                                                         ["Ravenglass Direct Lending Fund I"],
                                                         facts))
    if draft is None:
        section = {"heading": "Ravenglass Direct Lending Fund I", "points": points,
                   "by": "Template", "pending_recording": True}
    else:
        section = {"heading": "Ravenglass Direct Lending Fund I",
                   "points": [p for s in draft.sections for p in s.points], "by": "AI"}
    # The code-written facts, for the client's own summary (never the model's wording), and the
    # obligors whose financials are missing, for the brief's "Missing financials".
    section["facts"] = points
    section["missing_financials"] = [rows[i["obligor"]]["name"] for i in missing]
    pattern = re.compile(r"\{\{(\w+)\}\}")
    section["unknown_placeholders"] = sorted({m for p in section["points"]
                                              for m in pattern.findall(p) if m not in figures})
    section["numbers_in_text"] = sorted({m for p in section["points"] for m in re.findall(
        r"(?<![\w{])\d[\d,.]*%?", pattern.sub("", p))})
    return section, figures


# Headroom, QC and the workbook


def headroom_rows(t: dict[str, Any], history: list[tuple[str, float]], row: Any) -> list[
        dict[str, Any]]:
    bb = t["borrowing_base"]
    out = [row(FACILITY, "Availability", "Section 2.4", bb["availability"], 0, "min", "US$",
               [*history, ("May 2026", bb["availability"])], Decimal(10_000_000),
               note=f"Certificate shows {_usd(bb['certificate']['availability'])}; it keeps the "
               "excluded loans")]
    for r in t["obligors"]:
        if not r["received"]:
            continue
        if not r["leverage_passed"] or r["addbacks_flagged"] or r["max_leverage_basis"].startswith(
                "Waiver"):
            note = ""
            if r["addbacks_flagged"] and r["readings"]:
                note = f"{r['readings'][-1]['leverage']:.2f}x with every add-back capped: " \
                    "with an expert"
            elif r["max_leverage_basis"].startswith("Waiver"):
                note = f"Waived from {r['original_max_leverage']:.2f}x for Q1"
            out.append(row(FACILITY, f"Leverage, {r['name']}", "Obligor agreement",
                           r["leverage"], r["max_leverage"], "max", "x",
                           [("Q1 2026", r["leverage"])], note=note))
    out += [
        row(FACILITY, "Largest obligor share", "Section 1.1", bb["largest"]["pct"],
            bb["single_limit_pct"], "max", "%", [("May 2026", bb["largest"]["pct"])],
            Decimal(1), note=bb["largest"]["name"]),
        row(FACILITY, "Largest sector share", "Section 1.1", bb["largest_sector"]["pct"],
            bb["sector_limit_pct"], "max", "%", [("May 2026", bb["largest_sector"]["pct"])],
            Decimal(2), note=bb["largest_sector"]["sector"]),
    ]
    return out


def qc_values(t: dict[str, Any]) -> dict[str, Any]:
    bb = t["borrowing_base"]
    return {
        "Aggregate eligible balance": bb["eligible"],
        "Obligor loans excluded": len(bb["excluded"]),
        "Borrowing base": bb["borrowing_base"],
        "Availability": bb["availability"],
        "Largest obligor share": bb["largest"]["pct"],
        "Concentration excess": bb["excess_reduction"],
    }


def to_money(value: Any) -> int:
    return to_cents(str(value))
