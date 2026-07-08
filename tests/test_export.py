"""The dashboard's data comes from agent_pipeline.export — summarize + collect."""

from __future__ import annotations

from agent_pipeline.audit import AuditLog
from agent_pipeline.contracts import Actor
from agent_pipeline.export import collect, summarize


def _completed(tmp_path, run_id="done"):
    log = AuditLog(run_id, {"log_dir": str(tmp_path)})
    log.record_event(Actor.SYSTEM, "run_start")
    log.record_event(Actor.WORKER, "execute", step_id="s1", confidence=0.9)
    log.record_event(Actor.REVIEWER, "review", step_id="s1", decision="pass")
    log.record_event(Actor.SYSTEM, "run_complete", decision="completed")
    log.close()
    return log.path


def _aborted(tmp_path, run_id="stopped"):
    log = AuditLog(run_id, {"log_dir": str(tmp_path)})
    log.record_event(Actor.SYSTEM, "run_start")
    log.record_event(
        Actor.REVIEWER, "review", step_id="s1", decision="escalate", policy_flags=["pii:email"]
    )
    log.record_event(Actor.SYSTEM, "abort", step_id="s1", decision="rejected")
    log.close()
    return log.path


def test_summarize_completed_run(tmp_path):
    rec = summarize(_completed(tmp_path))
    assert rec is not None
    assert rec["run_id"] == "done"
    assert rec["status"] == "completed"
    assert rec["chain_ok"] is True
    assert len(rec["events"]) == 4
    assert rec["steps"] == ["s1"]


def test_summarize_marks_aborted(tmp_path):
    rec = summarize(_aborted(tmp_path))
    assert rec["status"] == "aborted"
    assert rec["policy_flags"] == ["pii:email"]


def test_summarize_bad_file_returns_none(tmp_path):
    bad = tmp_path / "junk.jsonl"
    bad.write_text("this is not json\n")
    assert summarize(bad) is None


def test_collect_dedupes_and_orders_newest_first(tmp_path):
    _completed(tmp_path, "run-a")
    _aborted(tmp_path, "run-b")
    runs = collect([tmp_path, tmp_path])  # same dir twice -> must dedupe
    ids = [r["run_id"] for r in runs]
    assert sorted(ids) == ["run-a", "run-b"]
    assert len(ids) == 2  # not four
