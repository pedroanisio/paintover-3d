"""A city park on a summer afternoon: a brick path curving away between lawns, a slatted bench in front of a clipped hedge,
broadleaf trees, and glass towers past the far trees. publish_catalog.py freezes it, so a project uses it without this file.
The origin is on the lawn where the reference photograph was taken from, looking along +z, and the sun stands ahead and to the
right, so the trees throw their shade back across the path. Sizes are a park's: a path 3 m wide, a bench 1.8 m long with
its seat 45 cm up, hedges 1.2 to 1.6 m, trees 9 to 16 m, and towers 120 to 230 m tall half a kilometre away."""
import math
import random
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

sys.path.insert(0, str(Path(__file__).resolve().parent))

from grand_tourer import _number, pillow, tube

from srlocations import Backdrop, Box, Cone, Cylinder, Group, Material, Node, Plugin, Point, Prefab, Registry, Seat, Sphere, Spot, Surface, Vec3

TEXTURES = Path(__file__).resolve().parent.parent / "textures" / "park"
PATH = ((0.3, -1.5), (-0.5, 9.0), (-3.0, 18.0), (-38.0, 34.0))  # the path's middle, as a Bezier curve over the lawn
WIDTH, KERB = 3.0, 0.09  # of the path, and of the stone edge on each side
SUN = (40.0, 50.0)  # azimuth from +z toward +x, and elevation, in degrees: what the location's rig is set to
LENGTH = 48.0  # of the path along its middle, near enough, for its bricks to keep their size
TILE = 1.2  # metres one picture of bricks covers

SHADERS = {
    "paving.brick": (Material("#fff1e6", 0.88, maps={"baseColorMap": str(TEXTURES / "pavers.png")},
                              extra={"uvScaleX": round(LENGTH / TILE, 2), "uvScaleY": round(WIDTH / TILE, 2)}),
                     ["stone", "textured"], "Warm brick pavers in running bond, laid along a path"),
    "kerb.stone": (Material("#bdb2a5", 0.8), ["stone"], "Pale stone path edging"),
    "grass.lawn": (Material("#ffffff", 0.95, maps={"baseColorMap": str(TEXTURES / "grass.png")},
                            extra={"uvScaleX": 150, "uvScaleY": 150}), ["plant", "textured"], "Mown lawn in summer"),
    "leaf.sun": (Material("#c4e07a", 0.8, maps={"baseColorMap": str(TEXTURES / "leaves.png")}, extra={"uvScaleX": 6, "uvScaleY": 4}),
                 ["plant", "textured"], "Broadleaf canopy where the sun comes through"),
    "leaf.shade": (Material("#5e8a45", 0.85, maps={"baseColorMap": str(TEXTURES / "leaves.png")}, extra={"uvScaleX": 6, "uvScaleY": 4}),
                   ["plant", "textured"], "Broadleaf canopy on its shaded side"),
    "leaf.hedge": (Material("#a6d266", 0.85, maps={"baseColorMap": str(TEXTURES / "leaves.png")}, extra={"uvScaleX": 4, "uvScaleY": 8}),
                   ["plant", "textured"], "A clipped hedge of small bright leaves"),
    "leaf.far": (Material("#6f9a5c", 0.95, maps={"baseColorMap": str(TEXTURES / "leaves.png")}, extra={"uvScaleX": 10, "uvScaleY": 6}), ["plant", "haze"], "Trees across the park, softened by distance"),
    "leaf.haze": (Material("#6f8f7a", 1.0), ["plant", "haze"], "A tree line far off, blue with air"),
    "bark.trunk": (Material("#3d342c", 0.95), ["wood"], "Dark grey-brown bark"),
    "wood.bench": (Material("#b8682f", 0.5, extra={"clearcoat": 0.4, "clearcoatRoughness": 0.4}), ["wood"],
                   "Varnished hardwood slats"),
    "iron.bench": (Material("#24282a", 0.45, 0.7), ["metal"], "Black cast iron"),
    "glass.tower": (Material("#e6eef7", 0.25, 0.35, maps={"baseColorMap": str(TEXTURES / "glass.png")}), ["glass", "textured"],
                    "Blue curtain-wall glass, pale with distance"),
    "glass.tower.dark": (Material("#bccbdc", 0.25, 0.35, maps={"baseColorMap": str(TEXTURES / "glass.png")}), ["glass", "textured"],
                         "A darker curtain wall, pale with distance"),
    "cloud": (Material("#f6f8fa", 1.0, extra={"unlit": True}), ["sky"], "A summer cloud"),
    # The night: the same pavers after rain, under a clear coat of water, and the lamps that light them
    "paving.wet": (Material("#8a786b", 0.85, maps={"baseColorMap": str(TEXTURES / "pavers.png")},
                            extra={"uvScaleX": round(LENGTH / TILE, 2), "uvScaleY": round(WIDTH / TILE, 2), "clearcoat": 1.0,
                                   "clearcoatRoughness": 0.04}),
                   ["stone", "textured", "wet"], "Brick pavers after rain, dark and glossy"),
    "kerb.wet": (Material("#8f877e", 0.45, extra={"clearcoat": 1.0, "clearcoatRoughness": 0.05}), ["stone", "wet"],
                 "Pale stone path edging, wet"),
    "iron.lamp": (Material("#1c2321", 0.45, 0.75), ["metal"], "Dark green-black painted iron, for lamp posts"),
    "glow.lantern": (Material("#fff6e6", 0.35, glow="#ffd9a0", glow_strength=6.0), ["light"], "A lit lantern's frosted glass"),
    "glow.bollard": (Material("#fff6e6", 0.35, glow="#ffe4bd", glow_strength=4.0), ["light"], "A lit path light's diffuser"),
    "steel.bollard": (Material("#7d8588", 0.45, 0.6), ["metal"], "Brushed steel, for low path lights"),
    "glass.unlit": (Material("#4a4740", 0.3), ["glass"], "Frosted glass with the light inside it off"),
    "grass.night": (Material("#5d6a66", 0.95, maps={"baseColorMap": str(TEXTURES / "grass.png")},
                             extra={"uvScaleX": 150, "uvScaleY": 150}), ["plant", "textured"], "Mown lawn at night, its green gone grey"),
    "leaf.night": (Material("#4f6a55", 0.85, maps={"baseColorMap": str(TEXTURES / "leaves.png")}, extra={"uvScaleX": 6, "uvScaleY": 4}),
                   ["plant", "textured"], "Broadleaf canopy at night, where a lamp can reach it"),
    "leaf.night.shade": (Material("#2a3a30", 0.9, maps={"baseColorMap": str(TEXTURES / "leaves.png")},
                                  extra={"uvScaleX": 6, "uvScaleY": 4}), ["plant", "textured"], "Broadleaf canopy at night, inside"),
    "mist.night": (Material("#4a6090", 1.0, opacity=0.2, maps={"baseColorMap": str(TEXTURES / "mist.png")}, extra={"unlit": True}),
                   ["sky", "haze", "textured"],
                   "A thin blue night mist, one card of a bank"),
    "haze.lamp": (Material("#ffc98f", 1.0, opacity=0.55, maps={"baseColorMap": str(TEXTURES / "haze.png")}, extra={"unlit": True}),
                  ["light", "haze", "textured"], "A street lamp's warm light caught in the mist around its pool"),
}
SLOTS = {"slats": "studio.wood.bench", "iron": "studio.iron.bench", "paving": "studio.paving.brick", "lawn": "studio.grass.lawn"}


def point(u: float) -> tuple[float, float]:
    """The path's middle at u, from 0 behind the camera to 1 at its far end."""
    s = 1 - u
    weights = (s * s * s, 3 * u * s * s, 3 * u * u * s, u * u * u)
    return (sum(w * p[0] for w, p in zip(weights, PATH)), sum(w * p[1] for w, p in zip(weights, PATH)))


def heading(u: float) -> float:
    """Which way the path runs at u, as a yaw."""
    s = 1 - u
    dx, dz = (3 * (s * s * (b[i] - a[i]) + 2 * u * s * (c[i] - b[i]) + u * u * (d[i] - c[i])) for i in (0, 1) for a, b, c, d in [PATH])
    return math.degrees(math.atan2(dx, dz))


def beside(u: float, offset: float) -> tuple[float, float]:
    """A point `offset` metres right of the path's middle, looking along it."""
    x, z = point(u)
    turn = math.radians(heading(u))
    return x + offset * math.cos(turn), z - offset * math.sin(turn)


def _bezier(i: int) -> str:
    weights = ("(1-u)*(1-u)*(1-u)", "3*u*(1-u)*(1-u)", "3*u*u*(1-u)", "u*u*u")
    return "+".join(f"{w}*{_number(p[i])}" for w, p in zip(weights, PATH))


def _slope(i: int) -> str:
    a, b, c, d = (p[i] for p in PATH)
    return f"(3*((1-u)*(1-u)*{_number(b - a)}+2*u*(1-u)*{_number(c - b)}+u*u*{_number(d - c)}))"


def sweep(across: str, rise: str, material: str, u: tuple[float, float] = (0, 1), v: tuple[float, float] = (0, 1),
          samples: Sequence[int] = (160, 4), inward: bool = False, **place) -> Surface:
    """A surface that follows the path: `across` is metres right of its middle and `rise` metres up, both in u along the
    path and v around the section."""
    length = f"sqrt({_slope(0)}*{_slope(0)}+{_slope(1)}*{_slope(1)})"
    x = f"{_bezier(0)}+({across})*{_slope(1)}/{length}"
    z = f"{_bezier(1)}-({across})*{_slope(0)}/{length}"
    return Surface(x, rise, z, u=u, v=v, samples=samples, material=material, inward=inward, **place)


def ribbon(left: float, right: float, y: float, material: str, **place) -> Surface:
    """A strip lying along the path, from `left` to `right` metres either side of its middle."""
    return sweep("v", _number(y), material, v=(left, right), inward=True, **place)


@dataclass
class Bench(Prefab):
    """A park bench with wooden slats on two cast-iron ends. It faces -z, as a stock chair does, and seats three."""
    length: float = 1.8
    slats: str = "studio.wood.bench"
    iron: str = "studio.iron.bench"

    def seats(self) -> Sequence[Seat]:
        return [Seat(Vec3(x, 0, 0.13), 180.0, 0.45, 0.36, 0.1) for x in (-0.58, 0.0, 0.58)]

    def build(self) -> Sequence[Node]:
        half = self.length / 2
        parts: list[Node] = [Box((self.length, 0.032, 0.07), at=(0, 0.435, z), material=self.slats, name=f"seat-{i}")
                             for i, z in enumerate((-0.2, -0.115, -0.03, 0.055, 0.14))]
        back = [Box((self.length, 0.085, 0.026), at=(0, y, 0), material=self.slats, name=f"back-{i}")
                for i, y in enumerate((0.1, 0.2, 0.3, 0.4))]
        parts.append(Group(back, at=(0, 0.47, 0.215), pitch=-7, name="back"))
        for side, x in (("left", -half + 0.1), ("right", half - 0.1)):
            end = [tube(((0, 0.0, -0.27), (0, 0.2, -0.27), (0, 0.4, -0.22)), 0.022, self.iron, samples=(16, 8)),
                   tube(((0, 0.0, 0.3), (0, 0.25, 0.25), (0, 0.42, 0.2)), 0.022, self.iron, samples=(16, 8)),
                   tube(((0, 0.42, 0.2), (0, 0.66, 0.26), (0, 0.87, 0.31)), 0.02, self.iron, samples=(16, 8)),
                   tube(((0, 0.42, -0.23), (0, 0.66, -0.3), (0, 0.63, 0.1), (0, 0.68, 0.24)), 0.019, self.iron, samples=(24, 8)),
                   Box((0.045, 0.04, 0.46), at=(0, 0.4, -0.02), material=self.iron)]
            parts.append(Group(end, at=(x, 0, 0), name=f"{side}-end"))
        parts.append(Box((self.length - 0.2, 0.035, 0.03), at=(0, 0.39, 0.16), material=self.iron, name="rail"))
        return parts


@dataclass
class Tree(Prefab):
    """A broadleaf tree: a leaning trunk, a few limbs, and a crown of leafy masses, lighter on the side the sun is on."""
    height: float = 12.0
    spread: float = 3.5
    lean: float = 0.4
    clumps: int = 30
    seed: int = 0
    sunlit: str = "studio.leaf.sun"
    shaded: str = "studio.leaf.shade"
    yields = True

    def build(self) -> Sequence[Node]:
        rng = random.Random(self.seed)
        h, r = self.height, self.spread
        turn = rng.uniform(0, 360)
        lx, lz = self.lean * math.sin(math.radians(turn)), self.lean * math.cos(math.radians(turn))
        fork = (lx, h * 0.42, lz)
        parts: list[Node] = [tube(((0, -0.2, 0), (lx * 0.3, h * 0.2, lz * 0.3), fork), 0.06 * r ** 0.5 + 0.07, "studio.bark.trunk",
                                  samples=(20, 10), name="trunk")]
        middle = (lx * 1.3, h * 0.66, lz * 1.3)
        for limb in range(4):
            angle = math.radians(turn + limb * 90 + rng.uniform(-30, 30))
            tip = (middle[0] + math.sin(angle) * r * 0.6, h * rng.uniform(0.6, 0.75), middle[2] + math.cos(angle) * r * 0.6)
            parts.append(tube((fork, ((fork[0] + tip[0]) / 2, (fork[1] + tip[1]) / 2 + 0.6, (fork[2] + tip[2]) / 2), tip),
                              0.09 * r ** 0.5, "studio.bark.trunk", samples=(16, 8), name="limb"))
        sun = (math.sin(math.radians(SUN[0])) * math.cos(math.radians(SUN[1])), math.sin(math.radians(SUN[1])),
               math.cos(math.radians(SUN[0])) * math.cos(math.radians(SUN[1])))
        low = h * 0.3  # where the crown begins
        centre, tall = (middle[0], (low + h) / 2, middle[2]), (h - low) / 2
        parts.append(pillow((r * 1.3, tall * 1.2, r * 1.3), self.shaded, square=0.9, samples=(24, 14), at=centre, casts_shadow=False, name="crown"))
        for clump in range(self.clumps):  # over the surface of the crown, so few are hidden inside it
            around, up = rng.uniform(0, 2 * math.pi), math.asin(rng.uniform(-0.6, 1.0))
            depth = rng.uniform(0.7, 1.0)
            dx, dy, dz = math.cos(up) * math.sin(around) * depth, math.sin(up) * depth, math.cos(up) * math.cos(around) * depth
            size = r * rng.uniform(0.26, 0.42)
            facing = dx * sun[0] + dy * sun[1] + dz * sun[2]
            parts.append(pillow((size * 1.2, size * rng.uniform(0.6, 0.8), size), self.sunlit if facing > -0.1 else self.shaded,
                                square=0.85, samples=(18, 12), at=(centre[0] + dx * r, centre[1] + dy * tall, centre[2] + dz * r),
                                yaw=rng.uniform(0, 360), name="crown"))
        return parts


@dataclass
class StreetLamp(Prefab):
    """A generic post-top park lantern: an iron post, a frosted glass lantern under a cap, and the light inside it. Its optic
    throws the light forward, as a path lantern's does: a spot centred `throw` metres ahead of the post along +z, `cone`
    degrees wide, and a dimmer glow all round. `lit=False` is the same lamp switched off, glass and all, so a picture of it
    on and one of it off differ by its light alone."""
    height: float = 3.6  # to the top of the cap
    candela: float = 1100.0
    glow: float = 120.0  # candela of the light all round, on the post, the leaves above and the ground at its foot
    throw: float = 5.5
    cone: float = 60.0
    softness: float = 1.0  # of the beam's edge, 0 hard to 1 fading from its middle, so the pool has no rim
    reach: float = 22.0
    lit: bool = True

    def build(self) -> Sequence[Node]:
        h, iron = self.height, "studio.iron.lamp"
        glass = "studio.glow.lantern" if self.lit else "studio.glass.unlit"
        middle = h - 0.42  # of the lantern
        parts: list[Node] = [Cylinder(0.13, 0.36, at=(0, 0.18, 0), material=iron, segments=16, name="base"),
                             Cylinder(0.055, h - 0.9, at=(0, 0.36 + (h - 0.9) / 2, 0), material=iron, segments=16, casts_shadow=False,
                                      name="post"),
                             Cylinder(0.09, 0.08, at=(0, h - 0.68, 0), material=iron, segments=16, casts_shadow=False, name="collar"),
                             Cylinder(0.15, 0.4, at=(0, middle, 0), material=glass, segments=16, casts_shadow=False, name="lantern"),
                             Cone(0.24, 0.18, at=(0, h - 0.12, 0), material=iron, casts_shadow=False, name="cap"),
                             Sphere(0.035, at=(0, h - 0.0, 0), material=iron, casts_shadow=False, name="finial")]
        if self.lit:
            down = math.degrees(math.atan2(middle, self.throw))
            parts += [Spot(self.candela, at=(0, middle, 0), pitch=-down, cone=self.cone, color="#ffd29a", reach=self.reach,
                           shadows=True, softness=self.softness, name="lamp"),
                      Point(self.glow, at=(0, middle, 0), color="#ffd29a", reach=self.reach, name="glow")]
        return parts


@dataclass
class Bollard(Prefab):
    """A low path light: a steel post with a ring of light near its top. `lit=False` is it switched off."""
    height: float = 0.8
    candela: float = 4.0
    reach: float = 5.0
    lit: bool = True

    def build(self) -> Sequence[Node]:
        h, iron = self.height, "studio.steel.bollard"
        parts: list[Node] = [Cylinder(0.075, h - 0.17, at=(0, (h - 0.17) / 2, 0), material=iron, segments=16, name="post"),
                             Cylinder(0.07, 0.12, at=(0, h - 0.11, 0), material="studio.glow.bollard" if self.lit else "studio.glass.unlit",
                                      segments=16, casts_shadow=False, name="diffuser"),
                             Cylinder(0.085, 0.05, at=(0, h - 0.025, 0), material=iron, segments=16, name="cap")]
        if self.lit:
            parts.append(Point(self.candela, at=(0, h - 0.11, 0), color="#ffe0b0", reach=self.reach, name="light"))
        return parts


@dataclass
class Mist(Prefab):
    """A bank of thin night mist: `cards` see-through sheets facing -z, with no body, the first `near` metres along +z and each `step`
    further, so what is far off goes lower in contrast and bluer. Stand it where a shot looks from, turned the way it looks."""
    near: float = 6.0
    step: float = 2.5
    cards: int = 12
    width: float = 160.0
    height: float = 5.0
    material: str = "studio.mist.night"

    def build(self) -> Sequence[Node]:
        return [Backdrop(self.width, self.height, at=(0, self.height / 2, self.near + i * self.step), material=self.material,
                         name=f"mist-{i}") for i in range(self.cards)]


@dataclass
class Haze(Prefab):
    """The street lamp's light caught in the mist around its pool: `cards` see-through warm sheets facing -z, with no body,
    standing on the ground `step` metres apart, clear at their edges and at the ground. It is part of the lamp's light, so a
    picture with the lamp switched off leaves it out. Stand it behind the pool, turned the way the shot looks."""
    width: float = 9.0
    height: float = 4.5
    cards: int = 2
    step: float = 1.5
    material: str = "studio.haze.lamp"

    def build(self) -> Sequence[Node]:
        return [Backdrop(self.width, self.height, at=(0, self.height / 2, i * self.step), material=self.material,
                         name=f"haze-{i}") for i in range(self.cards)]


@dataclass
class Park(Prefab):
    """The whole park, set around the path. `night` is the same park after rain at night: the path and its kerbs
    wet, the leaves and lawn in night colours, and no clouds, which are lit by nothing but themselves."""
    seed: int = 3
    night: bool = False

    def ground(self) -> list[Node]:
        paving, kerb = ("studio.paving.wet", "studio.kerb.wet") if self.night else ("studio.paving.brick", "studio.kerb.stone")
        lawn = "studio.grass.night" if self.night else "studio.grass.lawn"
        return [Box((320, 0.1, 320), at=(0, -0.05, 60), material=lawn, name="lawn"),
                ribbon(-WIDTH / 2, WIDTH / 2, 0.012, paving, name="path"),
                ribbon(-WIDTH / 2 - KERB, -WIDTH / 2, 0.02, kerb, name="kerb-left"),
                ribbon(WIDTH / 2, WIDTH / 2 + KERB, 0.02, kerb, name="kerb-right")]

    def hedge(self) -> list[Node]:
        """A clipped bank along the path's right, behind the bench, highest nearest the camera, with a few lumps on top."""
        rng = random.Random(self.seed + 1)
        # In short sections, because a body's hull is convex and one bank round the bend would take in the lawn inside it
        parts: list[Node] = [sweep("3.9+1.2*u+1.3*cos(180*v)", "(1.3-0.5*u)*pow(sin(180*v),0.45)", "studio.leaf.hedge",
                                   u=(start / 40, (start + 1) / 40), samples=(8, 14), name="hedge") for start in range(11)]
        u = 0.0
        while u < 0.27:
            x, z = beside(u, 3.9 + 1.2 * u + rng.uniform(-0.6, 0.6))
            size = rng.uniform(0.7, 1.2)
            parts.append(pillow((size * 1.3, size * 0.7, size), "studio.leaf.hedge", square=0.85, samples=(16, 10),
                                at=(x, 1.3 - 0.5 * u - size * 0.3, z), yaw=rng.uniform(0, 180), name="hedge"))
            u += 0.015
        x, z = beside(0.275, 4.2)
        parts.append(pillow((2.6, 2.0, 1.6), "studio.leaf.hedge", square=0.6, samples=(20, 12), at=(x, 0, z), yaw=heading(0.275),
                            name="hedge-end"))
        return parts

    def trees(self) -> list[Node]:
        rng = random.Random(self.seed + 2)
        # Big trees frame the near corners, and those toward the middle are smaller and further, which leaves the gap of sky
        # and towers the photograph has. Each is x, z, height and the radius of its crown.
        places = [(-4.6, 5.5, 13, 5.5), (-9.5, 9.0, 11, 4.4), (-5.0, 17.0, 6, 2.2), (-11.0, 22.0, 7, 3.0), (-2.6, 27.0, 7, 2.4),
                  (5.4, 3.0, 15, 6.0), (10.0, 11.0, 14, 5.2), (5.5, 15.5, 12, 4.4), (3.0, 24.0, 8, 3.0), (-16.0, 14.0, 12, 4.4),
                  (8.0, 26.0, 10, 3.6), (-7.5, 32.0, 8, 3.0), (12.0, 18.0, 13, 4.2), (-20.0, 28.0, 10, 3.6), (-14.0, 40.0, 8, 3.0),
                  (2.0, 38.0, 7, 2.6), (14.0, 34.0, 11, 4.0), (-28.0, 20.0, 13, 4.5), (-24.0, 44.0, 10, 3.6), (20.0, 26.0, 13, 4.4)]
        leaves = ("studio.leaf.night", "studio.leaf.night.shade") if self.night else ("studio.leaf.sun", "studio.leaf.shade")
        return [Tree(height, spread, rng.uniform(0.2, 0.7), 64 if z < 12 else 40, rng.randrange(1000), *leaves, at=(x, 0, z),
                     name=f"tree-{i}") for i, (x, z, height, spread) in enumerate(places)]

    def shrubs(self) -> list[Node]:
        """Round clipped bushes out on the lawns, and a second bench far down the path."""
        rng = random.Random(self.seed + 3)
        parts: list[Node] = []
        for along, off, size in ((0.45, -4.5, 1.6), (0.48, -6.0, 1.3), (0.75, -5.0, 1.8), (0.62, 5.5, 1.2), (0.9, 4.5, 2.2),
                                 (0.95, -6.5, 1.6), (0.8, 7.5, 1.4)):
            x, z = beside(along, off)
            parts.append(pillow((size * rng.uniform(1.1, 1.5), size, size * 1.2), "studio.leaf.hedge", square=0.85, samples=(20, 12),
                                at=(x, size * 0.4, z), yaw=rng.uniform(0, 180), name="shrub"))
        x, z = beside(0.72, -2.2)
        parts.append(Bench(at=(x, 0, z), yaw=heading(0.72) - 90, name="far-bench"))
        return parts

    def distance(self) -> list[Node]:
        """A tree line across the park, a fainter one beyond it, the towers and two clouds."""
        rng = random.Random(self.seed + 4)
        parts: list[Node] = []
        for ring, (radius, low, high, material) in enumerate(((62, 5, 13, "studio.leaf.far"), (110, 8, 16, "studio.leaf.haze"))):
            for step in range(150):  # all the way round, so a shot can look any way
                angle = math.radians(step * 2.4 + rng.uniform(-1, 1))
                size, far = rng.uniform(low, high), radius + rng.uniform(-6, 6)
                parts.append(pillow((size * rng.uniform(0.9, 1.5), size, size), material, square=0.9, samples=(14, 8), casts_shadow=False,
                                    at=(far * math.sin(angle), size * rng.uniform(0.25, 0.55), 20 + far * math.cos(angle)),
                                    name=f"tree-line-{ring}"))
        for x, z, wide, tall, glass in ((-150, 470, 38, 230, "studio.glass.tower"), (-100, 520, 46, 175, "studio.glass.tower.dark"),
                                        (-45, 560, 42, 150, "studio.glass.tower"), (10, 540, 34, 190, "studio.glass.tower.dark"),
                                        (55, 600, 50, 160, "studio.glass.tower"), (100, 640, 40, 175, "studio.glass.tower.dark"),
                                        (-20, 700, 40, 120, "studio.glass.tower.dark"), (-200, 640, 50, 140, "studio.glass.tower.dark"),
                                        (140, 700, 36, 125, "studio.glass.tower")):
            parts.append(Box((wide, tall, wide * 0.9), at=(x, tall / 2, z), yaw=rng.uniform(-10, 10), material=glass,
                             casts_shadow=False, name="tower"))
        for x, y, z, size in () if self.night else ((-150, 230, 900, 90), (-100, 250, 900, 120), (-40, 235, 900, 100), (-70, 285, 900, 80),
                              (10, 215, 900, 70), (-190, 215, 900, 60)):  # one cumulus, in puffs
            parts.append(pillow((size * 1.4, size * 0.75, size * 0.6), "studio.cloud", square=0.95, samples=(24, 12), casts_shadow=False,
                                at=(x, y, z), name="cloud"))
        return parts

    def build(self) -> Sequence[Node]:
        x, z = beside(0.15, 1.9)
        bench = Bench(at=(x, 0, z), yaw=heading(0.15) + 105, name="bench")
        return [*self.ground(), *self.hedge(), *self.trees(), *self.shrubs(), *self.distance(), bench]


class ParkPlugin(Plugin):
    name = "park"
    version = "1.0.0"
    requires = ("stock",)
    shaders, slots = SHADERS, SLOTS

    def register(self, registry: Registry) -> None:
        registry.prefabs.add("park.bench", Bench)
        registry.prefabs.add("park.tree", Tree)
        registry.prefabs.add("park.park", Park)
        registry.prefabs.add("park.lamp", StreetLamp)
        registry.prefabs.add("park.bollard", Bollard)
        registry.prefabs.add("park.mist", Mist)
        registry.prefabs.add("park.haze", Haze)
