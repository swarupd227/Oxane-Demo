"""What the casework run asks the model. Every answer is checked by code before it is used.

The model reads (definitions, the client's model), suggests (backbook differences) and drafts
(client queries). It never computes a figure: impacts, values and dates come from code, and
drafted text carries {{placeholders}} that code fills.
"""

import json
from typing import Any, Literal

from pydantic import BaseModel

from app.pipeline.catalogue import PLATFORM_FIELDS
from app.pipeline.gateway import Gateway
from app.pipeline.steps import GROUND_RULES

# Nested definitions


class Reference(BaseModel):
    target: str
    role: Literal["input", "context"]


class DefinedTerm(BaseModel):
    term: str
    document: Literal["credit_agreement", "amendment_1"]
    clause: str
    quote: str
    refers_to: list[Reference]
    amended_by: str | None
    amendment_quote: str | None


class DefinitionTrace(BaseModel):
    terms: list[DefinedTerm]
    not_in_pack: list[str]


def trace_definitions(gateway: Gateway, documents: dict[str, str], roots: list[str]
                      ) -> DefinitionTrace:
    body = "\n\n".join(f'<document id="{name}">\n{text}\n</document>'
                       for name, text in sorted(documents.items()))
    return gateway.parse(
        "trace_definitions", GROUND_RULES,
        [{"type": "text", "text": body, "cache_control": {"type": "ephemeral"}},
         {"type": "text", "text": (
             "Trace the chain of defined terms behind each of these: " + ", ".join(roots) + ". "
             "Start at each one and follow every defined term, section or schedule its "
             "definition relies on, then theirs, until nothing further in these documents is "
             "needed to work the value out. List each term once. Name a section or schedule "
             "node like Section 2.3 or Schedule 2, and a defined term exactly as it is "
             "capitalised in its definition, in the singular. `quote` is the opening words of "
             "the definition or clause, eight to thirty words, copied exactly and all from one "
             "page. In `refers_to`, a reference is an input when the term's value is worked out "
             "from it, and context when it is only mentioned, such as a document a figure is "
             "shown in. If an amendment changes the term, its section or schedule, give the "
             "amendment's clause in `amended_by` like Amendment No. 1, Section 2(a), and its "
             "words, copied exactly, in `amendment_quote`. `not_in_pack` lists any document a "
             "definition relies on whose content is not in these documents.")}],
        DefinitionTrace,
    )


# The client's own model

TOPICS = Literal[
    "advance_rate", "reserve", "past_due_exclusion", "status_exclusion",
    "concentration_denominator",
    "dealer_grouping", "fico_bucket", "missing_fico", "excess_order", "limit_state",
    "limit_dealer", "limit_term", "limit_used", "limit_fico", "report_due",
    "report_percent_format", "report_negative_format", "report_nil_format", "report_fico_bands",
    "report_delinquency", "other",
]
BASES = Literal[
    "eligible_pool", "total_pool", "dealer_code", "common_ownership", "schedule_order",
    "charged_off_and_repossessed", "sub_600_bucket", "decimal", "negative_number", "dash",
    "agreement_definition", "none",
]


class Treatment(BaseModel):
    topic: TOPICS
    cell: str
    quote: str
    operator: Literal["<", "<=", ">", ">=", "none"]
    number: float | None
    basis: BASES
    reading: str


class ClientModelReading(BaseModel):
    template_version: str
    treatments: list[Treatment]


def read_client_model(gateway: Gateway, workbook: str) -> ClientModelReading:
    return gateway.parse(
        "read_client_model", GROUND_RULES,
        [{"type": "text", "text": (
            "This is the lender's own borrowing base model and reporting template, with each "
            "cell's address in brackets. Record how it treats each point, one treatment per "
            "parameter, limit or reporting requirement. `cell` is the address of the cell that "
            "holds the value, and `quote` that cell's text copied exactly. `number` is the "
            "figure the cell sets, with a share written as a percentage (0.2 becomes 20), or "
            "null. `operator` is the comparison the cell applies to that figure: for a past-due "
            "or score band, the test a receivable must meet to be excluded or put in the band. "
            "`basis` is the treatment where it is not a number, such as what a concentration "
            "share is measured against, or how dealers are grouped, or none. `reading` is one "
            "short, plain sentence in UK spelling.\n\n" + workbook)}],
        ClientModelReading, max_tokens=12000,
    )


class QueryDraft(BaseModel):
    topic: str
    subject: str
    text: str


class QueryDrafts(BaseModel):
    queries: list[QueryDraft]


QUERY_GUIDE = (
    "Draft one query to the lender for each difference below between its own borrowing base "
    "model and the facility agreement, as the verification agent's onboarding analyst. Each is "
    "two or three plain sentences in UK spelling: what the model does, what the agreement says, "
    "the effect on this month's figures, and the one question the lender must answer. Never "
    "write a number, date, percentage, clause or cell reference yourself: write the "
    "placeholder exactly as listed for that difference, such as {{model_value}}, and code "
    "will insert the checked value. Where the agreement is silent, say so and ask how the "
    "lender wants it treated. `subject` is a short line with no placeholders. Do not say "
    "the model is wrong; say which reading governs the borrowing base and ask the lender to "
    "confirm. Never mention placeholders or this brief."
)


def draft_client_queries(gateway: Gateway, differences: list[dict[str, Any]]) -> QueryDrafts:
    return gateway.parse(
        "draft_client_queries", GROUND_RULES,
        [{"type": "text", "text": QUERY_GUIDE + "\n\nDifferences:\n"
          + json.dumps(differences, indent=1)}],
        QueryDrafts, max_tokens=8000,
    )


# Backbook


class BackbookSuggestion(BaseModel):
    deal: str
    column: str
    kind: Literal["renamed_column", "new_column", "blank_values", "code_values"]
    field: str | None
    treat_blank_as: str | None
    code_map: list[list[str]]
    reason: str


class BackbookSuggestions(BaseModel):
    suggestions: list[BackbookSuggestion]


def suggest_backbook(gateway: Gateway, differences: list[dict[str, Any]],
                     stored: dict[str, str]) -> BackbookSuggestions:
    fields = "\n".join(f"- {name}: {text}" for name, text in PLATFORM_FIELDS.items())
    return gateway.parse(
        "suggest_backbook", GROUND_RULES,
        [{"type": "text", "text": (
            "These existing deals' tapes come from the same servicing system as a deal whose "
            "mapping is stored, and were loaded with that mapping. Below is every place where a "
            "tape did not fit it. For each, suggest what to do. A renamed_column names the "
            "platform `field` the column holds. A new_column names a platform `field` only if "
            "one below holds exactly that data, and otherwise leaves `field` null so the column "
            "is kept as raw data. For blank_values, say what a blank means in `treat_blank_as` "
            "(a single value, or null to leave the rows out). For code_values, `code_map` pairs "
            "each tape code with a stored value, as [code, value]. `reason` is one short, plain "
            "sentence in UK spelling.\n\nPlatform fields:\n" + fields
            + "\n\nStored mapping (tape column: field):\n" + json.dumps(stored, indent=0)
            + "\n\nDifferences:\n" + json.dumps(differences, indent=1))}],
        BackbookSuggestions, max_tokens=8000,
    )
