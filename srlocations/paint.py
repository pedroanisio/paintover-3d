"""Paint over a location, in two kinds. A PaintLayer is 2D and sits on top of the picture: its marks can be anchored to
world points, so they follow any shot, or to the frame. A Decal is paint on the set: a flat shape on a surface that
props can pass in front of, as it goes through the depth buffer like any solid.

A layer with `depth` stays 2D, but the set hides it. Paint has no depth of its own, so each mark gets a hidden mask, a
track matte: the solids that could cover it in black and a white card where the mark is, drawn through the depth buffer.
What stays white is what can be seen. Each mark has its own mask so that one figure's clear corners never show another
through a solid, and a mask holds only the solids in the way, so a mark with nothing in front of it costs nothing.
"""
from __future__ import annotations

import math
import struct
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional, Protocol, Sequence, Union

from srlocations.collision import Hull
from srlocations.geometry import Transform, Vec3, VecLike
from srlocations.nodes import Box as Block, Placed, Polyline, Solid

Pixel = tuple[float, float]
Box = tuple[int, int, int, int]  # left, top, right and bottom, in a picture's pixels
KAPPA = 0.5523  # a cubic Bezier's handle for a quarter circle
BODY = 0.15  # a card stands this far toward the camera from its mark: the front of a body, and it clears a rug under the feet
ROOMY = 1.5  # how much bigger than its mark a card is; only the mark's own pixels are drawn, so more is harmless
FLAT = 0.02  # marks whose points span less height than this lie on a surface
THIN = 0.002
BLACK, WHITE = "paint-hold-black", "paint-hold-white"


class View(Protocol):
    width: int
    height: int

    def pixel(self, point: Vec3) -> Optional[Pixel]: ...

    def pixels_per_metre(self, point: Vec3) -> float: ...


@dataclass(frozen=True)
class Card:
    """Where a mark is, for the set to hide it. Upright it faces the camera with `at` the middle of its bottom edge, and
    lying down `at` is its centre and `height` runs along z. It stands in for a mark at one distance."""
    at: Vec3
    width: float
    height: float
    lying: bool = False

    def placed(self, eye: Vec3) -> Placed:
        away = eye - self.at
        reach = max(away.length, 1e-6)
        ahead = Vec3(*(value * min(BODY, reach / 2) / reach for value in away))
        spot = self.at + ahead
        if self.lying:
            size = (self.width * ROOMY, THIN, self.height * ROOMY)
            return next(Block(size=size, at=spot, name="card").walk())
        tall = self.height * ROOMY
        card = Block(size=(self.width * ROOMY, tall, THIN), at=spot + Vec3(0, tall / 2, 0), name="card",
                     yaw=math.degrees(math.atan2(away.x, away.z)))
        return next(card.walk())


def spread(points: Sequence[VecLike], margin: float = 0.0) -> list[Card]:
    """A card around world points: lying down if they lie flat, else upright at their middle."""
    if not points:
        return []
    xs, ys, zs = zip(*(tuple(Vec3.of(point)) for point in points))
    wide, deep, tall = max(xs) - min(xs), max(zs) - min(zs), max(ys) - min(ys)
    middle = (min(xs) + max(xs)) / 2, (min(zs) + max(zs)) / 2
    if tall < FLAT:
        return [Card(Vec3(middle[0], min(ys), middle[1]), wide + 2 * margin, deep + 2 * margin, lying=True)]
    return [Card(Vec3(middle[0], min(ys) - margin, middle[1]), math.hypot(wide, deep) + 2 * margin, tall + 2 * margin)]


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

    def cards(self, view: View) -> Sequence[Card]:
        """Where it is in the set. None of them leaves it on top of everything, even in a layer with depth."""
        return ()


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

    def reach(self) -> Sequence[VecLike]:
        """The points it spans."""
        return ()

    def cards(self, view: View) -> Sequence[Card]:
        return () if self.frame else spread(self.reach())


@dataclass
class Stroke(Anchored):
    points: Sequence[VecLike] = ()
    width: float = 0.03
    closed: bool = False
    smooth: bool = True

    def reach(self) -> Sequence[VecLike]:
        return self.points

    def cards(self, view: View) -> Sequence[Card]:
        return () if self.frame else spread(self.points, self.width)

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

    def reach(self) -> Sequence[VecLike]:
        return self.points

    def draw(self, canvas: "Canvas", node_id: str) -> None:
        pixels = self.anchors(canvas.view, self.points)
        if pixels:
            canvas.shape(node_id, curve(pixels, True, self.smooth), fill=self.color)


@dataclass
class Disc(Anchored):
    """A circle that always faces the camera. `radius` is in metres, or fractions of the frame's height."""
    center: VecLike = (0, 0, 0)
    radius: float = 0.1

    def reach(self) -> Sequence[VecLike]:
        x, y, *rest = (*self.center, 0.0)
        return [(x - self.radius, y - self.radius, *rest), (x + self.radius, y + self.radius, *rest)]

    def cards(self, view: View) -> Sequence[Card]:
        if self.frame:
            return ()
        foot = Vec3.of(self.center) - Vec3(0, self.radius, 0)
        return [Card(foot, 2 * self.radius, 2 * self.radius)]

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
                               scaleX=round(canvas.view.width / png_size(path)[0], 6),
                               scaleY=round(canvas.view.height / png_size(path)[1], 6))


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

    def cards(self, view: View) -> Sequence[Card]:
        spans = [tuple(Vec3.of(point)) for mark in self.marks for point in mark.reach()]
        if self.frame or not spans:
            return ()
        return [Card(Vec3.of(self.at), 2 * max(abs(x) for x, *_ in spans), max(y for _, y, *_ in spans))]

    def draw(self, canvas: "Canvas", node_id: str) -> None:
        foot = self.anchor(canvas.view, self.at)
        if foot is not None:
            card = Canvas(canvas.scene, canvas.group, StandeeView(canvas.view, foot, self.size(canvas.view, self.at, 1.0)))
            for number, mark in enumerate(self.marks):
                mark.draw(card, f"{node_id}-{number}")


@dataclass
class Sticker(Anchored):
    """A transparent picture standing at `at`, `height` tall and sized by distance. `box` is the part of the picture the
    height is measured on, all of it by default, and the middle of its bottom edge stands on the point."""
    at: VecLike = (0, 0, 0)
    path: Union[str, Path] = ""
    height: float = 1.0
    box: Optional[Box] = None
    flip: bool = False

    def cards(self, view: View) -> Sequence[Card]:
        if self.frame:
            return ()
        width, tall = png_size(Path(self.path).resolve())
        left, top, right, bottom = self.box or (0, 0, width, tall)
        metres = self.height / (bottom - top)
        return [Card(Vec3.of(self.at), 2 * metres * max((left + right) / 2, width - (left + right) / 2), metres * bottom)]

    def draw(self, canvas: "Canvas", node_id: str) -> None:
        foot = self.anchor(canvas.view, self.at)
        if foot is None:
            return
        path = Path(self.path).resolve()
        width, tall = png_size(path)
        left, top, right, bottom = self.box or (0, 0, width, tall)
        scale = round(self.size(canvas.view, self.at, self.height) / (bottom - top), 6)
        canvas.group.add_layer(id=node_id, asset=canvas.image(f"{node_id}-file", path, width, tall), x=round(foot[0], 2),
                               y=round(foot[1], 2), anchorX=(left + right) / 2, anchorY=bottom,
                               scaleX=-scale if self.flip else scale, scaleY=scale)


MARKS = {"stroke": Stroke, "fill": Fill, "disc": Disc, "picture": Picture, "sticker": Sticker, "standee": Standee}


def mark_from_spec(item: dict, base: Path, spots: Mapping[str, Any]) -> Anchored | Picture:
    """One mark from data. A picture's path is relative to `base`, and a sticker or standee can stand on a mark's name."""
    values = dict(item)
    name = values.pop("kind", None)
    if name not in MARKS:
        raise ValueError(f"a mark has kind {', '.join(MARKS)}, not {name!r}")
    if "path" in values:
        values["path"] = base / values["path"]
    if isinstance(values.get("at"), str):
        if values["at"] not in spots:
            raise ValueError(f"a {name} stands on mark {values['at']!r}, and there is no such mark")
        values["at"] = spots[values["at"]].at
    if name == "standee":
        values["marks"] = [mark_from_spec(mark, base, spots) for mark in values.get("marks", ())]
    return MARKS[name](**values)


@dataclass
class PaintLayer:
    """Marks that composite together, as a layer does in a paint program. `shots` and `looks` limit it to some shots and
    some looks, by name; empty means all of them. With `depth` the set hides its marks in world space, and frame marks and
    pictures stay on top. Without it the layer lies over everything, as paint on a finished frame does."""
    name: str
    blend: str = "normal"
    opacity: float = 1.0
    shots: Sequence[str] = ()
    items: list[PaintItem] = field(default_factory=list)
    looks: Sequence[str] = ()
    depth: bool = False

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
    def from_spec(cls, spec: dict, base: Path = Path("."), spots: Optional[Mapping[str, Any]] = None) -> "PaintLayer":
        values = {key: value for key, value in spec.items() if key != "items"}
        layer = cls(**values)
        for item in spec.get("items", ()):
            try:
                layer.add(mark_from_spec(item, base, spots or {}))
            except ValueError as error:
                raise ValueError(f"layer {layer.name!r}: {error}") from error
        return layer


@dataclass(frozen=True)
class Reach:
    """How much of a shot a box takes up. `frame` is its rectangle in pixels, None if it passes the camera."""
    low: Vec3
    high: Vec3
    near: float
    far: float
    frame: Optional[tuple[float, float, float, float]]

    def overlaps(self, other: "Reach") -> bool:
        if self.frame is None or other.frame is None:
            return True
        a, b = self.frame, other.frame
        return a[0] <= b[2] and b[0] <= a[2] and a[1] <= b[3] and b[1] <= a[3]


class Holdout:
    """Makes the masks of one document: its solids, ready to be drawn black behind a card."""

    def __init__(self, compiler: Any, scene: Any, solids: Iterable[Placed], view: Any, effects: str = "") -> None:
        self.compiler, self.scene, self.view, self.effects = compiler, scene, view, effects
        self.solids = [(leaf, self.reach(leaf)) for leaf in solids]
        self.ready = False

    def reach(self, leaf: Placed) -> Reach:
        low, high = leaf.item.bounds(leaf.world)
        points = [Vec3(x, y, z) for x in (low.x, high.x) for y in (low.y, high.y) for z in (low.z, high.z)]
        depths = [self.view.to_camera(point).z for point in points]
        pixels = [self.view.pixel(point) for point in points]
        frame = None
        if all(pixels):
            xs, ys = zip(*pixels)
            frame = min(xs), min(ys), max(xs), max(ys)
        return Reach(low, high, min(depths), max(depths), frame)

    def covers(self, solid: Reach, card: Reach) -> bool:
        """Whether a solid can come between the camera and a card. From above, nothing wholly under a card can."""
        under = solid.high.y <= card.low.y < self.view.eye.y
        return solid.near <= card.far and not under and solid.overlaps(card)

    def matte(self, parent: Any, node_id: str, cards: Sequence[Card]) -> Optional[str]:
        """The id of a mask for these cards, or None when no solid is in the way."""
        placed = [card.placed(self.view.eye) for card in cards]
        reaches = [self.reach(leaf) for leaf in placed]
        ahead = [leaf for leaf, reach in self.solids if any(self.covers(reach, card) for card in reaches)]
        if not ahead:
            return None
        if not self.ready:
            self.ready = True
            library = (self.scene.find_all("materials") or [self.scene.add_materials()])[0]
            library.add_material(id=BLACK, baseColor="#000000", unlit=True)
            library.add_material(id=WHITE, baseColor="#ffffff", unlit=True)
        matte_id = f"{node_id}-matte"
        group = parent.add_group(id=matte_id, **({"effects": self.effects} if self.effects else {}))
        for index, leaf in enumerate(ahead):
            self.compiler.draw(group, leaf, index, f"{node_id}-", BLACK, shadow=False)
        for index, leaf in enumerate(placed):
            self.compiler.draw(group, leaf, index, f"{node_id}-", WHITE, shadow=False)
        return matte_id


class Canvas:
    """Where one layer draws, for one shot of one document. With a `holdout`, the set hides what is placed on it."""

    def __init__(self, scene: Any, group: Any, view: View, holdout: Optional[Holdout] = None) -> None:
        self.scene, self.group, self.view, self.holdout = scene, group, view, holdout

    def place(self, item: PaintItem, node_id: str) -> None:
        """Draws a mark, behind the set if this canvas has depth."""
        cards = item.cards(self.view) if self.holdout else ()
        matte = self.holdout.matte(self.group, node_id, cards) if cards else None
        if matte is None:
            item.draw(self, node_id)
        else:
            item.draw(Canvas(self.scene, self.group.add_group(id=f"{node_id}-held", matte=matte, matteMode="luma"), self.view),
                      node_id)

    def shape(self, node_id: str, path: str, **paint: Any) -> None:
        self.group.add_shape(id=node_id, shape="path", path=path, x=0, y=0, anchorX=0, anchorY=0,
                             width=self.view.width, height=self.view.height, **paint)

    def image(self, asset_id: str, path: Path, width: int, height: int) -> str:
        if not self.scene.find_all("assets"):
            self.scene.add_assets()
        self.scene.find_all("assets")[0].add_image(id=asset_id, src=str(path), width=width, height=height)
        return asset_id


def paint_over(scene: Any, composition: Any, layers: Sequence[PaintLayer], shot: str, view: View, look: str,
               holdout: Optional[Holdout] = None) -> None:
    """Adds the location's paint for this shot and look on top of everything before it in the composition. A compiler with
    no surfaces, as a wireframe has, gives no `holdout`, and a layer with depth then lies on top."""
    for index, layer in enumerate(layers):
        if layer.items and (not layer.shots or shot in layer.shots) and (not layer.looks or look in layer.looks):
            group = composition.add_group(id=f"paint-{index}", blend=layer.blend, opacity=layer.opacity)
            canvas = Canvas(scene, group, view, holdout if layer.depth else None)
            for number, item in enumerate(layer.items):
                canvas.place(item, f"paint-{index}-{number}")


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

    def hulls(self, world: Transform) -> list[Hull]:
        return []

    def _centred(self) -> list[tuple[float, float]]:
        xs, ys = [p[0] for p in self.outline], [p[1] for p in self.outline]
        cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
        return [(x - cx, y - cy) for x, y in self.outline]

    def spec(self) -> dict[str, Any]:
        """What a catalog stores."""
        return {"outline": [list(point) for point in self.outline], "smooth": self.smooth, "thickness": self.thickness,
                "looks": list(self.looks)}

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
