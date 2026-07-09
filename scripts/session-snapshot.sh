#!/usr/bin/env bash
# Deterministic raw block for a HANDOFF.md entry. No AI: countable truth +
# recent commits + gate/secure status. Prepend the output to HANDOFF.md and
# fill the _(fill in)_ lines with what actually happened this session.
set -uo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

DATE="$(date +%Y-%m-%d)"; TIME="$(date +%H:%M)"
head=$(git rev-parse --short HEAD 2>/dev/null || echo "?")
branch=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo main)
ahead=$(git rev-list --count origin/"$branch".."$branch" 2>/dev/null || echo "?")
gate=$(./scripts/gate.sh >/dev/null 2>&1 && echo "PASS" || echo "FAIL")
secure=$(./scripts/secure.sh >/dev/null 2>&1 && echo "all saved" || echo "action needed")

cat <<EOF
## $DATE — Session (snapshot $TIME)

**State:** HEAD \`$head\` · $ahead commit(s) unpushed · gate **$gate** · secure **$secure**

**Commits this session (newest first):**
$(git log --oneline -15 | sed 's/^/- /')

**Done:** _(fill in — what actually changed this session)_

**Decided:** _(fill in — decisions made; also record them in BIBLE.md)_

**Open / blocked:** _(fill in — which BIBLE decision-register items block the next task?)_

**Next:** _(fill in — the concrete next step)_

**Continuity warnings:** _(fill in — invariants not to break, threads not to lose)_

---
EOF
