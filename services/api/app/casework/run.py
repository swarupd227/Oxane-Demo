"""Run the onboarding casework for case 0412, and save what the workbench reads.

    python -m app.casework.run --mode record   (needs a model key)
    python -m app.casework.run --mode replay   (no network)

It builds on the recorded onboarding run in fixtures/run: the rule set the engine accepted, the
accepted mapping and the validated terms. It never reads an answer key.
"""

import argparse
import hashlib
import json
import re
import sys
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from engine.run import run

from app import engine_service
from app.casework import backbook, client_model, config, definitions, qc, steps
from app.config import settings
from app.pipeline.documents import read_pdf
from app.pipeline.gateway import AnthropicClient, Gateway

CONFIG = Path(__file__).with_name("casework.yaml")
PLACEHOLDER = re.compile(r"\{\{(\w+)\}\}")
UNITS = {"Loans on the tape": "count", "Advance rate": "%", "Largest single-state share": "%",
         "Weighted average APR, eligible pool": "%", "60+ day delinquency ratio, April": "%"}
DEDUCTIONS = {"Excess concentration amount", "Reserve amount"}


@lru_cache
def record() -> dict[str, Any]:
    return yaml.safe_load(CONFIG.read_text(encoding="utf-8"))


def _pipeline(name: str) -> Any:
    return json.loads((settings.pipeline_dir / name).read_text(encoding="utf-8"))


def _difference_brief(row: dict[str, Any]) -> str:
    """What differs, in words with no figures, from the structure of the comparison."""
    if row["status"] == "silent":
        return "The lender's model sets a treatment the agreement does not address."
    return {
        "advance_rate": "The model applies a different advance rate from the one in effect for "
                        "the period.",
        "past_due_exclusion": "The model's past-due cut-off draws the boundary on the other side "
                              "of the boundary day from the agreement.",
        "concentration_denominator": "The model measures every concentration share against a "
                                     "different base from the agreement's.",
        "dealer_grouping": "The model treats affiliated dealers as separate dealers.",
        "fico_bucket": "The model's sub-600 band includes the boundary score, which the "
                       "agreement's band leaves out.",
    }.get(row["topic"], "The model treats this differently from the agreement.")


def _fill(text: str, values: dict[str, dict[str, Any]]) -> str:
    return PLACEHOLDER.sub(lambda m: str(values[m.group(1)]["value"]) if m.group(1) in values
                           else m.group(0), text)


def draft_queries(gateway: Gateway, comparison: dict[str, Any]) -> list[dict[str, Any]]:
    rows = {row["topic"]: row for row in comparison["rows"]}
    asked = [{"topic": d["topic"], "label": rows[d["topic"]]["label"],
              "difference": _difference_brief(rows[d["topic"]]),
              "placeholders": {f"{{{{{k}}}}}": v["means"] for k, v in d["placeholders"].items()}}
             for d in comparison["differences"]]
    drafts = {d.topic: d for d in steps.draft_client_queries(gateway, asked).queries}
    scripted = {q["topic"]: q for q in record()["queries"] if q.get("topic")}
    queries = []
    for difference in comparison["differences"]:
        topic = difference["topic"]
        draft = drafts.get(topic)
        values = difference["placeholders"]
        text = draft.text if draft else ""
        unknown = sorted({m for m in PLACEHOLDER.findall(text) if m not in values})
        numbers = sorted(set(re.findall(r"(?<![\w{])\d[\d,.]*%?", PLACEHOLDER.sub("", text))))
        plan = scripted.get(topic, {})
        queries.append({
            "id": plan.get("id", f"Q-{topic}"), "topic": topic, "to": plan.get("to"),
            "subject": draft.subject if draft else rows[topic]["label"],
            "template": text, "text": _fill(text, values), "figures": values,
            "unknown_placeholders": unknown, "numbers_in_text": numbers,
            "blocking": plan.get("blocking", False),
        })
    return sorted(queries, key=lambda q: q["id"])


def run_casework(gateway: Gateway, out_dir: Path) -> dict[str, Any]:
    meta = record()
    output = settings.deal_kit_output
    pack = _pipeline("pack.json")
    workbench = _pipeline("workbench.json")
    facts = _pipeline("facts.json")
    stored = _pipeline("mapping.json")["columns"]
    terms = {term["name"]: term for term in workbench["terms"]}
    documents = {doc: read_pdf(doc, output / "pack" / pack[doc])
                 for doc in ("credit_agreement", "amendment_1")}

    engine_service.reset()
    ruleset = engine_service.rules()
    loans = list(engine_service.loans())
    base = run(loans, ruleset, engine_service.PERIOD_END, engine_service.OUTSTANDING_CENTS,
               dealer_aliases=engine_service.SUNRISE)
    fico_id = client_model.fico_rule(ruleset)
    state_id = next(r.id for r in ruleset.concentration
                    if r.group_by and r.group_by.name == "obligor_state")
    answers = {k: v for q in meta["queries"] for k, v in (q.get("answer_facts") or {}).items()}

    # 1. Nested definitions: the model traces, code checks and resolves.
    trace = steps.trace_definitions(
        gateway, {doc: item.body for doc, item in documents.items()}, definitions.ROOTS)
    checked = definitions.check_trace(trace, documents)
    resolution = definitions.resolve(checked, base, loans, ruleset, answers)

    # 2. The client's own model against the validated configuration.
    model_path = output / meta["files"]["client_model"]
    cells = client_model.cells_of(model_path)
    reading = steps.read_client_model(gateway, client_model.workbook_text(cells))
    position = client_model.agreement_position(ruleset, base, documents, terms)
    comparison = client_model.compare(reading.treatments, cells, position, base, ruleset, loans,
                                      engine_service.SUNRISE, engine_service.OUTSTANDING_CENTS)
    queries = draft_queries(gateway, comparison)
    conventions = {t.topic: t.basis for t in reading.treatments}

    # 3. Independent QC.
    qc_result = qc.compare(output / meta["files"]["qc"], base, loans, fico_id, state_id)

    # 4. Configuration workbook rows.
    tape_file = pack["loan_tape"]
    sample = engine_service.tape_rows()[0]
    platform = qc.platform_values(base, loans, fico_id, state_id)
    config_rows = {
        "fields": config.field_rows(stored, dict(sample), tape_file, workbench["mapping"]["dates"],
                                    facts.get("origination_dates", {})),
        "rules": config.rule_rows(ruleset, documents),
        "terms": config.term_rows(ruleset, terms, facts),
        "report": config.report_rows(
            platform, {line: UNITS.get(line, "US$") for line in platform},
            {"percent": conventions.get("report_percent_format", ""),
             "negative": conventions.get("report_negative_format", ""),
             "nil": conventions.get("report_nil_format", "")}, DEDUCTIONS),
        "ruleset_digest": ruleset.digest,
    }

    # 5. Backbook: the stored mapping applied to existing deals.
    statuses = {loan["status"] for loan in loans}
    deals, tapes = backbook.load(output / meta["files"]["backbook"], meta["backbook"], stored,
                                 statuses)
    found = [d for deal in deals for d in deal["differences"]]
    suggestions = steps.suggest_backbook(gateway, found, stored).suggestions if found else []
    backbook.attach(deals, tapes, suggestions, stored, statuses)

    usage = {
        "model": gateway.model, "calls": len(gateway.usage),
        "input_tokens": sum(item.input_tokens for item in gateway.usage),
        "output_tokens": sum(item.output_tokens for item in gateway.usage),
        "cost_usd": gateway.total_cost_usd(),
        "model_seconds": round(sum(item.seconds for item in gateway.usage)),
    }
    result = {
        "case": meta["case"]["number"],
        "inputs": {
            "ruleset_digest": ruleset.digest,
            "client_model": hashlib.sha256(model_path.read_bytes()).hexdigest(),
        },
        "usage": usage,
        "definitions": {**checked, **resolution, "roots": definitions.ROOTS},
        "client_model": {"file": model_path.name, "template_version": reading.template_version,
                         **comparison},
        "queries": queries,
        "qc": qc_result,
        "config": config_rows,
        "backbook": deals,
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "casework.json").write_text(
        json.dumps(result, indent=1, sort_keys=True, default=str) + "\n", encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["record", "replay", "live"], required=True)
    mode = parser.parse_args().mode
    gateway = Gateway(mode=mode, fixtures=settings.casework_llm_fixtures,
                      client_factory=lambda: AnthropicClient(settings.llm_provider))
    result = run_casework(gateway, settings.casework_dir)
    if mode == "record":
        gateway.prune()
    checks = result["definitions"]["checks"]
    print(json.dumps({
        "definition_quotes": f"{checks['quotes_found']} of {checks['quotes']}",
        "differences": len(result["client_model"]["differences"]),
        "queries": len(result["queries"]),
        "qc_genuine": result["qc"]["genuine"],
        "backbook_exceptions": sum(d["exceptions"] for d in result["backbook"]),
        **result["usage"],
    }, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
