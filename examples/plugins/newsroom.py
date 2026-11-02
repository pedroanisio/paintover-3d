"""A television news studio: a curved anchor desk of glass and wood on a lit riser, a curved video wall, a lighting grid and
a pedestal camera with its prompter. publish_catalog.py freezes it, so a project uses it without this file. The origin is on
the floor in front of the desk, which curves toward the cameras at -z, and anchors stand behind it facing them. The pictures
are drawn by news_pictures.py. Sizes are a studio's: a desk 1 m high, a riser 16 cm, a video wall 2.8 m tall 9 m away
round its curve, and a grid 5.4 m up."""
import math
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

sys.path.insert(0, str(Path(__file__).resolve().parent))

from grand_tourer import _number, tube

from srlocations import Backdrop, Box, Cylinder, Group, Material, Node, Plugin, Point, Prefab, Registry, Spot, Surface

PICTURES = Path(__file__).resolve().parent.parent / "textures" / "news"
DESK = (0.0, 2.6)  # the middle of the desk's curve, on the floor
OUTER, INNER, TOP = 3.0, 2.35, 0.98  # the desk's front and back radius, and its top
ENDS = (128.0, 232.0)  # where the desk runs round its middle, in degrees of yaw; 180 faces the cameras
RISER = 0.16
WALL, RADIUS = (0.0, -2.0), 9.0  # the video wall's curve, seen from inside


def screen(name: str, strength: float = 1.0) -> Material:
    return Material("#000000", 0.6, glow="#ffffff", glow_strength=strength, maps={"emissiveMap": str(PICTURES / f"{name}.png")})


SHADERS = {
    "floor.concrete": (Material("#ffffff", 0.32, maps={"baseColorMap": str(PICTURES / "concrete.png")}, extra={"uvScaleX": 12, "uvScaleY": 10}),
                       ["floor", "textured"], "Sealed grey studio concrete"),
    "desk.glass.clear": (Material("#eef0f2", 0.05, opacity=0.22, extra={"doubleSided": True}), ["glass"], "A clear glass desk top, untinted"),
    "desk.frost.plum": (Material("#2a1458", 0.4, glow="#2a1458", glow_strength=1.2, extra={"doubleSided": True}), ["glass", "glow"],
                        "Frosted glass lit plum from behind"),
    "desk.back": (Material("#17191e", 0.6, extra={"doubleSided": True}), ["plastic"], "The dark inside of a desk"),
    "wood.desk": (Material("#6e4227", 0.45, extra={"clearcoat": 0.5, "clearcoatRoughness": 0.3, "doubleSided": True}), ["wood"], "Lacquered walnut"),
    "glow.tangerine": (Material("#000000", 1.0, glow="#ff8a1f", glow_strength=1.5), ["glow"], "A tangerine light strip"),
    "glow.mint": (Material("#000000", 1.0, glow="#3fe0b5", glow_strength=1.6), ["glow"], "A mint light strip"),
    "glow.panel.plum": (Material("#160a30", 0.6, glow="#2a1458", glow_strength=1.4), ["glow"], "A lit plum panel"),
    "glow.lens": (Material("#000000", 1.0, glow="#fff6e8", glow_strength=6.0), ["glow"], "The lens of a lit studio lamp"),
    "riser.grey": (Material("#4a4e57", 0.5, extra={"doubleSided": True}), ["plastic"], "Grey riser deck"),
    "wall.black": (Material("#0b0c10", 0.7, extra={"doubleSided": True}), ["plastic"], "Black studio wall and ceiling"),
    "metal.gear": (Material("#22252b", 0.4, 0.6), ["metal"], "Dark broadcast hardware"),
    "metal.truss": (Material("#3a3d42", 0.45, 0.8), ["metal"], "Lighting truss"),
    "cable.black": (Material("#09090b", 0.55), ["rubber"], "Camera cable"),
    "paper.white": (Material("#f2f2ee", 0.9), ["paper"], "Script pages"),
    "lens.glass": (Material("#1a2230", 0.05, 0.3), ["glass"], "A camera lens"),
    "screen.pattern": (screen("pattern"), ["glow", "screen"], "Sweeps of tangerine and mint on plum, with nothing written"),
    "screen.wall": (screen("wall"), ["glow", "screen"], "Waves of mint dots and rings on plum, with nothing written"),
}
SLOTS = {"floor": "studio.floor.concrete", "wood": "studio.wood.desk", "frost": "studio.desk.frost.plum", "strip": "studio.glow.tangerine"}


def _around(centre: Sequence[float], radius: str) -> tuple[str, str]:
    return f"{_number(centre[0])}+({radius})*sin(u)", f"{_number(centre[1])}+({radius})*cos(u)"


def band(centre: Sequence[float], radius: float, turn: Sequence[float], rise: Sequence[float], material: str, outward: bool = False,
         pieces: int = 1, **place) -> list[Surface]:
    """Part of an upright cylinder about `centre`, from yaw `turn[0]` to `turn[1]` and from `rise[0]` to `rise[1]` up, facing
    its middle unless `outward`. In `pieces`, because a body's hull is convex and one long curve would take in what it curves
    round."""
    x, z = _around(centre, _number(radius))
    step = (turn[1] - turn[0]) / pieces
    return [Surface(x, "v", z, u=(turn[0] + i * step, turn[0] + (i + 1) * step), v=tuple(rise),
                    samples=(max(4, round(abs(step) / 3)), 2), material=material, inward=outward, **place) for i in range(pieces)]


def picture(centre: Sequence[float], radius: float, turn: Sequence[float], rise: Sequence[float], material: str, **place) -> Surface:
    """A screen on the inside of a curve, its picture across it once, left to right and top to bottom."""
    x, z = _around(centre, _number(radius))
    return Surface(x, "v", z, u=tuple(turn), v=tuple(rise), samples=(max(4, round(abs(turn[1] - turn[0]) / 2)), 2), material=material,
                   **place)


def ring(centre: Sequence[float], radii: Sequence[float], turn: Sequence[float], y: float, material: str, pieces: int = 1,
         inward: bool = True, **place) -> list[Surface]:
    """A flat part of an annulus at height `y`, facing up."""
    x, z = _around(centre, "v")
    step = (turn[1] - turn[0]) / pieces
    return [Surface(x, _number(y), z, u=(turn[0] + i * step, turn[0] + (i + 1) * step), v=tuple(radii),
                    samples=(max(4, round(abs(step) / 3)), 2), material=material, inward=inward, **place) for i in range(pieces)]


def end(centre: Sequence[float], radii: Sequence[float], turn: float, rise: Sequence[float], material: str, **place) -> Surface:
    """A flat end across a curve, along its radius."""
    s, c = math.sin(math.radians(turn)), math.cos(math.radians(turn))
    return Surface(f"{_number(centre[0])}+v*{_number(s)}", "u", f"{_number(centre[1])}+v*{_number(c)}", u=tuple(rise), v=tuple(radii),
                   samples=(2, 2), material=material, **place)


def aim(at: Sequence[float], target: Sequence[float]) -> dict:
    dx, dy, dz = (t - a for a, t in zip(at, target))
    return {"yaw": math.degrees(math.atan2(dx, dz)), "pitch": math.degrees(math.atan2(dy, math.hypot(dx, dz)))}


@dataclass
class Desk(Prefab):
    """The anchor desk and its riser: a curve of lit frosted glass between walnut ends, with tangerine strips along it and a
    glass top, on a grey deck with a mint edge."""
    wood: str = "studio.wood.desk"
    frost: str = "studio.desk.frost.plum"
    strip: str = "studio.glow.tangerine"

    def build(self) -> Sequence[Node]:
        a0, a1 = ENDS
        deck = (a0 - 10, a1 + 10)
        parts: list[Node] = [*ring(DESK, (1.2, OUTER + 0.45), deck, RISER, "studio.riser.grey", pieces=8, name="riser"),
                             *band(DESK, OUTER + 0.45, deck, (0, RISER), "studio.riser.grey", pieces=8, outward=True, name="riser-edge"),
                             *band(DESK, OUTER + 0.455, deck, (0.025, 0.05), "studio.glow.mint", pieces=8, outward=True, name="riser-light"),
                             end(DESK, (1.2, OUTER + 0.45), deck[0], (0, RISER), "studio.riser.grey", name="riser-end"),
                             end(DESK, (1.2, OUTER + 0.45), deck[1], (0, RISER), "studio.riser.grey", name="riser-end")]
        low, high = RISER + 0.04, TOP - 0.03
        panel = 13.0  # degrees of walnut at each end
        parts += band(DESK, OUTER, (a0 + panel, a1 - panel), (low, high), self.frost, pieces=8, outward=True, name="front")
        for start in (a0, a1 - panel):
            parts += band(DESK, OUTER + 0.02, (start, start + panel), (low, high), self.wood, outward=True, name="front-wood")
        for turn in range(round(a0 + panel + 13), round(a1 - panel), 13):  # the joints between the panes of glass
            parts += band(DESK, OUTER + 0.01, (turn - 0.3, turn + 0.3), (low, high), "studio.desk.back", outward=True, name="joint")
        for y in (low + 0.1, high - 0.08):
            parts += band(DESK, OUTER + 0.035, (a0, a1), (y, y + 0.03), self.strip, pieces=8, outward=True, name="strip")
        parts += band(DESK, INNER, (a0, a1), (low, high), "studio.desk.back", pieces=8, name="back")
        parts += [end(DESK, (INNER, OUTER + 0.02), turn, (low, high), self.wood, name="end") for turn in (a0, a1)]
        parts += ring(DESK, (INNER - 0.08, OUTER + 0.12), (a0 - 2, a1 + 2), TOP, "studio.desk.glass.clear", pieces=8, name="top")
        parts += band(DESK, OUTER + 0.12, (a0 - 2, a1 + 2), (TOP - 0.025, TOP), "studio.glow.mint", pieces=8, outward=True, name="top-edge")
        return parts + self.dressing()

    def dressing(self) -> list[Node]:
        """What is on the desk: a laptop, scripts and two microphones."""
        def on(turn: float, radius: float) -> tuple[float, float]:
            return DESK[0] + radius * math.sin(math.radians(turn)), DESK[1] + radius * math.cos(math.radians(turn))
        parts: list[Node] = []
        x, z = on(176, 2.62)
        parts.append(Group([Box((0.34, 0.015, 0.24), at=(0, 0.0075, 0), material="studio.metal.gear"),
                            Box((0.34, 0.23, 0.012), at=(0, 0.115, 0.13), pitch=-12, material="studio.metal.gear")],
                           at=(x, TOP, z), yaw=-4, name="laptop"))
        for turn, radius, yaw in ((196, 2.6, 18), (199, 2.75, 22), (160, 2.62, -15), (213, 2.7, 30)):
            x, z = on(turn, radius)
            parts.append(Box((0.21, 0.004, 0.297), at=(x, TOP + 0.002, z), yaw=yaw, material="studio.paper.white", name="script"))
        for turn in (169, 207):
            x, z = on(turn, 2.55)
            parts.append(Group([Cylinder(0.035, 0.02, at=(0, 0.01, 0), material="studio.metal.gear"),
                                tube(((0, 0.02, 0), (0, 0.2, 0.02), (0, 0.3, -0.12)), 0.006, "studio.metal.gear", samples=(16, 6)),
                                Cylinder(0.011, 0.06, at=(0, 0.3, -0.15), pitch=-70, material="studio.metal.gear")],
                               at=(x, TOP, z), yaw=turn - 180, name="microphone"))
        return parts


@dataclass
class PedestalCamera(Prefab):
    """A studio camera on a pedestal: a three-legged dolly, a column, the camera with its prompter hood, and a monitor on
    top. It faces +z. `prompter` False leaves the camera bare, as a jib or a second angle has it."""
    height: float = 1.35
    prompter: bool = True

    def build(self) -> Sequence[Node]:
        gear = "studio.metal.gear"
        h = self.height
        parts: list[Node] = [Cylinder(0.32, 0.12, at=(0, 0.16, 0), material=gear, name="base"),
                             Cylinder(0.06, h - 0.2, at=(0, 0.1 + (h - 0.2) / 2, 0), material=gear, name="column"),
                             Cylinder(0.1, 0.5, at=(0, 0.55, 0), material=gear, name="column")]
        for leg in range(3):
            turn = math.radians(leg * 120 + 30)
            parts.append(Box((0.08, 0.06, 0.5), at=(0.28 * math.sin(turn), 0.1, 0.28 * math.cos(turn)), yaw=math.degrees(turn), material=gear,
                             name="leg"))
            parts.append(Cylinder(0.05, 0.04, at=(0.52 * math.sin(turn), 0.05, 0.52 * math.cos(turn)), roll=90, material=gear, name="wheel"))
        parts += [tube(((0.42 * math.cos(math.radians(a)), h - 0.32, 0.42 * math.sin(math.radians(a))),
                        (0.42 * math.cos(math.radians(a + 60)), h - 0.32, 0.42 * math.sin(math.radians(a + 60))),
                        (0.42 * math.cos(math.radians(a + 120)), h - 0.32, 0.42 * math.sin(math.radians(a + 120)))),
                       0.014, gear, samples=(20, 6), name="steering-ring") for a in (0, 120, 240)]
        head = [Box((0.24, 0.26, 0.46), at=(0, 0.13, -0.04), material=gear, name="body"),
                Cylinder(0.075, 0.34, at=(0, 0.13, 0.36), pitch=90, material=gear, name="lens"),
                Cylinder(0.068, 0.01, at=(0, 0.13, 0.535), pitch=90, material="studio.lens.glass", name="glass"),
                Box((0.2, 0.15, 0.04), at=(-0.04, 0.36, -0.2), material=gear, name="viewfinder"),
                Backdrop(width=0.17, height=0.12, at=(-0.04, 0.36, -0.221), yaw=180, material="studio.screen.pattern", name="viewfinder-screen"),
                tube(((-0.1, 0.05, -0.25), (-0.25, 0.0, -0.55), (-0.3, -0.05, -0.75)), 0.016, gear, samples=(16, 6), name="pan-bar"),
                tube(((0.1, 0.05, -0.25), (0.25, 0.0, -0.55), (0.3, -0.05, -0.75)), 0.016, gear, samples=(16, 6), name="pan-bar")]
        if self.prompter:
            head += [Box((0.5, 0.42, 0.42), at=(0, 0.16, 0.56), material=gear, name="hood"),
                     Box((0.46, 0.36, 0.01), at=(0, 0.16, 0.775), material="studio.lens.glass", name="prompter-glass")]
        parts.append(Group(head, at=(0, h, 0), name="head"))
        return parts


@dataclass
class Studio(Prefab):
    """The whole studio: floor, walls and grid, the video wall, the desk, cameras, monitors and cables."""

    def room(self) -> list[Node]:
        return [Box((26, 0.1, 22), at=(0, -0.05, 2), material="studio.floor.concrete", name="floor"),
                Box((26, 0.1, 22), at=(0, 6.25, 2), material="studio.wall.black", casts_shadow=False, name="ceiling"),
                *band(WALL, RADIUS + 0.6, (-62, 62), (0, 6.2), "studio.wall.black", pieces=12, name="back-wall"),
                Box((0.2, 6.2, 22), at=(-12.5, 3.1, 2), material="studio.wall.black", name="wall"),
                Box((0.2, 6.2, 22), at=(12.5, 3.1, 2), material="studio.wall.black", name="wall"),
                Box((26, 6.2, 0.2), at=(0, 3.1, -9), material="studio.wall.black", name="wall")]

    def video_wall(self) -> list[Node]:
        parts: list[Node] = [picture(WALL, RADIUS, (-40, -5), (0.75, 3.5), "studio.screen.pattern", name="screen-left")]
        parts += band(WALL, RADIUS, (-4.6, 2.6), (0.75, 3.5), "studio.glow.panel.plum", pieces=2, name="column")
        parts.append(picture(WALL, RADIUS, (3, 46), (0.75, 3.5), "studio.screen.wall", name="screen-right"))
        parts += band(WALL, RADIUS, (-48, 54), (0, 0.75), "studio.wall.black", pieces=12, name="plinth")
        parts += band(WALL, RADIUS - 0.05, (-48, 54), (3.7, 3.82), "studio.glow.mint", pieces=12, name="crown-light")
        parts += band(WALL, RADIUS - 0.05, (-46, -42), (0, 4.4), "studio.glow.tangerine", name="pillar")
        parts += band(WALL, RADIUS - 0.1, (-42, -40.4), (0.75, 3.5), "studio.glow.panel.plum", name="column")
        parts += band(WALL, RADIUS, (47, 54), (0.75, 3.5), "studio.glow.panel.plum", name="column")
        return parts

    def grid(self) -> list[Node]:
        """Truss across the studio with lamps hung from it, each a real spot aimed at the desk or the wall."""
        parts: list[Node] = [Box((18, 0.25, 0.25), at=(0, 5.4, z), material="studio.metal.truss", casts_shadow=False, name="truss")
                             for z in (-3.5, -0.5, 2.5)]
        anchors = (0.0, 1.4, 0.6)
        lamps = [((-3.5, -3.5), anchors, 56.0), ((-1.2, -3.5), anchors, 56.0), ((1.2, -3.5), anchors, 56.0), ((3.5, -3.5), anchors, 56.0),
                 ((-2.4, -0.5), (0.0, 0.0, -0.8), 30.0), ((2.4, -0.5), (0.0, 0.0, -0.8), 30.0),
                 ((-1.6, 2.5), (0.0, 1.5, 0.5), 30.0), ((1.6, 2.5), (0.0, 1.5, 0.5), 30.0),
                 ((-6.0, -0.5), (-4.0, 0.0, -2.0), 18.0), ((6.0, -0.5), (4.0, 0.0, -2.0), 18.0)]
        for index, ((x, z), target, power) in enumerate(lamps):
            at = (x, 5.05, z)
            facing = aim(at, target)
            parts.append(Group([Cylinder(0.14, 0.32, pitch=90, material="studio.metal.gear", casts_shadow=False),
                                Cylinder(0.12, 0.01, at=(0, 0, 0.165), pitch=90, material="studio.glow.lens", casts_shadow=False),
                                Box((0.03, 0.3, 0.03), at=(0, 0.2, 0), material="studio.metal.gear", casts_shadow=False)],
                               at=at, yaw=facing["yaw"], pitch=facing["pitch"], name="lamp"))
            parts.append(Spot(power, color="#fff3e4", at=at, cone=46, reach=14, shadows=index < 4, softness=0.5, name=f"spot-{index}",
                              **facing))
        parts += [Point(1.6, color="#3fe0b5", at=(0, 0.6, -0.9), reach=4.0, name="desk-glow"),
                  Point(2.5, color="#ff8a1f", at=(0, 2.2, 5.0), reach=8.0, name="wall-spill")]
        return parts

    def floor_gear(self) -> list[Node]:
        """The cameras, a stack of monitors and their cables."""
        parts: list[Node] = [PedestalCamera(at=(-2.3, 0, -4.4), yaw=22, name="camera-1"),
                             PedestalCamera(at=(4.2, 0, -2.4), yaw=-42, name="camera-2")]
        stand = [Box((0.06, 1.3, 0.06), at=(0, 0.65, 0), material="studio.metal.gear"),
                 Box((0.5, 0.04, 0.4), at=(0, 0.02, 0), material="studio.metal.gear")]
        for level, y in enumerate((0.95, 1.38)):
            stand += [Box((0.62, 0.38, 0.06), at=(0, y, 0), material="studio.metal.gear"),
                      Backdrop(width=0.56, height=0.32, at=(0, y, -0.031), material="studio.screen.pattern", name=f"monitor-{level}")]
        parts.append(Group(stand, at=(-5.0, 0, -2.0), yaw=-32, name="monitors"))
        for points in (((-2.3, 0.01, -4.4), (-3.6, 0.01, -3.0), (-4.6, 0.01, -1.4), (-6.5, 0.01, 0.5)),
                       ((-2.2, 0.01, -4.3), (-1.2, 0.01, -3.2), (-2.5, 0.01, -1.4), (-4.8, 0.01, -1.9)),
                       ((4.2, 0.01, -2.4), (5.0, 0.01, -1.0), (4.0, 0.01, -0.2), (6.5, 0.01, 0.8)),
                       ((4.3, 0.01, -2.3), (3.2, 0.01, -1.4), (4.6, 0.01, -0.6), (5.6, 0.01, -1.8))):
            parts.append(tube(points, 0.012, "studio.cable.black", samples=(48, 6), casts_shadow=False, name="cable"))
        return parts

    def build(self) -> Sequence[Node]:
        return [*self.room(), *self.video_wall(), *self.grid(), Desk(name="desk"), *self.floor_gear()]


class NewsroomPlugin(Plugin):
    name = "newsroom"
    version = "1.1.0"
    requires = ("stock",)
    shaders, slots = SHADERS, SLOTS

    def register(self, registry: Registry) -> None:
        registry.prefabs.add("news.desk", Desk)
        registry.prefabs.add("news.camera", PedestalCamera)
        registry.prefabs.add("news.studio", Studio)
