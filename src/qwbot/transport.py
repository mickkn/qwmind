"""Linux FIFO ezQuake console command transport. No telemetry is provided by FIFO."""
import os
import stat
import time
from pathlib import Path


class FIFOTransport:
    def __init__(self, path: Path, timeout: float = 5):
        self.path, self.timeout, self.fd = path, timeout, None

    def __enter__(self):
        deadline = time.monotonic() + self.timeout
        while True:
            try:
                if not stat.S_ISFIFO(self.path.stat().st_mode):
                    raise RuntimeError(f"Not a FIFO: {self.path}")
                self.fd = os.open(self.path, os.O_WRONLY | os.O_NONBLOCK)
                return self
            except (FileNotFoundError, OSError) as exc:
                if time.monotonic() >= deadline:
                    raise RuntimeError(f"Cannot open {self.path}: {exc}") from exc
                time.sleep(.1)

    def send(self, command: str):
        if self.fd is None:
            raise RuntimeError("Transport not open")
        if not command or any(c in command for c in '\r\n\x00') or not command.isascii():
            raise ValueError("Invalid console command")
        payload = (command + '\n').encode('ascii')
        if os.write(self.fd, payload) != len(payload):
            raise OSError("Partial FIFO write")

    def __exit__(self, *_):
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None


class MemoryTransport:
    """Deterministic test transport; does not connect to a game."""
    def __init__(self):
        self.commands = []

    def send(self, command):
        self.commands.append(command)
