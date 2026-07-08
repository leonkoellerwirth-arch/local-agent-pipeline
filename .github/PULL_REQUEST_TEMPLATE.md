## Summary

<!-- One to three sentences: what this PR does and why. -->

## Changes

<!-- Bullet list of the concrete changes made. -->

-

## Review checklist

- [ ] `ruff check . && ruff format --check .` passes locally
- [ ] `pytest -q` passes locally (all tests offline, no Ollama needed)
- [ ] New behaviour is covered by tests using `ScriptedBackend`
- [ ] No dead code, no TODOs left in the diff
- [ ] `AuditEvent` schema changes (if any) are backward-compatible with the sibling toolkit
- [ ] Docstrings added or updated for new/changed public symbols
- [ ] `CHANGELOG.md` entry added under `[Unreleased]`

## Related issues

<!-- Closes #<n> -->
