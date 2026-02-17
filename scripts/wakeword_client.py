#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import socket
import sys
from pathlib import Path


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Simple Terminal B client that prints wakeword daemon JSONL events."
    )
    parser.add_argument(
        "--socket",
        default=default_socket_path(),
        help="Unix socket path (default: HERZEN_WAKEWORD_SOCKET or ./run/wakeword.sock).",
    )
    return parser.parse_args(argv)


def default_socket_path() -> str:
    configured = os.environ.get("HERZEN_WAKEWORD_SOCKET", "").strip()
    if configured:
        return configured

    repo_root = Path(__file__).resolve().parent.parent
    return str(repo_root / "run" / "wakeword.sock")


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    socket_path = Path(args.socket).expanduser()
    if not socket_path.is_absolute():
        socket_path = socket_path.resolve()

    client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        client.connect(str(socket_path))
    except OSError as exc:
        print(f"Failed to connect to socket {socket_path}: {exc}", file=sys.stderr)
        return 1

    print(f"Connected to {socket_path}")

    buffer = b""
    try:
        while True:
            chunk = client.recv(4096)
            if not chunk:
                print("Socket closed by daemon.")
                return 0

            buffer += chunk
            while b"\n" in buffer:
                line, buffer = buffer.split(b"\n", 1)
                text = line.decode("utf-8", errors="replace").strip()
                if text:
                    print(text)
    except KeyboardInterrupt:
        print("\nClient stopped.")
        return 0
    finally:
        client.close()


if __name__ == "__main__":
    raise SystemExit(main())
