"""The casework as the workbench shows it: the recorded run joined with the session.

The query tracker splits elapsed time into analyst time and time waiting on the client, in
business hours on the sandbox clock. The QC comparison holds the first report as provisional
until every genuine variance has a resolution and a second analyst releases it. The
configuration workbook's thresholds show any rule change a second analyst approved.
"""

import json
from datetime import datetime, time, timedelta
from functools import lru_cache
from typing import Any

from app.casework.run import record
from app.config import settings
from app.session import Refused


def current() -> dict[str, Any]:
    path = settings.casework_dir / "casework.json"
    if not path.exists():
        raise FileNotFoundError("Run python -m app.casework.run --mode replay")
    return _load(path.stat().st_mtime)


@lru_cache(maxsize=2)
def _load(_: float) -> dict[str, Any]:
    return json.loads((settings.casework_dir / "casework.json").read_text(encoding="utf-8"))


# Business hours


def _hours_of(day: dict[str, str]) -> tuple[time, time]:
    return time.fromisoformat(day["start"]), time.fromisoformat(day["end"])


def business_hours(start: datetime, end: datetime, day: dict[str, str]) -> float:
    """Hours between two times that fall on a weekday within the business day."""
    if end <= start:
        return 0.0
    opens, closes = _hours_of(day)
    total = timedelta()
    cursor = start.date()
    while cursor <= end.date():
        if cursor.weekday() < 5:
            low = max(start, datetime.combine(cursor, opens))
            high = min(end, datetime.combine(cursor, closes))
            if high > low:
                total += high - low
        cursor += timedelta(days=1)
    return round(total.total_seconds() / 3600, 2)


def _union_hours(spans: list[tuple[datetime, datetime]], day: dict[str, str]) -> float:
    merged: list[list[datetime]] = []
    for start, end in sorted(spans):
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    return round(sum(business_hours(a, b, day) for a, b in merged), 2)


def _at(value: Any) -> datetime | None:
    if value is None:
        return None
    return value if isinstance(value, datetime) else datetime.fromisoformat(str(value))


def tracker(casework: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
    meta = record()
    day, clock = meta["case"]["business_day"], _at(meta["case"]["clock"])
    received = _at(meta["case"]["pack_received"])
    drafted = {q["id"]: q for q in casework["queries"]}
    rows, waiting = [], []
    for plan in meta["queries"]:
        if plan.get("topic") and plan["id"] not in drafted:
            continue  # The comparison found no such difference, so no query was raised.
        draft = drafted.get(plan["id"], {})
        live = state["queries"].get(plan["id"], {}) if not plan.get("earlier") else None
        raised = _at(plan["raised"])
        sent = _at(plan["sent"]) if plan.get("earlier") or (live and live["sent"]) else None
        answered = (_at(plan.get("answered")) if sent and (plan.get("earlier") or (
            live and live["answered"])) else None)
        closed = _at(plan.get("closed")) if answered else None
        status = ("closed" if closed else "answered" if answered else
                  "with client" if sent else "drafted")
        analyst = business_hours(raised, sent or clock, day) + (
            business_hours(answered, closed or clock, day) if answered else 0)
        wait_end = answered or clock
        if sent:
            waiting.append((sent, wait_end))
        rows.append({
            "id": plan["id"], "source": plan.get("source") or "Client model",
            "topic": plan.get("topic"), "to": plan["to"],
            "subject": draft.get("subject") or plan.get("subject"),
            "text": draft.get("text") or plan.get("text"),
            "figures": draft.get("figures"),
            "raised": raised.isoformat(), "sent": sent and sent.isoformat(),
            "answered": answered and answered.isoformat(), "closed": closed and closed.isoformat(),
            "answer": plan.get("answer") if answered else None,
            "answer_waiting": bool(sent and not answered and plan.get("answer")),
            "resolution": plan.get("resolution") if answered else None,
            "status": status, "blocking": plan.get("blocking", False),
            "earlier": bool(plan.get("earlier")),
            "analyst_hours": round(analyst, 2),
            "waiting_hours": business_hours(sent, wait_end, day) if sent else 0.0,
        })
    elapsed = business_hours(received, clock, day)
    client = _union_hours(waiting, day)
    return {
        "clock": clock.isoformat(), "pack_received": received.isoformat(),
        "business_day": day, "queries": rows,
        "elapsed_hours": elapsed, "client_waiting_hours": client,
        "analyst_hours": round(elapsed - client, 2),
        "open_with_client": sum(1 for r in rows if r["status"] == "with client"),
        "drafted": sum(1 for r in rows if r["status"] == "drafted"),
    }


def qc_view(casework: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
    qc = casework["qc"]
    lines = [{**line, "resolution": state["variances"].get(line["line"])}
             for line in qc["lines"]]
    open_lines = [x["line"] for x in lines if x["class"] == "genuine" and not x["resolution"]]
    released = state["reportReleasedAt"]
    return {
        **qc, "lines": lines, "open": open_lines,
        "passed": not open_lines,
        "status": "released" if released else "provisional",
        "released_at": released, "released_by": state["reportReleasedBy"],
        "can_release": not open_lines and bool(state["approvedAt"]) and not released,
        "resolutions": record()["qc_resolutions"],
    }


def thresholds(casework: dict[str, Any], state: dict[str, Any]) -> list[dict[str, Any]]:
    edit = state["ruleEdit"]
    rows = []
    for row in [*casework["config"]["rules"], *casework["config"]["terms"]]:
        row = dict(row)
        if row.get("term"):
            row["validated"] = state["termApprovals"].get(row["term"]) == "approved"
        else:
            row["validated"] = True
        if edit and edit["status"] == "approved" and row.get("rule") == edit["rule_id"]:
            row["engine"] = f"{edit['to']:g}" if isinstance(edit["to"], int | float) \
                else str(edit["to"])
            row["in_source"] = False
            row["change"] = (f"{edit['from']} to {edit['to']}, approved by a second analyst. "
                             f"Reason: {edit['reason']}")
        rows.append(row)
    return rows


def conventions(casework: dict[str, Any], track: dict[str, Any]) -> list[dict[str, Any]]:
    answered = {q["topic"]: q for q in track["queries"] if q.get("topic") and q["answer"]}
    result = []
    for row in casework["client_model"]["rows"]:
        if row["kind"] == "reporting":
            result.append({**row, "treatment": "Adopted"})
        elif row["status"] in ("differs", "silent"):
            query = answered.get(row["topic"])
            result.append({**row, "treatment": (f"{query['resolution']} ({query['id']}, "
                                                f"answered {query['answered'][:10]})")
                           if query else "Agreement applied; query open"})
    return result


def status(state: dict[str, Any], qc: dict[str, Any]) -> dict[str, Any]:
    approved, released = state["approvedAt"], state["reportReleasedAt"]
    if approved and released:
        label = (f"FINAL: approved {approved[:10]} by {state['approvedByName']}; first report "
                 f"released after QC {released[:10]}")
    elif approved:
        label = ("PROVISIONAL: approved, but the first report has not passed independent QC "
                 "and been released")
    else:
        label = "PROVISIONAL: draft configuration until a second analyst approves the case"
    return {"label": label, "final": bool(approved and released),
            "prepared_by": state["preparedBy"], "approved_by": state["approvedByName"],
            "released": released, "qc_passed": qc["passed"]}


def backbook_view(casework: dict[str, Any], state: dict[str, Any]) -> list[dict[str, Any]]:
    accepted = set(state["backbookAccepted"])
    return [{**deal, "loaded": deal["clean"] or deal["id"] in accepted,
             "can_accept": not deal["clean"] and deal["id"] not in accepted
             and all(d["check"]["ok"] for d in deal["differences"])}
            for deal in casework["backbook"]]


def view(state: dict[str, Any]) -> dict[str, Any]:
    casework = current()
    track = tracker(casework, state)
    qc = qc_view(casework, state)
    return {
        "usage": casework["usage"],
        "definitions": casework["definitions"],
        "client_model": casework["client_model"],
        "tracker": track,
        "qc": qc,
        "config": {"status": status(state, qc), "thresholds": thresholds(casework, state),
                   "fields": casework["config"]["fields"],
                   "report": casework["config"]["report"],
                   "conventions": conventions(casework, track),
                   "ruleset_digest": casework["config"]["ruleset_digest"]},
        "backbook": backbook_view(casework, state),
    }


def check_event(state: dict[str, Any], kind: str, payload: dict[str, Any]) -> None:
    """The casework controls. Four-eyes and the case lock are checked by the session first."""
    casework = current()
    plans = {q["id"]: q for q in record()["queries"]}
    live = {q["id"] for q in casework["queries"]}
    ids = list(payload.get("ids") or [payload.get("id")])
    if kind == "send-query":
        for ident in ids:
            if ident not in live:
                raise Refused("Only a drafted client query can be sent")
            if ident in state["queries"]:
                raise Refused(f"{ident} has already been sent")
    if kind == "record-answer":
        for ident in ids:
            sent = state["queries"].get(ident)
            if not sent:
                raise Refused("Send the query before recording an answer")
            if sent["answered"]:
                raise Refused(f"The answer to {ident} is already recorded")
            if not plans.get(ident, {}).get("answer"):
                raise Refused(f"The client has not answered {ident} yet")
    if kind == "resolve-variance":
        genuine = {x["line"] for x in casework["qc"]["lines"] if x["class"] == "genuine"}
        if payload.get("line") not in genuine:
            raise Refused("Only a genuine QC variance needs a resolution")
        if payload.get("resolution") not in record()["qc_resolutions"]:
            raise Refused("Choose one of the resolutions")
        if not payload.get("reason"):
            raise Refused("A reason is required")
        if not state["ran"]:
            raise Refused("Run the April tape first")
    if kind == "release-report":
        if not state["approvedAt"]:
            raise Refused("The case must be approved before its first report is released")
        if state["reportReleasedAt"]:
            raise Refused("The first report is already released")
        if qc_view(casework, state)["open"]:
            raise Refused("A genuine QC variance is still open, so the report stays provisional")
    if kind == "accept-backbook":
        deal = next((d for d in casework["backbook"] if d["id"] == payload.get("deal")), None)
        if deal is None:
            raise Refused("Unknown backbook deal")
        if deal["id"] in state["backbookAccepted"] or deal["clean"]:
            raise Refused("This deal is already loaded")
        if not all(d["check"]["ok"] for d in deal["differences"]):
            raise Refused("A suggestion failed its check, so an expert has to decide first")
