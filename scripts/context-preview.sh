#!/usr/bin/env bash
# Read-only use of an existing interpreter. Never provisions or changes Hermes state.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
PY="${HERMES_PYTHON:-python3}"
if [[ "${1:-}" == "--python" ]]; then
  PY="${2:?--python requires an interpreter}"
  shift 2
fi
exec "$PY" -m scripts.context_preview "$@"
