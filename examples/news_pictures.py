"""Draws the news studio's video wall, its monitors and its concrete floor into examples/textures/news. They are checked in,
so this only runs to change them. Run: .venv/bin/python examples/news_pictures.py"""
import math
import random
from pathlib import Path

import flight_deck_pictures as pictures
from flight_deck_pictures import Canvas, Color, blend, write

OUT = Path(__file__).resolve().parent / "textures" / "news"
WHITE, RED, NAVY, ORANGE, SKY = (245, 246, 250), (206, 34, 38), (12, 34, 92), (255, 118, 26), (70, 160, 255)
LAND = ((-100, 47, 32, 17), (-82, 28, 12, 9), (-42, 72, 11, 7), (-60, -16, 14, 24), (14, 50, 17, 9), (20, 4, 21, 27),
        (46, 27, 11, 8), (92, 50, 48, 19), (78, 20, 8, 10), (104, 14, 9, 9), (134, -25, 16, 10), (139, 37, 3, 7), (-155, 63, 12, 6))


def backdrop(c: Canvas, x0: float, x1: float, swirl: tuple[float, float], seed: int) -> None:
    """Deep blue, lighter toward the middle, with sweeps of orange and blue about a point, as a news open has."""
    for y in range(c.height):
        c.rect(x0, y, x1, y + 1, tuple(round(v) for v in blend(((0, (8, 30, 96)), (0.55, (24, 86, 196)), (1, (10, 36, 110))), y / c.height)))
    rng = random.Random(seed)
    cx, cy = swirl
    for ring in range(9):
        radius = 90 + ring * 38 + rng.uniform(-10, 10)
        start = rng.uniform(-40, 60)
        color = ORANGE if ring % 3 != 1 else SKY
        c.arc(cx, cy, radius, start, start + rng.uniform(90, 170), color, width=rng.uniform(6, 22))
    for ring in range(3):
        c.arc(cx, cy, 40 + ring * 16, 0, 300, (150, 205, 255), width=3)


def breaking() -> None:
    c = Canvas(960, 360)
    backdrop(c, 0, 960, (640, 190), 3)
    c.rect(90, 148, 650, 222, RED)
    c.rect(90, 222, 650, 228, WHITE)
    c.text(118, 164, "BREAKING NEWS", WHITE, 6.4)
    c.save("breaking")


def world() -> None:
    """A map of dots between a column of pictures and a column of headlines, over a ticker."""
    c = Canvas(1440, 400)
    backdrop(c, 0, 1440, (1250, 140), 5)
    for row, tone in enumerate(((150, 60, 40), (40, 90, 150), (90, 100, 110))):  # pictures from the field
        top = 22 + row * 98
        c.rect(18, top, 222, top + 86, (230, 236, 244))
        c.rect(22, top + 4, 218, top + 82, tone)
        c.dot(80 + row * 30, top + 44, 22, tuple(min(255, v + 80) for v in tone))
    c.rect(240, 20, 1060, 316, (6, 40, 120))
    for y in range(26, 312, 7):
        for x in range(246, 1056, 7):
            lon, lat = (x - 246) / 810 * 360 - 180, 84 - (y - 26) / 286 * 150
            if any(((lon - cx) / rx) ** 2 + ((lat - cy) / ry) ** 2 < 1 for cx, cy, rx, ry in LAND):
                c.dot(x, y, 2.1, (120, 196, 255))
    c.dot(470, 125, 7, ORANGE)
    c.dot(820, 140, 7, ORANGE)
    for top, words, ground in ((40, "BREAKING", RED), (120, "NEWS", NAVY)):
        c.rect(1080, top, 1420, top + 64, WHITE)
        c.rect(1084, top + 4, 1416, top + 60, ground)
        c.text(1100, top + 15, words, WHITE, 5)
    c.rect(1080, 200, 1420, 316, (40, 110, 210))
    c.dot(1250, 258, 46, ORANGE)
    c.rect(0, 330, 1440, 400, WHITE)
    c.rect(0, 330, 150, 400, RED)
    c.text(24, 348, "NEWS", WHITE, 5)
    c.text(176, 352, "MARKETS OPEN HIGHER  /  COUNCIL VOTES TONIGHT  /  RAIN BY EVENING", NAVY, 3.6)
    c.save("world")


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
    for draw in (breaking, world, concrete):
        draw()
