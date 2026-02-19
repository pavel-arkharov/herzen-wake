# herzen-wake

`herzen-wake` is a persistent local wakeword daemon that runs independently from
the main Herzen runtime. It captures microphone audio, performs wakeword
inference with openWakeWord, and emits newline-delimited JSON (`ready`,
`wakeword`, `heartbeat`, `error`) over a local Unix socket. This keeps wakeword
detection stable even while the main app is restarted during development.

This repository contains the Python daemon, configuration and protocol layers,
development runner scripts, and tests for config/protocol/engine behavior.
Mother repo: [herzen](https://github.com/pavel-arkharov/herzen).

## Requirements

- macOS
- Python 3.11+
- local microphone permissions

## Setup

1. Create and activate a virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

2. Install package and test dependencies:

```bash
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

3. Download openWakeWord ONNX models (recommended on macOS):

```bash
python -c "from openwakeword.utils import download_models; download_models(model_names=['hey_jarvis'], target_directory='./models/default/backup/wakewords')"
```

## Environment

Required:

- `HERZEN_WAKEWORD_SOCKET`: absolute or relative Unix socket path
- `HERZEN_WAKEWORD_MODEL_PATHS`: comma-separated `.onnx`/`.tflite` paths

Optional:

- `HERZEN_WAKEWORD_THRESHOLD` (default `0.5`)
- `HERZEN_WAKEWORD_COOLDOWN_MS` (default `1500`)
- `HERZEN_WAKEWORD_CHUNK_SAMPLES` (default `1280`)
- `HERZEN_WAKEWORD_SAMPLE_RATE` (default `16000`)
- `HERZEN_WAKEWORD_MIC_DEVICE` (optional input device index or name)

Example:

```bash
export HERZEN_WAKEWORD_SOCKET="$PWD/run/wakeword.sock"
export HERZEN_WAKEWORD_MODEL_PATHS="$PWD/models/default/backup/wakewords/hey_jarvis_v0.1.onnx"
export HERZEN_WAKEWORD_THRESHOLD="0.5"
```

## Run

```bash
source .venv/bin/activate
PYTHONPATH=src python -m herzen_wake.daemon
```

Or use the helper:

```bash
./scripts/run_dev.sh
```

Terminal B client listener:

```bash
./scripts/run_client.sh
```

Debug mode (verbose detection diagnostics):

```bash
./scripts/run_dev.sh --debug-mode
```

Optional debug tuning:

```bash
./scripts/run_dev.sh --debug-mode --debug-score-floor 0.05 --debug-log-interval-ms 250
```

`run_dev.sh` sets temporary dev defaults when env vars are unset:

- `HERZEN_WAKEWORD_SOCKET=$PWD/run/wakeword.sock`
- `HERZEN_WAKEWORD_MODEL_PATHS` selection order:
  - newest `$PWD/*hyartsen*.onnx` or `$PWD/*hyartzen*.onnx` (if present)
  - newest `$PWD/models/production/wakewords/herzen*.onnx` (if present)
  - newest `$PWD/models/herzen*.onnx` (legacy fallback)
  - otherwise fallback `$PWD/models/default/backup/wakewords/hey_jarvis_v0.1.onnx`

Current local model layout:

- production wakewords: `$PWD/models/production/wakewords/`
- production feature models: `$PWD/models/production/openwakeword/`
- default backup wakewords: `$PWD/models/default/backup/wakewords/`

To switch later to your trained `herzen` model, set:

```bash
export HERZEN_WAKEWORD_MODEL_PATHS="/absolute/path/to/herzen_v1.onnx"
./scripts/run_dev.sh
```

## Verify

Config check only:

```bash
PYTHONPATH=src python -m herzen_wake.daemon --check-config
```

Tests:

```bash
PYTHONPATH=src pytest
```

## Protocol examples

```json
{"type":"ready","timestamp":"2026-02-16T18:10:00.000Z","version":"0.1.0","models":["hey_jarvis_v0.1"]}
{"type":"wakeword","timestamp":"2026-02-16T18:10:05.120Z","keyword":"hey_jarvis_v0.1","score":0.82,"threshold":0.5,"model":"hey_jarvis_v0.1"}
{"type":"error","timestamp":"2026-02-16T18:10:06.001Z","code":"MIC_FAILURE","message":"Input device disconnected"}
```
