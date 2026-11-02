"""Draws the starship bridge's screens, mimic board, chart, deck plates and the stars outside into examples/textures/bridge.
They are checked in, so this only runs to change them. Run: .venv/bin/python examples/bridge_pictures.py"""
import math
import random
from pathlib import Path

import flight_deck_pictures as pictures
from flight_deck_pictures import Canvas, write
from news_pictures import pictures_noise

OUT = Path(__file__).resolve().parent / "textures" / "bridge"
CYAN, RED, AMBER, GREEN, WHITE = (90, 200, 255), (235, 50, 45), (255, 170, 50), (80, 230, 120), (225, 235, 245)


def stars() -> None:
    """Deep space: a blue nebula drifting across, and stars of every brightness, a few with a glow."""
    width, height = 2048, 1024
    cloud, wisp = pictures_noise(width, 6, 31), pictures_noise(width, 18, 32)
    rng = random.Random(33)
    data = bytearray()
    for y in range(height):
        for x in range(width):
            band = math.exp(-((y - height * (0.35 + 0.15 * math.sin(x / width * 6.3))) / (height * 0.22)) ** 2)
            mist = max(0.0, cloud(x, y * 2) * 0.8 + wisp(x, y * 2) * 0.4 - 0.45) * band
            data.extend((round(4 + 40 * mist), round(6 + 60 * mist), round(12 + 110 * mist)))
    for _ in range(5200):
        x, y, light = rng.randrange(width), rng.randrange(height), rng.random() ** 3
        for dy, dx, share in ((0, 0, 1.0),) + (((0, 1, 0.4), (1, 0, 0.4), (0, -1, 0.4), (-1, 0, 0.4)) if light > 0.5 else ()):
            at = (((y + dy) % height) * width + (x + dx) % width) * 3
            tint = (200 + 55 * light, 210 + 45 * light, 255) if rng.random() < 0.7 else (255, 220, 190)
            for i in range(3):
                data[at + i] = min(255, data[at + i] + round(tint[i] * (0.25 + 0.75 * light) * share))
    write(OUT / "stars.png", width, height, bytes(data))


def scope() -> None:
    """A round sensor scope: rings, a sweep and contacts."""
    c = Canvas(256, 256, (4, 12, 22))
    for radius in (40, 75, 110):
        c.arc(128, 128, radius, 0, 360, (40, 130, 200), width=2)
    c.line(128, 18, 128, 238, (30, 90, 140), 1)
    c.line(18, 128, 238, 128, (30, 90, 140), 1)
    for step in range(30):
        c.line(128, 128, 128 + 110 * math.sin(math.radians(40 + step)), 128 - 110 * math.cos(math.radians(40 + step)),
               (20, 60 + step * 4, 90 + step * 5), 2)
    for x, y in ((170, 90), (90, 160), (150, 180)):
        c.dot(x, y, 4, CYAN)
    c.save("scope")


def tactical() -> None:
    """A red tactical grid with a target box and readouts."""
    c = Canvas(256, 192, (24, 4, 4))
    for x in range(8, 256, 24):
        c.line(x, 8, x, 184, (90, 20, 18), 1)
    for y in range(8, 192, 24):
        c.line(8, y, 248, y, (90, 20, 18), 1)
    for x0, y0, x1, y1 in ((96, 64, 160, 128),):
        for a, b, cc, d in ((x0, y0, x1, y0), (x1, y0, x1, y1), (x1, y1, x0, y1), (x0, y1, x0, y0)):
            c.line(a, b, cc, d, RED, 3)
    c.dot(128, 96, 6, (255, 120, 90))
    c.text(12, 168, "TRK 0427", (255, 120, 100), 2)
    c.save("tactical")


def readouts() -> None:
    """Bar graphs and figures in green and amber."""
    rng = random.Random(51)
    c = Canvas(256, 160, (4, 14, 10))
    for column in range(10):
        high = rng.uniform(20, 100)
        c.rect(14 + column * 22, 120 - high, 28 + column * 22, 120, GREEN if column % 4 else AMBER)
    c.text(14, 134, "PWR 98.2  NAV OK", GREEN, 2)
    c.save("readouts")


def keys() -> None:
    """A console top: rows of keys and lamps on grey, which tiles."""
    rng = random.Random(61)
    c = Canvas(512, 256, (44, 47, 52))
    for row in range(8):
        for column in range(16):
            x, y = 8 + column * 31.5, 8 + row * 31
            kind = rng.random()
            if kind < 0.45:
                c.rect(x, y, x + 24, y + 22, (70, 74, 80))
                c.rect(x + 2, y + 2, x + 22, y + 18, (92, 96, 104))
            elif kind < 0.8:
                c.rect(x, y, x + 24, y + 22, (20, 22, 25))
                c.rect(x + 4, y + 6, x + 20, y + 14, rng.choice((RED, AMBER, GREEN, CYAN, WHITE)))
            else:
                c.dot(x + 12, y + 11, 8, (25, 27, 30))
                c.dot(x + 12, y + 11, 4, rng.choice((RED, GREEN, CYAN)))
    c.save("keys")


def mimic() -> None:
    """A mimic board: the ship's systems drawn as lines between boxes, with lamps on them and meters beside, and no words."""
    rng = random.Random(81)
    c = Canvas(1536, 384, (30, 34, 36))
    for x in range(0, 1536, 192):  # the board's panels
        c.rect(x, 0, x + 3, 384, (18, 20, 22))
    rows = (70, 160, 250, 330)
    for row, y in enumerate(rows):  # the main lines, each a colour of its own
        tone = (WHITE, GREEN, AMBER, CYAN)[row]
        c.line(30, y, 1506, y, tone, 4)
    for x in range(80, 1500, 96):  # feeds between the lines, boxes on them and lamps where they meet
        top, bottom = sorted(rng.sample(rows, 2))
        c.line(x, top, x, bottom, (150, 156, 160), 3)
        middle = (top + bottom) / 2
        c.rect(x - 18, middle - 14, x + 18, middle + 14, (60, 66, 70))
        c.rect(x - 14, middle - 10, x + 14, middle + 10, (36, 40, 44))
        for y in (top, bottom):
            c.dot(x, y, 7, (20, 22, 24))
            c.dot(x, y, 5, rng.choice((GREEN, GREEN, GREEN, AMBER, RED)))
    for x in range(110, 1500, 192):  # small bar meters along the bottom
        for bar in range(5):
            high = rng.uniform(8, 30)
            c.rect(x + bar * 9, 372 - high, x + bar * 9 + 6, 372, GREEN if bar % 4 else AMBER)
    c.save("mimic")


def chart() -> None:
    """A star chart: a grid, stars, and a course of waypoints across it."""
    rng = random.Random(91)
    c = Canvas(512, 320, (6, 14, 24))
    for x in range(16, 512, 40):
        c.line(x, 8, x, 312, (22, 54, 80), 1)
    for y in range(20, 320, 40):
        c.line(8, y, 504, y, (22, 54, 80), 1)
    for _ in range(140):
        c.dot(rng.uniform(10, 502), rng.uniform(10, 310), rng.uniform(0.8, 2.2), (150, 190, 230))
    course = ((40, 260), (150, 210), (250, 220), (340, 140), (460, 70))
    for (x0, y0), (x1, y1) in zip(course, course[1:]):
        c.line(x0, y0, x1, y1, AMBER, 3)
    for x, y in course:
        c.dot(x, y, 7, AMBER)
        c.dot(x, y, 4, (6, 14, 24))
    c.save("chart")


def deck() -> None:
    """Two metres of deck: dark plates a metre square with seams, bolts and wear."""
    size = 256
    wear, grit = pictures_noise(size, 6, 71), random.Random(72)
    data = bytearray()
    for y in range(size):
        for x in range(size):
            seam = x % 128 < 2 or y % 128 < 2
            bolt = min(x % 128, 128 - x % 128) < 7 and min(y % 128, 128 - y % 128) < 7 and math.hypot(x % 128 - 6 if x % 128 < 64 else x % 128 - 122,
                                                                                                         y % 128 - 6 if y % 128 < 64 else y % 128 - 122) < 2.5
            tone = 26 if seam else (88 if bolt else 58 + 22 * wear(x, y) + grit.uniform(-4, 4))
            data.extend((round(tone), round(tone * 1.02), round(tone * 1.08)))
    write(OUT / "deck.png", size, size, bytes(data))


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    pictures.OUT = OUT  # Canvas.save writes into the flight deck's folder unless told otherwise
    for draw in (stars, scope, tactical, readouts, keys, deck, mimic, chart):
        draw()
