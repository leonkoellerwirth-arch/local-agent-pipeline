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
Bind to localhost only; this endpoint runs the pipeline on request.
"""

from __future__ import annotations

import json
import os
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
DECISION_TIMEOUT_S = 900  # if nobody answers the review, fail safe (reject)

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
        answered = self._s._event.wait(timeout=DECISION_TIMEOUT_S)
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


def _start_run(source: str, text: str) -> str:
    pipeline_cfg = _load_yaml(str(ROOT / "config" / "pipeline.yaml"))
    policy_cfg = _load_yaml(str(ROOT / "config" / "policy.yaml"))
    _load_dotenv(ROOT / ".env")

    if source.startswith("example:"):
        content = (EXAMPLES_DIR / f"{source.split(':', 1)[1]}.txt").read_text(encoding="utf-8")
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
        length = int(self.headers.get("Content-Length", "0"))
        if not length:
            return {}
        try:
            return json.loads(self.rfile.read(length).decode("utf-8"))
        except json.JSONDecodeError:
            return {}

    def do_GET(self) -> None:  # noqa: N802 - required handler name
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
        if self.path == "/api/run":
            body = self._read_json()
            source = str(body.get("source", ""))
            text = str(body.get("text", ""))
            if not source and not text.strip():
                self._send(400, {"error": "provide a source or some text"})
                return
            try:
                run_id = _start_run(source, text)
            except OSError as exc:
                self._send(400, {"error": str(exc)})
                return
            self._send(202, {"run_id": run_id})
        elif self.path.startswith("/api/run/") and self.path.endswith("/decide"):
            run_id = self.path[len("/api/run/") : -len("/decide")]
            session = SESSIONS.get(run_id)
            if not session:
                self._send(404, {"error": "unknown run"})
                return
            session._decision = self._read_json()
            session._event.set()
            self._send(200, {"ok": True})
        else:
            self._send(404, {"error": "not found"})

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
    port = int(os.environ.get("API_PORT", "18082"))
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"audit API on http://127.0.0.1:{port}  (runs, examples, run, decide)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()


if __name__ == "__main__":
    main()
