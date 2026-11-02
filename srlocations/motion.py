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

import re
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Optional, Sequence

from srlocations.geometry import Transform, Vec3
from srlocations.nodes import Light, Placed, Solid

SMOOTH = "smooth"
BEZIER = re.compile(r"cubic-bezier\(\s*([-+.\deE]+)\s*,\s*([-+.\deE]+)\s*,\s*([-+.\deE]+)\s*,\s*([-+.\deE]+)\s*\)")


class MotionError(ValueError):
    """A move that cannot be made."""


class Eases(dict):
    """Eases by name. A name written as CSS writes a curve, "cubic-bezier(x1, y1, x2, y2)", is an ease without being added."""

    def __missing__(self, name: str) -> Callable[[float], float]:
        found = BEZIER.fullmatch(name) if isinstance(name, str) else None
        if found is None:
            raise KeyError(name)
        return _bezier(*(float(part) for part in found.groups()))

    def __contains__(self, name: object) -> bool:
        return super().__contains__(name) or isinstance(name, str) and BEZIER.fullmatch(name) is not None


EASES: dict[str, Callable[[float], float]] = Eases({
    "linear": lambda u: u,
    "ease-in": lambda u: u * u,
    "ease-out": lambda u: u * (2 - u),
    "ease-in-out": lambda u: u * u * (3 - 2 * u),
    "hold": lambda u: 1.0 if u >= 1 else 0.0,
    SMOOTH: lambda u: u,  # passes through its keys without stopping; see `through`
})


def cubic_bezier(x1: float, y1: float, x2: float, y2: float) -> str:
    """The name of an ease drawn as CSS draws one: a curve from (0, 0) to (1, 1), time across and progress up, pulled by two
    handles. `move(ease=)` takes the name or the four numbers. A handle's x is within 0 to 1, so time only goes forward; its
    y may go past them, and then the move goes past its key and comes back."""
    if not (0 <= x1 <= 1 and 0 <= x2 <= 1):
        raise MotionError(f"a handle's x is within 0 to 1, as time only goes forward, not {x1} and {x2}")
    return f"cubic-bezier({x1:g}, {y1:g}, {x2:g}, {y2:g})"


def _bezier(x1: float, y1: float, x2: float, y2: float) -> Callable[[float], float]:
    cubic_bezier(x1, y1, x2, y2)
    along = lambda t, a, b: 3 * (1 - t) ** 2 * t * a + 3 * (1 - t) * t * t * b + t ** 3

    def ease(u: float) -> float:
        if u <= 0 or u >= 1:
            return 1.0 if u >= 1 else 0.0
        low, high = 0.0, 1.0
        for _ in range(52):  # halving to the last bit of a float: the curve's x only grows, so this always finds it
            middle = (low + high) / 2
            low, high = (middle, high) if along(middle, x1, x2) < u else (low, middle)
        return along((low + high) / 2, y1, y2)
    return ease


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
    if after.ease == SMOOTH and _parts(before.value) is not None:
        return through(keys, index, u)
    return blend(before.value, after.value, EASES[after.ease](u))


def _parts(value: Any) -> Optional[dict[Any, float]]:
    """A value as numbers that can each run along a curve: a number, a position's three, or a pose's controls."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return {"": float(value)}
    if isinstance(value, Vec3):
        return dict(enumerate(value))
    if isinstance(value, Mapping):
        return {name: float(control) for name, control in value.items()}
    return None


def _slope(before: float, here: float, after: float, behind: float, ahead: float) -> float:
    """How fast a curve runs through a key, from the slopes either side. It is zero where the keys turn back or hold, and
    never steeper than the slopes allow, so the curve never goes past a key (Fritsch and Carlson's monotone cubic)."""
    into, out = (here - before) / behind, (after - here) / ahead
    if into * out <= 0:
        return 0.0
    first, second = 2 * ahead + behind, ahead + 2 * behind
    return (first + second) / (first / into + second / out)


def through(keys: Sequence[Key], index: int, u: float) -> Any:
    """A curve through the keys either side, in time, so that a move with several keys never stops at them. It starts and
    ends at rest, and it never passes a key's value, so a body that is keyed to stop short of a wall stays short of it."""
    span = keys[index].time - keys[index - 1].time
    parts = [_parts(key.value) or {} for key in keys]
    names = sorted({name for part in parts for name in part}, key=str)

    def tangent(at: int, name: Any) -> float:
        if at in (0, len(keys) - 1):
            return 0.0
        values = [parts[k].get(name, 0.0) for k in (at - 1, at, at + 1)]
        return _slope(*values, keys[at].time - keys[at - 1].time, keys[at + 1].time - keys[at].time) * span

    curve = {name: _hermite(parts[index - 1].get(name, 0.0), parts[index].get(name, 0.0), tangent(index - 1, name),
                            tangent(index, name), u) for name in names}
    value = keys[index].value
    if isinstance(value, Vec3):
        return Vec3(*(curve[axis] for axis in range(3)))
    if isinstance(value, Mapping):
        return curve
    return curve[""]

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


class Frames:
    """What is drawn frame by frame under a parent, as paint and the wireframe are. Where a frame begins by adding the
    same as the frame before, but for ids and windows, those nodes of the frame before live on instead: a film whose camera
    stands still holds its paint once. Only a frame's first nodes can, so that what comes later stays on top."""

    def __init__(self, parent: Any) -> None:
        self.parent, self.last = parent, None

    def add(self, frame: int, window: Mapping[str, float], draw: Callable[[], Any]) -> Any:
        """Calls `draw`, which adds this frame's nodes to the parent with `window` and ids ending in -f and the frame."""
        count = len(self.parent.elements())
        result = draw()
        added = self.parent.elements()[count:]
        suffix = re.compile(f"-f{frame}(?![0-9])")
        signature = [_signature(element, suffix) for element in added]
        same = 0
        while self.last and same < min(len(added), len(self.last[0])) and signature[same] == self.last[0][same]:
            same += 1
        for element, held in zip(added[:same], self.last[1][:same] if self.last else ()):
            self.parent.remove(element)
            held.end = window["end"]
        self.last = (signature, (self.last[1][:same] if self.last else []) + added[same:])
        return result


def _signature(element: Any, suffix: "re.Pattern[str]") -> tuple:
    return (element.xml_name, element.content.strip(),
            tuple(sorted((name, suffix.sub("", str(value))) for name, value in element.attributes().items()
                         if name not in ("id", "start", "end"))),
            tuple(_signature(child, suffix) for child in element.elements()))


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
        placed = []
        for index in range(len(self.location.nodes)):
            columns = [self._walk(moment.nodes[index]) for moment in self.moments]
            shapes = [] if all(column is columns[0] for column in columns) else [shape(column) for column in columns]
            if all(each == shapes[0] for each in shapes):
                placed += [self._tracked(leaves) for leaves in zip(*columns)]
            else:
                placed += self._reshaped(columns, shapes)
        return placed

    def _tracked(self, leaves: Sequence[Placed]) -> Placed:
        first = leaves[0]
        if all(leaf is first for leaf in leaves):
            return first
        return Placed(first.item, first.world, first.path, first.roles, tuple(leaf.world for leaf in leaves))

    def _reshaped(self, columns: Sequence[list[Placed]], shapes: Sequence[tuple]) -> list[Placed]:
        """A node whose parts change: its solids in each shape, each living for the frames it has that shape. Its lights
        stay, because they are the document's, and so must not change in number."""
        lights = [[leaf for leaf in column if isinstance(leaf.item, Light)] for column in columns]
        if any(len(each) != len(lights[0]) for each in lights):
            raise MotionError(f"{columns[0][0].path.split('/')[0]} changes how many lights it has, which a film cannot")
        placed, first = [], 0
        for last in range(1, len(columns) + 1):
            if last < len(columns) and shapes[last] == shapes[first]:
                continue
            kept = shapes[first] == shapes[0]  # what has the parts it began with is keyed where they began
            solids = [[leaf for leaf in column if not isinstance(leaf.item, Light)] for column in columns[first:last]]
            for number, leaves in enumerate(zip(*solids)):
                worlds = [leaves[min(max(frame - first, 0), last - first - 1)].world for frame in range(self.frames)]
                placed.append(Placed(leaves[0].item, leaves[0].world, leaves[0].path, leaves[0].roles,
                                     tuple(worlds) if len(set(worlds)) > 1 else (), (first, last),
                                     [leaf for leaf in columns[0] if not isinstance(leaf.item, Light)][number].world
                                     if kept else None, None if kept else number))
            first = last
        return placed + [self._tracked(leaves) for leaves in zip(*lights)]

    def solids(self) -> list[Placed]:
        return [leaf for leaf in self.placed() if isinstance(leaf.item, Solid)]

    def lights(self) -> list[Placed]:
        return [leaf for leaf in self.placed() if isinstance(leaf.item, Light)]


def shape(leaves: Sequence[Placed]) -> tuple:
    """What a node's leaves are, apart from where: two moments of the same shape draw as one object that moves."""
    return tuple((leaf.path, type(leaf.item), leaf.item.dimensions(), leaf.item.geometry(1.0), leaf.item.skins())
                 if isinstance(leaf.item, Solid) else (leaf.path, leaf.item) for leaf in leaves)
