"""The pitch brief's Use Case 2 controls, enforced by the API: validation blocks, QC variances,
approval levels per client, the no-AI client, client alerts, Excel with live formulas, status
briefs, mapping memory per client and the 5b scorecard."""

import io
import re

import pytest
from conftest import RECORDED_RUN
from fastapi.testclient import TestClient
from openpyxl import load_workbook

from app.config import settings
from app.main import app
from app.monitoring import clients as policy
from app.monitoring import workbook
from app.monitoring.cycle import record
from app.pipeline.gateway import Gateway

client = TestClient(app)
pytestmark = pytest.mark.skipif(
    not (settings.cycle_dir / "cycle.json").exists(), reason="No monitoring cycle has been recorded"
)


@pytest.fixture(autouse=True)
def fresh_cycle(seed_view, monkeypatch):
    monkeypatch.setattr(settings, "pipeline_dir", RECORDED_RUN)
    client.post("/api/monitoring/session/reset")


def act(kind: str, actor: str = "analyst", **payload):
    return client.post(
        "/api/monitoring/session/events", json={"type": kind, "actor": actor, "payload": payload}
    )


def cycle():
    return client.get("/api/monitoring/cycle").json()


def session():
    return client.get("/api/monitoring/session").json()


def decide(facility: str) -> None:
    for item in cycle()["findings"]:
        if item["rule_outcome"] is None and facility in item["facility"].split(","):
            response = act("triage", id=item["id"], outcome=item["suggested"]["outcome"])
            assert response.status_code == 200, response.json()


# Validate


def test_validation_runs_every_rule_family_with_blocking_and_warning_rules():
    feeds = cycle()["validation"]["feeds"]
    families = {r["family"] for f in feeds for r in f["rules"]}
    assert families >= {"missing_data", "duplicates", "reference_data", "data_types", "logical"}
    assert any(f["prior_period"] for f in feeds)
    severities = {r["severity"] for f in feeds for r in f["rules"]}
    assert severities == {"blocking", "warning"}


def test_a_blocking_failure_holds_the_northmoor_pack_until_resolved():
    decide("northmoor")
    assert session()["held"]["northmoor"]
    refused = act("approve-pack", "approver", facility="northmoor")
    assert refused.status_code == 409 and "blocking" in refused.json()["detail"]
    assert act("resolve-block", facility="northmoor").status_code == 409  # needs a note
    assert act("resolve-block", facility="northmoor",
               note="Servicer confirmed the line was sent twice").status_code == 200
    assert not session()["held"]["northmoor"]
    assert act("approve-pack", "approver", facility="northmoor").status_code == 200
    assert session()["packs"]["northmoor"]


def test_the_prior_period_change_is_explained_with_a_found_quote():
    feed = next(f for f in cycle()["validation"]["feeds"] if f["facility"] == "bramble")
    explanation = feed["explanation"]
    assert explanation["verified"] and explanation["source"]
    numbers = re.findall(r"\d[\d,]*(?:\.\d+)?", re.sub(r"\{\{\w+\}\}", "", explanation["cause"]))
    assert all(n in explanation["quote"] for n in numbers)
    item = next(i for i in cycle()["findings"] if i["id"].startswith("F-change-bramble"))
    assert item["suggested"] == {**item["suggested"], "outcome": "logged", "by": "AI"}


# Calculate and report: QC and Excel


def test_qc_variances_are_classified_and_a_genuine_one_holds_release():
    qc = cycle()["qc"]
    classes = {line["class"] for f in qc.values() for line in f["lines"]}
    assert classes == {"agrees", "blank", "rounding", "sign", "percent", "genuine"}
    assert qc["bramble"]["genuine"] == ["Gross charge-offs"]
    decide("bramble")
    refused = act("approve-pack", "approver", facility="bramble")
    assert refused.status_code == 409 and "QC" in refused.json()["detail"]
    note = "QC used the servicer report; the nine loans are under query"
    assert act("resolve-qc", facility="bramble", line="Gross charge-offs",
               note=note).status_code == 200
    assert act("approve-pack", "approver", facility="bramble").status_code == 200


@pytest.mark.parametrize("facility", ["bramble", "northmoor", "kestrel", "larkspur"])
def test_workbook_formulas_give_the_platform_figures(facility):
    data = cycle()
    content, values = workbook.build(data, session(), facility)
    book = load_workbook(io.BytesIO(content))
    formulas = [c.value for c in book["Calculation"]["B"][1:] if c.value]
    assert formulas and all(str(f).startswith("=") for f in formulas)
    inputs = [c for c in book["Inputs"]["B"][1:] if c.value is not None]
    assert inputs and all(c.comment and c.comment.text.startswith("Source:") for c in inputs)
    assert "PROVISIONAL" in book["Summary"]["A2"].value
    platform = {line["line"]: line["platform"] for line in data["qc"][facility]["lines"]}
    expected = {
        "bramble": [("Borrowing base", "Borrowing base"), ("Availability", "Availability"),
                    ("Eligible pool", "Eligible pool balance")],
        "northmoor": [("Three-month average", "Three-month average"),
                      ("June level that breaches", "June level that breaches")],
        "kestrel": [("Loan-to-value, with markdown", "Loan-to-value, with markdown"),
                    ("Five largest investments", "Five largest investments")],
        "larkspur": [("CCC excess adjustment", "CCC excess adjustment"),
                     ("Borrowing base", "Borrowing base"), ("CCC share", "CCC share")],
    }[facility]
    for calc_name, qc_line in expected:
        assert abs(values[calc_name] - platform[qc_line]) < 0.006, calc_name
    assert "QC comparison" in book.sheetnames


def test_workbook_download_says_provisional_until_released():
    response = client.get("/api/monitoring/workbook/kestrel.xlsx")
    assert response.status_code == 200 and "provisional" in response.headers[
        "content-disposition"]
    decide("kestrel")
    assert act("approve-pack", "approver", facility="kestrel").status_code == 200
    released = client.get("/api/monitoring/workbook/kestrel.xlsx")
    assert "released" in released.headers["content-disposition"]
    book = load_workbook(io.BytesIO(released.content))
    assert book["Summary"]["A2"].value.startswith("RELEASED")


# Review: approval levels per client


def test_thornbury_needs_a_third_level_from_a_different_person():
    decide("larkspur")
    assert act("approve-pack", "senior", facility="larkspur").status_code == 409
    assert act("approve-pack", "approver", facility="larkspur").status_code == 200
    state = session()
    assert state["provisional"]["larkspur"] and "larkspur" not in state["packs"]
    assert act("approve-pack", "approver", facility="larkspur").status_code == 409
    assert act("approve-pack", "senior", facility="larkspur").status_code == 200
    assert not session()["provisional"]["larkspur"]


def test_calderwood_needs_two_levels():
    assert [lv["actor"] for lv in session()["levels"]["kestrel"]] == ["approver"]
    assert [lv["actor"] for lv in session()["levels"]["larkspur"]] == ["approver", "senior"]


# Data handling: the client that does not permit AI


def test_the_no_ai_client_makes_no_model_calls_and_gets_rule_suggestions():
    data = cycle()
    usage = {c["client"]: c for c in data["usage"]["by_client"]}
    assert usage["thornbury"]["calls"] == 0 and usage["calderwood"]["calls"] > 0
    larkspur = [i for i in data["findings"] if i["facility"] == "larkspur"]
    assert larkspur and all(i["suggested"]["by"] == "Rule" for i in larkspur)
    pack = next(p for p in data["packs"] if p["facility"] == "larkspur")
    assert pack["ai"] is False
    assert next(b for b in data["briefs"] if b["client"] == "thornbury")["ai"] is False


def test_the_guard_refuses_any_model_call_for_or_about_the_no_ai_client(tmp_path):
    gateways = policy.guarded(Gateway(mode="replay", fixtures=tmp_path), record())
    with pytest.raises(policy.ModelNotPermitted):
        gateways["thornbury"].parse("any", "", [{"type": "text", "text": "hello"}], object)
    with pytest.raises(policy.ModelNotPermitted):
        gateways["calderwood"].parse(
            "any", "", [{"type": "text", "text": "Larkspur CLO positions"}], object)


# Map and ingest


def test_mapping_memory_is_scoped_to_each_client():
    mapping = cycle()["mapping"]
    owners = {f["id"]: f["client"] for f in cycle()["facilities"]}
    for feed in mapping["feeds"]:
        assert feed["client"] == owners[feed["facility"]]
    calderwood = next(m for m in mapping["memories"] if m["client"] == "calderwood")
    assert "larkspur" not in {layout["facility"] for layout in calderwood["layouts"]}
    northmoor = next(f for f in mapping["feeds"] if f["facility"] == "northmoor")
    assert northmoor["layout"] == "unchanged" and not northmoor["ai_used"]
    larkspur = next(f for f in mapping["feeds"] if f["facility"] == "larkspur")
    assert larkspur["overrides"][0]["override"] == "lower_of"


def test_submissions_carry_channel_deadline_and_consented_reuse():
    subs = cycle()["submissions"]
    assert {s["channel"] for s in subs} == {"Email", "SFTP", "API", "Data room", "Upload"}
    assert all(s["internal_deadline"] >= s["due"] for s in subs)
    reused = [s for s in subs if s["status"] == "reused"]
    assert len(reused) == 1 and reused[0]["reused"]["consent"]


# Monitor and alert


def test_preset_alert_is_drafted_checked_and_back_tested():
    presets = cycle()["alerts"]["calderwood"]["presets"]
    response = client.post("/api/monitoring/alerts/draft",
                           json={"client": "calderwood", "request": presets[0]["request"]})
    body = response.json()
    assert response.status_code == 200 and body["valid"] and body["fires"] >= 1
    assert body["rule"]["facility"] == "northmoor"


def test_an_unrecorded_request_is_refused_in_replay_and_thornbury_has_no_ai_alerts():
    response = client.post("/api/monitoring/alerts/draft",
                           json={"client": "calderwood", "request": "Ping me about anything odd"})
    assert response.status_code == 422
    assert client.post("/api/monitoring/alerts/draft",
                       json={"client": "thornbury", "request": "x"}).status_code == 409


def test_an_alert_goes_live_only_after_the_analyst_approves_it():
    preset = cycle()["alerts"]["calderwood"]["presets"][2]
    assert act("request-alert", "client", client="calderwood", request=preset["request"],
               rule=preset["rule"], summary=preset["drafted"]["summary"],
               fires=preset["fires"]).status_code == 200
    assert session()["alerts"][0]["status"] == "requested"
    assert act("approve-alert", "approver", alert=1).status_code == 409
    assert act("approve-alert", alert=1).status_code == 200
    assert session()["alerts"][0]["status"] == "live"


def test_headroom_covers_every_facility():
    rows = cycle()["headroom"]
    assert {r["facility"] for r in rows} == {"bramble", "northmoor", "kestrel", "larkspur"}
    ccc = next(r for r in rows if r["facility"] == "larkspur" and r["test"] == "CCC share")
    assert not ccc["passed"] and ccc["trend"] == "towards"


# Communicate


def test_status_briefs_have_no_model_written_numbers():
    for brief in cycle()["briefs"]:
        assert brief["unknown_placeholders"] == [] and brief["numbers_in_text"] == []
        assert [s["heading"] for s in brief["sections"]][:5] == [
            "Missing data", "Open questions", "Exclusions", "Identifier changes",
            "Missing financials"]


# Scorecard


def test_scorecard_reports_the_brief_measures_by_name():
    card = client.get("/api/monitoring/scorecard").json()
    names = [m["name"] for m in card["measures"]]
    assert names == [
        "Accuracy and completeness of loaded updates and reconciliations",
        "Material issues missed",
        "False alerts per cycle",
        "Hours per cycle, by mandate",
        "Turnaround time per cycle",
        "Processing cost per cycle",
        "Share of values linked to source evidence, with an audit trail of changes",
        "Additional deals supportable per analyst",
    ]
    measures = {m["name"]: m for m in card["measures"]}
    accuracy = measures[names[0]]["measured"]["value"].split()[0:3]
    assert accuracy[0] == accuracy[2]
    assert measures["Material issues missed"]["measured"]["value"] == "0"
    assert measures["False alerts per cycle"]["measured"]["value"] == "0"
    assert measures["Hours per cycle, by mandate"]["assumed"]
    assert card["assumptions"]


# The rest of the book


def test_the_rest_of_the_book_is_worked_out_by_code_and_within_every_limit():
    c = cycle()
    book = c["book"]
    assert len(book["facilities"]) == 20
    assert not {f["id"] for f in book["facilities"]} & {f["id"] for f in c["facilities"]}
    assert all(r["passed"] and not r["early_warning"] for r in book["headroom"])
    assert {s["status"] for s in book["submissions"]} <= {"received", "received_late"}
    # Book facilities add no findings, so the scorecard's measures are unchanged.
    assert not {i["facility"] for i in c["findings"]} & {f["id"] for f in book["facilities"]}


def test_a_book_delinquency_average_is_recomputed_from_the_reported_figures():
    import csv

    rows = [r for r in csv.DictReader((settings.deal_kit_output / "cycle" / "book"
                                       / "Book_Summaries.csv").open(encoding="utf-8"))
            if r["facility"] == "ashcombe"]
    from decimal import ROUND_HALF_UP, Decimal

    monthly = [float((Decimal(r["dq60_balance"]) / Decimal(r["pool_balance"]) * 100)
                     .quantize(Decimal("0.01"), ROUND_HALF_UP)) for r in rows]
    row = next(r for r in cycle()["book"]["headroom"]
               if r["facility"] == "ashcombe" and r["test"].startswith("60+"))
    assert [s["value"] for s in row["series"]] == monthly
    assert abs(row["value"] - sum(monthly) / 3) < 0.006


def test_findings_and_submissions_carry_references_and_dates():
    c = cycle()
    refs = [f["ref"] for f in c["findings"]]
    assert len(set(refs)) == len(refs) and all(r.startswith("EXC-2026-05-") for r in refs)
    assert all(f["raised"] <= c["cycle"]["as_of"] for f in c["findings"])
    subs = [s["ref"] for s in c["submissions"] + c["book"]["submissions"]]
    assert len(set(subs)) == len(subs)
    assert set(c["team"]) == {"analyst", "approver", "senior", "client"}


def test_audit_entries_name_the_record_they_touch():
    item = next(i for i in cycle()["findings"] if i["rule_outcome"] is None)
    assert act("triage", id=item["id"], outcome=item["suggested"]["outcome"]).status_code == 200
    entry = session()["audit"][-1]
    assert entry["subject"] == item["id"] and entry["type"] == "triage" and len(entry["hash"]) >= 12
