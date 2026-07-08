# Maintainer Standard Operating Procedure

This document is for contributors maintaining or extending `local-agent-pipeline`.
It covers the development workflow, review checklist, and the specific change
procedures that most often come up.

---

## Development workflow

### Setup

```bash
uv venv --python 3.13 .venv
uv pip install -e ".[dev]" --python .venv/bin/python
```

Or with plain pip (Python 3.11+ required):

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
```

### Daily loop

```bash
.venv/bin/ruff check .           # lint — fix with --fix
.venv/bin/ruff format .          # format
.venv/bin/pytest -q              # full suite (no Ollama, runs in <1 s)
```

CI runs these three commands on every push and every PR. If CI is red the branch
does not merge.

### Running a real pipeline run

```bash
# start Ollama first, pull the models in config/pipeline.yaml
agent-pipeline run --input examples/sample-report.txt
agent-pipeline run --input examples/sample-contract.txt
agent-pipeline run --input examples/sample-contract.txt --non-interactive
agent-pipeline audit runs/<run_id>.jsonl
```

---

## Review checklist

Use this before marking a PR ready for review. Every item is a hard gate.

- [ ] `ruff check . && ruff format --check .` — zero errors, correctly formatted.
- [ ] `pytest -q` — all tests pass.
- [ ] **New behaviour has offline tests.** Use `ScriptedBackend` in `tests/conftest.py`.
      No test may contact Ollama, the filesystem outside `tmp_path`, or the network.
- [ ] **Contracts first.** If the change introduces new data that must flow between
      stages, add or update a Pydantic model in `contracts.py` before touching
      anything else. Stages are only allowed to speak in validated models.
- [ ] **Audit completeness.** Every new pipeline transition must emit exactly one
      `AuditEvent`. Run `test_audit_completeness.py` patterns to verify.
      Check `test_run_is_bracketed_by_start_and_complete` still holds.
- [ ] **No dead code, no TODOs** in the final diff.
- [ ] **`AuditEvent` schema compat** — see the section below before changing
      existing fields.
- [ ] **Docstrings** on every new or changed public symbol.
- [ ] **`CHANGELOG.md`** entry under `[Unreleased]`.

---

## Adding a new policy rule or risk trigger

Policy logic belongs in `config/policy.yaml`. No Python change is required for
most additions.

**Adding a PII pattern**

1. Open `config/policy.yaml`.
2. Under `risk_triggers.pii_patterns`, add a named entry:
   ```yaml
   passport: '\b[A-Z]{1,2}[0-9]{6,9}\b'
   ```
3. The reviewer will automatically test it and emit `pii:passport` in `policy_flags`.
4. Add a test in `tests/test_policy_gate.py` confirming the new flag fires on a
   matching document and is absent on a clean one. Use the existing
   `test_contract_triggers_pii_and_value_flags` pattern.

**Changing the contract-value threshold**

Edit `contract_value_threshold_eur` in `config/policy.yaml`. The existing tests
use `EUR 150,000` with a threshold of `100,000`; if you lower the threshold below
`150,000` the existing tests remain valid.

**Adding a new heuristic that requires Python code**

1. Add the check in `Reviewer._heuristics` in `reviewer.py`. Follow the
   existing pattern: append to `flags` and `reasons`, never mutate the input.
2. Add a named constant or pattern to `policy.yaml` if the check has a
   configurable parameter.
3. Add tests in `tests/test_policy_gate.py` with a scripted backend, no Ollama.

**Changing the minimum-confidence floor**

Edit `min_confidence` in `config/policy.yaml`. The test
`test_low_confidence_escalates_even_when_clean` uses `0.2` with a floor of `0.6`;
keep that invariant or update the test.

---

## Adding an action to the whitelist

The action space is the contract between policy and the planner. Extending it
requires touching three places:

1. **`contracts.py`** — add the new value to the `Action` `StrEnum`:
   ```python
   class Action(StrEnum):
       CLASSIFY = "classify"
       EXTRACT  = "extract"
       SUMMARIZE = "summarize"
       TRANSLATE = "translate"   # new
   ```

2. **`config/policy.yaml`** — add the action name to `action_space`:
   ```yaml
   action_space:
     - classify
     - extract
     - summarize
     - translate
   ```

3. **`worker.py`** — add an entry to `_ACTION_INSTRUCTIONS` with the prompt
   that tells the model what JSON shape to return:
   ```python
   Action.TRANSLATE: (
       "Translate the document into English. Return JSON with keys: "
       '"translation" (string) and "confidence" (0.0-1.0).'
   ),
   ```

4. Add tests:
   - In `tests/test_contracts.py`, update `test_action_space_is_exactly_three`
     (rename and add the new value).
   - In `tests/test_pipeline_flow.py`, add a backend that emits the new action
     and verify the worker returns a valid result.

Note: removing an action from the whitelist does not require a migration because
existing JSONL trails are append-only and already record the full `action` string.

---

## Release procedure

There is no automated release pipeline. This is a reference pattern; releases
are milestone markers, not distributed packages.

1. Decide on the version number (semantic: `MAJOR.MINOR.PATCH`). All current
   changes are backward-compatible, so increment the minor or patch version.
2. Update `version` in `pyproject.toml`.
3. Update `__version__` in `src/agent_pipeline/__init__.py`.
4. Move all entries from `[Unreleased]` in `CHANGELOG.md` to a new
   `[X.Y.Z] - YYYY-MM-DD` section, and add the comparison link at the bottom.
5. Commit: `chore: release vX.Y.Z`.
6. Tag: `git tag -a vX.Y.Z -m "Release vX.Y.Z"`.
7. Push the commit and the tag: `git push && git push --tags`.
8. Create a GitHub release from the tag, pasting the CHANGELOG section as
   the release notes.

There is deliberately no `pypi.yml` workflow. Publishing to PyPI would change
the project's surface (versioned package, install from the internet) in a way
that conflicts with its "local only, no data egress" framing.

---

## Keeping the audit schema compatible with the sibling toolkit

The `AuditEvent` model in `contracts.py` is the integration contract with
[`agentic-ai-governance-toolkit`](https://github.com/leonkoellerwirth-arch/agentic-ai-governance-toolkit).
Its `log_analyzer` reads the same JSONL format.

**Stable fields** — do not rename or remove these without coordinating with the
sibling repo:

| Field | Type | Notes |
|-------|------|-------|
| `timestamp` | ISO-8601 datetime with TZ | Always UTC |
| `run_id` | string | Uniquely identifies the run |
| `actor` | `"planner"` / `"worker"` / `"reviewer"` / `"human"` / `"system"` | Enum values |
| `action` | string | e.g. `"plan"`, `"execute"`, `"review"`, `"gate_decision"` |
| `decision` | string or null | e.g. `"pass"`, `"escalate"`, `"reject"`, `"completed"` |
| `policy_flags` | list of strings | May be extended; the sibling must tolerate unknown values |
| `prev_hash` | string or null | Tamper-evidence chain: previous event's `entry_hash` |
| `entry_hash` | string or null | Tamper-evidence chain: hash of this event + `prev_hash` |

**Tamper-evidence chain.** `prev_hash`/`entry_hash` link the events into an
append-only chain that `audit.verify_chain` (and `agent-pipeline audit --verify`)
checks. `entry_hash` is computed over the canonical JSON of the event *excluding
`entry_hash` itself* (see `audit.chain_hash`). **Any tool that rewrites a trail
must recompute the chain**, or the trail will — correctly — fail verification.
Never edit a trail in place; treat it as immutable.

**Safe to add:** new optional fields with `None` defaults — Pydantic ignores
unknown fields on deserialization, so the sibling toolkit continues to work.
Note that adding a field changes every `entry_hash` (the field is included in
the canonical form), so regenerate committed example trails when you do.

**Requires coordination:** renaming a field, changing a field's type, or
removing a field. Open an issue in both repos before making that kind of change.

**Schema drift check:** if you touch `AuditEvent`, run:
```bash
.venv/bin/python -c "
from agent_pipeline.contracts import AuditEvent
print(AuditEvent.model_json_schema())
"
```
and diff it against the schema snapshot in the sibling toolkit's documentation
before merging.
