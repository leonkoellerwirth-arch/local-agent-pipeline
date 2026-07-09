---
description: Open a work session — reconstruct the exact project state from the deterministic scripts and the repo memory (HANDOFF.md, BIBLE.md) before changing anything, so work continues without drift. Counterpart to session-stop. Trigger: "session-start", "continue", "where were we", "new session", "catch me up", start of a work session.
allowed-tools: Bash, Read, Grep, Glob
---

Reconstruct the exact state **before** writing or changing anything. Goal: **no drift from the existing project.**

**Step 1 — Deterministic truth (scripts, no AI):**
- `./scripts/state.sh` — branch, HEAD, uncommitted/unpushed, LoC, tests, ruff.
- `./scripts/gate.sh` — the hard quality gate (must be PASS to build on).
- `./scripts/secure.sh` — is everything committed & pushed?

**Step 2 — Repo memory (in this order):**
- `HANDOFF.md` — read the **top (newest) entry** in full: Done / Decided / Open-blocked / Next / Continuity warnings.
- `BIBLE.md` — the invariants (§1–§4) and the **Decision register** (§6): every open `- [ ]` item.
- If the next task is unclear, skim `README.md` and `docs/SOP.md`.

**Step 3 — Brief the user (short, concrete):**
1. **Where we are** — numbers from `state.sh` + gate/secure status (green/red).
2. **Last done** — from the newest HANDOFF entry.
3. **Blocking decisions** — which open BIBLE decision-register items block the next task. **Clear these with the maintainer first.**
4. **Next** — the concrete next step.
5. **Continuity warnings** — invariants/threads that must not be broken.

**Rule:** Do not start substantive work while a blocking BIBLE decision is open. If `gate.sh` fails or `secure.sh` reports unsaved/unpushed work, fix that first. End the session with **`/session-stop`**.
