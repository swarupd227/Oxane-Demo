"""The monitoring cycle: replay reproduces the recorded run, the scorecard holds, and the
triage and approval controls are enforced by the API, not the screen."""

import json

import pytest
from conftest import RECORDED_RUN
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app
from app.monitoring.cycle import run_cycle
from app.pipeline.gateway import Gateway

client = TestClient(app)
ANALYST, APPROVER = "analyst", "approver"
RECORDED_CYCLE = settings.cycle_dir

pytestmark = pytest.mark.skipif(
    not (RECORDED_CYCLE / "cycle.json").exists(), reason="No monitoring cycle has been recorded"
)


@pytest.fixture(autouse=True)
def fresh_cycle(seed_view, monkeypatch):
    monkeypatch.setattr(settings, "pipeline_dir", RECORDED_RUN)
    client.post("/api/monitoring/session/reset")


def act(kind: str, actor: str = ANALYST, **payload):
    return client.post(
        "/api/monitoring/session/events", json={"type": kind, "actor": actor, "payload": payload}
    )


def cycle():
    return client.get("/api/monitoring/cycle").json()


def decide_all(facility: str | None = None) -> None:
    for item in cycle()["findings"]:
        if item["rule_outcome"] is None and (facility is None or facility in item["facility"]):
            assert (
                act("triage", id=item["id"], outcome=item["suggested"]["outcome"]).status_code
                == 200
            )


def test_replay_reproduces_the_recorded_cycle(tmp_path):
    gateway = Gateway(mode="replay", fixtures=settings.cycle_llm_fixtures)
    replayed = run_cycle(gateway, tmp_path)
    recorded = json.loads((RECORDED_CYCLE / "cycle.json").read_text(encoding="utf-8"))
    assert replayed["findings"] == recorded["findings"]
    assert replayed["tests"] == recorded["tests"]
    assert replayed["unverified"] == []


def test_every_number_in_the_lender_packs_comes_from_code():
    for pack in cycle()["packs"]:
        assert pack["unknown_placeholders"] == [] and pack["numbers_in_text"] == [], pack[
            "facility"
        ]


def test_scorecard_finds_every_planted_issue_and_raises_no_noise():
    measures = {m["name"]: m for m in client.get("/api/monitoring/scorecard").json()["measures"]}
    accuracy = measures["Accuracy and completeness"]["value"].split(" of ")
    assert accuracy[0] == accuracy[1]
    assert measures["Material issues missed"]["value"] == "0"
    assert measures["False alerts"]["value"] == "0"


def test_noise_is_logged_by_rule_with_a_reason():
    logged = [i for i in cycle()["findings"] if i["rule_outcome"] == "logged"]
    assert {i["id"].split("-")[1] for i in logged} >= {"layout", "northmoor", "certificate"}
    assert all(i["suggested"]["by"] == "Rule" and i["suggested"]["reason"] for i in logged)


def test_changing_a_suggested_outcome_needs_a_reason():
    item = next(i for i in cycle()["findings"] if i["suggested"]["outcome"] == "query")
    assert act("triage", id=item["id"], outcome="confirmed").status_code == 409
    assert act("triage", id=item["id"], outcome="confirmed", note="Lender asked").status_code == 200


def test_a_pack_cannot_be_approved_until_its_findings_are_decided():
    response = act("approve-pack", APPROVER, facility="kestrel")
    assert response.status_code == 409 and "decision" in response.json()["detail"]
    decide_all("kestrel")
    assert act("approve-pack", APPROVER, facility="kestrel").status_code == 200


def test_the_preparer_cannot_approve_and_the_approver_cannot_triage():
    decide_all()
    assert act("approve-pack", ANALYST, facility="kestrel").status_code == 409
    item = cycle()["findings"][0]
    assert act("triage", APPROVER, id=item["id"], outcome="query").status_code == 409


def test_an_approved_pack_locks_its_findings():
    decide_all()
    assert act("approve-pack", APPROVER, facility="kestrel").status_code == 200
    item = next(
        i for i in cycle()["findings"] if i["facility"] == "kestrel" and i["rule_outcome"] is None
    )
    assert act("triage", id=item["id"], outcome="expert", note="Late change").status_code == 409


def test_what_if_june_breaches_above_the_threshold():
    breach = client.post("/api/monitoring/what-if", json={"facility": "northmoor", "value": 5.9})
    safe = client.post("/api/monitoring/what-if", json={"facility": "northmoor", "value": 5.7})
    assert breach.json()["breached"] and not safe.json()["breached"]


def test_only_cycle_documents_are_served():
    assert (
        client.get("/api/monitoring/files/kestrel/Kestrel_Q1_2026_NAV_Report.pdf").status_code
        == 200
    )
    assert client.get("/api/monitoring/files/../deal.yaml").status_code == 404
    assert client.get("/api/monitoring/files/cycle-key/key.json").status_code == 404
