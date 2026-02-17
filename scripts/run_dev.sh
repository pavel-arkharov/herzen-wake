#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [[ ! -d ".venv" ]]; then
  python3 -m venv .venv
fi

source .venv/bin/activate

DEFAULT_SOCKET="$ROOT_DIR/run/wakeword.sock"
DEFAULT_MODEL="$ROOT_DIR/models/default/backup/wakewords/hey_jarvis_v0.1.onnx"
DEFAULT_HERZEN_MODEL="$(ls -t "$ROOT_DIR"/models/production/wakewords/herzen*.onnx 2>/dev/null | head -n 1 || true)"
if [[ -z "$DEFAULT_HERZEN_MODEL" ]]; then
  DEFAULT_HERZEN_MODEL="$(ls -t "$ROOT_DIR"/models/herzen*.onnx 2>/dev/null | head -n 1 || true)"
fi

if [[ -z "${HERZEN_WAKEWORD_SOCKET:-}" ]]; then
  export HERZEN_WAKEWORD_SOCKET="$DEFAULT_SOCKET"
fi

if [[ -z "${HERZEN_WAKEWORD_MODEL_PATHS:-}" ]]; then
  if [[ -n "$DEFAULT_HERZEN_MODEL" && -f "$DEFAULT_HERZEN_MODEL" ]]; then
    export HERZEN_WAKEWORD_MODEL_PATHS="$DEFAULT_HERZEN_MODEL"
    echo "Using Herzen model: $DEFAULT_HERZEN_MODEL"
  elif [[ -f "$DEFAULT_MODEL" ]]; then
    export HERZEN_WAKEWORD_MODEL_PATHS="$DEFAULT_MODEL"
    echo "Using fallback model: $DEFAULT_MODEL"
  else
    echo "Missing default model: $DEFAULT_MODEL" >&2
    echo "Download models first or set HERZEN_WAKEWORD_MODEL_PATHS explicitly." >&2
    exit 2
  fi
fi

export PYTHONPATH="$ROOT_DIR/src${PYTHONPATH:+:$PYTHONPATH}"
exec python -m herzen_wake.daemon "$@"
