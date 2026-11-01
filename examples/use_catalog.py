"""Project B: builds a showroom from the shared catalog alone. It never loads the sci-fi plugin that made the bulkhead.

Run: .venv/bin/python examples/use_catalog.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from srlocations import Location, Registry, Renderer, Shaded, SharedCatalog, Sphere, Traced
from srlocations.stock.prefabs import Room


def showroom(registry: Registry) -> Location:
    location = Location("showroom", registry)
    location.add(Room(9, 7, 3.2, floor="studio.floor.checker", walls="stock.plaster.cream"))
    location.add("studio.dining-set", at=(-2.0, 0, 1.2), yaw=20)
    location.add("studio.floor-lamp.warm", at=(-3.9, 0, 2.9))
    location.add("studio.floor-lamp.warm", at=(4.0, 0, -0.4))
    location.add("studio.bulkhead", at=(2.3, 0, 2.5))
    for index, shader in enumerate(("studio.copper.brushed", "studio.soap-film", "studio.car-paint.midnight")):
        location.add(Sphere(0.42, at=(0.5 + index * 1.05, 0.42, 0.0), material=shader, segments=64))
    location.rig("stock.interior", fill=0.9)
    location.shot("wide", (-0.4, 1.75, -3.3), (0.2, 0.8, 1.0), lens=20)
    return location


def offices(registry: Registry) -> Location:
    """One table and one bookcase, reused at three sizes and in three finishes."""
    location = Location("offices", registry)
    location.add(Room(13, 8, 3.0, floor="stock.wood.oak", walls="stock.plaster.white"))
    location.add("studio.meeting-table", variant="boardroom", at=(-2.4, 0, 1.5))
    location.add("studio.meeting-table", variant="huddle", at=(-1.2, 0, -2.4), shaders={"seat": "stock.fabric.teal"})
    location.add("studio.meeting-table", length=2.6, spacing=0.7, pendants=1, at=(2.5, 0, -1.9),
                 shaders={"top": "studio.soap-film", "seat": "stock.fabric.rust"})
    location.add("studio.bookcase", variant="wall", at=(3.6, 0, 3.8))
    location.add("studio.bookcase", variant="low", at=(5.4, 0, 0.6), yaw=90, shaders={"wood": "stock.wood.walnut", "back": "stock.fabric.teal"})
    location.add("studio.bookcase", width=1.0, height=1.8, at=(-0.8, 0, 3.8))
    location.add("studio.dining-set", at=(5.2, 0, -3.0), shaders={"seat": "stock.fabric.teal"})
    location.rig("stock.interior", fill=0.7)
    location.shot("wide", (-6.1, 1.7, -3.75), (1.0, 0.7, 0.6), lens=18)
    return location


def main() -> None:
    catalog = SharedCatalog.open(ROOT / "catalog")
    registry = Registry.default().use(catalog)
    assert "scifi" not in registry.plugins.loaded
    location = showroom(registry)
    print("issues:", location.validate() or "none")
    print("pins:", catalog.pins(location))
    renderer = Renderer()
    print(renderer.render(location, "wide", ROOT / "renders/wireframe/5-catalog-showroom.png").name)
    print(renderer.render(location, "wide", ROOT / "renders/shaded/5-catalog-showroom.png", Shaded()).name)
    reused = offices(registry)
    print("issues:", reused.validate() or "none")
    print("pins:", catalog.pins(reused))
    print(renderer.render(reused, "wide", ROOT / "renders/wireframe/6-reusable-props.png").name)
    print(renderer.render(reused, "wide", ROOT / "renders/shaded/6-reusable-props.png", Shaded()).name)
    parked = catalog.location("grand-tourer", registry=registry)  # a whole location
    print("issues:", parked.validate() or "none")
    print("pins:", catalog.pins(parked))
    print(renderer.render(parked, "from-the-door", ROOT / "renders/wireframe/7-grand-tourer.png").name)
    for shot in parked.shots:
        print(renderer.render(parked, shot, ROOT / f"renders/traced/7-grand-tourer-{shot}.png", Traced(1422, 711)).name)


if __name__ == "__main__":
    main()
