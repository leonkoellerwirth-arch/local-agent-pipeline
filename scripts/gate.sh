#!/usr/bin/env bash
# Hard quality gate — the invariants from BIBLE.md, checked deterministically.
# Exits non-zero if anything fails. Used by session-stop before committing.
set -uo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

PY=".venv/bin/python"; [ -x "$PY" ] || PY="python3"
RUFF=".venv/bin/ruff"; [ -x "$RUFF" ] || RUFF="ruff"
fail=0
check() { if eval "$2" >/dev/null 2>&1; then echo "  ✓ $1"; else echo "  ✗ $1"; fail=1; fi; }

echo "== hard gate =="
check "ruff check clean"            "$RUFF check ."
check "ruff format clean"           "$RUFF format --check ."
check "pytest green (offline)"      "$PY -m pytest -q"
check "no TODO/FIXME in src/"       "! grep -rniE --include='*.py' 'TODO|FIXME|XXX' src"
check "no customer-internal names"  "! grep -rniE --exclude-dir=__pycache__ '(daimler|toennies|tönnies)' src tests examples config README.md"
check "no obvious secrets tracked"  "! git grep -nIE '(sk-[A-Za-z0-9]{20,}|BEGIN (RSA|OPENSSH) PRIVATE KEY|AIza[0-9A-Za-z_-]{30,})' -- . ':(exclude).env.example'"
check "internal brief not tracked"  "! git ls-files --error-unmatch CLAUDE-CODE-BRIEFING-local-agent-pipeline.md"
if [ -d web/node_modules ]; then
  check "web build (tsc + vite)"    "(cd web && npm run build)"
else
  echo "  · web build skipped (web/node_modules absent — run web/start.sh once)"
fi

echo
[ "$fail" -eq 0 ] && echo "GATE: PASS" || { echo "GATE: FAIL"; exit 1; }
