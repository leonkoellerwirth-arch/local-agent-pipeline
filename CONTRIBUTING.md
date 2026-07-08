# Contributing

Thank you for considering a contribution to `local-agent-pipeline`. Because the
project is a **reference pattern**, the bar for additions is deliberate restraint:
every file should still be explainable in a few minutes after your change.

## Development setup

```bash
# Python 3.11 or newer required
uv venv --python 3.13 .venv
uv pip install -e ".[dev]" --python .venv/bin/python
```

Or with plain pip:

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
```

## Running tests and lint

```bash
.venv/bin/ruff check .           # lint
.venv/bin/ruff format --check .  # formatting check
.venv/bin/pytest -q              # test suite (no Ollama required)
```

The CI workflow runs exactly these three commands. A PR cannot merge if any
of them fails.

## Commit convention

Prefix each commit message with one of:

| Prefix | When to use |
|--------|-------------|
| `feat:` | new behaviour visible to users |
| `fix:` | corrects wrong behaviour |
| `test:` | adds or changes tests only |
| `docs:` | documentation only |
| `chore:` | tooling, CI, or dependency updates |

Example: `feat: add --non-interactive flag to run command`

## Pull request expectations

1. **Tests first.** All new code that adds behaviour must come with offline
   tests (no Ollama, no network). The `ScriptedBackend` in `tests/conftest.py`
   is the right tool.
2. **No dead code, no TODOs.** Finish the change before opening the PR.
3. **Contracts before implementation.** If your change touches the `AuditEvent`
   schema, consider backward compatibility with the sibling `agentic-ai-governance-toolkit`.
4. **Keep it small.** Scope one logical change per PR. Large refactors should
   be discussed in an issue first.
5. **Sober tone.** Match the existing docstring style — engineering prose, no hype.

## Where things live

| Path | What it is |
|------|-----------|
| `src/agent_pipeline/contracts.py` | Pydantic models — the shared vocabulary |
| `src/agent_pipeline/cli.py` | CLI entry point and pipeline orchestrator |
| `src/agent_pipeline/gate.py` | Human and policy gate implementations |
| `src/agent_pipeline/audit.py` | JSONL audit logging |
| `config/pipeline.yaml` | Model names, timeouts, retry settings |
| `config/policy.yaml` | Action space, PII patterns, thresholds |
| `tests/conftest.py` | `ScriptedBackend` — the offline LLM fake |
| `docs/SOP.md` | Maintainer standard operating procedure |

## Questions

Open an issue. For security disclosures, see [SECURITY.md](SECURITY.md).
