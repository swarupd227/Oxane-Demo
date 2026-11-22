"""The agreement against the client's own model.

The model reads Calderwood's workbook into treatments, one per cell. Code checks each quote is
the cell's text, sets each treatment against the validated configuration (the rules engine's
rule set and the approved terms, each with its source), and works out what every difference
would do to the April borrowing base by running the engine both ways.
"""

from decimal import Decimal
from pathlib import Path
from typing import Any

from engine.rules import AdvanceRate, Compare, Const, RuleSet
from engine.run import Loan, RunResult, run
from openpyxl import load_workbook

from app.casework.steps import Treatment
from app.pipeline.documents import PdfDocument, find_citation

PERIOD_LABEL = "April 2026"
COMPARED = ("advance_rate", "reserve", "past_due_exclusion", "status_exclusion",
            "concentration_denominator", "dealer_grouping", "fico_bucket", "missing_fico",
            "excess_order", "limit_state", "limit_dealer", "limit_term", "limit_used",
            "limit_fico")
TOPIC_LABELS = {
    "advance_rate": "Advance rate", "reserve": "Reserve",
    "past_due_exclusion": "Past-due exclusion",
    "status_exclusion": "Status exclusion", "concentration_denominator": "Concentration basis",
    "dealer_grouping": "Dealer grouping", "fico_bucket": "Sub-600 FICO bucket",
    "missing_fico": "Obligors with no score", "excess_order": "Order of excess",
    "limit_state": "Single-state limit", "limit_dealer": "Single-dealer limit",
    "limit_term": "Long-term limit", "limit_used": "Used-vehicle limit",
    "limit_fico": "Sub-600 FICO limit", "report_due": "Report deadline",
    "report_percent_format": "Percentages", "report_negative_format": "Deductions",
    "report_nil_format": "Nil values", "report_fico_bands": "FICO stratification",
    "report_delinquency": "Delinquency ratio",
}


def cells_of(path: Path) -> dict[str, Any]:
    book = load_workbook(path, data_only=True)
    return {f"{sheet.title}!{cell.coordinate}": cell.value
            for sheet in book.worksheets for row in sheet.iter_rows() for cell in row
            if cell.value is not None}


def workbook_text(cells: dict[str, Any]) -> str:
    return "\n".join(f"[{address}] {value}" for address, value in cells.items())


def _same_text(quote: str, value: Any) -> bool:
    def clean(text: str) -> str:
        return " ".join(str(text).split()).lower()

    if isinstance(value, float | int):
        try:
            return Decimal(quote.strip().rstrip("%")) in (Decimal(str(value)),
                                                          Decimal(str(value)) * 100)
        except ArithmeticError:
            return False
    return clean(quote) == clean(value)


def verify(treatment: Treatment, cells: dict[str, Any]) -> str | None:
    """Why a treatment cannot be used, or None if its cell and figure check out."""
    if treatment.cell not in cells:
        return f"{treatment.cell} is not a cell in the workbook"
    value = cells[treatment.cell]
    if not _same_text(treatment.quote, value):
        return f"The quote is not the text of {treatment.cell}"
    if treatment.number is not None and isinstance(value, float | int):
        if Decimal(str(treatment.number)) not in (Decimal(str(value)), Decimal(str(value)) * 100):
            return f"{treatment.number} is not the figure in {treatment.cell}"
    return None


def _limit(ruleset: RuleSet, topic: str) -> tuple[Decimal, str, str] | None:
    wanted = {"limit_state": "obligor_state", "limit_dealer": "dealer_name",
              "limit_term": "original_term", "limit_used": "vehicle_condition",
              "limit_fico": "fico"}[topic]
    for rule in ruleset.concentration:
        test = rule.group_by.name if rule.group_by else (
            rule.where.model_dump_json() if rule.where else "")
        if f'"{wanted}"' in test or test == wanted:
            return rule.limit_pct, rule.clause_ref, rule.clause_text
    return None


def agreement_position(ruleset: RuleSet, result: RunResult, documents: dict[str, PdfDocument],
                       terms: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """How the validated configuration treats each point, with the source of each."""
    def cite(document: str, quote: str) -> dict[str, Any] | None:
        return find_citation(documents, document, quote)

    rules = {rule.id: rule for rule in ruleset.eligibility}
    e1 = rules["E1"].test
    past_due = int(e1.right.value) if isinstance(e1, Compare) and isinstance(e1.right, Const) \
        else None
    c4 = next(r for r in ruleset.concentration if r.id == fico_rule(ruleset))
    fico_limit = c4.where.right.value if isinstance(c4.where, Compare) and isinstance(
        c4.where.right, Const) else None
    c2 = next(r for r in ruleset.concentration if r.group_by and r.group_by.name == "dealer_name")
    advance = terms["Advance rate"]
    position: dict[str, dict[str, Any]] = {
        "advance_rate": {"operator": "none", "number": result.advance_rate_pct, "basis": "none",
                         "text": f"{result.advance_rate_pct.normalize():f}% from 1 March 2026",
                         "clause": result.advance_rate_source, "source": advance["source"]},
        "reserve": {"operator": "none", "number": ruleset.reserve_pct, "basis": "none",
                    "text": f"{ruleset.reserve_pct.normalize():f}% of the Eligible Pool Balance",
                    "clause": "Section 1.1, Reserve Amount",
                    "source": terms["Reserve amount"]["source"]},
        "past_due_exclusion": {"operator": ">", "number": Decimal(past_due), "basis": "none",
                               "text": f"excluded when more than {past_due} days past due",
                               "clause": rules["E1"].clause_ref,
                               "source": cite("credit_agreement", rules["E1"].clause_text)},
        "status_exclusion": {"operator": "none", "number": None,
                             "basis": "charged_off_and_repossessed",
                             "text": "charged-off and repossessed receivables excluded",
                             "clause": rules["E2"].clause_ref,
                             "source": cite("credit_agreement", rules["E2"].clause_text)},
        "concentration_denominator": {
            "operator": "none", "number": None, "basis": "eligible_pool",
            "text": "the Eligible Pool Balance before any excess is deducted",
            "clause": "Section 1.1, Eligible Pool Balance",
            "source": cite("credit_agreement", "measured against the Eligible Pool Balance "
                           "before any deduction of the Excess Concentration Amount")},
        "dealer_grouping": {"operator": "none", "number": None, "basis": "common_ownership",
                            "text": "dealers under common ownership or trading under variations "
                                    "of one name counted as one dealer",
                            "clause": c2.clause_ref,
                            "source": cite("credit_agreement", "treating Dealers under common "
                                           "ownership or trading under variations of one name "
                                           "as one Dealer")},
        "fico_bucket": {"operator": "<", "number": fico_limit, "basis": "none",
                        "text": f"a FICO score below {fico_limit}",
                        "clause": c4.clause_ref,
                        "source": cite("amendment_1", "origination below 600")},
        "missing_fico": {"operator": "none", "number": None, "basis": "none", "silent": True,
                         "text": "not addressed", "clause": "Schedule 1 and Schedule 2",
                         "source": None},
        "excess_order": {"operator": "none", "number": None, "basis": "schedule_order",
                         "text": "limits applied in schedule order, each amount counted once",
                         "clause": "Section 1.1, Excess Concentration Amount",
                         "source": cite("credit_agreement", "The limits are applied in the order "
                                        "listed in Schedule 2")},
    }
    for topic in ("limit_state", "limit_dealer", "limit_term", "limit_used", "limit_fico"):
        found = _limit(ruleset, topic)
        if found:
            pct, clause, text = found
            position[topic] = {"operator": "none", "number": pct, "basis": "none",
                               "text": f"{pct.normalize():f}%", "clause": clause,
                               "source": cite("amendment_1" if topic == "limit_fico"
                                              else "credit_agreement",
                                              text if topic != "limit_fico" else
                                              "origination below 600")}
    return position


def _differs(treatment: Treatment, agreed: dict[str, Any]) -> bool:
    if agreed.get("silent"):
        return treatment.basis != "none" or treatment.number is not None
    if agreed["number"] is not None and (treatment.number is None or Decimal(
            str(treatment.number)) != Decimal(agreed["number"])):
        return True
    if agreed["operator"] != "none" and treatment.operator != agreed["operator"]:
        return True
    return agreed["basis"] != "none" and treatment.basis != agreed["basis"]


def _variant(topic: str, treatment: Treatment, ruleset: RuleSet, loans: list[Loan],
             as_of: Any, outstanding: int, aliases: dict[str, str]) -> RunResult | None:
    """The April run with the client model's treatment in place of the agreement's."""
    kwargs: dict[str, Any] = {"dealer_aliases": aliases}
    rules = ruleset
    if topic == "advance_rate" and treatment.number is not None:
        rate = AdvanceRate(pct=Decimal(str(treatment.number)),
                           effective_from=min(r.effective_from for r in ruleset.advance_rates),
                           source="Client model")
        rules = ruleset.model_copy(update={"advance_rates": (rate,)})
    elif topic == "past_due_exclusion" and treatment.number is not None:
        limit = Decimal(str(treatment.number))
        rules = ruleset.with_threshold("E1", limit - 1 if treatment.operator == ">=" else limit)
    elif topic == "concentration_denominator" and treatment.basis == "total_pool":
        kwargs["concentration_base"] = "gross"
    elif topic == "dealer_grouping" and treatment.basis == "dealer_code":
        kwargs["dealer_aliases"] = {}
    elif topic == "fico_bucket" and treatment.number is not None and treatment.operator in (
            "<", "<="):
        def band(rule: Any) -> Any:
            if rule.where is None or "fico" not in rule.where.model_dump_json():
                return rule
            where = rule.where.model_copy(update={
                "op": treatment.operator, "right": Const(value=Decimal(str(treatment.number)))})
            return rule.model_copy(update={"where": where})
        rules = ruleset.model_copy(update={"concentration": tuple(map(band,
                                                                         ruleset.concentration))})
    else:
        return None
    return run(loans, rules, as_of, outstanding, **kwargs)


def fico_rule(ruleset: RuleSet) -> str:
    return next(rule.id for rule in ruleset.concentration
                if rule.where is not None and '"fico"' in rule.where.model_dump_json())


def _bucket(result: RunResult, rule_id: str) -> int:
    item = result.concentrations.get(rule_id)
    return item.largest_cents if item else 0


def _usd(cents: int) -> str:
    sign = "-" if cents < 0 else ""
    return f"{sign}US${abs(cents) / 100:,.2f}"


def _describe_treatment(t: Treatment) -> str:
    if t.topic == "advance_rate" and t.number is not None:
        return f"{Decimal(str(t.number)).normalize():f}% throughout"
    if t.topic == "past_due_exclusion" and t.number is not None:
        words = {">=": "or more", ">": "more than"}
        n = int(t.number)
        return (f"excluded at {n} or more days past due" if t.operator == ">="
                else f"excluded when {words.get(t.operator, '')} {n} days past due")
    if t.topic == "fico_bucket" and t.number is not None:
        return (f"a FICO score of {int(t.number)} and below" if t.operator == "<="
                else f"a FICO score below {int(t.number)}")
    worded = {
        ("concentration_denominator", "total_pool"): "the total pool balance, every receivable "
                                                     "on the tape",
        ("dealer_grouping", "dealer_code"): "each servicer dealer code as a separate dealer",
        ("missing_fico", "sub_600_bucket"): "placing them in the sub-600 bucket",
    }
    return worded.get((t.topic, t.basis), t.quote)


def compare(reading: list[Treatment], cells: dict[str, Any], position: dict[str, dict[str, Any]],
            base: RunResult, ruleset: RuleSet, loans: list[Loan], aliases: dict[str, str],
            outstanding: int) -> dict[str, Any]:
    rows, differences, rejected = [], [], []
    fico_id = fico_rule(ruleset)
    for treatment in reading:
        problem = verify(treatment, cells)
        if problem:
            rejected.append({"cell": treatment.cell, "topic": treatment.topic, "reason": problem})
            continue
        agreed = position.get(treatment.topic) if treatment.topic in COMPARED else None
        row = {"topic": treatment.topic, "label": TOPIC_LABELS.get(treatment.topic,
                                                                    treatment.topic),
               "cell": treatment.cell, "quote": treatment.quote, "reading": treatment.reading,
               "agreement": agreed["text"] if agreed else None,
               "clause": agreed["clause"] if agreed else None,
               "source": agreed["source"] if agreed else None,
               "kind": "reporting" if treatment.topic.startswith("report_") else "parameter"}
        if agreed is None:
            row["status"] = "adopted" if row["kind"] == "reporting" else "not_compared"
        elif not _differs(treatment, agreed):
            row["status"] = "agrees"
        else:
            row["status"] = "silent" if agreed.get("silent") else "differs"
            variant = _variant(treatment.topic, treatment, ruleset, loans, base.as_of,
                               outstanding, aliases)
            change = variant.borrowing_base_cents - base.borrowing_base_cents if variant else 0
            moved = (len(set(base.eligible_loan_ids) ^ set(variant.eligible_loan_ids))
                     if variant else 0)
            bucket = _bucket(variant, fico_id) - _bucket(base, fico_id) if variant else 0
            missing = sum(1 for loan in loans if loan.get("fico") in (None, ""))
            if change:
                impact = (f"an {PERIOD_LABEL} borrowing base {_usd(abs(change))} "
                          f"{'higher' if change > 0 else 'lower'} than under the agreement")
            elif bucket:
                impact = (f"no change to the {PERIOD_LABEL} borrowing base, though the sub-600 "
                          f"bucket would hold {_usd(bucket)} more")
            elif treatment.topic == "missing_fico":
                impact = (f"no change for {PERIOD_LABEL}, as every receivable has a score"
                          if not missing else
                          f"{missing} receivables without a score in {PERIOD_LABEL}")
            else:
                impact = (f"no change for {PERIOD_LABEL}, as no receivable sits on the "
                          "boundary")
            row.update({
                "borrowing_base_change": change / 100, "loans_moved": moved,
                "bucket_change": bucket / 100,
                "availability_with_model": (variant.availability_cents / 100 if variant
                                            else base.availability_cents / 100),
                "impact": impact,
            })
            differences.append({
                "topic": treatment.topic,
                "placeholders": {
                    "model_value": {"value": _describe_treatment(treatment),
                                    "means": "how the lender's model treats it"},
                    "agreement_value": {"value": agreed["text"],
                                        "means": "how the facility agreement treats it"},
                    "clause": {"value": agreed["clause"], "means": "where the agreement says so"},
                    "cell": {"value": treatment.cell, "means": "the cell in the lender's model"},
                    "impact": {"value": impact, "means": "what the difference does this month"},
                },
                "silent": bool(agreed.get("silent")),
            })
        rows.append(row)
    return {"rows": rows, "differences": differences, "rejected": rejected}
