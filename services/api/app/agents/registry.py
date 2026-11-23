"""The agent registry: every model agent and code engine, read from registry.yaml.

Downstream links are worked out from each agent's upstream list, so the two can never disagree.
`problems()` is what the tests hold the file to.
"""

import hashlib
import time
from collections.abc import Callable
from functools import cache
from pathlib import Path
from typing import Any

import yaml

from app.config import settings

REGISTRY = Path(__file__).with_name("registry.yaml")
KINDS = {"model", "code"}
TRIGGER_KINDS = {"event", "schedule", "request"}


# Recorded files only change when a run is recorded again, and reading them through a bind
# mount is slow, so what is read from them is kept for a short while.
TTL_SECONDS = 600.0
_kept: dict[tuple[str, ...], tuple[float, Any]] = {}


def cached[T](key: tuple[str, ...], read: Callable[[], T]) -> T:
    now = time.monotonic()
    hit = _kept.get(key)
    if hit is not None and now - hit[0] < TTL_SECONDS:
        return hit[1]
    value = read()
    _kept[key] = (now, value)
    return value


@cache
def raw() -> dict[str, Any]:
    return yaml.safe_load(REGISTRY.read_text(encoding="utf-8"))


def agents() -> list[dict[str, Any]]:
    data = raw()
    listed = data["agents"]
    downstream: dict[str, list[dict[str, str]]] = {a["id"]: [] for a in listed}
    for agent in listed:
        for link in agent["upstream"]:
            if link["agent"] in downstream:
                downstream[link["agent"]].append({"agent": agent["id"],
                                                  "hands_off": link["hands_off"]})
    return [{**agent, "downstream": downstream[agent["id"]]} for agent in listed]


def by_id() -> dict[str, dict[str, Any]]:
    return {agent["id"]: agent for agent in agents()}


def task_owner() -> dict[str, str]:
    """Gateway task name -> the agent that owns it."""
    return {task: agent["id"] for agent in raw()["agents"] for task in agent["gateway_tasks"]}


def task_label(task: str) -> str:
    for agent in raw()["agents"]:
        if task in agent["gateway_tasks"]:
            return agent["gateway_tasks"][task]
    return task.replace("_", " ").capitalize()


def fixture_dirs() -> list[Path]:
    return [settings.llm_fixtures, settings.casework_llm_fixtures, settings.cycle_llm_fixtures]


def prompt_version(agent: dict[str, Any]) -> dict[str, Any] | None:
    """The recorded prompt set: each recording is keyed by a hash of its full request, so a
    changed prompt gives a new key and a new version here."""
    keys = sorted(cached(
        ("prompt", agent["id"], *map(str, fixture_dirs())),
        lambda: [f"{path.parent.name}/{path.stem}" for folder in fixture_dirs()
                 for task in agent["gateway_tasks"] for path in (folder / task).glob("*.json")]))
    if not keys:
        return None
    digest = hashlib.sha256("\n".join(keys).encode("utf-8")).hexdigest()
    return {"id": f"rec-{digest[:8]}", "recordings": len(keys)}


def problems() -> list[str]:
    """Everything wrong with the registry, as sentences. Empty when it is sound."""
    data = raw()
    found: list[str] = []
    stages = [s["id"] for s in data["stages"]]
    pains = {p["id"] for p in data["pain_points"]}
    classes = {c["id"] for c in data["asset_classes"]}
    constraints = set(data["constraints"])
    ids = [a["id"] for a in data["agents"]]
    order = {a["id"]: stages.index(a["stage"]) for a in data["agents"] if a["stage"] in stages}
    if len(ids) != len(set(ids)):
        found.append("Agent ids repeat")
    seen_tasks: dict[str, str] = {}
    for agent in data["agents"]:
        aid = agent["id"]
        if agent["kind"] not in KINDS:
            found.append(f"{aid}: unknown kind {agent['kind']}")
        if agent["stage"] not in stages:
            found.append(f"{aid}: unknown stage {agent['stage']}")
        for trigger in agent["triggers"]:
            if trigger["kind"] not in TRIGGER_KINDS:
                found.append(f"{aid}: unknown trigger kind {trigger['kind']}")
        if not agent["triggers"]:
            found.append(f"{aid}: no trigger")
        for link in agent["upstream"]:
            if link["agent"] not in order:
                found.append(f"{aid}: upstream {link['agent']} does not resolve")
            elif aid in order and order[link["agent"]] > order[aid]:
                found.append(f"{aid}: upstream {link['agent']} sits in a later stage")
            if link["agent"] == aid:
                found.append(f"{aid}: depends on itself")
        for pain in agent["pain_points"]:
            if pain not in pains:
                found.append(f"{aid}: unknown pain point {pain}")
        for when in ("now", "after_pilot"):
            for asset in agent["asset_classes"][when]:
                if asset not in classes:
                    found.append(f"{aid}: unknown asset class {asset}")
        for name in agent["constraints"]:
            if name not in constraints:
                found.append(f"{aid}: unknown constraint {name}")
        for uc, steps in agent["use_cases"].items():
            known = data["use_cases"].get(uc, {}).get("steps", {})
            for step in steps:
                if step not in known:
                    found.append(f"{aid}: {uc} has no step {step}")
        if agent["kind"] == "model":
            if not agent["gateway_tasks"]:
                found.append(f"{aid}: a model agent with no gateway task")
            if "no_ai_clients" not in agent["constraints"]:
                found.append(f"{aid}: a model agent without the no-AI client constraint")
        elif agent["gateway_tasks"]:
            found.append(f"{aid}: a code engine that owns gateway tasks")
        for task in agent["gateway_tasks"]:
            if task in seen_tasks:
                found.append(f"{task}: owned by {seen_tasks[task]} and {aid}")
            seen_tasks[task] = aid
    found += _cycles(data["agents"])
    return found


def _cycles(listed: list[dict[str, Any]]) -> list[str]:
    graph = {a["id"]: [link["agent"] for link in a["upstream"]] for a in listed}
    state: dict[str, int] = {}

    def visit(node: str) -> bool:
        if state.get(node) == 1:
            return True
        if state.get(node) == 2 or node not in graph:
            return False
        state[node] = 1
        looped = any(visit(up) for up in graph[node])
        state[node] = 2
        return looped

    return [f"{node}: dependency loop" for node in graph if visit(node)][:1]
