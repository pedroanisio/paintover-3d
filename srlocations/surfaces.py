"""Curved solids. A box and a sphere cannot make a seat, so a Surface is any shape x(u, v), y(u, v), z(u, v) can draw.

The expressions are in metres, in the location's frame, and in the language prop templates use (see templates.py), so
angles are in degrees. They are read here as well as by the engine, which is what gives a Surface true bounds, wireframe
lines and an error at build time rather than at render time. The engine fills in the triangles.

    Surface("cos(u) * cos(v)", "sin(v)", "sin(u) * cos(v)", u=(0, 360), v=(-90, 90), closed=(True, False))
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from functools import lru_cache
from typing import Any, Sequence

from srlocations.collision import Cloud, Hull
from srlocations.geometry import Transform, Vec3
from srlocations.nodes import Polyline, Solid
from srlocations.templates import MAX_SURFACE_EXPRESSION, TemplateError, engine_expression, evaluate

MAX_SAMPLES = 512  # along each direction: a catalog is shared data, so a size is enforced on it
TRACED_LINES = (4, 3)  # how finely bounds and wireframes follow a surface


@lru_cache(maxsize=4096)
def _traced(x: str, y: str, z: str, u: tuple[float, float], v: tuple[float, float]) -> tuple[tuple[Vec3, ...], ...]:
    """Points on the surface, a row for each value of v."""
    us = [u[0] + (u[1] - u[0]) * i / (TRACED_LINES[0] * 2) for i in range(TRACED_LINES[0] * 2 + 1)]
    vs = [v[0] + (v[1] - v[0]) * i / (TRACED_LINES[1] * 2) for i in range(TRACED_LINES[1] * 2 + 1)]
    return tuple(tuple(Vec3(*(evaluate(axis, {"u": a, "v": b}, MAX_SURFACE_EXPRESSION) for axis in (x, y, z))) for a in us)
                 for b in vs)


@dataclass
class Surface(Solid):
    x: str = "0"
    y: str = "0"
    z: str = "0"
    u: Sequence[float] = (0.0, 1.0)
    v: Sequence[float] = (0.0, 1.0)
    samples: Sequence[int] = (48, 32)  # vertices along u and along v
    closed: Sequence[bool] = (False, False)  # whether u and v wrap around
    inward: bool = False  # faces the other way, for a shell seen from inside it
    primitive = "parametric"

    def __post_init__(self) -> None:
        self.u, self.v, self.samples, self.closed = tuple(self.u), tuple(self.v), tuple(self.samples), tuple(self.closed)
        if not all(2 <= count <= MAX_SAMPLES for count in self.samples):
            raise TemplateError(f"a surface has 2 to {MAX_SAMPLES} samples each way, not {self.samples}")

    def spec(self) -> dict[str, Any]:
        """What a catalog stores."""
        return {"x": self.x, "y": self.y, "z": self.z, "u": list(self.u), "v": list(self.v),
                "samples": list(self.samples), "closed": list(self.closed), "inward": self.inward}

    def dimensions(self) -> dict[str, float]:
        return {}

    def dress(self, element: Any) -> None:
        # The engine's y points down, which mirrors the surface and would turn it inside out, so v runs backwards.
        turned = not self.inward
        names = {"u": "u", "v": f"({self.v[0] + self.v[1]}-v)" if turned else "v"}
        x, y, z = (engine_expression(axis, names) for axis in (self.x, self.y, self.z))
        element.add_parametricSurface(x=f"100*{x}", y=f"-100*{y}", z=f"100*{z}", u0=self.u[0], u1=self.u[1], v0=self.v[0],
                                      v1=self.v[1], uSamples=self.samples[0], vSamples=self.samples[1],
                                      closedU=self.closed[0], closedV=self.closed[1])

    def bands(self, spacing: float) -> list[Solid]:
        """Along v, measured down the middle of the surface."""
        traced = _traced(self.x, self.y, self.z, self.u, self.v)
        middle = [row[len(row) // 2] for row in traced]
        count = round(sum((b - a).length for a, b in zip(middle, middle[1:])) / spacing)
        if count < 2:
            return []
        low, high = self.v
        rows = max(2, self.samples[1] // count + 1)
        return [replace(self, v=(low + (high - low) * i / count, low + (high - low) * (i + 1) / count),
                        samples=(self.samples[0], rows), closed=(self.closed[0], False), casts_shadow=False)
                for i in range(count)]

    def _points(self) -> list[Vec3]:
        return [point for row in _traced(self.x, self.y, self.z, self.u, self.v) for point in row]

    def half_extents(self) -> Vec3:
        return Vec3(*(max(abs(getattr(p, axis)) for p in self._points()) for axis in "xyz"))

    def bounds(self, world: Transform) -> tuple[Vec3, Vec3]:
        points = [world.apply(point) for point in self._points()]
        return (Vec3(*(min(getattr(p, a) for p in points) for a in "xyz")),
                Vec3(*(max(getattr(p, a) for p in points) for a in "xyz")))

    def hulls(self, world: Transform) -> list[Hull]:
        """A surface need not be convex, so it is its patches: a body crossing it is seen, and one wholly inside is not."""
        rows = [[world.apply(point) for point in row] for row in _traced(self.x, self.y, self.z, self.u, self.v)]
        return [Cloud([rows[v][u], rows[v][u + 1], rows[v + 1][u + 1], rows[v + 1][u]])
                for v in range(len(rows) - 1) for u in range(len(rows[0]) - 1)]

    def edges(self) -> list[Polyline]:
        rows = [[tuple(point) for point in row] for row in _traced(self.x, self.y, self.z, self.u, self.v)]
        return [*rows[::2], *([row[i] for row in rows] for i in range(0, len(rows[0]), 2))]
