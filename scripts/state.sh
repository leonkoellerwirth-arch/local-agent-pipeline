#!/usr/bin/env bash
# Deterministic project state — no AI, no tokens. The factual half of a
# session briefing (see .claude/skills/session-start). Read-only.
set -uo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

PY=".venv/bin/python"; [ -x "$PY" ] || PY="python3"
RUFF=".venv/bin/ruff"; [ -x "$RUFF" ] || RUFF="ruff"

branch=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "?")
head=$(git rev-parse --short HEAD 2>/dev/null || echo "?")
dirty=$(git status --porcelain 2>/dev/null | grep -vc '^$' || echo "?")
ahead=$(git rev-list --count origin/"$branch".."$branch" 2>/dev/null || echo "?")
src_loc=$(find src -name '*.py' 2>/dev/null | xargs wc -l 2>/dev/null | tail -1 | awk '{print $1}')
tests=$(grep -rhoE '^def (test_[A-Za-z0-9_]+)' tests 2>/dev/null | wc -l | tr -d ' ')
ruff_status=$("$RUFF" check . >/dev/null 2>&1 && echo "clean" || echo "ISSUES")

echo "== local-agent-pipeline — state =="
echo "branch: $branch   HEAD: $head   uncommitted files: $dirty   commits ahead of origin: $ahead"
echo "source LoC (src/): ${src_loc:-?}   test functions: $tests   ruff: $ruff_status"
echo
echo "recent commits:"
git log --oneline -8 2>/dev/null | sed 's/^/  /'
echo
echo "(run scripts/gate.sh for the hard pass/fail gate; scripts/secure.sh for committed+pushed status)"
