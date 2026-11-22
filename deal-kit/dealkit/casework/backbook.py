"""April tapes for four existing Calderwood facilities, the backbook.

Each servicer exports from the same loan servicing system as Bramble, so Bramble's stored
mapping should load them. Each tape differs from Bramble's layout in at most a few planted ways,
recorded for the answer key: a renamed column, an extra column with blanks for current loans,
or the servicer's own status codes.
"""

import csv
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np

from dealkit.tape import COLUMNS, _base_row, _dealers, _finish_rows, _raw_value


def _rows(rng: np.random.Generator, spec: dict[str, Any], cutoff: date) -> list[dict[str, Any]]:
    dealers = _dealers(rng)
    weights = rng.dirichlet(np.full(len(dealers), 2.0))
    weights = weights / weights.sum()
    rows = [_base_row(rng, number, cutoff, dealers, weights, 31000.0)
            for number in range(spec["loans"])]
    for number, row in enumerate(rows):
        row["loan_id"] = f"{spec['prefix']}{200000 + number}"
        row["servicer_code"] = spec["servicer_code"]
    # A few loans in each status, so every code the servicer uses appears on the tape.
    picks = [int(i) for i in rng.choice(len(rows), size=9, replace=False)]
    for index in picks[:4]:
        rows[index]["days_past_due"] = int(rng.integers(31, 75))
        rows[index]["status"] = "DELINQUENT"
    for index in picks[4:6]:
        rows[index]["status"] = "CHARGED_OFF"
        rows[index]["charge_off_date"] = cutoff.replace(day=int(rng.integers(3, 28)))
        rows[index]["charge_off_amount"] = rows[index]["current_balance"]
    for index in picks[6:]:
        rows[index]["status"] = "REPO"
        rows[index]["repossession_date"] = cutoff.replace(day=int(rng.integers(3, 28)))
    for row in rows:
        row["raw_origination_date"] = row["origination_date"].strftime("%m/%d/%Y")
    _finish_rows(rows, cutoff)
    return rows


def build_backbook(casework: dict[str, Any], cutoff: date, folder: Path) -> list[dict[str, Any]]:
    rng = np.random.default_rng(casework["seed"])
    facts = []
    for spec in casework["backbook"]:
        rows = _rows(rng, spec, cutoff)
        renamed = spec.get("renamed", {})
        extra = spec.get("extra_column")
        codes = spec.get("status_codes", {})
        header = [renamed.get(name, name) for name in COLUMNS]
        if extra:
            header.append(extra["name"])
        blank_dpd = 0
        path = folder / spec["file"]
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle, lineterminator="\n")
            writer.writerow(header)
            for row in rows:
                values = []
                for name in COLUMNS.values():
                    value = _raw_value(row, name)
                    if name == "status":
                        value = codes.get(value, value)
                    # The servicer's export leaves days past due blank for current loans.
                    if name == "days_past_due" and spec.get("blank_dpd_when_current") \
                            and value == 0 and row["status"] == "ACTIVE":
                        value = ""
                        blank_dpd += 1
                    values.append(value)
                if extra:
                    values.append(int(rng.choice([0, 0, 0, 1, 2])))
                writer.writerow(values)
        expected = []
        for column, new in renamed.items():
            expected.append({"kind": "renamed_column", "column": new, "field": COLUMNS[column]})
        if extra:
            expected.append({"kind": "new_column", "column": extra["name"], "field": None})
        if blank_dpd:
            expected.append({"kind": "blank_values", "column": "DPD", "field": "days_past_due",
                             "rows": blank_dpd, "treat_as": 0})
        if codes:
            expected.append({"kind": "code_values", "column": "LoanStatus", "field": "status",
                             "map": {code: status for status, code in codes.items()}})
        facts.append({
            "id": spec["id"], "name": spec["name"], "file": spec["file"],
            "deal_type": spec["deal_type"], "rows": len(rows), "columns": len(header),
            "pool_balance": round(sum(row["current_balance"] for row in rows), 2),
            "exceptions": expected,
        })
    return facts
