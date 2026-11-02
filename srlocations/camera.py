"""A camera that moves as one held or carried does: it follows late, lets small moves go, looks ahead, and shakes.

Each is a function of time alone, so a frame of a film is still the still of `location.at(time)`. A follow that lags has a
past, so it is worked out from the start in fixed steps up to the time asked for, always the same steps for the same time.
A shake is a sum of a few slow waves with phases drawn from its seed: the same seed gives the same shake on every render.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, replace
from typing import Any, Callable, Optional, Sequence, Union

from srlocations.geometry import Vec3, aim

STEP = 1 / 120  # seconds between the steps of a follow that lags
OCTAVES = ((1.0, 1.0), (2.17, 0.5), (4.61, 0.25))  # a shake's waves, as multiples of its frequency, and their weights
RAMP = 0.25  # seconds a handheld shake takes to come in and to go


@dataclass(frozen=True)
class Follow:
    """A shot kept on a node or a mark, at `offset` from it. `lag` is how many seconds the camera takes to make up about
    two thirds of a move, `dead` how many metres the target may stray from where the camera looks before it turns, and
    `ahead` how many seconds along the target's path it looks."""
    what: Union[Any, str]
    offset: Vec3 = Vec3()
    lag: float = 0.0
    dead: float = 0.0
    ahead: float = 0.0

    def __post_init__(self) -> None:
        if min(self.lag, self.dead, self.ahead) < 0:
            raise ValueError(f"a follow's lag, dead zone and look-ahead are 0 or more, not {self.lag}, {self.dead}, {self.ahead}")

    @property
    def exact(self) -> bool:
        return not (self.lag or self.dead or self.ahead)


def steady(path: Callable[[float], Vec3], time: float, lag: float = 0.0, dead: float = 0.0, ahead: float = 0.0,
           step: float = STEP) -> Vec3:
    """Where a camera following `path`, a position at each time, looks at `time`. It starts on the path at the start."""
    looking = path(ahead)
    if not (lag or dead):
        return path(time + ahead)
    steps = int(time / step)
    for count in range(1, steps + 1):
        looking = _toward(looking, path(count * step + ahead), step, lag, dead)
    if time > steps * step:
        looking = _toward(looking, path(time + ahead), time - steps * step, lag, dead)
    return looking


def _toward(looking: Vec3, target: Vec3, seconds: float, lag: float, dead: float) -> Vec3:
    """One step of a follow: the part of the way past the dead zone, made up as a lag allows in that time."""
    way = target - looking
    if way.length <= dead:
        return looking
    share = (way.length - dead) / way.length * (1 - math.exp(-seconds / lag) if lag else 1.0)
    return looking + Vec3(way.x * share, way.y * share, way.z * share)


@dataclass(frozen=True)
class Shake:
    """A camera shaken from `start` to `end`. `amount` is about the most, in degrees, the view turns, and `drift` the most,
    in metres, the camera wanders. `frequency` is the slowest wave, in Hz. Without `decay` it is a hand holding the camera,
    coming in and going over a quarter of a second; with it, a blow, at full strength at `start` and falling to a third
    every `decay` seconds."""
    amount: float = 0.5
    frequency: float = 1.0
    start: float = 0.0
    end: Optional[float] = None
    decay: Optional[float] = None
    drift: float = 0.0
    seed: int = 0

    def __post_init__(self) -> None:
        if self.frequency <= 0 or (self.decay is not None and self.decay <= 0):
            raise ValueError(f"a shake's frequency and decay are above 0, not {self.frequency} and {self.decay}")
        if self.end is not None and self.end <= self.start:
            raise ValueError(f"a shake ends after it starts, and {self.end} is not after {self.start}")

    @property
    def last(self) -> Optional[float]:
        """When it is over: its end, or when a blow has fallen below a hundredth."""
        if self.end is not None:
            return self.end
        return None if self.decay is None else self.start + self.decay * math.log(100)

    def strength(self, time: float) -> float:
        if time < self.start or (self.last is not None and time > self.last):
            return 0.0
        if self.decay is not None:
            return math.exp(-(time - self.start) / self.decay)
        edges = [(time - self.start) / RAMP] + ([] if self.end is None else [(self.end - time) / RAMP])
        return min(1.0, *edges)

    def offsets(self, time: float) -> tuple[float, float, Vec3]:
        """How far the view turns, in yaw and pitch, and how far the camera moves, at `time`."""
        strength = self.strength(time)
        if not strength:
            return 0.0, 0.0, Vec3()
        rng = random.Random(self.seed)
        phases = [[rng.uniform(0, 2 * math.pi) for _ in OCTAVES] for _ in range(5)]
        total = sum(weight for _, weight in OCTAVES)
        waves = [sum(weight * math.sin(2 * math.pi * self.frequency * multiple * time + phase)
                     for (multiple, weight), phase in zip(OCTAVES, channel)) / total * strength for channel in phases]
        yaw, pitch, *moved = waves
        return yaw * self.amount, pitch * self.amount, Vec3(*(part * self.drift for part in moved))


def shaken(shot: Any, shakes: Sequence[Shake], time: float) -> Any:
    """A shot with its shakes at `time`: the camera moved, and the view turned about it."""
    for shake in shakes:
        yaw, pitch, moved = shake.offsets(time)
        if not (yaw or pitch or moved.length):
            continue
        (turn, lift), distance = aim(shot.eye, shot.look_at), (shot.look_at - shot.eye).length
        turn, lift = math.radians(turn + yaw), math.radians(max(-89.9, min(89.9, lift + pitch)))
        eye = shot.eye + moved
        way = Vec3(math.sin(turn) * math.cos(lift), math.sin(lift), math.cos(turn) * math.cos(lift))
        shot = replace(shot, eye=eye, look_at=eye + Vec3(way.x * distance, way.y * distance, way.z * distance))
    return shot
