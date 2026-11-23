"""The hand-off to Oxane's platform, Panorama. A stub: the demo is not connected to Panorama.

An outbound client posts two things: an approved onboarding load file at go-live, and a month's
released monitoring results. Where Panorama is (`PANORAMA_BASE_URL`) and how to authenticate
(`PANORAMA_API_KEY`) are configuration. Unset, the client posts to the mock inside this app,
`POST /api/mock/panorama/{kind}`, which checks the payload's shape and returns a receipt ID
derived from the payload's hash. Every attempt, its request and its response are written to the
record's hash-chained audit log by the caller; nothing is sent anywhere else.
"""

import hashlib
import json
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from app.config import settings

KINDS = {
    "onboarding-load": "Approved onboarding load file",
    "monitoring-results": "Released monitoring results",
}
MOCK_PATH = "/api/mock/panorama"
REQUIRED = {"onboarding-load": ("case", "facility", "client", "status", "terms", "ruleset"),
            "monitoring-results": ("facility", "client", "period", "status", "results")}

router = APIRouter()


def config() -> dict[str, Any]:
    """What the integration is set to. The key is never shown, only whether one is set."""
    mock = not settings.panorama_base_url.strip()
    return {"mode": "mock" if mock else "configured",
            "base_url": MOCK_PATH if mock else settings.panorama_base_url.rstrip("/"),
            "auth": "none (in-app mock)" if mock else (
                "bearer key set" if settings.panorama_api_key else "no key set"),
            "note": "Stub: the in-app mock stands in for Panorama. Set PANORAMA_BASE_URL and "
                    "PANORAMA_API_KEY to point at a real endpoint." if mock else
                    "Configured endpoint; the demo build has not been tested against it."}


def _body(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()


def receipt_for(kind: str, body: bytes) -> str:
    return "PNR-" + hashlib.sha256(kind.encode() + b"\n" + body).hexdigest()[:10].upper()


def accept(kind: str, payload: dict[str, Any]) -> dict[str, Any]:
    """The mock Panorama: checks the shape, issues a receipt. Same payload, same receipt."""
    if kind not in KINDS:
        raise HTTPException(status_code=404, detail="Unknown Panorama feed")
    missing = [k for k in REQUIRED[kind] if payload.get(k) in (None, "", [], {})]
    if missing:
        raise HTTPException(status_code=422, detail={"message": "Rejected by Panorama (mock)",
                                                     "missing": missing})
    if payload.get("status") not in ("final", "released"):
        raise HTTPException(status_code=409, detail="Panorama (mock) accepts only approved or "
                            "released data")
    return {"receipt": receipt_for(kind, _body(payload)), "accepted": True, "feed": kind,
            "received_at": datetime.now(UTC).isoformat(), "mock": True}


@router.post(MOCK_PATH + "/{kind}")
async def post_mock(kind: str, request: Request) -> dict[str, Any]:
    try:
        payload = json.loads(await request.body() or b"{}")
    except json.JSONDecodeError as error:
        raise HTTPException(status_code=400, detail="Not JSON") from error
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Expected a JSON object")
    return accept(kind, payload)


@router.get("/api/panorama/config")
def get_config() -> dict[str, Any]:
    return config()


def send(kind: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Post one payload. Returns the record of the attempt: request, response and receipt."""
    body = _body(payload)
    cfg = config()
    url = f"{cfg['base_url']}/{kind}"
    request = {"method": "POST", "url": url, "bytes": len(body),
               "sha256": hashlib.sha256(body).hexdigest(), "feed": KINDS[kind],
               "mode": cfg["mode"], "at": datetime.now(UTC).isoformat()}
    try:
        if cfg["mode"] == "mock":
            status, answer = 200, accept(kind, json.loads(body))
        else:
            import httpx

            headers = {"Content-Type": "application/json"}
            if settings.panorama_api_key:
                headers["Authorization"] = f"Bearer {settings.panorama_api_key}"
            reply = httpx.post(url, content=body, headers=headers,
                               timeout=settings.panorama_timeout_seconds)
            status = reply.status_code
            try:
                answer = reply.json()
            except ValueError:
                answer = {"text": reply.text[:300]}
    except HTTPException as refused:
        status, answer = refused.status_code, {"detail": refused.detail}
    except Exception as error:  # noqa: BLE001 - a failed hand-off is recorded, never raised
        status, answer = 0, {"detail": f"{type(error).__name__}: {error}"[:300]}
    receipt = answer.get("receipt") if isinstance(answer, dict) and status == 200 else None
    return {"kind": kind, "request": request,
            "response": {"status": status, "body": answer}, "receipt": receipt,
            "ok": bool(receipt)}


def results_payload(facility: dict[str, Any], sub: dict[str, Any]) -> dict[str, Any]:
    """A released month's results, as Panorama would take them: the numbers code computed."""
    state = sub["state"]
    engine = (state.get("validation") or {}).get("engine") or {}
    report = state.get("report") or {}
    return {
        "facility": facility["ref"], "facility_name": facility["name"],
        "client": facility["client"], "period": sub["period"],
        "status": "released" if report.get("released_at") else "provisional",
        "results": {k: engine.get(k) for k in (
            "gross_pool_cents", "eligible_pool_cents", "excess_cents", "advance_rate_pct",
            "reserve_cents", "borrowing_base_cents", "availability_cents", "run_digest")},
        "tests": state.get("tests") or {},
        "approvals": report.get("approvals", []),
        "findings": [{"ref": f["ref"], "title": f["title"],
                      "outcome": (f.get("decision") or {}).get("outcome")}
                     for f in state.get("findings", [])],
    }
