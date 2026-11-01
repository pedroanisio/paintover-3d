"""A tiled texture is measured in the world, so it runs on across pieces of a wall and around corners."""
import sys
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT), str(ROOT / "tests")]

from test_looks import H, W, bands, deep, errors, flat_set, half_png, pixel, stage

from srlocations import Box, Cylinder, Flat, Group, Look, Renderer, Styled, Texture
from srlocations.geometry import Transform, Vec3
from srlocations.sheets import sheet, world_uv
from srlocations.stock.prefabs import Wall, window


def stripes(tmp_path, tile=1.0):
    return Look([Flat()], textures={"": Texture(half_png(tmp_path / "half.png"), tile=tile)})


def row(rows, y=H * 0.4):
    return [pixel(rows, x, y) for x in range(W)]


def differs(a, b):
    return sum(any(abs(p - q) > 32 for p, q in zip(x, y)) for x, y in zip(a, b))


def test_a_wall_in_two_pieces_shows_what_one_piece_shows(tmp_path):
    whole, pieces = flat_set(), flat_set()
    whole.add(Box((6, 3, 0.2), at=(0, 1.5, 3), material="t.grey"))
    pieces.add(Box((2.3, 3, 0.2), at=(-1.85, 1.5, 3), material="t.grey"))
    pieces.add(Box((3.7, 3, 0.2), at=(1.15, 1.5, 3), material="t.grey"))
    mode = Styled(stripes(tmp_path), W, H, 1)
    assert differs(row(stage(mode, whole, "front", tmp_path)), row(stage(mode, pieces, "front", tmp_path))) <= 2


def test_the_courses_run_on_past_a_window(tmp_path):
    """The pieces above and below a window are separate solids: the row through each must match a wall with no window."""
    solid, holed = flat_set(), flat_set()
    solid.add(Wall(6, 3, material="t.grey", at=(0, 0, 3)))
    holed.add(Wall(6, 3, [window(0, width=1.6)], material="t.grey", at=(0, 0, 3)))
    mode = Styled(stripes(tmp_path), W, H, 1)
    plain, cut = stage(mode, solid, "front", tmp_path), stage(mode, holed, "front", tmp_path)
    below, above = H * 0.585, H * 0.22  # at y = 0.45 and 2.8, on the pieces under and over the window
    assert bands(plain, below) >= 8
    assert differs(row(plain, below), row(cut, below)) <= 2 and differs(row(plain, above), row(cut, above)) <= 2


@pytest.mark.parametrize("x,z", [(3, 3), (3, -3), (-3, 3), (-3, -3)])
def test_two_walls_agree_at_every_corner_of_a_room(x, z):
    corner = Vec3(x, 1.2, z)
    faces_x, faces_z = Vec3(-1 if x > 0 else 1, 0, 0), Vec3(0, 0, -1 if z > 0 else 1)
    assert world_uv(corner, faces_x) == pytest.approx(world_uv(corner, faces_z))


def test_a_floor_takes_its_uvs_from_the_ground():
    assert world_uv(Vec3(2, 0, 5), Vec3(0, 1, 0)) == (2, 5)
    assert world_uv(Vec3(2, 3, 5), Vec3(0, -1, 0)) == (2, 5)


def test_a_turned_wall_keeps_its_size_and_shows_its_front(tmp_path):
    counts = []
    for yaw in (0, 180):
        location = flat_set()
        location.add(Group(children=[Box((6, 3, 0.2), at=(0, 1.5, 0), material="t.grey")], at=(0, 0, 3), yaw=yaw))
        counts.append(bands(stage(Styled(stripes(tmp_path), W, H, 1), location, "front", tmp_path), H / 2))
    assert abs(counts[0] - counts[1]) <= 1 and counts[0] >= 8


def test_a_same_box_in_the_same_place_is_one_file(tmp_path, monkeypatch):
    monkeypatch.setenv("SRLOCATIONS_CACHE", str(tmp_path / "cache"))
    box, place = Box((1, 2, 3)), Transform.at((1, 0, 0))
    assert sheet(box, place, 1.0).path == sheet(box, place, 1.0).path
    assert sheet(box, place, 1.0).path != sheet(box, Transform.at((2, 0, 0)), 1.0).path
    assert len(list((tmp_path / "cache/sheets").iterdir())) == 2


def test_a_look_is_valid_and_a_package_carries_its_sheets(tmp_path, monkeypatch):
    monkeypatch.setenv("SRLOCATIONS_CACHE", str(tmp_path / "cache"))
    location = flat_set()
    location.add(Wall(6, 3, [window(0)], material="t.grey", at=(0, 0, 3)))
    mode = Styled(stripes(tmp_path), W, H, 1)
    scene = Renderer().compile(location, "front", mode)
    assert errors(scene) == []
    assert deep(scene, "mesh") and all(node.src.endswith(".obj") for node in deep(scene, "mesh"))
    archive = Renderer().archive(location, "front", tmp_path / "wall.vpkg.zip", mode)
    assert sum(name.endswith(".obj") for name in zipfile.ZipFile(archive).namelist()) == len(deep(scene, "mesh"))
    document = Renderer().package(location, "front", tmp_path / "moved", mode)
    for made in (tmp_path / "cache/sheets").iterdir():
        made.unlink()
    assert Renderer().draw(document, tmp_path / "shot.png").is_file()


def test_round_solids_keep_their_panels(tmp_path):
    location = flat_set()
    location.add(Cylinder(1, 3, at=(0, 0, 3), material="t.grey"))
    scene = Renderer().compile(location, "front", Styled(stripes(tmp_path), W, H, 1))
    assert not deep(scene, "mesh")


def test_a_texture_that_fills_each_face_stays_a_box(tmp_path):
    location = flat_set()
    location.add(Box((6, 3, 0.2), at=(0, 1.5, 3), material="t.grey"))
    scene = Renderer().compile(location, "front", Styled(stripes(tmp_path, tile=None), W, H, 1))
    assert not deep(scene, "mesh")
