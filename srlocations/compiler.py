"""Backends: a Compiler turns a Location into something else; SceneCompiler targets sr_core.scene."""
from __future__ import annotations

import math
import re
import shutil
import subprocess
import sys
import tempfile
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Generic, Mapping, Optional, Sequence, TypeVar, Union

from sr_core.scene import Scene

from srlocations import portable
from srlocations.collision import CollisionError
from srlocations.geometry import Matrix, Transform, Vec3, aim, rotation
from srlocations.location import Location, Shot
from srlocations.motion import Clip, MotionError, written
from srlocations.nodes import Light, Placed, Round, Solid
from srlocations.paint import Holdout, paint_over

T = TypeVar("T")
UNITS_PER_METRE = 100
FLIP = (1, -1, 1)  # world y is up, engine y is down


class Compiler(ABC, Generic[T]):
    @abstractmethod
    def compile(self, location: Location, shot: str) -> T:
        ...


def engine_position(point: Vec3) -> dict[str, float]:
    return {axis: round(value * flip * UNITS_PER_METRE, 3) for axis, value, flip in zip("xyz", point, FLIP)}


def engine_angles(basis: Matrix) -> dict[str, float]:
    """Euler angles of a world basis for the engine's Rz*Ry*Rx, in its y-down frame."""
    m = [[basis[r][c] * FLIP[r] * FLIP[c] for c in range(3)] for r in range(3)]
    tilt = math.asin(max(-1.0, min(1.0, -m[2][0])))
    if abs(m[2][0]) < 1 - 1e-9:
        x, z = math.atan2(m[2][1], m[2][2]), math.atan2(m[1][0], m[0][0])
    else:  # gimbal lock: all the remaining turn is z's
        x, z = 0.0, math.atan2(-m[0][1], m[1][1])
    return {name: round(math.degrees(value), 4)
            for name, value in (("rotationX", x), ("rotationY", tilt), ("rotation", z)) if abs(value) > 1e-9}


def safe_id(text: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_-]+", "-", text).strip("-")
    return cleaned if cleaned[:1].isalpha() else f"n-{cleaned}"


def _see_through(leaf: Placed, location: Location) -> bool:
    """Whether paint behind this solid still shows, as it does behind glass."""
    materials = [skin.own or location.registry.materials.get(skin.name) for skin in leaf.item.skins()]
    return all(material.opacity < 1 or material.extra.get("transmission", 0) for material in materials)


def columns(frames: Sequence[Mapping[str, float]]) -> dict[str, list[float]]:
    """Each property's value at each frame. An angle of zero is left out of a frame, so a turn may start from nothing."""
    return {name: [frame.get(name, 0.0) for frame in frames] for name in sorted({name for frame in frames for name in frame})}


def camera_keys(take: Shot) -> dict[str, float]:
    yaw, pitch = aim(take.eye, take.look_at)
    return {**engine_position(take.eye), "yaw": round(yaw, 4), "pitch": round(pitch, 4), "focalLength": take.lens}


def light_keys(world: Transform) -> dict[str, float]:
    yaw, pitch = aim((0, 0, 0), world.apply((0, 0, 1)) - world.position)
    return {**engine_position(world.position), "yaw": round(yaw, 4), "pitch": round(pitch, 4)}


class SceneCompiler(Compiler[Scene]):
    """Flattens the graph into one scene: a project, its materials and lights, a camera and the solids."""
    mode = "stock.shaded"  # the name paint and decals limited to some looks are matched against
    camera: dict[str, Any] = {}  # extra attributes for the shot's camera
    clip: Optional[Clip] = None  # the shot being compiled

    def __init__(self, width: int = 1280, height: int = 720, fps: int = 30, duration: float = 1,
                 supersample: int = 2) -> None:
        self.width, self.height, self.fps, self.duration = width, height, fps, duration
        self.supersample = supersample

    def compile(self, location: Location, shot: str) -> Scene:
        self.clip = Clip(location, shot, self.fps)
        take = self.clip.takes[0]
        scene = Scene(version="auto")
        scene.add_project(width=self.width, height=self.height, fps=str(self.fps), duration=self.length,
                          background=location.background, supersample=self.supersample)
        solids = [leaf for leaf in self.clip.solids() if leaf.item.drawn_in(self.mode)]
        lights = self.clip.lights()
        self._materials(scene, location, solids)
        self._declare(scene, solids)
        self._lights(scene, lights)
        composition = scene.add_composition()
        self._camera(composition, take)
        for index, leaf in enumerate(solids):
            self.draw(composition, leaf, index)
        self._paint(scene, composition, location, take, solids)
        return scene

    @property
    def length(self) -> float:
        return self.clip.duration if self.clip.moving else self.duration

    def _paint(self, scene: Scene, composition, location: Location, take: Shot, solids: list[Placed], effects: str = "") -> None:
        if not self.clip.moving:
            self._paint_frame(scene, composition, location, take, solids, effects)
            return
        ready = False  # a mask's materials go in the document once
        for frame, moment in enumerate(self.clip.moments):
            still = [leaf for leaf in moment.solids() if leaf.item.drawn_in(self.mode)]
            holdout = self._paint_frame(scene, composition, moment, self.clip.takes[frame], still, effects, ready,
                                        self.clip.window(frame), f"-f{frame}")
            ready = ready or bool(holdout and holdout.ready)

    def _paint_frame(self, scene: Scene, composition, location: Location, take: Shot, solids: list[Placed], effects: str = "",
                     ready: bool = False, window: Optional[Mapping[str, float]] = None, suffix: str = "") -> Optional[Holdout]:
        view = Projection(take, self.width, self.height)
        holdout = None
        if any(layer.depth for layer in location.paintings):
            holdout = Holdout(self, scene, [leaf for leaf in solids if not _see_through(leaf, location)], view, effects,
                              location.registry.materials)
            holdout.ready = ready
        paint_over(scene, composition, location.paintings, take.name, view, self.mode, holdout, window, suffix)
        return holdout

    def _materials(self, scene: Scene, location: Location, solids: list[Placed]) -> None:
        names = sorted({skin.name for leaf in solids for skin in leaf.item.skins() if not skin.own})
        if not names:  # the schema refuses an empty <materials>
            return
        library = scene.add_materials()
        for name in names:
            library.add_material(id=safe_id(name), **location.registry.materials.get(name).attributes())

    def _declare(self, scene: Scene, solids: list[Placed]) -> None:
        for leaf in solids:
            leaf.item.declare(scene)

    def _lights(self, scene: Scene, lights: list[Placed]) -> None:
        if not lights:  # and an empty <lights>
            return
        rack = scene.add_lights()
        for index, leaf in enumerate(lights):
            light: Light = leaf.item
            direction = leaf.world.apply((0, 0, 1)) - leaf.world.position
            yaw, pitch = aim((0, 0, 0), direction)
            element = rack.add_light(id=f"light-{index}", type=light.kind, intensity=light.intensity, color=light.color,
                                     castShadow=light.shadows, shadowSoftness=light.softness, yaw=round(yaw, 4),
                                     pitch=round(pitch, 4), **engine_position(leaf.world.position), **light.attributes())
            if leaf.track:
                written(element, columns([light_keys(world) for world in leaf.track]), self.fps, len(leaf.track))

    def _camera(self, composition, take: Shot) -> None:
        yaw, pitch = aim(take.eye, take.look_at)
        camera = composition.add_camera(id="camera", focalLength=take.lens, near=5, far=500000, yaw=round(yaw, 4),
                                        pitch=round(pitch, 4), **engine_position(take.eye), **self.camera)
        if self.clip.moving:
            written(camera, columns([camera_keys(moment) for moment in self.clip.takes]), self.fps, self.clip.frames)

    def draw(self, parent, leaf: Placed, index: int, prefix: str = "", material: Union[str, dict[str, str], None] = None,
             shadow: Optional[bool] = None, grow: float = 0.0) -> None:
        """One solid under `parent`. A pass of a Look gives its own material and an id prefix, and `grow`, in metres, to
        close the hairline cracks between sections that a flat colour would show. A dict of material ids by slot replaces
        those parts of an imported model and leaves the rest as the file has them."""
        solid: Solid = leaf.item
        if material is None:
            skins = solid.skins()
            whole = len(skins) == 1 and not skins[0].slot and not skins[0].own
            material = safe_id(skins[0].name) if whole else {s.slot: safe_id(s.name) for s in skins if not s.own}
        painted = ({"materialOverride": " ".join(f"{k}:{v}" for k, v in material.items())} if material else {}) \
            if isinstance(material, dict) else {"material": material}
        size = {name: round((value + grow) * UNITS_PER_METRE, 3) for name, value in solid.dimensions().items()}
        if isinstance(solid, Round):
            size["segments"] = solid.segments
        element = parent.add_object3D(id=safe_id(f"{prefix}{leaf.path}-{index}"), primitive=solid.primitive,
                                      **painted, castShadow=solid.casts_shadow if shadow is None else shadow,
                                      **size, **solid.geometry(UNITS_PER_METRE), **engine_position(leaf.world.position),
                                      **engine_angles(leaf.world.basis))
        solid.dress(element)
        if leaf.track:
            written(element, columns([{**engine_position(world.position), **engine_angles(world.basis)}
                                      for world in leaf.track]), self.fps, len(leaf.track))


class TracedCompiler(SceneCompiler):
    """The same scene, path traced: real soft shadows, bounced light and reflections, for a final frame."""
    mode = "stock.traced"

    def __init__(self, width: int = 1280, height: int = 720, samples: int = 256, bounces: int = 6, fps: int = 30) -> None:
        super().__init__(width, height, fps, supersample=1)
        self.camera = {"renderer": "pathtrace", "pathSamples": samples, "maxBounces": bounces}


class Projection:
    """The camera of a shot as the engine computes it, from world points to pixels."""
    NEAR = 0.05
    SENSOR = (36.0, 24.0)  # the engine's default gate, in millimetres

    def __init__(self, take: Shot, width: int, height: int) -> None:
        self.eye, self.width, self.height = take.eye, width, height
        yaw, pitch = aim(take.eye, take.look_at)
        self.basis = rotation(yaw, pitch)
        # A frame at least as wide as the gate fits its width, a narrower one its height.
        wide = width / height >= self.SENSOR[0] / self.SENSOR[1]
        self.focal = take.lens * (width / self.SENSOR[0] if wide else height / self.SENSOR[1])

    def to_camera(self, point: Vec3) -> Vec3:
        d = point - self.eye
        return Vec3(*(sum(self.basis[r][c] * value for r, value in enumerate(d)) for c in range(3)))

    def to_pixels(self, seen: Vec3) -> tuple[float, float]:
        return (self.width / 2 + self.focal * seen.x / seen.z, self.height / 2 - self.focal * seen.y / seen.z)

    def pixel(self, point: Vec3) -> Optional[tuple[float, float]]:
        """Where a world point lands, in frame or out of it; None behind the camera."""
        seen = self.to_camera(point)
        return None if seen.z < self.NEAR else self.to_pixels(seen)

    def pixels_per_metre(self, point: Vec3) -> float:
        return self.focal / max(self.to_camera(point).z, self.NEAR)

    def segment(self, start: Vec3, end: Vec3) -> Optional[tuple[tuple[float, float], tuple[float, float]]]:
        """The two pixels of a world segment, cut at the near plane; None when none of it can be in frame."""
        a, b = self.to_camera(start), self.to_camera(end)
        if a.z < self.NEAR and b.z < self.NEAR:
            return None
        if a.z < self.NEAR or b.z < self.NEAR:
            t = (self.NEAR - a.z) / (b.z - a.z)
            cut = a + Vec3(*((q - p) * t for p, q in zip(a, b)))
            a, b = (cut, b) if a.z < self.NEAR else (a, cut)
        p, q = self.to_pixels(a), self.to_pixels(b)
        outside = (max(p[0], q[0]) < 0 or min(p[0], q[0]) > self.width
                   or max(p[1], q[1]) < 0 or min(p[1], q[1]) > self.height)
        return None if outside else (p, q)


class WireframeCompiler(Compiler[Scene]):
    """Every solid's edges projected into one 2D path. Lines stay one width at any distance and any resolution."""
    mode = "stock.wireframe"

    def __init__(self, width: int = 480, height: int = 270, line: str = "#9fd8ff", thickness: float = 0.75,
                 background: str = "#0d1420", fps: int = 30) -> None:
        self.width, self.height, self.line, self.thickness = width, height, line, thickness
        self.background, self.fps = background, fps

    def compile(self, location: Location, shot: str) -> Scene:
        clip = Clip(location, shot, self.fps)
        scene = Scene(version="auto")
        scene.add_project(width=self.width, height=self.height, fps=str(self.fps),
                          duration=clip.duration if clip.moving else 1, background=self.background)
        composition = scene.add_composition()
        for frame, moment in enumerate(clip.moments):  # a still is one frame, with no window
            projection = Projection(clip.takes[frame], self.width, self.height)
            window, suffix = (clip.window(frame), f"-f{frame}") if clip.moving else ({}, "")
            composition.add_shape(id=f"wireframe{suffix}", shape="path", path=self.path(moment, projection), x=0, y=0,
                                  anchorX=0, anchorY=0, width=self.width, height=self.height, stroke=self.line,
                                  strokeWidth=self.thickness, fill="#00000000", **window)
            paint_over(scene, composition, moment.paintings, shot, projection, self.mode, None, window, suffix)
        return scene

    def path(self, location: Location, projection: Projection) -> str:
        moves: list[str] = []
        for leaf in location.solids():
            if not leaf.item.drawn_in(self.mode):
                continue
            for line in leaf.item.edges():
                points = [leaf.world.apply(point) for point in line]
                for start, end in zip(points, points[1:]):
                    if (pixels := projection.segment(start, end)) is not None:
                        (x0, y0), (x1, y1) = pixels
                        moves.append(f"M{x0:.2f} {y0:.2f}L{x1:.2f} {y1:.2f}")
        return "".join(moves) or "M0 0"


class RenderMode(ABC):
    """How a location becomes pixels: a mode names a compiler; plugins can add their own to registry.modes."""

    @abstractmethod
    def compiler(self) -> Compiler[Scene]:
        ...


@dataclass
class Wireframe(RenderMode):
    """The default: quick to render and to read while blocking out a location."""
    width: int = 480
    height: int = 270
    line: str = "#9fd8ff"
    thickness: float = 0.75
    fps: int = 30

    def compiler(self) -> Compiler[Scene]:
        return WireframeCompiler(self.width, self.height, self.line, self.thickness, fps=self.fps)


@dataclass
class Shaded(RenderMode):
    """Materials, lights and shadows."""
    width: int = 1280
    height: int = 720
    supersample: int = 2
    fps: int = 30

    def compiler(self) -> Compiler[Scene]:
        return SceneCompiler(self.width, self.height, self.fps, supersample=self.supersample)


@dataclass
class Traced(RenderMode):
    """Path traced on the GPU: slower, and the one to use where a surface needs to reflect what is around it."""
    width: int = 1280
    height: int = 720
    samples: int = 256
    bounces: int = 6
    fps: int = 30

    def compiler(self) -> Compiler[Scene]:
        return TracedCompiler(self.width, self.height, self.samples, self.bounces, self.fps)


def find_engine() -> Path:
    """The scene-render beside this Python, where ./doctor.py puts it, else the one on PATH."""
    beside = Path(sys.executable).with_name("scene-render")
    return beside if beside.exists() else Path(shutil.which("scene-render") or beside)


class Renderer:
    """Runs the engine. render() draws in `default_mode`, wireframe unless told otherwise."""

    def __init__(self, engine: Union[str, Path, None] = None, default_mode: Optional[RenderMode] = None) -> None:
        self.engine, self.default_mode = Path(engine) if engine else find_engine(), default_mode or Wireframe()

    def compile(self, location: Location, shot: str, mode: Union[RenderMode, str, None] = None, **params: Any) -> Scene:
        """A shot of a location. `mode` is a RenderMode or a name from registry.modes, with `params` for it."""
        blocked = location.clashes(bodies_only=True)
        if blocked:
            raise CollisionError(f"{blocked[0]}; settle() moves it clear, and solid=False lets it through on purpose")
        chosen = location.registry.modes.get(mode)(**params) if isinstance(mode, str) else mode or self.default_mode
        return chosen.compiler().compile(location, shot)

    def render(self, location: Location, shot: str, output: str | Path,
               mode: Union[RenderMode, str, None] = None, **params: Any) -> Path:
        return self.still(self.compile(location, shot, mode, **params), output)

    def frame(self, location: Location, shot: str, output: str | Path, time: float = 0.0,
              mode: Union[RenderMode, str, None] = None, **params: Any) -> Path:
        """One moment of a shot that moves, as a still."""
        return self.render(location.at(time), shot, output, mode, **params)

    def clip(self, location: Location, shot: str, output: str | Path,
             mode: Union[RenderMode, str, None] = None, **params: Any) -> Path:
        """A shot as a film, in whatever the extension of `output` says. A location where nothing moves has no film to make,
        so give it a move, if only `location.move(shot, seconds)` to hold."""
        if not location.duration(shot):
            raise MotionError(f"nothing moves in shot {shot!r}, so it has no length; render() draws a still")
        output = Path(output).resolve()  # the engine reads a relative path from the document, which is about to go
        output.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory() as folder:
            document = portable.package(self.compile(location, shot, mode, **params), Path(folder) / "location.scene.xml")
            done = subprocess.run([str(self.engine), "encode", str(document), "--path", str(output), "--hw", "software"],
                                  text=True, capture_output=True)  # hardware encoders have left ghost tiles in film
        # --strict here also refuses a warning about something off camera, which any film of a room has.
        if done.returncode != 0 or "not rendered yet" in done.stdout + done.stderr:
            raise RuntimeError(f"scene-render failed:\n{done.stdout}{done.stderr}")
        return output

    def package(self, location: Location, shot: str, folder: str | Path,
                mode: Union[RenderMode, str, None] = None, **params: Any) -> Path:
        """A shot as a folder that renders on any machine with an engine. Returns its document, for draw()."""
        document = Path(folder) / f"{safe_id(location.name)}-{safe_id(shot)}.scene.xml"
        return portable.package(self.compile(location, shot, mode, **params), document)

    def archive(self, location: Location, shot: str, output: str | Path,
                mode: Union[RenderMode, str, None] = None, **params: Any) -> Path:
        """A shot as one .vpkg.zip to hand to someone else."""
        name = f"{safe_id(location.name)}-{safe_id(shot)}"
        return portable.archive(self.compile(location, shot, mode, **params), output, name)

    def still(self, scene: Scene, output: str | Path, frame: int = 0) -> Path:
        with tempfile.TemporaryDirectory() as folder:
            return self.draw(portable.package(scene, Path(folder) / "location.scene.xml"), output, frame)

    def draw(self, document: str | Path, output: str | Path, frame: int = 0) -> Path:
        """Renders a document already on disk, such as a package from another machine."""
        output = Path(output)
        output.parent.mkdir(parents=True, exist_ok=True)
        done = subprocess.run([str(self.engine), "render", str(document), "--frame", str(frame),
                               "--output", str(output), "--strict"], text=True, capture_output=True)
        if done.returncode != 0:
            raise RuntimeError(f"scene-render failed:\n{done.stdout}{done.stderr}")
        return output
