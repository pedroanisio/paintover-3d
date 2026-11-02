"""The scene graph: everything a location holds is a Node that places Solids and Lights in the world."""
from __future__ import annotations

import math
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, replace
from typing import Any, Iterator, Mapping, Optional, Sequence, Union

from srlocations.collision import Block, Cloud, Drum, Egg, Hull
from srlocations.geometry import Matrix, Transform, Vec3, VecLike, corners
from srlocations.materials import Material


Polyline = list[tuple[float, float, float]]
WIRE_SEGMENTS = 16


def ring(radius: float, y: float) -> Polyline:
    """A closed circle in the xz plane at height y."""
    turns = [2 * math.pi * i / WIRE_SEGMENTS for i in range(WIRE_SEGMENTS + 1)]
    return [(radius * math.cos(t), y, radius * math.sin(t)) for t in turns]


@dataclass(frozen=True)
class Placed:
    """A leaf of the graph with its world transform; `path` names the prefabs it came through, and `roles` holds what it
    and they are in the set."""
    item: Union["Solid", "Light"]
    world: Transform
    path: str
    roles: frozenset[str] = frozenset()
    track: tuple[Transform, ...] = ()  # its world at each frame of a clip, when it moves

    def within(self, part: "Solid") -> "Placed":
        """A part of this solid, which moves with it. A part that `is` the solid must not apply its transform again."""
        if part is self.item:
            return self
        return replace(self, item=part, world=self.world.then(part.transform),
                       track=tuple(world.then(part.transform) for world in self.track))


@dataclass(frozen=True)
class Seat:
    """Somewhere a figure can sit: the floor under its hips there, the way it faces, how high the seat is above that, and
    how far ahead its front edge is."""
    at: Vec3
    facing: float
    height: float = 0.0
    depth: float = 0.0


@dataclass
class Node(ABC):
    at: VecLike = field(default=(0, 0, 0), kw_only=True)
    yaw: float = field(default=0.0, kw_only=True)
    pitch: float = field(default=0.0, kw_only=True)
    roll: float = field(default=0.0, kw_only=True)
    name: Optional[str] = field(default=None, kw_only=True)
    basis: Optional[Matrix] = field(default=None, kw_only=True)  # replaces yaw, pitch and roll when set
    role: str = field(default="", kw_only=True)  # what it is in the set, for a look to aim at; spaces part several
    moves = False  # True for what acts on a set, which nothing may pass through; see collision.py
    collides = True
    yields = False  # True for what gives way to other set pieces, as leaves do; a figure still cannot walk through it
    sits = False  # True for what takes a seat when one is near

    def keyed(self, values: Mapping[str, Any]) -> dict[str, Any]:
        """What a key on this node holds: these values in a form that can be blended."""
        return {key: Vec3.of(value) if key == "at" else value for key, value in values.items()}

    def posed(self, values: Mapping[str, Any]) -> "Node":
        """This node with keyed values, at one moment."""
        return replace(self, **values)

    def seats(self) -> Sequence[Seat]:
        """The places it offers to sit, in its local frame."""
        return ()

    def sitting(self) -> tuple[float, float]:
        """In its local frame, how high what it sits on is, and how far ahead the backs of its knees are."""
        return 0.0, 0.0

    @property
    def transform(self) -> Transform:
        if self.basis is not None:
            return Transform(Vec3.of(self.at), self.basis)
        return Transform.at(self.at, self.yaw, self.pitch, self.roll)

    def parts(self) -> Sequence["Node"]:
        """The nodes directly under this one."""
        return ()

    def descend(self) -> Iterator["Node"]:
        """This node and everything under it, prefabs included."""
        yield self
        for part in self.parts():
            yield from part.descend()

    @property
    def label(self) -> str:
        return self.name or type(self).__name__.lower()

    @abstractmethod
    def walk(self, parent: Transform = Transform(), path: str = "") -> Iterator[Placed]:
        """Every leaf under this node, in world space."""

    def tagged(self, leaves: Iterator[Placed]) -> Iterator[Placed]:
        """Leaves from under this node, which take on its roles."""
        own = frozenset(self.role.split())
        return (replace(leaf, roles=leaf.roles | own) for leaf in leaves) if own else leaves


@dataclass(frozen=True)
class Skin:
    """One material of a solid. `name` is what a look or palette knows it by. `slot` is the part of an imported model it
    covers, and empty means the whole solid. `own` is the material the file gives it, which a registry does not know."""
    name: str
    slot: str = ""
    own: Optional[Material] = None


@dataclass
class Solid(Node):
    """One engine primitive. `material` is a name the location's registry resolves."""
    material: str = field(default="stock.default", kw_only=True)
    casts_shadow: bool = field(default=True, kw_only=True)
    primitive = ""
    hollow = False  # True when its bounds are not filled, so cameras and marks may be inside them

    def walk(self, parent: Transform = Transform(), path: str = "") -> Iterator[Placed]:
        yield Placed(self, parent.then(self.transform), f"{path}/{self.label}".lstrip("/"), frozenset(self.role.split()))

    @abstractmethod
    def dimensions(self) -> dict[str, float]:
        """The primitive's size attributes in metres, by engine attribute name."""

    def geometry(self, units: float) -> dict[str, Any]:
        """Engine attributes that are not plain sizes, such as a path. `units` is scene units per metre."""
        return {}

    def dress(self, element: Any) -> None:
        """Adds whatever the engine reads from child elements to this solid's <object3D>."""

    def declare(self, scene: Any) -> None:
        """Adds anything this solid needs in the document beyond its <object3D>, such as an asset."""

    def skins(self) -> list[Skin]:
        """The materials it is drawn in."""
        return [Skin(self.material)]

    def two_sided(self, materials: Any) -> bool:
        """Whether its faces show from behind, so that anything drawn in its place must keep them."""
        return any((skin.own or materials.get(skin.name)).extra.get("doubleSided") for skin in self.skins())

    def facets(self) -> list[tuple["Solid", Vec3]]:
        """The surfaces ink can tell apart, each as a solid and its outward normal; a zero normal means a curved one."""
        return [(self, Vec3(0, 0, 0))]

    def spans(self) -> list[tuple["Solid", float, float]]:
        """The surfaces a texture is laid on, each with the metres that one 0 to 1 of its UVs covers across and up. The
        engine scales UVs per material and maps every face of a primitive 0 to 1, so a texture stretches on its own."""
        half = self.half_extents()
        return [(self, 2 * half.x, 2 * half.y)]

    def bands(self, spacing: float) -> list["Solid"]:
        """Its curved surface as solids laid side by side, about `spacing` metres wide, so ink can draw a line between them.
        None of them means it stays whole: too small to divide, or a model, whose triangles are in the file."""
        return []

    def faces(self) -> list[tuple[tuple[Vec3, ...], Vec3]]:
        """Its flat faces in the local frame, as corners and an outward normal, for a texture to run across in world space.
        None of these means a texture is laid through spans() instead."""
        return []

    def drawn_in(self, look: str) -> bool:
        """Whether this solid belongs in a look, by the look's name."""
        return True

    @abstractmethod
    def half_extents(self) -> Vec3:
        """Half the size of the primitive's local bounding box."""

    def hulls(self, world: Transform) -> list[Hull]:
        """Its body as convex shapes in the world, for collision; none means nothing can hit it."""
        return [Block(world, self.half_extents())]

    def edges(self) -> list[Polyline]:
        """The lines a wireframe draws, in the local frame. By default the bounding box's twelve edges."""
        x, y, z = self.half_extents()
        rims = [[(sx * x, b, sz * z) for sx, sz in ((-1, -1), (1, -1), (1, 1), (-1, 1), (-1, -1))] for b in (-y, y)]
        pillars = [[(sx * x, -y, sz * z), (sx * x, y, sz * z)] for sx in (-1, 1) for sz in (-1, 1)]
        return rims + pillars

    def bounds(self, world: Transform) -> tuple[Vec3, Vec3]:
        points = list(corners(world, self.half_extents()))
        return (Vec3(*(min(getattr(p, a) for p in points) for a in "xyz")),
                Vec3(*(max(getattr(p, a) for p in points) for a in "xyz")))


@dataclass
class Box(Solid):
    size: VecLike = (1, 1, 1)
    primitive = "box"

    def dimensions(self) -> dict[str, float]:
        w, h, d = Vec3.of(self.size)
        return {"width": w, "height": h, "depth": d}

    def half_extents(self) -> Vec3:
        w, h, d = Vec3.of(self.size)
        return Vec3(w / 2, h / 2, d / 2)

    def facets(self) -> list[tuple[Solid, Vec3]]:
        """A thin slab inside each face, flush with it: one primitive has one material, and creases need six."""
        half, slabs = tuple(self.half_extents()), []
        depth = min(0.001, min(half) / 2)
        for axis in range(3):
            for sign in (-1, 1):
                size, at, normal = [2 * h for h in half], [0.0, 0.0, 0.0], [0.0, 0.0, 0.0]
                size[axis], at[axis], normal[axis] = depth, sign * (half[axis] - depth / 2), float(sign)
                slabs.append((Box(tuple(size), at=tuple(at), casts_shadow=False), Vec3(*normal)))
        return slabs

    def faces(self) -> list[tuple[tuple[Vec3, ...], Vec3]]:
        half, sides = tuple(self.half_extents()), []
        for axis in range(3):
            across, up = (axis + 1) % 3, (axis + 2) % 3
            for sign in (-1, 1):
                corners_of = []
                for a, b in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
                    point = [0.0, 0.0, 0.0]
                    point[axis], point[across], point[up] = sign * half[axis], a * half[across], b * half[up]
                    corners_of.append(Vec3(*point))
                normal = [0.0, 0.0, 0.0]
                normal[axis] = float(sign)
                sides.append((tuple(corners_of), Vec3(*normal)))
        return sides

    def spans(self) -> list[tuple[Solid, float, float]]:
        """A panel on each face. The engine runs a box's UVs a different way along each axis and cannot rotate them, so
        each panel is a box turned until its front faces out: u runs across and v up, and bricks stay in courses."""
        w, h, d = Vec3.of(self.size)
        depth = min(0.001, min(w, h, d) / 4)
        faces = [(w, h, (0, 0, (d - depth) / 2), {}), (d, h, ((w - depth) / 2, 0, 0), {"yaw": 90.0}),
                 (w, d, (0, (h - depth) / 2, 0), {"pitch": 90.0})]
        return [(Box((across, up, depth), at=tuple(sign * v for v in at), casts_shadow=False, **turn), across, up)
                for across, up, at, turn in faces for sign in (-1, 1)]


@dataclass
class Round(Solid):
    """A solid of revolution with its axis along local y."""
    radius: float = 0.5
    height: float = 1.0
    segments: int = field(default=32, kw_only=True)

    def dimensions(self) -> dict[str, float]:
        return {"radius": self.radius, "height": self.height}

    def half_extents(self) -> Vec3:
        return Vec3(self.radius, self.height / 2, self.radius)

    def rung(self, height: float) -> float:
        """Its radius at a height above its middle."""
        return self.radius

    def bands(self, spacing: float) -> list[Solid]:
        change = self.rung(self.height / 2) - self.rung(-self.height / 2)
        count = round(math.hypot(change, self.height) / spacing)
        if count < 2:
            return []
        low, step, distance = -self.height / 2, self.height / count, f"({self.rung(0.0)} + {change / self.height} * v)"
        return [strip(f"{distance} * cos(u)", "v", f"{distance} * sin(u)", (low + i * step, low + (i + 1) * step),
                      self.segments) for i in range(count)]

    def spokes(self) -> list[tuple[float, float]]:
        """Eight directions around the axis, as x and z on a circle of this radius."""
        return [(self.radius * math.cos(t), self.radius * math.sin(t)) for t in (i * math.pi / 4 for i in range(8))]


@dataclass
class Backdrop(Solid):
    """A picture hung in the local x-y plane, facing -z, centred on its origin. It has no body, and the engine does not
    draw a plane's back, but a shot from outside a building can still find one facing it across the set."""
    width: float = 4.0
    height: float = 2.0
    primitive = "plane"
    hollow = True

    def __post_init__(self) -> None:
        self.casts_shadow = False

    def hulls(self, world: Transform) -> list[Hull]:
        return []

    def dimensions(self) -> dict[str, float]:
        return {"width": self.width, "height": self.height}

    def half_extents(self) -> Vec3:
        return Vec3(self.width / 2, self.height / 2, 0.0)

    def edges(self) -> list[Polyline]:
        return []


def strip(x: str, y: str, z: str, v: tuple[float, float], segments: int) -> Solid:
    """A band around a solid of revolution."""
    from srlocations.surfaces import Surface  # built on this module
    return Surface(x, y, z, u=(0, 360), v=v, samples=(segments + 1, 8), closed=(True, False), casts_shadow=False)


def caps(radius: float, height: float, ends: Sequence[int]) -> list[tuple[Solid, Vec3]]:
    """Thin discs just outside the flat ends of a round solid."""
    return [(Cylinder(radius, 0.001, at=(0, end * (height / 2 + 0.0005), 0), casts_shadow=False), Vec3(0, float(end), 0))
            for end in ends]


class Cylinder(Round):
    primitive = "cylinder"

    def hulls(self, world: Transform) -> list[Hull]:
        return [Drum(world, self.radius, self.height)]

    def facets(self) -> list[tuple[Solid, Vec3]]:
        return [(self, Vec3(0, 0, 0)), *caps(self.radius, self.height, (-1, 1))]

    def spans(self) -> list[tuple[Solid, float, float]]:
        return [(self, 2 * math.pi * self.radius, self.height),
                *((cap, 2 * self.radius, 2 * self.radius) for cap, _ in self.facets()[1:])]

    def edges(self) -> list[Polyline]:
        h = self.height / 2
        return [ring(self.radius, -h), ring(self.radius, h), *([(x, -h, z), (x, h, z)] for x, z in self.spokes())]


class Cone(Round):
    """The point is at the top."""
    primitive = "cone"

    def rung(self, height: float) -> float:
        return self.radius * (0.5 - height / self.height)

    def hulls(self, world: Transform) -> list[Hull]:
        h = self.height / 2
        return [Cloud([world.apply((0.0, h, 0.0)), *(world.apply((x, -h, z)) for x, z in self.spokes())])]

    def facets(self) -> list[tuple[Solid, Vec3]]:
        return [(self, Vec3(0, 0, 0)), *caps(self.radius, self.height, (-1,))]

    def spans(self) -> list[tuple[Solid, float, float]]:
        return [(self, 2 * math.pi * self.radius, math.hypot(self.radius, self.height)),
                *((cap, 2 * self.radius, 2 * self.radius) for cap, _ in self.facets()[1:])]

    def edges(self) -> list[Polyline]:
        h = self.height / 2
        return [ring(self.radius, -h), *([(x, -h, z), (0.0, h, 0.0)] for x, z in self.spokes())]


@dataclass
class Sphere(Solid):
    radius: float = 0.5
    segments: int = field(default=32, kw_only=True)
    primitive = "sphere"

    def bands(self, spacing: float) -> list[Solid]:
        """Between circles of latitude, evenly spaced up the surface."""
        count = round(math.pi * self.radius / spacing)
        if count < 2:
            return []
        r, step = self.radius, 180 / count
        return [strip(f"{r} * cos(v) * cos(u)", f"{r} * sin(v)", f"{r} * cos(v) * sin(u)",
                      (-90 + i * step, -90 + (i + 1) * step), self.segments) for i in range(count)]

    def hulls(self, world: Transform) -> list[Hull]:
        return [Egg(world, (self.radius,) * 3)]

    def dimensions(self) -> dict[str, float]:
        return {"radius": self.radius}

    def half_extents(self) -> Vec3:
        return Vec3(self.radius, self.radius, self.radius)

    def spans(self) -> list[tuple[Solid, float, float]]:
        return [(self, 2 * math.pi * self.radius, math.pi * self.radius)]

    def edges(self) -> list[Polyline]:
        r = self.radius
        rings = [ring(r * math.cos(t), r * math.sin(t)) for t in (-math.pi / 4, 0.0, math.pi / 4)]
        for yaw in (0.0, math.pi / 2):
            turns = [2 * math.pi * i / WIRE_SEGMENTS for i in range(WIRE_SEGMENTS + 1)]
            rings.append([(r * math.cos(t) * math.cos(yaw), r * math.sin(t), r * math.cos(t) * math.sin(yaw))
                          for t in turns])
        return rings


@dataclass
class Group(Node):
    """Nodes that move together."""
    children: Sequence[Node] = ()

    def parts(self) -> Sequence[Node]:
        return self.children

    def walk(self, parent: Transform = Transform(), path: str = "") -> Iterator[Placed]:
        world, here = parent.then(self.transform), f"{path}/{self.label}".lstrip("/")
        for child in self.children:
            yield from self.tagged(child.walk(world, here))


@dataclass
class Prefab(Node):
    """A reusable, parametric piece of a location: subclass it as a dataclass and implement build()."""

    @abstractmethod
    def build(self) -> Sequence[Node]:
        """The nodes of this prefab in its local frame, with the origin on the floor at its centre."""

    def parts(self) -> Sequence[Node]:
        return self.build()

    def walk(self, parent: Transform = Transform(), path: str = "") -> Iterator[Placed]:
        world, here = parent.then(self.transform), f"{path}/{self.label}".lstrip("/")
        for child in self.build():
            yield from self.tagged(child.walk(world, here))


@dataclass
class Light(Node):
    """A light is a node, so a lamp prefab can carry the light it gives."""
    intensity: float = 1.0
    color: str = field(default="#ffffff", kw_only=True)
    shadows: bool = field(default=False, kw_only=True)
    softness: float = field(default=0.0, kw_only=True)
    kind = ""

    def walk(self, parent: Transform = Transform(), path: str = "") -> Iterator[Placed]:
        yield Placed(self, parent.then(self.transform), f"{path}/{self.label}".lstrip("/"))

    def attributes(self) -> dict[str, Any]:
        """Attributes particular to this kind of light, in engine units."""
        return {}


class Ambient(Light):
    kind = "ambient"


class Sun(Light):
    """Directional, in lux; `yaw` and `pitch` say where it points."""
    kind = "directional"


@dataclass
class Sky(Ambient):
    """A gradient dome: it lights the location from every side, shows in its reflections and is drawn behind it."""
    zenith: str = field(default="#3a6ea5", kw_only=True)
    horizon: str = field(default="#c8d8e8", kw_only=True)
    ground: str = field(default="#4a4038", kw_only=True)
    falloff: float = field(default=0.5, kw_only=True)  # below 1 the horizon colour climbs further up the sky
    kind = "dome"

    def attributes(self) -> dict[str, Any]:
        return {"sky": "gradient", "environmentVisible": True, "skyZenith": self.zenith, "skyHorizon": self.horizon,
                "skyGround": self.ground, "skyExponent": self.falloff}


@dataclass
class Point(Light):
    """In candela; `reach` is where it fades out, in metres."""
    reach: Optional[float] = field(default=None, kw_only=True)
    kind = "point"

    def attributes(self) -> dict[str, float]:
        return {} if self.reach is None else {"range": self.reach * 100}


@dataclass
class Spot(Point):
    cone: float = field(default=45.0, kw_only=True)
    kind = "spot"

    def attributes(self) -> dict[str, float]:
        return {**super().attributes(), "spotAngle": self.cone}
