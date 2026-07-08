"""Data contracts for the pipeline.

These Pydantic models are the shared vocabulary of every stage. A step becomes
a ``PlanStep``, its output a ``WorkResult``, its verdict a ``Review``, and every
transition an ``AuditEvent``. Because each stage speaks in validated models, a
malformed hand-off fails loudly at the boundary instead of leaking downstream.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, Field


def _utcnow() -> datetime:
    """Timezone-aware UTC timestamp (naive ``utcnow`` is deprecated in 3.12+)."""
    return datetime.now(UTC)


class Action(StrEnum):
    """The allowed action space for a worker step.

    The planner may only emit steps drawn from this set; anything else is
    discarded and logged. Keeping the space small and explicit is what makes
    the planner's output auditable rather than open-ended.
    """

    CLASSIFY = "classify"
    EXTRACT = "extract"
    SUMMARIZE = "summarize"


class Actor(StrEnum):
    """Who performed an audited action."""

    PLANNER = "planner"
    WORKER = "worker"
    REVIEWER = "reviewer"
    HUMAN = "human"
    SYSTEM = "system"


class Decision(StrEnum):
    """The reviewer's verdict on a worker result."""

    PASS = "pass"
    ESCALATE = "escalate"
    REJECT = "reject"


class HumanDecision(StrEnum):
    """The choice a human makes at the gate."""

    APPROVE = "approve"
    REJECT = "reject"
    EDIT = "edit"


class Task(BaseModel):
    """A single document run through the pipeline."""

    run_id: str = Field(..., description="Unique id for this pipeline run.")
    input_path: str = Field(..., description="Source path of the document.")
    content: str = Field(..., description="Raw document text.")
    created_at: datetime = Field(default_factory=_utcnow)


class PlanStep(BaseModel):
    """One typed step in the plan. ``action`` is constrained to the space."""

    step_id: str
    action: Action
    description: str = Field(..., description="Why this step exists, in one line.")


class Plan(BaseModel):
    """An ordered list of validated steps (at most five)."""

    steps: list[PlanStep] = Field(default_factory=list, max_length=5)


class WorkResult(BaseModel):
    """The structured output of a single worker step."""

    step_id: str
    action: Action
    output: dict = Field(..., description="Structured, action-specific payload.")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Worker self-estimate.")
    raw: str = Field(..., description="Raw model text, kept for the audit trail.")


class Review(BaseModel):
    """The reviewer's independent judgement of a ``WorkResult``."""

    step_id: str
    decision: Decision
    confidence: float = Field(..., ge=0.0, le=1.0)
    reasons: list[str] = Field(default_factory=list)
    policy_flags: list[str] = Field(
        default_factory=list, description="Named triggers that fired, e.g. 'pii_detected'."
    )


class AuditEvent(BaseModel):
    """One line in the audit trail. Every pipeline transition emits exactly one.

    Prompts and outputs are stored as hashes here; the optional plaintext dump
    lives in a separate, configurable directory (see the README's privacy note).

    ``prev_hash`` and ``entry_hash`` chain the events together: each event's
    hash covers its own content *and* the previous event's hash, so the trail is
    append-only and tamper-evident. Editing, deleting, or reordering any event
    breaks the chain from that point on (verified by ``audit.verify_chain``).
    These are populated by ``AuditLog``; they are ``None`` on a free-standing
    event that has not been written to a log.
    """

    timestamp: datetime = Field(default_factory=_utcnow)
    run_id: str
    step_id: str | None = None
    actor: Actor
    action: str = Field(..., description="Free-form action label, e.g. 'plan' or 'review'.")
    model: str | None = Field(default=None, description="Model that produced this, if any.")
    prompt_hash: str | None = None
    output_hash: str | None = None
    decision: str | None = None
    confidence: float | None = None
    latency_ms: int | None = None
    policy_flags: list[str] = Field(default_factory=list)
    prev_hash: str | None = Field(default=None, description="entry_hash of the previous event.")
    entry_hash: str | None = Field(default=None, description="Hash of this event + prev_hash.")
