---
description: Close a work session — save the repo memory, pass the hard gate, and commit & push everything so nothing is forgotten and nothing is left half-done. Counterpart to session-start. Trigger: "session-stop", "wrap up", "end session", "done for today", "close the session", end of a work session.
allowed-tools: Bash, Read, Write, Edit, Grep, Glob
---

Close the session so the next one (via `/session-start`) continues **without drift, without loss, and without a half-finished hand-off**. Do not skip a step; actually run each one.

**Step 1 — Inventory.**
- `git status --short` — what is open? Nothing should be left unintentionally.
- If code changed and something is now unverified, drive it (or say explicitly what is still unverified).

**Step 2 — Update canon & continuity.**
- `BIBLE.md` — record decisions made this session; tick or add Decision-register items. Decisions live in the file, not just the chat.
- **★ Rescue chat threads (mandatory, or they are lost):** any idea, maintainer input, or half-formed plan that exists only in this conversation and is in **no file** yet goes into the HANDOFF entry (Open/Next). Mark unconfirmed items as "maintainer input, to sharpen" — preserve, don't invent. Nothing we are working on may be missing at the next `/session-start`.

**Step 3 — Hard gate.**
- `./scripts/gate.sh` — **must print GATE: PASS.** Fix any failure first.

**Step 4 — Write the repo memory.**
- `./scripts/session-snapshot.sh` and prepend its block to the **top** of `HANDOFF.md` (newest first).
- Fill the `_(fill in)_` lines with what really happened: **Done · Decided · Open/blocked · Next · Continuity warnings**. Concrete and honest — no overstating progress (`state.sh` is the truth).

**Step 5 — Secure (git).**
- Commit granularly (one commit per concern, conventional messages: feat/fix/docs/ci…). Document what and why.
- `git push origin main`.
- `./scripts/secure.sh` — **must report "all saved".** Otherwise commit/push until it does.

**Step 6 — Hand off.**
Give a short closing note: state (numbers), what was saved, what is next, which decisions block the next session. That is the starting point `/session-start` reads next time.

**Rule:** the session is done only when `gate.sh` is PASS, `secure.sh` says "all saved", and the newest `HANDOFF.md` entry reflects reality. Invent nothing, hide nothing, leave nothing uncommitted.
