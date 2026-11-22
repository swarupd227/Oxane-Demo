"""The casework answer key, read only by the scorecard. The pipeline must never read it."""

from pathlib import Path
from typing import Any

from dealkit.key import normalise, page_texts

# The defined terms the borrowing base and the delinquency test rest on, as an expert reads
# them: each term, a phrase from its definition and the terms its value is worked out from.
DEFINITIONS: list[dict[str, Any]] = [
    {"term": "Borrowing Base", "document": "credit_agreement",
     "quote": '"Borrowing Base" means, on any date of determination',
     "inputs": ["Eligible Pool Balance", "Excess Concentration Amount", "Advance Rate",
                "Reserve Amount"]},
    {"term": "Eligible Pool Balance", "document": "credit_agreement",
     "quote": '"Eligible Pool Balance" means, on any date',
     "inputs": ["Outstanding Balance", "Pool Receivable", "Eligible Receivable"]},
    {"term": "Eligible Receivable", "document": "credit_agreement",
     "quote": '"Eligible Receivable" means, on any date of determination',
     "inputs": ["Pool Receivable", "Schedule 1"]},
    {"term": "Excess Concentration Amount", "document": "credit_agreement",
     "quote": '"Excess Concentration Amount" means, on any date',
     "inputs": ["Schedule 2", "Outstanding Balance", "Eligible Receivable"]},
    {"term": "Advance Rate", "document": "credit_agreement",
     "quote": '"Advance Rate" has the meaning given in Section 2.3.',
     "inputs": ["Section 2.3"], "amended_by": "amendment_1"},
    {"term": "Reserve Amount", "document": "credit_agreement",
     "quote": '"Reserve Amount" means, on any date',
     "inputs": ["Eligible Pool Balance"]},
    {"term": "Schedule 2", "document": "credit_agreement", "quote": "CONCENTRATION LIMITS",
     "inputs": [], "amended_by": "amendment_1"},
    {"term": "Delinquency Ratio", "document": "credit_agreement",
     "quote": '"Delinquency Ratio" means, for any Collection Period',
     "inputs": ["Outstanding Balance", "Pool Receivable", "Defaulted Receivable"]},
    {"term": "Defaulted Receivable", "document": "credit_agreement",
     "quote": '"Defaulted Receivable" means any Receivable',
     "inputs": ["Credit and Collection Policy"]},
]

# Referred to by the definitions but not part of the pack: the policy is the servicer's own.
NOT_IN_PACK = ["Credit and Collection Policy"]


def definitions_key(pack_dir: Path, files: dict[str, str]) -> dict[str, Any]:
    texts = {doc: page_texts(pack_dir / name) for doc, name in files.items()
             if name.endswith(".pdf")}
    terms = []
    for item in DEFINITIONS:
        pages = texts[item["document"]]
        hits = [n for n, body in enumerate(pages, start=1) if normalise(item["quote"]) in body]
        if not hits:
            raise ValueError(f"Definition not found: {item['term']}")
        terms.append({**item, "page": hits[-1]})
    return {"terms": terms, "not_in_pack": NOT_IN_PACK,
            "edges": [[item["term"], target] for item in DEFINITIONS for target in item["inputs"]]}


def client_model_key(cells: dict[str, dict[str, Any]], impacts: dict[str, Any]
                     ) -> dict[str, Any]:
    differences = {topic: {**cell, **impacts.get(topic, {})} for topic, cell in cells.items()
                   if cell["differs"]}
    return {"cells": {topic: cell["cell"] for topic, cell in cells.items()},
            "differences": differences,
            "agreed": impacts["agreed"]}
