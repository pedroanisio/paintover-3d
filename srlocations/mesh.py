"""Imported models. A Mesh draws a file the engine can read, placed like any solid.

Its origin is the model's own, its units are metres and it stands y-up, as glTF and OBJ have it: the engine turns a model
half way round x on the way in, so the model's +z points to the SDK's -z. glTF and OBJ are read here as well as by the
engine, which gives a Mesh true bounds, wireframe lines and the names of its materials. Other formats are the engine's to
read alone, so a Mesh of one states its size.

Left alone a model keeps its own materials. `material` replaces them all, and `materials` replaces some by the names the
model gives them. A pass that needs a flat colour reads it from the file; a picture in the file only reaches passes that
draw the model's own materials, so a look gets colour from the file, from `materials`, or from its own `textures`.
"""
from __future__ import annotations

import base64
import json
import math
import re
import struct
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional, Sequence, Union
from urllib.parse import unquote

from srlocations.collision import Cloud, Hull
from srlocations.geometry import Transform, Vec3, VecLike
from srlocations.materials import Material
from srlocations.nodes import Polyline, Skin, Solid
from srlocations.portable import bundle, digest

MODEL = "stock.model"  # the material name of a Mesh left with its own materials
FORMATS = {".gltf": "gltf", ".glb": "glb", ".obj": "obj", ".usd": "usd", ".usda": "usd", ".usdc": "usd", ".usdz": "usdz",
           ".fbx": "fbx", ".ply": "ply", ".splat": "splat"}
READ_HERE = ("gltf", "glb", "obj")
SLOT = re.compile(r"[^\s:]+")  # the engine's list of overrides is split on spaces and colons
CREASE = math.cos(math.radians(32))  # two faces meeting more sharply than this show as a line in a wireframe
TURNING = 1e-9  # two normals with a product of a component below minus this point opposite ways along it
MAX_TRIANGLES = 400000  # past this a wireframe draws the bounding box: it is a blocking view, not a model viewer
MAX_LINES = 6000
COMPONENTS = {5120: "b", 5121: "B", 5122: "h", 5123: "H", 5125: "I", 5126: "f"}
GLB_MAGIC, GLB_JSON, GLB_BIN = b"glTF", 0x4E4F534A, 0x004E4942
Matrix4 = list[list[float]]
IDENTITY: Matrix4 = [[float(r == c) for c in range(4)] for r in range(4)]


class MeshError(ValueError):
    pass


def tone(red: float, green: float, blue: float) -> str:
    """A colour from a model file, which is linear, as the sRGB the engine's materials are written in."""
    def encoded(value: float) -> int:
        value = max(0.0, min(1.0, value))
        return round(255 * (12.92 * value if value <= 0.0031308 else 1.055 * value ** (1 / 2.4) - 0.055))
    return f"#{encoded(red):02x}{encoded(green):02x}{encoded(blue):02x}"


@dataclass(frozen=True)
class Model:
    """What is read from a file, in the SDK's local frame."""
    points: tuple[tuple[float, float, float], ...]
    triangles: tuple[tuple[int, int, int], ...]
    tones: Mapping[str, str]  # the name of each material it uses, and its colour
    low: Vec3
    high: Vec3
    two_sided: frozenset[str] = frozenset()  # the materials whose faces show from behind, "" for one with no name

    def lines(self) -> list[Polyline]:
        """Open edges, creases and outlines, the longest first if there are too many. An outline is where a surface turns
        away along x or z, so a smooth model with no creases still reads. Points at one place count as one, since a file
        repeats them wherever normals or UVs change."""
        if len(self.triangles) > MAX_TRIANGLES:
            return []
        welded: dict[tuple[float, ...], int] = {}
        index = [welded.setdefault(tuple(round(value, 5) for value in point), len(welded)) for point in self.points]
        spans = list(welded)
        sides: dict[tuple[int, int], list[Vec3]] = {}
        for a, b, c in self.triangles:
            a, b, c = index[a], index[b], index[c]
            if len({a, b, c}) < 3:
                continue
            normal = _normal(spans[a], spans[b], spans[c])
            for edge in ((a, b), (b, c), (c, a)):
                sides.setdefault((min(edge), max(edge)), []).append(normal)
        kept = [edge for edge, normals in sides.items()
                if len(normals) != 2 or sum(p * q for p, q in zip(*normals)) < CREASE
                or normals[0].x * normals[1].x < -TURNING or normals[0].z * normals[1].z < -TURNING]
        kept.sort(key=lambda edge: -math.dist(spans[edge[0]], spans[edge[1]]))
        return [[spans[a], spans[b]] for a, b in kept[:MAX_LINES]]


def _normal(a: Sequence[float], b: Sequence[float], c: Sequence[float]) -> Vec3:
    u, v = [q - p for p, q in zip(a, b)], [q - p for p, q in zip(a, c)]
    x, y, z = u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0]
    length = math.sqrt(x * x + y * y + z * z) or 1.0
    return Vec3(x / length, y / length, z / length)


def _finished(path: Path, points: list[tuple[float, float, float]], triangles: list[tuple[int, int, int]],
              tones: dict[str, str], two_sided: Iterable[str] = ()) -> Model:
    if not triangles:
        raise MeshError(f"{path} has no triangles to draw")
    turned = tuple((x, y, -z) for x, y, z in points)
    seen = [turned[index] for index in {index for triangle in triangles for index in triangle}]
    return Model(turned, tuple(triangles), tones, Vec3(*map(min, zip(*seen))), Vec3(*map(max, zip(*seen))), frozenset(two_sided))


def _mtl(path: Path) -> dict[str, str]:
    tones: dict[str, str] = {}
    name = ""
    if path.is_file():
        for line in path.read_text(errors="replace").splitlines():
            key, _, rest = line.strip().partition(" ")
            if key == "newmtl":
                name = rest.strip()
                tones[name] = tone(0.8, 0.8, 0.8)
            elif key == "Kd" and name:
                tones[name] = tone(*(float(value) for value in rest.split()[:3]))
    return tones


def _obj(path: Path, node: str) -> Model:
    points: list[tuple[float, float, float]] = []
    triangles: list[tuple[int, int, int]] = []
    known: dict[str, str] = {}
    tones: dict[str, str] = {}
    current, active, names = "", "", set()
    for line in path.read_text(errors="replace").splitlines():
        key, _, rest = line.strip().partition(" ")
        if key == "v":
            x, y, z = (float(value) for value in rest.split()[:3])
            points.append((x, y, z))
        elif key == "mtllib":
            known |= _mtl(path.parent / rest.strip())
        elif key == "usemtl":
            active = rest.strip()
        elif key in ("o", "g"):
            current = rest.strip()
            names.add(current)
        elif key == "f" and (not node or current == node):
            corners = [int(word.split("/")[0]) for word in rest.split()]
            corners = [number - 1 if number > 0 else len(points) + number for number in corners]
            triangles.extend((corners[0], b, c) for b, c in zip(corners[1:], corners[2:]))
            if active:
                tones[active] = known.get(active, tone(0.8, 0.8, 0.8))
    if node and node not in names:
        raise MeshError(f"{path} has no node {node!r}; it has {', '.join(sorted(names)) or 'none'}")
    return _finished(path, points, triangles, tones)


def _times(a: Matrix4, b: Matrix4) -> Matrix4:
    return [[sum(a[r][k] * b[k][c] for k in range(4)) for c in range(4)] for r in range(4)]


def _local(node: dict) -> Matrix4:
    if "matrix" in node:
        m = node["matrix"]
        return [[m[c * 4 + r] for c in range(4)] for r in range(4)]
    x, y, z, w = node.get("rotation", (0, 0, 0, 1))
    sx, sy, sz = node.get("scale", (1, 1, 1))
    tx, ty, tz = node.get("translation", (0, 0, 0))
    return [[(1 - 2 * (y * y + z * z)) * sx, 2 * (x * y - z * w) * sy, 2 * (x * z + y * w) * sz, tx],
            [2 * (x * y + z * w) * sx, (1 - 2 * (x * x + z * z)) * sy, 2 * (y * z - x * w) * sz, ty],
            [2 * (x * z - y * w) * sx, 2 * (y * z + x * w) * sy, (1 - 2 * (x * x + y * y)) * sz, tz],
            [0.0, 0.0, 0.0, 1.0]]


class Gltf:
    """The geometry of a .gltf or .glb. The engine reads every feature; this reads what bounds and lines need."""
    SIZES = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4}

    def __init__(self, path: Path) -> None:
        self.path, self.embedded = path, b""
        data = path.read_bytes()
        if data[:4] == GLB_MAGIC:
            data = self._chunks(data)
        self.document = json.loads(data)
        self.buffers = [self._buffer(buffer) for buffer in self.document.get("buffers", ())]

    def _chunks(self, data: bytes) -> bytes:
        offset, text = 12, b""
        while offset + 8 <= len(data):
            length, kind = struct.unpack_from("<II", data, offset)
            chunk = data[offset + 8:offset + 8 + length]
            if kind == GLB_JSON:
                text = chunk
            elif kind == GLB_BIN:
                self.embedded = chunk
            offset += 8 + length
        return text

    def _buffer(self, buffer: dict) -> bytes:
        uri = buffer.get("uri")
        if uri is None:
            return self.embedded
        if uri.startswith("data:"):
            return base64.b64decode(uri.partition(",")[2])
        return (self.path.parent / unquote(uri)).read_bytes()

    def _values(self, index: int) -> list[tuple]:
        accessor = self.document["accessors"][index]
        if "bufferView" not in accessor or accessor["componentType"] not in COMPONENTS:
            raise MeshError(f"{self.path} stores its geometry in a compressed form; give the Mesh a size")
        view = self.document["bufferViews"][accessor["bufferView"]]
        count, width = accessor["count"], self.SIZES[accessor["type"]]
        layout = struct.Struct(f"<{width}{COMPONENTS[accessor['componentType']]}")
        data = self.buffers[view["buffer"]]
        start = view.get("byteOffset", 0) + accessor.get("byteOffset", 0)
        stride = view.get("byteStride") or layout.size
        return [layout.unpack_from(data, start + number * stride) for number in range(count)]

    def _primitive(self, primitive: dict, world: Matrix4, model: dict) -> None:
        if primitive.get("mode", 4) != 4:
            return
        points = model["points"]
        base = len(points)
        points.extend(tuple(sum(world[row][k] * value for k, value in enumerate((*p, 1.0))) for row in range(3))
                      for p in self._values(primitive["attributes"]["POSITION"]))
        count = len(points) - base
        order = [value[0] for value in self._values(primitive["indices"])] if "indices" in primitive else range(count)
        model["triangles"].extend((base + a, base + b, base + c) for a, b, c in zip(*[iter(order)] * 3))
        if "material" in primitive:
            material = self.document["materials"][primitive["material"]]
            factor = material.get("pbrMetallicRoughness", {}).get("baseColorFactor", (1, 1, 1, 1))
            model["tones"][material.get("name", "")] = tone(*factor[:3])
            if material.get("doubleSided"):
                model["two_sided"].add(material.get("name", ""))

    def _walk(self, index: int, parent: Matrix4, model: dict, own: bool = True) -> None:
        node = self.document["nodes"][index]
        world = _times(parent, _local(node)) if own else parent
        if "mesh" in node:
            for primitive in self.document["meshes"][node["mesh"]]["primitives"]:
                self._primitive(primitive, world, model)
        for child in node.get("children", ()):
            self._walk(child, world, model)

    def model(self, node: str) -> Model:
        found: dict = {"points": [], "triangles": [], "tones": {}, "two_sided": set()}
        nodes = self.document.get("nodes", ())
        if node:
            named = [index for index, item in enumerate(nodes) if item.get("name") == node]
            if not named:
                names = ", ".join(sorted(str(item["name"]) for item in nodes if "name" in item))
                raise MeshError(f"{self.path} has no node {node!r}; it has {names or 'none'}")
            self._walk(named[0], IDENTITY, found, own=False)  # the engine drops a chosen node's own transform
        else:
            scene = self.document.get("scenes", ({"nodes": range(len(nodes))},))[self.document.get("scene", 0)]
            for index in scene.get("nodes", ()):
                self._walk(index, IDENTITY, found)
        found["tones"].pop("", None)
        return _finished(self.path, found["points"], found["triangles"], found["tones"], found["two_sided"])


@lru_cache(maxsize=256)
def _read(path: str, stamp: int, node: str) -> Model:
    source = Path(path)
    return _obj(source, node) if source.suffix.lower() == ".obj" else Gltf(source).model(node)


def read_model(path: Union[str, Path], node: str = "") -> Model:
    """The model in a file. A file changed since it was last read is read again."""
    source = Path(path).resolve()
    return _read(str(source), source.stat().st_mtime_ns, node)


@lru_cache(maxsize=256)
def _identity(path: str, stamp: int) -> str:
    return digest(bundle(Path(path)))[:20]


@dataclass
class Mesh(Solid):
    """An imported model. `scale` is one number or three. `node` draws one named node of the model and what hangs from it.
    `size` is the width, height and depth of a model that stands on its origin, needed when this SDK cannot read the file.
    `hollow` is for a model of a whole set: cameras and marks are then meant to be inside its bounds."""
    path: Union[str, Path] = ""
    material: str = field(default=MODEL, kw_only=True)
    scale: Union[float, VecLike] = 1.0
    node: str = ""
    size: Optional[VecLike] = None
    materials: dict[str, str] = field(default_factory=dict)
    hollow: bool = False
    primitive = "mesh"

    def __post_init__(self) -> None:
        self.path = Path(self.path)
        if not self.path.is_file():
            raise FileNotFoundError(f"no model {self.path}")
        if self.format not in READ_HERE and self.size is None:
            raise MeshError(f"{self.path}: this SDK cannot read a .{self.format} file, so give the Mesh a size")

    @property
    def format(self) -> str:
        suffix = self.path.suffix.lower()
        if suffix not in FORMATS:
            raise MeshError(f"{self.path}: the engine reads {', '.join(sorted(FORMATS))}, not {suffix or 'no extension'}")
        return FORMATS[suffix]

    @property
    def factors(self) -> Vec3:
        return Vec3.of((self.scale,) * 3 if isinstance(self.scale, (int, float)) else self.scale)

    @property
    def asset_id(self) -> str:
        source = self.path.resolve()
        return f"model-{_identity(str(source), source.stat().st_mtime_ns)}"

    def model(self) -> Optional[Model]:
        return read_model(self.path, self.node) if self.size is None else None

    def declare(self, scene: Any) -> None:
        assets = scene.find_all("assets") or [scene.add_assets()]
        if not any(mesh.id == self.asset_id for mesh in assets[0].find_all("mesh")):
            assets[0].add_mesh(id=self.asset_id, src=str(self.path.resolve()), format=self.format)

    def dimensions(self) -> dict[str, float]:
        return {}

    def geometry(self, units: float) -> dict[str, Any]:
        x, y, z = self.factors
        scaled = {name: value for name, value in (("scaleX", x), ("scaleY", y), ("scaleZ", z)) if value != 1}
        return {"mesh": self.asset_id, **scaled, **({"node": self.node} if self.node else {})}

    def skins(self) -> list[Skin]:
        if self.material != MODEL:
            return [Skin(self.material)]
        model = self.model()
        tones = {name: color for name, color in (model.tones if model else {}).items() if SLOT.fullmatch(name)}
        two_sided = model.two_sided if model else frozenset()
        sided = {"doubleSided": True}
        if not tones:
            return [Skin(MODEL, own=Material("#c8c8c8", extra=sided if two_sided else {}))]
        return [Skin(self.materials[slot], slot) if slot in self.materials
                else Skin(f"{self.path.stem}.{slot}", slot, Material(color, extra=sided if slot in two_sided else {}))
                for slot, color in tones.items()]

    def extent(self) -> tuple[Vec3, Vec3]:
        """The model's box in the local frame, scaled."""
        model = self.model()
        if model is None:
            width, height, depth = Vec3.of(self.size)
            return Vec3(-width / 2, 0, -depth / 2), Vec3(width / 2, height, depth / 2)
        return (Vec3(*(min(l * f, h * f) for l, h, f in zip(model.low, model.high, self.factors))),
                Vec3(*(max(l * f, h * f) for l, h, f in zip(model.low, model.high, self.factors))))

    def half_extents(self) -> Vec3:
        low, high = self.extent()
        return Vec3(*(max(abs(a), abs(b)) for a, b in zip(low, high)))

    def bounds(self, world: Transform) -> tuple[Vec3, Vec3]:
        low, high = self.extent()
        points = [world.apply(Vec3(x, y, z)) for x in (low.x, high.x) for y in (low.y, high.y) for z in (low.z, high.z)]
        return (Vec3(*(min(getattr(p, a) for p in points) for a in "xyz")),
                Vec3(*(max(getattr(p, a) for p in points) for a in "xyz")))

    def hulls(self, world: Transform) -> list[Hull]:
        """Its box, which is as near as this SDK knows a model's shape. A hollow model is a set to stand in, so it has none."""
        if self.hollow:
            return []
        low, high = self.extent()
        return [Cloud([world.apply(Vec3(x, y, z)) for x in (low.x, high.x) for y in (low.y, high.y) for z in (low.z, high.z)])]

    def spans(self) -> list[tuple["Solid", float, float]]:
        low, high = self.extent()
        return [(self, high.x - low.x, high.y - low.y)]

    def edges(self) -> list[Polyline]:
        model = self.model()
        lines = model.lines() if model else []
        if lines:
            x, y, z = self.factors
            return [[(px * x, py * y, pz * z) for px, py, pz in line] for line in lines]
        (lx, ly, lz), (hx, hy, hz) = self.extent()
        rims = [[(a, b, c) for a, c in ((lx, lz), (hx, lz), (hx, hz), (lx, hz), (lx, lz))] for b in (ly, hy)]
        return rims + [[(a, ly, c), (a, hy, c)] for a in (lx, hx) for c in (lz, hz)]
