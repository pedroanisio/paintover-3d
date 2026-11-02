"""Skeletons and motion for other packages: BVH out and in, and a skinned GLB. A file is right-handed and y-up, so the SDK's
(x, y, z) is written (x, y, -z). What is written is checked by a BVH reader and forward kinematics of the test's own, and by
reading the GLB's bytes here; only the round trips use the module's reader."""
import json
import math
import struct
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT)]

from srlocations import Flat, Location, Look, Mesh, Projection, Registry, Renderer, Styled
from srlocations.geometry import Transform, Vec3
from srlocations.interchange import InterchangeError, load_bvh, load_gltf, save_bvh, save_glb
from srlocations.mesh import _local, _times
from srlocations.stock.mannequin import JOINTS, POSES, Mannequin
from test_looks import GREY, H, W, flat_set, near, pixel

MM = 0.001


# A BVH reader and forward kinematics of the test's own.

def parse_bvh(text: str) -> tuple[list[dict], list[list[float]], float]:
    tokens, at, bones, stack = text.split(), 0, [], []
    while tokens[at] != "MOTION":
        word = tokens[at]
        if word in ("ROOT", "JOINT"):
            bones.append({"name": tokens[at + 1], "parent": stack[-1] if stack else None, "channels": [], "end": None})
            at += 2
        elif word == "End":
            bones[stack[-1]]["end"] = tuple(float(v) for v in tokens[at + 4:at + 7])
            at += 8  # End Site { OFFSET x y z }
            continue
        elif word == "{":
            stack.append(len(bones) - 1)
            at += 1
        elif word == "}":
            stack.pop()
            at += 1
        elif word == "OFFSET":
            bones[stack[-1]]["offset"] = tuple(float(v) for v in tokens[at + 1:at + 4])
            at += 4
        elif word == "CHANNELS":
            count = int(tokens[at + 1])
            bones[stack[-1]]["channels"] = tokens[at + 2:at + 2 + count]
            at += 2 + count
        else:
            at += 1
    frames, frame_time = int(tokens[at + 2]), float(tokens[at + 5])
    numbers = [float(v) for v in tokens[at + 6:]]
    width = sum(len(bone["channels"]) for bone in bones)
    assert len(numbers) == frames * width
    return bones, [numbers[i * width:(i + 1) * width] for i in range(frames)], frame_time


def turn(axis: str, degrees: float) -> list[list[float]]:
    c, s = math.cos(math.radians(degrees)), math.sin(math.radians(degrees))
    return {"X": [[1, 0, 0], [0, c, -s], [0, s, c]], "Y": [[c, 0, s], [0, 1, 0], [-s, 0, c]],
            "Z": [[c, -s, 0], [s, c, 0], [0, 0, 1]]}[axis]


def times3(a, b):
    return [[sum(a[r][k] * b[k][c] for k in range(3)) for c in range(3)] for r in range(3)]


def forward(bones: list[dict], row: list[float]) -> dict[str, tuple[list[float], list[list[float]]]]:
    """Each joint's position and rotation in the file's world: offset, then translation channels, then rotations in the
    order listed, each about the parent-relative axis left by the one before."""
    worlds, at = [], 0
    for bone in bones:
        position, rotation = list(bone["offset"]), [[1, 0, 0], [0, 1, 0], [0, 0, 1]]
        for channel in bone["channels"]:
            value, at = row[at], at + 1
            if channel.endswith("position"):
                position["XYZ".index(channel[0])] += value
            else:
                rotation = times3(rotation, turn(channel[0], value))
        if bone["parent"] is not None:
            p, r = worlds[bone["parent"]]
            position = [sum(r[i][k] * position[k] for k in range(3)) + p[i] for i in range(3)]
            rotation = times3(r, rotation)
        worlds.append((position, rotation))
    return {bone["name"]: world for bone, world in zip(bones, worlds)}


def written(point: Vec3, scale: float = 1.0) -> list[float]:
    return [point.x * scale, point.y * scale, -point.z * scale]


def flipped(basis) -> list[list[float]]:
    signs = (1, 1, -1)
    return [[basis[r][c] * signs[r] * signs[c] for c in range(3)] for r in range(3)]


def worlds(figure: Mannequin) -> dict[str, Transform]:
    return {name: figure.transform.then(frame) for name, frame in figure.frames().items()}


def walking() -> tuple[Location, Mannequin]:
    location = Location("walk", Registry.default())
    location.add("stock.box", size=(10, 0.1, 10), at=(0, -0.05, 0), material="stock.concrete")
    figure = location.add(Mannequin(name="walker", at=(0.3, 0, -0.2), yaw=30))
    location.move(figure, 0.5, pose="walk", ease="linear")
    location.move(figure, 1.0, at=(0.6, 0, 0.4), yaw=60, pose="stand")
    location.plant(figure, "left_foot", 0.5, 0.8)
    return location, figure


def moment(location: Location, figure: Mannequin, time: float) -> Mannequin:
    return location.at(time).nodes[location.nodes.index(figure)]


FIGURES = {**{f"pose-{name}": Mannequin(pose=name) for name in POSES},
           "seeded": Mannequin(seed=7, pose="walk"),
           "placed": Mannequin(kind="child", pose="point", at=(1.2, 0.3, -2.0), yaw=-125,
                               adjust={"head.turn_left_right": 25, "spine.left_right": 12}),
           "toddler": Mannequin(kind="toddler", pose="sit", grounded=False)}


# BVH out

@pytest.mark.parametrize("name", FIGURES)
def test_a_bvh_puts_every_joint_where_the_figure_has_it(name, tmp_path):
    figure = FIGURES[name]
    bones, rows, _ = parse_bvh(save_bvh(tmp_path / "pose.bvh", figure).read_text())
    found, expected = forward(bones, rows[0]), worlds(figure)
    t = Mannequin(pose="t", kind=figure.kind, seed=figure.seed, height=figure.height).frames()
    assert len(rows) == 1 and len(found) == len(JOINTS)
    for joint in JOINTS:
        position, rotation = found[joint.name]
        assert math.dist([v / 100 for v in position], written(expected[joint.name].position)) < 0.1 * MM, joint.name
        # A bone's world turn in the file is its turn from the T-stance, where a thumb is already turned.
        turn = Transform(basis=expected[joint.name].basis).then(Transform(basis=tuple(zip(*t[joint.name].basis)))).basis
        assert max(abs(a - b) for x, y in zip(rotation, flipped(turn)) for a, b in zip(x, y)) < 1e-5


def test_a_bvh_has_the_skeleton_at_rest_and_the_usual_channels(tmp_path):
    figure = Mannequin(kind="woman", height=1.7, pose="sit")
    bones, rows, frame_time = parse_bvh(save_bvh(tmp_path / "rest.bvh", figure, fps=24).read_text())
    assert frame_time == pytest.approx(1 / 24, abs=1e-6)
    assert bones[0]["name"] == "hips" and bones[0]["offset"] == (0, 0, 0)
    assert bones[0]["channels"] == ["Xposition", "Yposition", "Zposition", "Zrotation", "Xrotation", "Yrotation"]
    assert all(bone["channels"] == ["Zrotation", "Xrotation", "Yrotation"] for bone in bones[1:])
    leaves = {joint.name for joint in JOINTS} - {joint.parent for joint in JOINTS}
    assert {bone["name"] for bone in bones if bone["end"]} == leaves
    # With every channel at zero the joints stand as the T-stance of this body and height does, thumbs too, about the hips.
    rest, t = forward(bones, [0.0] * len(rows[0])), Mannequin(kind="woman", height=1.7, pose="t").frames()
    for joint in JOINTS:
        assert math.dist([v / 100 for v in rest[joint.name][0]],
                         written(t[joint.name].position - t["hips"].position)) < 0.1 * MM, joint.name


def test_a_bvh_follows_a_walking_location(tmp_path):
    location, figure = walking()
    bones, rows, frame_time = parse_bvh(save_bvh(tmp_path / "walk.bvh", figure, location, fps=10).read_text())
    assert len(rows) == 11 and frame_time == pytest.approx(0.1, abs=1e-6)
    for frame, row in enumerate(rows):
        found, expected = forward(bones, row), worlds(moment(location, figure, frame / 10))
        for joint in JOINTS:
            assert math.dist([v / 100 for v in found[joint.name][0]], written(expected[joint.name].position)) < 0.1 * MM


def test_a_bvh_can_name_its_bones_as_another_package_does(tmp_path):
    bones, _, _ = parse_bvh(save_bvh(tmp_path / "mixamo.bvh", Mannequin(), names="mixamo", units=1).read_text())
    names = [bone["name"] for bone in bones]
    assert names[0] == "mixamorig:Hips" and "mixamorig:LeftForeArm" in names and "mixamorig:RightHandPinky3" in names
    assert "jaw" in names and "mixamorig:LeftEye" in names  # Mixamo's body has no jaw, so it keeps this SDK's name
    with pytest.raises(InterchangeError, match="unity"):
        save_bvh(tmp_path / "other.bvh", Mannequin(), names="maya")


def test_a_bvh_needs_a_mannequin(tmp_path):
    location = Location("set", Registry.default())
    location.add("stock.box", size=(1, 1, 1), name="crate")
    with pytest.raises(InterchangeError):
        save_bvh(tmp_path / "crate.bvh", "crate", location)


# BVH in

def standing(pose, like: Mannequin) -> dict[str, Transform]:
    return Mannequin(pose=pose, kind=like.kind, seed=like.seed, height=like.height, grounded=False).frames()


@pytest.mark.parametrize("names", ["", "unity", "mixamo"])
def test_a_bvh_read_back_gives_the_same_joints(names, tmp_path):
    location, figure = walking()
    path = save_bvh(tmp_path / "walk.bvh", figure, location, fps=10, names=names)
    take = load_bvh(path)
    assert take.fps == 10 and len(take.poses) == 11 and not take.unknown and not take.clamped
    for frame, pose in enumerate(take.poses):
        found, expected = standing(pose, figure), worlds(moment(location, figure, frame / 10))
        for joint in JOINTS:
            assert (found[joint.name].position - expected[joint.name].position).length < MM, (frame, joint.name)


@pytest.mark.parametrize("name", ["pose-sit", "pose-drive", "seeded", "placed"])
def test_a_pose_read_back_is_the_same_pose(name, tmp_path):
    figure = FIGURES[name]
    take = load_bvh(save_bvh(tmp_path / "pose.bvh", figure), figure)
    found, expected = standing(take.poses[0], figure), worlds(figure)
    assert max((found[j.name].position - expected[j.name].position).length for j in JOINTS) < MM


ARMS_DOWN = """HIERARCHY
ROOT mixamorig:Hips
{
  OFFSET 0 0 0
  CHANNELS 6 Xposition Yposition Zposition Zrotation Xrotation Yrotation
  JOINT mixamorig:Spine
  {
    OFFSET 0 10 0
    CHANNELS 3 Zrotation Xrotation Yrotation
    JOINT mixamorig:Spine1
    {
      OFFSET 0 12 0
      CHANNELS 3 Zrotation Xrotation Yrotation
      JOINT mixamorig:Spine2
      {
        OFFSET 0 12 0
        CHANNELS 3 Zrotation Xrotation Yrotation
        JOINT mixamorig:Neck
        {
          OFFSET 0 18 0
          CHANNELS 3 Zrotation Xrotation Yrotation
          JOINT mixamorig:Head
          {
            OFFSET 0 8 0
            CHANNELS 3 Zrotation Xrotation Yrotation
            End Site
            {
              OFFSET 0 20 0
            }
          }
        }
        JOINT mixamorig:LeftShoulder
        {
          OFFSET 4 12 0
          CHANNELS 3 Zrotation Xrotation Yrotation
          JOINT mixamorig:LeftArm
          {
            OFFSET 14 0 0
            CHANNELS 3 Zrotation Xrotation Yrotation
            JOINT mixamorig:LeftForeArm
            {
              OFFSET 0 -28 0
              CHANNELS 3 Xrotation Yrotation Zrotation
              JOINT mixamorig:LeftHand
              {
                OFFSET 0 -25 0
                CHANNELS 3 Zrotation Xrotation Yrotation
                End Site
                {
                  OFFSET 0 -18 0
                }
              }
            }
          }
        }
        JOINT mixamorig:RightShoulder
        {
          OFFSET -4 12 0
          CHANNELS 3 Zrotation Xrotation Yrotation
          JOINT mixamorig:RightArm
          {
            OFFSET -14 0 0
            CHANNELS 3 Zrotation Xrotation Yrotation
            JOINT mixamorig:RightForeArm
            {
              OFFSET 0 -28 0
              CHANNELS 3 Zrotation Xrotation Yrotation
              JOINT mixamorig:RightHand
              {
                OFFSET 0 -25 0
                CHANNELS 3 Zrotation Xrotation Yrotation
                End Site
                {
                  OFFSET 0 -18 0
                }
              }
            }
          }
        }
      }
    }
  }
  JOINT mixamorig:LeftUpLeg
  {
    OFFSET 9 -6 0
    CHANNELS 3 Zrotation Xrotation Yrotation
    JOINT mixamorig:LeftLeg
    {
      OFFSET 0 -44 0
      CHANNELS 3 Zrotation Xrotation Yrotation
      JOINT mixamorig:LeftFoot
      {
        OFFSET 0 -42 0
        CHANNELS 3 Zrotation Xrotation Yrotation
        End Site
        {
          OFFSET 0 -4 15
        }
      }
    }
  }
  JOINT mixamorig:RightUpLeg
  {
    OFFSET -9 -6 0
    CHANNELS 3 Zrotation Xrotation Yrotation
    JOINT mixamorig:RightLeg
    {
      OFFSET 0 -44 0
      CHANNELS 3 Zrotation Xrotation Yrotation
      JOINT mixamorig:RightFoot
      {
        OFFSET 0 -42 0
        CHANNELS 3 Zrotation Xrotation Yrotation
        End Site
        {
          OFFSET 0 -4 15
        }
      }
    }
  }
  JOINT sword
  {
    OFFSET 0 0 10
    CHANNELS 3 Zrotation Xrotation Yrotation
    End Site
    {
      OFFSET 0 0 80
    }
  }
}
MOTION
Frames: {count}
Frame Time: 0.04
{rows}
"""
# The channels of one frame, by bone, in the file's order: 6 for the hips, then 3 for each bone below.
ORDER = ["mixamorig:Hips", "mixamorig:Spine", "mixamorig:Spine1", "mixamorig:Spine2", "mixamorig:Neck", "mixamorig:Head",
         "mixamorig:LeftShoulder", "mixamorig:LeftArm", "mixamorig:LeftForeArm", "mixamorig:LeftHand",
         "mixamorig:RightShoulder", "mixamorig:RightArm", "mixamorig:RightForeArm", "mixamorig:RightHand",
         "mixamorig:LeftUpLeg", "mixamorig:LeftLeg", "mixamorig:LeftFoot", "mixamorig:RightUpLeg", "mixamorig:RightLeg",
         "mixamorig:RightFoot", "sword"]


def arms_down(tmp_path: Path, *frames: dict) -> Path:
    """A file in centimetres, in the way Mixamo's characters stand: facing +z, the left side at +x, but at rest with the arms
    hanging down. Each frame names the channels it turns; the rest are 0."""
    rows = []
    for turned in frames:
        row = list(turned.get("mixamorig:Hips", (0, 92, 0, 0, 0, 0)))
        for bone in ORDER[1:]:
            row += list(turned.get(bone, (0, 0, 0)))
        rows.append(" ".join(str(value) for value in row))
    path = tmp_path / "arms-down.bvh"
    path.write_text(ARMS_DOWN.replace("{count}", str(len(frames))).replace("{rows}", "\n".join(rows)))
    return path


def along(frames: dict[str, Transform], start: str, end: str) -> Vec3:
    way = frames[end].position - frames[start].position
    return Vec3(*(v / way.length for v in way))


def degrees_apart(a: Vec3, b: Vec3) -> float:
    return math.degrees(math.acos(max(-1.0, min(1.0, a.x * b.x + a.y * b.y + a.z * b.z))))


def test_a_bvh_from_another_rig_is_retargeted_by_its_rest_pose(tmp_path):
    path = arms_down(tmp_path,
                     {},  # at rest: arms down
                     {"mixamorig:LeftArm": (90, 0, 0), "mixamorig:RightArm": (-90, 0, 0)},  # raised to a T
                     {"mixamorig:LeftForeArm": (-90, 0, 0)},  # left forearm turned forward, about x, listed first in its channels
                     {"mixamorig:Hips": (0, 92, 0, 0, 0, 90)})  # turned toward the file's +x, which is the figure's left
    take = load_bvh(path)
    assert take.fps == 25 and len(take.poses) == 4
    rest, t, bent, turned = (standing(pose, Mannequin()) for pose in take.poses)
    down, ahead = Vec3(0, -1, 0), Vec3(0, 0, 1)
    for side in ("left", "right"):
        assert degrees_apart(along(rest, f"{side}_upper_arm", f"{side}_lower_arm"), down) < 0.5
        assert degrees_apart(along(rest, f"{side}_lower_arm", f"{side}_hand"), down) < 0.5
        assert degrees_apart(along(rest, f"{side}_upper_leg", f"{side}_lower_leg"), down) < 0.5
        assert take.poses[0].get(f"{side}_lower_arm.stretch", 0) == pytest.approx(0, abs=0.1)
    assert all(abs(take.poses[0].get(f"hips.{c}", 0)) < 0.1 for c in ("front_back", "left_right", "twist_left_right"))
    assert degrees_apart(along(t, "left_upper_arm", "left_hand"), Vec3(-1, 0, 0)) < 0.5
    assert degrees_apart(along(t, "right_upper_arm", "right_hand"), Vec3(1, 0, 0)) < 0.5
    assert degrees_apart(along(bent, "left_upper_arm", "left_lower_arm"), down) < 0.5
    assert degrees_apart(along(bent, "left_lower_arm", "left_hand"), ahead) < 0.5
    assert take.poses[2]["left_lower_arm.stretch"] == pytest.approx(-90, abs=0.1)
    facing = Transform(basis=turned["hips"].basis).apply(ahead)
    assert degrees_apart(facing, Vec3(-1, 0, 0)) < 0.5
    # The hips keep their height: the file's 92 cm, in this body's proportions.
    assert rest["hips"].position.y == pytest.approx(Mannequin(pose="t", grounded=False).frames()["hips"].position.y, abs=0.03)


def test_unknown_joints_are_reported_and_their_turns_carried(tmp_path):
    take = load_bvh(arms_down(tmp_path, {"sword": (30, 40, 50)}))
    assert take.unknown == ("sword",)
    assert all(not key.startswith("sword") for key in take.poses[0])


def test_a_bones_namespace_is_looked_through(tmp_path):
    path = arms_down(tmp_path, {})
    path.write_text(path.read_text().replace("mixamorig:", "mixamorig7:"))
    take = load_bvh(path)
    assert take.unknown == ("sword",) and take.poses[0]["left_lower_arm.stretch"] == pytest.approx(0, abs=0.1)


def test_out_of_range_values_are_held_and_reported(tmp_path):
    path = arms_down(tmp_path, {}, {"mixamorig:LeftForeArm": (60, 0, 0)})  # an elbow bent backwards
    take = load_bvh(path)
    assert take.poses[1]["left_lower_arm.stretch"] == pytest.approx(5)
    assert take.clamped["left_lower_arm.stretch"] == (1,)  # and the hand, turning to follow the file's forearm, stops too
    assert all(key.startswith(("left_lower_arm.", "left_hand.")) for key in take.clamped)
    free = load_bvh(path, Mannequin(limits=False))
    assert free.poses[1]["left_lower_arm.stretch"] == pytest.approx(60, abs=0.1) and not free.clamped


def test_a_file_that_is_not_a_bvh_is_refused(tmp_path):
    path = tmp_path / "broken.bvh"
    path.write_text("HIERARCHY\nROOT hips\n{\n  OFFSET 0 0\n")
    with pytest.raises(InterchangeError):
        load_bvh(path)


# GLB

def glb_parts(path: Path) -> tuple[dict, bytes]:
    data = path.read_bytes()
    magic, version, length = struct.unpack_from("<4sII", data)
    assert magic == b"glTF" and version == 2 and length == len(data)
    size, kind = struct.unpack_from("<II", data, 12)
    assert kind == 0x4E4F534A and size % 4 == 0
    document = json.loads(data[20:20 + size])
    rest = 20 + size
    binary_size, binary_kind = struct.unpack_from("<II", data, rest)
    assert binary_kind == 0x004E4942 and binary_size % 4 == 0 and rest + 8 + binary_size == len(data)
    return document, data[rest + 8:]


SIZES = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}
WIDTHS = {5120: 1, 5121: 1, 5122: 2, 5123: 2, 5125: 4, 5126: 4}
FORMATS = {5120: "b", 5121: "B", 5122: "h", 5123: "H", 5125: "I", 5126: "f"}


def values(document: dict, binary: bytes, index: int) -> list[tuple]:
    accessor = document["accessors"][index]
    view = document["bufferViews"][accessor["bufferView"]]
    width = SIZES[accessor["type"]]
    layout = struct.Struct(f"<{width}{FORMATS[accessor['componentType']]}")
    start = view.get("byteOffset", 0) + accessor.get("byteOffset", 0)
    stride = view.get("byteStride") or layout.size
    return [layout.unpack_from(binary, start + n * stride) for n in range(accessor["count"])]


def test_a_glb_is_well_formed(tmp_path):
    location, figure = walking()
    check_well_formed(*glb_parts(save_glb(tmp_path / "walk.glb", figure, location, fps=10)), frames=11)


def check_well_formed(document: dict, binary: bytes, frames: int) -> None:
    """What glTF 2.0 asks of the buffers, views, accessors, skin, meshes and animation, as far as this file uses them."""
    assert document["asset"]["version"] == "2.0"
    assert document["buffers"][0]["byteLength"] <= len(binary) < document["buffers"][0]["byteLength"] + 4
    for view in document["bufferViews"]:
        assert view["buffer"] == 0 and view.get("byteOffset", 0) % 4 == 0
        assert view.get("byteOffset", 0) + view["byteLength"] <= document["buffers"][0]["byteLength"]
    for accessor in document["accessors"]:
        view = document["bufferViews"][accessor["bufferView"]]
        width = WIDTHS[accessor["componentType"]] * SIZES[accessor["type"]]
        assert accessor.get("byteOffset", 0) % WIDTHS[accessor["componentType"]] == 0
        assert accessor.get("byteOffset", 0) + accessor["count"] * width <= view["byteLength"]
    skin = document["skins"][0]
    assert len(skin["joints"]) == len(JOINTS) and document["nodes"][skin["skeleton"]]["name"] == "hips"
    assert document["accessors"][skin["inverseBindMatrices"]]["count"] == len(JOINTS)
    assert sorted(document["nodes"][index]["name"] for index in skin["joints"]) == sorted(joint.name for joint in JOINTS)
    meshes = [node for node in document["nodes"] if "mesh" in node]
    assert meshes and all(node["skin"] == 0 for node in meshes)
    for mesh in document["meshes"]:
        for primitive in mesh["primitives"]:
            attributes = primitive["attributes"]
            counts = {document["accessors"][index]["count"] for index in attributes.values()}
            assert len(counts) == 1
            position = document["accessors"][attributes["POSITION"]]
            points = values(document, binary, attributes["POSITION"])
            assert position["min"] == [min(p[i] for p in points) for i in range(3)]
            assert position["max"] == [max(p[i] for p in points) for i in range(3)]
            assert max(index for (index,) in values(document, binary, primitive["indices"])) < position["count"]
            assert all(max(joints) < len(JOINTS) for joints in values(document, binary, attributes["JOINTS_0"]))
            assert all(sum(weights) == pytest.approx(1) for weights in values(document, binary, attributes["WEIGHTS_0"]))
            assert all(abs(math.hypot(*normal) - 1) < 1e-4 for normal in values(document, binary, attributes["NORMAL"]))
    animation = document["animations"][0]
    assert len(animation["channels"]) == len(JOINTS) + 1
    for sampler in animation["samplers"]:
        times = values(document, binary, sampler["input"])
        assert len(times) == frames and document["accessors"][sampler["input"]]["max"] == [pytest.approx((frames - 1) / 10)]
        assert document["accessors"][sampler["input"]]["min"] == [0.0]
        assert document["accessors"][sampler["output"]]["count"] == len(times)
    for channel in animation["channels"]:
        output = values(document, binary, animation["samplers"][channel["sampler"]]["output"])
        if channel["target"]["path"] == "rotation":
            assert all(abs(math.hypot(*q) - 1) < 1e-5 for q in output)


def test_a_glb_read_as_a_mesh_has_the_figures_bounds_and_materials(tmp_path):
    figure = Mannequin(kind="woman", pose="point", at=(0.4, 0, -1.0), yaw=40, adjust={"spine.front_back": 10})
    mesh = Mesh(path=save_glb(tmp_path / "point.glb", figure))
    low, high = mesh.bounds(Transform())
    boxes = [placed.item.bounds(placed.world) for placed in figure.walk()]
    assert (low - Vec3(*(min(getattr(b[0], a) for b in boxes) for a in "xyz"))).length < MM
    assert (high - Vec3(*(max(getattr(b[1], a) for b in boxes) for a in "xyz"))).length < MM
    registry = Registry.default()
    skins = {skin.name.partition(".")[2]: skin.own.color for skin in mesh.skins()}
    assert skins == {name: registry.materials.get(name).color
                     for name in (figure.body, figure.joint, figure.left, figure.right)}


def test_a_glb_faces_outward(tmp_path):
    document, binary = glb_parts(save_glb(tmp_path / "t.glb", Mannequin(pose="t")))
    for mesh in document["meshes"]:
        primitive = mesh["primitives"][0]
        points = values(document, binary, primitive["attributes"]["POSITION"])
        middle = [sum(p[i] for p in points) / len(points) for i in range(3)]
        corners = [index for (index,) in values(document, binary, primitive["indices"])]
        for a, b, c in zip(*[iter(corners)] * 3):
            u = [q - p for p, q in zip(points[a], points[b])]
            v = [q - p for p, q in zip(points[a], points[c])]
            normal = (u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0])
            assert sum(n * (p - m) for n, p, m in zip(normal, points[a], middle)) > -1e-12


def node_worlds(document: dict, binary: bytes, frame: int) -> dict[str, list[list[float]]]:
    """Each joint node's world matrix at one keyframe of the animation."""
    nodes = [dict(node) for node in document["nodes"]]
    animation = document["animations"][0]
    for channel in animation["channels"]:
        output = values(document, binary, animation["samplers"][channel["sampler"]]["output"])
        nodes[channel["target"]["node"]][channel["target"]["path"]] = list(output[frame])
    parents = {child: index for index, node in enumerate(nodes) for child in node.get("children", ())}
    found: dict[int, list[list[float]]] = {}

    def world(index: int) -> list[list[float]]:
        if index not in found:
            local = _local(nodes[index])
            found[index] = _times(world(parents[index]), local) if index in parents else local
        return found[index]
    return {nodes[index]["name"]: world(index) for index in document["skins"][0]["joints"]}


def test_a_glbs_joints_follow_the_location(tmp_path):
    location, figure = walking()
    document, binary = glb_parts(save_glb(tmp_path / "walk.glb", figure, location, fps=10))
    for frame in (0, 3, 6, 10):
        found, expected = node_worlds(document, binary, frame), worlds(moment(location, figure, frame / 10))
        for joint in JOINTS:
            matrix, want = found[joint.name], expected[joint.name]
            assert math.dist([row[3] for row in matrix[:3]], written(want.position)) < 0.1 * MM
            assert max(abs(matrix[r][c] - flipped(want.basis)[r][c]) for r in range(3) for c in range(3)) < 1e-5


def test_a_glbs_skin_carries_each_limb_with_its_bone(tmp_path):
    location, figure = walking()
    document, binary = glb_parts(save_glb(tmp_path / "walk.glb", figure, location, fps=10))
    inverse = values(document, binary, document["skins"][0]["inverseBindMatrices"])
    joints = document["skins"][0]["joints"]
    found = node_worlds(document, binary, 7)
    skinning = [_times(found[document["nodes"][index]["name"]], [[m[c * 4 + r] for c in range(4)] for r in range(4)])
                for index, m in zip(joints, inverse)]
    low, high = [math.inf] * 3, [-math.inf] * 3
    for primitive in (mesh["primitives"][0] for mesh in document["meshes"]):
        attributes = primitive["attributes"]
        for point, bones in zip(values(document, binary, attributes["POSITION"]), values(document, binary, attributes["JOINTS_0"])):
            m = skinning[bones[0]]
            moved = [sum(m[r][k] * value for k, value in enumerate((*point, 1.0))) for r in range(3)]
            low, high = [min(a, b) for a, b in zip(low, moved)], [max(a, b) for a, b in zip(high, moved)]
    later = moment(location, figure, 0.7)
    boxes = [placed.item.bounds(placed.world) for placed in later.walk()]
    want_low = Vec3(*(min(getattr(b[0], a) for b in boxes) for a in "xyz"))
    want_high = Vec3(*(max(getattr(b[1], a) for b in boxes) for a in "xyz"))
    # The file's z is the SDK's -z, so its low z is the figure's high one.
    assert math.dist(low, [want_low.x, want_low.y, -want_high.z]) < MM
    assert math.dist(high, [want_high.x, want_high.y, -want_low.z]) < MM


def test_a_glb_of_one_pose_has_no_animation(tmp_path):
    document, _ = glb_parts(save_glb(tmp_path / "sit.glb", Mannequin(pose="sit")))
    assert "animations" not in document


# A skinned GLB

PARENTS = {joint.name: joint.parent for joint in JOINTS}


def matrix4(m: tuple) -> list[list[float]]:
    """An accessor's MAT4, which glTF stores by columns, as rows."""
    return [[m[c * 4 + r] for c in range(4)] for r in range(4)]


def moved(m: list[list[float]], point) -> list[float]:
    return [sum(m[r][k] * value for k, value in enumerate((*point, 1.0))) for r in range(3)]


def in_file(world: Transform) -> list[list[float]]:
    """A transform in the SDK as the 4 by 4 matrix a model file holds for it."""
    basis = flipped(world.basis)
    return [[*basis[r], written(world.position)[r]] for r in range(3)] + [[0.0, 0.0, 0.0, 1.0]]


def inverse(m: list[list[float]]) -> list[list[float]]:
    """The inverse of a rotation and a translation."""
    turn = [[m[c][r] for c in range(3)] for r in range(3)]
    back = [-sum(turn[r][k] * m[k][3] for k in range(3)) for r in range(3)]
    return [[*turn[r], back[r]] for r in range(3)] + [[0.0, 0.0, 0.0, 1.0]]


def transpose(m) -> list[list[float]]:
    return [[m[c][r] for c in range(3)] for r in range(3)]


def degrees_between(a, b) -> float:
    """How far apart two rotations are, in radians."""
    trace = sum(times3(transpose(a), b)[i][i] for i in range(3))
    return math.acos(max(-1.0, min(1.0, (trace - 1) / 2)))


def skinned(document: dict, binary: bytes, frame: int) -> list[tuple]:
    """Every vertex as the skin and one keyframe of the animation place it: the position, the weights by joint name, and
    the position at the bind."""
    inverse_binds = values(document, binary, document["skins"][0]["inverseBindMatrices"])
    joints = document["skins"][0]["joints"]
    found = node_worlds(document, binary, frame)
    skinning = [_times(found[document["nodes"][index]["name"]], matrix4(m)) for index, m in zip(joints, inverse_binds)]
    vertices = []
    for mesh in document["meshes"]:
        for primitive in mesh["primitives"]:
            attributes = primitive["attributes"]
            for point, bones, weights in zip(values(document, binary, attributes["POSITION"]),
                                             values(document, binary, attributes["JOINTS_0"]),
                                             values(document, binary, attributes["WEIGHTS_0"])):
                place = [sum(w * v for w, v in zip(weights, column))
                         for column in zip(*(moved(skinning[bone], point) for bone in bones))]
                named = {document["nodes"][joints[bone]]["name"]: weight for bone, weight in zip(bones, weights) if weight}
                vertices.append((place, named, point))
    return vertices


def t_stance(figure: Mannequin) -> dict[str, Transform]:
    return Mannequin(pose="t", kind=figure.kind, seed=figure.seed, height=figure.height, grounded=figure.grounded).frames()


def test_a_skinned_glb_is_well_formed_and_one_body(tmp_path):
    location, figure = walking()
    document, binary = glb_parts(save_glb(tmp_path / "walk.glb", figure, location, fps=10, skinned=True))
    check_well_formed(document, binary, frames=11)
    assert len(document["meshes"]) == 1 and len([node for node in document["nodes"] if "mesh" in node]) == 1
    used = {primitive["material"] for primitive in document["meshes"][0]["primitives"]}
    assert len(used) == len(document["meshes"][0]["primitives"]) == len(document["materials"])  # one primitive to a material


def test_a_skinned_glbs_weights_are_whole_and_few(tmp_path):
    document, binary = glb_parts(save_glb(tmp_path / "walk.glb", Mannequin(pose="walk"), skinned=True))
    for primitive in document["meshes"][0]["primitives"]:
        attributes = primitive["attributes"]
        assert document["accessors"][attributes["WEIGHTS_0"]]["type"] == "VEC4"
        for joints, weights in zip(values(document, binary, attributes["JOINTS_0"]),
                                   values(document, binary, attributes["WEIGHTS_0"])):
            assert abs(sum(weights) - 1) < 1e-6 and min(weights) >= 0
            used = [joint for joint, weight in zip(joints, weights) if weight]
            assert len(used) == len(set(used)) <= 4


def test_a_skinned_glb_is_bound_at_the_t_stance(tmp_path):
    figure = FIGURES["placed"]
    document, binary = glb_parts(save_glb(tmp_path / "point.glb", figure, skinned=True))
    rest = t_stance(figure)
    inverse_binds = values(document, binary, document["skins"][0]["inverseBindMatrices"])
    for index, m in zip(document["skins"][0]["joints"], inverse_binds):
        want = inverse(in_file(rest[document["nodes"][index]["name"]]))
        assert max(abs(a - b) for x, y in zip(matrix4(m), want) for a, b in zip(x, y)) < 1e-5
    # Without its animation the file stands at the bind too, so any reader shows the body it was bound in.
    nodes = document["nodes"]
    parents = {child: index for index, node in enumerate(nodes) for child in node.get("children", ())}

    def world(index: int) -> list[list[float]]:
        return _times(world(parents[index]), _local(nodes[index])) if index in parents else _local(nodes[index])
    for index in document["skins"][0]["joints"]:
        want = in_file(rest[nodes[index]["name"]])
        assert max(abs(a - b) for x, y in zip(world(index), want) for a, b in zip(x, y)) < 1e-5
    # A figure on its own is a pose, kept as an animation of one key.
    assert len(values(document, binary, document["animations"][0]["samplers"][0]["input"])) == 1


def neighbours(a: str, b: str) -> bool:
    return PARENTS[a] == b or PARENTS[b] == a


@pytest.mark.parametrize("case", ["walking", "placed", "toddler"])
def test_a_skin_puts_the_body_where_the_figure_has_its_limbs(case, tmp_path):
    if case == "walking":
        location, source = walking()
        path, frame = save_glb(tmp_path / "walk.glb", source, location, fps=10, skinned=True), 7
        figure = moment(location, source, 0.7)
    else:
        figure = FIGURES[case]
        path, frame = save_glb(tmp_path / f"{case}.glb", figure, skinned=True), 0
    document, binary = glb_parts(path)
    posed, rest = worlds(figure), t_stance(figure)
    rigid = {name: _times(in_file(posed[name]), inverse(in_file(rest[name]))) for name in posed}  # bind to pose, by bone
    eggs = {}
    for placed in figure.walk():
        eggs.setdefault(placed.item.name.partition(".")[0], []).append((placed.world, placed.item.radii))
    vertices = skinned(document, binary, frame)
    for place, weights, point in vertices:
        # Every vertex is where the bones it follows put it, by its weights, as frames() has the bones. The file holds
        # float32, which rounds a position 2 m from the origin to within 0.2 micrometres; 0.01 mm leaves room for that
        # through a chain of 8 joints, and is far below anything a picture shows.
        want = [sum(weight * value for weight, value in zip(weights.values(), column))
                for column in zip(*(moved(rigid[name], point) for name in weights))]
        assert math.dist(place, want) < 0.01 * MM
        if len(weights) == 1:  # one bone's alone: on the surface of one of that bone's eggs, as the figure stands
            (main,) = weights
            sdk = Vec3(place[0], place[1], -place[2])
            off = []
            for world, radii in eggs[main]:
                local = world.undo(sdk)
                scale = math.sqrt(sum((v / r) ** 2 for v, r in zip(local, radii)))
                off.append(local.length * abs(1 - 1 / scale))
            assert min(off) < 0.01 * MM, main
        else:  # blended about one bone and its neighbours: no further from where that bone puts it than their bends allow
            main = next((name for name in weights if all(other == name or neighbours(name, other) for other in weights)), None)
            assert main, weights
            allowed = 0.0
            for name, weight in weights.items():
                if name != main:
                    joint = rest[name if PARENTS[name] == main else main].position  # the joint the two bones share
                    bend = degrees_between(times3(posed[name].basis, transpose(rest[name].basis)),
                                           times3(posed[main].basis, transpose(rest[main].basis)))
                    allowed += weight * bend * math.dist(point, written(joint))
            assert math.dist(place, moved(rigid[main], point)) <= allowed + 0.01 * MM


def test_an_elbow_and_a_knee_bend_between_their_bones(tmp_path):
    figure = Mannequin(pose="t")
    document, binary = glb_parts(save_glb(tmp_path / "t.glb", figure, skinned=True))
    rest = t_stance(figure)
    vertices = skinned(document, binary, 0)
    for upper, lower in (("left_upper_arm", "left_lower_arm"), ("right_upper_leg", "right_lower_leg")):
        joint = written(rest[lower].position)
        nearest = min(vertices, key=lambda vertex: math.dist(vertex[2], joint))
        assert nearest[1].get(upper, 0) > 0.2 and nearest[1].get(lower, 0) > 0.2, nearest[1]
        assert math.dist(nearest[2], joint) < 0.06
        # Half way down either bone, the skin follows that bone alone.
        for bone, end in ((upper, lower), (lower, lower.replace("lower_arm", "hand").replace("lower_leg", "foot"))):
            middle = [(a + b) / 2 for a, b in zip(written(rest[bone].position), written(rest[end].position))]
            nearest = min(vertices, key=lambda vertex: math.dist(vertex[2], middle))
            assert nearest[1] == {bone: 1.0}, (bone, nearest[1])


def test_a_skinned_glb_draws_its_pose_in_the_engine(tmp_path):
    figure = Mannequin(pose="stand")
    location = flat_set()
    location.add(Mesh(path=save_glb(tmp_path / "stand.glb", figure, skinned=True), at=(0, 0, 3)))
    view = Projection(location.shots["front"], W, H)
    hand = view.pixel(Transform.at((0, 0, 3)).apply(worlds(figure)["left_hand"].position))
    forearm = view.pixel(Transform.at((0, 0, 3)).apply(t_stance(figure)["left_lower_arm"].position + Vec3(0.1, 0, 0)))

    def drawn(clip: bool) -> list[bytes]:
        scene = Renderer().compile(location, "front", Styled(Look([Flat()], sky=GREY), W, H, supersample=1))
        meshes = [node for node in scene.iter() if node.xml_name == "object3D" and node.primitive == "mesh"]
        assert len(meshes) == 1
        if clip:
            meshes[0].animationClip = "0"
        output = Renderer().still(scene, tmp_path / f"{clip}.png")
        raw = subprocess.run(["ffmpeg", "-loglevel", "error", "-i", str(output), "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                             capture_output=True, check=True).stdout
        return [raw[row * W * 3:(row + 1) * W * 3] for row in range(H)]
    rest, posed = drawn(False), drawn(True)
    # At rest the body stands in the T-stance, its forearm out to the side; with its clip it stands as the figure does.
    assert not near(pixel(rest, *forearm), GREY) and near(pixel(posed, *forearm), GREY)
    assert near(pixel(rest, *hand), GREY) and not near(pixel(posed, *hand), GREY)


# glTF in

def test_a_skinned_glb_read_back_gives_the_same_joints(tmp_path):
    location, figure = walking()
    take = load_gltf(save_glb(tmp_path / "walk.glb", figure, location, fps=10, skinned=True))
    assert take.fps == 10 and len(take.poses) == 11 and not take.unknown and not take.clamped
    for frame, pose in enumerate(take.poses):
        found, expected = standing(pose, figure), worlds(moment(location, figure, frame / 10))
        for joint in JOINTS:
            assert (found[joint.name].position - expected[joint.name].position).length < MM, (frame, joint.name)


@pytest.mark.parametrize("name", ["pose-sit", "pose-drive", "seeded", "placed"])
def test_a_pose_read_back_from_a_glb_is_the_same_pose(name, tmp_path):
    figure = FIGURES[name]
    take = load_gltf(save_glb(tmp_path / "pose.glb", figure, skinned=True), figure)
    assert len(take.poses) == 1
    found, expected = standing(take.poses[0], figure), worlds(figure)
    assert max((found[j.name].position - expected[j.name].position).length for j in JOINTS) < MM


def rewritten(path: Path, change) -> Path:
    """A GLB with its JSON changed by `change`, the binary kept."""
    document, binary = glb_parts(path)
    text = json.dumps(change(document)).encode()
    text += b" " * (-len(text) % 4)
    chunks = struct.pack("<II", len(text), 0x4E4F534A) + text + struct.pack("<II", len(binary), 0x004E4942) + binary
    path.write_bytes(b"glTF" + struct.pack("<II", 2, 12 + len(chunks)) + chunks)
    return path


@pytest.mark.parametrize("prefix", ["mixamorig:", "mixamorig", "mixamorig_", "mixamorig1:"])
def test_a_glbs_mixamo_names_are_seen_through_with_or_without_a_colon(prefix, tmp_path):
    figure = FIGURES["pose-sit"]
    path = save_glb(tmp_path / "sit.glb", figure, skinned=True, names="mixamo")
    assert any(node["name"] == "mixamorig:LeftForeArm" for node in glb_parts(path)[0]["nodes"])

    def renamed(document: dict) -> dict:
        for node in document["nodes"]:
            node["name"] = node["name"].replace("mixamorig:", prefix)
        return document
    take = load_gltf(rewritten(path, renamed), figure)
    assert not take.unknown  # the eyes too, which Mixamo names; the jaw, which it lacks, keeps this SDK's name
    found, expected = standing(take.poses[0], figure), worlds(figure)
    assert max((found[j.name].position - expected[j.name].position).length for j in JOINTS) < MM


def test_a_skeleton_under_a_turned_and_scaled_node_reads_the_same(tmp_path):
    # As a package's export often has it: the bones under an "Armature" in other units, turned to its idea of up or ahead.
    location, figure = walking()
    path = save_glb(tmp_path / "walk.glb", figure, location, fps=10, skinned=True)

    def wrapped(document: dict) -> dict:
        hips = document["scenes"][0]["nodes"][0]
        half = math.sqrt(0.5)
        document["nodes"].append({"name": "Armature", "rotation": [0, half, 0, half], "scale": [100, 100, 100],
                                  "children": [hips]})
        document["scenes"][0]["nodes"][0] = len(document["nodes"]) - 1
        return document
    take = load_gltf(rewritten(path, wrapped))
    assert not take.unknown and len(take.poses) == 11
    for frame in (0, 4, 10):
        found, expected = standing(take.poses[frame], figure), worlds(moment(location, figure, frame / 10))
        assert max((found[j.name].position - expected[j.name].position).length for j in JOINTS) < MM


def test_a_gltf_with_its_buffer_in_a_file_beside_it_is_read(tmp_path):
    figure = FIGURES["seeded"]
    document, binary = glb_parts(save_glb(tmp_path / "walk.glb", figure, skinned=True))
    (tmp_path / "walk.bin").write_bytes(binary)
    document["buffers"][0]["uri"] = "walk.bin"
    (tmp_path / "walk.gltf").write_text(json.dumps(document))
    take = load_gltf(tmp_path / "walk.gltf", figure)
    found, expected = standing(take.poses[0], figure), worlds(figure)
    assert max((found[j.name].position - expected[j.name].position).length for j in JOINTS) < MM


def test_a_file_that_is_not_a_gltf_is_refused(tmp_path):
    path = tmp_path / "broken.glb"
    path.write_bytes(b"glTF" + struct.pack("<II", 2, 40) + b"\0" * 8)
    with pytest.raises(InterchangeError):
        load_gltf(path)
    document, _ = glb_parts(save_glb(tmp_path / "t.glb", Mannequin(), skinned=True))
    del document["animations"], document["skins"]
    for node in document["nodes"]:
        node["name"] = "bone"
    (tmp_path / "nothing.gltf").write_text(json.dumps({**document, "meshes": [], "buffers": []}))
    with pytest.raises(InterchangeError, match="no bone"):
        load_gltf(tmp_path / "nothing.gltf")
    with pytest.raises(InterchangeError, match="no animation 'dance'; it has mannequin"):
        load_gltf(tmp_path / "t.glb", animation="dance")


# The bone names of a Mixamo character as a published file has them: three.js r160, examples/models/gltf/Xbot.glb
# (https://github.com/mrdoob/three.js/raw/r160/examples/models/gltf/Xbot.glb), every node under its "Armature", each
# written there with the prefix "mixamorig:".
XBOT = """Hips Spine Spine1 Spine2 Neck Head HeadTop_End LeftEye RightEye
LeftShoulder LeftArm LeftForeArm LeftHand RightShoulder RightArm RightForeArm RightHand
LeftHandThumb1 LeftHandThumb2 LeftHandThumb3 LeftHandThumb4 LeftHandIndex1 LeftHandIndex2 LeftHandIndex3 LeftHandIndex4
LeftHandMiddle1 LeftHandMiddle2 LeftHandMiddle3 LeftHandMiddle4 LeftHandRing1 LeftHandRing2 LeftHandRing3 LeftHandRing4
LeftHandPinky1 LeftHandPinky2 LeftHandPinky3 LeftHandPinky4
RightHandThumb1 RightHandThumb2 RightHandThumb3 RightHandThumb4 RightHandIndex1 RightHandIndex2 RightHandIndex3 RightHandIndex4
RightHandMiddle1 RightHandMiddle2 RightHandMiddle3 RightHandMiddle4 RightHandRing1 RightHandRing2 RightHandRing3 RightHandRing4
RightHandPinky1 RightHandPinky2 RightHandPinky3 RightHandPinky4
LeftUpLeg LeftLeg LeftFoot LeftToeBase LeftToe_End RightUpLeg RightLeg RightFoot RightToeBase RightToe_End"""
XBOT_ENDS = {"HeadTop_End", "LeftToe_End", "RightToe_End", *(f"{side}Hand{finger}4" for side in ("Left", "Right")
                                                            for finger in ("Thumb", "Index", "Middle", "Ring", "Pinky"))}


def test_mixamo_names_are_those_of_a_published_mixamo_character():
    published = {f"mixamorig:{name}" for name in XBOT.split()}
    assert len(published) == 67
    named = {joint.name: joint.known_as.get("mixamo") for joint in JOINTS}
    assert {name for name in named.values() if name} <= published  # every name given is one Mixamo uses
    # Mixamo has every bone of this body but the jaw, and its other bones end a chain, where nothing turns.
    assert [joint for joint, name in named.items() if not name] == ["jaw"]
    assert published - set(named.values()) == {f"mixamorig:{name}" for name in XBOT_ENDS}
