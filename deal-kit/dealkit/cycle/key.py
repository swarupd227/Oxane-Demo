"""The cycle answer key: the correct result of every check, written before the demo runs.

The pipeline never reads it. The scorecard compares the run with it.
"""

import copy
import json
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from dealkit.calc import system_view

# US federal holidays that fall in the reporting windows of this cycle.
HOLIDAYS = {date(2026, 5, 25), date(2026, 6, 19)}


def business_day(month_start: date, count: int) -> date:
    """The `count`th business day of the month starting `month_start`."""
    day, seen = month_start, 0
    while True:
        if day.weekday() < 5 and day not in HOLIDAYS:
            seen += 1
            if seen == count:
                return day
        day += timedelta(days=1)


def submissions(cycle: dict[str, Any], files: dict[str, dict[str, str]]) -> list[dict[str, Any]]:
    june_due = business_day(date(2026, 6, 1), 15)
    b, n, k = cycle["bramble"], cycle["northmoor"], cycle["kestrel"]
    kestrel_due = k["quarter_end"] + timedelta(days=60)
    rows = [
        ("bramble", "loan_tape", "Loan tape, May", june_due, b["received"]["loan_tape"]),
        (
            "bramble",
            "servicer_report",
            "Servicer report, May",
            june_due,
            b["received"]["servicer_report"],
        ),
        (
            "bramble",
            "borrowing_base_certificate",
            "Borrowing base certificate, May",
            june_due,
            b["received"]["borrowing_base_certificate"],
        ),
        (
            "bramble",
            "financial_statements",
            "Q1 financial statements",
            date(2026, 5, 15),
            b["received"]["q1_financials"],
        ),
        (
            "bramble",
            "compliance_certificate",
            "Q1 compliance certificate",
            date(2026, 5, 15),
            b["received"]["compliance_certificate"],
        ),
        (
            "bramble",
            "amendment_2",
            "Amendment No. 2",
            b["amendment_2"]["signed"],
            b["received"]["amendment_2"],
        ),
        ("northmoor", "loan_tape_may", "Loan tape, May", june_due, n["received"]["loan_tape"]),
        (
            "northmoor",
            "borrowing_base_certificate_may",
            "Borrowing base certificate, May",
            june_due,
            n["received"]["borrowing_base_certificate"],
        ),
        ("northmoor", "servicer_report_may", "Servicer report, May", june_due, None),
        ("kestrel", "nav_report", "Q1 NAV report", kestrel_due, k["received"]["nav_report"]),
        (
            "kestrel",
            "valuation_report",
            "Q1 valuation report",
            kestrel_due,
            k["received"]["valuation_report"],
        ),
        (
            "kestrel",
            "compliance_certificate",
            "Q1 compliance certificate",
            kestrel_due,
            k["received"]["compliance_certificate"],
        ),
    ]
    result = []
    for facility, doc, label, due, received in rows:
        result.append(
            {
                "facility": facility,
                "document": doc,
                "label": label,
                "due": due.isoformat(),
                "received": received.isoformat() if received else None,
                "file": files[facility].get(doc),
                "status": "received"
                if received and received <= due
                else "late"
                if received is None and cycle["demo_date"] > due
                else "received_late",
            }
        )
    return result


def build_cycle_key(
    deal: dict[str, Any],
    cycle: dict[str, Any],
    bramble: dict[str, Any],
    northmoor: dict[str, Any],
    kestrel: dict[str, Any],
    files: dict[str, dict[str, str]],
    folder: Path,
    larkspur: dict[str, Any],
) -> dict[str, Any]:
    may = copy.deepcopy(deal)
    may["bbc"]["outstanding_advances_usd"] = cycle["bramble"]["outstanding_advances_usd"]
    pool = [row for row in bramble["rows"] if row["status"] not in ("PAID_OFF", "REPURCHASED")]
    view = system_view(pool, may, match_dealers=True)
    june = copy.deepcopy(may)
    for item in june["concentration"]:
        if item["id"] == "C2":
            item["limit_pct"] = cycle["bramble"]["amendment_2"]["dealer_limit_pct"]
    june_view = system_view(pool, june, match_dealers=True)
    certificate = bramble["certificate"]
    system = {
        "eligible_pool": view.eligible_pool / 100,
        "excess": view.excess / 100,
        "borrowing_base": view.borrowing_base / 100,
        "availability": view.availability / 100,
    }

    f, terms = deal["financials"], deal["terms"]
    worth = f["total_equity"] - f["goodwill"] - f["intangibles"] - f["related_party_receivables"]
    carve = min(f["subordinated_debt"], terms["subordinated_debt_cap_usd"] // 1000)
    guarantee = cycle["bramble"]["compliance"]["affiliate_guarantee_k"]
    reported = round((f["total_liabilities"] - carve) / (worth + carve), 2)
    with_guarantee = round((f["total_liabilities"] + guarantee - carve) / (worth + carve), 2)
    shared = northmoor["shared_vin"]
    sunrise = view.concentrations["C2"]

    key = {
        "cycle": {
            "period": cycle["period"]["label"],
            "period_end": cycle["period"]["end"].isoformat(),
            "demo_date": cycle["demo_date"].isoformat(),
            "tolerance_usd": cycle["tolerance_usd"],
        },
        "submissions": submissions(cycle, files),
        "checks": {
            "roll_forward": {k: v for k, v in bramble["roll_forward"].items()},
            "charge_offs": bramble["charge_offs"],
            "terms_version": {
                "may": {
                    "facility_limit": deal["facility"]["limit_usd"],
                    "dealer_limit_pct": 5,
                    "advance_rate_pct": terms["advance_rate_amended_pct"],
                    "version": "Credit Agreement as amended by Amendment No. 1",
                },
                "june": {
                    "facility_limit": cycle["bramble"]["amendment_2"]["limit_usd"],
                    "dealer_limit_pct": cycle["bramble"]["amendment_2"]["dealer_limit_pct"],
                    "advance_rate_pct": terms["advance_rate_amended_pct"],
                    "version": "Credit Agreement as amended by Amendments No. 1 and 2",
                },
                "sunrise": {
                    "share_pct": sunrise["share_pct"],
                    "may_excess": sunrise["excess_cents"] / 100,
                    "june_excess": june_view.concentrations["C2"]["excess_cents"] / 100,
                },
            },
            "bramble_borrowing_base": {
                "system": system,
                "certificate": certificate,
                "eligible_pool_difference": round(
                    certificate["eligible_pool"] - system["eligible_pool"], 2
                ),
                "borrowing_base_difference": round(
                    certificate["borrowing_base"] - system["borrowing_base"], 2
                ),
            },
            "northmoor_borrowing_base": {
                "may": northmoor["borrowing_base"]["may"],
                "status": "pending servicer report",
            },
            "bramble_delinquency": bramble["delinquency"],
            "northmoor_delinquency": northmoor["delinquency"],
            "northmoor_excess_spread": northmoor["excess_spread"],
            "bramble_covenants": {
                "tangible_net_worth_k": worth,
                "liquidity_k": f["unrestricted_cash"],
                "leverage_reported": reported,
                "leverage_with_guarantee": with_guarantee,
                "max_leverage": terms["max_leverage_ratio"],
                "guarantee_k": guarantee,
            },
            "kestrel": kestrel,
            "duplicate_collateral": {"within": {"bramble": 0, "northmoor": 0}, "across": [shared]},
            "northmoor_collections": northmoor["collections"],
            "larkspur": {
                **larkspur["months"],
                "downgrades": larkspur["downgrades"],
                "price_moves": larkspur["price_moves"],
                "identifier_change": larkspur["identifier_change"],
                "par_roll": larkspur["par_roll"],
                "trades": larkspur["trades"],
            },
            "validation": {
                "northmoor": {"blocking": [{"rule": "duplicates", **northmoor["duplicate_line"]}]},
                "bramble": {"warnings": bramble["warnings"]},
                "larkspur": {"warnings": {"not_rated": larkspur["not_rated"]}},
            },
            "prior_period": {
                "bramble": {
                    "pool_balance_change_pct": round(
                        (
                            bramble["roll_forward"]["tape_closing"]
                            / bramble["roll_forward"]["opening"]
                            - 1
                        )
                        * 100,
                        2,
                    ),
                    "new_loans": bramble["roll_forward"]["new_loans"],
                },
            },
        },
        "issues": {
            "M1": {
                "facility": "northmoor",
                "check": "submissions",
                "outcome": "query",
                "summary": "Servicer report, May, not received; chased and escalated",
            },
            "M2": {
                "facility": "bramble",
                "check": "roll_forward",
                "outcome": "query",
                "summary": f"{len(bramble['roll_forward']['missing_loans'])} loans missing "
                "from the May tape",
                "loans": bramble["roll_forward"]["missing_loans"],
                "amount": bramble["roll_forward"]["gap"],
            },
            "M3": {
                "facility": "bramble",
                "check": "charge_offs",
                "outcome": "query",
                "summary": "Charge-offs higher in the servicer report than on the tape",
                "loans": bramble["charge_offs"]["loans"],
                "amount": bramble["charge_offs"]["difference"],
            },
            "M4": {
                "facility": "bramble",
                "check": "terms_version",
                "outcome": "logged",
                "summary": "Amendment No. 2 effective 1 June; May uses the earlier terms",
            },
            "M5": {
                "facility": "northmoor",
                "check": "triggers",
                "outcome": "confirmed",
                "summary": "60+ day delinquency rising towards the 6.0% trigger",
                "average": northmoor["delinquency"]["average"],
            },
            "M6": {
                "facility": "bramble",
                "check": "covenants",
                "outcome": "expert",
                "summary": "Leverage 6.20x if the affiliate guarantee counts, against 6.00x",
                "value": with_guarantee,
            },
            "M7": {
                "facility": "bramble,northmoor",
                "check": "duplicate_collateral",
                "outcome": "confirmed",
                "summary": "One VIN pledged in two facilities",
                "vin": shared["vin"],
            },
            "M8": {
                "facility": "kestrel",
                "check": "nav_ltv",
                "outcome": "expert",
                "summary": "Post-quarter markdown: does it count in NAV for the test?",
                "value": kestrel["ltv_adjusted_pct"],
            },
            "M9": {
                "facility": "kestrel",
                "check": "valuation_freshness",
                "outcome": "query",
                "summary": "One position last valued in December 2025",
                "position": kestrel["stale"][0]["name"],
            },
            "M10": {
                "facility": "northmoor",
                "check": "validation",
                "outcome": "query",
                "summary": "May tape repeats one loan's row: a blocking duplicate holds the load",
                "loan": northmoor["duplicate_line"]["loan_id"],
            },
            "M11": {
                "facility": "larkspur",
                "check": "ccc_bucket",
                "outcome": "confirmed",
                "summary": "A May downgrade takes the CCC bucket over 7.5%; the excess is haircut",
                "issuer": larkspur["downgrades"][0]["issuer"],
                "ccc_pct": larkspur["months"]["may"]["ccc_pct"],
                "haircut": larkspur["months"]["may"]["haircut"],
            },
            "M12": {
                "facility": "larkspur",
                "check": "price_move",
                "outcome": "confirmed",
                "summary": "One loan's bid falls more than 10 points in the month",
                "issuer": larkspur["price_moves"][0]["issuer"],
            },
        },
        "noise": {
            "N1": {
                "facility": "bramble",
                "check": "layout",
                "summary": "Two new tape columns, mapped and logged",
                "columns": list(cycle["bramble"]["new_columns"]),
            },
            "N2": {
                "facility": "northmoor",
                "check": "collections",
                "summary": "May collections dip within last year's seasonal range",
            },
            "N3": {
                "facility": "bramble",
                "check": "borrowing_base",
                "summary": "US$3.20 rounding difference in the certificate",
            },
            "N4": {
                "facility": "bramble",
                "check": "prior_period",
                "summary": "Pool up on April because April and May purchases came together; "
                "explained by the servicer report",
            },
            "N5": {
                "facility": "larkspur",
                "check": "identifiers",
                "summary": "One loan's LoanX ID and CUSIP changed; linked, not sold and bought",
                "old": larkspur["identifier_change"]["old_loanx"],
                "new": larkspur["identifier_change"]["new_loanx"],
            },
        },
    }
    _verify(key, cycle)
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "key.json").write_text(
        json.dumps(key, indent=2, default=str) + "\n", encoding="utf-8"
    )
    return key


def add_review_scenarios(key: dict[str, Any], cycle: dict[str, Any], ravenglass: dict[str, Any],
                         wharfedale: dict[str, Any], daily: dict[str, Any]) -> None:
    """The RFP review's scenarios: a middle-market facility, a subscription line and the CLO
    daily feeds. Added after the original key, which they leave as it was."""
    key["checks"]["ravenglass"] = ravenglass
    key["checks"]["wharfedale"] = wharfedale
    key["checks"]["larkspur_daily"] = daily
    r, w = ravenglass, wharfedale
    key["issues"] |= {
        "M13": {"facility": "ravenglass", "check": "obligor_covenants", "outcome": "confirmed",
                "summary": f"{r['breach']['name']}: leverage {r['breach']['leverage']:.2f}x "
                f"against a {r['breach']['max_leverage']:.2f}x maximum; out of the base",
                "obligor": r["breach"]["id"], "value": r["breach"]["leverage"]},
        "M14": {"facility": "ravenglass", "check": "addbacks", "outcome": "expert",
                "summary": f"{r['addbacks']['name']}: add-backs of "
                f"{r['addbacks']['addback_pct']:.0f}% of EBITDA; leverage passes or breaches "
                "on how the cap is read",
                "obligor": r["addbacks"]["id"], "readings": r["addbacks"]["readings"]},
        "M15": {"facility": "ravenglass", "check": "obligor_financials", "outcome": "query",
                "summary": f"{r['missing']['name']}: Q1 financials not delivered; excluded from "
                "the borrowing base", "obligor": r["missing"]["id"]},
        "M16": {"facility": "ravenglass", "check": "covenant_terms", "outcome": "logged",
                "summary": f"{r['waiver']['name']}: waiver raises maximum leverage from "
                f"{r['waiver']['original']:.2f}x to {r['waiver']['amended']:.2f}x for Q1",
                "obligor": r["waiver"]["id"]},
        "M17": {"facility": "wharfedale", "check": "investor_exclusion", "outcome": "confirmed",
                "summary": f"{w['exclusion']['name']} downgraded to {w['exclusion']['to']}: "
                "excluded, borrowing base below the loans outstanding",
                "investor": w["exclusion"]["id"],
                "prepayment": w["after_exclusion"]["prepayment"]},
        "M18": {"facility": "wharfedale", "check": "investor_concentration",
                "outcome": "confirmed",
                "summary": f"{w['concentration']['name']} over the single-investor limit after "
                "the exclusion", "investor": w["concentration"]["id"],
                "excess": w["concentration"]["excess"]},
        "M19": {"facility": "wharfedale", "check": "notice_reconciliation", "outcome": "query",
                "summary": f"Register has not posted capital call {w['capital_call']['number']} "
                f"for {w['register']['stale']['name']}",
                "investor": w["register"]["stale"]["id"]},
        "M20": {"facility": "larkspur", "check": "daily_feeds", "outcome": "query",
                "summary": f"No bid price file for {daily['missing'][0]['as_of']}",
                "as_of": daily["missing"][0]["as_of"]},
    }
    key["noise"] |= {
        "N6": {"facility": "ravenglass", "check": "obligor_covenants",
               "summary": f"{r['rounding']['name']}: fund reports {r['rounding']['reported']:.2f}x"
               f", recomputed {r['rounding']['recomputed']:.2f}x; within tolerance"},
        "N7": {"facility": "wharfedale", "check": "notice_reconciliation",
               "summary": f"Distribution notice {w['distribution']['number']} reconciles to the "
               "register, recallable amount added back"},
        "N8": {"facility": "larkspur", "check": "daily_feeds",
               "summary": f"Position file for {daily['late'][0]['as_of']} arrived after its "
               "deadline, complete"},
    }
    _verify_review(key, cycle)


def _verify_review(key: dict[str, Any], cycle: dict[str, Any]) -> None:
    r, w = key["checks"]["ravenglass"], key["checks"]["wharfedale"]
    daily = key["checks"]["larkspur_daily"]
    assert r["obligors"] == 40 and r["received"] == 39, r["obligors"]
    assert r["breach"]["leverage"] > r["breach"]["max_leverage"], r["breach"]
    readings = r["addbacks"]["readings"]
    assert readings["as_reported"] <= r["addbacks"]["max_leverage"] < readings[
        "integration_capped"] <= readings["all_capped"], readings
    assert r["waiver"]["original"] < r["waiver"]["leverage"] <= r["waiver"]["amended"]
    assert r["rounding"]["recomputed"] - r["rounding"]["reported"] == 0.01 or abs(
        r["rounding"]["recomputed"] - r["rounding"]["reported"] - 0.01) < 1e-9
    assert sorted(r["excluded"].values()) == ["Material Obligor Event",
                                               "financials not delivered"], r["excluded"]
    assert r["availability"] > 0 and r["certificate_difference"] > 0, r
    assert r["largest_obligor"]["pct"] <= 7.5 and r["largest_sector"]["pct"] <= 20, r
    assert len(r["layouts"]) == 4 and len(r["certificate_forms"]) == 2
    assert w["before_exclusion"]["prepayment"] == 0 < w["after_exclusion"]["prepayment"], w
    assert not w["before_exclusion"]["concentration_excess"], w["before_exclusion"]
    assert w["concentration"]["share_pct"] > 15 and w["concentration"]["excess"] > 0
    assert w["register"]["stale"]["difference"] > 0
    assert daily["expected"] == 60 and daily["received"] == 59, daily
    assert cycle["ravenglass"]["obligors"] == r["obligors"]


def _verify(key: dict[str, Any], cycle: dict[str, Any]) -> None:
    """The numbers the script quotes must hold, or the kit is not built."""
    checks = key["checks"]
    roll = checks["roll_forward"]
    planted = cycle["bramble"]["planted"]
    assert abs(roll["gap"] - planted["m2_gap_usd"]) <= 500, roll["gap"]
    assert abs(roll["gap"] - roll["missing_balance"]) < 0.02, roll
    assert abs(checks["charge_offs"]["difference"] - planted["m3_charge_off_usd"]) <= 1500
    bb = checks["bramble_borrowing_base"]
    assert abs(bb["eligible_pool_difference"] - planted["n3_rounding_usd"]) < 0.005, bb
    assert abs(bb["borrowing_base_difference"]) < cycle["tolerance_usd"], bb
    nd = checks["northmoor_delinquency"]
    assert (nd["march"], nd["april"], nd["may"]) == (5.10, 5.60, 6.60), nd
    assert nd["average"] == 5.77 and nd["june_breach_above"] == 5.80, nd
    assert checks["bramble_covenants"]["leverage_reported"] == 5.28
    assert checks["bramble_covenants"]["leverage_with_guarantee"] == 6.20
    kestrel = checks["kestrel"]
    assert (kestrel["ltv_reported_pct"], kestrel["ltv_adjusted_pct"]) == (30.3, 32.2), kestrel
    assert [s["age_days"] for s in kestrel["stale"]] == [106], kestrel["stale"]
    assert kestrel["largest_position_pct"] <= cycle["kestrel"]["max_single_position_pct"]
    assert kestrel["top_five_pct"] <= cycle["kestrel"]["max_top_five_pct"]
    collections = checks["northmoor_collections"]
    assert collections["last_may_vs_april"] <= collections["may_vs_april"] < 1, collections
    spread = checks["northmoor_excess_spread"]
    assert (spread["march"]["pct"], spread["april"]["pct"]) == (4.30, 4.10), spread
    lark = checks["larkspur"]
    assert lark["april"]["ccc_pct"] < 7.5 < lark["may"]["ccc_pct"], lark["may"]["ccc_pct"]
    assert lark["april"]["haircut"] == 0 < lark["may"]["haircut"], lark["may"]
    assert [d["issuer"] for d in lark["downgrades"]] == ["Kettlewell Auto Parts"]
    assert [m["issuer"] for m in lark["price_moves"]] == ["Denholme Chemicals"]
    roll_par = lark["par_roll"]
    assert roll_par["april"] - roll_par["sold"] + roll_par["bought"] == roll_par["may"]
    late = [s for s in key["submissions"] if s["status"] == "late"]
    assert [(s["facility"], s["document"]) for s in late] == [("northmoor", "servicer_report_may")]
