"""Draws the park's pavers, grass, leaves and tower glass into examples/textures/park. They are checked in, so this only runs
to change them. Run: .venv/bin/python examples/park_pictures.py"""
import math
import random
from pathlib import Path
from typing import Callable

from flight_deck_pictures import write

OUT = Path(__file__).resolve().parent / "textures" / "park"
Color = tuple[float, float, float]


def shade(color: Color, amount: float) -> Color:
    return tuple(max(0.0, min(255.0, c * amount)) for c in color)


def save(name: str, width: int, height: int, pixel: Callable[[int, int], Color]) -> None:
    data = bytearray()
    for y in range(height):
        for x in range(width):
            data.extend(round(max(0.0, min(255.0, c))) for c in pixel(x, y))
    write(OUT / f"{name}.png", width, height, bytes(data))


def noise(size: int, cells: int, seed: int) -> Callable[[float, float], float]:
    """Smooth value noise that wraps at `size`, 0 to 1."""
    rng = random.Random(seed)
    grid = [[rng.random() for _ in range(cells)] for _ in range(cells)]

    def at(x: float, y: float) -> float:
        gx, gy = x / size * cells, y / size * cells
        x0, y0 = int(gx) % cells, int(gy) % cells
        x1, y1, fx, fy = (x0 + 1) % cells, (y0 + 1) % cells, gx - int(gx), gy - int(gy)
        fx, fy = fx * fx * (3 - 2 * fx), fy * fy * (3 - 2 * fy)
        top = grid[y0][x0] * (1 - fx) + grid[y0][x1] * fx
        bottom = grid[y1][x0] * (1 - fx) + grid[y1][x1] * fx
        return top * (1 - fy) + bottom * fy
    return at


def pavers() -> None:
    """1.2 m square: bricks 20 by 10 cm in running bond, warm and uneven, with pale joints."""
    size, rows, across = 384, 12, 6
    rng = random.Random(4)
    tones = [(rng.uniform(158, 192), rng.uniform(122, 146), rng.uniform(108, 128)) for _ in range(rows * across * 2)]
    grain = noise(size, 48, 9)

    def pixel(x: int, y: int) -> Color:
        row, high = divmod(y, size // rows)
        shift = (size // across // 2) * (row % 2)
        column, wide = divmod((x + shift) % size, size // across)
        if high < 2 or wide < 2:
            return (196, 178, 162)
        edge = min(high, wide, size // rows - high, size // across - wide)
        return shade(tones[row * across + column], (0.88 + 0.2 * grain(x, y)) * (0.93 if edge < 4 else 1.0))
    save("pavers", size, size, pixel)


def grass() -> None:
    """2 m square of mown lawn: patches of lighter and darker green with fine blades."""
    size = 256
    patches, blades = noise(size, 6, 2), noise(size, 64, 3)
    rng = random.Random(5)
    speck = [rng.random() for _ in range(size * size)]

    def pixel(x: int, y: int) -> Color:
        light = 0.82 + 0.3 * patches(x, y) + 0.12 * blades(x, y) + 0.1 * (speck[y * size + x] - 0.5)
        return shade((146, 204, 64), light)
    save("grass", size, size, pixel)


def leaves() -> None:
    """Foliage close to: clusters of leaves, bright where they face out and dark in the gaps between."""
    size = 256
    rng = random.Random(7)
    light = [[0.18] * size for _ in range(size)]
    for _ in range(900):
        cx, cy, r = rng.uniform(0, size), rng.uniform(0, size), rng.uniform(4, 10)
        top = rng.uniform(0.55, 1.0)
        for dy in range(-int(r) - 1, int(r) + 2):
            for dx in range(-int(r) - 1, int(r) + 2):
                d = math.hypot(dx, dy) / r
                if d < 1:
                    value = top * (1 - 0.55 * d * d) * (0.85 + 0.3 * max(0.0, -dy / r))
                    row, column = int(cy + dy) % size, int(cx + dx) % size
                    light[row][column] = max(light[row][column], value)

    def pixel(x: int, y: int) -> Color:
        v = light[y][x]
        return (60 + 150 * v, 95 + 160 * v, 25 + 60 * v)
    save("leaves", size, size, pixel)


def glass() -> None:
    """A curtain wall, 8 bays by 40 floors: panes that catch the sky unevenly, between pale mullions and spandrels."""
    width, height, bays, floors = 128, 480, 8, 40
    rng = random.Random(11)
    panes = [rng.uniform(0.75, 1.15) for _ in range(bays * floors)]
    sky = noise(width, 4, 12)

    def pixel(x: int, y: int) -> Color:
        bay, inside_x = divmod(x, width // bays)
        floor, inside_y = divmod(y, height // floors)
        if inside_x < 2 or inside_y < 3:
            return (196, 206, 214)
        tone = panes[floor * bays + bay] * (0.85 + 0.3 * sky(x, y * 0.25)) * (1.05 - 0.25 * y / height)
        return shade((122, 158, 196), tone)
    save("glass", width, height, pixel)


PICTURES = (pavers, grass, leaves, glass)

if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    for draw in PICTURES:
        draw()
