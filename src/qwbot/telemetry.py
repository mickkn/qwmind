"""Optional telemetry adapter contract for a FUTURE ezQuake modification.

No stock ezQuake telemetry implementation is claimed or included.
JSON UDP datagrams are local-only and untrusted; do not bind to public networks.
"""
import json
import socket
import time
from .models import Position, Snapshot


def parse_snapshot(raw: bytes) -> Snapshot:
    if len(raw) > 4096:
        raise ValueError("Telemetry packet too large")
    data = json.loads(raw)
    name = data['map']
    pos = data['origin']
    if not isinstance(name, str) or not name or len(name) > 64 or not all(c.isalnum() or c in '_-' for c in name):
        raise ValueError("Invalid map name")
    if not isinstance(pos, list) or len(pos) != 3:
        raise ValueError("origin must contain three coordinates")
    return Snapshot(name, Position(*(float(v) for v in pos)), float(data['yaw']),
                    time.monotonic(), int(data.get('health', 100)), bool(data.get('on_ground', True)))


class UDPReceiver:
    def __init__(self, port=27999):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(('127.0.0.1', port))
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
