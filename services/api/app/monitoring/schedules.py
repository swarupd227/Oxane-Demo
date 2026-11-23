"""Document schedules, daily feeds and the mapping library.

Each facility's expected documents come from its asset class's template, set when it was
onboarded. Code ties each line to what arrived this cycle; daily feeds are checked day by day
against their deadlines and against each other (every position held needs a price). The mapping
library counts this cycle's files in each stored layout, recognising obligor documents by their
own headings. Nothing here calls a model.
"""

import csv
from datetime import date, datetime, time
from pathlib import Path
from typing import Any

from engine.feeds import business_days, check_daily

FEED_NAMES = {"positions": "Daily position file", "prices": "Daily prices",
              "ratings": "Daily ratings feed"}


def _read(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def daily_feeds(meta: dict[str, Any], root: Path, period: tuple[date, date]) -> dict[str, Any]:
    fac = next(f for f in meta["facilities"] if f["id"] == "larkspur")
    folder = root / fac["daily_folder"]
    template = {line["daily"]: line for line in meta["schedule_templates"][fac["schedule"]]
                if line.get("daily")}
    log = _read(folder / fac["daily_log"])
    days = business_days(*period)
    feeds, held, priced = [], {}, {}
    for feed, line in template.items():
        arrived = {}
        for row in log:
            if row["feed"] != feed:
                continue
            day = date.fromisoformat(row["as_of"])
            at = datetime.fromisoformat(row["received_at"]) if row["received_at"] else None
            arrived[day] = (at, int(row["rows"] or 0))
            if at and row["file"] and feed in ("positions", "prices"):
                ids = {r[next(k for k, v in fac["daily_mapping"][feed].items() if v == "loanx")]
                       for r in _read(folder / row["file"])}
                (held if feed == "positions" else priced)[day] = ids
        hour, minute = (int(x) for x in line["at"].split(":"))
        checked = check_daily(feed, days, int(line["lag"]), time(hour, minute), arrived)
        files = {date.fromisoformat(r["as_of"]): r["file"] for r in log if r["feed"] == feed}
        feeds.append({
            "feed": feed, "document": FEED_NAMES[feed], "channel": line["channel"],
            "format": line["format"], "due": line["due"],
            "days": [{"as_of": d.as_of.isoformat(), "deadline": d.deadline.isoformat(
                timespec="minutes"), "received_at": d.received.isoformat(timespec="minutes")
                if d.received else None, "status": d.status, "minutes_late": d.minutes_late,
                "rows": d.rows, "file": files.get(d.as_of) or None} for d in checked],
            "expected": len(checked),
            "received": sum(1 for d in checked if d.received),
            "late": [d.as_of.isoformat() for d in checked if d.status == "late"],
            "missing": [d.as_of.isoformat() for d in checked if d.status == "missing"],
        })
    coverage = []
    for day in days:
        ids = held.get(day, set())
        prices = priced.get(day)
        coverage.append({"as_of": day.isoformat(), "positions": len(ids),
                         "priced": len(ids & prices) if prices is not None else 0,
                         "unpriced": len(ids - prices) if prices is not None else len(ids),
                         "price_file": prices is not None})
    ratings_file = {r["as_of"]: r["file"] for r in log if r["feed"] == "ratings" and r["file"]}
    changes = []
    for as_of, name in sorted(ratings_file.items()):
        for r in _read(folder / name):
            changes.append({"as_of": as_of, "loanx": r["LoanX_ID"], "issuer": r["Issuer"],
                            "agency": r["Agency"], "previous": r["Previous"],
                            "current": r["Current"], "file": name})
    return {"facility": "larkspur", "folder": fac["daily_folder"], "business_days": len(days),
            "feeds": feeds, "coverage": coverage, "rating_changes": changes,
            "expected": sum(f["expected"] for f in feeds),
            "received": sum(f["received"] for f in feeds)}


def _item(**item: Any) -> dict[str, Any]:
    return {"rule_outcome": None, "evidence": [], "sources": [], "clauses": [], **item}


def findings(daily: dict[str, Any], pretty: Any) -> list[dict[str, Any]]:
    """Larkspur's client does not permit AI, so rules suggest each outcome."""
    items = []
    coverage = {c["as_of"]: c for c in daily["coverage"]}
    for feed in daily["feeds"]:
        for day in feed["days"]:
            if day["status"] == "missing":
                gap = coverage[day["as_of"]]
                items.append(_item(
                    id=f"F-feed-larkspur-{feed['feed']}-gap-{day['as_of']}", facility="larkspur",
                    check="Daily feeds",
                    title=f"{feed['document']} for {pretty(day['as_of'])} not received",
                    detail=f"Due {pretty(day['deadline'][:10])} at {day['deadline'][11:]} by "
                    f"{feed['channel']}. Nothing arrived and nothing was resent, so "
                    f"{gap['unpriced']} positions have no bid for that day and the day's price "
                    "checks did not run. The month-end test uses 29 May prices and is not "
                    "affected.", owner="Pricing service", sender="Meridian Loan Pricing",
                    suggested={"outcome": "query", "by": "Rule",
                               "reason": "A delivery is missing, so the pricing service must "
                               "resend it. Suggested by rule: this client does not permit AI."}))
            elif day["status"] == "late":
                items.append(_item(
                    id=f"F-feed-larkspur-{feed['feed']}-late-{day['as_of']}", facility="larkspur",
                    check="Daily feeds", rule_outcome="logged",
                    rule_reason="Arrived the next morning, complete and matching the next day's "
                    "file; no check used it before it came. Logged against the sender's record.",
                    title=f"{feed['document']} for {pretty(day['as_of'])} arrived "
                    f"{day['minutes_late'] // 60} h {day['minutes_late'] % 60} min late",
                    detail=f"Due {day['deadline'].replace('T', ' ')}, received "
                    f"{day['received_at'].replace('T', ' ')}, {day['rows']} rows.",
                    suggested={"outcome": "logged", "by": "Rule",
                               "reason": "Late but complete; logged."}))
    return items


TOPICS = {"F-feed-larkspur-prices-gap": "One day's price file was never delivered",
          "F-feed-larkspur-positions-late": "One day's position file arrived late, complete",
          "F-feed-": "A daily feed delivery was late or missing"}


def facility_schedules(meta: dict[str, Any], facilities: list[dict[str, Any]],
                       submissions: list[dict[str, Any]], daily: dict[str, Any],
                       book: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Each facility's expected documents for the cycle, line by line, from its template."""
    templates = meta["schedule_templates"]
    record = {f["id"]: f for f in meta["facilities"]}
    by_kind = meta["schedule_by_kind"]
    daily_by_feed = {f["feed"]: f for f in daily["feeds"]}
    out = []
    for f in [*facilities, *book]:
        name = record[f["id"]]["schedule"] if f["id"] in record else by_kind[f.get("kind")
                                                                             or "auto"]
        mine = [s for s in submissions if s["facility"] == f["id"]]
        lines = []
        for line in templates[name]:
            row = {k: line[k] for k in ("document", "format", "frequency", "channel", "due",
                                        "internal")}
            if line.get("applies_note"):
                lines.append({**row, "status": "not_applicable", "expected": 0, "received": 0,
                              "late": 0, "note": line["applies_note"]})
                continue
            if line.get("daily"):
                feed = daily_by_feed.get(line["daily"]) if f["id"] == "larkspur" else None
                if feed is None:
                    lines.append({**row, "status": "summary_only", "expected": 0, "received": 0,
                                  "late": 0, "note": "Summary figures only on this platform"})
                    continue
                lines.append({**row, "expected": feed["expected"], "received": feed["received"],
                              "late": len(feed["late"]), "missing": len(feed["missing"]),
                              "status": "missing" if feed["missing"] else "late" if feed["late"]
                              else "complete", "note": ""})
                continue
            matched = [s for s in mine if s["label"].startswith(line["match"])]
            if not matched:
                lines.append({**row, "status": "not_due", "expected": 0, "received": 0,
                              "late": 0, "note": "None due this cycle"})
                continue
            got = [s for s in matched if s["received"] or s.get("reused")]
            late = [s for s in matched if s["status"] == "late"]
            lines.append({**row, "expected": len(matched), "received": len(got),
                          "late": sum(1 for s in matched if s["status"] == "received_late"),
                          "missing": len(late),
                          "status": "missing" if late else "late" if any(
                              s["status"] == "received_late" for s in matched) else "complete",
                          "refs": [s.get("ref") for s in matched][:3], "note": ""})
        out.append({"facility": f["id"], "template": name, "lines": lines})
    return out


def library(meta: dict[str, Any], facilities: list[dict[str, Any]],
            submissions: list[dict[str, Any]], ravenglass: dict[str, Any],
            daily: dict[str, Any]) -> list[dict[str, Any]]:
    received = {s["file"] for s in submissions if s.get("file") and s["received"]}
    used: dict[str, list[str]] = {}
    for r in ravenglass["obligors"]:
        for key in ("layout", "certificate_layout"):
            if r[key]:
                used.setdefault(r[key], []).append(r["id"])
    feeds = {f["feed"]: f for f in daily["feeds"]}
    names = {f["id"]: f["name"] for f in facilities}
    out = []
    for entry in meta["mapping_library"]:
        if entry.get("obligor_documents"):
            count, unit = len(used.get(entry["id"], [])), "obligors"
        elif entry.get("daily"):
            count, unit = feeds[entry["daily"]]["received"], "daily files"
        else:
            count, unit = sum(1 for f in entry.get("files", []) if f in received), "files"
        versions = entry["versions"]
        last = versions[-1]
        out.append({
            "id": entry["id"], "document": entry["document"], "sender": entry["sender"],
            "format": entry["format"], "client": entry["client"],
            "facilities": entry["facilities"],
            "facility_names": [names.get(f, f.title()) for f in entry["facilities"]],
            "columns": entry.get("columns"), "signature": entry.get("signature"),
            "count": count, "unit": unit, "obligors": used.get(entry["id"], []),
            "version": last["version"],
            "last_changed": last["date"].isoformat() if isinstance(last["date"], date)
            else str(last["date"]), "changed_by": last["by"],
            "versions": [{**v, "date": v["date"].isoformat() if isinstance(v["date"], date)
                          else str(v["date"])} for v in versions],
        })
    return out
