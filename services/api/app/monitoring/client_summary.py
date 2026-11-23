"""The status-call summary a client sees in the portal, once the analyst releases it.

The status-call brief is internal: written to Oxane's named contact, about the client in the
third person, with drafting marks. The client gets a separate summary written to them, built by
code from the same facts the brief is drafted from (never from the model's wording), with every
figure a {{placeholder}} filled by code. It reaches the portal only after the monitoring analyst
releases it (the "release-summary" event in the cycle session).
"""

import re
from datetime import date, timedelta
from typing import Any

PLACEHOLDER = re.compile(r"\{\{(\w+)\}\}")

# Words written about the client in the third person, as they read when written to the client.
SECOND_PERSON = [
    ("with the client's consent", "with your consent"),
    ("on this client's facilities", "on your facilities"),
    ("the client may need to decide", "you may need to decide"),
    ("the lender has been told", "we have told you"),
    ("Logged; no query needed.", "No action needed from you."),
    ("administrator asked to correct it", "we have asked the administrator to correct it"),
    ("the pricing service has been asked to resend it", "we have asked the pricing service to "
     "resend it"),
]
# Marks that belong to Oxane's own working view and never to a client-facing text.
INTERNAL_MARKS = ("Template", "draft", "pending", "Drafted", "Priya", "Oxane monitoring")


def call_week(as_of: str | date) -> date:
    """The Monday of the week the status call falls in."""
    day = as_of if isinstance(as_of, date) else date.fromisoformat(as_of)
    return day - timedelta(days=day.weekday())


def pretty(day: date) -> str:
    return f"{day.day} {day:%b %Y}"


def second_person(text: str) -> str:
    for old, new in SECOND_PERSON:
        text = text.replace(old, new)
    return text


def _points(points: list[str]) -> list[str]:
    return [second_person(p.rstrip(".") + ".") for p in points if p and p.strip()]


def internal_terms(client: dict[str, Any], team: dict[str, Any]) -> list[str]:
    """Names and marks a client-facing text must never contain: Oxane's people, the client's
    named Oxane contact, and drafting marks."""
    names = [client["contact"]["name"]] + [m["name"] for k, m in team.items()
                                           if k != "client" and isinstance(m, dict)
                                           and m.get("name")]
    firsts = [n.split()[0] for n in names]
    return sorted({*names, *firsts, *INTERNAL_MARKS})


def problems(summary: dict[str, Any], client: dict[str, Any], team: dict[str, Any],
             other_clients: list[dict[str, Any]]) -> list[str]:
    """Why a summary is not fit for the client, or [] when it is."""
    texts = [summary["title"], summary["greeting"], summary["opening"]] + [
        p for s in summary["sections"] for p in [s["heading"], *s["points"]]]
    found = []
    for term in internal_terms(client, team):
        if any(re.search(rf"\b{re.escape(term)}\b", t) for t in texts):
            found.append(f"internal term {term!r}")
    for other in other_clients:
        for name in (other["name"], other["client_contact"]["name"], other["contact"]["name"]):
            if any(name in t for t in texts):
                found.append(f"another client's name {name!r}")
    unknown = sorted({m for t in texts for m in PLACEHOLDER.findall(t)
                      if m not in summary["figures"]})
    found += [f"unknown placeholder {u}" for u in unknown]
    if any("client's" in t or "the client " in t for t in texts):
        found.append("refers to the client in the third person")
    return found


def build(client: dict[str, Any], cycle: dict[str, Any], sections: list[dict[str, Any]],
          figures: dict[str, Any]) -> dict[str, Any]:
    """The client's summary from code-written facts: `sections` is [{heading, points}], each
    point a code-written fact with {{placeholders}} for `figures`."""
    first = client["client_contact"]["name"].split()[0]
    week = pretty(call_week(cycle["as_of"]))
    return {
        "client": client["id"],
        "title": f"{cycle['label']} monitoring summary",
        "greeting": f"Dear {first},",
        "opening": f"Here is where your facilities stand for the {cycle['label']} cycle, ahead "
                   f"of our status call in the week of {week}. Figures are as calculated by our "
                   "checks; anything that needs your decision is marked.",
        "sections": [{"heading": s["heading"], "points": _points(s["points"])}
                     for s in sections if [p for p in s["points"] if p and p.strip()]],
        "figures": {k: {"value": v["value"], "means": v["means"], "source": v.get("source")}
                    for k, v in figures.items()},
        "week_of": call_week(cycle["as_of"]).isoformat(),
    }
