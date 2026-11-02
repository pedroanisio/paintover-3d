"""Geometry's hot paths give the same bits as the plain formulas: published digests and the frame-to-still tests depend on it."""
import math
import random
import sys
from pathlib import Path

sys.path[:0] = [str(Path(__file__).resolve().parent.parent)]

from srlocations.geometry import Transform, Vec3, _multiply, rotation


def plain_multiply(a, b):
    return tuple(tuple(sum(a[r][k] * b[k][c] for k in range(3)) for c in range(3)) for r in range(3))


def plain_rotation(yaw, pitch, roll):
    y, p, r = (math.radians(v) for v in (yaw, pitch, roll))
    yawed = ((math.cos(y), 0.0, math.sin(y)), (0.0, 1.0, 0.0), (-math.sin(y), 0.0, math.cos(y)))
    pitched = ((1.0, 0.0, 0.0), (0.0, math.cos(p), math.sin(p)), (0.0, -math.sin(p), math.cos(p)))
    rolled = ((math.cos(r), -math.sin(r), 0.0), (math.sin(r), math.cos(r), 0.0), (0.0, 0.0, 1.0))
    return plain_multiply(yawed, plain_multiply(pitched, rolled))


def plain_apply(transform, point):
    moved = [sum(row[c] * v for c, v in enumerate(point)) for row in transform.basis]
    return Vec3(*moved) + transform.position


def test_the_matrix_products_are_the_plain_formulas_to_the_bit():
    rng = random.Random(1)
    entry = lambda: rng.choice([rng.uniform(-1, 1), 0.0, -0.0, 1.0, -1.0, 1e-17])
    for _ in range(5000):
        a, b = (tuple(tuple(entry() for _ in range(3)) for _ in range(3)) for _ in "ab")
        assert repr(_multiply(a, b)) == repr(plain_multiply(a, b))
        angles = [rng.choice([0, -0.0, 90, 180, rng.uniform(-200, 200)]) for _ in range(3)]
        assert repr(rotation(*angles)) == repr(plain_rotation(*angles))
        world = Transform(Vec3(*(rng.uniform(-3, 3) for _ in range(3))), a)
        point = tuple(rng.choice([0.0, -0.0, rng.uniform(-3, 3)]) for _ in range(3))
        assert repr(world.apply(point)) == repr(plain_apply(world, point))
