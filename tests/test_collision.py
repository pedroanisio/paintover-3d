"""Collision: the shapes themselves, the rules for when an overlap is a fault, and figures that keep out of the furniture."""
import random
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT), str(ROOT / "examples")]

from use_cases import office

from srlocations import Box, CatalogError, CollisionError, Cone, Cylinder, Decal, Location, Registry, Renderer, Sphere, Surface, Vec3
from srlocations.collision import DRESSED, TOUCH, Block, Body, Drum, Egg, Hull, deepest, overlap
from srlocations.geometry import Transform
from srlocations.stock.mannequin import POSES, Mannequin


def hull(solid, at=(0, 0, 0), **turn):
    return solid.hulls(Transform.at(at, **turn))[0]


def bare(*marks) -> Location:
    location = Location("bare")
    location.add("stock.box", size=(10, 0.1, 10), at=(0, -0.05, 0), material="stock.concrete")
    for name, at, facing in marks:
        location.mark(name, at, facing)
    return location


@pytest.mark.parametrize("gap, touching", [(1.01, False), (0.99, True), (0.2, True)])
def test_two_boxes_are_apart_when_some_direction_parts_them(gap, touching):
    assert bool(overlap(hull(Box()), hull(Box(), (gap, 0, 0)))) is touching


def test_the_depth_is_the_shortest_way_out():
    depth, way = overlap(hull(Box()), hull(Box(), (0.9, 0, 0)))
    assert depth == pytest.approx(0.1, abs=1e-6) and way.x == pytest.approx(-1)


def test_a_turned_box_is_not_its_bounding_box():
    diagonal = hull(Box(size=(2, 0.1, 0.1)), yaw=45)
    assert overlap(diagonal, hull(Box(size=(0.2, 0.2, 0.2)), (0.8, 0, 0.8))) is None and overlap(diagonal, hull(Box(), (0.71, 0, -0.71)))


def test_a_shifted_hull_is_tested_where_it_has_moved():
    assert overlap(hull(Box()), hull(Box(), (3, 0, 0))) is None
    assert overlap(hull(Box()), hull(Box(), (3, 0, 0)), Vec3(2.5, 0, 0))


@pytest.mark.parametrize("solid, side, past", [(Sphere(0.5), 0.5, 0.51), (Cylinder(0.5, 2), 0.5, 0.51)])
def test_round_shapes_are_round(solid, side, past):
    corner = hull(Box(size=(0.1, 0.1, 0.1)), (side * 0.72 + 0.05, 0, side * 0.72 + 0.05))
    assert overlap(hull(solid), corner) is None
    assert overlap(hull(solid), hull(Box(size=(0.1, 0.1, 0.1)), (past - 0.06, 0, 0)))


def test_a_cone_narrows_to_its_point():
    assert overlap(hull(Cone(0.5, 1)), hull(Box(size=(0.1, 0.1, 0.1)), (0.4, 0.45, 0))) is None
    assert overlap(hull(Cone(0.5, 1)), hull(Box(size=(0.1, 0.1, 0.1)), (0.4, -0.45, 0)))


def test_an_egg_lying_along_a_thin_panel_clashes_only_where_it_reaches():
    thigh = Egg(Transform.at((0, 0, 0)), (0.5, 0.05, 0.05))
    assert overlap(thigh, hull(Box(size=(0.02, 0.4, 0.4)), (0.45, 0, 0)))
    assert overlap(thigh, hull(Box(size=(0.02, 0.4, 0.4)), (0.52, 0, 0))) is None
    assert overlap(thigh, hull(Box(size=(0.4, 0.02, 0.4)), (0, 0.07, 0))) is None


def test_a_curved_surface_is_tested_by_its_patches():
    bowl = Surface("cos(u) * cos(v)", "sin(v)", "sin(u) * cos(v)", u=(0, 360), v=(-90, 90), closed=(True, False))
    near = lambda at: any(overlap(patch, hull(Box(size=(0.1, 0.1, 0.1)), at)) for patch in bowl.hulls(Transform()))
    assert near((1, 0, 0)) and not near((1.3, 0, 0))


def test_paint_and_a_hollow_model_have_no_body():
    assert Decal().hulls(Transform()) == []


def test_the_parts_of_one_object_do_not_clash():
    location = bare()
    location.add("stock.chair", at=(0, 0, 0))
    assert location.clashes() == []


def test_set_pieces_may_meet_a_little():
    location = bare()
    location.add("stock.box", size=(1, 1, 1), at=(0, 0.5, 0))
    location.add("stock.box", size=(1, 1, 1), at=(1 - DRESSED / 2, 0.5, 0))
    assert location.clashes() == []


def test_set_pieces_sharing_a_volume_are_a_warning():
    location = bare()
    location.add("stock.box", size=(1, 1, 1), at=(0, 0.5, 0))
    location.add("stock.box", size=(1, 1, 1), at=(0.5, 0.5, 0))
    assert [(issue.severity, issue.code) for issue in location.validate() if "overlap" in issue.code] == [("warning", "solids-overlap")]


def test_leaves_give_way_to_a_wall_but_not_to_a_figure():
    location = bare()
    location.add("stock.tree", at=(0, 0, 0))
    location.add("stock.box", size=(1, 8, 8), at=(1.5, 4, 0))
    assert location.clashes() == []
    location.add(Mannequin(at=(0, 0, 0), name="x"))
    assert [clash.moving for clash in location.clashes()] == [True]


def test_a_figure_in_a_set_piece_is_an_error():
    location = bare()
    location.add("stock.box", size=(1, 2, 1), at=(0, 1, 0))
    location.add(Mannequin(at=(0, 0, 0), name="x"))
    assert [issue.severity for issue in location.validate() if issue.code == "body-clash"] == ["error"]


def test_figures_cannot_stand_in_each_other():
    location = bare()
    location.add(Mannequin(at=(0, 0, 0), name="a"))
    location.add(Mannequin(at=(0.1, 0, 0), name="b"))
    assert [clash.moving for clash in location.clashes()] == [True]


def test_a_figure_resting_on_the_floor_is_not_a_clash():
    location = bare()
    location.add(Mannequin(pose="walk", name="x"))
    assert location.clashes() == []


def test_a_figure_can_ask_to_be_let_through():
    location = bare()
    location.add("stock.box", size=(1, 2, 1), at=(0, 1, 0))
    location.add(Mannequin(name="x", solid=False))
    assert location.clashes() == []


def test_a_render_refuses_a_figure_inside_something():
    location = bare()
    location.add("stock.box", size=(1, 2, 1), at=(0, 1, 0))
    location.add(Mannequin(name="x"))
    location.shot("front", (0, 1, -5), (0, 1, 0))
    with pytest.raises(CollisionError, match="inside box"):
        Renderer().compile(location, "front")


def test_a_figure_moves_clear_of_what_is_on_its_mark():
    location = bare(("a", (0, 0, 0), 0))
    location.add("stock.box", size=(1, 2, 1), at=(0.55, 1, 0))
    figure = location.stand("a")[0]
    assert location.clashes() == [] and 0 < Vec3.of(figure.at).length < 0.8


def test_a_figure_with_no_room_is_refused_and_left_out():
    location = bare(("a", (0, 0, 0), 0))
    location.add("stock.box", size=(4, 4, 4), at=(0, 2, 0))
    with pytest.raises(CollisionError, match="no room"):
        location.stand("a")
    assert not any(isinstance(node, Mannequin) for node in location.nodes)


def seated(mark=(0, 0, 0.3), chair=(0, 0, 0), yaw=0.0, **given):
    location = bare(("a", mark, 0))
    location.add("stock.chair", at=chair, yaw=yaw)
    return location, location.stand("a", pose="sit", **given)[0]


@pytest.mark.parametrize("yaw", [0.0, 90.0, 180.0, 270.0])
def test_a_sitting_figure_takes_the_seat_and_faces_out_of_it(yaw):
    location, figure = seated(yaw=yaw)
    assert location.clashes() == []
    hips = figure.transform.then(figure.frames()["hips"]).position
    assert (hips - Vec3(0, hips.y, 0)).length < 0.12
    knee = figure.transform.then(figure.frames()["right_lower_leg"]).position
    ahead = Transform.at((0, 0, 0), yaw).apply((0, 0, -1))
    assert (knee.x - hips.x) * ahead.x + (knee.z - hips.z) * ahead.z > 0.3


def test_a_seated_figure_is_touching_the_seat_with_no_gap():
    location, figure = seated()
    assert location.clashes() == []
    body, chair = Body.of(figure), next(Body.of(node) for node in location.nodes if not node.moves and node.seats())
    assert deepest(body, chair, Vec3(0, -0.012, 0), TOUCH)


def test_a_chair_does_not_seat_two():
    location, figure = seated()
    location.mark("b", (0.1, 0, 0.3))
    other = location.stand("b", pose="stand")[0]
    assert location.clashes() == [] and (Vec3.of(other.at) - Vec3.of(figure.at)).length > 0.3


def test_figures_sit_on_a_sofa_side_by_side():
    location = bare(("a", (-0.5, 0, 0), 0), ("b", (0.5, 0, 0), 0))
    location.add("stock.sofa", width=2.0, at=(0, 0, 0))
    first, second = location.stand("a", "b", pose="sit")
    assert location.clashes() == [] and first.at != second.at


def test_with_no_seat_near_a_figure_sits_where_it_is():
    location = bare(("a", (0, 0, 0), 0))
    assert location.stand("a", pose="sit")[0].at == Vec3(0, 0, 0)


def test_the_office_holds_its_cast():
    room = office(Registry.default())
    room.stand("detective", pose="sit")
    room.stand("client", pose="sit")
    assert room.clashes() == [] and [issue for issue in room.validate() if issue.severity == "error"] == []


def test_the_stock_sets_stay_quiet():
    room = office(Registry.default())
    assert [issue for issue in room.validate() if issue.code == "solids-overlap"] == []


def test_seeing_from_the_eyes_of_a_figure():
    location, figure = seated()
    shot = location.pov(figure)
    assert shot.name == "a-pov" and shot.lens == 24
    head = figure.transform.then(figure.frames()["head"]).position
    assert shot.eye.y > head.y and shot.look_at.z < shot.eye.z  # the chair faces -z


def test_the_view_follows_the_head_and_the_eyes():
    location = bare(("a", (0, 0, 0), 0))
    still = location.stand("a")[0].sight()
    turned = Mannequin(adjust={"head.turn_left_right": 40}).sight()
    glance = Mannequin(adjust={"left_eye.in_out": 15, "right_eye.in_out": 15}).sight()
    assert (turned[1] - turned[0]).x > 0.5 > (still[1] - still[0]).x
    assert (glance[1] - glance[0]).z == pytest.approx(1, abs=0.1)


def test_a_view_is_clear_of_the_head():
    figure = Mannequin()
    eye = figure.sight()[0]
    head = next(part for part in figure.build() if part.name == "head")
    high = head.bounds(head.transform)[1]
    assert eye.z > high.z


def test_a_view_names_a_figure_by_its_name():
    location = bare(("a", (0, 0, 0), 0))
    location.stand("a")
    assert location.pov("a", "seen", 30).lens == 30
    with pytest.raises(CatalogError, match="no figure 'b'; this location has a"):
        location.pov("b")


@pytest.mark.parametrize("kind", ["man", "woman", "teen", "child", "toddler"])
@pytest.mark.parametrize("seed", [None, 1, 2, 3])
def test_every_body_sits_in_a_chair(kind, seed):
    location, figure = seated(kind=kind, seed=seed)
    assert location.clashes() == []
    assert location.pov(figure).eye.y > 0.6


# clashes over a walk: these pin what clashes() finds, and when, so a faster search is shown to find the same

def walked(table=None, floor=False, plants=False, **table_params) -> Location:
    """A figure taking two steps 1.4 m along +z in a second, its feet planted as it goes if `plants`, with a table at
    `table` if one is given."""
    location = Location("walk").mark("a", (0, 0, 0))
    if floor:
        location.add("stock.box", size=(10, 0.1, 10), at=(0, -0.05, 0), material="stock.concrete", name="floor")
    figure = location.stand("a")[0]
    if table is not None:
        location.add("stock.table", at=(table, 0, 0.7), name="table", **table_params)
    location.move(figure, 1.0, ease="linear", at=(0, 0, 1.4))
    location.move(figure, 0.25, pose=dict(POSES["walk"]))
    location.move(figure, 0.75, pose=dict(POSES["walk"].mirror()))
    location.move(figure, 1.0, pose="stand")
    if plants:
        location.plant(figure, "right_foot", 0.05, 0.35)
        location.plant(figure, "left_foot", 0.55, 0.85)
    return location


def found(location, bodies_only=False):
    return [(clash.first, clash.second, round(clash.depth, 6), round(clash.time, 9), clash.moving)
            for clash in location.clashes(bodies_only)]


@pytest.mark.parametrize("floor", [False, True])
def test_a_walk_into_a_table_is_found_where_each_limb_first_meets_it(floor):
    location = walked(table=0.0, floor=floor)
    expected = [("a/left_middle_distal", "table/box", 0.011, 0.0859375, True),
                ("a/left_ring_distal", "table/box", 0.006062, 0.08984375, True),
                ("a/right_upper_leg", "table/box", 0.007834, 0.12109375, True),
                ("a/left_upper_leg", "table/box", 0.221941, 0.3359375, True)]
    assert found(location) == expected and found(location, bodies_only=True) == expected


def test_a_walk_with_planted_feet_into_a_table_is_found_too():
    assert found(walked(table=0.0, plants=True)) == [("a/left_index_distal", "table/box", 0.018208, 0.08125, True),
                                                      ("a/left_middle_distal", "table/box", 0.02908, 0.0875, True),
                                                      ("a/left_ring_distal", "table/box", 0.027423, 0.09375, True),
                                                      ("a/right_upper_leg", "table/box", 0.011396, 0.1875, True),
                                                      ("a/left_upper_leg", "table/box", 0.024685, 0.2, True)]


def test_a_hand_that_grazes_a_table_in_passing_is_found_once():
    assert found(walked(table=1.0, height=0.73)) == [("a/right_middle_distal", "table/box", 0.006325, 0.3046875, True)]


@pytest.mark.parametrize("floor, plants", [(False, False), (True, True)])
def test_a_walk_past_a_table_or_over_a_floor_is_clear(floor, plants):
    assert found(walked(table=1.0, height=0.7, floor=floor, plants=plants)) == []


def solves(monkeypatch) -> list:
    """Each figure whose joints are worked out from here on: a figure solves once, the first time it is asked."""
    asked, frames = [], Mannequin.frames
    def counted(figure):
        if not any(figure is seen for seen in asked):
            asked.append(figure)
        return frames(figure)
    monkeypatch.setattr(Mannequin, "frames", counted)
    return asked


def test_a_moving_figure_is_solved_once_for_each_instant(monkeypatch):
    """The figure is the costly part of a check over time, and a shot from its eyes needs no second solve to find a clash."""
    location = walked(table=1.0, height=0.73)
    location.pov("a")
    location.frame("stock.close-up", "a")
    instants = location.instants()
    asked = solves(monkeypatch)
    location.clashes()
    assert len(asked) == len(instants)


def test_a_figure_with_nothing_to_meet_is_not_solved(monkeypatch):
    location = walked()
    asked = solves(monkeypatch)
    assert location.clashes() == [] and asked == []


def test_a_figure_that_passes_through_on_purpose_is_not_solved(monkeypatch):
    """Through a table and over a floor: solid=False means nothing it does is a clash, so there is nothing to look between keys for."""
    location = walked(table=0.0, floor=True)
    location.figure("a").solid = False
    asked = solves(monkeypatch)
    assert location.clashes(bodies_only=True) == [] and location.clashes() == [] and asked == []


def test_a_figure_made_solid_by_a_key_is_still_checked():
    location = walked(table=0.0, floor=True)
    figure = location.figure("a")
    figure.solid = False
    location.move(figure, 0.5, ease="hold", solid=True)
    found = location.clashes(bodies_only=True)
    assert found and all(clash.second.startswith("table/") and clash.time >= 0.5 for clash in found)


def test_a_hull_finds_its_box_as_reach_does_to_the_last_bit():
    """Every part of a moving figure is boxed at every instant, so the shapes work theirs out directly, and must agree."""
    shuffled = random.Random(7)
    pick = lambda: shuffled.choice([0, 0.0, -0.0, 90, -180, shuffled.uniform(-360, 360)])
    for _ in range(3000):
        world = Transform.at(tuple(shuffled.choice([0.0, -0.0, shuffled.uniform(-5, 5)]) for _ in range(3)),
                             yaw=pick(), pitch=pick(), roll=pick())
        sizes = [shuffled.choice([0.0, shuffled.uniform(0.001, 2)]) for _ in range(3)]
        for shape in (Block(world, Vec3(*sizes)), Egg(world, sizes), Drum(world, sizes[0], sizes[1])):
            assert repr(shape.box()) == repr(Hull.box(shape))
