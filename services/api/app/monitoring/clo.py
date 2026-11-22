"""Larkspur, Thornbury Bank's CLO warehouse: loaded, validated and tested by code alone.

Thornbury does not permit AI, so nothing here calls a model. The collateral report and the price
file are structured, and the stored mapping for Thornbury's layouts reads them. Ratings use
Thornbury's master field, the lower of Moody's and S&P, which overrides the platform default.
"""

import csv
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

from engine.clo import (
    borrowing_base,
    compare_positions,
    early_warnings,
    notch,
    par_roll,
)
from engine.run import to_cents
from openpyxl import load_workbook

from app.monitoring import validate as validation


def _read_positions(path: Path, mapping: dict[str, str]) -> tuple[list[dict[str, Any]],
                                                                  list[dict[str, Any]], list[str]]:
    book = load_workbook(path, read_only=True)
    sheet = book["Positions"]
    rows = list(sheet.iter_rows(values_only=True))
    header = [str(h) for h in rows[0]]
    positions = []
    for line, values in enumerate(rows[1:], start=2):
        raw = dict(zip(header, values, strict=True))
        item = {mapping[k]: ("" if v is None else str(v)) for k, v in raw.items() if k in mapping}
        item["sheet_row"] = line
        positions.append(item)
    trades = []
    if "Trades" in book.sheetnames:
        for values in list(book["Trades"].iter_rows(values_only=True))[1:]:
            trades.append({"trade_date": values[0], "direction": values[1], "loanx": values[2],
                           "issuer": values[3], "facility": values[4],
                           "par_cents": int(values[5]) * 100, "price": float(values[6])})
    return positions, trades, header


def _read_prices(path: Path, mapping: dict[str, str]) -> dict[str, dict[str, Any]]:
    with path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    return {
        row["LoanX_ID"]: {**{mapping[k]: v for k, v in row.items() if k in mapping},
                          "file_row": index}
        for index, row in enumerate(rows, start=2)
    }


def _typed(position: dict[str, Any]) -> dict[str, Any]:
    return {
        **position,
        "par_cents": to_cents(position["par"]),
        "spread_bps": int(position["spread_bps"]),
        "maturity": position["maturity"],
    }


def basis_for(client: dict[str, Any]) -> tuple[str, dict[str, Any] | None]:
    override = next((o for o in client.get("master_field_overrides", [])
                     if o["field"] == "rating_for_tests"), None)
    return (override["override"] if override else "moodys"), override


def larkspur_tests(record: dict[str, Any], client: dict[str, Any], folder: Path,
                   evidence: Any) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """The facility's tests and its validation reports. No model is called."""
    facility = next(f for f in record["facilities"] if f["id"] == "larkspur")
    terms = facility["terms"]
    basis, override = basis_for(client)
    loaded: dict[str, dict[str, Any]] = {}
    reports = []
    for month in ("April", "May"):
        positions, trades, header = _read_positions(folder / facility["positions"][month],
                                                    facility["mapping"])
        prices = _read_prices(folder / facility["prices"][month], facility["price_mapping"])
        joined = [{**p, "bid": prices.get(p["loanx"], {}).get("bid", "")} for p in positions]
        report, rows = validation.run_feed(
            record, "larkspur", facility["positions"][month],
            folder / facility["positions"][month], "clo_positions", joined,
        )
        report["month"] = month
        report["price_file"] = facility["prices"][month]
        report["columns"] = header
        if month == "May":
            reports.append(report)
        loaded[month] = {"positions": [_typed(r) for r in rows], "prices": prices,
                         "trades": trades}
    april, may = loaded["April"], loaded["May"]
    bids = {k: Decimal(v["bid"]) for k, v in may["prices"].items()}
    prior_bids = {k: Decimal(v["bid"]) for k, v in april["prices"].items()}
    commitment, drawn = terms["commitment_usd"] * 100, terms["drawn_usd"] * 100
    limit, rate = Decimal(str(terms["ccc_limit_pct"])), Decimal(str(terms["advance_rate_pct"]))
    result = borrowing_base(may["positions"], bids, limit, rate, commitment, drawn, basis)
    before = borrowing_base(april["positions"], prior_bids, limit, rate, commitment, drawn, basis)
    default = borrowing_base(may["positions"], bids, limit, rate, commitment, drawn, "moodys")
    changes = compare_positions(april["positions"], may["positions"], may["trades"])
    links = {c.new_loanx: c.old_loanx for c in changes.relinked}
    ratings, moves = early_warnings(april["positions"], may["positions"], prior_bids, bids, links,
                                    Decimal(str(terms["price_move_alert_pts"])), basis)
    roll = par_roll(april["positions"], may["positions"], may["trades"])
    agreement = f"larkspur/{facility['agreement']}"
    evidence.add(agreement)
    ccc_source = evidence.cite(agreement, terms["ccc_quote"], "Credit Agreement 1.1, CCC Excess")
    clauses = [c for c in (
        ccc_source,
        evidence.cite(agreement, terms["adjustment_quote"],
                      "Credit Agreement 1.1, CCC Excess Adjustment"),
        evidence.cite(agreement, terms["base_quote"], "Credit Agreement 1.1, Borrowing Base"),
    ) if c]
    warning_source = evidence.cite(agreement, terms["warning_quote"],
                                   "Credit Agreement 6.5, Early warning")
    by_old = {p["loanx"]: p for p in april["positions"]}
    excess_ids = {p.loanx for p in result.excess}
    view_positions = []
    for p in may["positions"]:
        old = by_old.get(links.get(p["loanx"], p["loanx"]))
        found = notch(p["moodys"], p["sp"], basis)
        view_positions.append({
            "loanx": p["loanx"], "cusip": p["cusip"], "issuer": p["issuer"],
            "facility": p["facility"], "par": p["par_cents"] / 100,
            "spread_bps": p["spread_bps"], "maturity": p["maturity"], "moodys": p["moodys"],
            "sp": p["sp"], "industry": p["industry"],
            "ccc": p["loanx"] in result.ccc_positions,
            "in_excess": p["loanx"] in excess_ids,
            "bid": float(bids[p["loanx"]]),
            "prior_bid": float(prior_bids[old["loanx"]]) if old else None,
            "prior_rating": [old["moodys"], old["sp"]] if old else None,
            "notch": found,
            "sheet_row": p["sheet_row"],
            "price_row": may["prices"][p["loanx"]]["file_row"],
        })

    def money(cents: int) -> float:
        return cents / 100

    tests = {
        "basis": basis,
        "override": override,
        "determination_date": facility["determination_date"].isoformat()
        if isinstance(facility["determination_date"], date) else facility["determination_date"],
        "positions_file": facility["positions"]["May"],
        "prices_file": facility["prices"]["May"],
        "positions": view_positions,
        "borrowing_base": {
            "total_par": money(result.total_par_cents),
            "ccc_par": money(result.ccc_par_cents),
            "ccc_pct": float(result.ccc_pct),
            "ccc_limit_pct": float(limit),
            "ccc_limit": money(result.ccc_limit_cents),
            "ccc_excess": money(result.ccc_excess_cents),
            "excess": [
                {"loanx": e.loanx, "issuer": e.issuer,
                 "par_in_excess": money(e.par_in_excess_cents), "bid": float(e.bid),
                 "haircut": money(e.haircut_cents)}
                for e in result.excess
            ],
            "haircut": money(result.haircut_cents),
            "adjusted": money(result.adjusted_cents),
            "advance_rate_pct": float(rate),
            "borrowing_base": money(result.borrowing_base_cents),
            "commitment": money(commitment),
            "drawn": money(drawn),
            "availability": money(result.availability_cents),
            "passed": result.passed,
        },
        "april": {
            "ccc_pct": float(before.ccc_pct),
            "haircut": money(before.haircut_cents),
            "borrowing_base": money(before.borrowing_base_cents),
            "availability": money(before.availability_cents),
            "total_par": money(before.total_par_cents),
        },
        "moodys_only": {"ccc_pct": float(default.ccc_pct), "passed": default.passed,
                        "haircut": money(default.haircut_cents)},
        "changes": {
            "sold": list(changes.sold),
            "bought": list(changes.bought),
            "relinked": [
                {"old_loanx": c.old_loanx, "new_loanx": c.new_loanx, "old_cusip": c.old_cusip,
                 "new_cusip": c.new_cusip, "issuer": c.issuer, "matched_on": list(c.matched_on)}
                for c in changes.relinked
            ],
            "unexplained_gone": list(changes.unexplained_gone),
            "unexplained_new": list(changes.unexplained_new),
        },
        "trades": [{**t, "par": t["par_cents"] / 100} for t in may["trades"]],
        "par_roll": {k: v / 100 for k, v in roll.items()},
        "downgrades": [
            {"loanx": r.loanx, "issuer": r.issuer, "before": list(r.before),
             "after": list(r.after), "notches": r.notches, "into_ccc": r.into_ccc}
            for r in ratings
        ],
        "price_moves": [
            {"loanx": m.loanx, "issuer": m.issuer, "before": float(m.before),
             "after": float(m.after), "change": float(m.change)}
            for m in moves
        ],
        "price_move_limit": float(terms["price_move_alert_pts"]),
        "clauses": clauses,
        "ccc_source": ccc_source,
        "warning_source": warning_source,
        "ai_used": False,
    }
    return tests, reports
