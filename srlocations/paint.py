"""Paint over a location, in two kinds. A PaintLayer is 2D and sits on top of the picture: its marks can be anchored to
world points, so they follow any shot, or to the frame. A Decal is paint on the set: a flat shape on a surface that
props can pass in front of, as it goes through the depth buffer like any solid.
"""
from __future__ import annotations

import struct
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional, Protocol, Sequence, Union

from srlocations.geometry import Vec3, VecLike
from srlocations.nodes import Polyline, Solid

Pixel = tuple[float, float]
KAPPA = 0.5523  # a cubic Bezier's handle for a quarter circle


class View(Protocol):
    width: int
    height: int

    def pixel(self, point: Vec3) -> Optional[Pixel]: ...

    def pixels_per_metre(self, point: Vec3) -> float: ...


def curve(points: Sequence[Pixel], closed: bool = False, smooth: bool = True, scale: float = 1.0) -> str:
    """SVG path data through the points; smooth makes a Catmull-Rom curve that passes through each one."""
    fmt = lambda p: f"{p[0] * scale:.2f} {p[1] * scale:.2f}"
    path = "M" + fmt(points[0])
    count = len(points)
    if not smooth or count < 3:
        path += "".join("L" + fmt(p) for p in points[1:])
    else:
        at = (lambda i: points[i % count]) if closed else (lambda i: points[max(0, min(count - 1, i))])
        for i in range(count if closed else count - 1):
            p0, p1, p2, p3 = at(i - 1), at(i), at(i + 1), at(i + 2)
            first = (p1[0] + (p2[0] - p0[0]) / 6, p1[1] + (p2[1] - p0[1]) / 6)
            second = (p2[0] - (p3[0] - p1[0]) / 6, p2[1] - (p3[1] - p1[1]) / 6)
            path += f"C{fmt(first)} {fmt(second)} {fmt(p2)}"
    return path + ("Z" if closed else "")


class PaintItem(ABC):
    """One mark. `frame=True` reads its points as fractions of the frame, x right and y down, instead of world metres."""

    @abstractmethod
    def draw(self, canvas: "Canvas", node_id: str) -> None:
        ...


@dataclass
class Anchored(PaintItem):
    color: str = field(default="#000000", kw_only=True)
    frame: bool = field(default=False, kw_only=True)

    def anchor(self, view: View, point: VecLike) -> Optional[Pixel]:
        x, y, *_ = (*point, 0.0)
        return (x * view.width, y * view.height) if self.frame else view.pixel(Vec3.of(point))

    def anchors(self, view: View, points: Sequence[VecLike]) -> Optional[list[Pixel]]:
        """Every point in pixels; a mark with a point behind the camera is left out of that shot whole."""
        pixels = [self.anchor(view, point) for point in points]
        return None if any(pixel is None for pixel in pixels) else pixels

    def size(self, view: View, point: VecLike, value: float) -> float:
        """A size in metres at the point, or for a frame mark in fractions of the frame's height."""
        return value * view.height if self.frame else value * view.pixels_per_metre(Vec3.of(point))


@dataclass
class Stroke(Anchored):
    points: Sequence[VecLike] = ()
    width: float = 0.03
    closed: bool = False
    smooth: bool = True

    def draw(self, canvas: "Canvas", node_id: str) -> None:
        pixels = self.anchors(canvas.view, self.points)
        if pixels:
            middle = self.points[len(self.points) // 2]
            canvas.shape(node_id, curve(pixels, self.closed, self.smooth), stroke=self.color,
                         strokeWidth=round(self.size(canvas.view, middle, self.width), 3), fill="#00000000")


@dataclass
class Fill(Anchored):
    points: Sequence[VecLike] = ()
    smooth: bool = False

    def draw(self, canvas: "Canvas", node_id: str) -> None:
        pixels = self.anchors(canvas.view, self.points)
        if pixels:
            canvas.shape(node_id, curve(pixels, True, self.smooth), fill=self.color)


@dataclass
class Disc(Anchored):
    """A circle that always faces the camera. `radius` is in metres, or fractions of the frame's height."""
    center: VecLike = (0, 0, 0)
    radius: float = 0.1

    def draw(self, canvas: "Canvas", node_id: str) -> None:
        middle = self.anchor(canvas.view, self.center)
        if middle is not None:
            x, y, r = *middle, self.size(canvas.view, self.center, self.radius)
            k = r * KAPPA
            canvas.shape(node_id, f"M{x + r:.2f} {y:.2f}C{x + r:.2f} {y + k:.2f} {x + k:.2f} {y + r:.2f} {x:.2f} {y + r:.2f}"
                                  f"C{x - k:.2f} {y + r:.2f} {x - r:.2f} {y + k:.2f} {x - r:.2f} {y:.2f}"
                                  f"C{x - r:.2f} {y - k:.2f} {x - k:.2f} {y - r:.2f} {x:.2f} {y - r:.2f}"
                                  f"C{x + k:.2f} {y - r:.2f} {x + r:.2f} {y - k:.2f} {x + r:.2f} {y:.2f}Z", fill=self.color)


def png_size(path: Path) -> tuple[int, int]:
    with path.open("rb") as image:
        head = image.read(24)
    if head[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError(f"{path} is not a PNG")
    return struct.unpack(">II", head[16:24])


@dataclass
class Picture(PaintItem):
    """A finished paintover: a transparent PNG laid across the whole frame. Render a shot, paint on it, bring it back."""
    path: Union[str, Path] = ""

    def draw(self, canvas: "Canvas", node_id: str) -> None:
        path = Path(self.path).resolve()
        asset = canvas.image(f"{node_id}-file", path, *png_size(path))
        canvas.group.add_layer(id=node_id, asset=asset, x=0, y=0, anchorX=0, anchorY=0,
                               scaleX=round(canvas.view.width / png_size(path)[0] * 100, 4),
                               scaleY=round(canvas.view.height / png_size(path)[1] * 100, 4))


class StandeeView:
    """Local metres, x right and y up, on a card that stands at one world point and always faces the camera."""

    def __init__(self, view: View, at: Pixel, scale: float) -> None:
        self.width, self.height, self.at, self.scale = view.width, view.height, at, scale

    def pixel(self, point: Vec3) -> Pixel:
        return self.at[0] + point.x * self.scale, self.at[1] - point.y * self.scale

    def pixels_per_metre(self, point: Vec3) -> float:
        return self.scale


@dataclass
class Standee(Anchored):
    """Marks on a card standing at `at`, sized by distance: a paper figure that is flat but never seen edge-on."""
    at: VecLike = (0, 0, 0)
    marks: Sequence[Anchored] = ()

    def draw(self, canvas: "Canvas", node_id: str) -> None:
        foot = self.anchor(canvas.view, self.at)
        if foot is not None:
            card = Canvas(canvas.scene, canvas.group, StandeeView(canvas.view, foot, self.size(canvas.view, self.at, 1.0)))
            for number, mark in enumerate(self.marks):
                mark.draw(card, f"{node_id}-{number}")


MARKS = {"stroke": Stroke, "fill": Fill, "disc": Disc, "picture": Picture}


@dataclass
class PaintLayer:
    """Marks that composite together, as a layer does in a paint program. `shots` and `looks` limit it to some shots and
    some looks, by name; empty means all of them."""
    name: str
    blend: str = "normal"
    opacity: float = 1.0
    shots: Sequence[str] = ()
    items: list[PaintItem] = field(default_factory=list)
    looks: Sequence[str] = ()

    def add(self, item: PaintItem) -> "PaintLayer":
        self.items.append(item)
        return self

    def stroke(self, points: Sequence[VecLike], **params: Any) -> "PaintLayer":
        return self.add(Stroke(points=points, **params))

    def fill(self, points: Sequence[VecLike], **params: Any) -> "PaintLayer":
        return self.add(Fill(points=points, **params))

    def disc(self, center: VecLike, radius: float, **params: Any) -> "PaintLayer":
        return self.add(Disc(center=center, radius=radius, **params))

    def picture(self, path: Union[str, Path]) -> "PaintLayer":
        return self.add(Picture(path=path))

    def standee(self, at: VecLike, marks: Sequence[Anchored]) -> "PaintLayer":
        return self.add(Standee(at=at, marks=marks))

    @classmethod
    def from_spec(cls, spec: dict, base: Path = Path(".")) -> "PaintLayer":
        values = {key: value for key, value in spec.items() if key != "items"}
        layer = cls(**values)
        for item in spec.get("items", ()):
            item = dict(item)
            name = item.pop("kind", None)
            if name not in MARKS:
                raise ValueError(f"layer {layer.name!r}: a mark has kind {', '.join(MARKS)}, not {name!r}")
            kind = MARKS[name]
            if kind is Picture:
                item["path"] = base / item["path"]
            layer.add(kind(**item))
        return layer


class Canvas:
    """Where one layer draws, for one shot of one document."""

    def __init__(self, scene: Any, group: Any, view: View) -> None:
        self.scene, self.group, self.view = scene, group, view

    def shape(self, node_id: str, path: str, **paint: Any) -> None:
        self.group.add_shape(id=node_id, shape="path", path=path, x=0, y=0, anchorX=0, anchorY=0,
                             width=self.view.width, height=self.view.height, **paint)

    def image(self, asset_id: str, path: Path, width: int, height: int) -> str:
        if not self.scene.find_all("assets"):
            self.scene.add_assets()
        self.scene.find_all("assets")[0].add_image(id=asset_id, src=str(path), width=width, height=height)
        return asset_id


def paint_over(scene: Any, composition: Any, layers: Sequence[PaintLayer], shot: str, view: View, look: str) -> None:
    """Adds the location's paint for this shot and look on top of everything before it in the composition."""
    for index, layer in enumerate(layers):
        if layer.items and (not layer.shots or shot in layer.shots) and (not layer.looks or look in layer.looks):
            group = composition.add_group(id=f"paint-{index}", blend=layer.blend, opacity=layer.opacity)
            canvas = Canvas(scene, group, view)
            for number, item in enumerate(layer.items):
                item.draw(canvas, f"paint-{index}-{number}")


@dataclass
class Decal(Solid):
    """A flat shape painted on the set, drawn in the local x-y plane and facing -z. Its origin is its outline's centre."""
    outline: Sequence[tuple[float, float]] = ((-0.5, -0.5), (0.5, -0.5), (0.5, 0.5), (-0.5, 0.5))
    smooth: bool = False
    thickness: float = 0.004
    looks: Sequence[str] = ()
    primitive = "extrude"

    def __post_init__(self) -> None:
        self.casts_shadow = False

    def drawn_in(self, look: str) -> bool:
        return not self.looks or look in self.looks

    def _centred(self) -> list[tuple[float, float]]:
        xs, ys = [p[0] for p in self.outline], [p[1] for p in self.outline]
        cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
        return [(x - cx, y - cy) for x, y in self.outline]

    def dimensions(self) -> dict[str, float]:
        return {"depth": self.thickness}

    def geometry(self, units: float) -> dict[str, Any]:
        return {"path": curve([(x, -y) for x, y in self._centred()], True, self.smooth, units)}

    def half_extents(self) -> Vec3:
        points = self._centred()
        return Vec3(max(abs(p[0]) for p in points), max(abs(p[1]) for p in points), self.thickness / 2)

    def edges(self) -> list[Polyline]:
        points = [(x, y, 0.0) for x, y in self._centred()]
        return [[*points, points[0]]]
