"""Textures measured in the world. The engine maps a picture 0 to 1 on every face of a primitive, with a scale per material
and no offset, so two boxes side by side cannot continue one picture. A model carries its own UVs, so a box with a tiled
texture is written as a small OBJ whose UVs come from where its faces are.

Heights give v, so brick courses run level around a room. Along a wall u is x - z, the same number on both walls at any
corner, so a pattern also meets itself at all four. The price is that u runs backwards on two of the four walls, which a
pattern does not show and lettering would. A floor or a ceiling takes x and z.
"""
from __future__ import annotations

import hashlib
import math
import os
from pathlib import Path

from srlocations.geometry import Transform, Vec3
from srlocations.mesh import Mesh
from srlocations.nodes import Solid
from srlocations.portable import cache_folder

ACROSS = Vec3(1, 0, -1)  # u is the distance along this on a wall, which is what makes corners meet
FLAT = 0.7  # a face with more of its normal than this along y lies down


def dot(a: Vec3, b: Vec3) -> float:
    return a.x * b.x + a.y * b.y + a.z * b.z


def wall_uv(point: Vec3, normal: Vec3) -> tuple[float, float]:
    """A point on a face that stands up, in metres. A sloped face measures up its own slope."""
    length = math.hypot(normal.x, normal.z)
    out = Vec3(normal.x / length, 0, normal.z / length)
    along = Vec3(out.z, 0, -out.x)
    sign = -1.0 if dot(along, ACROSS) < 0 else 1.0
    up = Vec3(-out.x * normal.y, length, -out.z * normal.y)
    return sign * dot(point, along) + dot(point, out) * dot(out, ACROSS), dot(point, up)


def world_uv(point: Vec3, normal: Vec3) -> tuple[float, float]:
    return (point.x, point.z) if abs(normal.y) > FLAT else wall_uv(point, normal)


def sheet(solid: Solid, world: Transform, tile: float, grow: float = 0.0) -> Mesh:
    """The solid as a model with one repeat of a picture to every `tile` metres. A model is turned on import, so a point
    (x, y, z) here is written (x, y, -z). That reverses which way round a face winds, and the engine does not draw the
    back of a face. `grow` closes cracks between sections, and the picture stays where it was."""
    half = solid.half_extents()
    scale = Vec3(*(1 + grow / (2 * h) if h else 1.0 for h in half))
    lines = ["o sheet"]
    for number, (corners, normal) in enumerate(solid.faces()):
        turned = world.apply(normal) - world.position
        for corner in corners:
            grown = Vec3(corner.x * scale.x, corner.y * scale.y, corner.z * scale.z)
            u, v = world_uv(world.apply(corner), turned)
            lines += [f"v {grown.x:.5f} {grown.y:.5f} {-grown.z:.5f}", f"vt {u / tile:.5f} {v / tile:.5f}"]
        lines.append(f"vn {normal.x:.0f} {normal.y:.0f} {-normal.z:.0f}")
        a, b, c = corners[0], corners[1], corners[2]
        first = number * 4 + 1
        order = (3, 2, 1, 0) if dot(cross(b - a, c - a), normal) > 0 else (0, 1, 2, 3)
        lines.append("f " + " ".join(f"{first + i}/{first + i}/{number + 1}" for i in order))
    text = "\n".join(lines) + "\n"
    path = cache_folder("sheets") / f"{hashlib.sha256(text.encode()).hexdigest()}.obj"
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(f".{os.getpid()}.tmp")
        temporary.write_text(text)
        temporary.replace(path)
    return Mesh(path, casts_shadow=solid.casts_shadow)


def cross(a: Vec3, b: Vec3) -> Vec3:
    return Vec3(a.y * b.z - a.z * b.y, a.z * b.x - a.x * b.z, a.x * b.y - a.y * b.x)
