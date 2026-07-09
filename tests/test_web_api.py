"""Local-access guards on the web console (web/api_server.py).

The console binds to localhost and drives real runs, so it must refuse requests
without the shared session token, from a foreign Origin, with an oversized body,
beyond the concurrency limit, or with an invalid decision/example. None of these
paths start a pipeline, so the suite stays offline (no Ollama) as ever.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from collections.abc import Iterator
from http.server import ThreadingHTTPServer

import api_server
import pytest

from agent_pipeline.contracts import HumanDecision

TOKEN = "test-token-123"


@pytest.fixture(autouse=True)
def _reset_state() -> Iterator[None]:
    """Isolate module globals between tests."""
    api_server.SESSIONS.clear()
    api_server.API_TOKEN = TOKEN
    api_server.WEB_CFG = {
        "max_body_bytes": 200,
        "max_concurrent_runs": 2,
        "allowed_origins": ["http://127.0.0.1:5173"],
    }
    yield
    api_server.SESSIONS.clear()


@pytest.fixture
def base_url() -> Iterator[str]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), api_server.Handler)
    import threading

    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()


def _request(
    url: str, *, method: str = "GET", headers: dict | None = None, body: dict | None = None
) -> tuple[int, dict]:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, method=method, data=data, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:  # noqa: S310 - localhost test server
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode())


def _auth(extra: dict | None = None) -> dict:
    return {"X-API-Token": TOKEN, **(extra or {})}


# --- token & origin -------------------------------------------------------
def test_health_is_open_without_token(base_url):
    status, body = _request(f"{base_url}/health")
    assert status == 200 and body == {"status": "ok"}


def test_missing_token_is_rejected(base_url):
    status, body = _request(f"{base_url}/api/runs")
    assert status == 401 and "token" in body["error"]


def test_valid_token_is_accepted(base_url):
    status, _ = _request(f"{base_url}/api/runs", headers=_auth())
    assert status == 200


def test_foreign_origin_is_rejected(base_url):
    headers = _auth({"Origin": "http://evil.example"})
    status, body = _request(f"{base_url}/api/runs", headers=headers)
    assert status == 403 and "cross-origin" in body["error"]


def test_allowed_origin_passes(base_url):
    headers = _auth({"Origin": "http://127.0.0.1:5173"})
    status, _ = _request(f"{base_url}/api/runs", headers=headers)
    assert status == 200


# --- body size, concurrency, validation -----------------------------------
def test_oversized_body_gets_413(base_url):
    big = {"text": "x" * 500}  # exceeds max_body_bytes=200
    status, body = _request(f"{base_url}/api/run", method="POST", headers=_auth(), body=big)
    assert status == 413 and "too large" in body["error"]


def test_too_many_concurrent_runs_gets_429(base_url):
    for i in range(2):  # fill max_concurrent_runs=2
        api_server.SESSIONS[f"r{i}"] = api_server.RunSession(run_id=f"r{i}", status="running")
    status, body = _request(
        f"{base_url}/api/run", method="POST", headers=_auth(), body={"text": "hi"}
    )
    assert status == 429 and "concurrent" in body["error"]


def test_unknown_example_gets_400(base_url):
    body = {"source": "example:../../etc/passwd"}
    status, resp = _request(f"{base_url}/api/run", method="POST", headers=_auth(), body=body)
    assert status == 400 and "unknown example" in resp["error"]


def test_empty_run_request_gets_400(base_url):
    status, resp = _request(f"{base_url}/api/run", method="POST", headers=_auth(), body={})
    assert status == 400


def test_decide_unknown_session_gets_404(base_url):
    body = {"decision": "approve"}
    status, resp = _request(
        f"{base_url}/api/run/nope/decide", method="POST", headers=_auth(), body=body
    )
    assert status == 404


def test_decide_invalid_decision_gets_400(base_url):
    api_server.SESSIONS["live"] = api_server.RunSession(run_id="live", status="awaiting_review")
    body = {"decision": "sudo-approve"}
    status, resp = _request(
        f"{base_url}/api/run/live/decide", method="POST", headers=_auth(), body=body
    )
    assert status == 400 and "decision" in resp["error"]


def test_valid_run_is_accepted(base_url, monkeypatch):
    # Guard passes → the endpoint hands off to _start_run; stub it so no pipeline
    # (and no Ollama) is needed to prove the 202 path.
    monkeypatch.setattr(api_server, "_start_run", lambda source, text: "stub-run-id")
    status, resp = _request(
        f"{base_url}/api/run", method="POST", headers=_auth(), body={"text": "review this"}
    )
    assert status == 202 and resp["run_id"] == "stub-run-id"


def test_valid_decision_reaches_the_session(base_url):
    session = api_server.RunSession(run_id="live", status="awaiting_review")
    api_server.SESSIONS["live"] = session
    for decision in (d.value for d in HumanDecision):
        session._event.clear()
        status, _ = _request(
            f"{base_url}/api/run/live/decide",
            method="POST",
            headers=_auth(),
            body={"decision": decision},
        )
        assert status == 200
        assert session._event.is_set()
