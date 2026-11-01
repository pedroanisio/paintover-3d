"""Whether solids pass through each other, and when that matters.

Each solid gives `hulls()`: convex shapes in the world, described by how far each reaches in a direction. Two convex shapes
are apart exactly when some direction separates them, and the direction that needs the least travel says how to part them.

Not every overlap is a fault, so these rules decide, here and nowhere else:

- The parts of one object never clash. A chair's legs meet its seat, and a figure's limbs meet at their joints.
- A solid with no hulls has no body: a decal is paint, and a hollow model is a set to stand in.
- A node with `moves`, such as a figure, acts on the set, so nothing may pass through it beyond a TOUCH of contact.
- Set pieces are dressed by hand and meet on purpose, as a table's legs stand on a rug, so they may share DRESSED of depth.
- A node with `yields` gives way to set pieces, as a tree's leaves do against a wall.
- A node with `collides` False has asked to be left out.

`Location.settle()` moves a node clear, and a render refuses a figure that is still passing through something.
"""
from __future__ import annotations

import math
from abc import ABC, abstractmethod
from dataclasses import dataclass, replace
from typing import Any, Iterable, Iterator, Optional, Sequence

from srlocations.geometry import Transform, Vec3

TOUCH = 0.005  # metres a moving body may press into what it rests on
DRESSED = 0.03  # metres two set pieces may share
REACH = 0.8  # the furthest a body is moved to clear a set
STEPS = 32
DIRECTIONS = tuple(Vec3(x, y, z) for x, y, z in ((1, 0, 0), (0, 1, 0), (0, 0, 1), (1, 1, 0), (1, -1, 0), (1, 0, 1), (1, 0, -1),
                                                 (0, 1, 1), (0, 1, -1), (1, 1, 1), (1, 1, -1), (1, -1, 1), (1, -1, -1)))


class CollisionError(ValueError):
    pass


def _unit(v: Vec3) -> Optional[Vec3]:
    return Vec3(v.x / v.length, v.y / v.length, v.z / v.length) if v.length > 1e-9 else None


def _dot(a: Vec3, b: Vec3) -> float:
    return a.x * b.x + a.y * b.y + a.z * b.z


def _columns(world: Transform) -> tuple[Vec3, Vec3, Vec3]:
    b = world.basis
    return Vec3(b[0][0], b[1][0], b[2][0]), Vec3(b[0][1], b[1][1], b[2][1]), Vec3(b[0][2], b[1][2], b[2][2])


class Hull(ABC):
    """A convex shape in the world."""
    axes: Sequence[Vec3] = ()  # directions likely to part it from something: its faces
    centre: Vec3

    @abstractmethod
    def reach(self, d: Vec3) -> float:
        """How far it extends along the unit direction d."""

    def box(self) -> tuple[Vec3, Vec3]:
        x, y, z = Vec3(1, 0, 0), Vec3(0, 1, 0), Vec3(0, 0, 1)
        return (Vec3(-self.reach(Vec3(-1, 0, 0)), -self.reach(Vec3(0, -1, 0)), -self.reach(Vec3(0, 0, -1))),
                Vec3(self.reach(x), self.reach(y), self.reach(z)))


class Block(Hull):
    def __init__(self, world: Transform, half: Vec3) -> None:
        self.centre, self.axes, self.half = world.position, _columns(world), tuple(half)

    def reach(self, d: Vec3) -> float:
        return _dot(self.centre, d) + sum(abs(_dot(axis, d)) * half for axis, half in zip(self.axes, self.half))


class Egg(Hull):
    def __init__(self, world: Transform, radii: Sequence[float]) -> None:
        self.centre, self.axes, self.radii = world.position, _columns(world), tuple(radii)

    def reach(self, d: Vec3) -> float:
        return _dot(self.centre, d) + math.sqrt(sum((_dot(axis, d) * r) ** 2 for axis, r in zip(self.axes, self.radii)))


class Drum(Hull):
    """A cylinder, along local y."""

    def __init__(self, world: Transform, radius: float, height: float) -> None:
        self.centre, self.axis, self.radius, self.half = world.position, _columns(world)[1], radius, height / 2
        self.axes = (self.axis,)

    def reach(self, d: Vec3) -> float:
        along = _dot(self.axis, d)
        return _dot(self.centre, d) + abs(along) * self.half + math.sqrt(max(0.0, 1 - along * along)) * self.radius


class Cloud(Hull):
    """The convex hull of some points: a cone, a patch of a curved surface, the box of a model."""

    def __init__(self, points: Sequence[Vec3]) -> None:
        self.points = list(points)
        self.centre = Vec3(*(sum(getattr(p, a) for p in self.points) / len(self.points) for a in "xyz"))
        if len(self.points) >= 3:
            a, b, c = self.points[:3]
            u, v = b - a, c - a
            normal = _unit(Vec3(u.y * v.z - u.z * v.y, u.z * v.x - u.x * v.z, u.x * v.y - u.y * v.x))
            self.axes = (normal,) if normal else ()

    def reach(self, d: Vec3) -> float:
        return max(_dot(point, d) for point in self.points)


def overlap(a: Hull, b: Hull, shift: Vec3 = Vec3(), allow: float = 0.0) -> Optional[tuple[float, Vec3]]:
    """How far `a`, moved by `shift`, must go to clear `b`, and which way; None if they share no more than `allow`."""
    def depth(n: Vec3) -> float:
        return b.reach(n) + a.reach(Vec3(-n.x, -n.y, -n.z)) - _dot(shift, n)

    best, way = math.inf, Vec3(1, 0, 0)
    towards = _unit(a.centre + shift - b.centre)
    for n in (*([towards] if towards else []), *a.axes, *b.axes, *(_unit(d) for d in DIRECTIONS)):
        for signed in (n, Vec3(-n.x, -n.y, -n.z)):
            found = depth(signed)
            if found <= allow:
                return None
            if found < best:
                best, way = found, signed
    step = 0.4
    while step > 0.02:  # the deepest curves part along no listed direction, so feel around the best one
        for side in (Vec3(step, 0, 0), Vec3(-step, 0, 0), Vec3(0, step, 0), Vec3(0, -step, 0), Vec3(0, 0, step), Vec3(0, 0, -step)):
            turned = _unit(way + side)
            if turned is None:
                continue
            found = depth(turned)
            if found <= allow:
                return None
            if found < best:
                best, way = found, turned
                break
        else:
            step /= 2
    return best, way


@dataclass(frozen=True)
class Clash:
    """`first` is `depth` metres into `second`; moving it along `way` by that much parts them."""
    first: str
    second: str
    depth: float
    way: Vec3
    moving: bool = False  # a moving body is in it, so it is a fault and not a question

    def __str__(self) -> str:
        return f"{self.first} is {self.depth * 100:.1f} cm inside {self.second}"


@dataclass
class Body:
    """All the hulls of one node of a location, which never clash with each other."""
    node: Any
    hulls: list[tuple[Hull, tuple[Vec3, Vec3], str]]
    low: Vec3
    high: Vec3

    @classmethod
    def of(cls, node: Any) -> Optional["Body"]:
        hulls = []
        for leaf in node.walk():
            for hull in leaf.item.hulls(leaf.world) if hasattr(leaf.item, "hulls") else ():
                hulls.append((hull, hull.box(), leaf.path))
        if not hulls:
            return None
        return cls(node, hulls, Vec3(*(min(getattr(box[0], a) for _, box, _ in hulls) for a in "xyz")),
                   Vec3(*(max(getattr(box[1], a) for _, box, _ in hulls) for a in "xyz")))


def _near(low: Vec3, high: Vec3, other_low: Vec3, other_high: Vec3, shift: Vec3, margin: float = 0.0) -> bool:
    return all(l + s - margin < oh and h + s + margin > ol
               for l, h, ol, oh, s in zip(low, high, other_low, other_high, shift))


def deepest(a: Body, b: Body, shift: Vec3 = Vec3(), allow: float = 0.0) -> Optional[Clash]:
    worst: Optional[Clash] = None
    if not _near(a.low, a.high, b.low, b.high, shift):
        return None
    for hull, (low, high), path in a.hulls:
        if not _near(low, high, b.low, b.high, shift):
            continue
        for other, (other_low, other_high), other_path in b.hulls:
            if _near(low, high, other_low, other_high, shift):
                found = overlap(hull, other, shift, allow)
                if found and (worst is None or found[0] > worst.depth):
                    worst = Clash(path, other_path, found[0], found[1])
    return worst


def clashes(nodes: Iterable[Any], bodies_only: bool = False) -> Iterator[Clash]:
    """Every pair of nodes that breaks the rules above. `bodies_only` looks at nothing but moving bodies."""
    present = [node for node in nodes if node.collides]
    if bodies_only and not any(node.moves for node in present):
        return
    bodies = [body for body in map(Body.of, present) if body]
    bodies.sort(key=lambda body: not body.node.moves)  # a moving body is named first
    for index, body in enumerate(bodies):
        for other in bodies[index + 1:]:
            moving = body.node.moves or other.node.moves
            if moving or not (bodies_only or body.node.yields or other.node.yields):
                found = deepest(body, other, allow=TOUCH if moving else DRESSED)
                if found:
                    yield replace(found, moving=moving)


def clear(node: Any, nodes: Iterable[Any]) -> Vec3:
    """The least move that takes a node out of the others, resting it on what it presses down on. Raises if none is near."""
    body = Body.of(node)
    if body is None:
        return Vec3()
    others = [other for other in map(Body.of, (n for n in nodes if n is not node and n.collides)) if other
              and _near(body.low, body.high, other.low, other.high, Vec3(), REACH)]
    shift, last = Vec3(), None
    for _ in range(STEPS):
        found = [clash for clash in (deepest(body, other, shift, TOUCH) for other in others) if clash]
        if not found:
            return shift
        last = max(found, key=lambda clash: clash.depth)
        travel = last.depth + TOUCH / 2
        if last.way.y > 0.5:  # it is on top of this: a body rises off it and does not slide
            shift = shift + Vec3(0, travel / last.way.y, 0)
        else:
            shift = shift + Vec3(last.way.x * travel, last.way.y * travel, last.way.z * travel)
        if shift.length > REACH:
            break
    raise CollisionError(f"{node.label} has no room here: {last}")
