"""One room, untouched, drawn in looks that differ by texture and material, with paint and a decal that belong to one look.
Run: .venv/bin/python examples/texture_looks.py. The textures are drawn here, so the example needs no files."""
import math
import random
import struct
import sys
import zlib
from dataclasses import replace
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from paintover import HOME, living_room

from srlocations import Decal, Flat, Ink, Lit, Location, Look, PaintLayer, Registry, Renderer, Shaded, Styled, Texture
from srlocations.stock.looks import ink_toon

OUT = ROOT / "renders/looks"
TEXTURES = ROOT / "examples/textures"
SIZE = 256
Color = tuple[int, int, int]


def write_png(path: Path, pixel: Callable[[int, int], Color]) -> Path:
    def chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data))
    rows = b"".join(b"\0" + bytes(v for x in range(SIZE) for v in pixel(x, y)) for y in range(SIZE))
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", SIZE, SIZE, 8, 2, 0, 0, 0))
                     + chunk(b"IDAT", zlib.compress(rows)) + chunk(b"IEND", b""))
    return path


def grey(value: float) -> Color:
    level = round(255 * max(0.0, min(1.0, value)))
    return level, level, level


def hatch(x: int, y: int) -> Color:
    """Pencil strokes, heavy one way and light the other. Every term repeats across the tile."""
    turn = 2 * math.pi / SIZE
    wander = 0.3 * math.sin(turn * x) + 0.25 * math.sin(turn * 3 * y)
    strokes = 0.5 + 0.5 * math.cos(turn * 12 * (x + y) + wander)
    cross = 0.5 + 0.5 * math.cos(turn * 5 * (x - y) + wander)
    return grey(1 - 0.3 * strokes ** 40 - 0.1 * cross ** 60)


def halftone(x: int, y: int) -> Color:
    """Printed dots on a staggered grid."""
    cell = SIZE / 8
    u, v = (x / cell) % 1, ((y + (cell / 2 if int(x / cell) % 2 else 0)) / cell) % 1
    return grey(0.66 if math.hypot(u - 0.5, v - 0.5) < 0.3 else 1.0)


def drafting(x: int, y: int) -> Color:
    """Drafting film: fine squares inside a heavier one."""
    major, minor = x % SIZE < 3 or y % SIZE < 3, x % (SIZE // 5) < 1 or y % (SIZE // 5) < 1
    return (122, 170, 226) if major else (58, 110, 182) if minor else (24, 66, 138)


def brick(x: int, y: int) -> Color:
    rows, columns, rough = 8, 4, random.Random(x // 3 * 97 + y // 3).random() * 0.1
    row = y * rows // SIZE
    across = (x + (SIZE // (columns * 2) if row % 2 else 0)) % SIZE
    if y % (SIZE // rows) < 5 or across % (SIZE // columns) < 6:
        return grey(0.72 + rough)
    shade = 0.72 + 0.28 * random.Random(row * 31 + across * columns // SIZE).random() + rough
    return round(170 * shade), round(82 * shade), round(62 * shade)


def planks(x: int, y: int) -> Color:
    boards = 4
    board = x * boards // SIZE
    if x % (SIZE // boards) < 4:
        return 58, 38, 24
    turn = 2 * math.pi / SIZE
    seed = random.Random(board).random() * 6
    grain = 0.5 + 0.5 * math.sin(turn * 24 * x + seed + 1.4 * math.sin(turn * y + seed))
    shade = 0.76 + 0.14 * grain + 0.1 * random.Random(board * 7).random()
    return round(176 * shade), round(122 * shade), round(74 * shade)


def textures() -> dict[str, Path]:
    TEXTURES.mkdir(exist_ok=True)
    return {name: write_png(TEXTURES / f"{name}.png", draw) for name, draw in
            (("hatch", hatch), ("halftone", halftone), ("drafting", drafting), ("brick", brick), ("planks", planks))}


def looks(maps: dict[str, Path]) -> dict[str, Look]:
    """Every difference below is a look's: none of it touches the location."""
    return {
        "example.pencil": Look([Flat(), Ink(color="#35312c", width=1.3, vary=0.5, wobble=1.6)], sky="#f6f1e4",
                               name="example.pencil", textures={"": Texture(maps["hatch"], tile=0.9, tint="#f6f1e4")}),
        "example.comic": replace(ink_toon(HOME, cut=0.42), name="example.comic",
                                 textures={"": Texture(maps["halftone"], tile=0.3)}),
        "example.blueprint": Look([Flat(), Ink(color="#e8f1ff", width=1.2, vary=0.15, wobble=0.0)], sky="#18428a",
                                  name="example.blueprint", textures={"": Texture(maps["drafting"], tile=1.0, tint="#ffffff")}),
        "example.loft": Look([Lit()], name="example.loft",
                             textures={"stock.plaster": Texture(maps["brick"], tile=1.0, tint="#ffffff"),
                                       "stock.wood.oak": Texture(maps["planks"], tile=0.9, tint="#ffffff")},
                             materials={"stock.fabric.teal": "stock.fabric.rust"}),
    }


def stick_figure(layer: PaintLayer, mark, height: float) -> None:
    """A figure as a storyboard artist draws one, on a card that turns to the camera."""
    h, ink = height, {"color": "#35312c", "width": 0.012}
    card = PaintLayer("stick")
    head = [(0.085 * h * math.cos(i * math.pi / 4), 0.8 * h + 0.085 * h * math.sin(i * math.pi / 4)) for i in range(8)]
    card.stroke(head, closed=True, **ink)
    card.stroke([(0, 0.72 * h), (0.01 * h, 0.36 * h)], **ink)
    card.stroke([(-0.2 * h, 0.44 * h), (0, 0.64 * h), (0.2 * h, 0.46 * h)], **ink)
    card.stroke([(-0.14 * h, 0), (0.01 * h, 0.36 * h), (0.14 * h, 0)], **ink)
    layer.standee(mark.at, card.items)


def annotate(location: Location) -> None:
    """What belongs to one look: paint for three of them, and a decal only the comic has."""
    pencil = location.paint("storyboard", looks=["example.pencil"])
    for mark in location.marks.values():
        stick_figure(pencil, mark, 1.5)

    plan = location.paint("dimensions", looks=["example.blueprint"])
    line = {"color": "#ffffff", "width": 0.01, "smooth": False}
    plan.stroke([(-3.75, 2.55, 2.74), (3.75, 2.55, 2.74)], **line)
    for x in (-3.75, 3.75):
        plan.stroke([(x, 2.47, 2.74), (x, 2.63, 2.74)], **line)
    for mark in location.marks.values():
        x, _, z = mark.at
        y = 0.02
        plan.stroke([(x - 0.3, y, z), (x + 0.3, y, z)], **line).stroke([(x, y, z - 0.3), (x, y, z + 0.3)], **line)
        plan.disc((x, y, z), 0.05, color="#ffffff")

    def burst(scale: float) -> list[tuple[float, float]]:
        return [(0.1 + scale * r * math.cos(i * math.pi / 8), 0.18 + 1.6 * scale * r * math.sin(i * math.pi / 8))
                for i in range(16) for r in [0.09 if i % 2 else 0.05]]
    pop = location.paint("burst", looks=["example.comic"])
    pop.fill(burst(1.0), color="#e8432e", frame=True).fill(burst(0.74), color="#ffd23f", frame=True)
    star = [(0.32 * (1 if i % 2 else 0.45) * math.cos(i * math.pi / 5), 0.32 * (1 if i % 2 else 0.45) * math.sin(i * math.pi / 5))
            for i in range(10)]
    location.add(Decal(star, material="home.art.sun", looks=["example.comic"], name="star", at=(0.3, 1.8, 2.74)))


def main() -> None:
    registry = Registry.default()
    styles = looks(textures())
    for name, look in styles.items():
        registry.modes.add(name, lambda look=look, **params: Styled(look, **params))
    room = living_room(registry, ("stock.ink-toon", "example.comic"))
    annotate(room)
    print("issues:", room.validate() or "none")
    renderer = Renderer()
    for name, look in styles.items():
        print(renderer.render(room, "wide", OUT / f"room-{name.split('.')[1]}.png", Styled(look)).name)
    print(renderer.render(room, "wide", OUT / "room-plain-shaded.png", Shaded()).name)
    print(renderer.archive(room, "wide", OUT / "room-comic.vpkg.zip", Styled(styles["example.comic"])).name)


if __name__ == "__main__":
    main()
