"""The pitch blockers: the client portal shows only what was released to that client, written to
them; tests and flows never leave duplicate or mis-attributed hand-offs; a purge removes what
they left; and the header's live-AI badge knows when the key's last test failed."""

import json
import re
import uuid

import pytest
from conftest import RECORDED_RUN
from fastapi.testclient import TestClient
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.admin import ai_provider as ap
from app.admin import purge
from app.admin.models import AppSetting
from app.config import settings
from app.db import engine
from app.deals.models import Client, WorkItem
from app.main import app
from app.monitoring import client_summary

client = TestClient(app)
CODE = "blockers-test-code"
pytestmark = pytest.mark.skipif(not (settings.cycle_dir / "cycle.json").exists(),
                                reason="No monitoring cycle has been recorded")


def h(persona: str, code: bool = False) -> dict[str, str]:
    headers = {"X-Acting-User": persona}
    if code:
        headers["X-Demo-Access-Code"] = CODE
    return headers


def cycle_event(kind: str, persona: str, **payload):
    return client.post("/api/monitoring/session/events", headers=h(persona),
                       json={"type": kind, "actor": "analyst", "payload": payload})


def case_event(kind: str, persona: str, **payload):
    return client.post("/api/session/events", headers=h(persona),
                       json={"type": kind, "actor": "analyst", "payload": payload})


def portal(persona: str) -> dict:
    response = client.get("/api/portal", headers=h(persona))
    assert response.status_code == 200, response.text
    return response.json()


def fill(text: str, figures: dict) -> str:
    return re.sub(r"\{\{(\w+)\}\}", lambda m: figures[m.group(1)]["value"], text)


def recorded_cycle() -> dict:
    return json.loads((settings.cycle_dir / "cycle.json").read_text(encoding="utf-8"))


@pytest.fixture(autouse=True)
def fresh(seed_view, monkeypatch):
    monkeypatch.setattr(settings, "pipeline_dir", RECORDED_RUN)
    monkeypatch.setattr(settings, "demo_access_code", CODE)
    client.post("/api/monitoring/session/reset", headers=h("priya"))
    client.post("/api/session/reset", headers=h("hannah"))


# B1: the portal


def test_the_portal_never_returns_the_internal_brief_or_an_unreleased_summary():
    cycle = recorded_cycle()
    for persona, client_id in (("james", "calderwood"), ("laura", "thornbury")):
        data = portal(persona)
        assert "brief" not in data and data["summary"] is None
        text = json.dumps(data)
        brief = next(b for b in cycle["briefs"] if b["client"] == client_id)
        # Not one line of the internal brief, drafted or template, reaches the client.
        for line in [brief["opening"], *(p for s in brief["sections"] for p in s["points"])]:
            filled = fill(line, brief["figures"])
            assert filled not in text and line not in text
        for marker in ("Priya", "Daniel Okafor", "Template", "draft pending", "{{"):
            assert marker not in text, (persona, marker)


def test_the_summary_reaches_only_its_own_client_and_only_after_release():
    assert cycle_event("release-summary", "james", client="calderwood").status_code == 403
    assert cycle_event("release-summary", "marcus", client="calderwood").status_code == 403
    assert cycle_event("release-summary", "priya", client="nobody").status_code == 409
    assert cycle_event("release-summary", "priya", client="calderwood").status_code == 200
    assert cycle_event("release-summary", "priya", client="calderwood").status_code == 409

    james = portal("james")
    summary = james["summary"]
    assert summary is not None and summary["greeting"] == "Dear James,"
    text = json.dumps(summary)
    assert "your" in text and "{{" not in text and "Priya" not in text
    assert "Ravenglass" in text and "Larkspur" not in text and "Thornbury" not in text
    # Thornbury's is still unreleased, and never shows Calderwood's.
    laura = portal("laura")
    assert laura["summary"] is None and "Calderwood" not in json.dumps(laura)
    # Laura is told only of her own; James gets a notice in his work.
    assert any(w["title"] == "Status-call summary released" for w in james["work"])
    assert not any(w["title"] == "Status-call summary released" for w in laura["work"])
    assert cycle_event("release-summary", "priya", client="thornbury").status_code == 200
    laura = portal("laura")
    assert laura["summary"]["greeting"] == "Dear Laura,"
    assert not re.search(r"Calderwood|Bramble|Northmoor|Kestrel|Ravenglass",
                         json.dumps(laura["summary"]))


def test_each_summary_is_written_to_the_client_with_no_internal_terms():
    cycle = recorded_cycle()
    clients = {c["id"]: c for c in cycle["clients"]}
    assert {s["client"] for s in cycle["client_summaries"]} == set(clients)
    for summary in cycle["client_summaries"]:
        me = clients[summary["client"]]
        others = [c for c in clients.values() if c["id"] != me["id"]]
        assert client_summary.problems(summary, me, cycle["team"], others) == []
        assert summary["week_of"] == "2026-06-22"


def test_the_brief_does_not_contradict_itself():
    cycle = recorded_cycle()
    for brief in cycle["briefs"]:
        sections = {s["heading"]: s["points"] for s in brief["sections"]}
        filled = [fill(p, brief["figures"])
                  for p in [brief["opening"], *(p for ps in sections.values() for p in ps)]]
        # Dates in prose read as 22 Jun 2026, never 2026-06-22.
        assert not any(re.search(r"\b\d{4}-\d{2}-\d{2}\b", p) for p in filled), brief["client"]
        if brief["client"] == "calderwood":
            missing = sections["Missing financials"]
            assert not any("Nothing is outstanding" in p or "None outstanding" in p
                           for p in missing)
            assert any("Ashlar Packaging Group" in p for p in missing)
        else:
            text = " ".join(sections["Missing data"])
            assert "not received" in text and "both on time" not in text


# B2: hand-offs


def items(title: str) -> list[WorkItem]:
    with Session(engine) as db:
        return list(db.scalars(select(WorkItem).where(WorkItem.title == title,
                                                      WorkItem.subject.like("scripted:%"))
                               .order_by(WorkItem.id)))


def prepare_case(persona: str = "hannah") -> None:
    terms = client.get("/api/workbench").json()["terms"]
    names = [t["name"] for t in terms if t["tier"] > 1 and t["confidence"] == "high"]
    for kind, payload in [("intake-done", {}), ("bulk-approve", {"names": names}),
                          ("approve-term", {"name": "Facility limit"}),
                          ("approve-term", {"name": "Advance rate"}), ("accept-mapping", {}),
                          ("run", {}),
                          ("work-exception", {"id": "X4", "outcome": "queried", "note": "Sent"}),
                          ("work-exception", {"id": "X5", "outcome": "escalated", "note": "Sent"}),
                          ("work-exception", {"id": "X6", "outcome": "accepted",
                                              "note": "Same dealer"})]:
        assert case_event(kind, persona, **payload).status_code == 200, kind


APPROVE = "Approve load file, case 0412 Bramble"


def test_scripted_hand_offs_are_opened_once_by_the_requester_and_done_by_the_approver():
    prepare_case()
    current = client.get("/api/session").json()
    open_now = [i for i in items(APPROVE) if i.status == "open"]
    assert len(open_now) == 1
    item = open_now[0]
    assert item.from_persona == "hannah" and item.assignee == "marcus"
    # More events from anyone, including the approver, never open it twice.
    case_event("approve-term", "hannah", name="Margin")
    assert len([i for i in items(APPROVE) if i.status == "open"]) == 1
    assert current["approvedAt"] is None
    response = client.post("/api/session/events", headers=h("marcus"),
                           json={"type": "approve-load", "actor": "approver",
                                 "payload": {"carry_forward": True}})
    assert response.status_code == 200, response.text
    done = [i for i in items(APPROVE) if i.id == item.id][0]
    assert done.status == "done" and done.done_by == "marcus"
    work = client.get("/api/work", headers=h("marcus")).json()
    shown = next(w for w in work["done"] if w["id"] == item.id)
    assert shown["done_by_name"] == "Marcus Hale" and shown["from_name"] == "Hannah Cole"


def test_an_event_with_no_persona_is_still_attributed():
    prepare_case()
    client.post("/api/session/events", json={"type": "approve-load", "actor": "approver",
                                             "payload": {"carry_forward": True}})
    done = [i for i in items(APPROVE) if i.status == "done"]
    assert done and done[-1].done_by == "marcus"


def test_a_requester_never_approves_their_own_request():
    from app.deals import handoffs
    from app.personas import find

    with Session(engine) as db:
        marcus = find("marcus")
        key = f"test:{uuid.uuid4().hex}"
        item = handoffs.open_item(db, key, "test:self", uuid.uuid4().hex, "approval",
                                  "Approve my own thing", "reviewer", "/approve", marcus)
        assert item.assignee is None  # never routed back to the requester
        db.commit()
        item_id = item.id
    assert not any(w["id"] == item_id for w in
                   client.get("/api/work", headers=h("marcus")).json()["waiting"])
    refused = client.post(f"/api/work/{item_id}/complete", headers=h("marcus"), json={})
    assert refused.status_code == 403
    with Session(engine) as db:
        handoffs.close_items(db, key, find("marcus"), exact=True)
        row = db.get(WorkItem, item_id)
        assert row.status == "withdrawn"  # closed by the requester: withdrawn, not done
        db.execute(delete(WorkItem).where(WorkItem.id == item_id))
        db.commit()


# B2: the purge


def test_purge_is_a_dry_run_by_default_and_then_removes_test_data():
    made = client.post("/api/deals/clients", headers=h("alex"), json={
        "name": f"Purge Check {uuid.uuid4().hex[:6]}", "contact_name": "Pat Example",
        "ai_permitted": False, "approval_levels": 2})
    assert made.status_code == 200, made.text
    made_id = made.json()["id"]
    prepare_case()
    with Session(engine) as db:
        dry = purge.purge_test_data(db)
        assert dry["applied"] is False and dry["clients"] >= 1 and dry["scripted_rebuilt"] >= 1
        assert db.get(Client, made_id) is not None  # nothing changed
    with Session(engine) as db:
        done = purge.purge_test_data(db, apply=True)
    assert done["clients"] == dry["clients"]
    with Session(engine) as db:
        assert db.get(Client, made_id) is None
        assert db.scalars(select(Client)).first() is None
        open_items = [i for i in db.scalars(select(WorkItem)) if i.status == "open"]
    # The scripted hand-offs are rebuilt once from the current session.
    assert [i.title for i in open_items].count(APPROVE) == 1
    # The client users created at run time go with their clients.
    persons = client.get("/api/personas").json()["personas"]
    assert not any(p["id"].startswith("client-") for p in persons)


def test_the_purge_endpoint_is_for_the_administrator_only():
    assert client.post("/api/admin/purge-test-data", headers=h("marcus", True)).status_code == 403
    dry = client.post("/api/admin/purge-test-data", headers=h("alex"))
    kept = client.post("/api/admin/purge-test-data", params={"keep_client": [999999]},
                       headers=h("alex"))
    assert kept.status_code == 200 and kept.json()["applied"] is False
    assert dry.status_code == 200 and dry.json()["applied"] is False


# B3: the live-AI badge


def test_status_reports_whether_the_key_in_use_passed_its_last_test(monkeypatch):
    name = f"test-{uuid.uuid4().hex[:8]}"
    monkeypatch.setattr(ap, "NAME", name)
    monkeypatch.setattr(settings, "anthropic_api_key", "sk-ant-api03-" + "Q" * 80)
    monkeypatch.setattr(settings, "llm_provider", "anthropic")
    monkeypatch.setattr(settings, "deals_stub_model", False)
    try:
        assert client.get("/api/deals/status").json()["key_ok"] is None
        with Session(engine) as db:
            db.add(AppSetting(name=name, provider="anthropic", updated_at=None,
                              last_test={"ok": False, "status": 401, "subject": "env",
                                         "provider": "anthropic",
                                         "at": "2026-11-23T00:00:00+00:00"}))
            db.commit()
        status = client.get("/api/deals/status")
        assert status.json()["mode"] == "live" and status.json()["key_ok"] is False
        assert "sk-ant" not in status.text
        with Session(engine) as db:
            row = db.get(AppSetting, name)
            row.last_test = {**row.last_test, "ok": True, "status": 200}
            db.commit()
        assert client.get("/api/deals/status").json()["key_ok"] is True
    finally:
        with Session(engine) as db:
            db.execute(delete(AppSetting).where(AppSetting.name == name))
            db.commit()
