"""Draws the starship bridge's screens, holo table, deck plates and the stars outside into examples/textures/bridge. They are
checked in, so this only runs to change them. Run: .venv/bin/python examples/bridge_pictures.py"""
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


def holo() -> None:
    """The holo table's top: a planet's map in dots inside rings, with a grid and two marked places."""
    c = Canvas(512, 512, (2, 10, 26))
    land = pictures_noise(512, 7, 41)
    for y in range(40, 472, 6):
        for x in range(40, 472, 6):
            if math.hypot(x - 256, y - 256) < 210 and land(x, y) > 0.55:
                c.dot(x, y, 1.9, (110, 210, 255))
    for radius in (214, 224, 240):
        c.arc(256, 256, radius, 0, 360, (60, 160, 230), width=2)
    for turn in range(0, 360, 30):
        c.arc(256, 256, 232, turn, turn + 18, (120, 210, 255), width=5)
    for offset in range(-180, 181, 60):
        c.line(256 + offset, 46, 256 + offset, 466, (20, 70, 120), 1)
        c.line(46, 256 + offset, 466, 256 + offset, (20, 70, 120), 1)
    for x, y in ((200, 210), (320, 300)):
        c.arc(x, y, 12, 0, 360, AMBER, width=2)
        c.dot(x, y, 3, AMBER)
    c.save("holo")


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
    for draw in (stars, holo, scope, tactical, readouts, keys, deck):
        draw()
