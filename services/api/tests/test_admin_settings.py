"""Settings › AI provider: the key is encrypted at rest, never returned, used ahead of the
environment's key, and only the administrator with the access code may touch it.

No real network: the connection test's one HTTP call is replaced in every test.
"""

import uuid
from pathlib import Path
from typing import Any

import httpx
import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.admin import ai_provider as ap
from app.admin.models import AppSetting
from app.config import settings
from app.db import engine
from app.deals import audit
from app.main import app
from app.pipeline.gateway import AnthropicClient

client = TestClient(app)
CODE = "settings-test-code"
KEY = "sk-ant-api03-" + "A1b2C3d4" * 10 + "-wxyz"
ENV_KEY = "sk-ant-api03-" + "Z9y8X7w6" * 10 + "-envk"
URL = "/api/admin/ai-provider"


def h(persona: str = "alex", code: str | None = CODE) -> dict[str, str]:
    headers = {"X-Acting-User": persona}
    if code is not None:
        headers["X-Demo-Access-Code"] = code
    return headers


class Calls:
    """Stands in for the network: records each request and answers with a canned response."""

    def __init__(self, status: int = 200, body: Any = None) -> None:
        self.status = status
        self.body = body if body is not None else {"data": [{"id": "claude-opus-5-5"}]}
        self.seen: list[dict[str, Any]] = []

    def __call__(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        self.seen.append({"method": method, "url": url, **kwargs})
        return httpx.Response(self.status, json=self.body,
                              request=httpx.Request(method, url))


@pytest.fixture(autouse=True)
def isolated(monkeypatch: pytest.MonkeyPatch):
    """A setting row and an audit chain of this test's own, so the shared database's real
    setting is never touched."""
    name = f"test-{uuid.uuid4().hex[:8]}"
    monkeypatch.setattr(ap, "NAME", name)
    monkeypatch.setattr(ap, "AUDIT_CHAIN", uuid.uuid4().hex)
    monkeypatch.setattr(settings, "demo_access_code", CODE)
    monkeypatch.setattr(settings, "settings_encryption_key", Fernet.generate_key().decode())
    monkeypatch.setattr(settings, "local_env_file", "")
    monkeypatch.setattr(settings, "llm_provider", "anthropic")
    monkeypatch.setattr(settings, "anthropic_api_key", ENV_KEY)
    calls = Calls()
    monkeypatch.setattr(ap, "_send", calls)
    ap.check_limit.reset()
    yield calls
    ap.check_limit.reset()
    with Session(engine) as db:
        db.execute(delete(AppSetting).where(AppSetting.name == name))
        db.commit()


def saved(response: Any) -> dict[str, Any]:
    assert response.status_code == 200, (response.status_code, response.text[:400])
    assert KEY not in response.text and ENV_KEY not in response.text
    return response.json()


def test_the_key_is_encrypted_at_rest_and_round_trips():
    token = ap.encrypt(KEY)
    assert KEY.encode() not in token
    assert ap.decrypt(token) == KEY
    saved(client.put(URL, headers=h(), json={"provider": "anthropic", "key": KEY}))
    with Session(engine) as db:
        row = db.get(AppSetting, ap.NAME)
        assert row is not None and row.key_encrypted and KEY.encode() not in row.key_encrypted
        assert ap.decrypt(row.key_encrypted) == KEY and row.last4 == "wxyz"


def test_a_different_encryption_key_cannot_read_it(monkeypatch):
    token = ap.encrypt(KEY)
    monkeypatch.setattr(settings, "settings_encryption_key", Fernet.generate_key().decode())
    assert ap.decrypt(token) is None
    monkeypatch.setattr(settings, "settings_encryption_key", "not-a-fernet-key")
    assert not ap.encryption_ready()


def test_no_response_ever_returns_the_key():
    put = saved(client.put(URL, headers=h(), json={"provider": "anthropic", "key": KEY,
                                                   "model": "claude-opus-5-5"}))
    assert put["saved"] is True and put["source"] == "db" and put["last4"] == "wxyz"
    assert put["env_written"] is False
    got = saved(client.get(URL, headers=h()))
    assert got["configured"] is True and got["source"] == "db"
    assert got["updated_by"] == "Alex Morgan" and got["model"] == "claude-opus-5-5"
    assert not any(KEY in str(v) for v in got.values())
    saved(client.post(f"{URL}/test", headers=h(), json={}))
    saved(client.post(f"{URL}/test", headers=h(), json={"key": KEY}))
    saved(client.delete(URL, headers=h()))
    # The hash-chained log says what changed, never the key or its last four.
    with Session(engine) as db:
        events = audit.events(db, ap.AUDIT_CHAIN)
    assert [e.type for e in events] == ["ai-provider-save", "ai-provider-remove"]
    for event in events:
        assert KEY not in str(event.payload) and "wxyz" not in str(event.payload)


def test_a_bad_key_is_refused_without_echoing_it():
    bad = "sk-ant-has spaces in it and is long enough"
    response = client.put(URL, headers=h(), json={"provider": "anthropic", "key": bad})
    assert response.status_code == 422 and bad not in response.text
    assert response.json()["detail"]["fields"]["key"]
    wrong_type = client.put(URL, headers=h(), json={"key": 12345678901234567890})
    assert wrong_type.status_code == 422 and "12345678901234567890" not in wrong_type.text
    assert client.put(URL, headers=h(), json={"provider": "openai", "key": KEY}).status_code == 422


@pytest.mark.parametrize("method,path,body", [
    ("GET", URL, None), ("PUT", URL, {"key": KEY}), ("DELETE", URL, None),
    ("POST", f"{URL}/test", {"key": KEY}),
])
def test_only_the_administrator_gets_in(method, path, body, monkeypatch):
    def call(headers: dict[str, str]) -> Any:
        return client.request(method, path, headers=headers, json=body)

    for persona in ("hannah", "elena", "marcus"):
        refused = call(h(persona))
        assert refused.status_code == 403
        assert refused.json()["detail"]["reason"] == "not_admin"
    assert call({}).json()["detail"]["reason"] == "not_admin"
    # A client user is stopped before the endpoint runs.
    assert call(h("james")).status_code == 403
    # There is no access code: the administrator persona alone is enough to read the settings.
    if method == "GET":
        assert call(h(code=None)).status_code == 200
    with Session(engine) as db:
        assert db.get(AppSetting, ap.NAME) is None


def test_the_saved_key_comes_first_then_the_environment(monkeypatch):
    assert ap.effective() == ap.Effective("anthropic", ENV_KEY, settings.deals_model, "env")
    saved(client.put(URL, headers=h(), json={"provider": "anthropic", "key": KEY}))
    assert ap.effective().key == KEY and ap.effective().source == "db"
    saved(client.delete(URL, headers=h()))
    assert ap.effective().key == ENV_KEY and ap.effective().source == "env"
    monkeypatch.setattr(settings, "anthropic_api_key", "")
    assert ap.effective().source == "none" and not ap.effective().configured
    # A saved key that today's encryption key cannot read falls back, and says so.
    monkeypatch.setattr(settings, "anthropic_api_key", ENV_KEY)
    saved(client.put(URL, headers=h(), json={"provider": "anthropic", "key": KEY}))
    monkeypatch.setattr(settings, "settings_encryption_key", Fernet.generate_key().decode())
    fallback = ap.effective()
    assert fallback.key == ENV_KEY and fallback.unreadable
    assert saved(client.get(URL, headers=h()))["saved_key_unreadable"] is True


def test_a_model_client_picks_up_a_new_key_on_the_next_call(monkeypatch):
    built: list[str] = []

    def fake_sdk(current: ap.Effective) -> Any:
        built.append(current.key)
        return object()

    monkeypatch.setattr(ap, "sdk_client", fake_sdk)
    model = AnthropicClient("anthropic")
    model._sdk()
    model._sdk()
    assert built == [ENV_KEY]  # one client per key, not per call
    saved(client.put(URL, headers=h(), json={"provider": "anthropic", "key": KEY}))
    model._sdk()
    assert built == [ENV_KEY, KEY]
    saved(client.delete(URL, headers=h()))
    model._sdk()
    assert built == [ENV_KEY, KEY, ENV_KEY]


def test_the_new_deals_gateway_and_status_use_the_resolved_key(monkeypatch):
    from app.deals.guard import DealsGateway

    monkeypatch.setattr(settings, "anthropic_api_key", "")
    monkeypatch.setattr(settings, "deals_stub_model", False)
    assert DealsGateway().live is False
    saved(client.put(URL, headers=h(), json={"provider": "anthropic", "key": KEY,
                                             "model": "claude-test-model"}))
    gateway = DealsGateway()
    assert gateway.live is True and gateway.model == "claude-test-model"


def test_without_an_encryption_key_nothing_is_saved(monkeypatch):
    monkeypatch.setattr(settings, "settings_encryption_key", "")
    view = saved(client.get(URL, headers=h()))
    assert view["encryption_ready"] is False
    refused = client.put(URL, headers=h(), json={"provider": "anthropic", "key": KEY})
    assert refused.status_code == 409
    assert refused.json()["detail"]["reason"] == "encryption_missing"
    assert KEY not in refused.text
    with Session(engine) as db:
        assert db.get(AppSetting, ap.NAME) is None


def test_saving_locally_writes_the_env_file_keeping_every_other_line(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_bytes(b"# Ports\r\nWEB_PORT=5180\r\nANTHROPIC_API_KEY=old\r\n\r\n"
                    b"export ANTHROPIC_API_KEY=older\r\nDEMO_ACCESS_CODE=abc # note\r\n")
    monkeypatch.setattr(settings, "local_env_file", str(env))
    view = saved(client.put(URL, headers=h(), json={"provider": "anthropic", "key": KEY}))
    assert view["env_written"] is True and view["env_file"] == {"enabled": True,
                                                                 "writable": True}
    assert env.read_bytes() == (b"# Ports\r\nWEB_PORT=5180\r\nANTHROPIC_API_KEY=" + KEY.encode()
                                + b"\r\n\r\nDEMO_ACCESS_CODE=abc # note\r\n")
    assert not list(tmp_path.glob(".*.tmp"))


def test_write_env_adds_a_missing_line_and_creates_a_missing_file(tmp_path):
    env = tmp_path / ".env"
    env.write_text("WEB_PORT=5180\nLLM_MODE=replay", encoding="utf-8")
    ap.write_env(env, "ANTHROPIC_API_KEY", "value-1")
    assert env.read_text(encoding="utf-8") == ("WEB_PORT=5180\nLLM_MODE=replay\n"
                                               "ANTHROPIC_API_KEY=value-1\n")
    fresh = tmp_path / "new.env"
    ap.write_env(fresh, "ANTHROPIC_API_KEY", "value-2")
    assert fresh.read_text(encoding="utf-8") == "ANTHROPIC_API_KEY=value-2\n"


def test_write_env_rewrites_in_place_when_the_file_cannot_be_renamed_over(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text("A=1\nANTHROPIC_API_KEY=old\n", encoding="utf-8")

    def busy(*_: Any) -> None:
        raise OSError(16, "Device or resource busy")

    monkeypatch.setattr(ap.os, "replace", busy)
    ap.write_env(env, "ANTHROPIC_API_KEY", "new")
    assert env.read_text(encoding="utf-8") == "A=1\nANTHROPIC_API_KEY=new\n"
    assert not list(tmp_path.glob(".*.tmp"))


def test_an_unwritable_env_file_still_saves_and_says_so(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "local_env_file", str(tmp_path / "missing-dir" / ".env"))
    view = saved(client.put(URL, headers=h(), json={"provider": "anthropic", "key": KEY}))
    assert view["saved"] is True and view["env_written"] is False
    assert view["env_error"] and KEY not in view["env_error"]


def test_the_connection_test_reports_a_working_key(isolated: Calls):
    result = saved(client.post(f"{URL}/test", headers=h(), json={"key": KEY}))
    assert result["ok"] is True and result["status"] == 200
    assert result["models"] == ["claude-opus-5-5"] and result["subject"] == "typed"
    assert isinstance(result["latency_ms"], int)
    sent = isolated.seen[0]
    assert sent["method"] == "GET" and sent["url"] == "https://api.anthropic.com/v1/models"
    assert sent["headers"]["x-api-key"] == KEY
    # Testing a typed key saves nothing but the result.
    view = saved(client.get(URL, headers=h()))
    assert view["source"] == "env" and view["last_test"]["ok"] is True
    assert view["last_test"]["model_count"] == 1


def test_the_connection_test_explains_a_refused_key_without_echoing_it(monkeypatch):
    refused = Calls(401, {"type": "error", "error": {
        "type": "authentication_error", "message": f"invalid x-api-key {KEY}"}})
    monkeypatch.setattr(ap, "_send", refused)
    result = saved(client.post(f"{URL}/test", headers=h(), json={}))
    assert result["ok"] is False and result["status"] == 401 and result["subject"] == "env"
    assert result["error"].startswith("authentication_error: invalid x-api-key")
    assert refused.seen[0]["headers"]["x-api-key"] == ENV_KEY


def test_the_connection_test_survives_the_network_failing(monkeypatch):
    def down(method: str, url: str, **_: Any) -> httpx.Response:
        raise httpx.ConnectTimeout(f"timed out sending {KEY}")

    monkeypatch.setattr(ap, "_send", down)
    result = saved(client.post(f"{URL}/test", headers=h(), json={"key": KEY}))
    assert result["ok"] is False and result["status"] is None
    assert "ConnectTimeout" in result["error"]


def test_the_connection_test_on_foundry_sends_one_token(monkeypatch, isolated: Calls):
    monkeypatch.setenv("ANTHROPIC_FOUNDRY_RESOURCE", "example-resource")
    monkeypatch.delenv("ANTHROPIC_FOUNDRY_BASE_URL", raising=False)
    result = saved(client.post(f"{URL}/test", headers=h(),
                               json={"key": KEY, "provider": "foundry"}))
    assert result["ok"] is True
    sent = isolated.seen[0]
    assert sent["url"] == "https://example-resource.services.ai.azure.com/anthropic/v1/messages"
    assert sent["json"]["max_tokens"] == 1


def test_the_connection_test_needs_a_key_and_is_rate_limited(monkeypatch, isolated: Calls):
    monkeypatch.setattr(settings, "anthropic_api_key", "")
    assert client.post(f"{URL}/test", headers=h(), json={}).status_code == 422
    assert isolated.seen == []
    for _ in range(ap.CHECK_LIMIT_PER_MINUTE):
        assert client.post(f"{URL}/test", headers=h(), json={"key": KEY}).status_code == 200
    limited = client.post(f"{URL}/test", headers=h(), json={"key": KEY})
    assert limited.status_code == 429
    assert len(isolated.seen) == ap.CHECK_LIMIT_PER_MINUTE


def test_scrub_removes_any_key_shaped_text():
    assert ap.scrub(f"bad {KEY} and sk-ant-other123456") == "bad [redacted] and [redacted]"


def test_the_saved_key_path_is_never_written_in_plaintext(tmp_path: Path):
    """There is no plaintext fallback anywhere: the table has no plaintext column."""
    assert "key_plain" not in AppSetting.__table__.columns
    assert {c.name for c in AppSetting.__table__.columns} == {
        "name", "provider", "key_encrypted", "last4", "model", "last_test", "updated_by",
        "updated_at"}
