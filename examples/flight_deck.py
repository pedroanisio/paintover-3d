"""The published flight deck from every shot, empty and with its crew, then the first shot path traced. It needs only the
catalog. Run: .venv/bin/python examples/flight_deck.py"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from srlocations import Registry, Renderer, Shaded, SharedCatalog, Traced
from srlocations.stock.mannequin import Mannequin

OUT = ROOT / "renders/flight-deck"
HEIGHT = 1.75
SEAT = 0.52, 0.615, 0.07  # a pilot's hips: out from the middle, above the floor, along the aircraft
ARMS = {"upper_arm.down_up": -100, "upper_arm.front_back": -26, "lower_arm.stretch": -71, "lower_arm.twist_in_out": -40}  # solved to reach the yoke
LEGS = {"upper_leg.front_back": -84, "upper_leg.in_out": 4, "lower_leg.stretch": -68, "foot.up_down": -8}  # solved to reach the pedals
PILOT = {"hips.front_back": 14, **{f"{side}_{name}": value for side in ("left", "right") for name, value in (ARMS | LEGS).items()}}


def main() -> None:
    renderer, catalog = Renderer(), SharedCatalog.open(ROOT / "catalog")
    deck = catalog.location("flight-deck", registry=Registry.default())
    for shot in deck.shots:
        renderer.render(deck, shot, OUT / f"{shot}.png", Shaded(1200, 800))
    renderer.render(deck, "from-the-jump-seat", OUT / "from-the-jump-seat-traced.png", Traced(1200, 800, samples=128))
    for x, name in ((-SEAT[0], "captain"), (SEAT[0], "first-officer")):
        deck.add(Mannequin(pose="sit", adjust=PILOT, height=HEIGHT, grounded=False, solid=False, at=(x, SEAT[1] - 0.55 * HEIGHT, SEAT[2]), name=name))
    renderer.render(deck, "from-the-jump-seat", OUT / "crew.png", Shaded(1200, 800))


if __name__ == "__main__":
    main()
