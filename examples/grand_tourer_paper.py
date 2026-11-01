"""The published grand tourer as paper cut-outs, with paint over it. The catalog's location stays as it is: paint goes on
a copy built here, and adds what a flat cut-out loses: needles and hands, a reflection, shade in the seat's folds, cloud.

Run: .venv/bin/python examples/grand_tourer_paper.py"""
import math
import sys
from dataclasses import replace
from pathlib import Path
from typing import Sequence

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from srlocations import Location, Renderer, SharedCatalog, Styled
from srlocations.stock.looks import paper_cutout

OUT = ROOT / "renders/looks"
PAPER = {"studio.leather.cognac": "#d9772e", "studio.leather.spruce": "#23423e", "studio.leather.ink": "#26262e",
         "studio.veneer.ebony": "#5a2c1a", "studio.piano.black": "#17171d", "studio.metal.satin": "#e6e4dc",
         "studio.metal.champagne": "#e2bb6a", "studio.paint.garnet": "#d3232b", "studio.mirror.glass": "#bfe0e6",
         "studio.carpet.ink": "#34343e", "studio.headliner.tan": "#8d6f50", "studio.stitch.linen": "#fbe7c6",
         "studio.gauge.face": "#123a48", "studio.conifer.dark": "#1f4a3c", "studio.hillside.dusk": "#3f6b58",
         "studio.haze.near": "#7f9fa0", "studio.haze.mid": "#a3bdbb", "studio.haze.far": "#c3d3cb",
         "studio.haze.valley": "#ecdcb8", "studio.from.stock.asphalt": "#55555f"}
SKY = "#9cc6cc"
HERO, DRIVER = "from-the-door", "drivers-seat"
LOOK = "stock.paper-cutout"
SEAT, SEAT_YAW, SEAT_DROP, BACK_HEIGHT, BACK_DEPTH, BACK_TILT = (0.37, 0.05), 0.0, 0.16, 0.33, -0.22, 19.0
Point = tuple[float, float, float]


def on_seat(x: float, y: float, z: float) -> Point:
    """A point in the passenger seat's own frame, in the world."""
    turn = math.radians(SEAT_YAW)
    return (SEAT[0] + x * math.cos(turn) + z * math.sin(turn), y - SEAT_DROP, SEAT[1] - x * math.sin(turn) + z * math.cos(turn))


def on_back(x: float, y: float, z: float) -> Point:
    """A point in the frame of the passenger seat's backrest, in the world."""
    tilt = math.radians(BACK_TILT)
    return on_seat(x, BACK_HEIGHT + y * math.cos(tilt) + z * math.sin(tilt), BACK_DEPTH + z * math.cos(tilt) - y * math.sin(tilt))


def dial(centre: Point, radius: float, pitch: float, angle: float) -> list[Point]:
    """A pointer from a dial's centre, `angle` degrees clockwise from straight up, on a face tilted back by `pitch`."""
    x, y, z = centre
    turn, tilt = math.radians(angle), math.radians(pitch)
    up = radius * math.cos(turn)
    return [(x, y, z), (x + radius * math.sin(turn), y + up * math.cos(tilt), z + up * math.sin(tilt))]


def instruments(location: Location) -> None:
    gauges = location.paint("gauges", shots=[DRIVER], looks=[LOOK])
    for x, reading in ((-0.46, 50), (-0.28, -70)):
        centre = (x, 0.72, 0.436)
        for tick in range(-120, 121, 30):
            gauges.stroke(dial(centre, 0.034, 6, tick)[1:] + dial(centre, 0.028, 6, tick)[1:], color="#cfe6ea", width=0.0016)
        gauges.stroke(dial(centre, 0.03, 6, reading), color="#ff5a3c", width=0.003)
        gauges.disc(centre, 0.005, color="#e2bb6a")
    clocks = location.paint("clocks", shots=[HERO, DRIVER], looks=[LOOK])
    for x, z, hours, minutes in ((0.25, 0.538, 60, 170), (0.36, 0.528, -30, 95), (0.47, 0.508, 120, -40)):
        clocks.stroke(dial((x, 0.655, z), 0.018, 0, hours), color="#fbe7c6", width=0.0035)
        clocks.stroke(dial((x, 0.655, z), 0.027, 0, minutes), color="#fbe7c6", width=0.0025)


def reflection(location: Location) -> None:
    """The road behind, in the door mirror's glass."""
    x, y, z = -1.08, 0.88, 0.427
    across, tall = 0.125, 0.065
    def glass(u: float, v: float) -> Point:
        turn = math.radians(-8)
        return (x + u * across * math.cos(turn), y + v * tall, z - u * across * math.sin(turn))
    mirror = location.paint("mirror", shots=[HERO, DRIVER], looks=[LOOK])
    mirror.fill([glass(-1, -0.15), glass(-0.5, 0.1), glass(0.1, -0.1), glass(0.6, 0.15), glass(1, -0.05), glass(1, -0.7), glass(-1, -0.7)],
                color="#6f9a8a", smooth=True)
    mirror.fill([glass(0.3, -0.75), glass(0.3, -0.1), glass(0.42, 0.45), glass(0.54, -0.1), glass(0.54, -0.75)], color="#1f4a3c")


def seat_folds(location: Location) -> None:
    """Shade where the hide folds, and a soft light on the crown of each lobe."""
    shade = location.paint("seat folds", blend="multiply", opacity=0.34, shots=[HERO], looks=[LOOK])
    shade.fill([on_back(0.03, 0.04, 0.1), on_back(0.03, 0.66, 0.09), on_back(0.075, 0.66, 0.09), on_back(0.115, 0.34, 0.1), on_back(0.1, 0.04, 0.1)],
               color="#9a4a3a", smooth=True)
    shade.fill([on_seat(-0.24, 0.42, -0.2), on_seat(0.24, 0.42, -0.2), on_seat(0.24, 0.42, -0.1), on_seat(0, 0.43, -0.07), on_seat(-0.24, 0.42, -0.1)],
               color="#9a4a3a", smooth=True)
    for z in (0.02, 0.14):
        shade.stroke([on_seat(-0.13, 0.41, z), on_seat(0, 0.42, z + 0.012), on_seat(0.13, 0.41, z)], color="#7a3a2a", width=0.009)
    shine = location.paint("seat light", opacity=0.12, shots=[HERO], looks=[LOOK])
    shine.fill([on_back(0.13, 0.12, 0.09), on_back(0.15, 0.4, 0.09), on_back(0.13, 0.62, 0.08), on_back(0.17, 0.4, 0.07)], color="#ffe6bd", smooth=True)


def weather(location: Location, shot: str, clouds: Sequence[tuple[float, float, float]]) -> None:
    sky = location.paint(f"cloud {shot}", opacity=0.92, shots=[shot], looks=[LOOK])
    for x, y, size in clouds:
        for dx, dy, r in ((-1.6, 0.25, 0.5), (-0.7, 0, 0.8), (0.35, -0.15, 1.0), (1.3, 0.1, 0.72), (2.1, 0.32, 0.42)):
            sky.disc((x + dx * size * 0.5, y + dy * size), r * size, color="#ffffff", frame=True)


def painted(location: Location) -> Location:
    instruments(location)
    reflection(location)
    seat_folds(location)
    weather(location, HERO, [(0.8, 0.05, 0.022), (0.62, 0.09, 0.015)])
    weather(location, DRIVER, [(0.33, 0.09, 0.034), (0.56, 0.13, 0.024)])
    return location


def main() -> None:
    catalog = SharedCatalog.open(ROOT / "catalog")
    location = painted(catalog.location("grand-tourer"))
    print("issues:", location.validate() or "none")
    look = replace(paper_cutout(PAPER), sky=SKY)
    renderer = Renderer()
    for shot in location.shots:
        print(renderer.render(location, shot, OUT / f"grand-tourer-{shot}-paper.png", Styled(look, 1422, 711)).name)


if __name__ == "__main__":
    main()
