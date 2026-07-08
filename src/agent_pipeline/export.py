"""Summarize audit trails for external views (dashboard, reports).

Reuses ``read_events`` and ``verify_chain`` so any view shows exactly what the
CLI would — the audit logic is never reimplemented elsewhere.
"""

from __future__ import annotations

from pathlib import Path

from .audit import read_events, verify_chain


def _status(actions: set[str]) -> str:
    if "run_complete" in actions:
        return "completed"
    if "abort" in actions:
        return "aborted"
    return "incomplete"


def summarize(path: str | Path) -> dict | None:
    """Summarize one JSONL trail into a view-friendly record (``None`` if unreadable)."""
    path = Path(path)
    try:
        events = read_events(path)
    except (ValueError, OSError):
        return None
    if not events:
        return None

    actions = {e.action for e in events}
    steps = list(dict.fromkeys(e.step_id for e in events if e.step_id))
    flags = sorted({f for e in events for f in e.policy_flags})
    chain = verify_chain(events)
    started, last = events[0].timestamp, events[-1].timestamp

    return {
        "run_id": events[0].run_id,
        "path": str(path),
        "started": started.isoformat(),
        "elapsed_s": round((last - started).total_seconds(), 2),
        "status": _status(actions),
        "steps": steps,
        "policy_flags": flags,
        "chain_ok": chain.ok,
        "chain_reason": chain.reason,
        "events": [e.model_dump(mode="json") for e in events],
    }


def collect(dirs: list[Path]) -> list[dict]:
    """Summarize every ``*.jsonl`` trail under ``dirs`` (deduped, newest first)."""
    seen: set[Path] = set()
    runs: list[dict] = []
    for directory in dirs:
        directory = Path(directory)
        if not directory.is_dir():
            continue
        for path in sorted(directory.glob("*.jsonl")):
            if path in seen:
                continue
            seen.add(path)
            record = summarize(path)
            if record:
                runs.append(record)
    runs.sort(key=lambda r: r["started"], reverse=True)
    return runs
