"""Shots composed around figures, and marks as data for a 2D rig.

A framing is a function in `registry.framings`: it takes figures and `lens`, and gives an eye, a point to look at and a lens.
Shots here are the three a paint-over blockout needs. They are worked out from where the figures' eyes are, so
`location.frame()` takes them again when a figure moves, and a mannequin can block a shot that a character takes over.

`location.blocking()` is the other half of that hand-over: each mark as plain JSON, with its place in the frame of a shot.
"""
from __future__ import annotations

import math
from typing import TYPE_CHECKING, Any, Optional

from srlocations.geometry import Transform, Vec3

if TYPE_CHECKING:
    from srlocations.figures import Figure
    from srlocations.location import Location

GATE = 24.0  # the engine's film gate is this high, in millimetres
CHEST = 0.3  # a close-up shows this far below the eyes, in metres
ABOVE = 0.15  # and this far above them
SHOULDER = (0.28, 0.1, 0.62)  # an over-the-shoulder's eye from the near figure's eyes: to the side, up, and behind


def _distance(tall: float, lens: float) -> float:
    """How far from something to fill the height of the frame with `tall` metres of it."""
    return tall * lens / GATE


def _flat(v: Vec3) -> Vec3:
    size = math.hypot(v.x, v.z)
    return Vec3(v.x / size, 0.0, v.z / size) if size > 1e-9 else Vec3(0, 0, 1)


def _toward(point: Vec3, way: Vec3, far: float) -> Vec3:
    return point + Vec3(way.x * far, way.y * far, way.z * far)


def close_up(figure: "Figure", lens: Optional[float] = None) -> tuple[Vec3, Vec3, float]:
    """Head and shoulders, from the way it faces."""
    lens = lens or 85.0
    eye, ahead = figure.sight()
    tall = CHEST + ABOVE
    middle = eye + Vec3(0, (ABOVE - CHEST) / 2, 0)
    return _toward(middle, _flat(ahead - eye), _distance(tall, lens)), middle, lens


def two_shot(first: "Figure", second: "Figure", lens: Optional[float] = None) -> tuple[Vec3, Vec3, float]:
    """Both from the waist up, from the side they turn to: square on to the line between them."""
    lens = lens or 40.0
    a, b = first.sight()[0], second.sight()[0]
    middle = Vec3((a.x + b.x) / 2, (a.y + b.y) / 2, (a.z + b.z) / 2)
    across = _flat(b - a)
    side = Vec3(-across.z, 0.0, across.x)
    facing = (first.sight()[1] - a) + (second.sight()[1] - b)
    side = side if side.x * facing.x + side.z * facing.z >= 0 else Vec3(-side.x, 0.0, -side.z)
    wide = (b - a).length + 1.2  # a figure's width and some air at each side, at the frame's 16:9
    far = max(_distance(wide * 9 / 16, lens), _distance(1.1, lens))
    return _toward(middle, side, far), middle, lens


def over_the_shoulder(near: "Figure", subject: "Figure", lens: Optional[float] = None) -> tuple[Vec3, Vec3, float]:
    """`subject`, past the shoulder of `near`, on the side of the frame nearer the middle of the set's first figure."""
    lens = lens or 50.0
    a, b = near.sight()[0], subject.sight()[0]
    ahead = _flat(b - a)
    right = Vec3(ahead.z, 0.0, -ahead.x)
    side, up, back = SHOULDER
    return a + Vec3(right.x * side - ahead.x * back, up, right.z * side - ahead.z * back), b, lens


def blocking(location: "Location", shot: str, width: int, height: int) -> list[dict[str, Any]]:
    """Each mark as plain data. Pixels are measured from the top left of a frame this size, and are None behind the camera."""
    from srlocations.compiler import Projection  # built on this module's neighbours
    view, marks = Projection(location.shots[shot], width, height), []
    bodies = {figure.name: figure for figure in location.figures()}
    for mark in location.marks.values():
        at = location.standing(mark.name)
        tall = bodies[mark.name].height if mark.name in bodies else 1.7
        feet, head = view.pixel(at), view.pixel(at + Vec3(0, tall, 0))
        facing = Transform.at(yaw=bodies[mark.name].yaw if mark.name in bodies else mark.facing).apply((0, 0, 1))
        marks.append({"mark": mark.name, "at": [*at], "facing": math.degrees(math.atan2(facing.x, facing.z)), "framing": mark.framing,
                      "height": tall, "feet": list(feet) if feet else None, "head": list(head) if head else None,
                      "scale": view.pixels_per_metre(at),
                      "in_frame": bool(feet and head and 0 <= feet[0] <= width and 0 <= head[1] <= height and feet[1] >= 0 and head[1] <= height)})
    return marks
