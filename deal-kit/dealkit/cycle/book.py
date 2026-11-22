"""The rest of the desk's book: twenty facilities with nothing planted.

Each one reports summary figures only (pool, eligible balance, 60+ day balance, NAV, par and so
on), so the four worked facilities sit among ordinary ones. The workbench works out every ratio,
test, headroom and status from these files. Nothing here goes into the answer key, and the
figures are drawn well inside each limit, so no test fails or nears its limit.

Four files, all from the book's own seed:

- Book_Facilities.json: the facility record set at onboarding (terms, reporting, analyst)
- Book_Summaries.csv: three periods of reported figures per facility
- Book_Inbox_May_2026.csv: what each facility owed this cycle and when it arrived
- Book_Desk_Log.csv: who prepared and approved each facility's report before the demo date
"""

import csv
import json
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any

import numpy as np

FILES = {
    "facilities": "Book_Facilities.json",
    "summaries": "Book_Summaries.csv",
    "inbox": "Book_Inbox_May_2026.csv",
    "log": "Book_Desk_Log.csv",
}
MONTHS = [("Mar 2026", "2026-03-31"), ("Apr 2026", "2026-04-30"), ("May 2026", "2026-05-31")]
QUARTERS = [("Q3 2025", "2025-09-30"), ("Q4 2025", "2025-12-31"), ("Q1 2026", "2026-03-31")]
KINDS = {
    "auto": ("Auto loan warehouse", "Auto ABF"),
    "consumer": ("Consumer loan warehouse", "Consumer ABF"),
    "equipment": ("Equipment finance warehouse", "Equipment ABF"),
    "trade": ("Receivables facility", "Trade receivables"),
    "subscription": ("Subscription line", "Fund finance"),
    "nav": ("NAV facility", "Fund finance"),
    "clo": ("CLO warehouse", "CLO / BSL"),
}
SUMMARY_COLUMNS = [
    "facility", "period", "period_end", "pool_balance", "eligible_balance", "dq60_balance",
    "excess_spread_amount", "drawn", "nav", "largest_position", "uncalled_commitments",
    "eligible_uncalled", "par", "ccc_par", "spread_income",
]
HOLIDAYS = {date(2026, 5, 25), date(2026, 6, 19)}


def _business(day: date, step: int) -> date:
    """`step` business days after (or before, if negative) the given day."""
    direction = 1 if step >= 0 else -1
    while step:
        day += timedelta(days=direction)
        if day.weekday() < 5 and day not in HOLIDAYS:
            step -= direction
    return day


def _usd(value: float) -> int:
    return int(round(value))


def _terms(kind: str, rng: np.random.Generator) -> dict[str, Any]:
    if kind in ("auto", "consumer", "equipment", "trade"):
        return {
            "advance_rate_pct": int(rng.choice([80, 85, 88, 90])),
            "dq60_trigger_pct": float(rng.choice([4.5, 5.0, 6.0, 7.0])),
            "excess_spread_floor_pct": float(rng.choice([2.0, 2.5, 3.0])),
            "clauses": {"dq60": "Section 7.1(a)", "excess_spread": "Section 7.1(b)",
                        "availability": "Section 2.3"},
        }
    if kind == "subscription":
        return {"advance_rate_pct": 90, "min_coverage_x": 1.5,
                "clauses": {"coverage": "Section 6.1", "availability": "Section 2.4"}}
    if kind == "nav":
        return {"max_ltv_pct": int(rng.choice([25, 30, 35])),
                "max_single_position_pct": int(rng.choice([15, 20])),
                "clauses": {"ltv": "Section 7.1", "concentration": "Section 6.3"}}
    return {"advance_rate_pct": int(rng.choice([65, 70])), "ccc_limit_pct": 7.5,
            "min_was_bps": int(rng.choice([300, 325])),
            "clauses": {"ccc": "Section 1.1", "was": "Section 6.2", "availability": "Section 2.3"}}


def _series(
    kind: str, commitment: float, terms: dict[str, Any], rng: np.random.Generator
) -> list[dict[str, Any]]:
    """Three periods of reported figures, each comfortably inside its limits."""
    rows = []
    if kind in ("auto", "consumer", "equipment", "trade"):
        advance = terms["advance_rate_pct"] / 100
        pool = commitment * rng.uniform(0.95, 1.25) / advance
        dq = terms["dq60_trigger_pct"] * rng.uniform(0.35, 0.6)
        spread = terms["excess_spread_floor_pct"] + rng.uniform(2.0, 4.5)
        utilisation = rng.uniform(0.62, 0.8)
        for _ in MONTHS:
            pool *= rng.uniform(0.985, 1.025)
            eligible = pool * rng.uniform(0.94, 0.975)
            dq_month = max(0.2, dq + rng.uniform(-0.15, 0.15))
            spread_month = spread + rng.uniform(-0.3, 0.3)
            rows.append({
                "pool_balance": _usd(pool),
                "eligible_balance": _usd(eligible),
                "dq60_balance": _usd(pool * dq_month / 100),
                "excess_spread_amount": _usd(pool * spread_month / 100 / 12),
                "drawn": _usd(min(eligible * advance, commitment) * utilisation),
            })
    elif kind == "subscription":
        uncalled = commitment * rng.uniform(2.4, 3.2)
        drawn = commitment * rng.uniform(0.45, 0.6)
        for _ in MONTHS:
            uncalled *= rng.uniform(0.97, 1.0)
            drawn *= rng.uniform(0.97, 1.04)
            rows.append({
                "uncalled_commitments": _usd(uncalled),
                "eligible_uncalled": _usd(uncalled * rng.uniform(0.86, 0.92)),
                "drawn": _usd(drawn),
            })
    elif kind == "nav":
        ltv = terms["max_ltv_pct"] * rng.uniform(0.5, 0.7)
        nav = commitment * rng.uniform(3.0, 4.5)
        share = terms["max_single_position_pct"] * rng.uniform(0.45, 0.7)
        for _ in QUARTERS:
            nav *= rng.uniform(0.99, 1.03)
            ltv_q = ltv + rng.uniform(-0.6, 0.6)
            rows.append({
                "nav": _usd(nav),
                "drawn": _usd(nav * ltv_q / 100),
                "largest_position": _usd(nav * (share + rng.uniform(-0.5, 0.5)) / 100),
            })
    else:
        advance = terms["advance_rate_pct"] / 100
        par = commitment * rng.uniform(1.15, 1.35) / advance
        ccc = rng.uniform(2.0, 5.2)
        was = terms["min_was_bps"] + rng.uniform(45, 90)
        utilisation = rng.uniform(0.6, 0.78)
        for _ in MONTHS:
            par *= rng.uniform(0.99, 1.03)
            rows.append({
                "par": _usd(par),
                "ccc_par": _usd(par * (ccc + rng.uniform(-0.4, 0.4)) / 100),
                "spread_income": _usd(par * (was + rng.uniform(-6, 6)) / 10000),
                "drawn": _usd(min(par * advance, commitment) * utilisation),
            })
    return rows


def _owed(kind: str, prefix: str) -> list[tuple[str, str, str]]:
    """What a facility of this kind sends each cycle: label, file and channel."""
    if kind in ("auto", "consumer", "equipment"):
        return [("Loan tape, May", f"{prefix}_Loan_Tape_2026-05.csv", "SFTP"),
                ("Servicer report, May", f"{prefix}_Servicer_Report_May_2026.pdf", "Email"),
                ("Borrowing base certificate, May", f"{prefix}_BBC_May_2026.xlsx", "Upload")]
    if kind == "trade":
        return [("Receivables ageing, May", f"{prefix}_Ageing_2026-05.xlsx", "Upload"),
                ("Borrowing base certificate, May", f"{prefix}_BBC_May_2026.xlsx", "Email")]
    if kind == "subscription":
        return [("Investor register, May", f"{prefix}_Investor_Register_2026-05.xlsx",
                 "Data room"),
                ("Borrowing base certificate, May", f"{prefix}_BBC_May_2026.pdf", "Email")]
    if kind == "nav":
        return [("Q1 NAV report", f"{prefix}_Q1_2026_NAV_Report.pdf", "Data room"),
                ("Q1 compliance certificate", f"{prefix}_Q1_2026_Compliance_Certificate.pdf",
                 "Email")]
    return [("Collateral report, May", f"{prefix}_Collateral_Report_2026-05-29.xlsx", "SFTP"),
            ("Bid prices, 29 May", f"{prefix}_Prices_2026-05-29.csv", "API")]


def _at(day: date, rng: np.random.Generator) -> datetime:
    minutes = int(rng.integers(9 * 60, 16 * 60))
    return datetime.combine(day, time(minutes // 60, minutes % 60))


def _later(at: datetime, rng: np.random.Generator) -> datetime:
    """A working time 40 minutes to a day and a half after the last step."""
    then = at + timedelta(minutes=int(rng.integers(40, 900)))
    if then.hour >= 18 or then.date() != at.date():
        then = _at(_business(at.date(), 1), rng)
    return then


def build_book(cycle: dict[str, Any], folder: Path) -> dict[str, Any]:
    spec = cycle["book"]
    rng = np.random.default_rng(spec["seed"])
    as_of = cycle["demo_date"]
    analysts, reviewers = spec["analysts"], spec["reviewers"]
    record, summaries, inbox, log = [], [], [], []
    for index, (fid, name, client, kind, size_m, role) in enumerate(spec["facilities"]):
        commitment = size_m * 1_000_000
        terms = _terms(kind, rng)
        kind_type, asset_class = KINDS[kind]
        prefix = name.split()[0][:3].upper()
        quarterly = kind == "nav"
        owed = _owed(kind, prefix)
        analyst = analysts[index % len(analysts)]
        record.append({
            "id": fid,
            "name": name,
            "borrower": f"{name} LLC" if client == "calderwood" else f"{name} Ltd",
            "client": client,
            "kind": kind,
            "type": kind_type,
            "asset_class": asset_class,
            "role": role,
            "commitment_usd": commitment,
            "reporting": "Quarterly" if quarterly else "Monthly",
            "analyst": analyst,
            "terms": terms,
        })
        periods = QUARTERS if quarterly else MONTHS
        for (label, end), figures in zip(periods, _series(kind, commitment, terms, rng),
                                         strict=True):
            summaries.append({"facility": fid, "period": label, "period_end": end, **figures})

        # Monthly files fall due between 10 and 22 June; quarterly ones on 30 May.
        if quarterly:
            due = date(2026, 5, 29)
        else:
            due = date(2026, 6, int(rng.choice([10, 12, 15, 16, 17, 18, 22])))
        last = due
        for label, file, channel in owed:
            if label.startswith("Bid prices"):
                file_due = received = date(2026, 5, 29)
            else:
                file_due = due
                early = int(rng.integers(0, 4))
                received = _business(due, -early)
                # One file in eight arrives a business day after it was due.
                if rng.uniform() < 0.125:
                    received = _business(due, 1)
            last = max(last, received)
            inbox.append({"facility": fid, "label": label, "file": file,
                          "due": file_due.isoformat(), "received": received.isoformat(),
                          "channel": channel})

        # The desk log before the demo date: prepared a business day after the last file, then
        # each approval level, a different person each time.
        prepared = _business(last, 1)
        if prepared >= as_of:
            continue
        at = _at(prepared, rng)
        log.append({"facility": fid, "event": "prepared", "level": 1, "by": analyst,
                    "at": at.isoformat()})
        levels = [2, 3] if client == "thornbury" else [2]
        others = [p for p in analysts if p != analyst]
        signers = {2: str(rng.choice([reviewers[0], *others[:2]])), 3: reviewers[1]}
        for level in levels:
            at = _later(at, rng)
            if at.date() >= as_of or rng.uniform() < 0.15:
                break
            log.append({"facility": fid, "event": "approved", "level": level,
                        "by": signers[level], "at": at.isoformat()})

    folder.mkdir(parents=True, exist_ok=True)
    (folder / FILES["facilities"]).write_text(json.dumps(record, indent=1) + "\n",
                                              encoding="utf-8")
    for name, rows, columns in (
        ("summaries", summaries, SUMMARY_COLUMNS),
        ("inbox", inbox, ["facility", "label", "file", "due", "received", "channel"]),
        ("log", log, ["facility", "event", "level", "by", "at"]),
    ):
        with (folder / FILES[name]).open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=columns, lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)
    return {"facilities": len(record), "files": len(inbox)}
