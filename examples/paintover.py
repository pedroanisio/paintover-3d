"""Native paintover: one 3D set, drawn as a cartoon and as paper cut-outs, with paint on it and over it.
Run: .venv/bin/python examples/paintover.py. The figures are placeholders painted at the location's marks."""
import sys
from pathlib import Path
from typing import Sequence

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from srlocations import Decal, Group, Location, Material, PaintLayer, Registry, Renderer, Shaded, Styled, Wireframe
from srlocations.stock.looks import ink_toon, paper_cutout
from srlocations.stock.prefabs import Room, door, window

OUT = ROOT / "renders/looks"
CARTOONS = ("stock.ink-toon", "stock.paper-cutout")  # the painted figures belong to these; a real render gets real actors
HOME = {"stock.plaster.cream": "#f4a6c0", "stock.wood.oak": "#c98b45", "stock.fabric.teal": "#3f8fd2",
        "stock.fabric.rust": "#d9622b", "stock.glass": "#bfe9fb"}
TOWN = {"stock.concrete": "#f4f7fb", "stock.asphalt": "#d5dde6", "stock.plaster.white": "#ffffff",
        "stock.brick.red": "#c8553d", "stock.brick.tan": "#d8a24a", "stock.plaster.cream": "#7fb069",
        "stock.leaf.green": "#2f7d4f", "stock.bark.brown": "#6b4226"}


def figure(layer: PaintLayer, mark, skin: str, top: str, legs: str, hat: str = "", height: float = 1.2) -> None:
    """A simple placeholder person: paper on a card that stands on a mark and turns to face every camera."""
    h = height
    card = PaintLayer("figure")
    card.fill([(-0.17 * h, 0.28 * h), (0.17 * h, 0.28 * h), (0.15 * h, 0), (-0.15 * h, 0)], color=legs)
    card.fill([(-0.24 * h, 0.68 * h), (0.24 * h, 0.68 * h), (0.2 * h, 0.24 * h), (-0.2 * h, 0.24 * h)], color=top)
    card.disc((0, 0.83 * h), 0.2 * h, color=skin)
    if hat:
        card.fill([(-0.21 * h, 0.88 * h), (-0.15 * h, 1.04 * h), (0, 1.09 * h), (0.15 * h, 1.04 * h), (0.21 * h, 0.88 * h)],
                  color=hat, smooth=True)
    for side in (-1, 1):
        card.disc((side * 0.07 * h, 0.86 * h), 0.055 * h, color="#ffffff")
        card.disc((side * 0.065 * h, 0.85 * h), 0.022 * h, color="#000000")
    card.stroke([(-0.07 * h, 0.75 * h), (0, 0.72 * h), (0.07 * h, 0.75 * h)], width=0.012 * h)
    layer.standee(mark.at, card.items)


def contact(layer: PaintLayer, mark, radius: float = 0.34) -> None:
    """A shadow pooled on the floor, in world space, so it lies down with the perspective."""
    x, y, z = mark.at
    layer.fill([(x - radius, y + 0.01, z), (x, y + 0.01, z - radius * 0.7), (x + radius, y + 0.01, z),
                (x, y + 0.01, z + radius * 0.7)], color="#000000", smooth=True)


def living_room(registry: Registry, cartoons: Sequence[str] = CARTOONS) -> Location:
    registry.materials.add("home.art.sky", Material("#ffd27a"), override=True)
    registry.materials.add("home.art.hill", Material("#4fa66b"), override=True)
    registry.materials.add("home.art.frame", Material("#7a4a24"), override=True)
    registry.materials.add("home.art.sun", Material("#f2552c"), override=True)
    location = Location("living-room", registry)
    location.add(Room(7.5, 5.5, 2.8, walls="stock.plaster.cream", floor="stock.wood.oak",
                      north=[window(2.3)], west=[door(0.6)]))
    location.add("stock.rug", at=(-0.6, 0, 0.3))
    location.add("stock.sofa", at=(-0.8, 0, 2.2))
    location.add("stock.table", width=1.1, depth=0.6, height=0.42, top="stock.wood.walnut", at=(-0.8, 0, 0.5))
    location.add("stock.floor-lamp", at=(-2.75, 0, 2.2))
    location.add("stock.plant", at=(3.1, 0, 2.2))
    wall = 2.75  # the room's inside face; -z comes off it into the room
    art = [Decal(((-1.0, -0.62), (1.0, -0.62), (1.0, 0.62), (-1.0, 0.62)), material="home.art.frame", name="frame",
                 at=(0, 0, -0.01)),
           Decal(((-0.92, -0.54), (0.92, -0.54), (0.92, 0.54), (-0.92, 0.54)), material="home.art.sky", name="sky",
                 at=(0, 0, -0.02)),
           Decal(((-0.92, -0.54), (-0.92, -0.08), (-0.5, 0.14), (-0.1, -0.1), (0.3, 0.1), (0.92, -0.2), (0.92, -0.54)),
                 material="home.art.hill", smooth=False, name="hills", at=(0, -0.24, -0.03)),
           Decal(((-0.2, 0), (-0.14, 0.14), (0, 0.2), (0.14, 0.14), (0.2, 0), (0.14, -0.14), (0, -0.2), (-0.14, -0.14)),
                 material="home.art.sun", smooth=True, name="sun", at=(0.5, 0.22, -0.03))]
    location.add(Group(art, at=(-1.6, 1.75, wall), name="painting"))
    location.rig("stock.interior", fill=0.5)
    location.mark("host", (1.1, 0, 0.9)).mark("guest", (-2.2, 0, -0.4))
    location.shot("wide", (0.5, 1.55, -2.65), (-0.6, 1.0, 2.2), lens=20)
    location.shot("corner", (3.1, 1.3, -2.4), (-0.8, 1.0, 1.4), lens=24)
    shade = location.paint("floor shadows", blend="multiply", opacity=0.3, looks=cartoons)
    cast = location.paint("cast", looks=cartoons)
    for name, colors in (("host", ("#ffcf3f", "#e8432e", "#2c5fa8", "")), ("guest", ("#c98a5a", "#37a0a0", "#3b2f4a", "#6a3fa0"))):
        contact(shade, location.marks[name])
        figure(cast, location.marks[name], *colors, height=1.45 if name == "host" else 1.3)
    return location


def town(registry: Registry) -> Location:
    location = registry.archetypes.get("stock.street")().build(registry, seed=4, length=60)
    location.mark("left", (-1.6, 0, 8)).mark("middle", (0.1, 0, 7.4)).mark("right", (1.7, 0, 8))
    location.shot("town", (0, 1.25, -1.5), (0, 2.1, 24), lens=26)
    shade = location.paint("snow shadows", blend="multiply", opacity=0.22, looks=CARTOONS)
    cast = location.paint("cast", looks=CARTOONS)
    for name, colors in (("left", ("#ffd9b0", "#3a7bd5", "#3a3a4a", "#e0453a")), ("middle", ("#c98a5a", "#e8a32e", "#5a4632", "#2f9e6b")),
                         ("right", ("#ffd9b0", "#b14fc4", "#2c3e70", "#3fb5c4"))):
        contact(shade, location.marks[name], 0.42)
        figure(cast, location.marks[name], *colors)
    location.paint("sky", shots=["town"]).disc((0.5, 0.17), 0.08, color="#ffe066", frame=True)
    return location


def main() -> None:
    registry = Registry.default()
    renderer = Renderer()
    room, street = living_room(registry), town(registry)
    print("issues:", room.validate() or "none", street.validate() or "none")
    for shot in room.shots:
        print(renderer.render(room, shot, OUT / f"room-{shot}-ink-toon.png", Styled(ink_toon(HOME, cut=0.42))).name)
    print(renderer.render(room, "wide", OUT / "room-wide-paper.png", Styled(paper_cutout(HOME))).name)
    print(renderer.render(room, "wide", OUT / "room-wide-shaded.png", Shaded()).name)
    print(renderer.render(room, "wide", OUT / "room-wide-wireframe.png", Wireframe()).name)
    print(renderer.render(street, "town", OUT / "town-paper.png", Styled(paper_cutout(TOWN))).name)
    print(renderer.render(street, "town", OUT / "town-ink-toon.png", Styled(ink_toon(TOWN))).name)


if __name__ == "__main__":
    main()
