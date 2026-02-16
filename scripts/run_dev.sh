#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [[ ! -d ".venv" ]]; then
  python3 -m venv .venv
fi

source .venv/bin/activate

DEFAULT_SOCKET="$ROOT_DIR/run/wakeword.sock"
DEFAULT_MODEL="$ROOT_DIR/models/openwakeword/hey_jarvis_v0.1.onnx"

if [[ -z "${HERZEN_WAKEWORD_SOCKET:-}" ]]; then
  export HERZEN_WAKEWORD_SOCKET="$DEFAULT_SOCKET"
fi

if [[ -z "${HERZEN_WAKEWORD_MODEL_PATHS:-}" ]]; then
  if [[ ! -f "$DEFAULT_MODEL" ]]; then
    echo "Missing default model: $DEFAULT_MODEL" >&2
    echo "Download models first or set HERZEN_WAKEWORD_MODEL_PATHS explicitly." >&2
    exit 2
  fi
  export HERZEN_WAKEWORD_MODEL_PATHS="$DEFAULT_MODEL"
fi

export PYTHONPATH="$ROOT_DIR/src${PYTHONPATH:+:$PYTHONPATH}"
exec python -m herzen_wake.daemon "$@"
