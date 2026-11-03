"""Fidelity: a take against the points it was read from, in time, speed, acceleration, ripple and sliding feet."""
import math
from dataclasses import replace

import pytest

from srlocations.fidelity import HIPS, LIMBS, fidelity, positions
from srlocations.interchange import Take, load_keypoints
from srlocations.stock.mannequin import BY_NAME, Mannequin

FPS = 24


def swing(frames=96, rate=1.5, wobble=0.0, wobbling=5.0, **extra):
    """Arms and an elbow swinging at `rate` Hz, the elbow shaking `wobble` degrees at `wobbling` Hz, and `extra` controls
    as functions of time."""
    poses = []
    for n in range(frames):
        t = n / FPS
        pose = {"left_upper_arm.down_up": -40 + 35 * math.sin(2 * math.pi * rate * t),
                "right_upper_arm.front_back": 30 * math.sin(2 * math.pi * rate * t + 1),
                "left_lower_arm.stretch": -60 + 30 * math.cos(2 * math.pi * rate * t) + wobble * math.sin(2 * math.pi * wobbling * t)}
        pose.update({key: f(t) for key, f in extra.items()})
        poses.append(pose)
    return Take(tuple(poses), FPS)


def points(take):
    return [{name: list(at) for name, at in frame.items()} for frame in positions(take, joints=LIMBS + HIPS)]


def test_take_overrides_figure_adjustments_in_positions():
    key = "left_upper_arm.front_back"
    take = Take(({key: 0}, {key: -60}), FPS)
    figure = Mannequin(kind="child", adjust={key: 30, "head.turn_left_right": 20})
    joints = LIMBS + HIPS + ("left_eye",)
    expected = positions(take, replace(figure, adjust={}), joints)
    found = positions(take, figure, joints)
    assert (expected[1]["left_hand"] - expected[0]["left_hand"]).length > 0.3
    assert found == expected
    assert figure.adjust == {key: 30, "head.turn_left_right": 20}


def test_take_overrides_figure_adjustments_in_fidelity():
    take = swing(9)
    figure = Mannequin(kind="child", adjust={"left_upper_arm.down_up": 30})
    source = positions(take, replace(figure, adjust={}))
    found = fidelity(source, take, figure).by_limb["left_hand"]
    assert found["miss"] == pytest.approx(0, abs=1e-9)
    assert found["speed"] == pytest.approx(1)
    assert figure.adjust == {"left_upper_arm.down_up": 30}


@pytest.mark.parametrize("prefix", ["", "mixamorig:", "mixamorig1"])
def test_aliased_points_compare_as_the_points_that_were_imported(prefix):
    source = positions(swing(9), joints=LIMBS + HIPS + ("left_upper_arm", "right_upper_arm"))
    aliased = [{prefix + BY_NAME[name].known_as["mixamo"]: at for name, at in frame.items()} |
               {"tail": (0, 0, 0)} for frame in source]
    take = load_keypoints(aliased, fps=FPS)
    assert take.unknown == ("tail",)
    expected, found = fidelity(source, take), fidelity(aliased, take)
    assert found.miss == pytest.approx(expected.miss)
    assert found.speed == pytest.approx(expected.speed)
    for name in LIMBS:
        assert found.by_limb[name]["miss"] == pytest.approx(expected.by_limb[name]["miss"])


def test_a_take_against_its_own_joints_keeps_everything():
    take = swing()
    found = fidelity(points(take), take)
    assert found.lag == 0 and found.speed == pytest.approx(1) and found.acceleration == pytest.approx(1)
    assert found.beats == pytest.approx(1) and found.miss == pytest.approx(0, abs=1e-9) and found.ripple == pytest.approx(0, abs=1e-9)


def test_a_take_two_frames_behind_its_points_is_late_by_two_frames():
    take = swing(98)
    late = Take(take.poses[:-2], FPS)
    ahead = points(Take(take.poses[2:], FPS))
    assert fidelity(ahead, late).lag == pytest.approx(2 / FPS)
    assert fidelity(points(late), Take(take.poses[2:], FPS)).lag == pytest.approx(-2 / FPS)


def test_smoothing_a_stop_and_go_flattens_its_acceleration_and_keeps_its_time():
    """Each quarter second the arm stops dead, then goes: what a hit in a dance is, and what a wide filter rounds off."""
    hits = lambda t: 60 * min(1, max(0, 4 * (t % 1)), max(0, 3 - 4 * (t % 1)))  # up in a quarter, held, down, held
    jerky = swing(rate=0.0, **{"left_upper_arm.front_back": hits})
    keys = list(jerky.poses[0])
    smooth = Take(tuple({key: sum(jerky.poses[min(len(jerky.poses) - 1, max(0, n + k))][key] for k in range(-3, 4)) / 7 for key in keys}
                        for n in range(len(jerky.poses))), FPS)
    found = fidelity(points(jerky), smooth)
    assert found.lag == 0 and found.acceleration < 0.8


def test_a_shaking_elbow_is_ripple_and_a_slow_one_is_not():
    """The elbow moves only the hand, and the summary is the median of the limbs, so the hand is where to look."""
    fast = fidelity(points(swing()), swing(wobble=4, wobbling=5)).by_limb["left_hand"]
    slow = fidelity(points(swing()), swing(wobble=4, wobbling=0.5)).by_limb["left_hand"]
    assert fast["ripple"] > 0.002 and slow["ripple"] < fast["ripple"] / 5
    assert fast["miss"] == pytest.approx(slow["miss"], rel=0.5)


def test_feet_that_stay_put_do_not_slide_and_a_widening_stance_does():
    still = swing()
    widening = swing(**{side + "_upper_leg.in_out": (lambda t: 12 + 10 * math.sin(2 * math.pi * t)) for side in ("left", "right")})
    assert fidelity(points(still), still).slide == 0
    assert fidelity(points(widening), widening).slide > 0.05


def test_a_body_tilted_off_its_feet_for_half_its_frames_is_fallen_half_the_time():
    """Both thighs forward and the shins with them: the whole body leans back off its heels, as a plank falls."""
    tilted = lambda t: -30.0 if t >= 1 else 0.0
    take = swing(48, **{side + "_upper_leg.front_back": tilted for side in ("left", "right")})
    assert fidelity(points(take), take).fallen == pytest.approx(0.5)


def test_a_fall_shorter_than_a_step_is_not_counted():
    tilted = lambda t: -30.0 if 1 <= t < 1 + 4 / FPS else 0.0
    take = swing(48, **{side + "_upper_leg.front_back": tilted for side in ("left", "right")})
    assert fidelity(points(take), take).fallen == 0


def test_a_foot_a_few_centimetres_up_still_bears_weight():
    """The floor drop sets the lower foot down and the other floats: balance() leaves it out, and fallen counts it."""
    take = swing(24, **{"left_upper_leg.front_back": lambda t: -8.0})
    assert replace(Mannequin(), pose=take.poses[0], solid=False).balance() < 0
    assert fidelity(points(take), take).fallen == 0


def test_held_is_the_share_of_frames_each_control_was_held_at_its_range():
    take = swing(4)
    held = Take(take.poses, FPS, clamped={"left_lower_arm.stretch": (1, 2)})
    assert fidelity(points(take), held).held == {"left_lower_arm.stretch": 0.5}


def test_points_and_a_take_of_different_lengths_are_refused():
    take = swing(10)
    with pytest.raises(ValueError, match="compare a take with what it was read from"):
        fidelity(points(take)[:-1], take)
