"""The analyst's session, held as an append-only log of events.

State is never stored. It is worked out from the events, so the log cannot
disagree with what the screen shows. Each event carries the hash of the one
before it, which makes any later change to the history detectable.
"""

import hashlib
import json
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.deal import load_deal
from app.models import CaseEvent, OnboardingCase

ANALYST = "analyst"
APPROVER = "approver"
ACTOR_NAMES = {ANALYST: "Onboarding analyst", APPROVER: "Second analyst"}
GENESIS = "0" * 64

# These are worked live on stage. Everything else was done before the demo, and says so.
LIVE_TERMS = {"Facility limit", "Advance rate"}
TERM_EXCEPTIONS = {"Advance rate": "X1", "Facility limit": "X3"}
EARLIER_EXCEPTIONS = {"X2": "queried", "X7": "queried", "X8": "accepted", "X9": "accepted",
                      "X10": "accepted"}

# What only the person who prepared the case may do, and what only a reviewer may do.
PREPARER_EVENTS = {"intake-done", "approve-term", "bulk-approve", "queue-term", "edit-term",
                   "accept-mapping", "run", "work-exception", "propose-rule"}
REVIEWER_EVENTS = {"decline-rule", "approve-load"}


class Refused(Exception):
    """A person tried something the controls do not allow."""


def _initial() -> dict[str, Any]:
    return {
        "startedAt": None, "intakeDone": False, "termApprovals": {}, "termEdits": {},
        "mappingAccepted": False, "ran": False, "dealerMatched": False, "exceptions": {},
        "ruleEdit": None, "approvedAt": None, "approvedBy": None, "audit": [],
    }


def _describe(event: CaseEvent) -> tuple[str, str | None]:
    """The audit line for an event, and its reason."""
    p = event.payload
    return {
        "intake-done": ("Uploaded 8-file document pack", None),
        "approve-term": (f"Approved {p.get('name')}", None),
        "bulk-approve": (f"Bulk approved {len(p.get('names', []))} Tier 2 and 3 values", None),
        "queue-term": (f"Sent {p.get('name')} to the queue", None),
        "edit-term": (f"Edited {p.get('name')} to {p.get('value')}", p.get("reason")),
        "accept-mapping": ("Accepted tape mapping", None),
        "run": ("Ran the April tape: 16 rules run, E7 not evaluated", None),
        "work-exception": (f"{p.get('id')}: {p.get('outcome')}", p.get("note")),
        "propose-rule": (f"Proposed {p.get('rule_id')}: {p.get('from')} to {p.get('to')}",
                         p.get("reason")),
        "decline-rule": (f"Declined rule change to {p.get('rule_id')}", p.get("reason")),
        "approve-load": (f"Approved load file with {p.get('open_items', 0)} open items", None),
    }[event.type]


def fold(events: list[CaseEvent]) -> dict[str, Any]:
    state = _initial()
    for event in events:
        p = event.payload
        at = event.at.isoformat()
        kind = event.type
        if kind == "intake-done":
            state["intakeDone"] = True
            state["startedAt"] = at
        elif kind == "approve-term":
            state["termApprovals"][p["name"]] = "approved"
            if p["name"] in TERM_EXCEPTIONS:
                state["exceptions"][TERM_EXCEPTIONS[p["name"]]] = "accepted"
        elif kind == "bulk-approve":
            state["termApprovals"].update(dict.fromkeys(p["names"], "approved"))
        elif kind == "queue-term":
            state["termApprovals"][p["name"]] = "queued"
        elif kind == "edit-term":
            state["termEdits"][p["name"]] = p["value"]
        elif kind == "accept-mapping":
            state["mappingAccepted"] = True
        elif kind == "run":
            state["ran"] = True
        elif kind == "work-exception":
            state["exceptions"][p["id"]] = p["outcome"]
            if p["id"] == "X6" and p["outcome"] == "accepted":
                state["dealerMatched"] = True
        elif kind == "propose-rule":
            state["ruleEdit"] = {key: p[key] for key in ("rule_id", "from", "to", "reason")}
            state["ruleEdit"]["status"] = "pending"
        elif kind == "decline-rule":
            state["ruleEdit"].update(status="declined", decline_reason=p["reason"])
        elif kind == "approve-load":
            state["approvedAt"] = at
            state["approvedBy"] = event.actor
        action, reason = _describe(event)
        state["audit"].append({"at": at, "actor": ACTOR_NAMES.get(event.actor, event.actor),
                               "action": action, "reason": reason, "earlier": event.earlier})
    return state


def _hash(prev: str, session_id: str, seq: int, at: datetime, actor: str, kind: str,
          payload: dict[str, Any], earlier: bool) -> str:
    body = json.dumps([prev, session_id, seq, at.isoformat(), actor, kind, payload, earlier],
                      sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def chain_intact(events: list[CaseEvent]) -> bool:
    previous = GENESIS
    for event in events:
        expected = _hash(previous, event.session_id, event.seq, event.at, event.actor, event.type,
                         event.payload, event.earlier)
        if event.prev_hash != previous or event.hash != expected:
            return False
        previous = event.hash
    return True


def current_session(db: Session) -> str:
    number = load_deal().case.number
    case = db.get(OnboardingCase, number)
    if case is None:
        case = OnboardingCase(number=number)
        db.add(case)
    if case.session_id is None:
        case.session_id = uuid.uuid4().hex
        db.commit()
    return case.session_id


def load_events(db: Session, session_id: str) -> list[CaseEvent]:
    query = select(CaseEvent).where(CaseEvent.session_id == session_id).order_by(CaseEvent.seq)
    return list(db.scalars(query))


def _append(db: Session, session_id: str, events: list[CaseEvent], actor: str, kind: str,
            payload: dict[str, Any], earlier: bool = False) -> None:
    seq = len(events) + 1
    previous = events[-1].hash if events else GENESIS
    at = datetime.now(UTC)
    event = CaseEvent(
        session_id=session_id, seq=seq, at=at, actor=actor, type=kind, payload=payload,
        earlier=earlier, prev_hash=previous,
        hash=_hash(previous, session_id, seq, at, actor, kind, payload, earlier),
    )
    db.add(event)
    events.append(event)


def open_items(state: dict[str, Any], workbench: dict[str, Any]) -> list[str]:
    """What stays open after approval, because it waits on someone outside the case."""
    items = [f"{item['id']}: {item['title']} ({item['owner']})"
             for item in workbench["exceptions"]
             if item.get("blocking") and state["exceptions"].get(item["id"]) != "accepted"]
    items += [f"{term['name']}: open until the source arrives"
              for term in workbench["terms"] if term["status"] == "missing"]
    return items


def readiness(state: dict[str, Any], workbench: dict[str, Any]) -> dict[str, bool]:
    tier1 = [term for term in workbench["terms"]
             if term["tier"] == 1 and term["status"] != "missing"]
    edit = state["ruleEdit"]
    return {
        "tier1_approved": all(state["termApprovals"].get(t["name"]) == "approved" for t in tier1),
        "exceptions_worked": all(i["id"] in state["exceptions"] for i in workbench["exceptions"]),
        "run_complete": state["ran"],
        "no_rule_pending": not (edit and edit["status"] == "pending"),
    }


READINESS_TEXT = {
    "tier1_approved": "Every Tier 1 value needs an approval first",
    "exceptions_worked": "Every exception must be worked first",
    "run_complete": "The validation run has not been done",
    "no_rule_pending": "A rule change is still waiting for a decision",
}


def _check(state: dict[str, Any], events: list[CaseEvent], workbench: dict[str, Any], actor: str,
           kind: str, payload: dict[str, Any]) -> None:
    if actor not in ACTOR_NAMES:
        raise Refused("Unknown analyst")
    if state["approvedAt"]:
        raise Refused("This case is approved and can no longer be changed")
    if kind in PREPARER_EVENTS and actor != ANALYST:
        raise Refused("A reviewer cannot change the case they are reviewing")
    if kind in REVIEWER_EVENTS and any(
        event.actor == actor and event.type in PREPARER_EVENTS for event in events
    ):
        raise Refused("You prepared this case, so a second analyst has to review it")
    if kind != "intake-done" and not state["intakeDone"]:
        raise Refused("Upload the document pack first")

    terms = {term["name"]: term for term in workbench["terms"]}
    if kind == "bulk-approve":
        wrong = [name for name in payload["names"]
                 if name not in terms or terms[name]["tier"] == 1
                 or terms[name]["confidence"] != "high"]
        if wrong:
            raise Refused(f"Only high-confidence Tier 2 and 3 values can be bulk approved: {wrong}")
    if kind == "approve-term" and terms.get(payload["name"], {}).get("status") == "missing":
        raise Refused("A value that was not found cannot be approved")
    if kind in ("edit-term", "propose-rule", "decline-rule") and not payload.get("reason"):
        raise Refused("A reason is required")
    if kind == "decline-rule" and not (state["ruleEdit"]
                                       and state["ruleEdit"]["status"] == "pending"):
        raise Refused("There is no rule change waiting")
    if kind == "approve-load":
        unmet = [READINESS_TEXT[name] for name, done in readiness(state, workbench).items()
                 if not done]
        if unmet:
            raise Refused(unmet[0])
        if open_items(state, workbench) and not payload.get("carry_forward"):
            raise Refused("Open items must be carried forward explicitly")


def record(db: Session, workbench: dict[str, Any], actor: str, kind: str,
           payload: dict[str, Any]) -> None:
    session_id = current_session(db)
    events = load_events(db, session_id)
    state = fold(events)
    if kind == "intake-done" and state["intakeDone"]:
        return
    if kind == "run" and state["ran"]:
        return
    if kind not in PREPARER_EVENTS | REVIEWER_EVENTS:
        raise Refused(f"Unknown action: {kind}")
    _check(state, events, workbench, actor, kind, payload)
    if kind == "approve-load":
        payload = {**payload, "open_items": len(open_items(state, workbench))}
    if kind == "decline-rule":
        payload = {**payload, "rule_id": state["ruleEdit"]["rule_id"]}
    _append(db, session_id, events, actor, kind, payload)
    if kind == "intake-done":
        _record_earlier_work(db, session_id, events, workbench)
    db.commit()


def _record_earlier_work(db: Session, session_id: str, events: list[CaseEvent],
                         workbench: dict[str, Any]) -> None:
    """Work that happened before the demo goes in the log, labelled as such."""
    for term in workbench["terms"]:
        if term["tier"] == 1 and term["confidence"] == "high" and term["name"] not in LIVE_TERMS:
            _append(db, session_id, events, ANALYST, "approve-term", {"name": term["name"]}, True)
    known = {item["id"] for item in workbench["exceptions"]}
    for exception, outcome in EARLIER_EXCEPTIONS.items():
        if exception in known:
            _append(db, session_id, events, ANALYST, "work-exception",
                    {"id": exception, "outcome": outcome, "note": None}, True)


def reset(db: Session) -> None:
    """Start a fresh session. The old one stays in the log, because nothing is ever deleted."""
    number = load_deal().case.number
    case = db.get(OnboardingCase, number)
    if case is None:
        case = OnboardingCase(number=number)
        db.add(case)
    case.session_id = uuid.uuid4().hex
    db.commit()


def view(db: Session, workbench: dict[str, Any]) -> dict[str, Any]:
    events = load_events(db, current_session(db))
    state = fold(events)
    return {
        **state,
        "readiness": readiness(state, workbench),
        "openItems": open_items(state, workbench),
        "chainIntact": chain_intact(events),
        "chainHead": events[-1].hash if events else GENESIS,
    }
