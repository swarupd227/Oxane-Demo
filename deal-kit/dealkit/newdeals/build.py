"""Build the two test deals from newdeals.yaml.

python -m dealkit.newdeals.build

Each deal gets an onboarding pack, the next month's submission and a key. The key is for tests
only; the pipeline never reads it.
"""

import hashlib
import json
import shutil
from datetime import date
from pathlib import Path
from typing import Any

import yaml

from dealkit.config import OUTPUT_DIR, ROOT
from dealkit.newdeals import documents, tapes

NEWDEALS_FILE = ROOT / "newdeals.yaml"
NEWDEALS_DIR = OUTPUT_DIR / "newdeals"
MANIFEST = ROOT / "newdeals.manifest.json"


def load() -> dict[str, Any]:
    return yaml.safe_load(NEWDEALS_FILE.read_text(encoding="utf-8"))


def _consumer_eligible(deal: dict[str, Any], row: tapes.Row) -> list[str]:
    e = deal["eligibility"]
    failed = []
    if row["days_past_due"] > e["max_days_past_due"]:
        failed.append("days_past_due")
    if row["credit_score"] < e["min_credit_score"]:
        failed.append("credit_score")
    if row["original_term"] > e["max_original_term"]:
        failed.append("original_term")
    if row["current_balance"] > e["max_current_balance"]:
        failed.append("current_balance")
    if row["apr"] > float(e["max_apr"]):
        failed.append("apr")
    if row["obligor_state"] in e["restricted_states"]:
        failed.append("obligor_state")
    if row["status"] in e["excluded_statuses"]:
        failed.append("status")
    return failed


def _sme_eligible(deal: dict[str, Any], row: tapes.Row) -> list[str]:
    e = deal["eligibility"]
    failed = []
    if row["days_past_due"] > e["max_days_past_due"]:
        failed.append("days_past_due")
    if row["risk_grade"] > e["max_risk_grade"]:
        failed.append("risk_grade")
    if row["original_balance"] > e["max_original_principal"]:
        failed.append("original_balance")
    if row["remaining_term"] > e["max_remaining_term"]:
        failed.append("remaining_term")
    if row["sector"] in e["excluded_sectors"]:
        failed.append("sector")
    if row["status"] in e["excluded_statuses"]:
        failed.append("status")
    return failed


def _summary(rows: list[tapes.Row], check: Any) -> dict[str, Any]:
    by_field: dict[str, int] = {}
    eligible = 0.0
    count = 0
    for row in rows:
        failed = check(row)
        for name in failed:
            by_field[name] = by_field.get(name, 0) + 1
        if not failed:
            eligible += row["current_balance"]
            count += 1
    return {
        "loans": len(rows),
        "eligible_loans": count,
        "eligible_pool": round(eligible, 2),
        "failures_by_field": by_field,
        "gross_pool": round(sum(row["current_balance"] for row in rows), 2),
    }


def build_consumer(deal: dict[str, Any], folder: Path) -> dict[str, Any]:
    onboarding, monthly = folder / "onboarding", folder / "monthly"
    rows = tapes.consumer_tape(deal)
    tapes.write_consumer_csv(rows, onboarding / deal["tape"]["file"])
    documents.consumer_agreement(deal, onboarding / "Harbourline_Loan_and_Security_Agreement.pdf")
    documents.consumer_amendment(deal, onboarding / "Harbourline_First_Amendment.pdf")
    documents.client_model(deal, onboarding / deal["client_model"]["file"])
    closed = ("CHARGED_OFF", "PAID_OFF")
    september = documents.servicer_report(
        deal,
        rows,
        deal["tape"]["cutoff"],
        onboarding / "Harbourline_Servicer_Report_September_2026.pdf",
        None,
        closed,
        {
            f"{date.fromisoformat(k + '-01'):%B %Y}": v
            for k, v in deal["tape"]["history_pct"].items()
        },
    )
    later_rows, facts = tapes.consumer_later(deal, rows)
    tapes.write_consumer_csv(later_rows, monthly / deal["later"]["file"])
    history = {
        f"{date.fromisoformat(k + '-01'):%B %Y}": v
        for k, v in list(deal["tape"]["history_pct"].items())[1:]
    }
    history["September 2026"] = f"{september:.2f}"
    october = documents.servicer_report(
        deal,
        later_rows,
        deal["later"]["cutoff"],
        monthly / deal["later"]["report"],
        facts,
        closed,
        history,
    )
    return {
        "deal_type": deal["deal_type"],
        "client": deal["lender"]["name"],
        "facility": deal["borrower"]["name"],
        "terms": {
            "commitment": deal["commitment_usd"],
            "advance_rate": deal["amendment"]["advance_rate_pct"],
            "advance_rate_original": deal["advance_rate_pct"],
            "reserve": deal["reserve_pct"],
            "delinquency_trigger": deal["triggers"]["delinquency"]["limit_pct"],
            "net_loss_trigger": deal["triggers"]["net_loss"]["limit_pct"],
        },
        "rules": {"eligibility": 7, "concentration": 4},
        "onboarding": _summary(rows, lambda r: _consumer_eligible(deal, r)),
        "client_model_differences": ["advance_rate"],
        "september_delinquency_pct": september,
        "october_delinquency_pct": october,
        "later": {**facts, "loans": len(later_rows)},
    }


def build_sme(deal: dict[str, Any], folder: Path) -> dict[str, Any]:
    onboarding, monthly = folder / "onboarding", folder / "monthly"
    rows = tapes.sme_tape(deal)
    tapes.write_sme_xlsx(rows, onboarding / deal["tape"]["file"])
    documents.sme_agreement(deal, onboarding / "Fenwick_Receivables_Financing_Agreement.pdf")
    later_rows, facts = tapes.sme_later(deal, rows)
    tapes.write_sme_xlsx(
        later_rows,
        monthly / deal["later"]["file"],
        deal["later"]["renamed"],
        deal["later"]["added"],
        deal["seed"] + 2,
    )
    closed = ("WRITTEN_OFF", "REPAID")
    history = {
        f"{date.fromisoformat(k + '-01'):%B %Y}": v
        for k, v in list(deal["tape"]["history_pct"].items())[1:]
    }
    history["September 2026"] = f"{tapes.delinquency_pct(rows, 30, closed):.2f}"
    october = documents.servicer_report(
        deal,
        later_rows,
        deal["later"]["cutoff"],
        monthly / deal["later"]["report"],
        facts,
        closed,
        history,
    )
    return {
        "deal_type": deal["deal_type"],
        "client": deal["lender"]["name"],
        "facility": deal["borrower"]["name"],
        "terms": {
            "commitment": deal["commitment_usd"],
            "advance_rate": deal["advance_rate_pct"],
            "reserve": None,
            "delinquency_trigger": deal["triggers"]["delinquency"]["limit_pct"],
        },
        "rules": {"eligibility": 6, "concentration": 4},
        "onboarding": _summary(rows, lambda r: _sme_eligible(deal, r)),
        "october_delinquency_pct": october,
        "later": {
            **facts,
            "loans": len(later_rows),
            "renamed": deal["later"]["renamed"],
            "added": deal["later"]["added"],
        },
    }


def build_newdeals() -> dict[str, str]:
    deals = load()
    shutil.rmtree(NEWDEALS_DIR, ignore_errors=True)
    keys = {
        deals["consumer"]["id"]: build_consumer(
            deals["consumer"], NEWDEALS_DIR / deals["consumer"]["id"]
        ),
        deals["sme"]["id"]: build_sme(deals["sme"], NEWDEALS_DIR / deals["sme"]["id"]),
    }
    for ident, key in keys.items():
        (NEWDEALS_DIR / ident / "key.json").write_text(
            json.dumps(key, indent=2, default=str) + "\n", encoding="utf-8"
        )
    return {
        path.relative_to(OUTPUT_DIR).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(NEWDEALS_DIR.rglob("*"))
        if path.is_file()
    }


def main() -> None:
    manifest = build_newdeals()
    MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"Built {len(manifest)} files in {NEWDEALS_DIR}")


if __name__ == "__main__":
    main()
