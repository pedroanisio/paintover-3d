"""Draws the news studio's video wall, its monitors and its concrete floor into examples/textures/news. They are checked in,
so this only runs to change them. Run: .venv/bin/python examples/news_pictures.py"""
import math
import random
from pathlib import Path

import flight_deck_pictures as pictures
from flight_deck_pictures import Canvas, blend, write

OUT = Path(__file__).resolve().parent / "textures" / "news"
PLUM, DEEP, TANGERINE, EMBER, MINT, JADE = (42, 20, 88), (22, 10, 48), (255, 138, 31), (217, 98, 10), (63, 224, 181), (31, 169, 138)


def backdrop(c: Canvas, x0: float, x1: float, swirl: tuple[float, float], seed: int) -> None:
    """Deep plum, lighter toward the middle, with sweeps of tangerine and mint about a point."""
    for y in range(c.height):
        c.rect(x0, y, x1, y + 1, tuple(round(v) for v in blend(((0, DEEP), (0.55, PLUM), (1, DEEP)), y / c.height)))
    rng = random.Random(seed)
    cx, cy = swirl
    for ring in range(9):
        radius = 90 + ring * 38 + rng.uniform(-10, 10)
        start = rng.uniform(-40, 60)
        color = TANGERINE if ring % 3 == 0 else (EMBER if ring % 3 == 2 else MINT)
        c.arc(cx, cy, radius, start, start + rng.uniform(90, 170), color, width=rng.uniform(6, 22))
    for ring in range(3):
        c.arc(cx, cy, 40 + ring * 16, 0, 300, JADE, width=3)


def pattern() -> None:
    """The left of the video wall and the monitors: sweeps in the palette and nothing written."""
    c = Canvas(960, 360)
    backdrop(c, 0, 960, (640, 190), 3)
    for row in range(4):  # bars that slide in from the left, as an open has, but empty
        c.rect(90, 120 + row * 34, 90 + (420, 300, 360, 220)[row], 140 + row * 34, (TANGERINE, JADE, EMBER, MINT)[row])
    c.save("pattern")


def wall() -> None:
    """The right of the video wall: waves of mint dots across plum, between panels and rings, and nothing written."""
    c = Canvas(1440, 400)
    backdrop(c, 0, 1440, (1250, 140), 5)
    for row in range(3):  # panels down the left, plain
        top = 22 + row * 98
        c.rect(18, top, 222, top + 86, JADE)
        c.rect(22, top + 4, 218, top + 82, DEEP)
        c.arc(120, top + 43, 26, 0, 270, (TANGERINE, MINT, EMBER)[row], width=6)
    c.rect(240, 20, 1060, 316, DEEP)
    for y in range(26, 312, 7):
        for x in range(246, 1056, 7):
            wave = 168 + 60 * math.sin((x - 246) / 90) + 30 * math.sin((x - 246) / 37 + 1.3)
            if abs(y - wave) < 22 + 14 * math.sin(x / 61):
                c.dot(x, y, 2.1, MINT)
    for ring, color in enumerate((MINT, TANGERINE, JADE, EMBER)):  # rings to the right, where the swirl is
        c.arc(1250, 200, 40 + ring * 30, ring * 50, ring * 50 + 230, color, width=10)
    c.save("wall")


def concrete() -> None:
    """Two metres of sealed grey concrete: soft clouding and fine grit."""
    size = 256
    clouds, grit = pictures_noise(size, 5, 21), random.Random(22)
    data = bytearray()
    for y in range(size):
        for x in range(size):
            tone = 104 + 26 * clouds(x, y) + grit.uniform(-6, 6)
            data.extend(round(max(0, min(255, tone * k))) for k in (1.0, 1.01, 1.04))
    write(OUT / "concrete.png", size, size, bytes(data))


def pictures_noise(size: int, cells: int, seed: int):
    rng = random.Random(seed)
    grid = [[rng.random() for _ in range(cells)] for _ in range(cells)]

    def at(x: float, y: float) -> float:
        gx, gy = x / size * cells, y / size * cells
        x0, y0, fx, fy = int(gx) % cells, int(gy) % cells, gx - int(gx), gy - int(gy)
        x1, y1 = (x0 + 1) % cells, (y0 + 1) % cells
        fx, fy = fx * fx * (3 - 2 * fx), fy * fy * (3 - 2 * fy)
        return (grid[y0][x0] * (1 - fx) + grid[y0][x1] * fx) * (1 - fy) + (grid[y1][x0] * (1 - fx) + grid[y1][x1] * fx) * fy
    return at


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    pictures.OUT = OUT  # Canvas.save writes into the flight deck's folder unless told otherwise
    for draw in (pattern, wall, concrete):
        draw()
