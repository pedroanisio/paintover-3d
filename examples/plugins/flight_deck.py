"""An airliner's flight deck at dusk over a lit city. publish_catalog.py freezes it, so a project uses it without this file.
The aircraft faces +z with its origin on the floor between the seats. The pictures are drawn by flight_deck_pictures.py."""
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

sys.path.insert(0, str(Path(__file__).parent))

from grand_tourer import pillow, sheet, tube

from srlocations import Backdrop, Box, Cylinder, Group, Material, Node, Plugin, Point, Prefab, Registry, Spot, Surface

PICTURES = Path(__file__).resolve().parent.parent / "textures" / "flight-deck"
SEAT_X, SEAT_Z = 0.52, 0.15
YOKE_Z, YOKE_Y, YOKE_HALF = 0.5, 0.82, 0.17
WALL, TILT = 1.3, 11  # half the width inside, and how steeply the roof falls toward the nose
PANEL_Z, PANEL_Y, LEAN = 1.02, 0.79, 7  # the panel's face, and how far its top leans away
LIP_Z, LIP_HIGH, LIP_LOW = 0.9, 1.16, 1.02  # the glareshield's edge, at the middle and at the ends


def screen(name: str, strength: float = 1.0) -> Material:
    return Material("#000000", 0.75, glow="#ffffff", glow_strength=strength, maps={"emissiveMap": str(PICTURES / f"{name}.png")})


SHADERS = {
    "panel.cream": (Material("#b4b1aa", 0.5, extra={"doubleSided": True}), ["plastic"], "Pale flight deck lining"),
    "panel.graphite": (Material("#26272b", 0.6, extra={"doubleSided": True}), ["plastic"], "Flat dark instrument panel paint"),
    "panel.black": (Material("#0b0b0e", 0.7, extra={"doubleSided": True}), ["plastic"], "Black behind the instruments"),
    "fabric.quilt": (Material("#31469a", 0.85), ["fabric"], "Blue seat piping"),
    "fabric.slate": (Material("#6b6a70", 0.95), ["fabric"], "Grey seat cloth"),
    "fabric.seat": (Material("#a9a7ad", 0.9), ["fabric"], "Pale seat cushion"),
    "carpet.slate": (Material("#1b1c22", 0.95), ["fabric"], "Dark flight deck carpet"),
    "metal.lever": (Material("#b9bcc2", 0.3, 1.0), ["metal"], "Worn lever metal"),
    "glass.windshield": (Material("#c8d4ec", 0.04, opacity=0.05, extra={"doubleSided": True}), ["glass"], "Clear windshield"),
    "glow.lip": (Material("#000000", 1.0, glow="#3a58ff", glow_strength=3.0), ["glow"], "Blue flood strip"),
    "glow.lamp": (Material("#000000", 1.0, glow="#d8dce8", glow_strength=0.5), ["glow"], "A dim dome lamp"),
    "screen.pfd": (screen("pfd"), ["glow", "screen"], "Primary flight display"),
    "screen.nd": (screen("nd"), ["glow", "screen"], "Navigation display"),
    "screen.eicas": (screen("eicas"), ["glow", "screen"], "Engine display"),
    "screen.cdu": (screen("cdu"), ["glow", "screen"], "Flight management keypad and screen"),
    "screen.standby": (screen("standby"), ["glow", "screen"], "Standby attitude display"),
    "screen.mcp": (screen("mcp"), ["glow", "screen"], "Autopilot panel"),
    "screen.overhead": (screen("overhead", 1.2), ["glow", "screen"], "Overhead panel with its lamps lit"),
    "screen.radios": (screen("radios"), ["glow", "screen"], "Radio panels"),
    "view.city": (Material("#ffffff", 1.0, extra={"unlit": True}, maps={"baseColorMap": str(PICTURES / "city.png")}),
                  ["backdrop"], "A lit city at dusk from the air"),
}
SLOTS = {"lining": "studio.panel.cream", "panel": "studio.panel.graphite", "piping": "studio.fabric.quilt", "cloth": "studio.fabric.slate",
         "cushion": "studio.fabric.seat", "carpet": "studio.carpet.slate"}


def roof(z: float) -> float:
    """How high the lining is along the aircraft: it comes down to meet the windshield."""
    return 1.6 + 0.2 * (1.05 - z)


def picture(size: Sequence[float], material: str, **place) -> Backdrop:
    return Backdrop(width=size[0], height=size[1], material=material, **place)


@dataclass
class FlightDeck(Prefab):
    lining: str = "studio.panel.cream"
    panel: str = "studio.panel.graphite"
    black: str = "studio.panel.black"
    piping: str = "studio.fabric.quilt"
    cloth: str = "studio.fabric.slate"
    cushion: str = "studio.fabric.seat"
    carpet: str = "studio.carpet.slate"
    lever: str = "studio.metal.lever"
    glass: str = "studio.glass.windshield"

    def shell(self) -> list[Node]:
        rear, front = -1.3, 1.05
        parts: list[Node] = [
            Box((2.8, 0.04, 3.2), at=(0, -0.02, 0.2), material=self.carpet),
            Box((2.8, 2.1, 0.04), at=(0, 1.0, rear), material=self.lining),
            sheet([[(-WALL, roof(z) - 0.2, z), (-0.6, roof(z) + 0.02, z), (0.6, roof(z) + 0.02, z), (WALL, roof(z) - 0.2, z)]
                   for z in (rear, front)], self.lining, inward=True, name="roof"),
            Box((0.98, 0.02, 1.5), at=(0, roof(0.42) - 0.05, 0.42), pitch=-TILT, material=self.panel),
        ]
        for side in (-1, 1):
            parts.extend([
                sheet([[(side * WALL, 0, z), (side * (WALL + 0.04), 0.6, z), (side * WALL, 1.1, z)] for z in (rear, 1.2)], self.lining, inward=side > 0, name="wall"),
                sheet([[(side * WALL, 1.1, z), (side * (WALL - 0.02), 1.34, z)] for z in (rear, -0.16)], self.lining, inward=side > 0, name="wall-high"),
                sheet([[(side * (WALL - 0.02), 1.34, -0.3), (side * (WALL - 0.02), roof(-0.3) - 0.2, -0.3)], [(side * WALL, 1.34, rear), (side * WALL, roof(rear) - 0.2, rear)]],
                      self.lining, name="rear-pillar"),
                # the side window's frame, then the post between it and the windshield
                tube([(side * WALL, 1.12, -0.16), (side * WALL, 1.12, 0.8)], 0.03, self.lining),
                tube([(side * (WALL - 0.01), 1.34, -0.16), (side * (WALL - 0.01), roof(0.2) - 0.2, 0.2), (side * (WALL - 0.03), roof(0.8) - 0.19, 0.8)], 0.035, self.lining),
                tube([(side * (WALL - 0.01), 1.12, -0.16), (side * (WALL - 0.01), 1.36, -0.16)], 0.05, self.lining, flat=0.8),
                sheet([[(side * 1.04, LIP_LOW + 0.02, 1.2), (side * 1.12, LIP_LOW + 0.04, 1.06)], [(side * (WALL - 0.04), 1.52, 1.0), (side * WALL, roof(0.8) - 0.16, 0.86)]],
                      self.lining, name="post"),
            ])
        parts.extend([
            sheet([[(-WALL, roof(1.05) - 0.14, 1.04), (0, roof(1.05) + 0.1, 1.1), (WALL, roof(1.05) - 0.14, 1.04)],
                   [(-WALL, roof(0.9), 0.9), (0, roof(0.9) + 0.02, 0.9), (WALL, roof(0.9), 0.9)]], self.lining, name="header"),
            sheet([[(-1.04, LIP_LOW + 0.04, 1.5), (0, 1.1, 1.52), (1.04, LIP_LOW + 0.04, 1.5)], [(-WALL, roof(1.05) - 0.14, 1.04), (0, roof(1.05) + 0.1, 1.1), (WALL, roof(1.05) - 0.14, 1.04)]],
                  self.glass, name="windshield"),
            Box((0.075, 0.6, 0.05), at=(0, 1.36, 1.3), pitch=-30, material=self.lining),  # the middle post
            Cylinder(0.03, 0.05, at=(0, 1.46, 1.19), pitch=90, material=self.panel, segments=20),
            Box((0.1, 0.07, 0.07), at=(0, 1.51, 1.16), material=self.black),
            Box((0.12, 0.04, 0.015), at=(-0.28, 1.5, 0.98), roll=-6, material=self.black),  # a little mirror
            Cylinder(0.006, 0.05, at=(-0.28, 1.55, 0.98), material=self.panel, segments=10),
            picture((60, 20), "studio.view.city", at=(0, -0.7, 16), casts_shadow=False, name="view"),
            picture((60, 20), "studio.view.city", at=(-16, -0.7, 8), yaw=-90, casts_shadow=False, name="view-left"),
            picture((60, 20), "studio.view.city", at=(16, -0.7, 8), yaw=90, casts_shadow=False, name="view-right"),
        ])
        return parts

    def glareshield(self) -> list[Node]:
        arch = 2 * LIP_HIGH - LIP_LOW
        crown = LIP_LOW + 2 * (LIP_HIGH - LIP_LOW)
        lip = [(-1.04, LIP_LOW, LIP_Z), (0, crown, LIP_Z - 0.05), (1.04, LIP_LOW, LIP_Z)]
        down = [(x, y - 0.14, z + 0.015) for x, y, z in lip]
        parts: list[Node] = [
            sheet([lip, [(-1.04, LIP_LOW + 0.04, 1.5), (0, 1.1, 1.52), (1.04, LIP_LOW + 0.04, 1.5)]], self.panel, name="glareshield-top"),
            sheet([down, lip], self.panel, name="glareshield-face"),
            sheet([down, [(x, y, z + 0.2) for x, y, z in down]], self.black, name="glareshield-under"),
            picture((1.0, 0.11), "studio.screen.mcp", at=(0, LIP_HIGH - 0.07, LIP_Z - 0.045), casts_shadow=False, name="mcp"),
        ]
        for x in (-0.46, -0.28, -0.08, 0.2, 0.42):  # the autopilot's knobs
            parts.append(Cylinder(0.014, 0.022, at=(x, LIP_HIGH - 0.115, LIP_Z - 0.06), pitch=90, material=self.lever, segments=16))
        for side in (-1, 1):
            parts.append(Box((0.2, 0.012, 0.012), at=(side * 0.62, LIP_HIGH - 0.21, LIP_Z - 0.008), material="studio.glow.lip"))
            parts.append(picture((0.2, 0.09), "studio.screen.radios", at=(side * 0.72, LIP_HIGH - 0.09, LIP_Z - 0.02), roll=side * -8, casts_shadow=False))
        return parts

    def instruments(self) -> list[Node]:
        parts: list[Node] = [
            Box((2.62, 0.54, 0.05), at=(0, 0, 0.03), material=self.panel),
            Box((2.62, 0.5, 0.03), at=(0, -0.48, 0.2), material=self.black),
        ]
        for x, width, height, name in ((-0.27, 0.235, 0.235, "nd"), (0.27, 0.235, 0.235, "eicas"), (0, 0.235, 0.235, "nd"), (-0.57, 0.17, 0.215, "pfd"),
                                       (0.57, 0.17, 0.215, "pfd"), (-0.74, 0.09, 0.1, "standby"), (0.74, 0.09, 0.1, "standby")):
            parts.append(Box((width + 0.03, height + 0.03, 0.02), at=(x, 0.02, 0.0), material=self.black))
            parts.append(picture((width, height), f"studio.screen.{name}", at=(x, 0.02, -0.011), casts_shadow=False, name=name))
        return parts

    def yoke(self, side: int) -> list[Node]:
        """It stands on the floor between the pilot's knees, at x 0 of its group."""
        lever, black = self.lever, self.black
        parts: list[Node] = [
            tube([(0, 0.02, 0.2), (0, 0.45, 0.1), (0, YOKE_Y - 0.05, 0)], 0.024, black),
            Box((0.1, 0.09, 0.05), at=(0, YOKE_Y - 0.01, -0.01), material=lever),
            tube([(0, YOKE_Y, -0.02), (0.13, YOKE_Y - 0.01, -0.03), (YOKE_HALF, YOKE_Y + 0.05, -0.03), (YOKE_HALF, YOKE_Y + 0.14, -0.03)], 0.016, black),
            tube([(0, YOKE_Y, -0.02), (-0.13, YOKE_Y - 0.01, -0.03), (-YOKE_HALF, YOKE_Y + 0.05, -0.03), (-YOKE_HALF, YOKE_Y + 0.14, -0.03)], 0.016, black),
            Box((0.14, 0.05, 0.01), at=(0, YOKE_Y + 0.0, -0.04), material=self.panel),
            Box((0.09, 0.03, 0.002), at=(0, YOKE_Y + 0.0, -0.046), material="studio.glow.lamp"),
        ]
        for x in (-YOKE_HALF, YOKE_HALF):
            parts.append(tube([(x, YOKE_Y + 0.04, -0.03), (x, YOKE_Y + 0.15, -0.03)], 0.021, lever if x * side > 0 else black, samples=(10, 12)))
        return parts

    def pedestal(self) -> list[Node]:
        half = 0.2
        parts: list[Node] = [
            Box((2 * half, 0.5, 1.0), at=(0, 0.25, 0.48), material=self.panel),
            Box((2 * half, 0.26, 0.62), at=(0, 0.56, 0.72), pitch=-16, material=self.panel),
            Box((2 * half, 0.1, 0.5), at=(0, 0.53, 0.2), material=self.panel),
            Box((0.12, 0.05, 0.5), at=(0, 0.6, 0.34), material=self.black),  # the throttle quadrant
        ]
        for x in (-0.1, 0.1):
            parts.append(picture((0.17, 0.24), "studio.screen.cdu", at=(x, 0.7, 0.82), pitch=-74, casts_shadow=False, name="cdu"))
        for x in (-0.135, 0.135):
            parts.append(picture((0.1, 0.34), "studio.screen.radios", at=(x, 0.597, 0.36), pitch=-90, casts_shadow=False, name="quadrant"))
        parts.append(picture((0.38, 0.34), "studio.screen.radios", at=(0, 0.59, 0.0 + 0.1), pitch=-90, casts_shadow=False, name="radios"))
        parts.append(picture((0.38, 0.1), "studio.screen.mcp", at=(0, 0.655, 0.66), pitch=-74, casts_shadow=False, name="trim"))
        for x, z, top in ((-0.045, 0.34, 0.8), (0.045, 0.38, 0.8), (-0.11, 0.42, 0.74), (0.11, 0.42, 0.74)):
            parts.append(tube([(x, 0.66, z + 0.08), (x, 0.74, z + 0.02), (x, top, z)], 0.008, self.lever, samples=(14, 8)))
            parts.append(pillow((0.05, 0.03, 0.05), self.black, 0.4, at=(x, top + 0.012, z), samples=(16, 12)))
            parts.append(Box((0.008, 0.005, 0.4), at=(x, 0.692, z), material=self.black))
        for x in (-0.03, 0.03):
            parts.append(pillow((0.05, 0.045, 0.09), self.lever, 0.5, at=(x, 0.82, 0.32), samples=(16, 12)))
        parts.append(Box((0.1, 0.03, 0.025), at=(0, 0.82, 0.32), material=self.lever))
        return parts

    def overhead(self) -> list[Node]:
        z = 0.42
        y = roof(z) - 0.065
        parts: list[Node] = [picture((0.84, 1.28), "studio.screen.overhead", at=(0, y, z), pitch=90 - TILT, casts_shadow=False, name="overhead")]
        for row in range(9):
            for column in range(9):
                along = -0.56 + row * 0.14
                parts.append(Cylinder(0.007, 0.018, at=((column - 4) * 0.09, y - 0.009 + along * 0.2, z - along + 0.02), pitch=-TILT, material=self.lever, segments=10))
        for side in (-1, 1):
            parts.extend([
                Box((0.2, 0.012, 0.13), at=(side * 0.72, roof(0.74) - 0.09, 0.74), pitch=-TILT, material=self.panel),  # a lamp's bezel
                Box((0.15, 0.012, 0.09), at=(side * 0.72, roof(0.74) - 0.097, 0.74), pitch=-TILT, material="studio.glow.lamp"),
                Box((0.3, 0.07, 0.012), at=(side * 0.72, roof(0.96) - 0.13, 0.96), pitch=-8, material=self.lining),  # a stowed visor
            ])
        return parts

    def console(self, side: int) -> list[Node]:
        parts: list[Node] = [
            pillow((0.32, 0.86, 1.2), self.lining, 0.2, at=(side * 1.16, 0.43, 0.42), samples=(32, 16)),
            pillow((0.26, 0.2, 1.0), self.lining, 0.3, at=(side * 1.17, 0.84, 0.44), samples=(24, 14)),
            pillow((0.16, 0.03, 0.34), self.panel, 0.3, at=(side * 1.13, 0.945, 0.56), samples=(16, 8)),
            pillow((0.3, 0.05, 0.4), self.lining, 0.35, at=(side * 1.12, 0.92, -0.05), samples=(20, 10)),
            Cylinder(0.02, 0.07, at=(side * 1.11, 0.98, 0.6), material=self.lever, segments=16),  # the tiller
        ]
        return parts

    def seat(self, side: int) -> list[Node]:
        """`side` is -1 for the captain's. The back leans 15 degrees, and the cushion's front stands 4 higher than its rear."""
        back: list[Node] = [
            pillow((0.5, 0.82, 0.13), self.panel, 0.32, 0.12, at=(0, 0.33, 0), samples=(40, 28)),
            pillow((0.4, 0.72, 0.1), self.cushion, 0.32, 0.1, at=(0, 0.33, 0.045), samples=(32, 20)),
        ]
        for edge in (-1, 1):
            back.append(pillow((0.08, 0.92, 0.17), self.piping, 0.5, at=(edge * 0.245, 0.36, 0.0), roll=edge * 2.5, samples=(20, 280)))
            ribs = back[-1]
            ribs.x += "+0.002*sin(9000*sin(v))*cos(u)"
            ribs.z += "+0.002*sin(9000*sin(v))*sin(u)"
        back.append(pillow((0.46, 0.07, 0.17), self.piping, 0.5, at=(0, 0.8, 0.0), samples=(40, 14)))
        parts: list[Node] = [
            Box((0.36, 0.3, 0.42), at=(0, 0.17, 0.02), material=self.black),
            Box((0.5, 0.03, 0.04), at=(0, 0.02, 0.3), material=self.lever),
            Box((0.5, 0.03, 0.04), at=(0, 0.02, -0.26), material=self.lever),
            pillow((0.5, 0.1, 0.5), self.panel, 0.34, at=(0, 0.38, 0.02), pitch=4),
            pillow((0.46, 0.1, 0.48), self.cushion, 0.4, at=(0, 0.46, 0.03), pitch=4),
            Group(back, at=(0, 0.42, -0.25), pitch=15, name="back"),
        ]
        for edge in (-1, 1):
            parts.append(Group([pillow((0.075, 0.09, 0.34), self.cloth, 0.55, at=(0, 0.0, 0.0), samples=(28, 18)),
                                Box((0.03, 0.2, 0.03), at=(0, -0.1, -0.13), material=self.black)],
                               at=(edge * 0.285, 0.7, 0.03), pitch=7, name=f"arm-{edge}"))
        return parts

    def pedals(self, side: int) -> list[Node]:
        parts: list[Node] = []
        for x in (-0.13, 0.13):
            parts.append(Box((0.1, 0.24, 0.02), at=(x, 0.2, 0.02), pitch=-20, material=self.lever))
            parts.append(Box((0.03, 0.22, 0.03), at=(x, 0.1, 0.09), pitch=-20, material=self.black))
        return parts

    def lights(self) -> list[Node]:
        parts: list[Node] = [
            Point(1.1, color="#aebaf0", at=(0, 1.42, 0.35), reach=3.0, name="dome"),
            Point(0.22, color="#ffc48a", at=(0, 0.95, 0.6), reach=1.6, name="pedestal"),
            Point(0.22, color="#8d9bea", at=(0, 1.5, -0.8), reach=1.7, name="rear"),
            Point(0.7, color="#f2b9a0", at=(0, 1.5, 2.3), reach=3.4, name="dusk"),
        ]
        for side in (-1, 1):
            parts.extend([
                Point(0.12, color="#7f93ff", at=(side * 0.62, 0.9, 0.5), reach=0.9, name=f"flood-{side}"),
                Point(0.4, color="#c9c6f4", at=(side * 1.45, 1.25, 0.4), reach=2.0, name=f"side-{side}"),
                Spot(0.8, color="#ffe2c0", at=(side * 0.52, 1.5, 0.3), yaw=0, pitch=-85, cone=60, reach=1.8, name=f"chart-{side}"),
            ])
        return parts

    def build(self) -> Sequence[Node]:
        parts: list[Node] = [*self.shell(), *self.glareshield(), Group(self.instruments(), at=(0, PANEL_Y, PANEL_Z), pitch=-LEAN, name="panel"),
                             *self.pedestal(), *self.overhead(), *self.lights()]
        for side in (-1, 1):
            parts.append(Group(self.seat(side), at=(side * SEAT_X, 0, SEAT_Z), name=f"seat-{side}"))
            parts.append(Group(self.yoke(side), at=(side * SEAT_X, 0, YOKE_Z), name=f"yoke-{side}"))
            parts.append(Group(self.pedals(side), at=(side * SEAT_X, 0, 0.81), name=f"pedals-{side}"))
            parts.extend(self.console(side))
        return parts


class FlightDeckPlugin(Plugin):
    name = "flight-deck"
    version = "1.0.0"
    requires = ("stock",)
    shaders, slots = SHADERS, SLOTS

    def register(self, registry: Registry) -> None:
        registry.prefabs.add("air.flight-deck", FlightDeck)
