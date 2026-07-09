# CLAUDE.md — working in local-agent-pipeline

A minimal, fully local multi-agent pipeline where auditability and human
oversight are first-class. **Reference pattern, not a framework** — never
overclaim it.

## Start every session with `/session-start`

It reconstructs the exact state (from `scripts/state.sh`/`gate.sh`/`secure.sh`
+ the newest `HANDOFF.md` entry + the `BIBLE.md` decision register) so you
continue without drift. **Do not start substantive work while a blocking
decision is open or the gate is red.**

Then, before changing anything:

1. **Read [`BIBLE.md`](BIBLE.md)** — the binding invariants and the open
   Decision register. Do not violate an invariant; if something needed isn't
   covered, add it to the register and ask — **do not improvise it.**
2. Reach for procedures in [`docs/SOP.md`](docs/SOP.md) (add a policy rule,
   extend the action space, cut a release, keep the audit schema compatible).

## Non-negotiables (full list in BIBLE.md §2–§4)

- Contracts (`contracts.py`) are the spec; every stage speaks in validated models.
- Every pipeline transition emits exactly one audit event; the trail is
  hash-chained — never edit a trail in place.
- Planner is bound to the `policy.yaml` action whitelist; reviewer is a
  different model; the gate is never bypassed.
- Behaviour in YAML (no magic numbers); tests never need Ollama; no provider SDKs.
- English, type hints + docstrings, honest self-description.

## Quality gate (before any commit/push)

`./scripts/gate.sh` must print **GATE: PASS** (ruff, pytest, web build, no
TODO/secrets/customer names). Dev environment:

```bash
./setup.sh                 # first time: venv (Python ≥3.11 via uv) + deps + models
.venv/bin/ruff check . && .venv/bin/python -m pytest -q
./start.sh                 # optional: the web console (API + dashboard)
```

## Commits

Conventional and granular — one concern per commit (`feat:`/`fix:`/`docs:`/`ci:`),
documenting what and why.

## End every session with `/session-stop`

It runs the gate, snapshots a new `HANDOFF.md` entry (Done/Decided/Open/Next/
Warnings), records decisions in `BIBLE.md`, then commits & pushes — so nothing is
forgotten and nothing is left half-done.

## Skills

`/session-start` · `/session-stop` · `/project-state`. Backbone scripts
(deterministic, no AI): `scripts/state.sh`, `gate.sh`, `secure.sh`,
`session-snapshot.sh`.
