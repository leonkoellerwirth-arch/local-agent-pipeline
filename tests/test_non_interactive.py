"""Non-interactive gate and audit CLI subcommand tests.

All assertions cover governance-critical behaviour:
* A PolicyGate (system actor) auto-rejects escalations and records a
  non_interactive_mode flag — never asking a human.
* The audit CLI subcommand reads a JSONL trail and exits cleanly, emitting
  the run ID and actor names in its output.
"""

from __future__ import annotations

import io

from click.testing import CliRunner
from rich.console import Console

from agent_pipeline.audit import AuditLog
from agent_pipeline.cli import _render_audit_trail, main, run_pipeline
from agent_pipeline.contracts import Actor, HumanDecision, Task
from agent_pipeline.gate import Gate, PolicyGate
from conftest import ScriptedBackend, make_llm

CONTRACT = (
    "Total contract value is EUR 150,000. Contact billing@example-contractor.test. "
    "IBAN: DE89 3704 0044 0532 0130 00."
)


def _run(tmp_path, backend, pipeline_cfg, policy_cfg, *, content=CONTRACT, gate=None):
    audit_cfg = {"log_dir": str(tmp_path / "runs"), "dump_plaintext": False}
    task = Task(run_id="r", input_path="x.txt", content=content)
    with AuditLog("r", audit_cfg) as audit:
        result = run_pipeline(
            task,
            pipeline_cfg=pipeline_cfg,
            policy_cfg=policy_cfg,
            llm=make_llm(backend),
            audit=audit,
            gate=gate or PolicyGate(),
        )
        return result, audit


# ---------------------------------------------------------------------------
# PolicyGate unit tests
# ---------------------------------------------------------------------------


def test_policy_gate_actor_is_system():
    gate = PolicyGate()
    assert gate.actor is Actor.SYSTEM


def test_policy_gate_default_rejects():
    from agent_pipeline.contracts import Action, Decision, Review, WorkResult

    result = WorkResult(
        step_id="s1", action=Action.EXTRACT, output={"ok": True}, confidence=0.9, raw="{}"
    )
    review = Review(step_id="s1", decision=Decision.ESCALATE, confidence=0.5)
    outcome = PolicyGate().request(result, review)
    assert outcome.decision is HumanDecision.REJECT


def test_policy_gate_approve_mode():
    from agent_pipeline.contracts import Action, Decision, Review, WorkResult

    result = WorkResult(
        step_id="s1", action=Action.EXTRACT, output={"ok": True}, confidence=0.9, raw="{}"
    )
    review = Review(step_id="s1", decision=Decision.ESCALATE, confidence=0.5)
    outcome = PolicyGate(HumanDecision.APPROVE).request(result, review)
    assert outcome.decision is HumanDecision.APPROVE


# ---------------------------------------------------------------------------
# Non-interactive pipeline integration
# ---------------------------------------------------------------------------


def test_non_interactive_rejects_escalation(tmp_path, pipeline_cfg, policy_cfg):
    """Contract content triggers escalation; PolicyGate auto-rejects it."""
    backend = ScriptedBackend(plan_actions=("extract",), reviewer_assessment="pass")
    result, audit = _run(tmp_path, backend, pipeline_cfg, policy_cfg, content=CONTRACT)
    assert result.status == "aborted"
    assert result.note == "rejected"


def test_non_interactive_records_system_actor(tmp_path, pipeline_cfg, policy_cfg):
    """The gate_decision audit event must carry actor=system, not actor=human."""
    backend = ScriptedBackend(plan_actions=("extract",), reviewer_assessment="pass")
    _, audit = _run(tmp_path, backend, pipeline_cfg, policy_cfg, content=CONTRACT)
    gate_events = [e for e in audit.events if e.action == "gate_decision"]
    assert gate_events, "expected at least one gate_decision event"
    for ev in gate_events:
        assert ev.actor is Actor.SYSTEM, "non-interactive gate must use actor=system"


def test_non_interactive_records_non_interactive_mode_flag(tmp_path, pipeline_cfg, policy_cfg):
    """non_interactive_mode must appear in policy_flags so the trail is self-explanatory."""
    backend = ScriptedBackend(plan_actions=("extract",), reviewer_assessment="pass")
    _, audit = _run(tmp_path, backend, pipeline_cfg, policy_cfg, content=CONTRACT)
    gate_events = [e for e in audit.events if e.action == "gate_decision"]
    assert gate_events
    for ev in gate_events:
        assert "non_interactive_mode" in ev.policy_flags


def test_interactive_gate_still_records_human_actor(tmp_path, pipeline_cfg, policy_cfg):
    """Regression: the Gate (interactive) must still write actor=human."""
    backend = ScriptedBackend(plan_actions=("extract",), reviewer_assessment="pass")
    human_gate = Gate(
        console=Console(file=io.StringIO()),
        prompt_choice=lambda choices: "approve",
        prompt_text=lambda _label: "approved",
    )
    audit_cfg = {"log_dir": str(tmp_path / "runs"), "dump_plaintext": False}
    task = Task(run_id="r2", input_path="x.txt", content=CONTRACT)
    with AuditLog("r2", audit_cfg) as audit:
        run_pipeline(
            task,
            pipeline_cfg=pipeline_cfg,
            policy_cfg=policy_cfg,
            llm=make_llm(backend),
            audit=audit,
            gate=human_gate,
        )
    gate_events = [e for e in audit.events if e.action == "gate_decision"]
    assert gate_events
    for ev in gate_events:
        assert ev.actor is Actor.HUMAN


# ---------------------------------------------------------------------------
# audit CLI subcommand
# ---------------------------------------------------------------------------


def test_audit_cmd_exits_zero_on_valid_trail(tmp_path, pipeline_cfg, policy_cfg):
    """Run the pipeline to produce a real trail, then audit it."""
    backend = ScriptedBackend()
    audit_cfg = {"log_dir": str(tmp_path / "runs"), "dump_plaintext": False}
    task = Task(run_id="audit-test", input_path="x.txt", content="A benign note.")
    with AuditLog("audit-test", audit_cfg) as audit_log:
        run_pipeline(
            task,
            pipeline_cfg=pipeline_cfg,
            policy_cfg=policy_cfg,
            llm=make_llm(backend),
            audit=audit_log,
            gate=PolicyGate(HumanDecision.APPROVE),
        )
        trail_path = audit_log.path

    runner = CliRunner()
    result = runner.invoke(main, ["audit", str(trail_path)])
    assert result.exit_code == 0, result.output


def test_audit_cmd_output_contains_run_id(tmp_path, pipeline_cfg, policy_cfg):
    backend = ScriptedBackend()
    audit_cfg = {"log_dir": str(tmp_path / "runs"), "dump_plaintext": False}
    task = Task(run_id="my-run-42", input_path="x.txt", content="A benign note.")
    with AuditLog("my-run-42", audit_cfg) as audit_log:
        run_pipeline(
            task,
            pipeline_cfg=pipeline_cfg,
            policy_cfg=policy_cfg,
            llm=make_llm(backend),
            audit=audit_log,
            gate=PolicyGate(HumanDecision.APPROVE),
        )
        trail_path = audit_log.path

    runner = CliRunner()
    result = runner.invoke(main, ["audit", str(trail_path)])
    assert "my-run-42" in result.output


def test_audit_cmd_output_contains_actors(tmp_path, pipeline_cfg, policy_cfg):
    backend = ScriptedBackend()
    audit_cfg = {"log_dir": str(tmp_path / "runs"), "dump_plaintext": False}
    task = Task(run_id="actor-check", input_path="x.txt", content="A benign note.")
    with AuditLog("actor-check", audit_cfg) as audit_log:
        run_pipeline(
            task,
            pipeline_cfg=pipeline_cfg,
            policy_cfg=policy_cfg,
            llm=make_llm(backend),
            audit=audit_log,
            gate=PolicyGate(HumanDecision.APPROVE),
        )
        trail_path = audit_log.path

    runner = CliRunner()
    result = runner.invoke(main, ["audit", str(trail_path)])
    assert "planner" in result.output
    assert "worker" in result.output
    assert "reviewer" in result.output


def test_render_audit_trail_empty_events(capsys):
    """_render_audit_trail should handle an empty event list gracefully."""
    buf = io.StringIO()
    console = Console(file=buf, highlight=False)
    _render_audit_trail(console, [])
    output = buf.getvalue()
    assert "No events" in output
