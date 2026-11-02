"""The Private Credit Ontology: what the model is grounded in, and what checks its answers."""

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

ONTOLOGY_PATH = Path(__file__).parent / "private_credit_ontology.yaml"

INSTRUCTION = (
    "The material includes `ontology`: Artizent's Private Credit Ontology for the concepts that "
    "apply here, with the layer each belongs to (private credit, asset-based finance or auto "
    "loans), what each means, the form its value takes and how the concepts relate. Reason in "
    "those terms, and prefer their meanings to any guess of your own. Where the output asks for "
    "`concepts`, list the IDs you relied on, using only IDs given in the ontology."
)


@lru_cache
def _document() -> dict[str, Any]:
    return yaml.safe_load(ONTOLOGY_PATH.read_text(encoding="utf-8"))


def version() -> str:
    return _document()["version"]


def name() -> str:
    return _document()["name"]


def layers() -> dict[str, dict[str, Any]]:
    return {layer["id"]: layer for layer in _document()["layers"]}


def concepts() -> dict[str, dict[str, Any]]:
    return {concept["id"]: concept for concept in _document()["concepts"]}


def for_field(name: str) -> str:
    """The concept that governs a facility term."""
    return next(cid for cid, concept in concepts().items() if name in concept.get("fields", []))


def for_tape_field(name: str) -> str:
    """The concept a platform field belongs to."""
    return next(cid for cid, concept in concepts().items()
                if name in concept.get("tape_fields", []))


def grounding(ids: set[str]) -> list[dict[str, Any]]:
    """These concepts and the ones they relate to, in ontology order, as given to the model."""
    known = concepts()
    related = {r["target"] for cid in ids for r in known[cid].get("relations", [])}
    return [
        {"id": cid, "layer": layers()[c["layer"]]["label"], "label": c["label"], "kind": c["kind"],
         "meaning": c["meaning"],
         "relations": [f"{r['type']} {r['target']}" for r in c.get("relations", [])]}
        for cid, c in known.items() if cid in ids | related
    ]


def block(ids: set[str]) -> str:
    """The grounding as it appears in a prompt."""
    return "ontology:\n" + json.dumps(grounding(ids), indent=0)


def unknown(cited: list[str], given: list[dict[str, Any]]) -> list[str]:
    """IDs the model cited that were not in what it was given."""
    return sorted(set(cited) - {concept["id"] for concept in given})


FORMS = {
    "money": re.compile(r"US\$\s?\d"),
    "percent": re.compile(r"\d(\.\d+)?\s?%"),
    "ratio": re.compile(r"\d+(\.\d+)?\s+to\s+\d+(\.\d+)?"),
    "count": re.compile(r"\d"),
    "date": re.compile(r"\b(19|20)\d{2}\b"),
}
FORM_NAMES = {"money": "a US dollar amount", "percent": "a percentage",
              "ratio": "a ratio such as 6.00 to 1.00", "count": "a number", "date": "a date"}


def form_problem(concept_id: str, value: str) -> str | None:
    """Why a value does not take the form its concept defines, or None if it does."""
    concept = concepts()[concept_id]
    form = FORMS.get(concept["kind"])
    if form is None or form.search(value):
        return None
    return f"The ontology defines {concept['label'].lower()} as {FORM_NAMES[concept['kind']]}."


def view(concept_id: str) -> dict[str, Any]:
    """A concept as the workbench shows it, with its relations in words."""
    known = concepts()
    concept = known[concept_id]
    return {
        "id": concept_id, "label": concept["label"], "meaning": concept["meaning"],
        "layer": layers()[concept["layer"]]["label"],
        "relations": [{"type": r["type"], "target": known[r["target"]]["label"]}
                      for r in concept.get("relations", [])],
    }
