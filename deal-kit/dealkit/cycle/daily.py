"""Larkspur's daily feeds through May: what a CLO warehouse sends between month ends.

Built from the month-end files that build_larkspur writes, so the two always agree: the daily
positions follow May's trades on their trade dates, the daily rating feed carries the May
downgrade on the day it happened, and the daily bids move from April's to May's. The 29 May
deliveries are the month-end files themselves.

Planted here: the 14 May position file arrived the next morning after its deadline, complete
(N8), and no price file was ever delivered for 21 May (M20).
"""

import csv
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any

import numpy as np
from openpyxl import load_workbook

FOLDER = "larkspur-daily"
LOG = "Larkspur_Daily_Feed_Log_May_2026.csv"
HOLIDAYS = {date(2026, 5, 25), date(2026, 6, 19)}
FEEDS = {
    "positions": "Larkspur_Positions_{day}.csv",
    "prices": "Meridian_Prices_{day}.csv",
    "ratings": "Ingleby_Ratings_{day}.csv",
}


def business_days(start: date, end: date) -> list[date]:
    days, day = [], start
    while day <= end:
        if day.weekday() < 5 and day not in HOLIDAYS:
            days.append(day)
        day += timedelta(days=1)
    return days


def next_business_day(day: date) -> date:
    day += timedelta(days=1)
    while day.weekday() >= 5 or day in HOLIDAYS:
        day += timedelta(days=1)
    return day


def _positions(path: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    book = load_workbook(path, read_only=True)
    rows = list(book["Positions"].iter_rows(values_only=True))
    header = [str(h) for h in rows[0]]
    positions = [dict(zip(header, r, strict=True)) for r in rows[1:]]
    trades = []
    if "Trades" in book.sheetnames:
        trade_rows = list(book["Trades"].iter_rows(values_only=True))
        trade_header = [str(h) for h in trade_rows[0]]
        trades = [dict(zip(trade_header, r, strict=True)) for r in trade_rows[1:]]
    return positions, trades


def _prices(path: Path) -> dict[str, dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return {row["LoanX_ID"]: row for row in csv.DictReader(handle)}


def build_daily(cycle: dict[str, Any], larkspur_folder: Path, folder: Path) -> dict[str, Any]:
    spec, lark = cycle["larkspur_daily"], cycle["larkspur"]
    rng = np.random.default_rng(spec["seed"])
    april, _ = _positions(larkspur_folder / "Larkspur_Collateral_Report_2026-04-30.xlsx")
    may, trades = _positions(larkspur_folder / "Larkspur_Collateral_Report_2026-05-29.xlsx")
    april_bids = _prices(larkspur_folder / "Meridian_Prices_2026-04-30.csv")
    may_bids = _prices(larkspur_folder / "Meridian_Prices_2026-05-29.csv")
    month_end_prices = (larkspur_folder / "Meridian_Prices_2026-05-29.csv").read_text("utf-8")
    change = lark["planted"]["identifier_change"]
    down = lark["planted"]["downgrade"]
    drop = lark["planted"]["price_drop"]
    old_loanx, new_loanx = change["old"][0], change["new"][0]
    by_issuer_may = {p["Issuer"]: p for p in may}
    days = business_days(date(2026, 5, 1), date(2026, 5, 29))
    sold = {t["LoanX ID"]: date.fromisoformat(t["Trade Date"]) for t in trades
            if t["Direction"] == "Sell"}
    bought = {t["LoanX ID"]: date.fromisoformat(t["Trade Date"]) for t in trades
              if t["Direction"] == "Buy"}
    late, gap = spec["planted"]["late"], spec["planted"]["gap"]
    log, files = [], 0
    for index, day in enumerate(days):
        held = []
        for p in april:
            loanx = p["LoanX ID"]
            if loanx in sold and day >= sold[loanx]:
                continue
            row = dict(p)
            if loanx == old_loanx and day >= spec["identifier_change_day"]:
                row = dict(by_issuer_may[p["Issuer"]])
            if p["Issuer"] == down["issuer"] and day >= spec["downgrade_day"]:
                row["Moody's Rating"], row["S&P Rating"] = down["may"]
            held.append(row)
        held += [p for p in may if p["LoanX ID"] in bought and day >= bought[p["LoanX ID"]]]
        held.sort(key=lambda p: p["Issuer"])
        stamp = day.isoformat()
        name = FEEDS["positions"].format(day=stamp)
        with (folder / name).open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle, lineterminator="\n")
            writer.writerow(["LoanX ID", "Issuer", "Par Amount", "Moody's Rating", "S&P Rating",
                             "As Of"])
            for p in held:
                writer.writerow([p["LoanX ID"], p["Issuer"], p["Par Amount"], p["Moody's Rating"],
                                 p["S&P Rating"], stamp])
        files += 1
        received = datetime.combine(next_business_day(day),
                                    time(6, int(rng.integers(5, 56))))
        if late["feed"] == "positions" and day == late["as_of"]:
            received = datetime.fromisoformat(late["received"])
        log.append({"feed": "positions", "as_of": stamp, "file": name,
                    "rows": len(held), "received_at": received.isoformat(timespec="minutes")})

        # Prices: from April's bid towards May's, on the same 1/8 grid; 29 May is the month-end
        # file itself.
        name = FEEDS["prices"].format(day=stamp)
        if gap["feed"] == "prices" and day == gap["as_of"]:
            log.append({"feed": "prices", "as_of": stamp, "file": "", "rows": 0,
                        "received_at": ""})
        else:
            if day == days[-1]:
                (folder / name).write_text(month_end_prices, encoding="utf-8")
                rows = len(may_bids)
            else:
                share = (index + 1) / len(days)
                with (folder / name).open("w", encoding="utf-8", newline="") as handle:
                    writer = csv.writer(handle, lineterminator="\n")
                    writer.writerow(["LoanX_ID", "Bid", "Ask", "Quotes", "Price_Date"])
                    for p in sorted(held, key=lambda x: x["LoanX ID"]):
                        loanx = p["LoanX ID"]
                        end = float(may_bids[loanx]["Bid"]) if loanx in may_bids else float(
                            may_bids[new_loanx]["Bid"]) if loanx == old_loanx else float(
                            april_bids[loanx]["Bid"])
                        start = float(april_bids[loanx]["Bid"]) if loanx in april_bids else \
                            float(april_bids[old_loanx]["Bid"]) if loanx == new_loanx else end
                        if p["Issuer"] == drop["issuer"]:
                            bid = end if day >= spec["price_drop_day"] else start
                        else:
                            bid = round((start + (end - start) * share) * 8) / 8
                        writer.writerow([loanx, f"{bid:.3f}", f"{bid + 0.5:.3f}",
                                         3 + int(loanx[-1]) % 4, stamp])
                rows = len(held)
            files += 1
            at = datetime.combine(day, time(17, int(rng.integers(5, 51))))
            log.append({"feed": "prices", "as_of": stamp, "file": name, "rows": rows,
                        "received_at": at.isoformat(timespec="minutes")})

        # Ratings: the day's changes only. Most days there are none.
        name = FEEDS["ratings"].format(day=stamp)
        changes = []
        if day == spec["downgrade_day"]:
            issuer = next(p for p in april if p["Issuer"] == down["issuer"])
            changes.append([issuer["LoanX ID"], down["issuer"], "Moody's", down["april"][0],
                            down["may"][0], stamp])
            changes.append([issuer["LoanX ID"], down["issuer"], "S&P", down["april"][1],
                            down["may"][1], stamp])
        with (folder / name).open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle, lineterminator="\n")
            writer.writerow(["LoanX_ID", "Issuer", "Agency", "Previous", "Current",
                             "Effective"])
            writer.writerows(changes)
        files += 1
        at = datetime.combine(next_business_day(day), time(5, int(rng.integers(30, 59))))
        log.append({"feed": "ratings", "as_of": stamp, "file": name, "rows": len(changes),
                    "received_at": at.isoformat(timespec="minutes")})
    with (folder / LOG).open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["feed", "as_of", "file", "rows",
                                                    "received_at"], lineterminator="\n")
        writer.writeheader()
        writer.writerows(log)
    return {
        "business_days": len(days),
        "expected": len(days) * len(FEEDS),
        "received": sum(1 for r in log if r["received_at"]),
        "late": [{"feed": late["feed"], "as_of": late["as_of"].isoformat()}],
        "missing": [{"feed": gap["feed"], "as_of": gap["as_of"].isoformat()}],
        "rating_changes": [{"as_of": spec["downgrade_day"].isoformat(),
                            "issuer": down["issuer"]}],
        "files": files,
    }
