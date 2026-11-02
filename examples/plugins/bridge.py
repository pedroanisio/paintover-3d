"""A starship's bridge: a pit with a round holo table between banks of consoles, a raised command deck behind a railing, a
bay of six windows on deep space with ships standing off, and a coffered ceiling with lines of light. publish_catalog.py
freezes it, so a project uses it without this file. The ship's bow is +z: the origin is on the pit floor, the deck steps up
0.6 m at z 3 and the windows close it at the bow. The pictures are drawn by bridge_pictures.py. Sizes are a large ship's: a
room 14 m wide, a ceiling 5.2 m up, consoles 0.8 m high and windows 2.2 m tall."""
import math
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

sys.path.insert(0, str(Path(__file__).resolve().parent))

from grand_tourer import pillow, tube

from srlocations import Backdrop, Box, Cylinder, Group, Material, Node, Plugin, Point, Prefab, Registry, Seat, Vec3

PICTURES = Path(__file__).resolve().parent.parent / "textures" / "bridge"
DECK, STEP = 0.6, 3.0  # the command deck's height, and where its edge is along the ship
BAY, REACH = (0.0, 3.5), 6.0  # the middle of the window bay on the floor, and how far its windows stand from it
TURNS = (-60, -36, -12, 12, 36, 60)  # each window's yaw
SILL, LINTEL, CEILING = 1.3, 4.0, 5.2


def screen(name: str, strength: float = 1.0) -> Material:
    return Material("#000000", 0.5, glow="#ffffff", glow_strength=strength, maps={"emissiveMap": str(PICTURES / f"{name}.png")})


SHADERS = {
    "hull.grey": (Material("#5d636b", 0.5, 0.45), ["metal"], "Grey bulkhead plating"),
    "hull.dark": (Material("#25282d", 0.55, 0.5), ["metal"], "Dark ceiling and recess plating"),
    "deck.plate": (Material("#ffffff", 0.45, 0.4, maps={"baseColorMap": str(PICTURES / "deck.png")}, extra={"uvScaleX": 7, "uvScaleY": 5}),
                   ["metal", "floor", "textured"], "Dark deck plates a metre square"),
    "deck.grate": (Material("#0e1013", 0.7, 0.5), ["metal", "floor"], "A floor vent grating"),
    "glow.strip": (Material("#000000", 1.0, glow="#e6f0ff", glow_strength=3.5), ["glow"], "A white light panel"),
    "glow.holo": (screen("holo", 1.6), ["glow", "screen"], "A holographic map of a planet"),
    "screen.scope": (screen("scope"), ["glow", "screen"], "A round sensor scope"),
    "screen.tactical": (screen("tactical"), ["glow", "screen"], "A red tactical display"),
    "screen.readouts": (screen("readouts"), ["glow", "screen"], "Bar graphs and figures"),
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
class CommandChair(Prefab):
    """A padded chair on a column, with an arm console either side. It faces +z, the way the ship does."""
    padding: str = "studio.chair.black"

    def seats(self) -> Sequence[Seat]:
        return [Seat(Vec3(0, 0, -0.06), 0.0, 0.455, 0.3, 0.13)]

    def build(self) -> Sequence[Node]:
        parts: list[Node] = [Cylinder(0.36, 0.05, at=(0, 0.025, 0), material="studio.hull.dark", name="base"),
                             Cylinder(0.08, 0.32, at=(0, 0.21, -0.22), material="studio.rail.steel", name="column"),
                             pillow((0.6, 0.12, 0.56), self.padding, square=0.35, samples=(24, 12), at=(0, 0.395, 0.0), name="seat"),
                             pillow((0.6, 0.86, 0.15), self.padding, square=0.35, samples=(24, 16), at=(0, 0.875, -0.28), pitch=-8,
                                    name="back"),
                             pillow((0.34, 0.24, 0.14), self.padding, square=0.4, samples=(16, 10), at=(0, 1.405, -0.36), pitch=-8,
                                    name="headrest")]
        for side in (-1, 1):
            parts += [Box((0.13, 0.22, 0.5), at=(side * 0.38, 0.555, -0.04), material="studio.hull.grey", name="arm"),
                      Box((0.13, 0.02, 0.36), at=(side * 0.38, 0.675, 0.02), material="studio.keys.panel", name="arm-keys")]
        return parts


@dataclass
class HoloTable(Prefab):
    """A round table on a pedestal, its top a lit map, its rim set with small screens."""

    def build(self) -> Sequence[Node]:
        parts: list[Node] = [Cylinder(0.75, 0.08, at=(0, 0.04, 0), material="studio.hull.dark", name="foot"),
                             Cylinder(0.55, 0.52, at=(0, 0.34, 0), material="studio.hull.grey", name="pedestal"),
                             Cylinder(1.18, 0.3, at=(0, 0.75, 0), material="studio.hull.grey", name="rim"),
                             Cylinder(1.22, 0.04, at=(0, 0.92, 0), material="studio.hull.dark", name="lip"),
                             Cylinder(0.98, 0.012, at=(0, 0.946, 0), material="studio.glow.holo", name="map"),
                             Point(1.4, color="#5cb8ff", at=(0, 1.35, 0), reach=3.0, name="holo-light")]
        for i in range(8):
            turn = math.radians(i * 45 + 22.5)
            picture = ("studio.screen.scope", "studio.screen.readouts", "studio.screen.tactical")[i % 3]
            parts.append(Backdrop(width=0.3, height=0.16, at=(1.19 * math.sin(turn), 0.76, 1.19 * math.cos(turn)), yaw=math.degrees(turn) + 180,
                                  material=picture, name="rim-screen"))
        return parts


@dataclass
class Bridge(Prefab):
    """The whole bridge and the view from it."""
    plating: str = "studio.hull.grey"
    deck: str = "studio.deck.plate"
    light: str = "studio.glow.strip"

    def floors(self) -> list[Node]:
        parts: list[Node] = [Box((14, 0.1, 10), at=(0, -0.05, -2.0), material=self.deck, name="pit-floor"),
                             Box((14, DECK, 7), at=(0, DECK / 2, STEP + 3.5), material=self.deck, name="command-deck"),
                             Box((14, 0.03, 0.03), at=(0, DECK - 0.08, STEP - 0.02), material=self.light, casts_shadow=False, name="deck-edge")]
        for i, h in enumerate((0.15, 0.3, 0.45)):
            parts.append(Box((2.0, h, 0.32), at=(0, h / 2, STEP - 0.96 + i * 0.32), material=self.plating, name=f"step-{i}"))
        for x in (-2.4, 2.4):
            parts.append(Box((0.7, 0.012, 7.5), at=(x, 0.006, -2.6), material="studio.deck.grate", name="grate"))
        return parts

    def railing(self) -> list[Node]:
        top, parts = DECK + 1.0, []
        for side in (-1, 1):
            parts.append(tube(((side * 1.1, top, STEP + 0.05), (side * 3.8, top, STEP + 0.05), (side * 6.5, top, STEP + 0.05)), 0.025,
                              "studio.rail.steel", samples=(16, 8), name="rail"))
            parts.append(tube(((side * 1.1, top, STEP + 0.05), (side * 1.1, 0.75 + 0.3, STEP - 0.5), (side * 1.1, 1.0, STEP - 1.05)), 0.025,
                              "studio.rail.steel", samples=(16, 8), name="stair-rail"))
            for x in (1.1, 2.45, 3.8, 5.15, 6.5):
                parts.append(Cylinder(0.025, 1.0, at=(side * x, DECK + 0.5, STEP + 0.05), material="studio.rail.steel", name="post"))
            parts.append(Cylinder(0.025, 1.0, at=(side * 1.1, 0.5, STEP - 1.05), material="studio.rail.steel", name="post"))
        return parts

    def windows(self) -> list[Node]:
        """Six windows round the bow, each with a sill, a lintel, mullions and cut corners, and nothing in the openings."""
        half = REACH * math.tan(math.radians(12))
        parts: list[Node] = []
        for turn in TURNS:
            a = math.radians(turn)
            frame = [Box((2 * half + 0.2, SILL - DECK, 0.4), at=(0, (SILL + DECK) / 2, 0), material=self.plating, name="sill"),
                     Box((2 * half + 0.2, CEILING - LINTEL, 0.4), at=(0, (CEILING + LINTEL) / 2, 0), material=self.plating, name="lintel")]
            for side in (-1, 1):
                frame.append(Box((0.36, LINTEL - SILL, 0.5), at=(side * half, (SILL + LINTEL) / 2, 0), material=self.plating, name="mullion"))
                for y, lean in ((SILL + 0.16, 1), (LINTEL - 0.16, -1)):
                    frame.append(Box((0.5, 0.14, 0.42), at=(side * (half - 0.3), y, 0), roll=side * lean * 45, material=self.plating,
                                     name="corner"))
            parts.append(Group(frame, at=(BAY[0] + REACH * math.sin(a), 0, BAY[1] + REACH * math.cos(a)), yaw=turn, name="window"))
        for side in (-1, 1):  # the bay's ends, out to the walls
            parts.append(Box((2.2, CEILING, 0.5), at=(side * 6.2, CEILING / 2, BAY[1] + 2.4), yaw=side * 62, material=self.plating, name="bay-end"))
        return parts

    def walls(self) -> list[Node]:
        parts: list[Node] = [Box((14.6, 0.2, 18), at=(0, CEILING + 0.1, 1), material="studio.hull.dark", name="ceiling"),
                             Box((14.6, CEILING, 0.3), at=(0, CEILING / 2, -7.1), material=self.plating, name="aft-wall")]
        for side in (-1, 1):
            parts.append(Box((0.3, CEILING, 13), at=(side * 7.15, CEILING / 2, -0.6), material=self.plating, name="side-wall"))
            for z, turn in ((4.0, side * -40), (-0.2, 0), (-4.6, 0)):  # pillars with their lights
                parts.append(Box((0.9, CEILING, 0.8), at=(side * 6.6, CEILING / 2, z), yaw=turn, material=self.plating, name="pillar"))
                parts.append(lights(CEILING - 1.2, 7, at=(side * 6.12, 0.6, z), yaw=side * 90 + turn))
            parts.append(Box((0.12, 0.9, 3.4), at=(side * 6.98, 4.1, -2.4), material="studio.deck.grate", name="vent"))
            for z, picture in ((-1.6, "studio.screen.tactical"), (-2.4, "studio.screen.scope"), (-3.2, "studio.screen.readouts")):
                parts.append(Box((0.16, 0.62, 0.72), at=(side * 6.92, 1.75, z), material="studio.hull.dark", name="wall-console"))
                parts.append(Backdrop(width=0.62, height=0.5, at=(side * 6.83, 1.75, z), yaw=-side * 90, material=picture, name="wall-screen"))
            parts.append(Box((0.5, 0.95, 2.8), at=(side * 6.75, 0.475, -2.4), material=self.plating, name="wall-bench"))
            parts.append(Box((0.42, 0.03, 2.7), at=(side * 6.68, 0.96, -2.4), roll=-side * 12, material="studio.keys.panel", name="wall-keys"))
        return parts

    def ceiling(self) -> list[Node]:
        """Beams across and along, and two lines of light panels running to the windows."""
        parts: list[Node] = []
        for x in (-4.6, -3.2, 3.2, 4.6):
            parts.append(Box((0.35, 0.45, 17), at=(x, CEILING - 0.22, 1), material="studio.hull.dark", casts_shadow=False, name="beam"))
        for z in (-5.0, -1.8, 1.4, 4.6):
            parts.append(Box((14, 0.45, 0.35), at=(0, CEILING - 0.22, z), material="studio.hull.dark", casts_shadow=False, name="beam"))
        for side in (-1, 1):
            parts.append(Box((0.7, 0.3, 13), at=(side * 1.9, CEILING - 0.35, 0.5), material=self.plating, casts_shadow=False, name="light-run"))
            for i in range(11):
                parts.append(Box((0.26, 0.03, 0.85), at=(side * 1.9, CEILING - 0.51, -5.2 + i * 1.15), material=self.light,
                                 casts_shadow=False, name="light-panel"))
            for z in (-3.5, 0.5, 4.5):
                parts.append(Point(9.0, color="#dfe9ff", at=(side * 1.9, CEILING - 0.8, z), reach=9.0, name="ceiling-light"))
        parts += [Point(3.0, color="#cfe0ff", at=(side * 5.8, 2.6, z), reach=4.0, name="pillar-light") for side in (-1, 1) for z in (4.0, -0.2)]
        return parts

    def stations(self) -> list[Node]:
        return [HoloTable(at=(0, 0, -0.5), name="holo-table"),
                Console(3.0, ("studio.screen.tactical", "studio.screen.scope", "studio.screen.readouts", "studio.screen.scope"),
                        self.plating, at=(-3.3, 0, 1.6), yaw=12, name="pit-console"),
                Console(3.0, ("studio.screen.readouts", "studio.screen.scope", "studio.screen.tactical", "studio.screen.scope"),
                        self.plating, at=(3.3, 0, 1.6), yaw=-12, name="pit-console"),
                Console(2.6, ("studio.screen.tactical", "studio.screen.readouts", "studio.screen.scope"), self.plating, at=(-4.7, 0, -2.4),
                        yaw=58, name="corner-console"),
                Console(2.6, ("studio.screen.scope", "studio.screen.tactical", "studio.screen.readouts"), self.plating, at=(4.7, 0, -2.4),
                        yaw=-58, name="corner-console"),
                CommandChair(at=(0, DECK, 5.4), name="command-chair"),
                Console(1.1, ("studio.screen.scope",), self.plating, at=(-1.15, DECK, 5.9), yaw=-10, name="chair-console"),
                Console(1.1, ("studio.screen.readouts",), self.plating, at=(1.15, DECK, 5.9), yaw=10, name="chair-console"),
                *(Console(1.8, ("studio.screen.readouts", "studio.screen.scope"), self.plating,
                          at=(BAY[0] + (REACH - 1.0) * math.sin(math.radians(turn)), DECK, BAY[1] + (REACH - 1.0) * math.cos(math.radians(turn))),
                          yaw=turn, name="window-console") for turn in (-36, 36))]

    def space(self) -> list[Node]:
        """Stars all round the bow, a capital ship standing off to port, and smaller craft further out."""
        parts: list[Node] = [Backdrop(width=420, height=210, at=(160 * math.sin(math.radians(turn)), 20, BAY[1] + 160 * math.cos(math.radians(turn))),
                                      yaw=turn, material="studio.space.stars", name="stars") for turn in (-75, 0, 75)]
        hull = [pillow((14, 5, 90), "studio.ship.white", square=0.25, taper=0.3, samples=(24, 16), name="hull"),
                Box((10, 3, 30), at=(0, 3.2, -18), material="studio.ship.white", name="superstructure"),
                Box((5, 4, 8), at=(0, 6.5, -26), material="studio.ship.white", name="tower"),
                Box((16, 1.2, 40), at=(0, -0.5, -8), material="studio.hull.grey", name="keel"),
                *(Cylinder(1.6, 0.5, at=(x, 0.5, -45.2), pitch=90, material="studio.ship.engine", name="engine") for x in (-4, 0, 4))]
        parts.append(Group(hull, at=(-40, 8, 110), yaw=62, pitch=4, name="capital-ship"))
        for x, y, z, turn in ((40, 6, 120, -30), (55, 2, 150, -20), (-15, 12, 170, 10)):
            parts.append(Group([pillow((3, 1.2, 10), "studio.ship.white", square=0.3, taper=0.4, samples=(16, 10)),
                                Cylinder(0.6, 0.3, at=(0, 0, -5.1), pitch=90, material="studio.ship.engine")],
                               at=(x, y, z), yaw=turn, name="escort"))
        return parts

    def build(self) -> Sequence[Node]:
        return [*self.floors(), *self.railing(), *self.windows(), *self.walls(), *self.ceiling(), *self.stations(), *self.space()]


class BridgePlugin(Plugin):
    name = "bridge"
    version = "1.0.0"
    requires = ("stock",)
    shaders, slots = SHADERS, SLOTS

    def register(self, registry: Registry) -> None:
        registry.prefabs.add("ship.console", Console)
        registry.prefabs.add("ship.command-chair", CommandChair)
        registry.prefabs.add("ship.holo-table", HoloTable)
        registry.prefabs.add("ship.bridge", Bridge)
