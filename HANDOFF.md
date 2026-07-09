# HANDOFF.md — session memory

> The **memory of this repo.** One block per working session, **newest first**,
> so a fresh session continues without drift or loss. At session start run
> `/session-start` (reconstructs state from `scripts/` + this log + `BIBLE.md`).
> At session end run `/session-stop` (gate → snapshot → this log → commit → push).
> Be concrete and honest — `scripts/state.sh` is the factual truth.

---

## 2026-07-09 — Repo polish: "looks professional at a glance"

**State:** HEAD `1ca7f85` · 5 commit(s) unpushed at snapshot · gate **PASS**.

**Commits this session (newest first):**
- `1ca7f85` docs: add ROADMAP.md + record the polish in the changelog
- `a424c5f` docs: ship a social-preview image
- `92e457f` docs: add a real Audit Console screenshot to the README
- `7e7ae68` ci(deps): have Dependabot watch the web npm lockfile
- `aeb4d96` chore(deps): add uv.lock for reproducible Python installs

**Done:** Maintainer asked to make the repo look professional immediately. The repo
was already well-equipped (badges, LICENSE, CONTRIBUTING/COC/SECURITY, CHANGELOG,
issue/PR templates, Dependabot). The remaining gap was **visual proof** + a few
reproducibility signals — closed all five:
- **#1 Dashboard screenshot (real).** Launched the Audit Console (`web/start.sh`),
  which serves the existing real `runs/` through the Vite proxy — **no fresh
  Ollama run needed**. Headless-Chrome shot at 2× → `docs/img/dashboard.png`
  (pngquant, 112 KB). Shows 4 stat tiles (8 runs, 50% escalation, 12.1s, **Audit
  Chain: All intact**), the run list, and a full trail (planner→worker→reviewer→
  **escalate**→human **reject**→abort) with real models (`llama3.2`,
  `aya-expanse:8b`), latencies, and policy flags. Embedded in README after the
  Dashboard section. Real capture, not a mockup (honest-description invariant).
- **#2 Social-preview** `docs/img/social-preview.png` — 1280×640 OG image built as
  HTML→Chrome→pngquant (88 KB), matching the console's dark/emerald theme
  ("Agents you can prove, not just run"). **Still needs the maintainer to upload
  it** under Settings → Social preview (cannot be done via git).
- **#3 `uv.lock`** committed (18 pkgs; pyproject untouched). **#4** Dependabot now
  also watches `web/package-lock.json` (npm, `/web`).
- **#5 `ROADMAP.md`** — honest backlog (audit-integrity hardening, config
  validation, CI matrix) + explicit non-goals (no framework/hosted service/SDKs).
- Console started for the shot was stopped cleanly (ports 18082/5173 free again).

**Decided (now in BIBLE §6):** README screenshots are **real, never mockups**;
reproducible installs are committed (`uv.lock` + `web/package-lock.json`, both in
Dependabot). The "Repo polish" register item is narrowed — social-preview image
done, only **GitHub Pages** (optional) + the manual upload remain.

**Open / blocked:** unchanged register items — reviewer default without
`llama3.1`; commit-trailers on the public repo (this session followed the
existing convention and kept them); GitHub Pages; **audit-integrity hardening
(P1)** still needs the maintainer to fix the schema shape (§3/§4) before coding.
**Action item for the maintainer:** upload `docs/img/social-preview.png` in the
repo's Settings → Social preview.

**Next:** maintainer's pick from the review backlog — the P1 audit-integrity
hardening is the highest-value item but is schema-blocked pending a decision.
Otherwise: config schema-validation in the CLI, CI matrix (3.11/3.12/3.13),
`pip-audit`.

**Continuity warnings:** honour the invariants — reference pattern (no overclaim),
tests stay **offline** (no Ollama in CI), no provider SDKs, never edit a trail in
place, keys never in URLs, console stays localhost-only, `start.sh` never kills
foreign processes. **Any README screenshot/output must stay real** — regenerate
`docs/img/dashboard.png` from a live console if the UI changes, never fake it.

---

## 2026-07-09 — External review: all P0 (security) items fixed

**State:** HEAD `41f56a8` · 6 commit(s) unpushed at snapshot · gate **PASS**.

**Commits this session (newest first):**
- `41f56a8` fix: scope the gate's TODO/name greps to source, not compiled bytecode
- `5999825` style: ruff-format api_server.py (missed blank line)
- `c21f4c3` docs: correct SECURITY.md to the real threat model
- `59858f9` fix: don't let start.sh kill processes it didn't start
- `bc3e81a` feat: guard the local web console with token, origin, and limits
- `78f464a` fix: never put the Gemini API key in a request URL

**Done:** Worked an external code review (maintainer-provided, German, P0–P3).
Verified every **P0** claim against the code, then fixed all four:
- **P0.2** Gemini key was a `?key=` URL param and `_post_json` echoed the full
  URL on error → moved the key to the `x-goog-api-key` header; added `_safe_url()`
  to strip query strings from error messages. 3 tests.
- **P0.3** the localhost web console ran real pipeline runs with no access
  control → added a shared session token (`X-API-Token`, forwarded by the Vite
  proxy so the browser never holds it), an Origin allow-list (403), body-size
  (413) and concurrency (429) caps, example-id validation (**fixed a real
  path-traversal**, `example:../../…`), and decision-enum validation. Limits live
  in `config/pipeline.yaml` (`web:`). New `tests/test_web_api.py` — 13 offline
  cases. Added `web` to pytest `pythonpath`.
- **P0.4** `start.sh` did `lsof … | kill` on both ports unconditionally → now a
  taken port is a hard error; killing is opt-in via `--free-port`. It also
  generates and exports `API_TOKEN` to both processes so the new guard works.
- **P0.1** rewrote `SECURITY.md` from false claims ("no ports / no credentials /
  no external calls") to the real three-surface threat model.
- Incidental: fixed a **latent gate bug** — `grep … src` scanned `__pycache__`
  `.pyc`, and a bytecode byte-run `XxX` tripped the `XXX` check in the gate's
  shell; scoped the greps to source only. Tests: **86 pass**, gate **PASS**.

**Decided (now in BIBLE §6):** keys in headers never URLs; the console is a
local-safety layer not real auth (never expose publicly); `start.sh` never kills
foreign processes; `SECURITY.md` tells the truth; the gate scans source not
bytecode.

**Open / blocked:** the three prior register items are unchanged (reviewer model
without `llama3.1`; commit trailers on public repo; social-preview/Pages). New
open item: **audit-integrity hardening (review P1)** — full-length SHA-256 vs the
16-hex fingerprint, optional HMAC/signature, and the human gate-reason in the
trail; these touch the audit schema (§4) + integrity claim (§3), so decide the
shape with the maintainer first.

**Next:** maintainer's pick from the review backlog, roughly in the reviewer's
recommended order:
- **P1:** gate-reason into the audit; full hashes (or document as fingerprint);
  optional HMAC; `uv.lock`/constraints for Python repro; add `web/package-lock.json`
  to Dependabot.
- **P2:** config schema-validation in the CLI; document the reviewer PII regex as
  a demo guardrail; CI matrix (3.11/3.12/3.13); add `pip-audit`.
- **P3:** README split (Product / Security / Maintainer workflow); ROADMAP/RELEASE;
  signed releases/provenance; the still-open dependabot PRs.

**Continuity warnings:** honour the BIBLE invariants — reference pattern (no
overclaim), tests stay **offline** (the new web tests reject before any run, so no
Ollama), no provider SDKs, never edit a trail in place, keys never in URLs, the
web console stays localhost-only, `start.sh` never kills foreign processes. Any
docs demo/output stays **real**.

---

## 2026-07-09 — README: session-workflow skills documented

**State:** HEAD `825ccc8` · 0 commit(s) unpushed · gate **PASS** · secure **all saved**.

**Commits this session:**
- `825ccc8` docs: document the session-workflow skills with a real transcript demo

**Done:**
- Replaced the thin "Working across sessions" note in `README.md` with a full
  **"How we work with this repo (session workflow)"** section: the three state
  artefacts (`BIBLE.md` / `HANDOFF.md` / `scripts/`), the three skills
  (`/session-start`, `/project-state`, `/session-stop`), and the binding rule
  not to start work on a red gate or open decision.
- Added a **Demo** subsection with the **real, unedited** output of
  `state.sh`/`gate.sh`/`secure.sh` on a clean tree (the one commit-list elision
  is called out inline) — concrete, not abstract, and honest per the BIBLE.

**Decided:** nothing new — no BIBLE invariant or register item changed this
session (documentation only).

**Open / blocked:** unchanged from the entry below — the three open `BIBLE.md`
register items (reviewer model without `llama3.1`; commit-trailer policy on the
public repo; social-preview image / Pages). None block core work.

**Next:** maintainer's pick — merge the open dependabot PRs (pyyaml,
actions/checkout 4→7, actions/setup-node 4→6), the pre-commit gate hook (offered,
not yet decided), or resolve a register item. Run `/session-start` first.

**Continuity warnings:** honour the BIBLE invariants — no overclaim (reference
pattern), tests stay offline, no provider SDKs, never edit a trail in place, no
customer-internal names. Any demo/output added to docs stays **real** (run it,
don't mock it).

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
