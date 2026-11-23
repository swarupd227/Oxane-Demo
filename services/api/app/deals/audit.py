"""Each record's history as a hash-chained, append-only log in case_event.

Every client, case, facility and submission has its own chain. Each event names the person who
acted and says in words what they did, and carries the hash of the event before it.
"""

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import CaseEvent
from app.session import GENESIS, _hash, chain_intact


def append(db: Session, chain: str, actor: str, kind: str, text: str,
           payload: dict[str, Any] | None = None) -> CaseEvent:
    last = db.scalars(select(CaseEvent).where(CaseEvent.session_id == chain)
                      .order_by(CaseEvent.seq.desc()).limit(1)).first()
    previous = last.hash if last else GENESIS
    seq = (last.seq + 1) if last else 1
    at = datetime.now(UTC)
    body = {**(payload or {}), "text": text}
    actor = actor[:32]
    kind = kind[:32]
    event = CaseEvent(session_id=chain, seq=seq, at=at, actor=actor, type=kind, payload=body,
                      earlier=False, prev_hash=previous,
                      hash=_hash(previous, chain, seq, at, actor, kind, body, False))
    db.add(event)
    db.flush()
    return event


def events(db: Session, chain: str) -> list[CaseEvent]:
    return list(db.scalars(select(CaseEvent).where(CaseEvent.session_id == chain)
                           .order_by(CaseEvent.seq)))


def history(db: Session, *chains: str) -> dict[str, Any]:
    """The merged history of one or more chains, newest first, and whether each is intact."""
    entries = []
    intact = True
    for chain in chains:
        rows = events(db, chain)
        intact = intact and chain_intact(rows)
        entries += [{"at": e.at.isoformat(), "actor": e.actor, "type": e.type,
                     "action": e.payload.get("text", e.type), "reason": e.payload.get("reason"),
                     "refs": e.payload.get("refs", []), "hash": e.hash, "seq": e.seq}
                    for e in rows]
    entries.sort(key=lambda item: item["at"], reverse=True)
    return {"entries": entries, "chain_intact": intact}
