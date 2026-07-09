# HANDOFF.md — session memory

> The **memory of this repo.** One block per working session, **newest first**,
> so a fresh session continues without drift or loss. At session start run
> `/session-start` (reconstructs state from `scripts/` + this log + `BIBLE.md`).
> At session end run `/session-stop` (gate → snapshot → this log → commit → push).
> Be concrete and honest — `scripts/state.sh` is the factual truth.

---

## 2026-07-09 — Session continuity introduced; repo published

**State:** HEAD `9cfeb60` · `main` released as **v0.1.0** (public) · gate **PASS** · secure **all saved** · CI **green** (lint-and-test + web) · dashboard runs live.

**Done:**
- Built the full pipeline (planner/worker/reviewer/gate/audit/contracts/llm/cli),
  70 offline tests, ruff-clean; **tamper-evident hash-chained audit trail** with
  `audit --verify`; example docs + committed trails + rendered SVGs.
- **Optional external providers** (OpenAI/Gemini/Claude) via `.env`, HTTP-only,
  audited; dropped the `ollama` package (Ollama now called via REST too).
- **Web console** (`web/`, Vite + React + stdlib Python API): run the pipeline
  and resolve the human-review gate **in the browser**, plus an in-app **Docs**
  tab; `./setup.sh` then `./start.sh`.
- Community health files, CI (Python **and** web build), dependabot; **pushed
  public** and released **v0.1.0**.
- **This session's addition:** `BIBLE.md` (invariants + decision register),
  `HANDOFF.md` (this log), backbone scripts (`state`/`gate`/`secure`/
  `session-snapshot`), and `session-start`/`session-stop`/`project-state` skills,
  wired via project `CLAUDE.md`.

**Decided:** stdlib API (no Docker/framework/SDKs); local-first with opt-in,
audited external review; positioning as a reference pattern, not a framework.
(All recorded in `BIBLE.md`.)

**Open / blocked:** see the Decision register in `BIBLE.md` — (1) reviewer model
on machines without `llama3.1`; (2) whether to keep `Co-Authored-By: Claude` /
`Claude-Session` commit trailers on the public repo; (3) social-preview image /
GitHub Pages. None block core work.

**Next:** whatever the maintainer prioritises — merge the open dependabot PRs (CI
green on them: pyyaml, actions/checkout 4→7, actions/setup-node 4→6), add a
social-preview image, or continue feature work. **Maintainer input, to sharpen:**
a pre-commit git hook that runs `scripts/gate.sh` so a red gate can't be
committed (offered, not yet decided). Run `/session-start` for the live picture
first.

**Continuity warnings:** honour the BIBLE invariants — no step off the audit
record, never edit a trail in place (recompute the chain), tests stay offline,
no provider SDKs, no customer-internal names, and never overclaim (it is a
reference pattern). The committed default reviewer stays `llama3.1`; any switch
to an installed model is a local, uncommitted edit.

---
