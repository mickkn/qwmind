"""
:File:        src/qwbot/telemetry.py

:Details:     Parse and receive local JSON telemetry from a future ezQuake adapter.
              No stock ezQuake telemetry implementation is included.

:Date:        30-10-2026
:Author:      Mick K.
"""

import json
import math
import socket
import time

from .models import Position, Snapshot


def parse_snapshot(raw: bytes) -> Snapshot:
    """Parse and validate one JSON telemetry datagram."""
    if len(raw) > 4096:
        raise ValueError("Telemetry packet too large")
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("Telemetry packet must be a JSON object")
    name = data.get("map")
    pos = data.get("origin")
    if (
        not isinstance(name, str)
        or not name
        or len(name) > 64
        or not all(c.isascii() and (c.isalnum() or c in "_-") for c in name)
    ):
        raise ValueError("Invalid map name")
    if not isinstance(pos, list) or len(pos) != 3:
        raise ValueError("origin must contain three coordinates")
    values = (*pos, data.get("yaw"))
    if any(type(value) not in (int, float) for value in values):
        raise ValueError("Coordinates and yaw must be finite numbers")
    try:
        coordinates = tuple(float(value) for value in values)
    except OverflowError as exc:
        raise ValueError("Coordinates and yaw must be finite numbers") from exc
    if not all(math.isfinite(value) for value in coordinates):
        raise ValueError("Coordinates and yaw must be finite numbers")
    health = data.get("health", 100)
    on_ground = data.get("on_ground", True)
    if type(health) is not int:
        raise ValueError("health must be an integer")
    if type(on_ground) is not bool:
        raise ValueError("on_ground must be a boolean")
    return Snapshot(
        name,
        Position(*coordinates[:3]),
        coordinates[3],
        time.monotonic(),
        health,
        on_ground,
    )


class UDPReceiver:
    def __init__(self, port=27999):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(("127.0.0.1", port))
        self.sock.setblocking(False)

    def latest(self):
        snapshot = None
        while True:
            try:
                data, _ = self.sock.recvfrom(4097)
            except BlockingIOError:
                break
            try:
                snapshot = parse_snapshot(data)
            except (ValueError, KeyError, TypeError, OverflowError):
                continue
        return snapshot

    def close(self):
        self.sock.close()
