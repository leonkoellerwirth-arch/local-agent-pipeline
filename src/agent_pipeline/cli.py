"""Command-line entry point and the pipeline orchestrator.

``run_pipeline`` is the whole flow in one readable function: plan → work →
review → (gate) → output, with an audit event at every transition. It takes its
collaborators as arguments so a test can drive the entire escalation flow with a
faked model and canned gate answers — no Ollama, no terminal.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import click
import yaml
from rich.console import Console

from .audit import AuditLog
from .contracts import Actor, Decision, HumanDecision, Plan, Task, WorkResult
from .gate import Gate
from .llm import LLMClient
from .planner import Planner
from .reviewer import Reviewer
from .worker import Worker, WorkerError


@dataclass
class PipelineResult:
    """The outcome of a run: what was accepted and how it ended."""

    run_id: str
    status: str  # "completed" | "aborted"
    plan: Plan
    results: list[WorkResult] = field(default_factory=list)
    note: str = ""


def _new_run_id() -> str:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
    return f"{stamp}-{uuid.uuid4().hex[:6]}"


def run_pipeline(
    task: Task,
    *,
    pipeline_cfg: dict,
    policy_cfg: dict,
    llm: LLMClient,
    audit: AuditLog,
    gate: Gate,
) -> PipelineResult:
    """Run one document through the pipeline, auditing every transition."""
    models = pipeline_cfg["models"]
    planner = Planner(llm, models["planner"], policy_cfg["action_space"])
    worker = Worker(llm, models["worker"], int(pipeline_cfg["llm"].get("max_retries", 1)))
    reviewer = Reviewer(llm, models["reviewer"], policy_cfg)

    audit.record_event(Actor.SYSTEM, "run_start")

    # --- Plan -------------------------------------------------------------
    plan, discarded, plan_trace = planner.make_plan(task)
    audit.record_stage(Actor.PLANNER, "plan", plan_trace)
    for action in discarded:
        audit.record_event(
            Actor.PLANNER,
            "discard_step",
            decision=action,
            policy_flags=["action_not_in_space"],
        )
    if not plan.steps:
        audit.record_event(Actor.SYSTEM, "abort", decision="no_valid_plan")
        return PipelineResult(task.run_id, "aborted", plan, note="planner produced no valid steps")

    # --- Work → Review → (Gate) per step ---------------------------------
    accepted: list[WorkResult] = []
    for step in plan.steps:
        try:
            result, work_trace = worker.run_step(step, task)
        except WorkerError as exc:
            audit.record_stage(  # audit the failure, then stop
                Actor.WORKER, "execute_failed", _empty_trace(models["worker"]), step_id=step.step_id
            )
            audit.record_event(Actor.SYSTEM, "abort", step_id=step.step_id, decision="worker_error")
            return PipelineResult(task.run_id, "aborted", plan, accepted, note=str(exc))

        audit.record_stage(
            Actor.WORKER, "execute", work_trace, step_id=step.step_id, confidence=result.confidence
        )

        review, review_trace = reviewer.review(result, task)
        audit.record_stage(
            Actor.REVIEWER,
            "review",
            review_trace,
            step_id=step.step_id,
            decision=review.decision.value,
            confidence=review.confidence,
            policy_flags=review.policy_flags,
        )

        outcome = _resolve(step, result, review, gate, audit)
        if outcome is None:
            return PipelineResult(task.run_id, "aborted", plan, accepted, note="rejected")
        accepted.append(outcome)

    audit.record_event(Actor.SYSTEM, "run_complete", decision="completed")
    return PipelineResult(task.run_id, "completed", plan, accepted)


def _resolve(step, result, review, gate, audit) -> WorkResult | None:
    """Apply the reviewer decision. Returns the accepted result, or None to abort."""
    if review.decision is Decision.PASS:
        return result
    if review.decision is Decision.REJECT:
        audit.record_event(Actor.SYSTEM, "abort", step_id=step.step_id, decision="rejected")
        return None

    # Decision.ESCALATE → human gate
    gate_outcome = gate.request(result, review)
    audit.record_event(
        Actor.HUMAN,
        "gate_decision",
        step_id=step.step_id,
        decision=gate_outcome.decision.value,
        policy_flags=review.policy_flags,
    )
    if gate_outcome.decision is HumanDecision.REJECT:
        return None
    return gate_outcome.result  # approve or edit


def _empty_trace(model: str):
    from .llm import StageTrace

    return StageTrace(model=model, prompt="", output="", latency_ms=0)


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------
def _load_yaml(path: str) -> dict:
    return yaml.safe_load(Path(path).read_text(encoding="utf-8"))


@click.group()
def main() -> None:
    """agent-pipeline — a minimal, auditable, local multi-agent pipeline."""


@main.command()
@click.option("--input", "input_path", required=True, type=click.Path(exists=True, dir_okay=False))
@click.option("--config", "config_path", default="config/pipeline.yaml", show_default=True)
@click.option("--policy", "policy_path", default="config/policy.yaml", show_default=True)
def run(input_path: str, config_path: str, policy_path: str) -> None:
    """Run a document through the pipeline."""
    console = Console()
    pipeline_cfg = _load_yaml(config_path)
    policy_cfg = _load_yaml(policy_path)

    run_id = _new_run_id()
    task = Task(
        run_id=run_id,
        input_path=input_path,
        content=Path(input_path).read_text(encoding="utf-8"),
    )

    llm = LLMClient(pipeline_cfg["llm"])
    gate = Gate(console)
    with AuditLog(run_id, pipeline_cfg["audit"]) as audit:
        result = run_pipeline(
            task,
            pipeline_cfg=pipeline_cfg,
            policy_cfg=policy_cfg,
            llm=llm,
            audit=audit,
            gate=gate,
        )
        _print_summary(console, result, audit.path)


def _print_summary(console: Console, result: PipelineResult, audit_path: Path) -> None:
    colour = "green" if result.status == "completed" else "red"
    console.print(f"\n[bold {colour}]Run {result.run_id}: {result.status}[/bold {colour}]")
    if result.note:
        console.print(f"  note: {result.note}")
    for item in result.results:
        console.print(f"  [cyan]{item.action.value}[/cyan] → {item.output}")
    console.print(f"  audit trail: [dim]{audit_path}[/dim]")


if __name__ == "__main__":
    main()
