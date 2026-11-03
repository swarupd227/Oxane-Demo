"""Run one monthly monitoring cycle across the lender's facilities, and save what the
workbench reads.

    python -m app.monitoring.cycle --mode record   (needs a model key)
    python -m app.monitoring.cycle --mode replay   (no network)

Four steps, as in the specification: collect, reconcile, test, then triage and report. The model
reads documents, maps new columns, suggests triage outcomes and drafts the pack's words. Every
number is computed here, by the engine, from figures whose quotes were found in their documents.
"""

import argparse
import csv
import json
import re
import sys
from datetime import date, datetime, timedelta
from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from engine.covenants import delinquency_ratio
from engine.monitoring import (
    CLOSED,
    TermVersion,
    charge_offs,
    duplicate_collateral,
    in_force,
    leverage,
    loan_to_value,
    pct,
    position_concentration,
    roll_forward,
    rolling_trigger,
    seasonal,
    stale_valuations,
    within_tolerance,
)
from engine.rules import load_ruleset
from engine.run import coerce_loan, run, to_cents
from openpyxl import load_workbook

from app.config import settings
from app.monitoring import steps
from app.pipeline.catalogue import PLATFORM_FIELDS
from app.pipeline.documents import PdfDocument, find_citation, normalise, read_pdf
from app.pipeline.gateway import AnthropicClient, Gateway
from app.pipeline.run import read_financials

RECORD_FILE = Path(__file__).parent / "portfolio.yaml"
HOLIDAYS = {date(2026, 5, 25), date(2026, 6, 19)}


@lru_cache
def record() -> dict[str, Any]:
    return yaml.safe_load(RECORD_FILE.read_text(encoding="utf-8"))


def facility(facility_id: str) -> dict[str, Any]:
    return next(item for item in record()["facilities"] if item["id"] == facility_id)


def cycle_path(relative: str) -> Path:
    """`pack/<file>` is the onboarding pack; `<facility>/<file>` is this cycle's submissions."""
    root = settings.deal_kit_output
    return root / relative if relative.startswith("pack/") else root / "cycle" / relative


def served_files() -> set[str]:
    """Every document a citation may point at, so the file endpoint serves nothing else."""
    names = {
        f"pack/{name}"
        for name in json.loads(
            (settings.pipeline_dir / "pack.json").read_text(encoding="utf-8")
        ).values()
    }
    for item in record()["facilities"]:
        folder = cycle_path(item["folder"])
        if folder.exists():
            names |= {f"{item['folder']}/{path.name}" for path in folder.iterdir()}
    return names


# Reading


def money(text: str) -> int:
    """Cents from a printed amount: US$1,234.56, (1,234.56) or 1,234."""
    found = re.search(r"\d[\d,]*(?:\.\d+)?", text)
    if found is None:
        raise ValueError(f"No amount in {text!r}")
    value = to_cents(found.group(0).replace(",", ""))
    negative = "(" in text[: found.start()] or text.strip().startswith(("-", "−"))
    return -value if negative else value


def usd(text: str) -> Decimal:
    """Dollars from a printed amount, with its unit: US$85 million, US$53,900 thousand, 1,420.0."""
    number = Decimal(re.findall(r"\d[\d,]*(?:\.\d+)?", text)[0].replace(",", ""))
    lowered = text.lower()
    if "million" in lowered or re.search(r"\d\s*m(?![a-z])", lowered):
        number *= 1_000_000
    elif "thousand" in lowered:
        number *= 1000
    return number


def pretty(iso: str) -> str:
    """An ISO date as an analyst writes it: 22 Jun 2026."""
    day = date.fromisoformat(iso)
    return f"{day.day} {day:%b %Y}"


def month_key(name: str) -> str:
    """'Apr 2025', 'April 2025' and 'April, 2025' all become 'apr 2025'."""
    match = re.search(r"([A-Za-z]{3})[A-Za-z]*,?\s+(\d{4})", name)
    return f"{match.group(1).lower()} {match.group(2)}" if match else name.lower()


def read_tape(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def light(row: dict[str, str]) -> dict[str, Any]:
    """What monitoring needs from a mapped row, typed, with money in cents."""
    return {
        "loan_id": row["loan_id"],
        "vin": row["vin"],
        "status": row["status"],
        "current_balance": to_cents(row.get("current_balance") or "0"),
        "days_past_due": int(row.get("days_past_due") or 0),
        "charge_off_amount": to_cents(row["charge_off_amount"])
        if row.get("charge_off_amount")
        else None,
        "dealer_name": row.get("dealer_name", ""),
        "obligor_state": row.get("obligor_state", ""),
        "vehicle": " ".join(
            filter(None, [row.get("model_year"), row.get("vehicle_make"), row.get("vehicle_model")])
        ),
        "origination_date": row.get("origination_date", ""),
    }


def mapped(rows: list[dict[str, str]], columns: dict[str, str]) -> list[dict[str, str]]:
    return [{columns[k]: v for k, v in row.items() if k in columns} for row in rows]


class Evidence:
    """Documents a figure may cite. A figure counts only if its quote is found and holds it."""

    def __init__(self) -> None:
        self.documents: dict[str, PdfDocument] = {}
        self.unverified: list[str] = []

    def add(self, relative: str) -> PdfDocument:
        if relative not in self.documents:
            self.documents[relative] = read_pdf(relative, cycle_path(relative))
        return self.documents[relative]

    def cite(self, relative: str, quote: str, label: str | None = None) -> dict[str, Any] | None:
        found = find_citation(self.documents, relative, quote)
        if found and label:
            found["label"] = label
        return found

    def figure(self, relative: str, figures: list[steps.Figure], name: str) -> dict[str, Any]:
        """The named figure, its value and its citation. Raises if the model did not give it."""
        wanted = name.lower()
        item = next((f for f in figures if normalise(f.name).lower() == wanted), None) or next(
            (f for f in figures if wanted in normalise(f.name).lower()), None
        )
        if item is None:
            raise ValueError(f"{name} was not read from {relative}")
        citation = self.cite(relative, item.quote)
        # The quote must print the figure itself, whatever currency or unit the value adds.
        number = re.search(r"\d[\d,]*(?:\.\d+)?", item.value)
        held = bool(number) and number.group(0) in normalise(item.quote)
        if citation is None or not held:
            self.unverified.append(f"{relative}: {name}")
        return {"value": item.value, "source": citation, "verified": bool(citation and held)}


# Collect


def business_days_after(day: date, count: int) -> date:
    while count:
        day += timedelta(days=1)
        if day.weekday() < 5 and day not in HOLIDAYS:
            count -= 1
    return day


def collect(as_of: date) -> list[dict[str, Any]]:
    policy = record()["chase_policy"]
    items = []
    for item in record()["submissions"]:
        due, received = item["due"], item["received"]
        late = received is None and as_of > due
        chase = []
        if late:
            first = business_days_after(due, policy["first"])
            escalate = business_days_after(due, policy["escalate"])
            sender = item.get("sender", "the sender")
            chase = [
                {
                    "at": first.isoformat(),
                    "action": "Reminder sent automatically",
                    "to": f"{item.get('contact', 'Reporting team')}, {sender}",
                    "text": f"The {item['label'].lower()} was due on {due:%d %B %Y} and has not "
                    "been received. Please send it today, or tell us when to expect it.",
                },
            ]
            if as_of >= escalate:
                chase.append(
                    {
                        "at": escalate.isoformat(),
                        "action": "Escalated automatically",
                        "to": f"Relationship manager at {sender}; copied to the lender",
                        "text": "Still not received one business day after the "
                        "reminder. The May borrowing base stays pending.",
                    }
                )
        items.append(
            {
                **{k: v for k, v in item.items() if k not in ("due", "received")},
                "due": due.isoformat(),
                "received": received.isoformat() if received else None,
                "status": "late"
                if late
                else "received"
                if received and received <= due
                else "received_late"
                if received
                else "awaited",
                "chase": chase,
            }
        )
    return items


def layout_changes(
    gateway: Gateway, bramble: dict[str, Any], header: list[str], rows: list[dict[str, str]]
) -> dict[str, Any]:
    """New columns are mapped from memory where possible and suggested by the model where not."""
    memory = json.loads((settings.pipeline_dir / "mapping.json").read_text("utf-8"))["columns"]
    new = [column for column in header if column not in memory]
    reading = steps.map_new_columns(
        gateway, new, memory, PLATFORM_FIELDS, [{k: row[k] for k in new} for row in rows[:5]]
    )
    used = set(memory.values())
    columns = []
    for suggestion in reading.columns:
        accepted = (
            suggestion.field in PLATFORM_FIELDS and suggestion.field not in used
            if suggestion.field
            else True
        )
        columns.append(
            {
                "column": suggestion.column,
                "field": suggestion.field if accepted else None,
                "reason": suggestion.reason,
                "values": sorted({row[suggestion.column] for row in rows}),
                "outcome": "Kept as an extra attribute"
                if not suggestion.field
                else "Mapped"
                if accepted
                else "Held: field already in use",
            }
        )
    return {
        "facility": bramble["id"],
        "file": bramble["tape"],
        "from_memory": len(header) - len(new),
        "columns_total": len(header),
        "new_columns": columns,
    }


# Reconcile


def reconcile_bramble(
    gateway: Gateway,
    evidence: Evidence,
    bramble: dict[str, Any],
    april_rows: list[dict[str, str]],
    may_rows: list[dict[str, str]],
) -> dict[str, Any]:
    report = f"bramble/{bramble['servicer_report']}"
    reading = steps.read_servicer_report(gateway, evidence.add(report))
    figures = {
        name: evidence.figure(report, reading.figures, name)
        for name in (
            "Pool balance at start of period",
            "Receivables purchased",
            "Principal collections",
            "Gross charge-offs",
            "Pool balance at end of period",
            "Interest received",
        )
    }
    # The report prints outflows in brackets; the roll-forward subtracts their size.
    collections = abs(money(figures["Principal collections"]["value"]))
    april, may = [light(r) for r in april_rows], [light(r) for r in may_rows]
    roll = roll_forward(april, may, collections)
    tolerance = to_cents(str(record()["tolerances"]["roll_forward_usd"]))
    by_id = {row["loan_id"]: row for row in april}
    reported = {item.loan_id: money(item.amount) for item in reading.charge_offs}
    offs = charge_offs(may, reported)
    may_by_id = {row["loan_id"]: row for row in may}
    schedule_quote = next(
        (i.loan_id for i in reading.charge_offs if i.loan_id in offs.only_in_report), None
    )
    trend = {f.name: f for f in reading.figures if f.name.lower().startswith("60+ day ratio")}
    return {
        "roll_forward": {
            "opening": roll.opening_cents / 100,
            "additions": roll.additions_cents / 100,
            "new_loans": roll.new_loans,
            "collections": roll.collections_cents / 100,
            "charge_offs": roll.charge_offs_cents / 100,
            "expected": roll.expected_cents / 100,
            "actual": roll.actual_cents / 100,
            "gap": roll.gap_cents / 100,
            "within_tolerance": abs(roll.gap_cents) <= tolerance,
            "sources": {
                "collections": figures["Principal collections"]["source"],
                "opening": figures["Pool balance at start of period"]["source"],
            },
            "servicer_closing": money(figures["Pool balance at end of period"]["value"]) / 100,
            "missing": [
                {
                    "loan_id": loan_id,
                    "april_balance": by_id[loan_id]["current_balance"] / 100,
                    "dealer": by_id[loan_id]["dealer_name"],
                    "state": by_id[loan_id]["obligor_state"],
                    "vehicle": by_id[loan_id]["vehicle"],
                }
                for loan_id in roll.missing_loan_ids
            ],
            "missing_april_balance": roll.missing_last_balance_cents / 100,
        },
        "charge_offs": {
            "tape": offs.tape_cents / 100,
            "report": offs.report_cents / 100,
            "difference": offs.difference_cents / 100,
            "source": figures["Gross charge-offs"]["source"],
            "schedule_source": evidence.cite(report, schedule_quote) if schedule_quote else None,
            "loans": [
                {
                    "loan_id": loan_id,
                    "report_amount": reported[loan_id] / 100,
                    "tape_status": may_by_id[loan_id]["status"],
                    "tape_balance": may_by_id[loan_id]["current_balance"] / 100,
                    "days_past_due": may_by_id[loan_id]["days_past_due"],
                }
                for loan_id in offs.only_in_report
                if loan_id in may_by_id
            ],
        },
        "interest": money(figures["Interest received"]["value"]) / 100,
        "delinquency_trend": {
            name.split(",")[-1].strip(): {
                "value": float(Decimal(item.value.rstrip("%"))),
                "source": evidence.cite(report, item.quote),
            }
            for name, item in trend.items()
        },
    }


# Terms in force


def terms_timeline(
    gateway: Gateway, evidence: Evidence, onboarding: dict[str, Any], period_end: date
) -> dict[str, Any]:
    terms = {term["name"]: term for term in onboarding["terms"]}
    pack = json.loads((settings.pipeline_dir / "pack.json").read_text("utf-8"))

    def onboarding_source(term: dict[str, Any]) -> dict[str, Any] | None:
        source = dict(term["source"]) if term.get("source") else None
        if source:
            source["document"] = f"pack/{pack[source['document']]}"
        return source

    amendment = "bramble/Bramble_Amendment_No_2.pdf"
    reading = steps.read_amendment(gateway, evidence.add(amendment))
    changes = {change.term.lower(): change for change in reading.changes}

    def change(*words: str) -> steps.TermChange:
        return next(c for name, c in changes.items() if all(w in name for w in words))

    # The amendment changes Schedule 2, row 2, which the onboarded rules hold as the dealer limit.
    limit_change = next(
        c
        for c in reading.changes
        if re.search(r"US\$[\d,]+", c.new_value) and re.search(r"limit|commitment", c.term, re.I)
    )
    dealer_change = next(
        c
        for c in reading.changes
        if c is not limit_change
        and ("concentration" in f"{c.term} {c.quote}".lower() or "schedule 2" in c.quote.lower())
    )
    signed = date.fromisoformat(onboarding_signing(terms))
    first_effective = date.fromisoformat(terms["Advance rate"]["effective_from"])
    rows = []
    for name, original, amended_1, amended_2 in (
        ("Facility limit", terms["Facility limit"]["value"], None, limit_change),
        (
            "Advance rate",
            terms["Advance rate"]["original_value"],
            terms["Advance rate"]["amended_value"],
            None,
        ),
        ("Dealer concentration limit", "5%", None, dealer_change),
    ):
        source = onboarding_source(terms.get(name) or terms["Concentration limits"])
        if name == "Advance rate" and terms[name].get("also_cited"):
            source = onboarding_source({"source": terms[name]["also_cited"][0]})
        versions = [
            {
                "label": "Credit Agreement",
                "effective_from": signed.isoformat(),
                "value": original,
                "source": source,
            }
        ]
        if amended_1:
            versions.append(
                {
                    "label": "Amendment No. 1",
                    "effective_from": first_effective.isoformat(),
                    "value": amended_1,
                    "source": onboarding_source(terms["Advance rate"]),
                }
            )
        if amended_2:
            versions.append(
                {
                    "label": "Amendment No. 2",
                    "effective_from": amended_2.effective_from,
                    "value": amended_2.new_value,
                    "clause": f"Amendment No. 2, {amended_2.clause}",
                    "source": evidence.cite(amendment, amended_2.quote),
                }
            )
        dated = [
            TermVersion(v["label"], date.fromisoformat(v["effective_from"]), v, "")
            for v in versions
        ]
        current = in_force(dated, period_end)
        june = in_force(dated, period_end + timedelta(days=30))
        rows.append(
            {
                "name": name,
                "versions": versions,
                "in_force": current.label,
                "value_in_force": current.values["value"],
                "next": june.label,
                "next_value": june.values["value"],
            }
        )
    return {
        "facility": "bramble",
        "period_end": period_end.isoformat(),
        "signed": reading.signed,
        "periods_note": reading.periods_note,
        "periods_source": evidence.cite(amendment, reading.periods_note),
        "terms": rows,
    }


def onboarding_signing(terms: dict[str, Any]) -> str:
    value = terms["Signing date"]["value"]
    for pattern in ("%d %b %Y", "%d %B %Y", "%B %d, %Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, pattern).date().isoformat()
        except ValueError:
            continue
    raise ValueError(f"Unreadable signing date: {value}")


# Test


def bramble_tests(
    gateway: Gateway,
    evidence: Evidence,
    bramble: dict[str, Any],
    may_rows: list[dict[str, str]],
    trend: dict[str, Any],
    onboarding_facts: dict[str, Any],
) -> dict[str, Any]:
    folder = cycle_path("bramble")
    ruleset = load_ruleset((settings.pipeline_dir / "ruleset.json").read_text("utf-8"))
    pool = [
        coerce_loan(row) for row in may_rows if row["status"] not in ("PAID_OFF", "REPURCHASED")
    ]
    outstanding = bramble["outstanding_advances_usd"] * 100
    result = run(
        pool, ruleset, date(2026, 5, 31), outstanding, dealer_aliases=bramble["dealer_aliases"]
    )
    sheet = load_workbook(folder / bramble["certificate"])["BBC Summary"]
    stated = {
        "eligible_pool": to_cents(str(sheet["B7"].value)),
        "borrowing_base": to_cents(str(sheet["B11"].value)),
        "availability": to_cents(str(sheet["B13"].value)),
    }
    limit = Decimal(record()["tolerances"]["certificate_usd"])
    checks = {
        name: within_tolerance(Decimal(stated[name]) / 100, Decimal(computed) / 100, limit)
        for name, computed in (
            ("eligible_pool", result.eligible_pool_cents),
            ("borrowing_base", result.borrowing_base_cents),
            ("availability", result.availability_cents),
        )
    }
    may_ratio = delinquency_ratio(
        [coerce_loan(r) for r in may_rows if r["status"] not in ("PAID_OFF", "REPURCHASED")]
    )
    covenants = onboarding_facts["covenants"]
    months = [
        (month, Decimal(str(trend[month]["value"])))
        for month in ("March 2026", "April 2026")
        if month in trend
    ] + [("May 2026", may_ratio)]
    trigger = rolling_trigger(
        months,
        Decimal(str(covenants["delinquency_trigger_pct"])),
        warning_band=Decimal(str(record()["tolerances"]["trigger_warning_pts"])),
    )

    # Financial covenants: the statements are spread by code, the certificate is read by the model.
    statements = evidence.add(f"bramble/{bramble['financial_statements']}")
    figures = read_financials(statements)
    certificate_doc = f"bramble/{bramble['compliance_certificate']}"
    compliance = steps.read_compliance(gateway, evidence.add(certificate_doc))
    worth = (
        figures["total_equity"]
        - figures["goodwill"]
        - figures["intangibles"]
        - figures["related_party_receivables"]
    )
    cap = covenants["subordinated_debt_cap"] // 1000
    maximum = Decimal(str(covenants["max_leverage_ratio"]))
    reported_line = next(
        f for f in compliance.figures if "leverage ratio" == normalise(f.name).lower()
    )
    reported = Decimal(re.findall(r"\d+\.\d+", reported_line.value)[0])
    off_sheet = [item for item in compliance.contingent_obligations if not item.on_balance_sheet]
    added = int(sum(usd(item.amount) for item in off_sheet) / 1000)
    as_reported = leverage(
        figures["total_liabilities"], worth, figures["subordinated_debt"], cap, maximum
    )
    with_guarantees = leverage(
        figures["total_liabilities"],
        worth,
        figures["subordinated_debt"],
        cap,
        maximum,
        added_liabilities=added,
    )
    agreement = f"pack/{_pack_file('credit_agreement')}"
    evidence.add(agreement)
    return {
        "borrowing_base": {
            "system": {
                "eligible_pool": result.eligible_pool_cents / 100,
                "excess": result.excess_cents / 100,
                "borrowing_base": result.borrowing_base_cents / 100,
                "availability": result.availability_cents / 100,
                "advance_rate_pct": float(result.advance_rate_pct),
                "provisional": result.provisional,
            },
            "certificate": {k: v / 100 for k, v in stated.items()},
            "differences": {k: float(c.difference) for k, c in checks.items()},
            "within_tolerance": all(c.within for c in checks.values()),
            "tolerance": float(limit),
            "sunrise": {
                "share_pct": float(result.concentrations["C2"].share_pct),
                "excess": result.concentrations["C2"].excess_cents / 100,
            },
        },
        "delinquency": _trigger_view(trigger, "Section 7.1", None),
        "leverage": {
            "reported": float(reported),
            "recomputed": float(as_reported.ratio),
            "with_guarantees": float(with_guarantees.ratio),
            "maximum": float(maximum),
            "tangible_net_worth_k": worth,
            "carve_out_k": as_reported.carve_out,
            "total_liabilities_k": figures["total_liabilities"],
            "guarantees_k": added,
            "guarantees": [
                {
                    "description": item.description,
                    "amount": item.amount,
                    "source": evidence.cite(certificate_doc, item.quote),
                }
                for item in off_sheet
            ],
            "reported_source": evidence.cite(certificate_doc, reported_line.quote),
            "clauses": [
                c
                for c in (
                    evidence.cite(
                        agreement,
                        '"Total Liabilities" means',
                        "Credit Agreement 1.1, "
                        "Total Liabilities: balance sheet liabilities under GAAP",
                    ),
                    evidence.cite(
                        agreement, '"Leverage Ratio" means', "Credit Agreement 1.1, Leverage Ratio"
                    ),
                )
                if c
            ],
        },
        "liquidity_k": figures["unrestricted_cash"],
    }


@lru_cache
def _pack_file(document: str) -> str:
    return json.loads((settings.pipeline_dir / "pack.json").read_text("utf-8"))[document]


def _trigger_view(trigger: Any, clause: str, source: dict[str, Any] | None) -> dict[str, Any]:
    return {
        "monthly": [{"month": month, "value": float(value)} for month, value in trigger.monthly],
        "average": float(trigger.average),
        "limit": float(trigger.limit),
        "direction": trigger.direction,
        "breached": trigger.breached,
        "early_warning": trigger.early_warning,
        "headroom": float(trigger.headroom),
        "next_month_breaches_beyond": float(trigger.next_month_breaches_beyond)
        if trigger.next_month_breaches_beyond is not None
        else None,
        "clause": clause,
        "source": source,
    }


def northmoor_tests(
    gateway: Gateway, evidence: Evidence, northmoor: dict[str, Any]
) -> dict[str, Any]:
    folder = cycle_path("northmoor")
    terms = northmoor["terms"]
    tapes = {
        month: mapped(read_tape(folder / name), northmoor["mapping"])
        for month, name in northmoor["tapes"].items()
    }
    monthly = [
        (
            f"{month} 2026",
            delinquency_ratio(
                [
                    coerce_like(row)
                    for row in rows
                    if row["status"] not in ("PAID_OFF", "REPURCHASED")
                ]
            ),
        )
        for month, rows in tapes.items()
    ]
    agreement = f"northmoor/{northmoor['agreement']}"
    evidence.add(agreement)
    trigger = rolling_trigger(
        monthly,
        Decimal(str(terms["delinquency_trigger_pct"])),
        warning_band=Decimal(str(record()["tolerances"]["trigger_warning_pts"])),
    )
    spreads, history = [], []
    for month, name in northmoor["servicer_reports"].items():
        relative = f"northmoor/{name}"
        reading = steps.read_excess_spread(gateway, evidence.add(relative))
        parts = {
            key: money(evidence.figure(relative, reading.figures, key)["value"])
            for key in (
                "Interest collections",
                "Servicing fee",
                "Interest on advances",
                "Charge-offs net of recoveries",
                "Ending principal balance",
            )
        }
        stated = evidence.figure(relative, reading.figures, "Excess spread")
        # Recompute the spread from its parts; the stated figure is only a cross-check.
        net = (
            parts["Interest collections"]
            - abs(parts["Servicing fee"])
            - abs(parts["Interest on advances"])
            - abs(parts["Charge-offs net of recoveries"])
        )
        value = pct(net * 12, parts["Ending principal balance"])
        spreads.append(
            {
                "month": f"{month} 2026",
                "value": float(value),
                "stated": stated["value"],
                "source": stated["source"],
            }
        )
        if reading.collections_history:
            history = [
                {"month": f.name, "value_k": int(money(f.value) // 100)}
                for f in reading.collections_history
            ]
    spread_trigger = rolling_trigger(
        [(s["month"], Decimal(str(s["value"]))) for s in spreads],
        Decimal(str(terms["excess_spread_floor_pct"])),
        "min",
    )

    # May collections, worked out from the tapes while the servicer report is outstanding.
    collected = {}
    for month, before, after in (
        ("April", tapes["March"], tapes["April"]),
        ("May", tapes["April"], tapes["May"]),
    ):
        prior = {r["loan_id"]: r for r in (light(x) for x in before) if r["status"] not in CLOSED}
        now = {r["loan_id"]: light(r) for r in after}
        collected[month] = sum(
            row["current_balance"] - now[loan]["current_balance"]
            for loan, row in prior.items()
            if loan in now and now[loan]["status"] != "CHARGED_OFF"
        )
    by_month = {month_key(item["month"]): item["value_k"] for item in history}
    dip = seasonal(collected["May"], collected["April"], by_month["may 2025"], by_month["apr 2025"])
    return {
        "delinquency": _trigger_view(
            trigger,
            terms["delinquency_clause"],
            evidence.cite(agreement, terms["delinquency_quote"]),
        ),
        "excess_spread": {
            **_trigger_view(
                spread_trigger,
                terms["excess_spread_clause"],
                evidence.cite(agreement, terms["excess_spread_quote"]),
            ),
            "months_available": len(spreads),
            "months_required": 3,
            "pending": "May servicer report not received",
        },
        "excess_spread_months": spreads,
        "collections": {
            "april": collected["April"] / 100,
            "may": collected["May"] / 100,
            "change": float(dip.change),
            "last_year_change": float(dip.last_year_change),
            "seasonal": dip.within,
            "history": history,
        },
        "borrowing_base": {"status": "pending", "reason": "May servicer report not received"},
        "tapes": {month: len(rows) for month, rows in tapes.items()},
    }


def coerce_like(row: dict[str, str]) -> dict[str, Any]:
    return {
        "status": row["status"],
        "current_balance": to_cents(row["current_balance"] or "0"),
        "days_past_due": int(row["days_past_due"] or 0),
    }


def kestrel_tests(gateway: Gateway, evidence: Evidence, kestrel: dict[str, Any]) -> dict[str, Any]:
    terms = kestrel["terms"]
    names = [
        f"kestrel/{kestrel[k]}"
        for k in ("nav_report", "valuation_report", "compliance_certificate")
    ]
    documents = [evidence.add(name) for name in names]
    agreement = f"kestrel/{kestrel['agreement']}"
    evidence.add(agreement)
    reading = steps.read_nav_pack(gateway, documents)

    def figure(name: str) -> dict[str, Any]:
        for relative in names:
            item = evidence.figure(relative, reading.figures, name)
            if item["verified"]:
                evidence.unverified = [u for u in evidence.unverified if not u.endswith(name)]
                return item
        return item

    nav = figure("Net asset value")
    drawn = figure("Loans outstanding")
    # The NAV pack prints US$ millions.
    nav_cents = int(usd(nav["value"] + " million") * 100)
    drawn_cents = int(usd(drawn["value"] + " million") * 100)
    reported_ltv = figure("Loan-to-Value Ratio")
    limit = Decimal(terms["max_ltv_pct"])
    positions = [
        {
            "name": p.name,
            "value_cents": int(usd(p.fair_value + " million") * 100),
            "valued": date.fromisoformat(p.valuation_date),
            "source": evidence.cite(names[1], p.quote),
        }
        for p in reading.positions
    ]
    calc_date = kestrel["calculation_date"]
    stale = stale_valuations(positions, calc_date, terms["valuation_max_age_days"])
    events = [e for e in reading.events if not e.reflected_in_valuation]
    markdown = int(sum(usd(e.amount) for e in events) * 100)
    base = loan_to_value(drawn_cents, nav_cents, limit)
    adjusted = loan_to_value(drawn_cents, nav_cents, limit, adjustments_cents=-markdown)
    concentration = position_concentration(
        positions,
        nav_cents,
        Decimal(terms["max_single_position_pct"]),
        Decimal(terms["max_top_five_pct"]),
    )
    return {
        "nav": nav_cents / 100,
        "drawn": drawn_cents / 100,
        "nav_source": nav["source"],
        "drawn_source": drawn["source"],
        "ltv": {
            "reported": float(base.ratio_pct),
            "with_markdown": float(adjusted.ratio_pct),
            "limit": float(limit),
            "stated": reported_ltv["value"],
            "markdown": markdown / 100,
            "headroom_pts": float(limit - adjusted.ratio_pct),
            "clause": terms["ltv_clause"],
            "clauses": [
                c
                for c in (
                    evidence.cite(
                        agreement,
                        '"Net Asset Value" means',
                        "NAV Facility Agreement 1.1, Net Asset Value",
                    ),
                    evidence.cite(
                        agreement,
                        '"Valuation Event" means',
                        "NAV Facility Agreement 1.1, Valuation Event",
                    ),
                )
                if c
            ],
            "events": [
                {
                    "position": e.position,
                    "amount": float(usd(e.amount)),
                    "date": e.date,
                    "source": evidence.cite(names[1], e.quote),
                }
                for e in events
            ],
        },
        "valuations": {
            "max_age_days": terms["valuation_max_age_days"],
            "clause": terms["valuation_clause"],
            "calculation_date": calc_date.isoformat(),
            "positions": len(positions),
            "stale": [
                {
                    "name": s.name,
                    "valued": s.valued.isoformat(),
                    "age_days": s.age_days,
                    "value": next(p["value_cents"] for p in positions if p["name"] == s.name) / 100,
                    "source": next(p["source"] for p in positions if p["name"] == s.name),
                }
                for s in stale
            ],
        },
        "concentration": {
            "largest": concentration.largest_name,
            "largest_pct": float(concentration.largest_pct),
            "top_five_pct": float(concentration.top_five_pct),
            "largest_limit": float(concentration.largest_limit_pct),
            "top_five_limit": float(concentration.top_five_limit_pct),
            "passed": concentration.passed,
            "clause": terms["concentration_clause"],
        },
        "positions": [
            {"name": p["name"], "value": p["value_cents"] / 100, "valued": p["valued"].isoformat()}
            for p in positions
        ],
    }


def collateral(
    bramble_rows: list[dict[str, str]], northmoor_rows: list[dict[str, str]]
) -> dict[str, Any]:
    tapes = {
        "bramble": [light(r) for r in bramble_rows],
        "northmoor": [light(r) for r in northmoor_rows],
    }
    by_key = {(facility, row["loan_id"]): row for facility, rows in tapes.items() for row in rows}
    within, across = duplicate_collateral(tapes)

    def view(shared: Any) -> dict[str, Any]:
        return {
            "vin": shared.vin,
            "holdings": [
                {
                    "facility": facility,
                    **{
                        k: by_key[(facility, loan)][k]
                        for k in (
                            "loan_id",
                            "status",
                            "dealer_name",
                            "obligor_state",
                            "vehicle",
                            "origination_date",
                            "days_past_due",
                        )
                    },
                    "current_balance": by_key[(facility, loan)]["current_balance"] / 100,
                }
                for facility, loan in shared.holdings
            ],
        }

    return {
        "checked": {
            f: sum(1 for r in rows if r["status"] not in CLOSED) for f, rows in tapes.items()
        },
        "within": [view(s) for s in within],
        "across": [view(s) for s in across],
        "scope": "Calderwood Bank's own facilities only",
    }


# Triage and report


def findings(
    subs: list[dict[str, Any]],
    layout: dict[str, Any],
    recon: dict[str, Any],
    timeline: dict[str, Any],
    tests: dict[str, Any],
    shared: dict[str, Any],
) -> list[dict[str, Any]]:
    """Every check that failed or nearly failed, plus the items logged within tolerance.

    Rules decide `logged` first. Everything else gets a model suggestion and an analyst decision.
    """
    b, n, k = tests["bramble"], tests["northmoor"], tests["kestrel"]
    items: list[dict[str, Any]] = []

    def add(**item: Any) -> None:
        items.append({"rule_outcome": None, "evidence": [], "sources": [], "clauses": [], **item})

    for sub in subs:
        if sub["status"] == "late":
            add(
                id="F-late-servicer-report",
                facility=sub["facility"],
                check="Submissions",
                title=f"{sub['label']} not received",
                detail=f"Due {pretty(sub['due'])}. Reminder sent {pretty(sub['chase'][0]['at'])}"
                + (f", escalated {pretty(sub['chase'][1]['at'])}" if len(sub["chase"]) > 1 else "")
                + ". The borrowing base stays pending until it arrives.",
                owner="Servicer",
                sender=sub.get("sender"),
            )
    roll = recon["roll_forward"]
    if not roll["within_tolerance"]:
        add(
            id="F-roll-forward",
            facility="bramble",
            check="Reconciliation",
            title=f"{len(roll['missing'])} loans missing from the May tape",
            detail=f"The roll-forward expects US${roll['expected']:,.2f}; the tape totals "
            f"US${roll['actual']:,.2f}. The gap of US${roll['gap']:,.2f} matches "
            f"{len(roll['missing'])} loans on the April tape that the May tape does not list, "
            "not even as paid off or charged off.",
            amount=roll["gap"],
            loans=[m["loan_id"] for m in roll["missing"]],
            owner="Servicer",
            sources=[roll["sources"]["collections"]],
        )
    offs = recon["charge_offs"]
    if offs["loans"]:
        add(
            id="F-charge-offs",
            facility="bramble",
            check="Reconciliation",
            title=f"Charge-offs US${offs['difference']:,.2f} higher in the servicer report",
            detail=f"{len(offs['loans'])} loans are charged off in the servicer report but live "
            "on the tape.",
            amount=offs["difference"],
            loans=[item["loan_id"] for item in offs["loans"]],
            owner="Servicer",
            sources=[s for s in (offs["source"], offs["schedule_source"]) if s],
        )
    for term in timeline["terms"]:
        if term["next"] != term["in_force"]:
            add(
                id=f"F-terms-{term['name'].lower().replace(' ', '-')}",
                facility="bramble",
                check="Terms version",
                rule_outcome="logged",
                rule_reason="Takes effect after the period end. May is tested on the terms then "
                "in force; both versions are on the timeline.",
                title=f"{term['name']}: {term['next_value']} from "
                f"{pretty(term['versions'][-1]['effective_from'])}",
                detail=f"May uses {term['value_in_force']} ({term['in_force']}).",
                sources=[term["versions"][-1]["source"]] if term["versions"][-1]["source"] else [],
            )
    bb = b["borrowing_base"]
    if bb["within_tolerance"] and any(bb["differences"].values()):
        add(
            id="F-certificate-rounding",
            facility="bramble",
            check="Borrowing base",
            rule_outcome="logged",
            rule_reason=f"Within the US${bb['tolerance']:,.0f} tolerance agreed for certificates.",
            title=f"Certificate eligible pool US${bb['differences']['eligible_pool']:,.2f} "
            "above the recomputed figure",
            detail="Recomputed borrowing base agrees with the certificate within tolerance.",
        )
    for column in layout["new_columns"]:
        add(
            id=f"F-layout-{column['column'].lower()}",
            facility="bramble",
            check="Layout change",
            rule_outcome="logged",
            rule_reason="New column with no platform field; the other "
            f"{layout['from_memory']} columns mapped from memory.",
            title=f"New tape column {column['column']}",
            detail=column["reason"],
        )
    nd = n["delinquency"]
    if nd["breached"] or nd["early_warning"]:
        add(
            id="F-northmoor-delinquency",
            facility="northmoor",
            check="Triggers",
            title=f"60+ day delinquency average {nd['average']:.2f}% against a "
            f"{nd['limit']:.1f}% trigger",
            detail="Monthly "
            + ", ".join(f"{m['value']:.2f}%" for m in nd["monthly"])
            + f". June breaches the trigger above {nd['next_month_breaches_beyond']:.2f}%.",
            owner="Lender",
            sources=[nd["source"]] if nd["source"] else [],
        )
    collections = n["collections"]
    if collections["change"] < 0:
        add(
            id="F-northmoor-collections",
            facility="northmoor",
            check="Collections",
            rule_outcome="logged" if collections["seasonal"] else None,
            rule_reason=f"Down {abs(collections['change']) * 100:.1f}% on April; last May fell "
            f"{abs(collections['last_year_change']) * 100:.1f}%, so within the "
            "seasonal range.",
            title="May principal collections below April",
            detail="Worked out from the tapes while the servicer report is outstanding.",
        )
    lev = b["leverage"]
    if lev["with_guarantees"] > lev["maximum"] >= lev["recomputed"]:
        add(
            id="F-bramble-leverage",
            facility="bramble",
            check="Financial covenants",
            title=f"Leverage {lev['with_guarantees']:.2f}x if the guarantee counts, against "
            f"{lev['maximum']:.2f}x",
            detail=f"Reported {lev['reported']:.2f}x, recomputed {lev['recomputed']:.2f}x on the "
            f"balance sheet. The certificate discloses a US${lev['guarantees_k']:,} thousand "
            "guarantee kept off the balance sheet.",
            owner="Credit expert",
            sources=[g["source"] for g in lev["guarantees"] if g["source"]],
            clauses=lev["clauses"],
        )
    for shared_vin in shared["across"]:
        add(
            id="F-shared-vin",
            facility="bramble,northmoor",
            check="Duplicate collateral",
            title=f"VIN {shared_vin['vin']} pledged in two facilities",
            detail=" and ".join(
                f"{h['facility'].title()} loan {h['loan_id']}" for h in shared_vin["holdings"]
            )
            + " are secured by the same car.",
            owner="Lender",
        )
    ltv = k["ltv"]
    if ltv["events"]:
        add(
            id="F-kestrel-markdown",
            facility="kestrel",
            check="NAV loan-to-value",
            title=f"Loan-to-value {ltv['reported']:.1f}% on reported NAV, "
            f"{ltv['with_markdown']:.1f}% "
            "with the post-quarter markdown",
            detail="; ".join(
                f"{e['position']} marked down US${e['amount'] / 1e6:,.0f}m on {pretty(e['date'])}"
                for e in ltv["events"]
            )
            + ". The Manager has not declared a "
            "Valuation Event.",
            owner="Credit expert",
            sources=[e["source"] for e in ltv["events"] if e["source"]],
            clauses=ltv["clauses"],
        )
    for stale in k["valuations"]["stale"]:
        add(
            id="F-kestrel-stale-valuation",
            facility="kestrel",
            check="Valuation freshness",
            title=f"{stale['name']} last valued {pretty(stale['valued'])}",
            detail=f"{stale['age_days']} days before the calculation date, against a "
            f"{k['valuations']['max_age_days']}-day limit.",
            owner="Manager",
            sources=[stale["source"]] if stale["source"] else [],
        )
    return items


def triage(gateway: Gateway, items: list[dict[str, Any]]) -> None:
    open_items = [
        {"id": i["id"], "check": i["check"], "title": i["title"], "detail": i["detail"]}
        for i in items
        if i["rule_outcome"] is None
    ]
    reading = steps.suggest_triage(gateway, open_items)
    suggestions = {s.id: s for s in reading.suggestions}
    for item in items:
        if item["rule_outcome"]:
            item["suggested"] = {"outcome": "logged", "reason": item["rule_reason"], "by": "Rule"}
        elif item["id"] in suggestions:
            s = suggestions[item["id"]]
            item["suggested"] = {"outcome": s.outcome, "reason": s.reason, "by": "AI"}
        else:
            item["suggested"] = {
                "outcome": "query",
                "reason": "No suggestion was returned, so it defaults to a query.",
                "by": "Rule",
            }


# Each finding as the pack drafter sees it: a topic with no figures, so every number in the
# text has to come from a placeholder.
TOPICS = {
    "F-late-servicer-report": "May servicer report not received; reminder and escalation sent",
    "F-roll-forward": "Loans missing from the May tape, found by the roll-forward",
    "F-charge-offs": "Charge-offs higher in the servicer report than on the tape",
    "F-terms-facility-limit": "Amendment No. 2 raises the facility limit from June",
    "F-terms-dealer-concentration-limit": "Amendment No. 2 raises the dealer limit from June",
    "F-certificate-rounding": "Rounding difference in the borrowing base certificate",
    "F-layout-": "New column on the May tape with no platform field",
    "F-northmoor-delinquency": "60+ day delinquency close to its three-month trigger",
    "F-northmoor-collections": "May collections below April, in line with last May",
    "F-bramble-leverage": "Leverage over its maximum only if an affiliate guarantee counts",
    "F-shared-vin": "One car securing a loan in both Bramble and Northmoor",
    "F-kestrel-markdown": "Loan-to-value with and without a post-quarter markdown",
    "F-kestrel-stale-valuation": "One investment's valuation older than the agreement allows",
}
OUTCOME_WORDS = {
    "logged": "logged within tolerance, no alert",
    "query": "query to the sender",
    "confirmed": "confirmed issue, lender told",
    "expert": "sent for expert review",
}


def topic(item: dict[str, Any]) -> str:
    return next(text for prefix, text in TOPICS.items() if item["id"].startswith(prefix))


PACK_HEADINGS = {
    "bramble": [
        "Submissions",
        "Reconciliation",
        "Borrowing base and terms",
        "Triggers and covenants",
        "Collateral",
        "Open items",
    ],
    "northmoor": [
        "Submissions",
        "Triggers",
        "Borrowing base and collections",
        "Collateral",
        "Open items",
    ],
    "kestrel": ["Submissions", "Loan-to-value", "Valuations and concentration", "Open items"],
}


def pack_figures(
    facility_id: str, tests: dict[str, Any], recon: dict[str, Any], items: list[dict[str, Any]]
) -> dict[str, dict[str, Any]]:
    """Each figure the pack may quote: its value as code formats it, what it means, its source."""

    def dollars(value: float) -> str:
        return f"US${value:,.2f}"

    def fig(value: str, means: str, source: dict[str, Any] | None = None) -> dict[str, Any]:
        return {"value": value, "means": means, "source": source}

    mine = [i for i in items if facility_id in i["facility"].split(",")]
    figures = {
        "open_items": fig(
            str(sum(i["suggested"]["outcome"] != "logged" for i in mine)),
            "findings that need someone to act",
        )
    }
    if facility_id == "bramble":
        b, roll, offs = tests["bramble"], recon["roll_forward"], recon["charge_offs"]
        bb, lev = b["borrowing_base"], b["leverage"]
        figures |= {
            "expected": fig(dollars(roll["expected"]), "pool balance the roll-forward expects"),
            "actual": fig(dollars(roll["actual"]), "pool balance on the May tape"),
            "gap": fig(dollars(roll["gap"]), "roll-forward gap"),
            "missing": fig(str(len(roll["missing"])), "loans missing from the May tape"),
            "charge_off_difference": fig(
                dollars(offs["difference"]),
                "charge-offs in the report above the tape",
                offs["source"],
            ),
            "charge_off_loans": fig(
                str(len(offs["loans"])), "loans charged off in the report but live on the tape"
            ),
            "borrowing_base": fig(
                dollars(bb["system"]["borrowing_base"]), "May borrowing base, recomputed"
            ),
            "availability": fig(dollars(bb["system"]["availability"]), "availability, recomputed"),
            "certificate_difference": fig(
                dollars(bb["differences"]["borrowing_base"]),
                "certificate borrowing base above the recomputed one",
            ),
            "tolerance": fig(f"US${bb['tolerance']:,.0f}", "tolerance agreed for certificates"),
            "delinquency_average": fig(
                f"{b['delinquency']['average']:.2f}%", "three-month 60+ day delinquency average"
            ),
            "delinquency_limit": fig(f"{b['delinquency']['limit']:.1f}%", "delinquency trigger"),
            "leverage_reported": fig(
                f"{lev['reported']:.2f}x", "leverage the borrower reported", lev["reported_source"]
            ),
            "leverage_with_guarantee": fig(
                f"{lev['with_guarantees']:.2f}x", "leverage if the affiliate guarantee counts"
            ),
            "leverage_limit": fig(f"{lev['maximum']:.2f}x", "maximum leverage"),
            "guarantee": fig(
                f"US${lev['guarantees_k'] / 1000:,.1f}m",
                "affiliate guarantee kept off the balance sheet",
                lev["guarantees"][0]["source"] if lev["guarantees"] else None,
            ),
        }
    elif facility_id == "northmoor":
        n = tests["northmoor"]
        figures |= {
            "delinquency_average": fig(
                f"{n['delinquency']['average']:.2f}%",
                "three-month 60+ day delinquency average",
                n["delinquency"]["source"],
            ),
            "delinquency_limit": fig(
                f"{n['delinquency']['limit']:.1f}%",
                "delinquency trigger: an amortisation event above it",
            ),
            "june_threshold": fig(
                f"{n['delinquency']['next_month_breaches_beyond']:.2f}%",
                "June delinquency above which the trigger is breached",
            ),
            "excess_spread": fig(
                f"{n['excess_spread']['average']:.2f}%", "excess spread average, March and April"
            ),
            "excess_spread_floor": fig(
                f"{n['excess_spread']['limit']:.1f}%", "excess spread floor"
            ),
            "collections_change": fig(
                f"{abs(n['collections']['change']) * 100:.1f}%",
                "fall in May principal collections against April",
            ),
            "last_year_change": fig(
                f"{abs(n['collections']['last_year_change']) * 100:.1f}%",
                "fall in principal collections last May",
            ),
        }
    else:
        k = tests["kestrel"]
        stale = k["valuations"]["stale"]
        figures |= {
            "ltv_reported": fig(
                f"{k['ltv']['reported']:.1f}%", "loan-to-value on reported NAV", k["nav_source"]
            ),
            "ltv_with_markdown": fig(
                f"{k['ltv']['with_markdown']:.1f}%",
                "loan-to-value counting the post-quarter markdown",
            ),
            "ltv_limit": fig(f"{k['ltv']['limit']:.0f}%", "maximum loan-to-value"),
            "markdown": fig(f"US${k['ltv']['markdown'] / 1e6:,.0f}m", "post-quarter markdown"),
            "stale_days": fig(
                str(stale[0]["age_days"]) if stale else "0", "age of the stale valuation, in days"
            ),
            "valuation_limit": fig(
                str(k["valuations"]["max_age_days"]), "valuation age limit, in days"
            ),
            "largest_position": fig(
                f"{k['concentration']['largest_pct']:.1f}%", "largest investment, share of NAV"
            ),
            "top_five": fig(
                f"{k['concentration']['top_five_pct']:.1f}%",
                "five largest investments, share of NAV",
            ),
        }
    return figures


def lender_pack(
    gateway: Gateway,
    facility_id: str,
    name: str,
    tests: dict[str, Any],
    recon: dict[str, Any],
    items: list[dict[str, Any]],
    subs: list[dict[str, Any]],
) -> dict[str, Any]:
    figures = pack_figures(facility_id, tests, recon, items)
    facts: dict[str, Any] = {
        "submissions": [
            {"document": s["label"], "status": s["status"].replace("_", " ")}
            for s in subs
            if s["facility"] == facility_id
        ],
        "findings": [
            {"topic": topic(i), "outcome": OUTCOME_WORDS[i["suggested"]["outcome"]]}
            for i in items
            if facility_id in i["facility"].split(",")
        ],
        "placeholders": {f"{{{{{key}}}}}": item["means"] for key, item in figures.items()},
    }
    if facility_id == "northmoor":
        facts["borrowing_base"] = "Pending until the May servicer report arrives."
    if facility_id == "kestrel":
        facts["concentration"] = "Both concentration tests pass."
    draft = steps.draft_pack(gateway, name, PACK_HEADINGS[facility_id], facts)
    placeholders = re.compile(r"\{\{(\w+)\}\}")
    texts = [draft.summary, *(section.text for section in draft.sections)]
    unknown = sorted({m for t in texts for m in placeholders.findall(t) if m not in figures})
    numbers = sorted(
        {m for t in texts for m in re.findall(r"(?<![\w{])\d[\d,.]*%?", placeholders.sub("", t))}
    )
    return {
        "facility": facility_id,
        "summary": draft.summary,
        "sections": [{"heading": s.heading, "text": s.text} for s in draft.sections],
        "figures": figures,
        "unknown_placeholders": unknown,
        "numbers_in_text": numbers,
    }


def run_cycle(gateway: Gateway, out_dir: Path) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    meta = record()
    as_of, period_end = meta["cycle"]["as_of"], meta["cycle"]["period_end"]
    onboarding = json.loads((settings.pipeline_dir / "workbench.json").read_text("utf-8"))
    facts = json.loads((settings.pipeline_dir / "facts.json").read_text("utf-8"))
    memory = json.loads((settings.pipeline_dir / "mapping.json").read_text("utf-8"))["columns"]
    bramble, northmoor, kestrel = (facility(f) for f in ("bramble", "northmoor", "kestrel"))
    evidence = Evidence()

    # Collect
    subs = collect(as_of)
    may_raw = read_tape(cycle_path("bramble") / bramble["tape"])
    layout = layout_changes(gateway, bramble, list(may_raw[0]), may_raw)
    may_rows = mapped(may_raw, memory)
    april_rows = mapped(
        read_tape(settings.deal_kit_output / "pack" / _pack_file("loan_tape")), memory
    )
    northmoor_may = mapped(
        read_tape(cycle_path("northmoor") / northmoor["tapes"]["May"]), northmoor["mapping"]
    )

    # Reconcile
    recon = reconcile_bramble(gateway, evidence, bramble, april_rows, may_rows)
    timeline = terms_timeline(gateway, evidence, onboarding, period_end)

    # Test
    tests = {
        "bramble": bramble_tests(
            gateway, evidence, bramble, may_rows, recon["delinquency_trend"], facts
        ),
        "northmoor": northmoor_tests(gateway, evidence, northmoor),
        "kestrel": kestrel_tests(gateway, evidence, kestrel),
    }
    shared = collateral(may_rows, northmoor_may)

    # Triage and report
    items = findings(subs, layout, recon, timeline, tests, shared)
    triage(gateway, items)
    packs = [
        lender_pack(gateway, f["id"], f["name"], tests, recon, items, subs)
        for f in meta["facilities"]
    ]

    usage = {
        "model": gateway.model,
        "calls": len(gateway.usage),
        "input_tokens": sum(u.input_tokens for u in gateway.usage),
        "output_tokens": sum(u.output_tokens for u in gateway.usage),
        "cost_usd": gateway.total_cost_usd(),
        "model_seconds": round(sum(u.seconds for u in gateway.usage)),
    }
    result = {
        "cycle": meta["cycle"] | {"as_of": as_of.isoformat(), "period_end": period_end.isoformat()},
        "lender": meta["lender"],
        "desk": meta["desk"],
        "tolerances": meta["tolerances"],
        "facilities": [
            {
                k: v
                for k, v in f.items()
                if k
                in (
                    "id",
                    "name",
                    "borrower",
                    "type",
                    "asset_class",
                    "role",
                    "size",
                    "size_note",
                    "reporting",
                )
            }
            for f in meta["facilities"]
        ],
        "submissions": subs,
        "layout": layout,
        "reconciliation": recon,
        "terms": timeline,
        "tests": tests,
        "collateral": shared,
        "findings": items,
        "packs": packs,
        "unverified": evidence.unverified,
        "usage": usage,
    }
    (out_dir / "cycle.json").write_text(
        json.dumps(result, indent=1, default=str) + "\n", encoding="utf-8"
    )
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["record", "replay", "live"], required=True)
    mode = parser.parse_args().mode
    gateway = Gateway(
        mode=mode,
        fixtures=settings.cycle_llm_fixtures,
        client_factory=lambda: AnthropicClient(settings.llm_provider),
    )
    result = run_cycle(gateway, settings.cycle_dir)
    if mode == "record":
        gateway.prune()
    print(
        json.dumps(
            {
                "findings": len(result["findings"]),
                "unverified": result["unverified"],
                **result["usage"],
            },
            indent=1,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
