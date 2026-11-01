"""Stock prefabs. Each is a dataclass: its fields are its parameters, and a name in the registry makes it data-drivable."""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Optional, Sequence

from srlocations.nodes import Box, Cone, Cylinder, Node, Point, Prefab, Sphere

WALL = 0.15


@dataclass(frozen=True)
class Opening:
    """A hole in a wall: `center` along it, from its middle, `bottom` to `top` above the floor."""
    center: float
    width: float = 1.0
    bottom: float = 0.0
    top: float = 2.1


def door(center: float) -> Opening:
    return Opening(center, 0.95, 0.0, 2.1)


def window(center: float, width: float = 1.4) -> Opening:
    return Opening(center, width, 0.9, 2.2)


@dataclass
class Wall(Prefab):
    """A straight wall along local x, cut around its openings; glazed where an opening starts above the floor."""
    length: float = 4.0
    height: float = 2.8
    openings: Sequence[Opening] = ()
    material: str = "stock.plaster.white"
    thickness: float = WALL

    def build(self) -> Sequence[Node]:
        parts: list[Node] = []
        def piece(x0: float, x1: float, y0: float, y1: float) -> None:
            if x1 - x0 > 1e-6 and y1 - y0 > 1e-6:
                parts.append(Box(size=(x1 - x0, y1 - y0, self.thickness), at=((x0 + x1) / 2, (y0 + y1) / 2, 0),
                                 material=self.material))
        cursor = -self.length / 2
        for hole in sorted(self.openings, key=lambda o: o.center):
            left, right = hole.center - hole.width / 2, hole.center + hole.width / 2
            piece(cursor, left, 0, self.height)
            piece(left, right, 0, hole.bottom)
            piece(left, right, hole.top, self.height)
            if hole.bottom > 0:
                parts.append(Box(size=(hole.width, hole.top - hole.bottom, 0.02), material="stock.glass.window",
                                 at=(hole.center, (hole.bottom + hole.top) / 2, 0), casts_shadow=False))
            cursor = right
        piece(cursor, self.length / 2, 0, self.height)
        return parts


@dataclass
class Room(Prefab):
    """Floor, ceiling and four walls; the origin is the floor's centre, the inside runs x +-width/2, z +-depth/2."""
    width: float = 6.0
    depth: float = 5.0
    height: float = 2.8
    floor: str = "stock.wood.oak"
    walls: str = "stock.plaster.white"
    ceiling: Optional[str] = "stock.plaster.white"
    north: Sequence[Opening] = ()
    south: Sequence[Opening] = ()
    east: Sequence[Opening] = ()
    west: Sequence[Opening] = ()

    def build(self) -> Sequence[Node]:
        w, d, h = self.width, self.depth, self.height
        slab = 0.1
        parts: list[Node] = [
            Box(size=(w + 2 * WALL, slab, d + 2 * WALL), at=(0, -slab / 2, 0), material=self.floor, name="floor"),
            Wall(w + 2 * WALL, h, self.north, self.walls, at=(0, 0, d / 2 + WALL / 2), name="north"),
            Wall(w + 2 * WALL, h, self.south, self.walls, at=(0, 0, -d / 2 - WALL / 2), name="south"),
            Wall(d, h, self.east, self.walls, at=(w / 2 + WALL / 2, 0, 0), yaw=90, name="east"),
            Wall(d, h, self.west, self.walls, at=(-w / 2 - WALL / 2, 0, 0), yaw=90, name="west"),
        ]
        if self.ceiling:
            parts.append(Box(size=(w + 2 * WALL, slab, d + 2 * WALL), at=(0, h + slab / 2, 0), material=self.ceiling,
                             name="ceiling"))
        return parts


@dataclass
class Table(Prefab):
    width: float = 1.4
    depth: float = 0.8
    height: float = 0.75
    top: str = "stock.wood.walnut"
    legs: str = "stock.metal.black"

    def build(self) -> Sequence[Node]:
        x, z, t = self.width / 2 - 0.06, self.depth / 2 - 0.06, 0.04
        parts: list[Node] = [Box(size=(self.width, t, self.depth), at=(0, self.height - t / 2, 0), material=self.top)]
        for sx, sz in ((-1, -1), (-1, 1), (1, -1), (1, 1)):
            parts.append(Box(size=(0.05, self.height - t, 0.05), at=(sx * x, (self.height - t) / 2, sz * z),
                             material=self.legs))
        return parts


@dataclass
class Chair(Prefab):
    """Faces -z, the way a seat at the +z side of a table does."""
    frame: str = "stock.wood.oak"
    seat: str = "stock.fabric.teal"

    def build(self) -> Sequence[Node]:
        parts: list[Node] = [Box(size=(0.44, 0.06, 0.44), at=(0, 0.46, 0), material=self.seat),
                             Box(size=(0.44, 0.45, 0.04), at=(0, 0.72, 0.2), material=self.frame)]
        for sx, sz in ((-1, -1), (-1, 1), (1, -1), (1, 1)):
            parts.append(Box(size=(0.04, 0.44, 0.04), at=(sx * 0.19, 0.22, sz * 0.19), material=self.frame))
        return parts


@dataclass
class Sofa(Prefab):
    width: float = 2.0
    fabric: str = "stock.fabric.rust"

    def build(self) -> Sequence[Node]:
        w = self.width
        return [Box(size=(w, 0.3, 0.9), at=(0, 0.3, 0), material=self.fabric),
                Box(size=(w, 0.45, 0.22), at=(0, 0.62, 0.34), material=self.fabric),
                Box(size=(0.2, 0.3, 0.9), at=(-w / 2 + 0.1, 0.55, 0), material=self.fabric),
                Box(size=(0.2, 0.3, 0.9), at=(w / 2 - 0.1, 0.55, 0), material=self.fabric)]


@dataclass
class Bookshelf(Prefab):
    """Back against +z. Book colours come from `seed`, so a shelf is the same every time."""
    width: float = 1.6
    height: float = 2.1
    shelves: int = 5
    wood: str = "stock.wood.walnut"
    seed: int = 1

    def build(self) -> Sequence[Node]:
        rng = random.Random(self.seed)
        depth, step = 0.32, self.height / self.shelves
        spines = ["stock.fabric.rust", "stock.fabric.teal", "stock.paint.blue", "stock.paint.red", "stock.paint.yellow",
                  "stock.plaster.cream"]
        parts: list[Node] = [Box(size=(self.width, self.height, 0.02), at=(0, self.height / 2, depth / 2),
                                 material=self.wood)]
        for side in (-1, 1):
            parts.append(Box(size=(0.03, self.height, depth), at=(side * self.width / 2, self.height / 2, 0),
                             material=self.wood))
        for level in range(self.shelves + 1):
            parts.append(Box(size=(self.width, 0.03, depth), at=(0, level * step + 0.015, 0), material=self.wood))
            if level == self.shelves:
                break
            x = -self.width / 2 + 0.05
            while x < self.width / 2 - 0.15:
                thick, tall = rng.uniform(0.03, 0.07), step * rng.uniform(0.55, 0.85)
                if rng.random() > 0.12:
                    parts.append(Box(size=(thick, tall, 0.2), at=(x + thick / 2, level * step + 0.03 + tall / 2, 0),
                                     material=rng.choice(spines), casts_shadow=False))
                x += thick + 0.004
        return parts


@dataclass
class Rug(Prefab):
    width: float = 2.4
    depth: float = 1.7
    material: str = "stock.fabric.teal"

    def build(self) -> Sequence[Node]:
        return [Box(size=(self.width, 0.012, self.depth), at=(0, 0.006, 0), material=self.material, casts_shadow=False)]


@dataclass
class FloorLamp(Prefab):
    """Carries its own light."""
    height: float = 1.7
    candela: float = 7.0

    def build(self) -> Sequence[Node]:
        h = self.height
        return [Cylinder(0.14, 0.03, at=(0, 0.015, 0), material="stock.metal.brass"),
                Cylinder(0.012, h, at=(0, h / 2, 0), material="stock.metal.brass", segments=12),
                Cone(0.2, 0.26, at=(0, h - 0.02, 0), material="stock.glow.warm", casts_shadow=False),
                Point(self.candela, at=(0, h - 0.1, 0), color="#ffc98a", reach=9.0, name="lamp")]


@dataclass
class PendantLamp(Prefab):
    """Hangs from the ceiling at height `ceiling`; `at` is its point on the floor."""
    ceiling: float = 2.8
    drop: float = 0.8
    candela: float = 6.0

    def build(self) -> Sequence[Node]:
        low = self.ceiling - self.drop
        return [Cylinder(0.006, self.drop, at=(0, low + self.drop / 2, 0), material="stock.metal.black", segments=8),
                Cone(0.2, 0.2, at=(0, low + 0.04, 0), material="stock.metal.black"),
                Sphere(0.06, at=(0, low - 0.04, 0), material="stock.glow.warm", casts_shadow=False),
                Point(self.candela, at=(0, low - 0.1, 0), color="#ffd29a", reach=7.0, name="bulb")]


@dataclass
class Plant(Prefab):
    def build(self) -> Sequence[Node]:
        return [Cylinder(0.16, 0.3, at=(0, 0.15, 0), material="stock.plaster.cream"),
                Sphere(0.3, at=(0, 0.62, 0), material="stock.leaf.green"),
                Sphere(0.2, at=(0.14, 0.86, 0.05), material="stock.leaf.green"),
                Sphere(0.17, at=(-0.13, 0.84, -0.06), material="stock.leaf.green")]


@dataclass
class Tree(Prefab):
    height: float = 5.0
    spread: float = 1.5
    seed: int = 0

    def build(self) -> Sequence[Node]:
        rng = random.Random(self.seed)
        trunk = self.height * 0.5
        parts: list[Node] = [Cylinder(0.14, trunk, at=(0, trunk / 2, 0), material="stock.bark.brown", segments=12)]
        for _ in range(6):
            parts.append(Sphere(self.spread * rng.uniform(0.5, 0.8), material="stock.leaf.green", segments=16,
                                at=(rng.uniform(-1, 1) * self.spread * 0.6,
                                    trunk + rng.uniform(0.2, 1) * self.height * 0.35,
                                    rng.uniform(-1, 1) * self.spread * 0.6)))
        return parts


@dataclass
class Building(Prefab):
    """A block with a grid of windows on its -z face; `lit` is the share with a light on behind them."""
    width: float = 10.0
    depth: float = 9.0
    floors: int = 5
    facade: str = "stock.brick.red"
    lit: float = 0.0
    seed: int = 0
    storey: float = 3.1

    def build(self) -> Sequence[Node]:
        rng = random.Random(self.seed)
        h = self.floors * self.storey
        parts: list[Node] = [Box(size=(self.width, h, self.depth), at=(0, h / 2, 0), material=self.facade),
                             Box(size=(self.width + 0.3, 0.3, self.depth + 0.3), at=(0, h + 0.15, 0),
                                 material="stock.concrete")]
        face = -self.depth / 2 - 0.02
        bays = max(1, int(self.width // 2.4))
        pitch = self.width / bays
        for floor in range(self.floors):
            for bay in range(bays):
                glow = rng.random() < self.lit
                parts.append(Box(size=(1.3, 1.7, 0.06), at=(-self.width / 2 + pitch * (bay + 0.5),
                                                            self.storey * (floor + 0.55), face),
                                 material="stock.glow.window" if glow else "stock.glass.dark", casts_shadow=False))
        return parts


@dataclass
class StreetLamp(Prefab):
    height: float = 5.0
    candela: float = 60.0

    def build(self) -> Sequence[Node]:
        h = self.height
        return [Cylinder(0.07, h, at=(0, h / 2, 0), material="stock.metal.black", segments=12),
                Box(size=(0.08, 0.06, 1.0), at=(0, h, 0.5), material="stock.metal.black"),
                Box(size=(0.2, 0.08, 0.4), at=(0, h - 0.06, 0.8), material="stock.glow.warm", casts_shadow=False),
                Point(self.candela, at=(0, h - 0.25, 0.8), color="#ffcf96", reach=20.0, name="lamp")]


@dataclass
class Car(Prefab):
    paint: str = "stock.paint.blue"

    def build(self) -> Sequence[Node]:
        parts: list[Node] = [Box(size=(1.8, 0.55, 4.2), at=(0, 0.6, 0), material=self.paint),
                             Box(size=(1.55, 0.5, 2.1), at=(0, 1.1, -0.1), material="stock.glass.dark")]
        for sx, sz in ((-1, -1), (-1, 1), (1, -1), (1, 1)):
            parts.append(Cylinder(0.33, 0.24, at=(sx * 0.85, 0.33, sz * 1.35), roll=90, material="stock.rubber"))
        return parts


PREFABS = {"wall": Wall, "room": Room, "table": Table, "chair": Chair, "sofa": Sofa, "bookshelf": Bookshelf, "rug": Rug,
           "floor-lamp": FloorLamp, "pendant-lamp": PendantLamp, "plant": Plant, "tree": Tree, "building": Building,
           "street-lamp": StreetLamp, "car": Car, "box": Box, "cylinder": Cylinder, "sphere": Sphere}
