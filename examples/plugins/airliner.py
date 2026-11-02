"""A single-aisle airliner's cabin, three seats either side of the aisle. publish_catalog.py freezes it, so a project uses it
without this file. The cabin runs along z with its nose toward +z, the seats face the nose, and the origin is on the floor
in the aisle, level with the first row's cushions. Sizes are a narrow-body's: 3.7 m wide, seats 44 cm wide
and rows 84 cm apart, with a 54 cm aisle. The curved walls are arcs of one circle, so a wall panel is written in angle around it."""
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

sys.path.insert(0, str(Path(__file__).resolve().parent))

from grand_tourer import _number, _soft, pillow, sheet, tube

from srlocations import Box, Cylinder, Group, Material, Node, Plugin, Point, Prefab, Registry, Spot, Surface

RADIUS, CENTRE = 1.86, 1.0  # of the fuselage's inside, and how high its centre is above the floor
PITCH = 0.84  # from one row to the next
BAY = 2 * PITCH  # an overhead bin spans two rows
AISLE, PLACE = 0.27, 0.49  # half the aisle, and the width of a seat with its armrest
LOW, HIGH, TOP = -20.0, 20.0, 25.0  # degrees around the wall: the top of the dado, of the window panels and of the lit band
DADO = 1.72  # where the low, nearly upright wall meets the floor, which leaves a window seat room for its feet
SOFFIT = (1.67, 1.79)  # where the wall meets the underside of the bins
LIP = (0.86, 1.66)  # the bins' lower edge, above the middle seat
CROWN = (0.52, 2.19)  # the bins' top edge
SPINE = 0.24, 2.3  # half the width and the height of the centre of the ceiling
DOOR = (LIP, (0.89, 1.92), (0.72, 2.16), CROWN)  # the curve of a bin door
FOLD = 0.3  # how far along it the door breaks

SHADERS = {
    "fabric.petrol": (Material("#173f58", 0.74, extra={"sheenColor": "#4c86a8", "sheenRoughness": 0.6}),
                      ["fabric"], "Blue-green seat cloth"),
    "plastic.charcoal": (Material("#26282c", 0.42), ["plastic"], "Dark grey moulded seat shell"),
    "plastic.cabin": (Material("#efe6d6", 0.5, extra={"doubleSided": True}), ["plastic"], "Warm white cabin wall"),
    "plastic.bin": (Material("#55686e", 0.3, extra={"doubleSided": True}), ["plastic"], "Blue-grey overhead bin"),
    "plastic.door": (Material("#7d8d8f", 0.3, extra={"doubleSided": True}), ["plastic"], "Paler lower edge of a bin"),
    "plastic.reveal": (Material("#aeb6bb", 0.45, extra={"doubleSided": True}), ["plastic"], "Cool grey window surround"),
    "plastic.soffit": (Material("#a6aaa8", 0.24, extra={"doubleSided": True}), ["plastic"], "Pale glossy panel under the bins"),
    "carpet.navy": (Material("#1b2a4c", 0.92), ["fabric"], "Dense navy aisle carpet"),
    "curtain.rust": (Material("#7e3517", 0.8, extra={"doubleSided": True}), ["fabric"], "Rust curtain"),
    "glow.amber": (Material("#000000", 1.0, glow="#ffb066", glow_strength=1.3, extra={"doubleSided": True}),
                   ["glow"], "Amber mood lighting"),
    "glow.wash": (Material("#000000", 1.0, glow="#eab27f", glow_strength=0.62, extra={"doubleSided": True}),
                  ["glow"], "Amber light washed down a wall"),
    "glow.window": (Material("#000000", 1.0, glow="#fff4e6", glow_strength=2.2, extra={"doubleSided": True}), ["glow"], "Bright sky through a window"),
    "glow.exit": (Material("#000000", 1.0, glow="#39c66b", glow_strength=2.0), ["glow"], "A green exit sign"),
}
SLOTS = {"hide": "studio.leather.cognac", "cloth": "studio.fabric.petrol", "shell": "studio.plastic.charcoal",
         "wall": "studio.plastic.cabin", "carpet": "studio.carpet.navy", "trim": "studio.metal.satin"}


def on_wall(turn: float) -> tuple[float, float]:
    """A point of the wall on the +x side, this many degrees above level, as x and y."""
    from math import cos, radians, sin
    return RADIUS * cos(radians(turn)), CENTRE + RADIUS * sin(radians(turn))


def _bow(expression: str, side: int) -> str:
    return f"{side}*({expression})" if side < 0 else expression


def _polar(side: int, radial: str, turn: str, along: str, **place) -> dict:
    """The three axes of a surface written around the fuselage."""
    return {"x": f"{side}*({radial})*cos({turn})", "y": f"{_number(CENTRE)}+({radial})*sin({turn})", "z": along, **place}


def window_panel(side: int, z: float, wall: str, reveal: str, glass: str, pale: str) -> list[Node]:
    """One row's stretch of wall: flat at its square edges, then a tall arched bay sinking back to a small window. Each
    panel fills its square, so together they make a wall with holes in it, which no box could."""
    half_along, half_up = PITCH / 2, (HIGH - LOW) / 2  # the second in degrees
    middle = (LOW + HIGH) / 2
    a, b = "cos(u)", "sin(u)"
    square = f"(1/max(abs({a}),abs({b})))"
    bay_along, bay_turn = f"0.27*{_soft(a, 0.55)}", f"8.5+10.5*{_soft(b, 0.5)}"
    hole_along, hole_turn = f"0.125*{_soft(a, 0.6)}", f"3.6+6.2*{_soft(b, 0.6)}"
    centre = _number(z)

    def between(outer: str, inner: str) -> str:
        return f"({outer})*(1-v)+({inner})*v"

    parts: list[Node] = [
        Surface(**_polar(side, _number(RADIUS), between(f"{_number(middle)}+{_number(half_up)}*{b}*{square}", bay_turn),
                         f"{centre}+{between(f'{_number(half_along)}*{a}*{square}', bay_along)}"),
                u=(0, 360), v=(0, 1), closed=(True, False), samples=(64, 3), material=wall),
        Surface(**_polar(side, f"{_number(RADIUS)}+0.1*v*v", between(bay_turn, hole_turn), f"{centre}+{between(bay_along, hole_along)}"),
                u=(0, 360), v=(0, 1), closed=(True, False), samples=(48, 8), material=reveal)]
    parts.append(Surface(**_polar(side, f"{_number(RADIUS + 0.105)}", f"3.6+6.2*{_soft(b, 0.6)}*v",
                                  f"{centre}+0.125*{_soft(a, 0.6)}*v"), u=(0, 360), v=(0, 1), closed=(True, False),
                         samples=(32, 4), material=glass, casts_shadow=False))
    parts.append(Surface(**_polar(side, f"{_number(RADIUS + 0.098)}", "7.8+2.1*v", f"{centre}+0.122*(2*u-1)"), u=(0, 1), v=(0, 1),
                         samples=(4, 4), material=pale, casts_shadow=False))
    return parts


def band(side: int, low: float, high: float, start: float, end: float, material: str) -> Surface:
    """A stretch of wall between two angles, the length of the cabin."""
    return Surface(**_polar(side, _number(RADIUS), f"{_number(low)}+{_number(high - low)}*u", f"{_number(start)}+{_number(end - start)}*v"),
                   u=(0, 1), v=(0, 1), samples=(8, 2), material=material)


def split(curve: Sequence[Sequence[float]], t: float) -> tuple[list, list]:
    """A Bezier curve cut in two at `t`, by de Casteljau, so a panel can follow part of a curve exactly."""
    rows = [list(curve)]
    while len(rows[-1]) > 1:
        rows.append([tuple(a + (b - a) * t for a, b in zip(p, q)) for p, q in zip(rows[-1], rows[-1][1:])])
    return [row[0] for row in rows], [row[-1] for row in rows][::-1]


def extruded(profile: Sequence[Sequence[float]], side: int, start: float, end: float, material: str, **place) -> Surface:
    """A curve of 2 to 4 x, y points on the +x side, run along z from `start` to `end`."""
    return sheet([[(side * x, y, start), (side * x, y, end)] for x, y in profile], material, samples=(24, 2), inward=side < 0, **place)


def ribbed(size: Sequence[float], material: str, ribs: int, **place) -> Surface:
    """A padded panel with a row of shallow horizontal pleats."""
    shape = pillow(size, material, 0.3, samples=(24, 8 * ribs), **place)
    shape.z += f"+0.0042*sin({_number(ribs * 180)}*sin(v))"
    return shape


def creased(size: Sequence[float], material: str, **place) -> Surface:
    """A headrest cover pulled in down its middle."""
    shape = pillow(size, material, 0.34, samples=(36, 20), **place)
    shape.z += f"+0.007*pow(max(0,1-abs(({shape.x})/{_number(size[0] / 2)})*5),2)*({_soft('sin(v)', 0.34)}+1)"
    return shape


@dataclass
class Row(Prefab):
    """Three seats outward from the aisle on the +x side, or the -x side with `side` -1."""
    side: int = 1
    hide: str = "studio.leather.cognac"
    cloth: str = "studio.fabric.petrol"
    shell: str = "studio.plastic.charcoal"
    trim: str = "studio.metal.satin"
    panel: str = "studio.plastic.bin"

    def seat(self, x: float) -> Node:
        hide, cloth, shell = self.hide, self.cloth, self.shell
        back: list[Node] = [
            pillow((0.44, 0.8, 0.09), shell, 0.2, taper=0.09, at=(0, 0.38, -0.015), samples=(28, 18)),
            ribbed((0.4, 0.56, 0.1), cloth, 12, taper=0.06, at=(0, 0.19, -0.033)),
            pillow((0.38, 0.68, 0.1), cloth, 0.3, taper=0.06, at=(0, 0.3, 0.03), samples=(24, 16)),
            creased((0.39, 0.28, 0.066), hide, at=(0, 0.64, -0.048)),
            pillow((0.35, 0.2, 0.06), hide, 0.34, at=(0, 0.67, 0.035), samples=(20, 12)),
        ]
        return Group([pillow((0.43, 0.1, 0.46), hide, 0.4, at=(0, 0.365, 0.03), pitch=3, samples=(28, 16)),  # the front stands higher
                      pillow((0.44, 0.08, 0.42), shell, 0.3, at=(0, 0.3, 0.02), pitch=3, samples=(20, 12)),
                      Group(back, at=(0, 0.37, -0.2), pitch=14, name="back")], at=(x, 0, 0), name="seat")

    def build(self) -> Sequence[Node]:
        side, trim, shell = self.side, self.trim, self.shell
        seats = [AISLE + PLACE * (index + 0.5) for index in range(3)]
        parts: list[Node] = [self.seat(side * x) for x in seats]
        for index in range(4):  # the armrests between and beside the seats
            x = side * (AISLE + PLACE * index)
            parts.append(pillow((0.05, 0.05, 0.4), shell, 0.35, at=(x, 0.6, -0.02), samples=(20, 12)))
            parts.append(pillow((0.058, 0.058, 0.09), trim, 0.3, at=(x, 0.6, 0.14), samples=(16, 10)))
        parts.append(pillow((0.03, 0.38, 0.44), self.panel, 0.3, at=(side * AISLE, 0.29, 0.0), samples=(16, 12)))
        for x in (seats[0] + 0.25, seats[2] - 0.25):
            parts.append(Box((0.04, 0.28, 0.5), at=(side * x, 0.14, 0.0), material=trim))
        parts.append(Box((1.4, 0.035, 0.035), at=(side * (AISLE + 0.74), 0.27, -0.12), material=trim))
        return parts


@dataclass
class Airliner(Prefab):
    rows: int = 14
    hide: str = "studio.leather.cognac"
    cloth: str = "studio.fabric.petrol"
    shell: str = "studio.plastic.charcoal"
    wall: str = "studio.plastic.cabin"
    carpet: str = "studio.carpet.navy"
    trim: str = "studio.metal.satin"

    @property
    def fore(self) -> float:
        return (self.rows - 0.4) * PITCH

    def walls(self) -> list[Node]:
        start = -2 * PITCH
        parts: list[Node] = []
        for side in (-1, 1):
            for row in range(-2, self.rows + 1):
                parts.extend(window_panel(side, row * PITCH, self.wall, "studio.plastic.reveal", "studio.glow.window", self.wall))
            parts.append(band(side, HIGH, TOP, start, self.fore, "studio.glow.wash"))
            parts.append(extruded((on_wall(LOW), (DADO, 0)), side, start, self.fore, self.wall, name="dado"))
        return parts

    def bins(self) -> list[Node]:
        parts: list[Node] = []
        bays = int((self.fore + 2 * PITCH) / BAY) + 1
        for side in (-1, 1):
            parts.append(extruded((SOFFIT, LIP), side, -2 * PITCH, self.fore, "studio.plastic.soffit"))
            parts.append(extruded([(x + 0.04, y + 0.01) for x, y in DOOR], side, -2 * PITCH, self.fore, self.shell, name="bin-gaps"))  # behind the doors
            parts.append(extruded((CROWN, (CROWN[0] - 0.12, CROWN[1] + 0.11), (SPINE[0] + 0.1, SPINE[1]), SPINE), side, -2 * PITCH, self.fore,
                                  self.wall, name="ceiling"))
            parts.append(extruded(((CROWN[0] + 0.02, CROWN[1] - 0.01), (CROWN[0] - 0.05, CROWN[1] + 0.05)), side, -2 * PITCH, self.fore,
                                  "studio.glow.amber", name="cove"))
            for bay in range(bays):
                start, end = -2 * PITCH + bay * BAY + 0.006, -2 * PITCH + (bay + 1) * BAY - 0.006
                lower, upper = split(DOOR, FOLD)
                lift = [(x + 0.012, y) for x, y in lower]
                parts.append(extruded(lift[:-1] + [(lift[-1][0], lift[-1][1] - 0.012)], side, start, end, "studio.plastic.door", name=f"lip-{side}-{bay}"))
                parts.append(extruded([(x + 0.012, y) for x, y in split(upper, 0.015)[1]], side, start, end, "studio.plastic.bin", name=f"door-{side}-{bay}"))
                middle = (start + end) / 2
                parts.append(pillow((0.018, 0.05, 0.34), self.shell, 0.3, at=(side * 0.897, 1.79, middle), samples=(14, 8)))
                parts.append(pillow((0.012, 0.018, 0.26), self.trim, 0.3, at=(side * 0.907, 1.79, middle), samples=(10, 6)))
            for row in range(self.rows):  # the air and reading lights over each row
                z = row * PITCH
                for x in (1.02, 1.42):
                    parts.append(pillow((0.26, 0.012, 0.075), self.shell, 0.5, at=(side * x, 1.665 + (x - LIP[0]) * 0.145, z), roll=side * 8, samples=(12, 6)))
        return parts

    def ceiling(self) -> list[Node]:
        trim, spine, height = self.trim, SPINE[0], SPINE[1]
        parts: list[Node] = [Box((2 * spine, 0.02, self.fore + 2 * PITCH), at=(0, height + 0.01, (self.fore - 2 * PITCH) / 2), material="studio.plastic.soffit"),
                             tube([(-spine, height - 0.01, -2 * PITCH), (-spine, height - 0.01, self.fore)], 0.012, self.shell),
                             tube([(spine, height - 0.01, -2 * PITCH), (spine, height - 0.01, self.fore)], 0.012, self.shell)]
        for x, y in ((0.31, 2.292), (0.4, 2.27)):
            for side in (-1, 1):
                parts.append(tube([(side * x, y, -2 * PITCH), (side * x, y, self.fore)], 0.004, self.shell, samples=(4, 6)))
        for index in range(int((self.fore + 2 * PITCH) / BAY) + 1):
            z = -2 * PITCH + (index + 0.5) * BAY
            parts.append(Box((2 * spine - 0.02, 0.006, 0.012), at=(0, height - 0.001, z + BAY / 2), material=self.shell))
            for x in (-0.13, 0.13):
                parts.append(Cylinder(0.042, 0.012, at=(x, height - 0.004, z), material=self.shell, segments=24))
                parts.append(Cylinder(0.026, 0.014, at=(x, height - 0.006, z), material="studio.glow.amber", segments=24))
        return parts

    def lights(self) -> list[Node]:
        parts: list[Node] = []
        for index in range(-1, self.rows + 1):  # the engine keeps 63 lights to a part of the frame, and the far end has them all
            z = index * PITCH
            for side in (-1, 1):
                parts.append(Point(0.2, color="#ffb478", at=(side * 0.42, 1.88, z), reach=2.2))
                if index % 3 == 0:
                    parts.append(Point(0.5, color="#ffd2a6", at=(side * 1.25, 1.42, z), reach=2.6))
        for index in range(0, self.rows, 4):  # what shows the backs of the seats; a catalog prop can hold no sun
            parts.append(Spot(2.2, color="#fff1e2", at=(0, 2.2, (index - 2) * PITCH), yaw=0, pitch=-30, cone=56, reach=7, name=f"wash-{index}"))
            parts.append(Point(0.7, color="#cfe0e6", at=(0, 1.3, (index - 2) * PITCH), reach=3.2, name=f"aisle-{index}"))  # all a bin's face sees
        return parts

    def bulkhead(self) -> list[Node]:
        z, door = self.fore, 0.36
        wall, shell = self.wall, self.shell
        parts: list[Node] = [
            Box((1.8, 2.4, 0.06), at=(-(door + 0.9), 1.2, z + 0.06), material=wall),
            Box((1.8, 2.4, 0.06), at=(door + 0.9, 1.2, z + 0.06), material=wall),
            Box((2 * door, 0.42, 0.06), at=(0, 2.11, z + 0.06), material=wall),
            Box((0.3, 0.06, 0.01), at=(0, 2.03, z + 0.024), material="studio.glow.exit"),
            Box((0.07, 1.9, 0.09), at=(-door - 0.02, 0.95, z + 0.05), material=self.trim),
            Box((0.07, 1.9, 0.09), at=(door + 0.02, 0.95, z + 0.05), material=self.trim),
            Box((2 * door, 0.03, 1.5), at=(0, 0.0, z + 0.8), material=self.carpet),
            Box((2 * door + 0.4, 2.4, 0.04), at=(0, 1.2, z + 1.55), material=self.shell),
            Box((2 * door, 2.4, 0.03), at=(0, 1.2, z + 1.5), material="studio.plastic.soffit"),
        ]
        for y in (0.45, 0.85, 1.25, 1.65):  # the galley's shelves, seen through the door
            parts.append(Box((0.62, 0.02, 0.32), at=(0, y, z + 1.3), material=self.trim))
        for side in (-1, 1):
            parts.append(Surface(f"{side}*(0.4+0.42*u)", f"2.25*v", f"{_number(z - 0.04)}+0.035*sin(u*1260)", u=(0, 1), v=(0, 1),
                                 samples=(96, 2), material="studio.curtain.rust", name=f"curtain-{side}"))
            parts.append(Box((0.26, 0.2, 0.012), at=(side * 1.08, 1.42, z + 0.024), material="studio.plastic.soffit"))
            for x in (-0.05, 0.05):
                parts.append(Box((0.07, 0.11, 0.004), at=(side * 1.08 + x, 1.42, z + 0.016), material=shell))
        return parts

    def build(self) -> Sequence[Node]:
        parts: list[Node] = [Box((3.7, 0.1, self.fore + 2 * PITCH + 1), at=(0, -0.05, (self.fore - 2 * PITCH + 1) / 2), material=self.carpet, name="floor"),
                             Box((3.8, 2.5, 0.06), at=(0, 1.2, -2 * PITCH - 0.03), material=self.wall, name="aft-wall"),
                             *self.walls(), *self.bins(), *self.ceiling(), *self.bulkhead(), *self.lights()]
        for row in range(self.rows):
            for side in (-1, 1):
                parts.append(Group(Row(side, self.hide, self.cloth, self.shell, self.trim).build(), at=(0, 0, row * PITCH), name=f"row-{row}-{side}"))
        return parts


class AirlinerPlugin(Plugin):
    name = "airliner"
    version = "1.0.0"
    requires = ("stock",)
    shaders, slots = SHADERS, SLOTS

    def register(self, registry: Registry) -> None:
        registry.prefabs.add("air.cabin", Airliner)
