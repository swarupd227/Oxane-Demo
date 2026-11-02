"""Run the whole pipeline over the pack, and save what the workbench reads.

    python -m app.pipeline.run --mode record   (needs a model key)
    python -m app.pipeline.run --mode replay   (no network)
"""

import argparse
import csv
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

from openpyxl import load_workbook

from app import engine_service
from app.config import settings
from app.pipeline import checks, steps
from app.pipeline.assemble import (
    Evidence,
    Scan,
    amount,
    build_ruleset,
    build_terms,
    check_mapping,
    formula_sources,
    iso_date,
    percent,
)
from app.pipeline.documents import read_pdf
from app.pipeline.gateway import AnthropicClient, Gateway
from app.pipeline.queue import build_queue

KIND_IDS = {
    "Agreement": "credit_agreement", "Amendment": "amendment_1", "Fee letter": "fee_letter",
    "Loan tape": "loan_tape", "Servicer report": "servicer_report",
    "Certificate": "borrowing_base_certificate", "Financials": "financial_statements",
    "Requirements": "lender_requirements",
}


def workbook_text(path: Path) -> str:
    book = load_workbook(path, data_only=True)
    lines = []
    for sheet in book.worksheets:
        lines.append(f"[sheet {sheet.title}]")
        for row in sheet.iter_rows(values_only=True):
            cells = [str(cell) for cell in row if cell is not None]
            if cells:
                lines.append(" | ".join(cells))
    return "\n".join(lines)


def read_tape(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def read_financials(document: Any) -> dict[str, int]:
    """The statements are tables of labelled figures, so plain code reads them."""
    text = " ".join(page.text for page in document.pages)

    def figure(label: str) -> int:
        match = re.search(re.escape(label) + r" ([\d,]+)", text)
        if match is None:
            raise ValueError(f"{label} is not in the statements")
        return int(match.group(1).replace(",", ""))

    return {
        "total_equity": figure("Total members' equity"), "goodwill": figure("Goodwill"),
        "intangibles": figure("Intangible assets, net"),
        "related_party_receivables": figure("Due from affiliates"),
        "subordinated_debt": figure("Subordinated notes"),
        "total_liabilities": figure("Total liabilities"),
        "unrestricted_cash": figure("Cash and cash equivalents"),
    }


def read_delinquency_history(document: Any) -> list[float]:
    text = " ".join(page.text for page in document.pages)
    rows = re.findall(r"(?:February|March|April) 2026 (\d+\.\d+)%", text)
    if len(rows) < 3:
        raise ValueError("The servicer report has no three-month trend")
    return [float(value) for value in rows[:3]]


def subordinated_debt_cap(agreement: Any) -> int:
    text = " ".join(page.text for page in agreement.pages)
    match = re.search(r"Subordinated Debt in an aggregate amount of up to US\$([\d,]+)", text)
    if match is None:
        raise ValueError("The agreement has no Subordinated Debt carve-out")
    return int(match.group(1).replace(",", ""))


def _previews(files: list[Path]) -> dict[str, str]:
    previews = {}
    for path in files:
        if path.suffix == ".pdf":
            previews[path.name] = "\n".join(page.raw for page in read_pdf("", path).pages[:2])
        elif path.suffix == ".xlsx":
            previews[path.name] = workbook_text(path)
        else:
            previews[path.name] = "\n".join(path.read_text(encoding="utf-8").splitlines()[:3])
    return previews


def _save(folder: Path, name: str, content: Any) -> None:
    (folder / name).write_text(json.dumps(content, indent=1, sort_keys=True, default=str) + "\n",
                               encoding="utf-8")


def run_pipeline(gateway: Gateway, pack_dir: Path, out_dir: Path) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    files = sorted(path for path in pack_dir.iterdir() if path.is_file())
    pack_digest = hashlib.sha256(b"".join(path.read_bytes() for path in files)).hexdigest()

    # Intake: classify, then read each file by what it turned out to be.
    classified = steps.classify(gateway, _previews(files)).documents
    by_id = {KIND_IDS[item.kind]: pack_dir / item.file for item in classified
             if item.kind in KIND_IDS}
    documents = {doc: read_pdf(doc, path) for doc, path in by_id.items() if path.suffix == ".pdf"}
    agreement, amendment = documents["credit_agreement"], documents["amendment_1"]
    workbooks = {doc: workbook_text(path) for doc, path in by_id.items() if path.suffix == ".xlsx"}

    scans = [Scan("credit_agreement", page.number, steps.read_scan(gateway, agreement, page.number))
             for page in agreement.pages if page.is_image_only]
    missing = checks.missing_attachments(agreement, [scan.read.text for scan in scans])
    evidence = Evidence(documents, scans, workbooks)

    # Terms: two reads of Tier 1, each answer checked against the source.
    readable = {doc: item.body for doc, item in documents.items()
                if doc in ("credit_agreement", "amendment_1", "fee_letter")}
    readable["credit_agreement"] += "".join(
        f"\n\n[page {scan.page}, scanned]\n{scan.read.text}" for scan in scans)
    readable["lender_requirements"] = workbooks["lender_requirements"]
    first = steps.extract_terms(gateway, readable, tier1_only=False)
    second = steps.extract_terms(gateway, readable, tier1_only=True)
    reading = steps.read_amendment(gateway, amendment)
    terms, problems = build_terms(first, second, evidence, reading)

    # Mapping: the model suggests, and the values have to fit.
    rows = read_tape(by_id["loan_tape"])
    columns = check_mapping(
        [item.model_dump() for item in steps.map_tape(gateway, rows).columns], rows)
    mapped = {item["column"]: item["field"] for item in columns if item["field"]}
    renamed = [{mapped[k]: v for k, v in row.items() if k in mapped} for row in rows]
    dates = checks.review_dates(renamed, "origination_date", "first_payment_date", "loan_id")

    # Rules: the engine has to accept the draft, or the run stops here.
    signing = next(iso_date(item.dated) for item in classified if item.kind == "Agreement")
    effective = next((iso_date(item.effective) for item in classified
                      if item.kind == "Amendment"), None)
    statuses = sorted({row["status"] for row in renamed})
    ruleset = build_ruleset(steps.draft_rules(gateway, agreement, amendment, statuses), terms,
                            signing, effective, statuses)
    requirements = steps.read_requirements(
        gateway, workbooks["lender_requirements"], list(rows[0])).requirements

    # Save what the engine needs, then run it on this pipeline's own output.
    _save(out_dir, "pack.json", {doc: path.name for doc, path in by_id.items()})
    _save(out_dir, "mapping.json", {"columns": mapped})
    (out_dir / "ruleset.json").write_text(ruleset.model_dump_json(indent=1) + "\n",
                                          encoding="utf-8")
    values = {term["name"]: term["value"] for term in terms}
    _save(out_dir, "facts.json", {
        "financials": read_financials(documents["financial_statements"]),
        "delinquency_history": read_delinquency_history(documents["servicer_report"]),
        "origination_dates": dates.resolved,
        "uncertain_origination_dates": list(dates.uncertain_rows),
        "covenants": {
            "min_tangible_net_worth": amount(values["Minimum tangible net worth covenant"]),
            "max_leverage_ratio": re.findall(r"\d+\.\d+", values["Maximum leverage covenant"])[0],
            "min_liquidity": amount(values["Minimum liquidity covenant"]),
            "subordinated_debt_cap": subordinated_debt_cap(agreement),
            "delinquency_trigger_pct": percent(values["Delinquency trigger"]),
        },
    })
    engine_service.reset()
    before = engine_service.validation_run(dealer_match=False)
    after = engine_service.validation_run(dealer_match=True)

    formula = steps.resolve_leverage(gateway, agreement)
    formula_view = {"term": formula.term, "formula": formula.formula,
                    "conditions": formula.conditions,
                    "parts": formula_sources(formula, evidence)}
    variants = checks.dealer_variants(sorted({row["dealer_name"] for row in renamed}))
    blanks = checks.blank_money_lines(documents["servicer_report"])
    queue = build_queue(terms, problems, missing, before, after, variants, blanks, dates,
                        [item.model_dump() for item in requirements], formula_view)

    usage = {
        "model": gateway.model,
        "calls": len(gateway.usage),
        "input_tokens": sum(item.input_tokens for item in gateway.usage),
        "output_tokens": sum(item.output_tokens for item in gateway.usage),
        "cost_usd": gateway.total_cost_usd(),
        "model_seconds": round(sum(item.seconds for item in gateway.usage)),
    }
    result = {
        "seed": False,
        "period_end": engine_service.PERIOD_END.isoformat(),
        "pack_digest": pack_digest,
        "usage": usage,
        "documents": _document_views(classified, by_id, documents, rows),
        "missing_documents": [{"name": item["name"], "reason": item["reason"]}
                              for item in missing],
        "terms": terms,
        "rules": engine_service.rule_views(),
        "mapping": {
            "rows": [{**item, "sample": rows[0].get(item["column"], "")} for item in columns],
            "requirements": [{"name": item.requirement, "status": item.status,
                              "detail": item.detail} for item in requirements],
            "dates": {"mixed_rows": dates.mixed_rows, "uncertain": len(dates.uncertain_rows),
                      "method": "Resolved against the first payment date"},
        },
        "exceptions": queue,
    }
    _save(out_dir, "workbench.json", result)
    return result


def _document_views(classified: list[Any], by_id: dict[str, Path], documents: dict[str, Any],
                    rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    views = []
    ids = {path.name: doc for doc, path in by_id.items()}
    order = list(KIND_IDS)
    for item in sorted(classified, key=lambda c: order.index(c.kind) if c.kind in order else 99):
        doc = ids.get(item.file, item.file)
        if doc in documents:
            size = f"{len(documents[doc].pages)} pages"
        elif item.file.endswith(".csv"):
            size = f"{len(rows):,} rows, {len(rows[0])} columns"
        else:
            size = "Workbook"
        views.append({
            "id": doc, "file": item.file, "title": item.title, "kind": item.kind,
            "dated": iso_date(item.dated), "version": item.version,
            "effective": iso_date(item.effective) or iso_date(item.dated),
            "size": size, "links_to": ids.get(item.amends_file) if item.amends_file else None,
        })
    return views


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["record", "replay", "live"], required=True)
    mode = parser.parse_args().mode
    gateway = Gateway(mode=mode, fixtures=settings.llm_fixtures,
                      client_factory=lambda: AnthropicClient(settings.llm_provider))
    result = run_pipeline(gateway, settings.deal_kit_output / "pack", settings.pipeline_dir)
    if mode == "record":
        gateway.prune()
    print(json.dumps({"exceptions": len(result["exceptions"]), **result["usage"]}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
