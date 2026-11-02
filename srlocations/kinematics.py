"""Limbs solved by geometry instead of by search.

A limb of two bones, such as an upper arm and a forearm, reaches a point in one way up to a turn about the line from its root
to that point. The law of cosines gives the bend at the middle joint from the two lengths and the distance, and a pole, a point
the elbow or knee should point toward, picks the turn. What is left is to say that rotation in a joint's own angles, in the
order the joint applies them. Of the two angle sets that give the same rotation, the one nearer the angles a joint has now is
kept, and each angle is moved by whole turns to the one nearest its old value, so a pose never flips between frames.

Nothing here knows a skeleton. `stock/mannequin.py` gives the lengths, frames and ranges.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional, Sequence

from srlocations.geometry import Matrix, Transform, Vec3, VecLike

# Each turn of `rotation()` as an axis and the sign of a right-handed turn about it: pitch turns +z toward +y, which is a
# negative turn about +x.
AXES = {"yaw": (Vec3(0, 1, 0), 1.0), "pitch": (Vec3(1, 0, 0), -1.0), "roll": (Vec3(0, 0, 1), 1.0)}
STRAIGHT = 1e-6  # a limb is never solved quite straight, so the plane it bends in stays known


@dataclass(frozen=True)
class Hold:
    """A hand or a foot kept at a point in the location, whatever the rest of the figure does. With `basis` it keeps that
    orientation too, as far as its joints allow, and `pole` is a point the elbow or knee points toward."""
    joint: str
    at: Vec3
    basis: Optional[Matrix] = None
    pole: Optional[Vec3] = None


def dot(a: Vec3, b: Vec3) -> float:
    return a.x * b.x + a.y * b.y + a.z * b.z


def cross(a: Vec3, b: Vec3) -> Vec3:
    return Vec3(a.y * b.z - a.z * b.y, a.z * b.x - a.x * b.z, a.x * b.y - a.y * b.x)


def scaled(a: Vec3, factor: float) -> Vec3:
    return Vec3(a.x * factor, a.y * factor, a.z * factor)


def unit(a: Vec3) -> Vec3:
    return scaled(a, 1 / a.length) if a.length > 1e-12 else Vec3()


def turned(axis: Vec3, radians: float, point: Vec3) -> Vec3:
    """A point turned about an axis through the origin, right-handed (Rodrigues' formula)."""
    c, s = math.cos(radians), math.sin(radians)
    return scaled(point, c) + scaled(cross(axis, point), s) + scaled(axis, dot(axis, point) * (1 - c))


def transposed(m: Matrix) -> Matrix:
    return tuple(tuple(m[c][r] for c in range(3)) for r in range(3))


def bend(upper: float, lower: float, distance: float) -> float:
    """How far, in degrees, the second bone turns from the line of the first for the limb's two ends to be `distance` apart:
    0 for a straight limb. A distance out of reach gives the nearest the limb can do."""
    if upper <= 0 or lower <= 0:
        return 0.0
    distance = min(distance, (upper + lower) * (1 - STRAIGHT))
    cosine = (distance * distance - upper * upper - lower * lower) / (2 * upper * lower)
    return math.degrees(math.acos(max(-1.0, min(1.0, cosine))))


def middle(end: VecLike, upper: float, lower: float, pole: VecLike, fallback: VecLike = (0, 0, -1)) -> Vec3:
    """Where the middle joint goes, from a root at the origin, for the far end to be at `end`: on the circle of points
    `upper` from the root and `lower` from the end, on the side toward `pole`. Where `pole` lies on the line to the end,
    `fallback` is used. An end out of reach puts the joint on the line toward it."""
    end, pole = Vec3.of(end), Vec3.of(pole)
    distance = end.length
    if distance < 1e-12:
        raise ValueError("a limb cannot reach its own root")
    way = scaled(end, 1 / distance)
    reach = min(distance, (upper + lower) * (1 - STRAIGHT))
    along = (upper * upper - lower * lower + reach * reach) / (2 * reach)
    radius = math.sqrt(max(0.0, upper * upper - along * along))
    return scaled(way, along) + scaled(_across(way, pole, fallback), radius)


def _across(way: Vec3, pole: Vec3, fallback: VecLike) -> Vec3:
    """The part of `pole` square to `way`, as a unit vector."""
    for candidate in (pole, Vec3.of(fallback), Vec3(0, 0, -1), Vec3(0, 1, 0)):
        square = candidate - scaled(way, dot(candidate, way))
        if square.length > 1e-6 * max(1.0, candidate.length):
            return unit(square)
    raise ValueError("no direction is square to the limb")  # cannot happen: two fixed candidates are square to each other


def framed(first: Vec3, normal: Vec3) -> Matrix:
    """A rotation from the axes to a frame whose x is along `first` and whose z is along `normal`, square to it."""
    x = unit(first)
    z = unit(normal - scaled(x, dot(normal, x)))
    y = cross(z, x)
    return tuple(tuple(tuple((x, y, z)[c])[r] for c in range(3)) for r in range(3))


def carrying(first: Vec3, second: Vec3, onto_first: Vec3, onto_second: Vec3) -> Matrix:
    """The rotation that turns `first` along `onto_first` and the plane of the two vectors onto the plane of the other two,
    with `second` on the same side."""
    source = framed(first, cross(first, second))
    target = framed(onto_first, cross(onto_first, onto_second))
    return tuple(tuple(sum(target[r][k] * source[c][k] for k in range(3)) for c in range(3)) for r in range(3))


def apply(m: Matrix, point: Vec3) -> Vec3:
    return Transform(basis=m).apply(point)


def angles(m: Matrix, turns: Sequence[str]) -> list[tuple[float, float, float]]:
    """The angles, in degrees, of three turns applied in order (each in the frame the one before left) that make the rotation
    `m`: two sets, as any rotation has. Turns are "yaw", "pitch" and "roll"; the first and last may be the same, as in a yaw,
    then a pitch, then a yaw."""
    if len(turns) != 3 or turns[0] == turns[1] or turns[1] == turns[2]:
        raise ValueError(f"three turns, each unlike the next, not {tuple(turns)}")
    (a, sa), (b, sb), (c, sc) = (AXES[turn] for turn in turns)
    v = apply(m, c)
    if turns[0] == turns[2]:  # proper Euler angles: the middle turn is the angle between the first axis and where it went
        middle_angle = math.acos(max(-1.0, min(1.0, dot(a, v))))
        middles = (middle_angle, -middle_angle)
    else:
        handed = dot(a, cross(b, c))
        middle_angle = math.asin(max(-1.0, min(1.0, handed * dot(a, v))))
        middles = (middle_angle, math.pi - middle_angle)
    square = next(axis for axis, _ in AXES.values() if abs(dot(axis, c)) < 0.5)
    found = []
    for second in middles:
        reached = turned(b, second, c)
        first = _between(a, reached, v)
        rest = turned(b, -second, turned(a, -first, apply(m, square)))
        third = _between(c, square, rest)
        found.append(tuple(math.degrees(angle) * sign for angle, sign in ((first, sa), (second, sb), (third, sc))))
    return found


def _between(axis: Vec3, start: Vec3, end: Vec3) -> float:
    """The right-handed turn about `axis` that takes `start` nearest to `end`."""
    p = start - scaled(axis, dot(axis, start))
    q = end - scaled(axis, dot(axis, end))
    if p.length < 1e-9 or q.length < 1e-9:
        return 0.0  # the axis points at it, so any turn will do
    return math.atan2(dot(axis, cross(p, q)), dot(p, q))


def nearest(angle: float, near: float) -> float:
    """The angle equal to `angle` by whole turns that is nearest to `near`."""
    return angle + 360.0 * round((near - angle) / 360.0)
