"""The pitch-brief gaps: the client model Oxane builds where the client has none, reporting
requirements at intake, calculations without a manual trigger, partial reuse by bank and sender,
the Panorama hand-off (a stub) and clients outside the AI scope.

Model calls go to the deterministic test double, so these run offline; code checks, engine
runs, controls, hand-offs and the audit chain are the real ones.
"""

import io

import deals_flow as flow
import pytest
from deals_flow import client, h, ok
from openpyxl import load_workbook
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import panorama
from app.config import settings
from app.db import engine
from app.deals.models import LlmSpend

FENWICK_DOC = "Fenwick_Receivables_Financing_Agreement.pdf"


@pytest.fixture(autouse=True)
def deals_settings(monkeypatch: pytest.MonkeyPatch, tmp_path):
    monkeypatch.setattr(settings, "deals_stub_model", True)
    monkeypatch.setattr(settings, "demo_access_code", flow.CODE)
    monkeypatch.setattr(settings, "deals_llm_fixtures", tmp_path / "llm-deals")
    monkeypatch.setattr(settings, "panorama_base_url", "")
    yield


@pytest.fixture(scope="module", autouse=True)
def tidy():
    yield
    flow.cleanup(flow.CREATED)


@pytest.fixture(scope="module")
def sme():
    """An AI-permitted bank onboards Fenwick, which comes with no client model."""
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(settings, "deals_stub_model", True)
        patch.setattr(settings, "demo_access_code", flow.CODE)
        row = flow.new_client("Marlow Bank plc", "Owen Price", True)
        case = flow.onboard_ai("fenwick", row, "Fenwick SME Funding LLC", "SME loans",
                               80_000_000, [FENWICK_DOC, "Fenwick_Portfolio_2026-09.xlsx"])
        yield {"client": row, "case": case, "contact": f"client-{row['id']}"}


def _case(cid: int, persona: str = "hannah") -> dict:
    return ok(client.get(f"/api/deals/cases/{cid}", headers=h(persona)))


def _book(content: bytes):
    return load_workbook(io.BytesIO(content))


# 2. Reporting requirements, captured at intake


def test_reporting_is_its_own_step_and_feeds_the_configuration_workbook(sme):
    cid = sme["case"]["id"]
    bad = client.post(f"/api/deals/cases/{cid}/reporting", headers=h("hannah"),
                      json={"lines": ["gross_pool", "made_up"], "frequency": "Hourly",
                            "format": "DOC", "day": 40})
    fields = bad.json()["detail"]["fields"]
    assert bad.status_code == 422 and {"lines", "frequency", "format", "day"} <= set(fields)
    assert client.post(f"/api/deals/cases/{cid}/reporting", headers=h("tom"),
                       json={"lines": ["gross_pool"]}).status_code == 403
    case = flow.capture_reporting(cid, day=12, note="Lender wants availability first")
    reporting = case["state"]["reporting"]
    assert reporting["lines"][0] == "gross_pool" and reporting["day"] == 12
    assert reporting["version"] == 2 and case["readiness"]["reporting_captured"]
    assert any(e["type"] == "reporting" for e in case["history"]["entries"])
    book = _book(client.get(f"/api/deals/cases/{cid}/configuration.xlsx",
                            headers=h("hannah")).content)
    rows = [r for r in book["Report"].iter_rows(values_only=True)]
    assert ("Frequency", "Monthly") in [r[:2] for r in rows]
    assert any(r[0] == "Borrowing base" and r[2] == "borrowing_base" for r in rows)
    assert any(r[0] == "Due by day" and r[1] == 12 for r in rows)


# 1. No client model: Oxane builds one and the client validates it


def test_without_a_client_model_qc_waits_for_one(sme):
    case = _case(sme["case"]["id"])
    assert case["setup"]["own_client_model"] is False
    assert case["readiness"]["client_model_agreed"] is False
    refused = client.post(f"/api/deals/cases/{case['id']}/submit-qc", headers=h("hannah"))
    assert refused.status_code == 422 and "client model agreed" in refused.json()["detail"]


def test_oxane_builds_the_model_from_approved_terms_in_code(sme):
    cid = sme["case"]["id"]
    case = flow.step(cid, "client-model/build", code=True)
    built = case["state"]["built_model"]
    assert built["version"] == 1 and built["status"] == "built"
    assert built["notes_by"] == "ai" and "{{" not in " ".join(built["notes"])
    engine_view = case["state"]["validation"]["engine"]
    assert f"US${engine_view['borrowing_base_cents'] / 100:,.2f}" in " ".join(built["notes"])
    doc = next(d for d in case["documents_list"] if d["id"] == built["doc_id"])
    assert doc["kind"] == "client_model" and doc["kind_source"] == "oxane"
    content = client.get(f"/api/deals/documents/{doc['id']}/file", headers=h("hannah")).content
    book = _book(content)
    assert {"Read me", "Inputs", "Eligibility", "Borrowing base", "Report"} <= set(
        book.sheetnames)
    base = {r[0]: r[1] for r in book["Borrowing base"].iter_rows(min_row=2, values_only=True)}
    assert base["Borrowing base"] == "=(B3-B4)*B5/100-B6" and base["Availability"] == \
        "=MIN(B7,B8)"
    assert base["Eligible pool"] == engine_view["eligible_pool_cents"] / 100
    rules = [r[0] for r in book["Eligibility"].iter_rows(min_row=2, values_only=True)]
    assert rules == [r["id"] for r in case["state"]["rules"]["eligibility"]]
    item = next(e for e in case["state"]["exceptions"] if e["key"] == "model:validation:v1")
    assert item["severity"] == "blocking" and item["status"] == "open"
    # Only the client can validate it.
    for action in ("accept", "escalate"):
        refused = client.post(f"/api/deals/cases/{cid}/exceptions/{item['ref']}",
                              headers=h("hannah"), json={"action": action, "note": "fine"})
        assert refused.status_code == 409


def test_the_client_asks_for_changes_then_confirms_v2_and_the_wait_is_tracked(sme):
    cid, contact = sme["case"]["id"], sme["contact"]
    case = _case(cid)
    ref = next(e["ref"] for e in case["state"]["exceptions"]
               if e["key"] == "model:validation:v1")
    case = flow.step(cid, f"exceptions/{ref}", {"action": "query",
                                                "note": "Please validate the model"})
    assert case["state"]["built_model"]["status"] == "with_client"
    assert any(ref in w["title"] or "Query on" in w["title"] for w in
               ok(client.get("/api/work", headers=h(contact)))["waiting"])
    portal = ok(client.get("/api/portal", headers=h(contact)))
    query = next(q for q in portal["queries"] if q["ref"] == ref)
    assert query["model"] and query["status"] == "waiting"
    download = client.get(query["model"], headers=h(contact))
    assert download.status_code == 200 and download.content[:2] == b"PK"
    stranger = flow.new_client("Other Bank plc", "Ann Other", True)
    assert client.get(query["model"], headers=h(f"client-{stranger['id']}")).status_code == 404
    no_outcome = client.post(f"/api/deals/queries/{cid}/{ref}/answer", headers=h(contact),
                             json={"text": "Looks fine"})
    assert no_outcome.status_code == 422
    ok(client.post(f"/api/deals/queries/{cid}/{ref}/answer", headers=h(contact),
                   json={"text": "Our reserve is 2%", "outcome": "changes"}))
    case = _case(cid)
    assert case["state"]["built_model"]["status"] == "changes_requested"
    assert client.post(f"/api/deals/cases/{cid}/exceptions/{ref}", headers=h("hannah"),
                       json={"action": "close"}).status_code == 409
    case = flow.step(cid, "client-model/build", code=True)
    built = case["state"]["built_model"]
    assert built["version"] == 2 and built["history"][0]["validation"]["outcome"] == "changes"
    old = next(e for e in case["state"]["exceptions"] if e["ref"] == ref)
    assert old["status"] == "resolved"
    ref2 = next(e["ref"] for e in case["state"]["exceptions"]
                if e["key"] == "model:validation:v2")
    flow.step(cid, f"exceptions/{ref2}", {"action": "query", "note": "Version 2"})
    ok(client.post(f"/api/deals/queries/{cid}/{ref2}/answer", headers=h(contact),
                   json={"text": "Agreed", "outcome": "confirmed"}))
    case = flow.step(cid, f"exceptions/{ref2}", {"action": "close"})
    assert case["readiness"]["client_model_agreed"]
    tracker = case["setup"]["queries"]
    rows = {r["ref"]: r for r in tracker["queries"]}
    assert rows[ref2]["model_check"] and rows[ref2]["answered_at"]
    assert rows[ref2]["client_wait_hours"] is not None and tracker["client_wait_hours"] >= 0
    kinds = [e["type"] for e in case["history"]["entries"]]
    assert kinds.count("build-client-model") == 2 and "model-validation" in kinds
    assert case["history"]["chain_intact"]


# 5. Panorama: a stub that issues receipts, recorded in the audit chain


def test_the_mock_panorama_checks_shape_and_issues_stable_receipts():
    assert panorama.config()["mode"] == "mock"
    body = {"facility": "FAC-1", "client": "X", "period": "2026-10", "status": "released",
            "results": {"borrowing_base_cents": 1}}
    first = ok(client.post("/api/mock/panorama/monitoring-results", json=body))
    again = ok(client.post("/api/mock/panorama/monitoring-results", json=body))
    assert first["receipt"].startswith("PNR-") and first["receipt"] == again["receipt"]
    assert client.post("/api/mock/panorama/monitoring-results",
                       json={**body, "status": "provisional"}).status_code == 409
    assert client.post("/api/mock/panorama/monitoring-results",
                       json={"facility": "x"}).status_code == 422
    assert client.post("/api/mock/panorama/nothing", json=body).status_code == 404
    cfg = ok(client.get("/api/panorama/config", headers=h("alex")))
    assert cfg["mode"] == "mock" and "Stub" in cfg["note"]


def test_go_live_sends_the_load_file_to_panorama(sme):
    cid = sme["case"]["id"]
    case = flow.finish_onboarding(_case(cid), sme["contact"])
    sent = case["panorama"]
    assert sent["ok"] and sent["receipt"].startswith("PNR-")
    assert sent["request"]["url"] == "/api/mock/panorama/onboarding-load"
    assert sent["request"]["mode"] == "mock" and sent["response"]["status"] == 200
    event = next(e for e in case["history"]["entries"] if e["type"] == "panorama-sent")
    assert sent["receipt"] in event["action"] and event["hash"] == sent["audit_hash"]
    facility = ok(client.get(f"/api/deals/facilities/{case['facility_id']}",
                             headers=h("priya")))
    assert facility["panorama"] == sent["receipt"]
    assert facility["config"]["reporting"]["lines"][0] == "gross_pool"
    assert facility["config"]["client_model"]["status"] == "confirmed"
    assert client.post(f"/api/deals/cases/{cid}/panorama",
                       headers=h("marcus")).status_code == 409
    sme["facility_id"] = case["facility_id"]


# 3. Calculations run without a manual trigger


def test_a_clean_load_runs_the_calculations_by_itself(sme):
    sub = flow.first_month(sme["facility_id"], "fenwick", "Fenwick_Portfolio_2026-10.xlsx",
                           "Fenwick_Monthly_Report_October_2026.pdf")
    state = sub["state"]
    assert state["mapping"]["confirmed"] and state["validation"]["engine"]
    assert not state["validation"]["held"] and state["tests"]["borrowing_base_cents"]
    assert [r["trigger"] for r in state["runs"]] == ["auto"]
    assert state["runs"][0]["by"] == "Workbench (automatic)"
    event = next(e for e in sub["history"]["entries"] if e["type"] == "auto-run")
    assert event["actor"] == "Workbench (automatic)" and "automatically" in event["action"]
    assert not any(e["type"] == "process" for e in sub["history"]["entries"])
    sme["sub"] = sub


def test_released_results_go_to_panorama(sme):
    sub = flow.triage_all(sme["sub"])
    sid = sub["id"]
    flow.sub_step(sid, "report/draft", code=True)
    flow.sub_step(sid, "approve", persona="priya")
    sub = flow.sub_step(sid, "approve", persona="marcus")
    assert sub["status"] == "released"
    sent = sub["state"]["panorama"]
    assert sent["ok"] and sent["request"]["url"].endswith("/monitoring-results")
    assert any(e["type"] == "panorama-sent" for e in sub["history"]["entries"])
    facility = ok(client.get(f"/api/deals/facilities/{sme['facility_id']}", headers=h("priya")))
    row = next(s for s in facility["submissions"] if s["id"] == sid)
    assert row["panorama"] == sent["receipt"]


def test_a_failed_panorama_hand_off_is_recorded_not_raised(monkeypatch):
    monkeypatch.setattr(settings, "panorama_base_url", "http://127.0.0.1:9")
    monkeypatch.setattr(settings, "panorama_timeout_seconds", 1.0)
    sent = panorama.send("monitoring-results", {"facility": "F", "client": "C",
                                                "period": "2026-10", "status": "released",
                                                "results": {"a": 1}})
    assert sent["ok"] is False and sent["receipt"] is None
    assert sent["request"]["mode"] == "configured" and sent["response"]["status"] == 0


def test_a_held_load_waits_for_the_manual_re_run():
    row = flow.new_client("Ashgrove Capital Partners LP", "Nadia Brooks", True)
    case = flow.onboard_ai("harbourline", row, "Harbourline Consumer Receivables LLC",
                           "Consumer instalment", 150_000_000, [
                               "Harbourline_Loan_and_Security_Agreement.pdf",
                               "Harbourline_First_Amendment.pdf",
                               "Harbourline_Loan_Tape_2026-09.csv",
                               "Ashgrove_Harbourline_BB_Model_v1.xlsx"])
    case = flow.finish_onboarding(case, f"client-{row['id']}")
    sub = flow.first_month(case["facility_id"], "harbourline",
                           "Harbourline_Loan_Tape_2026-10.csv",
                           "Harbourline_Servicer_Report_October_2026.pdf")
    assert sub["status"] == "held" and "engine" not in sub["state"]["validation"]
    assert sub["state"]["runs"][-1] == {**sub["state"]["runs"][-1], "trigger": "auto",
                                        "held": True}
    blocking = next(f for f in sub["state"]["findings"] if f["severity"] == "blocking")
    sub = flow.sub_step(sub["id"], f"triage/{blocking['ref']}",
                        {"outcome": "confirmed", "note": "Duplicate row excluded"})
    assert sub["status"] == "held" and sub["state"]["hold_released"]["rows"] >= 1
    sub = flow.sub_step(sub["id"], "process", code=True)
    assert sub["status"] == "in_review" and sub["state"]["validation"]["engine"]
    assert [r["trigger"] for r in sub["state"]["runs"]] == ["auto", "manual"]
    assert "hold_released" not in sub["state"]


# 4. Partial reuse: the bank's rule library and the lender's mapping


def test_a_second_facility_reuses_the_bank_library_where_its_agreement_agrees(sme):
    row = sme["client"]
    case = flow.new_case(row["id"], "Fenwick SME Funding II", "SME loans", 80_000_000)
    cid = case["id"]
    folder = flow.deal_dir("fenwick") / "onboarding"
    flow.upload(cid, folder / FENWICK_DOC)
    flow.upload(cid, folder / "Fenwick_Portfolio_2026-09.xlsx")
    case = flow.step(cid, "classify", code=True)
    assert case["setup"]["rule_library"], "the first facility's rules form the library"
    case = flow.step(cid, "rules", {"action": "library"})
    reused = [r for k in ("eligibility", "concentration") for r in case["state"]["rules"][k]
              if r["source"] == "library"]
    assert reused and all(r["verified"] and r["origin"]["facility_id"] == sme["facility_id"]
                          for r in reused)
    assert case["setup"]["provenance"]["library_rules"] == len(reused)
    again = flow.step(cid, "rules", {"action": "library"})
    assert not again["state"]["rules"]["library_checked"]["added"]
    # Another bank's library is never offered.
    other = flow.new_client("Stranger Bank plc", "Ann Other", True)
    other_case = flow.new_case(other["id"], "Elsewhere", "SME loans", 1_000_000)
    refused = client.post(f"/api/deals/cases/{other_case['id']}/rules", headers=h("hannah"),
                          json={"action": "library"})
    assert refused.status_code == 422 and "library is empty" in refused.json()["detail"]
    facility = ok(client.get(f"/api/deals/facilities/{sme['facility_id']}", headers=h("priya")))
    prov = facility["provenance"]
    assert prov["mapping"]["from"] in ("lender_mapping", "new")
    assert prov["facility_rules"] == len(prov["rules"])


def test_the_portfolio_shows_library_rules_sender_layouts_and_facility_specifics():
    reuse = ok(client.get("/api/monitoring/reuse"))
    by_id = {f["facility"]: f for f in reuse["facilities"]}
    northmoor = by_id["northmoor"]
    assert {r["id"] for r in northmoor["rules"]} == {"CWL-01", "CWL-02", "CWL-03"}
    assert next(r for r in northmoor["rules"] if r["id"] == "CWL-01")["parameter"] == \
        "6.0%, Section 7.1(a)"
    shared = next(x for x in northmoor["layouts"] if x["id"] == "LAY-0301")
    assert shared["from"] == "sender_layout" and shared["shared_with"] == ["bramble"]
    larkspur = by_id["larkspur"]
    assert all(r["id"].startswith("TBL-") for r in larkspur["rules"])
    assert larkspur["specific"] and larkspur["counts"]["reused_layouts"] >= 2
    book = by_id["ashcombe"]
    assert next(r for r in book["rules"] if r["id"] == "CWL-01")["parameter"] == \
        "7%, Section 7.1(a)"
    assert book["layouts"][0]["from"] == "lender_template"
    for f in reuse["facilities"]:
        prefix = "CWL-" if f["client"] == "calderwood" else "TBL-"
        assert all(r["id"].startswith(prefix) for r in f["rules"]), f["facility"]
    assert {lib["client"] for lib in reuse["libraries"]} == {"calderwood", "thornbury"}


# 6. Clients outside the AI scope: the same steps, no model call


def test_a_no_ai_client_gets_a_built_model_and_reporting_with_no_model_call():
    row = flow.new_client("Kingsgate Bank N.A.", "Rosa Lind", False)
    case = flow.new_case(row["id"], "Fenwick SME Funding III", "SME loans", 80_000_000)
    cid = case["id"]
    folder = flow.deal_dir("fenwick") / "onboarding"
    flow.upload(cid, folder / FENWICK_DOC, "agreement")
    flow.upload(cid, folder / "Fenwick_Portfolio_2026-09.xlsx", "loan_tape")
    flow.step(cid, "terms/manual")
    for term, (value, page) in {"commitment": ("US$80,000,000", 2),
                                "advance_rate": ("70.00%", 2),
                                "delinquency_trigger": ("7.50%", 3)}.items():
        flow.step(cid, f"terms/{term}", {"action": "enter", "value": value,
                                         "document": FENWICK_DOC, "page": page,
                                         "basis_days": 30, "window_months": 3})
    for term in ("reserve", "loss_trigger"):
        flow.step(cid, f"terms/{term}", {"action": "absent", "reason": "Not in the agreement"})
    flow.capture_reporting(cid)
    flow.step(cid, "rules", {"action": "add", "kind": "eligibility", "rule": {
        "ref": "First Schedule (a)", "plain_english": "Not more than 30 days in arrears",
        "clause_text": "the loan is not more than 30 days in arrears;", "document": FENWICK_DOC,
        "test": {"kind": "max", "field": "days_past_due", "high": 30}}})
    flow.step(cid, "rules", {"action": "approve"})
    flow.step(cid, "mapping/suggest", code=True)
    flow.step(cid, "mapping", {})
    flow.step(cid, "validate", {"as_of": "2026-09-30"})
    case = flow.step(cid, "client-model/build", code=True)
    assert case["state"]["built_model"]["notes_by"] == "template"
    assert case["cost"]["calls"] == 0
    with Session(engine) as db:
        assert db.scalars(select(LlmSpend).where(LlmSpend.case_id == cid)).first() is None
