# herzen-wake

`herzen-wake` is the wakeword listener for **Herzen**. It runs as a small local
background daemon, listens to your microphone, and emits wakeword events to the
main app through a Unix socket.

**Herzen** is the main personal-assistant project (TypeScript/Node) and lives
in the mother repo: [pavel-arkharov/herzen](https://github.com/pavel-arkharov/herzen).
This repo exists so wakeword detection can stay stable and independent while
Herzen is restarted, updated, or developed.

## Quick Start (5 minutes)

Requirements:

- macOS
- Python 3.11+
- microphone permission for your terminal app

Setup:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

Download a starter model:

```bash
python -c "from openwakeword.utils import download_models; download_models(model_names=['hey_jarvis'], target_directory='./models/default/backup/wakewords')"
```

Run daemon:

```bash
./scripts/run_dev.sh
```

In another terminal (to see events):

```bash
./scripts/run_client.sh
```

## Walkthrough (2-3 minutes)

If you want the fast tour, read these in order:

1. [Current State](docs/current-state.md)  
   What is already built, what is tested, and what is still pending.
2. [Setup and Run](docs/setup-and-run.md)  
   Exact setup commands, model path behavior, and day-to-day run commands.
3. [Architecture](docs/architecture.md)  
   How the daemon is structured (config, audio, engine, socket server, lifecycle).
4. [Protocol Contract](docs/protocol-contract.md)  
   Message format (`ready`, `wakeword`, `heartbeat`, `error`) used over the Unix socket.
5. [Operations Runbook](docs/operations.md)  
   Troubleshooting and practical health checks.

Optional:

- [Open Questions](docs/open-questions.md) for planned design decisions and future tradeoffs.

## Model Setup (How To Get A Model)

You have two practical options:

1. Use the starter model (`hey_jarvis`) via the command above.
2. Use your own trained wakeword model (`.onnx`) by placing it in:
   - `models/production/wakewords/` (recommended), or
   - `models/` (legacy fallback).

`./scripts/run_dev.sh` auto-selects a model in this order:

1. newest root `*hyartsen*.onnx` or `*hyartzen*.onnx`
2. newest `models/production/wakewords/herzen*.onnx`
3. newest `models/herzen*.onnx`
4. fallback `models/default/backup/wakewords/hey_jarvis_v0.1.onnx`

If you want to force a specific file:

```bash
export HERZEN_WAKEWORD_MODEL_PATHS="/absolute/path/to/model.onnx"
./scripts/run_dev.sh
```

## Everyday Commands

Run:

```bash
./scripts/run_dev.sh
```

Config check only:

```bash
./scripts/run_dev.sh --check-config
```

Verbose debug mode:

```bash
./scripts/run_dev.sh --debug-mode
```

Tests:

```bash
PYTHONPATH=src .venv/bin/pytest -q
```

## Advanced Configuration (Optional)

Main environment variables:

- `HERZEN_WAKEWORD_SOCKET` (default: `run/wakeword.sock` in dev script)
- `HERZEN_WAKEWORD_MODEL_PATHS` (comma-separated model paths)
- `HERZEN_WAKEWORD_THRESHOLD` (default `0.5`)
- `HERZEN_WAKEWORD_COOLDOWN_MS` (default `1500`)
- `HERZEN_WAKEWORD_MIC_DEVICE` (optional input device index/name)

More detail is available in `/docs`.
