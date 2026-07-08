"""End-to-end flow: pass, escalate-then-gate, planner filtering, worker failure."""

from __future__ import annotations

import io

from rich.console import Console

from agent_pipeline.audit import AuditLog
from agent_pipeline.cli import run_pipeline
from agent_pipeline.contracts import Actor, Task
from agent_pipeline.gate import Gate
from conftest import ScriptedBackend, make_llm

CONTRACT = "Total contract value is EUR 150,000. Contact billing@example-contractor.test."
BENIGN = "A short internal note with no sensitive data."


def _gate(choice: str) -> Gate:
    return Gate(
        console=Console(file=io.StringIO()),
        prompt_choice=lambda choices: choice,
        prompt_text=lambda label: "human reason",
    )


def _run(tmp_path, backend, pipeline_cfg, policy_cfg, *, content=BENIGN, gate=None):
    audit_cfg = {"log_dir": str(tmp_path / "runs"), "dump_plaintext": False}
    task = Task(run_id="r", input_path="x.txt", content=content)
    with AuditLog("r", audit_cfg) as audit:
        result = run_pipeline(
            task,
            pipeline_cfg=pipeline_cfg,
            policy_cfg=policy_cfg,
            llm=make_llm(backend),
            audit=audit,
            gate=gate or _gate("approve"),
        )
        return result, audit


def test_happy_path_completes_with_all_results(tmp_path, pipeline_cfg, policy_cfg):
    result, _ = _run(tmp_path, ScriptedBackend(), pipeline_cfg, policy_cfg)
    assert result.status == "completed"
    assert len(result.results) == len(result.plan.steps) == 3


def test_escalation_then_gate_approve_completes(tmp_path, pipeline_cfg, policy_cfg):
    # Contract content fires heuristics regardless of the model's assessment.
    backend = ScriptedBackend(plan_actions=("extract",), reviewer_assessment="pass")
    result, audit = _run(
        tmp_path, backend, pipeline_cfg, policy_cfg, content=CONTRACT, gate=_gate("approve")
    )
    assert result.status == "completed"
    assert any(e.actor is Actor.HUMAN and e.action == "gate_decision" for e in audit.events)


def test_escalation_then_gate_reject_aborts(tmp_path, pipeline_cfg, policy_cfg):
    backend = ScriptedBackend(plan_actions=("extract",))
    result, _ = _run(
        tmp_path, backend, pipeline_cfg, policy_cfg, content=CONTRACT, gate=_gate("reject")
    )
    assert result.status == "aborted"
    assert result.note == "rejected"


def test_planner_discards_actions_outside_space(tmp_path, pipeline_cfg, policy_cfg):
    backend = ScriptedBackend(plan_actions=("classify", "delete", "summarize"))
    result, audit = _run(tmp_path, backend, pipeline_cfg, policy_cfg)
    # "delete" is not in the action space: it is dropped, the rest survive.
    assert [s.action.value for s in result.plan.steps] == ["classify", "summarize"]
    discards = [e for e in audit.events if e.action == "discard_step"]
    assert len(discards) == 1
    assert discards[0].policy_flags == ["action_not_in_space"]


def test_worker_failure_aborts_run(tmp_path, pipeline_cfg, policy_cfg):
    backend = ScriptedBackend(plan_actions=("classify",), worker_bad_forever=True)
    result, audit = _run(tmp_path, backend, pipeline_cfg, policy_cfg)
    assert result.status == "aborted"
    assert any(e.action == "abort" and e.decision == "worker_error" for e in audit.events)


def test_worker_retry_recovers_after_one_bad_response(tmp_path, pipeline_cfg, policy_cfg):
    backend = ScriptedBackend(plan_actions=("classify",), worker_bad_first=True)
    result, _ = _run(tmp_path, backend, pipeline_cfg, policy_cfg)
    assert result.status == "completed"
    assert len(result.results) == 1
