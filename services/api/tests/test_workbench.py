from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def workbench():
    return client.get("/api/workbench").json()


def test_workbench_has_every_seeded_section():
    body = workbench()
    assert body["seed"] is True
    assert len(body["documents"]) == 8
    assert len(body["terms"]) == 26
    assert len(body["rules"]) == 17
    assert len(body["mapping"]["rows"]) == 38
    assert len(body["exceptions"]) == 10


def test_every_text_citation_has_a_highlight():
    for term in workbench()["terms"]:
        source = term["source"]
        if source:
            assert source["rects"], term["name"]
            for rect in source["rects"]:
                assert 0 <= rect["x0"] < rect["x1"] <= 1
                assert 0 <= rect["top"] < rect["bottom"] <= 1


def test_advance_rate_cites_both_documents():
    term = next(t for t in workbench()["terms"] if t["name"] == "Advance rate")
    assert term["source"]["document"] == "amendment_1"
    assert term["also_cited"][0]["document"] == "credit_agreement"


def test_pack_serves_only_pack_files():
    assert client.get("/api/pack/Bramble_Amendment_No_1.pdf").status_code == 200
    assert client.get("/api/pack/deal.yaml").status_code == 404
    assert client.get("/api/pack/..%2Fanswer-key%2Ffields.json").status_code == 404


def test_run_reconciles_and_the_dealer_match_lowers_availability():
    before = client.post("/api/run", json={"dealer_match": False}).json()
    after = client.post("/api/run", json={"dealer_match": True}).json()
    assert before["pool_bridge"]["unexplained"] == 0
    assert before["pool_bridge"]["reproduces_certificate"]
    assert {line["rule_id"] for line in before["pool_bridge"]["lines"]} == {"E1", "E12"}
    assert after["system"]["excess"] > 0 == before["system"]["excess"]
    assert 500_000 > after["system"]["availability"] > 0
    assert before["provisional"] and before["not_evaluated"] == ["E7"]


def test_rule_preview_reports_the_change():
    result = client.post("/api/rules/preview", json={"rule_id": "E1", "value": 60}).json()
    assert result["newly_eligible"] == 41
    assert client.post("/api/rules/preview",
                       json={"rule_id": "E7", "value": 1}).status_code == 422
