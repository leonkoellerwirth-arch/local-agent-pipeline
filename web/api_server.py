"""A tiny read-only API for the dashboard.

Serves the audit trails as JSON so the Vite frontend can render them. Built on
the standard library only — no web framework, no Docker — in keeping with the
rest of the project. The Vite dev server proxies ``/api`` and ``/health`` here
(see ``web/vite.config.ts``).

Run via the project's virtualenv so ``agent_pipeline`` is importable:
    .venv/bin/python web/api_server.py            # port 18082 (or $API_PORT)
"""

from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from agent_pipeline.export import collect

ROOT = Path(__file__).resolve().parents[1]
# Real runs plus the committed demo trails, so the dashboard shows data on a
# fresh clone. Override the run directory with RUNS_DIR.
RUN_DIRS = [Path(os.environ.get("RUNS_DIR", ROOT / "runs")), ROOT / "examples" / "expected-outputs"]


class Handler(BaseHTTPRequestHandler):
    def _send(self, status: int, payload: object) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802 - required BaseHTTPRequestHandler name
        if self.path == "/health":
            self._send(200, {"status": "ok"})
        elif self.path.startswith("/api/runs"):
            self._send(200, collect(RUN_DIRS))
        else:
            self._send(404, {"error": "not found"})

    def log_message(self, *_args: object) -> None:  # keep the console quiet
        pass


def main() -> None:
    port = int(os.environ.get("API_PORT", "18082"))
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"audit API on http://127.0.0.1:{port}  (GET /api/runs, /health)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()


if __name__ == "__main__":
    main()
