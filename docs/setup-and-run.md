# Setup And Run

## Prerequisites

- macOS
- Python 3.11+
- microphone permission granted to terminal/app host

## Initial setup

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

## Download baseline models

The project currently uses a temporary default wakeword model (`hey_jarvis`) until
the custom `herzen` model is shipped.

```bash
python -c "from openwakeword.utils import download_models; download_models(model_names=['hey_jarvis'], target_directory='./models/openwakeword')"
```

## Environment variables

Required:

- `HERZEN_WAKEWORD_SOCKET`: Unix socket path
- `HERZEN_WAKEWORD_MODEL_PATHS`: comma-separated model paths (`.onnx`/`.tflite`)

Optional:

- `HERZEN_WAKEWORD_THRESHOLD` (default `0.5`)
- `HERZEN_WAKEWORD_COOLDOWN_MS` (default `1500`)
- `HERZEN_WAKEWORD_CHUNK_SAMPLES` (default `1280`)
- `HERZEN_WAKEWORD_SAMPLE_RATE` (default `16000`, currently enforced)
- `HERZEN_WAKEWORD_MIC_DEVICE` (input device index or name)
- `HERZEN_WAKEWORD_LOG_LEVEL` (default `INFO`)

## Recommended local run

```bash
./scripts/run_dev.sh
```

## Debug mode

Enable verbose detection diagnostics:

```bash
./scripts/run_dev.sh --debug-mode
```

Tune diagnostics:

```bash
./scripts/run_dev.sh --debug-mode --debug-score-floor 0.05 --debug-log-interval-ms 250
```

When env vars are unset, `run_dev.sh` uses:

- `HERZEN_WAKEWORD_SOCKET=$PWD/run/wakeword.sock`
- `HERZEN_WAKEWORD_MODEL_PATHS=$PWD/models/openwakeword/hey_jarvis_v0.1.onnx`

## Config-only validation

```bash
./scripts/run_dev.sh --check-config
```

## Switching to trained `herzen` model later

```bash
export HERZEN_WAKEWORD_MODEL_PATHS="/absolute/path/to/herzen_v1.onnx"
./scripts/run_dev.sh
```

## Test command

```bash
PYTHONPATH=src .venv/bin/pytest -q
```
