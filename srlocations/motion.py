"""Things that change over time. `location.move()` keys a shot, a mark or a node, and `location.at(time)` gives that moment as
a still location, so the rule for all of this is short: a frame of a moving shot is a still of that moment.

The engine interpolates by property and the SDK by meaning: it aims a camera from its eye and target, and it turns a joint in
a parent's frame, so a frame between two loose keys would not be the same picture. So a `Clip` writes one key to a frame, with
linear interpolation, at the exact time of that frame. A key time rounded to six places lands the engine a hair off the key,
and that is enough to flip ink pixels.

Solids, lights and the camera carry keys, so every pass of a look follows them without knowing. Paint and the wireframe are
2D, positioned from a projection, so a frame's marks go in a group that lives for that frame, and they are drawn by the same
code as a still's. A PaintItem from a plugin moves with no change.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Optional, Sequence

from srlocations.geometry import Transform, Vec3
from srlocations.nodes import Light, Placed, Solid

SMOOTH = "smooth"
EASES: dict[str, Callable[[float], float]] = {
    "linear": lambda u: u,
    "ease-in": lambda u: u * u,
    "ease-out": lambda u: u * (2 - u),
    "ease-in-out": lambda u: u * u * (3 - 2 * u),
    "hold": lambda u: 1.0 if u >= 1 else 0.0,
    SMOOTH: lambda u: u,  # passes through its keys without stopping; see `through`
}


class MotionError(ValueError):
    """A move that cannot be made."""


def blend(a: Any, b: Any, u: float) -> Any:
    """Between two values of a key. A pose is a mapping of controls, each from zero if one side lacks it, and anything else
    that is not a number changes when it arrives."""
    if isinstance(a, bool) or not isinstance(a, (int, float, Vec3, Mapping)):
        return b if u >= 1 else a
    if isinstance(a, Vec3):
        return Vec3(*(blend(p, q, u) for p, q in zip(a, b)))
    if isinstance(a, Mapping):
        return {key: blend(a.get(key, 0.0), b.get(key, 0.0), u) for key in sorted({*a, *b})}
    return a + (b - a) * u


def _hermite(a: float, b: float, out: float, into: float, u: float) -> float:
    return (a * (1 + 2 * u) * (1 - u) ** 2 + out * u * (1 - u) ** 2 + b * u * u * (3 - 2 * u) + into * u * u * (u - 1))


@dataclass(frozen=True)
class Key:
    """A value something reaches at a time, and how it gets there from the key before."""
    time: float
    value: Any
    ease: str = "ease-in-out"


@dataclass
class Track:
    """One thing's keys, by field. Fields keep their own times, and each holds its last value."""
    fields: dict[str, list[Key]] = field(default_factory=dict)

    def key(self, name: str, start: Any, key: Key) -> None:
        """Adds a key. A field's first key starts it from `start`, what it is before anything moves."""
        keys = self.fields.setdefault(name, [Key(0.0, start)])
        keys[:] = sorted([old for old in keys if old.time != key.time] + [key], key=lambda k: k.time)

    @property
    def end(self) -> float:
        return max((keys[-1].time for keys in self.fields.values()), default=0.0)

    @property
    def times(self) -> set[float]:
        return {key.time for keys in self.fields.values() for key in keys}

    def at(self, time: float) -> dict[str, Any]:
        return {name: value_at(keys, time) for name, keys in self.fields.items()}


def value_at(keys: Sequence[Key], time: float) -> Any:
    if time <= keys[0].time:
        return keys[0].value
    if time >= keys[-1].time:
        return keys[-1].value
    index = next(i for i, key in enumerate(keys) if key.time > time)
    before, after = keys[index - 1], keys[index]
    u = (time - before.time) / (after.time - before.time)
    if after.ease == SMOOTH and isinstance(before.value, (int, float, Vec3)) and not isinstance(before.value, bool):
        return through(keys, index, u)
    return blend(before.value, after.value, EASES[after.ease](u))


def through(keys: Sequence[Key], index: int, u: float) -> Any:
    """A curve through the keys either side, in time, so that a move with several keys never stops at them. It starts and
    ends at rest."""
    span = keys[index].time - keys[index - 1].time
    parts = lambda key: tuple(key.value) if isinstance(key.value, Vec3) else (key.value,)

    def tangents(at: int) -> Sequence[float]:
        if at in (0, len(keys) - 1):
            return (0.0,) * len(parts(keys[at]))
        before, after = keys[at - 1], keys[at + 1]
        return [(b - a) / (after.time - before.time) * span for a, b in zip(parts(before), parts(after))]

    curve = [_hermite(a, b, out, into, u) for a, b, out, into
             in zip(parts(keys[index - 1]), parts(keys[index]), tangents(index - 1), tangents(index))]
    return Vec3(*curve) if isinstance(keys[index].value, Vec3) else curve[0]


def written(element: Any, values: Mapping[str, Sequence[float]], fps: float, frames: int) -> None:
    """Keys on one element, one to a frame, leaving out what stays the same. A property that never changes has none."""
    last = frames - 1
    for name, column in values.items():
        if len(set(column)) > 1:
            animate = element.add_animate(property=name)
            for frame, value in enumerate(column):
                if frame in (0, last) or value != column[frame - 1] or value != column[frame + 1]:
                    animate.add_key(time=frame / fps, value=str(value))


class Clip:
    """A shot of a location, frame by frame. A location where nothing moves is one frame, and compiles as it always has."""

    def __init__(self, location: Any, shot: str, fps: float = 30) -> None:
        self.location, self.shot, self.fps = location, shot, fps
        length = location.duration(shot)
        self.frames = round(length * fps) + 1 if length else 1
        self.moving = self.frames > 1
        self.moments = [location.at(frame / fps) for frame in range(self.frames)] if self.moving else [location]
        self.takes = [moment.shots[shot] for moment in self.moments]
        self._walked: dict[int, list[Placed]] = {}
        self._placed: Optional[list[Placed]] = None

    @property
    def duration(self) -> float:
        return self.frames / self.fps

    def window(self, frame: int) -> dict[str, float]:
        """The attributes that make a node live for one frame."""
        return {"start": frame / self.fps, "end": (frame + 1) / self.fps}

    def _walk(self, node: Any) -> list[Placed]:
        if id(node) not in self._walked:  # most of a location does not move, so a moment shares those nodes
            self._walked[id(node)] = list(node.walk())
        return self._walked[id(node)]

    def placed(self) -> list[Placed]:
        """Every leaf at the first frame. One that moves carries its world at each frame."""
        if self._placed is None:
            self._placed = self._frames() if self.moving else self.location.placed()
        return self._placed

    def _frames(self) -> list[Placed]:
        columns = [[leaf for node in moment.nodes for leaf in self._walk(node)] for moment in self.moments]
        if any(len(column) != len(columns[0]) for column in columns):
            raise MotionError("a moving prefab changed how many parts it has; only what keeps its parts can move")
        return [self._tracked(leaves) for leaves in zip(*columns)]

    def _tracked(self, leaves: Sequence[Placed]) -> Placed:
        first = leaves[0]
        if all(leaf is first for leaf in leaves):
            return first
        size = _size(first.item)
        for leaf in leaves:
            if leaf.path != first.path or _size(leaf.item) != size:
                raise MotionError(f"{first.path} changes shape as it moves, and only its place and its turn can change")
        return Placed(first.item, first.world, first.path, first.roles, tuple(leaf.world for leaf in leaves))

    def solids(self) -> list[Placed]:
        return [leaf for leaf in self.placed() if isinstance(leaf.item, Solid)]

    def lights(self) -> list[Placed]:
        return [leaf for leaf in self.placed() if isinstance(leaf.item, Light)]


def _size(item: Any) -> Optional[Mapping[str, float]]:
    return item.dimensions() if isinstance(item, Solid) else None
