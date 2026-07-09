# Roadmap

This is a **reference pattern**, not a product — so this roadmap deepens the
core (auditability, oversight, legibility) rather than widening scope. Items are
grouped by priority, roughly following an external review's recommendations.
Nothing here is a promise or a schedule; it is the honest backlog.

Binding invariants and the open decision register live in
[`BIBLE.md`](BIBLE.md); each item below that touches a gated area says so.

## Done

- **Audit-integrity hardening** ✅ — the audit story is now tamper-*resistant*,
  not only tamper-*evident*: content fingerprints widened to full SHA-256, the
  human gate-reason recorded in the trail (`gate_reason`, covered by the chain),
  and an optional HMAC-SHA256 seal over the chain head (opt-in via
  `AUDIT_HMAC_KEY`, sidecar `.sig`). Schema change is additive; example trails
  regenerated.
- **Reproducible installs** ✅ — `uv.lock` and `web/package-lock.json` committed,
  both watched by Dependabot.
- **Config schema-validation** ✅ — `pipeline.yaml` / `policy.yaml` are validated
  at load (Pydantic, in `config.py`); a malformed config fails fast with a clear
  message instead of a mid-run `KeyError`.
- **CI hardening** ✅ — test matrix across Python 3.11 / 3.12 / 3.13 and a
  `pip-audit` job for known-vulnerable dependencies.
- **Reviewer PII regex documented** ✅ — called out as a demo guardrail (in
  `policy.yaml` and the README), not a compliance-grade detector.

## Next

- **Dependency PRs** — triage the open Dependabot PRs; the major web bumps
  (Tailwind 4, TypeScript 7, Vite 8) need testing against the dashboard build
  before merge.

## Later

- **Docs split** — separate Product / Security / Maintainer-workflow docs as the
  README grows.
- **Signed releases / provenance** for tagged versions.
- **GitHub Pages** for the dashboard (optional). _(A social-preview image already
  ships at [`docs/img/social-preview.png`](docs/img/social-preview.png); the
  maintainer uploads it under Settings → Social preview.)_

## Explicit non-goals

To stay small and legible, this project will **not** grow into:

- a general agent **framework** (it is the opposite of LangGraph / CrewAI /
  AutoGen — read it end to end in one sitting);
- a **hosted or multi-tenant** service (the web console is a local-only safety
  layer, never real auth — see [`SECURITY.md`](SECURITY.md));
- a dependency on heavy **provider SDKs** (all model calls stay plain HTTP);
- anything that adds surface without a real justification. **Deepen, don't
  widen.**

Have a proposal? Open an issue — see [`CONTRIBUTING.md`](CONTRIBUTING.md).
