#!/usr/bin/env bash
# Is everything saved? Checks that the working tree is committed and pushed,
# so a session never ends with unsaved or unpushed work. No AI.
set -uo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

branch=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo main)
issues=0

if [ -n "$(git status --porcelain 2>/dev/null)" ]; then
  echo "✗ uncommitted changes:"; git status --short | sed 's/^/    /'; issues=1
else
  echo "✓ working tree clean"
fi

git fetch --quiet origin "$branch" 2>/dev/null || true
ahead=$(git rev-list --count origin/"$branch".."$branch" 2>/dev/null || echo "?")
if [ "$ahead" = "0" ]; then
  echo "✓ pushed — origin/$branch is up to date"
else
  echo "✗ $ahead commit(s) not pushed to origin/$branch"; issues=1
fi

echo
[ "$issues" -eq 0 ] && echo "SECURE: all saved" || { echo "SECURE: action needed"; exit 1; }
