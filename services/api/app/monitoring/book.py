"""The rest of the desk's book: the facilities with nothing planted this cycle.

Each reports summary figures only. Code works out every ratio, test, headroom, deadline and
report status here from the cycle kit's files: the facility record, three periods of reported
figures, the inbox log and the desk log. No model reads any of it.
"""

import csv
import json
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

from engine.monitoring import pct, rolling_trigger

from app.monitoring.alerts import _row

FILES = {
    "facilities": "Book_Facilities.json",
    "summaries": "Book_Summaries.csv",
    "inbox": "Book_Inbox_May_2026.csv",
    "log": "Book_Desk_Log.csv",
}
ABF = ("auto", "consumer", "equipment", "trade")


def _read(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _d(text: str) -> Decimal:
    return Decimal(text or "0")


def _size(commitment: int) -> str:
    return f"US${commitment / 1e6:,.0f}m"


def tests(facility: dict[str, Any], periods: list[dict[str, str]]) -> list[dict[str, Any]]:
    """Every contract test for one facility, as headroom rows, from its reported figures."""
    fid, kind, terms = facility["id"], facility["kind"], facility["terms"]
    clauses = terms["clauses"]
    labels = [p["period"] for p in periods]
    rows: list[dict[str, Any]] = []
    if kind in ABF:
        advance = Decimal(terms["advance_rate_pct"])
        dq = [(p["period"], pct(_d(p["dq60_balance"]), _d(p["pool_balance"]))) for p in periods]
        trigger = rolling_trigger(dq, Decimal(str(terms["dq60_trigger_pct"])))
        spread = [
            (p["period"], pct(_d(p["excess_spread_amount"]) * 12, _d(p["pool_balance"])))
            for p in periods
        ]
        floor = rolling_trigger(spread, Decimal(str(terms["excess_spread_floor_pct"])), "min")
        availability = [
            (p["period"], float(min(_d(p["eligible_balance"]) * advance / 100,
                                    Decimal(facility["commitment_usd"])) - _d(p["drawn"])))
            for p in periods
        ]
        rows += [
            _row(fid, "60+ day delinquency, three-month average", clauses["dq60"],
                 float(trigger.average), float(trigger.limit), "max", "%",
                 [(label, float(v)) for label, v in dq]),
            _row(fid, "Excess spread, three-month average", clauses["excess_spread"],
                 float(floor.average), float(floor.limit), "min", "%",
                 [(label, float(v)) for label, v in spread]),
            _row(fid, "Availability", clauses["availability"], availability[-1][1], 0, "min",
                 "US$", availability),
        ]
    elif kind == "subscription":
        advance = Decimal(terms["advance_rate_pct"])
        base = [_d(p["eligible_uncalled"]) * advance / 100 for p in periods]
        coverage = [(label, float((b / _d(p["drawn"])).quantize(Decimal("0.01"))))
                    for label, b, p in zip(labels, base, periods, strict=True)]
        availability = [
            (label, float(min(b, Decimal(facility["commitment_usd"])) - _d(p["drawn"])))
            for label, b, p in zip(labels, base, periods, strict=True)
        ]
        rows += [
            _row(fid, "Coverage ratio", clauses["coverage"], coverage[-1][1],
                 terms["min_coverage_x"], "min", "x", coverage, Decimal("0.25")),
            _row(fid, "Availability", clauses["availability"], availability[-1][1], 0, "min",
                 "US$", availability),
        ]
    elif kind == "nav":
        ltv = [(p["period"], float(pct(_d(p["drawn"]), _d(p["nav"])))) for p in periods]
        largest = [(p["period"], float(pct(_d(p["largest_position"]), _d(p["nav"]))))
                   for p in periods]
        rows += [
            _row(fid, "Loan-to-value", clauses["ltv"], ltv[-1][1], terms["max_ltv_pct"], "max",
                 "%", ltv, Decimal(3)),
            _row(fid, "Largest investment", clauses["concentration"], largest[-1][1],
                 terms["max_single_position_pct"], "max", "%", largest, Decimal(1)),
        ]
    else:
        advance = Decimal(terms["advance_rate_pct"])
        limit = Decimal(str(terms["ccc_limit_pct"]))
        ccc = [(p["period"], float(pct(_d(p["ccc_par"]), _d(p["par"])))) for p in periods]
        was = [(p["period"], float((_d(p["spread_income"]) / _d(p["par"]) * 10000)
                                   .quantize(Decimal("1")))) for p in periods]
        availability = []
        for p in periods:
            excess = max(Decimal(0), _d(p["ccc_par"]) - _d(p["par"]) * limit / 100)
            base = (_d(p["par"]) - excess) * advance / 100
            availability.append((p["period"], float(
                min(base, Decimal(facility["commitment_usd"])) - _d(p["drawn"]))))
        rows += [
            _row(fid, "CCC share", clauses["ccc"], ccc[-1][1], float(limit), "max", "%", ccc),
            _row(fid, "Weighted average spread", clauses["was"], was[-1][1],
                 terms["min_was_bps"], "min", "bps", was, Decimal(10)),
            _row(fid, "Availability", clauses["availability"], availability[-1][1], 0, "min",
                 "US$", availability),
        ]
    return rows


def _report(entries: list[dict[str, str]], levels: int) -> dict[str, Any]:
    prepared = next((e for e in entries if e["event"] == "prepared"), None)
    approvals = [{"level": int(e["level"]), "by": e["by"], "at": e["at"]}
                 for e in entries if e["event"] == "approved"]
    done = (1 if prepared else 0) + len(approvals)
    status = "released" if done == levels else "in_review" if prepared else "preparing"
    return {
        "status": status,
        "levels": levels,
        "done": done,
        "prepared": {"by": prepared["by"], "at": prepared["at"]} if prepared else None,
        "approvals": approvals,
        "released_at": approvals[-1]["at"] if status == "released" else None,
    }


def build(meta: dict[str, Any], folder: Path, as_of: date,
          business_days_after: Any) -> dict[str, Any]:
    """The book as the workbench shows it: one summary per facility, the files each owed, and
    a headroom row for every contract test."""
    if not (folder / FILES["facilities"]).exists():
        return {"facilities": [], "submissions": [], "headroom": []}
    record = json.loads((folder / FILES["facilities"]).read_text(encoding="utf-8"))
    summaries, inbox, log = (_read(folder / FILES[name]) for name in ("summaries", "inbox", "log"))
    clients = {c["id"]: c for c in meta["clients"]}
    days = meta["internal_deadline_days"]
    facilities, submissions, headroom = [], [], []
    for facility in record:
        fid = facility["id"]
        client = clients[facility["client"]]
        periods = [p for p in summaries if p["facility"] == fid]
        rows = tests(facility, periods)
        headroom += rows
        owed = []
        for item in (i for i in inbox if i["facility"] == fid):
            due, received = date.fromisoformat(item["due"]), date.fromisoformat(item["received"])
            internal = business_days_after(due, days)
            owed.append({
                "facility": fid,
                "label": item["label"],
                "file": item["file"],
                "channel": item["channel"],
                "client": client["id"],
                "due": item["due"],
                "received": item["received"],
                "internal_deadline": internal.isoformat(),
                "deadline_status": "met" if received <= internal
                else "missed" if as_of > internal else "at_risk",
                "status": "received" if received <= due else "received_late",
                "reused": None,
                "chase": [],
            })
        submissions += owed
        main = rows[0]
        latest = periods[-1]
        facilities.append({
            "id": fid,
            "name": facility["name"],
            "borrower": facility["borrower"],
            "client": client["id"],
            "client_name": client["name"],
            "ai_permitted": client["ai_permitted"],
            "type": facility["type"],
            "asset_class": facility["asset_class"],
            "role": facility["role"],
            "size": _size(facility["commitment_usd"]),
            "commitment": facility["commitment_usd"],
            "drawn": int(_d(latest["drawn"])),
            "reporting": facility["reporting"],
            "period": latest["period"],
            "analyst": facility["analyst"],
            "documents": {"received": len(owed), "total": len(owed), "late": 0},
            "tests": [{k: r[k] for k in ("test", "clause", "value", "limit", "unit", "direction",
                                         "headroom", "passed", "early_warning", "trend")}
                      for r in rows],
            "trend": {"label": main["test"], "unit": main["unit"], "limit": main["limit"],
                      "direction": main["direction"], "series": main["series"]},
            "report": _report([e for e in log if e["facility"] == fid],
                              len(client["approval_levels"])),
        })
    return {"facilities": facilities, "submissions": submissions, "headroom": headroom}
