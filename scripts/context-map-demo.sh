#!/usr/bin/env bash
# Standalone only: does not launch Hermes or change its config/home/environment.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
# Explicit --python reuses a prepared PM test interpreter read-only. Otherwise use
# documented PM wrapper in an isolated ignored development home (never production).
PY=""
if [[ "${1:-}" == "--python" ]]; then
  PY="$2"
  shift 2
fi
if [[ $# == 0 ]]; then
  set -- --output "ignored/context-map-offline-$(date +%Y%m%d-%H%M%S)"
fi
if [[ -n "$PY" ]]; then
  "$PY" -c 'import httpx; import pytest' >/dev/null
  exec "$PY" -m scripts.context_map --demo "$@"
fi
export HERMES_HOME="$ROOT/ignored/context-map-dev-home"
export HERMES_RUNTIME_DIR="$HERMES_HOME/tools"
exec scripts/run-in-hermes-env python -m scripts.context_map --demo "$@"
