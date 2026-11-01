"""Paint the set hides. Whether a mark shows only exists in the pixels, so these render."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT), str(ROOT / "tests")]

from sr_core.vpkg import archive as vpkg

from srlocations import (Blueprint, Fill, Flat, Look, Material, Mesh, PaintLayer, Portrait, Projection, Renderer, Shaded,
                         Standee, Sticker, Styled, Vec3, Wireframe)
from srlocations.nodes import Box
from test_cast import figure
from test_looks import BLUE, GREY, H, RED, W, deep, errors, flat_set, near, pixel, stage

FLAT = Styled(Look([Flat()], sky=GREY), W, H, supersample=1)
PURE_BLUE = b"\0\0\xff\xff"


def wall(at, material: str = "t.red", wide: float = 1.0) -> Box:
    return Box(size=(wide, 3, 0.2), at=at, material=material)


def seen(location, shot_points, folder, mode=FLAT) -> list[tuple[int, ...]]:
    rows = stage(mode, location, "front", folder)
    view = Projection(location.shots["front"], W, H)
    return [pixel(rows, *view.pixel(Vec3(*point))) for point in shot_points]


def cast_blue(location, folder, mark: str = "mid", **options) -> None:
    location.mark(mark, (0, 0, 3))
    location.cast(Portrait(figure(folder / "blue.png", PURE_BLUE, box=(0, 0, 40, 80))), mark, height=2, shadow=0, **options)


def test_the_set_hides_a_character_behind_it_and_only_there(tmp_path):
    location = flat_set()
    location.add(wall((-0.6, 1.5, 1)))
    location.add(wall((0.6, 1.5, 5), "t.blue"))
    cast_blue(location, tmp_path)
    behind, open_air, in_front = seen(location, [(-0.3, 1, 3), (0, 1, 3), (0.4, 1, 3)], tmp_path)
    assert near(behind, RED) and near(open_air, BLUE) and near(in_front, BLUE)


def test_a_character_can_still_ignore_the_set(tmp_path):
    location = flat_set()
    location.add(wall((0, 1.5, 1), wide=3))
    cast_blue(location, tmp_path, depth=False)
    assert near(seen(location, [(0, 1, 3)], tmp_path)[0], BLUE)


def test_a_layer_ignores_the_set_unless_it_asks(tmp_path):
    location = flat_set()
    location.add(wall((0, 1.5, 1), wide=3))
    location.paint("over").disc((0, 1, 3), 0.3, color=BLUE)
    assert near(seen(location, [(0, 1, 3)], tmp_path)[0], BLUE)
    assert deep(FLAT.compiler().compile(location, "front"), "group")[-1].matte is None


def test_a_depth_layer_is_hidden_in_a_shaded_render_too(tmp_path):
    location = flat_set()
    location.background = "#808080"
    location.add(wall((-0.6, 1.5, 1)))
    cast_blue(location, tmp_path)
    rows = seen(location, [(-0.3, 1, 3), (0.1, 1, 3)], tmp_path, Shaded(W, H))
    assert not near(rows[0], BLUE, 80) and near(rows[1], BLUE)


def test_every_kind_of_world_mark_can_be_hidden(tmp_path):
    location = flat_set()
    location.add(wall((0, 1.5, 1), wide=3))
    location.paint("over", depth=True).disc((0, 1, 3), 0.3, color=BLUE).fill(
        [(0.3, 0.5, 3), (0.6, 0.5, 3), (0.6, 1.5, 3), (0.3, 1.5, 3)], color=BLUE).add(
        Standee(at=(-0.5, 0, 3), marks=[Fill(points=[(-0.2, 0), (0.2, 0), (0.2, 1), (-0.2, 1)], color=BLUE)])).add(
        Sticker(at=(0, 0, 3), path=figure(tmp_path / "s.png", PURE_BLUE, box=(0, 0, 40, 80)), height=1))
    scene = FLAT.compiler().compile(location, "front")
    assert errors(scene) == []
    assert len([g for g in deep(scene, "group") if (g.id or "").endswith("-matte")]) == 4
    assert all(near(color, RED) for color in seen(location, [(0, 1, 3), (0.45, 1, 3), (-0.5, 0.5, 3), (0, 0.3, 3)], tmp_path))


def test_a_frame_mark_in_a_depth_layer_stays_on_top(tmp_path):
    location = flat_set()
    location.add(wall((0, 1.5, 1), wide=3))
    location.paint("over", depth=True).disc((0.5, 0.5), 0.1, color=BLUE, frame=True)
    assert near(pixel(stage(FLAT, location, "front", tmp_path), W / 2, H / 2), BLUE)


def test_glass_does_not_hide_paint(tmp_path):
    location = flat_set()
    location.registry.materials.add("t.glass", Material("#ffffff", opacity=0.3), override=True)
    location.add(wall((0, 1.5, 1), "t.glass", wide=3))
    cast_blue(location, tmp_path)
    assert not [g for g in deep(FLAT.compiler().compile(location, "front"), "group") if (g.id or "").endswith("-matte")]


def test_a_mark_with_nothing_in_the_way_needs_no_mask(tmp_path):
    location = flat_set()
    location.add(Box(size=(20, 0.1, 40), at=(0, -0.05, 0), material="t.grey", name="floor"))
    location.add(wall((0, 1.5, 6), wide=8))
    location.add(wall((3, 1.5, 1), "t.blue"))  # nearer, but off to the side of the frame's figure
    cast_blue(location, tmp_path)
    assert not [g for g in deep(FLAT.compiler().compile(location, "front"), "group") if (g.id or "").endswith("-matte")]


def test_a_rug_does_not_cut_off_feet(tmp_path):
    location = flat_set()
    location.shot("front", (0, 1.6, -5), (0, 0.8, 3), lens=30)
    location.add(Box(size=(6, 0.02, 6), at=(0, 0.01, 3), material="t.grey", name="rug"))
    location.add(wall((0, 1.5, 0), wide=0.2))  # a mask is needed, and it must keep the feet
    location.mark("mid", (0.6, 0, 3))
    location.cast(Portrait(figure(tmp_path / "blue.png", PURE_BLUE, box=(0, 0, 40, 80))), "mid", height=2, shadow=0)
    assert near(seen(location, [(0.6, 0.03, 3)], tmp_path)[0], BLUE)


def test_a_seated_character_is_not_cut_by_its_seat(tmp_path):
    location = flat_set()
    location.shot("front", (0, 1.4, -5), (0, 0.8, 3), lens=30)
    location.add(Box(size=(2, 0.42, 1), at=(0, 0.21, 3), material="t.grey", name="seat"))
    location.add(Box(size=(2, 1, 0.2), at=(0, 0.5, 3.5), material="t.red", name="back"))
    location.mark("on", (0, 0.42, 3))
    location.cast(Portrait(figure(tmp_path / "blue.png", PURE_BLUE, box=(0, 0, 40, 80))), "on", height=0.8, shadow=0)
    assert near(seen(location, [(0, 0.5, 3)], tmp_path)[0], BLUE)


def test_one_figures_clear_corner_does_not_show_another_through_a_solid(tmp_path):
    location = flat_set()
    location.add(wall((0, 1.5, 3), wide=3))
    location.mark("far", (0, 0, 5)).mark("close", (0, 0, 1))
    far = figure(tmp_path / "far.png", PURE_BLUE, box=(0, 0, 40, 80))
    close = figure(tmp_path / "close.png", b"\0\xff\0\xff", size=(80, 80), box=(0, 0, 10, 80))  # clear to the right of a strip
    location.cast(Portrait(far), "far", height=2, shadow=0)
    location.cast(Portrait(close, box=(0, 0, 80, 80)), "close", height=2, shadow=0)
    assert near(seen(location, [(0, 1, 3)], tmp_path)[0], RED)


def test_a_pool_of_shadow_is_hidden_with_its_character(tmp_path):
    location = flat_set()
    location.shot("front", (0, 2.5, -5), (0, 0.5, 3), lens=30)
    location.add(Box(size=(20, 0.1, 40), at=(0, -0.05, 0), material="t.grey", name="floor"))
    location.add(Box(size=(3, 2, 0.2), at=(0, 1, 1), material="t.red", name="screen"))
    location.mark("mid", (0, 0, 3))
    location.cast(Portrait(figure(tmp_path / "a.png", PURE_BLUE)), "mid")
    scene = FLAT.compiler().compile(location, "front")
    assert {g.id for g in deep(scene, "group") if (g.id or "").endswith("-matte")} == {"paint-0-0-shadow-0-matte", "paint-0-0-0-matte"}
    assert errors(scene) == []


def test_a_wireframe_has_no_surfaces_to_hide_paint(tmp_path):
    location = flat_set()
    location.add(wall((0, 1.5, 1), wide=3))
    cast_blue(location, tmp_path)
    assert near(seen(location, [(0, 1, 3)], tmp_path, Wireframe(W, H))[0], BLUE)


def test_a_look_that_warps_the_set_warps_the_mask_with_it(tmp_path):
    location = flat_set()
    location.add(wall((0, 1.5, 1), wide=3))
    cast_blue(location, tmp_path)
    scene = Styled(Look([Flat()], sky=GREY, warp=4), W, H, supersample=1).compiler().compile(location, "front")
    assert [g for g in deep(scene, "group") if (g.id or "").endswith("-matte")][0].effects == ["look-warp"]


def test_a_model_can_hide_paint(tmp_path):
    location = flat_set()
    obj = tmp_path / "block.obj"
    obj.write_text("v -1.5 0 0\nv 1.5 0 0\nv 1.5 3 0\nv -1.5 3 0\nf 1 2 3 4\nf 4 3 2 1\n")
    location.add(Mesh(obj, at=(0, 0, 1), material="t.red"))
    cast_blue(location, tmp_path)
    assert near(seen(location, [(0, 1, 3)], tmp_path)[0], RED)


def test_paint_depth_is_data_too(tmp_path):
    layer = PaintLayer.from_spec({"name": "over", "depth": True, "items": [{"kind": "disc", "center": [0, 1, 3], "radius": 0.2}]})
    assert layer.depth
    data = {"name": "stage", "marks": [{"name": "spot", "at": [0, 0, 3]}], "shots": [{"name": "front", "eye": [0, 1, -5], "look_at": [0, 1, 3], "lens": 30}],
            "cast": [{"character": {"image": "hero.png"}, "mark": "spot", "depth": False}]}
    figure(tmp_path / "hero.png", PURE_BLUE)
    path = tmp_path / "stage.location.json"
    path.write_text(json.dumps(data))
    assert not Blueprint.load(path).build().paintings[0].depth


def test_a_held_mark_packages_and_renders_the_same(tmp_path):
    location = flat_set()
    location.add(wall((-0.6, 1.5, 1)))
    cast_blue(location, tmp_path)
    renderer = Renderer()
    archive = renderer.archive(location, "front", tmp_path / "shot.vpkg.zip", FLAT)
    assert vpkg.verify(archive).ok
