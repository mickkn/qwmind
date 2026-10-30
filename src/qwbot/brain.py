"""Simple exploration policy. Telemetry enables stuck detection and waypoint recording."""
import random
from .models import Action


class Explorer:
    def __init__(self, seed=42):
        self.rng = random.Random(seed)
        self.last_position = None
        self.still_ticks = 0
        self.step = 0

    def decide(self, snapshot=None):
        self.step += 1
        if snapshot is not None:
            if self.last_position and snapshot.position.distance(self.last_position) < 6:
                self.still_ticks += 1
            else:
                self.still_ticks = 0
            self.last_position = snapshot.position
        stuck = self.still_ticks >= 4
        if stuck:
            self.still_ticks = 0
        turn = self.rng.choice((-110, -65, 65, 110)) if stuck else (
            self.rng.choice((-30, 30)) if self.step % 8 == 0 else 0)
        return Action(forward=True, left=self.step % 13 in (0, 1),
                      right=self.step % 17 in (0, 1),
                      jump=stuck or self.step % 9 == 0, turn=turn)
