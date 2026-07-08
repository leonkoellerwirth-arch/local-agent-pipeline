# Security Policy

## Scope

`local-agent-pipeline` is a **reference pattern**, not a production service.
It is designed to run entirely on a local machine:

* No data leaves the host. All model calls go to a local Ollama instance.
* No network ports are opened. There is no server component.
* No credentials, API keys, or authentication tokens are used.
* Audit trails are written to a local directory (`runs/`) and are never
  transmitted anywhere.

The primary security surface is the local filesystem and the Ollama process
itself, both of which are outside this project's scope.

## Supported versions

Only the current `main` branch is maintained. There are no versioned releases
with separate security support windows.

## Reporting a vulnerability

If you discover a genuine security issue in this codebase (e.g. a path-traversal
bug in audit file handling, an injection vector in the YAML config loading, or
an unintended network call), please **do not open a public GitHub issue**.

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

* Behavior of Ollama itself or the models it runs.
* Issues that require the attacker to already have write access to the host
  filesystem or to the `config/` directory.
* The fact that `audit.dump_plaintext: true` writes document content to disk —
  that is an intentional, documented, opt-in feature.
