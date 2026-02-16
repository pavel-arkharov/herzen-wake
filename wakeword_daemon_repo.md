# Wakeword Daemon Task (`herzen-wake` Separate Repo)

Use this prompt in a coding chat that works in the separate wakeword repo (planned path: `/Users/parkharo/Programming/herzen-wake`).

---

You are implementing a persistent local wakeword daemon for Herzen.

## Why this repo exists

Herzen (main repo) is a Node/TypeScript assistant and should not own heavy wakeword inference runtime details.

Wakeword detection must:

- remain local/offline
- not depend on service accounts (no vendor AccessKey)
- survive frequent `pnpm dev` restarts in Herzen

So wakeword runs as a separate daemon process in terminal A, while Herzen runs in terminal B.

## Critical context about Herzen (consumer)

Herzen core expects trigger behavior with strict semantics:

- wakeword detections are discrete events (not a stream exposed to user)
- core has one pending trigger waiter at a time
- if trigger source closes: clean shutdown path
- if trigger source fails/protocol breaks: failure path

Herzen currently uses typed trigger-domain errors:

- `SOURCE_CLOSED`
- `SOURCE_FAILED`

Design daemon protocol and lifecycle so Herzen can map cleanly to these states.

## Target backend

Use `openWakeWord` in Python.

Baseline assumptions:

- macOS only for current MVP
- microphone audio must be 16-bit mono 16kHz PCM
- frame chunks should align with openWakeWord guidance (80ms multiples)

## Shared contract (must follow)

Primary contract lives in Herzen repo:

- `/Users/parkharo/Programming/herzen/docs/architecture/wakeword_sidecar_contract.md`

This daemon must implement that protocol exactly unless change is coordinated.

## Scope

In scope:

- Python daemon process (`wakewordd`)
- microphone capture + openWakeWord inference loop
- Unix socket server + newline-delimited JSON events
- config/env parsing and validation
- graceful shutdown and cleanup
- minimal tests for protocol/config behavior

Out of scope:

- training pipeline automation for custom wakewords
- GUI, web dashboard, or remote control APIs
- cloud deployment

## Recommended repo structure

- `README.md`
- `pyproject.toml` (or requirements + tooling)
- `src/herzen_wake/daemon.py`
- `src/herzen_wake/config.py`
- `src/herzen_wake/protocol.py`
- `src/herzen_wake/audio.py`
- `tests/`
- optional `scripts/run_dev.sh`

## Environment contract

Implement these env vars:

- `HERZEN_WAKEWORD_SOCKET` (required path)
- `HERZEN_WAKEWORD_MODEL_PATHS` (comma-separated `.tflite`/`.onnx` paths)
- `HERZEN_WAKEWORD_THRESHOLD` (0..1, default `0.5`)
- `HERZEN_WAKEWORD_COOLDOWN_MS` (default `1500`)
- `HERZEN_WAKEWORD_CHUNK_SAMPLES` (default `1280`)
- `HERZEN_WAKEWORD_SAMPLE_RATE` (default `16000`)
- `HERZEN_WAKEWORD_MIC_DEVICE` (optional, default system input)

Validation failures should exit non-zero with clear stderr messages.

## Protocol behavior requirements

On client connect:

- send `ready` message first

During runtime:

- send `wakeword` messages when detection score >= threshold and outside cooldown
- include keyword/model, score, threshold, timestamp
- optional heartbeat every 5s

On internal fatal error:

- send `error` message with code + message where possible
- close socket cleanly

Policy:

- support one active client in MVP
- if second client connects, refuse politely (or close previous with clear warning)

## Implementation plan

### Increment 1: Project bootstrap + config/protocol definitions

- create package scaffolding
- implement config parser + validation
- define protocol message schemas and serializer

### Increment 2: Daemon socket server + lifecycle

- bind Unix socket
- remove stale socket file safely on startup
- enforce socket file permissions for local process use
- implement accept loop + graceful SIGINT/SIGTERM shutdown

### Increment 3: openWakeWord detection loop

- initialize model(s)
- initialize microphone capture
- stream frames into model
- produce wakeword events with cooldown gate

### Increment 4: Reliability hardening

- handle microphone disconnect/runtime errors
- convert exceptions into protocol `error` and deterministic exit codes
- ensure resources always close (mic, model, socket)

### Increment 5: Smoke and diagnostics

- add concise stdout logging for startup/ready/client-connect/detections/errors
- provide one command to run daemon locally
- verify reconnect behavior when Herzen restarts

## Acceptance criteria

- daemon can run continuously while Herzen restarts
- wakeword events continue flowing after Herzen reconnects
- no busy-loop CPU spikes at idle
- Ctrl+C always exits quickly and releases socket/mic handles
- protocol stays compatible with Herzen client expectations

Suggested verification commands:

- `python -m herzen_wake.daemon --help` (if CLI wrapper exists)
- test command chosen for repo tooling (`pytest`, etc.)
- manual connect test via simple local socket client

## Deliverables expected

1. Implementation summary by increment
2. Protocol examples (ready/wakeword/error JSON lines)
3. Commands run + outcomes
4. Open issues/next steps (max 5)
