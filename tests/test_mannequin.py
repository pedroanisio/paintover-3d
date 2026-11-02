"""The mannequin: its parameters against the references, the way each control turns, and a figure standing in a set."""
import hashlib
import json
import math
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import pytest
from sr_core.scene import check

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT)]

from srlocations import Blueprint, Location, Projection, Registry, Renderer, SceneCompiler, Shaded, SharedCatalog, Vec3
from srlocations.figures import angle
from srlocations.registry import CatalogError
from srlocations.stock.mannequin import (ALIASES, BY_NAME, JOINTS, JOINTS_VERSION, KINDS, PARAMETERS, POSES, Mannequin,
                                         PoseError, both, curled, joint_named)

BODY = ["Spine Front-Back", "Spine Left-Right", "Spine Twist Left-Right", "Chest Front-Back", "Chest Left-Right",
        "Chest Twist Left-Right", "UpperChest Front-Back", "UpperChest Left-Right", "UpperChest Twist Left-Right",
        "Neck Nod Down-Up", "Neck Tilt Left-Right", "Neck Turn Left-Right", "Head Nod Down-Up", "Head Tilt Left-Right",
        "Head Turn Left-Right", "Left Eye Down-Up", "Left Eye In-Out", "Right Eye Down-Up", "Right Eye In-Out", "Jaw Close",
        "Jaw Left-Right"]
LEG = ["Upper Leg Front-Back", "Upper Leg In-Out", "Upper Leg Twist In-Out", "Lower Leg Stretch", "Lower Leg Twist In-Out",
       "Foot Up-Down", "Foot Twist In-Out", "Toes Up-Down"]
ARM = ["Shoulder Down-Up", "Shoulder Front-Back", "Arm Down-Up", "Arm Front-Back", "Arm Twist In-Out", "Forearm Stretch",
       "Forearm Twist In-Out", "Hand Down-Up", "Hand In-Out"]
HAND = [f"{finger} {part}" for finger in ("Thumb", "Index", "Middle", "Ring", "Little")
        for part in ("1 Stretched", "Spread", "2 Stretched", "3 Stretched")]
MUSCLES = (BODY + [f"{side} {name}" for side in ("Left", "Right") for name in LEG]
           + [f"{side} {name}" for side in ("Left", "Right") for name in ARM]
           + [f"{side} {name}" for side in ("Left", "Right") for name in HAND])
BONES = {"Hips", "Spine", "Chest", "UpperChest", "Neck", "Head", "LeftEye", "RightEye", "Jaw"} | {
    f"{side}{bone}" for side in ("Left", "Right")
    for bone in ("UpperLeg", "LowerLeg", "Foot", "Toes", "Shoulder", "UpperArm", "LowerArm", "Hand",
                 *(f"{finger}{part}" for finger in ("Thumb", "Index", "Middle", "Ring", "Little")
                   for part in ("Proximal", "Intermediate", "Distal")))}


def where(pose, joint: str, **given) -> Vec3:
    return Mannequin(pose=pose, grounded=False, **given).frames()[joint].position


def moved(key: str, value: float, joint: str) -> Vec3:
    return where({key: value}, joint) - where({}, joint)


def mirrored(key: str) -> str:
    return key.replace("left_", "\0").replace("right_", "left_").replace("\0", "right_")


def test_the_parameters_are_unitys_muscles_the_root_and_a_foot_roll():
    muscles = [dof.muscle for dof in PARAMETERS.values() if dof.muscle]
    assert len(MUSCLES) == 95 and muscles == MUSCLES
    assert [key for key, dof in PARAMETERS.items() if not dof.muscle] == [
        "hips.right", "hips.up", "hips.forward", "hips.front_back", "hips.left_right", "hips.twist_left_right",
        "left_foot.roll_in_out", "right_foot.roll_in_out"]
    assert len(PARAMETERS) == 103


def test_the_skeleton_is_unitys_humanoid():
    assert {joint.known_as["unity"] for joint in JOINTS} == BONES
    assert len(JOINTS) == len(BONES) == 55


def test_parents_come_first_and_each_joint_has_a_range():
    seen = set()
    for joint in JOINTS:
        assert joint.parent is None or joint.parent in seen
        seen.add(joint.name)
    assert all(dof.low < dof.high for dof in PARAMETERS.values())
    assert all(dof.low <= 0 <= dof.high for dof in PARAMETERS.values())


def test_other_packages_names_reach_a_joint():
    assert joint_named("mixamorig:LeftForeArm").name == "left_lower_arm"
    assert joint_named("LeftHandIndex3").name == "left_index_distal"
    assert joint_named("thigh_r").name == "right_upper_leg"
    assert joint_named("pinky_02_l").name == "left_little_intermediate"
    assert joint_named("mixamorig:LeftHandPinky1").name == joint_named("LeftHandPinky1").name == "left_little_proximal"
    assert joint_named("RightUpperArm").name == "right_upper_arm"
    assert where({"mixamorig:LeftArm.down_up": 40}, "left_hand") == where({"left_upper_arm.down_up": 40}, "left_hand")


def test_a_reference_name_means_one_bone():
    for other, name in ALIASES.items():
        assert [joint.name for joint in JOINTS if other in joint.known_as.values()] == [name]


@pytest.mark.parametrize("key", list(PARAMETERS))
def test_every_parameter_moves_the_figure(key):
    dof = PARAMETERS[key]
    value = dof.high or dof.low
    still, turned = Mannequin(pose={}, grounded=False), Mannequin(pose={key: value}, grounded=False)
    assert still.frames() != turned.frames()


@pytest.mark.parametrize("key", [key for key in PARAMETERS if key.startswith("left_")])
def test_an_angle_means_the_same_motion_on_either_side(key):
    dof = PARAMETERS[key]
    value = dof.high or dof.low
    left = Mannequin(pose={key: value}, grounded=False).frames()
    right = Mannequin(pose={mirrored(key): value}, grounded=False).frames()
    for name, frame in left.items():
        other = right[mirrored(name)].position
        assert frame.position.x == pytest.approx(-other.x, abs=1e-9)
        assert frame.position.y == pytest.approx(other.y, abs=1e-9)
        assert frame.position.z == pytest.approx(other.z, abs=1e-9)


@pytest.mark.parametrize("key, value, joint, axis, sign", [
    ("spine.front_back", -30, "head", "z", 1),            # forward
    ("spine.left_right", 10, "head", "x", 1),             # to its right
    ("neck.nod_down_up", -20, "left_eye", "y", -1),       # down, so the eyes drop
    ("right_upper_leg.front_back", -45, "right_foot", "z", 1),
    ("right_upper_leg.in_out", 30, "right_foot", "x", 1),
    ("left_upper_leg.in_out", 30, "left_foot", "x", -1),
    ("right_lower_leg.stretch", -60, "right_foot", "z", -1),
    ("right_foot.up_down", -30, "right_toes", "y", 1),
    ("right_toes.up_down", -40, "right_foot", "y", 0),
    ("right_shoulder.down_up", 20, "right_hand", "y", 1),
    ("right_upper_arm.down_up", -60, "right_hand", "y", -1),
    ("right_upper_arm.front_back", -60, "right_hand", "z", 1),
    ("right_lower_arm.stretch", -90, "right_hand", "z", 1),
    ("right_hand.down_up", -60, "right_index_proximal", "y", -1),
    ("right_index_proximal.stretched", -60, "right_index_intermediate", "y", -1),
    ("right_index_proximal.spread", 15, "right_index_intermediate", "z", 1),
    ("right_little_proximal.spread", 15, "right_little_intermediate", "z", -1),
    ("hips.up", 0.5, "head", "y", 1),
])
def test_each_control_turns_the_way_its_name_reads(key, value, joint, axis, sign):
    change = getattr(moved(key, value, joint), axis)
    assert change == pytest.approx(0, abs=1e-9) if sign == 0 else change * sign > 0.005


def test_a_head_turned_right_faces_right():
    head = Mannequin(pose={"head.turn_left_right": 40}, grounded=False).frames()["head"]
    assert (head.apply((0, 0, 1)) - head.position).x > 0.5


def test_a_twist_leaves_the_bone_where_it_is():
    for key, end in (("right_upper_arm.twist_in_out", "right_lower_arm"), ("right_upper_leg.twist_in_out", "right_lower_leg")):
        assert moved(key, 40, end).length == pytest.approx(0, abs=1e-9)


def test_the_elbow_bends_forward_at_the_side_of_the_body():
    frames = Mannequin(pose=both({"upper_arm.down_up": -85, "lower_arm.stretch": -90}), grounded=False).frames()
    upper, hand = frames["right_lower_arm"].position, frames["right_hand"].position
    assert hand.z - upper.z > 0.2 and abs(hand.y - upper.y) < 0.05


@pytest.mark.parametrize("pose", list(POSES))
def test_bones_keep_their_length_in_every_pose(pose):
    rest, posed = Mannequin(pose={}).frames(), Mannequin(pose=pose).frames()
    for joint in JOINTS:
        if joint.parent and joint.parent != "hips":
            length = (rest[joint.name].position - rest[joint.parent].position).length
            assert (posed[joint.name].position - posed[joint.parent].position).length == pytest.approx(length, abs=1e-9)


@pytest.mark.parametrize("pose", list(POSES))
def test_every_pose_rests_on_the_floor(pose):
    figure = Mannequin(pose=pose)
    assert min(part.bounds(part.transform)[0].y for part in figure.build()) == pytest.approx(0, abs=1e-6)


def test_a_figure_is_as_tall_as_it_says():
    for height in (1.5, 1.75, 2.0):
        parts = Mannequin(pose="t", height=height).build()
        assert max(part.bounds(part.transform)[1].y for part in parts) == pytest.approx(height, rel=0.01)


def test_without_the_floor_the_hips_stay_put():
    assert Mannequin(pose="sit", grounded=False).frames()["hips"].position == where({}, "hips")
    assert Mannequin(pose="sit").frames()["hips"].position.y < where({}, "hips").y - 0.3


def test_sitting_meets_a_chair():
    hips = Mannequin(pose="sit").frames()["hips"].position.y
    assert 0.55 < hips < 0.62  # the stock chair's seat is 0.49 high and the pelvis reaches 0.11 below the hip joint


def test_a_control_past_its_range_is_refused():
    with pytest.raises(PoseError, match=r"left_lower_leg.stretch is 40.*-142 to 2"):
        Mannequin(pose={"left_lower_leg.stretch": 40})
    assert Mannequin(pose={"left_lower_leg.stretch": 40}, limits=False).values()["left_lower_leg.stretch"] == 40


def test_a_typo_gets_a_suggestion():
    with pytest.raises(PoseError, match="did you mean left_upper_arm"):
        Mannequin(pose={"left_upper_arn.down_up": 1})
    with pytest.raises(PoseError, match="did you mean head.nod_down_up"):
        Mannequin(pose={"head.nod_down_ip": 1})
    with pytest.raises(PoseError, match="did you mean sit"):
        Mannequin(pose="sat")


def test_adjust_goes_on_top_of_a_pose():
    figure = Mannequin(pose="sit", adjust={"head.turn_left_right": 25})
    assert figure.values()["head.turn_left_right"] == 25
    assert figure.values()["left_upper_leg.front_back"] == POSES["sit"]["left_upper_leg.front_back"]


def test_curled_closes_within_range():
    Mannequin(pose=curled(1.0))
    assert Mannequin(pose=curled(1.0)).frames() != Mannequin(pose=curled(0.0)).frames()


def set_with_marks() -> Location:
    location = Location("marks")
    location.add("stock.box", size=(8, 0.1, 8), at=(0, -0.05, 0), material="stock.concrete")
    location.add("stock.box", size=(8, 4, 0.2), at=(0, 2, 3), material="stock.concrete")
    location.mark("a", (-1, 0, 0), facing=90).mark("b", (1, 0, 0), facing=180)
    location.rig("stock.interior")
    location.shot("front", (0, 1.2, -5), (0, 1, 0), lens=30)
    return location


def test_a_figure_stands_on_a_mark_and_faces_its_way():
    location = set_with_marks()
    figures = location.stand()
    assert [figure.name for figure in figures] == ["a", "b"]
    world = figures[0].transform.then(figures[0].frames()["head"])
    assert world.position.x == pytest.approx(-1) and (world.apply((0, 0, 1)) - world.position).x > 0.9
    assert isinstance(figures[1], Mannequin)


def test_stand_names_only_marks_that_exist():
    with pytest.raises(CatalogError, match="no mark 'c'"):
        set_with_marks().stand("c")


def test_a_figure_does_not_take_its_own_mark():
    location = set_with_marks()
    location.stand(pose="sit")
    assert location.validate() == []


def test_a_figure_can_be_left_out_of_a_look():
    location = set_with_marks()
    location.stand(looks=("stock.wireframe",))
    drawn = SceneCompiler().compile(location, "front")
    assert not [node for node in drawn.iter() if node.xml_name == "object3D" and "left_hand" in (node.id or "").replace("-", "_")]
    assert all(leaf.item.drawn_in("stock.wireframe") for leaf in location.solids())


def test_a_figure_compiles_clean_in_a_blueprint():
    built = Blueprint({"name": "plain", "nodes": [{"use": "stock.mannequin", "pose": "walk", "at": [0, 0, 1],
                                                   "adjust": {"head.turn_left_right": 15}}],
                       "shots": [{"name": "front", "eye": [0, 1.2, -4], "look_at": [0, 1, 0]}]}).build()
    found = check(SceneCompiler().compile(built, "front"), schema=True)
    assert [issue for issue in found if issue.severity == "error"] == []


def test_a_figure_freezes_into_a_catalog_with_its_shape(tmp_path):
    registry = Registry.default()
    catalog = SharedCatalog.create(tmp_path / "shared", "studio")
    figure = Mannequin(pose="sit")
    catalog.publish_prop("figure", figure, registry)
    frozen = Registry.default().use(SharedCatalog.open(tmp_path / "shared")).create("studio.figure")
    leaves, wanted_leaves = list(frozen.walk()), list(figure.walk())
    assert len(leaves) == len(wanted_leaves)
    for made, leaf in zip(leaves, wanted_leaves):
        for found, wanted in zip(made.item.bounds(made.world), leaf.item.bounds(leaf.world)):  # a limb's are exact, a surface's sampled
            assert (found - wanted).length == pytest.approx(0, abs=4e-3)


def rendered(location: Location, shot: str, folder: Path, width: int = 320, height: int = 180) -> list[bytes]:
    path = Renderer().render(location, shot, folder / "shot.png", Shaded(width, height, 1))
    raw = subprocess.run(["ffmpeg", "-loglevel", "error", "-i", str(path), "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                         capture_output=True, check=True).stdout
    return [raw[row * width * 3:(row + 1) * width * 3] for row in range(height)]


def sampled(rows: list[bytes], pixel: tuple[float, float]) -> tuple[int, ...]:
    return tuple(rows[int(pixel[1])][int(pixel[0]) * 3:int(pixel[0]) * 3 + 3])


def test_the_right_shoulder_is_red_and_on_the_right_of_the_body(tmp_path):
    """Seen from the front, a figure's right is on the left of the picture."""
    location = set_with_marks()
    figure = location.add(Mannequin(pose="t", yaw=180, at=(0, 0, 0)))
    frames = figure.frames()
    view = Projection(location.shots["front"], 320, 180)
    rows = rendered(location, "front", tmp_path)
    right = view.pixel(figure.transform.then(frames["right_upper_arm"]).apply((0.0, 0.05, -0.05)))
    left = view.pixel(figure.transform.then(frames["left_upper_arm"]).apply((0.0, 0.05, -0.05)))
    assert right[0] < left[0]
    red, blue = sampled(rows, right), sampled(rows, left)
    assert red[0] > red[2] + 30 and blue[2] > blue[0] + 30


def test_a_figure_is_hidden_by_what_stands_in_front_of_it(tmp_path):
    location = set_with_marks()
    figure = location.add(Mannequin(pose="t", yaw=180))
    location.add("stock.box", size=(0.8, 3, 0.1), at=(0.5, 1.5, -1), material="stock.brick.red")
    spot = figure.transform.then(figure.frames()["left_upper_arm"]).apply((0.0, 0.05, -0.05))
    pixel = Projection(location.shots["front"], 320, 180).pixel(spot)
    found = sampled(rendered(location, "front", tmp_path), pixel)
    assert found[0] > found[2] + 30  # the wall of red brick, and not the blue of the shoulder behind it


def test_the_stock_poses_stay_inside_their_ranges():
    for name in POSES:
        Mannequin(pose=name)
    assert math.isfinite(sum(Mannequin(pose="drive").values().values()))


def head_share(figure) -> float:
    head = next(part for part in figure.build() if part.name == "head")
    low, high = head.bounds(head.transform)
    return (high.y - low.y) / figure.height


@pytest.mark.parametrize("kind", list(KINDS))
@pytest.mark.parametrize("seed", [None, 0, 1, 2, 3, 4])
def test_a_body_stands_as_tall_as_it_says(kind, seed):
    figure = Mannequin(pose="t", kind=kind, seed=seed)
    parts = figure.build()
    assert max(part.bounds(part.transform)[1].y for part in parts) == pytest.approx(figure.height, rel=0.03)


def test_the_kinds_are_the_sizes_they_should_be():
    assert [Mannequin(kind=kind).height for kind in ("man", "woman", "teen", "child", "toddler")] == [1.75, 1.63, 1.668, 1.254, 0.902]


def test_a_younger_body_has_a_bigger_head_for_its_height():
    assert head_share(Mannequin(kind="toddler")) > head_share(Mannequin(kind="child")) > head_share(Mannequin()) * 1.2


def test_a_woman_is_narrower_at_the_shoulder_and_wider_at_the_hip_than_a_man():
    def across(figure, joint):
        return figure.frames()[f"right_{joint}"].position.x * 1.75 / figure.height
    man, woman = Mannequin(pose="t"), Mannequin(pose="t", kind="woman")
    assert across(woman, "upper_arm") < across(man, "upper_arm") and across(woman, "upper_leg") > across(man, "upper_leg")


def test_a_seed_always_gives_the_same_body():
    assert Mannequin(seed=7).frames() == Mannequin(seed=7).frames() and Mannequin(seed=7).height == Mannequin(seed=7).height


def test_seeds_give_different_bodies_and_all_the_kinds():
    assert len({Mannequin(seed=seed).height for seed in range(40)}) == 40
    kinds = [kind for kind in KINDS if not KINDS[kind].measured]
    picked = {min(kinds, key=lambda kind: abs(KINDS[kind].height - Mannequin(seed=seed).height)) for seed in range(40)}
    assert picked == set(kinds)


def test_a_seed_stays_inside_a_kind_it_is_given():
    assert all(1.16 < Mannequin(kind="child", seed=seed).height < 1.35 for seed in range(20))


def test_height_overrides_a_kind():
    assert Mannequin(kind="child", height=1.4).height == 1.4


def test_an_unknown_kind_gets_a_suggestion():
    with pytest.raises(PoseError, match="did you mean woman"):
        Mannequin(kind="women")


@pytest.mark.parametrize("kind", list(KINDS))
def test_every_kind_takes_every_pose(kind):
    for pose in POSES:
        figure = Mannequin(pose=pose, kind=kind, seed=5)
        assert min(part.bounds(part.transform)[0].y for part in figure.build()) == pytest.approx(0, abs=1e-6)


def test_a_body_comes_from_a_blueprint():
    built = Blueprint({"name": "plain", "nodes": [{"use": "stock.mannequin", "kind": "child", "seed": 3}],
                       "shots": [{"name": "front", "eye": [0, 1.2, -4], "look_at": [0, 1, 0]}]}).build()
    assert built.nodes[0].height == Mannequin(kind="child", seed=3).height


@pytest.mark.parametrize("control, low, high", [
    ("left_upper_leg.front_back", -134, 30), ("left_upper_leg.in_out", -30, 45), ("left_upper_leg.twist_in_out", -45, 45),
    ("left_lower_leg.stretch", -142, 2), ("left_foot.up_down", -39, 62), ("left_toes.up_down", -70, 45),
    ("left_lower_arm.stretch", -150, 5), ("left_lower_arm.twist_in_out", -82, 91), ("left_upper_arm.twist_in_out", -90, 90),
    ("left_hand.down_up", -80, 70), ("left_hand.in_out", -20, 45),
    ("left_index_proximal.stretched", -90, 45), ("left_index_intermediate.stretched", -100, 0),
    ("left_index_distal.stretched", -90, 10), ("left_thumb_intermediate.stretched", -50, 0), ("left_thumb_distal.stretched", -80, 0)])
def test_a_range_a_clinical_table_measures_is_its_widest_normal(control, low, high):
    joint, _, name = control.partition(".")
    dof = next(dof for dof in BY_NAME[joint].dofs if dof.name == name)
    assert (dof.low, dof.high) == (low, high)


def test_the_spine_and_neck_share_what_the_tables_give_them():
    def total(joints, name, end):
        return sum(abs(getattr(next(dof for dof in BY_NAME[joint].dofs if dof.name == name), end)) for joint in joints)
    spine, neck = ("spine", "chest", "upper_chest"), ("neck", "head")
    assert [total(spine, "front_back", "low"), total(spine, "front_back", "high")] == [90, 30]  # flexion, extension
    assert [total(spine, "left_right", "high"), total(spine, "twist_left_right", "high")] == [30, 30]
    assert [total(neck, "nod_down_up", "high"), total(neck, "tilt_left_right", "high"), total(neck, "turn_left_right", "high")] == [45, 45, 80]


# More stock poses, each checked for what it is for

def joints(figure) -> dict:
    return {name: figure.transform.then(frame).position for name, frame in figure.frames().items()}


def lowest(figure, *prefixes) -> float:
    return min(part.bounds(part.transform)[0].y for part in figure.build() if part.name.startswith(prefixes))


@pytest.mark.parametrize("pose", ["crouch", "kneel", "sit-floor", "lie", "run", "wave", "arms-crossed", "hands-on-hips",
                                  "phone", "type"])
def test_a_new_pose_is_in_range_on_the_floor_and_untangled(pose):
    for kind in KINDS:
        figure = Mannequin(pose=pose, kind=kind)
        assert lowest(figure, "") == pytest.approx(0, abs=1e-6)
        assert figure.tangled() == [], (kind, figure.tangled())


def test_a_crouch_has_the_hips_low_and_the_heels_down():
    at, stand = joints(Mannequin(pose="crouch")), joints(Mannequin(pose="stand"))
    assert at["hips"].y < stand["hips"].y * 0.55
    figure = Mannequin(pose="crouch")
    assert lowest(figure, "left_foot") < 0.01 and lowest(figure, "right_foot") < 0.01


def test_a_kneeling_figure_is_upright_on_its_knees():
    figure = Mannequin(pose="kneel")
    at = joints(figure)
    assert lowest(figure, "left_lower_leg") < 0.01 and lowest(figure, "right_lower_leg") < 0.01
    assert at["head"].y > figure.height * 0.6


def test_a_figure_sitting_on_the_floor_sits_on_it():
    figure = Mannequin(pose="sit-floor")
    assert lowest(figure, "hips") < 0.06 and joints(figure)["head"].y > figure.height * 0.4  # the thighs are fuller than the pelvis


def test_a_lying_figure_is_flat_on_its_back():
    figure = Mannequin(pose="lie")
    at = joints(figure)
    assert max(part.bounds(part.transform)[1].y for part in figure.build()) < 0.3
    assert abs(at["head"].z - at["left_foot"].z) > figure.height * 0.8
    assert figure.transform.then(figure.frames()["chest"]).basis[1][2] > 0.9  # the chest's front faces up


def test_a_runner_has_a_knee_up_and_the_elbows_bent():
    at = joints(Mannequin(pose="run"))
    assert at["right_lower_leg"].y > at["hips"].y - 0.25
    for side in ("left", "right"):
        assert angle(at[f"{side}_upper_arm"], at[f"{side}_lower_arm"], at[f"{side}_hand"]) < 110


def test_a_wave_has_the_hand_above_the_head():
    at = joints(Mannequin(pose="wave"))
    assert at["right_hand"].y > at["head"].y + 0.05


def test_crossed_arms_fold_each_forearm_across_toward_the_other_elbow():
    at = joints(Mannequin(pose="arms-crossed"))
    for side, other, way in (("left", "right", -1), ("right", "left", 1)):
        assert at[f"{side}_hand"].x * way < -0.02  # the wrist is past the middle
        assert (at[f"{side}_hand"] - at[f"{other}_lower_arm"]).length < 0.24
        assert at[f"{side}_hand"].z > at["chest"].z
        assert abs(at[f"{side}_hand"].y - at[f"{side}_lower_arm"].y) < 0.08  # the forearms lie nearly level
        assert angle(at[f"{side}_upper_arm"], at[f"{side}_lower_arm"], at[f"{side}_hand"]) < 80  # folded
        assert at[f"{side}_lower_arm"].y < at[f"{side}_upper_arm"].y - 0.15  # the elbows hang by the sides


def test_hands_on_hips_rest_beside_them():
    at = joints(Mannequin(pose="hands-on-hips"))
    for side, way in (("left", -1), ("right", 1)):
        assert abs(at[f"{side}_hand"].y - at["hips"].y) < 0.12 and at[f"{side}_hand"].x * way > 0.1
        assert at[f"{side}_lower_arm"].x * way > at[f"{side}_hand"].x * way  # the elbows stick out


def test_a_phone_is_held_to_the_ear():
    figure = Mannequin(pose="phone")
    at = joints(figure)
    ear = at["head"] + Vec3(0.07 * figure.height / 1.75, 0.03, 0)
    assert (at["right_hand"] - ear).length < 0.08


def test_typing_sits_with_the_hands_out_in_front_at_elbow_height():
    pose = POSES["type"]
    at = joints(Mannequin(pose="type"))
    assert pose.sits
    for side in ("left", "right"):
        assert at[f"{side}_hand"].z > at["chest"].z + 0.25 and abs(at[f"{side}_hand"].y - at[f"{side}_lower_arm"].y) < 0.06


# Balance

ONE_LEG = {**POSES["stand"], "right_upper_leg.front_back": -80, "right_lower_leg.stretch": 0, **both({"upper_arm.down_up": -20})}


def inside(point: Vec3, polygon: list) -> bool:
    """Whether a point on the floor is within a convex polygon of points on it, in x and z."""
    turns = [(b.x - a.x) * (point.z - a.z) - (b.z - a.z) * (point.x - a.x) for a, b in zip(polygon, polygon[1:] + polygon[:1])]
    return all(turn >= 0 for turn in turns) or all(turn <= 0 for turn in turns)


def test_the_centre_of_mass_of_a_standing_figure_is_a_little_above_its_middle():
    for kind in KINDS:
        figure = Mannequin(kind=kind)
        centre = figure.centre_of_mass()
        assert abs(centre.x) < 1e-6
        assert figure.frames()["hips"].position.y < centre.y < figure.frames()["chest"].position.y
        if KINDS[kind].measured:  # an adult stands with it at 0.55 to 0.57 of its height (Winter, after Dempster)
            assert 0.53 < centre.y / figure.height < 0.59


def test_the_centre_of_mass_follows_a_raised_arm_and_the_figure_in_the_location():
    figure = Mannequin(adjust={"right_upper_arm.down_up": 0})
    hand = figure.frames()["right_hand"].position
    assert figure.centre_of_mass().x * hand.x > 0
    moved = Mannequin(at=(2, 0, 1), yaw=90)
    assert (moved.centre_of_mass() - moved.transform.apply(Mannequin().centre_of_mass())).length < 1e-9


def test_a_standing_figure_is_carried_by_both_feet_with_its_weight_between_them():
    figure = Mannequin()
    support = figure.support()
    assert len(support) >= 4 and all(abs(point.y) < 1e-9 for point in support)
    frames = figure.frames()
    for side in ("left", "right"):
        assert inside(Vec3(frames[f"{side}_foot"].position.x, 0, frames[f"{side}_foot"].position.z + 0.02), support)
    assert inside(figure.centre_of_mass(), support)
    assert figure.balance() > 0.02
    assert Mannequin(grounded=False).support() == [] and Mannequin(grounded=False).balance() is None


def test_a_balanced_figure_moves_its_hips_over_the_foot_it_stands_on_and_keeps_it_where_it_was():
    raised = Mannequin(pose=ONE_LEG)
    assert raised.balance() < 0  # it would fall over its raised leg
    balanced = replace(raised, balanced=True)
    assert balanced.balance() >= 0.0199
    foot = balanced.frames()["left_foot"]
    assert (foot.position - raised.frames()["left_foot"].position).length < 0.002
    assert balanced.frames()["hips"].position.x < raised.frames()["hips"].position.x - 0.03  # towards the left foot
    assert not balanced.tangled()


def test_balance_leaves_a_steady_or_seated_figure_alone():
    for pose in ("stand", "sit"):
        plain, balanced = Mannequin(pose=pose), Mannequin(pose=pose, balanced=True)
        moved = (balanced.frames()["hips"].position - plain.frames()["hips"].position).length
        assert moved < 1e-9


def test_the_names_of_the_joints_and_their_controls_change_only_with_their_version():
    names = [[joint.name, [dof.name for dof in joint.dofs]] for joint in JOINTS]
    assert (len(names), sum(len(dofs) for _, dofs in names)) == (55, 103)
    assert (JOINTS_VERSION, hashlib.sha256(json.dumps(names).encode()).hexdigest()[:16]) == ("1.0.0", "88629dcb422eb384")
