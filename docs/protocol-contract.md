# Protocol Contract

## Transport

- Unix domain socket
- UTF-8 newline-delimited JSON (one object per line)
- daemon emits events only (client sends no protocol messages in MVP)

## Message envelope

All messages include:

- `type` (string)
- `timestamp` (ISO-8601 UTC string)

## `ready`

Sent immediately after successful client connection.

Required fields:

- `version` (daemon version string)
- `models` (array of loaded model names)

Example:

```json
{"type":"ready","timestamp":"2026-02-16T19:33:31.455Z","version":"0.1.0","models":["hey_jarvis_v0.1"]}
```

## `wakeword`

Sent when:

- score >= configured threshold
- cooldown window has elapsed

Required fields:

- `keyword` (string)
- `score` (number)
- `threshold` (number)

Optional fields:

- `model` (string)

Example:

```json
{"type":"wakeword","timestamp":"2026-02-16T19:34:00.120Z","keyword":"hey_jarvis_v0.1","score":0.82,"threshold":0.5,"model":"hey_jarvis_v0.1"}
```

## `heartbeat` (optional)

Liveness signal emitted approximately every 5 seconds while a client is connected.

Example:

```json
{"type":"heartbeat","timestamp":"2026-02-16T19:34:05.000Z"}
```

## `error`

Fatal daemon-side failure event. Usually followed by socket close.

Required fields:

- `code` (string)
- `message` (string)

Example:

```json
{"type":"error","timestamp":"2026-02-16T19:34:10.001Z","code":"MIC_FAILURE","message":"Failed to start microphone input: ..."}
```

## Single-client policy

- only one active client is supported
- extra clients are rejected with:

```json
{"type":"error","timestamp":"...","code":"CLIENT_BUSY","message":"wakewordd supports one active client connection in MVP."}
```

## Herzen error mapping expectation

- clean socket close -> `SOURCE_CLOSED`
- daemon `error` message -> `SOURCE_FAILED`
- malformed/invalid protocol data -> `SOURCE_FAILED`
