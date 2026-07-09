"""Audit-integrity hardening: full-length content hashes, the recorded gate
reason, and the optional HMAC seal that makes a trail tamper-*resistant*, not
just tamper-*evident*."""

from __future__ import annotations

from click.testing import CliRunner

from agent_pipeline.audit import (
    DEFAULT_HMAC_KEY_ENV,
    GENESIS_HASH,
    AuditLog,
    chain_hash,
    content_hash,
    read_events,
    sign_chain,
    signature_path,
    verify_chain,
    verify_signature,
)
from agent_pipeline.cli import main
from agent_pipeline.contracts import Actor

KEY = "correct horse battery staple"


def _rechain(events) -> None:
    """Re-seal a trail the way a forger would: recompute every hash so the plain
    chain verifies again. The head necessarily changes, which is what the HMAC
    seal catches."""
    prev = GENESIS_HASH
    for e in events:
        e.prev_hash = prev
        e.entry_hash = chain_hash(e)
        prev = e.entry_hash


# --- Full-length content fingerprints ---------------------------------------


def test_content_hash_is_full_sha256():
    h = content_hash("some prompt text")
    assert h is not None and h.startswith("sha256:")
    assert len(h) == len("sha256:") + 64  # full digest, not truncated to 16


def test_content_hash_passes_none_through():
    assert content_hash(None) is None


# --- Gate reason is recorded and covered by the chain -----------------------


def _trail(tmp_path, *, config=None) -> AuditLog:
    log = AuditLog("h", config or {"log_dir": str(tmp_path)})
    log.record_event(Actor.SYSTEM, "run_start")
    log.record_event(Actor.WORKER, "execute", step_id="s1")
    log.record_event(Actor.REVIEWER, "review", step_id="s1", decision="escalate")
    log.record_event(
        Actor.HUMAN,
        "gate_decision",
        step_id="s1",
        decision="reject",
        gate_reason="values could not be confirmed with the counterparty",
    )
    log.record_event(Actor.SYSTEM, "abort", decision="rejected")
    log.close()
    return log


def test_gate_reason_is_recorded(tmp_path):
    log = _trail(tmp_path)
    gate = next(e for e in log.events if e.action == "gate_decision")
    assert gate.gate_reason == "values could not be confirmed with the counterparty"


def test_editing_gate_reason_breaks_the_chain(tmp_path):
    from agent_pipeline.audit import verify_chain

    _trail(tmp_path)
    events = read_events(tmp_path / "h.jsonl")
    # Rewrite the human's stated reason to launder the rejection.
    events[3].gate_reason = "looked fine to me"
    result = verify_chain(events)
    assert not result.ok
    assert result.broken_index == 3


# --- Optional HMAC seal ------------------------------------------------------


def test_no_seal_written_without_a_key(tmp_path, monkeypatch):
    monkeypatch.delenv(DEFAULT_HMAC_KEY_ENV, raising=False)
    _trail(tmp_path)
    assert not signature_path(tmp_path / "h.jsonl").exists()


def test_seal_written_and_valid_when_key_set(tmp_path, monkeypatch):
    monkeypatch.setenv(DEFAULT_HMAC_KEY_ENV, KEY)
    log = _trail(tmp_path)
    sig_file = signature_path(tmp_path / "h.jsonl")
    assert sig_file.exists()
    signature = sig_file.read_text().strip()
    assert signature.startswith("hmac-sha256:")
    assert verify_signature(log.events, signature, KEY.encode())


def test_seal_detects_rechained_tampering(tmp_path, monkeypatch):
    monkeypatch.setenv(DEFAULT_HMAC_KEY_ENV, KEY)
    _trail(tmp_path)
    signature = signature_path(tmp_path / "h.jsonl").read_text().strip()
    events = read_events(tmp_path / "h.jsonl")
    events[2].decision = "pass"  # hide the escalation...
    _rechain(events)  # ...and forge the whole chain so verify_chain passes again
    assert verify_chain(events).ok  # the plain chain no longer catches it
    assert not verify_signature(events, signature, KEY.encode())  # but the seal does


def test_seal_rejects_a_wrong_key(tmp_path, monkeypatch):
    monkeypatch.setenv(DEFAULT_HMAC_KEY_ENV, KEY)
    log = _trail(tmp_path)
    signature = signature_path(tmp_path / "h.jsonl").read_text().strip()
    assert not verify_signature(log.events, signature, b"a different key")


def test_sign_chain_rejects_empty_trail():
    import pytest

    with pytest.raises(ValueError):
        sign_chain([], KEY.encode())


# --- CLI reports the seal ----------------------------------------------------


def test_verify_cli_reports_valid_seal(tmp_path, monkeypatch):
    monkeypatch.setenv(DEFAULT_HMAC_KEY_ENV, KEY)
    _trail(tmp_path)
    result = CliRunner().invoke(main, ["audit", str(tmp_path / "h.jsonl"), "--verify"])
    assert result.exit_code == 0
    assert "HMAC seal valid" in result.output


def test_verify_cli_flags_a_forged_seal(tmp_path, monkeypatch):
    monkeypatch.setenv(DEFAULT_HMAC_KEY_ENV, KEY)
    _trail(tmp_path)
    path = tmp_path / "h.jsonl"
    events = read_events(path)
    events[2].decision = "pass"
    _rechain(events)  # forge the chain so only the HMAC seal can catch it
    path.write_text("\n".join(e.model_dump_json() for e in events) + "\n", encoding="utf-8")
    result = CliRunner().invoke(main, ["audit", str(path), "--verify"])
    assert result.exit_code == 1
    assert "seal INVALID" in result.output


def test_verify_cli_notes_seal_without_key(tmp_path, monkeypatch):
    monkeypatch.setenv(DEFAULT_HMAC_KEY_ENV, KEY)
    _trail(tmp_path)  # writes the .sig
    monkeypatch.delenv(DEFAULT_HMAC_KEY_ENV, raising=False)  # verifier has no key
    result = CliRunner().invoke(main, ["audit", str(tmp_path / "h.jsonl"), "--verify"])
    assert result.exit_code == 0
    assert "not set" in result.output
