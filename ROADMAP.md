# Roadmap

This is a **reference pattern**, not a product — so this roadmap deepens the
core (auditability, oversight, legibility) rather than widening scope. Items are
grouped by priority, roughly following an external review's recommendations.
Nothing here is a promise or a schedule; it is the honest backlog.

Binding invariants and the open decision register live in
[`BIBLE.md`](BIBLE.md); each item below that touches a gated area says so.

## Now (next up)

- **Audit-integrity hardening.** Make the audit story *tamper-resistant*, not
  only tamper-evident: full-length SHA-256 alongside the 16-hex fingerprint (or
  document the fingerprint as privacy-only), an optional HMAC/signature, and the
  human gate-reason recorded in the trail. _Touches the audit schema (BIBLE §4)
  and the integrity claim (§3) — shape to be agreed with the maintainer first._
- **Reproducible installs.** `uv.lock` for the Python side (done); keep it and
  `web/package-lock.json` current, both watched by Dependabot.

## Next

- **Config schema-validation in the CLI** — fail fast on a malformed
  `policy.yaml` / `pipeline.yaml` at the boundary, with a clear message.
- **CI matrix** across Python 3.11 / 3.12 / 3.13, plus `pip-audit` in the gate.
- **Document the reviewer PII regex** explicitly as a demo guardrail, not a
  compliance-grade detector.

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
