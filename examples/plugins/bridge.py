"""A starship's bridge laid out as real control rooms are: one floor, a straight band of raked windows across the bow with a
line of consoles under it and chairs at the middle two, a wall-sized mimic board to port with its desk, a chart table
against the starboard wall, and a coffered ceiling with lines of light. Outside are deep space and ships of no known class.
publish_catalog.py freezes it, so a project uses it without this file. The ship's bow is +z: the origin is on the floor in
the middle of the room and the windows close it at z 5. The pictures are drawn by bridge_pictures.py. Sizes are a large
ship's: a room 14 m wide, a ceiling 3.6 m up, consoles 0.8 m high and windows 2 m tall, leaning out 15 degrees."""
import math
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

sys.path.insert(0, str(Path(__file__).resolve().parent))

from grand_tourer import pillow

from srlocations import Backdrop, Box, Cylinder, Group, Material, Node, Plugin, Point, Prefab, Registry, Seat, Vec3

PICTURES = Path(__file__).resolve().parent.parent / "textures" / "bridge"
FRONT, AFT, SIDE = 5.0, -6.2, 7.0  # the bow's windows, the aft wall and the side walls, all inner faces
SILL, LINTEL, CEILING, RAKE = 1.15, 3.15, 3.6, 15.0
PANES = 6  # windows across the bow, between mullions
STATIONS = (-4.05, -1.35, 1.35, 4.05)  # the consoles along the bow, and chairs at the middle two


def screen(name: str, strength: float = 1.0) -> Material:
    return Material("#000000", 0.5, glow="#ffffff", glow_strength=strength, maps={"emissiveMap": str(PICTURES / f"{name}.png")})


SHADERS = {
    "hull.grey": (Material("#5d636b", 0.5, 0.45), ["metal"], "Grey bulkhead plating"),
    "hull.dark": (Material("#25282d", 0.55, 0.5), ["metal"], "Dark ceiling and recess plating"),
    "deck.plate": (Material("#ffffff", 0.45, 0.4, maps={"baseColorMap": str(PICTURES / "deck.png")}, extra={"uvScaleX": 7, "uvScaleY": 5}),
                   ["metal", "floor", "textured"], "Dark deck plates a metre square"),
    "deck.grate": (Material("#0e1013", 0.7, 0.5), ["metal", "floor"], "A floor vent grating"),
    "glow.strip": (Material("#000000", 1.0, glow="#e6f0ff", glow_strength=3.5), ["glow"], "A white light panel"),
    "screen.scope": (screen("scope"), ["glow", "screen"], "A round sensor scope"),
    "screen.tactical": (screen("tactical"), ["glow", "screen"], "A red tactical display"),
    "screen.readouts": (screen("readouts"), ["glow", "screen"], "Bar graphs and figures"),
    "screen.mimic": (screen("mimic", 0.9), ["glow", "screen"], "A mimic board of the ship's systems, lines and lamps without words"),
    "screen.chart": (screen("chart", 0.9), ["glow", "screen"], "A star chart with a plotted course"),
    "keys.panel": (Material("#ffffff", 0.5, glow="#ffffff", glow_strength=0.35, maps={"baseColorMap": str(PICTURES / "keys.png"),
                                                                                       "emissiveMap": str(PICTURES / "keys.png")}),
                   ["glow", "textured"], "A console top of keys and lit lamps"),
    "space.stars": (Material("#ffffff", 1.0, extra={"unlit": True}, maps={"baseColorMap": str(PICTURES / "stars.png")}), ["backdrop"],
                    "Deep space with a blue nebula"),
    "ship.white": (Material("#b8bcc2", 0.6, 0.3), ["metal"], "A capital ship's pale hull"),
    "ship.engine": (Material("#000000", 1.0, glow="#7fc4ff", glow_strength=5.0), ["glow"], "Engine glow"),
    "rail.steel": (Material("#a2a8b0", 0.3, 0.9), ["metal"], "Brushed steel railing"),
    "chair.black": (Material("#17191c", 0.55), ["leather"], "Black command chair padding"),
}
SLOTS = {"plating": "studio.hull.grey", "deck": "studio.deck.plate", "light": "studio.glow.strip"}


def lights(height: float, count: int, **place) -> Group:
    """A column of light panels, as the pillars carry."""
    step = height / count
    return Group([Box((0.1, step * 0.7, 0.03), at=(0, (i + 0.5) * step, 0), material="studio.glow.strip", casts_shadow=False)
                  for i in range(count)], **place)


@dataclass
class Console(Prefab):
    """A bridge console: a body, a sloped top of keys and a hood of screens. Whoever works it stands at -z facing +z."""
    width: float = 2.0
    screens: Sequence[str] = ("studio.screen.scope", "studio.screen.readouts")
    plating: str = "studio.hull.grey"

    def build(self) -> Sequence[Node]:
        w = self.width
        parts: list[Node] = [Box((w, 0.74, 0.62), at=(0, 0.37, 0.02), material=self.plating, name="body"),
                             Box((w - 0.06, 0.03, 0.5), at=(0, 0.79, -0.04), pitch=14, material="studio.keys.panel", name="keys"),
                             Box((w, 0.08, 0.66), at=(0, 0.74, 0.02), material="studio.hull.dark", name="lip"),
                             Box((w, 0.5, 0.1), at=(0, 1.12, 0.28), pitch=-12, material="studio.hull.dark", name="hood")]
        span = (w - 0.1) / len(self.screens)
        for i, picture in enumerate(self.screens):
            x = -w / 2 + 0.05 + span * (i + 0.5)
            parts.append(Backdrop(width=span - 0.08, height=0.4, at=(x, 1.12, 0.225), pitch=-12, material=picture, name="screen"))
        return parts


@dataclass
class ConsoleChair(Prefab):
    """A padded swivel chair for a console, its column behind the hips so a body can be marked where it sits. It faces +z,
    toward the console's screens."""
    padding: str = "studio.chair.black"

    def seats(self) -> Sequence[Seat]:
        return [Seat(Vec3(0, 0, -0.06), 0.0, 0.455, 0.3, 0.13)]

    def build(self) -> Sequence[Node]:
        parts: list[Node] = [Cylinder(0.3, 0.05, at=(0, 0.025, -0.1), material="studio.hull.dark", name="base"),
                             Cylinder(0.06, 0.32, at=(0, 0.21, -0.22), material="studio.rail.steel", name="column"),
                             pillow((0.52, 0.11, 0.5), self.padding, square=0.35, samples=(24, 12), at=(0, 0.395, 0.0), name="seat"),
                             pillow((0.5, 0.66, 0.13), self.padding, square=0.35, samples=(24, 16), at=(0, 0.78, -0.28), pitch=-8,
                                    name="back")]
        for side in (-1, 1):
            parts.append(Box((0.06, 0.04, 0.34), at=(side * 0.3, 0.62, -0.04), material="studio.hull.grey", name="arm"))
        return parts


@dataclass
class MimicBoard(Prefab):
    """A wall-sized control board of the ship's systems with a low desk before it, as a power plant or a launch control room
    has. Whoever works it stands at -z, past the desk, facing the board at +z."""
    length: float = 6.4
    plating: str = "studio.hull.grey"

    def build(self) -> Sequence[Node]:
        n = self.length
        return [Box((n + 0.2, 2.5, 0.1), at=(0, 1.95, 0.05), material="studio.hull.dark", name="frame"),
                Backdrop(width=n, height=n / 4, at=(0, 1.95, -0.005), material="studio.screen.mimic", name="board"),
                Box((n - 1.0, 0.74, 0.55), at=(0, 0.37, -1.0), material=self.plating, name="desk"),
                Box((n - 1.06, 0.03, 0.46), at=(0, 0.76, -1.04), pitch=10, material="studio.keys.panel", name="desk-keys")]


@dataclass
class ChartTable(Prefab):
    """A chart table with a sloped, lit top and a lamp over it, to stand against a wall. Whoever reads it stands at -z."""
    plating: str = "studio.hull.grey"

    def build(self) -> Sequence[Node]:
        slope = 12.0
        up, back = 0.021 * math.cos(math.radians(slope)), -0.021 * math.sin(math.radians(slope))  # just off the top
        return [Box((1.5, 0.84, 0.9), at=(0, 0.42, 0), material=self.plating, name="body"),
                Box((1.56, 0.04, 0.96), at=(0, 0.9, 0), pitch=slope, material="studio.hull.dark", name="top"),
                Backdrop(width=1.44, height=0.86, at=(0, 0.9 + up, back), pitch=slope - 90, material="studio.screen.chart",
                         name="chart"),
                Box((1.2, 0.08, 0.3), at=(0, 2.05, 0.25), material="studio.hull.dark", name="lamp"),
                Point(0.9, color="#ffe2b8", at=(0, 1.9, 0.15), reach=2.5, name="chart-light")]


@dataclass
class Bridge(Prefab):
    """The whole bridge and the view from it."""
    plating: str = "studio.hull.grey"
    deck: str = "studio.deck.plate"
    light: str = "studio.glow.strip"

    def floor(self) -> list[Node]:
        depth = FRONT - AFT
        parts: list[Node] = [Box((2 * SIDE, 0.1, depth + 1), at=(0, -0.05, (FRONT + AFT) / 2 + 0.5), material=self.deck, name="floor")]
        for x in (-2.7, 2.7):
            parts.append(Box((0.7, 0.012, 6.5), at=(x, 0.006, -0.6), material="studio.deck.grate", name="grate"))
        return parts

    def windows(self) -> list[Node]:
        """A straight band of windows across the bow, their tops leaning out as a ship's bridge windows do, and nothing in
        the openings."""
        tall = LINTEL - SILL
        lean = math.radians(RAKE)
        pane = 2 * (SIDE - 0.4) / PANES
        band: list[Node] = [Box((0.24, tall, 0.3), at=(-(SIDE - 0.4) + i * pane, tall / 2, 0.15), material=self.plating, name="mullion")
                            for i in range(PANES + 1)]
        band.append(Box((2 * SIDE, 0.3, 0.4), at=(0, tall + 0.15, 0.2), material=self.plating, name="header"))
        out, top = tall * math.sin(lean), SILL + tall * math.cos(lean) + 0.3
        return [Box((2 * SIDE, SILL, 0.4), at=(0, SILL / 2, FRONT + 0.2), material=self.plating, name="sill"),
                Box((2 * SIDE, 0.04, 0.5), at=(0, SILL - 0.02, FRONT - 0.05), material="studio.hull.dark", name="sill-top"),
                Group(band, at=(0, SILL, FRONT), pitch=-RAKE, name="window-band"),
                Box((2 * SIDE, CEILING - top + 0.1, 0.4), at=(0, (CEILING + top) / 2, FRONT + out + 0.3), material=self.plating, name="lintel")]

    def walls(self) -> list[Node]:
        depth = FRONT - AFT + 2.0
        parts: list[Node] = [Box((2 * SIDE + 0.6, 0.2, depth), at=(0, CEILING + 0.1, (FRONT + AFT) / 2 + 1.0), material="studio.hull.dark",
                                 name="ceiling"),
                             Box((2 * SIDE + 0.6, CEILING, 0.3), at=(0, CEILING / 2, AFT - 0.15), material=self.plating, name="aft-wall"),
                             Box((1.4, 2.3, 0.1), at=(0, 1.15, AFT + 0.05), material="studio.hull.dark", name="door"),
                             lights(2.3, 5, at=(-0.78, 0, AFT + 0.12)), lights(2.3, 5, at=(0.78, 0, AFT + 0.12))]
        for side in (-1, 1):
            parts.append(Box((0.3, CEILING, depth), at=(side * (SIDE + 0.15), CEILING / 2, (FRONT + AFT) / 2 + 1.0), material=self.plating,
                             name="side-wall"))
            for z in (FRONT - 2.0, AFT + 1.2):  # pillars with their lights
                parts.append(Box((0.9, CEILING, 0.8), at=(side * (SIDE - 0.4), CEILING / 2, z), material=self.plating, name="pillar"))
                parts.append(lights(CEILING - 0.9, 5, at=(side * (SIDE - 0.87), 0.45, z), yaw=side * 90))
        for z, pictures in ((1.4, ("studio.screen.tactical", "studio.screen.scope")), (-3.6, ("studio.screen.readouts", "studio.screen.scope"))):
            parts.append(Box((0.5, 0.95, 2.2), at=(SIDE - 0.25, 0.475, z), material=self.plating, name="wall-bench"))
            parts.append(Box((0.42, 0.03, 2.1), at=(SIDE - 0.32, 0.96, z), roll=-12, material="studio.keys.panel", name="wall-keys"))
            for offset, picture in zip((-0.5, 0.5), pictures):
                parts.append(Box((0.16, 0.62, 0.86), at=(SIDE - 0.08, 1.75, z + offset), material="studio.hull.dark", name="wall-console"))
                parts.append(Backdrop(width=0.76, height=0.5, at=(SIDE - 0.17, 1.75, z + offset), yaw=90, material=picture, name="wall-screen"))
        return parts

    def ceiling(self) -> list[Node]:
        """Beams across and along, and two lines of light panels running to the windows."""
        parts: list[Node] = []
        for x in (-4.6, -3.2, 3.2, 4.6):
            parts.append(Box((0.35, 0.4, FRONT - AFT), at=(x, CEILING - 0.2, (FRONT + AFT) / 2), material="studio.hull.dark", casts_shadow=False,
                             name="beam"))
        for z in (-4.4, -1.4, 1.6, 4.4):
            parts.append(Box((2 * SIDE, 0.4, 0.35), at=(0, CEILING - 0.2, z), material="studio.hull.dark", casts_shadow=False, name="beam"))
        for side in (-1, 1):
            parts.append(Box((0.7, 0.24, FRONT - AFT), at=(side * 1.9, CEILING - 0.32, (FRONT + AFT) / 2), material=self.plating,
                             casts_shadow=False, name="light-run"))
            for i in range(10):
                parts.append(Box((0.26, 0.03, 0.85), at=(side * 1.9, CEILING - 0.455, AFT + 0.6 + i * 1.1), material=self.light,
                                 casts_shadow=False, name="light-panel"))
            for z in (-4.0, -0.5, 3.0):
                parts.append(Point(6.0, color="#dfe9ff", at=(side * 1.9, CEILING - 0.7, z), reach=8.0, name="ceiling-light"))
        parts += [Point(1.6, color="#cfe0ff", at=(side * (SIDE - 1.1), 2.0, z), reach=3.0, name="pillar-light")
                  for side in (-1, 1) for z in (FRONT - 2.0, AFT + 1.2)]
        return parts

    def stations(self) -> list[Node]:
        screens = (("studio.screen.tactical", "studio.screen.scope", "studio.screen.readouts"),
                   ("studio.screen.readouts", "studio.screen.scope", "studio.screen.readouts"),
                   ("studio.screen.scope", "studio.screen.readouts", "studio.screen.scope"),
                   ("studio.screen.readouts", "studio.screen.tactical", "studio.screen.scope"))
        parts: list[Node] = [Console(2.6, pictures, self.plating, at=(x, 0, FRONT - 0.45), name="bow-console")
                             for x, pictures in zip(STATIONS, screens)]
        parts += [ConsoleChair(at=(x, 0, FRONT - 1.4), name="console-chair") for x in STATIONS[1:3]]
        parts.append(MimicBoard(6.4, self.plating, at=(-SIDE + 0.05, 0, -1.4), yaw=-90, name="mimic-board"))
        parts.append(ChartTable(self.plating, at=(SIDE - 0.5, 0, -1.1), yaw=90, name="chart-table"))
        return parts

    def space(self) -> list[Node]:
        """Stars all round the bow, a capital ship standing off to port, and smaller craft further out."""
        parts: list[Node] = [Backdrop(width=420, height=210, at=(160 * math.sin(math.radians(turn)), 20, FRONT + 160 * math.cos(math.radians(turn))),
                                      yaw=turn, material="studio.space.stars", name="stars") for turn in (-75, 0, 75)]
        hull = [pillow((14, 5, 90), "studio.ship.white", square=0.25, taper=0.3, samples=(24, 16), name="hull"),
                Box((10, 3, 30), at=(0, 3.2, -18), material="studio.ship.white", name="superstructure"),
                Box((5, 4, 8), at=(0, 6.5, -26), material="studio.ship.white", name="tower"),
                Box((16, 1.2, 40), at=(0, -0.5, -8), material="studio.hull.grey", name="keel"),
                *(Cylinder(1.6, 0.5, at=(x, 0.5, -45.2), pitch=90, material="studio.ship.engine", name="engine") for x in (-4, 0, 4))]
        parts.append(Group(hull, at=(-30, 10, 140), yaw=62, pitch=4, name="capital-ship"))
        for x, y, z, turn in ((40, 6, 120, -30), (55, 2, 150, -20), (-15, 12, 170, 10)):
            parts.append(Group([pillow((3, 1.2, 10), "studio.ship.white", square=0.3, taper=0.4, samples=(16, 10)),
                                Cylinder(0.6, 0.3, at=(0, 0, -5.1), pitch=90, material="studio.ship.engine")],
                               at=(x, y, z), yaw=turn, name="escort"))
        return parts

    def build(self) -> Sequence[Node]:
        return [*self.floor(), *self.windows(), *self.walls(), *self.ceiling(), *self.stations(), *self.space()]


class BridgePlugin(Plugin):
    name = "bridge"
    version = "2.0.0"
    requires = ("stock",)
    shaders, slots = SHADERS, SLOTS

    def register(self, registry: Registry) -> None:
        registry.prefabs.add("ship.console", Console)
        registry.prefabs.add("ship.console-chair", ConsoleChair)
        registry.prefabs.add("ship.mimic-board", MimicBoard)
        registry.prefabs.add("ship.chart-table", ChartTable)
        registry.prefabs.add("ship.bridge", Bridge)
