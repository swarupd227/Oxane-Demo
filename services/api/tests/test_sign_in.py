"""With sign-in on, identity comes from the platform header and never from the request."""

import pytest
from conftest import RECORDED_RUN
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app

client = TestClient(app)
ALICE, BEN, EVE = "alice@example.com", "ben@example.com", "eve@example.com"
pytestmark = pytest.mark.skipif(not (RECORDED_RUN / "workbench.json").exists(),
                                reason="No run has been recorded")


def as_user(user):
    return {"x-ms-client-principal-name": user}


def act(user, kind, actor="analyst", **payload):
    return client.post("/api/session/events", headers=as_user(user),
                       json={"type": kind, "actor": actor, "payload": payload})


@pytest.fixture(autouse=True)
def signed_in(seed_view, monkeypatch):
    monkeypatch.setattr(settings, "pipeline_dir", RECORDED_RUN)
    monkeypatch.setattr(settings, "auth_required", True)
    monkeypatch.setattr(settings, "analyst_users", f"{ALICE}, {EVE}")
    monkeypatch.setattr(settings, "approver_users", BEN)
    client.post("/api/session/reset", headers=as_user(ALICE))


def prepare(user=ALICE):
    act(user, "intake-done")
    terms = client.get("/api/workbench", headers=as_user(user)).json()["terms"]
    act(user, "bulk-approve",
        names=[t["name"] for t in terms if t["tier"] > 1 and t["confidence"] == "high"])
    act(user, "approve-term", name="Facility limit")
    act(user, "approve-term", name="Advance rate")
    act(user, "accept-mapping")
    act(user, "run")
    act(user, "work-exception", id="X4", outcome="queried", note="Sent")
    act(user, "work-exception", id="X5", outcome="escalated", note="Sent")
    act(user, "work-exception", id="X6", outcome="accepted", note="Same dealer")


def test_nothing_is_served_without_sign_in():
    assert client.get("/api/session").status_code == 401
    assert client.get("/api/workbench").status_code == 401
    assert client.get("/api/load-file").status_code == 401


def test_health_stays_open_for_the_platform_probe():
    assert client.get("/api/health").status_code == 200


def test_me_reports_the_signed_in_user():
    body = client.get("/api/me", headers=as_user(BEN)).json()
    assert body == {"signed_in": True, "user": BEN, "role": "approver"}


def test_a_forged_actor_in_the_body_is_ignored():
    prepare()
    response = act(ALICE, "approve-load", actor="approver", carry_forward=True)
    assert response.status_code == 409
    assert "second analyst" in response.json()["detail"]


def test_someone_not_on_a_list_cannot_act():
    response = act("stranger@example.com", "intake-done")
    assert response.status_code == 409
    assert "not recognised" in response.json()["detail"]


def test_a_stranger_cannot_reset_the_case():
    assert client.post("/api/session/reset",
                       headers=as_user("stranger@example.com")).status_code == 403


def test_a_named_second_analyst_approves_and_is_recorded():
    prepare()
    assert act(BEN, "approve-load", carry_forward=True).status_code == 200
    state = client.get("/api/session", headers=as_user(BEN)).json()
    assert state["approvedByName"] == BEN
    assert state["preparedBy"] == ALICE
    assert any(entry["actor"] == BEN for entry in state["audit"])
    loaded = client.get("/api/load-file", headers=as_user(BEN)).json()
    approval = loaded["approval"]
    assert (approval["prepared_by"], approval["approved_by"]) == (ALICE, BEN)


def test_one_person_on_both_lists_still_cannot_approve_their_own_case(monkeypatch):
    monkeypatch.setattr(settings, "approver_users", f"{BEN}, {ALICE}")
    # On both lists, Alice is treated as a reviewer, and a reviewer cannot prepare.
    assert act(ALICE, "intake-done").status_code == 409
