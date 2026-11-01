"""The controls, tested through the API and against the database itself."""

import json

import pytest
from conftest import RECORDED_RUN
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app import session as case_session
from app.config import settings
from app.db import engine
from app.main import app

client = TestClient(app)
ANALYST, APPROVER = "analyst", "approver"


def act(kind: str, actor: str = ANALYST, **payload):
    return client.post("/api/session/events",
                       json={"type": kind, "actor": actor, "payload": payload})


def state():
    return client.get("/api/session").json()


@pytest.fixture(autouse=True)
def fresh_session(seed_view, monkeypatch):
    monkeypatch.setattr(settings, "pipeline_dir", RECORDED_RUN)
    client.post("/api/session/reset")


pytestmark = pytest.mark.skipif(not (RECORDED_RUN / "workbench.json").exists(),
                                reason="No run has been recorded")


def prepare_case():
    act("intake-done")
    act("approve-term", name="Facility limit")
    act("approve-term", name="Advance rate")
    act("run")
    act("work-exception", id="X4", outcome="queried", note="Sent")
    act("work-exception", id="X5", outcome="escalated", note="Sent")
    act("work-exception", id="X6", outcome="accepted", note="Same dealer")


def test_nothing_happens_before_the_pack_is_uploaded():
    assert act("run").status_code == 409


def test_earlier_work_is_logged_and_labelled():
    act("intake-done")
    entries = state()["audit"]
    assert any(entry["earlier"] for entry in entries)
    assert not entries[0]["earlier"]
    assert state()["exceptions"]["X2"] == "queried"


def test_preparer_cannot_approve_their_own_case():
    prepare_case()
    response = act("approve-load", carry_forward=True)
    assert response.status_code == 409
    assert "second analyst" in response.json()["detail"]
    assert state()["approvedAt"] is None


def test_the_screen_is_not_the_control_a_forged_actor_name_is_refused():
    prepare_case()
    assert act("approve-load", actor="manager", carry_forward=True).status_code == 409


def test_reviewer_cannot_change_the_case():
    prepare_case()
    assert act("approve-term", actor=APPROVER, name="Margin").status_code == 409


def test_second_analyst_can_approve_and_the_case_then_locks():
    prepare_case()
    assert act("approve-load", actor=APPROVER, carry_forward=True).status_code == 200
    assert state()["approvedBy"] == APPROVER
    assert act("approve-term", name="Margin").status_code == 409


def test_approval_needs_every_tier_1_value():
    act("intake-done")
    response = act("approve-load", actor=APPROVER, carry_forward=True)
    assert response.status_code == 409
    assert "Tier 1" in response.json()["detail"]


def test_open_items_must_be_carried_forward_explicitly():
    prepare_case()
    response = act("approve-load", actor=APPROVER)
    assert "carried forward" in response.json()["detail"]


def test_tier_1_cannot_be_bulk_approved():
    act("intake-done")
    assert act("bulk-approve", names=["Reserve amount"]).status_code == 409


def test_a_value_that_was_not_found_cannot_be_approved():
    act("intake-done")
    assert act("approve-term", name="Restricted jurisdictions").status_code == 409


def test_edits_need_a_reason():
    act("intake-done")
    assert act("edit-term", name="Margin", value="3.50%", reason="").status_code == 409


def test_a_pending_rule_change_blocks_approval_until_a_reviewer_decides():
    prepare_case()
    act("propose-rule", rule_id="E5", **{"from": 75000, "to": 70000}, reason="Stress test")
    response = act("approve-load", actor=APPROVER, carry_forward=True)
    assert "rule change" in response.json()["detail"]
    assert act("decline-rule", actor=ANALYST, reason="No").status_code == 409
    assert act("decline-rule", actor=APPROVER, reason="Threshold stands").status_code == 200
    assert act("approve-load", actor=APPROVER, carry_forward=True).status_code == 200


def test_load_file_needs_approval_and_carries_its_evidence():
    prepare_case()
    assert client.get("/api/load-file").status_code == 409
    act("edit-term", name="Margin", value="3.25% over Term SOFR", reason="Clearer wording")
    act("approve-load", actor=APPROVER, carry_forward=True)
    response = client.get("/api/load-file")
    assert response.status_code == 200
    assert "attachment" in response.headers["content-disposition"]
    body = response.json()
    assert body["approved_by"] == "Second analyst"
    assert body["provisional"] is True
    assert body["audit_chain_head"] == state()["chainHead"]
    assert len(body["terms"]) == 26
    assert next(t for t in body["terms"] if t["name"] == "Margin")["edited"] is True
    assert any("Schedule 4" in item for item in body["open_items"])


def test_the_database_refuses_to_change_history():
    act("intake-done")
    for statement in ("UPDATE case_event SET actor = 'someone'", "DELETE FROM case_event"):
        with engine.begin() as connection, pytest.raises(DBAPIError, match="append-only"):
            connection.execute(text(statement))


def test_reset_keeps_the_old_session_in_the_log():
    act("intake-done")
    with engine.connect() as connection:
        before = connection.execute(text("SELECT count(*) FROM case_event")).scalar()
    client.post("/api/session/reset")
    assert state()["intakeDone"] is False
    with engine.connect() as connection:
        assert connection.execute(text("SELECT count(*) FROM case_event")).scalar() == before


def test_a_tampered_event_breaks_the_chain():
    act("intake-done")
    act("run")
    from sqlalchemy.orm import Session

    with Session(engine) as db:
        events = case_session.load_events(db, case_session.current_session(db))
        assert case_session.chain_intact(events)
        events[-1].actor = "someone"  # Only in memory. The database would refuse this.
        assert not case_session.chain_intact(events)
        db.rollback()


def measures():
    return {item["name"]: item for item in client.get("/api/scorecard").json()["measures"]}


def test_scorecard_reports_the_recorded_run():
    prepare_case()
    results = measures()
    assert results["Exceptions found"]["value"] == "10 of 10"
    assert results["False items"]["value"] == "0"
    assert results["Field-level accuracy, Tier 1, before review"]["value"] == "11 of 11"
    assert results["Field-level accuracy, Tier 2 and 3"]["value"] == "15 of 15"
    assert results["Rule results"]["value"] == "11 of 11"
    assert results["Onboarding time"]["value"] == "Not finished yet"
    assert results["Processing cost"]["value"].startswith("US$0.")


def test_scorecard_catches_a_wrong_value(tmp_path, monkeypatch):
    run = json.loads((RECORDED_RUN / "workbench.json").read_text("utf-8"))
    for term in run["terms"]:
        if term["name"] == "Minimum liquidity covenant":
            term["value"] = "US$11,000,000"
    run["exceptions"] = [item for item in run["exceptions"] if item["id"] != "X5"]
    run["exceptions"].append({"id": "Q1", "title": "A false item"})
    from app.scoring import scorecard

    results = {item["name"]: item for item in
               scorecard(run, case_session._initial())["measures"]}
    assert results["Field-level accuracy, Tier 1, before review"]["value"] == "10 of 11"
    assert "Minimum liquidity" in results["Material errors and omissions"]["details"][0]
    assert results["Exceptions found"]["value"] == "9 of 10"
    assert results["False items"]["details"] == ["Q1"]


def test_scorecard_claims_nothing_from_seed_data(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "pipeline_dir", tmp_path / "none")
    assert client.get("/api/scorecard").json()["available"] is False
