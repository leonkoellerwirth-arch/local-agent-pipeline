#!/usr/bin/env bash
#
# One-command setup for local-agent-pipeline (macOS / Linux).
#
#   ./setup.sh                 full setup: venv, install, pull models, tests, demo
#   ./setup.sh --skip-models   skip the Ollama model downloads
#   ./setup.sh --no-demo       skip the example run at the end
#   ./setup.sh -h | --help     show this help
#
# The script is idempotent: re-running reuses the existing .venv and only does
# what is still needed. It never touches your system Python — everything lands
# in a project-local .venv.

set -euo pipefail

SKIP_MODELS=0
RUN_DEMO=1

for arg in "$@"; do
  case "$arg" in
    --skip-models) SKIP_MODELS=1 ;;
    --no-demo)     RUN_DEMO=0 ;;
    -h|--help)     sed -n '3,17p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "Unknown option: $arg (use --help)"; exit 2 ;;
  esac
done

# Always run from the repo root (the directory containing this script).
cd "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# --- pretty output --------------------------------------------------------
if [ -t 1 ]; then BOLD=$(printf '\033[1m'); DIM=$(printf '\033[2m'); GREEN=$(printf '\033[32m'); YELLOW=$(printf '\033[33m'); RESET=$(printf '\033[0m'); else BOLD=""; DIM=""; GREEN=""; YELLOW=""; RESET=""; fi
step() { echo "${BOLD}==>${RESET} $*"; }
warn() { echo "${YELLOW}!  $*${RESET}"; }
ok()   { echo "${GREEN}✓${RESET} $*"; }

VENV=".venv"
VENV_PY="$VENV/bin/python"

# --- 1. find a Python >= 3.11 --------------------------------------------
find_python() {
  local candidate
  for candidate in python3.13 python3.12 python3.11; do
    if command -v "$candidate" >/dev/null 2>&1; then echo "$candidate"; return 0; fi
  done
  if command -v python3 >/dev/null 2>&1 && \
     python3 -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)'; then
    echo python3; return 0
  fi
  return 1
}

# --- 2. create the virtualenv --------------------------------------------
if [ -x "$VENV_PY" ]; then
  step "Reusing existing virtualenv ($VENV)"
else
  PY=$(find_python) || {
    echo "${YELLOW}Python >= 3.11 not found.${RESET} This project needs 3.11+."
    echo "Install it (e.g. 'brew install python@3.13') and re-run ./setup.sh"
    exit 1
  }
  step "Creating virtualenv with $PY"
  if command -v uv >/dev/null 2>&1; then
    uv venv "$VENV" --python "$PY"
  else
    "$PY" -m venv "$VENV"
  fi
fi

# --- 3. install the package (with dev extras) ----------------------------
step "Installing agent-pipeline and dev dependencies"
if command -v uv >/dev/null 2>&1; then
  uv pip install -e ".[dev]" --python "$VENV_PY" >/dev/null
else
  "$VENV_PY" -m pip install --upgrade pip >/dev/null
  "$VENV_PY" -m pip install -e ".[dev]" >/dev/null
fi
ok "Installed ($("$VENV_PY" --version))"

# --- 4. scaffold .env and report configured external providers ----------
step "External-review providers (optional)"
if [ ! -f .env ] && [ -f .env.example ]; then
  cp .env.example .env
  ok "Created .env from .env.example — add keys to enable OpenAI/Gemini/Claude"
fi
if [ -f .env ]; then
  CONFIGURED=""
  grep -qE '^(OPENAI_API_KEY|OPEN_AI_KEY)=.+'          .env && CONFIGURED="$CONFIGURED openai"
  grep -qE '^(GEMINI_API_KEY|GEMINI_KEY|GOOGLE_API_KEY)=.+' .env && CONFIGURED="$CONFIGURED gemini"
  grep -qE '^(ANTHROPIC_API_KEY|CLAUDE_KEY)=.+'        .env && CONFIGURED="$CONFIGURED claude"
  if [ -n "$CONFIGURED" ]; then
    ok "Keys found for:$CONFIGURED — route a role in config/pipeline.yaml (e.g. reviewer: openai:gpt-4o)"
  else
    echo "${DIM}   No cloud keys set — staying fully local. Edit .env to enable stronger review.${RESET}"
  fi
fi

# --- 5. pull the Ollama models declared in config/pipeline.yaml ----------
MODELS_READY=0
if [ "$SKIP_MODELS" -eq 1 ]; then
  warn "Skipping model download (--skip-models)."
elif ! command -v ollama >/dev/null 2>&1; then
  warn "Ollama not found — skipping model download."
  warn "Install it from https://ollama.com/download, then re-run ./setup.sh"
else
  # Read the model names straight from config so this never drifts from the app.
  MODELS=$("$VENV_PY" - <<'PY'
import yaml
cfg = yaml.safe_load(open("config/pipeline.yaml"))
print(" ".join(sorted(set(cfg["models"].values()))))
PY
)
  step "Pulling Ollama models: $MODELS"
  MODELS_READY=1
  for m in $MODELS; do
    if ! ollama pull "$m"; then
      warn "Could not pull '$m' (is the Ollama server running?). Continuing."
      MODELS_READY=0
    fi
  done
  [ "$MODELS_READY" -eq 1 ] && ok "Models ready"
fi

# --- 6. smoke test (never needs Ollama) ----------------------------------
step "Running the test suite (offline, mocked models)"
"$VENV_PY" -m pytest -q

# --- 7. demo -------------------------------------------------------------
if [ "$RUN_DEMO" -eq 1 ]; then
  step "Demo: verifying a committed audit trail (no model needed)"
  "$VENV/bin/agent-pipeline" audit examples/expected-outputs/sample-contract.jsonl --verify
  if [ "$MODELS_READY" -eq 1 ]; then
    step "Demo: running the benign example end to end"
    "$VENV/bin/agent-pipeline" run --input examples/sample-report.txt
  else
    warn "Skipping the live example run (models not available)."
  fi
fi

# --- done ----------------------------------------------------------------
echo
ok "${BOLD}Setup complete.${RESET}"
echo "${DIM}Activate the environment:${RESET}  source $VENV/bin/activate"
echo "${DIM}Run a document:${RESET}          agent-pipeline run --input examples/sample-contract.txt"
echo "${DIM}Read a trail:${RESET}            agent-pipeline audit runs/<run_id>.jsonl [--verify]"
