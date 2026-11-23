"""Hand-offs between personas, as work items.

Every step that finishes one person's part and waits on another creates a work item for the
next persona: it shows in their My work, in the notification bell, and as "Handed to ... " in the
record's own history. Opening and closing a hand-off are events in a hash-chained log.

New deals create and close hand-offs as they go. The scripted scenarios (case 0412 and the May
cycle) keep their own session logs untouched; their hand-offs are worked out from session state
after each action and kept in a separate chain per session, so their scores never change.
"""

import hashlib
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.deals import audit
from app.deals.models import WorkItem
from app.personas import ROLES, STATIC, Persona, all_personas

DEFAULT_ASSIGNEE = {p.role: p.id for p in STATIC if p.role != "client"}
SCRIPTED_CLIENTS = {"calderwood": "james", "thornbury": "laura"}
# Sign-offs: never routed back to, or completed by, the persona who asked for them.
SIGN_OFF = {"approval", "release", "qc", "expert"}
VERB = {"approval": "for approval", "query": "with a query", "expert": "for expert judgement",
        "qc": "for independent QC", "release": "for release", "review": "for review",
        "work": "", "notice": ""}


def ref(item: WorkItem) -> str:
    return f"WI-{5000 + item.id}"


def name_of(persona_id: str | None, db: Session | None = None) -> str:
    if not persona_id:
        return ""
    for persona in all_personas(db):
        if persona.id == persona_id:
            return persona.name
    return persona_id


def client_persona(client_key: str, db: Session) -> str | None:
    if client_key in SCRIPTED_CLIENTS:
        return SCRIPTED_CLIENTS[client_key]
    if client_key.startswith("deal:"):
        ident = f"client-{client_key.split(':', 1)[1]}"
        return ident if any(p.id == ident for p in all_personas(db)) else None
    return None


def open_item(db: Session, key: str, subject: str, chain: str, kind: str, title: str,
              role: str, link: str, by: Persona | None, detail: str = "",
              client_key: str | None = None, assignee: str | None = None,
              sla_hours: int = 24) -> WorkItem:
    """Hand work to the next persona, once. Reopening a closed key starts a new item."""
    same = or_(WorkItem.key == key, WorkItem.key.like(f"{key}#%"))
    existing = db.scalars(select(WorkItem).where(same).order_by(WorkItem.id.desc())).first()
    if existing and existing.status == "open":
        return existing
    if existing:
        count = db.scalars(select(WorkItem).where(same)).all()
        key = f"{key}#{len(count) + 1}"
    if assignee is None:
        assignee = client_persona(client_key, db) if role == "client" and client_key \
            else DEFAULT_ASSIGNEE.get(role)
    if by is not None and kind in SIGN_OFF and assignee == by.id:
        # The requester cannot sign off their own work: it stays on the role's queue, hidden
        # from them (see mine) and refused to them (see complete).
        assignee = None
    item = WorkItem(key=key[:160], subject=subject, chain=chain, kind=kind, title=title[:200],
                    detail=detail[:400], role=role, assignee=assignee, client_key=client_key,
                    from_persona=by.id if by else None, link=link, status="open",
                    sla_hours=sla_hours)
    db.add(item)
    db.flush()
    target = name_of(assignee, db) or ROLES[role]
    words = VERB.get(kind, "")
    audit.append(db, chain, by.name if by else "Workbench", "handoff",
                 f"Handed to {target}{' ' + words if words else ''}: {title}",
                 {"item": ref(item), "to": assignee, "role": role})
    return item


def close_items(db: Session, prefix: str, by: Persona | None, note: str | None = None,
                outcome: str = "done", exact: bool = False) -> list[WorkItem]:
    match = WorkItem.key == prefix if exact else WorkItem.key.like(f"{prefix}%")
    items = list(db.scalars(select(WorkItem).where(match, WorkItem.status == "open")))
    for item in items:
        # A sign-off is never "done by" the person who asked for it: closed by them, it was
        # withdrawn, not given.
        result = outcome
        if result == "done" and by is not None and item.kind in SIGN_OFF \
                and by.id == item.from_persona:
            result = "withdrawn"
        item.status = result
        item.done_at = datetime.now(UTC)
        item.done_by = by.id if by else None
        item.note = note
        audit.append(db, item.chain, by.name if by else "Workbench", "handoff-done",
                     f"{'Completed' if result == 'done' else 'Withdrew'} {ref(item)}: "
                     f"{item.title}", {"item": ref(item), "note": note})
    return items


def view(item: WorkItem, db: Session | None = None) -> dict[str, Any]:
    now = datetime.now(UTC)
    due = item.created_at + timedelta(hours=item.sla_hours)
    return {
        "id": item.id, "ref": ref(item), "kind": item.kind, "title": item.title,
        "detail": item.detail, "role": item.role, "role_label": ROLES[item.role],
        "assignee": item.assignee, "assignee_name": name_of(item.assignee, db),
        "from": item.from_persona, "from_name": name_of(item.from_persona, db),
        "link": item.link, "status": item.status, "subject": item.subject,
        "created_at": item.created_at.isoformat(), "due_at": due.isoformat(),
        "overdue": item.status == "open" and now > due,
        "age_hours": round((now - item.created_at).total_seconds() / 3600, 1),
        "done_at": item.done_at.isoformat() if item.done_at else None,
        "done_by": item.done_by, "done_by_name": name_of(item.done_by, db), "note": item.note,
    }


def mine(db: Session, persona: Persona) -> dict[str, Any]:
    """A persona's queue: waiting on them, handed off by them, and recently done."""
    if persona.role == "client":
        mine_q = WorkItem.assignee == persona.id
    else:
        mine_q = or_(WorkItem.assignee == persona.id,
                     (WorkItem.assignee.is_(None)) & (WorkItem.role == persona.role))
    waiting = [i for i in db.scalars(select(WorkItem).where(mine_q, WorkItem.status == "open")
                                     .order_by(WorkItem.created_at))
               if not (i.kind in SIGN_OFF and i.from_persona == persona.id)]
    handed = list(db.scalars(select(WorkItem).where(WorkItem.from_persona == persona.id)
                             .order_by(WorkItem.created_at.desc()).limit(15)))
    done = list(db.scalars(select(WorkItem).where(mine_q, WorkItem.status == "done")
                           .order_by(WorkItem.done_at.desc()).limit(15)))
    team = None
    if persona.role in ("head", "admin"):
        rows = db.scalars(select(WorkItem).where(WorkItem.status == "open")).all()
        counts: dict[str, int] = {}
        for item in rows:
            counts[item.assignee or item.role] = counts.get(item.assignee or item.role, 0) + 1
        team = [{"persona": key, "name": name_of(key, db) or ROLES.get(key, key), "open": n}
                for key, n in sorted(counts.items(), key=lambda kv: -kv[1])]
    if persona.role == "client":
        handed, team = [], None
    return {"persona": persona.view(), "waiting": [view(i, db) for i in waiting],
            "handed_off": [view(i, db) for i in handed], "done": [view(i, db) for i in done],
            "team": team}


def for_subject(db: Session, subject: str) -> list[dict[str, Any]]:
    return [view(i, db) for i in db.scalars(select(WorkItem).where(WorkItem.subject == subject)
                                            .order_by(WorkItem.created_at.desc()))]


def complete(db: Session, item_id: int, persona: Persona, note: str | None) -> WorkItem:
    """A persona marks their own item done. An expert's decision goes back to the analyst."""
    from fastapi import HTTPException

    item = db.get(WorkItem, item_id)
    if item is None or item.status != "open":
        raise HTTPException(status_code=404, detail="No open work item")
    mine_item = item.assignee == persona.id or (item.assignee is None and item.role == persona.role)
    if not mine_item:
        raise HTTPException(status_code=403, detail=f"This item is waiting on "
                            f"{name_of(item.assignee, db) or ROLES[item.role]}")
    if item.kind in SIGN_OFF and item.from_persona == persona.id:
        raise HTTPException(status_code=403, detail="You asked for this sign-off, so someone "
                            "else has to give it")
    if item.kind == "expert" and not (note or "").strip():
        raise HTTPException(status_code=422, detail="Record the decision and its reasoning")
    close_items(db, item.key, persona, note, exact=True)
    if item.kind == "expert":
        back = "onboarding_analyst" if item.subject.startswith(("case:", "scripted:0412")) \
            else "monitoring_analyst"
        open_item(db, f"{item.key}:decided", item.subject, item.chain, "review",
                  f"Expert decision: {item.title.removeprefix('Expert judgement: ')}", back,
                  item.link, persona, detail=(note or "")[:400])
    return item


# The scripted scenarios


def chain_for(session_id: str) -> str:
    return hashlib.md5(f"handoff:{session_id}".encode()).hexdigest()


def _persona_for(role: str, client: str | None = None) -> Persona | None:
    if role == "client":
        ident = SCRIPTED_CLIENTS.get(client or "")
        return next((p for p in STATIC if p.id == ident), None)
    return next((p for p in STATIC if p.role == role), None)


def _handed_by(spec: dict[str, Any], by: Persona | None) -> Persona | None:
    """Who handed a scripted item over: the role whose step created it ("from"), not whoever's
    action happened to run the sync. The acting persona counts only if they hold that role."""
    role = spec.get("from")
    if role is None:
        return by
    if by is not None and by.role == role:
        return by
    return _persona_for(role, spec.get("from_client"))


def _closer(item: WorkItem, by: Persona | None) -> tuple[Persona | None, str]:
    """Who closed an item the scripted state no longer wants, and how. The persona it waited on
    completed it; anyone else's action withdrew it. With no persona named (an API call that only
    gives the session actor), the item's own assignee is recorded, never a blank."""
    if by is None:
        holder = next((p for p in STATIC if p.id == item.assignee), None) \
            or _persona_for(item.role)
        return holder, "done"
    if by.id == item.assignee or (item.assignee is None and by.role == item.role):
        return by, "done"
    return by, "withdrawn"


def _sync(db: Session, subject: str, chain: str, wanted: dict[str, dict[str, Any]],
          by: Persona | None) -> None:
    """Open each wanted item that is missing, and close each open item no longer wanted.
    Items a persona completes by hand (notices, expert decisions) are left to them. Idempotent:
    an item already open, or a one-off already seen in this session, is never opened again."""
    open_rows = {i.key.split("#")[0]: i for i in db.scalars(
        select(WorkItem).where(WorkItem.subject == subject, WorkItem.status == "open"))}
    for key, spec in wanted.items():
        if key in open_rows:
            continue
        done_before = db.scalars(select(WorkItem).where(WorkItem.key == key)).first()
        if done_before is not None and spec.get("once"):
            continue
        if done_before is not None and done_before.status == "done" and spec["kind"] in (
                "notice", "expert", "review"):
            continue
        open_item(db, key, subject, chain, spec["kind"], spec["title"], spec["role"],
                  spec["link"], _handed_by(spec, by), spec.get("detail", ""), spec.get("client"))
    for key, item in open_rows.items():
        if key not in wanted and item.kind not in ("notice", "review") and ":decided" not in key:
            closer, outcome = _closer(item, by)
            close_items(db, item.key, closer, outcome=outcome, exact=True)


def sync_onboarding(db: Session, session_id: str, state: dict[str, Any],
                    casework: dict[str, Any] | None, by: Persona | None) -> None:
    subject = f"scripted:0412:{session_id[:16]}"
    prefix = f"0412:{session_id[:12]}"
    wanted: dict[str, dict[str, Any]] = {}
    ready = all(state.get("readiness", {}).values())
    if state.get("intakeDone") and ready and not state.get("approvedAt"):
        wanted[f"{prefix}:approve-load"] = {
            "kind": "approval", "role": "reviewer", "from": "onboarding_analyst",
            "link": "/approve",
            "title": "Approve load file, case 0412 Bramble"}
    edit = state.get("ruleEdit")
    if edit and edit.get("status") == "pending":
        wanted[f"{prefix}:rule:{edit['rule_id']}"] = {
            "kind": "approval", "role": "reviewer", "from": "onboarding_analyst",
            "link": "/approve",
            "title": f"Review rule change to {edit['rule_id']}", "detail": edit.get("reason", "")}
    for ident, outcome in state.get("exceptions", {}).items():
        if outcome == "escalated":
            wanted[f"{prefix}:expert:{ident}"] = {
                "kind": "expert", "role": "expert", "from": "onboarding_analyst",
                "link": f"/exceptions?item={ident}",
                "title": f"Expert judgement: {ident}, case 0412", "once": True}
    if casework:
        for query in casework.get("tracker", {}).get("queries", []):
            if query.get("sent") and not query.get("answered") and not query.get("earlier"):
                wanted[f"{prefix}:query:{query['id']}"] = {
                    "kind": "query", "role": "client", "client": "calderwood",
                    "from": "onboarding_analyst",
                    "link": "/portal", "title": f"Answer query {query['id']}: "
                    f"{query.get('subject') or query.get('topic') or ''}"}
            if query.get("answered") and not query.get("earlier"):
                wanted[f"{prefix}:answered:{query['id']}"] = {
                    "kind": "notice", "role": "onboarding_analyst", "from": "client",
                    "from_client": "calderwood", "link": "/queries",
                    "title": f"Client answered {query['id']}", "once": True}
        qc = casework.get("qc", {})
        if state.get("approvedAt") and qc.get("open"):
            wanted[f"{prefix}:qc"] = {
                "kind": "qc", "role": "qc", "from": "reviewer", "link": "/qc",
                "title": f"Independent QC: {len(qc['open'])} genuine variances, case 0412"}
        if qc.get("can_release"):
            wanted[f"{prefix}:release"] = {"kind": "release", "role": "reviewer", "from": "qc",
                                           "link": "/qc",
                                           "title": "Release first report, case 0412"}
    if state.get("reportReleasedAt"):
        wanted[f"{prefix}:live"] = {
            "kind": "notice", "role": "monitoring_analyst", "from": "reviewer",
            "link": "/monitoring",
            "title": "Bramble is live: first monthly cycle is yours", "once": True}
    _sync(db, subject, chain_for(session_id), wanted, by)


LEVEL_ROLE = {"analyst": "monitoring_analyst", "approver": "reviewer", "senior": "head"}


def last_role(levels: list[dict[str, Any]]) -> str:
    """The role that gave a pack's final approval, so released it."""
    return LEVEL_ROLE.get(levels[-1]["actor"], "reviewer") if levels else "monitoring_analyst"


def prev_role(levels: list[dict[str, Any]], done: int) -> str:
    """Who asks for the next approval level: the level before it, or the preparer."""
    return LEVEL_ROLE.get(levels[done - 1]["actor"], "reviewer") if done else "monitoring_analyst"


def sync_cycle(db: Session, session_id: str, cycle: dict[str, Any], state: dict[str, Any],
               by: Persona | None) -> None:
    subject = f"scripted:cycle:{session_id[:16]}"
    prefix = f"cycle:{session_id[:12]}"
    names = {f["id"]: f for f in cycle["facilities"]}
    wanted: dict[str, dict[str, Any]] = {}
    for finding in cycle["findings"]:
        decided = state.get("triage", {}).get(finding["id"])
        if decided and decided["outcome"] == "expert":
            wanted[f"{prefix}:expert:{finding['id']}"] = {
                "kind": "expert", "role": "expert", "from": "monitoring_analyst", "once": True,
                "link": f"/monitoring/triage?ref={finding['ref']}",
                "title": f"Expert judgement: {finding['title']}"}
        # A finding may name who hears of it once decided: the client contact told of a
        # confirmed issue, or given a point for the status call.
        spec = finding.get("handoff")
        if spec and decided and decided["outcome"] == spec["on"]:
            wanted[f"{prefix}:handoff:{finding['id']}"] = {
                "kind": "notice", "role": spec["role"], "client": spec.get("client"),
                "from": "monitoring_analyst",
                "once": True, "title": spec["title"],
                "link": "/portal" if spec["role"] == "client"
                else f"/monitoring/triage?ref={finding['ref']}",
                "detail": finding["detail"][:400]}
    for facility, levels in state.get("levels", {}).items():
        if facility in state.get("packs", {}):
            client = names[facility]["client"]
            wanted[f"{prefix}:released:{facility}"] = {
                "kind": "notice", "role": "client", "client": client, "from": last_role(levels),
                "once": True,
                "link": "/portal", "title": f"Report released: {names[facility]['name']}"}
            continue
        done = len(state.get("approvals", {}).get(facility, []))
        if 0 < done < len(levels):
            nxt = levels[done]
            role = {"approver": "reviewer", "senior": "head"}.get(nxt["actor"])
            if role:
                wanted[f"{prefix}:approve:{facility}:{nxt['level']}"] = {
                    "kind": "approval", "role": role, "from": prev_role(levels, done),
                    "link": "/monitoring/pack",
                    "title": f"Approve {names[facility]['name']} report, level {nxt['level']}"}
        if state.get("qcOpen", {}).get(facility):
            wanted[f"{prefix}:qc:{facility}"] = {
                "kind": "qc", "role": "qc", "from": "monitoring_analyst",
                "link": "/monitoring/pack",
                "title": f"Independent QC variance: {names[facility]['name']}"}
    for client in state.get("summaries", {}):
        wanted[f"{prefix}:summary:{client}"] = {
            "kind": "notice", "role": "client", "client": client, "from": "monitoring_analyst",
            "once": True, "link": "/portal", "title": "Status-call summary released"}
    for alert in state.get("alerts", []):
        if alert["status"] == "requested":
            wanted[f"{prefix}:alert:{alert['id']}"] = {
                "kind": "approval", "role": "monitoring_analyst", "from": "client",
                "from_client": alert["client"], "link": "/monitoring/monitor",
                "title": f"Client alert request: {alert.get('summary') or alert['request']}"}
    _sync(db, subject, chain_for(session_id), wanted, by)


def subject_history(db: Session, session_id: str) -> dict[str, Any]:
    return audit.history(db, chain_for(session_id))
