"""Characters on marks. The set is 3D and a character is a picture: a Performer gives a transparent cut-out, and an Actor
stands it on a mark at a real height, sized by distance, so it follows any shot. An Ensemble draws them back to front.

A cut-out is paint: it is laid over the picture and always faces the camera, so furniture does not hide it yet.
"""
from __future__ import annotations

import struct
import zlib
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, replace
from functools import lru_cache
from pathlib import Path
from typing import Callable, Mapping, Optional, Sequence, Union

from srlocations.geometry import Vec3, VecLike
from srlocations.paint import Box, Canvas, Fill, PaintItem, Sticker, png_size

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
OPAQUE_ENOUGH = 8  # an alpha at or below this is a soft edge's fringe, not part of the figure


def _unfiltered(data: bytes, width: int, height: int, step: int) -> list[bytearray]:
    stride = width * step
    rows: list[bytearray] = []
    previous = bytearray(stride)
    for number in range(height):
        start = number * (stride + 1)
        kind, row = data[start], bytearray(data[start + 1:start + 1 + stride])
        if kind == 1:
            for i in range(step, stride):
                row[i] = (row[i] + row[i - step]) & 255
        elif kind == 2:
            row = bytearray((a + b) & 255 for a, b in zip(row, previous))
        elif kind == 3:
            for i in range(stride):
                row[i] = (row[i] + ((row[i - step] if i >= step else 0) + previous[i]) // 2) & 255
        elif kind == 4:
            for i in range(stride):
                a, b, c = (row[i - step], previous[i], previous[i - step]) if i >= step else (0, previous[i], 0)
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                row[i] = (row[i] + (a if pa <= pb and pa <= pc else b if pb <= pc else c)) & 255
        rows.append(row)
        previous = row
    return rows


def _png(path: Union[str, Path]) -> tuple[tuple[int, ...], bytes]:
    """A PNG's header fields and its compressed picture. A file changed since it was last read is read again."""
    source = Path(path).resolve()
    return _read_png(str(source), source.stat().st_mtime_ns)


@lru_cache(maxsize=256)
def _read_png(path: str, stamp: int) -> tuple[tuple[int, ...], bytes]:
    raw = Path(path).read_bytes()
    if raw[:8] != PNG_SIGNATURE:
        raise ValueError(f"{path} is not a PNG")
    offset, idat, header = 8, bytearray(), None
    while offset < len(raw):
        length, tag = struct.unpack_from(">I4s", raw, offset)
        if tag == b"IHDR":
            header = struct.unpack_from(">IIBBBBB", raw, offset + 8)
        elif tag == b"IDAT":
            idat += raw[offset + 8:offset + 8 + length]
        offset += 12 + length
    return header, bytes(idat)


def colours(path: Union[str, Path]) -> list[tuple[int, int, int]]:
    """Every pixel of an 8-bit RGB or RGBA PNG."""
    (width, height, depth, color, _, _, interlaced), data = _png(path)
    step = {2: 3, 6: 4}.get(color)
    if step is None or depth != 8 or interlaced:
        raise ValueError(f"{path} is not 8-bit RGB")
    return [(row[i], row[i + 1], row[i + 2]) for row in _unfiltered(zlib.decompress(data), width, height, step)
            for i in range(0, width * step, step)]


def alpha_box(path: Union[str, Path]) -> Box:
    """The part of a PNG that is not transparent, as left, top, right and bottom pixels."""
    (width, height, depth, color, _, _, interlaced), data = _png(path)
    step = {4: 2, 6: 4}.get(color)
    if step is None or depth != 8 or interlaced:  # no alpha channel, or one this does not read: the whole picture counts
        return 0, 0, width, height
    rows = _unfiltered(zlib.decompress(data), width, height, step)
    filled = [(y, [x for x, alpha in enumerate(row[step - 1::step]) if alpha > OPAQUE_ENOUGH]) for y, row in enumerate(rows)]
    filled = [(y, xs) for y, xs in filled if xs]
    if not filled:
        raise ValueError(f"{path} is fully transparent")
    return (min(xs[0] for _, xs in filled), filled[0][0], max(xs[-1] for _, xs in filled) + 1, filled[-1][0] + 1)


@dataclass(frozen=True)
class Cutout:
    """A picture of a character. `box` is the figure within it, in pixels; the feet are at the middle of its bottom edge."""
    path: Path
    box: Box


class Performer(ABC):
    """A character that can be drawn. Plugins fill registry.cast with these."""

    @abstractmethod
    def cutout(self, pose: Mapping[str, str]) -> Cutout:
        """The character in a pose. What a pose may hold is the performer's own."""


@dataclass(frozen=True)
class Portrait(Performer):
    """Any transparent PNG as a character. It has one pose. `box` overrides the measured figure, for a picture with
    something around the character that should not count toward its height."""
    path: Union[str, Path]
    box: Optional[Box] = None

    def __post_init__(self) -> None:
        png_size(Path(self.path))

    def cutout(self, pose: Mapping[str, str]) -> Cutout:
        if pose:
            raise ValueError(f"{self.path} is one picture, so it has no pose {dict(pose)}")
        return Cutout(Path(self.path), self.box or alpha_box(self.path))


@dataclass
class Actor:
    """A performer at a point. `height` is in metres, from the feet to the top of the figure."""
    performer: Performer
    at: VecLike
    height: float = 1.7
    pose: Mapping[str, str] = field(default_factory=dict)
    flip: bool = False
    shadow: float = 0.3  # how dark the pool of shadow under its feet is, 0 for none
    mark: str = ""  # the mark it stands on, which it goes with

    def sticker(self) -> Sticker:
        cutout = self.performer.cutout(self.pose)
        return Sticker(at=self.at, path=cutout.path, height=self.height, box=cutout.box, flip=self.flip)

    def contact(self) -> Fill:
        """A shadow in world space, so it lies down with the perspective."""
        x, y, z = Vec3.of(self.at)
        reach = self.height * 0.2
        return Fill(points=[(x - reach, y + 0.01, z), (x, y + 0.01, z - reach * 0.7), (x + reach, y + 0.01, z),
                            (x, y + 0.01, z + reach * 0.7)], color=f"#000000{round(self.shadow * 255):02x}", smooth=True)


@dataclass
class Ensemble(PaintItem):
    """Actors sharing a layer. Whoever is nearer the camera in a shot is drawn later, so it differs from shot to shot."""
    actors: list[Actor] = field(default_factory=list)

    def carried(self, offset: Callable[[str], Vec3]) -> "Ensemble":
        return replace(self, actors=[replace(actor, at=Vec3.of(actor.at) + offset(actor.mark)) for actor in self.actors])

    def draw(self, canvas: Canvas, node_id: str) -> None:
        ordered: Sequence[Actor] = sorted(self.actors, key=lambda actor: canvas.view.pixels_per_metre(Vec3.of(actor.at)))
        for number, actor in enumerate(ordered):
            if actor.shadow:
                canvas.place(actor.contact(), f"{node_id}-shadow-{number}")
        for number, actor in enumerate(ordered):
            canvas.place(actor.sticker(), f"{node_id}-{number}")
