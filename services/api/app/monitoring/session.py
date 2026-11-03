"""The monitoring analyst's session: triage decisions and lender pack approvals.

It uses the same append-only, hash-chained event log as onboarding, under the cycle's own case
number, so state is always worked out from the events and any later change is detectable.
"""

import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.models import CaseEvent, OnboardingCase
from app.session import GENESIS, Refused, _append, chain_intact, load_events

ANALYST = "analyst"
APPROVER = "approver"
ACTOR_NAMES = {ANALYST: "Monitoring analyst", APPROVER: "Second analyst"}
OUTCOMES = {
    "logged": "Logged, no alert",
    "query": "Query to sender",
    "confirmed": "Confirmed issue",
    "expert": "Expert review",
}
PREPARER_EVENTS = {"open-cycle", "confirm-layout", "triage", "send-chase"}
REVIEWER_EVENTS = {"approve-pack"}


def _initial() -> dict[str, Any]:
    return {
        "openedAt": None,
        "layoutConfirmed": False,
        "triage": {},
        "chases": [],
        "packs": {},
        "audit": [],
        "actions": 0,
    }


def _describe(event: CaseEvent) -> tuple[str, str | None]:
    p = event.payload
    return {
        "open-cycle": ("Opened the May 2026 cycle", None),
        "confirm-layout": ("Confirmed the two new Bramble tape columns", None),
        "triage": (
            f"{p.get('title') or p.get('id')}: {OUTCOMES.get(p.get('outcome'), '')}",
            p.get("note"),
        ),
        "send-chase": (f"Sent a further chase for {p.get('label')}", None),
        "approve-pack": (f"Approved and sent the {p.get('name')} lender pack", None),
    }[event.type]


def fold(events: list[CaseEvent]) -> dict[str, Any]:
    state = _initial()
    for event in events:
        p, at = event.payload, event.at.isoformat()
        if event.type == "open-cycle":
            state["openedAt"] = state["openedAt"] or at
        elif event.type == "confirm-layout":
            state["layoutConfirmed"] = True
        elif event.type == "triage":
            state["triage"][p["id"]] = {
                "outcome": p["outcome"],
                "note": p.get("note"),
                "at": at,
                "overrode": bool(p.get("overrode")),
            }
        elif event.type == "send-chase":
            state["chases"].append({"label": p.get("label"), "at": at})
        elif event.type == "approve-pack":
            state["packs"][p["facility"]] = {
                "at": at,
                "by": p.get("user") or ACTOR_NAMES[event.actor],
            }
        if event.type != "open-cycle":
            state["actions"] += 1
        action, reason = _describe(event)
        state["audit"].append(
            {
                "at": at,
                "actor": p.get("user") or ACTOR_NAMES.get(event.actor),
                "action": action,
                "reason": reason,
            }
        )
    return state


def current_session(db: Session, cycle: dict[str, Any]) -> str:
    number = cycle["cycle"]["id"]
    case = db.get(OnboardingCase, number)
    if case is None:
        case = OnboardingCase(number=number, status="in_review")
        db.add(case)
    if case.session_id is None:
        case.session_id = uuid.uuid4().hex
        db.commit()
    return case.session_id


def decided(state: dict[str, Any], item: dict[str, Any]) -> str | None:
    """An item's outcome: the analyst's decision, or the rule's for items within tolerance."""
    if item["id"] in state["triage"]:
        return state["triage"][item["id"]]["outcome"]
    return "logged" if item.get("rule_outcome") == "logged" else None


def pending(state: dict[str, Any], cycle: dict[str, Any], facility: str) -> list[str]:
    return [
        item["title"]
        for item in cycle["findings"]
        if facility in item["facility"].split(",") and decided(state, item) is None
    ]


def _check(
    state: dict[str, Any],
    events: list[CaseEvent],
    cycle: dict[str, Any],
    actor: str,
    kind: str,
    payload: dict[str, Any],
) -> None:
    if actor not in ACTOR_NAMES:
        raise Refused("User not recognised")
    if kind in PREPARER_EVENTS and actor != ANALYST:
        raise Refused("The second analyst reviews the packs and does not triage")
    if kind in REVIEWER_EVENTS:
        user = payload.get("user")
        if any(
            e.type in PREPARER_EVENTS - {"open-cycle"}
            and (e.actor == actor or (user and e.payload.get("user") == user))
            for e in events
        ):
            raise Refused("You prepared this cycle, so a second analyst has to approve its packs")
    if kind == "triage":
        item = next((i for i in cycle["findings"] if i["id"] == payload.get("id")), None)
        if item is None or payload.get("outcome") not in OUTCOMES:
            raise Refused("Unknown finding or outcome")
        if payload["outcome"] != item["suggested"]["outcome"] and not payload.get("note"):
            raise Refused("A reason is required when the decision differs from the suggestion")
        if any(facility in state["packs"] for facility in item["facility"].split(",")):
            raise Refused("This facility's pack is already approved")
    if kind == "approve-pack":
        facility = payload.get("facility")
        if facility in state["packs"]:
            raise Refused("This pack is already approved")
        waiting = pending(state, cycle, facility)
        if waiting:
            raise Refused(f"Every finding needs a decision first: {waiting[0]}")


def record(
    db: Session, cycle: dict[str, Any], actor: str, kind: str, payload: dict[str, Any]
) -> None:
    session_id = current_session(db, cycle)
    events = load_events(db, session_id)
    state = fold(events)
    if kind not in PREPARER_EVENTS | REVIEWER_EVENTS:
        raise Refused("This action is not available")
    if kind == "open-cycle" and state["openedAt"]:
        return
    _check(state, events, cycle, actor, kind, payload)
    if kind == "triage":
        item = next(i for i in cycle["findings"] if i["id"] == payload["id"])
        payload = {
            **payload,
            "title": item["title"],
            "overrode": payload["outcome"] != item["suggested"]["outcome"],
        }
    if kind == "approve-pack":
        name = next(f["name"] for f in cycle["facilities"] if f["id"] == payload["facility"])
        payload = {**payload, "name": name}
    _append(db, session_id, events, actor, kind, payload)
    db.commit()


def reset(db: Session, cycle: dict[str, Any]) -> None:
    number = cycle["cycle"]["id"]
    case = db.get(OnboardingCase, number)
    if case is None:
        case = OnboardingCase(number=number, status="in_review")
        db.add(case)
    case.session_id = uuid.uuid4().hex
    db.commit()


def view(db: Session, cycle: dict[str, Any]) -> dict[str, Any]:
    events = load_events(db, current_session(db, cycle))
    state = fold(events)
    return {
        **state,
        "decisions": {item["id"]: decided(state, item) for item in cycle["findings"]},
        "pending": {f["id"]: pending(state, cycle, f["id"]) for f in cycle["facilities"]},
        "chainIntact": chain_intact(events),
        "chainHead": events[-1].hash if events else GENESIS,
        "firstAt": events[0].at.isoformat() if events else None,
        "lastAt": events[-1].at.isoformat() if events else None,
    }
