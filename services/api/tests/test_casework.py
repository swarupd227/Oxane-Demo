"""Onboarding casework: replay reproduces the recorded run, every figure is code's and checked,
and the query, QC, release and backbook controls are enforced by the API."""

import io
import json
from datetime import datetime

import pytest
from conftest import RECORDED_RUN
from fastapi.testclient import TestClient
from openpyxl import load_workbook

from app.casework.backbook import check
from app.casework.run import run_casework
from app.casework.steps import BackbookSuggestion
from app.casework.view import business_hours
from app.config import settings
from app.main import app
from app.pipeline.gateway import Gateway

client = TestClient(app)
ANALYST, APPROVER = "analyst", "approver"
RECORDED = settings.casework_dir

pytestmark = pytest.mark.skipif(not (RECORDED / "casework.json").exists(),
                                reason="No casework run has been recorded")


@pytest.fixture(autouse=True)
def fresh_session(seed_view, monkeypatch):
    monkeypatch.setattr(settings, "pipeline_dir", RECORDED_RUN)
    client.post("/api/session/reset")


def act(kind: str, actor: str = ANALYST, **payload):
    return client.post("/api/session/events",
                       json={"type": kind, "actor": actor, "payload": payload})


def casework():
    return client.get("/api/casework").json()


def prepare_case() -> None:
    terms = client.get("/api/workbench").json()["terms"]
    act("intake-done")
    act("bulk-approve", names=[t["name"] for t in terms
                               if t["tier"] > 1 and t["confidence"] == "high"])
    act("approve-term", name="Facility limit")
    act("approve-term", name="Advance rate")
    act("accept-mapping")
    act("run")
    act("work-exception", id="X4", outcome="queried", note="Sent")
    act("work-exception", id="X5", outcome="escalated", note="Sent")
    act("work-exception", id="X6", outcome="accepted", note="Same dealer")


def test_replay_reproduces_the_recorded_casework_without_a_model(tmp_path):
    gateway = Gateway(mode="replay", fixtures=settings.casework_llm_fixtures)
    result = run_casework(gateway, tmp_path)
    recorded = json.loads((RECORDED / "casework.json").read_text(encoding="utf-8"))
    assert json.loads(json.dumps(result, sort_keys=True, default=str)) == recorded
    assert all(item.from_replay for item in gateway.usage)


def test_every_definition_is_quoted_on_its_page_and_the_chain_resolves():
    defs = casework()["definitions"]
    checks = defs["checks"]
    assert checks["quotes_found"] == checks["quotes"] > 10
    assert checks["input_cycles"] == [] and checks["unresolved_references"] == []
    assert defs["borrowing_base_reproduced"]
    nodes = {n["key"]: n for n in defs["nodes"]}
    assert nodes["advance rate"]["amendment_source"]["document"] == "amendment_1"
    assert nodes["borrowing base"]["resolved"]["value"] == "US$48,193,346.69"
    assert defs["delinquency"]["literal"] != defs["delinquency"]["without_repossessed"]


def test_client_model_differences_become_queries_with_code_filled_figures():
    data = casework()
    model = data["client_model"]
    assert model["rejected"] == []
    differing = [r["topic"] for r in model["rows"] if r["status"] in ("differs", "silent")]
    assert sorted(differing) == sorted(["advance_rate", "past_due_exclusion",
                                        "concentration_denominator", "dealer_grouping",
                                        "fico_bucket", "missing_fico"])
    rate = next(r for r in model["rows"] if r["topic"] == "advance_rate")
    assert rate["borrowing_base_change"] == pytest.approx(1478462.91, abs=0.01)
    drafted = [q for q in data["tracker"]["queries"] if q["topic"]]
    assert len(drafted) == 6
    raw = json.loads((RECORDED / "casework.json").read_text(encoding="utf-8"))["queries"]
    assert all(not q["unknown_placeholders"] and not q["numbers_in_text"] for q in raw)
    assert "US$1,478,462.91" in next(q["text"] for q in raw if q["topic"] == "advance_rate")


def test_business_hours_skip_nights_and_weekends():
    day = {"start": "09:00", "end": "17:30"}
    friday, monday = datetime(2026, 5, 15, 16, 0), datetime(2026, 5, 18, 10, 0)
    assert business_hours(friday, monday, day) == 2.5


def test_query_tracker_splits_analyst_time_from_client_waiting():
    prepare_case()
    before = casework()["tracker"]
    assert before["drafted"] == 6
    ids = [q["id"] for q in before["queries"] if q["status"] == "drafted"]
    assert act("record-answer", ids=ids[:1]).status_code == 409  # Not sent yet.
    assert act("send-query", ids=ids).status_code == 200
    assert act("send-query", ids=ids[:1]).status_code == 409
    answered = [q["id"] for q in casework()["tracker"]["queries"] if q["answer_waiting"]]
    assert act("record-answer", ids=answered).status_code == 200
    after = casework()["tracker"]
    assert after["drafted"] == 0
    assert after["elapsed_hours"] == pytest.approx(
        after["analyst_hours"] + after["client_waiting_hours"])
    open_query = next(q for q in after["queries"] if q["topic"] == "missing_fico")
    assert open_query["status"] == "with client"
    assert act("record-answer", ids=[open_query["id"]]).status_code == 409


def test_a_genuine_qc_variance_holds_the_report_until_resolved_and_released_by_a_reviewer():
    prepare_case()
    qc = casework()["qc"]
    assert [x["class"] for x in qc["lines"]].count("genuine") == 2
    assert all(x["explained_by"] for x in qc["lines"] if x["class"] == "genuine")
    assert act("approve-load", actor=APPROVER, carry_forward=True).status_code == 200
    assert act("release-report", actor=APPROVER).status_code == 409  # Variances open.
    for line in qc["genuine"]:
        assert act("resolve-variance", line=line, resolution="Typed in",
                   reason="x").status_code == 409
        assert act("resolve-variance", line=line, resolution=qc["resolutions"][2],
                   reason="Traced to the listed loans").status_code == 200
    assert act("release-report").status_code == 409  # The preparer cannot release.
    assert act("release-report", actor=APPROVER).status_code == 200
    assert casework()["qc"]["status"] == "released"
    assert casework()["config"]["status"]["final"]


def test_backbook_loads_only_after_every_suggestion_checks_out():
    prepare_case()
    deals = {d["id"]: d for d in casework()["backbook"]}
    assert deals["ashdown"]["loaded"] and deals["ashdown"]["exceptions"] == 0
    assert all(d["check"]["ok"] for deal in deals.values() for d in deal["differences"])
    assert act("accept-backbook", deal="ashdown").status_code == 409
    assert act("accept-backbook", deal="whitcombe").status_code == 200
    assert next(d for d in casework()["backbook"] if d["id"] == "whitcombe")["loaded"]


def test_leaving_rows_out_is_never_accepted_without_an_expert():
    blank = {"kind": "blank_values", "column": "DPD", "field": "days_past_due"}
    rows = [{"DPD": "", "CurrBal": "100.00", "NextDueDate": "2026-05-20"}]
    suggestion = BackbookSuggestion(deal="x", column="DPD", kind="blank_values", field=None,
                                    treat_blank_as=None, code_map=[], reason="")
    ok, evidence = check(suggestion, blank, rows, {}, set())
    assert not ok and "expert" in evidence


def test_configuration_workbook_thresholds_match_their_sources_and_say_provisional():
    prepare_case()
    shown = casework()["config"]
    assert all(row["in_source"] for row in shown["thresholds"])
    response = client.get("/api/casework/config-workbook.xlsx")
    assert response.status_code == 200
    book = load_workbook(io.BytesIO(response.content))
    assert book["Status"]["A2"].value.startswith("PROVISIONAL")
    sheet = book["Rules and thresholds"]
    assert all(cell.comment and cell.comment.text.startswith("Source:")
               for cell in sheet["D"][1:])
    assert {"Field map", "Report lines", "Client conventions"} <= set(book.sheetnames)


def test_an_approved_rule_change_shows_against_its_source():
    prepare_case()
    act("propose-rule", rule_id="E5", **{"from": 75000, "to": 70000, "reason": "Credit view"})
    act("approve-rule", actor=APPROVER, reason="Agreed")
    row = next(r for r in casework()["config"]["thresholds"] if r["rule"] == "E5")
    assert row["engine"] == "70000" and not row["in_source"] and "approved" in row["change"]


def test_casework_files_are_served_by_name_only():
    assert client.get("/api/casework/files/QC_Bramble_Onboarding_April_2026.xlsx"
                      ).status_code == 200
    assert client.get("/api/casework/files/key.json").status_code == 404


def test_scorecard_reports_the_brief_measures_by_name():
    prepare_case()
    brief = client.get("/api/scorecard").json()["brief"]
    names = [m["name"] for m in brief["measures"]]
    assert names == [
        "Field-level accuracy against expert-verified records",
        "Material errors and omissions", "Exception rate", "Hours per onboarding, by deal type",
        "Elapsed time, split from client waiting", "Cost per onboarding",
        "Share of values linked to source", "Capacity released"]
    accuracy = brief["measures"][0]
    assert accuracy["passed"], accuracy["measured"]["details"]
    assert brief["measures"][3]["assumed"]["value"]
