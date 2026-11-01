"""Draws the pictures behind stock view materials into srlocations/stock/views. They are checked in, so this only runs to
change them. Run: .venv/bin/python examples/views.py"""
import math
import random
import struct
import zlib
from pathlib import Path
from typing import Sequence

OUT = Path(__file__).resolve().parent.parent / "srlocations/stock/views"
WIDTH, HEIGHT, HORIZON = 512, 256, 0.62  # the horizon is this far down the picture
Color = tuple[int, int, int]


def write(path: Path, rows: Sequence[list[Color]]) -> None:
    def chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data))
    data = b"".join(b"\0" + bytes(v for pixel in row for v in pixel) for row in rows)
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", WIDTH, HEIGHT, 8, 2, 0, 0, 0))
                     + chunk(b"IDAT", zlib.compress(data, 9)) + chunk(b"IEND", b""))


def mix(a: Color, b: Color, share: float) -> Color:
    return tuple(round(p + (q - p) * max(0.0, min(1.0, share))) for p, q in zip(a, b))


def sky(top: Color, low: Color) -> list[list[Color]]:
    return [[mix(top, low, y / (HEIGHT * HORIZON)) for _ in range(WIDTH)] for y in range(HEIGHT)]


def ridge(x: int, height: float, seed: float) -> float:
    return height * (0.6 + 0.25 * math.sin(x / 47 + seed) + 0.15 * math.sin(x / 13 + seed * 2))


def hills(rows: list[list[Color]], layers: Sequence[tuple[float, Color]]) -> None:
    ground = HEIGHT * HORIZON
    for number, (height, color) in enumerate(layers):
        for x in range(WIDTH):
            for y in range(int(ground - ridge(x, height, number * 1.7)), HEIGHT):
                rows[y][x] = color
        ground += 8


def clouds(rows: list[list[Color]], color: Color, rng: random.Random) -> None:
    for _ in range(9):
        cx, cy, reach = rng.randrange(WIDTH), rng.randrange(int(HEIGHT * 0.4)), rng.randrange(30, 70)
        for y in range(max(0, cy - 12), min(HEIGHT, cy + 12)):
            for x in range(cx - reach, cx + reach):
                near = 1 - ((x - cx) / reach) ** 2 - ((y - cy) / 12) ** 2
                if near > 0:
                    rows[y][x % WIDTH] = mix(rows[y][x % WIDTH], color, near * 1.4)


def skyline(rows: list[list[Color]], body: Color, ground: Color, light: Color, lit: float, rng: random.Random) -> None:
    base = int(HEIGHT * HORIZON)
    x = 0
    while x < WIDTH:
        wide, tall = rng.randrange(16, 40), rng.randrange(24, 110)
        for across in range(x, min(WIDTH, x + wide)):
            for y in range(base - tall, base):
                rows[y][across] = body
        for across in range(x + 3, min(WIDTH - 3, x + wide - 3), 5):
            for up in range(base - tall + 4, base - 3, 6):
                if rng.random() < lit:
                    for dot in ((0, 0), (1, 0), (0, 1), (1, 1), (2, 0), (2, 1)):
                        rows[up + dot[1]][across + dot[0]] = light
        x += wide + rng.randrange(0, 5)
    for y in range(base, HEIGHT):
        rows[y] = [mix(ground, body, (y - base) / (HEIGHT - base))] * WIDTH


def main() -> None:
    OUT.mkdir(exist_ok=True)
    day = sky((96, 158, 222), (214, 232, 240))
    clouds(day, (250, 250, 248), random.Random(3))
    hills(day, [(46, (150, 182, 176)), (30, (108, 156, 104)), (14, (74, 124, 70))])
    write(OUT / "day.png", day)
    dusk = sky((58, 54, 112), (246, 158, 96))
    skyline(dusk, (44, 40, 66), (64, 56, 84), (255, 206, 130), 0.16, random.Random(5))
    write(OUT / "dusk.png", dusk)
    night = sky((8, 12, 34), (28, 34, 70))
    stars = random.Random(8)
    for _ in range(150):
        night[stars.randrange(int(HEIGHT * HORIZON))][stars.randrange(WIDTH)] = (214, 218, 236)
    skyline(night, (16, 18, 34), (22, 24, 40), (255, 212, 130), 0.38, random.Random(9))
    write(OUT / "night.png", night)


if __name__ == "__main__":
    main()
