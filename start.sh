#!/usr/bin/env bash
# Convenience entry point: launch the Audit Console (API + dashboard).
# The real launcher lives in web/start.sh; this just forwards to it so you can
# run ./start.sh from the repo root. For first-time Python setup, run ./setup.sh.
exec "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/web/start.sh" "$@"
