# Architecture

## High-level design

`herzen-wake` runs independently from Herzen core:

- Terminal A: `herzen-wake` daemon process
- Terminal B: Herzen runtime (`pnpm dev`)
- IPC bridge: local Unix socket (`HERZEN_WAKEWORD_SOCKET`)

This separation allows wakeword detection to stay alive while Herzen restarts.

## Runtime components

1. Configuration layer (`config.py`)
- Parses env vars and validates hard constraints (sample rate, chunk sizing, model paths).

2. Wakeword engine (`WakewordEngine` in `daemon.py`)
- Loads `openWakeWord` model(s).
- Scores incoming audio frames.
- Applies threshold and cooldown gating.

3. Audio source (`audio.py`)
- Uses `sounddevice.RawInputStream`.
- Produces `int16` chunks sized by `HERZEN_WAKEWORD_CHUNK_SAMPLES`.

4. Socket server (`WakewordDaemon` in `daemon.py`)
- Binds Unix socket.
- Accepts one active client.
- Emits `ready`, `wakeword`, optional `heartbeat`, and fatal `error` events.

## Lifecycle

1. Parse/validate config.
2. Remove stale socket file and bind server socket.
3. Start wakeword engine and microphone thread.
4. Accept client and emit `ready`.
5. Stream detection events while daemon is healthy.
6. On fatal runtime failure: emit `error`, close client, exit non-zero.
7. On shutdown signal: close resources and unlink socket.

## Concurrency model

- main thread:
  - socket accept loop
  - event forwarding
  - heartbeat scheduling
  - signal handling
- detector thread:
  - blocking microphone reads
  - wakeword scoring
  - detection queue writes

## Security and hygiene

- local-only Unix socket (no TCP listener)
- stale socket cleanup on startup
- restrictive socket mode (`0600`)
- no audio transcript payloads are emitted over protocol
