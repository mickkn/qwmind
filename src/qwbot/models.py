from dataclasses import dataclass
from math import dist


@dataclass(frozen=True)
class Position:
    x: float
    y: float
    z: float

    def distance(self, other: "Position") -> float:
        return dist((self.x, self.y, self.z), (other.x, other.y, other.z))


@dataclass(frozen=True)
class Snapshot:
    map_name: str
    position: Position
    yaw: float
    timestamp: float
    health: int = 100
    on_ground: bool = True


@dataclass(frozen=True)
class Action:
    forward: bool = False
    left: bool = False
    right: bool = False
    jump: bool = False
    turn: float = 0.0
