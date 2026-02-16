from __future__ import annotations

import logging
from typing import Any

import numpy as np
import sounddevice as sd

from .config import MicDevice


class AudioError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


class SoundDeviceAudioSource:
    def __init__(
        self,
        *,
        sample_rate: int,
        chunk_samples: int,
        mic_device: MicDevice = None,
    ):
        self.sample_rate = sample_rate
        self.chunk_samples = chunk_samples
        self.mic_device = mic_device
        self._stream: Any | None = None

    def start(self) -> None:
        if self._stream is not None:
            return
        try:
            stream = sd.RawInputStream(
                samplerate=self.sample_rate,
                channels=1,
                dtype="int16",
                blocksize=self.chunk_samples,
                device=self.mic_device,
            )
            stream.start()
        except Exception as exc:
            raise AudioError("MIC_INIT_FAILED", f"Failed to start microphone input: {exc}") from exc
        self._stream = stream

    def read_chunk(self) -> np.ndarray:
        if self._stream is None:
            raise AudioError("MIC_READ_FAILED", "Microphone stream is not started.")

        try:
            data, overflowed = self._stream.read(self.chunk_samples)
        except Exception as exc:
            raise AudioError("MIC_READ_FAILED", f"Microphone read failed: {exc}") from exc

        if overflowed:
            logging.warning("Microphone overflow detected while reading chunk.")

        chunk = np.frombuffer(data, dtype=np.int16)
        if chunk.size != self.chunk_samples:
            raise AudioError(
                "MIC_READ_FAILED",
                f"Expected {self.chunk_samples} samples, received {chunk.size}.",
            )
        return chunk.copy()

    def stop(self) -> None:
        stream = self._stream
        self._stream = None
        if stream is None:
            return

        try:
            stream.stop()
        except Exception:
            pass
        try:
            stream.close()
        except Exception:
            pass
