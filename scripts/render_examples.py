"""Regenerate the committed example artifacts in ``examples/expected-outputs/``.

Run from the repo root: ``python scripts/render_examples.py``.

This drives the real pipeline over the two example documents with a **mocked**
model (the same trick the test suite uses), so the artifacts are reproducible
without Ollama. The policy flags, escalation decision, and hash chain are all
genuine — only the model's free-text output is canned, and that text is stored
only as a hash anyway. It produces:

* ``sample-report.jsonl`` / ``sample-contract.jsonl`` — full audit trails.
* ``sample-contract-audit.svg`` — the ``agent-pipeline audit`` render.
* ``sample-contract-gate.svg`` — the human-review gate panel.
"""

from __future__ import annotations

import json
from pathlib import Path

import yaml
from rich.console import Console

from agent_pipeline.audit import AuditLog
from agent_pipeline.cli import _render_audit_trail, run_pipeline
from agent_pipeline.contracts import Review, Task, WorkResult
from agent_pipeline.gate import Gate, GateOutcome
from agent_pipeline.llm import LLMClient

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "examples" / "expected-outputs"
CONFIG: dict = {
    "models": {"planner": "llama3.2", "worker": "llama3.2", "reviewer": "llama3.1"},
    "llm": {"max_retries": 1},
    "audit": {"log_dir": str(OUT), "dump_plaintext": False},
}
POLICY = yaml.safe_load((ROOT / "config" / "policy.yaml").read_text())


def fake_backend(model: str, prompt: str, json_mode: bool) -> str:
    """Deterministic canned responses, routed by stage markers in the prompt."""
    if "You plan how to process" in prompt:
        steps = [{"action": a, "description": f"do {a}"} for a in ("classify", "extract")]
        return json.dumps({"steps": steps})
    if "You are a reviewer" in prompt:
        return json.dumps({"assessment": "pass", "confidence": 0.88, "reasons": ["looks faithful"]})
    if "Classify the document" in prompt:
        return json.dumps({"label": "contract", "confidence": 0.9})
    if "Extract key facts" in prompt:
        return json.dumps({"fields": {"parties": 2, "term_months": 12}, "confidence": 0.9})
    return json.dumps({"summary": "A short summary.", "confidence": 0.9})


class _RecordingGate(Gate):
    """A gate that approves and remembers the first escalation it saw (for rendering)."""

    def __init__(self, console: Console) -> None:
        super().__init__(
            console=console,
            prompt_choice=lambda choices: "approve",
            prompt_text=lambda label: "reviewed; values confirmed with counterparty",
        )
        self.captured: tuple[WorkResult, Review] | None = None

    def request(self, result: WorkResult, review: Review) -> GateOutcome:
        if self.captured is None:
            self.captured = (result, review)
        return super().request(result, review)


def run_example(name: str, gate: Gate) -> AuditLog:
    content = (ROOT / "examples" / f"{name}.txt").read_text(encoding="utf-8")
    task = Task(run_id=name, input_path=f"examples/{name}.txt", content=content)
    llm = LLMClient({"host": "mock"}, backend=fake_backend)
    with AuditLog(name, CONFIG["audit"]) as audit:
        run_pipeline(task, pipeline_cfg=CONFIG, policy_cfg=POLICY, llm=llm, audit=audit, gate=gate)
    return audit


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)

    # Benign report: passes clean, no gate needed.
    run_example("sample-report", Gate(console=Console(quiet=True)))

    # Contract: escalates; capture the gate view and render both SVGs.
    gate = _RecordingGate(Console(quiet=True))
    contract = run_example("sample-contract", gate)

    audit_console = Console(record=True, width=118)
    _render_audit_trail(audit_console, contract.events)
    audit_console.save_svg(str(OUT / "sample-contract-audit.svg"), title="agent-pipeline audit")

    if gate.captured is not None:
        result, review = gate.captured
        gate_console = Console(record=True, width=90)
        Gate(
            console=gate_console,
            prompt_choice=lambda choices: "approve",
            prompt_text=lambda label: "reviewed; values confirmed with counterparty",
        ).request(result, review)
        gate_console.save_svg(str(OUT / "sample-contract-gate.svg"), title="human review gate")

    print(f"Wrote artifacts to {OUT}")


if __name__ == "__main__":
    main()
