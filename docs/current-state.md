# Current State

## Scope delivered

The repository currently contains an MVP daemon that:

- runs as a persistent local process on macOS
- captures microphone audio (`int16`, mono, 16kHz) using `sounddevice`
- performs wakeword scoring through `openWakeWord`
- serves newline-delimited JSON events over a Unix domain socket
- supports one active client connection at a time
- handles graceful shutdown on `SIGINT`/`SIGTERM`

## Key files

- `src/herzen_wake/daemon.py`: process lifecycle, socket server, detection loop
- `src/herzen_wake/config.py`: environment parsing and validation
- `src/herzen_wake/audio.py`: microphone stream abstraction
- `src/herzen_wake/protocol.py`: JSON message constructors/serializer
- `scripts/run_dev.sh`: development runner with practical defaults
- `scripts/run_client.sh`: Terminal B socket listener helper
- `tests/test_config.py`: configuration validation tests
- `tests/test_protocol.py`: protocol message shape/encoding tests
- `tests/test_daemon_cli.py`: debug flag parsing coverage
- `tests/test_daemon_engine.py`: wakeword engine score-type regression coverage

## Verification status

Executed successfully:

- `PYTHONPATH=src .venv/bin/pytest -q`
- `PYTHONPATH=src .venv/bin/python -m herzen_wake.daemon --help`
- `./scripts/run_dev.sh --check-config`
- daemon startup and local socket client read of `ready` message
- CLI debug-mode parsing tests
- wakeword engine regression test for NumPy scalar scores

## Current behavior decisions

- daemon requires explicit socket/model envs at config layer
- `scripts/run_dev.sh` provides default dev values when envs are unset and prefers newest root `hyartsen/hyartzen` model, then production `herzen` model
- cooldown is enforced daemon-side
- wakeword events are dropped when no active client is connected
- second client connection is rejected with `CLIENT_BUSY` error message
- `--debug-mode` enables verbose diagnostics without changing protocol contract
- detection scoring accepts Python numeric types and NumPy scalar numeric types
- model assets are organized by intent:
  - `models/production/wakewords` for active Herzen models
  - `models/production/openwakeword` for required ONNX feature models
  - `models/default/backup` for fallback/reference models

## Not yet implemented

- model training/packaging automation for custom `herzen` wakeword
- integration/system tests with a real Herzen runtime process
- advanced reconnect/backpressure metrics instrumentation
