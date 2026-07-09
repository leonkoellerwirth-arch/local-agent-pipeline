"""The dashboard's API: read the audit trails *and* run the pipeline.

Built on the standard library only — no web framework, no Docker. It lets a
non-technical user drive the whole pipeline from the browser:

* ``GET  /api/runs``            — all past trails (for the dashboard).
* ``GET  /api/examples``        — the bundled example documents.
* ``POST /api/run``             — start a run (example or pasted text).
* ``GET  /api/run/<id>``        — poll one run's live state.
* ``POST /api/run/<id>/decide`` — answer a human-review request in the browser.

Human oversight happens *in the browser*: when the reviewer escalates, the run
pauses (``WebGate`` blocks its worker thread) and the UI shows the finding with
Approve / Reject / Edit buttons — the same gate the CLI has, moved to the web.

It binds to localhost only and starts real runs, so it is guarded accordingly:
a shared session token (``X-API-Token``; generated at startup or pinned via
``$API_TOKEN`` so the Vite proxy can share it), a localhost ``Origin`` allow-list,
a max request-body size (413), and a concurrent-run cap (429). The limits live in
``config/pipeline.yaml`` (``web:``). These make it safe on a shared machine; they
are not a substitute for real auth on a public host — don't expose it to one.
"""

from __future__ import annotations

import json
import os
import secrets
import threading
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from agent_pipeline.audit import AuditLog
from agent_pipeline.cli import _load_dotenv, _load_yaml, run_pipeline
from agent_pipeline.contracts import Actor, HumanDecision, Review, Task, WorkResult
from agent_pipeline.export import collect
from agent_pipeline.gate import BaseGate, GateOutcome
from agent_pipeline.llm import LLMClient, LLMError

ROOT = Path(__file__).resolve().parents[1]
RUN_DIRS = [Path(os.environ.get("RUNS_DIR", ROOT / "runs")), ROOT / "examples" / "expected-outputs"]
EXAMPLES_DIR = ROOT / "examples"

# --- local-access guards --------------------------------------------------
# The console binds to localhost and drives real runs, so we defend against the
# two local threats: another process on the box, and a malicious web page the
# user has open (which can POST to 127.0.0.1). A shared token blocks the first;
# an Origin allow-list blocks the second. Values come from config/pipeline.yaml
# (`web:`); the token is generated per process unless $API_TOKEN pins it so the
# Vite proxy can share it (see web/start.sh, web/vite.config.ts).
API_TOKEN = os.environ.get("API_TOKEN") or secrets.token_urlsafe(24)
WEB_CFG: dict = {}


def _cfg(key: str, default: object) -> object:
    return WEB_CFG.get(key, default)


def _allowed_origins() -> tuple[str, ...]:
    return tuple(_cfg("allowed_origins", ("http://127.0.0.1:5173", "http://localhost:5173")))


def _decision_timeout_s() -> int:
    return int(_cfg("decision_timeout_s", 900))

# Project docs surfaced inside the app, so everything is visible in one place.
DOCS = [
    ("readme", "Overview", ROOT / "README.md"),
    ("bible", "Project Bible", ROOT / "BIBLE.md"),
    ("handoff", "Handoff (session log)", ROOT / "HANDOFF.md"),
    ("sop", "Maintainer SOP", ROOT / "docs" / "SOP.md"),
    ("contributing", "Contributing", ROOT / "CONTRIBUTING.md"),
    ("changelog", "Changelog", ROOT / "CHANGELOG.md"),
]


@dataclass
class RunSession:
    """Live state of one browser-triggered run, polled by the UI."""

    run_id: str
    status: str = "running"  # running | awaiting_review | completed | aborted | error
    review: dict | None = None
    result: dict | None = None
    error: str | None = None
    path: str | None = None
    _decision: dict | None = None
    _event: threading.Event = field(default_factory=threading.Event)


SESSIONS: dict[str, RunSession] = {}


class WebGate(BaseGate):
    """A gate that surfaces escalations to the browser and waits for a click."""

    actor = Actor.HUMAN

    def __init__(self, session: RunSession) -> None:
        self._s = session

    def request(self, result: WorkResult, review: Review) -> GateOutcome:
        self._s.review = {
            "step_id": result.step_id,
            "action": result.action.value,
            "decision": review.decision.value,
            "policy_flags": review.policy_flags,
            "reasons": review.reasons,
            "raw": result.raw,
        }
        self._s.status = "awaiting_review"
        answered = self._s._event.wait(timeout=_decision_timeout_s())
        self._s._event.clear()
        self._s.review = None
        self._s.status = "running"

        decision_data = self._s._decision or {}
        if not answered:  # nobody answered in time → fail safe
            return GateOutcome(HumanDecision.REJECT, result, "review timed out")

        decision = HumanDecision(decision_data.get("decision", "reject"))
        edited = result
        if decision is HumanDecision.EDIT and isinstance(decision_data.get("output"), dict):
            edited = result.model_copy(
                update={
                    "output": decision_data["output"],
                    "raw": json.dumps(decision_data["output"]),
                }
            )
        return GateOutcome(decision, edited, decision_data.get("reason", ""))


def _new_run_id() -> str:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
    return f"{stamp}-{uuid.uuid4().hex[:6]}"


def _run_worker(session: RunSession, task: Task, pipeline_cfg: dict, policy_cfg: dict) -> None:
    try:
        llm = LLMClient(pipeline_cfg["llm"])
        with AuditLog(task.run_id, pipeline_cfg["audit"]) as audit:
            result = run_pipeline(
                task,
                pipeline_cfg=pipeline_cfg,
                policy_cfg=policy_cfg,
                llm=llm,
                audit=audit,
                gate=WebGate(session),
            )
            session.path = str(audit.path)
            session.result = {
                "status": result.status,
                "note": result.note,
                "results": [{"action": r.action.value, "output": r.output} for r in result.results],
            }
            session.status = result.status
    except LLMError as exc:
        session.status, session.error = "error", str(exc)
    except Exception as exc:  # noqa: BLE001 - surface any failure to the UI, don't crash the server
        session.status, session.error = "error", f"{type(exc).__name__}: {exc}"


def _example_names() -> set[str]:
    """The ids of the bundled example documents (their file stems)."""
    return {path.stem for path in EXAMPLES_DIR.glob("*.txt")}


class BadRequest(ValueError):
    """A client-side error (bad example id, etc.) that maps to HTTP 400."""


def _start_run(source: str, text: str) -> str:
    pipeline_cfg = _load_yaml(str(ROOT / "config" / "pipeline.yaml"))
    policy_cfg = _load_yaml(str(ROOT / "config" / "policy.yaml"))
    _load_dotenv(ROOT / ".env")

    if source.startswith("example:"):
        # Only known example ids are accepted — never build a path from the raw
        # value, or `example:../../etc/passwd` would read arbitrary files.
        example_id = source.split(":", 1)[1]
        if example_id not in _example_names():
            raise BadRequest(f"unknown example '{example_id}'")
        content = (EXAMPLES_DIR / f"{example_id}.txt").read_text(encoding="utf-8")
        input_path = source
    else:
        content = text
        input_path = "pasted-text"

    run_id = _new_run_id()
    task = Task(run_id=run_id, input_path=input_path, content=content)
    session = RunSession(run_id=run_id)
    SESSIONS[run_id] = session
    threading.Thread(
        target=_run_worker, args=(session, task, pipeline_cfg, policy_cfg), daemon=True
    ).start()
    return run_id


def _session_view(s: RunSession) -> dict:
    return {
        "run_id": s.run_id,
        "status": s.status,
        "review": s.review,
        "result": s.result,
        "error": s.error,
        "path": s.path,
    }


class Handler(BaseHTTPRequestHandler):
    def _send(self, status: int, payload: object) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", "0") or "0")
        if not length:
            return {}
        try:
            return json.loads(self.rfile.read(length).decode("utf-8"))
        except json.JSONDecodeError:
            return {}

    def _guarded(self) -> bool:
        """Enforce the local-access guards; on failure send the error and return False.

        ``/health`` is exempt so a launcher can probe liveness without the token.
        """
        if self.path == "/health":
            return True
        origin = self.headers.get("Origin")
        if origin is not None and origin not in _allowed_origins():
            self._send(403, {"error": "cross-origin request refused"})
            return False
        if not secrets.compare_digest(self.headers.get("X-API-Token", ""), API_TOKEN):
            self._send(401, {"error": "missing or invalid API token"})
            return False
        return True

    def do_GET(self) -> None:  # noqa: N802 - required handler name
        if not self._guarded():
            return
        if self.path == "/health":
            self._send(200, {"status": "ok"})
        elif self.path.startswith("/api/runs"):
            self._send(200, collect(RUN_DIRS))
        elif self.path == "/api/examples":
            self._send(200, self._examples())
        elif self.path == "/api/docs":
            self._send(200, self._docs())
        elif self.path.startswith("/api/run/"):
            run_id = self.path[len("/api/run/") :]
            session = SESSIONS.get(run_id)
            self._send(200, _session_view(session)) if session else self._send(
                404, {"error": "unknown run"}
            )
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self) -> None:  # noqa: N802 - required handler name
        if not self._guarded():
            return
        length = int(self.headers.get("Content-Length", "0") or "0")
        if length > int(_cfg("max_body_bytes", 262144)):
            self._send(413, {"error": "request body too large"})
            return
        if self.path == "/api/run":
            self._handle_run()
        elif self.path.startswith("/api/run/") and self.path.endswith("/decide"):
            self._handle_decide()
        else:
            self._send(404, {"error": "not found"})

    def _handle_run(self) -> None:
        active = sum(1 for s in SESSIONS.values() if s.status in ("running", "awaiting_review"))
        if active >= int(_cfg("max_concurrent_runs", 4)):
            self._send(429, {"error": "too many concurrent runs; try again shortly"})
            return
        body = self._read_json()
        source = str(body.get("source", ""))
        text = str(body.get("text", ""))
        if not source and not text.strip():
            self._send(400, {"error": "provide a source or some text"})
            return
        try:
            run_id = _start_run(source, text)
        except (BadRequest, OSError) as exc:
            self._send(400, {"error": str(exc)})
            return
        self._send(202, {"run_id": run_id})

    def _handle_decide(self) -> None:
        run_id = self.path[len("/api/run/") : -len("/decide")]
        session = SESSIONS.get(run_id)
        if not session:
            self._send(404, {"error": "unknown run"})
            return
        decision = self._read_json()
        if decision.get("decision") not in tuple(d.value for d in HumanDecision):
            self._send(400, {"error": "decision must be approve, reject, or edit"})
            return
        session._decision = decision
        session._event.set()
        self._send(200, {"ok": True})

    def _examples(self) -> list[dict]:
        items = []
        for path in sorted(EXAMPLES_DIR.glob("*.txt")):
            text = path.read_text(encoding="utf-8")
            items.append({"id": path.stem, "name": path.stem, "preview": text[:160].strip()})
        return items

    def _docs(self) -> list[dict]:
        items = []
        for doc_id, title, path in DOCS:
            if path.is_file():
                items.append(
                    {"id": doc_id, "title": title, "markdown": path.read_text(encoding="utf-8")}
                )
        return items

    def log_message(self, *_args: object) -> None:  # keep the console quiet
        pass


def main() -> None:
    global WEB_CFG
    WEB_CFG = _load_yaml(str(ROOT / "config" / "pipeline.yaml")).get("web", {})
    port = int(os.environ.get("API_PORT", "18082"))
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"audit API on http://127.0.0.1:{port}  (runs, examples, run, decide)")
    print(f"session token (X-API-Token): {API_TOKEN}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()


if __name__ == "__main__":
    main()
