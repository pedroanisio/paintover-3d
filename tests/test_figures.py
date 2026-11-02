"""Figures on a set: how they settle, what they touch, what they see, and what a review or a 2D rig can read from them."""
import json
import random
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT), str(ROOT / "examples")]

from use_cases import office

from srlocations import (Blueprint, Box, CollisionError, Contact, Cutout, Figure, Location, Node, Performer, Projection, Registry,
                         SharedCatalog, Surface, Vec3)
from srlocations.figures import angle
from srlocations.geometry import Transform
from srlocations.stock.mannequin import KINDS, POSES, SURVEY, Build, Mannequin, Pose, PoseError, both


INCH = 0.0254
ADULTS = ("man", "woman")


def bare(*marks) -> Location:
    location = Location("bare", Registry.default())
    location.add("stock.box", size=(10, 0.1, 10), at=(0, -0.05, 0), material="stock.concrete")
    for name, at, facing in marks:
        location.mark(name, at, facing)
    return location


def seated(**given) -> tuple[Location, Mannequin]:
    """A figure on a chair at the origin, which faces -z, so a figure sits on it at yaw 180."""
    location = bare(("sitter", (0, 0, -0.2), 180))
    location.add("stock.chair", at=(0, 0, 0))
    return location, location.stand("sitter", pose="sit", **given)[0]


def codes(location: Location) -> set[str]:
    return {issue.code for issue in location.validate()}


class Plain(Performer):
    def cutout(self, pose=None) -> Cutout:
        return Cutout(Path("nothing.png"), (0, 0, 10, 10))


def test_a_mannequin_is_a_figure_and_a_character_is_not():
    assert isinstance(Mannequin(), Figure) and not isinstance(Plain(), Figure)
    assert Mannequin().moves and Mannequin().collides and not Mannequin(solid=False).collides


def test_the_base_of_a_figure_has_no_rig():
    class Statue(Figure):
        def build(self):
            return [Box()]
        def sight(self):
            return Vec3(0, 1, 0), Vec3(0, 1, 1)
        def values(self):
            return {}
        def take(self, values, sits=False):
            pass
        def aiming(self, pose=None, adjust=None):
            return {}, False

    statue = Statue()
    assert statue.look_at((0, 0, 1)) is statue and statue.posture() == {} and statue.tangled() == () and statue.arm_reach() == 0
    with pytest.raises(NotImplementedError):
        statue.reach_to("left_hand", (0, 0, 0))


def test_angle_is_at_the_joint():
    assert angle(Vec3(1, 0, 0), Vec3(0, 0, 0), Vec3(0, 1, 0)) == pytest.approx(90)


# Poses and kinds

def test_poses_and_kinds_are_in_the_registry():
    registry = Registry.default()
    registry.poses.add("mine", Pose(both({"upper_arm.down_up": -60})))
    registry.kinds.add("tall", Build(2.1))
    location = Location("set", registry).mark("a", (0, 0, 0))
    figure = location.stand("a", pose="mine", kind="tall")[0]
    assert figure.values()["left_upper_arm.down_up"] == -60 and figure.height == 2.1
    assert "sit" in registry.poses and "woman" in registry.kinds


def test_a_figure_without_a_registry_knows_the_stock_poses():
    assert Mannequin(pose="sit").sits and Mannequin(pose="drive").sits and not Mannequin(pose="stand").sits
    with pytest.raises(PoseError, match="did you mean"):
        Mannequin(kind="wman").build_of


def test_a_blueprint_brings_its_poses_kinds_contact_and_figures():
    blueprint = Blueprint({"name": "b", "contact": {"sink": 0.05, "cushions": ["stock.concrete"]},
                           "poses": {"mine": Pose({"head.nod_down_up": 10}).spec()}, "kinds": {"tall": {"height": 2.0}},
                           "marks": [{"name": "a", "at": [0, 0, 0]}], "stand": [{"mark": "a", "pose": "mine", "kind": "tall"}]})
    location = blueprint.build(Registry.default())
    assert location.contact.sink == 0.05 and location.contact.cushions == ["stock.concrete"]
    assert location.figure("a").height == 2.0 and location.figure("a").values()["head.nod_down_up"] == 10


# Settling

def test_settle_all_moves_what_came_in_by_add():
    location = bare()
    location.add("stock.box", size=(1, 1, 1), at=(0, 0.5, 0), material="stock.concrete", name="crate")
    figure = location.add(Mannequin(at=(0.1, 0, 0), name="walker"))
    assert location.clashes(bodies_only=True)
    assert location.settle_all() == [figure]
    assert location.clashes(bodies_only=True) == []


def test_settle_all_starts_from_the_mark():
    location = bare(("a", (0, 0, 0), 90))
    figure = location.stand("a")[0]
    figure.at, figure.yaw = (3, 0, 3), 0
    location.settle_all()
    assert Vec3.of(figure.at) == Vec3(0, 0, 0) and figure.yaw == 90


def test_settle_all_leaves_in_what_no_longer_fits():
    location = bare(("a", (0, 0, 0), 0))
    figure = location.stand("a")[0]
    location.add("stock.box", size=(9.9, 3, 9.9), at=(0, 1.5, 0), material="stock.concrete")
    with pytest.raises(CollisionError):
        location.settle_all()
    assert figure in location.nodes


def test_settle_refuses_and_removes_unless_kept():
    location = bare(("a", (0, 0, 0), 0))
    location.add("stock.box", size=(9.9, 3, 9.9), at=(0, 1.5, 0), material="stock.concrete")
    with pytest.raises(CollisionError):
        location.stand("a")
    assert location.figures() == []
    kept = location.add(Mannequin(name="a"))
    with pytest.raises(CollisionError):
        location.settle(kept, keep=True)
    assert kept in location.nodes


def test_a_figure_off_its_mark_is_reported():
    location = bare(("a", (0.1, 0, 0), 0))
    location.add("stock.box", size=(1, 1, 1), at=(0, 0.5, 0), material="stock.concrete")
    figure = location.stand("a")[0]
    assert (Vec3.of(figure.at) - location.marks["a"].at).length > 0.1
    assert "figure-off-mark" in codes(location)


def test_a_character_goes_with_the_figure_on_its_mark():
    location = bare(("a", (0.1, 0, 0), 0))
    location.add("stock.box", size=(1, 1, 1), at=(0, 0.5, 0), material="stock.concrete")
    actor = location.cast(Plain(), "a")
    figure = location.stand("a")[0]
    assert Vec3.of(actor.at) == Vec3.of(figure.at)
    assert "cast-off-figure" not in codes(location)


def test_a_character_cast_after_a_figure_stands_where_it_settled():
    location = bare(("a", (0.1, 0, 0), 0))
    location.add("stock.box", size=(1, 1, 1), at=(0, 0.5, 0), material="stock.concrete")
    figure = location.stand("a")[0]
    assert Vec3.of(location.cast(Plain(), "a").at) == Vec3.of(figure.at) == location.standing("a")


def test_a_character_left_behind_is_reported():
    location = bare(("a", (0, 0, 0), 0))
    actor = location.cast(Plain(), "a")
    location.stand("a")
    actor.at = (2, 0, 0)
    assert "cast-off-figure" in codes(location)


# Contact

def test_a_figure_sits_on_a_chair_and_leans_on_its_back():
    location, figure = seated()
    assert location.seat_of(figure) is not None and location.clashes() == []
    assert min(location.gap(figure, joint, (0, -1, 0)) for joint in figure.footing()) <= Contact().rest
    assert location.gap(figure, "chest", (0, 0, 1)) <= Contact().rest


def test_a_seated_figure_of_every_kind_is_clean_on_a_chair():
    for kind in ("man", "woman", "teen", "man-95th", "woman-5th"):
        location, figure = seated(kind=kind)
        assert location.clashes() == [], kind
        assert list(figure.tangled()) == [], kind


def test_a_cushion_gives_a_little_and_a_firm_seat_does_not():
    firm, soft = bare(), bare()
    firm.add("stock.box", size=(1, 0.4, 1), at=(0, 0.2, 0), material="stock.concrete")
    soft.add("stock.box", size=(1, 0.4, 1), at=(0, 0.2, 0), material="stock.concrete", role="soft")
    for location in (firm, soft):
        location.add(Mannequin(pose="stand", at=(0, 0.38, 0), grounded=True, name="on"))
    assert firm.clashes(bodies_only=True)
    assert soft.clashes(bodies_only=True) == []


def test_contact_is_set_per_location_and_cushions_match_any_version():
    assert Contact(cushions=("studio.leather",)).soft(type("Leaf", (), {"roles": (), "item": Box(material="studio.leather@3")})())
    assert not Contact().soft(type("Leaf", (), {"roles": (), "item": Box(material="studio.leather@3")})())
    assert Contact().soft(type("Leaf", (), {"roles": ("soft",), "item": Box()})())
    location = bare()
    location.add("stock.box", size=(1, 0.4, 1), at=(0, 0.2, 0), material="stock.concrete")
    location.add(Mannequin(at=(0, 0.38, 0), name="on"))
    assert location.clashes(bodies_only=True)
    location.contact = Contact(cushions=("stock.concrete",))
    assert location.clashes(bodies_only=True) == []


def test_a_figure_above_its_seat_is_not_resting():
    location, figure = seated()
    assert "figure-not-resting" not in codes(location)
    figure.at = Vec3.of(figure.at) + Vec3(0, 0.1, 0)
    assert "figure-not-resting" in codes(location)


def test_a_figure_clear_of_the_backrest_is_reported():
    location, figure = seated()
    figure.at = Vec3.of(figure.at) + Vec3(0, 0, -0.1)
    assert any("backrest" in issue.message for issue in location.validate() if issue.code == "figure-not-resting")


def test_a_standing_figure_in_the_air_is_not_resting():
    location = bare()
    location.add(Mannequin(at=(0, 0.2, 0), name="up"))
    assert "figure-not-resting" in codes(location)


def test_a_figure_that_is_not_solid_is_left_to_its_author():
    location = bare()
    location.add(Mannequin(at=(0, 0.2, 0), solid=False, name="ghost"))
    assert not {"figure-not-resting", "figure-off-mark", "figure-tangled"} & codes(location)


# Faults

def test_each_limb_at_fault_is_named():
    location = bare()
    location.add("stock.box", size=(2, 0.1, 2), at=(0, 1.0, 0), material="stock.concrete", name="plate")
    figure = location.add(Mannequin(solid=False, name="through"))
    faults = location.faults(figure)
    assert len(location.clashes()) == 0  # it is not solid, so only a review asks
    names = [clash.first.rpartition("/")[2].partition(".")[0] for clash in faults]
    assert len(names) >= 3 and len(names) == len(set(names))  # a joint's ball counts with its bone


def test_a_limb_inside_a_closed_surface_is_buried():
    ball = Surface(x="0.6*sin(v)*cos(u)", y="0.6*cos(v)", z="0.6*sin(v)*sin(u)", u=(0, 360), v=(0, 180), closed=(True, False), material="stock.concrete")
    assert ball.encloses(Vec3(0, 0, 0), Transform()) and not ball.encloses(Vec3(0, 2, 0), Transform())
    location = bare()
    location.add(ball, at=(0, 1.2, 0))
    figure = location.add(Mannequin(solid=False, name="in"))
    assert any(clash.buried for clash in location.faults(figure))


def test_a_hollow_or_open_surface_holds_nothing():
    open_ = Surface(x="0.6*sin(v)*cos(u)", y="0.6*cos(v)", z="0.6*sin(v)*sin(u)", u=(0, 360), v=(0, 180), material="stock.concrete")
    assert not open_.encloses(Vec3(0, 0, 0), Transform())
    closed = Surface(x="0.6*sin(v)*cos(u)", y="0.6*cos(v)", z="0.6*sin(v)*sin(u)", u=(0, 360), v=(0, 180), closed=(True, False), material="stock.concrete")
    closed.hollow = True
    assert not closed.encloses(Vec3(0, 0, 0), Transform())


@pytest.mark.parametrize("pose", [name for name in POSES])
@pytest.mark.parametrize("kind", ["man", "woman", "child", "man-95th", "woman-5th"])
def test_no_stock_pose_is_tangled(pose, kind):
    assert list(Mannequin(pose=pose, kind=kind).tangled()) == []


def test_a_sit_is_clean_across_seeds():
    for seed in range(12):
        assert list(Mannequin(pose="sit", seed=seed).tangled()) == [], seed


def test_a_figure_through_itself_is_a_warning_and_not_a_refusal():
    location = bare(("a", (0, 0, 0), 0))
    location.stand("a", pose="sit", adjust=both({"upper_arm.down_up": -100, "upper_arm.front_back": 10, "lower_arm.stretch": -80,
                                                 "lower_arm.twist_in_out": -20, "hand.down_up": -20}))
    assert list(location.figure("a").tangled())
    found = [issue for issue in location.validate() if issue.code == "figure-tangled"]
    assert found and all(issue.severity == "warning" for issue in found)


# Pose

def test_a_mirror_swaps_the_sides():
    pose = Pose({"left_upper_arm.down_up": -30, "right_upper_leg.front_back": 10, "head.turn_left_right": 20, "head.nod_down_up": 5})
    flipped = pose.mirror()
    assert flipped["right_upper_arm.down_up"] == -30 and flipped["left_upper_leg.front_back"] == 10
    assert flipped["head.turn_left_right"] == -20 and flipped["head.nod_down_up"] == 5
    assert dict(flipped.mirror()) == dict(pose)


def test_a_mirrored_figure_is_the_mirror_image():
    pose = POSES["point"]
    plain, flipped = Mannequin(pose=pose).frames(), Mannequin(pose=pose.mirror()).frames()
    for side, other in (("left", "right"), ("right", "left")):
        a, b = plain[f"{side}_hand"].position, flipped[f"{other}_hand"].position
        assert (a.x, a.y, a.z) == pytest.approx((-b.x, b.y, b.z), abs=1e-6)


def test_a_blend_goes_control_by_control():
    a, b = Pose({"head.nod_down_up": 10}), Pose({"head.nod_down_up": 30, "head.turn_left_right": 20}, sits=True)
    assert dict(a.blend(b, 0.5)) == {"head.nod_down_up": 20, "head.turn_left_right": 10}
    assert dict(a.blend(b, 0)) == {"head.nod_down_up": 10, "head.turn_left_right": 0} and not a.blend(b, 0.25).sits and a.blend(b, 1).sits


def test_a_pose_is_json():
    pose = POSES["sit"]
    again = Pose.from_spec(json.loads(json.dumps(pose.spec())))
    assert dict(again) == dict(pose) and again.sits


def test_a_pose_stands_in_for_a_mapping_of_parameters():
    assert dict(Mannequin(pose=dict(POSES["sit"])).values()) == dict(Mannequin(pose="sit").values())


# Moving a figure on a set

def test_repose_arrives_when_nothing_is_in_the_way():
    location = bare(("a", (0, 0, 0), 0))
    location.stand("a")
    assert location.repose("a", "walk") == 1
    wanted = Mannequin(pose="walk").values()
    assert {key: value for key, value in location.figure("a").values().items() if value} == {key: value for key, value in wanted.items() if value}


def test_repose_stops_where_the_set_stops_it():
    location = bare(("a", (0, 0, 0), 0))
    location.add("stock.box", size=(1, 3, 0.2), at=(0, 1.5, 0.45), material="stock.concrete")
    figure = location.stand("a")[0]
    share = location.repose("a", "point")
    assert 0 <= share < 1 and location.clashes() == []
    assert figure.values() != Mannequin(pose="point").values()


def test_a_figure_that_is_not_solid_goes_straight_through():
    location = bare()
    location.add("stock.box", size=(1, 3, 0.2), at=(0, 1.5, 0.45), material="stock.concrete")
    location.add(Mannequin(solid=False, name="ghost"))
    assert location.repose("ghost", "point") == 1


@pytest.mark.parametrize("joint, point", [("left_hand", (-0.4, 1.0, 0.3)), ("right_hand", (0.3, 1.4, 0.3)), ("left_foot", (-0.1, 0.3, 0.3))])
def test_a_limb_reaches_a_point(joint, point):
    figure = Mannequin(limits=True)
    assert figure.reach_to(joint, point) <= 0.011
    assert (figure.transform.apply(figure.frames()[joint].position) - Vec3.of(point)).length <= 0.011


def test_a_reach_stays_in_the_ranges():
    figure = Mannequin()
    figure.reach_to("left_hand", (-0.4, 1.0, 0.3))
    Mannequin(pose=dict(figure.values()))  # limits hold, or this raises


def test_a_point_out_of_reach_changes_nothing():
    figure = Mannequin()
    before = dict(figure.values())
    with pytest.raises(PoseError):
        figure.reach_to("left_hand", (-3, 1, 0))
    assert dict(figure.values()) == before


def test_only_an_arm_or_a_leg_reaches():
    with pytest.raises(PoseError, match="not on an arm or a leg"):
        Mannequin().reach_to("head", (0, 1, 0))


def test_a_reach_through_the_set_is_refused():
    location = bare(("a", (0, 0, 0), 0))
    location.add("stock.box", size=(1, 3, 0.12), at=(0, 1.5, 0.3), material="stock.concrete")
    figure = location.stand("a")[0]
    before = dict(figure.values())
    with pytest.raises(CollisionError, match="left_hand"):
        location.reach("a", "left_hand", (-0.2, 1.1, 0.45))
    assert dict(figure.values()) == before


def test_a_figure_looks_at_a_point_within_its_neck():
    figure = Mannequin()
    figure.look_at((1, 1.65, 2))
    eye, ahead = figure.sight()
    way = ahead - eye
    assert way.x > 0.1 and way.z > 0


def test_pov_follows_a_figure_that_turns_or_moves():
    location = bare(("a", (0, 0, 0), 0), ("b", (1.5, 0, 2), 180))
    location.stand()
    before = location.pov("a")
    location.look("a", "b")
    after = location.shots["a-pov"]
    assert Vec3.of(after.look_at) != Vec3.of(before.look_at)
    location.figure("a").at = (0.5, 0, 0)
    location.settle(location.figure("a"))
    assert Vec3.of(location.shots["a-pov"].eye).x > Vec3.of(after.eye).x


def test_looking_at_nothing_known_says_so():
    location = bare(("a", (0, 0, 0), 0))
    location.stand("a")
    with pytest.raises(Exception, match="no figure or mark"):
        location.look("a", "nobody")


# Sight lines

def test_a_sight_line_finds_what_is_between():
    location = bare(("a", (0, 0, 0), 0), ("b", (0, 0, 4), 180))
    location.add("stock.box", size=(1, 3, 0.2), at=(0, 1.5, 2), material="stock.concrete", name="wall")
    location.stand()
    assert "wall" in location.sees("a", "b")
    location.nodes = [node for node in location.nodes if node.label != "wall"]
    assert location.sees("a", "b") is None


def test_a_window_does_not_block_a_sight_line():
    location = bare(("a", (0, 0, 0), 0), ("b", (0, 0, 4), 180))
    location.add("stock.box", size=(1, 3, 0.02), at=(0, 1.5, 2), material="stock.concrete", role="window")
    location.stand()
    assert location.sees("a", "b") is None


def test_a_shot_from_a_figure_cannot_be_blocked_by_itself():
    location = bare(("a", (0, 0, 0), 0))
    location.stand("a")
    location.pov("a")
    assert "sight-blocked" not in codes(location)


def test_a_blocked_two_shot_is_reported():
    location = bare(("a", (-0.6, 0, 0), 90), ("b", (0.6, 0, 0), -90))
    location.stand()
    location.frame("stock.two-shot", "a", "b", name="both")
    assert "sight-blocked" not in codes(location)
    location.add("stock.box", size=(4, 3, 0.2), at=(0, 1.5, Vec3.of(location.shots["both"].eye).z / 2), material="stock.concrete")
    assert "sight-blocked" in codes(location)


# Framing and blocking

def test_a_close_up_faces_the_figure_and_fills_the_frame():
    location = bare(("a", (0, 0, 0), 0))
    location.stand("a")
    shot = location.frame("stock.close-up", "a")
    assert shot.name == "a-close-up" and Vec3.of(shot.eye).z > 0.3
    eye = location.figure("a").sight()[0]
    view = Projection(shot, 1920, 1080)
    assert 0 < view.pixel(eye)[1] < 1080


def test_a_two_shot_holds_both_faces():
    location = bare(("a", (-0.6, 0, 0), 90), ("b", (0.6, 0, 0), -90))
    location.stand()
    view = Projection(location.frame("stock.two-shot", "a", "b"), 1920, 1080)
    for name in "ab":
        x, y = view.pixel(location.figure(name).sight()[0])
        assert 0 < x < 1920 and 0 < y < 1080


def test_an_over_the_shoulder_is_behind_the_near_figure_and_sees_the_other():
    location = bare(("a", (0, 0, 0), 0), ("b", (0, 0, 1.5), 180))
    location.stand()
    shot = location.frame("stock.over-the-shoulder", "a", "b")
    assert Vec3.of(shot.eye).z < 0
    x, y = Projection(shot, 1920, 1080).pixel(location.figure("b").sight()[0])
    assert 0 < x < 1920 and 0 < y < 1080


def test_a_framing_is_taken_again_when_a_figure_moves():
    location = bare(("a", (0, 0, 0), 0))
    location.stand("a")
    before = Vec3.of(location.frame("stock.close-up", "a").eye)
    location.figure("a").at = (1, 0, 0)
    location.settle(location.figure("a"))
    assert Vec3.of(location.shots["a-close-up"].eye).x == pytest.approx(before.x + 1)


def test_a_two_figure_framing_needs_two():
    location = bare(("a", (0, 0, 0), 0))
    location.stand("a")
    with pytest.raises(TypeError):
        location.frame("stock.two-shot", "a")


def test_blocking_is_plain_data_for_a_rig():
    location = bare()
    location.mark("a", (0, 0, 0), 30, framing="stock.close-up")
    location.mark("empty", (1, 0, 0), 180)
    location.stand("a", height=1.8)
    location.shot("wide", (0, 1.2, -5), (0, 1, 0), lens=30)
    marks = json.loads(json.dumps(location.blocking("wide", 1280, 720)))
    first, second = marks
    assert first["mark"] == "a" and first["framing"] == "stock.close-up" and first["height"] == 1.8 and first["facing"] == pytest.approx(30)
    assert first["in_frame"] and first["head"][1] < first["feet"][1] and first["scale"] > 0
    assert first["feet"] == pytest.approx(list(Projection(location.shots["wide"], 1280, 720).pixel(Vec3(0, 0, 0))))
    assert second["mark"] == "empty" and second["framing"] == "" and second["height"] == 1.7


def test_blocking_follows_a_settled_figure():
    location = bare(("a", (0.1, 0, 0), 0))
    location.add("stock.box", size=(1, 1, 1), at=(0, 0.5, 0), material="stock.concrete")
    figure = location.stand("a")[0]
    location.shot("wide", (0, 1.2, -5), (0, 1, 0), lens=30)
    assert location.blocking("wide")[0]["at"] == list(Vec3.of(figure.at))


def test_a_mark_behind_the_camera_is_not_in_frame():
    location = bare(("a", (0, 0, 0), 0))
    location.shot("away", (0, 1, 2), (0, 1, 5))
    assert location.blocking("away")[0]["in_frame"] is False


# The catalog keeps what a figure needs

def published(node, tmp_path) -> Node:
    catalog = SharedCatalog.create(tmp_path / "shared", "studio")
    catalog.publish_prop("thing", node, Registry.default())
    return Registry.default().use(SharedCatalog.open(tmp_path / "shared")).create("studio.thing")


def test_a_published_chair_can_still_be_sat_on(tmp_path):
    made = published(Registry.default().create("stock.chair"), tmp_path)
    wanted = list(Registry.default().create("stock.chair").seating())
    found = list(made.seating())
    assert len(found) == len(wanted) == 1
    assert (found[0].at - wanted[0].at).length < 1e-6
    assert (found[0].facing, found[0].height, found[0].depth, found[0].back) == (wanted[0].facing, wanted[0].height, wanted[0].depth, wanted[0].back)
    location = bare(("sitter", (0, 0, -0.2), 180))
    location.add(made, at=(0, 0, 0))
    assert location.seat_of(location.stand("sitter", pose="sit")[0]) is not None


def test_seats_turn_with_a_published_prop(tmp_path):
    made = published(Registry.default().create("stock.chair"), tmp_path)
    made.yaw = 90
    seat = next(iter(made.seating()))
    assert (seat.facing - next(iter(Registry.default().create("stock.chair").seating())).facing - 90) % 360 == pytest.approx(0)


def test_a_prop_without_seats_keeps_its_digest(tmp_path):
    catalog = SharedCatalog.create(tmp_path / "shared", "studio")
    box = Registry.default().create("stock.box", size=(1, 1, 1), material="stock.concrete")
    entry = catalog.publish_prop("crate", box, Registry.default())
    payload = json.loads(next((tmp_path / "shared/props/crate").rglob("*.json")).read_text())
    text = json.dumps(payload)
    assert '"seats"' not in text and '"moves"' not in text


def test_a_published_figure_still_counts_as_a_body(tmp_path):
    made = published(Mannequin(pose="stand"), tmp_path)
    assert made.moves
    assert all(leaf.item.hollow for leaf in made.walk() if isinstance(leaf.item, Surface))


# Survey figures

@pytest.mark.parametrize("sex", ADULTS)
@pytest.mark.parametrize("index, name", list(enumerate(("5th", "50th", "95th"))))
def test_a_standard_figure_measures_what_the_survey_says(sex, index, name):
    measures = Mannequin(kind=f"{sex}-{name}").measures()
    for key, row in SURVEY[sex].items():
        assert measures[key] == pytest.approx(row[index] * INCH, abs=0.003), key


def test_measures_ignore_the_pose_and_the_place():
    assert Mannequin(pose="sit", at=(1, 2, 3), yaw=40).measures() == Mannequin().measures()


def test_a_seed_neither_varies_nor_picks_a_measured_body():
    assert Mannequin(kind="man-95th", seed=3).measures() == Mannequin(kind="man-95th").measures()
    measured = {name for name, build in KINDS.items() if build.measured}
    assert len(measured) == 6
    picks = {random.Random(seed).choice([name for name in KINDS if name not in measured]) for seed in range(200)}
    assert picks == {"man", "woman", "teen", "child", "toddler"}
    for seed in range(50):
        assert Mannequin(seed=seed).build_of.measured is False


def test_seeds_give_the_bodies_they_gave():
    rng = random.Random(7)
    assert Mannequin(seed=7).build_of == KINDS[rng.choice(["man", "woman", "teen", "child", "toddler"])].varied(rng)


# Reports

def test_a_report_gives_numbers_and_no_verdicts():
    location = office(Registry.default())
    location.stand("detective", pose="sit")
    location.stand("client", pose="sit")
    report = location.report()
    first = report.figures[0]
    assert first.name == "detective" and first.height > 1 and 0 < first.headroom <= 1.5 and first.arm_reach > 0.3
    assert set(first.posture) >= {"knee", "elbow", "trunk to thigh"}
    assert first.faults == [] and first.tangled == []
    text = str(report)
    assert "office" in text.lower() and "headroom" in text and "client" in text
    assert "wanted" not in text


def test_a_report_says_what_it_judges_by_a_box():
    location = bare()
    location.add(Mannequin(name="a"))
    assert location.report().figures[0].boxed == []


def test_a_report_covers_a_figure_with_no_mark_and_a_mark_with_no_figure():
    location = bare(("empty", (2, 0, 0), 0))
    location.add(Mannequin(name="a"))
    figure = location.report().figures[0]
    assert figure.off_mark is None and figure.headroom == 1.5 and figure.sight_lines == {"empty": None}


# In motion

def test_a_framing_stays_composed_while_a_figure_moves():
    location = bare(("a", (0, 0, 0), 0))
    figure = location.stand("a")[0]
    location.frame("stock.close-up", "a", name="near")
    location.move(figure, 2, at=(1, 0, 0))
    start, end = location.at(0).shots["near"], location.at(2).shots["near"]
    assert Vec3.of(end.eye).x == pytest.approx(Vec3.of(start.eye).x + 1)


def test_a_figure_that_walks_off_its_mark_is_not_a_fault():
    location = bare(("a", (0, 0, 0), 0))
    figure = location.stand("a")[0]
    location.move(figure, 2, at=(2, 0, 0))
    assert "figure-off-mark" not in codes(location)


def test_a_figure_carried_by_a_moving_mark_is_not_a_fault():
    location = bare(("a", (0, 0, 0), 0))
    location.stand("a")
    location.move("a", 2, at=(2, 0, 0))
    assert "figure-off-mark" not in codes(location)


def test_a_figure_pushed_off_its_mark_is_still_reported_in_a_moving_location():
    location = bare(("a", (0.1, 0, 0), 0), ("b", (3, 0, 0), 0))
    location.add("stock.box", size=(1, 1, 1), at=(0, 0.5, 0), material="stock.concrete")
    location.stand()
    location.move(location.figure("b"), 2, at=(4, 0, 0))
    assert any("'a'" in issue.message or issue.message.startswith("a ") for issue in location.validate() if issue.code == "figure-off-mark")


def test_a_moving_figure_keeps_the_location_s_contact():
    location = bare(("a", (0, 0, 0), 0))
    location.contact = Contact(sink=0.05)
    figure = location.stand("a")[0]
    location.move(figure, 2, at=(2, 0, 0))
    assert location.at(1).contact.sink == 0.05
