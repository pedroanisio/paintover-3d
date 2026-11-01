"""World geometry in metres: x right, y up, z away from the default view.

The engine's frame is y down in centimetres; only the compiler knows that.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable, Sequence, Union

Matrix = tuple[tuple[float, float, float], ...]
IDENTITY: Matrix = ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))


@dataclass(frozen=True)
class Vec3:
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0

    @classmethod
    def of(cls, value: "VecLike") -> "Vec3":
        return value if isinstance(value, Vec3) else cls(*(float(v) for v in value))

    def __add__(self, other: "Vec3") -> "Vec3":
        return Vec3(self.x + other.x, self.y + other.y, self.z + other.z)

    def __sub__(self, other: "Vec3") -> "Vec3":
        return Vec3(self.x - other.x, self.y - other.y, self.z - other.z)

    def __iter__(self):
        return iter((self.x, self.y, self.z))

    @property
    def length(self) -> float:
        return math.sqrt(self.x**2 + self.y**2 + self.z**2)


VecLike = Union[Vec3, Sequence[float]]


def _multiply(a: Matrix, b: Matrix) -> Matrix:
    return tuple(tuple(sum(a[r][k] * b[k][c] for k in range(3)) for c in range(3)) for r in range(3))


def rotation(yaw: float = 0.0, pitch: float = 0.0, roll: float = 0.0) -> Matrix:
    """Yaw turns +z toward +x, pitch turns +z toward +y (looks up), roll turns +x toward +y."""
    y, p, r = (math.radians(v) for v in (yaw, pitch, roll))
    yawed = ((math.cos(y), 0.0, math.sin(y)), (0.0, 1.0, 0.0), (-math.sin(y), 0.0, math.cos(y)))
    pitched = ((1.0, 0.0, 0.0), (0.0, math.cos(p), math.sin(p)), (0.0, -math.sin(p), math.cos(p)))
    rolled = ((math.cos(r), -math.sin(r), 0.0), (math.sin(r), math.cos(r), 0.0), (0.0, 0.0, 1.0))
    return _multiply(yawed, _multiply(pitched, rolled))


@dataclass(frozen=True)
class Transform:
    position: Vec3 = Vec3()
    basis: Matrix = IDENTITY

    @classmethod
    def at(cls, position: VecLike = (0, 0, 0), yaw: float = 0, pitch: float = 0, roll: float = 0) -> "Transform":
        return cls(Vec3.of(position), rotation(yaw, pitch, roll))

    def apply(self, point: VecLike) -> Vec3:
        p = Vec3.of(point)
        moved = [sum(row[c] * v for c, v in enumerate(p)) for row in self.basis]
        return Vec3(*moved) + self.position

    def then(self, child: "Transform") -> "Transform":
        """The child's transform expressed in this transform's parent frame."""
        return Transform(self.apply(child.position), _multiply(self.basis, child.basis))


def aim(eye: VecLike, target: VecLike) -> tuple[float, float]:
    """The yaw and pitch, in degrees, that look from eye to target."""
    d = Vec3.of(target) - Vec3.of(eye)
    if d.length == 0:
        raise ValueError("eye and target are the same point")
    return math.degrees(math.atan2(d.x, d.z)), math.degrees(math.asin(d.y / d.length))


def corners(transform: Transform, half: Vec3) -> Iterable[Vec3]:
    for sx in (-1, 1):
        for sy in (-1, 1):
            for sz in (-1, 1):
                yield transform.apply((sx * half.x, sy * half.y, sz * half.z))
