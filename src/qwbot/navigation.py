"""
:File:        src/qwbot/navigation.py

:Details:     Persist waypoint observations and query same-map routes.

:Date:        30-10-2026
:Author:      Mick K.
"""

import math
import sqlite3
from collections import deque

from .models import Position


class NavigationStore:
    def __init__(self, path):
        self.db = sqlite3.connect(path)
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS nodes (
              id INTEGER PRIMARY KEY, map TEXT NOT NULL, x REAL NOT NULL,
              y REAL NOT NULL, z REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS edges (
              a INTEGER NOT NULL, b INTEGER NOT NULL, successes INTEGER NOT NULL DEFAULT 1,
              PRIMARY KEY(a,b));
            CREATE INDEX IF NOT EXISTS nodes_map ON nodes(map);
        """)
        self.db.commit()

    def nearest(self, map_name, pos, max_distance=96):
        rows = self.db.execute("SELECT id,x,y,z FROM nodes WHERE map=?", (map_name,))
        candidates = (
            (math.dist((x, y, z), (pos.x, pos.y, pos.z)), i) for i, x, y, z in rows
        )
        distance, node = min(candidates, default=(float("inf"), None))
        return node if distance <= max_distance else None

    def observe(self, map_name, pos, previous=None, radius=96):
        """Record a waypoint and connect it to the previous same-map observation."""
        if previous is not None:
            row = self.db.execute(
                "SELECT map FROM nodes WHERE id=?", (previous,)
            ).fetchone()
            if row is None:
                raise ValueError(f"Unknown previous waypoint: {previous}")
            if row[0] != map_name:
                raise ValueError("Previous waypoint belongs to a different map")
        node = self.nearest(map_name, pos, radius)
        if node is None:
            cursor = self.db.execute(
                "INSERT INTO nodes(map,x,y,z) VALUES(?,?,?,?)",
                (map_name, pos.x, pos.y, pos.z),
            )
            node = cursor.lastrowid
        if previous is not None and previous != node:
            self.db.execute(
                "INSERT INTO edges(a,b,successes) VALUES(?,?,1) "
                "ON CONFLICT(a,b) DO UPDATE SET successes=successes+1",
                (previous, node),
            )
        self.db.commit()
        return node

    def route(self, start, goal):
        """Return the fewest-edge same-map route, or an empty list if unreachable."""
        start_row = self.db.execute(
            "SELECT map FROM nodes WHERE id=?", (start,)
        ).fetchone()
        goal_row = self.db.execute(
            "SELECT map FROM nodes WHERE id=?", (goal,)
        ).fetchone()
        if start_row is None or goal_row is None or start_row[0] != goal_row[0]:
            return []
        if start == goal:
            return [start]
        graph = {}
        for a, b in self.db.execute(
            "SELECT edges.a,edges.b FROM edges "
            "JOIN nodes AS source ON source.id=edges.a "
            "JOIN nodes AS target ON target.id=edges.b "
            "WHERE source.map=? AND target.map=?",
            (start_row[0], start_row[0]),
        ):
            graph.setdefault(a, []).append(b)
        queue, previous = deque([start]), {start: None}
        while queue:
            node = queue.popleft()
            if node == goal:
                result = [goal]
                while result[-1] != start:
                    result.append(previous[result[-1]])
                return result[::-1]
            for nxt in graph.get(node, []):
                if nxt not in previous:
                    previous[nxt] = node
                    queue.append(nxt)
        return []

    def counts(self, map_name):
        n = self.db.execute(
            "SELECT count(*) FROM nodes WHERE map=?", (map_name,)
        ).fetchone()[0]
        e = self.db.execute(
            "SELECT count(*) FROM edges WHERE a IN "
            "(SELECT id FROM nodes WHERE map=?)",
            (map_name,),
        ).fetchone()[0]
        return n, e

    def close(self):
        self.db.close()
