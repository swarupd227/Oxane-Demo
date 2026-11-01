"""Load the deal pack into the engine and shape its results for the workbench."""

import csv
import json
import re
from dataclasses import asdict
from datetime import date
from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from typing import Any

from engine.covenants import (
    CovenantTerms,
    Financials,
    delinquency_ratio,
    delinquency_trigger,
    evaluate_covenants,
    leverage_without_carve_out,
)
from engine.reconcile import (
    Certificate,
    borrower_rules,
    bridge_borrowing_base,
    bridge_eligible_pool,
    impact,
)
from engine.rules import RuleSet, describe, load_ruleset
from engine.run import Loan, RunResult, coerce_loan, run, to_cents, weighted_average
from openpyxl import load_workbook

from app.config import settings
from app.deal import load_deal

PERIOD_END = date(2026, 4, 30)
SUNRISE = {"Sunrise Motors": "Sunrise Motors LLC"}
OUTSTANDING_CENTS = 4_800_000_000


def read_key(name: str) -> Any:
    path = settings.deal_kit_output / "answer-key" / f"{name}.json"
    return json.loads(path.read_text(encoding="utf-8"))


def pack_path(file_name: str) -> Path:
    return settings.deal_kit_output / "pack" / file_name


def _pipeline_file(name: str) -> Path | None:
    path = settings.pipeline_dir / name
    return path if path.exists() else None


def _active(name: str) -> Any:
    """Use the pipeline's own output once a run exists. The key only backs the seed view."""
    path = _pipeline_file(f"{name}.json")
    return json.loads(path.read_text(encoding="utf-8")) if path else read_key(name)


def reset() -> None:
    """Forget cached inputs, after a pipeline run has replaced them."""
    for cached in (rules, tape_rows, loans, certificate):
        cached.cache_clear()


def active_files() -> list[str]:
    return list(_active("pack").values())


@lru_cache
def rules() -> RuleSet:
    path = _pipeline_file("ruleset.json") or settings.ruleset_file
    return load_ruleset(path.read_text(encoding="utf-8"))


@lru_cache
def tape_rows() -> tuple[dict[str, str], ...]:
    with pack_path(_active("pack")["loan_tape"]).open(encoding="utf-8", newline="") as handle:
        return tuple(csv.DictReader(handle))


@lru_cache
def loans() -> tuple[Loan, ...]:
    columns = _active("mapping")["columns"]
    return tuple(coerce_loan({columns[k]: v for k, v in row.items()}) for row in tape_rows())


@lru_cache
def certificate() -> Certificate:
    book = load_workbook(pack_path(_active("pack")["borrowing_base_certificate"]))
    sheet = book["BBC Summary"]

    def money(cell: str) -> int:
        return to_cents(Decimal(str(sheet[cell].value)))

    stated = {row[0].value: row[1].value
              for row in book["Ineligible Detail"].iter_rows(min_row=2)}
    days = re.search(r"(\d+) days", stated["1"])
    if days is None:
        raise ValueError("Certificate does not state its past-due test")
    return Certificate(
        eligible_pool_cents=money("B7"),
        excess_cents=-money("B8"),
        advance_rate_pct=Decimal(str(sheet["B9"].value)) * 100,
        reserve_cents=-money("B10"),
        borrowing_base_cents=money("B11"),
        outstanding_advances_cents=money("B12"),
        availability_cents=money("B13"),
        thresholds={"E1": Decimal(days.group(1))},
        rules_not_applied=frozenset({"E7", "E12"}),
    )


def _usd(cents: int) -> float:
    return cents / 100


def _loan_row(loan: Loan, rules_failed: tuple[str, ...]) -> dict[str, Any]:
    return {
        "loan_id": loan["loan_id"],
        "balance": _usd(loan["current_balance"]),
        "days_past_due": loan["days_past_due"],
        "status": loan["status"],
        "fico": loan["fico"],
        "state": loan["obligor_state"],
        "dealer": loan["dealer_name"],
        "vin": loan["vin"],
        "vehicle": f"{loan['model_year']} {loan['vehicle_make']} {loan['vehicle_model']}",
        "rules_failed": list(rules_failed),
    }


def _figures(result: RunResult) -> dict[str, Any]:
    return {
        "gross_pool": _usd(result.gross_pool_cents),
        "eligible_pool": _usd(result.eligible_pool_cents),
        "excess": _usd(result.excess_cents),
        "advance_rate_pct": float(result.advance_rate_pct),
        "reserve": _usd(result.reserve_cents),
        "borrowing_base": _usd(result.borrowing_base_cents),
        "outstanding": _usd(result.outstanding_advances_cents),
        "availability": _usd(result.availability_cents),
    }


def _covenant_inputs() -> dict[str, Any]:
    """Read from the statements after a pipeline run. The seed view uses the deal file."""
    facts = _pipeline_file("facts.json")
    if facts:
        return json.loads(facts.read_text(encoding="utf-8"))
    raw = load_deal().model_extra or {}
    f, t, history = raw["financials"], raw["terms"], raw["servicer_history"]
    return {
        "financials": {name: f[name] for name in (
            "total_equity", "goodwill", "intangibles", "related_party_receivables",
            "subordinated_debt", "total_liabilities", "unrestricted_cash")},
        "delinquency_history": [history["february_pct"], history["march_pct"]],
        "covenants": {
            "min_tangible_net_worth": t["min_tangible_net_worth_usd"],
            "max_leverage_ratio": t["max_leverage_ratio"],
            "min_liquidity": t["min_liquidity_usd"],
            "subordinated_debt_cap": t["subordinated_debt_cap_usd"],
            "delinquency_trigger_pct": t["delinquency_trigger_pct"],
        },
    }


def _covenants() -> dict[str, Any]:
    facts = _covenant_inputs()
    figures = Financials(**facts["financials"])
    limits = facts["covenants"]
    terms = CovenantTerms(
        min_tangible_net_worth=limits["min_tangible_net_worth"] // 1000,
        max_leverage_ratio=Decimal(str(limits["max_leverage_ratio"])),
        min_liquidity=limits["min_liquidity"] // 1000,
        subordinated_debt_cap=limits["subordinated_debt_cap"] // 1000,
    )
    february, march, *_ = facts["delinquency_history"]
    april = delinquency_ratio(list(loans()))
    trigger = delinquency_trigger(
        (Decimal(str(february)), Decimal(str(march)), april),
        Decimal(str(limits["delinquency_trigger_pct"])),
    )
    return {
        "tests": [
            {**asdict(item), "value": float(item.value), "limit": float(item.limit)}
            for item in evaluate_covenants(figures, terms)
        ],
        "leverage_without_carve_out": float(leverage_without_carve_out(figures)),
        "delinquency": {
            "monthly_pct": [february, march, float(april)],
            "average_pct": float(trigger.average_pct),
            "trigger_pct": float(trigger.trigger_pct),
            "tripped": trigger.tripped,
        },
    }


def validation_run(dealer_match: bool) -> dict[str, Any]:
    tape, ruleset, stated = list(loans()), rules(), certificate()
    aliases = SUNRISE if dealer_match else {}
    result = run(tape, ruleset, PERIOD_END, OUTSTANDING_CENTS, dealer_aliases=aliases)
    bridge = bridge_eligible_pool(tape, ruleset, result, stated, PERIOD_END)
    base = bridge_borrowing_base(bridge, result, stated)
    replay = run(tape, borrower_rules(ruleset, stated), PERIOD_END, OUTSTANDING_CENTS)
    by_id = {loan["loan_id"]: loan for loan in tape}

    def rows(ids: tuple[str, ...]) -> list[dict[str, Any]]:
        ordered = sorted(ids, key=lambda i: -by_id[i]["current_balance"])
        return [_loan_row(by_id[i], result.failed_rules_by_loan.get(i, ())) for i in ordered]

    labels = {rule.id: rule.plain_english for rule in ruleset.eligibility}
    labels |= {rule.id: rule.plain_english for rule in ruleset.concentration}
    return {
        "digest": result.digest,
        "provisional": result.provisional,
        "not_evaluated": [rule_id for rule_id, item in result.rules.items()
                          if item.status == "not_evaluated"],
        "dealer_match": dealer_match,
        "system": _figures(result),
        "borrower": _figures(replay),
        "pool_bridge": {
            "borrower": _usd(bridge.borrower_cents),
            "system": _usd(bridge.system_cents),
            "gap": _usd(bridge.gap_cents),
            "unexplained": _usd(bridge.unexplained_cents),
            "reproduces_certificate": bridge.reproduces_certificate,
            "lines": [
                {"rule_id": line.rule_id, "label": line.label, "loans": len(line.loan_ids),
                 "amount": _usd(line.amount_cents), "rows": rows(line.loan_ids)}
                for line in bridge.lines
            ],
        },
        "base_bridge": {
            "borrower": _usd(base.borrower_cents),
            "system": _usd(base.system_cents),
            "lines": [{"label": label, "amount": _usd(amount)} for label, amount in base.lines],
        },
        "rules": [
            {"id": rule_id, "label": labels[rule_id], "status": item.status,
             "failed": len(item.failed_loan_ids), "failed_amount": _usd(item.failed_cents)}
            for rule_id, item in result.rules.items()
        ],
        "concentrations": [
            {"id": item.rule_id, "label": labels[item.rule_id], "largest": item.largest,
             "share_pct": float(item.share_pct), "limit_pct": float(item.limit_pct),
             "excess": _usd(item.excess_cents), "active": item.active}
            for item in result.concentrations.values()
        ],
        "covenants": _covenants(),
        "weighted_average_apr": round(
            float(weighted_average(tape, result.eligible_loan_ids, "apr")), 2),
    }


def rule_preview(rule_id: str, value: Decimal) -> dict[str, Any]:
    tape, ruleset = list(loans()), rules()
    before = run(tape, ruleset, PERIOD_END, OUTSTANDING_CENTS)
    after = run(tape, ruleset.with_threshold(rule_id, value), PERIOD_END, OUTSTANDING_CENTS)
    change = impact(before, after)
    return {
        "newly_ineligible": len(change.newly_ineligible),
        "newly_eligible": len(change.newly_eligible),
        "eligible_pool_change": _usd(change.eligible_pool_change_cents),
        "borrowing_base_change": _usd(change.borrowing_base_change_cents),
    }


def rule_views() -> list[dict[str, Any]]:
    ruleset = rules()
    views = [
        {"id": rule.id, "group": "eligibility", "plain_english": rule.plain_english,
         "clause_ref": rule.clause_ref, "clause_text": rule.clause_text,
         "logic": describe(rule.test), "threshold": _threshold(rule.test),
         "status": "not_evaluated" if rule.id == "E7" else "ready"}
        for rule in ruleset.eligibility
    ]
    views += [
        {"id": rule.id, "group": "concentration", "plain_english": rule.plain_english,
         "clause_ref": rule.clause_ref, "clause_text": rule.clause_text,
         "logic": f"largest group <= {rule.limit_pct}% of eligible pool" if rule.group_by
         else f"share({describe(rule.where)}) <= {rule.limit_pct}% of eligible pool",
         "threshold": None, "status": "ready",
         "effective_from": rule.effective_from.isoformat() if rule.effective_from else None}
        for rule in ruleset.concentration
    ]
    return views


def _threshold(test: Any) -> float | None:
    right = getattr(test, "right", None)
    return float(right.value) if right is not None and right.kind == "const" else None
