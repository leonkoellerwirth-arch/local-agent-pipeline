# Security Policy

## Scope

`local-agent-pipeline` is a **reference pattern**, not a production service. It is
built to run on a developer's machine and is not hardened for exposure to a
network. What follows is the honest threat model — read it before trusting the
project with anything sensitive.

### Local by default

With the shipped configuration, every model call goes to a **local Ollama**
instance (`http://localhost:11434`). In this default mode:

* No document content leaves the host.
* No API keys or authentication tokens are used.
* The only network traffic is localhost → Ollama.

### External providers are opt-in — and send your data off-host

You can route any role (typically the reviewer) to an external provider by
prefixing its model, e.g. `reviewer: openai:gpt-4o` (see
[`.env.example`](.env.example) and the README's "External review" section). When
you do:

* That role's **prompt — which includes your input document — is sent over HTTPS
  to the provider** (OpenAI, Google Gemini, or Anthropic). Data leaves the host.
* An **API key** is read from the environment / `.env`. Keep `.env` out of git
  (it is gitignored) and off shared machines. Keys are sent as request headers,
  never in a URL, so they do not leak through error messages or logs.
* The audit trail records exactly which provider/model made each decision.

This is never the default; it happens only when you name an external provider.

### The web console opens a local port and runs the pipeline

`web/start.sh` (and `web/api_server.py`) start a small HTTP API that can launch
real pipeline runs from the browser. It is **bound to `127.0.0.1` only** and
guarded so a stray local process or a malicious web page cannot drive it:

* a shared session token (`X-API-Token`), generated at startup or pinned via
  `$API_TOKEN`, which the Vite dev-proxy forwards so the browser never holds it;
* a localhost `Origin` allow-list;
* a maximum request-body size and a concurrent-run cap;
* example ids validated against the bundled set (no path traversal).

These guards make it reasonable on a shared developer machine. They are **not** a
substitute for real authentication — **do not bind this console to a public
interface or expose it to the internet.**

### Audit trails on disk

Trails are written to a local directory (`runs/`) and are never transmitted
anywhere by this project. By default they store only **hashes** of prompts and
outputs, so a trail can be shared without leaking document content. Setting
`audit.dump_plaintext: true` additionally writes the plaintext to disk — an
intentional, documented, opt-in feature.

## Supported versions

Only the current `main` branch is maintained. There are no versioned releases
with separate security support windows.

## Reporting a vulnerability

If you discover a genuine security issue in this codebase (e.g. a path-traversal
bug in audit or example file handling, an injection vector in the YAML config
loading, a secret that leaks into logs, or a missing guard on the web console),
please **do not open a public GitHub issue**.

Instead, email the maintainer directly:

**contact@leonkoellerwirth.de**

Include:
1. A short description of the vulnerability.
2. Steps to reproduce it.
3. The potential impact as you see it.

You will receive an acknowledgement within 72 hours. Because this is a small
reference project maintained by one person, response and patch timelines are
best-effort, not governed by a formal SLA.

## Out of scope

The following are **not** considered security vulnerabilities for this project:

* Behavior of Ollama, the external providers, or the models they run.
* The fact that routing a role to an external provider sends data to that
  provider — that is the documented, opt-in purpose of the feature.
* Exposing the local web console on a non-localhost interface — it is documented
  as localhost-only and not built for that.
* Issues that require the attacker to already have write access to the host
  filesystem or to the `config/` directory.
* The fact that `audit.dump_plaintext: true` writes document content to disk —
  that is an intentional, documented, opt-in feature.
