"""Agents console endpoints: the registry with each agent's runs, and the run log."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.agents import registry, runlog
from app.config import settings
from app.db import get_session

router = APIRouter(prefix="/api/agents", tags=["agents"])
SessionDep = Annotated[Session, Depends(get_session)]


def _clients() -> dict[str, dict[str, Any]]:
    cycle = runlog._load(settings.cycle_dir / "cycle.json") or {}
    return {c["id"]: {"id": c["id"], "name": c["name"], "ai_permitted": c["ai_permitted"]}
            for c in cycle.get("clients", [])}


def _view(agent: dict[str, Any], rows: list[dict[str, Any]]) -> dict[str, Any]:
    mine = [r for r in rows if r["agent"] == agent["id"]]
    return {**agent, "prompt_version": registry.prompt_version(agent),
            "stats": runlog.stats(mine) if agent["kind"] == "model" else None}


@router.get("")
def get_agents(db: SessionDep) -> dict[str, Any]:
    data = registry.raw()
    rows = runlog.all_runs(db)
    listed = [_view(agent, rows) for agent in registry.agents()]
    return {
        "version": data["version"],
        "model": data["model"],
        "llm_mode": settings.llm_mode,
        "stages": data["stages"],
        "use_cases": data["use_cases"],
        "pain_points": data["pain_points"],
        "asset_classes": data["asset_classes"],
        "constraints": data["constraints"],
        "outcomes": runlog.OUTCOMES,
        "clients": _clients(),
        "agents": listed,
        "totals": runlog.stats(rows),
        "by_client": {cid: runlog.stats([r for r in rows if r["client"] == cid])
                      for cid in sorted({r["client"] for r in rows})},
        "runs": rows,
    }


@router.get("/runs")
def get_runs(db: SessionDep, agent: str | None = None, client: str | None = None,
             outcome: str | None = None) -> dict[str, Any]:
    rows = runlog.all_runs(db)
    if agent:
        rows = [r for r in rows if r["agent"] == agent]
    if client:
        rows = [r for r in rows if r["client"] == client]
    if outcome:
        rows = [r for r in rows if r["outcome"] == outcome]
    return {"runs": rows, "stats": runlog.stats(rows), "outcomes": runlog.OUTCOMES}


@router.get("/{agent_id}")
def get_agent(agent_id: str, db: SessionDep) -> dict[str, Any]:
    agent = registry.by_id().get(agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail="Unknown agent")
    rows = runlog.all_runs(db)
    return {**_view(agent, rows), "runs": [r for r in rows if r["agent"] == agent_id]}
