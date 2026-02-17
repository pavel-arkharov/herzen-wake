from __future__ import annotations

import argparse
import logging
import numbers
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
DEFAULT_DEBUG_SCORE_FLOOR = 0.05
DEFAULT_DEBUG_LOG_INTERVAL_MS = 500

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
    def __init__(
        self,
        config: WakewordConfig,
        *,
        debug_mode: bool = False,
        debug_score_floor: float = DEFAULT_DEBUG_SCORE_FLOOR,
        debug_log_interval_ms: int = DEFAULT_DEBUG_LOG_INTERVAL_MS,
    ):
        self._config = config
        self._debug_mode = debug_mode
        self._debug_score_floor = debug_score_floor
        self._debug_log_interval_seconds = max(debug_log_interval_ms, 1) / 1000.0
        self._model = None
        self._model_names: list[str] = []
        self._last_detection_monotonic = 0.0
        self._last_debug_log_monotonic = 0.0

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

        now = time.monotonic()
        best_keyword = ""
        best_score = float("-inf")
        normalized_scores: dict[str, float] = {}
        for keyword, raw_score in scores.items():
            if isinstance(raw_score, bool) or not isinstance(raw_score, numbers.Real):
                continue
            score = float(raw_score)
            normalized_scores[str(keyword)] = score
            if score > best_score:
                best_keyword = str(keyword)
                best_score = score

        if self._debug_mode and normalized_scores:
            interval_elapsed = now - self._last_debug_log_monotonic >= self._debug_log_interval_seconds
            should_log_snapshot = interval_elapsed or best_score >= self._config.threshold
            if should_log_snapshot:
                if best_score >= self._debug_score_floor:
                    logging.debug(
                        "Wakeword score snapshot (best=%s score=%.3f threshold=%.3f top=%s).",
                        best_keyword,
                        best_score,
                        self._config.threshold,
                        _format_top_scores(normalized_scores),
                    )
                else:
                    logging.debug(
                        "Wakeword score snapshot below floor (best=%s score=%.3f floor=%.3f top=%s).",
                        best_keyword,
                        best_score,
                        self._debug_score_floor,
                        _format_top_scores(normalized_scores),
                    )
                self._last_debug_log_monotonic = now

        if not best_keyword or best_score < self._config.threshold:
            if self._debug_mode and best_keyword and best_score >= self._debug_score_floor:
                logging.debug(
                    "Suppressed wakeword candidate (reason=below_threshold keyword=%s score=%.3f threshold=%.3f).",
                    best_keyword,
                    best_score,
                    self._config.threshold,
                )
            return None

        cooldown_seconds = self._config.cooldown_ms / 1000.0
        cooldown_elapsed = now - self._last_detection_monotonic
        if cooldown_elapsed < cooldown_seconds:
            if self._debug_mode:
                remaining_ms = int(max(cooldown_seconds - cooldown_elapsed, 0.0) * 1000)
                logging.debug(
                    "Suppressed wakeword candidate (reason=cooldown keyword=%s score=%.3f remaining_ms=%d).",
                    best_keyword,
                    best_score,
                    remaining_ms,
                )
            return None
        self._last_detection_monotonic = now

        if self._debug_mode:
            logging.debug(
                "Accepted wakeword candidate (keyword=%s score=%.3f threshold=%.3f).",
                best_keyword,
                best_score,
                self._config.threshold,
            )

        return DetectionEvent(
            keyword=best_keyword,
            score=best_score,
            threshold=self._config.threshold,
            model=best_keyword,
            timestamp=utc_now_iso(),
        )

    def _resolve_feature_model_kwargs(self) -> dict[str, str]:
        extension = ".onnx" if self._config.inference_framework == "onnx" else ".tflite"
        primary_dir = self._config.model_paths[0].parent

        for candidate_dir in _iter_feature_model_dirs(primary_dir):
            melspec_path = candidate_dir / f"melspectrogram{extension}"
            embedding_path = candidate_dir / f"embedding_model{extension}"
            if melspec_path.exists() and embedding_path.exists():
                if self._debug_mode:
                    logging.debug("Using feature models from %s", candidate_dir)
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
        debug_mode: bool = False,
        debug_score_floor: float = DEFAULT_DEBUG_SCORE_FLOOR,
        debug_log_interval_ms: int = DEFAULT_DEBUG_LOG_INTERVAL_MS,
    ):
        self.config = config
        self._debug_mode = debug_mode
        self._audio_source_factory = audio_source_factory or (
            lambda cfg: SoundDeviceAudioSource(
                sample_rate=cfg.sample_rate,
                chunk_samples=cfg.chunk_samples,
                mic_device=cfg.mic_device,
            )
        )
        self._engine = WakewordEngine(
            config,
            debug_mode=debug_mode,
            debug_score_floor=debug_score_floor,
            debug_log_interval_ms=debug_log_interval_ms,
        )
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
        if self._debug_mode:
            logging.debug(
                "Debug mode enabled (threshold=%.3f cooldown_ms=%d chunk_samples=%d sample_rate=%d mic_device=%s).",
                self.config.threshold,
                self.config.cooldown_ms,
                self.config.chunk_samples,
                self.config.sample_rate,
                self.config.mic_device,
            )
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
        if self._debug_mode:
            logging.debug("Sent ready message to client.")
        self._heartbeat_deadline = time.monotonic() + HEARTBEAT_INTERVAL_SECONDS

    def _flush_detection_events(self) -> None:
        while True:
            try:
                event = self._detection_queue.get_nowait()
            except queue.Empty:
                return

            if self._client_socket is None:
                if self._debug_mode:
                    logging.debug(
                        "Dropping detection (reason=no_client keyword=%s score=%.3f).",
                        event.keyword,
                        event.score,
                    )
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
        if self._debug_mode:
            logging.debug("Sent heartbeat message to client.")
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
        if self._debug_mode:
            message_type = str(message.get("type", "unknown"))
            if sent:
                logging.debug("Protocol send ok (type=%s).", message_type)
            else:
                logging.debug("Protocol send failed (type=%s); closing client.", message_type)
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
    parser.add_argument(
        "--debug-mode",
        action="store_true",
        help="Enable verbose wakeword diagnostics (score snapshots and suppression reasons).",
    )
    parser.add_argument(
        "--debug-score-floor",
        type=float,
        default=DEFAULT_DEBUG_SCORE_FLOOR,
        help=f"Minimum score to include in periodic debug score snapshots (default: {DEFAULT_DEBUG_SCORE_FLOOR}).",
    )
    parser.add_argument(
        "--debug-log-interval-ms",
        type=int,
        default=DEFAULT_DEBUG_LOG_INTERVAL_MS,
        help=f"Interval for periodic debug score snapshots (default: {DEFAULT_DEBUG_LOG_INTERVAL_MS}ms).",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.debug_mode:
        level = logging.DEBUG
    else:
        level_name = str(args.log_level).upper()
        level = getattr(logging, level_name, logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    if args.debug_score_floor < 0.0 or args.debug_score_floor > 1.0:
        print(
            "Configuration error: --debug-score-floor must be between 0.0 and 1.0.",
            file=sys.stderr,
        )
        return EXIT_CONFIG_ERROR
    if args.debug_log_interval_ms <= 0:
        print(
            "Configuration error: --debug-log-interval-ms must be a positive integer.",
            file=sys.stderr,
        )
        return EXIT_CONFIG_ERROR

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

    daemon = WakewordDaemon(
        config,
        debug_mode=args.debug_mode,
        debug_score_floor=args.debug_score_floor,
        debug_log_interval_ms=args.debug_log_interval_ms,
    )
    return daemon.run()


def _format_top_scores(scores: dict[str, float], *, limit: int = 3) -> str:
    top = sorted(scores.items(), key=lambda item: item[1], reverse=True)[:limit]
    if not top:
        return "-"
    return ", ".join(f"{keyword}:{score:.3f}" for keyword, score in top)


def _iter_feature_model_dirs(primary_dir: Path) -> list[Path]:
    # Prefer colocated feature models, then sibling openwakeword feature directory.
    candidates = [
        primary_dir,
        primary_dir / "openwakeword",
        primary_dir.parent / "openwakeword",
    ]
    unique: list[Path] = []
    seen: set[str] = set()
    for path in candidates:
        key = str(path.resolve() if path.exists() else path)
        if key in seen:
            continue
        seen.add(key)
        unique.append(path)
    return unique


if __name__ == "__main__":
    raise SystemExit(main())
