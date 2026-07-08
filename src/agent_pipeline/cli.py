"""Command-line entry point and the pipeline orchestrator.

``run_pipeline`` is the whole flow in one readable function: plan → work →
review → (gate) → output, with an audit event at every transition. It takes its
collaborators as arguments so a test can drive the entire escalation flow with a
faked model and canned gate answers — no Ollama, no terminal.

CLI subcommands
---------------
``agent-pipeline run``   — run a document through the pipeline.
``agent-pipeline audit`` — read a JSONL trail and print a rich summary table,
                           or verify its tamper-evident hash chain (--verify).
"""

from __future__ import annotations

import os
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import click
import yaml
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from .audit import AuditLog, read_events, verify_chain
from .contracts import (
    Actor,
    AuditEvent,
    Decision,
    HumanDecision,
    Plan,
    PlanStep,
    Review,
    Task,
    WorkResult,
)
from .gate import BaseGate, Gate, PolicyGate
from .llm import LLMClient, LLMError, StageTrace
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
    gate: BaseGate,
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


def _resolve(
    step: PlanStep,
    result: WorkResult,
    review: Review,
    gate: BaseGate,
    audit: AuditLog,
) -> WorkResult | None:
    """Apply the reviewer decision. Returns the accepted result, or None to abort."""
    if review.decision is Decision.PASS:
        return result
    if review.decision is Decision.REJECT:
        audit.record_event(Actor.SYSTEM, "abort", step_id=step.step_id, decision="rejected")
        return None

    # Decision.ESCALATE → gate (human or policy)
    gate_outcome = gate.request(result, review)
    flags = list(review.policy_flags)
    if gate.actor is Actor.SYSTEM:
        # Record that a system policy — not a person — made this decision.
        flags.append("non_interactive_mode")
    audit.record_event(
        gate.actor,
        "gate_decision",
        step_id=step.step_id,
        decision=gate_outcome.decision.value,
        policy_flags=flags,
    )
    if gate_outcome.decision is HumanDecision.REJECT:
        return None
    return gate_outcome.result  # approve or edit


def _empty_trace(model: str) -> StageTrace:
    return StageTrace(model=model, prompt="", output="", latency_ms=0)


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------
def _load_yaml(path: str) -> dict:
    return yaml.safe_load(Path(path).read_text(encoding="utf-8"))


def _load_dotenv(path: Path) -> None:
    """Load ``KEY=VALUE`` lines from a .env file into the environment.

    Existing environment variables win, so real secrets always override the
    file. Only needed when a role is routed to an external provider; local runs
    never read a key.
    """
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


@click.group()
def main() -> None:
    """agent-pipeline — a minimal, auditable, local multi-agent pipeline."""


@main.command()
@click.option("--input", "input_path", required=True, type=click.Path(exists=True, dir_okay=False))
@click.option("--config", "config_path", default="config/pipeline.yaml", show_default=True)
@click.option("--policy", "policy_path", default="config/policy.yaml", show_default=True)
@click.option(
    "--non-interactive",
    is_flag=True,
    default=False,
    help=(
        "Auto-reject any escalation without prompting. "
        "Intended for CI where a human cannot respond. "
        "The audit trail records actor=system and a non_interactive_mode flag."
    ),
)
def run(input_path: str, config_path: str, policy_path: str, non_interactive: bool) -> None:
    """Run a document through the pipeline."""
    console = Console()
    _load_dotenv(Path(".env"))  # make any external-provider keys available
    pipeline_cfg = _load_yaml(config_path)
    policy_cfg = _load_yaml(policy_path)

    run_id = _new_run_id()
    task = Task(
        run_id=run_id,
        input_path=input_path,
        content=Path(input_path).read_text(encoding="utf-8"),
    )

    llm = LLMClient(pipeline_cfg["llm"])
    gate: BaseGate = PolicyGate() if non_interactive else Gate(console)
    with AuditLog(run_id, pipeline_cfg["audit"]) as audit:
        try:
            result = run_pipeline(
                task,
                pipeline_cfg=pipeline_cfg,
                policy_cfg=policy_cfg,
                llm=llm,
                audit=audit,
                gate=gate,
            )
        except LLMError as exc:
            console.print(f"[red]Model call failed:[/red] {exc}")
            raise SystemExit(1) from exc
        _print_summary(console, result, audit.path)


def _print_summary(console: Console, result: PipelineResult, audit_path: Path) -> None:
    colour = "green" if result.status == "completed" else "red"
    console.print(f"\n[bold {colour}]Run {result.run_id}: {result.status}[/bold {colour}]")
    if result.note:
        console.print(f"  note: {result.note}")
    for item in result.results:
        console.print(f"  [cyan]{item.action.value}[/cyan] → {item.output}")
    console.print(f"  audit trail: [dim]{audit_path}[/dim]")


# --------------------------------------------------------------------------
# audit subcommand
# --------------------------------------------------------------------------

_ACTOR_STYLE: dict[str, str] = {
    "planner": "blue",
    "worker": "cyan",
    "reviewer": "magenta",
    "human": "yellow",
    "system": "dim",
}

_DECISION_STYLE: dict[str, str] = {
    "pass": "green",
    "completed": "green",
    "approve": "green",
    "escalate": "yellow",
    "reject": "red",
    "rejected": "red",
    "aborted": "red",
    "worker_error": "red",
    "no_valid_plan": "red",
}


def _styled(value: str | None, mapping: dict[str, str], default: str = "") -> str:
    """Wrap ``value`` in a Rich markup tag from ``mapping``, or return dimmed dash."""
    if not value:
        return f"[dim]{default or '—'}[/dim]"
    style = mapping.get(value.lower())
    return f"[{style}]{value}[/{style}]" if style else value


def _render_audit_trail(console: Console, events: list[AuditEvent]) -> None:
    """Print a rich summary panel and event table for a JSONL audit trail."""
    if not events:
        console.print("[yellow]No events found in trail.[/yellow]")
        return

    run_id = events[0].run_id
    t0 = events[0].timestamp
    t_last = events[-1].timestamp
    elapsed_s = (t_last - t0).total_seconds()

    # Final run decision from the last event that has one.
    final_decision = next((e.decision for e in reversed(events) if e.decision), None)

    # Aggregate all policy flags across the run.
    all_flags: list[str] = []
    for e in events:
        all_flags.extend(e.policy_flags)
    unique_flags = sorted(set(all_flags))

    # Unique step IDs (preserving encounter order).
    seen: dict[str, None] = {}
    for e in events:
        if e.step_id:
            seen[e.step_id] = None
    step_ids = list(seen)

    # Summary panel
    flags_line = ", ".join(unique_flags) if unique_flags else "none"
    steps_line = ", ".join(step_ids) if step_ids else "none"
    status_colour = _DECISION_STYLE.get((final_decision or "").lower(), "")
    status_markup = (
        f"[{status_colour}]{final_decision}[/{status_colour}]"
        if status_colour
        else (final_decision or "—")
    )
    summary_body = (
        f"[bold]Run:[/bold] {run_id}\n"
        f"[bold]Started:[/bold] {t0.strftime('%Y-%m-%d %H:%M:%S UTC')}  "
        f"[bold]Elapsed:[/bold] {elapsed_s:.1f} s\n"
        f"[bold]Status:[/bold] {status_markup}\n"
        f"[bold]Steps:[/bold] {steps_line}\n"
        f"[bold]Policy flags:[/bold] {flags_line}"
    )
    console.print(Panel(summary_body, title="Audit summary", border_style="blue"))

    # Event table
    table = Table(show_header=True, header_style="bold", box=None, padding=(0, 1))
    table.add_column("#", style="dim", justify="right", no_wrap=True)
    table.add_column("Time (UTC)", no_wrap=True)
    table.add_column("Actor", no_wrap=True)
    table.add_column("Action", no_wrap=True)
    table.add_column("Step", no_wrap=True)
    table.add_column("Model", no_wrap=True)
    table.add_column("Decision", no_wrap=True)
    table.add_column("Flags")
    table.add_column("ms", justify="right", no_wrap=True)

    for i, ev in enumerate(events, 1):
        ts = ev.timestamp.strftime("%H:%M:%S.") + f"{ev.timestamp.microsecond // 1000:03d}"
        actor = _styled(ev.actor.value if ev.actor else None, _ACTOR_STYLE)
        decision = _styled(ev.decision, _DECISION_STYLE)
        flags = ", ".join(ev.policy_flags) if ev.policy_flags else ""
        latency = str(ev.latency_ms) if ev.latency_ms is not None else ""
        table.add_row(
            str(i),
            ts,
            actor,
            ev.action,
            ev.step_id or "",
            ev.model or "",
            decision,
            flags,
            latency,
        )

    console.print(table)


@main.command(name="audit")
@click.argument("trail", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option(
    "--verify",
    is_flag=True,
    default=False,
    help="Verify the tamper-evident hash chain instead of printing the summary.",
)
def audit_cmd(trail: Path, verify: bool) -> None:
    """Print a rich summary of a JSONL audit trail, or verify its hash chain.

    TRAIL is the path to a run's .jsonl file (e.g. runs/20240101T120000-abc123.jsonl).
    With --verify, exits non-zero if the chain has been edited, truncated, or
    reordered.
    """
    console = Console()
    events = read_events(trail)
    if verify:
        result = verify_chain(events)
        if result.ok:
            console.print(f"[green]✓ Audit chain intact[/green] — {result.reason}")
        else:
            console.print(f"[red]✗ Audit chain BROKEN[/red] — {result.reason}")
            raise SystemExit(1)
        return
    _render_audit_trail(console, events)


if __name__ == "__main__":
    main()
