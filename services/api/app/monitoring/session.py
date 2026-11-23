"""The monitoring analyst's session: triage, resolutions, alerts and lender pack approvals.

It uses the same append-only, hash-chained event log as onboarding, under the cycle's own case
number, so state is always worked out from the events and any later change is detectable.

Every report is provisional until each approval level its client requires has signed off. Each
level is a different person from the preparer and from every earlier level. Before the first
approval, every finding needs a decision, a blocked load must be resolved, and a genuine QC
variance needs a recorded resolution.
"""

import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.models import CaseEvent, OnboardingCase
from app.session import GENESIS, Refused, _append, chain_intact, load_events

ANALYST = "analyst"
APPROVER = "approver"
SENIOR = "senior"
CLIENT = "client"
ACTOR_NAMES = {
    ANALYST: "Monitoring analyst",
    APPROVER: "Second analyst",
    SENIOR: "Head of monitoring",
    CLIENT: "Client",
}
OUTCOMES = {
    "logged": "Logged, no alert",
    "query": "Query to sender",
    "confirmed": "Confirmed issue",
    "expert": "Expert review",
}
PREPARER_EVENTS = {"open-cycle", "confirm-layout", "triage", "send-chase", "resolve-block",
                   "resolve-qc", "approve-alert", "release-summary"}
REVIEWER_EVENTS = {"approve-pack"}
CLIENT_EVENTS = {"request-alert"}


def _initial() -> dict[str, Any]:
    return {
        "openedAt": None,
        "layoutConfirmed": False,
        "triage": {},
        "chases": [],
        "blocks": {},
        "qcResolved": {},
        "approvals": {},
        "packs": {},
        # Status-call summaries released to each client's portal: client id -> {at, by}.
        "summaries": {},
        "alerts": [],
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
        "resolve-block": (f"Released {p.get('name')}'s held load", p.get("note")),
        "resolve-qc": (f"Resolved the QC variance on {p.get('line')} ({p.get('name')})",
                       p.get("note")),
        "request-alert": (f"Asked for an alert: {p.get('request')}", None),
        "approve-alert": (f"Approved the alert: {p.get('summary')}", None),
        "release-summary": (f"Released the status-call summary to {p.get('name')}", None),
        "approve-pack": (
            f"Approved the {p.get('name')} lender pack at level {p.get('level')}"
            + (": released" if p.get("released") else ""),
            None,
        ),
    }[event.type]


def fold(events: list[CaseEvent]) -> dict[str, Any]:
    state = _initial()
    for event in events:
        p, at = event.payload, event.at.isoformat()
        who = p.get("user") or ACTOR_NAMES.get(event.actor)
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
        elif event.type == "resolve-block":
            state["blocks"][p["facility"]] = {"note": p.get("note"), "at": at, "by": who}
        elif event.type == "resolve-qc":
            state["qcResolved"].setdefault(p["facility"], {})[p["line"]] = {
                "note": p.get("note"), "at": at, "by": who}
        elif event.type == "request-alert":
            state["alerts"].append({
                "id": len(state["alerts"]) + 1,
                "client": p["client"],
                "request": p["request"],
                "rule": p["rule"],
                "summary": p.get("summary"),
                "fires": p.get("fires"),
                "status": "requested",
                "requestedAt": at,
            })
        elif event.type == "approve-alert":
            alert = next(a for a in state["alerts"] if a["id"] == p["alert"])
            alert.update(status="live", approvedAt=at, approvedBy=who)
        elif event.type == "release-summary":
            state["summaries"][p["client"]] = {"at": at, "by": who}
        elif event.type == "approve-pack":
            state["approvals"].setdefault(p["facility"], []).append(
                {"level": p["level"], "title": p.get("title"), "by": who, "actor": event.actor,
                 "at": at})
            if p.get("released"):
                state["packs"][p["facility"]] = {"at": at, "by": who}
        if event.type != "open-cycle":
            state["actions"] += 1
        action, reason = _describe(event)
        # The record each event touches, so a finding or facility can show its own history.
        state["audit"].append({"at": at, "actor": who, "role": event.actor, "action": action,
                               "reason": reason, "type": event.type,
                               "subject": p.get("id") or p.get("facility") or p.get("client"),
                               "hash": event.hash})
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


def levels(cycle: dict[str, Any], facility: str) -> list[dict[str, Any]]:
    """The approval levels after the preparer, as the facility's client requires them."""
    owner = next(f["client"] for f in cycle["facilities"] if f["id"] == facility)
    client = next(c for c in cycle["clients"] if c["id"] == owner)
    return [level for level in client["approval_levels"] if level["level"] > 1]


def held(cycle: dict[str, Any], state: dict[str, Any], facility: str) -> bool:
    feeds = [f for f in cycle["validation"]["feeds"] if f["facility"] == facility and f["held"]]
    return bool(feeds) and facility not in state["blocks"]


def qc_open(cycle: dict[str, Any], state: dict[str, Any], facility: str) -> list[str]:
    done = state["qcResolved"].get(facility, {})
    return [line for line in cycle["qc"][facility]["genuine"] if line not in done]


def _prepared(events: list[CaseEvent], actor: str, user: str | None) -> bool:
    return any(
        e.type in PREPARER_EVENTS - {"open-cycle"}
        and (e.actor == actor or (user and e.payload.get("user") == user))
        for e in events
    )


def _check(
    state: dict[str, Any],
    events: list[CaseEvent],
    cycle: dict[str, Any],
    actor: str,
    kind: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Refuse what the controls forbid. Returns anything the event should also record."""
    if actor not in ACTOR_NAMES:
        raise Refused("User not recognised")
    if kind in PREPARER_EVENTS and actor != ANALYST:
        raise Refused("Only the preparing analyst does this; reviewers approve the packs")
    if kind in CLIENT_EVENTS and actor != CLIENT:
        raise Refused("Only the client asks for an alert")
    facilities = {f["id"]: f for f in cycle["facilities"]}
    if kind == "triage":
        item = next((i for i in cycle["findings"] if i["id"] == payload.get("id")), None)
        if item is None or payload.get("outcome") not in OUTCOMES:
            raise Refused("Unknown finding or outcome")
        if payload["outcome"] != item["suggested"]["outcome"] and not payload.get("note"):
            raise Refused("A reason is required when the decision differs from the suggestion")
        if any(f in state["approvals"] for f in item["facility"].split(",")):
            raise Refused("This facility's pack is already in approval")
        return {"title": item["title"],
                "overrode": payload["outcome"] != item["suggested"]["outcome"]}
    if kind == "resolve-block":
        facility = payload.get("facility")
        feed = next((f for f in cycle["validation"]["feeds"]
                     if f["facility"] == facility and f["held"]), None)
        if feed is None or facility in state["blocks"]:
            raise Refused("This facility has no held load to release")
        if not feed["resolution"]["collapsible"]:
            raise Refused("The rows differ, so only a corrected file can release this load")
        if not (payload.get("note") or "").strip():
            raise Refused("Record how the block was resolved")
        return {"name": facilities[facility]["name"], "rule": feed["resolution"]["rule"]}
    if kind == "resolve-qc":
        facility, line = payload.get("facility"), payload.get("line")
        if facility not in cycle["qc"] or line not in cycle["qc"][facility]["genuine"]:
            raise Refused("No genuine QC variance on that line")
        if not (payload.get("note") or "").strip():
            raise Refused("Record how the variance was resolved")
        return {"name": facilities[facility]["name"]}
    if kind == "request-alert":
        client = next((c for c in cycle["clients"] if c["id"] == payload.get("client")), None)
        if client is None or not client["ai_permitted"]:
            raise Refused("This client's alerts are set up by the analyst")
        if not payload.get("rule"):
            raise Refused("The request has no valid rule")
        return {}
    if kind == "release-summary":
        client = next((c for c in cycle["clients"] if c["id"] == payload.get("client")), None)
        if client is None or not any(s["client"] == client["id"]
                                     for s in cycle.get("client_summaries", [])):
            raise Refused("No summary for that client")
        if client["id"] in state["summaries"]:
            raise Refused("This summary is already released")
        return {"name": client["name"]}
    if kind == "approve-alert":
        alert = next((a for a in state["alerts"] if a["id"] == payload.get("alert")), None)
        if alert is None or alert["status"] != "requested":
            raise Refused("No alert waiting for approval")
        return {"summary": alert["summary"] or alert["request"]}
    if kind == "approve-pack":
        facility = payload.get("facility")
        if facility not in facilities:
            raise Refused("Unknown facility")
        if facility in state["packs"]:
            raise Refused("This pack is already released")
        done = state["approvals"].get(facility, [])
        required = levels(cycle, facility)
        level = required[len(done)]
        if actor != level["actor"]:
            raise Refused(f"Level {level['level']} is for the {level['title'].lower()}")
        user = payload.get("user")
        if _prepared(events, actor, user):
            raise Refused("You prepared this cycle, so a second analyst has to approve its packs")
        if any(a["actor"] == actor or (user and a["by"] == user) for a in done):
            raise Refused("Each approval level needs a different person")
        if not done:
            waiting = pending(state, cycle, facility)
            if waiting:
                raise Refused(f"Every finding needs a decision first: {waiting[0]}")
            if held(cycle, state, facility):
                raise Refused("The load is held by a blocking check. Resolve it first")
            open_qc = qc_open(cycle, state, facility)
            if open_qc:
                raise Refused(f"Resolve the genuine QC variance first: {open_qc[0]}")
        return {
            "name": facilities[facility]["name"],
            "level": level["level"],
            "title": level["title"],
            "released": len(done) + 1 == len(required),
        }
    return {}


def record(
    db: Session, cycle: dict[str, Any], actor: str, kind: str, payload: dict[str, Any]
) -> None:
    session_id = current_session(db, cycle)
    events = load_events(db, session_id)
    state = fold(events)
    if kind not in PREPARER_EVENTS | REVIEWER_EVENTS | CLIENT_EVENTS:
        raise Refused("This action is not available")
    if kind == "open-cycle" and state["openedAt"]:
        return
    extra = _check(state, events, cycle, actor, kind, payload)
    _append(db, session_id, events, actor, kind, {**payload, **extra})
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
    ids = [f["id"] for f in cycle["facilities"]]
    return {
        **state,
        "decisions": {item["id"]: decided(state, item) for item in cycle["findings"]},
        "pending": {f: pending(state, cycle, f) for f in ids},
        "levels": {f: levels(cycle, f) for f in ids},
        "held": {f: held(cycle, state, f) for f in ids},
        "qcOpen": {f: qc_open(cycle, state, f) for f in ids},
        "provisional": {f: f not in state["packs"] for f in ids},
        "chainIntact": chain_intact(events),
        "chainHead": events[-1].hash if events else GENESIS,
        "firstAt": events[0].at.isoformat() if events else None,
        "lastAt": events[-1].at.isoformat() if events else None,
        "events": len(events),
    }
