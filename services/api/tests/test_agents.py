"""The agents console: the registry matches the code's model calls, and the run log matches the
recorded calls, with the no-AI client's calls refused at zero cost."""

import ast
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.agents import registry, runlog
from app.agents.models import AgentRun
from app.config import settings
from app.db import engine
from app.main import app
from app.pipeline.gateway import Gateway

APP = Path(__file__).resolve().parents[1] / "app"
client = TestClient(app)


def gateway_tasks_in_code() -> dict[str, list[str]]:
    """Every literal task name passed as the first argument of a `.parse(...)` call in app/."""
    found: dict[str, list[str]] = {}
    for path in APP.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "parse" and node.args):
                continue
            first = node.args[0]
            names = [first] if isinstance(first, ast.Constant) else \
                [first.body, first.orelse] if isinstance(first, ast.IfExp) else []
            for name in names:
                if isinstance(name, ast.Constant) and isinstance(name.value, str) \
                        and name.value.isidentifier():
                    found.setdefault(name.value, []).append(str(path.relative_to(APP)))
    return found


def test_registry_has_no_problems():
    assert registry.problems() == []


def test_the_scan_sees_the_model_calls():
    found = gateway_tasks_in_code()
    # One from each place that calls the model.
    for task in ("classify", "extract_all", "extract_tier1", "trace_definitions",
                 "suggest_triage", "draft_status_brief"):
        assert task in found


def test_every_gateway_task_in_the_code_maps_to_exactly_one_agent():
    owners: dict[str, list[str]] = {}
    for agent in registry.raw()["agents"]:
        for task in agent["gateway_tasks"]:
            owners.setdefault(task, []).append(agent["id"])
    for task, places in gateway_tasks_in_code().items():
        assert len(owners.get(task, [])) == 1, f"{task} ({places[0]}) owned by {owners.get(task)}"


def test_every_registered_task_is_called_somewhere():
    assert set(registry.task_owner()) <= set(gateway_tasks_in_code())


def test_every_recorded_task_maps_to_an_agent():
    owners = registry.task_owner()
    for folder in registry.fixture_dirs():
        for task_dir in folder.iterdir() if folder.exists() else []:
            if task_dir.is_dir():
                assert task_dir.name in owners, task_dir.name


def test_every_dependency_resolves_and_runs_forward():
    agents = registry.by_id()
    stages = [s["id"] for s in registry.raw()["stages"]]
    for agent in agents.values():
        for link in agent["upstream"]:
            assert link["agent"] in agents
            assert stages.index(agents[link["agent"]]["stage"]) <= stages.index(agent["stage"])
        for link in agent["downstream"]:
            assert agent["id"] in [u["agent"] for u in agents[link["agent"]]["upstream"]]


def test_model_agents_carry_the_no_ai_constraint_and_code_engines_call_no_model():
    agents = registry.agents()
    assert {a["kind"] for a in agents} == {"model", "code"}
    for agent in agents:
        if agent["kind"] == "model":
            assert "no_ai_clients" in agent["constraints"], agent["id"]
            assert agent["gateway_tasks"], agent["id"]
        else:
            assert not agent["gateway_tasks"], agent["id"]
            assert "deterministic" in agent["constraints"], agent["id"]


def test_the_registry_names_the_gateway_model():
    assert registry.raw()["model"]["name"] == Gateway(mode="replay", fixtures=Path(".")).model


def test_every_agent_answers_a_pain_point_and_a_use_case_step():
    for agent in registry.agents():
        assert agent["pain_points"] and agent["use_cases"], agent["id"]
    covered = {p for a in registry.agents() for p in a["pain_points"]}
    assert covered == {p["id"] for p in registry.raw()["pain_points"]}


recorded = pytest.mark.skipif(
    not (settings.cycle_dir / "cycle.json").exists(), reason="No monitoring cycle has been recorded"
)


def recorded_files() -> list[Path]:
    return [p for folder in registry.fixture_dirs() for p in folder.glob("*/*.json")]


@recorded
def test_the_run_log_lists_every_recorded_call_once_with_its_cost():
    rows = [r for r in runlog.recorded_runs()
            if r["outcome"] not in ("refused", "pending_recording")]
    files = recorded_files()
    assert len(rows) == len(files)
    assert len({r["id"] for r in rows}) == len(rows)
    expected = 0.0
    for path in files:
        saved = json.loads(path.read_text(encoding="utf-8"))
        usage = runlog.Usage(**saved["usage"])
        expected += usage.cost_usd(saved["model"])
    assert round(sum(r["cost_usd"] for r in rows), 2) == round(expected, 2)
    assert all(r["agent"] for r in rows)
    assert all(r["outcome"] in runlog.OUTCOMES for r in rows)


@recorded
def test_the_no_ai_client_makes_no_calls_and_shows_its_refusals():
    cycle = json.loads((settings.cycle_dir / "cycle.json").read_text(encoding="utf-8"))
    blocked = {c["id"] for c in cycle["clients"] if not c["ai_permitted"]}
    assert blocked == {"thornbury"}
    rows = [r for r in runlog.recorded_runs() if r["client"] in blocked]
    assert rows, "Thornbury shows its refused calls"
    assert {r["outcome"] for r in rows} == {"refused"}
    assert sum(r["tokens_in"] + r["tokens_out"] for r in rows) == 0
    assert sum(r["cost_usd"] for r in rows) == 0
    stats = runlog.stats(rows)
    assert stats["runs"] == 0 and stats["refused"] == len(rows)


def test_stats_count_acceptance_over_decided_runs_only():
    def row(outcome, cost=0.01):
        return {"outcome": outcome, "tokens_in": 10, "tokens_out": 5, "cost_usd": cost,
                "duration_ms": 100, "at": "2026-06-24T10:00:00+00:00"}

    stats = runlog.stats([row("accepted"), row("accepted"), row("edited"), row("rejected"),
                          row("awaiting_review"), row("refused", 0)])
    assert stats["runs"] == 5
    assert stats["refused"] == 1
    assert stats["decided"] == 4
    assert stats["acceptance"] == 0.5
    assert stats["cost_usd"] == 0.05
    assert runlog.stats([row("awaiting_review")])["acceptance"] is None


def test_record_run_writes_a_live_run_the_log_shows():
    with Session(engine) as db:
        rid = runlog.record_run("deals_extract", "fenwick", "Extract terms · Fenwick", 1200, 300,
                                0.0108, "accepted", 4200, ref="Case N-0001", db=db)
        assert rid is not None
        rows = runlog.stored_runs(db)
        mine = next(r for r in rows if r["id"] == f"live-{rid}")
        assert mine["agent"] == "extraction"
        assert mine["cost_usd"] == 0.0108 and mine["tokens_in"] == 1200
        assert mine["workflow"] == "New deals"
        db.rollback()


def test_record_run_commits_on_its_own_and_refuses_an_unknown_outcome():
    with pytest.raises(ValueError):
        runlog.record_run("draft_pack", "calderwood", "x", 0, 0, 0, "approved", 0)
    rid = runlog.record_run("draft_pack", "thornbury", "Pack · Larkspur", 0, 0, 0, "refused", 0)
    try:
        assert rid is not None
        body = client.get("/api/agents/runs", params={"agent": "drafting"}).json()
        assert any(r["id"] == f"live-{rid}" and r["outcome"] == "refused" for r in body["runs"])
    finally:
        with Session(engine) as db:
            db.execute(delete(AgentRun).where(AgentRun.id == rid))
            db.commit()


def test_the_console_endpoints():
    body = client.get("/api/agents").json()
    assert len(body["agents"]) == len(registry.raw()["agents"])
    assert [s["id"] for s in body["stages"]][0] == "receive"
    model = [a for a in body["agents"] if a["kind"] == "model"]
    assert all(a["stats"] is not None for a in model)
    detail = client.get("/api/agents/triage").json()
    assert detail["name"] == "Triage" and "runs" in detail
    assert client.get("/api/agents/nobody").status_code == 404
