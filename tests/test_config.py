from __future__ import annotations

from pathlib import Path

import pytest

from herzen_wake.config import ConfigError, WakewordConfig


def _base_env(tmp_path: Path, *, extension: str = ".onnx") -> dict[str, str]:
    model_path = tmp_path / f"model{extension}"
    model_path.write_bytes(b"model")
    return {
        "HERZEN_WAKEWORD_SOCKET": str(tmp_path / "wakeword.sock"),
        "HERZEN_WAKEWORD_MODEL_PATHS": str(model_path),
    }


def test_parses_valid_env(tmp_path: Path) -> None:
    env = _base_env(tmp_path)
    cfg = WakewordConfig.from_env(env)

    assert cfg.socket_path.name == "wakeword.sock"
    assert len(cfg.model_paths) == 1
    assert cfg.model_paths[0].suffix == ".onnx"
    assert cfg.inference_framework == "onnx"
    assert cfg.threshold == 0.5
    assert cfg.cooldown_ms == 1500
    assert cfg.chunk_samples == 1280
    assert cfg.sample_rate == 16000


def test_requires_socket_path(tmp_path: Path) -> None:
    env = _base_env(tmp_path)
    env.pop("HERZEN_WAKEWORD_SOCKET")

    with pytest.raises(ConfigError, match="HERZEN_WAKEWORD_SOCKET is required"):
        WakewordConfig.from_env(env)


def test_requires_existing_model_file(tmp_path: Path) -> None:
    env = {
        "HERZEN_WAKEWORD_SOCKET": str(tmp_path / "wakeword.sock"),
        "HERZEN_WAKEWORD_MODEL_PATHS": str(tmp_path / "missing.onnx"),
    }

    with pytest.raises(ConfigError, match="missing model file"):
        WakewordConfig.from_env(env)


def test_rejects_invalid_threshold(tmp_path: Path) -> None:
    env = _base_env(tmp_path)
    env["HERZEN_WAKEWORD_THRESHOLD"] = "1.5"

    with pytest.raises(ConfigError, match="HERZEN_WAKEWORD_THRESHOLD"):
        WakewordConfig.from_env(env)


def test_rejects_non_80ms_chunk_alignment(tmp_path: Path) -> None:
    env = _base_env(tmp_path)
    env["HERZEN_WAKEWORD_CHUNK_SAMPLES"] = "1000"

    with pytest.raises(ConfigError, match="HERZEN_WAKEWORD_CHUNK_SAMPLES"):
        WakewordConfig.from_env(env)


def test_rejects_non_16k_sample_rate(tmp_path: Path) -> None:
    env = _base_env(tmp_path)
    env["HERZEN_WAKEWORD_SAMPLE_RATE"] = "44100"

    with pytest.raises(ConfigError, match="must be 16000"):
        WakewordConfig.from_env(env)


def test_rejects_tflite_when_runtime_is_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    env = _base_env(tmp_path, extension=".tflite")
    monkeypatch.setattr("herzen_wake.config.has_tflite_runtime", lambda: False)

    with pytest.raises(ConfigError, match="tflite-runtime"):
        WakewordConfig.from_env(env)


def test_parses_mic_device_by_index(tmp_path: Path) -> None:
    env = _base_env(tmp_path)
    env["HERZEN_WAKEWORD_MIC_DEVICE"] = "2"

    cfg = WakewordConfig.from_env(env)
    assert cfg.mic_device == 2


def test_parses_mic_device_by_name(tmp_path: Path) -> None:
    env = _base_env(tmp_path)
    env["HERZEN_WAKEWORD_MIC_DEVICE"] = "MacBook Pro Microphone"

    cfg = WakewordConfig.from_env(env)
    assert cfg.mic_device == "MacBook Pro Microphone"
