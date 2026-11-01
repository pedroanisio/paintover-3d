"""A grand tourer's cabin and a mountain overlook to park it at. Everything soft is a Surface built by the shape helpers
below; publish_catalog.py freezes both props, so a project uses them without this file. The car is left-hand drive, faces
+z, and has its origin on the cabin floor between the front seats. Its right door stands open."""
import math
import random
from dataclasses import dataclass
from typing import Optional, Sequence

from srlocations import Box, Cone, Cylinder, Group, Material, Node, Plugin, Prefab, Registry, Sphere, Surface

Point3 = Sequence[float]

SHADERS = {
    "leather.cognac": (Material("#b0581f", 0.44, extra={"sheenColor": "#e0a070", "sheenRoughness": 0.5}),
                       ["leather"], "Saddle-tan hide with a soft sheen"),
    "leather.spruce": (Material("#25322e", 0.34, extra={"clearcoat": 0.25, "clearcoatRoughness": 0.4}),
                       ["leather"], "Dark green-black hide for a dashboard top"),
    "leather.ink": (Material("#141518", 0.5), ["leather"], "Black hide"),
    "veneer.ebony": (Material("#1b0f0a", 0.3, extra={"clearcoat": 1, "clearcoatRoughness": 0.03}),
                     ["wood", "glossy"], "Dark open-grain veneer under deep lacquer"),
    "piano.black": (Material("#08090b", 0.25, extra={"clearcoat": 1, "clearcoatRoughness": 0.02}),
                    ["glossy"], "Black lacquer for a console"),
    "metal.satin": (Material("#d8d4cb", 0.2, 1.0), ["metal"], "Knurled-bright chrome trim"),
    "metal.champagne": (Material("#c9a877", 0.28, 1.0), ["metal"], "Warm gold-toned alloy"),
    "paint.garnet": (Material("#7d0d12", 0.3, 0.5, extra={"clearcoat": 1, "clearcoatRoughness": 0.04, "doubleSided": True}),
                     ["paint", "glossy"], "Deep red paint under a hard clear coat"),
    "mirror.glass": (Material("#ffffff", 0.02, 1.0), ["metal", "glossy"], "A true mirror"),
    "carpet.ink": (Material("#17171a", 0.95, extra={"doubleSided": True}), ["fabric"], "Dense black carpet"),
    "headliner.tan": (Material("#6d5a46", 0.9, extra={"doubleSided": True}), ["fabric"], "Soft tan roof lining"),
    "stitch.linen": (Material("#d9bd98", 0.7), ["thread"], "Pale contrast stitching"),
    "gauge.face": (Material("#05070a", 0.2, glow="#8fc0d0", glow_strength=0.5), ["glow"], "Softly lit instrument face"),
    "conifer.dark": (Material("#141c16", 0.95), ["plant"], "Dark conifer"),
    "hillside.dusk": (Material("#26302a", 1.0), ["ground"], "Shadowed hillside"),
    "haze.near": (Material("#000000", 1.0, glow="#8c9f93", glow_strength=1.0), ["backdrop", "glow"], "Nearest ridge, in haze"),
    "haze.mid": (Material("#000000", 1.0, glow="#aab8ad", glow_strength=1.0), ["backdrop", "glow"], "Middle ridge, in haze"),
    "haze.far": (Material("#000000", 1.0, glow="#c5cec2", glow_strength=1.0), ["backdrop", "glow"], "Far ridge, in haze"),
    "haze.valley": (Material("#000000", 1.0, glow="#d3c8b0", glow_strength=1.0), ["backdrop", "glow"], "Valley floor, in haze"),
}
SLOTS = {"hide": "studio.leather.cognac", "dash": "studio.leather.spruce", "shell": "studio.leather.ink",
         "veneer": "studio.veneer.ebony", "trim": "studio.metal.satin", "paint": "studio.paint.garnet"}


def _number(value: float) -> str:
    return f"{value:.5g}"


def _soft(term: str, power: float) -> str:
    return f"(sign({term})*pow(abs({term}),{_number(power)}))"


def pillow(size: Point3, material: str, square: float = 0.45, taper: float = 0.0, lean: float = 0.0, bow: float = 0.0,
           sag: float = 0.0, samples: Sequence[int] = (56, 36), **place) -> Surface:
    """A stuffed shape of this width, height and depth. `square` runs from 1, an egg, toward 0, a box. `taper` narrows
    its top, `lean` slides its top along z, `bow` curves it along z across x and `sag` curves it down across x."""
    a, b, c = (s / 2 for s in size)
    across, up, deep = (f"{_soft('cos(v)', square)}*{_soft('cos(u)', square)}", _soft("sin(v)", square),
                        f"{_soft('cos(v)', square)}*{_soft('sin(u)', square)}")
    x = f"{_number(a)}*{across}" + (f"*(1-{_number(taper)}*{up})" if taper else "")
    y = f"{_number(b)}*{up}" + (f"-{_number(sag)}*pow({across},2)" if sag else "")
    z = f"{_number(c)}*{deep}"
    if lean:
        z += f"+{_number(lean)}*{up}"
    if bow:
        z += f"+{_number(bow)}*pow({across},2)"
    return Surface(x, y, z, u=(0, 360), v=(-90, 90), closed=(True, False), samples=samples, material=material, **place)


def _bezier(points: Sequence[float], t: str = "u") -> str:
    """One coordinate of a Bezier curve of 2 to 4 points."""
    s = f"(1-{t})"
    weights = {2: (s, t), 3: (f"{s}*{s}", f"2*{t}*{s}", f"{t}*{t}"),
               4: (f"{s}*{s}*{s}", f"3*{t}*{s}*{s}", f"3*{t}*{t}*{s}", f"{t}*{t}*{t}")}[len(points)]
    return "+".join(f"{_number(p)}*{w}" for p, w in zip(points, weights))


def tube(points: Sequence[Point3], radius: float, material: str, flat: float = 1.0, samples: Sequence[int] = (32, 12),
         **place) -> Surface:
    """A rod along a Bezier curve, its ends rounded shut. `flat` squashes it across the plane it is bent in."""
    chord = [q - p for p, q in zip(points[0], points[-1])]
    length = math.sqrt(sum(c * c for c in chord)) or 1.0
    d = [c / length for c in chord]
    side = (d[2], 0.0, -d[0]) if abs(d[1]) < 0.95 else (1.0, 0.0, 0.0)
    norm = math.sqrt(sum(c * c for c in side))
    side = [c / norm for c in side]
    lift = (d[1] * side[2] - d[2] * side[1], d[2] * side[0] - d[0] * side[2], d[0] * side[1] - d[1] * side[0])
    round_end = "pow(abs(sin(180*u)),0.12)"
    axes = [f"{_bezier([p[i] for p in points])}+{round_end}*({_number(radius * side[i])}*cos(v)"
            f"+{_number(radius * flat * lift[i])}*sin(v))" for i in range(3)]
    return Surface(*axes, u=(0, 1), v=(0, 360), closed=(False, True), samples=samples, material=material, **place)


def ring(radius: float, thickness: float, material: str, arc: Sequence[float] = (0, 360), samples: Sequence[int] = (96, 14),
         **place) -> Surface:
    """A hoop in the x-y plane, or a length of one."""
    whole = arc[1] - arc[0] >= 360
    r, t = _number(radius), _number(thickness / 2)
    return Surface(f"({r}+{t}*cos(v))*cos(u)", f"({r}+{t}*cos(v))*sin(u)", f"{t}*sin(v)", u=tuple(arc), v=(0, 360),
                   closed=(whole, True), samples=samples, material=material, **place)


def sheet(rows: Sequence[Sequence[Point3]], material: str, samples: Sequence[int] = (40, 40), **place) -> Surface:
    """A panel through a grid of 2 to 4 by 2 to 4 control points, one sided in the shell of the car."""
    def axis(i: int) -> str:
        return _bezier_of([[point[i] for point in row] for row in rows])
    return Surface(axis(0), axis(1), axis(2), u=(0, 1), v=(0, 1), samples=samples, material=material, **place)


def _bezier_of(grid: Sequence[Sequence[float]]) -> str:
    s = "(1-v)"
    weights = {2: (s, "v"), 3: (f"{s}*{s}", f"2*v*{s}", "v*v"),
               4: (f"{s}*{s}*{s}", f"3*v*{s}*{s}", f"3*v*v*{s}", "v*v*v")}[len(grid)]
    return "+".join(f"({_bezier(row)})*{w}" for row, w in zip(grid, weights))


@dataclass
class Cabin(Prefab):
    """The interior, with enough body round it to stand in daylight."""
    hide: str = "studio.leather.cognac"
    dash: str = "studio.leather.spruce"
    shell: str = "studio.leather.ink"
    veneer: str = "studio.veneer.ebony"
    trim: str = "studio.metal.satin"
    paint: str = "studio.paint.garnet"

    def build(self) -> Sequence[Node]:
        return [*self.body(), Group(self.seat(-1), at=(-0.37, -0.16, 0.05), name="driver-seat"),
                Group(self.seat(1), at=(0.37, -0.16, 0.05), name="passenger-seat"), *self.rear(), *self.console(),
                *self.dashboard(), *self.left_door(), Group(self.wheel(), at=(-0.37, 0.69, 0.36), pitch=-20, name="wheel"),
                *self.right_door()]

    def seat(self, side: int) -> list[Node]:
        """`side` is -1 for the driver's: the switches are always on the outside."""
        hide, shell = self.hide, self.shell
        parts: list[Node] = [
            pillow((0.55, 0.2, 0.52), shell, 0.28, at=(0, 0.21, 0.02)),
            pillow((0.47, 0.11, 0.5), hide, 0.42, at=(0, 0.35, 0.03), pitch=-5),
            pillow((0.12, 0.12, 0.48), hide, 0.5, at=(-0.2, 0.37, 0.03), pitch=-5),
            pillow((0.12, 0.12, 0.48), hide, 0.5, at=(0.2, 0.37, 0.03), pitch=-5),
            tube([(-0.135, 0.408, -0.18), (-0.135, 0.418, 0.0), (-0.135, 0.416, 0.16), (-0.135, 0.388, 0.27)], 0.0028, "studio.stitch.linen"),
            tube([(0.135, 0.408, -0.18), (0.135, 0.418, 0.0), (0.135, 0.416, 0.16), (0.135, 0.388, 0.27)], 0.0028, "studio.stitch.linen"),
            pillow((0.016, 0.13, 0.34), self.trim, 0.3, at=(side * 0.279, 0.23, 0.08)),
            pillow((0.018, 0.09, 0.13), "studio.piano.black", 0.3, at=(side * 0.282, 0.23, 0.0)),
            pillow((0.018, 0.09, 0.13), "studio.piano.black", 0.3, at=(side * 0.282, 0.23, 0.16)),
        ]
        back: list[Node] = [
            pillow((0.5, 0.86, 0.12), shell, 0.5, 0.3, at=(0, 0.42, -0.085)),
            pillow((0.28, 0.6, 0.12), hide, 0.42, 0.14, at=(0, 0.31, -0.01)),
            pillow((0.21, 0.7, 0.16), hide, 0.6, 0.24, lean=-0.02, at=(-0.125, 0.35, 0.02), roll=-3),
            pillow((0.21, 0.7, 0.16), hide, 0.6, 0.24, lean=-0.02, at=(0.125, 0.35, 0.02), roll=3),
            pillow((0.34, 0.24, 0.15), hide, 0.55, 0.3, at=(0, 0.73, 0.0)),
            pillow((0.05, 0.84, 0.04), shell, 0.4, 0.2, at=(0, 0.42, 0.082)),
            tube([(0, 0.03, 0.107), (0, 0.42, 0.112), (0, 0.82, 0.078)], 0.0055, self.trim),
            tube([(side * 0.12, 0.05, 0.102), (side * 0.11, 0.36, 0.108), (side * 0.09, 0.62, 0.09)], 0.0024, "studio.stitch.linen"),
            tube([(-side * 0.12, 0.05, 0.102), (-side * 0.11, 0.36, 0.108), (-side * 0.09, 0.62, 0.09)], 0.0024, "studio.stitch.linen"),
        ]
        parts.append(Group(back, at=(0, 0.33, -0.22), pitch=19, name="back"))
        return parts

    def rear(self) -> list[Node]:
        hide = self.hide
        return [pillow((0.52, 0.2, 0.5), hide, 0.4, at=(-0.42, 0.21, -1.15), pitch=-6),
                pillow((0.52, 0.2, 0.5), hide, 0.4, at=(0.42, 0.21, -1.15), pitch=-6),
                pillow((0.52, 0.62, 0.16), hide, 0.45, 0.1, at=(-0.42, 0.59, -1.32), pitch=16),
                pillow((0.52, 0.62, 0.16), hide, 0.45, 0.1, at=(0.42, 0.59, -1.32), pitch=16),
                pillow((0.26, 0.4, 0.75), self.shell, 0.35, at=(0, 0.2, -1.08)),
                pillow((0.02, 0.2, 0.56), hide, 0.3, at=(0.13, 0.23, -1.06)),
                tube([(0.142, 0.345, -1.34), (0.145, 0.348, -1.06), (0.142, 0.345, -0.78)], 0.004, self.trim),
                pillow((0.1, 0.56, 1.0), hide, 0.4, at=(-0.74, 0.34, -1.05)),
                pillow((0.1, 0.24, 0.72), self.shell, 0.3, at=(0.8, 0.12, -1.12)),
                tube([(0.76, 0.242, -1.45), (0.75, 0.245, -1.1), (0.76, 0.24, -0.76)], 0.005, self.trim)]

    def console(self) -> list[Node]:
        trim, lacquer = self.trim, "studio.piano.black"
        parts: list[Node] = [
            pillow((0.3, 0.42, 1.25), "studio.carpet.ink", 0.25, at=(0, 0.2, 0.02)),
            pillow((0.24, 0.11, 0.42), self.shell, 0.45, at=(0, 0.43, -0.37), pitch=2),
            pillow((0.25, 0.04, 0.64), lacquer, 0.2, at=(0, 0.44, 0.17), pitch=8),
            tube([(-0.127, 0.41, -0.15), (-0.127, 0.45, 0.17), (-0.127, 0.5, 0.49)], 0.006, trim),
            tube([(0.127, 0.41, -0.15), (0.127, 0.45, 0.17), (0.127, 0.5, 0.49)], 0.006, trim),
            pillow((0.15, 0.012, 0.2), trim, 0.15, at=(0, 0.435, -0.04), pitch=8),
            pillow((0.14, 0.014, 0.19), lacquer, 0.15, at=(0, 0.44, -0.04), pitch=8),
            Cylinder(0.03, 0.03, at=(0.045, 0.465, 0.13), pitch=8, material=trim, segments=48),
            Cylinder(0.022, 0.03, at=(-0.045, 0.465, 0.13), pitch=8, material=trim, segments=48),
            pillow((0.036, 0.09, 0.05), trim, 0.5, 0.25, at=(0, 0.5, 0.25), pitch=8),
            pillow((0.024, 0.03, 0.036), self.hide, 0.5, at=(0, 0.555, 0.247), pitch=8),
            pillow((0.3, 0.3, 0.05), lacquer, 0.2, at=(0, 0.6, 0.53), pitch=-16),
            pillow((0.02, 0.26, 0.86), self.hide, 0.3, at=(0.158, 0.2, 0.1), name="tunnel-right"),
            pillow((0.02, 0.26, 0.86), self.hide, 0.3, at=(-0.158, 0.2, 0.1), name="tunnel-left"),
            tube([(0.17, 0.335, -0.32), (0.172, 0.335, 0.1), (0.17, 0.335, 0.52)], 0.004, trim),
            tube([(-0.17, 0.335, -0.32), (-0.172, 0.335, 0.1), (-0.17, 0.335, 0.52)], 0.004, trim),
            tube([(-0.155, 0.5, 0.49), (-0.158, 0.61, 0.525), (-0.155, 0.72, 0.56)], 0.007, trim),
            tube([(0.155, 0.5, 0.49), (0.158, 0.61, 0.525), (0.155, 0.72, 0.56)], 0.007, trim),
        ]
        for index, x in enumerate((-0.09, 0.0, 0.09)):
            parts.append(ring(0.036, 0.008, trim, at=(x, 0.56, 0.486), pitch=-16, name=f"dial-{index}"))
            parts.append(Cylinder(0.034, 0.012, at=(x, 0.56, 0.491), pitch=74, material=lacquer, segments=48))
            parts.append(Cylinder(0.02, 0.018, at=(x, 0.56, 0.48), pitch=74, material=trim, segments=32))
        for row, z in enumerate((0.07, 0.3, 0.36)):  # the rows of switches either side of the selector
            for side in (-1, 1):
                for x in (0.05, 0.08):
                    parts.append(Cylinder(0.009, 0.012, at=(side * x, 0.455 + (z - 0.17) * 0.14, z), pitch=8, material=trim, segments=20))
        for row in range(2):
            for column in range(6):
                parts.append(pillow((0.024, 0.012, 0.012), trim if (row + column) % 3 else lacquer, 0.3,
                                    at=(-0.1 + column * 0.04, 0.71 - row * 0.022, 0.536 + row * 0.006), pitch=-16, samples=(16, 10)))
        return parts

    def dashboard(self) -> list[Node]:
        dash, veneer, trim = self.dash, self.veneer, self.trim
        parts: list[Node] = [
            pillow((1.62, 0.2, 0.6), dash, 0.38, at=(0, 0.74, 0.86), bow=-0.1, sag=0.02, samples=(96, 40)),
            pillow((1.62, 0.26, 0.28), self.shell, 0.3, at=(0, 0.55, 0.72), bow=-0.1, sag=0.01, samples=(96, 36)),
            pillow((1.6, 0.095, 0.03), veneer, 0.25, at=(0, 0.655, 0.585), bow=-0.1, sag=0.01, samples=(96, 20)),
            tube([(-0.8, 0.699, 0.495), (-0.25, 0.701, 0.6), (0.25, 0.701, 0.6), (0.8, 0.699, 0.495)], 0.005, trim),
            tube([(-0.08, 0.612, 0.585), (0.25, 0.612, 0.585), (0.5, 0.612, 0.56), (0.8, 0.612, 0.49)], 0.0035, trim),
            pillow((0.5, 0.2, 0.05), self.shell, 0.2, at=(0.48, 0.48, 0.59), bow=-0.03, sag=0.015),
            tube([(0.24, 0.585, 0.585), (0.4, 0.595, 0.58), (0.55, 0.595, 0.555), (0.78, 0.57, 0.485)], 0.005, trim),
            pillow((0.07, 0.018, 0.02), trim, 0.4, at=(0.5, 0.52, 0.565)),
            pillow((0.3, 0.18, 0.1), self.hide, 0.45, at=(-0.36, 0.46, 0.72), pitch=-20),
            pillow((0.38, 0.11, 0.2), self.shell, 0.5, at=(-0.37, 0.75, 0.56), pitch=6),
            pillow((0.32, 0.1, 0.012), "studio.gauge.face", 0.25, at=(-0.37, 0.72, 0.452), pitch=-6),
        ]
        for x in (-0.46, -0.28):
            parts.append(ring(0.042, 0.007, trim, at=(x, 0.72, 0.444), pitch=-6))
        parts.append(pillow((0.1, 0.09, 0.016), trim, 0.3, at=(-0.385, 0.2, 1.0), pitch=-58, name="brake"))
        parts.append(pillow((0.06, 0.2, 0.016), trim, 0.3, at=(-0.27, 0.07, 0.89), pitch=-58, name="throttle"))
        for x, z in ((0.25, 0.552), (0.36, 0.542), (0.47, 0.522)):  # three clocks along the veneer
            parts.append(ring(0.034, 0.008, trim, at=(x, 0.655, z - 0.008)))
            parts.append(Cylinder(0.032, 0.006, at=(x, 0.655, z - 0.008), pitch=90, material="studio.gauge.face", segments=48))
        for x in (-0.72, 0.72):
            parts.append(ring(0.038, 0.009, trim, at=(x, 0.655, 0.51)))
            parts.append(Cylinder(0.036, 0.01, at=(x, 0.655, 0.515), pitch=90, material="studio.piano.black", segments=48))
        return parts

    def left_door(self) -> list[Node]:
        hide, veneer, trim = self.hide, self.veneer, self.trim
        return [pillow((0.08, 0.34, 1.12), hide, 0.42, at=(-0.82, 0.36, 0.0), bow=0.0),
                pillow((0.1, 0.05, 0.62), hide, 0.5, at=(-0.77, 0.47, -0.1)),
                pillow((0.05, 0.12, 1.14), self.shell, 0.3, at=(-0.82, 0.64, 0.0)),
                pillow((0.05, 0.05, 1.12), veneer, 0.25, at=(-0.79, 0.61, 0.0)),
                pillow((0.05, 0.05, 1.12), veneer, 0.25, at=(-0.8, 0.68, 0.0)),
                tube([(-0.77, 0.645, -0.55), (-0.76, 0.645, 0.0), (-0.77, 0.645, 0.55)], 0.0035, trim),
                pillow((0.02, 0.05, 0.2), "studio.piano.black", 0.3, at=(-0.78, 0.55, 0.2)),
                tube([(-0.765, 0.545, 0.12), (-0.755, 0.56, 0.2), (-0.765, 0.555, 0.29)], 0.007, trim),
                pillow((0.32, 0.19, 0.13), self.paint, 0.55, at=(-1.08, 0.88, 0.5), yaw=-8, name="mirror"),
                pillow((0.285, 0.155, 0.012), "studio.mirror.glass", 0.45, at=(-1.08, 0.88, 0.435), yaw=-8),
                tube([(-0.8, 0.76, 0.44), (-0.9, 0.78, 0.47), (-0.98, 0.82, 0.5)], 0.016, self.paint)]

    def right_door(self) -> list[Node]:
        return [pillow((0.09, 0.1, 1.3), self.shell, 0.3, at=(0.88, 0.07, -0.05)),
                tube([(0.83, 0.125, -0.65), (0.83, 0.125, 0.55)], 0.006, self.trim),
                pillow((0.34, 0.02, 0.44), self.hide, 0.3, at=(0.38, 0.02, 0.62), pitch=2)]

    def wheel(self) -> list[Node]:
        trim, hide, shell = "studio.metal.champagne", self.hide, self.shell
        parts: list[Node] = [
            ring(0.2, 0.036, shell, arc=(155, 215)),
            ring(0.2, 0.036, shell, arc=(325, 385)),
            ring(0.2, 0.038, hide, arc=(25, 155)),
            ring(0.2, 0.038, hide, arc=(215, 325)),
            Sphere(0.072, at=(0, 0, 0.015), material=trim),
            Cylinder(0.058, 0.02, at=(0, 0, -0.042), pitch=90, material=hide, segments=48),
            pillow((0.38, 0.045, 0.02), trim, 0.5, at=(0, 0.004, -0.005)),
            pillow((0.3, 0.018, 0.012), self.hide, 0.5, at=(0, -0.022, -0.012)),
            pillow((0.05, 0.2, 0.02), trim, 0.5, at=(0, -0.1, -0.005)),
            tube([(0, 0, 0.04), (0, 0, 0.32)], 0.032, shell),
        ]
        return parts

    def body(self) -> list[Node]:
        paint, lining, carpet = self.paint, "studio.headliner.tan", "studio.carpet.ink"
        roof_left, roof_right = -0.74, 0.74
        return [
            Box((1.8, 0.1, 3.0), at=(0, -0.05, -0.2), material=carpet, name="floor"),
            sheet([[(roof_left, 1.08, -1.45), (roof_left, 1.15, -0.3), (roof_left, 1.12, 0.25)],
                   [(0, 1.3, -1.45), (0, 1.3, -0.3), (0, 1.27, 0.3)],
                   [(roof_right, 1.08, -1.45), (roof_right, 1.15, -0.3), (roof_right, 1.12, 0.25)]], lining, name="lining"),
            tube([(-0.84, 0.74, 0.86), (-0.76, 0.97, 0.56), (-0.7, 1.17, 0.2)], 0.03, self.shell, name="left-a-pillar"),
            tube([(0.84, 0.74, 0.86), (0.76, 0.97, 0.56), (0.7, 1.17, 0.2)], 0.03, self.shell, name="right-a-pillar"),
            tube([(-0.7, 1.17, 0.2), (-0.72, 1.19, -0.6), (-0.75, 1.04, -1.3)], 0.03, self.shell, name="left-rail"),
            tube([(0.7, 1.17, 0.2), (0.72, 1.19, -0.6), (0.75, 1.04, -1.3)], 0.03, self.shell, name="right-rail"),
            tube([(-0.7, 1.19, 0.24), (0.0, 1.24, 0.32), (0.7, 1.19, 0.24)], 0.03, self.shell, flat=0.5, name="header"),
            pillow((0.06, 0.05, 0.2), self.shell, 0.4, at=(0, 1.18, 0.26), name="mirror-stalk"),
            pillow((0.24, 0.065, 0.025), self.shell, 0.5, at=(0, 1.12, 0.27), pitch=-8, name="rear-view"),
            pillow((0.3, 0.018, 0.16), lining, 0.4, at=(-0.36, 1.19, 0.22), pitch=8, name="left-visor"),
            pillow((0.3, 0.018, 0.16), lining, 0.4, at=(0.36, 1.19, 0.22), pitch=8, name="right-visor"),
            sheet([[(0.92, 0.74, 0.86), (0.9, 0.68, 2.7)], [(0, 0.88, 0.86), (0, 0.8, 2.7)], [(-0.92, 0.74, 0.86), (-0.9, 0.68, 2.7)]],
                  paint, name="bonnet"),
            Box((1.76, 0.82, 0.04), at=(0, 0.41, 1.12), material=carpet, name="firewall"),
            Box((0.04, 0.72, 0.64), at=(-0.84, 0.36, 0.82), material=carpet, name="left-kick"),
            Box((0.04, 0.72, 0.64), at=(0.84, 0.36, 0.82), material=carpet, name="right-kick"),
            sheet([[(-0.86, 0.005, 0.56), (-0.86, 0.005, 1.1)], [(-0.16, 0.005, 0.56), (-0.16, 0.005, 1.1)]], carpet, name="left-toe"),
            pillow((0.04, 0.34, 2.2), paint, 0.2, at=(-0.9, 0.36, -0.3), name="left-flank"),
            tube([(-0.92, 0.74, 0.86), (-0.96, 0.58, 1.6), (-0.92, 0.5, 2.7)], 0.05, paint, name="left-wing"),
            tube([(0.92, 0.74, 0.86), (0.96, 0.58, 1.6), (0.92, 0.5, 2.7)], 0.05, paint, name="right-wing"),
            sheet([[(-0.8, 0.0, -1.45), (-0.8, 1.13, -1.45)], [(0.8, 0.0, -1.45), (0.8, 1.13, -1.45)]], self.shell, name="back-wall"),
        ]


def _ridge(radius: float, base: float, crest: float, swell: float, material: str, seed: int) -> list[Node]:
    """A range of hills all round the car, cut in sectors so that none of their boxes contains a camera. `crest` is its
    mean height and `swell` how far it rises and falls from that. The waves wrap, so the range closes behind the car."""
    rng = random.Random(seed)
    waves = [(rng.randint(2, 4), rng.uniform(0, 360), 0.5), (rng.randint(5, 8), rng.uniform(0, 360), 0.28),
             (rng.randint(11, 15), rng.uniform(0, 360), 0.14), (rng.randint(27, 33), rng.uniform(0, 360), 0.06)]
    height = "+".join(f"{_number(k * swell)}*sin({f}*u+{_number(p)})" for f, p, k in waves)
    y = f"{_number(base)}+v*({_number(crest - base)}+{height})"
    sectors = []
    for index in range(12):
        sectors.append(Surface(f"{_number(radius)}*cos(u)", y, f"{_number(radius)}*sin(u)", u=(index * 30, index * 30 + 30),
                               v=(0, 1), samples=(96, 2), material=material, casts_shadow=False, inward=True, name=f"ridge-{seed}"))
    return sectors


@dataclass
class Overlook(Prefab):
    """A pull-off high on a mountain road. The hills are one flat colour each, thinner with distance as air makes them."""
    seed: int = 11

    def build(self) -> Sequence[Node]:
        rng = random.Random(self.seed)
        parts: list[Node] = [Box((9, 1, 12), at=(0, -0.62, 0), material="stock.asphalt", name="pull-off"),
                             Box((14000, 1, 14000), at=(0, -420, 0), material="studio.haze.valley", casts_shadow=False, name="valley"),
                             *_ridge(4600, -420, 280, 200, "studio.haze.far", 3),
                             *_ridge(3000, -420, 110, 130, "studio.haze.mid", 5),
                             *_ridge(1700, -420, 10, 80, "studio.haze.near", 8),
                             sheet([[(-300, -420, -300), (-300, -420, 300)], [(-4.5, -1.1, -6), (-4.5, -1.1, 6)]], "studio.hillside.dusk"),
                             sheet([[(4.5, -1.1, -6), (4.5, -1.1, 6)], [(300, -420, -300), (300, -420, 300)]], "studio.hillside.dusk"),
                             sheet([[(-300, -420, 300), (300, -420, 300)], [(-4.5, -1.1, 6), (4.5, -1.1, 6)]], "studio.hillside.dusk"),
                             sheet([[(-4.5, -1.1, -6), (4.5, -1.1, -6)], [(-300, -420, -300), (300, -420, -300)]], "studio.hillside.dusk"),
                             pillow((560, 40, 170), "studio.hillside.dusk", 0.8, at=(-105, -23, 205), samples=(64, 28), casts_shadow=False, name="tree-shelf"),
                             pillow((170, 40, 90), "studio.conifer.dark", 0.9, at=(-190, -17, 150), samples=(64, 28), casts_shadow=False, name="forest-hill")]
        for index in range(150):  # conifers along a crest far ahead
            x, z = rng.uniform(-300, 90), rng.uniform(170, 240)
            height = rng.uniform(9, 16)
            parts.append(Cone(height * 0.22, height, at=(x, rng.uniform(-5, -1) + height / 2, z), material="studio.conifer.dark", segments=10))
        for x, y, z, r in ((-15, -3, -4.5, 2.2), (-15, -6, -5, 2.6), (-16, -1, -5, 2), (-15, -8, -3.5, 2.4), (-16, -4, -3, 2),
                           (-15, -1.5, -6, 1.8)):  # a tree just below the road, behind the car
            parts.append(Sphere(r, at=(x, y, z), material="studio.conifer.dark", segments=24))
        return parts


class GrandTourer(Plugin):
    name = "grand-tourer"
    version = "1.0.0"
    requires = ("stock",)
    shaders, slots = SHADERS, SLOTS

    def register(self, registry: Registry) -> None:
        registry.prefabs.add("gt.cabin", Cabin)
        registry.prefabs.add("gt.overlook", Overlook)
