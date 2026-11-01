"""Generate the April 2026 loan tape, with its planted problems.

The tape uses the borrower's own column names, which differ from the platform
names in the eligibility rules. Mapping between them is scene 4's job.
"""

import csv
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import numpy as np

# Raw tape header -> platform field. Order is the column order in the CSV.
COLUMNS: dict[str, str] = {
    "LoanNumber": "loan_id",
    "VIN": "vin",
    "OrigDate": "origination_date",
    "FirstPmtDate": "first_payment_date",
    "MaturityDate": "maturity_date",
    "OrigBal": "original_balance",
    "CurrBal": "current_balance",
    "NoteRate": "apr",
    "OrigTerm": "original_term",
    "RemTerm": "remaining_term",
    "PmtsMade": "payments_made",
    "MonthlyPmt": "monthly_payment",
    "CreditScore": "fico",
    "BorrState": "obligor_state",
    "BorrZip3": "obligor_zip3",
    "EmployType": "employment_type",
    "StatedIncome": "stated_monthly_income",
    "PTI": "payment_to_income",
    "DealerName": "dealer_name",
    "DealerState": "dealer_state",
    "Make": "vehicle_make",
    "Model": "vehicle_model",
    "ModelYr": "model_year",
    "NewUsed": "vehicle_condition",
    "Mileage": "odometer_at_origination",
    "AmtFinanced": "amount_financed",
    "BookValue": "vehicle_book_value",
    "LTV": "loan_to_value",
    "DPD": "days_past_due",
    "LastPmtDate": "last_payment_date",
    "NextDueDate": "next_due_date",
    "ModCount": "modification_count",
    "LoanStatus": "status",
    "ChgOffDate": "charge_off_date",
    "ChgOffAmt": "charge_off_amount",
    "RepoDate": "repossession_date",
    "ServicerCode": "servicer_code",
    "CutoffDate": "cutoff_date",
}

US_STATES = (
    "AL AK AZ AR CA CO CT DE FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ "
    "NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY DC"
).split()

# Weights keep every state under the 20% limit in C1.
STATE_WEIGHTS = {
    "TX": 19.0, "FL": 13.5, "CA": 11.0, "GA": 6.5, "NC": 5.5, "OH": 4.5, "AZ": 4.5, "TN": 4.0,
    "IL": 3.5, "PA": 3.5, "SC": 3.0, "AL": 2.5, "OK": 2.5, "LA": 2.0, "MO": 2.0, "NV": 2.0,
    "IN": 1.5, "KY": 1.5, "MI": 1.5, "VA": 1.5,
}

# First three ZIP digits by state, from the USPS allocation.
ZIP3_RANGES = {
    "TX": (750, 799), "FL": (320, 349), "CA": (900, 961), "GA": (300, 319), "NC": (270, 289),
    "OH": (430, 458), "AZ": (850, 865), "TN": (370, 385), "IL": (600, 629), "PA": (150, 196),
    "SC": (290, 299), "AL": (350, 369), "OK": (730, 749), "LA": (700, 714), "MO": (630, 658),
    "NV": (889, 898), "IN": (460, 479), "KY": (400, 427), "MI": (480, 499), "VA": (220, 246),
}

MAKES = {
    "Toyota": ["Camry", "Corolla", "RAV4", "Tacoma"],
    "Ford": ["F-150", "Escape", "Explorer", "Fusion"],
    "Chevrolet": ["Silverado", "Equinox", "Malibu", "Traverse"],
    "Nissan": ["Altima", "Rogue", "Sentra", "Frontier"],
    "Honda": ["Civic", "Accord", "CR-V", "Pilot"],
    "Hyundai": ["Elantra", "Sonata", "Tucson", "Santa Fe"],
    "Kia": ["Forte", "Optima", "Sorento", "Sportage"],
    "Jeep": ["Wrangler", "Cherokee", "Grand Cherokee", "Compass"],
    "Dodge": ["Charger", "Durango", "Journey", "Ram 1500"],
}

DEALER_STEMS = (
    "Lone Star", "Gulf Coast", "Piedmont", "Red River", "Palmetto", "Bluegrass", "Desert Valley",
    "Tri-County", "Sierra", "Heartland", "Magnolia", "Cypress", "Summit", "Keystone", "Ozark",
    "Peachtree", "Mesa", "Liberty", "Harbor", "Prairie", "Riverbend", "Cardinal", "Pinnacle",
    "Crossroads", "Golden Gate", "Evergreen", "Lakeshore", "Frontier", "Canyon", "Trailhead",
)
DEALER_SUFFIXES = ("Auto Sales", "Motors", "Auto Group", "Chevrolet", "Toyota", "Ford", "Nissan")

VIN_ALPHABET = "ABCDEFGHJKLMNPRSTUVWXYZ0123456789"
VIN_WEIGHTS = (8, 7, 6, 5, 4, 3, 2, 10, 0, 9, 8, 7, 6, 5, 4, 3, 2)
VIN_VALUES = dict(zip("ABCDEFGH", range(1, 9), strict=True)) | dict(
    zip("JKLMN", range(1, 6), strict=True)
) | {"P": 7, "R": 9} | dict(zip("STUVWXYZ", range(2, 10), strict=True)) | {
    str(digit): digit for digit in range(10)
}


@dataclass
class Tape:
    rows: list[dict[str, Any]]
    # Planted facts for the answer key. The pipeline never sees these.
    planted: dict[str, Any] = field(default_factory=dict)


def _vin(rng: np.random.Generator) -> str:
    chars = list(rng.choice(list(VIN_ALPHABET), size=17))
    total = sum(VIN_VALUES[c] * w for c, w in zip(chars, VIN_WEIGHTS, strict=True))
    remainder = total % 11
    chars[8] = "X" if remainder == 10 else str(remainder)
    return "".join(str(c) for c in chars)


def _payment(principal: float, apr: float, term: int) -> float:
    rate = apr / 1200
    return principal * rate / (1 - (1 + rate) ** -term)


def _balance(principal: float, apr: float, payment: float, paid: int) -> float:
    rate = apr / 1200
    return principal * (1 + rate) ** paid - payment * ((1 + rate) ** paid - 1) / rate


def _add_months(start: date, months: int) -> date:
    index = start.year * 12 + start.month - 1 + months
    return date(index // 12, index % 12 + 1, min(start.day, 28))


def _months_between(start: date, end: date) -> int:
    return (end.year - start.year) * 12 + end.month - start.month


def _dealers(rng: np.random.Generator) -> list[str]:
    names = [f"{stem} {suffix}" for stem in DEALER_STEMS for suffix in DEALER_SUFFIXES]
    return list(rng.choice(names, size=140, replace=False))


def _base_row(rng: np.random.Generator, number: int, cutoff: date, dealers: list[str],
              dealer_weights: np.ndarray, mean_balance: float) -> dict[str, Any]:
    # Long terms stay under the 25% limit in C3, so the only excess is the dealer match.
    term = int(rng.choice([48, 60, 66, 72, 75, 84], p=[0.08, 0.26, 0.15, 0.34, 0.07, 0.10]))
    seasoned = int(rng.integers(2, min(term - 3, 40)))
    first_payment = _add_months(date(cutoff.year, cutoff.month, 1), -seasoned + 1).replace(
        day=int(rng.integers(1, 28))
    )
    origination = first_payment - timedelta(days=int(rng.integers(30, 46)))
    # Keep ordinary loans below the US$75,000 cap in E5.
    original = float(np.clip(rng.lognormal(np.log(mean_balance) - 0.06, 0.34), 9500, 74000))
    fico = int(np.clip(rng.normal(622, 34), 540, 790))
    apr = round(float(np.clip(27.5 - (fico - 540) * 0.075 + rng.normal(0, 1.6), 6.25, 29.5)), 2)
    payment = _payment(original, apr, term)
    paid = min(_months_between(first_payment, cutoff) + 1, term - 1)
    current = _balance(original, apr, payment, paid)
    make = str(rng.choice(list(MAKES)))
    condition = "USED" if rng.random() < 0.64 else "NEW"
    model_year = origination.year if condition == "NEW" else origination.year - int(
        rng.integers(1, 9)
    )
    state_weights = np.array(list(STATE_WEIGHTS.values()))
    state = str(rng.choice(list(STATE_WEIGHTS), p=state_weights / state_weights.sum()))
    income = round(float(rng.uniform(3200, 9500)), 2)
    book = round(original / rng.uniform(0.86, 1.18), 2)
    last_payment = date(cutoff.year, cutoff.month, int(rng.integers(1, 29)))
    return {
        "loan_id": f"BAF{100000 + number}",
        "vin": _vin(rng),
        "origination_date": origination,
        "first_payment_date": first_payment,
        "maturity_date": _add_months(first_payment, term - 1),
        "original_balance": round(original, 2),
        "current_balance": round(current, 2),
        "apr": apr,
        "original_term": term,
        "remaining_term": term - paid,
        "payments_made": paid,
        "monthly_payment": round(payment, 2),
        "fico": fico,
        "obligor_state": state,
        "obligor_zip3": f"{int(rng.integers(100, 999))}",
        "employment_type": str(rng.choice(["SALARIED", "HOURLY", "SELF_EMPLOYED", "RETIRED"],
                                          p=[0.52, 0.34, 0.1, 0.04])),
        "stated_monthly_income": income,
        "payment_to_income": round(payment / income * 100, 2),
        "dealer_name": str(rng.choice(dealers, p=dealer_weights)),
        "dealer_state": state,
        "vehicle_make": make,
        "vehicle_model": str(rng.choice(MAKES[make])),
        "model_year": model_year,
        "vehicle_condition": condition,
        "odometer_at_origination": int(rng.integers(8, 40)) if condition == "NEW"
        else int(rng.integers(18000, 92000)),
        "amount_financed": round(original, 2),
        "vehicle_book_value": book,
        "loan_to_value": round(original / book * 100, 2),
        "days_past_due": int(rng.choice([0, 0, 0, 0, 0, 0, 3, 7, 12, 18, 26])),
        "last_payment_date": last_payment,
        "next_due_date": _add_months(last_payment, 1),
        "modification_count": int(rng.choice([0, 1], p=[0.96, 0.04])),
        "status": "ACTIVE",
        "charge_off_date": None,
        "charge_off_amount": None,
        "repossession_date": None,
        "servicer_code": "BAF01",
        "cutoff_date": cutoff,
    }


def _plant_baseline_failures(rows: list[dict[str, Any]], counts: dict[str, int],
                             rng: np.random.Generator, cutoff: date,
                             pool: list[int]) -> dict[str, list[str]]:
    """Make loans fail exactly one rule, so each rule has a known result."""
    picks: dict[str, list[str]] = {}
    cursor = 0

    def take(rule: str) -> list[dict[str, Any]]:
        nonlocal cursor
        chosen = [rows[i] for i in pool[cursor: cursor + counts[rule]]]
        cursor += counts[rule]
        picks[rule] = [row["loan_id"] for row in chosen]
        return chosen

    for row in take("E1"):
        row["days_past_due"] = int(rng.integers(61, 120))
        row["status"] = "DELINQUENT"
    for index, row in enumerate(take("E2")):
        row["days_past_due"] = 0
        if index % 2 == 0:
            row["status"] = "CHARGED_OFF"
            row["charge_off_date"] = cutoff - timedelta(days=int(rng.integers(3, 28)))
            row["charge_off_amount"] = row["current_balance"]
        else:
            row["status"] = "REPO"
            row["repossession_date"] = cutoff - timedelta(days=int(rng.integers(3, 28)))
    for row in take("E3"):
        row["original_term"] = 96
        row["remaining_term"] = 96 - row["payments_made"]
        row["maturity_date"] = _add_months(row["first_payment_date"], 95)
    for row in take("E4"):
        row["fico"] = int(rng.integers(505, 540))
    for row in take("E5"):
        row["current_balance"] = round(float(rng.uniform(76000, 92000)), 2)
        row["original_balance"] = round(row["current_balance"] * 1.06, 2)
        row["amount_financed"] = row["original_balance"]
    for row, state in zip(take("E6"), ["PR", "ON", "BC"], strict=True):
        row["obligor_state"] = state
        row["dealer_state"] = state
    for row in take("E8"):
        row["modification_count"] = int(rng.integers(2, 4))
    for row in take("E9"):
        row["apr"] = round(float(rng.uniform(30.2, 32.9)), 2)
    for row in take("E10"):
        row["vehicle_condition"] = "USED"
        row["model_year"] = row["origination_date"].year - int(rng.integers(11, 14))
    for row in take("E11"):
        row["payments_made"] = 0
        row["remaining_term"] = row["original_term"]
        row["current_balance"] = row["original_balance"]
    return picks


def _plant_x4(rows: list[dict[str, Any]], pool: list[int], count: int, target: float,
              rng: np.random.Generator) -> list[str]:
    """Draw a natural spread of 41 balances that total about the agreed gap."""
    balances = np.array([rows[i]["current_balance"] for i in pool])
    while True:
        sample = rng.choice(len(pool), size=count, replace=False)
        if abs(balances[sample].sum() - target) <= target * 0.01:
            break
    chosen = sorted(int(pool[i]) for i in sample)
    for index in chosen:
        rows[index]["days_past_due"] = int(rng.integers(31, 60))
        rows[index]["status"] = "DELINQUENT"
    return [rows[i]["loan_id"] for i in chosen]


def _plant_x5(rows: list[dict[str, Any]], pool: list[int], shared: int) -> list[dict[str, Any]]:
    """Give 3 VINs to 2 loans each. The second loan is a different borrower and dealer state."""
    clusters = []
    for number in range(shared):
        first, second = rows[pool[number * 2]], rows[pool[number * 2 + 1]]
        for attribute in ("vehicle_make", "vehicle_model", "model_year", "vehicle_condition"):
            second[attribute] = first[attribute]
        second["vin"] = first["vin"]
        clusters.append({"vin": first["vin"], "loan_ids": [first["loan_id"], second["loan_id"]]})
    return clusters


def _plant_x6(rows: list[dict[str, Any]], pool: list[int], names: list[str],
              shares: list[float]) -> dict[str, list[str]]:
    """Fill two spellings of one dealer until each holds its target share of the pool."""
    total = sum(rows[i]["current_balance"] for i in pool)
    groups: dict[str, list[str]] = {name: [] for name in names}
    cursor = 0
    for name, share in zip(names, shares, strict=True):
        filled = 0.0
        while filled < total * share / 100:
            row = rows[pool[cursor]]
            cursor += 1
            row["dealer_name"] = name
            row["dealer_state"] = "TX"
            filled += row["current_balance"]
            groups[name].append(row["loan_id"])
    return groups


def _finish_rows(rows: list[dict[str, Any]], cutoff: date) -> None:
    """Make ZIP codes and payment dates agree with the rest of each row.

    This runs after planting and uses no random numbers, so no balance, rule
    result or planted exception can change.
    """
    for row in rows:
        ranges = ZIP3_RANGES.get(row["obligor_state"])
        if ranges:
            low, high = ranges
            row["obligor_zip3"] = f"{low + int(row['obligor_zip3']) % (high - low + 1):03d}"
        else:
            row["obligor_zip3"] = ""

        due_day = row["first_payment_date"].day
        due = date(cutoff.year, cutoff.month, min(due_day, 28))
        if due > cutoff:
            due = _add_months(due, -1)
        if row["days_past_due"]:
            # The oldest unpaid instalment fell due this many days before the cut-off.
            row["next_due_date"] = cutoff - timedelta(days=row["days_past_due"])
            row["last_payment_date"] = _add_months(row["next_due_date"], -1)
        else:
            row["last_payment_date"] = due
            row["next_due_date"] = _add_months(due, 1)


def _format_date(value: date | None) -> str:
    return "" if value is None else value.strftime("%Y-%m-%d")


def _plant_x9(rows: list[dict[str, Any]], count: int, rng: np.random.Generator) -> list[str]:
    """Write most origination dates as MM/DD/YYYY and a batch as DD/MM/YYYY."""
    picked = {int(i) for i in rng.choice(len(rows), size=count, replace=False)}
    for index, row in enumerate(rows):
        value: date = row["origination_date"]
        row["raw_origination_date"] = value.strftime(
            "%d/%m/%Y" if index in picked else "%m/%d/%Y"
        )
    return [rows[i]["loan_id"] for i in sorted(picked)]


def generate_tape(deal: dict[str, Any]) -> Tape:
    rng = np.random.default_rng(deal["seed"])
    spec = deal["tape"]
    planted = deal["planted"]
    cutoff: date = spec["cutoff_date"]

    dealers = _dealers(rng)
    weights = rng.dirichlet(np.full(len(dealers), 2.0))
    # Keep the largest ordinary dealer well below the 5% limit in C2.
    weights = np.minimum(weights, 0.03)
    weights = weights / weights.sum()

    rows = [
        _base_row(rng, number, cutoff, dealers, weights, spec["mean_original_balance_usd"])
        for number in range(spec["loans"])
    ]

    order = [int(i) for i in rng.permutation(len(rows))]
    counts = spec["baseline_failures"]
    baseline_total = sum(counts.values())
    baseline = _plant_baseline_failures(rows, counts, rng, cutoff, order[:baseline_total])
    remaining = order[baseline_total:]

    x4_pool, remaining = remaining[:600], remaining[600:]
    x4 = _plant_x4(rows, x4_pool, planted["x4_past_due_loans"], planted["x4_gap_target_usd"], rng)
    # Loans not used by X4 go back so the later plants never overlap it.
    x4_ids = set(x4)
    remaining = [i for i in x4_pool if rows[i]["loan_id"] not in x4_ids] + remaining

    x5 = _plant_x5(rows, remaining[:planted["x5_shared_vins"] * 2], planted["x5_shared_vins"])
    remaining = remaining[planted["x5_shared_vins"] * 2:]
    x6 = _plant_x6(rows, remaining, planted["x6_dealer_names"], planted["x6_dealer_share_pct"])
    x9 = _plant_x9(rows, planted["x9_mixed_date_rows"], rng)
    _finish_rows(rows, cutoff)

    return Tape(rows=rows, planted={
        "baseline": baseline, "x4_loans": x4, "x5_clusters": x5, "x6_groups": x6,
        "x9_loans": x9,
    })


def write_csv(tape: Tape, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(COLUMNS)
        for row in tape.rows:
            writer.writerow([_raw_value(row, name) for name in COLUMNS.values()])


def _raw_value(row: dict[str, Any], name: str) -> Any:
    if name == "origination_date":
        return row["raw_origination_date"]
    value = row[name]
    if value is None:
        return ""
    return _format_date(value) if isinstance(value, date) else value
