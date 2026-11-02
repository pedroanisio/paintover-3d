"""Skeletons and motion for other packages: a mannequin's bones and moves written as BVH or as a skinned GLB, and poses read
back from a BVH, whichever package wrote it.

Both formats are right-handed and y-up. A model file's (x, y, z) lands at the SDK's (x, y, -z) (see mesh.py), so both are
written that way, and a figure that faces +z here faces -z in the file. The root carries the figure's place in the location,
so a walk crosses the floor in the file as it does here. A file is sampled `fps` times a second from `start` to `end` of a
location, frame n at exactly start + n / fps, as a clip is, or holds a single figure as it stands.

A BVH has the 55 bones with this body's offsets, the hips with three positions and three turns and every other bone with
three turns, in centimetres unless `units` says otherwise, named as this SDK names them or as a package in `Joint.known_as`
does. With every channel at 0 it stands in the T-stance, thumbs and all, so a bone's turns are its turn from there. Its
root's offset is 0, so a reader that adds that to the root's positions and one that does not agree.

`load_bvh()` reads the bones it knows by this SDK's names or by any in `ALIASES`, and reports the rest, whose turns still
reach the bones below them. Another rig's rest pose need not be a T-stance: each bone is turned from the way it points at the
file's rest to the way it points here, so arms that hang at rest there hang here at rest. The file is turned about y so its
left and right fall on this figure's, and scaled by how long its bones are against this body's. A joint with fewer than
three controls keeps what they can do and leaves the rest to the bones below it. A value outside its range is held at it and
reported, unless the figure has `limits=False`.

A GLB has the same bones as a skin, and each limb is a mesh bound rigidly to its bone, where the figure stands at the first
sample, so a Mesh of the file stands as the figure did. Its animation turns every joint and moves the hips.
"""
from __future__ import annotations

import json
import math
import re
import struct
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Iterator, Mapping, Optional, Sequence, Union

from srlocations.geometry import IDENTITY, Matrix, Transform, Vec3, rotation
from srlocations.kinematics import angles, apply, cross, dot, nearest, scaled, transposed, turned, unit
from srlocations.nodes import Node
from srlocations.registry import Registry
from srlocations.stock.mannequin import ALIASES, BY_NAME, JOINTS, LINEAGE, MOVES, PARAMETERS, Joint, Mannequin, Pose

FLIP = (1.0, 1.0, -1.0)  # the SDK's frame to a file's and back: z changes sign
PACKAGES = sorted({package for joint in JOINTS for package in joint.known_as})
CHILDREN = {joint.name: [child for child in JOINTS if child.parent == joint.name] for joint in JOINTS}
CHANNELS = ("Xposition", "Yposition", "Zposition", "Xrotation", "Yrotation", "Zrotation")
ROOT_CHANNELS, BONE_CHANNELS = CHANNELS[:3] + ("Zrotation", "Xrotation", "Yrotation"), ("Zrotation", "Xrotation", "Yrotation")
SLACK = 1e-3  # degrees, or metres, past a range too small to report: rounding, not a pose
FACET = 0.0005  # metres a GLB limb's flat faces may fall inside the egg they stand for
FLOAT, UNSIGNED_BYTE, UNSIGNED_SHORT, UNSIGNED_INT = 5126, 5121, 5123, 5125
FORMATS = {FLOAT: "f", UNSIGNED_BYTE: "B", UNSIGNED_SHORT: "H", UNSIGNED_INT: "I"}
SIZES = {"SCALAR": 1, "VEC3": 3, "VEC4": 4, "MAT4": 16}
VERTICES, INDICES = 34962, 34963  # what a buffer view holds, for a GPU
HEX = re.compile(r"#[0-9a-fA-F]{6}")


class InterchangeError(ValueError):
    pass


@dataclass(frozen=True)
class Take:
    """Poses read from a motion file, one to a frame, `fps` frames to a second. `unknown` names the file's joints that are
    none of a mannequin's, and `clamped` each control held at its range, with the frames it was held in."""
    poses: tuple[Pose, ...]
    fps: float
    unknown: tuple[str, ...] = ()
    clamped: Mapping[str, tuple[int, ...]] = field(default_factory=dict)


def _depth_first(name: str = "hips") -> Iterator[Joint]:
    yield BY_NAME[name]
    for child in CHILDREN[name]:
        yield from _depth_first(child.name)


ORDER = tuple(_depth_first())  # the order a BVH lists bones and their channels in


def _times(a: Matrix, b: Matrix) -> Matrix:
    return Transform(basis=a).then(Transform(basis=b)).basis


def _out(point: Vec3) -> Vec3:
    """A point or direction from the SDK's frame to a file's, or back."""
    return Vec3(point.x * FLIP[0], point.y * FLIP[1], point.z * FLIP[2])


def _flipped(basis: Matrix) -> Matrix:
    """A rotation from the SDK's frame to a file's, or back."""
    return tuple(tuple(basis[r][c] * FLIP[r] * FLIP[c] for c in range(3)) for r in range(3))


def _file(world: Transform) -> Transform:
    return Transform(_out(world.position), _flipped(world.basis))


def _number(value: float) -> str:
    text = f"{value:.6f}".rstrip("0").rstrip(".")
    return "0" if text == "-0" else text


def _moments(figure: Union[Mannequin, Node, str], location, fps: float, start: float,
             end: Optional[float]) -> tuple[list[Mannequin], list[float]]:
    """The figure at each frame, and when each frame is."""
    if location is None:
        if not isinstance(figure, Mannequin):
            raise InterchangeError(f"only a mannequin has these bones, not {figure!r}; give a location to name one in it")
        return [figure], [0.0]
    found = figure if isinstance(figure, Node) else next((node for node in location.nodes if node.label == figure), None)
    if not isinstance(found, Mannequin) or not any(node is found for node in location.nodes):
        raise InterchangeError(f"{location.name} has no mannequin {getattr(found, 'label', figure)!r}")
    index = next(place for place, node in enumerate(location.nodes) if node is found)
    end = location.duration() if end is None else end
    if fps <= 0 or end < start:
        raise InterchangeError(f"frames run forward at a rate above 0, not from {start} to {end} at {fps}")
    times = [start + frame / fps for frame in range(math.floor((end - start) * fps + 1e-9) + 1)]
    return [location.at(time).nodes[index] for time in times], times


def _worlds(figure: Mannequin) -> dict[str, Transform]:
    return {name: figure.transform.then(frame) for name, frame in figure.frames().items()}


def _locals(worlds: Mapping[str, Transform]) -> dict[str, Transform]:
    """Each joint on its parent, and the hips in the location."""
    return {joint.name: worlds[joint.name] if joint.parent is None else
            Transform(worlds[joint.parent].undo(worlds[joint.name].position),
                      _times(transposed(worlds[joint.parent].basis), worlds[joint.name].basis)) for joint in JOINTS}


def _tip(figure: Mannequin, joint: Joint) -> Vec3:
    """Where a bone with nothing hanging from it ends, in its own frame: the far side of its egg."""
    centre, height = figure._bulk(joint)[0], figure.height * figure.build_of.fit
    return Vec3(*(2 * share * height for share in centre))


def _continued(joint: Joint) -> Optional[str]:
    """The child a joint's bone points to: the spine from the hips, the neck from the chest, the middle finger from a hand,
    or its only child. A head points to none, since its eyes and jaw hang off it."""
    children = [child.name for child in CHILDREN[joint.name]]
    for wanted in ("spine", "neck", joint.name.replace("hand", "middle_proximal")):
        if wanted in children:
            return wanted
    return children[0] if len(children) == 1 else None


def _zxy(m: Matrix, near: Sequence[float]) -> tuple[float, float, float]:
    """The turns about z, then x, then y, in degrees and right-handed, that make `m`: of the two sets, the one nearest
    `near`, each angle moved by whole turns, so a channel never jumps between frames."""
    first = math.asin(max(-1.0, min(1.0, m[2][1])))
    if math.cos(first) < 1e-9:  # pointing straight up or down, where z and y turn alike, so y stays at 0
        found = [(math.degrees(math.atan2(m[1][0], m[0][0])), math.degrees(first), 0.0)]
    else:
        found = []
        for x in (first, math.pi - first):
            c = math.cos(x)
            found.append((math.degrees(math.atan2(-m[0][1] / c, m[1][1] / c)), math.degrees(x),
                          math.degrees(math.atan2(-m[2][0] / c, m[2][2] / c))))
    options = [tuple(nearest(angle, was) for angle, was in zip(option, near)) for option in found]
    return min(options, key=lambda option: sum((angle - was) ** 2 for angle, was in zip(option, near)))


def _namer(names: str):
    if names and names not in PACKAGES:
        raise InterchangeError(f"no package {names!r} names bones here; there are {', '.join(PACKAGES)}")
    return lambda joint: joint.known_as.get(names, joint.name) if names else joint.name


def save_bvh(path: Union[str, Path], figure: Union[Mannequin, Node, str], location=None, fps: float = 30.0,
             start: float = 0.0, end: Optional[float] = None, units: float = 100.0, names: str = "") -> Path:
    """Writes a mannequin's skeleton and moves as BVH: the figure as it stands, or with a location, the figure in it or of
    that name from `start` to `end`, by default its whole length. `units` are the file's to a metre, and `names` is a
    package in `Joint.known_as` whose bone names to use, such as "mixamo"; a bone it lacks keeps this SDK's name."""
    path, named = Path(path), _namer(names)
    moments, _ = _moments(figure, location, fps, start, end)
    body = moments[0]
    rest = body._solved({})
    lines = ["HIERARCHY"]

    def bone(joint: Joint, depth: int) -> None:
        pad, channels = "  " * depth, ROOT_CHANNELS if joint.parent is None else BONE_CHANNELS
        offset = Vec3() if joint.parent is None else _out(rest[joint.name].position - rest[joint.parent].position)
        lines.extend([f"{pad}{'JOINT' if joint.parent else 'ROOT'} {named(joint)}", f"{pad}{{",
                      f"{pad}  OFFSET {' '.join(_number(v * units) for v in offset)}",
                      f"{pad}  CHANNELS {len(channels)} {' '.join(channels)}"])
        for child in CHILDREN[joint.name]:
            bone(child, depth + 1)
        if not CHILDREN[joint.name]:
            tip = _out(Transform(basis=rest[joint.name].basis).apply(_tip(body, joint)))
            lines.extend([f"{pad}  End Site", f"{pad}  {{", f"{pad}    OFFSET {' '.join(_number(v * units) for v in tip)}",
                          f"{pad}  }}"])
        lines.append(f"{pad}}}")

    bone(ORDER[0], 0)
    rows, before = [], {}
    for moment in moments:
        worlds = _worlds(moment)
        turns = {name: _times(world.basis, transposed(rest[name].basis)) for name, world in worlds.items()}  # from the T-stance
        row = [v * units for v in _out(worlds["hips"].position)]
        for joint in ORDER:
            local = turns[joint.name] if joint.parent is None else _times(transposed(turns[joint.parent]), turns[joint.name])
            before[joint.name] = _zxy(_flipped(local), before.get(joint.name, (0.0, 0.0, 0.0)))
            row.extend(before[joint.name])
        rows.append(" ".join(_number(v) for v in row))
    lines.extend(["MOTION", f"Frames: {len(rows)}", f"Frame Time: {1 / fps:.7f}", *rows])
    path.write_text("\n".join(lines) + "\n")
    return path


@dataclass
class _Bone:
    name: str
    parent: Optional[int]
    offset: Vec3 = Vec3()
    channels: tuple[str, ...] = ()
    end: Optional[Vec3] = None


def _parsed(text: str, source: Path) -> tuple[list[_Bone], list[list[float]], float]:
    """A BVH's bones, in the order it lists them, the channels of each frame, and the seconds between frames."""
    words, at = text.split(), 0

    def word() -> str:
        nonlocal at
        if at >= len(words):
            raise InterchangeError(f"{source} ends in the middle")
        at += 1
        return words[at - 1]

    def number() -> float:
        found = word()
        try:
            return float(found)
        except ValueError:
            raise InterchangeError(f"{source} has {found!r} where a number belongs") from None

    def expect(*tokens: str) -> None:
        for token in tokens:
            found = word()
            if found != token:
                raise InterchangeError(f"{source} has {found!r} where {token!r} belongs")

    def current() -> _Bone:
        if not stack:
            raise InterchangeError(f"{source} has a value outside any joint")
        return bones[stack[-1]]

    bones: list[_Bone] = []
    stack: list[int] = []
    expect("HIERARCHY")
    while True:
        token = word()
        if token in ("ROOT", "JOINT"):
            bones.append(_Bone(word(), stack[-1] if stack else None))
            expect("{")
            stack.append(len(bones) - 1)
        elif token == "End":
            expect("Site", "{", "OFFSET")
            current().end = Vec3(number(), number(), number())
            expect("}")
        elif token == "OFFSET":
            current().offset = Vec3(number(), number(), number())
        elif token == "CHANNELS":
            bone, count = current(), int(number())
            bone.channels = tuple(word() for _ in range(count))
            if not set(bone.channels) <= set(CHANNELS):
                raise InterchangeError(f"{source}: {bone.name} has channels {' '.join(bone.channels)}")
        elif token == "}" and stack:
            stack.pop()
        elif token == "MOTION" and bones and not stack:
            break
        else:
            raise InterchangeError(f"{source} has {token!r} where a joint belongs")
    expect("Frames:")
    count = int(number())
    expect("Frame", "Time:")
    frame_time = number()
    width = sum(len(bone.channels) for bone in bones)
    values = [number() for _ in range(count * width)]
    if frame_time <= 0 or at != len(words):
        raise InterchangeError(f"{source} has {len(words) - at} numbers past its {count} frames, or no time between them")
    return bones, [values[frame * width:(frame + 1) * width] for frame in range(count)], frame_time


def _axis(name: str, degrees: float) -> Matrix:
    """A right-handed turn about a file's axis."""
    c, s = math.cos(math.radians(degrees)), math.sin(math.radians(degrees))
    return {"X": ((1, 0, 0), (0, c, -s), (0, s, c)), "Y": ((c, 0, s), (0, 1, 0), (-s, 0, c)),
            "Z": ((c, -s, 0), (s, c, 0), (0, 0, 1))}[name]


def _posed(bones: Sequence[_Bone], row: Sequence[float]) -> list[Transform]:
    """Each bone in the file's world in one frame: its offset and positions, then its turns in the order it lists them."""
    worlds: list[Transform] = []
    values = iter(row)
    for bone in bones:
        position, basis = list(bone.offset), IDENTITY
        for channel in bone.channels:
            value = next(values)
            if channel.endswith("position"):
                position["XYZ".index(channel[0])] += value
            else:
                basis = _times(basis, _axis(channel[0], value))
        local = Transform(Vec3(*position), basis)
        worlds.append(worlds[bone.parent].then(local) if bone.parent is not None else local)
    return worlds


def _known(name: str) -> Optional[str]:
    """This SDK's name for a bone, by its own name or a package's, with or without a namespace such as "mixamorig1:"."""
    for candidate in (name, name.rpartition(":")[2]):
        joint = BY_NAME.get(ALIASES.get(candidate, candidate))
        if joint is not None:
            return joint.name
    return None


def _swing(start: Vec3, end: Vec3) -> Matrix:
    """The smallest turn that points `start` along `end`."""
    start, end = unit(start), unit(end)
    axis, cosine = cross(start, end), dot(start, end)
    if axis.length < 1e-9:
        if cosine > 0:
            return IDENTITY
        axis = cross(start, Vec3(1, 0, 0) if abs(start.x) < 0.9 else Vec3(0, 1, 0))
    angle, axis = math.atan2(axis.length, cosine), unit(axis)
    columns = [turned(axis, angle, way) for way in (Vec3(1, 0, 0), Vec3(0, 1, 0), Vec3(0, 0, 1))]
    return tuple(tuple(tuple(column)[r] for column in columns) for r in range(3))


def _controls(figure: Mannequin, free: Mannequin, joint: Joint, basis: Matrix,
              before: Mapping[str, float]) -> tuple[dict[str, float], list[str]]:
    """A joint's turning controls for a rotation on its parent, and which of them were held at a range. Of the two sets
    that make it, the one within the ranges is kept, or the one least outside them, then the one nearest those `before`."""
    turns = [dof for dof in joint.dofs if dof.turn not in MOVES]
    yaw, pitch, roll = joint.rest
    wanted = _times(transposed(rotation(joint.turned("yaw", yaw), pitch, joint.turned("roll", roll))), basis)
    order = [dof.turn for dof in turns]
    order += [turn for turn in ("yaw", "pitch", "roll") if turn not in order]  # turns it lacks, left out at the end
    controls = [(joint, dof) for dof in turns]
    options = [free._chosen(controls, [found], before)[0] for found in angles(wanted, order)]

    def outside(option: Mapping[str, float]) -> float:
        return sum(max(PARAMETERS[key].low - value, value - PARAMETERS[key].high, 0.0) for key, value in option.items())
    best = min(options, key=lambda option: (max(0.0, outside(option) - SLACK) if figure.limits else 0.0,
                                            sum((value - before.get(key, 0.0)) ** 2 for key, value in option.items())))
    if not figure.limits:
        return best, []
    held = {key: max(PARAMETERS[key].low, min(PARAMETERS[key].high, value)) for key, value in best.items()}
    return held, [key for key, value in best.items() if abs(held[key] - value) > SLACK]


def _heading(at_rest: Sequence[Vec3], bone_of: Mapping[str, int]) -> float:
    """The yaw that turns a file so that its left and right fall on a figure's, along x: half a turn for a file that faces
    +z, as most packages' do, since a figure here faces +z and the file's z is reversed."""
    for bare in ("upper_leg", "upper_arm", "shoulder"):
        if f"left_{bare}" in bone_of and f"right_{bare}" in bone_of:
            across = _out(at_rest[bone_of[f"right_{bare}"]] - at_rest[bone_of[f"left_{bare}"]])
            if math.hypot(across.x, across.z) > 1e-9:
                return math.degrees(math.atan2(across.z, across.x))
    return 0.0


def _bound(figure: Mannequin, bones: Sequence[_Bone], at_rest: Sequence[Vec3], bone_of: Mapping[str, int],
           turn: Matrix) -> dict[str, Matrix]:
    """Each joint the file has, turned from this figure's rest so that its bone points the way the file's does at rest."""
    rest, bound = figure._solved({}), {}
    for joint in JOINTS:
        if joint.name not in bone_of:
            continue
        index, child = bone_of[joint.name], _continued(joint)
        mine = (rest[child].position - rest[joint.name].position if child else
                Transform(basis=rest[joint.name].basis).apply(_tip(figure, joint)))
        there = at_rest[bone_of[child]] - at_rest[index] if child in bone_of else bones[index].end
        if there is not None and there.length > 1e-9:
            swing = _swing(mine, apply(turn, _out(there)))
        else:  # nothing says where this bone points in the file, so it is turned as the bone above it is
            above = next((link.name for link in LINEAGE[joint.name][-2::-1] if link.name in bound), None)
            swing = _times(bound[above], transposed(rest[above].basis)) if above else IDENTITY
        bound[joint.name] = _times(swing, rest[joint.name].basis)
    return bound


def load_bvh(path: Union[str, Path], figure: Optional[Mannequin] = None) -> Take:
    """The poses in a BVH, one to a frame, for `figure`'s body, by default the stock man. Each pose has the figure's frame,
    so the hips carry the file's place on the floor; a figure with `grounded=False` keeps the hips' height as the file has
    it, and a grounded one is set on its floor."""
    path, figure = Path(path), Mannequin() if figure is None else figure
    bones, rows, frame_time = _parsed(path.read_text(errors="replace"), path)
    bone_of: dict[str, int] = {}
    unknown = []
    for index, bone in enumerate(bones):
        name = _known(bone.name)
        if name is None or name in bone_of:
            unknown.append(bone.name)
        else:
            bone_of[name] = index
    at_rest: list[Vec3] = []  # each bone at the file's rest, where every channel is 0
    for bone in bones:
        at_rest.append(bone.offset + at_rest[bone.parent] if bone.parent is not None else bone.offset)
    turn, rest = rotation(yaw=_heading(at_rest, bone_of)), figure._solved({})
    ours = theirs = 0.0
    for name, index in bone_of.items():
        child = _continued(BY_NAME[name])
        if child in bone_of:
            ours += (rest[child].position - rest[name].position).length
            theirs += (at_rest[bone_of[child]] - at_rest[index]).length
    scale, bound = ours / theirs if theirs > 0 else 1.0, _bound(figure, bones, at_rest, bone_of, turn)
    free, length = replace(figure, limits=False) if figure.limits else figure, figure.height * figure.build_of.fit
    poses, clamped, before = [], {}, {}
    for frame, row in enumerate(rows):
        worlds, actual, values = _posed(bones, row), {}, {}
        for joint in JOINTS:  # each from its parent as solved, so what one joint cannot do the next makes up
            parent = actual[joint.parent] if joint.parent else Transform()
            if joint.name in bone_of:
                world = worlds[bone_of[joint.name]]
                wanted = _times(_times(turn, _times(_flipped(world.basis), transposed(turn))), bound[joint.name])
                found, held = _controls(figure, free, joint, _times(transposed(parent.basis), wanted), before)
                if joint.parent is None:
                    moved = scaled(apply(turn, _out(world.position)), scale) - rest[joint.name].position
                    for dof in (dof for dof in joint.dofs if dof.turn in MOVES):
                        key, value = f"{joint.name}.{dof.name}", dot(moved, MOVES[dof.turn]) / dof.sign
                        found[key] = max(dof.low, min(dof.high, value)) if figure.limits else value
                        held += [key] if abs(found[key] - value) > SLACK else []
                values.update(found)
                for key in held:
                    clamped.setdefault(key, []).append(frame)
            actual[joint.name] = parent.then(figure._local(joint, values, length))
        poses.append(Pose(values))
        before = values
    return Take(tuple(poses), round(1 / frame_time, 3), tuple(unknown), {key: tuple(frames) for key, frames in clamped.items()})


class _Blob:
    """The binary chunk of a GLB, with the buffer views and accessors that read it."""

    def __init__(self) -> None:
        self.data, self.views, self.accessors = bytearray(), [], []

    def add(self, flat: Sequence[float], kind: str, component: int, target: Optional[int] = None,
            bounds: bool = False) -> int:
        """An accessor over these values, in a view of their own; `bounds` gives it the min and max a reader needs."""
        packed = struct.pack(f"<{len(flat)}{FORMATS[component]}", *flat)
        view = {"buffer": 0, "byteOffset": len(self.data), "byteLength": len(packed), **({"target": target} if target else {})}
        self.views.append(view)
        self.data += packed + bytes(-len(packed) % 4)
        width = SIZES[kind]
        accessor = {"bufferView": len(self.views) - 1, "componentType": component, "count": len(flat) // width, "type": kind}
        if bounds:  # as the file stores them, so a validator reading the values back finds these
            stored = struct.unpack(f"<{len(flat)}{FORMATS[component]}", packed)
            accessor |= {"min": [min(stored[i::width]) for i in range(width)], "max": [max(stored[i::width]) for i in range(width)]}
        self.accessors.append(accessor)
        return len(self.accessors) - 1


def _quaternion(m: Matrix) -> list[float]:
    """A rotation as glTF writes one: x, y, z, w."""
    trace = m[0][0] + m[1][1] + m[2][2]
    if trace > 0:
        s = math.sqrt(trace + 1.0) * 2
        found = ((m[2][1] - m[1][2]) / s, (m[0][2] - m[2][0]) / s, (m[1][0] - m[0][1]) / s, s / 4)
    elif m[0][0] > m[1][1] and m[0][0] > m[2][2]:
        s = math.sqrt(1.0 + m[0][0] - m[1][1] - m[2][2]) * 2
        found = (s / 4, (m[0][1] + m[1][0]) / s, (m[0][2] + m[2][0]) / s, (m[2][1] - m[1][2]) / s)
    elif m[1][1] > m[2][2]:
        s = math.sqrt(1.0 + m[1][1] - m[0][0] - m[2][2]) * 2
        found = ((m[0][1] + m[1][0]) / s, s / 4, (m[1][2] + m[2][1]) / s, (m[0][2] - m[2][0]) / s)
    else:
        s = math.sqrt(1.0 + m[2][2] - m[0][0] - m[1][1]) * 2
        found = ((m[0][2] + m[2][0]) / s, (m[1][2] + m[2][1]) / s, s / 4, (m[1][0] - m[0][1]) / s)
    size = math.sqrt(sum(v * v for v in found))
    return [v / size for v in found]


def _linear(color: str) -> list[float]:
    """An sRGB colour as the linear one a model file holds."""
    if not HEX.fullmatch(color):
        return [0.6, 0.6, 0.6]
    values = [int(color[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    return [v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4 for v in values]


def _egg(radii: Sequence[float], world: Transform) -> tuple[list[float], list[float], list[int]]:
    """The points, normals and triangles of an egg with these radii placed by `world` in the SDK, written in a file's frame.
    Its faces fall no further than FACET inside the egg, and wind counter-clockwise seen from outside, as glTF has them."""
    step = math.sqrt(4 * FACET / max(radii))
    around, up = max(8, 4 * math.ceil(2 * math.pi / step / 4)), max(4, 2 * math.ceil(math.pi / step / 2))
    (rx, ry, rz), points, normals = radii, [], []
    for row in range(up + 1):
        v = math.pi * (row / up - 0.5)
        for column in range(around):
            u = 2 * math.pi * column / around
            cu, su, cv, sv = math.cos(u), math.sin(u), math.cos(v), math.sin(v)
            points.extend(_out(world.apply((rx * cu * cv, ry * sv, rz * su * cv))))
            normals.extend(unit(_out(Transform(basis=world.basis).apply((cu * cv / rx, sv / ry, su * cv / rz)))))
    triangles = []
    for row in range(up):
        for column in range(around):
            a, b = row * around + column, row * around + (column + 1) % around
            c, d = b + around, a + around
            triangles += ([a, b, c] if row > 0 else []) + ([a, c, d] if row < up - 1 else [])  # none at the poles
    return points, normals, triangles


def save_glb(path: Union[str, Path], figure: Union[Mannequin, Node, str], location=None, fps: float = 30.0,
             start: float = 0.0, end: Optional[float] = None, registry: Optional[Registry] = None) -> Path:
    """Writes a mannequin as a skinned GLB: the figure as it stands, or with a location, the figure in it or of that name,
    bound where it stands at `start` and animated to `end`, by default the location's whole length. Its materials are
    the figure's, as `registry` has them, by default the location's."""
    path = Path(path)
    moments, times = _moments(figure, location, fps, start, end)
    registry = registry or (location.registry if location is not None else Registry.default())
    body, numbered = moments[0], {joint.name: index for index, joint in enumerate(JOINTS)}
    posed = [_locals(_worlds(moment)) for moment in moments]
    bind = _worlds(body)
    blob, nodes, meshes, materials = _Blob(), [], [], {}
    for joint in JOINTS:
        local = _file(posed[0][joint.name])
        children = [numbered[child.name] for child in CHILDREN[joint.name]]
        nodes.append({"name": joint.name, "translation": list(local.position), "rotation": _quaternion(local.basis),
                      **({"children": children} if children else {})})
    for part in body._parts(body.frames()):
        points, normals, triangles = _egg(part.radii, body.transform.then(part.transform))
        count, bone = len(points) // 3, numbered[part.name.partition(".")[0]]
        attributes = {"POSITION": blob.add(points, "VEC3", FLOAT, VERTICES, bounds=True),
                      "NORMAL": blob.add(normals, "VEC3", FLOAT, VERTICES),
                      "JOINTS_0": blob.add([bone, 0, 0, 0] * count, "VEC4", UNSIGNED_BYTE, VERTICES),
                      "WEIGHTS_0": blob.add([1.0, 0.0, 0.0, 0.0] * count, "VEC4", FLOAT, VERTICES)}
        indices = blob.add(triangles, "SCALAR", UNSIGNED_SHORT if count < 65536 else UNSIGNED_INT, INDICES)
        material = materials.setdefault(part.material, len(materials))
        meshes.append({"name": part.name, "primitives": [{"attributes": attributes, "indices": indices, "material": material}]})
        nodes.append({"name": f"{part.name}.mesh", "mesh": len(meshes) - 1, "skin": 0})
    inverse = []
    for joint in JOINTS:  # each joint's world at the bind, undone, as columns
        world = _file(bind[joint.name])
        undo = transposed(world.basis)
        back = apply(undo, world.position)
        inverse += [undo[0][0], undo[1][0], undo[2][0], 0.0, undo[0][1], undo[1][1], undo[2][1], 0.0,
                    undo[0][2], undo[1][2], undo[2][2], 0.0, -back.x, -back.y, -back.z, 1.0]
    document = {
        "asset": {"version": "2.0", "generator": "srlocations"},
        "scene": 0,
        "scenes": [{"name": body.label, "nodes": [numbered["hips"], *range(len(JOINTS), len(nodes))]}],
        "nodes": nodes,
        "meshes": meshes,
        "materials": [_material(name, registry) for name in materials],
        "skins": [{"name": body.label, "joints": list(range(len(JOINTS))), "skeleton": numbered["hips"],
                   "inverseBindMatrices": blob.add(inverse, "MAT4", FLOAT)}],
    }
    if len(moments) > 1:
        document["animations"] = [_animation(blob, posed, [time - start for time in times], location.name)]
    document |= {"accessors": blob.accessors, "bufferViews": blob.views, "buffers": [{"byteLength": len(blob.data)}]}
    text = json.dumps(document, separators=(",", ":")).encode()
    text += b" " * (-len(text) % 4)
    chunks = struct.pack("<II", len(text), 0x4E4F534A) + text + struct.pack("<II", len(blob.data), 0x004E4942) + bytes(blob.data)
    path.write_bytes(b"glTF" + struct.pack("<II", 2, 12 + len(chunks)) + chunks)
    return path


def _material(name: str, registry: Registry) -> dict:
    found = registry.materials.get(name)
    made = {"name": name, "pbrMetallicRoughness": {"baseColorFactor": [*_linear(found.color), found.opacity],
                                                   "metallicFactor": found.metallic, "roughnessFactor": found.roughness}}
    if found.opacity < 1:
        made["alphaMode"] = "BLEND"
    if found.extra.get("doubleSided"):
        made["doubleSided"] = True
    return made


def _animation(blob: _Blob, posed: Sequence[Mapping[str, Transform]], times: Sequence[float], name: str) -> dict:
    """Every joint's turn and the hips' place at each sample, in a straight line between them."""
    clock = blob.add(times, "SCALAR", FLOAT, bounds=True)
    samplers, channels = [], []
    for node, joint in enumerate(JOINTS):
        turns, before = [], [0.0, 0.0, 0.0, 1.0]
        for local in posed:
            quaternion = _quaternion(_file(local[joint.name]).basis)
            if sum(a * b for a, b in zip(quaternion, before)) < 0:  # the same turn, on the side that blends the short way
                quaternion = [-v for v in quaternion]
            turns += quaternion
            before = quaternion
        samplers.append({"input": clock, "output": blob.add(turns, "VEC4", FLOAT), "interpolation": "LINEAR"})
        channels.append({"sampler": len(samplers) - 1, "target": {"node": node, "path": "rotation"}})
        if joint.parent is None:
            places = [v for local in posed for v in _out(local[joint.name].position)]
            samplers.append({"input": clock, "output": blob.add(places, "VEC3", FLOAT), "interpolation": "LINEAR"})
            channels.append({"sampler": len(samplers) - 1, "target": {"node": node, "path": "translation"}})
    return {"name": name, "samplers": samplers, "channels": channels}
