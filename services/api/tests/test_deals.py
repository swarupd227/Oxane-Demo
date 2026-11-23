"""New deals, created to monitored, on the generated test deals.

Model calls go to the deterministic test double (app.deals.stub), so these run offline; the
pipeline's code checks, engine runs, controls and hand-offs are the real ones.
"""

import json
from datetime import UTC, datetime
from decimal import Decimal

import deals_flow as flow
import pytest
from deals_flow import client, h, ok
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.config import settings
from app.db import engine
from app.deals import stub
from app.deals.models import LlmSpend, WorkItem
from app.session import chain_intact

HARBOURLINE = ["Harbourline_Loan_and_Security_Agreement.pdf", "Harbourline_First_Amendment.pdf",
               "Harbourline_Loan_Tape_2026-09.csv", "Ashgrove_Harbourline_BB_Model_v1.xlsx",
               "Harbourline_Servicer_Report_September_2026.pdf"]


@pytest.fixture(autouse=True)
def deals_settings(monkeypatch: pytest.MonkeyPatch, tmp_path):
    monkeypatch.setattr(settings, "deals_stub_model", True)
    monkeypatch.setattr(settings, "demo_access_code", flow.CODE)
    monkeypatch.setattr(settings, "deals_llm_fixtures", tmp_path / "llm-deals")
    yield


@pytest.fixture(scope="module", autouse=True)
def tidy():
    """Leave the shared database as it was found."""
    yield
    flow.cleanup(flow.CREATED)


def key(deal: str) -> dict:
    return json.loads((flow.deal_dir(deal) / "key.json").read_text(encoding="utf-8"))


def _items(persona: str) -> list[dict]:
    return ok(client.get("/api/work", headers=h(persona)))["waiting"]


@pytest.fixture(scope="module")
def consumer():
    """Ashgrove (AI permitted, two levels) onboards Harbourline and runs its first month."""
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(settings, "deals_stub_model", True)
        patch.setattr(settings, "demo_access_code", flow.CODE)
        row = flow.new_client("Ashgrove Capital Partners LP", "Nadia Brooks", True)
        case = flow.onboard_ai("harbourline", row, "Harbourline Consumer Receivables LLC",
                               "Consumer instalment", 150_000_000, HARBOURLINE)
        yield {"client": row, "case": case}


def test_terms_are_read_with_quotes_and_the_amendment_applied(consumer):
    terms = consumer["case"]["state"]["terms"]
    assert terms["commitment"]["typed"] == 150_000_000
    rate = terms["advance_rate"]
    assert rate["typed"] == "86.00" and rate["effective_from"] == "2026-09-01"
    assert rate["original"]["typed"] == "88.00" and rate["original"]["verified"]
    assert rate["page"] and rate["doc_name"] == "Harbourline_First_Amendment.pdf"
    assert terms["reserve"]["typed"] == "1.50"
    assert terms["delinquency_trigger"]["basis_days"] == 60
    assert all(t["status"] in ("approved", "absent") for t in terms.values())


def test_engine_on_the_uploaded_tape_matches_the_independent_key(consumer):
    engine_view = consumer["case"]["state"]["validation"]["engine"]
    expected = key("harbourline")["onboarding"]
    assert engine_view["eligible_loans"] == expected["eligible_loans"]
    assert engine_view["eligible_pool_cents"] == round(expected["eligible_pool"] * 100)
    assert engine_view["gross_pool_cents"] == round(expected["gross_pool"] * 100)
    assert engine_view["advance_rate_pct"] == "86.00"


def test_rules_carry_their_clause_and_page(consumer):
    rules = consumer["case"]["state"]["rules"]
    assert len(rules["eligibility"]) == key("harbourline")["rules"]["eligibility"]
    assert len(rules["concentration"]) == key("harbourline")["rules"]["concentration"]
    added = next(r for r in rules["concentration"] if r["effective_from"])
    assert added["effective_from"] == "2026-09-01" and added["page"]
    assert all(r["verified"] and r["page"] for r in rules["eligibility"])


def test_the_client_model_difference_is_an_exception(consumer):
    titles = [e["title"] for e in consumer["case"]["state"]["exceptions"]]
    assert any("Client model advance rate 88.00 against 86.00" in t for t in titles)


def test_query_goes_to_the_client_and_back(consumer):
    case = flow.work_open(consumer["case"])
    item = next(e for e in case["state"]["exceptions"] if e["status"] == "with_client")
    contact = f"client-{consumer['client']['id']}"
    waiting = _items(contact)
    assert any(item["title"] in w["title"] for w in waiting)
    portal = ok(client.get("/api/portal", headers=h(contact)))
    assert any(q["ref"] == item["ref"] and q["status"] == "waiting" for q in portal["queries"])
    assert "cost" not in json.dumps(portal)
    ok(client.post(f"/api/deals/queries/{case['id']}/{item['ref']}/answer",
                   headers=h(contact), json={"text": "We will update our model"}))
    assert any("Client answered" in w["title"] for w in _items("hannah"))
    consumer["case"] = case


def test_four_eyes_qc_approval_and_go_live(consumer):
    cid = consumer["case"]["id"]
    case = ok(client.get(f"/api/deals/cases/{cid}", headers=h("hannah")))
    for item in case["state"]["exceptions"]:
        if item["status"] in ("answered", "decided"):
            case = flow.step(cid, f"exceptions/{item['ref']}", {"action": "close"})
    case = flow.step(cid, "submit-qc")
    assert any(w["title"].startswith("Independent QC") for w in _items("tom"))
    blocked = client.post(f"/api/deals/cases/{cid}/qc", headers=h("hannah"),
                          json={"item": "term:commitment", "result": "agrees"})
    assert blocked.status_code == 403
    for item in case["qc_items"]:
        case = flow.step(cid, "qc", {"item": item["id"], "result": "agrees"}, persona="tom")
    assert any(i["id"] == "calc:eligible" and i["computed"] == "agrees" for i in case["qc_items"])
    case = flow.step(cid, "qc/complete", persona="tom")
    assert case["stage"] == "review"
    assert client.post(f"/api/deals/cases/{cid}/approve", headers=h("hannah"),
                       json={}).status_code == 403
    case = flow.step(cid, "approve", {"reason": None}, persona="marcus")
    load = client.get(f"/api/deals/cases/{cid}/load-file.json", headers=h("marcus"))
    assert load.status_code == 200 and load.json()["status"] == "final"
    workbook = client.get(f"/api/deals/cases/{cid}/configuration.xlsx", headers=h("marcus"))
    assert workbook.status_code == 200 and "final" in workbook.headers["content-disposition"]
    case = flow.step(cid, "go-live", persona="marcus")
    assert case["stage"] == "live" and case["facility_id"]
    facility = ok(client.get(f"/api/deals/facilities/{case['facility_id']}", headers=h("priya")))
    assert [s["period"] for s in facility["submissions"]] == ["2026-10", "2026-11", "2026-12"]
    assert facility["submissions"][0]["due_date"] == "2026-11-15"
    assert any(facility["name"] in w["title"] for w in _items("priya"))
    assert case["history"]["chain_intact"]
    actors = {e["actor"] for e in case["history"]["entries"]}
    assert {"Hannah Cole", "Tom Fairley", "Marcus Hale"} <= actors
    consumer["facility_id"] = case["facility_id"]


def test_first_month_reuses_the_mapping_holds_the_duplicate_and_reconciles(consumer):
    sub = flow.first_month(consumer["facility_id"], "harbourline",
                           "Harbourline_Loan_Tape_2026-10.csv",
                           "Harbourline_Servicer_Report_October_2026.pdf")
    assert sub["state"]["mapping"]["source"] == "facility"
    assert sub["state"]["validation"]["held"] is True
    later = key("harbourline")["later"]
    dup = next(f for f in sub["state"]["findings"] if f["severity"] == "blocking")
    assert later["duplicate"] in dup["detail"]
    assert client.post(f"/api/deals/submissions/{sub['id']}/report/draft",
                       headers=h("priya", True)).status_code == 422
    sub = flow.triage_all(sub)
    state = sub["state"]
    assert not state["validation"]["held"]
    roll = state["reconciliation"]["roll_forward"]
    assert later["dropped"] in roll["missing_loan_ids"]
    assert roll["collections_cents"] == round(Decimal(str(later["principal_collections"])) * 100)
    assert state["tests"]["delinquency_window"] == 2
    figures = state["report_figures"]
    assert figures["principal_collections"]["verified"] and figures["charge_offs"]["page"] == 1
    consumer["sub_id"] = sub["id"]


def test_report_released_after_the_client_s_levels(consumer):
    sid = consumer["sub_id"]
    sub = flow.sub_step(sid, "report/draft", code=True)
    text = " ".join(sub["state"]["report"]["text"])
    assert "{{" not in text and "US$" in text
    sub = flow.sub_step(sid, "approve", persona="priya")
    assert client.post(f"/api/deals/submissions/{sid}/approve",
                       headers=h("priya")).status_code in (403, 409)
    assert any("level 2" in w["title"] for w in _items("marcus"))
    sub = flow.sub_step(sid, "approve", persona="marcus")
    assert sub["status"] == "released"
    contact = f"client-{consumer['client']['id']}"
    portal = ok(client.get("/api/portal", headers=h(contact)))
    assert portal["reports"] and portal["reports"][0]["period"] == "2026-10"
    report = client.get(f"/api/deals/submissions/{sid}/report.xlsx", headers=h(contact))
    assert report.status_code == 200
    assert client.get(f"/api/deals/cases/{consumer['case']['id']}",
                      headers=h(contact)).status_code == 403
    facilities = ok(client.get("/api/deals/facilities", headers=h("elena")))
    assert any(f["id"] == consumer["facility_id"] and f["latest"]["status"] == "released"
               for f in facilities)


def test_sme_layout_change_is_mapped_and_stored_per_client():
    row = flow.new_client("Marlow Bank plc", "Owen Price", True, 3)
    case = flow.onboard_ai("fenwick", row, "Fenwick SME Funding LLC", "SME loans", 80_000_000,
                           ["Fenwick_Receivables_Financing_Agreement.pdf",
                            "Fenwick_Portfolio_2026-09.xlsx"])
    terms = case["state"]["terms"]
    assert terms["reserve"]["status"] == "absent" and terms["reserve"]["typed"] is None
    missing = next(e for e in case["state"]["exceptions"] if e["key"] == "term:missing:reserve")
    assert missing["severity"] == "blocking"
    engine_view = case["state"]["validation"]["engine"]
    assert engine_view["reserve_cents"] == 0
    assert engine_view["eligible_pool_cents"] == round(key("fenwick")["onboarding"]
                                                       ["eligible_pool"] * 100)
    case = flow.finish_onboarding(case, f"client-{row['id']}")
    sub = flow.first_month(case["facility_id"], "fenwick", "Fenwick_Portfolio_2026-10.xlsx",
                           "Fenwick_Monthly_Report_October_2026.pdf")
    mapping = sub["state"]["mapping"]
    assert mapping["source"] == "ai" and set(mapping["changed_columns"]) == {
        "Arrears Days", "Days in Arrears", "Collateral Type"}
    assert mapping["columns"]["Days in Arrears"] == "days_past_due"
    detail = ok(client.get(f"/api/deals/clients/{row['id']}", headers=h("alex")))
    assert len(detail["mappings"]) == 2
    other = ok(client.get("/api/deals/clients", headers=h("alex")))
    assert all(len(c["name"]) for c in other)


def test_no_ai_client_runs_manually_with_page_references():
    row = flow.new_client("Kingsgate Bank N.A.", "Rosa Lind", False)
    case = flow.new_case(row["id"], "Fenwick SME Funding II", "SME loans", 80_000_000)
    cid = case["id"]
    refused = client.post(f"/api/deals/cases/{cid}/documents",
                          params={"name": "x.pdf", "kind": "auto"},
                          content=b"%PDF-1.4", headers=h("hannah", True))
    assert refused.status_code == 422 and "kind" in refused.json()["detail"]["fields"]
    folder = flow.deal_dir("fenwick") / "onboarding"
    flow.upload(cid, folder / "Fenwick_Receivables_Financing_Agreement.pdf", "agreement")
    flow.upload(cid, folder / "Fenwick_Portfolio_2026-09.xlsx", "loan_tape")
    assert client.post(f"/api/deals/cases/{cid}/extract",
                       headers=h("hannah", True)).status_code == 409
    flow.step(cid, "terms/manual")
    doc = "Fenwick_Receivables_Financing_Agreement.pdf"
    wrong = client.post(f"/api/deals/cases/{cid}/terms/commitment", headers=h("hannah"),
                        json={"action": "enter", "value": "US$80,000,000", "document": doc,
                              "page": 1})
    assert wrong.status_code == 422 and "value" in wrong.json()["detail"]["fields"]
    entries = {"commitment": ("US$80,000,000", 2), "advance_rate": ("70.00%", 2),
               "delinquency_trigger": ("7.50%", 3)}
    for term, (value, page) in entries.items():
        case = flow.step(cid, f"terms/{term}", {"action": "enter", "value": value,
                                                "document": doc, "page": page,
                                                "basis_days": 30, "window_months": 3})
    for term in ("reserve", "loss_trigger"):
        case = flow.step(cid, f"terms/{term}", {"action": "absent", "reason": "Not in the "
                                                "agreement; checked every section"})
    bad = client.post(f"/api/deals/cases/{cid}/rules", headers=h("hannah"), json={
        "action": "add", "kind": "eligibility", "rule": {
            "ref": "First Schedule (a)", "plain_english": "Not more than 30 days in arrears",
            "clause_text": "the loan is not more than 45 days in arrears;", "document": doc,
            "test": {"kind": "max", "field": "days_past_due", "high": 45}}})
    assert bad.status_code == 422
    case = flow.step(cid, "rules", {"action": "add", "kind": "eligibility", "rule": {
        "ref": "First Schedule (a)", "plain_english": "Not more than 30 days in arrears",
        "clause_text": "the loan is not more than 30 days in arrears;", "document": doc,
        "test": {"kind": "max", "field": "days_past_due", "high": 30}}})
    case = flow.step(cid, "rules", {"action": "add", "kind": "concentration", "rule": {
        "ref": "Second Schedule, 3", "plain_english": "Any one region",
        "clause_text": "Loans to borrowers in any one region: 30.00% of the aggregate principal "
                       "of Qualifying Loans.", "document": doc, "limit_pct": 30.0,
        "group_by": "region"}})
    case = flow.step(cid, "rules", {"action": "approve"})
    case = flow.step(cid, "mapping/suggest", code=True)
    assert case["state"]["mapping"]["source"] == "rules"
    case = flow.step(cid, "mapping", {})
    case = flow.step(cid, "validate", {"as_of": "2026-09-30"})
    assert case["state"]["validation"]["engine"]["advance_rate_pct"] == "70.00"
    assert case["cost"]["calls"] == 0
    with Session(engine) as db:
        assert db.scalars(select(LlmSpend).where(LlmSpend.case_id == cid)).first() is None


def test_overlapping_changes_to_one_case_both_survive(monkeypatch):
    """A case's state is saved whole, so a step that read it before another step's save would
    wipe that save. On the hosted app the rule approval took 1.4 s and the next step began
    inside it, and the approval was lost; each change to a case now waits for the last."""
    import time
    from concurrent.futures import ThreadPoolExecutor

    from app.deals import onboard

    row = flow.new_client("Kingsgate Bank N.A.", "Rosa Lind", False)
    case = flow.new_case(row["id"], "Fenwick SME Funding III", "SME loans", 80_000_000)
    cid = case["id"]
    folder = flow.deal_dir("fenwick") / "onboarding"
    flow.upload(cid, folder / "Fenwick_Receivables_Financing_Agreement.pdf", "agreement")
    flow.upload(cid, folder / "Fenwick_Portfolio_2026-09.xlsx", "loan_tape")
    flow.step(cid, "terms/manual")
    doc = "Fenwick_Receivables_Financing_Agreement.pdf"
    for term, (value, page) in {"commitment": ("US$80,000,000", 2), "advance_rate": ("70.00%", 2),
                                "delinquency_trigger": ("7.50%", 3)}.items():
        flow.step(cid, f"terms/{term}", {"action": "enter", "value": value, "document": doc,
                                         "page": page, "basis_days": 30, "window_months": 3})
    for term in ("reserve", "loss_trigger"):
        flow.step(cid, f"terms/{term}", {"action": "absent", "reason": "Not in the agreement"})
    flow.step(cid, "rules", {"action": "add", "kind": "eligibility", "rule": {
        "ref": "First Schedule (a)", "plain_english": "Not more than 30 days in arrears",
        "clause_text": "the loan is not more than 30 days in arrears;", "document": doc,
        "test": {"kind": "max", "field": "days_past_due", "high": 30}}})

    real = onboard.suggest_mapping

    def slow(*args, **kwargs):
        result = real(*args, **kwargs)
        time.sleep(1.5)
        return result

    monkeypatch.setattr(onboard, "suggest_mapping", slow)
    with ThreadPoolExecutor(2) as pool:
        mapping = pool.submit(client.post, f"/api/deals/cases/{cid}/mapping/suggest",
                              headers=h("hannah", True))
        time.sleep(0.5)
        approval = pool.submit(client.post, f"/api/deals/cases/{cid}/rules",
                               headers=h("hannah"), json={"action": "approve"})
        assert mapping.result().status_code == 200
        assert approval.result().status_code == 200
    state = ok(client.get(f"/api/deals/cases/{cid}", headers=h("hannah")))["state"]
    assert state["rules"]["status"] == "approved"
    assert state["mapping"]["source"] == "rules"


def test_unfamiliar_documents_degrade_without_inventing_numbers():
    row = flow.new_client("Ashgrove Capital Partners LP", "Nadia Brooks", True)
    case = flow.new_case(row["id"], "Unfamiliar pack", "Auto ABS", 50_000_000)
    pack = settings.deal_kit_output / "pack"
    flow.upload(case["id"], pack / "Bramble_Fee_Letter.pdf", "agreement")
    case = flow.step(case["id"], "extract", code=True)
    terms = case["state"]["terms"]
    assert terms["commitment"]["status"] == "missing" and terms["commitment"]["typed"] is None
    blocking = [e for e in case["state"]["exceptions"] if e["severity"] == "blocking"]
    assert any(e["key"] == "term:missing:advance_rate" for e in blocking)


def test_a_figure_not_in_its_quote_is_flagged(monkeypatch):
    real = stub.extract

    def lying(content):
        answer = real(content)
        for term in answer["terms"]:
            if term["key"] == "reserve":
                term["value"] = "2.50%"
            if term["key"] == "commitment":
                term["quote"] = "The Lender agrees to lend US$150,000,000 forever."
        return answer

    monkeypatch.setitem(stub.ANSWERS, "deals_extract", lying)
    row = flow.new_client("Ashgrove Capital Partners LP", "Nadia Brooks", True)
    case = flow.new_case(row["id"], "Checked pack", "Consumer instalment", 150_000_000)
    folder = flow.deal_dir("harbourline") / "onboarding"
    flow.upload(case["id"], folder / HARBOURLINE[0], "agreement")
    case = flow.step(case["id"], "extract", code=True)
    terms = case["state"]["terms"]
    assert terms["reserve"]["problem"] == "A figure in the value is not in the quote"
    assert terms["commitment"]["problem"] == "Quote not found in the document"
    assert terms["reserve"]["typed"] is None and terms["reserve"]["confidence"] == "low"
    approve = client.post(f"/api/deals/cases/{case['id']}/terms/reserve",
                          headers=h("hannah"), json={"action": "approve"})
    assert approve.status_code == 422


def test_cap_and_upload_limits(monkeypatch):
    row = flow.new_client("Ashgrove Capital Partners LP", "Nadia Brooks", True)
    case = flow.new_case(row["id"], "Limits", "Consumer instalment", 1_000_000)
    url = f"/api/deals/cases/{case['id']}/documents"
    pdf = (flow.deal_dir("harbourline") / "onboarding" / HARBOURLINE[1]).read_bytes()
    assert client.post(url, params={"name": "a.exe"}, content=b"MZ",
                       headers=h("hannah", True)).status_code == 422
    assert client.post(url, params={"name": "a.pdf"}, content=b"not a pdf",
                       headers=h("hannah", True)).status_code == 422
    monkeypatch.setattr(settings, "max_upload_mb", 0)
    assert client.post(url, params={"name": "a.pdf"}, content=pdf,
                       headers=h("hannah", True)).status_code == 413
    monkeypatch.setattr(settings, "max_upload_mb", 20)
    flow.upload(case["id"], flow.deal_dir("harbourline") / "onboarding" / HARBOURLINE[0],
                "agreement")
    # Live path with today's spend at the cap: refused before any call is made.
    monkeypatch.setattr(settings, "deals_stub_model", False)
    monkeypatch.setattr(settings, "anthropic_api_key", "not-a-real-key")
    with Session(engine) as db:
        spend = LlmSpend(day=datetime.now(UTC).date(), task="cap-test", model="test",
                         input_tokens=0, output_tokens=0, cost_usd=Decimal("1000"),
                         replay=False, seconds=Decimal(0))
        db.add(spend)
        db.commit()
        spend_id = spend.id
    try:
        refused = client.post(f"/api/deals/cases/{case['id']}/extract",
                              headers=h("hannah", True))
        assert refused.status_code == 429
        status = ok(client.get("/api/deals/status"))
        assert status["cap_reached"] is True
    finally:
        with Session(engine) as db:
            db.execute(delete(LlmSpend).where(LlmSpend.id == spend_id))
            db.commit()


def test_roles_are_enforced_by_the_api():
    assert client.post("/api/deals/clients", headers=h("hannah"),
                       json={"name": "X"}).status_code == 403
    assert client.post("/api/deals/clients", json={"name": "X"}).status_code == 403
    invalid = client.post("/api/deals/clients", headers=h("alex"),
                          json={"name": "", "approval_levels": 5})
    assert invalid.status_code == 422
    assert set(invalid.json()["detail"]["fields"]) == {"name", "approval_levels"}
    assert client.get("/api/workbench", headers=h("james")).status_code == 403
    assert client.get("/api/monitoring/cycle", headers=h("james")).status_code == 403
    assert client.get("/api/portal", headers=h("james")).status_code == 200
    assert client.post("/api/session/events", headers=h("marcus"),
                       json={"type": "intake-done", "actor": "analyst"}).status_code == 403
    personas = ok(client.get("/api/personas"))["personas"]
    assert {p["role"] for p in personas} >= {"onboarding_analyst", "expert", "qc", "reviewer",
                                            "monitoring_analyst", "head", "client", "admin"}


def test_scripted_escalation_hands_off_to_the_expert_and_back():
    client.post("/api/session/reset", headers=h("hannah"))
    ok(client.post("/api/session/events", headers=h("hannah"),
                   json={"type": "intake-done", "actor": "analyst"}))
    workbench = ok(client.get("/api/workbench"))
    ident = workbench["exceptions"][0]["id"]
    ok(client.post("/api/session/events", headers=h("hannah"), json={
        "type": "work-exception", "actor": "analyst",
        "payload": {"id": ident, "outcome": "escalated", "note": "Needs a credit view"}}))
    item = next(w for w in _items("ruth") if ident in w["title"])
    assert item["from_name"] == "Hannah Cole"
    no_note = client.post(f"/api/work/{item['id']}/complete", headers=h("ruth"), json={})
    assert no_note.status_code == 422
    ok(client.post(f"/api/work/{item['id']}/complete", headers=h("ruth"),
                   json={"note": "Treat as eligible; document the reason"}))
    assert any("Expert decision" in w["title"] for w in _items("hannah"))
    history = ok(client.get("/api/work/scripted-history", params={"scope": "onboarding"}))
    assert history["chain_intact"] and any("Handed to Ruth Adeyemi" in e["action"]
                                           for e in history["entries"])
    session = ok(client.get("/api/session"))
    assert session["preparedBy"] == "Hannah Cole"
    client.post("/api/session/reset", headers=h("hannah"))
    with Session(engine) as db:
        rows = db.scalars(select(WorkItem).where(WorkItem.subject.like("scripted:0412%"),
                                                 WorkItem.status == "open")).all()
        assert all(r.kind in ("notice", "review") for r in rows)


def test_case_crud_validates_inline_and_audits():
    row = flow.new_client("Ashgrove Capital Partners LP", "Nadia Brooks", True)
    bad = client.post("/api/deals/cases", headers=h("hannah"),
                      json={"client_id": row["id"], "facility_name": "", "deal_type": "Nope",
                            "commitment": -1})
    assert bad.status_code == 422
    assert set(bad.json()["detail"]["fields"]) == {"facility_name", "deal_type", "commitment"}
    case = flow.new_case(row["id"], "Edit me", "SME loans", 1_000_000)
    edited = ok(client.patch(f"/api/deals/cases/{case['id']}", headers=h("hannah"),
                             json={"facility_name": "Edited", "commitment": 2_000_000}))
    assert edited["facility_name"] == "Edited" and edited["commitment_cents"] == 200_000_000
    doc = flow.upload(case["id"], flow.deal_dir("fenwick") / "onboarding" /
                      "Fenwick_Portfolio_2026-09.xlsx", "loan_tape")["documents_list"][0]
    again = client.post(f"/api/deals/cases/{case['id']}/documents",
                        params={"name": "copy.xlsx", "kind": "loan_tape"},
                        content=(flow.deal_dir("fenwick") / "onboarding" /
                                 "Fenwick_Portfolio_2026-09.xlsx").read_bytes(),
                        headers=h("hannah", True))
    assert again.status_code == 422
    replaced = ok(client.post(f"/api/deals/cases/{case['id']}/documents/{doc['id']}/replace",
                              params={"name": "Fenwick_Portfolio_2026-10.xlsx"},
                              content=(flow.deal_dir("fenwick") / "monthly" /
                                       "Fenwick_Portfolio_2026-10.xlsx").read_bytes(),
                              headers=h("hannah", True)))
    active = [d for d in replaced["documents_list"] if d["status"] == "active"]
    assert active[0]["version"] == 2
    removed = ok(client.delete(f"/api/deals/cases/{case['id']}/documents/{active[0]['id']}",
                               headers=h("hannah")))
    assert all(d["status"] != "active" for d in removed["documents_list"])
    archived = client.post(f"/api/deals/cases/{case['id']}/archive", headers=h("hannah"),
                           json={"note": "Duplicate case"})
    assert archived.status_code == 200
    with Session(engine) as db:
        from app.deals import audit
        from app.deals.models import DealCase

        events = audit.events(db, db.get(DealCase, case["id"]).audit_id)
        assert chain_intact(events)
        assert [e.type for e in events][:3] == ["create-case", "edit-case", "upload"]
