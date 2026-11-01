"""The first use cases, rendered to renders/. Run: .venv/bin/python examples/use_cases.py [wireframe|shaded]"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from srlocations import Blueprint, Library, Location, Registry, Renderer
from srlocations.stock.prefabs import Room, door, window

OUT = ROOT / "renders"


def office(registry: Registry) -> Location:
    """Use case 1: a set dressed by hand, from objects."""
    location = Location("detective-office", registry)
    location.add(Room(7, 5.5, 2.9, walls="stock.plaster.sage", north=[window(-1.6), window(1.6)], west=[door(1.2)]))
    location.add("stock.rug", at=(0.2, 0, 0.3))
    location.add("stock.table", width=1.7, depth=0.85, at=(0.8, 0, 1.3))
    location.add("stock.chair", at=(0.8, 0, 1.95))
    location.add("stock.chair", seat="stock.fabric.rust", at=(0.8, 0, 0.5), yaw=180)
    location.add("stock.bookshelf", width=2.0, at=(3.3, 0, 0.2), yaw=90, seed=7)
    location.add("stock.sofa", at=(-2.2, 0, -1.2), yaw=90)
    location.add("stock.floor-lamp", at=(-3.0, 0, -2.3))
    location.add("stock.pendant-lamp", ceiling=2.9, at=(0.8, 0, 1.3), candela=5)
    location.add("stock.plant", at=(-3.0, 0, 2.2))
    location.rig("stock.interior")
    location.mark("detective", (0.8, 0, 2.0), facing=180).mark("client", (0.8, 0, 0.3))
    location.shot("wide", (-2.4, 1.55, -2.55), (1.0, 0.95, 1.2), lens=22)
    location.shot("over-the-desk", (1.6, 1.45, -0.5), (0.8, 0.95, 2.0), lens=28)
    return location


def main() -> None:
    registry = Registry.default()
    registry.use(Library.from_file(ROOT / "examples/cafe-lib.json"))
    registry.plugins.load_file(ROOT / "examples/plugins/scifi.py")

    locations = {
        "1-office": (office(registry), ["wide", "over-the-desk"]),
        "2-street-day": (registry.archetypes.get("stock.street")().build(registry, seed=4), ["street-level", "overlook"]),
        "2-street-night": (registry.archetypes.get("stock.street")().build(registry, seed=4, night=True), ["street-level"]),
        "3-cafe-from-json": (Blueprint.load(ROOT / "examples/cafe.location.json").build(registry), ["wide"]),
        "4-scifi-plugin": (registry.archetypes.get("scifi.corridor")().build(registry), ["down-the-hall"]),
    }
    mode = f"stock.{sys.argv[1]}" if len(sys.argv) > 1 else None  # the renderer's default mode when not named
    label, renderer = (mode or "stock.wireframe").removeprefix("stock."), Renderer()
    for key, (location, shots) in locations.items():
        issues = location.validate()
        print(f"{key}: {len(location.solids())} solids, {len(location.lights())} lights, {len(issues)} issues")
        for issue in issues:
            print(f"  {issue.severity}: {issue.code}: {issue.message}")
        for shot in shots:
            print("  rendered", renderer.render(location, shot, OUT / label / f"{key}-{shot}.png", mode).name)


if __name__ == "__main__":
    main()
