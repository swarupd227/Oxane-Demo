"""The onboarding pipeline: the team's other cases, at summary level.

casework.yaml names each case, its client, deal type, stage and dates. Everything counted or
summed here is worked out from the seed and the deal type's profile: the first tape's records and
pool balance, documents received, terms extracted and approved, rules configured, exceptions and
client queries, open QC variances and business days in stage. The same seed always gives the
same file, so the list never disagrees with itself between builds.
"""

import json
import math
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any

import numpy as np


def business_days(start: date, end: date) -> int:
    return int(np.busday_count(start, end)) if end > start else 0


def _weekday(day: date) -> date:
    while day.weekday() >= 5:
        day += timedelta(days=1)
    return day


def _case(rng: np.random.Generator, spec: dict[str, Any], profile: dict[str, Any],
          stage: int, as_of: date) -> dict[str, Any]:
    low, high = profile["records"]
    records = int(rng.integers(low, high + 1))
    spread = float(profile["spread"])
    balances = rng.lognormal(math.log(profile["balance"]) - spread**2 / 2, spread, records)
    pool = round(float(balances.sum()), 2)

    documents = int(profile["documents"])
    received = documents if stage >= 1 else int(rng.integers(2, documents))
    terms = int(profile["terms"])
    extracted = terms if stage >= 1 else 0
    if stage == 1:
        approved = int(terms * rng.uniform(0.25, 0.6))
    elif stage == 2:
        approved = terms - int(rng.integers(1, 4))
    else:
        approved = terms if stage >= 3 else 0
    rules = int(profile["rules"]) if stage >= 2 else 0

    exceptions = int(rng.integers(6, 15)) if stage >= 1 else 0
    queries = int(rng.integers(3, 10)) if stage >= 2 else (int(rng.integers(0, 3)) if stage else 0)
    open_exceptions = with_client = 0
    if stage == 1:
        open_exceptions, with_client = exceptions - int(rng.integers(0, 3)), queries
    elif stage == 2:
        open_exceptions = int(rng.integers(2, 6))
        with_client = int(rng.integers(2, queries + 1))
    elif stage == 3:
        open_exceptions, with_client = int(rng.integers(0, 2)), int(rng.integers(0, 2))
    variances = int(rng.integers(0, 3)) if stage == 3 else 0

    entered = date.fromisoformat(str(spec["stage_entered"]))
    opened = date.fromisoformat(str(spec["opened"]))
    last = as_of - timedelta(days=int(rng.integers(0, 4)) + (6 if stage == 4 else 0))
    while last.weekday() >= 5:
        last -= timedelta(days=1)
    last_at = datetime.combine(last, time(int(rng.integers(9, 16)), int(rng.integers(0, 60))))
    target = None if stage == 4 else _weekday(as_of + timedelta(days=int(rng.integers(12, 45))))
    return {
        "number": spec["number"],
        "client": spec["client"],
        "facility": spec["facility"],
        "deal_type": spec["deal_type"],
        "stage": spec["stage"],
        "limit_usd": spec["limit_usd"],
        "owner": spec["owner"],
        "opened": opened.isoformat(),
        "stage_entered": entered.isoformat(),
        "went_live": entered.isoformat() if stage == 4 else None,
        "target_go_live": target.isoformat() if target else None,
        "business_days_open": business_days(opened, as_of),
        "business_days_in_stage": business_days(entered, as_of),
        "records": records,
        "pool_balance": pool,
        "documents": {"expected": documents, "received": received},
        "terms": {"total": terms, "extracted": extracted, "approved": approved},
        "rules": rules,
        "exceptions": {"total": exceptions, "open": open_exceptions},
        "queries": {"total": queries, "with_client": with_client},
        "qc_variances_open": variances,
        "last_activity": last_at.isoformat(),
    }


def build_pipeline(casework: dict[str, Any], folder: Path) -> dict[str, Any]:
    spec = casework["pipeline"]
    rng = np.random.default_rng(spec["seed"])
    as_of = date.fromisoformat(str(spec["as_of"]))
    stages = spec["stages"]
    cases = [_case(rng, case, spec["profiles"][case["deal_type"]], stages.index(case["stage"]),
                   as_of) for case in spec["cases"]]
    pipeline = {
        "as_of": as_of.isoformat(),
        "stages": stages,
        "team": spec["team"],
        "cases": cases,
        "backbook": {deal: {"number": item["number"], "opened": str(item["opened"])}
                     for deal, item in spec["backbook"].items()},
    }
    (folder / spec["file"]).write_text(
        json.dumps(pipeline, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return pipeline
