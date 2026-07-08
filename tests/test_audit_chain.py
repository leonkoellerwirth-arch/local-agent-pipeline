"""The audit trail is tamper-evident: editing it breaks a verifiable hash chain."""

from __future__ import annotations

from click.testing import CliRunner

from agent_pipeline.audit import GENESIS_HASH, AuditLog, read_events, verify_chain
from agent_pipeline.cli import main
from agent_pipeline.contracts import Actor


def _trail(tmp_path) -> AuditLog:
    log = AuditLog("chain", {"log_dir": str(tmp_path)})
    log.record_event(Actor.SYSTEM, "run_start")
    log.record_event(Actor.PLANNER, "plan")
    log.record_event(Actor.WORKER, "execute", step_id="s1", confidence=0.9)
    log.record_event(Actor.REVIEWER, "review", step_id="s1", decision="pass")
    log.record_event(Actor.SYSTEM, "run_complete", decision="completed")
    log.close()
    return log


def test_first_event_links_to_genesis(tmp_path):
    log = _trail(tmp_path)
    assert log.events[0].prev_hash == GENESIS_HASH


def test_every_event_is_sealed(tmp_path):
    log = _trail(tmp_path)
    for event in log.events:
        assert event.entry_hash and event.entry_hash.startswith("sha256:")
        # Full sha256 digest (64 hex chars), not the truncated content hash.
        assert len(event.entry_hash) == len("sha256:") + 64


def test_fresh_trail_verifies_clean(tmp_path):
    _trail(tmp_path)
    events = read_events(tmp_path / "chain.jsonl")
    result = verify_chain(events)
    assert result.ok
    assert result.broken_index is None


def test_editing_content_breaks_the_chain(tmp_path):
    _trail(tmp_path)
    events = read_events(tmp_path / "chain.jsonl")
    # Someone quietly flips a reviewer 'pass' to hide an escalation.
    events[3].decision = "escalate"
    result = verify_chain(events)
    assert not result.ok
    assert result.broken_index == 3
    assert "tampered" in result.reason


def test_deleting_an_event_breaks_the_chain(tmp_path):
    _trail(tmp_path)
    events = read_events(tmp_path / "chain.jsonl")
    del events[2]  # drop the worker step to hide that it ran
    result = verify_chain(events)
    assert not result.ok
    assert result.broken_index == 2


def test_reordering_events_breaks_the_chain(tmp_path):
    _trail(tmp_path)
    events = read_events(tmp_path / "chain.jsonl")
    events[1], events[2] = events[2], events[1]
    result = verify_chain(events)
    assert not result.ok
    assert result.broken_index == 1


def _rewrite(path, events) -> None:
    path.write_text("\n".join(e.model_dump_json() for e in events) + "\n", encoding="utf-8")


def test_verify_cli_passes_on_clean_trail(tmp_path):
    _trail(tmp_path)
    result = CliRunner().invoke(main, ["audit", str(tmp_path / "chain.jsonl"), "--verify"])
    assert result.exit_code == 0
    assert "intact" in result.output


def test_verify_cli_fails_on_tampered_trail(tmp_path):
    _trail(tmp_path)
    path = tmp_path / "chain.jsonl"
    events = read_events(path)
    events[3].decision = "escalate"  # rewrite history
    _rewrite(path, events)
    result = CliRunner().invoke(main, ["audit", str(path), "--verify"])
    assert result.exit_code == 1
    assert "BROKEN" in result.output
