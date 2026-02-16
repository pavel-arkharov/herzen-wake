# Operations Runbook

## Start/stop

Start:

```bash
./scripts/run_dev.sh
```

Stop:

- press `Ctrl+C` in daemon terminal

Expected shutdown behavior:

- socket closed
- microphone stream closed
- socket file unlinked

## Health checks

1. Config check:

```bash
./scripts/run_dev.sh --check-config
```

2. Unit tests:

```bash
PYTHONPATH=src .venv/bin/pytest -q
```

3. Socket `ready` smoke check (from another terminal):

```bash
python -c "import socket; s=socket.socket(socket.AF_UNIX, socket.SOCK_STREAM); s.connect('run/wakeword.sock'); print(s.recv(4096).decode().strip()); s.close()"
```

## Troubleshooting

`Configuration error: HERZEN_WAKEWORD_MODEL_PATHS ... missing model file`
- ensure model files are downloaded and path is correct

`Configuration error: tflite models require tflite-runtime ...`
- use ONNX models on macOS (`*.onnx`)

`PermissionError` when binding socket
- verify daemon is run in a normal host shell (not restricted sandbox)
- verify parent directory permissions for socket path

No microphone devices available
- grant microphone permission to terminal host
- check input device selection via `HERZEN_WAKEWORD_MIC_DEVICE`

## Model replacement workflow

When custom `herzen` wakeword model is available:

1. place model artifact(s) on disk
2. set:

```bash
export HERZEN_WAKEWORD_MODEL_PATHS="/absolute/path/to/herzen_v1.onnx"
```

3. restart daemon
4. verify `ready.models` contains the new model id

## Logging

- default level: `INFO`
- override:

```bash
HERZEN_WAKEWORD_LOG_LEVEL=DEBUG ./scripts/run_dev.sh
```
