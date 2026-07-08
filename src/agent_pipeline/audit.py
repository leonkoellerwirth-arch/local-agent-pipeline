"""Structured audit logging — one JSONL event per pipeline transition.

The audit log is the contract this project is really about: no step happens
without a line recording who did it, with which model, how long it took, and
what was decided. Prompts and outputs are stored as short hashes so a trail can
be shared safely; the full text is written only when ``dump_plaintext`` is on,
into a separate directory (see the README's privacy note).

The JSONL schema is kept compatible with the ``log_analyzer`` in the sibling
``agentic-ai-governance-toolkit``.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import TracebackType

from .contracts import Actor, AuditEvent
from .llm import StageTrace


def content_hash(text: str | None) -> str | None:
    """Short, stable hash of a prompt or output (``None`` passes through)."""
    if text is None:
        return None
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


class AuditLog:
    """Writes audit events to ``<log_dir>/<run_id>.jsonl`` and keeps them in memory."""

    def __init__(self, run_id: str, config: dict) -> None:
        self.run_id = run_id
        self.events: list[AuditEvent] = []
        self._dump_plaintext = bool(config.get("dump_plaintext", False))
        self._seq = 0

        log_dir = Path(config.get("log_dir", "runs"))
        log_dir.mkdir(parents=True, exist_ok=True)
        self._path = log_dir / f"{run_id}.jsonl"
        self._file = self._path.open("w", encoding="utf-8")

        self._dump_dir = Path(config.get("dump_dir", "runs/dumps")) / run_id

    @property
    def path(self) -> Path:
        """Path of the JSONL trail for this run."""
        return self._path

    def record(self, event: AuditEvent) -> AuditEvent:
        """Append one already-built event to the trail."""
        self._file.write(event.model_dump_json() + "\n")
        self._file.flush()
        self.events.append(event)
        return event

    def record_event(
        self,
        actor: Actor,
        action: str,
        *,
        step_id: str | None = None,
        decision: str | None = None,
        confidence: float | None = None,
        policy_flags: list[str] | None = None,
    ) -> AuditEvent:
        """Record a non-model event (human decision, discarded step, system note)."""
        return self.record(
            AuditEvent(
                run_id=self.run_id,
                step_id=step_id,
                actor=actor,
                action=action,
                decision=decision,
                confidence=confidence,
                policy_flags=policy_flags or [],
            )
        )

    def record_stage(
        self,
        actor: Actor,
        action: str,
        trace: StageTrace,
        *,
        step_id: str | None = None,
        decision: str | None = None,
        confidence: float | None = None,
        policy_flags: list[str] | None = None,
    ) -> AuditEvent:
        """Record a model-backed stage, hashing (and optionally dumping) its text."""
        self._maybe_dump(actor, action, step_id, trace)
        return self.record(
            AuditEvent(
                run_id=self.run_id,
                step_id=step_id,
                actor=actor,
                action=action,
                model=trace.model,
                prompt_hash=content_hash(trace.prompt),
                output_hash=content_hash(trace.output),
                decision=decision,
                confidence=confidence,
                latency_ms=trace.latency_ms,
                policy_flags=policy_flags or [],
            )
        )

    def _maybe_dump(
        self, actor: Actor, action: str, step_id: str | None, trace: StageTrace
    ) -> None:
        if not self._dump_plaintext:
            return
        self._dump_dir.mkdir(parents=True, exist_ok=True)
        self._seq += 1
        name = f"{self._seq:02d}-{step_id or 'run'}-{actor.value}-{action}.txt"
        (self._dump_dir / name).write_text(
            f"--- PROMPT ---\n{trace.prompt}\n\n--- OUTPUT ---\n{trace.output}\n",
            encoding="utf-8",
        )

    def close(self) -> None:
        """Close the underlying file."""
        if not self._file.closed:
            self._file.close()

    def __enter__(self) -> AuditLog:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()


def read_events(path: str | Path) -> list[AuditEvent]:
    """Read a JSONL trail back into ``AuditEvent`` objects (used by tests and tools)."""
    events = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if line.strip():
            events.append(AuditEvent.model_validate(json.loads(line)))
    return events
