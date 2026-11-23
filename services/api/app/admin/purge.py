"""Remove what tests and test flows left in a demo database, then rebuild the scripted hand-offs.

    python -m app.admin.purge --test-data            # dry run: what would go, nothing changes
    python -m app.admin.purge --test-data --apply    # do it

It removes every record created at run time in the deal workbench (clients and their client
users, cases, documents, facilities, submissions, stored mappings, model spend rows, agent runs
and work items), every scripted hand-off from earlier sessions, and duplicate or stale ones, then
opens the scripted hand-offs once from the current sessions of case 0412 and the May cycle.

It never touches the scripted fixtures (files), the scripted session logs, the hash-chained audit
log (case_event rows cannot be changed), the encrypted AI-provider setting or the migrations.
`--keep-client ID` keeps one created client and everything under it.

The same runs from Settings for the administrator: POST /api/admin/purge-test-data.
"""

import argparse
import json
from typing import Any

from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.orm import Session

from app.agents.models import AgentRun
from app.deals.models import (
    Client,
    ClientMapping,
    DealCase,
    Document,
    Facility,
    LlmSpend,
    Submission,
    WorkItem,
)

DEAL_SUBJECTS = ("case:", "facility:", "submission:", "client:")


def _count(db: Session, model: Any, *where: Any) -> int:
    return int(db.scalar(select(func.count()).select_from(model).where(*where)) or 0)


def _purge(db: Session, keep: set[int]) -> dict[str, Any]:
    clients = [c for c in db.scalars(select(Client).order_by(Client.id)) if c.id not in keep]
    client_ids = [c.id for c in clients]
    kept_cases = list(db.scalars(select(DealCase.id).where(DealCase.client_id.in_(keep))))
    kept_facilities = list(db.scalars(select(Facility.id).where(Facility.client_id.in_(keep))))
    kept_subs = list(db.scalars(select(Submission.id).where(
        Submission.facility_id.in_(kept_facilities))))
    cases = list(db.scalars(select(DealCase.id).where(DealCase.client_id.in_(client_ids))))
    facilities = list(db.scalars(select(Facility.id).where(Facility.client_id.in_(client_ids))))
    subs = list(db.scalars(select(Submission.id).where(Submission.facility_id.in_(facilities))))
    kept_subjects = {f"case:{i}" for i in kept_cases} | {f"facility:{i}" for i in kept_facilities} \
        | {f"submission:{i}" for i in kept_subs} | {f"client:{i}" for i in keep}

    counts: dict[str, Any] = {
        "clients": len(client_ids),
        "client_users": sum(1 for c in clients if c.contact_name and c.archived_at is None),
        "cases": len(cases),
        "facilities": len(facilities),
        "submissions": len(subs),
        "documents": _count(db, Document, or_(Document.case_id.in_(cases),
                                              Document.submission_id.in_(subs))),
        "client_mappings": _count(db, ClientMapping, ClientMapping.client_id.in_(client_ids)),
    }
    # Spend rows for the removed records, and any left behind by records already gone.
    spend = or_(LlmSpend.case_id.in_(cases), LlmSpend.submission_id.in_(subs),
                LlmSpend.case_id.is_(None) & LlmSpend.submission_id.is_(None),
                LlmSpend.case_id.not_in(select(DealCase.id)),
                LlmSpend.submission_id.not_in(select(Submission.id)))
    spend = spend & ~(LlmSpend.case_id.in_(kept_cases) | LlmSpend.submission_id.in_(kept_subs))
    counts["spend_rows"] = _count(db, LlmSpend, spend)
    # Agent runs of the deal workbench are logged against "deal:<client id>".
    runs = AgentRun.client.like("deal:%") & AgentRun.client.not_in(
        [f"deal:{i}" for i in keep] or [""])
    counts["agent_runs"] = _count(db, AgentRun, runs)
    # Work items: every new-deal item not kept, and every scripted one (rebuilt below).
    deal_items = or_(*(WorkItem.subject.like(f"{p}%") for p in DEAL_SUBJECTS))
    if kept_subjects:
        deal_items = deal_items & WorkItem.subject.not_in(kept_subjects)
    scripted = WorkItem.subject.like("scripted:%")
    counts["work_items_deals"] = _count(db, WorkItem, deal_items)
    counts["work_items_scripted"] = _count(db, WorkItem, scripted)
    counts["work_items_other"] = _count(db, WorkItem, ~deal_items, ~scripted,
                                        WorkItem.subject.not_in(kept_subjects or [""]))

    db.execute(delete(WorkItem).where(WorkItem.subject.not_in(kept_subjects or [""])))
    db.execute(delete(LlmSpend).where(spend))
    db.execute(delete(AgentRun).where(runs))
    db.execute(delete(Document).where(or_(Document.case_id.in_(cases),
                                          Document.submission_id.in_(subs))))
    db.execute(delete(Submission).where(Submission.id.in_(subs)))
    db.execute(update(DealCase).where(DealCase.id.in_(cases)).values(facility_id=None))
    db.execute(delete(Facility).where(Facility.id.in_(facilities)))
    db.execute(delete(DealCase).where(DealCase.id.in_(cases)))
    db.execute(delete(ClientMapping).where(ClientMapping.client_id.in_(client_ids)))
    db.execute(delete(Client).where(Client.id.in_(client_ids)))
    db.flush()

    # The scripted scenarios' hand-offs, once, from their current sessions.
    from app.main import sync_scripted

    sync_scripted(db, None, "both")
    db.flush()
    rebuilt = list(db.scalars(select(WorkItem).where(scripted).order_by(WorkItem.id)))
    counts["scripted_rebuilt"] = len(rebuilt)
    counts["scripted_open"] = [f"{i.title} -> {i.assignee or i.role}" for i in rebuilt
                               if i.status == "open"]
    return counts


def purge_test_data(db: Session, apply: bool = False,
                    keep: set[int] | None = None) -> dict[str, Any]:
    """Work out and (with apply) make the purge in one transaction. A dry run makes the same
    changes and rolls them back, so its counts are exactly what --apply would do."""
    try:
        counts = _purge(db, keep or set())
        if apply:
            db.commit()
        else:
            db.rollback()
    except Exception:
        db.rollback()
        raise
    return {"applied": apply, "kept_clients": sorted(keep or set()), **counts}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--test-data", action="store_true", required=True,
                        help="remove test-created records (the only purge there is)")
    parser.add_argument("--apply", action="store_true", help="make the change (default: dry run)")
    parser.add_argument("--keep-client", type=int, action="append", default=[],
                        help="id of a created client to keep, with everything under it")
    args = parser.parse_args()
    from app.db import engine

    with Session(engine) as db:
        result = purge_test_data(db, apply=args.apply, keep=set(args.keep_client))
    print(json.dumps(result, indent=2))
    if not args.apply:
        print("Dry run: nothing was changed. Run again with --apply to purge.")


if __name__ == "__main__":
    main()
