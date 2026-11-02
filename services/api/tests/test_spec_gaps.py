"""The spec's load file, queue, intake, mapping and review behaviour."""

import csv

import pytest
from conftest import RECORDED_RUN
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app

client = TestClient(app)
ANALYST, APPROVER = "analyst", "approver"
pytestmark = pytest.mark.skipif(not (RECORDED_RUN / "workbench.json").exists(),
                                reason="No run has been recorded")


def act(kind, actor=ANALYST, **payload):
    return client.post("/api/session/events",
                       json={"type": kind, "actor": actor, "payload": payload})


def state():
    return client.get("/api/session").json()


def bulk(**kwargs):
    terms = client.get("/api/workbench", **kwargs).json()["terms"]
    return [t["name"] for t in terms if t["tier"] > 1 and t["confidence"] == "high"]


def prepare():
    act("intake-done")
    act("bulk-approve", names=bulk())
    act("approve-term", name="Facility limit")
    act("approve-term", name="Advance rate")
    act("accept-mapping")
    act("run")
    act("work-exception", id="X4", outcome="queried", note="Sent")
    act("work-exception", id="X5", outcome="escalated", note="Sent")
    act("work-exception", id="X6", outcome="accepted", note="Same dealer")


def approve():
    assert act("approve-load", actor=APPROVER, carry_forward=True).status_code == 200


@pytest.fixture(autouse=True)
def fresh_session(seed_view, monkeypatch):
    monkeypatch.setattr(settings, "pipeline_dir", RECORDED_RUN)
    client.post("/api/session/reset")


def test_load_file_carries_every_loan_and_section():
    prepare()
    approve()
    body = client.get("/api/load-file").json()
    assert len(body["loans"]) == 2400
    assert len(body["tape_mapping"]) == 38
    assert len(body["rules"]["items"]) == 17
    assert len(body["exceptions"]) == 10
    assert {"facility_terms", "lender_fields", "concentrations", "covenants"} <= set(body)


def test_load_file_loans_agree_with_the_calculation():
    prepare()
    approve()
    body = client.get("/api/load-file").json()
    eligible = [loan for loan in body["loans"] if loan["eligible"]]
    total = sum(float(loan["current_balance"]) for loan in eligible)
    assert total == pytest.approx(body["borrowing_base"]["eligible_pool"], abs=0.01)
    failed = [loan for loan in body["loans"] if not loan["eligible"]]
    assert all(loan["failed_rules"] for loan in failed)


def test_load_file_resolves_mixed_dates_and_groups_the_dealer():
    prepare()
    approve()
    loans = client.get("/api/load-file").json()["loans"]
    assert all(loan["origination_date"][4] == "-" for loan in loans
               if not loan["origination_date_uncertain"])
    assert any(loan["origination_date_uncertain"] for loan in loans)
    variants = {loan["dealer_group"] for loan in loans if "Sunrise" in loan["dealer_name"]}
    assert variants == {"Sunrise Motors LLC"}


def test_load_file_answers_the_lender_fields():
    prepare()
    approve()
    fields = {f["name"]: f for f in client.get("/api/load-file").json()["lender_fields"]}
    assert fields["Weighted average APR"]["status"] == "derived"
    assert fields["Weighted average APR"]["value"] > 0
    assert fields["Availability"]["value"] == pytest.approx(193346.69, abs=0.01)


def test_a_sent_term_becomes_a_queue_item_that_blocks_approval():
    prepare()
    act("queue-term", name="Margin")
    items = state()["heldItems"]
    assert [item["term"] for item in items] == ["Margin"]
    response = act("approve-load", actor=APPROVER, carry_forward=True)
    assert "exception" in response.json()["detail"]

    item = items[0]
    act("work-exception", id=item["id"], outcome="accepted", note="Checked", term="Margin")
    assert state()["termApprovals"]["Margin"] == "approved"
    approve()
    listed = client.get("/api/load-file").json()["exceptions"]
    assert any(entry["id"] == item["id"] and entry["outcome"] == "accepted" for entry in listed)


def test_approving_a_sent_term_on_the_terms_screen_closes_its_item():
    prepare()
    act("queue-term", name="Margin")
    act("approve-term", name="Margin")
    assert state()["readiness"]["exceptions_worked"]


def test_each_pack_file_is_recognised_by_content_even_when_renamed():
    folder = settings.deal_kit_output / "pack"
    names = list(client.get("/api/workbench").json()["documents"])
    assert len(names) == 8
    for path in folder.iterdir():
        result = client.post("/api/intake/verify?name=renamed.bin", content=path.read_bytes())
        assert result.json() == {"name": "renamed.bin", "recognised": True, "file": path.name}


def test_a_changed_file_is_refused():
    path = settings.deal_kit_output / "pack" / "Bramble_Fee_Letter.pdf"
    result = client.post("/api/intake/verify?name=fee.pdf", content=path.read_bytes() + b" ")
    assert result.json()["recognised"] is False


def test_a_verified_load_is_recorded():
    act("intake-done", verified=True)
    assert state()["intakeVerified"] is True
    assert "matched by content" in state()["audit"][0]["action"]


def test_accepting_every_column_accepts_the_mapping():
    act("intake-done")
    path = settings.deal_kit_output / "pack" / "BAF_Loan_Tape_2026-04.csv"
    with path.open(encoding="utf-8", newline="") as handle:
        columns = next(csv.reader(handle))
    for column in columns[:-1]:
        act("accept-column", column=column)
    assert state()["mappingAccepted"] is False
    assert state()["changes"]["columns_accepted"] == 37
    act("accept-column", column=columns[-1])
    assert state()["mappingAccepted"] is True


def test_approval_needs_the_mapping_accepted():
    act("intake-done")
    act("bulk-approve", names=bulk())
    act("approve-term", name="Facility limit")
    act("approve-term", name="Advance rate")
    act("run")
    for ident, outcome in (("X4", "queried"), ("X5", "escalated"), ("X6", "accepted")):
        act("work-exception", id=ident, outcome=outcome, note="Done")
    response = act("approve-load", actor=APPROVER, carry_forward=True)
    assert "mapping" in response.json()["detail"]


def test_change_summary_lists_edits_and_worked_items():
    prepare()
    act("edit-term", name="Margin", value="3.50%", reason="Side letter")
    summary = state()["changes"]
    assert summary["terms"] == [{"name": "Margin", "from": "3.25%", "to": "3.50%",
                                 "reason": "Side letter"}]
    assert any(item["id"] == "X6" for item in summary["exceptions"])
    assert summary["columns_accepted"] == 38


def rule_change():
    act("propose-rule", rule_id="E5", **{"from": 75000, "to": 70000}, reason="Tighter cap")


def test_preparer_cannot_decide_their_own_rule_change():
    prepare()
    rule_change()
    assert act("approve-rule", reason="Fine by me").status_code == 409


def test_an_approved_rule_change_moves_the_numbers():
    prepare()
    before = client.post("/api/run", json={"dealer_match": True}).json()
    rule_change()
    assert client.post("/api/run", json={"dealer_match": True}).json()["digest"] == before["digest"]
    assert act("approve-rule", actor=APPROVER, reason="Agreed with credit").status_code == 200

    after = client.post("/api/run", json={"dealer_match": True}).json()
    assert after["system"]["eligible_pool"] < before["system"]["eligible_pool"]
    assert any(line["rule_id"] == "E5" for line in after["pool_bridge"]["lines"])
    assert after["pool_bridge"]["unexplained"] == 0

    approve()
    body = client.get("/api/load-file").json()
    assert body["rules"]["version"] == 2
    assert next(r for r in body["rules"]["items"] if r["id"] == "E5")["threshold"] == 70000


def test_a_declined_rule_change_leaves_the_numbers_alone():
    prepare()
    before = client.post("/api/run", json={"dealer_match": True}).json()
    rule_change()
    act("decline-rule", actor=APPROVER, reason="The agreement stands")
    after = client.post("/api/run", json={"dealer_match": True}).json()
    assert after["digest"] == before["digest"]
    approve()
    assert client.get("/api/load-file").json()["rules"]["version"] == 1
