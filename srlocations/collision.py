"""Whether solids pass through each other, and when that matters.

Each solid gives `hulls()`: convex shapes in the world, described by how far each reaches in a direction. Two convex shapes
are apart exactly when some direction separates them, and the direction that needs the least travel says how to part them.

Not every overlap is a fault, so these rules decide, here and nowhere else:

- The parts of one object never clash. A chair's legs meet its seat, and a figure's limbs meet at their joints.
- A solid with no hulls has no body: a decal is paint, and a hollow model is a set to stand in.
- A node with `moves`, such as a figure, acts on the set, so nothing may pass through it beyond a TOUCH of contact.
- A cushion gives: a moving body may SINK into anything with the role `soft`, or in a material a location's Contact names.
- A limb wholly inside a closed shell is as wrong as one crossing it, though no hull of the shell touches it.
- Set pieces are dressed by hand and meet on purpose, as a table's legs stand on a rug, so they may share DRESSED of depth.
- A node with `yields` gives way to set pieces, as a tree's leaves do against a wall.
- A node with `collides` False has asked to be left out.

These numbers are a `Contact`, and `location.contact` holds a location's own. Overlap says nothing about support, so `gap()`
measures how far a limb is from what should carry it. `Location.settle()` moves a node clear, and a render refuses a figure
that is still passing through something.
"""
from __future__ import annotations

import math
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, replace
from typing import Any, Callable, Iterable, Iterator, NamedTuple, Optional, Sequence

from srlocations.geometry import Transform, Vec3

TOUCH = 0.005  # metres a moving body may press into what it rests on
SINK = 0.03  # metres a moving body may sink into a cushion
DRESSED = 0.03  # metres two set pieces may share
REST = 0.02  # a limb further than this from what should carry it is not resting on it
REACH = 0.8  # the furthest a body is moved to clear a set
GAP = 0.3  # the furthest gap() looks
SOFT = "soft"  # the role of what a body sinks into
SEE_THROUGH = frozenset({"window", "view"})  # roles a sight line passes
STEPS = 32
DIRECTIONS = tuple(Vec3(x, y, z) for x, y, z in ((1, 0, 0), (0, 1, 0), (0, 0, 1), (1, 1, 0), (1, -1, 0), (1, 0, 1), (1, 0, -1),
                                                 (0, 1, 1), (0, 1, -1), (1, 1, 1), (1, 1, -1), (1, -1, 1), (1, -1, -1)))


class CollisionError(ValueError):
    pass


@dataclass(frozen=True)
class Contact:
    """How far things may meet in one location. `cushions` names materials that are soft there, which is how a prop published
    without the `soft` role gives way: "studio.leather.cognac" matches every version of it."""
    touch: float = TOUCH
    sink: float = SINK
    dressed: float = DRESSED
    rest: float = REST
    reach: float = REACH
    cushions: Sequence[str] = ()

    def soft(self, leaf: Any) -> bool:
        return SOFT in leaf.roles or getattr(leaf.item, "material", "").split("@")[0] in self.cushions


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
    buried: bool = False  # `first` lies wholly inside `second`, so no depth says how to part them
    time: float = 0.0  # in a location that moves, when it first happens

    def __str__(self) -> str:
        what = f"{self.first} is buried in {self.second}" if self.buried else f"{self.first} is {self.depth * 100:.1f} cm inside {self.second}"
        return what + (f" at {self.time:g} s" if self.time else "")


class Piece(NamedTuple):
    """One convex shape of a body, and what the leaf it came from is."""
    hull: Hull
    box: tuple[Vec3, Vec3]
    path: str
    soft: bool = False
    roles: frozenset = frozenset()


@dataclass
class Body:
    """All the hulls of one node of a location, which never clash with each other."""
    node: Any
    hulls: list[Piece]
    low: Vec3
    high: Vec3
    shells: list[tuple[Any, Transform, str]] = field(default_factory=list)  # leaves that can hold something in them

    @classmethod
    def made(cls, node: Any, hulls: list[Piece], shells: Sequence = ()) -> Optional["Body"]:
        if not hulls:
            return None
        return cls(node, hulls, Vec3(*(min(getattr(piece.box[0], a) for piece in hulls) for a in "xyz")),
                   Vec3(*(max(getattr(piece.box[1], a) for piece in hulls) for a in "xyz")), list(shells))

    @classmethod
    def of(cls, node: Any, contact: Contact = Contact()) -> Optional["Body"]:
        hulls, shells = [], []
        for leaf in node.walk():
            if not hasattr(leaf.item, "hulls"):
                continue
            soft = contact.soft(leaf)
            hulls.extend(Piece(hull, hull.box(), leaf.path, soft, leaf.roles) for hull in leaf.item.hulls(leaf.world))
            if not soft and leaf.item.shell:
                shells.append((leaf.item, leaf.world, leaf.path))
        return cls.made(node, hulls, shells)

    def part(self, keep: Callable[[str], bool]) -> Optional["Body"]:
        """The hulls whose paths pass `keep`, as a body of their own."""
        return Body.made(self.node, [piece for piece in self.hulls if keep(piece.path)])

    def limbs(self) -> list["Body"]:
        """One body for each named part. A figure's joint ball counts with its bone."""
        names = dict.fromkeys(piece.path.partition(".")[0] for piece in self.hulls)
        return [self.part(lambda path, name=name: path.partition(".")[0] == name) for name in names]


def _near(low: Vec3, high: Vec3, other_low: Vec3, other_high: Vec3, shift: Vec3, margin: float = 0.0) -> bool:
    return all(l + s - margin < oh and h + s + margin > ol
               for l, h, ol, oh, s in zip(low, high, other_low, other_high, shift))


def deepest(a: Body, b: Body, shift: Vec3 = Vec3(), allow: float = 0.0, sink: Optional[float] = None) -> Optional[Clash]:
    """The worst overlap of two bodies beyond `allow`, or beyond `sink` where either side is soft."""
    worst: Optional[Clash] = None
    if not _near(a.low, a.high, b.low, b.high, shift):
        return None
    for mine in a.hulls:
        if not _near(*mine.box, b.low, b.high, shift):
            continue
        for other in b.hulls:
            if _near(*mine.box, *other.box, shift):
                soft = sink is not None and (mine.soft or other.soft)
                found = overlap(mine.hull, other.hull, shift, sink if soft else allow)
                if found and (worst is None or found[0] > worst.depth):
                    worst = Clash(mine.path, other.path, found[0], found[1])
    return worst


def buried(a: Body, b: Body, shift: Vec3 = Vec3()) -> Optional[Clash]:
    """A part of `a`, moved by `shift`, lying wholly inside a shell of `b`."""
    if not b.shells or not _near(a.low, a.high, b.low, b.high, shift):
        return None
    for piece in a.hulls:
        for shell, world, path in b.shells:
            if shell.encloses(piece.hull.centre + shift, world):
                return Clash(piece.path, path, 0.0, Vec3(0, 1, 0), buried=True)
    return None


def _broken(body: Body, other: Body, moving: bool, contact: Contact) -> Optional[Clash]:
    if not moving:
        return deepest(body, other, allow=contact.dressed)
    return deepest(body, other, allow=contact.touch, sink=contact.sink) or (buried(body, other) if not other.node.moves else None)


def limb_clashes(limb: Body, others: Iterable[Body], contact: Contact = Contact()) -> Iterator[Clash]:
    """The worst thing one limb of a moving body breaks, if anything."""
    worst = max(filter(None, (_broken(limb, other, True, contact) for other in others)), key=lambda clash: (clash.buried, clash.depth), default=None)
    if worst:
        yield replace(worst, moving=True)


def clashes(nodes: Iterable[Any], bodies_only: bool = False, contact: Contact = Contact()) -> Iterator[Clash]:
    """Every pair of nodes that breaks the rules above, the deepest place standing for the pair. `bodies_only` looks at nothing
    but moving bodies."""
    present = [node for node in nodes if node.collides]
    if bodies_only and not any(node.moves for node in present):
        return
    bodies = [body for body in (Body.of(node, contact) for node in present) if body]
    bodies.sort(key=lambda body: not body.node.moves)  # a moving body is named first
    for index, body in enumerate(bodies):
        for other in bodies[index + 1:]:
            moving = body.node.moves or other.node.moves
            if moving or not (bodies_only or body.node.yields or other.node.yields):
                found = _broken(body, other, moving, contact)
                if found:
                    yield replace(found, moving=moving)


def gap(limb: Body, others: Sequence[Body], way: Vec3, limit: float = GAP, step: float = 0.005) -> float:
    """How far a limb moves along `way` before it meets one of the others, in metres, up to `limit`."""
    others = [other for other in others if _near(limb.low, limb.high, other.low, other.high, Vec3(), limit)]
    for count in range(round(limit / step) + 1):
        shift = Vec3(way.x * count * step, way.y * count * step, way.z * count * step)
        if any(deepest(limb, other, shift) for other in others):
            return count * step
    return limit


def blocked(start: Vec3, end: Vec3, bodies: Sequence[Body]) -> Optional[str]:
    """What the straight line between two points passes through first, if anything. Glass and pictures do not stop it."""
    line, hits = Cloud([start, end]), []
    low = Vec3(*(min(getattr(start, a), getattr(end, a)) for a in "xyz"))
    high = Vec3(*(max(getattr(start, a), getattr(end, a)) for a in "xyz"))
    for body in bodies:
        if not _near(low, high, body.low, body.high, Vec3()):
            continue
        for piece in body.hulls:
            if not piece.roles & SEE_THROUGH and _near(low, high, *piece.box, Vec3()) and overlap(line, piece.hull):
                hits.append(((piece.hull.centre - start).length, piece.path))
    return min(hits)[1] if hits else None


def fits(node: Any, others: Iterable[Body], contact: Contact = Contact()) -> bool:
    """Whether a moving node, as it is now, breaks no rule against these bodies."""
    body = Body.of(node, contact)
    return body is None or not any(_broken(body, other, True, contact) for other in others)


def clear(node: Any, nodes: Iterable[Any], contact: Contact = Contact()) -> Vec3:
    """The least move that takes a node out of the others, resting it on what it presses down on. Raises if none is near."""
    body = Body.of(node, contact)
    if body is None:
        return Vec3()
    others = [other for other in (Body.of(n, contact) for n in nodes if n is not node and n.collides) if other
              and _near(body.low, body.high, other.low, other.high, Vec3(), contact.reach)]
    shift, last = Vec3(), None
    for _ in range(STEPS):
        found = [clash for clash in (deepest(body, other, shift, contact.touch, contact.sink) for other in others) if clash]
        if not found:
            inside = next(filter(None, (buried(body, other, shift) for other in others if not other.node.moves)), None)
            if inside:
                raise CollisionError(f"{node.label} has no room here: {inside}")
            return shift
        last = max(found, key=lambda clash: clash.depth)
        travel = last.depth + TOUCH / 2
        if last.way.y > 0.5:  # it is on top of this: a body rises off it and does not slide
            shift = shift + Vec3(0, travel / last.way.y, 0)
        else:
            shift = shift + Vec3(last.way.x * travel, last.way.y * travel, last.way.z * travel)
        if shift.length > contact.reach:
            break
    raise CollisionError(f"{node.label} has no room here: {last}")
