"""The onboarding pipeline: generated cases at summary level, with case 0412 and its backbook
deals live from the session, and each event in the audit log tied to the records it touched."""

import pytest
from conftest import RECORDED_RUN
from fastapi.testclient import TestClient

from app import cases
from app.config import settings
from app.main import app

client = TestClient(app)

pytestmark = pytest.mark.skipif(
    not (settings.deal_kit_output / cases.PIPELINE_FILE).exists()
    or not (settings.casework_dir / "casework.json").exists(),
    reason="Build the deal kit and record the casework first")


@pytest.fixture(autouse=True)
def fresh_session(seed_view, monkeypatch):
    monkeypatch.setattr(settings, "pipeline_dir", RECORDED_RUN)
    client.post("/api/session/reset")


def act(kind: str, actor: str = "analyst", **payload):
    response = client.post("/api/session/events",
                           json={"type": kind, "actor": actor, "payload": payload})
    assert response.status_code == 200, response.text
    return response.json()


def pipeline():
    response = client.get("/api/cases")
    assert response.status_code == 200
    return response.json()


def test_the_pipeline_holds_the_active_case_its_backbook_and_the_generated_cases():
    body = pipeline()
    numbers = [case["number"] for case in body["cases"]]
    assert "0412" in numbers
    assert sum(number.startswith("0412-B") for number in numbers) == 4
    assert 10 <= len(numbers) <= 15
    assert {case["deal_type"] for case in body["cases"]} >= {
        "Auto ABF", "Consumer instalment", "SME loans", "Fund finance", "CLO warehouse"}
    assert [case["number"] for case in body["cases"] if case["active"]] == ["0412"]


def test_totals_are_the_sums_of_the_rows():
    body = pipeline()
    rows, summary = body["cases"], body["summary"]
    assert summary["cases"] == len(rows)
    assert sum(summary["by_stage"].values()) == len(rows)
    assert summary["open_exceptions"] == sum(case["exceptions"]["open"] for case in rows)
    assert summary["queries_with_client"] == sum(case["queries"]["with_client"] for case in rows)


def test_case_0412_moves_through_the_stages_with_the_session():
    active = next(case for case in pipeline()["cases"] if case["active"])
    assert active["stage"] == "Intake" and active["documents"]["received"] == 0
    act("intake-done")
    active = next(case for case in pipeline()["cases"] if case["active"])
    assert active["stage"] == "Interpretation"
    assert active["documents"] == {"expected": 9, "received": 8}
    assert active["exceptions"]["open"] == active["exceptions"]["total"] - 5


def test_audit_entries_name_the_records_they_touched():
    state = act("intake-done")
    state = act("approve-term", name="Advance rate")
    entry = state["audit"][-1]
    assert entry["type"] == "approve-term"
    assert entry["refs"] == ["term:Advance rate"]
    assert entry["seq"] == len(state["audit"])
    assert entry["hash"] == state["chainHead"]
    worked = [item for item in state["audit"] if item["type"] == "work-exception"]
    assert all(item["refs"][0].startswith("X") for item in worked)
