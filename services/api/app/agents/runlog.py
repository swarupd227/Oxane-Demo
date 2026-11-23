"""The agents' run log: recorded model calls from the fixtures, plus live calls from the database.

Recorded runs are read from the saved gateway responses (fixtures/llm, llm-casework, llm-cycle)
and the run outputs beside them. Each run's outcome comes from what code and people did with
its output: the code checks recorded in the run, then the decisions in the current session.
A client that does not permit AI shows its refused calls at zero cost.

Live calls made elsewhere are logged with `record_run(...)`.
"""

import json
import logging
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.agents import registry
from app.agents.models import AgentRun
from app.agents.registry import cached
from app.config import settings
from app.db import engine
from app.pipeline.gateway import Usage

log = logging.getLogger(__name__)

OUTCOMES = {
    "accepted": "Accepted",
    "edited": "Edited",
    "rejected": "Rejected",
    "quote_check_failed": "Quote check failed",
    "refused": "Refused: AI not permitted",
    "awaiting_review": "Awaiting review",
    "pending_recording": "Pending: not recorded",
}
DECIDED = ("accepted", "edited", "rejected", "quote_check_failed")

ONBOARDING = {"workflow": "Onboarding", "ref": "Case 0412", "client": "calderwood",
              "facility": "Bramble Auto Receivables I"}
# The documents each monitoring reading step is given (see app/monitoring/steps.py).
CYCLE_FACILITY = {"read_servicer_report": "bramble", "read_compliance": "bramble",
                  "read_amendment_2": "bramble", "map_new_columns": "bramble",
                  "explain_change": "bramble", "read_excess_spread": "northmoor",
                  "read_nav_pack": "kestrel", "read_obligor_financials": "ravenglass",
                  "read_covenant_notice": "ravenglass"}


def record_run(task: str, client: str, subject: str, tokens_in: int, tokens_out: int,
               cost_usd: float, outcome: str, duration_ms: int, *, ref: str = "",
               db: Session | None = None) -> int | None:
    """Log one model call for the agents console. `task` is the gateway task name, `client`
    the client id, `outcome` one of OUTCOMES (use "refused" for a client that does not permit
    AI, with zero tokens and cost). Pass `db` to write inside the caller's transaction (the
    caller commits); otherwise it is written and committed on its own. Returns the row id, or
    None if the database refused it: logging never breaks the call it describes."""
    if outcome not in OUTCOMES:
        raise ValueError(f"Unknown outcome {outcome!r}; expected one of {sorted(OUTCOMES)}")
    row = AgentRun(task=task[:64], client=client[:64], subject=subject[:200], ref=ref[:64],
                   tokens_in=int(tokens_in), tokens_out=int(tokens_out),
                   cost_usd=Decimal(str(round(float(cost_usd), 6))), outcome=outcome,
                   duration_ms=int(duration_ms))
    try:
        if db is not None:
            db.add(row)
            db.flush()
            return row.id
        with Session(engine) as own:
            own.add(row)
            own.commit()
            return row.id
    except SQLAlchemyError:
        log.warning("Could not log agent run for %s", task, exc_info=True)
        return None


def _load(path: Path) -> dict[str, Any] | None:
    def read() -> dict[str, Any] | None:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None

    return cached(("load", str(path)), read)


def _calls(folder: Path) -> list[tuple[Path, dict[str, Any], str]]:
    """The recorded responses in one fixtures folder, with when each was recorded."""
    def read() -> list[tuple[Path, dict[str, Any], str]]:
        found = []
        for path in sorted(folder.glob("*/*.json")):
            saved = _load(path)
            if saved is not None and "usage" in saved:
                found.append((path, saved, _when(path)))
        return found

    return cached(("calls", str(folder)), read)


def _workbench() -> dict[str, Any] | None:
    """The recorded onboarding run. Without one (the seed view) outcomes rest on the checks."""
    return _load(settings.pipeline_dir / "workbench.json")


def _sessions(db: Session | None, cycle: dict[str, Any] | None) -> dict[str, Any]:
    """The current onboarding and cycle sessions, where a database is there to read."""
    shown: dict[str, Any] = {"case": None, "cycle": None}
    if db is None:
        return shown
    try:
        from app import session as case_session
        from app.monitoring import session as cycle_session

        run = _workbench()
        if run is not None:
            shown["case"] = case_session.view(db, run)
        if cycle is not None:
            shown["cycle"] = cycle_session.view(db, cycle)
    except Exception:  # noqa: BLE001 - no session yet: outcomes rest on the code checks
        log.info("Agent run outcomes without session state", exc_info=True)
    return shown


def _drafted_ok(item: dict[str, Any]) -> bool:
    return not item.get("unknown_placeholders") and not item.get("numbers_in_text")


def _onboarding_outcome(task: str, parsed: dict[str, Any], casework: dict[str, Any] | None,
                        case: dict[str, Any] | None,
                        run: dict[str, Any] | None) -> tuple[str, str]:
    if task in ("extract_all", "extract_tier1") and run:
        terms = run.get("terms", [])
        found = [t for t in terms if t.get("status") != "missing"]
        verified = sum(1 for t in found if t.get("verified"))
        low = sum(1 for t in found if t.get("confidence") == "low")
        note = f"{verified} of {len(found)} quotes found; {low} held low confidence"
        missing = len(terms) - len(found)
        if missing:
            note += f"; {missing} not in the pack"
        return ("accepted" if verified == len(found) else "quote_check_failed"), note
    if task == "draft_rules" and run:
        edit = (case or {}).get("ruleEdit")
        rules = len(run.get("rules", []))
        if edit and edit.get("status") == "approved":
            return "edited", f"{rules} rules; {edit['rule_id']} changed by an analyst, approved"
        return "accepted", f"{rules} rules drafted, each against its clause"
    if casework:
        if task == "trace_definitions":
            checks = casework["definitions"]["checks"]
            ok = checks["quotes_found"] == checks["quotes"]
            return ("accepted" if ok else "quote_check_failed",
                    f"{checks['quotes_found']} of {checks['quotes']} quotes found")
        if task == "read_client_model":
            rejected = casework["client_model"].get("rejected", [])
            if rejected:
                return "quote_check_failed", f"{len(rejected)} treatments not found in their cells"
            return "accepted", f"{len(casework['client_model']['rows'])} treatments checked"
        if task == "draft_client_queries":
            queries = casework.get("queries", [])
            bad = [q for q in queries if not _drafted_ok(q)]
            if bad:
                return "rejected", f"{len(bad)} drafts carried a raw figure"
            return "accepted", f"{len(queries)} queries; every figure a placeholder"
        if task == "suggest_backbook":
            deals = casework.get("backbook", [])
            return "accepted", f"{sum(len(d['differences']) for d in deals)} differences " \
                f"across {len(deals)} deals, each checked against the tape"
    listed = {"classify": ("documents", "files classified"),
              "read_amendment": ("changes", "changes read with effective dates"),
              "map_tape": ("columns", "columns mapped, each checked against the tape"),
              "read_requirements": ("requirements", "requirements matched to the tape"),
              "resolve_leverage": ("parts", "formula parts quoted")}
    if task in listed and isinstance(parsed.get(listed[task][0]), list):
        note = f"{len(parsed[listed[task][0]])} {listed[task][1]}"
        if task == "classify" and run and run.get("missing_documents"):
            note += f"; {len(run['missing_documents'])} referred to but missing"
        return "accepted", note
    if task == "read_scan":
        return "accepted", "Scanned page read into text"
    return "accepted", "Passed code checks"


def _cycle_outcome(task: str, parsed: dict[str, Any], cycle: dict[str, Any],
                   state: dict[str, Any] | None) -> tuple[str, str]:
    triage = (state or {}).get("triage", {})
    if task.startswith("read_"):
        if cycle.get("unverified"):
            return "quote_check_failed", f"{len(cycle['unverified'])} figures unverified"
        figures = parsed.get("figures")
        return "accepted", (f"{len(figures)} figures, each quote found" if figures
                            else "Quotes found on their pages")
    if task == "map_new_columns":
        columns = len(parsed.get("columns", []))
        if state and state.get("layoutConfirmed"):
            return "accepted", f"{columns} new columns; layout confirmed"
        return "awaiting_review", f"{columns} new columns to confirm"
    if task == "explain_change":
        finding = next((f for f in cycle["findings"] if f.get("explanation")), None)
        if finding is None:
            return "accepted", "Cause quoted from the servicer report"
        decided = triage.get(finding["id"])
        if decided is None:
            return "awaiting_review", "Cause quoted; finding not yet decided"
        return ("edited" if decided.get("overrode") else "accepted"), "Cause quoted; logged"
    if task == "suggest_triage":
        suggested = [f for f in cycle["findings"] if (f.get("suggested") or {}).get("by") == "AI"]
        decided = [f for f in suggested if f["id"] in triage]
        changed = [f for f in decided if triage[f["id"]].get("overrode")]
        note = f"{len(decided)} of {len(suggested)} decided"
        if changed:
            return "edited", note + f"; {len(changed)} changed with a reason"
        return ("accepted" if suggested and len(decided) == len(suggested)
                else "awaiting_review"), note
    if task == "draft_pack":
        name = parsed.get("facility", "")
        facility = next((f for f in cycle["facilities"] if f["name"] == name), None)
        pack = next((p for p in cycle["packs"] if facility and p["facility"] == facility["id"]),
                    None)
        if pack and not _drafted_ok(pack):
            return "rejected", "Draft carried a raw figure or an unknown placeholder"
        if facility and facility["id"] in (state or {}).get("packs", {}):
            return "accepted", "Placeholders filled by code; released"
        return "awaiting_review", "Placeholders filled by code; awaiting approval"
    if task == "draft_status_brief":
        brief = next((b for b in cycle["briefs"] if b.get("ai")), None)
        if brief and not _drafted_ok(brief):
            return "rejected", "Draft carried a raw figure"
        return "accepted", "Every figure a placeholder filled by code"
    if task == "draft_alert":
        metric = parsed.get("metric")
        presets = [p for c in cycle["alerts"].values() for p in c.get("presets", [])]
        preset = next((p for p in presets if p["drafted"].get("metric") == metric), None)
        if preset is None or not preset.get("valid"):
            return "rejected", "Rule failed code's check"
        live = [a for a in (state or {}).get("alerts", []) if a.get("request") == preset["request"]]
        fires = int(preset.get("fires") or 0)
        note = f"Valid rule; back-test fires {'once' if fires == 1 else f'{fires} times'}"
        if any(a.get("status") == "live" for a in live):
            return "accepted", note + "; approved"
        return "awaiting_review", note + "; awaiting analyst approval"
    return "accepted", "Passed code checks"


def _subject(task: str, parsed: dict[str, Any], workflow: dict[str, Any],
             cycle: dict[str, Any] | None) -> tuple[str, str]:
    """(subject, facility id or '')"""
    label = registry.task_label(task)
    if cycle is None or workflow["workflow"] != "Monitoring":
        return f"{label} · {ONBOARDING['facility']}", "bramble"
    names = {f["id"]: f["name"] for f in cycle["facilities"]}
    facility = CYCLE_FACILITY.get(task, "")
    if isinstance(parsed.get("facility"), str):
        facility = next((fid for fid, n in names.items() if n == parsed["facility"]), facility)
    if isinstance(parsed.get("metric"), str):
        facility = parsed["metric"].split(".")[0]
    if task == "draft_alert":
        request = next((p["request"] for c in cycle["alerts"].values()
                        for p in c.get("presets", [])
                        if p["drafted"].get("metric") == parsed.get("metric")), None)
        if request:
            return f"{label} · “{request}”", facility
    if task == "suggest_triage":
        return f"{label} · Calderwood facilities", ""
    if task == "draft_status_brief":
        return f"{label} · Calderwood Bank plc", ""
    return f"{label} · {names.get(facility, facility)}", facility


def _when(path: Path) -> str:
    return datetime.fromtimestamp(path.stat().st_mtime, UTC).isoformat(timespec="seconds")


def recorded_runs(db: Session | None = None) -> list[dict[str, Any]]:
    """Every recorded model call, newest first, plus the calls refused for no-AI clients."""
    cycle = _load(settings.cycle_dir / "cycle.json")
    casework = _load(settings.casework_dir / "casework.json")
    run = _workbench()
    sessions = _sessions(db, cycle)
    owners = registry.task_owner()
    sets = [
        (settings.llm_fixtures, ONBOARDING),
        (settings.casework_llm_fixtures, ONBOARDING),
        (settings.cycle_llm_fixtures, {"workflow": "Monitoring", "client": "calderwood",
                                       "ref": f"Cycle {cycle['cycle']['id']}" if cycle else
                                       "Cycle"}),
    ]
    rows: list[dict[str, Any]] = []
    for folder, workflow in sets:
        for path, saved, at in _calls(folder):
            task =saved.get("task") or path.parent.name
            try:
                parsed = json.loads(saved.get("text") or "{}")
            except ValueError:
                parsed = {}
            if not isinstance(parsed, dict):
                parsed = {}
            usage = Usage(**{k: v for k, v in saved["usage"].items()
                             if k in Usage.__dataclass_fields__})
            if workflow["workflow"] == "Monitoring" and cycle:
                outcome, note = _cycle_outcome(task, parsed, cycle, sessions["cycle"])
            else:
                outcome, note = _onboarding_outcome(task, parsed, casework, sessions["case"],
                                                    run)
            subject, facility = _subject(task, parsed, workflow, cycle)
            rows.append({
                "id": f"rec-{path.parent.name}-{path.stem[:8]}",
                "at": at,
                "agent": owners.get(task),
                "task": task,
                "client": workflow["client"],
                "workflow": workflow["workflow"],
                "ref": workflow["ref"],
                "facility": facility,
                "subject": subject,
                "outcome": outcome,
                "note": note,
                "tokens_in": usage.input_tokens + usage.cache_read_tokens
                + usage.cache_write_tokens,
                "tokens_out": usage.output_tokens,
                "cost_usd": round(usage.cost_usd(saved.get("model", "")), 4),
                "duration_ms": int(round(usage.seconds * 1000)),
                "model": saved.get("model"),
                "source": "recorded",
            })
    if cycle:
        stamp = cached(("when", str(settings.cycle_dir)),
                       lambda: _when(settings.cycle_dir / "cycle.json"))
        rows += _refused(cycle, stamp)
        rows += _pending(cycle, stamp)
    rows.sort(key=lambda r: (r["at"], r["id"]), reverse=True)
    return rows


def _pending(cycle: dict[str, Any], at: str) -> list[dict[str, Any]]:
    """Model steps the cycle could not replay because they were never recorded. Each one's code
    fallback ran instead; recording them needs a model key."""
    ref = f"Cycle {cycle['cycle']['id']}"
    return [{"id": f"pend-{p['task']}-{index}", "at": at,
             "agent": registry.task_owner().get(p["task"]), "task": p["task"],
             "client": "calderwood", "workflow": "Monitoring", "ref": ref,
             "facility": p.get("facility", ""),
             "subject": f"{registry.task_label(p['task'])} · {p['subject']}",
             "outcome": "pending_recording",
             "note": "Not recorded yet; the code fallback ran", "tokens_in": 0, "tokens_out": 0,
             "cost_usd": 0.0, "duration_ms": 0, "model": None, "source": "recorded"}
            for index, p in enumerate(cycle.get("pending_recording", []))]


def _refused(cycle: dict[str, Any], at: str) -> list[dict[str, Any]]:
    """For each client that does not permit AI, the steps that ran on code instead."""
    rows = []
    ref = f"Cycle {cycle['cycle']['id']}"
    for client in cycle["clients"]:
        if client["ai_permitted"]:
            continue
        mine = {f["id"]: f for f in cycle["facilities"] if f["client"] == client["id"]}

        def row(task: str, facility: str, subject: str, note: str,
                client: dict[str, Any] = client) -> dict[str, Any]:
            return {"id": f"ref-{client['id']}-{task}-{facility}", "at": at,
                    "agent": registry.task_owner().get(task), "task": task,
                    "client": client["id"], "workflow": "Monitoring", "ref": ref,
                    "facility": facility, "subject": subject, "outcome": "refused",
                    "note": note, "tokens_in": 0, "tokens_out": 0, "cost_usd": 0.0,
                    "duration_ms": 0, "model": None, "source": "recorded"}

        for fid, facility in mine.items():
            by_rule = [f for f in cycle["findings"] if fid in f["facility"].split(",")
                       and (f.get("suggested") or {}).get("by") == "Rule"]
            if by_rule:
                rows.append(row("suggest_triage", fid,
                                f"{registry.task_label('suggest_triage')} · {facility['name']}",
                                f"{len(by_rule)} outcomes suggested by rule instead"))
            if any(p["facility"] == fid for p in cycle["packs"]):
                rows.append(row("draft_pack", fid,
                                f"{registry.task_label('draft_pack')} · {facility['name']}",
                                "Pack written from the code template"))
        if any(b["client"] == client["id"] and not b.get("ai") for b in cycle["briefs"]):
            rows.append(row("draft_status_brief", "",
                            f"{registry.task_label('draft_status_brief')} · {client['name']}",
                            "Brief written from the code template"))
        if not (cycle["alerts"].get(client["id"]) or {}).get("ai_permitted", False):
            rows.append(row("draft_alert", "",
                            f"{registry.task_label('draft_alert')} · {client['name']}",
                            "Alert requests set up by the analyst"))
    return rows


def stored_runs(db: Session) -> list[dict[str, Any]]:
    owners = registry.task_owner()
    try:
        found = db.scalars(select(AgentRun).order_by(AgentRun.at.desc()).limit(500)).all()
    except SQLAlchemyError:
        db.rollback()
        return []
    return [{
        "id": f"live-{r.id}", "at": r.at.isoformat(timespec="seconds"),
        "agent": owners.get(r.task), "task": r.task, "client": r.client,
        "workflow": "New deals" if r.task.startswith("deals_") else "Live",
        "ref": r.ref, "facility": "", "subject": r.subject, "outcome": r.outcome,
        "note": "", "tokens_in": r.tokens_in, "tokens_out": r.tokens_out,
        "cost_usd": round(float(r.cost_usd), 4), "duration_ms": r.duration_ms, "model": None,
        "source": "live",
    } for r in found]


def all_runs(db: Session | None) -> list[dict[str, Any]]:
    live = stored_runs(db) if db is not None else []
    rows = live + recorded_runs(db)
    rows.sort(key=lambda r: r["at"], reverse=True)
    return rows


def stats(rows: list[dict[str, Any]]) -> dict[str, Any]:
    calls = [r for r in rows if r["outcome"] not in ("refused", "pending_recording")]
    decided = [r for r in calls if r["outcome"] in DECIDED]
    accepted = sum(1 for r in decided if r["outcome"] == "accepted")
    counts = {key: sum(1 for r in rows if r["outcome"] == key) for key in OUTCOMES}
    return {
        "runs": len(calls),
        "refused": counts["refused"],
        "outcomes": counts,
        "tokens": sum(r["tokens_in"] + r["tokens_out"] for r in calls),
        "cost_usd": round(sum(r["cost_usd"] for r in calls), 4),
        "duration_ms": sum(r["duration_ms"] for r in calls),
        "decided": len(decided),
        "acceptance": round(accepted / len(decided), 4) if decided else None,
        "last_at": max((r["at"] for r in rows), default=None),
    }
