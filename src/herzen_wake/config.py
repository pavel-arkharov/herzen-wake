from __future__ import annotations

import importlib.util
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Mapping

DEFAULT_THRESHOLD = 0.5
DEFAULT_COOLDOWN_MS = 1500
DEFAULT_CHUNK_SAMPLES = 1280
DEFAULT_SAMPLE_RATE = 16000

FRAME_DURATION_MS = 80

MicDevice = int | str | None


class ConfigError(ValueError):
    """Raised when environment configuration is invalid."""


@dataclass(frozen=True)
class WakewordConfig:
    socket_path: Path
    model_paths: tuple[Path, ...]
    threshold: float
    cooldown_ms: int
    chunk_samples: int
    sample_rate: int
    mic_device: MicDevice
    inference_framework: Literal["onnx", "tflite"]

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "WakewordConfig":
        source = dict(os.environ if env is None else env)

        socket_path = _parse_required_path(source, "HERZEN_WAKEWORD_SOCKET")
        model_paths = _parse_model_paths(source.get("HERZEN_WAKEWORD_MODEL_PATHS", ""))

        threshold = _parse_float_in_range(
            source.get("HERZEN_WAKEWORD_THRESHOLD"),
            default=DEFAULT_THRESHOLD,
            name="HERZEN_WAKEWORD_THRESHOLD",
            minimum=0.0,
            maximum=1.0,
        )
        cooldown_ms = _parse_non_negative_int(
            source.get("HERZEN_WAKEWORD_COOLDOWN_MS"),
            default=DEFAULT_COOLDOWN_MS,
            name="HERZEN_WAKEWORD_COOLDOWN_MS",
        )
        sample_rate = _parse_positive_int(
            source.get("HERZEN_WAKEWORD_SAMPLE_RATE"),
            default=DEFAULT_SAMPLE_RATE,
            name="HERZEN_WAKEWORD_SAMPLE_RATE",
        )
        chunk_samples = _parse_positive_int(
            source.get("HERZEN_WAKEWORD_CHUNK_SAMPLES"),
            default=DEFAULT_CHUNK_SAMPLES,
            name="HERZEN_WAKEWORD_CHUNK_SAMPLES",
        )
        mic_device = _parse_mic_device(source.get("HERZEN_WAKEWORD_MIC_DEVICE"))

        if sample_rate != DEFAULT_SAMPLE_RATE:
            raise ConfigError(
                "HERZEN_WAKEWORD_SAMPLE_RATE must be 16000 for the current openWakeWord MVP."
            )

        frame_samples = _frame_samples(sample_rate)
        if chunk_samples % frame_samples != 0:
            raise ConfigError(
                "HERZEN_WAKEWORD_CHUNK_SAMPLES must be a multiple of "
                f"{frame_samples} ({FRAME_DURATION_MS}ms at {sample_rate}Hz)."
            )

        inference_framework = _resolve_inference_framework(model_paths)

        return cls(
            socket_path=socket_path,
            model_paths=model_paths,
            threshold=threshold,
            cooldown_ms=cooldown_ms,
            chunk_samples=chunk_samples,
            sample_rate=sample_rate,
            mic_device=mic_device,
            inference_framework=inference_framework,
        )


def has_tflite_runtime() -> bool:
    return importlib.util.find_spec("tflite_runtime") is not None


def _parse_required_path(env: Mapping[str, str], key: str) -> Path:
    raw = env.get(key)
    if raw is None:
        raise ConfigError(f"{key} is required.")

    text = raw.strip()
    if not text:
        raise ConfigError(f"{key} must be a non-empty path.")

    path = Path(text).expanduser()
    return path.resolve() if not path.is_absolute() else path


def _parse_model_paths(raw: str) -> tuple[Path, ...]:
    text = raw.strip()
    if not text:
        raise ConfigError("HERZEN_WAKEWORD_MODEL_PATHS is required.")

    paths: list[Path] = []
    for part in text.split(","):
        entry = part.strip()
        if not entry:
            continue

        path = Path(entry).expanduser()
        resolved = path.resolve() if not path.is_absolute() else path
        if not resolved.exists() or not resolved.is_file():
            raise ConfigError(
                "HERZEN_WAKEWORD_MODEL_PATHS includes a missing model file: "
                f"{resolved}"
            )
        if resolved.suffix.lower() not in {".onnx", ".tflite"}:
            raise ConfigError(
                "HERZEN_WAKEWORD_MODEL_PATHS supports only .onnx or .tflite files: "
                f"{resolved}"
            )
        paths.append(resolved)

    if not paths:
        raise ConfigError(
            "HERZEN_WAKEWORD_MODEL_PATHS must include at least one .onnx/.tflite path."
        )
    return tuple(paths)


def _resolve_inference_framework(
    model_paths: tuple[Path, ...]
) -> Literal["onnx", "tflite"]:
    suffixes = {path.suffix.lower() for path in model_paths}
    if len(suffixes) != 1:
        raise ConfigError(
            "HERZEN_WAKEWORD_MODEL_PATHS must use one framework at a time "
            "(all .onnx or all .tflite)."
        )

    suffix = next(iter(suffixes))
    if suffix == ".onnx":
        return "onnx"

    if not has_tflite_runtime():
        raise ConfigError(
            "tflite models require tflite-runtime, which is not available. "
            "Use .onnx models on macOS."
        )
    return "tflite"


def _parse_float_in_range(
    raw: str | None,
    *,
    default: float,
    name: str,
    minimum: float,
    maximum: float,
) -> float:
    if raw is None or not raw.strip():
        return default

    text = raw.strip()
    try:
        value = float(text)
    except ValueError as exc:
        raise ConfigError(f'{name} must be a number; received "{raw}".') from exc

    if value < minimum or value > maximum:
        raise ConfigError(
            f"{name} must be between {minimum} and {maximum}; received {value}."
        )
    return value


def _parse_positive_int(raw: str | None, *, default: int, name: str) -> int:
    if raw is None or not raw.strip():
        return default

    text = raw.strip()
    try:
        value = int(text)
    except ValueError as exc:
        raise ConfigError(
            f'{name} must be a positive integer; received "{raw}".'
        ) from exc
    if value <= 0:
        raise ConfigError(f"{name} must be a positive integer; received {value}.")
    return value


def _parse_non_negative_int(raw: str | None, *, default: int, name: str) -> int:
    if raw is None or not raw.strip():
        return default

    text = raw.strip()
    try:
        value = int(text)
    except ValueError as exc:
        raise ConfigError(
            f'{name} must be a non-negative integer; received "{raw}".'
        ) from exc
    if value < 0:
        raise ConfigError(
            f"{name} must be a non-negative integer; received {value}."
        )
    return value


def _parse_mic_device(raw: str | None) -> MicDevice:
    if raw is None:
        return None

    text = raw.strip()
    if not text:
        return None

    if text.isdigit():
        return int(text)
    return text


def _frame_samples(sample_rate: int) -> int:
    numerator = sample_rate * FRAME_DURATION_MS
    if numerator % 1000 != 0:
        raise ConfigError(
            "HERZEN_WAKEWORD_SAMPLE_RATE must align to whole-sample 80ms frames."
        )
    return numerator // 1000
