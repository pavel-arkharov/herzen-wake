from __future__ import annotations

import argparse
import logging
import os
import queue
import signal
import socket
import stat
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import numpy as np

from .audio import AudioError, SoundDeviceAudioSource
from .config import ConfigError, WakewordConfig
from .protocol import (
    encode_message,
    error_message,
    heartbeat_message,
    ready_message,
    utc_now_iso,
    wakeword_message,
)

DAEMON_VERSION = "0.1.0"
HEARTBEAT_INTERVAL_SECONDS = 5.0

EXIT_OK = 0
EXIT_CONFIG_ERROR = 2
EXIT_RUNTIME_ERROR = 3


@dataclass(frozen=True)
class DetectionEvent:
    keyword: str
    score: float
    threshold: float
    model: str | None
    timestamp: str


@dataclass(frozen=True)
class FatalEvent:
    code: str
    message: str


class WakewordEngine:
    def __init__(self, config: WakewordConfig):
        self._config = config
        self._model = None
        self._model_names: list[str] = []
        self._last_detection_monotonic = 0.0

    @property
    def model_names(self) -> list[str]:
        return list(self._model_names)

    def start(self) -> None:
        model_paths = [str(path) for path in self._config.model_paths]
        model_kwargs = self._resolve_feature_model_kwargs()

        try:
            from openwakeword.model import Model

            self._model = Model(
                wakeword_models=model_paths,
                inference_framework=self._config.inference_framework,
                **model_kwargs,
            )
        except Exception as exc:
            hint = (
                " Ensure openWakeWord embedding/melspectrogram model files are available "
                "and use ONNX model paths on macOS."
            )
            raise RuntimeError(f"Failed to initialize openWakeWord model: {exc}.{hint}") from exc

        try:
            self._model_names = sorted(str(name) for name in self._model.models.keys())
        except Exception:
            self._model_names = [path.stem for path in self._config.model_paths]

    def stop(self) -> None:
        if self._model is None:
            return
        try:
            self._model.reset()
        except Exception:
            pass
        self._model = None

    def predict(self, chunk: np.ndarray) -> DetectionEvent | None:
        if self._model is None:
            raise RuntimeError("Wakeword engine is not started.")

        scores = self._model.predict(chunk)
        if not isinstance(scores, dict) or not scores:
            return None

        best_keyword = ""
        best_score = float("-inf")
        for keyword, raw_score in scores.items():
            if not isinstance(raw_score, (float, int)):
                continue
            score = float(raw_score)
            if score > best_score:
                best_keyword = str(keyword)
                best_score = score

        if not best_keyword or best_score < self._config.threshold:
            return None

        now = time.monotonic()
        cooldown_seconds = self._config.cooldown_ms / 1000.0
        if now - self._last_detection_monotonic < cooldown_seconds:
            return None
        self._last_detection_monotonic = now

        return DetectionEvent(
            keyword=best_keyword,
            score=best_score,
            threshold=self._config.threshold,
            model=best_keyword,
            timestamp=utc_now_iso(),
        )

    def _resolve_feature_model_kwargs(self) -> dict[str, str]:
        extension = ".onnx" if self._config.inference_framework == "onnx" else ".tflite"
        models_dir = self._config.model_paths[0].parent

        melspec_path = models_dir / f"melspectrogram{extension}"
        embedding_path = models_dir / f"embedding_model{extension}"

        if melspec_path.exists() and embedding_path.exists():
            return {
                "melspec_model_path": str(melspec_path),
                "embedding_model_path": str(embedding_path),
            }
        return {}


class WakewordDaemon:
    def __init__(
        self,
        config: WakewordConfig,
        *,
        audio_source_factory: Callable[[WakewordConfig], SoundDeviceAudioSource] | None = None,
    ):
        self.config = config
        self._audio_source_factory = audio_source_factory or (
            lambda cfg: SoundDeviceAudioSource(
                sample_rate=cfg.sample_rate,
                chunk_samples=cfg.chunk_samples,
                mic_device=cfg.mic_device,
            )
        )
        self._engine = WakewordEngine(config)
        self._stop_event = threading.Event()
        self._detection_queue: queue.Queue[DetectionEvent] = queue.Queue()
        self._fatal_queue: queue.Queue[FatalEvent] = queue.Queue()
        self._server_socket: socket.socket | None = None
        self._client_socket: socket.socket | None = None
        self._detection_thread: threading.Thread | None = None
        self._audio_source: SoundDeviceAudioSource | None = None
        self._heartbeat_deadline = time.monotonic() + HEARTBEAT_INTERVAL_SECONDS
        self._lock = threading.Lock()

    def run(self) -> int:
        self._install_signal_handlers()
        self._prepare_socket()
        self._engine.start()
        self._start_detection_loop()

        logging.info("wakewordd started (socket=%s)", self.config.socket_path)
        exit_code = EXIT_OK

        try:
            while True:
                self._accept_client_if_available()
                self._flush_detection_events()
                self._emit_heartbeat_if_due()

                fatal = self._pop_fatal_event()
                if fatal is not None:
                    logging.error("Fatal daemon error [%s]: %s", fatal.code, fatal.message)
                    self._send_error_and_close_active_client(fatal)
                    exit_code = EXIT_RUNTIME_ERROR
                    break

                if self._stop_event.is_set():
                    break

                if self._detection_thread and not self._detection_thread.is_alive():
                    self._publish_fatal("MODEL_FAILURE", "Wakeword detection loop stopped unexpectedly.")

                time.sleep(0.02)
        finally:
            self.shutdown()
        return exit_code

    def shutdown(self) -> None:
        self._stop_event.set()

        self._close_active_client()

        server = self._server_socket
        self._server_socket = None
        if server is not None:
            try:
                server.close()
            except OSError:
                pass

        if self._detection_thread is not None:
            self._detection_thread.join(timeout=2.0)
            self._detection_thread = None

        if self._audio_source is not None:
            self._audio_source.stop()
            self._audio_source = None

        self._engine.stop()
        _unlink_socket_file(self.config.socket_path)
        logging.info("wakewordd stopped")

    def _install_signal_handlers(self) -> None:
        def _handler(signum: int, _frame: object) -> None:
            logging.info("Received signal %s, shutting down.", signum)
            self._stop_event.set()

        signal.signal(signal.SIGINT, _handler)
        signal.signal(signal.SIGTERM, _handler)

    def _prepare_socket(self) -> None:
        self.config.socket_path.parent.mkdir(parents=True, exist_ok=True)
        _remove_stale_socket_file(self.config.socket_path)

        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            server.bind(str(self.config.socket_path))
            os.chmod(self.config.socket_path, 0o600)
            server.listen(1)
            server.settimeout(0.1)
        except Exception:
            server.close()
            raise
        self._server_socket = server

    def _start_detection_loop(self) -> None:
        self._audio_source = self._audio_source_factory(self.config)
        thread = threading.Thread(
            target=self._run_detection_loop,
            name="wakeword-detector",
            daemon=True,
        )
        self._detection_thread = thread
        thread.start()

    def _run_detection_loop(self) -> None:
        assert self._audio_source is not None

        try:
            self._audio_source.start()
            logging.info("Microphone stream started.")
            while not self._stop_event.is_set():
                chunk = self._audio_source.read_chunk()
                event = self._engine.predict(chunk)
                if event is not None:
                    self._detection_queue.put(event)
        except AudioError as exc:
            self._publish_fatal(
                "MIC_FAILURE",
                str(exc),
            )
        except Exception as exc:
            self._publish_fatal(
                "MODEL_FAILURE",
                f"Wakeword inference failed: {exc}",
            )
        finally:
            self._audio_source.stop()

    def _publish_fatal(self, code: str, message: str) -> None:
        with self._lock:
            if self._stop_event.is_set():
                return
            self._fatal_queue.put(FatalEvent(code=code, message=message))
            self._stop_event.set()

    def _pop_fatal_event(self) -> FatalEvent | None:
        try:
            return self._fatal_queue.get_nowait()
        except queue.Empty:
            return None

    def _accept_client_if_available(self) -> None:
        server = self._server_socket
        if server is None:
            return

        try:
            conn, _ = server.accept()
        except socket.timeout:
            return
        except OSError:
            if self._stop_event.is_set():
                return
            raise

        with self._lock:
            if self._client_socket is not None:
                self._send_to_socket(
                    conn,
                    error_message(
                        code="CLIENT_BUSY",
                        message="wakewordd supports one active client connection in MVP.",
                    ),
                )
                conn.close()
                logging.warning("Rejected extra client connection while one client is active.")
                return

            self._client_socket = conn

        logging.info("Client connected.")
        if not self._send_to_active_client(
            ready_message(
                version=DAEMON_VERSION,
                models=self._engine.model_names,
            )
        ):
            self._close_active_client()
            return
        self._heartbeat_deadline = time.monotonic() + HEARTBEAT_INTERVAL_SECONDS

    def _flush_detection_events(self) -> None:
        while True:
            try:
                event = self._detection_queue.get_nowait()
            except queue.Empty:
                return

            if self._client_socket is None:
                continue

            sent = self._send_to_active_client(
                wakeword_message(
                    keyword=event.keyword,
                    score=event.score,
                    threshold=event.threshold,
                    model=event.model,
                    timestamp=event.timestamp,
                )
            )
            if sent:
                logging.info(
                    "Wakeword detected (keyword=%s score=%.3f threshold=%.3f).",
                    event.keyword,
                    event.score,
                    event.threshold,
                )

    def _emit_heartbeat_if_due(self) -> None:
        if self._client_socket is None:
            self._heartbeat_deadline = time.monotonic() + HEARTBEAT_INTERVAL_SECONDS
            return
        if time.monotonic() < self._heartbeat_deadline:
            return

        self._send_to_active_client(heartbeat_message())
        self._heartbeat_deadline = time.monotonic() + HEARTBEAT_INTERVAL_SECONDS

    def _send_error_and_close_active_client(self, fatal: FatalEvent) -> None:
        self._send_to_active_client(
            error_message(
                code=fatal.code,
                message=fatal.message,
            )
        )
        self._close_active_client()

    def _send_to_active_client(self, message: dict[str, object]) -> bool:
        with self._lock:
            client = self._client_socket

        if client is None:
            return False

        sent = self._send_to_socket(client, message)
        if not sent:
            self._close_active_client()
        return sent

    @staticmethod
    def _send_to_socket(client: socket.socket, message: dict[str, object]) -> bool:
        payload = encode_message(message)
        try:
            client.sendall(payload)
            return True
        except OSError:
            return False

    def _close_active_client(self) -> None:
        with self._lock:
            client = self._client_socket
            self._client_socket = None

        if client is None:
            return
        try:
            client.close()
        except OSError:
            pass


def _remove_stale_socket_file(path: Path) -> None:
    if not path.exists():
        return

    mode = path.lstat().st_mode
    if not stat.S_ISSOCK(mode):
        raise RuntimeError(f"Refusing to remove non-socket path: {path}")
    path.unlink()


def _unlink_socket_file(path: Path) -> None:
    if not path.exists():
        return
    try:
        mode = path.lstat().st_mode
    except OSError:
        return
    if not stat.S_ISSOCK(mode):
        return
    try:
        path.unlink()
    except OSError:
        pass


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the Herzen wakeword daemon.")
    parser.add_argument(
        "--check-config",
        action="store_true",
        help="Validate configuration and exit.",
    )
    parser.add_argument(
        "--log-level",
        default=os.environ.get("HERZEN_WAKEWORD_LOG_LEVEL", "INFO"),
        help="Python logging level (default: INFO).",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    level_name = str(args.log_level).upper()
    level = getattr(logging, level_name, logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    try:
        config = WakewordConfig.from_env()
    except ConfigError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return EXIT_CONFIG_ERROR

    if args.check_config:
        print("Configuration OK")
        print(f"socket={config.socket_path}")
        print(f"models={','.join(str(path) for path in config.model_paths)}")
        print(f"inference_framework={config.inference_framework}")
        return EXIT_OK

    daemon = WakewordDaemon(config)
    return daemon.run()


if __name__ == "__main__":
    raise SystemExit(main())
