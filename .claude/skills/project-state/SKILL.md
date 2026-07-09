---
description: Overall project state — git status, commits ahead/behind, source size, test count, ruff status, and the hard-gate result. Trigger: "project-state", "where do we stand", "status", "how far along are we".
allowed-tools: Bash, Read
---

Run `./scripts/state.sh` and show the output.

Then add a short, honest read below it:
- **Where we are** — from the numbers plus the newest `HANDOFF.md` entry.
- **Green or red** — run `./scripts/gate.sh` and `./scripts/secure.sh`; report PASS/FAIL and whether everything is committed and pushed.
- **Next** — the concrete next step (from HANDOFF "Next" and the `BIBLE.md` Decision register).

Use only the scripts' numbers and what is written in the repo — invent nothing.
