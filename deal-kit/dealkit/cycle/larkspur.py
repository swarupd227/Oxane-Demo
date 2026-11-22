"""Larkspur CLO 2026-1 Warehouse: Thornbury Bank's warehouse facility for a CLO manager, holding
broadly syndicated loans until the CLO prices.

The collateral administrator sends a positions workbook each month by SFTP and the pricing
service sends a price file by API. Everything is structured, so the facility runs on code alone,
as Thornbury requires: its data is never sent to a model.

Planted here: a May downgrade that takes the CCC bucket over its 7.5% limit, so the excess is
carried at market value (M11); a price fall of more than 10 points on one loan (M12); and one
loan whose LoanX ID and CUSIP changed, which must be linked, not raised as a sale and a new
purchase (N5).
"""

import csv
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any

import numpy as np
from openpyxl import Workbook
from reportlab.lib.units import inch
from reportlab.platypus import PageBreak, Spacer

from dealkit.legal_docs import _date
from dealkit.pdfkit import (
    ARTICLE,
    CENTERED,
    INDENT_1,
    SECTION,
    SMALL,
    TITLE,
    build,
    text,
)
from dealkit.workbooks import _header, _save_stable

FILES = {
    "credit_agreement": "Larkspur_Warehouse_Credit_Agreement.pdf",
    "positions_april": "Larkspur_Collateral_Report_2026-04-30.xlsx",
    "positions_may": "Larkspur_Collateral_Report_2026-05-29.xlsx",
    "prices_april": "Meridian_Prices_2026-04-30.csv",
    "prices_may": "Meridian_Prices_2026-05-29.csv",
}

MOODYS = ["Aaa", "Aa1", "Aa2", "Aa3", "A1", "A2", "A3", "Baa1", "Baa2", "Baa3", "Ba1", "Ba2",
          "Ba3", "B1", "B2", "B3", "Caa1", "Caa2", "Caa3", "Ca", "C"]
SP = ["AAA", "AA+", "AA", "AA-", "A+", "A", "A-", "BBB+", "BBB", "BBB-", "BB+", "BB", "BB-",
      "B+", "B", "B-", "CCC+", "CCC", "CCC-", "CC", "C"]
CCC_FROM = MOODYS.index("Caa1")

PREFIXES = [
    "Alderley", "Brackwell", "Carnforth", "Elstow", "Fernley", "Glaisdale", "Hartington",
    "Ingleby", "Kildwick", "Malham", "Nidderdale", "Ormesby", "Pateley", "Quernmore", "Rosedale",
    "Sedbergh", "Thrushcross", "Ulverston", "Yarwood", "Arncliffe", "Bainbridge", "Cotterdale",
    "Dentdale", "Farndale", "Grassington", "Ingleton", "Keld", "Litton", "Newbiggin", "Penistone",
    "Thwaite", "Upleatham", "Askrigg", "Burnsall", "Dacre", "Eskdale", "Horton", "Lofthouse",
    "Masham", "Nateby", "Osmotherley", "Ravenseat", "Sawley", "Tosside", "Uldale", "Wath",
    "Austwick", "Buckden", "Coverdale", "Dalby", "Hubberholme", "Starbotton",
]
SECTORS = [
    ("Packaging", "Containers and packaging"), ("Software", "Software"),
    ("Dental Partners", "Healthcare providers"), ("Logistics", "Transportation"),
    ("Healthcare", "Healthcare providers"), ("Foods", "Food products"),
    ("Insurance Services", "Insurance"), ("Building Products", "Building products"),
    ("Aerospace", "Aerospace and defence"), ("Waste Services", "Environmental services"),
    ("Pharma", "Pharmaceuticals"), ("Leisure", "Leisure"), ("Engineering", "Industrials"),
    ("Data Services", "IT services"), ("Veterinary Group", "Healthcare providers"),
    ("Testing Labs", "Business services"), ("Staffing", "Business services"),
    ("Laboratories", "Life sciences"), ("Marketing", "Media"),
    ("Home Services", "Consumer services"),
]
GRADES = {"Ba3": (0.10, 98.5, 100.5, 275, 325), "B1": (0.30, 97.0, 100.0, 325, 375),
          "B2": (0.35, 95.0, 99.5, 350, 425), "B3": (0.25, 91.0, 98.0, 400, 475)}


def lower_rating(moodys: str, sp: str) -> int:
    """The lower of the two ratings, as a notch index. NR counts as no rating."""
    notches = [scale.index(r) for scale, r in ((MOODYS, moodys), (SP, sp)) if r in scale]
    return max(notches)


def is_ccc(position: dict[str, Any]) -> bool:
    return lower_rating(position["moodys"], position["sp"]) >= CCC_FROM


def cusip(base: str) -> str:
    """Eight characters and the standard CUSIP check digit."""
    total = 0
    for index, char in enumerate(base[:8]):
        value = int(char) if char.isdigit() else ord(char) - 55
        if index % 2:
            value *= 2
        total += value // 10 + value % 10
    return base[:8] + str((10 - total % 10) % 10)


def _tick(rng: np.random.Generator, low: float, high: float) -> float:
    return round(float(rng.integers(int(low * 8), int(high * 8) + 1)) / 8, 3)


def _position(rng: np.random.Generator, issuer: str, industry: str, moodys: str, sp: str,
              par: int, loanx: str, base: str, facility: str = "Term Loan B") -> dict[str, Any]:
    grade = GRADES.get(moodys, GRADES["B3"])
    spread = int(rng.integers(grade[3] // 25, grade[4] // 25 + 1)) * 25
    year = int(rng.integers(2029, 2033))
    month = int(rng.integers(1, 13))
    return {
        "loanx": loanx,
        "cusip": cusip(base),
        "issuer": issuer,
        "facility": facility,
        "par": par,
        "spread_bps": spread,
        "floor_pct": 0.5 if rng.random() < 0.7 else 0.0,
        "maturity": date(year, month, 15),
        "moodys": moodys,
        "sp": sp,
        "industry": industry,
    }


def _book(spec: dict[str, Any], rng: np.random.Generator) -> tuple[list[dict[str, Any]], dict]:
    """April's positions, with each April and May bid, plus May's purchases."""
    planted = spec["planted"]
    fixed = {row[0] for row in spec["ccc_in_april"]} | {
        planted["downgrade"]["issuer"], planted["price_drop"]["issuer"],
        planted["identifier_change"]["issuer"], planted["not_rated"], planted["sold"],
        *(b[0] for b in planted["bought"]),
    }
    used_loanx: set[str] = set()

    def loanx() -> str:
        while True:
            value = f"LX{int(rng.integers(200000, 400000))}"
            if value not in used_loanx:
                used_loanx.add(value)
                return value

    def base() -> str:
        return f"{int(rng.integers(10000, 99999))}{chr(65 + int(rng.integers(0, 26)))}AB"

    sector = {name: industry for name, industry in SECTORS}
    names = [f"{p} {SECTORS[i % len(SECTORS)][0]}" for i, p in enumerate(PREFIXES)]
    names = [n for n in names if n not in fixed]
    regular_count = spec["positions"] - len(spec["ccc_in_april"]) - 5
    positions, bids = [], {}
    for name in names[:regular_count]:
        draw, cumulative, moodys = rng.random(), 0.0, "B3"
        for grade, (weight, *_rest) in GRADES.items():
            cumulative += weight
            if draw < cumulative:
                moodys = grade
                break
        sp = SP[MOODYS.index(moodys) + (1 if rng.random() < 0.15 and moodys != "B3" else 0)]
        industry = sector[name.split(" ", 1)[1]]
        position = _position(rng, name, industry, moodys, sp,
                             int(rng.integers(16, 45)) * 250000, loanx(), base())
        grade = GRADES[moodys]
        april = _tick(rng, grade[1], grade[2])
        may = round(april + float(rng.integers(-6, 7)) / 8, 3)
        positions.append(position)
        bids[position["loanx"]] = (april, min(may, 100.75))

    def special(name: str, moodys: str, sp: str, par: int, april: float, may: float,
                industry: str) -> dict[str, Any]:
        position = _position(rng, name, industry, moodys, sp, par, loanx(), base())
        positions.append(position)
        bids[position["loanx"]] = (april, may)
        return position

    for name, moodys, sp, par, april, may in spec["ccc_in_april"]:
        special(name, moodys, sp, par, april, may, sector[name.split(" ", 1)[1]]
                if name.split(" ", 1)[1] in sector else "Consumer services")
    down = planted["downgrade"]
    special(down["issuer"], *down["april"], down["par"], *down["bid"], "Auto components")
    drop = planted["price_drop"]
    special(drop["issuer"], *drop["rating"], drop["par"], *drop["bid"], "Chemicals")
    change = planted["identifier_change"]
    used_loanx.update({change["old"][0], change["new"][0]})
    linked = special(change["issuer"], "B2", "B", change["par"], 98.75, 98.875, "Education")
    bids[change["old"][0]] = bids.pop(linked["loanx"])
    linked.update(loanx=change["old"][0], cusip=cusip(change["old"][1]))
    special(planted["not_rated"], "B1", "NR", 6500000, 99.0, 99.125, "Business services")
    special(planted["sold"], "B2", "B", 6000000, 97.5, 97.25, "Hotels")
    bought = [
        {**_position(rng, name, "Consumer services" if "Pet" in name else "Financial technology",
                     "B1", "B+", par, loanx(), base()), "bid_may": price}
        for name, par, price in planted["bought"]
    ]
    return positions, {"bids": bids, "bought": bought}


def _cents(amount: Decimal) -> float:
    """Half up to the cent, as the agreement's amounts are stated."""
    return float(amount.quantize(Decimal("0.01"), ROUND_HALF_UP))


def _month(positions: list[dict[str, Any]], bid: dict[str, float], spec: dict[str, Any]
           ) -> dict[str, Any]:
    """The borrowing base, worked out independently of the platform's engine."""
    total = sum(p["par"] for p in positions)
    ccc = sorted((p for p in positions if is_ccc(p)), key=lambda p: (bid[p["loanx"]], p["loanx"]))
    ccc_par = sum(p["par"] for p in ccc)
    limit = total * spec["ccc_limit_pct"] / 100
    excess = max(0.0, ccc_par - limit)
    allocation, left = [], excess
    for p in ccc:
        if left <= 0:
            break
        part = min(p["par"], left)
        allocation.append({"loanx": p["loanx"], "issuer": p["issuer"], "par_in_excess":
                           round(part, 2), "bid": bid[p["loanx"]],
                           "haircut": _cents(Decimal(str(part)) * (1 - Decimal(str(bid[
                               p["loanx"]])) / 100))})
        left -= part
    haircut = round(sum(a["haircut"] for a in allocation), 2)
    adjusted = round(total - haircut, 2)
    base = _cents(Decimal(str(adjusted)) * Decimal(spec["advance_rate_pct"]) / 100)
    return {
        "positions": len(positions),
        "total_par": total,
        "ccc_par": ccc_par,
        "ccc_pct": round(ccc_par / total * 100, 2),
        "ccc_limit": round(limit, 2),
        "ccc_excess": round(excess, 2),
        "allocation": allocation,
        "haircut": haircut,
        "adjusted_balance": adjusted,
        "borrowing_base": base,
        "availability": round(min(spec["commitment_usd"], base) - spec["drawn_usd"], 2),
        "ccc_issuers": [p["issuer"] for p in ccc],
    }


def build_larkspur(cycle: dict[str, Any], folder: Path) -> dict[str, Any]:
    spec = cycle["larkspur"]
    planted = spec["planted"]
    rng = np.random.default_rng(cycle["seed"] + 11)
    april, extra = _book(spec, rng)
    bids = extra["bids"]
    april = sorted(april, key=lambda p: p["issuer"])

    change = planted["identifier_change"]
    may = []
    for p in april:
        if p["issuer"] == planted["sold"]:
            continue
        row = dict(p)
        if p["issuer"] == planted["downgrade"]["issuer"]:
            row["moodys"], row["sp"] = planted["downgrade"]["may"]
        if p["issuer"] == change["issuer"]:
            row["loanx"], row["cusip"] = change["new"][0], cusip(change["new"][1])
        may.append(row)
    for b in extra["bought"]:
        may.append({k: v for k, v in b.items() if k != "bid_may"})
    may = sorted(may, key=lambda p: p["issuer"])
    april_bid = {loanx: pair[0] for loanx, pair in bids.items()}
    may_bid = {
        (change["new"][0] if loanx == change["old"][0] else loanx): pair[1]
        for loanx, pair in bids.items()
    }
    may_bid |= {b["loanx"]: b["bid_may"] for b in extra["bought"]}
    may_bid = {k: v for k, v in may_bid.items() if k in {p["loanx"] for p in may}}

    sold = next(p for p in april if p["issuer"] == planted["sold"])
    trades = [
        {"trade_date": date(2026, 5, 6), "direction": "Sell", "loanx": sold["loanx"],
         "issuer": sold["issuer"], "facility": sold["facility"], "par": sold["par"],
         "price": 97.5},
        *[{"trade_date": date(2026, 5, 13 + 7 * i), "direction": "Buy", "loanx": b["loanx"],
           "issuer": b["issuer"], "facility": b["facility"], "par": b["par"],
           "price": b["bid_may"]} for i, b in enumerate(extra["bought"])],
    ]

    _agreement(cycle, folder / FILES["credit_agreement"])
    _positions(spec, april, spec["april_date"], folder / FILES["positions_april"], None)
    _positions(spec, may, spec["may_date"], folder / FILES["positions_may"], trades)
    _prices(april_bid, spec["april_date"], folder / FILES["prices_april"])
    _prices(may_bid, spec["may_date"], folder / FILES["prices_may"])

    months = {"april": _month(april, april_bid, spec), "may": _month(may, may_bid, spec)}
    by_old = {p["loanx"]: p for p in april}
    downgrades = [
        {"issuer": p["issuer"], "loanx": p["loanx"],
         "from": [by_old[p["loanx"]]["moodys"], by_old[p["loanx"]]["sp"]],
         "to": [p["moodys"], p["sp"]]}
        for p in may if p["loanx"] in by_old
        and lower_rating(p["moodys"], p["sp"]) > lower_rating(by_old[p["loanx"]]["moodys"],
                                                           by_old[p["loanx"]]["sp"])
    ]
    moves = [
        {"issuer": p["issuer"], "loanx": p["loanx"],
         "april": april_bid[old], "may": may_bid[p["loanx"]],
         "change": round(may_bid[p["loanx"]] - april_bid[old], 3)}
        for p in may
        for old in [change["old"][0] if p["loanx"] == change["new"][0] else p["loanx"]]
        if old in april_bid
        and april_bid[old] - may_bid[p["loanx"]] > spec["price_move_alert_pts"]
    ]
    return {
        "months": months,
        "downgrades": downgrades,
        "price_moves": moves,
        "identifier_change": {
            "issuer": change["issuer"],
            "old_loanx": change["old"][0], "new_loanx": change["new"][0],
            "old_cusip": cusip(change["old"][1]), "new_cusip": cusip(change["new"][1]),
        },
        "trades": [{**t, "trade_date": t["trade_date"].isoformat()} for t in trades],
        "par_roll": {
            "april": months["april"]["total_par"],
            "sold": sold["par"],
            "bought": sum(b["par"] for b in extra["bought"]),
            "may": months["may"]["total_par"],
        },
        "not_rated": planted["not_rated"],
    }


def _agreement(cycle: dict[str, Any], path: Path) -> None:
    spec = cycle["larkspur"]
    story: list[Any] = [
        Spacer(1, 1.4 * inch),
        text("WAREHOUSE CREDIT AGREEMENT", TITLE),
        text(f"dated as of {_date(spec['signed'])}", CENTERED),
        text(f"{spec['borrower'].upper()}, as Borrower", CENTERED),
        text(f"{spec['manager'].upper()}, as Collateral Manager", CENTERED),
        text(f"{spec['lender'].upper()}, as Lender", CENTERED),
        text(f"{spec['administrator'].upper()}, as Collateral Administrator", CENTERED),
        text(f"US${spec['commitment_usd']:,} revolving warehouse facility", CENTERED),
        PageBreak(),
        text("EXTRACT: SECTIONS RELEVANT TO MONITORING", ARTICLE),
        text("Conformed copy. Sections not relevant to monthly monitoring are omitted.", SMALL),
        text("Section 1.1 Definitions", SECTION),
        text(
            '"CCC Obligation" means a Collateral Obligation whose Moody\'s Rating is "Caa1" or '
            'below or whose S&P Rating is "CCC+" or below. Where the two ratings differ, the '
            "lower rating applies."
        ),
        text(
            '"CCC Excess" means the amount by which the Aggregate Principal Balance of all CCC '
            f"Obligations exceeds {spec['ccc_limit_pct']}% of the Aggregate Principal Balance "
            "of all Collateral Obligations."
        ),
        text(
            '"CCC Excess Adjustment" means the amount by which the principal balance of the CCC '
            "Obligations with the lowest Market Value, taken in order and up to the CCC Excess, "
            "exceeds their Market Value."
        ),
        text(
            '"Market Value" means, for a Collateral Obligation, its principal balance '
            "multiplied by the bid price reported by the Pricing Service on the Determination "
            "Date."
        ),
        text(
            '"Adjusted Collateral Balance" means the Aggregate Principal Balance of all '
            "Collateral Obligations less the CCC Excess Adjustment."
        ),
        text(
            f'"Borrowing Base" means {spec["advance_rate_pct"]}% of the Adjusted Collateral '
            "Balance."
        ),
        text("Section 2.3 Borrowing Base", SECTION),
        text(
            "The Loans outstanding shall not exceed the lesser of the Commitment and the "
            "Borrowing Base on any Determination Date. The last Business Day of each month is a "
            "Determination Date."
        ),
        text("Section 6.4 Reporting", SECTION),
        text(
            "(a) Within ten Business Days after each Determination Date the Collateral "
            "Administrator shall deliver to the Lender a Collateral Report listing each "
            "Collateral Obligation, its identifiers, principal balance, ratings and trades.",
            INDENT_1,
        ),
        text(
            f"(b) {spec['pricing_service']} shall deliver bid prices for each Collateral "
            "Obligation as of each Determination Date by its pricing interface.",
            INDENT_1,
        ),
        text("Section 6.5 Early warning", SECTION),
        text(
            "The Collateral Administrator shall tell the Lender of any downgrade of a Collateral "
            "Obligation and of any fall in its bid price of more than "
            f"{spec['price_move_alert_pts']} "
            "points in a month."
        ),
    ]
    build(path, story, "Larkspur Warehouse Credit Agreement",
          "Larkspur Warehouse Credit Agreement (extract)")


POSITION_COLUMNS = ["LoanX ID", "CUSIP", "Issuer", "Facility", "Par Amount", "Spread (bps)",
                    "Floor (%)", "Maturity Date", "Moody's Rating", "S&P Rating", "Industry"]


def _positions(spec: dict[str, Any], positions: list[dict[str, Any]], as_of: date, path: Path,
               trades: list[dict[str, Any]] | None) -> None:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Positions"
    _header(sheet, 1, POSITION_COLUMNS)
    for p in positions:
        sheet.append([p["loanx"], p["cusip"], p["issuer"], p["facility"], p["par"],
                      p["spread_bps"], p["floor_pct"], p["maturity"].isoformat(), p["moodys"],
                      p["sp"], p["industry"]])
    for column, width in zip("ABCDEFGHIJK", [11, 12, 32, 14, 14, 12, 9, 13, 14, 11, 26],
                             strict=True):
        sheet.column_dimensions[column].width = width
    report = workbook.create_sheet("Report")
    report.append(["Collateral Report", spec["name"]])
    report.append(["Determination Date", as_of.isoformat()])
    report.append(["Collateral Administrator", spec["administrator"]])
    report.append(["Collateral Manager", spec["manager"]])
    if trades is not None:
        sheet = workbook.create_sheet("Trades")
        _header(sheet, 1, ["Trade Date", "Direction", "LoanX ID", "Issuer", "Facility",
                           "Par Amount", "Price"])
        for t in trades:
            sheet.append([t["trade_date"].isoformat(), t["direction"], t["loanx"], t["issuer"],
                          t["facility"], t["par"], t["price"]])
    _save_stable(workbook, path)


def _prices(bids: dict[str, float], as_of: date, path: Path) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(["LoanX_ID", "Bid", "Ask", "Quotes", "Price_Date"])
        for loanx in sorted(bids):
            bid = bids[loanx]
            writer.writerow([loanx, f"{bid:.3f}", f"{bid + 0.5:.3f}",
                             3 + int(loanx[-1]) % 4, as_of.isoformat()])
