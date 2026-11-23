"""Who is acting, and what each role may do.

There is no sign-in on the demo, so the acting user comes from the `X-Acting-User` header the
workbench sends. The role is looked up here, never taken from the request, and every write is
checked against it. With sign-in on, identity comes from the platform as before.

One persona model serves both workbenches: the scripted scenarios map a persona onto the actor
their own session logs expect (analyst, approver, senior, client), so their history, scores and
recordings are unchanged.
"""

from dataclasses import asdict, dataclass
from typing import Any

from fastapi import HTTPException, Request

from app.config import settings

HEADER = "x-acting-user"

ROLES = {
    "onboarding_analyst": "Onboarding analyst",
    "expert": "Credit expert",
    "qc": "QC analyst",
    "reviewer": "Second analyst",
    "monitoring_analyst": "Monitoring analyst",
    "head": "Head of monitoring",
    "client": "Client user",
    "admin": "Administrator",
}
INTERNAL = set(ROLES) - {"client"}


@dataclass(frozen=True)
class Persona:
    id: str
    name: str
    role: str
    title: str
    client: str | None = None  # a client user's client: a scripted id or "deal:<id>"

    def view(self) -> dict[str, Any]:
        return {**asdict(self), "role_label": ROLES[self.role]}


STATIC = (
    Persona("hannah", "Hannah Cole", "onboarding_analyst", "Onboarding analyst"),
    Persona("ruth", "Ruth Adeyemi", "expert", "Credit expert"),
    Persona("tom", "Tom Fairley", "qc", "QC analyst, domain team"),
    Persona("marcus", "Marcus Hale", "reviewer", "Second analyst"),
    Persona("priya", "Priya Raman", "monitoring_analyst", "Monitoring analyst"),
    Persona("elena", "Elena Varga", "head", "Head of monitoring"),
    Persona("james", "James Whitcombe", "client", "Director, Calderwood Bank", "calderwood"),
    Persona("laura", "Laura Haskett", "client", "Thornbury Bank", "thornbury"),
    Persona("alex", "Alex Morgan", "admin", "Administrator"),
)


def all_personas(db: Any = None) -> list[Persona]:
    """The fixed team, plus one client user for each client created in the workbench."""
    people = list(STATIC)
    if db is not None:
        from sqlalchemy import select

        from app.deals.models import Client

        for client in db.scalars(select(Client).where(Client.archived_at.is_(None))
                                 .order_by(Client.id)):
            if client.contact_name:
                people.append(Persona(f"client-{client.id}", client.contact_name, "client",
                                      client.name, f"deal:{client.id}"))
    return people


def find(persona_id: str, db: Any = None) -> Persona | None:
    for persona in STATIC:
        if persona.id == persona_id:
            return persona
    if persona_id.startswith("client-") and db is not None:
        return next((p for p in all_personas(db) if p.id == persona_id), None)
    return None


SIGNED_IN_ROLES = {"analyst": "onboarding_analyst", "approver": "reviewer", "senior": "head"}


def acting(request: Request, db: Any = None) -> Persona | None:
    """The persona behind a request, or None when the request names nobody."""
    if settings.auth_required:
        user = request.headers.get("x-ms-client-principal-name") or ""
        role = settings.role_of(user)
        if not role:
            return None
        return Persona(user[:40], user, SIGNED_IN_ROLES[role], ROLES[SIGNED_IN_ROLES[role]])
    ident = request.headers.get(HEADER, "").strip()
    return find(ident, db) if ident else None


def require(request: Request, db: Any, *roles: str) -> Persona:
    persona = acting(request, db)
    if persona is None:
        raise HTTPException(status_code=403, detail="Choose who you are acting as")
    if roles and persona.role not in roles:
        allowed = " or ".join(ROLES[r].lower() for r in roles)
        raise HTTPException(status_code=403, detail=f"Only the {allowed} can do this. You are "
                            f"acting as {persona.name}, {ROLES[persona.role].lower()}")
    return persona


# The scripted scenarios: which persona may record which event, and as which session actor.

ONBOARDING_EVENTS: dict[str, dict[str, str]] = {
    "onboarding_analyst": {kind: "analyst" for kind in (
        "intake-done", "approve-term", "bulk-approve", "queue-term", "edit-term", "accept-mapping",
        "accept-column", "run", "work-exception", "propose-rule", "send-query", "record-answer",
        "accept-backbook")},
    "client": {"record-answer": "analyst"},
    "qc": {"resolve-variance": "analyst"},
    "reviewer": {kind: "approver" for kind in (
        "decline-rule", "approve-rule", "approve-load", "release-report")},
}
CYCLE_EVENTS: dict[str, dict[str, str]] = {
    "monitoring_analyst": {kind: "analyst" for kind in (
        "open-cycle", "confirm-layout", "triage", "send-chase", "resolve-block", "approve-alert",
        "approve-pack", "release-summary")} | {
        # The analyst relays a client's alert request from the Alerts screen. It is recorded as
        # the client's, as it is with sign-in on, and the analyst then approves it separately.
        "request-alert": "client"},
    "qc": {"resolve-qc": "analyst", "open-cycle": "analyst"},
    "reviewer": {"approve-pack": "approver", "open-cycle": "analyst"},
    "head": {"approve-pack": "senior", "open-cycle": "analyst"},
    "client": {"request-alert": "client"},
    "expert": {"open-cycle": "analyst"},
    "admin": {"open-cycle": "analyst"},
}


def scripted_actor(table: dict[str, dict[str, str]], persona: Persona, kind: str) -> str:
    actor = table.get(persona.role, {}).get(kind)
    if actor is None:
        raise HTTPException(status_code=403, detail=f"{persona.name} "
                            f"({ROLES[persona.role].lower()}) cannot do this here")
    return actor


# What a client user may reach. Everything else is internal: unreleased reports, other
# clients, internal notes and model cost.
CLIENT_PATHS = ("/api/health", "/api/personas", "/api/me", "/api/portal", "/api/work",
                "/api/deals/status", "/api/deals/access", "/api/monitoring/alerts/draft",
                "/api/monitoring/session/events", "/api/session/events", "/api/deals/queries/")


def client_may_reach(path: str) -> bool:
    if any(path == p or path.startswith(p + "/") or (p.endswith("/") and path.startswith(p))
           for p in CLIENT_PATHS):
        return True
    return (path.startswith("/api/deals/submissions/") and path.endswith("/report.xlsx")) or \
        path.startswith("/api/monitoring/workbook/")


def for_actor(table: dict[str, dict[str, str]], kind: str, actor: str) -> Persona | None:
    """The persona a session actor stands for when a request names none (the API used directly
    with only the scripted actor), so hand-offs are never attributed to a blank."""
    for role, kinds in table.items():
        if kinds.get(kind) == actor:
            return next((p for p in STATIC if p.role == role), None)
    return None
