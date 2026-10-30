"""
:File:        tests/test_core.py

:Details:     Unit tests for controller, telemetry, navigation, and exploration.

:Date:        30-10-2026
:Author:      Mick K.
"""

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from qwbot.brain import Explorer
from qwbot.controller import Controller
from qwbot.models import Action, Position, Snapshot
from qwbot.navigation import NavigationStore
from qwbot.telemetry import parse_snapshot
from qwbot.transport import MemoryTransport


class ControllerTests(unittest.TestCase):
    def test_key_transitions_and_cleanup(self):
        transport = MemoryTransport()
        c = Controller(transport)
        c.apply(Action(forward=True, jump=True))
        c.apply(Action(forward=True))
        c.stop()
        self.assertEqual(transport.commands[:3], ["+forward", "+jump", "-jump"])
        self.assertIn("-forward", transport.commands)

    def test_invalid_packet(self):
        with self.assertRaises(ValueError):
            parse_snapshot(b'{"map":"../evil","origin":[1,2,3],"yaw":0}')

    def test_invalid_telemetry_values(self):
        for payload in (
            {"map": "test", "origin": [1, float("nan"), 3], "yaw": 0},
            {"map": "test", "origin": [1, 2, 3], "yaw": 0, "on_ground": "false"},
            ["not", "an", "object"],
        ):
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                parse_snapshot(json.dumps(payload).encode())

    def test_telemetry(self):
        s = parse_snapshot(
            json.dumps({"map": "2fort5", "origin": [1, 2, 3], "yaw": 90}).encode()
        )
        self.assertEqual(s.position, Position(1, 2, 3))

    def test_navigation(self):
        with tempfile.TemporaryDirectory() as folder:
            db = NavigationStore(Path(folder) / "test.sqlite3")
            a = db.observe("2fort5", Position(0, 0, 0), radius=10)
            b = db.observe("2fort5", Position(100, 0, 0), a, radius=10)
            c = db.observe("2fort5", Position(200, 0, 0), b, radius=10)
            self.assertEqual(db.route(a, c), [a, b, c])
            self.assertEqual(db.counts("2fort5"), (3, 2))
            self.assertEqual(db.nearest("other", Position(0, 0, 0)), None)
            other_map_node = db.observe("other", Position(0, 0, 0), radius=10)
            self.assertEqual(db.route(a, other_map_node), [])
            with self.assertRaises(ValueError):
                db.observe("other", Position(100, 0, 0), previous=a, radius=10)
            db.close()

    def test_explorer(self):
        e = Explorer(1)
        s = Snapshot("2fort5", Position(0, 0, 0), 0, 0)
        actions = [e.decide(s) for _ in range(6)]
        self.assertTrue(all(a.forward for a in actions))
        self.assertTrue(any(a.turn != 0 for a in actions))


if __name__ == "__main__":
    unittest.main()
