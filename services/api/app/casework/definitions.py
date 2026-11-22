"""Nested definitions: check the model's trace of defined terms, then resolve it with code.

The model only reads: it says which term relies on which, and quotes each definition. Code finds
every quote on its page, checks every reference resolves to a term it traced (or to a document
the pack does not hold), looks for circular inputs, and then works out each term's value with the
rules engine, so the chain on screen ends in numbers code computed.
"""

import re
from collections import defaultdict
from decimal import ROUND_HALF_EVEN, Decimal
from typing import Any

from engine.covenants import delinquency_ratio
from engine.rules import RuleSet, describe
from engine.run import Loan, RunResult

from app.casework.steps import DefinitionTrace
from app.pipeline.documents import PdfDocument, find_citation

ROOTS = ["Borrowing Base", "Delinquency Ratio"]


def key_of(name: str) -> str:
    """One spelling per term: lower case, no article, singular."""
    text = re.sub(r"^(the|a|an)\s+", "", name.strip().strip('"').lower())
    text = re.sub(r"\s+", " ", text)
    words = text.split(" ")
    last = words[-1]
    if len(last) > 4 and last.endswith("s") and not last.endswith("ss"):
        words[-1] = last[:-1]
    return " ".join(words)


def _usd(cents: int | Decimal) -> str:
    return f"US${Decimal(cents) / 100:,.2f}"


def check_trace(trace: DefinitionTrace, documents: dict[str, PdfDocument]) -> dict[str, Any]:
    nodes: dict[str, dict[str, Any]] = {}
    for item in trace.terms:
        key = key_of(item.term)
        if key in nodes:
            continue
        amendment = (find_citation(documents, "amendment_1", item.amendment_quote)
                     if item.amendment_quote else None)
        nodes[key] = {
            "key": key, "term": item.term, "document": item.document, "clause": item.clause,
            "quote": item.quote, "source": find_citation(documents, item.document, item.quote),
            "amended_by": item.amended_by, "amendment_quote": item.amendment_quote,
            "amendment_source": amendment,
            "refers_to": [{"target": ref.target, "key": key_of(ref.target), "role": ref.role}
                          for ref in item.refers_to],
        }
    # The model may add a note to a document's name: "Schedule 4 - Restricted ... (...)".
    outside = {key_of(re.split(r" \(| - | – ", name)[0]): name for name in trace.not_in_pack}
    unresolved, mentioned = [], []
    for node in nodes.values():
        for ref in node["refers_to"]:
            if ref["key"] in nodes:
                ref["status"] = "traced"
            elif ref["key"] in outside:
                ref["status"] = "not_in_pack"
            elif ref["role"] == "context":
                ref["status"] = "mentioned"
                mentioned.append(ref["target"])
            else:
                ref["status"] = "untraced"
                unresolved.append(f"{node['term']} relies on {ref['target']}")

    inputs = {key: [r["key"] for r in node["refers_to"] if r["role"] == "input"
                    and r["key"] in nodes] for key, node in nodes.items()}
    roles = {(key, r["key"]): r["role"] for key, node in nodes.items()
             for r in node["refers_to"] if r["key"] in nodes}
    every = {key: [r["key"] for r in node["refers_to"] if r["key"] in nodes]
             for key, node in nodes.items()}
    depth = _depths(inputs, [key_of(root) for root in ROOTS])
    for key, node in nodes.items():
        node["depth"] = depth.get(key)
    return {
        "nodes": list(nodes.values()),
        "not_in_pack": trace.not_in_pack,
        "checks": {
            "quotes": len(nodes),
            "quotes_found": sum(1 for n in nodes.values() if n["source"]),
            "unverified": [n["term"] for n in nodes.values() if not n["source"]],
            "amendment_quotes_unverified": [n["term"] for n in nodes.values()
                                            if n["amendment_quote"] and not n["amendment_source"]],
            "unresolved_references": unresolved,
            "mentioned_only": sorted(set(mentioned)),
            "input_cycles": _cycles(inputs, nodes),
            # Mutual references that are not circular: one side only mentions the other.
            "mutual_references": [
                cycle for cycle in _cycles(every, nodes)
                if _mixed(cycle, roles) and all(depth.get(key_of(t)) is not None for t in cycle)
            ],
        },
    }


def _mixed(cycle: list[str], roles: dict[tuple[str, str], str]) -> bool:
    pairs = [(key_of(a), key_of(b)) for a, b in zip(cycle, [*cycle[1:], cycle[0]], strict=True)]
    kinds = {roles.get(pair) for pair in pairs}
    return "input" in kinds and "context" in kinds and len(cycle) <= 3


def _depths(edges: dict[str, list[str]], roots: list[str]) -> dict[str, int]:
    depth = {root: 0 for root in roots if root in edges}
    frontier = list(depth)
    while frontier:
        following = []
        for key in frontier:
            for target in edges.get(key, []):
                if target not in depth:
                    depth[target] = depth[key] + 1
                    following.append(target)
        frontier = following
    return depth


def _cycles(edges: dict[str, list[str]], nodes: dict[str, dict[str, Any]]) -> list[list[str]]:
    """Each cycle once, as the terms in order. A cycle of inputs would make a value circular."""
    found: set[tuple[str, ...]] = set()

    def walk(path: list[str]) -> None:
        for target in edges.get(path[-1], []):
            if target == path[0]:
                low = min(range(len(path)), key=lambda i: path[i])
                found.add(tuple(path[low:] + path[:low]))
            elif target not in path and target > path[0]:
                walk([*path, target])

    for start in sorted(edges):
        walk([start])
    return [[nodes[key]["term"] for key in cycle] for cycle in sorted(found)]


def _pct(value: Decimal) -> str:
    return f"{value.normalize():f}%"


def resolve(checked: dict[str, Any], result: RunResult, loans: list[Loan], ruleset: RuleSet,
            answers: dict[str, Any]) -> dict[str, Any]:
    """Code's value for each term it knows. The chain is the model's; every number is code's."""
    by_status: defaultdict[str, list[Loan]] = defaultdict(list)
    for loan in loans:
        by_status[loan["status"]].append(loan)
    eligible = len(result.eligible_loan_ids)
    pool = result.eligible_pool_cents
    rates = sorted(ruleset.advance_rates, key=lambda rate: rate.effective_from)
    rate = result.advance_rate_pct
    c4 = next((r for r in ruleset.concentration if r.effective_from), None)
    not_run = [rule_id for rule_id, item in result.rules.items()
               if item.status == "not_evaluated"]
    literal = delinquency_ratio(loans)
    without_repossessed = delinquency_ratio([x for x in loans if x["status"] != "REPO"])
    late = [x for x in loans if x["days_past_due"] >= 90 and x["status"] != "CHARGED_OFF"]
    policy_days = answers.get("charge_off_days")
    beyond_policy = ([x for x in loans if x["status"] != "CHARGED_OFF"
                      and x["days_past_due"] >= policy_days] if policy_days else None)
    excess_groups = [f"{name} {_usd(amount)}" for item in result.concentrations.values()
                     for name, amount in item.excess_by_group.items()]

    recomputed = (((Decimal(pool - result.excess_cents) * rate / 100)
                   .to_integral_value(rounding=ROUND_HALF_EVEN)) - result.reserve_cents)
    values: dict[str, dict[str, Any]] = {
        "borrowing base": {
            "value": _usd(result.borrowing_base_cents),
            "rule": "(Eligible Pool Balance - Excess Concentration Amount) x Advance Rate "
                    "- Reserve Amount",
            "worked": f"({_usd(pool)} - {_usd(result.excess_cents)}) x {_pct(rate)} - "
                      f"{_usd(result.reserve_cents)}",
            "check": int(recomputed) == result.borrowing_base_cents,
        },
        "eligible pool balance": {
            "value": _usd(pool),
            "rule": "Sum of the Outstanding Balance of every Pool Receivable that is an "
                    "Eligible Receivable",
            "worked": f"{eligible:,} eligible receivables",
            "check": pool == sum(x["current_balance"] for x in loans
                                 if x["loan_id"] in set(result.eligible_loan_ids)),
        },
        "eligible receivable": {
            "value": f"{eligible:,} of {len(loans):,}",
            "rule": "A Pool Receivable that meets every criterion in Schedule 1",
            "worked": f"{len(loans) - eligible:,} fail at least one criterion"
                      + (f"; criterion {', '.join(not_run)} not yet run" if not_run else ""),
        },
        "pool receivable": {
            "value": f"{len(loans):,} receivables",
            "worked": f"{_usd(result.gross_pool_cents)} on the April tape",
        },
        "outstanding balance": {"value": "Tape column CurrBal",
                                "worked": "Mapped to current_balance, held in cents"},
        "schedule 1": {
            "value": f"{len(ruleset.eligibility)} criteria",
            "rule": "; ".join(f"{r.id}: {describe(r.test)}" for r in ruleset.eligibility),
            "worked": f"{len(ruleset.eligibility) - len(not_run)} run"
                      + (f", {', '.join(not_run)} waits for Schedule 4" if not_run else ""),
        },
        "schedule 2": {
            "value": f"{len(ruleset.concentration)} limits",
            "rule": "; ".join(f"{r.id} {r.limit_pct}%" for r in ruleset.concentration),
            "worked": (f"{c4.id} applies from {c4.effective_from:%d %B %Y}" if c4 else ""),
        },
        "excess concentration amount": {
            "value": _usd(result.excess_cents),
            "rule": "Amount above each limit in Schedule 2, in schedule order, counted once",
            "worked": "; ".join(excess_groups) or "No limit exceeded",
        },
        "advance rate": {
            "value": _pct(rate),
            "rule": "; ".join(f"{_pct(r.pct)} from {r.effective_from:%d %b %Y} ({r.source})"
                              for r in rates),
            "worked": f"In effect on {result.as_of:%d %B %Y}: {result.advance_rate_source}",
        },
        "reserve amount": {
            "value": _usd(result.reserve_cents),
            "rule": f"{_pct(ruleset.reserve_pct)} x Eligible Pool Balance",
            "worked": f"{_pct(ruleset.reserve_pct)} x {_usd(pool)}",
            "check": result.reserve_cents == int((Decimal(pool) * ruleset.reserve_pct / 100)
                                                 .to_integral_value(rounding=ROUND_HALF_EVEN)),
        },
        "delinquency ratio": {
            "value": _pct(literal),
            "rule": "Outstanding Balance 60 or more days past due / Outstanding Balance of all "
                    "Pool Receivables, both excluding Defaulted Receivables that have been "
                    "charged off",
            "worked": f"Repossessed included; {_pct(without_repossessed)} if excluded",
            "alternative": _pct(without_repossessed),
        },
        "defaulted receivable": {
            "value": f"{len(by_status['CHARGED_OFF'])} charged off, "
                     f"{len(by_status['REPO'])} repossessed",
            "rule": "Charged off or due to be under the Credit and Collection Policy; obligor "
                    "insolvent; vehicle repossessed; or otherwise uncollectible",
            "worked": (f"{len(late)} at 90+ days past due, not charged off; "
                       + (f"{len(beyond_policy or [])} past the {policy_days}-day charge-off "
                          "period (Q-03)" if policy_days else "charge-off period not received")),
        },
        "collection period": {"value": "April 2026", "worked": "Calendar month to 30 April 2026"},
    }
    values["section 2.3"] = values["advance rate"]
    values["concentration limit"] = values["schedule 2"]
    for node in checked["nodes"]:
        node["resolved"] = values.get(node["key"])
    return {
        "borrowing_base_reproduced": values["borrowing base"]["check"],
        "delinquency": {"literal": float(literal), "without_repossessed":
                        float(without_repossessed)},
    }
