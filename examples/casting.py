"""A set with an imported model, real characters on its marks, and a house style that goes through a shared catalog.
Run: .venv/bin/python examples/casting.py. With SRSTUDIO_PYTHON set, srstudio's cast plays the finished looks and mannequins block the set; without it, mannequins
play every look."""
import math
import os
import sys
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from srlocations import Location, Mesh, Registry, Renderer, Shaded, SharedCatalog, Texture, Wireframe
from srlocations.stock.looks import ink_toon
from srlocations.stock.prefabs import Room, window
from paintover import HOME
from texture_looks import planks, write_png

OUT = ROOT / "renders/casting"
SEGMENTS = 24
BLOCKING = ("stock.wireframe", "stock.shaded")  # a mannequin is solid, so these show who hides what
FINISHED = ("studio.home", "stock.paper-cutout")  # a character is paint, so it goes on last and only here


def lathe(lines: list[str], material: str, profile: list[tuple[float, float]], center: tuple[float, float], base: int) -> int:
    """A shape turned on a lathe, written as OBJ: a thing no box, cylinder or cone can make. `profile` rises, so faces wind
    outward."""
    lines += [f"o {material}", f"usemtl {material}"]
    for radius, y in profile:
        for step in range(SEGMENTS):
            turn = 2 * math.pi * step / SEGMENTS
            lines.append(f"v {center[0] + radius * math.cos(turn):.5f} {y:.5f} {center[1] + radius * math.sin(turn):.5f}")
    for ring in range(len(profile) - 1):
        for step in range(SEGMENTS):
            a, b = ring * SEGMENTS + step, ring * SEGMENTS + (step + 1) % SEGMENTS
            c, d = a + SEGMENTS, b + SEGMENTS
            lines.append(f"f {base + a} {base + c} {base + d} {base + b}")
    return base + len(profile) * SEGMENTS


def lamp_table(folder: Path) -> Path:
    """A turned side table with a vase on it, in three materials."""
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "side-table.mtl").write_text("newmtl walnut\nKd 0.28 0.12 0.05\nnewmtl brass\nKd 0.9 0.6 0.15\n"
                                           "newmtl glaze\nKd 0.05 0.35 0.3\n")
    lines = ["mtllib side-table.mtl"]
    base = 1
    base = lathe(lines, "walnut", [(0.0, 0.14), (0.03, 0.14), (0.06, 0.28), (0.03, 0.42), (0.05, 0.54), (0.32, 0.57),
                                   (0.34, 0.6), (0.32, 0.62), (0.0, 0.62)], (0, 0), base)
    base = lathe(lines, "brass", [(0.0, 0.0), (0.26, 0.0), (0.24, 0.03), (0.05, 0.14), (0.0, 0.14)], (0, 0), base)
    lathe(lines, "glaze", [(0.0, 0.62), (0.05, 0.62), (0.12, 0.72), (0.14, 0.84), (0.09, 0.97), (0.04, 1.02), (0.06, 1.07),
                           (0.0, 1.07)], (0.04, 0), base)
    path = folder / "side-table.obj"
    path.write_text("\n".join(lines) + "\n")
    return path


def hire(registry: Registry) -> dict[str, tuple]:
    """Who stands on each mark, how tall, and in what pose. Nobody, without srstudio."""
    if not os.environ.get("SRSTUDIO_PYTHON"):
        return {}
    from srlocations.srstudio import SrstudioCast
    registry.plugins.load(SrstudioCast())
    return {"door": ("srstudio.milo", 1.75, {}), "sofa": ("srstudio.gary", 0.9, {"arms": "shrug", "mouth": "grin"}),
            "window": ("srstudio.dev", 1.8, {"arms": "shrug", "brows": "raised"}),
            "rug": ("srstudio.pip", 1.1, {"arms": "wave-a"})}  # Gary is a torso, so Gary sits


def room(registry: Registry) -> Location:
    location = Location("parlour", registry)
    location.add(Room(7.5, 5.5, 2.8, walls="stock.plaster.cream", floor="stock.wood.oak", north=[window(2.3)]))
    location.add("stock.rug", at=(-0.6, 0, 0.3))
    location.add("stock.sofa", at=(-0.8, 0, 2.2))
    location.add(Mesh(lamp_table(OUT / "models"), at=(1.45, 0, 1.75), name="side-table"))
    location.add(Mesh(OUT / "models" / "side-table.obj", at=(-2.9, 0, 2.0), scale=1.3, materials={"glaze": "stock.fabric.rust"},
                      name="tall-table"))
    location.rig("stock.interior", fill=0.5)
    location.mark("door", (1.55, 0, 2.4), facing=180).mark("window", (-2.3, 0, 1.5), facing=180).mark("rug", (0.3, 0, 1.0), facing=180)
    location.mark("sofa", (-1.0, 0.42, 1.8), facing=180)
    location.shot("wide", (0.5, 1.55, -2.65), (-0.2, 1.0, 2.2), lens=20)
    location.shot("corner", (3.1, 1.3, -2.4), (-0.8, 1.0, 1.4), lens=24)
    cast = hire(registry)
    blocking = BLOCKING if cast else ()
    location.stand("door", looks=blocking)
    location.stand("window", pose="point", looks=blocking)
    location.stand("rug", pose="walk", looks=blocking)
    location.stand("sofa", pose="sit", looks=blocking)
    for mark, (character, height, pose) in cast.items():
        location.cast(character, mark, height=height, pose=pose, shadow=0 if mark == "sofa" else 0.3, looks=FINISHED)
    return location


def house_style(registry: Registry) -> str:
    """The house style goes out to a catalog and comes back as a render mode, as it would on someone else's machine."""
    OUT.mkdir(parents=True, exist_ok=True)
    boards = Texture(write_png(OUT / "planks.png", planks), tile=1.6)
    look = replace(ink_toon(HOME, cut=0.42), name="home", textures={"stock.wood.oak": boards})
    catalog = SharedCatalog.create(OUT / "catalog", "studio")
    entry = catalog.publish_look("home", look, registry, tags=["toon"], description="The show's living-room style")
    print("published", entry.ref, "issues:", catalog.verify() or "none")
    registry.use(catalog)
    return "studio.home"


def main() -> None:
    registry = Registry.default()
    location = room(registry)
    style = house_style(registry)
    print("issues:", location.validate() or "none")
    renderer = Renderer()
    for shot in location.shots:
        print(renderer.render(location, shot, OUT / f"{shot}-house.png", style).name)
    print(renderer.render(location, "wide", OUT / "wide-paper.png", "stock.paper-cutout").name)
    print(renderer.render(location, "wide", OUT / "wide-shaded.png", Shaded()).name)
    print(renderer.render(location, "wide", OUT / "wide-wireframe.png", Wireframe(960, 540)).name)
    print(renderer.archive(location, "wide", OUT / "parlour.vpkg.zip", style).name)


if __name__ == "__main__":
    main()
