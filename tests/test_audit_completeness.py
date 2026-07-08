"""The core guarantee: no pipeline step happens without an audit event."""

from __future__ import annotations

import io

from rich.console import Console

from agent_pipeline.audit import AuditLog, read_events
from agent_pipeline.cli import run_pipeline
from agent_pipeline.contracts import Actor, Task
from agent_pipeline.gate import Gate
from conftest import ScriptedBackend, make_llm


def _silent_gate() -> Gate:
    return Gate(
        console=Console(file=io.StringIO()),
        prompt_choice=lambda choices: "approve",
        prompt_text=lambda label: "ok",
    )


def _run(tmp_path, backend, pipeline_cfg, policy_cfg):
    audit_cfg = {"log_dir": str(tmp_path / "runs"), "dump_plaintext": False}
    task = Task(run_id="testrun", input_path="x.txt", content="A benign internal note.")
    with AuditLog("testrun", audit_cfg) as audit:
        result = run_pipeline(
            task,
            pipeline_cfg=pipeline_cfg,
            policy_cfg=policy_cfg,
            llm=make_llm(backend),
            audit=audit,
            gate=_silent_gate(),
        )
        return result, audit


def test_every_step_has_worker_and_reviewer_events(tmp_path, pipeline_cfg, policy_cfg):
    result, audit = _run(tmp_path, ScriptedBackend(), pipeline_cfg, policy_cfg)

    executed = {
        e.step_id for e in audit.events if e.actor is Actor.WORKER and e.action == "execute"
    }
    reviewed = {e.step_id for e in audit.events if e.actor is Actor.REVIEWER}
    planned = {s.step_id for s in result.plan.steps}

    assert planned  # sanity: the plan is non-empty
    assert executed == planned, "every planned step must be executed and audited"
    assert reviewed == planned, "every executed step must be reviewed and audited"


def test_run_is_bracketed_by_start_and_complete(tmp_path, pipeline_cfg, policy_cfg):
    _, audit = _run(tmp_path, ScriptedBackend(), pipeline_cfg, policy_cfg)
    actions = [(e.actor, e.action) for e in audit.events]
    assert actions[0] == (Actor.SYSTEM, "run_start")
    assert actions[-1] == (Actor.SYSTEM, "run_complete")
    assert any(a == (Actor.PLANNER, "plan") for a in actions)


def test_model_events_carry_hashes_not_plaintext(tmp_path, pipeline_cfg, policy_cfg):
    _, audit = _run(tmp_path, ScriptedBackend(), pipeline_cfg, policy_cfg)
    model_events = [e for e in audit.events if e.model is not None]
    assert model_events
    for event in model_events:
        assert event.prompt_hash and event.prompt_hash.startswith("sha256:")
        assert event.output_hash and event.output_hash.startswith("sha256:")


def test_trail_is_written_and_reloadable(tmp_path, pipeline_cfg, policy_cfg):
    _, audit = _run(tmp_path, ScriptedBackend(), pipeline_cfg, policy_cfg)
    reloaded = read_events(audit.path)
    assert len(reloaded) == len(audit.events)


def test_plaintext_not_dumped_by_default(tmp_path, pipeline_cfg, policy_cfg):
    _run(tmp_path, ScriptedBackend(), pipeline_cfg, policy_cfg)
    assert not (tmp_path / "runs" / "dumps").exists()
