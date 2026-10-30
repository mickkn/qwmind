"""
:File:        src/qwbot/cli.py

:Details:     Command-line parsing and orchestration for the QWBot controller.

:Date:        30-10-2026
:Author:      Mick K.
"""

import argparse
import getpass
import logging
import re
import subprocess
import time
from pathlib import Path

from .brain import Explorer
from .controller import Controller
from .models import Action
from .navigation import NavigationStore
from .telemetry import UDPReceiver
from .transport import FIFOTransport

LOG = logging.getLogger("qwbot")


def run(args):
    process = None
    if args.launch:
        process = subprocess.Popen([str(args.launch), *args.client_arg])
        LOG.info("Started ezQuake process %s", process.pid)
    receiver = UDPReceiver(args.telemetry_port) if args.telemetry else None
    store = NavigationStore(args.database) if args.telemetry else None
    try:
        with FIFOTransport(args.pipe, args.timeout) as transport:
            controller = Controller(transport)
            try:
                controller.stop()
                controller.command("name " + args.name)
                if args.server:
                    controller.command("connect " + args.server)
                    time.sleep(args.connect_wait)
                explorer = Explorer(args.seed)
                last_node = None
                last_map = None
                end = time.monotonic() + args.duration
                while time.monotonic() < end:
                    snapshot = receiver.latest() if receiver else None
                    if snapshot:
                        if snapshot.map_name != last_map:
                            last_node = None
                            last_map = snapshot.map_name
                        last_node = store.observe(
                            snapshot.map_name, snapshot.position, last_node
                        )
                        LOG.info(
                            "%s pos=%s graph=%s",
                            snapshot.map_name,
                            snapshot.position,
                            store.counts(snapshot.map_name),
                        )
                    action = (
                        explorer.decide(snapshot)
                        if args.mode == "explore"
                        else Action(forward=True)
                    )
                    controller.apply(action)
                    time.sleep(min(args.tick, max(0, end - time.monotonic())))
            finally:
                controller.stop()
    finally:
        if receiver:
            receiver.close()
        if store:
            store.close()
        # Do not terminate a manually launched or optionally spawned game by default.
        if process:
            LOG.info("Client process left running: pid=%s", process.pid)


def main(argv=None):
    parser = argparse.ArgumentParser(description="External ezQuake bot controller v0.2")
    parser.add_argument(
        "--pipe", type=Path, default=Path("/tmp/ezquake_" + getpass.getuser())
    )
    parser.add_argument("--server", help="Host:port of your own/permitted server")
    parser.add_argument("--name", default="PythonBot01")
    parser.add_argument("--mode", choices=("test", "explore"), default="explore")
    parser.add_argument("--duration", type=float, default=60)
    parser.add_argument("--tick", type=float, default=0.25)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--timeout", type=float, default=8)
    parser.add_argument("--connect-wait", type=float, default=5)
    parser.add_argument(
        "--telemetry",
        action="store_true",
        help="Expect custom UDP JSON telemetry adapter",
    )
    parser.add_argument("--telemetry-port", type=int, default=27999)
    parser.add_argument("--database", type=Path, default=Path("navigation.sqlite3"))
    parser.add_argument("--launch", type=Path, help="Optional ezQuake executable path")
    parser.add_argument(
        "--client-arg", action="append", default=[], help="Client argument (repeatable)"
    )
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)
    if not re.fullmatch(r"[A-Za-z0-9_]{1,24}", args.name):
        parser.error("name must contain 1-24 ASCII letters, digits or underscores")
    if args.server and not re.fullmatch(r"[A-Za-z0-9.\-:\[\]]{1,255}", args.server):
        parser.error("invalid server address")
    if not (
        0 < args.duration <= 86400
        and 0.05 <= args.tick <= 10
        and 0 <= args.connect_wait <= 120
        and 0.05 <= args.timeout <= 120
        and 1 <= args.telemetry_port <= 65535
    ):
        parser.error(
            "invalid duration, tick, timeout, telemetry port or connection wait"
        )
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    try:
        run(args)
    except (RuntimeError, OSError, KeyboardInterrupt) as exc:
        parser.exit(1, f"Bot stopped: {exc}\n")


if __name__ == "__main__":
    main()
