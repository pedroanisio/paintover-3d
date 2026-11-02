"""Draws the screens, lit panels and the view behind the flight deck into examples/textures/flight-deck. They are checked in,
so this only runs to change them. Run: .venv/bin/python examples/flight_deck_pictures.py"""
import math
import random
import struct
import zlib
from pathlib import Path
from typing import Callable, Sequence

OUT = Path(__file__).resolve().parent / "textures" / "flight-deck"
SCALE = 3  # drawn this much larger and averaged down, which is the only antialiasing here
Color = tuple[int, int, int]

WHITE, GREEN, CYAN, MAGENTA, AMBER, GREY = (235, 238, 240), (70, 230, 120), (70, 215, 235), (235, 90, 225), (255, 176, 60), (120, 124, 130)
GLYPHS = {
    "0": "3E5149453E", "1": "00427F4000", "2": "4261514946", "3": "2141454B31", "4": "1814127F10", "5": "2745454539",
    "6": "3C4A494930", "7": "0171090503", "8": "3649494936", "9": "064949291E", "A": "7E1111117E", "B": "7F49494936",
    "C": "3E41414122", "D": "7F4141221C", "E": "7F49494941", "F": "7F09090901", "G": "3E4149497A", "H": "7F0808087F",
    "I": "00417F4100", "J": "2040413F01", "K": "7F08142241", "L": "7F40404040", "M": "7F020C027F", "N": "7F0408107F",
    "O": "3E4141413E", "P": "7F09090906", "Q": "3E4151215E", "R": "7F09192946", "S": "4649494931", "T": "01017F0101",
    "U": "3F4040403F", "V": "1F2040201F", "W": "3F4038403F", "X": "6314081463", "Y": "0708700807", "Z": "6151494543",
    ".": "0060600000", "/": "2010080402", "-": "0808080808", " ": "0000000000"}


def write(path: Path, width: int, height: int, data: bytes) -> None:
    def chunk(tag: bytes, body: bytes) -> bytes:
        return struct.pack(">I", len(body)) + tag + body + struct.pack(">I", zlib.crc32(tag + body))
    rows = b"".join(b"\0" + data[y * width * 3:(y + 1) * width * 3] for y in range(height))
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
                     + chunk(b"IDAT", zlib.compress(rows, 9)) + chunk(b"IEND", b""))


class Canvas:
    """All coordinates are in final pixels and may be fractions."""

    def __init__(self, width: int, height: int, ground: Color = (0, 0, 0)) -> None:
        self.width, self.height = width, height
        self.w, self.h = width * SCALE, height * SCALE
        self.pixels = bytearray(bytes(ground) * (self.w * self.h))

    def rect(self, x0: float, y0: float, x1: float, y1: float, color: Color) -> None:
        left, right = max(0, round(x0 * SCALE)), min(self.w, round(x1 * SCALE))
        run = bytes(color) * max(0, right - left)
        for y in range(max(0, round(y0 * SCALE)), min(self.h, round(y1 * SCALE))):
            start = (y * self.w + left) * 3
            self.pixels[start:start + len(run)] = run

    def dot(self, x: float, y: float, radius: float, color: Color) -> None:
        reach = radius * SCALE
        px, py = x * SCALE, y * SCALE
        for row in range(max(0, int(py - reach)), min(self.h, int(py + reach) + 1)):
            half = reach * reach - (row - py) ** 2
            if half < 0:
                continue
            half = math.sqrt(half)
            left, right = max(0, int(px - half)), min(self.w, int(px + half) + 1)
            start = (row * self.w + left) * 3
            run = bytes(color) * max(0, right - left)
            self.pixels[start:start + len(run)] = run

    def line(self, x0: float, y0: float, x1: float, y1: float, color: Color, width: float = 1.5) -> None:
        count = max(2, int(math.hypot(x1 - x0, y1 - y0) * SCALE / max(1.0, width)))
        for step in range(count + 1):
            t = step / count
            self.dot(x0 + (x1 - x0) * t, y0 + (y1 - y0) * t, width / 2, color)

    def arc(self, cx: float, cy: float, radius: float, start: float, end: float, color: Color, width: float = 1.5, ticks: int = 0) -> None:
        """Degrees clockwise from straight up. `ticks` adds that many marks across the arc."""
        count = max(8, int(abs(end - start) * radius / 40))
        points = [start + (end - start) * i / count for i in range(count + 1)]
        at = lambda turn, r: (cx + r * math.sin(math.radians(turn)), cy - r * math.cos(math.radians(turn)))
        for a, b in zip(points, points[1:]):
            self.line(*at(a, radius), *at(b, radius), color, width)
        for i in range(ticks + 1):
            turn = start + (end - start) * i / max(1, ticks)
            self.line(*at(turn, radius), *at(turn, radius - (12 if i % 5 == 0 else 6)), color, width)

    def text(self, x: float, y: float, words: str, color: Color, size: float = 2.0) -> None:
        for index, letter in enumerate(words.upper()):
            columns = GLYPHS.get(letter, GLYPHS[" "])
            for column in range(5):
                bits = int(columns[column * 2:column * 2 + 2], 16)
                for row in range(7):
                    if bits >> row & 1:
                        left = x + (index * 6 + column) * size
                        self.rect(left, y + row * size, left + size, y + (row + 1) * size, color)

    def glow(self, x: float, y: float, radius: float, color: Color) -> None:
        """A lamp: a bright middle fading into what is under it."""
        reach = int(radius * 2.6 * SCALE)
        px, py = round(x * SCALE), round(y * SCALE)
        for row in range(max(0, py - reach), min(self.h, py + reach)):
            for column in range(max(0, px - reach), min(self.w, px + reach)):
                near = 1 - math.hypot(row - py, column - px) / reach
                if near > 0:
                    share = min(1.0, near * near * 1.6)
                    at = (row * self.w + column) * 3
                    for i in range(3):
                        self.pixels[at + i] = round(self.pixels[at + i] * (1 - share) + color[i] * share)

    def save(self, name: str) -> None:
        out = bytearray(self.width * self.height * 3)
        pixels, w, s = self.pixels, self.w, SCALE
        for y in range(self.height):
            for x in range(self.width):
                for i in range(3):
                    total = 0
                    for row in range(y * s, y * s + s):
                        base = (row * w + x * s) * 3 + i
                        total += sum(pixels[base:base + 3 * s:3])
                    out[(y * self.width + x) * 3 + i] = total // (s * s)
        write(OUT / f"{name}.png", self.width, self.height, bytes(out))


def attitude(c: Canvas, x0: float, y0: float, x1: float, y1: float, horizon: float, bank: float) -> None:
    middle = (x0 + x1) / 2
    for x in range(int(x0), int(x1)):
        level = horizon + (x - middle) * bank
        c.rect(x, y0, x + 1, min(y1, max(y0, level)), (32, 104, 214))
        c.rect(x, min(y1, max(y0, level)), x + 1, y1, (176, 98, 34))
    c.line(x0, horizon + (x0 - middle) * bank, x1, horizon + (x1 - middle) * bank, WHITE, 2.5)


def pfd() -> None:
    c = Canvas(320, 400, (8, 9, 12))
    middle, horizon = 160, 170
    attitude(c, 62, 40, 258, 310, horizon, -0.08)
    for step in range(-4, 5):
        if step:
            half = 42 if step % 2 == 0 else 20
            y = horizon + step * 24
            c.line(middle - half, y + half * 0.08, middle + half, y - half * 0.08, WHITE, 2)
    c.arc(middle, 170, 118, -50, 50, WHITE, 2, 10)
    c.line(middle - 62, 170, middle - 22, 170, (250, 220, 40), 6)
    c.line(middle + 22, 170, middle + 62, 170, (250, 220, 40), 6)
    c.dot(middle, 170, 5, (250, 220, 40))
    for x0, x1, first in ((6, 56, 280), (264, 314, 12000)):
        c.rect(x0, 40, x1, 310, (56, 60, 70))
        for row in range(7):
            c.text(x0 + 6, 52 + row * 38, str(first + (3 - row) * (10 if first < 1000 else 100)), WHITE, 1.6)
        c.rect(x0, 158, x1, 186, (0, 0, 0))
        c.text(x0 + 6, 165, str(first), WHITE, 1.8)
    c.text(70, 12, "SPD", GREEN, 2)
    c.text(135, 12, "LNAV", GREEN, 2)
    c.text(215, 12, "VNAV", GREEN, 2)
    c.arc(middle, 470, 145, -40, 40, WHITE, 2, 16)
    c.text(135, 352, "137", WHITE, 2.4)
    c.save("pfd")


def nd() -> None:
    c = Canvas(460, 460, (3, 8, 8))
    cx, cy = 230, 380
    for radius, thick in ((330, 2.5), (250, 1.5), (165, 1.5), (82, 1.5)):
        c.arc(cx, cy, radius, -62, 62, WHITE if radius == 330 else (120, 230, 170), thick, 24 if radius == 330 else 0)
    for offset in range(3):
        c.text(cx - 19 + (offset - 1) * 125, 48 + abs(offset - 1) * 34, str(12 + offset * 3).zfill(3), WHITE, 2)
    c.line(cx, cy, cx + 30, 210, MAGENTA, 3)
    c.line(cx + 30, 210, cx - 90, 96, MAGENTA, 3)
    for x, y, name in ((cx + 30, 210, "KELPR"), (cx - 90, 96, "RIDGE")):
        c.line(x - 8, y, x + 8, y, WHITE, 2)
        c.line(x, y - 8, x, y + 8, WHITE, 2)
        c.text(x + 12, y - 8, name, CYAN, 2)
    c.line(cx, cy - 26, cx, cy + 20, WHITE, 4)
    c.line(cx - 20, cy, cx + 20, cy, WHITE, 4)
    c.text(10, 10, "GS 412", WHITE, 2.2)
    c.text(10, 36, "TAS 438", WHITE, 2.2)
    c.text(330, 10, "KELPR", MAGENTA, 2.2)
    c.text(330, 36, "12.4 NM", WHITE, 2.2)
    c.text(10, 430, "TFC", CYAN, 2)
    c.text(390, 430, "40", WHITE, 2.2)
    c.save("nd")


def eicas() -> None:
    c = Canvas(460, 460, (6, 8, 10))
    for x in (120, 340):
        for y, value in ((95, 92), (225, 68)):
            c.arc(x, y, 72, -120, 110, WHITE, 3, 10)
            turn = -120 + 230 * value / 100
            c.arc(x, y, 60, -120, turn, GREEN, 12)
            c.text(x - 22, y + 20, f"{value}.4", GREEN, 2.2)
    c.text(205, 88, "N1", CYAN, 2.4)
    c.text(198, 218, "EGT", CYAN, 2.4)
    for row, words in enumerate(("FUEL QTY 12480", "CAB ALT   6200", "OIL PRESS   68", "SLATS  RETRACT")):
        c.text(30, 320 + row * 30, words, GREEN if row else CYAN, 2.4)
    c.save("eicas")


def cdu() -> None:
    c = Canvas(280, 380, (22, 23, 26))
    c.rect(26, 16, 254, 170, (2, 7, 4))
    for row, words in enumerate(("ACT RTE LEGS", "KELPR    250", "RIDGE    310", "VALLE    350", "APPR     220", "EXEC")):
        c.text(36, 28 + row * 23, words, GREEN if row % 2 else (130, 245, 150), 2.1)
    for row in range(5):
        for column in range(6):
            x, y = 22 + column * 41, 186 + row * 37
            c.rect(x, y, x + 34, y + 27, (36, 37, 40))
            c.rect(x + 8, y + 10, x + 26, y + 16, AMBER)
    c.save("cdu")


def standby() -> None:
    c = Canvas(180, 200, (6, 7, 9))
    attitude(c, 12, 14, 168, 186, 100, -0.1)
    c.line(50, 100, 80, 100, (250, 220, 40), 5)
    c.line(100, 100, 130, 100, (250, 220, 40), 5)
    c.save("standby")


def mcp() -> None:
    c = Canvas(1100, 150, (30, 31, 34))
    for x, words in ((70, "137"), (250, "015"), (450, "12000"), (720, "0000"), (930, "015")):
        c.rect(x, 30, x + 7 + len(words) * 24, 74, (4, 8, 6))
        c.text(x + 8, 40, words, (120, 255, 150), 4)
    for index, words in enumerate(("SPD", "HDG", "ALT", "V/S", "CRS")):
        c.text((70, 250, 450, 720, 930)[index], 12, words, WHITE, 2)
    for index in range(26):
        x, lit = 30 + index * 41, index % 3 == 0
        c.rect(x, 92, x + 30, 128, (46, 47, 50))
        c.rect(x + 5, 104, x + 25, 116, GREEN if lit else (170, 150, 110))
    c.save("mcp")


def overhead() -> None:
    random.seed(7)
    c = Canvas(840, 1350, (20, 21, 24))
    for row in range(12):
        y = 40 + row * 108
        c.line(20, y - 18, 820, y - 18, (92, 95, 100), 1.5)
        c.text(30, y - 12, ("FUEL", "ELEC", "HYD", "AIR", "ANTI ICE", "APU")[row % 6], WHITE, 1.6)
        for column in range(12):
            x = 54 + column * 67
            if random.random() < 0.8:
                c.rect(x - 22, y + 14, x + 22, y + 66, (38, 39, 42))
            if random.random() < 0.5:
                c.glow(x, y + 40, 15, AMBER if random.random() < 0.8 else (255, 120, 40))
    c.save("overhead")


def radios() -> None:
    random.seed(11)
    c = Canvas(380, 700, (28, 29, 32))
    for row in range(7):
        y = 14 + row * 98
        c.rect(14, y, 366, y + 86, (40, 41, 45))
        c.rect(26, y + 10, 190, y + 40, (3, 7, 6))
        c.text(34, y + 16, f"1{random.randrange(18, 36)}.{random.randrange(100, 999)}", (120, 255, 150), 2.6)
        for key in range(5):
            x = 204 + key * 30
            c.rect(x, y + 12, x + 24, y + 36, (54, 55, 60))
            c.rect(x + 5, y + 21, x + 19, y + 27, (255, 214, 150) if random.random() < 0.7 else GREEN)
        for key in range(9):
            c.rect(24 + key * 38, y + 54, 54 + key * 38, y + 74, (196, 180, 150) if random.random() < 0.6 else (62, 63, 68))
    c.save("radios")


def blend(stops: Sequence[tuple[float, Color]], at: float) -> tuple[float, float, float]:
    for (a, p), (b, q) in zip(stops, stops[1:]):
        if at <= b:
            share = (at - a) / (b - a)
            return tuple(u + (v - u) * share for u, v in zip(p, q))
    return tuple(float(v) for v in stops[-1][1])


def city() -> None:
    """A dusk sky over a lit plain and far mountains. Ground lights are splatted through a real perspective, which is what
    makes streets run together at the horizon."""
    width, height, level, vanish = 3000, 1000, 400, 1100
    rng = random.Random(23)
    red, green, blue = [[0.0] * (width * height) for _ in range(3)]
    stops = [(0.0, (36, 32, 110)), (0.6, (100, 62, 168)), (0.76, (196, 88, 158)), (0.9, (244, 142, 104)), (1.0, (255, 190, 108))]
    for y in range(level):
        base = y / level
        for x in range(width):
            warm = 0.5 + 0.5 * math.sin(x / 520 - 1.6)
            streak = max(0.0, math.sin(y / 9 + math.sin(x / 210) * 3 + x / 700)) ** 6 * 0.28 * base
            r, g, b = blend(stops, min(1.0, base + 0.03 * warm * base))
            at = y * width + x
            red[at], green[at], blue[at] = r + 70 * streak, g + 30 * streak, b + 20 * streak
    for x in range(width):
        top = level - 12 - 7 * math.sin(x / 170 + 1) - 4 * math.sin(x / 61) - 2 * math.sin(x / 19)
        for y in range(int(top), level + 8):
            at = y * width + x
            share = min(1.0, (y - top) / 22 + 0.55)
            red[at], green[at], blue[at] = 62 * (1 - share) + 24 * share, 52 * (1 - share) + 22 * share, 100 * (1 - share) + 62 * share
    for y in range(level + 8, height):
        for x in range(width):
            at = y * width + x
            red[at], green[at], blue[at] = 15.0, 15.0, 34.0

    def splat(depth: float, across: float, color: Color, power: float) -> None:
        sy = level + 8 + 5000 / depth
        sx = vanish + across * 5000 / depth
        if not (2 <= sx < width - 2 and 2 <= sy < height - 2):
            return
        size = 1 if depth > 40 else 2
        for dy in range(-size, size + 1):
            for dx in range(-size, size + 1):
                share = power / (1 + dx * dx + dy * dy)
                at = int(sy + dy) * width + int(sx + dx)
                red[at] += color[0] * share
                green[at] += color[1] * share
                blue[at] += color[2] * share

    lamps = ((255, 176, 84), (255, 196, 110), (255, 142, 64), (255, 214, 150), (190, 214, 255))
    for _ in range(620000):
        depth = 6 + 600 * rng.random() ** 2.4
        if rng.random() < 0.5:
            across, along = round(rng.uniform(-1.1, 1.1) * depth / 7) * 7 + rng.gauss(0, 0.2), depth
        else:
            across, along = rng.uniform(-1.1, 1.1) * depth, round(depth / 7) * 7 + rng.gauss(0, 0.2)
        if math.sin(across / 23 + along / 31) * math.sin(along / 19 - across / 41) > 0.45 and rng.random() < 0.85:  # dark blocks keep it from being a carpet
            continue
        splat(max(along, 4.0), across, rng.choice(lamps), 0.07 + 7 / (40 + depth))
    for _ in range(36000):  # the avenue, and the roads that run into it at the horizon
        depth = 5 + 500 * rng.random() ** 2.2
        splat(depth, rng.gauss(0, 1.3), (255, 190, 110), 0.05)
    for _ in range(40000):
        depth = 6 + 400 * rng.random() ** 2
        splat(depth, rng.choice((-44, -21, 18, 39, 66, 104)) + rng.gauss(0, 0.3), (255, 170, 84), 0.14)

    data = bytearray(width * height * 3)
    for at in range(width * height):
        for i, channel in enumerate((red, green, blue)):
            value = channel[at]
            data[at * 3 + i] = min(255, round(value if value < 180 else 180 + 75 * (1 - math.exp(-(value - 180) / 120))))
    write(OUT / "city.png", width, height, bytes(data))


PICTURES: tuple[Callable[[], None], ...] = (pfd, nd, eicas, cdu, standby, mcp, overhead, radios, city)

if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    for draw in PICTURES:
        draw()
