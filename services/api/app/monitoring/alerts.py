"""Client self-service alerts and covenant headroom.

A client asks for an alert in plain English. The model turns the words into one structured rule
on a metric from the client's own catalogue, grounded in the ontology. Code then checks the rule
(the facility is the client's, the metric exists, the threshold is the number the client wrote,
the concepts are ones it was given), back-tests it on the facility's history, and holds it until
an analyst approves it. Only this client's facilities are in its catalogue.
"""

import re
from decimal import Decimal
from typing import Any

from engine.alerts import AlertRule, InvalidRule, back_test, check_rule, headroom

from app.monitoring import steps
from app.pipeline import ontology


def normalise_request(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip())


def catalogue(record: dict[str, Any], client_id: str) -> dict[str, dict[str, Any]]:
    mine = {f["id"] for f in record["facilities"] if f["client"] == client_id}
    return {key: value for key, value in record["alert_metrics"].items()
            if key.split(".")[0] in mine}


def history(record: dict[str, Any], cycle: dict[str, Any]) -> dict[str, list[tuple[str, float]]]:
    """Each alertable metric's values: earlier cycles from the record, this one from code."""
    t = cycle["tests"]
    past = {k: [(str(p), float(v)) for p, v in items]
            for k, items in record.get("history", {}).items()}
    trend = cycle["reconciliation"]["delinquency_trend"]
    bramble_months = [(m, v["value"]) for m, v in trend.items()
                      if re.fullmatch(r"(February|March|April) 2026", m)]
    k_ltv = [*past.get("kestrel.loan_to_value", []), ("Q1 2026", t["kestrel"]["ltv"]["reported"])]
    limit = t["kestrel"]["ltv"]["limit"]
    return {
        "bramble.delinquency_60_plus": [
            *bramble_months, ("May 2026", t["bramble"]["delinquency"]["monthly"][-1]["value"])],
        "bramble.availability_usd": [
            *past.get("bramble.availability_usd", []),
            ("May 2026", t["bramble"]["borrowing_base"]["system"]["availability"])],
        "bramble.leverage_ratio": [*past.get("bramble.leverage_ratio", []),
                                   ("Q1 2026", t["bramble"]["leverage"]["recomputed"])],
        "northmoor.delinquency_60_plus": [
            (m["month"], m["value"]) for m in t["northmoor"]["delinquency"]["monthly"]],
        "northmoor.excess_spread": [
            (m["month"], m["value"]) for m in t["northmoor"]["excess_spread_months"]],
        "kestrel.loan_to_value": k_ltv,
        "kestrel.ltv_headroom_pts": [(p, round(limit - v, 2)) for p, v in k_ltv],
        "larkspur.ccc_share": [*past.get("larkspur.ccc_share", []),
                               ("Apr 2026", t["larkspur"]["april"]["ccc_pct"]),
                               ("May 2026", t["larkspur"]["borrowing_base"]["ccc_pct"])],
    }


def number_in_request(threshold: Decimal, request: str) -> bool:
    """The threshold must be a number the client wrote, allowing for 'million' and 'thousand'."""
    lowered = request.lower().replace(",", "")
    for found in re.finditer(r"(\d+(?:\.\d+)?)\s*(million|m\b|thousand|k\b|bn|billion)?",
                             lowered):
        value = Decimal(found.group(1))
        scale = {"million": 10**6, "m": 10**6, "thousand": 1000, "k": 1000, "bn": 10**9,
                 "billion": 10**9}.get((found.group(2) or "").strip(), 1)
        if value * scale == threshold:
            return True
    return False


def draft(gateway: Any, record: dict[str, Any], cycle: dict[str, Any], client_id: str,
          request: str) -> dict[str, Any]:
    request = normalise_request(request)
    metrics = catalogue(record, client_id)
    offered = {
        key: {"label": m["label"], "unit": m["unit"], "concept": m["concept"]}
        for key, m in metrics.items()
    }
    concepts = {m["concept"] for m in metrics.values()} | {"alert_threshold"}
    reading = steps.draft_alert(gateway, request, offered, concepts)
    return check(record, cycle, client_id, request, reading.model_dump())


def check(record: dict[str, Any], cycle: dict[str, Any], client_id: str, request: str,
          drafted: dict[str, Any]) -> dict[str, Any]:
    """Code's verdict on a drafted rule, and when it would have fired."""
    metrics = catalogue(record, client_id)
    mine = {f["id"] for f in record["facilities"] if f["client"] == client_id}
    problems = []
    rule = None
    if not drafted["understood"]:
        problems.append(drafted["question"] or "The request did not match a metric.")
    else:
        try:
            threshold = Decimal(drafted["threshold"].replace(",", ""))
        except ArithmeticError:
            threshold = Decimal(-10**12)
            problems.append(f"{drafted['threshold']} is not a number")
        facility, _, metric = drafted["metric"].partition(".")
        rule = AlertRule(facility, metric, drafted["operator"], threshold)
        try:
            check_rule(rule, {k: {"unit": v["unit"], "range": v["range"]}
                              for k, v in metrics.items()}, mine)
        except InvalidRule as invalid:
            problems.append(str(invalid))
        if not number_in_request(threshold, request):
            problems.append(f"The threshold {drafted['threshold']} is not a number the client "
                            "wrote")
        unknown = sorted(set(drafted["concepts"]) - set(ontology.concepts()))
        if unknown:
            problems.append(f"Unknown ontology concepts: {', '.join(unknown)}")
    fired = []
    if rule and not problems:
        series = history(record, cycle).get(drafted["metric"], [])
        fired = [{"period": p, "value": float(v), "fires": f}
                 for p, v, f in back_test(rule, [(p, Decimal(str(v))) for p, v in series])]
    entry = metrics.get(drafted["metric"], {})
    return {
        "request": request,
        "client": client_id,
        "drafted": drafted,
        "rule": {"facility": rule.facility, "metric": rule.metric, "operator": rule.operator,
                 "threshold": float(rule.threshold), "unit": entry.get("unit", ""),
                 "label": entry.get("label", rule.metric)} if rule else None,
        "valid": rule is not None and not problems,
        "problems": problems,
        "back_test": fired,
        "fires": sum(1 for f in fired if f["fires"]),
        "by": "AI",
    }


# Covenant headroom across facilities

BANDS = {"%": Decimal("0.5"), "x": Decimal("0.5"), "US$": Decimal(5_000_000), "days": Decimal(15)}


def _row(facility: str, test: str, clause: str, value: float, limit: float, direction: str,
         unit: str, series: list[tuple[str, float]], band: Decimal | None = None,
         note: str = "", source: Any = None) -> dict[str, Any]:
    prior = Decimal(str(series[-2][1])) if len(series) > 1 else None
    h = headroom(Decimal(str(value)), Decimal(str(limit)), direction, band or BANDS[unit], prior)
    return {
        "facility": facility, "test": test, "clause": clause, "value": value, "limit": limit,
        "direction": direction, "unit": unit, "headroom": float(h.headroom),
        "used_pct": float(h.used_pct), "passed": h.passed, "early_warning": h.early_warning,
        "trend": h.trend, "series": [{"period": p, "value": v} for p, v in series],
        "note": note, "source": source,
    }


def headroom_view(record: dict[str, Any], cycle: dict[str, Any]) -> list[dict[str, Any]]:
    t = cycle["tests"]
    b, n, k, lark = t["bramble"], t["northmoor"], t["kestrel"], t["larkspur"]
    series = history(record, cycle)

    sunrise = b["borrowing_base"]["sunrise"]
    rows = [
        _row("bramble", "60+ day delinquency, three-month average", b["delinquency"]["clause"],
             b["delinquency"]["average"], b["delinquency"]["limit"], "max", "%",
             series["bramble.delinquency_60_plus"]),
        _row("bramble", "Leverage ratio", "Section 6.12(b)", b["leverage"]["recomputed"],
             b["leverage"]["maximum"], "max", "x", series["bramble.leverage_ratio"],
             note=f"{b['leverage']['with_guarantees']:.2f}x if the affiliate guarantee counts: "
             "with an expert", source=b["leverage"]["reported_source"]),
        _row("bramble", "Availability", "Section 2.3",
             b["borrowing_base"]["system"]["availability"], 0, "min", "US$",
             series["bramble.availability_usd"]),
        _row("bramble", "Largest dealer share", "Schedule 2", sunrise["share_pct"], 5, "max", "%",
             [("May 2026", sunrise["share_pct"])],
             note=f"Excess of US${sunrise['excess']:,.0f} deducted; limit 7% from 1 Jun"),
        _row("northmoor", "60+ day delinquency, three-month average",
             n["delinquency"]["clause"], n["delinquency"]["average"], n["delinquency"]["limit"],
             "max", "%", [(m["month"], m["value"]) for m in n["delinquency"]["monthly"]],
             note=f"June breaches above {n['delinquency']['next_month_breaches_beyond']:.2f}%",
             source=n["delinquency"]["source"]),
        _row("northmoor", "Excess spread, average", n["excess_spread"]["clause"],
             n["excess_spread"]["average"], n["excess_spread"]["limit"], "min", "%",
             [(m["month"], m["value"]) for m in n["excess_spread_months"]],
             note="Two of three months; May waits for the servicer report"),
        _row("kestrel", "Loan-to-value", k["ltv"]["clause"], k["ltv"]["reported"],
             k["ltv"]["limit"], "max", "%", series["kestrel.loan_to_value"], Decimal(3),
             note=f"{k['ltv']['with_markdown']:.1f}% with the post-quarter markdown: with an "
             "expert", source=k["nav_source"]),
        _row("kestrel", "Largest investment", k["concentration"]["clause"],
             k["concentration"]["largest_pct"], k["concentration"]["largest_limit"], "max", "%",
             [("Q1 2026", k["concentration"]["largest_pct"])], Decimal(2)),
        _row("kestrel", "Five largest investments", k["concentration"]["clause"],
             k["concentration"]["top_five_pct"], k["concentration"]["top_five_limit"], "max",
             "%", [("Q1 2026", k["concentration"]["top_five_pct"])], Decimal(2)),
        _row("larkspur", "CCC share", "Section 1.1", lark["borrowing_base"]["ccc_pct"],
             lark["borrowing_base"]["ccc_limit_pct"], "max", "%", series["larkspur.ccc_share"],
             note=f"Excess of US${lark['borrowing_base']['ccc_excess']:,.0f} carried at market "
             "value", source=lark["ccc_source"]),
        _row("larkspur", "Availability", "Section 2.3", lark["borrowing_base"]["availability"], 0,
             "min", "US$", [("Apr 2026", lark["april"]["availability"]),
                            ("May 2026", lark["borrowing_base"]["availability"])],
             Decimal(10_000_000)),
    ]
    return rows


def early_warning_indicators(cycle: dict[str, Any]) -> list[dict[str, Any]]:
    """Signals some clients ask for beyond the contract tests: ratings and price moves."""
    lark = cycle["tests"]["larkspur"]
    items = [
        {"facility": "larkspur", "kind": "Rating downgrade", "subject": d["issuer"],
         "detail": f"{'/'.join(d['before'])} to {'/'.join(d['after'])}"
         + (", now in the CCC bucket" if d["into_ccc"] else ""), "source": lark["warning_source"]}
        for d in lark["downgrades"]
    ] + [
        {"facility": "larkspur", "kind": "Price move", "subject": m["issuer"],
         "detail": f"Bid {m['before']:.2f} to {m['after']:.2f}, down {abs(m['change']):.2f} points",
         "source": lark["warning_source"]}
        for m in lark["price_moves"]
    ]
    n = cycle["tests"]["northmoor"]["delinquency"]["monthly"]
    if len(n) >= 3 and n[0]["value"] < n[1]["value"] < n[2]["value"]:
        items.append({"facility": "northmoor", "kind": "Rising trend", "subject":
                      "60+ day delinquency", "detail": " to ".join(f"{m['value']:.2f}%"
                                                                    for m in n),
                      "source": None})
    for event in cycle["tests"]["kestrel"]["ltv"]["events"]:
        items.append({"facility": "kestrel", "kind": "Valuation event", "subject":
                      event["position"], "detail": f"Marked down US${event['amount'] / 1e6:,.0f}m "
                      "after the quarter", "source": event["source"]})
    return items
