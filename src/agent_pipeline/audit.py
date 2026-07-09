"""Structured audit logging — one JSONL event per pipeline transition.

The audit log is the contract this project is really about: no step happens
without a line recording who did it, with which model, how long it took, and
what was decided. Prompts and outputs are stored as full SHA-256 hashes so a
trail can be shared safely without leaking content; the full text is written
only when ``dump_plaintext`` is on, into a separate directory (see the README's
privacy note).

**Two integrity guarantees, layered:**

* *Tamper-evident* (always on): every event is hash-chained with full SHA-256
  (``prev_hash``/``entry_hash``), so any edit, deletion, or reorder is
  detectable by recomputation (:func:`verify_chain`).
* *Tamper-resistant* (opt-in): if the environment variable named by
  ``audit.hmac_key_env`` (default ``AUDIT_HMAC_KEY``) is set, each closed trail
  is sealed with an HMAC-SHA256 over its chain head, written to a sidecar
  ``<run_id>.jsonl.sig``. Without the secret key an attacker cannot forge a
  valid seal even after re-chaining edited events (:func:`verify_signature`).
  The key lives only in the environment — never in the config or the repo.

The JSONL schema is kept compatible with the ``log_analyzer`` in the sibling
``agentic-ai-governance-toolkit``: ``gate_reason`` is an additive optional
field, and the HMAC seal is a sidecar file, so neither changes the event shape.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
from dataclasses import dataclass
from pathlib import Path
from types import TracebackType

from .contracts import Actor, AuditEvent
from .llm import StageTrace

# The chain starts from a fixed genesis value so the very first event still has
# a well-defined predecessor to hash against.
GENESIS_HASH = "sha256:genesis"

# Environment variable that, when set, enables the optional HMAC seal. Only its
# name is configurable (``audit.hmac_key_env``); the key value never leaves the
# environment.
DEFAULT_HMAC_KEY_ENV = "AUDIT_HMAC_KEY"


def content_hash(text: str | None) -> str | None:
    """Full SHA-256 hash of a prompt or output (``None`` passes through).

    Full-length (not truncated) so the fingerprint is collision-resistant, which
    matters when a hash is the only record of what a model saw or produced.
    """
    if text is None:
        return None
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def chain_hash(event: AuditEvent) -> str:
    """Compute an event's ``entry_hash`` from its content and its ``prev_hash``.

    The event's ``prev_hash`` must already be set. Serialization is canonical
    (sorted keys) and excludes ``entry_hash`` itself, so the hash is stable and
    self-referential-free.
    """
    payload = event.model_dump(mode="json", exclude={"entry_hash"})
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def sign_chain(events: list[AuditEvent], key: bytes) -> str:
    """Seal a trail with an HMAC-SHA256 over its chain head.

    The head (last ``entry_hash``) already commits to every earlier event via the
    chain, so signing it authenticates the whole trail. Requires a non-empty,
    already-chained trail.
    """
    if not events or events[-1].entry_hash is None:
        raise ValueError("cannot sign an empty or unchained trail")
    head = events[-1].entry_hash
    return "hmac-sha256:" + hmac.new(key, head.encode("utf-8"), hashlib.sha256).hexdigest()


def verify_signature(events: list[AuditEvent], signature: str, key: bytes) -> bool:
    """Return True iff ``signature`` is a valid HMAC seal for this trail and key.

    Constant-time comparison; a wrong key, an edited event (which changes the
    head), or a tampered signature all return False.
    """
    try:
        expected = sign_chain(events, key)
    except ValueError:
        return False
    return hmac.compare_digest(signature, expected)


def signature_path(trail: str | Path) -> Path:
    """Sidecar path holding a trail's HMAC seal: ``<trail>.sig``."""
    trail = Path(trail)
    return trail.with_name(trail.name + ".sig")


class AuditLog:
    """Writes audit events to ``<log_dir>/<run_id>.jsonl`` and keeps them in memory."""

    def __init__(self, run_id: str, config: dict) -> None:
        self.run_id = run_id
        self.events: list[AuditEvent] = []
        self._dump_plaintext = bool(config.get("dump_plaintext", False))
        self._seq = 0
        self._last_hash = GENESIS_HASH

        log_dir = Path(config.get("log_dir", "runs"))
        log_dir.mkdir(parents=True, exist_ok=True)
        self._path = log_dir / f"{run_id}.jsonl"
        self._file = self._path.open("w", encoding="utf-8")

        self._dump_dir = Path(config.get("dump_dir", "runs/dumps")) / run_id

        # Optional HMAC seal: only the env-var *name* is configurable; the key
        # value is read from the environment and never stored on the instance
        # longer than needed. Unset ⇒ trails are unsigned (still tamper-evident).
        key_env = config.get("hmac_key_env", DEFAULT_HMAC_KEY_ENV)
        key = os.environ.get(key_env) if key_env else None
        self._hmac_key = key.encode("utf-8") if key else None

    @property
    def path(self) -> Path:
        """Path of the JSONL trail for this run."""
        return self._path

    def record(self, event: AuditEvent) -> AuditEvent:
        """Chain, append, and flush one event.

        The event is linked to its predecessor (``prev_hash``) and sealed with
        its own ``entry_hash`` before being written, so the on-disk trail is
        tamper-evident.
        """
        event.prev_hash = self._last_hash
        event.entry_hash = chain_hash(event)
        self._last_hash = event.entry_hash
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
        gate_reason: str | None = None,
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
                gate_reason=gate_reason,
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
        """Close the trail file and, if an HMAC key is configured, seal it.

        The seal is an HMAC-SHA256 over the chain head, written to the sidecar
        ``<run_id>.jsonl.sig``. Sealing an empty trail is a no-op.
        """
        if not self._file.closed:
            self._file.close()
        if self._hmac_key and self.events:
            signature_path(self._path).write_text(
                sign_chain(self.events, self._hmac_key) + "\n", encoding="utf-8"
            )

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


@dataclass(frozen=True)
class ChainVerification:
    """Result of verifying an audit trail's hash chain."""

    ok: bool
    broken_index: int | None = None
    reason: str = ""


def verify_chain(events: list[AuditEvent]) -> ChainVerification:
    """Verify that a trail's hash chain is intact.

    Walks the events, recomputing each ``entry_hash`` and checking that every
    ``prev_hash`` matches the predecessor's ``entry_hash``. Returns the index of
    the first event that fails, if any — that is where the trail was edited,
    truncated, or reordered.
    """
    expected_prev = GENESIS_HASH
    for i, event in enumerate(events):
        if event.prev_hash != expected_prev:
            return ChainVerification(
                False, i, f"event {i} prev_hash does not match the previous event"
            )
        if event.entry_hash != chain_hash(event):
            return ChainVerification(
                False, i, f"event {i} content does not match its entry_hash (tampered)"
            )
        expected_prev = event.entry_hash
    return ChainVerification(True, None, f"chain intact across {len(events)} events")
