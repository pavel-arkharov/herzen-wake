from __future__ import annotations

import json
from datetime import datetime

from herzen_wake.protocol import (
    encode_message,
    error_message,
    heartbeat_message,
    ready_message,
    wakeword_message,
)


def _decode(payload: bytes) -> dict[str, object]:
    assert payload.endswith(b"\n")
    return json.loads(payload.decode("utf-8").strip())


def _assert_iso8601_z(timestamp: str) -> None:
    assert timestamp.endswith("Z")
    datetime.fromisoformat(timestamp.replace("Z", "+00:00"))


def test_ready_message_is_serialized_as_jsonl() -> None:
    message = ready_message(version="0.1.0", models=["herzen_v1"])
    parsed = _decode(encode_message(message))

    assert parsed["type"] == "ready"
    assert parsed["version"] == "0.1.0"
    assert parsed["models"] == ["herzen_v1"]
    _assert_iso8601_z(str(parsed["timestamp"]))


def test_wakeword_message_includes_required_fields() -> None:
    message = wakeword_message(
        keyword="herzen",
        score=0.82,
        threshold=0.5,
        model="herzen_v1",
    )
    parsed = _decode(encode_message(message))

    assert parsed["type"] == "wakeword"
    assert parsed["keyword"] == "herzen"
    assert parsed["score"] == 0.82
    assert parsed["threshold"] == 0.5
    assert parsed["model"] == "herzen_v1"
    _assert_iso8601_z(str(parsed["timestamp"]))


def test_wakeword_message_omits_model_when_unset() -> None:
    message = wakeword_message(
        keyword="herzen",
        score=0.75,
        threshold=0.5,
        model=None,
    )
    parsed = _decode(encode_message(message))
    assert "model" not in parsed


def test_heartbeat_and_error_shapes() -> None:
    heartbeat = _decode(encode_message(heartbeat_message()))
    err = _decode(encode_message(error_message(code="MIC_FAILURE", message="Device disconnected")))

    assert heartbeat["type"] == "heartbeat"
    assert err["type"] == "error"
    assert err["code"] == "MIC_FAILURE"
    assert err["message"] == "Device disconnected"
