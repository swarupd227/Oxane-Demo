"""The RFP review's scenarios: a middle-market back-leverage facility, a subscription line, and
document schedules with the CLO daily feeds. Code computes every figure; model steps that are
not recorded fall back to code and are listed as pending, never invented."""

import io

import pytest
from conftest import RECORDED_RUN
from fastapi.testclient import TestClient
from openpyxl import load_workbook

from app.config import settings
from app.main import app
from app.monitoring import workbook
from app.pipeline.gateway import BudgetExceeded, Gateway, Usage

client = TestClient(app)
RECORDED_CYCLE = settings.cycle_dir

pytestmark = pytest.mark.skipif(
    not (RECORDED_CYCLE / "cycle.json").exists(), reason="No monitoring cycle has been recorded"
)


@pytest.fixture(autouse=True)
def fresh_cycle(seed_view, monkeypatch):
    monkeypatch.setattr(settings, "pipeline_dir", RECORDED_RUN)
    client.post("/api/monitoring/session/reset")


def cycle():
    return client.get("/api/monitoring/cycle").json()


def act(kind: str, actor: str = "analyst", headers: dict | None = None, **payload):
    return client.post("/api/monitoring/session/events", headers=headers or {},
                       json={"type": kind, "actor": actor, "payload": payload})


def finding(prefix: str) -> dict:
    return next(i for i in cycle()["findings"] if i["id"].startswith(prefix))


# Middle-market


def test_every_obligor_is_tested_and_the_breach_leaves_the_base():
    t = cycle()["tests"]["ravenglass"]
    assert len(t["obligors"]) == 40 and t["received"] == 39
    breach = next(o for o in t["obligors"] if not o["leverage_passed"])
    assert breach["leverage"] > breach["max_leverage"] and not breach["eligible"]
    excluded = {b["obligor"]: b["reason"] for b in t["borrowing_base"]["excluded"]}
    assert sorted(excluded.values()) == ["Material Obligor Event", "Q1 financials not delivered"]
    bb = t["borrowing_base"]
    # The fund's certificate keeps both excluded loans: the difference is exactly their value.
    assert abs(bb["difference"] - bb["bridged"]) < 0.01


def test_the_waiver_sets_the_level_and_its_quote_is_found():
    t = cycle()["tests"]["ravenglass"]
    change = t["covenant_changes"][0]
    assert change["verified"] and change["source"]["page"] == 1
    waived = next(o for o in t["obligors"] if o["id"] == change["obligor"])
    assert waived["original_max_leverage"] < waived["leverage"] <= waived["max_leverage"]
    assert waived["eligible"]
    assert finding("F-ravenglass-waiver")["rule_outcome"] == "logged"


def test_add_backs_over_the_cap_go_to_an_expert_with_each_reading():
    item = finding("F-ravenglass-addbacks")
    assert item["suggested"]["outcome"] == "expert"
    t = cycle()["tests"]["ravenglass"]
    flagged = next(o for o in t["obligors"] if o["addbacks_flagged"])
    readings = [r["leverage"] for r in flagged["readings"]]
    assert readings == sorted(readings) and flagged["readings"][0]["passed"]
    assert not flagged["readings"][-1]["passed"]


def test_unrecorded_model_steps_are_listed_and_their_code_fallbacks_ran():
    c = cycle()
    pending = {p["task"] for p in c["pending_recording"]}
    if not pending:
        pytest.skip("The review's model steps are recorded")
    assert pending <= {"read_obligor_financials", "read_covenant_notice", "suggest_triage",
                       "draft_pack", "draft_status_brief"}
    t = c["tests"]["ravenglass"]
    assert t["extraction"]["status"] == "pending"
    assert all(o["basis"] == "portfolio_report" for o in t["obligors"])
    rvg = [i for i in c["findings"] if i["facility"] == "ravenglass"]
    assert all(i["suggested"]["by"] == "Rule" for i in rvg)
    pack = next(p for p in c["packs"] if p["facility"] == "ravenglass")
    assert pack["pending_recording"] and pack["unknown_placeholders"] == []
    assert pack["numbers_in_text"] == []
    # The original recordings still replay: 16 calls, none of them new.
    assert c["usage"]["calls"] == 16


def test_every_obligor_document_is_in_a_stored_layout():
    c = cycle()
    t = c["tests"]["ravenglass"]
    assert all(o["layout"] and o["certificate_layout"] for o in t["obligors"] if o["received"])
    library = {e["id"]: e for e in c["mapping"]["library"]}
    assert sum(library[k]["count"] for k in t["layouts"] if k.startswith("LAY-060")) == 39
    assert len({k for k in t["layouts"] if k.startswith("LAY-060")}) == 4


# Subscription line


def test_the_downgrade_excludes_the_investor_and_forces_a_prepayment():
    t = cycle()["tests"]["wharfedale"]
    assert [x["rating"] for x in t["exclusions"]] == ["BB+"] and t["unapplied"]
    bb, before = t["borrowing_base"], t["before_exclusion"]
    assert before["prepayment"] == 0 < bb["prepayment"]
    assert abs(bb["prepayment"] - (bb["drawn"] - bb["borrowing_base"])) < 0.01
    assert t["largest"]["share_pct"] > bb["single_limit_pct"] and bb["concentration_reduction"]


def test_notices_reconcile_and_the_stale_register_entry_is_queried():
    t = cycle()["tests"]["wharfedale"]
    assert t["notices"]["capital_call"]["reconciles"] and t["notices"]["distribution"]["reconciles"]
    assert len(t["register_breaks"]) == 1
    assert finding("F-wharfedale-register")["suggested"]["outcome"] == "query"
    assert finding("F-wharfedale-distribution")["rule_outcome"] == "logged"


def test_the_subscription_line_runs_on_code_only():
    c = cycle()
    items = [i for i in c["findings"] if i["facility"] == "wharfedale"]
    assert items and all(i["suggested"]["by"] == "Rule" for i in items)
    assert next(p for p in c["packs"] if p["facility"] == "wharfedale")["ai"] is False
    assert next(u for u in c["usage"]["by_client"] if u["client"] == "thornbury")["calls"] == 0


# Schedules and daily feeds


def test_every_facility_has_a_schedule_from_its_template():
    c = cycle()
    schedules = {s["facility"]: s for s in c["schedules"]}
    assert set(schedules) >= {f["id"] for f in c["facilities"]}
    assert len(schedules) == len(c["facilities"]) + len(c["book"]["facilities"])
    assert schedules["larkspur"]["template"] == "CLO / BSL"
    assert schedules["ravenglass"]["template"] == "Middle-market"
    oc = next(x for x in schedules["larkspur"]["lines"] if x["document"] == "OC/IC tests")
    assert oc["status"] == "not_applicable"


def test_the_clo_daily_feeds_flag_one_late_day_and_one_gap():
    daily = cycle()["daily_feeds"]
    assert daily["expected"] == 60 and daily["received"] == 59
    feeds = {f["feed"]: f for f in daily["feeds"]}
    assert feeds["positions"]["late"] == ["2026-05-14"] and feeds["prices"]["missing"] == [
        "2026-05-21"]
    assert finding("F-feed-larkspur-prices-gap")["suggested"]["outcome"] == "query"
    assert finding("F-feed-larkspur-positions-late")["rule_outcome"] == "logged"
    gap = next(d for d in daily["coverage"] if d["as_of"] == "2026-05-21")
    assert not gap["price_file"] and gap["unpriced"] == gap["positions"]


# Scoring, workbooks and hand-offs


def test_the_scorecard_scores_the_new_issues_and_keeps_the_old_ones():
    card = client.get("/api/monitoring/scorecard").json()
    ids = [i["id"] for i in card["issues"]]
    assert ids == [f"M{n}" for n in range(1, 21)] and all(i["found"] for i in card["issues"])
    assert [n["id"] for n in card["noise"]] == [f"N{n}" for n in range(1, 9)]
    assert not any(n["raised"] for n in card["noise"])


def test_review_workbooks_carry_formulas_and_source_notes():
    data = cycle()
    for facility, sheet in (("ravenglass", "Obligors"), ("wharfedale", "Investors")):
        content, _ = workbook.build(data, client.get("/api/monitoring/session").json(), facility)
        book = load_workbook(io.BytesIO(content))
        rows = list(book[sheet].iter_rows(min_row=2))
        assert any(str(c.value).startswith("=") for r in rows for c in r)
        noted = [c for r in rows for c in r if c.comment]
        assert noted and all(c.comment.text.startswith("Source:") for c in noted)


def test_a_confirmed_finding_hands_off_to_the_client_contact():
    item = finding("F-wharfedale-exclusion")
    response = act("triage", id=item["id"], outcome="confirmed",
                   headers={"X-Acting-User": "priya"})
    assert response.status_code == 200
    laura = client.get("/api/work", headers={"X-Acting-User": "laura"}).json()
    titles = [w["title"] for w in laura["waiting"]]
    assert any("Prepayment notice" in t for t in titles), titles
    james = client.get("/api/work", headers={"X-Acting-User": "james"}).json()
    assert not any("Prepayment notice" in w["title"] for w in james["waiting"])


def test_once_recorded_the_obligor_figures_come_from_the_documents(monkeypatch, tmp_path):
    """A test double stands in for the model, reading each figure off the page with its line
    as the quote, so the recorded path (quote check, units, recomputation) is exercised."""
    import re
    from decimal import Decimal

    from app.monitoring import cycle as pipeline
    from app.monitoring import middle_market as mm
    from app.monitoring import steps

    labels = {"Consolidated EBITDA": ("EBITDA", "Consolidated EBITDA", "LTM EBITDA"),
              "Net debt": ("Net debt", "Total Net Debt"),
              "Interest expense": ("Interest expense", "Finance costs", "Net interest",
                                   "Interest Expense", "Cash interest expense")}

    def read(gateway, documents, definition):
        out = []
        for fs, cc in zip(documents[::2], documents[1::2], strict=True):
            oid = re.search(r"RVG-\d{3}", fs.id).group(0)
            text = fs.pages[0].raw + "\n" + cc.pages[0].raw
            unit = "US$ millions" if "US$m" in text or "US$ millions" in text else "US$ thousands"
            figures = []
            for name, starts in labels.items():
                line = next(x for x in text.splitlines() if x.strip().startswith(starts)
                            and re.search(r"\d", x))
                figures.append(steps.Figure(name=name, value=re.findall(
                    r"\(?\d[\d,]*(?:\.\d+)?\)?", line)[-1], quote=line.strip()))
            out.append(steps.ObligorReading(obligor_id=oid, unit=unit, figures=figures,
                                            addbacks=[]))
        return steps.ObligorBatch(obligors=out)

    monkeypatch.setattr(mm.steps, "read_obligor_financials", read)
    meta = pipeline.record()
    rvg = pipeline.facility("ravenglass")
    subs = pipeline.collect_items(mm.submissions(rvg, pipeline.cycle_path("ravenglass")),
                                  meta["cycle"]["as_of"])
    t = mm.tests(Gateway(mode="replay", fixtures=tmp_path), pipeline.Evidence(), meta,
                 pipeline.cycle_path("ravenglass"), subs, mm.Pending())
    assert t["extraction"]["status"] == "recorded"
    extracted = [o for o in t["obligors"] if o["basis"] == "extracted"]
    assert len(extracted) >= 30
    replayed = cycle()["tests"]["ravenglass"]["obligors"]
    by_id = {o["id"]: o for o in replayed}
    for o in extracted:
        if not by_id[o["id"]]["addbacks_k"]:
            assert Decimal(str(o["leverage"])) == Decimal(str(by_id[o["id"]]["leverage"])), o["id"]


def test_the_recording_budget_stops_before_a_live_call(tmp_path):
    class Spent:
        def request(self, payload):
            return "{}", Usage("", 1_000_000, 0)

    from app.monitoring.steps import CovenantNotice

    gateway = Gateway(mode="record", fixtures=tmp_path, client_factory=Spent, budget_usd=0.0)
    with pytest.raises(BudgetExceeded):
        gateway.parse("any", "", [{"type": "text", "text": "x"}], CovenantNotice)
    assert not list(tmp_path.rglob("*.json"))
