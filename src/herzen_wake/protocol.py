from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Mapping, Sequence

JSONValue = object
JSONMessage = dict[str, JSONValue]


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace(
        "+00:00", "Z"
    )


def ready_message(
    *,
    version: str,
    models: Sequence[str],
    timestamp: str | None = None,
) -> JSONMessage:
    return {
        "type": "ready",
        "timestamp": timestamp or utc_now_iso(),
        "version": version,
        "models": list(models),
    }


def wakeword_message(
    *,
    keyword: str,
    score: float,
    threshold: float,
    model: str | None = None,
    timestamp: str | None = None,
) -> JSONMessage:
    message: JSONMessage = {
        "type": "wakeword",
        "timestamp": timestamp or utc_now_iso(),
        "keyword": keyword,
        "score": score,
        "threshold": threshold,
    }
    if model is not None:
        message["model"] = model
    return message


def heartbeat_message(*, timestamp: str | None = None) -> JSONMessage:
    return {
        "type": "heartbeat",
        "timestamp": timestamp or utc_now_iso(),
    }


def error_message(*, code: str, message: str, timestamp: str | None = None) -> JSONMessage:
    return {
        "type": "error",
        "timestamp": timestamp or utc_now_iso(),
        "code": code,
        "message": message,
    }


def encode_message(message: Mapping[str, JSONValue]) -> bytes:
    payload = json.dumps(message, separators=(",", ":"), ensure_ascii=True)
    return payload.encode("utf-8") + b"\n"
