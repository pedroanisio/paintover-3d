"""Things that move. The rule to hold to is that a frame of a moving shot is a still of that moment, so most of these render
both and compare them."""
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT), str(ROOT / "tests")]

from test_looks import deep, errors, solid_png

from srlocations import (Box, Clip, Cylinder, Disc, Flat, Group, Ink, Key, Location, Look, MotionError, Point, Prefab,
                         Registry, Renderer, Shaded, Solid, Styled, Vec3, Wireframe, portable)
from srlocations.collision import CollisionError
from sr_core.scene import Scene

from srlocations.compiler import Projection
from srlocations.looks import SHADERS, Stage
from srlocations.motion import blend, value_at
from srlocations.stock.looks import ink_toon
from srlocations.stock.mannequin import Mannequin
from srlocations.stock.prefabs import Room, window

W, H, FPS = 240, 135, 10
SMALL = Shaded(W, H, 1, fps=FPS)
TOON = Styled(ink_toon(), W, H, 1, fps=FPS)
WIRE = Wireframe(W, H, fps=FPS)


def rgb(path) -> bytes:
    return subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                          capture_output=True, check=True).stdout


def room(**walls) -> Location:
    location = Location("room")
    location.add(Room(6, 5, north=[window(0)], **walls))
    location.add("stock.sofa", at=(0, 0, 1.5), yaw=180)
    location.rig("stock.interior")
    location.shot("push", (-2, 1.5, -2), (0, 0.8, 1), lens=24)
    return location


def differing(renderer, location, shot, mode, frames, folder) -> dict[int, int]:
    """How many channel values differ at all between a moving document's frames and stills of those moments."""
    scene = renderer.compile(location, shot, mode)
    found = {}
    for frame in frames:
        moving = rgb(renderer.still(scene, folder / f"moving-{frame}.png", frame))
        still = rgb(renderer.frame(location, shot, folder / f"still-{frame}.png", frame / FPS, mode))
        assert len(moving) == len(still)
        found[frame] = sum(a != b for a, b in zip(moving, still))
    return found


# keys

def test_a_field_blends_by_its_ease():
    keys = [Key(0, 0.0), Key(2, 10.0, "linear")]
    assert value_at(keys, 1) == 5
    assert value_at(keys, -1) == 0 and value_at(keys, 3) == 10
    assert value_at([Key(0, 0.0), Key(2, 10.0, "ease-in-out")], 0.5) < 2.5
    assert value_at([Key(0, 0.0), Key(2, 10.0, "ease-in")], 1) == 2.5
    assert value_at([Key(0, 0.0), Key(2, 10.0, "ease-out")], 1) == 7.5
    assert value_at([Key(0, 0.0), Key(2, 10.0, "hold")], 1.9) == 0


def test_a_smooth_move_goes_through_a_key_without_stopping():
    keys = [Key(0, 0.0), Key(1, 1.0, "smooth"), Key(2, 2.0, "smooth")]
    just_before, just_after = value_at(keys, 0.99), value_at(keys, 1.01)
    assert value_at(keys, 1) == 1
    assert (just_after - just_before) / 0.02 == pytest.approx(1.0, abs=0.05)
    assert value_at(keys, 0.01) < 0.01  # and it starts from rest


def test_a_smooth_position_is_a_position():
    keys = [Key(0, Vec3()), Key(1, Vec3(1, 0, 2), "smooth"), Key(2, Vec3(2, 0, 0), "smooth")]
    assert value_at(keys, 1) == Vec3(1, 0, 2)
    assert isinstance(value_at(keys, 0.5), Vec3)


def test_a_smooth_move_never_overshoots_its_keys():
    keys = [Key(0, 0.0), Key(1, 1.0, "smooth"), Key(2, 1.0, "smooth"), Key(3, 0.0, "smooth")]
    samples = [value_at(keys, step / 100) for step in range(301)]
    assert min(samples) == 0 and max(samples) == 1
    assert value_at(keys, 1.5) == 1  # a key held is held, not bulged through


def test_a_smooth_pose_runs_each_control_on_its_own_curve():
    keys = [Key(0, {"a": 0.0}), Key(1, {"a": 1.0, "b": 2.0}, "smooth"), Key(2, {"a": 2.0, "b": 2.0}, "smooth")]
    middle = value_at(keys, 1)
    assert middle == {"a": 1.0, "b": 2.0}
    assert (value_at(keys, 1.01)["a"] - value_at(keys, 0.99)["a"]) / 0.02 == pytest.approx(1.0, abs=0.05)
    assert value_at(keys, 1.5)["b"] == 2.0


def test_a_pose_blends_control_by_control():
    assert blend({"a": 0.0, "b": 10.0}, {"a": 10.0}, 0.5) == {"a": 5.0, "b": 5.0}


def test_what_is_not_a_number_changes_when_it_arrives():
    assert blend("oak", "walnut", 0.9) == "oak" and blend("oak", "walnut", 1) == "walnut"
    assert blend(False, True, 0.5) is False


# moving

def test_nothing_moving_compiles_as_a_still():
    location = room()
    assert location.duration("push") == 0
    assert location.at(1.0) is location
    assert not deep(Renderer().compile(location, "push", SMALL), "animate")


def test_a_shot_lasts_until_the_last_thing_in_it_stops():
    location = room().move("push", 2, eye=(0, 1.5, -2))
    assert location.duration("push") == 2
    location.shot("other", (0, 1, -2), (0, 1, 0))
    assert location.duration("other") == 0  # another shot's moves are not in this one
    location.add(Box(size=(1, 1, 1), name="crate"))
    location.move("crate", 3, at=(1, 0, 0))
    assert location.duration("other") == 3 and location.duration("push") == 3


def test_a_moment_is_a_still_location():
    location = room().move("push", 2, eye=(2, 1.5, -2), ease="linear")
    moment = location.at(1)
    assert moment.shots["push"].eye == Vec3(0, 1.5, -2)
    assert moment.motion == {}
    assert location.shots["push"].eye == Vec3(-2, 1.5, -2)  # the location itself stays


def test_a_key_needs_a_time_after_the_start():
    with pytest.raises(MotionError, match="after the start"):
        room().move("push", 0, eye=(0, 1, 0))


def test_a_misspelt_ease_is_refused():
    with pytest.raises(MotionError, match="did you mean ease-in"):
        room().move("push", 1, ease="ease-inn", eye=(0, 1, 0))


def test_a_misspelt_field_is_refused():
    with pytest.raises(MotionError, match="did you mean eye"):
        room().move("push", 1, eyes=(0, 1, 0))


def test_what_is_not_here_is_refused():
    with pytest.raises(MotionError, match="nothing here is called"):
        room().move("ghost", 1, at=(0, 0, 0))


def test_a_name_that_is_a_shot_and_a_mark_is_refused():
    location = room().mark("push", (0, 0, 0))
    with pytest.raises(MotionError, match="a shot and a mark"):
        location.move("push", 1, at=(1, 0, 0))


def test_a_part_of_a_prefab_cannot_move_alone():
    part = Box(size=(1, 1, 1))
    location = room()
    location.add(Group(children=[part]))
    with pytest.raises(MotionError, match="not at the top"):
        location.move(part, 1, at=(1, 0, 0))


def test_no_values_waits():
    location = room().move("push", 1, eye=(1, 1.5, -2)).move("push", 2)
    assert location.at(1.5).shots["push"].eye == Vec3(1, 1.5, -2)
    assert location.duration("push") == 2


def test_a_still_shot_can_be_held_for_a_length():
    location = room().move("push", 2)
    assert location.duration("push") == 2
    assert location.at(1).shots["push"] == location.shots["push"]


def test_a_later_key_replaces_one_at_that_time():
    location = room().move("push", 1, eye=(1, 1, 1)).move("push", 1, eye=(2, 2, 2))
    assert location.at(1).shots["push"].eye == Vec3(2, 2, 2)


def test_fields_keep_their_own_times():
    location = room().move("push", 2, eye=(2, 1.5, -2), ease="linear").move("push", 1, lens=48, ease="linear")
    assert location.at(1).shots["push"].lens == 48
    assert location.at(1).shots["push"].eye == Vec3(0, 1.5, -2)


# the document

def test_keys_land_on_the_exact_time_of_their_frame():
    location = room().move("push", 1, eye=(2, 1.5, -2))
    scene = Renderer().compile(location, "push", Shaded(W, H, 1, fps=3))
    animate = next(a for a in deep(scene, "animate") if a.property == "x")
    assert [float(key.time) for key in animate.find_all("key")] == [0, 1 / 3, 2 / 3, 1]


def test_a_clip_shows_its_last_key():
    location = room().move("push", 1, eye=(2, 1.5, -2))
    assert Clip(location, "push", 10).frames == 11
    assert Renderer().compile(location, "push", SMALL).find_all("project")[0].duration == pytest.approx(1.1)


def test_what_stays_still_carries_no_keys():
    location = room()
    location.add(Box(size=(1, 1, 1), at=(1, 0.5, 0), name="crate"))
    location.move("crate", 1, at=(2, 0.5, 0))
    keyed = [element for element in deep(Renderer().compile(location, "push", SMALL), "object3D") if element.find_all("animate")]
    assert [element.id.split("-")[0] for element in keyed] == ["crate"]
    assert [animate.property for animate in keyed[0].find_all("animate")] == ["x"]


def test_a_moving_document_is_valid_in_every_mode():
    location = room().move("push", 0.3, eye=(2, 1.5, -2))
    location.add(Box(size=(0.5, 0.5, 0.5), at=(1, 0.25, 0), name="crate"))
    location.move("crate", 0.3, yaw=90)
    location.paint("notes", depth=True).disc((0, 1, 2), 0.2, color="#ff0000")
    for mode in (SMALL, TOON, WIRE):
        assert not errors(Renderer().compile(location, "push", mode))


# a frame is a still of that moment

def camera_move() -> Location:
    return room().move("push", 1, eye=(2, 1.5, -2), lens=35)


def test_a_moving_camera_is_exact_when_shaded(tmp_path):
    assert set(differing(Renderer(), camera_move(), "push", SMALL, (0, 3, 7, 10), tmp_path).values()) == {0}


def test_a_moving_camera_is_exact_in_a_look(tmp_path):
    assert set(differing(Renderer(), camera_move(), "push", TOON, (0, 3, 7, 10), tmp_path).values()) == {0}


def test_a_moving_camera_is_exact_as_a_wireframe(tmp_path):
    assert set(differing(Renderer(), camera_move(), "push", WIRE, (0, 3, 7, 10), tmp_path).values()) == {0}


def moving_things() -> Location:
    location = camera_move()
    location.add("stock.table", at=(-1.5, 0, 0), name="table")
    location.mark("host", (1.5, 0, -0.5))
    location.stand("host")
    location.move("table", 1, at=(-1.5, 0, 0.8), yaw=40)
    location.move("host", 1, at=(0.4, 0, -1.0), ease="linear")
    return location


def test_moving_solids_are_exact_when_shaded(tmp_path):
    assert set(differing(Renderer(), moving_things(), "push", SMALL, (3, 7, 10), tmp_path).values()) == {0}


def test_moving_solids_are_exact_as_a_wireframe(tmp_path):
    assert set(differing(Renderer(), moving_things(), "push", WIRE, (3, 7, 10), tmp_path).values()) == {0}


def test_moving_solids_are_exact_in_a_look(tmp_path):
    """Ink keys a surface by where it stood when the shot began, in a clip and in a still of a moment alike."""
    assert set(differing(Renderer(), moving_things(), "push", TOON, (3, 7, 10), tmp_path).values()) == {0}


def test_ink_keys_do_not_change_as_a_solid_turns():
    location = moving_things()
    keys = [[key for _, key in Ink().surfaces(Stage(Scene(version="auto"), None, TOON, moment, "push", Clip(moment, "push", FPS)))]
            for moment in (location, location.at(0.7))]
    assert keys[0] == keys[1]


def test_a_light_goes_with_its_node(tmp_path):
    location = Location("lamp")
    location.add(Box(size=(8, 0.1, 8), at=(0, -0.05, 0)))
    lamp = location.add(Group(children=[Point(intensity=400, at=(0, 1, 0))], at=(-2, 0, 0), name="lamp"))
    location.move(lamp, 1, at=(2, 0, 0), ease="linear")
    location.shot("down", (0, 4, -3), (0, 0, 0), lens=28)
    assert set(differing(Renderer(), location, "down", SMALL, (5, 10), tmp_path).values()) == {0}
    first, last = (rgb(Renderer().frame(location, "down", tmp_path / f"{t}.png", t, SMALL)) for t in (0, 1))
    assert first != last


def test_paint_follows_the_camera(tmp_path):
    location = camera_move()
    location.paint("notes").disc((0, 1, 2), 0.3, color="#ff0000").stroke([(-1, 0.02, 0), (1, 0.02, 0)], color="#00ff00", width=0.05)
    assert set(differing(Renderer(), location, "push", SMALL, (3, 7, 10), tmp_path).values()) == {0}


def test_paint_with_depth_goes_behind_what_moves_in_front(tmp_path):
    location = camera_move()
    location.add(Box(size=(1.5, 2, 0.2), at=(-3, 1, 0.5), name="screen", material="stock.plaster.cream"))
    location.move("screen", 1, at=(0, 1, 0.5))
    location.paint("notes", depth=True).disc((0, 1, 2), 0.4, color="#ff0000")
    assert set(differing(Renderer(), location, "push", SMALL, (5, 10), tmp_path).values()) == {0}


def test_a_multiply_layer_blends_with_the_picture_under_it(tmp_path):
    location = camera_move()
    location.paint("shade", blend="multiply", opacity=0.5).disc((0, 1, 2), 0.5, color="#0000ff")
    assert set(differing(Renderer(), location, "push", SMALL, (5,), tmp_path).values()) == {0}


def test_a_frame_lives_for_one_frame():
    location = camera_move()
    location.paint("notes").disc((0, 1, 2), 0.3, color="#ff0000")
    groups = [g for g in deep(Renderer().compile(location, "push", SMALL), "group") if g.id.startswith("paint-0")]
    assert len(groups) == 11
    assert [(g.start, g.end) for g in groups[:2]] == [(0, 0.1), (0.1, 0.2)]


def test_a_picture_on_every_frame_is_one_asset(tmp_path):
    location = camera_move()
    picture = tmp_path / "sign.png"
    Renderer().render(room(), "push", picture, SMALL)
    location.paint("sign").picture(picture)
    assert len(deep(Renderer().compile(location, "push", SMALL), "image")) == 1


# marks

def test_what_stands_on_a_mark_goes_with_it():
    location = room().mark("host", (1, 0, 0))
    figure = location.stand("host")[0]
    location.move("host", 1, at=(2, 0, 1), ease="linear")
    moment = location.at(0.5)
    assert moment.marks["host"].at == Vec3(1.5, 0, 0.5)
    assert Vec3.of(next(node for node in moment.nodes if node.name == "host").at) == Vec3.of(figure.at) + Vec3(0.5, 0, 0.5)


def test_a_figure_keeps_walking_with_its_mark_while_it_changes_pose():
    location = room().mark("host", (1, 0, 0))
    figure = location.stand("host")[0]
    location.move(figure, 1, pose="walk", ease="linear")
    location.move("host", 1, at=(2, 0, 1), ease="linear")
    moment = next(node for node in location.at(0.5).nodes if node.name == "host")
    assert Vec3.of(moment.at) == Vec3.of(figure.at) + Vec3(0.5, 0, 0.5)
    assert moment.values() != figure.values()


def test_paint_on_a_mark_goes_with_it():
    location = room().mark("host", (1, 0, 0))
    location.paint("ring").disc((1, 0.02, 0), 0.3, mark="host")
    location.move("host", 1, at=(2, 0, 0), ease="linear")
    assert location.at(0.5).paintings[0].items[0].center == Vec3(1.5, 0.02, 0)


def test_paint_on_no_mark_stays():
    location = room().mark("host", (1, 0, 0))
    location.paint("ring").disc((1, 0.02, 0), 0.3)
    location.move("host", 1, at=(2, 0, 0))
    assert location.at(1).paintings[0].items[0].center == (1, 0.02, 0)


def test_a_mark_in_a_blueprint_carries_what_stands_on_it():
    from srlocations.paint import PaintLayer
    location = room().mark("door", (1, 0, 0))
    layer = PaintLayer.from_spec({"name": "x", "items": [{"kind": "standee", "at": "door", "marks": []}]}, spots=location.marks)
    assert layer.items[0].mark == "door"


def test_a_plugin_paint_item_moves_with_no_change(tmp_path):
    from srlocations.paint import PaintItem, curve

    class Tick(PaintItem):
        def draw(self, canvas, node_id):
            x, y = canvas.view.pixel(Vec3(0, 1, 2))
            canvas.shape(node_id, curve([(x - 9, y), (x + 9, y)], smooth=False), stroke="#ff0000", strokeWidth=3)

    location = camera_move()
    location.paint("ticks").add(Tick())
    assert set(differing(Renderer(), location, "push", SMALL, (5,), tmp_path).values()) == {0}


# following

def test_a_shot_can_follow_a_node():
    location = room()
    crate = location.add(Box(size=(1, 1, 1), at=(-2, 0.5, 0), name="crate"))
    location.follow("push", crate, offset=(0, 0.5, 0))
    location.move(crate, 1, at=(2, 0.5, 0), ease="linear")
    assert location.at(0.5).shots["push"].look_at == Vec3(0, 1.0, 0)
    assert location.shots["push"].look_at == Vec3(-2, 1.0, 0)


def test_a_shot_can_follow_a_mark():
    location = room().mark("host", (1, 0, 0)).follow("push", "host", (0, 1, 0))
    location.move("host", 1, at=(2, 0, 0), ease="linear")
    assert location.at(1).shots["push"].look_at == Vec3(2, 1, 0)


def test_following_what_is_not_here_is_refused():
    with pytest.raises(MotionError, match="nothing here is called"):
        room().follow("push", "host")


def test_a_shot_from_a_figure_goes_with_the_figure():
    location = room()
    figure = location.add(Mannequin(at=(0, 0, 0), name="host"))
    shot = location.pov(figure)
    location.move(figure, 1, at=(1, 0, 0), ease="linear")
    assert location.at(1).shots[shot.name].eye.x == pytest.approx(shot.eye.x + 1)


# figures

def test_two_poses_blend_joint_by_joint():
    figure = Mannequin(pose="stand", name="host")
    location = room()
    location.add(figure)
    location.move(figure, 1, pose="walk", ease="linear")
    start, end = figure.values(), Mannequin(pose="walk").values()
    middle = next(node for node in location.at(0.5).nodes if node.name == "host").values()
    moved = max(start, key=lambda name: abs(start[name] - end.get(name, 0)))
    assert middle[moved] == pytest.approx((start[moved] + end.get(moved, 0)) / 2)


def test_adjust_is_part_of_a_pose_key():
    figure = Mannequin(pose="stand", adjust={"head.turn_left_right": 30}, name="host")
    location = room()
    location.add(figure)
    location.move(figure, 1, adjust={"head.turn_left_right": -30}, ease="linear")
    assert next(node for node in location.at(0.5).nodes if node.name == "host").values().get("head.turn_left_right", 0) == pytest.approx(0)


def test_a_misspelt_pose_is_refused_where_it_is_keyed():
    figure = Mannequin(name="host")
    location = room()
    location.add(figure)
    with pytest.raises(Exception, match="no pose"):
        location.move(figure, 1, pose="wlak")


def test_a_figure_keeps_its_parts_between_poses(tmp_path):
    location = room().mark("host", (1, 0, 0))
    location.stand("host")
    location.move(next(node for node in location.nodes if node.name == "host"), 0.3, pose="point", ease="linear")
    assert set(differing(Renderer(), location, "push", SMALL, (3,), tmp_path).values()) == {0}


def test_a_prefab_that_changes_size_is_drawn_in_each_size_for_its_frames(tmp_path):
    location = room()
    location.add("stock.table", width=1.2, name="table")
    location.move("table", 0.3, width=2.0, ease="linear")
    scene = Renderer().compile(location, "push", SMALL)
    tops = [element for element in deep(scene, "object3D") if "table" in element.id and element.attributes().get("end")]
    assert len({element.attributes()["start"] for element in tops}) == 4
    for mode in (SMALL, TOON, WIRE):
        assert set(differing(Renderer(), location, "push", mode, (1, 3), tmp_path).values()) == {0}


@dataclass
class Stack(Prefab):
    """As many crates as its height holds, so a key on its height changes how many parts it has."""
    height: float = 0.5

    def build(self):
        return [Box(size=(0.4, 0.28, 0.4), at=(0, 0.15 + 0.3 * level, 0), material="stock.wood.oak", name=f"crate{level}")
                for level in range(int(self.height / 0.3) + 1)]


def test_a_prefab_that_changes_how_many_parts_it_has_is_drawn_part_by_part(tmp_path):
    location = room()
    location.add(Stack(at=(1, 0, 0), name="stack"))
    location.move("stack", 1, height=1.4, yaw=30, ease="linear")  # three crates from frame 2 to 4, turning
    assert len(location.at(1).nodes[-1].build()) > len(location.nodes[-1].build())
    for mode in (SMALL, TOON, WIRE):
        assert set(differing(Renderer(), location, "push", mode, (0, 4, 10), tmp_path).values()) == {0}


@dataclass
class Lamps(Prefab):
    count: float = 1

    def build(self):
        return [Point(at=(level, 2, 0)) for level in range(int(self.count))]


def test_a_node_that_changes_how_many_lights_it_has_is_refused():
    location = room()
    location.add(Lamps(name="lamps"))
    location.move("lamps", 0.3, count=3)
    with pytest.raises(MotionError, match="lights"):
        Renderer().compile(location, "push", SMALL)


# checks

def test_a_body_that_walks_into_something_is_refused_with_the_time():
    location = room()
    location.add(Box(size=(1, 2, 1), at=(2, 1, 0), name="block"))
    location.add(Mannequin(at=(-1, 0, 0), name="host"))
    location.move("host", 2, at=(2, 0, 0), ease="linear")
    with pytest.raises(CollisionError, match=r"inside .*block.* at \d"):
        Renderer().compile(location, "push", SMALL)


def test_a_renderer_without_collisions_draws_a_body_inside_something(monkeypatch):
    location = room()
    location.add(Box(size=(1, 2, 1), at=(2, 1, 0), name="block"))
    location.add(Mannequin(at=(-1, 0, 0), name="host"))
    location.move("host", 2, at=(2, 0, 0), ease="linear")
    monkeypatch.setattr(Location, "clashes", lambda *_, **__: pytest.fail("looked for a clash"))
    assert Renderer(collisions=False).compile(location, "push", SMALL)


def test_a_body_cannot_pass_through_a_thin_wall_between_keys():
    """Its keys stand either side of the wall, so only looking between them finds it."""
    location = room()
    location.add(Box(size=(0.05, 2, 3), at=(0, 1, 0), name="screen"))
    location.add(Mannequin(at=(-1, 0, 0), name="host"))
    location.move("host", 0.2, at=(1, 0, 0), ease="linear")
    assert len(location.instants()) > 2
    with pytest.raises(CollisionError, match="screen"):
        Renderer().compile(location, "push", SMALL)
    assert any(issue.code == "body-clash" for issue in location.validate())


def test_what_stands_still_is_checked_once():
    location = room()
    location.add(Box(size=(1, 1, 1), at=(-2, 0.5, 1), name="a"))
    location.add(Box(size=(1, 1, 1), at=(-1.6, 0.5, 1), name="b"))
    location.move("push", 1, eye=(2, 1.5, -2))
    location.add(Mannequin(at=(1, 0, -1), name="host"))
    location.move("host", 1, at=(1.5, 0, -1))
    assert len([issue for issue in location.validate() if issue.code == "solids-overlap"]) == 1


def test_a_body_that_passes_clear_is_let_through():
    location = room().mark("host", (-1, 0, -1))
    location.stand("host")
    location.move("host", 1, at=(1, 0, -1), ease="linear")
    assert Renderer().compile(location, "push", SMALL)


def test_a_camera_that_ends_inside_something_is_found():
    location = room()
    location.add(Box(size=(1, 2, 1), at=(2, 1, -2), name="block"))
    location.move("push", 1, eye=(2, 1, -2))
    found = [issue for issue in location.validate() if issue.code == "shot-inside-solid"]
    assert len(found) == 1 and found[0].message.endswith("at 1 s")


def test_a_fault_is_told_once():
    location = room()
    location.add(Box(size=(0.1, 0.1, 0.1), at=(-2, 1.5, -2), name="block"))
    location.move("push", 2, eye=(-2, 1.5, -2))
    assert len([issue for issue in location.validate() if issue.code == "shot-inside-solid"]) == 1


# what looks do with time

def test_cel_measures_the_middle_of_a_shot():
    scene = Renderer().compile(camera_move(), "push", Styled(ink_toon(cut="auto"), W, H, 1, fps=FPS))
    assert not errors(scene)


def test_rings_and_faces_go_with_a_solid():
    location = room()
    location.add(Cylinder(radius=0.3, height=1, at=(0, 0.5, 0), name="drum"))
    location.move("drum", 0.3, at=(1, 0.5, 0))
    look = Look([Flat(), Ink(width=2, rings=0.2)], name="rings")
    scene = Renderer().compile(location, "push", Styled(look, W, H, 1, fps=FPS))
    drums = [element for element in deep(scene, "object3D") if "drum" in element.id]
    assert len(drums) > 3 and all(element.find_all("animate") for element in drums)


def test_a_tiled_texture_stays_on_a_moving_solid(tmp_path):
    from srlocations import Texture, Lit
    texture = tmp_path / "t.png"
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "testsrc=s=64x64", "-frames:v", "1", str(texture)], check=True)
    location = room()
    location.add(Box(size=(1, 1, 1), at=(0, 0.5, 0), name="crate", material="stock.plaster.cream"))
    location.move("crate", 0.3, at=(1, 0.5, 0))
    look = Look([Lit()], name="tiled", textures={"stock.plaster.cream": Texture(texture, tile=0.5)})
    scene = Renderer().compile(location, "push", Styled(look, W, H, 1, fps=FPS))
    crates = [element for element in deep(scene, "object3D") if "crate" in element.id]
    assert crates and all(element.find_all("animate") for element in crates)


# rendering

def test_a_clip_is_a_film_with_every_frame(tmp_path):
    location = room().move("push", 0.5, eye=(2, 1.5, -2))
    film = Renderer().clip(location, "push", tmp_path / "out" / "push.mp4", Shaded(W, 136, 1, fps=FPS))
    count = subprocess.run(["ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0", "-show_entries",
                            "stream=nb_read_frames", "-of", "csv=p=0", str(film)], capture_output=True, text=True).stdout
    assert int(count.strip().rstrip(",")) == 6


def test_a_clip_of_nothing_moving_is_refused(tmp_path):
    with pytest.raises(MotionError, match="render\\(\\) draws a still"):
        Renderer().clip(room(), "push", tmp_path / "x.mp4", SMALL)


def test_a_moving_shot_packages_and_renders_elsewhere(tmp_path):
    location = room().move("push", 0.5, eye=(2, 1.5, -2))
    location.paint("notes").disc((0, 1, 2), 0.3, color="#ff0000")
    renderer = Renderer()
    document = renderer.package(location, "push", tmp_path / "handover", SMALL)
    assert rgb(renderer.draw(document, tmp_path / "a.png", 4)) == rgb(renderer.frame(location, "push", tmp_path / "b.png", 0.4, SMALL))


def test_render_draws_the_first_moment(tmp_path):
    location = room().move("push", 1, eye=(2, 1.5, -2))
    assert rgb(Renderer().render(location, "push", tmp_path / "a.png", SMALL)) == rgb(Renderer().render(room(), "push", tmp_path / "b.png", SMALL))


def test_projection_agrees_with_a_moving_camera():
    location = room().move("push", 1, eye=(2, 1.5, -2), lens=35, ease="linear")
    view = Projection(location.at(0.5).shots["push"], W, H)
    assert view.eye == Vec3(0, 1.5, -2)


def test_a_blueprint_can_hold_moves():
    from srlocations import Blueprint
    location = Blueprint({"name": "b", "nodes": [{"use": "stock.table", "name": "table"}],
                          "shots": [{"name": "s", "eye": [0, 1, -3], "look_at": [0, 1, 0]}],
                          "moves": [{"what": "s", "time": 2, "eye": [1, 1, -3], "ease": "linear"},
                                    {"what": "table", "time": 2, "at": [1, 0, 0]}]}).build(Registry.default())
    assert location.duration("s") == 2
    assert location.at(1).shots["s"].eye == Vec3(0.5, 1, -3)


def test_a_film_with_a_broken_shader_is_refused(tmp_path, monkeypatch):
    for shader in SHADERS.glob("*.fs"):
        (tmp_path / shader.name).write_text("this is not glsl\n")
    monkeypatch.setattr("srlocations.looks.SHADERS", tmp_path)
    location = room().move("push", 0.2, eye=(2, 1.5, -2))
    with pytest.raises(RuntimeError, match="GLSL"):
        Renderer().clip(location, "push", tmp_path / "x.mp4", Styled(ink_toon(), W, 136, 1, fps=FPS))


def test_a_location_with_moves_can_be_published(tmp_path):
    from srlocations import SharedCatalog
    data = {"name": "b", "nodes": [{"use": "stock.table", "name": "table"}],
            "shots": [{"name": "s", "eye": [0, 1, -3], "look_at": [0, 1, 0]}], "moves": [{"what": "table", "time": 2, "at": [1, 0, 0]}]}
    catalog = SharedCatalog(tmp_path / "shared", "shared")
    catalog.publish_location("moving", data)
    assert catalog.location("moving").duration("s") == 2


def test_a_character_goes_with_its_mark(tmp_path):
    from srlocations import Cutout, Performer
    picture = tmp_path / "figure.png"
    solid_png(picture, bytes((255, 0, 0, 255)), 32)

    class Red(Performer):
        def cutout(self, pose):
            return Cutout(picture, (0, 0, 32, 32))

    location = room().mark("host", (-1, 0, 0))
    location.cast(Red(), "host")
    location.move("host", 1, at=(1, 0, 0), ease="linear")
    assert location.at(0.5).paintings[-1].items[0].actors[0].at == Vec3(0, 0, 0)
    assert set(differing(Renderer(), location, "push", SMALL, (5, 10), tmp_path).values()) == {0}


def test_a_character_changes_pose_when_its_key_arrives(tmp_path):
    from srlocations import Cutout, Performer
    pictures = {name: solid_png(tmp_path / f"{name}.png", rgba, 32)
                for name, rgba in (("red", bytes((255, 0, 0, 255))), ("blue", bytes((0, 0, 255, 255))))}

    class Painted(Performer):
        def cutout(self, pose):
            return Cutout(pictures[pose.get("colour", "red")], (0, 0, 32, 32))

    location = room().mark("host", (-1, 0, 0))
    actor = location.cast(Painted(), "host")
    location.move(actor, 0.5, pose={"colour": "blue"}, height=1.2)
    location.move("host", 1, at=(1, 0, 0), ease="linear")
    assert location.at(0.4).paintings[-1].items[0].actors[0].pose == {}
    assert location.at(0.5).paintings[-1].items[0].actors[0].pose == {"colour": "blue"}
    assert actor.pose == {}  # the actor itself stays
    assert set(differing(Renderer(), location, "push", SMALL, (2, 5, 8), tmp_path).values()) == {0}
    with pytest.raises(MotionError, match="not cast here"):
        location.move(type(actor)(Painted(), (0, 0, 0)), 1, height=2)
    with pytest.raises(MotionError, match="cannot move 'at'"):
        location.move(actor, 1, at=(0, 0, 0))


def test_motion_blur_smears_what_moves_and_leaves_ink_and_paint_sharp(tmp_path):
    location = camera_move()
    location.paint("notes").disc((0, 1, 2), 0.2, color="#ff0000")
    blurred = Renderer().compile(location, "push", Styled(ink_toon(), W, H, 1, fps=FPS, blur=180))
    project = deep(blurred, "project")[0].attributes()
    assert project["motionBlur"] in (True, "true") and float(project["shutterAngle"]) == 180
    assert all(group.attributes().get("motionBlur") == "off" for group in deep(blurred, "group") if group.id.startswith(("ink", "paint-")))
    assert "motionBlur" not in deep(Renderer().compile(room(), "push", Styled(ink_toon(), W, H, 1, blur=180)), "project")[0].attributes()
    frames = differing(Renderer(), location, "push", Shaded(W, H, 1, fps=FPS, blur=180), (5,), tmp_path)
    assert frames[5] > 0  # a blurred frame is not a still: the still has no shutter


def test_a_film_of_an_odd_size_is_refused(tmp_path):
    with pytest.raises(MotionError, match="even"):
        Renderer().clip(camera_move(), "push", tmp_path / "x.mp4", Shaded(W, 135, 1, fps=FPS))


def test_add_sets_fields_on_a_node_it_is_given():
    location = Location("l")
    assert location.add(Box(size=(1, 1, 1)), at=(1, 0, 2), name="crate").at == (1, 0, 2)
    with pytest.raises(TypeError, match="no field among colour"):
        location.add(Box(), colour="red")


def test_traced_follows_a_moving_camera(tmp_path):
    location = room().move("push", 0.2, eye=(2, 1.5, -2))
    scene = Renderer().compile(location, "push", "stock.traced", width=W, height=H, samples=2, bounces=1, fps=FPS)
    assert any(animate.property == "x" for animate in deep(scene, "animate"))


def test_a_moving_shot_goes_into_an_archive(tmp_path):
    archive = Renderer().archive(room().move("push", 0.2, eye=(2, 1.5, -2)), "push", tmp_path / "push.vpkg.zip", SMALL)
    assert archive.stat().st_size
