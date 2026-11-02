"""The Facility Ontology covers everything the model is asked about, and its checks can fail."""

import json

import pytest
from conftest import RECORDED_RUN

from app.pipeline import ontology
from app.pipeline.assemble import check_mapping
from app.pipeline.catalogue import FIELDS, PLATFORM_FIELDS


def test_every_term_and_tape_field_has_exactly_one_concept():
    concepts = ontology.concepts().values()
    for name, _, _ in FIELDS:
        assert sum(name in c.get("fields", []) for c in concepts) == 1, name
    for name in PLATFORM_FIELDS:
        assert sum(name in c.get("tape_fields", []) for c in concepts) == 1, name


def test_every_relation_points_at_a_concept():
    known = ontology.concepts()
    for concept in known.values():
        for relation in concept.get("relations", []):
            assert relation["target"] in known, (concept["id"], relation["target"])


def test_grounding_brings_in_related_concepts():
    given = {c["id"] for c in ontology.grounding({"advance_rate"})}
    assert given == {"advance_rate", "eligible_pool", "amendment"}


@pytest.mark.parametrize(("concept", "value"), [
    ("advance_rate", "85%"), ("leverage_covenant", "6.00 to 1.00"),
    ("facility_limit", "US$250,000,000"), ("final_maturity", "15 January 2029"),
    ("delinquency_trigger", "Three-period average Delinquency Ratio exceeds 6.0%"),
])
def test_values_in_their_concepts_form_pass(concept, value):
    assert ontology.form_problem(concept, value) is None


@pytest.mark.parametrize(("concept", "value", "why"), [
    ("advance_rate", "US$85,000,000", "a percentage"),
    ("leverage_covenant", "6.00x", "a ratio"),
    ("facility_limit", "250 million", "a US dollar amount"),
])
def test_a_value_in_the_wrong_form_is_caught(concept, value, why):
    assert why in ontology.form_problem(concept, value)


def test_cited_concepts_outside_the_grounding_are_named():
    given = ontology.grounding({"margin"})
    assert ontology.unknown(["margin", "eligible_pool"], given) == ["eligible_pool"]


def test_a_mapping_whose_concept_disagrees_is_held_for_review():
    rows = [{"Bal": "1200.50"}]
    agreed = check_mapping([{"column": "Bal", "field": "current_balance",
                             "concept": "outstanding_balance", "confidence": "high",
                             "note": None}], rows)[0]
    assert (agreed["confidence"], agreed["concept"]) == ("high", "Outstanding balance")
    wrong = check_mapping([{"column": "Bal", "field": "current_balance",
                            "concept": "loan_amount", "confidence": "high", "note": None}], rows)[0]
    assert wrong["confidence"] == "low"
    assert "outstanding balance field" in wrong["note"]


recorded = pytest.mark.skipif(not (RECORDED_RUN / "workbench.json").exists(),
                              reason="No run has been recorded")


@recorded
def test_the_recorded_run_is_grounded_throughout():
    run = json.loads((RECORDED_RUN / "workbench.json").read_text("utf-8"))
    assert run["ontology_version"] == ontology.version()
    assert all(term["grounding"]["concept"]["id"] for term in run["terms"])
    found = [term for term in run["terms"] if term["status"] != "missing"]
    assert all(term["grounding"]["cited"] for term in found)
    assert all(row["concept"] for row in run["mapping"]["rows"] if row["field"])
    assert all(rule["concepts"] for rule in run["rules"])
