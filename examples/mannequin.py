"""A mannequin on a set: every stock pose, figures seated in the office, what each one sees, and limbs solved to points. Run: .venv/bin/python examples/mannequin.py

Each picture goes into renders/mannequin/. The car needs the published catalog and the grand tourer plugin.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT), str(ROOT / "examples")]

from fit_check import DRIVER, SEAT, seated
from use_cases import office

from srlocations import Blueprint, Location, Registry, Renderer, SharedCatalog, Sky, Sun
from srlocations.stock.mannequin import KINDS, POSES, Mannequin, Pose

OUT = ROOT / "renders" / "mannequin"
ROW = 1.9
DEPTH = 2.2  # metres between the two rows of poses


def poses(registry: Registry) -> Location:
    """Every pose in two staggered rows on a plain floor, with shots from the front, the back and three quarters."""
    location = Location("mannequin-poses", registry)
    location.add("stock.box", size=(19, 0.1, 9), at=(0, -0.05, -1.1), material="stock.plaster.cream")
    location.nodes.extend([Sky(1.2, zenith="#dfe6ee", horizon="#f3efe6", ground="#b8b0a0"),
                           Sun(2.5, yaw=-30, pitch=-50, shadows=True, softness=0.4)])
    location.background = "#e8e6e0"
    front = (len(POSES) + 1) // 2
    for index, name in enumerate(POSES):
        row, place = divmod(index, front)
        across = (place - (front - 1) / 2) * ROW + row * ROW / 2  # the back row stands in the gaps of the front one
        location.add(Mannequin(pose=name, at=(across, 0, -row * DEPTH), name=name))
    location.shot("front", (0, 5, 16), (0, 0.6, -1.1), lens=30)
    location.shot("back", (0, 5, -18), (0, 0.6, -1.1), lens=30)
    location.shot("turned", (12, 2.4, 11), (0, 0.7, -1.1), lens=30)
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


def floor(registry: Registry, name: str) -> Location:
    location = Location(f"mannequin-{name}", registry)
    location.add("stock.box", size=(8, 0.1, 6), at=(0, -0.05, 0), material="stock.plaster.cream")
    location.nodes.extend([Sky(1.2, zenith="#dfe6ee", horizon="#f3efe6", ground="#b8b0a0"),
                           Sun(2.5, yaw=-30, pitch=-50, shadows=True, softness=0.4)])
    location.background = "#e8e6e0"
    return location


def reaching(registry: Registry) -> Location:
    """Two figures put a hand over the same spot of a table, one with the elbow toward the floor and one with it out."""
    location = floor(registry, "reach")
    for index, (name, pole) in enumerate((("elbow-down", (-0.5, 0.9, 0.0)), ("elbow-out", (-1.0, 1.8, 0.1)))):
        x = (index - 0.5) * 1.6
        location.add("stock.box", size=(0.6, 0.9, 0.5), at=(x - 0.45, 0.45, 0.45), material="stock.wood.oak")
        location.add(Mannequin(name=name, at=(x, 0, 0)))
        location.reach(name, "left_hand", (x - 0.4, 1.08, 0.3), pole=(x + pole[0], pole[1], pole[2]))  # a pole beside the arm
    location.shot("front", (0, 1.4, 4.2), (0, 0.9, 0), lens=35)
    return location


def squat(registry: Registry) -> Location:
    """A squat with both feet planted, as one still: the figure at the bottom and ghosts on the way down."""
    location = floor(registry, "squat")
    figure = location.add(Mannequin(name="squatter", adjust={"spine.front_back": -10}))
    location.move(figure, 1.0, at=(0, -0.25, -0.15), ease="ease-in-out")  # deeper, the ankles run out of range and the toes dig in
    location.plant(figure, "left_foot").plant(figure, "right_foot")
    location.shot("side", (3.2, 1.0, 0.6), (0, 0.6, 0), lens=35)
    return location.onion(1.0, (0.0, 0.5))


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

    survey = Location("mannequin-survey", registry)
    survey.add("stock.box", size=(12, 0.1, 5), at=(0, -0.05, 0), material="stock.plaster.cream")
    survey.nodes.extend([Sky(1.2, zenith="#dfe6ee", horizon="#f3efe6", ground="#b8b0a0"), Sun(2.5, yaw=-30, pitch=-50, shadows=True, softness=0.4)])
    survey.background = "#e8e6e0"
    measured = [name for name in KINDS if KINDS[name].measured]
    for index, name in enumerate(measured):
        survey.add(Mannequin(pose="stand", kind=name, at=((index - (len(measured) - 1) / 2) * 1.0, 0, 0), name=name))
    survey.shot("line", (0, 1.1, 8), (0, 0.9, 0), lens=35)
    renderer.render(survey, "line", OUT / "people-survey.png", "stock.shaded")

    renderer.render(reaching(registry), "front", OUT / "reach-poles.png", "stock.shaded")
    renderer.render(squat(registry), "side", OUT / "squat-onion.png", "stock.shaded")

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
    room.look("detective", "client")
    room.look("client", "detective")
    room.frame("stock.two-shot", "detective", "client", name="two-shot")
    room.frame("stock.close-up", "detective", name="close-up")
    room.frame("stock.over-the-shoulder", "client", "detective", name="over-the-shoulder")
    room.repose("visitor", Pose(POSES["point"]).mirror())
    for issue in room.validate():
        print(issue)
    print(room.report())
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
