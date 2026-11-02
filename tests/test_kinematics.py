"""Limbs solved by geometry, hands and feet held in place, eases drawn as curves, in-betweens pushed, and a camera that follows
late and shakes."""
import math
import random
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT)]

from srlocations import Location, Registry, Vec3
from srlocations.camera import Follow, Shake, shaken, steady
from srlocations.figures import angle
from srlocations.geometry import Transform
from srlocations.kinematics import Hold, angles, bend, carrying, middle, nearest
from srlocations.motion import EASES, Clip, MotionError, cubic_bezier
from srlocations.stock.mannequin import PARAMETERS, Mannequin, Pose, PoseError, both


def turning(order, values) -> Transform:
    frame = Transform()
    for turn, value in zip(order, values):
        frame = frame.then(Transform.at(**{turn: value}))
    return frame


def apart(a, b) -> float:
    return max(abs(x - y) for row, other in zip(a, b) for x, y in zip(row, other))


def walking(planted: bool = False) -> tuple[Location, Mannequin]:
    location = Location("walk", Registry.default())
    location.add("stock.box", size=(10, 0.1, 10), at=(0, -0.05, 0), material="stock.concrete")
    figure = location.add(Mannequin(name="walker"))
    location.shot("side", (3, 1.2, 0.3), (0, 0.9, 0.3))
    location.move(figure, 1.0, at=(0, -0.05, 0.12), ease="linear")
    if planted:
        location.plant(figure, "left_foot").plant(figure, "right_foot")
    return location, figure


def world(figure, joint: str) -> Transform:
    return figure.transform.then(figure.frames()[joint])


@pytest.mark.parametrize("order", [("roll", "yaw", "pitch"), ("pitch", "roll", "yaw"), ("yaw", "pitch", "yaw"),
                                   ("pitch", "roll", "yaw"), ("yaw", "pitch", "roll")])
def test_both_angle_sets_give_back_the_rotation(order):
    rng = random.Random(len(order) + hash(order) % 7)
    for _ in range(200):
        made = turning(order, [rng.uniform(-175, 175) for _ in order])
        for found in angles(made.basis, order):
            assert apart(turning(order, found).basis, made.basis) < 1e-9


def test_angles_refuse_a_turn_repeated_next_to_itself():
    with pytest.raises(ValueError):
        angles(Transform().basis, ("yaw", "yaw", "pitch"))


def test_the_law_of_cosines_gives_the_bend():
    assert bend(0.3, 0.3, 0.3) == pytest.approx(120)
    assert bend(0.3, 0.4, 0.5) == pytest.approx(90)
    assert bend(0.3, 0.3, 2.0) < 2  # out of reach, nearly straight, and never quite, so its plane is known


def test_the_middle_joint_goes_toward_the_pole():
    end = Vec3(0.3, 0, 0.1)
    for pole in ((0, -1, 0), (0, 1, 0), (0, 0, -1)):
        knee = middle(end, 0.3, 0.25, pole)
        assert knee.length == pytest.approx(0.3) and (end - knee).length == pytest.approx(0.25)
        assert sum(k * p for k, p in zip(knee, pole)) > 0


def test_carrying_turns_one_pair_onto_another():
    turned = carrying(Vec3(1, 0, 0), Vec3(1, 1, 0), Vec3(0, 0, 1), Vec3(0, 1, 1))
    assert apart(turned, Transform.at(yaw=-90).basis) < 1e-12


def test_an_angle_is_moved_by_whole_turns_to_the_nearest():
    assert nearest(-170, 175) == pytest.approx(190)
    assert nearest(10, -350) == pytest.approx(-350)


@pytest.mark.parametrize("joint, point", [("right_hand", (0.15, 1.1, 0.35)), ("right_hand", (0.05, 1.5, 0.2)),
                                          ("left_hand", (-0.2, 0.9, -0.2)), ("left_foot", (-0.15, 0.3, 0.3)),
                                          ("right_foot", (0.2, 0.1, 0.1))])
def test_a_limb_is_solved_without_searching(joint, point, monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError("searched")
    monkeypatch.setattr(Mannequin, "_searched", refuse)
    figure = Mannequin()
    assert figure.reach_to(joint, point) < 1e-3
    assert all(PARAMETERS[key].low <= value <= PARAMETERS[key].high for key, value in figure.values().items())


def test_a_knee_bends_forward_and_an_elbow_down():
    figure = Mannequin()
    figure.reach_to("left_foot", (-0.15, 0.3, 0.3))
    figure.reach_to("right_hand", (0.3, 1.0, 0.3))
    knee, hip, foot = (world(figure, f"left_{joint}").position for joint in ("lower_leg", "upper_leg", "foot"))
    assert knee.z > max(hip.z, foot.z) and abs(knee.x - hip.x) < 0.05
    elbow, shoulder, hand = (world(figure, f"right_{joint}").position for joint in ("lower_arm", "upper_arm", "hand"))
    assert elbow.y < (shoulder.y + hand.y) / 2


def test_a_pole_picks_where_the_elbow_points():
    elbows = {}
    for name, pole in (("down", (-0.4, 0.4, 0.0)), ("out", (-1.2, 1.1, 0.1))):
        figure = Mannequin()
        figure.reach_to("left_hand", (-0.4, 1.0, 0.3), pole=pole)
        elbows[name] = world(figure, "left_lower_arm").position
        assert tuple(world(figure, "left_hand").position) == pytest.approx((-0.4, 1.0, 0.3), abs=1e-4)
    assert elbows["down"].y < elbows["out"].y and elbows["out"].x < elbows["down"].x


def test_keep_holds_a_hand_turned_as_it_was():
    for limits in (False, True):
        loose, kept = Mannequin(limits=limits), Mannequin(limits=limits)
        before = kept.frames()["right_hand"].basis
        loose.reach_to("right_hand", (0.35, 1.0, 0.25))
        kept.reach_to("right_hand", (0.35, 1.0, 0.25), keep=True)
        assert apart(kept.frames()["right_hand"].basis, before) < apart(loose.frames()["right_hand"].basis, before)
        if not limits:
            assert apart(kept.frames()["right_hand"].basis, before) < 1e-4  # controls are kept to a thousandth of a degree


def test_a_reach_through_the_location_takes_a_pole_and_keep():
    location = Location("reach", Registry.default())
    figure = location.add(Mannequin(name="reacher"))
    assert location.reach("reacher", "right_hand", (0.3, 1.0, 0.3), pole=(0.6, 0.4, 0.0), keep=True) < 0.01


def test_a_finger_is_still_searched_for():
    target = world(Mannequin(adjust={"right_upper_arm.down_up": -30, "right_upper_arm.front_back": -20}), "right_index_distal")
    assert Mannequin().reach_to("right_index_distal", target.position) < 0.01


def test_a_hold_keeps_a_foot_where_it_was_as_the_hips_drop():
    still = Mannequin()
    hold = still.hold("left_foot")
    for at in ((0, 0, 0), (0, -0.05, 0.08), (0.03, -0.1, -0.08)):
        figure = Mannequin(at=at, holds=(hold,))
        foot = world(figure, "left_foot")
        assert tuple(foot.position) == pytest.approx(tuple(hold.at), abs=1e-4)
        assert apart(foot.basis, hold.basis) < 1e-3
    knee = world(Mannequin(at=(0, -0.1, 0), holds=(hold,)), "left_lower_leg").position
    assert knee.z > 0.05  # the knee bends forward to keep the foot down


def test_a_hold_out_of_reach_points_the_leg_at_it():
    hold = Mannequin().hold("left_foot")
    figure = Mannequin(at=(0, 0.3, 0), holds=(hold,))
    foot, hip = world(figure, "left_foot").position, world(figure, "left_upper_leg").position
    assert 0.25 < (foot - hold.at).length < 0.35 and abs(foot.x - hip.x) < 0.01


def test_only_a_hand_or_a_foot_is_held():
    with pytest.raises(PoseError):
        Mannequin(holds=(Hold("head", Vec3(0, 1.6, 0)),))
    assert Mannequin(holds=(Hold("LeftFoot", (-0.09, 0.07, 0)),)).holds[0].joint == "left_foot"


def test_plant_keeps_a_foot_down_until_it_is_lifted():
    location, figure = walking()
    location.plant(figure, "left_foot", 0.0, 0.6)
    location.plant(figure, "right_foot", 0.3)
    start = {side: world(location.at(0).nodes[1], f"{side}_foot").position for side in ("left", "right")}
    for time in (0.1, 0.3, 0.59):
        assert tuple(world(location.at(time).nodes[1], "left_foot").position) == pytest.approx(tuple(start["left"]), abs=1e-4)
    planted = world(location.at(0.3).nodes[1], "right_foot").position
    assert tuple(world(location.at(1.0).nodes[1], "right_foot").position) == pytest.approx(tuple(planted), abs=1e-4)
    assert world(location.at(0.6).nodes[1], "left_foot").position.z > start["left"].z + 0.05  # let go, it goes with the pose


def test_a_planted_film_is_its_stills():
    location, figure = walking()
    location.plant(figure, "left_foot")
    clip = Clip(location, "side", fps=10)
    foot = next(leaf for leaf in clip.placed() if leaf.path.endswith("left_foot"))
    assert foot.track and len({tuple(round(v, 5) for v in leaf.position) for leaf in foot.track}) == 1
    for frame in (0, 4, 10):
        moment = location.at(frame / 10).nodes[1]
        assert foot.track[frame] == next(leaf.world for leaf in moment.walk() if leaf.path.endswith("left_foot"))


def test_plant_refuses_what_has_no_feet_and_backward_time():
    location, figure = walking()
    with pytest.raises(MotionError):
        location.plant(figure, "left_foot", 0.5, 0.2)
    location.nodes.append(location.nodes.pop(0))  # the floor is not a figure
    with pytest.raises(Exception):
        location.plant("floor", "left_foot")


def test_a_cubic_bezier_ease_is_the_css_curve():
    ease = EASES[cubic_bezier(0.25, 0.1, 0.25, 1)]  # CSS "ease"
    assert ease(0) == 0 and ease(1) == 1 and ease(0.5) == pytest.approx(0.8024, abs=1e-3)
    straight = EASES["cubic-bezier(0, 0, 1, 1)"]
    assert all(straight(u) == pytest.approx(u) for u in (0.1, 0.37, 0.9))
    assert max(EASES[cubic_bezier(0.34, 1.56, 0.64, 1)](i / 100) for i in range(101)) > 1  # a handle past 1 overshoots
    assert "cubic-bezier(.4, 0, .2, 1)" in EASES and "cubic-bezier(1, 2)" not in EASES
    with pytest.raises(MotionError):
        cubic_bezier(1.2, 0, 0.5, 1)


def test_move_takes_four_numbers_as_an_ease():
    location, figure = walking()
    location.move(figure, 2.0, ease=(0.42, 0, 0.58, 1), at=(0, 0, 1))
    assert location.motion[id(figure)].fields["at"][-1].ease == "cubic-bezier(0.42, 0, 0.58, 1)"
    middle_z = location.at(1.5).nodes[1].at.z
    assert 0.12 < middle_z < 1 and middle_z == pytest.approx(0.12 + 0.88 * EASES["cubic-bezier(0.42, 0, 0.58, 1)"](0.5))


def test_push_and_relax_move_an_inbetween_from_the_blend():
    before, after = Pose(both({"lower_arm.stretch": 0})), Pose(both({"lower_arm.stretch": -60}))
    between = Pose(both({"lower_arm.stretch": -40}))
    assert between.push(before, after, 0.5)["left_lower_arm.stretch"] == pytest.approx(-45)
    assert between.relax(before, after, 1.0)["left_lower_arm.stretch"] == pytest.approx(-30)
    assert between.push(before, after, 20)["left_lower_arm.stretch"] == PARAMETERS["left_lower_arm.stretch"].low


def test_a_lagging_follow_trails_and_catches_up():
    path = lambda time: Vec3(0, 0, min(time, 1.0))
    assert steady(path, 0.5) == Vec3(0, 0, 0.5)
    late = steady(path, 0.5, lag=0.3)
    assert 0 < late.z < 0.5
    assert steady(path, 3.0, lag=0.3).z == pytest.approx(1.0, abs=1e-3)
    assert steady(path, 0.5, ahead=0.2).z == pytest.approx(0.7)
    assert steady(path, 0.04, dead=0.1).z == 0  # inside the dead zone it does not turn
    assert steady(path, 0.5, lag=0.3) == steady(path, 0.5, lag=0.3)
    with pytest.raises(ValueError):
        Follow("x", lag=-1)


def test_a_location_follows_late():
    location, figure = walking()
    location.follow("side", figure, (0, 0.9, 0), lag=0.4)
    assert location.at(0).shots["side"].look_at.z == pytest.approx(0)
    assert 0 < location.at(0.5).shots["side"].look_at.z < 0.06


def test_a_shake_is_the_same_every_time_and_stays_small():
    shake = Shake(amount=1.0, frequency=2.0, end=3.0, seed=4)
    assert shake.offsets(0) == (0.0, 0.0, Vec3())  # a hand comes in, it does not jump
    samples = [shake.offsets(i / 30) for i in range(90)]
    assert samples == [shake.offsets(i / 30) for i in range(90)]
    assert max(abs(yaw) for yaw, _, _ in samples) <= 1.0 and max(abs(yaw) for yaw, _, _ in samples) > 0.2
    assert Shake(seed=5).offsets(1.0) != Shake(seed=6).offsets(1.0)
    blow = Shake(amount=2.0, decay=0.2, start=1.0)
    assert blow.strength(1.0) == 1 and blow.strength(1.2) == pytest.approx(math.exp(-1)) and blow.strength(0.9) == 0


def test_a_shaken_shot_turns_about_its_eye():
    location, _ = walking()
    location.shake("side", amount=2.0, drift=0.0, seed=1)
    still, moved = location.shots["side"], location.at(0.5).shots["side"]
    assert moved.eye == still.eye and moved.look_at != still.look_at
    assert (moved.look_at - moved.eye).length == pytest.approx((still.look_at - still.eye).length)


def test_a_shake_makes_a_still_location_last():
    location = Location("still", Registry.default())
    location.shot("wide", (0, 1.6, 4), (0, 1, 0))
    with pytest.raises(MotionError):
        location.shake("wide")
    location.shake("wide", decay=0.25)
    assert location.duration() == pytest.approx(0.25 * math.log(100))


def test_an_onion_still_shows_ghosts_either_side():
    location, figure = walking(planted=True)
    still = location.onion(0.5, (0.0, 0.5, 1.0))
    ghosts = [node for node in still.nodes if "ghost" in node.role]
    assert [ghost.label for ghost in ghosts] == ["walker@0", "walker@1"]
    assert all(not ghost.collides and ghost.body == "stock.mannequin.ghost" for ghost in ghosts)
    assert not still.motion and not still.clashes()
    with pytest.raises(MotionError):
        Location("empty", Registry.default()).onion(0, (1,))
