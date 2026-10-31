from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_reports_database():
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok"}


def test_case_comes_from_the_deal_file():
    body = client.get("/api/case").json()
    assert body["number"] == "0412"
    assert body["status"] == "awaiting_pack"
    assert body["llm_mode"] == "replay"
    assert body["deal"]["facility"]["limit_usd"] == 250_000_000
    assert body["deal"]["lender"]["name"] == "Calderwood Bank plc"


def test_case_key_dates_stay_in_order():
    dates = [item["date"] for item in client.get("/api/case").json()["deal"]["dates"]]
    assert dates == sorted(dates)
