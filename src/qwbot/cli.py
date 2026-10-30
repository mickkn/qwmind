"""
:File:        src/qwbot/cli.py

:Details:     Command-line parsing and orchestration for the QWBot controller.

:Date:        30-10-2026
:Author:      Mick K.
"""

import argparse
import getpass
import logging
import os
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
    windows_input = args.transport == "windows" or (
        args.transport == "auto" and os.name == "nt"
    )
    if windows_input and args.server and not args.launch:
        raise RuntimeError("On Windows, use --launch with --server, or join the server manually")
    process = None
    if args.launch:
        executable = args.launch.resolve(strict=True)
        client_args = list(args.client_arg)
        if windows_input:
            client_args.extend(["+name", args.name])
            if args.server:
                client_args.extend(["+connect", args.server])
        if args.map:
            client_args.extend(["+map", args.map])
        process = subprocess.Popen(
            [str(executable), *client_args], cwd=executable.parent
        )
        LOG.info("Started ezQuake process %s", process.pid)
    receiver = store = None
    try:
        receiver = UDPReceiver(args.telemetry_port) if args.telemetry else None
        store = NavigationStore(args.database) if args.telemetry else None
        if windows_input:
            from .windows import WindowsTransport

            LOG.warning(
                "Focus ezQuake with console/menu closed within %.1fs. "
                "W/A/D/Space must be bound to movement/jump. "
                "F12 or switching windows stops the bot.",
                args.timeout,
            )
            adapter = WindowsTransport(
                args.timeout, process.pid if process else None,
                args.mouse_counts_per_degree,
            )
        else:
            adapter = FIFOTransport(args.pipe, args.timeout)
        with adapter as transport:
            controller = Controller(transport)
            try:
                controller.stop()
                if not windows_input:
                    controller.command("name " + args.name)
                elif not process:
                    LOG.info("Using the running client's name and current server")
                if args.server and not windows_input:
                    controller.command("connect " + args.server)
                if args.server or args.map:
                    time.sleep(args.connect_wait)
                explorer = Explorer(args.seed)
                last_node = None
                last_map = None
                end = time.monotonic() + args.duration
                while time.monotonic() < end:
                    if windows_input:
                        transport.check()
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
                    wake = min(end, time.monotonic() + args.tick)
                    while time.monotonic() < wake:
                        if windows_input:
                            transport.check()
                        time.sleep(min(0.05, max(0, wake - time.monotonic())))
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
    destination = parser.add_mutually_exclusive_group()
    destination.add_argument("--server", help="Host:port of your own/permitted server")
    destination.add_argument("--map", help="Local map to load at client launch (e.g. dm6)")
    parser.add_argument("--name", default="PythonBot01")
    parser.add_argument("--mode", choices=("test", "explore"), default="explore")
    parser.add_argument("--duration", type=float, default=60)
    parser.add_argument("--tick", type=float, default=0.25)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--timeout", type=float, default=8)
    parser.add_argument(
        "--transport", choices=("auto", "fifo", "windows"), default="auto",
        help="auto selects focused keyboard/mouse input on Windows, FIFO otherwise",
    )
    parser.add_argument(
        "--mouse-counts-per-degree", type=float, default=15.15,
        help="Windows turn calibration (default approximates sensitivity 3, m_yaw 0.022)",
    )
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
    if args.map is not None:
        if not args.launch:
            parser.error("--map requires --launch")
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", args.map):
            parser.error("map must contain 1-64 ASCII letters, digits, underscores or hyphens")
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
        and 0 < args.mouse_counts_per_degree <= 1000
    ):
        parser.error(
            "invalid duration, tick, timeout, telemetry port, connection wait "
            "or mouse counts per degree"
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
