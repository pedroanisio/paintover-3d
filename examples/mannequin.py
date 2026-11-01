"""A mannequin on a set: every stock pose, figures seated in the office, and what each one sees. Run: .venv/bin/python examples/mannequin.py

Each picture goes into renders/mannequin/. The car needs the published catalog and the grand tourer plugin.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT), str(ROOT / "examples")]

from fit_check import DRIVER, SEAT, seated
from use_cases import office

from srlocations import Blueprint, Location, Registry, Renderer, SharedCatalog, Sky, Sun
from srlocations.stock.mannequin import KINDS, POSES, Mannequin

OUT = ROOT / "renders" / "mannequin"
ROW = 1.9


def poses(registry: Registry) -> Location:
    """Every pose in a line on a plain floor, with shots from the front, the back and three quarters, and on a hand."""
    location = Location("mannequin-poses", registry)
    location.add("stock.box", size=(16, 0.1, 6), at=(0, -0.05, 0), material="stock.plaster.cream")
    location.nodes.extend([Sky(1.2, zenith="#dfe6ee", horizon="#f3efe6", ground="#b8b0a0"),
                           Sun(2.5, yaw=-30, pitch=-50, shadows=True, softness=0.4)])
    location.background = "#e8e6e0"
    for index, name in enumerate(POSES):
        location.add(Mannequin(pose=name, at=((index - (len(POSES) - 1) / 2) * ROW, 0, 0), name=name))
    location.shot("front", (0, 1.1, 15), (0, 0.85, 0), lens=30)
    location.shot("back", (0, 1.1, -15), (0, 0.85, 0), lens=30)
    location.shot("turned", (11, 1.3, 11), (0, 0.8, 0), lens=30)
    return location


def people(registry: Registry, name: str, figures: dict[str, dict]) -> Location:
    """Bodies in a line on a plain floor."""
    location = Location(f"mannequin-{name}", registry)
    location.add("stock.box", size=(12, 0.1, 6), at=(0, -0.05, 0), material="stock.plaster.cream")
    location.nodes.extend([Sky(1.2, zenith="#dfe6ee", horizon="#f3efe6", ground="#b8b0a0"),
                           Sun(2.5, yaw=-30, pitch=-50, shadows=True, softness=0.4)])
    location.background = "#e8e6e0"
    for index, (label, body) in enumerate(figures.items()):
        location.add(Mannequin(at=((index - (len(figures) - 1) / 2) * 0.95, 0, 0), name=label, **body))
    location.shot("front", (0, 1.0, 8.5), (0, 0.8, 0), lens=30)
    return location


def main() -> None:
    renderer, registry = Renderer(), Registry.default()
    sheet = poses(registry)
    for shot in sheet.shots:
        renderer.render(sheet, shot, OUT / f"poses-{shot}.png", "stock.shaded")
    renderer.render(sheet, "front", OUT / "poses-wireframe.png")
    renderer.render(sheet, "front", OUT / "poses-ink-toon.png", "stock.ink-toon")

    renderer.render(people(registry, "kinds", {kind: {"kind": kind} for kind in KINDS}), "front",
                    OUT / "people-kinds.png", "stock.shaded")
    renderer.render(people(registry, "seeds", {f"seed-{seed}": {"seed": seed} for seed in range(8)}), "front",
                    OUT / "people-seeds.png", "stock.shaded")

    room = office(registry)
    room.stand("detective", pose="sit")
    room.stand("client", pose="sit", adjust={"head.turn_left_right": -20})
    room.mark("visitor", (-1.2, 0, 0.6), facing=70)
    room.stand("visitor", pose="point", kind="woman", seed=4)
    room.mark("child", (2.2, 0, -0.3), facing=-60)
    room.stand("child", kind="child", seed=2)
    room.pov("detective")
    room.pov("client")
    room.pov("visitor")
    for issue in room.validate():
        print(issue)
    for shot in room.shots:
        renderer.render(room, shot, OUT / f"office-{shot}.png", "stock.shaded")

    catalog = ROOT / "catalog"
    registry = Registry.default()
    registry.plugins.load_file(ROOT / "examples/plugins/grand_tourer.py")
    registry.use(SharedCatalog.open(catalog))
    car = Blueprint.load(ROOT / "examples/grand-tourer.location.json").build(registry)
    seated(car, "driver", -0.37, SEAT, "drive", DRIVER, 1.78)
    car.stand("open-door", pose="stand")
    for shot in ("from-the-door", "drivers-seat"):
        renderer.render(car, shot, OUT / f"car-{shot}.png", "stock.shaded")


if __name__ == "__main__":
    main()
