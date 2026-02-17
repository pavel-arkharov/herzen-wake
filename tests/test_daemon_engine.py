from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import numpy as np

from herzen_wake.daemon import WakewordEngine, _iter_feature_model_dirs


class _FakeModel:
    def __init__(self, scores: dict[str, object]):
        self._scores = scores

    def predict(self, _chunk: np.ndarray) -> dict[str, object]:
        return self._scores


def test_engine_accepts_numpy_scalar_scores() -> None:
    config = SimpleNamespace(
        threshold=0.5,
        cooldown_ms=0,
        inference_framework="onnx",
        model_paths=(Path("dummy.onnx"),),
    )
    engine = WakewordEngine(config)  # type: ignore[arg-type]
    engine._model = _FakeModel({"hey_jarvis_v0.1": np.float32(0.91)})  # noqa: SLF001

    event = engine.predict(np.zeros(1280, dtype=np.int16))
    assert event is not None
    assert event.keyword == "hey_jarvis_v0.1"
    assert event.score > 0.9


def test_feature_model_dir_candidates_include_repo_openwakeword() -> None:
    candidates = _iter_feature_model_dirs(Path("/tmp/project/models"))

    assert Path("/tmp/project/models") in candidates
    assert Path("/tmp/project/models/openwakeword") in candidates
    assert Path("/tmp/project/openwakeword") in candidates
