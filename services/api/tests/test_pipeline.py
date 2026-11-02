"""The pipeline's plumbing and checks, tested against a scripted stand-in for the model.

The stand-in is built from the answer key, so these tests prove the code around
the model. They say nothing about how well a real model reads the documents.
"""

import ast
import json
from pathlib import Path

import pytest

from app import engine_service
from app.config import settings
from app.pipeline import checks, ontology, steps
from app.pipeline.assemble import (
    Evidence,
    build_ruleset,
    build_terms,
    check_mapping,
    iso_date,
)
from app.pipeline.documents import find_citation, read_pdf
from app.pipeline.gateway import Gateway, ModelError, ReplayMiss, Usage, strict_schema
from app.pipeline.run import read_delinquency_history, read_financials, run_pipeline

PACK = settings.deal_kit_output / "pack"


def key(name: str):
    return json.loads((settings.deal_kit_output / "answer-key" / f"{name}.json").read_text("utf-8"))


class Scripted:
    """Answers each request from a table, by the task the gateway recorded."""

    def __init__(self, answers):
        self.answers = answers
        self.calls = 0

    def request(self, payload):
        self.calls += 1
        schema = payload["output_config"]["format"]["schema"]
        task = next(name for name, match in TASK_SHAPES.items() if match(schema, payload))
        return json.dumps(self.answers[task](payload)), Usage("", 1000, 200)


def text_of(payload) -> str:
    return " ".join(block.get("text", "") for block in payload["messages"][0]["content"])


TASK_SHAPES = {
    "classify": lambda s, p: "Classified" in s.get("$defs", {}),
    "scan": lambda s, p: "legibility" in s["properties"],
    "extract": lambda s, p: "ExtractedField" in s.get("$defs", {}),
    "amend": lambda s, p: "AmendmentChange" in s.get("$defs", {}),
    "rules": lambda s, p: "DraftEligibility" in s.get("$defs", {}),
    "map": lambda s, p: "ColumnMatch" in s.get("$defs", {}),
    "reqs": lambda s, p: "RequirementMatch" in s.get("$defs", {}),
    "leverage": lambda s, p: "FormulaPart" in s.get("$defs", {}),
}

KINDS = {"Credit_Agreement": "Agreement", "Amendment": "Amendment", "Fee_Letter": "Fee letter",
         "Loan_Tape": "Loan tape", "Servicer": "Servicer report", "BBC": "Certificate",
         "Financial": "Financials", "Requirements": "Requirements"}


def scripted_classify(_):
    documents = []
    for path in sorted(PACK.iterdir()):
        kind = next(value for name, value in KINDS.items() if name in path.name)
        amendment = kind == "Amendment"
        documents.append({
            "file": path.name, "kind": kind, "title": path.stem, "dated": "2026-01-15",
            "version": "1", "effective": "2026-03-01" if amendment else "2026-01-15",
            "amends_file": "Bramble_Credit_Agreement_Executed.pdf" if amendment else None,
        })
    return {"documents": documents}


def scripted_extract(payload):
    wanted = text_of(payload)
    fields = []
    for item in key("fields"):
        name = item["name"]
        if f"- {name} (" not in wanted:
            continue
        missing = name == "Restricted jurisdictions"
        value = item["value"]
        if name == "Advance rate":
            value, quote, document = "85%", 'The "Advance Rate" means 85%.', "credit_agreement"
        elif name == "Facility limit":
            value, quote, document = "US$250,000,000", "US$250,000,000", "credit_agreement"
        elif name == "Reserve amount":
            value = "1% of eligible pool"
            quote, document = "an amount equal to 1% of the Eligible Pool Balance", item["document"]
        else:
            quote, document = item["quote"] or "", item["document"]
            value = _quoted_value(name, str(value), quote)
        fields.append({"name": name, "found": not missing, "value": "" if missing else value,
                       "source_document": document, "clause": item["clause"], "quote": quote,
                       "concepts": [ontology.for_field(name)]})
    return {"fields": fields}


def _quoted_value(name: str, value: str, quote: str) -> str:
    # Keep only figures the quote itself proves, as a real answer would.
    return value if checks.contains_value(value, quote) else quote


def scripted_rules(_):
    rules = json.loads(settings.ruleset_file.read_text("utf-8"))
    drafts = []
    tests = {
        1: ("max", "days_past_due", None, 30), 3: ("max", "original_term", None, 84),
        4: ("min", "fico", 540, None), 5: ("max", "current_balance", None, 75000),
        8: ("max", "modification_count", None, 1), 9: ("between", "apr", 6, 29.99),
        10: ("vehicle_age_max", None, None, 10), 11: ("min", "payments_made", 1, None),
    }
    special = {2: "not_status", 6: "in_us_states", 7: "not_restricted", 12: "unique_vin"}
    for number, rule in enumerate(rules["eligibility"], start=1):
        test, field, low, high = tests.get(number, (special.get(number), None, None, None))
        drafts.append({"paragraph": number, "plain_english": rule["plain_english"],
                       "clause_text": rule["clause_text"], "test": test, "field": field,
                       "low": low, "high": high,
                       "statuses": ["CHARGED_OFF", "REPO"] if number == 2 else [],
                       "concepts": ["eligibility_criterion"]
                       + ([ontology.for_tape_field(field)] if field else [])})
    buckets = [("state", None), ("dealer", None), ("long_term", 72), ("used", None),
               ("low_fico", 600)]
    concentration = [
        {"plain_english": rule["plain_english"], "clause_text": rule["clause_text"],
         "clause_ref": rule["clause_ref"], "bucket": bucket, "limit_pct": float(rule["limit_pct"]),
         "threshold": threshold, "effective_from": rule.get("effective_from"),
         "concepts": ["concentration_limit"]}
        for rule, (bucket, threshold) in zip(rules["concentration"], buckets, strict=True)
    ]
    return {"eligibility": drafts, "concentration": concentration}


ANSWERS = {
    "classify": scripted_classify,
    "scan": lambda _: {"text": "ANNEX A\nCalderwood Bank plc US$250,000,000",
                       "legibility": "poor", "x0": 0.2, "x1": 0.8, "top": 0.29, "bottom": 0.34},
    "extract": scripted_extract,
    "amend": lambda _: {"signed": "2026-02-20", "changes": [{
        "target": "Section 2.3", "kind": "replace_value", "old_value": "85%",
        "new_value": "82.5%", "effective_from": "2026-03-01",
        "quote": 'In Section 2.3, "85%" is deleted and replaced with "82.5%"'}]},
    "rules": scripted_rules,
    "map": lambda _: {"columns": [
        {"column": c, "field": f, "concept": ontology.for_tape_field(f), "confidence": "high",
         "note": None}
        for c, f in key("mapping")["columns"].items()]},
    "reqs": lambda _: {"alerts": 6, "requirements": [
        {"requirement": "Weighted average APR", "level": "Pool", "status": "derived",
         "detail": "sum(NoteRate x CurrBal) / sum(CurrBal)"},
        {"requirement": "Loan ID", "level": "Loan", "status": "met", "detail": "LoanNumber"}]},
    "leverage": lambda _: {"term": "Leverage Ratio", "formula": "(TL - SD) / (TNW + SD)", "parts": [
        {"clause": "6.12(c)", "quote": "Solely for the purpose of calculating the Leverage Ratio"},
    ]},
}


@pytest.fixture
def gateway(tmp_path):
    client = Scripted(ANSWERS)
    made = Gateway(mode="record", fixtures=tmp_path / "llm", client_factory=lambda: client)
    made.scripted = client
    return made


@pytest.fixture
def pipeline_output(gateway, tmp_path, monkeypatch):
    out = tmp_path / "run"
    monkeypatch.setattr(settings, "pipeline_dir", out)
    yield run_pipeline(gateway, PACK, out)
    monkeypatch.undo()
    engine_service.reset()


def test_replay_needs_no_network(gateway, tmp_path, monkeypatch):
    out = tmp_path / "run"
    monkeypatch.setattr(settings, "pipeline_dir", out)
    recorded = run_pipeline(gateway, PACK, out)

    def no_client():
        raise AssertionError("Replay must never build a client")

    replay = Gateway(mode="replay", fixtures=gateway.fixtures, client_factory=no_client)
    replayed = run_pipeline(replay, PACK, out)
    assert replayed["exceptions"] == recorded["exceptions"]
    assert replayed["terms"] == recorded["terms"]
    monkeypatch.undo()
    engine_service.reset()


def test_replay_refuses_an_unrecorded_request(tmp_path):
    gateway = Gateway(mode="replay", fixtures=tmp_path)
    with pytest.raises(ReplayMiss):
        steps.classify(gateway, {"a.pdf": "text"})


def test_a_changed_prompt_cannot_reuse_an_old_answer(gateway):
    steps.classify(gateway, {"a.pdf": "first"})
    calls = gateway.scripted.calls
    steps.classify(gateway, {"a.pdf": "first"})
    assert gateway.scripted.calls == calls
    steps.classify(gateway, {"a.pdf": "second"})
    assert gateway.scripted.calls == calls + 1


def test_an_invalid_answer_is_not_saved(tmp_path):
    class Broken:
        def request(self, payload):
            return '{"documents": "nonsense"}', Usage("", 1, 1)

    gateway = Gateway(mode="record", fixtures=tmp_path, client_factory=Broken)
    with pytest.raises(ValueError):
        steps.classify(gateway, {"a.pdf": "text"})
    assert not list(tmp_path.rglob("*.json"))


def test_no_client_is_a_clear_error(tmp_path):
    with pytest.raises(ModelError):
        steps.classify(Gateway(mode="record", fixtures=tmp_path), {"a.pdf": "text"})


def test_strict_schema_closes_every_object():
    schema = strict_schema(steps.Classification)
    assert schema["additionalProperties"] is False
    assert schema["$defs"]["Classified"]["additionalProperties"] is False
    assert "amends_file" in schema["$defs"]["Classified"]["required"]


@pytest.mark.parametrize("model", [
    steps.Classification, steps.ScanRead, steps.Extraction, steps.AmendmentReading,
    steps.ResolvedFormula, steps.DraftRules, steps.TapeMapping, steps.RequirementReading,
])
def test_strict_schema_keeps_every_field(model):
    """A field named like a schema annotation, such as title, must survive the clean-up."""
    original = model.model_json_schema()
    closed = strict_schema(model)
    for name, node in [("root", original), *original.get("$defs", {}).items()]:
        target = closed if name == "root" else closed["$defs"][name]
        assert set(target["properties"]) == set(node["properties"])
        assert set(target["required"]) == set(node["properties"])
        assert all("title" not in field for field in target["properties"].values())


def test_pipeline_finds_the_planted_exceptions_from_the_files(pipeline_output):
    ids = {item["id"] for item in pipeline_output["exceptions"]}
    assert {f"X{number}" for number in range(1, 11)} <= ids


def test_pipeline_engine_results_match_the_key(pipeline_output):
    run = engine_service.validation_run(dealer_match=False)
    expected = key("calculation")["system_before_dealer_match"]
    assert run["system"]["eligible_pool"] == expected["eligible_pool"]
    assert run["system"]["borrowing_base"] == expected["borrowing_base"]
    assert run["provisional"]


def test_pipeline_reads_covenant_inputs_from_the_statements(pipeline_output):
    tests = engine_service.validation_run(dealer_match=False)["covenants"]
    leverage = next(t for t in tests["tests"] if "leverage" in t["name"])
    assert leverage["value"] == key("exceptions")["X10"]["leverage_with_carve_out"]
    assert tests["delinquency"]["monthly_pct"][:2] == [0.71, 0.76]


def test_advance_rate_keeps_both_versions(pipeline_output):
    rate = next(t for t in pipeline_output["terms"] if t["name"] == "Advance rate")
    assert rate["source"]["document"] == "amendment_1"
    assert rate["also_cited"][0]["document"] == "credit_agreement"
    assert "82.5%" in rate["value"]


def test_a_made_up_quote_is_caught():
    documents = {"credit_agreement": read_pdf("credit_agreement",
                                              PACK / "Bramble_Credit_Agreement_Executed.pdf")}
    evidence = Evidence(documents, [])
    assert evidence.verify("credit_agreement", "The Advance Rate shall be 90%.")[1] == "unverified"
    assert find_citation(documents, "credit_agreement", 'The "Advance Rate" means 85%.')


def test_an_unverified_value_is_queued_and_marked_low():
    field = {"name": "Margin", "found": True, "value": "3.25%", "source_document": "x",
             "clause": "2.6", "quote": "A quote that is nowhere in any document"}
    first = steps.Extraction(fields=[steps.ExtractedField(**field)])
    reading = steps.AmendmentReading(changes=[], signed="2026-02-20")
    rate = {**field, "name": "Advance rate"}
    first.fields.append(steps.ExtractedField(**rate))
    terms, problems = build_terms(first, steps.Extraction(fields=[]), Evidence({}, []), reading)
    margin = next(term for term in terms if term["name"] == "Margin")
    assert margin["confidence"] == "low" and not margin["verified"]
    assert any(problem["field"] == "Margin" for problem in problems)


def test_a_disagreeing_second_read_lowers_a_tier_1_value():
    documents = {"credit_agreement": read_pdf("credit_agreement",
                                              PACK / "Bramble_Credit_Agreement_Executed.pdf")}
    make = lambda value: steps.Extraction(fields=[  # noqa: E731
        steps.ExtractedField(name="Reserve amount", found=True, value=value,
                             source_document="credit_agreement", clause="1.1",
                             quote="an amount equal to 1% of the Eligible Pool Balance"),
        steps.ExtractedField(name="Advance rate", found=True, value="85%",
                             source_document="credit_agreement", clause="2.3",
                             quote='The "Advance Rate" means 85%.')])
    terms, problems = build_terms(make("1%"), make("2%"), Evidence(documents, []),
                                  steps.AmendmentReading(changes=[], signed=""))
    reserve = next(term for term in terms if term["name"] == "Reserve amount")
    assert reserve["confidence"] == "medium"
    assert any("second read" in problem["why"] for problem in problems)


def test_missing_schedule_is_found_by_code():
    agreement = read_pdf("credit_agreement", PACK / "Bramble_Credit_Agreement_Executed.pdf")
    missing = checks.missing_attachments(agreement, ["Credit Agreement header\n\nANNEX A\n"])
    assert [item["name"] for item in missing] == ["Schedule 4"]


def test_date_review_matches_the_planted_rows():
    planted = key("exceptions")["X9"]
    with (PACK / "BAF_Loan_Tape_2026-04.csv").open(encoding="utf-8", newline="") as handle:
        import csv

        rows = [{"origination_date": r["OrigDate"], "first_payment_date": r["FirstPmtDate"],
                 "loan_id": r["LoanNumber"]} for r in csv.DictReader(handle)]
    review = checks.review_dates(rows, "origination_date", "first_payment_date", "loan_id")
    assert set(review.uncertain_rows) >= set(planted["uncertain_loan_ids"])
    assert 0 < review.day_first_rows <= planted["rows"]


def test_a_rule_status_that_is_not_on_the_tape_stops_the_run():
    draft = steps.DraftRules.model_validate(scripted_rules(None))
    draft.eligibility[1].statuses = ["charged_off", "repossessed"]
    terms = [{"name": "Advance rate", "value": "85%"},
             {"name": "Facility limit", "value": "US$250,000,000"},
             {"name": "Reserve amount", "value": "1%"}]
    with pytest.raises(ValueError, match="not on the tape"):
        build_ruleset(draft, terms, "2026-01-15", None, ["ACTIVE", "CHARGED_OFF", "REPO"])


def test_a_rule_relying_on_a_concept_it_was_not_given_stops_the_run():
    draft = steps.DraftRules.model_validate(scripted_rules(None))
    draft.eligibility[0].concepts = ["recovery_rate"]
    terms = [{"name": "Advance rate", "value": "85%"},
             {"name": "Facility limit", "value": "US$250,000,000"},
             {"name": "Reserve amount", "value": "1%"}]
    with pytest.raises(ValueError, match="not given"):
        build_ruleset(draft, terms, "2026-01-15", None, ["ACTIVE", "CHARGED_OFF", "REPO"])


def test_a_value_in_the_wrong_form_for_its_concept_is_marked_low(tmp_path, monkeypatch):
    def wrong_form(payload):
        answer = scripted_extract(payload)
        for item in answer["fields"]:
            if item["name"] == "Margin":
                item["value"] = item["quote"] = "three and a quarter"
        return answer

    client = Scripted({**ANSWERS, "extract": wrong_form})
    gateway = Gateway(mode="record", fixtures=tmp_path / "llm", client_factory=lambda: client)
    monkeypatch.setattr(settings, "pipeline_dir", tmp_path / "run")
    output = run_pipeline(gateway, PACK, tmp_path / "run")
    engine_service.reset()
    term = next(t for t in output["terms"] if t["name"] == "Margin")
    assert term["confidence"] == "low"


def test_prose_around_a_date_is_ignored():
    assert iso_date("2026-03-01 (amendments take effect)") == "2026-03-01"
    assert iso_date("Not stated") is None


def test_prose_answers_agree_when_only_the_wording_differs():
    assert checks.values_agree("Deducted from Eligible Pool Balance before the Advance Rate",
                               "Deducted from the Eligible Pool Balance before Advance Rate")
    assert not checks.values_agree("Deducted before the rate", "Added after the reserve is cut")
    assert not checks.values_agree("1% of the pool", "2% of the pool")


def test_recordings_from_old_prompts_are_pruned(gateway):
    steps.classify(gateway, {"a.pdf": "first"})
    old = list(gateway.fixtures.rglob("*.json"))
    gateway.used.clear()
    steps.classify(gateway, {"a.pdf": "second"})
    assert gateway.prune() == 1
    assert not old[0].exists()


def test_dealer_variants_are_grouped():
    groups = checks.dealer_variants(["Sunrise Motors LLC", "Sunrise Motors", "Other Auto"])
    assert groups == [["Sunrise Motors", "Sunrise Motors LLC"]]


def test_blank_recoveries_are_found_by_code():
    report = read_pdf("servicer_report", PACK / "BAF_Servicer_Report_April_2026.pdf")
    assert [label for label, _ in checks.blank_money_lines(report)] == ["Recoveries (US$)"]


def test_statements_and_trend_are_read_from_the_pdfs():
    figures = read_financials(read_pdf("f", PACK / "BAF_Financial_Statements_Q1_2026.pdf"))
    assert figures["total_equity"] == 58000 and figures["total_liabilities"] == 320800
    report = read_pdf("s", PACK / "BAF_Servicer_Report_April_2026.pdf")
    assert read_delinquency_history(report)[:2] == [0.71, 0.76]


def test_mapping_rejects_a_column_whose_values_do_not_fit():
    columns = [{"column": "VIN", "field": "fico", "confidence": "high", "note": None}]
    check_mapping(columns, [{"VIN": "ZRLYU0347EY9SYD5P"}])
    assert columns[0]["confidence"] == "low"


def test_pipeline_never_reads_the_answer_key():
    package = Path(__file__).parent.parent / "app" / "pipeline"
    for path in package.glob("*.py"):
        source = path.read_text("utf-8")
        assert "answer-key" not in source, path.name
        names = {node.attr for node in ast.walk(ast.parse(source))
                 if isinstance(node, ast.Attribute)}
        assert "read_key" not in names, path.name
