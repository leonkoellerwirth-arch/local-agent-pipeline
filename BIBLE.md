# BIBLE.md — binding invariants & decision register

> The **constitution of this repo.** An AI agent (or human) working here reads
> this first and does not violate it. Facts, invariants, and decisions live
> here; step-by-step procedures live in [`docs/SOP.md`](docs/SOP.md); the
> running session memory is [`HANDOFF.md`](HANDOFF.md). At session start run
> `/session-start`; at session end run `/session-stop`.
>
> When something needed is not covered here, do **not** improvise it — add it to
> the Decision register below as an open item and raise it with the maintainer.

---

## 1. Purpose & positioning (do not overclaim)

- This is a **reference pattern**, not a framework and not a production system.
  Never market it as more. It exists to make agent control points *legible and
  provable*, in code small enough to read in one sitting.
- **Local-first.** It runs fully on Ollama by default; nothing leaves the machine
  unless a role is explicitly routed to an external provider. External review is
  **opt-in and audited** — never add silent data egress.
- **Small & excellent.** One responsibility per file; each file explainable in
  ~5 minutes. **Deepen, don't widen** — improve the core rather than adding
  surface. New scope needs a real justification, not "it'd be nice".

## 2. Architecture invariants (never break)

1. **Contracts are the spec.** `contracts.py` (Pydantic) is the shared vocabulary;
   every stage speaks in validated models. A malformed hand-off must fail at the
   boundary, not leak downstream.
2. **No step off the record.** Every pipeline transition emits exactly one audit
   event. Enforced by `tests/test_audit_completeness.py` — keep it passing.
3. **The audit trail is tamper-evident.** Events are hash-chained
   (`prev_hash`/`entry_hash`). Never edit a trail in place; any tool that rewrites
   one must recompute the chain. Committed example trails must pass
   `agent-pipeline audit <file> --verify`.
4. **Action-space whitelist.** The planner may only emit actions listed in
   `config/policy.yaml`; anything else is discarded and logged. The planner must
   tolerate model output shape drift (objects *or* bare strings) without crashing.
5. **Independent reviewer.** The reviewer runs on a *different* model from the
   worker. Keep it configurable and distinct.
6. **The gate is sacred.** Escalated/risky results are never auto-accepted — a
   human (or an explicit `PolicyGate`/`WebGate` decision) must resolve them, and
   the decision is audited (`actor` shows human vs. system).
7. **Behaviour lives in YAML.** No magic numbers in code — models, thresholds,
   triggers, and the action space are config.
8. **Tests never need Ollama.** All model calls go through one injectable backend
   (`ScriptedBackend`). CI must stay GPU-free and offline.
9. **No provider SDKs.** Ollama and the cloud providers are all called over plain
   HTTP (`urllib`). Do not add heavy client libraries.

## 3. Quality gate (must hold before every commit/push)

Run `scripts/gate.sh` — it must print **GATE: PASS**:
`ruff check` + `ruff format --check` clean · `pytest` green · web build (tsc +
vite) green · no TODO/FIXME/dead code · no customer-internal names · no secrets
tracked · the internal brief not tracked. English throughout; type hints +
docstrings on all Python.

## 4. Audit schema stability (integration contract)

`AuditEvent` is the contract with the sibling
[`agentic-ai-governance-toolkit`](https://github.com/leonkoellerwirth-arch/agentic-ai-governance-toolkit)'s
`log_analyzer`. **Additive** optional fields are safe; renames/removals need
coordination in both repos. Adding a field changes every `entry_hash`, so
regenerate the committed example trails (`scripts/render_examples.py`) when you do.

## 5. Facts & coordinates

- **Repo:** `leonkoellerwirth-arch/local-agent-pipeline` (public). Released `v0.1.0`.
- **Author:** Leon Köllerwirth Hlihel — https://leonkoellerwirth.de.
- **Sibling:** `agentic-ai-governance-toolkit` (describes governance; this repo
  implements it).
- **Env:** system `python3` is 3.10 but the project needs ≥3.11 → use `.venv`
  (built by `./setup.sh`, Python 3.13 via `uv`). Entry points: `./setup.sh`
  (Python) and `./start.sh` → `web/start.sh` (the web console).
- **Never commit:** `.env` (gitignored), `CLAUDE-CODE-BRIEFING-*.md` (internal).

## 6. Decision register (resolve before related work)

Open items — `- [ ]` blocks the related task until decided with the maintainer.

- [ ] **Default reviewer model on machines without `llama3.1`.** Committed default
  is `reviewer: llama3.1`; it is not installed on the author's machine. Either
  `ollama pull llama3.1`, or set an installed model locally (e.g.
  `aya-expanse:8b`) — a legitimate, uncommitted local config edit.
- [ ] **Repo polish:** GitHub Pages for the dashboard (optional) — not yet done.
  The social-preview image now ships at `docs/img/social-preview.png`; only the
  maintainer's manual upload under Settings → Social preview remains.

Resolved decisions of record (why things are the way they are):

- Tamper-evident hash chain is the headline differentiator (vs. "we log stuff").
- Dashboard uses a **stdlib** Python API + Vite proxy (ytscapper's architecture)
  — **no Docker, no framework, no provider SDKs** — to fit "small & local".
- CI covers Python **and** the web build.
- **Cloud-provider keys go in request headers, never in a URL** (Gemini used a
  `?key=` query param); error messages strip query strings as defence in depth.
- **The local web console is guarded, not open:** localhost bind + shared
  session token (`X-API-Token`, injected by the Vite proxy) + Origin allow-list +
  body-size (413) and concurrency (429) caps + example-id validation. It is a
  local-machine safety layer, **not** real auth — never expose it publicly.
- **`start.sh` never kills a process it didn't start** — a taken port is a
  hard error; killing is opt-in via `--free-port`.
- **`SECURITY.md` states the real threat model** (local-by-default; external
  providers are opt-in and send data off-host; the console opens a local port).
- The gate scans **source only** for TODO/name markers — never compiled `.pyc`
  (a bytecode byte-sequence once tripped the `XXX` check).
- **Audit integrity is layered:** the full-SHA-256 hash chain is always-on
  tamper-*evidence*; the optional HMAC-SHA256 seal (env `AUDIT_HMAC_KEY`, sidecar
  `.sig`, over the chain head) adds tamper-*resistance*. The `gate_reason` is
  recorded in the trail. Content fingerprints are full SHA-256, not truncated.
  Schema changes stayed **additive** (§4): `gate_reason` is optional and the seal
  is a sidecar, so the sibling `log_analyzer` is unaffected.
- **Commit-message trailers are kept** (`Co-Authored-By: Claude` +
  `Claude-Session:`) — consistent with the whole history and honest about
  authorship; no history rewrite.
- **Reproducible installs are committed:** `uv.lock` pins the Python graph and
  `web/package-lock.json` the frontend; Dependabot watches pip, github-actions,
  **and** npm (`/web`).
- **README screenshots/outputs are real, never mockups** — the Audit Console
  shot (`docs/img/dashboard.png`) is a captured session; the trail SVGs and
  example JSONL come from `scripts/render_examples.py`. Regenerate from a live
  console or that script rather than editing by hand (honest-description
  invariant).
